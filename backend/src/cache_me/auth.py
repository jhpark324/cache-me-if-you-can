"""Official SIWC OSS public-client flow. No Codex credentials or API keys."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse
from uuid import uuid4

import httpx
import jwt
from openai import AsyncOpenAI, APIError, APIConnectionError, APITimeoutError
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from .config import atomic_private_json
from .brand import PRODUCT_NAME
from .model_errors import ACTION_REQUIRED_MODEL_ERRORS

ISSUER = 'https://auth.openai.com'
AUTHORIZE = ISSUER + '/api/accounts/authorize'
TOKEN = ISSUER + '/api/accounts/oauth/token'
RESOURCE = 'https://api.openai.com/v1'
_UNSET = object()


class AuthError(Exception):
    def __init__(self, code, message, *, details=None, retryable=False):
        self.code, self.message = code, message
        self.details, self.retryable = details, retryable
        super().__init__(message)

    def as_dict(self):
        return {'code': self.code, 'message': self.message, 'retryable': self.retryable, 'details': self.details}


def model_failure(*, status=None, code=None, param=None, request_id=None):
    """Preserve safe diagnostic identifiers without provider bodies or credentials."""
    def identifier(value):
        return value if isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9_.\[\]-]{1,160}', value) else None
    details = {k: v for k, v in {'http_status': status, 'provider_code': identifier(code),
                               'parameter': identifier(param), 'request_id': identifier(request_id)}.items() if v is not None}
    if code == 'subscription_sharing_usage_limit_exceeded':
        return AuthError('MODEL_USAGE_LIMIT', 'ChatGPT의 앱 사용 한도에 도달했습니다. ChatGPT 설정의 사용량을 확인해 주세요.', details=details)
    if code in ('subscription_sharing_unsupported_capability', 'subscription_sharing_route_not_supported') or status == 400:
        return AuthError('MODEL_REQUEST_INVALID', '모델이 지원하지 않는 요청 형식입니다. 앱의 모델 연결 설정을 확인해야 합니다.', details=details)
    if status == 401 or code == 'subscription_sharing_invalid_user':
        return AuthError('MODEL_AUTH_REJECTED', '모델이 현재 계정의 인증을 수락하지 않았습니다. 설정에서 연결 상태를 확인해 주세요.', details=details)
    if status == 403 or code in ('subscription_sharing_user_not_eligible', 'chatpass_v2_scope_not_authorized',
                                'chatpass_v2_invalid_authorization_context'):
        return AuthError('MODEL_PERMISSION_DENIED', '계정 또는 워크스페이스 정책이 모델 사용을 허용하지 않습니다.', details=details)
    if status == 429:
        return AuthError('MODEL_RATE_LIMIT', '모델 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.', details=details, retryable=True)
    if status in (500, 502, 503, 504) or code in ('subscription_sharing_usage_unavailable', 'subscription_sharing_user_unavailable'):
        return AuthError('MODEL_TEMPORARILY_UNAVAILABLE', '모델 서비스가 일시적으로 응답하지 않습니다. 잠시 후 다시 시도해 주세요.', details=details, retryable=True)
    return AuthError('MODEL_FAILED', '모델이 응답을 완료하지 못했습니다. 사용 한도와 연결 상태를 확인해 주세요.', details=details)


class ModelAuth:
    def __init__(self, data_dir: Path, origin: str):
        self.path = data_dir / 'credentials.json'
        self.origin = origin
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {
            'host_id': 'urn:uuid:' + str(uuid4()), 'accounts': {}, 'active': None,
        }
        # Older installations retained every account. Keep only the current
        # registration, including its client mapping for later reauthorization.
        current_id = self.data.get('active')
        current = self.data['accounts'].get(current_id)
        accounts = {current_id: current} if current else {}
        migrated = self.data['accounts'] != accounts or (current is None and current_id is not None)
        self.data['accounts'] = accounts
        self.data['active'] = current_id if current else None
        if not self.path.exists() or migrated:
            self.save()
        self.pending: dict[str, dict] = {}
        self.login_generations: dict[str, int] = {}
        self.inflight_logins: dict[str, dict] = {}
        self.auth_generation = 0
        self.model_generation = 0
        self.request_generation = 0
        self.request_blocked: AuthError | None = None
        self.lock = asyncio.Lock()
        self.models: list[dict] = []
        self.last_error = None

    def save(self):
        atomic_private_json(self.path, self.data)

    def active(self):
        return self.data['accounts'].get(self.data.get('active'))

    def resume_requests(self):
        """Resume only after an explicit, successfully validated user action."""
        self.request_generation += 1
        self.request_blocked = None

    def status(self, session_id: str | None = None):
        account = self.active() or {}
        return {
            'connected': bool(account.get('access_token')),
            'plan_enabled': 'chatgpt.tokens.use.direct' in account.get('scopes', []),
            'email': account.get('email'), 'active_account_id': self.data.get('active'),
            'accounts': [{'id': key, 'email': a.get('email'), 'label': (a.get('email') or 'ChatGPT') + ' · ' + key[-6:]} for key, a in self.data['accounts'].items()],
            'selected_model': account.get('model'), 'models': self.models,
            'selected_reasoning_effort': account.get('reasoning_effort'),
            'request_blocked': {'code': self.request_blocked.code, 'message': self.request_blocked.message,
                                'retryable': False} if self.request_blocked else None,
            'error': self.last_error, 'pending_login': self.login_pending(session_id) if session_id else False,
        }

    def begin(self, session_id: str, account_id: str | None = None, *, replace_account=False):
        if replace_account:
            account_id = None
        elif account_id is None:
            account_id = self.data.get('active')
        old = self.data['accounts'].get(account_id) if account_id else None
        if account_id and old is None:
            raise AuthError('NOT_FOUND', '등록된 계정을 찾을 수 없습니다.')
        now = time.time()
        self.login_generations[session_id] = self.login_generations.get(session_id, 0) + 1
        self.pending = {k: v for k, v in self.pending.items() if v['expires'] > now and v['session'] != session_id}
        state, nonce, verifier = (secrets.token_urlsafe(40) for _ in range(3))
        pending = {'session': session_id, 'nonce': nonce, 'verifier': verifier, 'expires': now + 600,
                   'client_id': old['client_id'] if old else 'dynamic_agent_client', 'account_id': account_id,
                   'redirect_uri': self.origin + '/auth/callback', 'auth_generation': self.auth_generation,
                   'login_generation': self.login_generations[session_id]}
        self.pending[state] = pending
        params = {
            'client_id': pending['client_id'], 'ext_agent_host_id': self.data['host_id'],
            'response_type': 'code', 'redirect_uri': pending['redirect_uri'],
            'scope': 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct',
            'resource': RESOURCE, 'state': state, 'nonce': nonce, 'code_challenge_method': 'S256',
            'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode(),
        }
        if old:
            if old.get('id_token'):
                params['id_token_hint'] = old['id_token']
            if old.get('email'):
                params['login_hint'] = old['email']
        else:
            params['agent_name_hint'] = PRODUCT_NAME
        return AUTHORIZE + '?' + urlencode(params)

    def cancel_login(self, session_id: str):
        cancelled = self.login_pending(session_id)
        self.login_generations[session_id] = self.login_generations.get(session_id, 0) + 1
        self.pending = {key: value for key, value in self.pending.items() if value['session'] != session_id}
        return {'cancelled': cancelled}

    def login_pending(self, session_id):
        return any(value['session'] == session_id and value['expires'] > time.time() and self.pending_is_current(value)
                   for value in [*self.pending.values(), *self.inflight_logins.values()])

    def pending_is_current(self, pending):
        return pending['auth_generation'] == self.auth_generation and pending['login_generation'] == self.login_generations.get(pending['session'])

    @staticmethod
    def token_expiry(tokens):
        value = tokens.get('expires_in', 3600)
        if type(value) not in (str, int) or (isinstance(value, str) and not re.fullmatch(r'[0-9]{1,12}', value)):
            raise ValueError('invalid token lifetime')
        seconds = int(value)
        if seconds <= 0:
            raise ValueError('invalid token lifetime')
        return time.time() + seconds

    async def discovery(self, client):
        response = await client.get(ISSUER + '/.well-known/openid-configuration')
        response.raise_for_status()
        doc = response.json()
        if doc.get('issuer') != ISSUER:
            raise AuthError('AUTH_INVALID', '로그인 발급자를 검증하지 못했습니다.')
        for key in ('jwks_uri', 'revocation_endpoint'):
            if key in doc and (urlparse(doc[key]).scheme != 'https' or urlparse(doc[key]).hostname != 'auth.openai.com'):
                raise AuthError('AUTH_INVALID', '인증 서버 주소를 검증하지 못했습니다.')
        return doc

    async def validate_id(self, client, token, client_id, nonce=None):
        doc = await self.discovery(client)
        response = await client.get(doc['jwks_uri'])
        response.raise_for_status()
        keyset = jwt.PyJWKSet.from_dict(response.json())
        header = jwt.get_unverified_header(token)
        key = next((k for k in keyset.keys if k.key_id == header.get('kid')), None)
        if key is None:
            raise AuthError('AUTH_INVALID', '로그인 서명을 확인하지 못했습니다.')
        claims = jwt.decode(token, key.key, algorithms=['RS256'], audience=client_id, issuer=ISSUER,
                            options={'require': ['sub', 'exp', 'iat']}, leeway=5)
        if not isinstance(claims['sub'], str) or not claims['sub'] or (nonce is not None and (not isinstance(claims.get('nonce'), str) or not secrets.compare_digest(claims['nonce'], nonce))):
            raise AuthError('AUTH_INVALID', '로그인 요청이 일치하지 않습니다.')
        audience = claims.get('aud')
        if (claims.get('azp') is not None or isinstance(audience, list) and len(audience) > 1) and claims.get('azp') != client_id:
            raise AuthError('AUTH_INVALID', '로그인 대상 앱이 일치하지 않습니다.')
        return claims

    async def callback(self, params: dict, session_id: str):
        state = params.get('state', '')
        pending = self.pending.get(state)
        if not pending or pending['expires'] <= time.time() or pending['session'] != session_id:
            raise AuthError('AUTH_INVALID', '로그인 요청이 만료되었거나 일치하지 않습니다. 다시 시작해 주세요.')
        self.pending.pop(state, None)
        if params.get('error') or not params.get('code'):
            raise AuthError('AUTH_CANCELLED', '로그인이 완료되지 않았습니다.')
        client_id = params.get('client_id') or pending['client_id']
        if client_id == 'dynamic_agent_client' or (pending['account_id'] and client_id != pending['client_id']):
            raise AuthError('AUTH_INVALID', '등록된 앱 식별자가 일치하지 않습니다.')
        self.inflight_logins[state] = pending
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(TOKEN, data={
                    'grant_type': 'authorization_code', 'client_id': client_id, 'code': params['code'],
                    'code_verifier': pending['verifier'], 'redirect_uri': pending['redirect_uri'], 'resource': RESOURCE,
                })
                response.raise_for_status()
                tokens = response.json()
                if not isinstance(tokens.get('access_token'), str) or not tokens['access_token'] or not isinstance(tokens.get('scope', ''), str):
                    raise AuthError('AUTH_INVALID', '올바른 인증 응답을 받지 못했습니다.')
                expires_at = self.token_expiry(tokens)
                claims = await self.validate_id(client, tokens['id_token'], client_id, pending['nonce'])
            key = client_id + ':' + claims['sub']
            if pending['account_id'] and key != pending['account_id']:
                raise AuthError('AUTH_INVALID', '선택한 ChatGPT 계정과 로그인 계정이 다릅니다.')
            async with self.lock:
                if not self.pending_is_current(pending):
                    raise AuthError('AUTH_CANCELLED', '취소한 로그인 결과는 반영하지 않습니다.')
                previous = self.data['accounts'].get(key, {})
                self.data['accounts'] = {key: {
                    'client_id': client_id, 'subject': claims['sub'], 'email': claims.get('email'),
                    'id_token': tokens['id_token'], 'access_token': tokens['access_token'],
                    'refresh_token': tokens.get('refresh_token'), 'scopes': tokens.get('scope', '').split(),
                    'expires_at': expires_at, 'model': previous.get('model'),
                    'reasoning_effort': previous.get('reasoning_effort'),
                }}
                self.data['active'] = key
                self.auth_generation += 1
                self.models = []
                self.save()
                self.resume_requests()
            self.last_error = None
        except AuthError:
            raise
        except (httpx.HTTPError, jwt.PyJWTError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
            raise AuthError('AUTH_FAILED', '로그인 검증에 실패했습니다. 다시 로그인해 주세요.') from None
        finally:
            self.inflight_logins.pop(state, None)

    async def access_token(self, *, force_refresh=False):
        async with self.lock:
            account = self.active()
            if not account or not account.get('access_token'):
                raise AuthError('LOGIN_REQUIRED', '설정에서 ChatGPT로 로그인해 주세요.')
            if 'chatgpt.tokens.use.direct' not in account.get('scopes', []):
                raise AuthError('PLAN_PERMISSION_REQUIRED', 'ChatGPT에서 이 앱의 모델 사용 권한을 허용해 주세요.')
            if not force_refresh and account['expires_at'] > time.time() + 60:
                return account['access_token']
            if not account.get('refresh_token'):
                raise AuthError('LOGIN_REQUIRED', '로그인이 만료되었습니다. 다시 로그인해 주세요.')
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(TOKEN, data={'grant_type': 'refresh_token', 'client_id': account['client_id'],
                        'refresh_token': account['refresh_token'], 'resource': RESOURCE})
                    if response.status_code == 401 or (response.status_code == 400 and response.headers.get('content-type', '').startswith('application/json') and response.json().get('error') in ('invalid_grant', 'invalid_client', 'unauthorized_client', 'access_denied')):
                        for key in ('access_token', 'refresh_token', 'id_token'):
                            account.pop(key, None)
                        self.save()
                        raise AuthError('LOGIN_REQUIRED', '다시 로그인해 주세요.')
                    response.raise_for_status()
                    tokens = response.json()
                    if not isinstance(tokens.get('access_token'), str) or not tokens['access_token'] or not isinstance(tokens.get('scope', ''), str):
                        raise AuthError('AUTH_REFRESH_FAILED', '올바른 갱신 응답을 받지 못했습니다.')
                    expires_at = self.token_expiry(tokens)
                    for key in ('refresh_token', 'id_token'):
                        if key in tokens and (not isinstance(tokens[key], str) or not tokens[key]):
                            raise AuthError('AUTH_REFRESH_FAILED', '올바른 갱신 응답을 받지 못했습니다.')
                    if tokens.get('id_token'):
                        claims = await self.validate_id(client, tokens['id_token'], account['client_id'])
                        if claims['sub'] != account['subject']:
                            raise AuthError('AUTH_INVALID', '갱신한 계정 정보가 일치하지 않습니다.')
                    updated = dict(account)
                    updated.update({k: tokens[k] for k in ('access_token', 'refresh_token', 'id_token') if k in tokens})
                    if 'scope' in tokens:
                        updated['scopes'] = tokens['scope'].split()
                    updated['expires_at'] = expires_at
                    account.clear()
                    account.update(updated)
                    self.save()
                    if 'chatgpt.tokens.use.direct' not in account['scopes']:
                        raise AuthError('PLAN_PERMISSION_REQUIRED', 'ChatGPT에서 이 앱의 모델 사용 권한을 허용해 주세요.')
                    return account['access_token']
            except httpx.HTTPError:
                raise AuthError('AUTH_REFRESH_FAILED', '로그인 갱신에 실패했습니다. 잠시 후 다시 시도해 주세요.', retryable=True) from None
            except (jwt.PyJWTError, ValueError, KeyError, TypeError, AttributeError):
                raise AuthError('AUTH_REFRESH_FAILED', '로그인 갱신 응답을 검증하지 못했습니다. 다시 로그인해 주세요.') from None

    async def list_models(self):
        generation, account_id = self.auth_generation, self.data.get('active')
        token = await self.access_token()
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(RESOURCE + '/models', headers={'Authorization': 'Bearer ' + token})
        except httpx.HTTPError:
            raise AuthError('MODELS_UNAVAILABLE', '모델 목록을 불러오지 못했습니다. 연결 상태를 확인하고 다시 불러와 주세요.', retryable=True) from None
        if response.status_code != 200:
            raise AuthError('MODELS_UNAVAILABLE', '계정의 모델 목록을 가져오지 못했습니다.')
        try:
            catalog = response.json().get('models')
        except (ValueError, AttributeError):
            catalog = None
        if not isinstance(catalog, list):
            raise AuthError('MODELS_UNAVAILABLE', '계정의 모델 목록을 확인하지 못했습니다. 다시 불러와 주세요.')
        if generation != self.auth_generation or account_id != self.data.get('active'):
            raise AuthError('AUTH_CANCELLED', '계정이 변경되어 이전 모델 목록을 반영하지 않습니다.')
        models, seen = [], set()
        for model in catalog:
            if not isinstance(model, dict) or model.get('visibility') != 'list' or not isinstance(model.get('slug'), str) or not model['slug'] or model['slug'] in seen:
                continue
            seen.add(model['slug'])
            name = model.get('display_name')
            item = {'slug': model['slug'], 'display_name': name if isinstance(name, str) and name else model['slug']}
            levels = model.get('supported_reasoning_levels', model.get('supported_reasoning_efforts', []))
            efforts = []
            if isinstance(levels, list):
                for level in levels:
                    if not isinstance(level, dict):
                        continue
                    effort = level.get('effort')
                    if not isinstance(effort, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', effort) or any(entry['effort'] == effort for entry in efforts):
                        continue
                    description = level.get('description')
                    efforts.append({'effort': effort, 'description': description if isinstance(description, str) else ''})
            default = model.get('default_reasoning_level', model.get('default_reasoning_effort'))
            item['supported_reasoning_efforts'] = efforts
            item['default_reasoning_effort'] = default if any(entry['effort'] == default for entry in efforts) else None
            for field in ('context_window', 'max_context_window', 'max_input_tokens', 'max_output_tokens'):
                value = model.get(field)
                if type(value) is int and value > 0:
                    item[field] = value
            tokenizer = model.get('tokenizer')
            if isinstance(tokenizer, str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}', tokenizer):
                item['tokenizer'] = tokenizer
            models.append(item)
        self.models = models
        account = self.active()
        selected = next((item for item in models if item['slug'] == account.get('model')), {})
        if account.get('reasoning_effort') is not None and not any(level['effort'] == account['reasoning_effort'] for level in selected.get('supported_reasoning_efforts', [])):
            account['reasoning_effort'] = None
            self.model_generation += 1
            self.save()
        self.last_error = None
        return self.models

    async def model_metadata(self):
        model = (self.active() or {}).get('model')
        if model and not any(item['slug'] == model for item in self.models):
            await self.list_models()
        item = next((item for item in self.models if item['slug'] == model), {})
        return {'model': model, 'context_window': item.get('context_window'),
                'max_context_window': item.get('max_context_window'), 'max_input_tokens': item.get('max_input_tokens'),
                'max_output_tokens': item.get('max_output_tokens'), 'tokenizer': item.get('tokenizer'),
                'source': 'catalog' if item else 'unavailable'}

    def select_model(self, model, reasoning_effort=_UNSET):
        account = self.active()
        selected = next((item for item in self.models if item['slug'] == model), None)
        if not account or selected is None:
            raise AuthError('MODEL_UNAVAILABLE', '계정에서 사용 가능한 모델을 선택해 주세요.')
        if reasoning_effort is _UNSET:
            reasoning_effort = account.get('reasoning_effort') if account.get('model') == model else None
        if reasoning_effort is not None and not any(level['effort'] == reasoning_effort for level in selected.get('supported_reasoning_efforts', [])):
            raise AuthError('REASONING_UNAVAILABLE', '선택한 모델에서 지원하는 추론 수준을 선택해 주세요.')
        if account.get('model') != model or account.get('reasoning_effort') != reasoning_effort:
            self.model_generation += 1
        account['model'] = model
        account['reasoning_effort'] = reasoning_effort
        self.save()
        self.resume_requests()

    async def logout(self):
        async with self.lock:
            account = self.active()
            revocation = {'token': account['refresh_token'], 'token_type_hint': 'refresh_token', 'client_id': account['client_id']} if account and account.get('refresh_token') else None
            self.auth_generation += 1
            self.pending.clear()
            if account:
                for key in ('access_token', 'refresh_token', 'id_token'):
                    account.pop(key, None)
            self.models = []
            self.save()
            self.resume_requests()
        # Local logout is already durable, including if this await is cancelled.
        confirmed = revocation is None
        if revocation:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    doc = await self.discovery(client)
                    for attempt in range(2):
                        response = await client.post(doc['revocation_endpoint'], data=revocation)
                        if response.status_code == 200:
                            confirmed = True
                            break
                        if attempt == 0:
                            await asyncio.sleep(1)
            except (httpx.HTTPError, KeyError, AuthError, ValueError, TypeError):
                pass
        return {'remote_revocation_confirmed': confirmed}

    async def generate_for_model(self, prompt: str, instructions: str, expected_model: str):
        return await self.generate(prompt, instructions, expected_model=expected_model)

    async def generate(self, prompt: str, instructions: str, *, expected_model: str | None = None):
        message = await self.generate_message([HumanMessage(content=prompt)], instructions, expected_model=expected_model)
        if message.tool_calls:
            raise AuthError('MODEL_FORMAT_ERROR', '텍스트 응답에 예상하지 않은 도구 호출이 포함되어 있습니다.')
        return message.content

    async def generate_message(self, messages: list[BaseMessage], instructions: str, *, tools: list[dict] | None = None,
                               expected_model: str | None = None, tool_choice=None) -> AIMessage:
        # Imported here so auth errors remain usable by the adapter without a cycle.
        from .chat_model import message_from_output, serialize_model_input, _field
        from .privacy import sanitize_ai_message

        generation = self.auth_generation
        account_id = self.data.get('active')
        model_generation = self.model_generation
        request_generation = self.request_generation
        model = (self.active() or {}).get('model')
        reasoning_effort = (self.active() or {}).get('reasoning_effort')
        if expected_model is not None and expected_model != model:
            raise AuthError('MODEL_CHANGED', '답변 모델이 변경되었습니다. 새 모델로 다시 요청해 주세요.')
        def check_context():
            if generation != self.auth_generation or account_id != self.data.get('active'):
                raise AuthError('LOGIN_REQUIRED', '로그인 상태가 변경되어 응답을 중지했습니다.')
            if model_generation != self.model_generation or request_generation != self.request_generation or model != (self.active() or {}).get('model') or reasoning_effort != (self.active() or {}).get('reasoning_effort'):
                raise AuthError('MODEL_CHANGED', '답변 모델이 변경되어 응답을 중지했습니다. 다시 요청해 주세요.')
        def record_failure(error):
            # Old requests must not pause a replacement account or a user's retry.
            if (generation == self.auth_generation and account_id == self.data.get('active')
                    and model_generation == self.model_generation and request_generation == self.request_generation
                    and (error.code in ACTION_REQUIRED_MODEL_ERRORS
                         or error.code == 'AUTH_REFRESH_FAILED' and not error.retryable)):
                self.request_blocked = AuthError(error.code, error.message, details=error.details)
            return error
        try:
            if self.request_blocked:
                raise self.request_blocked
            token = await self.access_token()
            check_context()
            if self.request_blocked:
                raise self.request_blocked
            if not model:
                raise AuthError('MODEL_REQUIRED', '설정에서 답변 모델을 선택해 주세요.')
            if reasoning_effort is not None:
                if not any(item['slug'] == model for item in self.models):
                    await self.list_models()
                    check_context()
                selected = next((item for item in self.models if item['slug'] == model), {})
                if not any(level['effort'] == reasoning_effort for level in selected.get('supported_reasoning_efforts', [])):
                    raise AuthError('REASONING_UNAVAILABLE', '설정에서 이 모델의 추론 수준을 다시 선택해 주세요.')
        except AuthError as exc:
            record_failure(exc)
            raise
        payload = serialize_model_input(messages, instructions, tools, tool_choice=tool_choice)
        if reasoning_effort is not None:
            payload['reasoning'] = {'effort': reasoning_effort}
        text, completed, characters, byte_count = [], False, 0, 0
        output, done_items = None, {}
        try:
            async with AsyncOpenAI(api_key=token, base_url=RESOURCE, max_retries=0, timeout=60) as client:
                # SIWC requires array input and does not accept max_output_tokens.
                check_context()
                if self.request_blocked:
                    raise self.request_blocked
                stream = await client.responses.create(model=model, **payload, store=False, stream=True)
                async with stream:
                    async for event in stream:
                        check_context()
                        if event.type in ('response.output_text.delta', 'response.function_call_arguments.delta'):
                            characters += len(event.delta)
                            byte_count += len(event.delta.encode('utf-8'))
                            if characters > 32000 or byte_count > 131072:
                                raise AuthError('MODEL_OUTPUT_LIMIT', '모델 응답이 처리 한도를 넘었습니다. 질문을 나누어 주세요.')
                            if event.type == 'response.output_text.delta':
                                text.append(event.delta)
                        elif event.type == 'response.output_item.done':
                            done_items[event.output_index] = event.item
                            # Enforce a bound before a potentially missing completed event.
                            message_from_output(list(done_items.values()))
                        elif event.type == 'response.completed':
                            output = _field(_field(event, 'response'), 'output')
                            if output is None and done_items:
                                output = [done_items[index] for index in sorted(done_items)]
                            completed = True
                        elif event.type in ('response.failed', 'response.incomplete', 'error'):
                            error = getattr(getattr(event, 'response', None), 'error', None)
                            raise model_failure(code=getattr(error, 'code', getattr(event, 'code', None)),
                                                param=getattr(error, 'param', getattr(event, 'param', None)))
        except AuthError as exc:
            record_failure(exc)
            raise
        except APITimeoutError:
            raise AuthError('MODEL_TIMEOUT', '모델 응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.', retryable=True) from None
        except APIConnectionError:
            raise AuthError('MODEL_UNAVAILABLE', '모델에 연결하지 못했습니다. 연결 상태를 확인하고 다시 시도해 주세요.', retryable=True) from None
        except APIError as exc:
            body = exc.body if isinstance(exc.body, dict) else {}
            error = body.get('error', body)
            error = error if isinstance(error, dict) else {}
            failure = model_failure(status=getattr(exc, 'status_code', None),
                code=error.get('code', getattr(exc, 'code', None)), param=error.get('param', getattr(exc, 'param', None)),
                request_id=getattr(exc, 'request_id', None))
            raise record_failure(failure) from None
        except Exception:
            raise AuthError('MODEL_UNAVAILABLE', '모델 연결에 실패했습니다. 로그인과 사용 한도를 확인해 주세요.') from None
        if not completed:
            raise AuthError('MODEL_INTERRUPTED', '응답 연결이 중단되었습니다. 다시 검색해 주세요.')
        check_context()
        message = message_from_output(output, ''.join(text))
        return sanitize_ai_message(message)
