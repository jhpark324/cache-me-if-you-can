"""Offline OAuth/JWT and model-stream boundary tests; never contact a provider."""
import asyncio
import base64
import hashlib
import json
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import cache_me.auth as auth_module
from cache_me.auth import AuthError, ISSUER, ModelAuth, RESOURCE, TOKEN

REAL_ASYNC_CLIENT = httpx.AsyncClient
CLIENT_ID = "public-test-client"


@pytest.fixture(scope="module")
def signing_keys():
    trusted = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(trusted.public_key()))
    jwk.update(kid="test-key", use="sig", alg="RS256")
    return trusted, other, {"keys": [jwk]}


def claims(nonce="nonce", **changes):
    now = int(time.time())
    return {"iss": ISSUER, "aud": CLIENT_ID, "sub": "subject-one", "iat": now,
            "exp": now + 3600, "nonce": nonce, "email": "test@example.invalid", **changes}


def signed(signing_keys, payload, *, other=False, kid="test-key"):
    return jwt.encode(payload, signing_keys[1 if other else 0], algorithm="RS256", headers={"kid": kid})


def install_transport(monkeypatch, signing_keys, token_response, requests=None, discovery_override=None):
    requests = requests if requests is not None else []
    def handle(request):
        requests.append(request)
        if str(request.url) == TOKEN:
            return httpx.Response(200, json=token_response)
        if str(request.url) == ISSUER + "/.well-known/openid-configuration":
            return httpx.Response(200, json=discovery_override or {
                "issuer": ISSUER, "jwks_uri": ISSUER + "/test/jwks", "revocation_endpoint": ISSUER + "/test/revoke",
            })
        if str(request.url) == ISSUER + "/test/jwks":
            return httpx.Response(200, json=signing_keys[2])
        raise AssertionError("Unexpected network endpoint: " + str(request.url))
    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(auth_module.httpx, "AsyncClient", lambda **kwargs: REAL_ASYNC_CLIENT(transport=transport, **kwargs))
    return requests


def login_pending(auth):
    query = parse_qs(urlparse(auth.begin("browser-session")).query)
    return query, auth.pending[query["state"][0]]


def token_payload(id_token, **changes):
    return {"id_token": id_token, "access_token": "secret-access-token", "refresh_token": "secret-refresh-token",
            "scope": "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct", "expires_in": 3600, **changes}


def prepare_expired_account(auth, **changes):
    account = {"client_id": CLIENT_ID, "subject": "subject-one", "email": "test@example.invalid",
               "access_token": "expired-secret", "refresh_token": "refresh-secret", "id_token": "old-id-token",
               "scopes": ["chatgpt.tokens.use.direct"], "expires_at": time.time() - 30, "model": "catalog-model", **changes}
    account_id = CLIENT_ID + ":subject-one"
    auth.data["accounts"][account_id] = account
    auth.data["active"] = account_id
    auth.save()
    return account_id, account


def test_callback_validates_signed_identity_and_pkce_without_exposing_secrets(tmp_path, signing_keys, monkeypatch):
    auth = ModelAuth(tmp_path, "http://127.0.0.1:8000")
    query, pending = login_pending(auth)
    token = signed(signing_keys, claims(pending["nonce"]))
    requests = install_transport(monkeypatch, signing_keys, token_payload(token))
    callback = {"state": query["state"][0], "code": "authorization-code", "client_id": CLIENT_ID}
    asyncio.run(auth.callback(callback, "browser-session"))
    posted = parse_qs(requests[0].content.decode())
    challenge = base64.urlsafe_b64encode(hashlib.sha256(posted["code_verifier"][0].encode()).digest()).rstrip(b"=").decode()
    assert posted["code"] == ["authorization-code"]
    assert posted["client_id"] == [CLIENT_ID]
    assert posted["resource"] == [RESOURCE]
    assert posted["redirect_uri"] == ["http://127.0.0.1:8000/auth/callback"]
    assert challenge == query["code_challenge"][0]
    assert auth.status()["connected"] and auth.status()["plan_enabled"]
    assert auth.data["active"] == CLIENT_ID + ":subject-one"
    assert "secret-access-token" not in json.dumps(auth.status())
    assert "secret-refresh-token" not in json.dumps(auth.status())
    assert "old-id-token" not in json.dumps(auth.status())
    calls = len(requests)
    with pytest.raises(AuthError, match="만료되었거나"):
        asyncio.run(auth.callback(callback, "browser-session"))
    assert len(requests) == calls  # A consumed state cannot initiate token exchange again.


def test_valid_identity_without_optional_email_has_a_safe_account_label(tmp_path, signing_keys, monkeypatch):
    auth = ModelAuth(tmp_path, "http://127.0.0.1:8000")
    query, pending = login_pending(auth)
    payload = claims(pending["nonce"])
    del payload["email"]
    install_transport(monkeypatch, signing_keys, token_payload(signed(signing_keys, payload)))
    asyncio.run(auth.callback({"state": query["state"][0], "code": "code", "client_id": CLIENT_ID}, "browser-session"))
    status = auth.status()
    assert status["connected"] and status["email"] is None
    assert isinstance(status["accounts"][0]["label"], str)
    assert status["accounts"][0]["label"]


@pytest.mark.parametrize("case", ["signature", "issuer", "audience", "nonce", "expired", "future_iat", "missing_sub", "unknown_kid"])
def test_callback_rejects_invalid_identity_claims_before_storing_tokens(tmp_path, signing_keys, monkeypatch, case):
    auth = ModelAuth(tmp_path, "http://127.0.0.1:8000")
    query, pending = login_pending(auth)
    payload = claims(pending["nonce"])
    if case == "issuer":
        payload["iss"] = "https://attacker.invalid"
    elif case == "audience":
        payload["aud"] = "another-client"
    elif case == "nonce":
        payload["nonce"] = "another-login"
    elif case == "expired":
        payload["exp"] = int(time.time()) - 60
    elif case == "future_iat":
        payload["iat"] = int(time.time()) + 3600
    elif case == "missing_sub":
        del payload["sub"]
    token = signed(signing_keys, payload, other=case == "signature", kid="unknown" if case == "unknown_kid" else "test-key")
    install_transport(monkeypatch, signing_keys, token_payload(token))
    with pytest.raises(AuthError) as caught:
        asyncio.run(auth.callback({"state": query["state"][0], "code": "authorization-code", "client_id": CLIENT_ID}, "browser-session"))
    assert auth.data["accounts"] == {}
    assert not auth.status()["connected"]
    assert "secret-access-token" not in str(caught.value)
    assert "secret-refresh-token" not in str(caught.value)


@pytest.mark.parametrize("override", [
    {"issuer": "https://attacker.invalid", "jwks_uri": ISSUER + "/test/jwks"},
    {"issuer": ISSUER, "jwks_uri": "https://attacker.invalid/jwks"},
    {"issuer": ISSUER, "jwks_uri": "http://auth.openai.com/jwks"},
    {"issuer": ISSUER, "jwks_uri": ISSUER + "/test/jwks", "revocation_endpoint": "https://attacker.invalid/revoke"},
])
def test_discovery_does_not_follow_untrusted_endpoints(tmp_path, signing_keys, monkeypatch, override):
    auth = ModelAuth(tmp_path, "http://127.0.0.1:8000")
    query, pending = login_pending(auth)
    token = signed(signing_keys, claims(pending["nonce"]))
    requests = install_transport(monkeypatch, signing_keys, token_payload(token), discovery_override=override)
    with pytest.raises(AuthError):
        asyncio.run(auth.callback({"state": query["state"][0], "code": "authorization-code", "client_id": CLIENT_ID}, "browser-session"))
    assert not auth.status()["connected"]
    assert all(request.url.host == "auth.openai.com" and request.url.scheme == "https" for request in requests)


def test_reauthorization_cannot_replace_selected_account_with_another_identity(tmp_path, signing_keys, monkeypatch):
    auth = ModelAuth(tmp_path, "http://127.0.0.1:8000")
    account_id, account = prepare_expired_account(auth)
    query = parse_qs(urlparse(auth.begin("browser-session", account_id)).query)
    pending = auth.pending[query["state"][0]]
    install_transport(monkeypatch, signing_keys, token_payload(signed(signing_keys, claims(pending["nonce"], sub="another-subject"))))
    with pytest.raises(AuthError, match="다릅니다"):
        asyncio.run(auth.callback({"state": query["state"][0], "code": "code", "client_id": CLIENT_ID}, "browser-session"))
    assert auth.data["active"] == account_id
    assert auth.active()["access_token"] == "expired-secret"
    assert len(auth.data["accounts"]) == 1


def test_refresh_requires_same_signed_subject_and_preserves_previous_credentials_on_failure(tmp_path, signing_keys, monkeypatch):
    auth = ModelAuth(tmp_path, "http://127.0.0.1:8000")
    prepare_expired_account(auth)
    install_transport(monkeypatch, signing_keys, token_payload(signed(signing_keys, claims(sub="another-subject"))))
    with pytest.raises(AuthError, match="계정 정보가 일치하지"):
        asyncio.run(auth.access_token())
    assert auth.active()["access_token"] == "expired-secret"
    assert auth.active()["refresh_token"] == "refresh-secret"


def test_refresh_rotates_credentials_after_validation(tmp_path, signing_keys, monkeypatch):
    auth = ModelAuth(tmp_path, "http://127.0.0.1:8000")
    prepare_expired_account(auth)
    requests = install_transport(monkeypatch, signing_keys, token_payload(signed(signing_keys, claims())))
    assert asyncio.run(auth.access_token()) == "secret-access-token"
    assert auth.active()["refresh_token"] == "secret-refresh-token"
    posted = parse_qs(requests[0].content.decode())
    assert posted["grant_type"] == ["refresh_token"]
    assert posted["client_id"] == [CLIENT_ID]
    assert posted["refresh_token"] == ["refresh-secret"]


@pytest.mark.parametrize("payload,expected_code", [
    ({"access_token": "new-but-unscoped", "scope": "openid profile", "expires_in": 3600}, "PLAN_PERMISSION_REQUIRED"),
    ({"scope": "chatgpt.tokens.use.direct", "expires_in": 3600}, "AUTH_REFRESH_FAILED"),
])
def test_refresh_does_not_reuse_missing_token_or_dropped_permission(tmp_path, signing_keys, monkeypatch, payload, expected_code):
    auth = ModelAuth(tmp_path, "http://127.0.0.1:8000")
    prepare_expired_account(auth)
    install_transport(monkeypatch, signing_keys, payload)
    with pytest.raises(AuthError) as caught:
        asyncio.run(auth.access_token())
    assert caught.value.code == expected_code


class FakeStream:
    def __init__(self, events):
        self.events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def __aiter__(self):
        async def iterate():
            for event in self.events:
                if isinstance(event, Exception):
                    raise event
                yield SimpleNamespace(**event)
        return iterate()


def install_model_stream(monkeypatch, events):
    recorded = {}
    class FakeOpenAI:
        def __init__(self, **kwargs):
            recorded["client"] = kwargs
            self.responses = SimpleNamespace(create=self.create)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def create(self, **kwargs):
            recorded["request"] = kwargs
            return FakeStream(events)
    monkeypatch.setattr(auth_module, "AsyncOpenAI", FakeOpenAI)
    return recorded


def test_model_output_is_returned_only_after_completed_event(tmp_path, monkeypatch):
    auth = ModelAuth(tmp_path, "http://127.0.0.1:8000")
    prepare_expired_account(auth, expires_at=time.time() + 3600)
    recorded = install_model_stream(monkeypatch, [
        {"type": "response.output_text.delta", "delta": "완료된 "},
        {"type": "response.output_text.delta", "delta": "응답"},
        {"type": "response.completed"},
    ])
    assert asyncio.run(auth.generate("질문 원문", "시스템 지침")) == "완료된 응답"
    assert recorded["request"]["store"] is False
    assert recorded["request"]["stream"] is True
    assert recorded["request"]["model"] == "catalog-model"
    assert recorded["request"]["input"] == [{"role": "user", "content": "질문 원문"}]
    assert "max_output_tokens" not in recorded["request"]
    assert recorded["client"]["base_url"] == RESOURCE
    assert recorded["client"]["max_retries"] == 0


@pytest.mark.parametrize("tail,code", [
    ([], "MODEL_INTERRUPTED"),
    ([{"type": "response.failed"}], "MODEL_FAILED"),
    ([{"type": "response.incomplete"}], "MODEL_FAILED"),
    ([{"type": "error"}], "MODEL_FAILED"),
    ([RuntimeError("secret-provider-payload")], "MODEL_UNAVAILABLE"),
])
def test_partial_model_text_is_never_returned_as_a_completed_answer(tmp_path, monkeypatch, tail, code):
    auth = ModelAuth(tmp_path, "http://127.0.0.1:8000")
    prepare_expired_account(auth, expires_at=time.time() + 3600)
    install_model_stream(monkeypatch, [{"type": "response.output_text.delta", "delta": "미검증 부분응답"}, *tail])
    with pytest.raises(AuthError) as caught:
        asyncio.run(auth.generate("질문", "지침"))
    assert caught.value.code == code
    assert "미검증 부분응답" not in str(caught.value)
    assert "secret-provider-payload" not in str(caught.value)


def test_model_output_limit_rejects_unbounded_stream(tmp_path, monkeypatch):
    auth = ModelAuth(tmp_path, "http://127.0.0.1:8000")
    prepare_expired_account(auth, expires_at=time.time() + 3600)
    install_model_stream(monkeypatch, [
        {"type": "response.output_text.delta", "delta": "x" * 32001},
        {"type": "response.completed"},
    ])
    with pytest.raises(AuthError) as error:
        asyncio.run(auth.generate("질문", "지침"))
    assert error.value.code == 'MODEL_OUTPUT_LIMIT'


def test_provider_error_retains_safe_details_without_secret_body():
    error = auth_module.model_failure(status=400, code='subscription_sharing_unsupported_capability',
        param='max_output_tokens', request_id='req_safe_123')
    assert error.code == 'MODEL_REQUEST_INVALID'
    assert error.as_dict()['details']['parameter'] == 'max_output_tokens'
    assert error.as_dict()['details']['request_id'] == 'req_safe_123'
    assert auth_module.model_failure(status=503).retryable is True
    assert auth_module.model_failure(status=429, code='subscription_sharing_usage_limit_exceeded').retryable is False
