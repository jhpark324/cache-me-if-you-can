"""OAuth lifecycle races using fake credentials and isolated HTTP transports."""
import asyncio
import json
import time
from urllib.parse import parse_qs

import httpx
import pytest

import second_brain.auth as auth_module
from second_brain.auth import AuthError, ISSUER, ModelAuth, RESOURCE, TOKEN
from test_auth_contract import (CLIENT_ID, REAL_ASYNC_CLIENT, claims, login_pending,
                                prepare_expired_account, signed, signing_keys, token_payload, install_model_stream, FakeStream)


def transport(monkeypatch, handler):
    mock = httpx.MockTransport(handler)
    monkeypatch.setattr(auth_module.httpx, 'AsyncClient', lambda **kwargs: REAL_ASYNC_CLIENT(transport=mock, **kwargs))


def discovery():
    return httpx.Response(200, json={'issuer': ISSUER, 'jwks_uri': ISSUER + '/test/jwks', 'revocation_endpoint': ISSUER + '/test/revoke'})


def test_concurrent_expired_requests_share_one_refresh(tmp_path, monkeypatch):
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    prepare_expired_account(auth)
    calls = []
    async def handle(request):
        assert str(request.url) == TOKEN
        calls.append(parse_qs(request.content.decode()))
        await asyncio.sleep(0)
        return httpx.Response(200, json={'access_token': 'new-token', 'refresh_token': 'rotated-token', 'expires_in': 3600})
    transport(monkeypatch, handle)
    async def run():
        return await asyncio.gather(auth.access_token(), auth.access_token(), auth.access_token())
    assert asyncio.run(run()) == ['new-token'] * 3
    assert len(calls) == 1
    assert auth.active()['refresh_token'] == 'rotated-token'
    assert json.loads(auth.path.read_text())['accounts'][auth.data['active']]['refresh_token'] == 'rotated-token'


def test_explicit_refresh_does_not_require_editing_stored_expiry(tmp_path, monkeypatch):
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    prepare_expired_account(auth, expires_at=time.time() + 3600)
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={'access_token': 'explicitly-refreshed', 'refresh_token': 'rotated-once', 'expires_in': 3600})
    transport(monkeypatch, handle)
    assert asyncio.run(auth.access_token()) == 'expired-secret'
    assert requests == []
    assert asyncio.run(auth.access_token(force_refresh=True)) == 'explicitly-refreshed'
    assert len(requests) == 1
    assert asyncio.run(auth.access_token()) == 'explicitly-refreshed'
    assert len(requests) == 1


@pytest.mark.parametrize('response', [
    httpx.Response(503, json={'error': 'temporarily_unavailable'}),
    httpx.Response(400, json={'error': 'temporarily_unavailable'}),
])
def test_transient_refresh_failure_preserves_credentials(tmp_path, monkeypatch, response):
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    prepare_expired_account(auth)
    before = auth.path.read_text()
    transport(monkeypatch, lambda request: response)
    with pytest.raises(AuthError) as caught:
        asyncio.run(auth.access_token())
    assert caught.value.code == 'AUTH_REFRESH_FAILED' and caught.value.retryable
    assert auth.active()['access_token'] == 'expired-secret'
    assert auth.path.read_text() == before


def test_invalid_grant_clears_tokens_and_requires_login(tmp_path, monkeypatch):
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    prepare_expired_account(auth)
    transport(monkeypatch, lambda request: httpx.Response(400, json={'error': 'invalid_grant'}))
    with pytest.raises(AuthError) as caught:
        asyncio.run(auth.access_token())
    assert caught.value.code == 'LOGIN_REQUIRED'
    assert not auth.status()['connected']
    assert not {'access_token', 'refresh_token', 'id_token'}.intersection(auth.active())
    assert 'expired-secret' not in auth.path.read_text()


@pytest.mark.parametrize('expires', ['not-a-number', -1, False])
def test_malformed_refresh_cannot_partially_replace_tokens(tmp_path, monkeypatch, expires):
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    prepare_expired_account(auth)
    before = auth.path.read_text()
    transport(monkeypatch, lambda request: httpx.Response(200, json={'access_token': 'must-not-commit', 'refresh_token': 'must-not-commit', 'expires_in': expires}))
    with pytest.raises(AuthError):
        asyncio.run(auth.access_token())
    assert auth.active()['access_token'] == 'expired-secret'
    assert auth.path.read_text() == before


@pytest.mark.parametrize('status,confirmed', [(200, True), (503, False)])
def test_logout_revocation_success_or_failure_always_clears_local_tokens(tmp_path, monkeypatch, status, confirmed):
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    prepare_expired_account(auth)
    auth.begin('browser-session')
    revocations = []
    def handle(request):
        if request.method == 'GET':
            return discovery()
        assert str(request.url) == ISSUER + '/test/revoke'
        assert not auth.status()['connected']  # Local logout precedes remote I/O.
        revocations.append(parse_qs(request.content.decode()))
        return httpx.Response(status)
    transport(monkeypatch, handle)
    result = asyncio.run(auth.logout())
    assert result == {'remote_revocation_confirmed': confirmed}
    assert len(revocations) == (1 if status == 200 else 2)
    assert revocations[0]['token'] == ['refresh-secret']
    assert not auth.status()['connected'] and not auth.status('browser-session')['pending_login']
    assert 'refresh-secret' not in auth.path.read_text()


def test_cancelled_remote_logout_still_leaves_local_credentials_removed(tmp_path, monkeypatch):
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    prepare_expired_account(auth)
    async def run():
        started = asyncio.Event()
        async def handle(request):
            if request.method == 'GET':
                return discovery()
            started.set()
            await asyncio.Event().wait()
        transport(monkeypatch, handle)
        task = asyncio.create_task(auth.logout())
        await started.wait()
        assert not auth.status()['connected']
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert 'refresh-secret' not in auth.path.read_text()
    asyncio.run(run())


def test_login_cancel_is_session_scoped_and_preserves_existing_login(tmp_path):
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    prepare_expired_account(auth, expires_at=time.time() + 3600)
    auth.begin('first-session')
    auth.begin('second-session')
    assert auth.status('first-session')['pending_login']
    assert auth.cancel_login('first-session') == {'cancelled': True}
    assert not auth.status('first-session')['pending_login']
    assert auth.status('second-session')['pending_login']
    assert auth.status()['connected']
    assert auth.cancel_login('first-session') == {'cancelled': False}


@pytest.mark.parametrize('action', ['cancel', 'logout', 'new_login'])
def test_inflight_callback_cannot_reconnect_after_cancellation(tmp_path, monkeypatch, signing_keys, action):
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    query, pending = login_pending(auth)
    response = token_payload(signed(signing_keys, claims(pending['nonce'])))
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        async def handle(request):
            if str(request.url) == TOKEN:
                started.set()
                await release.wait()
                return httpx.Response(200, json=response)
            if str(request.url).endswith('openid-configuration'):
                return discovery()
            assert str(request.url).endswith('/test/jwks')
            return httpx.Response(200, json=signing_keys[2])
        transport(monkeypatch, handle)
        task = asyncio.create_task(auth.callback({'state': query['state'][0], 'code': 'code', 'client_id': CLIENT_ID}, 'browser-session'))
        await started.wait()
        assert auth.status('browser-session')['pending_login']
        if action == 'cancel':
            assert auth.cancel_login('browser-session')['cancelled']
        elif action == 'logout':
            await auth.logout()
        else:
            auth.begin('browser-session')
        release.set()
        with pytest.raises(AuthError) as caught:
            await task
        assert caught.value.code == 'AUTH_CANCELLED'
        assert not auth.status()['connected'] and auth.data['accounts'] == {}
    asyncio.run(run())


def test_model_catalog_preserves_only_explicit_safe_limits(tmp_path, monkeypatch):
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    prepare_expired_account(auth, expires_at=time.time() + 3600)
    def handle(request):
        assert str(request.url) == RESOURCE + '/models'
        return httpx.Response(200, json={'models': [
            {'slug': 'catalog-model', 'visibility': 'list', 'context_window': 272000, 'max_context_window': 400000,
             'max_input_tokens': None, 'max_output_tokens': 'not-an-integer', 'unrelated_secret': 'must-not-expose'},
            {'slug': 'hidden', 'visibility': 'hidden', 'context_window': 999},
        ]})
    transport(monkeypatch, handle)
    metadata = asyncio.run(auth.model_metadata())
    assert metadata['context_window'] == 272000 and metadata['max_context_window'] == 400000
    assert metadata['max_input_tokens'] is None and metadata['max_output_tokens'] is None and metadata['tokenizer'] is None
    assert metadata['source'] == 'catalog'
    assert 'must-not-expose' not in json.dumps(auth.status())
    assert len(auth.models) == 1


def test_expected_model_is_checked_before_any_provider_request(tmp_path, monkeypatch):
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    prepare_expired_account(auth, expires_at=time.time() + 3600)
    recorded = install_model_stream(monkeypatch, [{'type': 'response.completed'}])
    with pytest.raises(AuthError) as caught:
        asyncio.run(auth.generate_for_model('질문', '지침', 'previous-budget-model'))
    assert caught.value.code == 'MODEL_CHANGED'
    assert recorded == {}


def test_model_change_during_token_acquisition_cannot_use_previous_budget(tmp_path, monkeypatch):
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    prepare_expired_account(auth, expires_at=time.time() + 3600)
    auth.models = [{'slug': 'catalog-model'}, {'slug': 'other-model'}]
    recorded = install_model_stream(monkeypatch, [{'type': 'response.completed'}])
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        async def delayed_token():
            started.set()
            await release.wait()
            return 'simulated-token'
        monkeypatch.setattr(auth, 'access_token', delayed_token)
        task = asyncio.create_task(auth.generate_for_model('질문', '지침', 'catalog-model'))
        await started.wait()
        auth.select_model('other-model')
        release.set()
        with pytest.raises(AuthError) as caught:
            await task
        assert caught.value.code == 'MODEL_CHANGED'
        assert recorded == {}
    asyncio.run(run())


@pytest.mark.parametrize('change', ['different_model', 'away_and_back', 'logout'])
def test_model_or_auth_change_during_stream_discards_partial_text(tmp_path, monkeypatch, change):
    from types import SimpleNamespace
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    prepare_expired_account(auth, expires_at=time.time() + 3600, refresh_token=None)
    auth.models = [{'slug': 'catalog-model'}, {'slug': 'other-model'}]
    class ChangingStream(FakeStream):
        def __aiter__(self):
            async def iterate():
                yield SimpleNamespace(type='response.output_text.delta', delta='보여주면 안 되는 부분응답')
                if change == 'logout':
                    await auth.logout()
                else:
                    auth.select_model('other-model')
                    if change == 'away_and_back':
                        auth.select_model('catalog-model')
                yield SimpleNamespace(type='response.completed')
            return iterate()
    class Client:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(create=self.create)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def create(self, **kwargs):
            assert kwargs['model'] == 'catalog-model'
            return ChangingStream([])
    monkeypatch.setattr(auth_module, 'AsyncOpenAI', Client)
    with pytest.raises(AuthError) as caught:
        asyncio.run(auth.generate_for_model('질문', '지침', 'catalog-model'))
    assert caught.value.code == ('LOGIN_REQUIRED' if change == 'logout' else 'MODEL_CHANGED')
    assert '보여주면 안 되는' not in str(caught.value)
