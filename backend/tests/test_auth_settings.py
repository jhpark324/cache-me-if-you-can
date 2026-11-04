"""Single-account settings and catalog-driven reasoning, with no provider calls."""
import asyncio
import json
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

import second_brain.auth as auth_module
from second_brain.auth import AuthError, ModelAuth, RESOURCE
from test_auth_contract import (CLIENT_ID, FakeStream, claims, install_model_stream,
                                install_transport, prepare_expired_account, signed,
                                signing_keys, token_payload)
from test_auth_operations import transport


def catalog_model(**changes):
    return {'slug': 'catalog-model', 'display_name': 'Catalog Model', 'visibility': 'list',
            'supported_reasoning_levels': [
                {'effort': 'low', 'description': 'Faster'},
                {'effort': 'high', 'description': 'More thorough'},
            ], 'default_reasoning_level': 'low', **changes}


def ready_auth(tmp_path):
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    prepare_expired_account(auth, expires_at=time.time() + 3600)
    return auth


def load_catalog(auth, monkeypatch, models=None):
    def handle(request):
        assert str(request.url) == RESOURCE + '/models'
        return httpx.Response(200, json={'models': models if models is not None else [catalog_model()]})
    transport(monkeypatch, handle)
    return asyncio.run(auth.list_models())


def test_startup_removes_historical_registrations_and_keeps_current_mapping(tmp_path):
    auth = ready_auth(tmp_path)
    current = auth.data['active']
    auth.data['accounts']['previous'] = {'client_id': 'old-client', 'access_token': 'old-secret'}
    auth.save()
    restarted = ModelAuth(tmp_path, auth.origin)
    assert list(restarted.data['accounts']) == [current]
    assert 'old-secret' not in restarted.path.read_text()
    assert 'previous' not in json.dumps(restarted.status())
    assert restarted.data['host_id'] == auth.data['host_id']


def test_missing_active_registration_does_not_restore_a_previous_account(tmp_path):
    auth = ready_auth(tmp_path)
    auth.data['active'] = 'no-longer-present'
    auth.save()
    restarted = ModelAuth(tmp_path, auth.origin)
    assert restarted.data['accounts'] == {}
    assert restarted.data['active'] is None
    assert not restarted.status()['connected']


def test_default_login_reuses_current_registration_after_logout(tmp_path):
    auth = ready_auth(tmp_path)
    auth.active()['refresh_token'] = None
    asyncio.run(auth.logout())
    query = parse_qs(urlparse(auth.begin('browser')).query)
    assert query['client_id'] == [CLIENT_ID]
    assert query['ext_agent_host_id'] == [auth.data['host_id']]
    assert 'agent_name_hint' not in query
    assert not {'access_token', 'refresh_token', 'id_token'}.intersection(auth.active())
    replacement = parse_qs(urlparse(auth.begin('browser', replace_account=True)).query)
    assert replacement['client_id'] == ['dynamic_agent_client']
    assert 'agent_name_hint' in replacement
    assert 'login_hint' not in replacement and 'id_token_hint' not in replacement


@pytest.mark.parametrize('valid', [True, False])
def test_replacement_keeps_existing_account_until_identity_is_validated(tmp_path, monkeypatch, signing_keys, valid):
    auth = ready_auth(tmp_path)
    previous = auth.data['active']
    before = auth.path.read_text()
    query = parse_qs(urlparse(auth.begin('browser', replace_account=True)).query)
    pending = auth.pending[query['state'][0]]
    identity = signed(signing_keys, claims(pending['nonce'] if valid else 'wrong-nonce', sub='replacement'))
    install_transport(monkeypatch, signing_keys, token_payload(identity))
    callback = auth.callback({'state': query['state'][0], 'code': 'code', 'client_id': CLIENT_ID}, 'browser')
    if not valid:
        with pytest.raises(AuthError):
            asyncio.run(callback)
        assert auth.path.read_text() == before
        assert auth.data['active'] == previous
        return
    asyncio.run(callback)
    assert list(auth.data['accounts']) == [CLIENT_ID + ':replacement']
    assert 'expired-secret' not in auth.path.read_text()
    assert auth.status()['connected']
    assert auth.status()['selected_model'] is None


def test_catalog_exposes_only_explicit_reasoning_choices_and_valid_default(tmp_path, monkeypatch):
    auth = ready_auth(tmp_path)
    models = load_catalog(auth, monkeypatch, [
        None, catalog_model(supported_reasoning_levels=[
            {'effort': 'low', 'description': 'Faster', 'secret': 'excluded'},
            {'effort': 'low', 'description': 'duplicate'},
            {'effort': 'high', 'description': None},
            {'effort': 'invalid effort'}, {'description': 'missing'}, 'high',
        ]),
        catalog_model(slug='hidden', visibility='hidden'),
        catalog_model(),
        catalog_model(slug='without-metadata', supported_reasoning_levels=None, default_reasoning_level='high'),
    ])
    assert [model['slug'] for model in models] == ['catalog-model', 'without-metadata']
    assert models[0]['supported_reasoning_efforts'] == [
        {'effort': 'low', 'description': 'Faster'}, {'effort': 'high', 'description': ''},
    ]
    assert models[0]['default_reasoning_effort'] == 'low'
    assert models[1]['supported_reasoning_efforts'] == []
    assert models[1]['default_reasoning_effort'] is None
    assert 'excluded' not in json.dumps(auth.status())


def test_model_and_effort_selection_is_atomic_and_persisted(tmp_path, monkeypatch):
    auth = ready_auth(tmp_path)
    load_catalog(auth, monkeypatch, [catalog_model(), catalog_model(slug='other')])
    auth.select_model('catalog-model', 'high')
    auth.select_model('catalog-model')
    assert auth.status()['selected_reasoning_effort'] == 'high'
    before = auth.path.read_text()
    generation = auth.model_generation
    with pytest.raises(AuthError) as caught:
        auth.select_model('other', 'unsupported')
    assert caught.value.code == 'REASONING_UNAVAILABLE'
    assert auth.path.read_text() == before and auth.model_generation == generation
    restarted = ModelAuth(tmp_path, auth.origin)
    assert restarted.status()['selected_model'] == 'catalog-model'
    assert restarted.status()['selected_reasoning_effort'] == 'high'
    auth.select_model('other')
    assert auth.status()['selected_reasoning_effort'] is None
    assert auth.model_generation == generation + 1


@pytest.mark.parametrize('effort', [None, 'low', 'high'])
def test_saved_reasoning_choice_reaches_responses_request_after_restart(tmp_path, monkeypatch, effort):
    auth = ready_auth(tmp_path)
    load_catalog(auth, monkeypatch)
    auth.select_model('catalog-model', effort)
    auth = ModelAuth(tmp_path, auth.origin)
    recorded = install_model_stream(monkeypatch, [
        {'type': 'response.output_text.delta', 'delta': '완료'}, {'type': 'response.completed'},
    ])
    assert asyncio.run(auth.generate('질문', '지침')) == '완료'
    if effort is None:
        assert 'reasoning' not in recorded['request']
    else:
        assert recorded['request']['reasoning'] == {'effort': effort}


def test_catalog_removing_effort_never_sends_stale_setting(tmp_path, monkeypatch):
    auth = ready_auth(tmp_path)
    load_catalog(auth, monkeypatch)
    auth.select_model('catalog-model', 'high')
    auth = ModelAuth(tmp_path, auth.origin)
    transport(monkeypatch, lambda request: httpx.Response(200, json={'models': [catalog_model(supported_reasoning_levels=[])]}))
    recorded = install_model_stream(monkeypatch, [{'type': 'response.completed'}])
    with pytest.raises(AuthError) as caught:
        asyncio.run(auth.generate('질문', '지침'))
    assert caught.value.code == 'MODEL_CHANGED'
    assert recorded == {}
    assert auth.status()['selected_reasoning_effort'] is None
    assert ModelAuth(tmp_path, auth.origin).status()['selected_reasoning_effort'] is None


@pytest.mark.parametrize('catalog', [None, {}, {'models': {}}, {'models': 'invalid'}])
def test_invalid_catalog_cannot_replace_previous_choices(tmp_path, monkeypatch, catalog):
    auth = ready_auth(tmp_path)
    before = load_catalog(auth, monkeypatch)
    transport(monkeypatch, lambda request: httpx.Response(200, json=catalog))
    with pytest.raises(AuthError) as caught:
        asyncio.run(auth.list_models())
    assert caught.value.code == 'MODELS_UNAVAILABLE'
    assert auth.models == before


def test_catalog_network_failure_is_safe_and_preserves_saved_selection(tmp_path, monkeypatch):
    auth = ready_auth(tmp_path)
    before_models = load_catalog(auth, monkeypatch)
    auth.select_model('catalog-model', 'high')
    before_credentials = auth.path.read_text()
    def unavailable(request):
        raise httpx.ConnectError('private-transport-details', request=request)
    transport(monkeypatch, unavailable)
    with pytest.raises(AuthError) as caught:
        asyncio.run(auth.list_models())
    assert caught.value.code == 'MODELS_UNAVAILABLE' and caught.value.retryable
    assert 'private-transport-details' not in str(caught.value)
    assert auth.models == before_models
    assert auth.path.read_text() == before_credentials
    restarted = ModelAuth(tmp_path, auth.origin)
    recorded = install_model_stream(monkeypatch, [{'type': 'response.completed'}])
    with pytest.raises(AuthError) as caught:
        asyncio.run(restarted.generate('질문', '지침'))
    assert caught.value.code == 'MODELS_UNAVAILABLE'
    assert recorded == {}
    assert restarted.status()['selected_reasoning_effort'] == 'high'


def test_effort_change_away_and_back_discards_inflight_response(tmp_path, monkeypatch):
    auth = ready_auth(tmp_path)
    load_catalog(auth, monkeypatch)
    auth.select_model('catalog-model', 'high')
    class ChangingStream(FakeStream):
        def __aiter__(self):
            async def iterate():
                yield SimpleNamespace(type='response.output_text.delta', delta='부분 응답')
                auth.select_model('catalog-model', 'low')
                auth.select_model('catalog-model', 'high')
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
            assert kwargs['reasoning'] == {'effort': 'high'}
            return ChangingStream([])
    monkeypatch.setattr(auth_module, 'AsyncOpenAI', Client)
    with pytest.raises(AuthError) as caught:
        asyncio.run(auth.generate('질문', '지침'))
    assert caught.value.code == 'MODEL_CHANGED'


def test_late_catalog_cannot_restore_choices_after_logout(tmp_path, monkeypatch):
    auth = ready_auth(tmp_path)
    auth.active()['refresh_token'] = None
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        async def handle(request):
            started.set()
            await release.wait()
            return httpx.Response(200, json={'models': [catalog_model()]})
        transport(monkeypatch, handle)
        task = asyncio.create_task(auth.list_models())
        await started.wait()
        await auth.logout()
        release.set()
        with pytest.raises(AuthError) as caught:
            await task
        assert caught.value.code == 'AUTH_CANCELLED'
        assert auth.models == []
    asyncio.run(run())
