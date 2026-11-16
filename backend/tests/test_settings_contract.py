"""Settings API contracts using isolated storage and synthetic account metadata."""
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from cache_me.auth import ModelAuth
from cache_me.config import Settings
from cache_me.main import create_app


@pytest.fixture
def connected_settings(tmp_path):
    settings = Settings(tmp_path / 'settings-api', background_jobs=False)
    app = create_app(settings)
    auth = app.state.auth
    account_id = 'test-client:subject'
    auth.data['accounts'] = {account_id: {
        'client_id': 'test-client', 'subject': 'subject',
        'email': 'settings@example.invalid', 'access_token': 'synthetic-access',
        'scopes': ['chatgpt.tokens.use.direct'], 'expires_at': 9999999999,
        'model': 'reasoning-model', 'reasoning_effort': None,
    }}
    auth.data['active'] = account_id
    auth.models = [
        {'slug': 'reasoning-model', 'display_name': 'Reasoning model',
         'supported_reasoning_efforts': [{'effort': 'low', 'description': 'Fast'},
                                         {'effort': 'high', 'description': 'Thorough'}],
         'default_reasoning_effort': 'low'},
        {'slug': 'basic-model', 'display_name': 'Basic model',
         'supported_reasoning_efforts': [], 'default_reasoning_effort': None},
    ]
    auth.save()
    with TestClient(app, base_url=settings.origin) as client:
        csrf = client.get('/api/v1/session').json()['data']['csrf_token']
        client.headers['x-csrf-token'] = csrf
        yield client, auth, settings


def test_model_and_reasoning_settings_validate_atomically_and_persist(connected_settings):
    client, auth, settings = connected_settings
    selection = {'model': 'reasoning-model', 'reasoning_effort': 'high'}
    assert client.patch('/api/v1/settings', json=selection,
                        headers={'x-csrf-token': 'wrong'}).status_code == 403
    assert auth.active()['reasoning_effort'] is None
    response = client.patch('/api/v1/settings', json=selection)
    assert response.status_code == 200
    assert response.json()['data']['selected_reasoning_effort'] == 'high'
    assert client.get('/api/v1/settings').json()['data']['auth']['selected_reasoning_effort'] == 'high'
    reloaded = ModelAuth(settings.data_dir, settings.origin)
    assert reloaded.active()['model'] == 'reasoning-model'
    assert reloaded.active()['reasoning_effort'] == 'high'

    generation = auth.model_generation
    for invalid in [
        {'model': 'basic-model', 'reasoning_effort': 'high'},
        {'model': 'reasoning-model', 'reasoning_effort': 'unsupported'},
        {'model': 'missing-model', 'reasoning_effort': None},
    ]:
        assert client.patch('/api/v1/settings', json=invalid).status_code == 400
        assert auth.active()['model'] == 'reasoning-model'
        assert auth.active()['reasoning_effort'] == 'high'
        assert auth.model_generation == generation

    # Legacy model-only callers preserve a same-model choice, reset on change.
    assert client.patch('/api/v1/settings', json={'model': 'reasoning-model'}).status_code == 200
    assert auth.active()['reasoning_effort'] == 'high'
    assert auth.model_generation == generation
    response = client.patch('/api/v1/settings', json={'model': 'basic-model'})
    assert response.status_code == 200
    assert response.json()['data']['selected_reasoning_effort'] is None
    assert auth.model_generation > generation

    # Explicit null selects the provider default for the same model too.
    assert client.patch('/api/v1/settings', json=selection).status_code == 200
    before_reset = auth.model_generation
    response = client.patch('/api/v1/settings', json={'model': 'reasoning-model', 'reasoning_effort': None})
    assert response.status_code == 200
    assert response.json()['data']['selected_reasoning_effort'] is None
    assert auth.model_generation > before_reset


def test_account_reconnect_and_replace_are_distinct_and_session_protected(connected_settings):
    client, auth, _ = connected_settings
    reconnect = client.post('/api/v1/auth/login', json={})
    assert reconnect.status_code == 200
    query = parse_qs(urlparse(reconnect.json()['data']['authorization_url']).query)
    assert query['client_id'] == ['test-client']
    assert query['login_hint'] == ['settings@example.invalid']

    replace = client.post('/api/v1/auth/login', json={'replace_account': True})
    assert replace.status_code == 200
    query = parse_qs(urlparse(replace.json()['data']['authorization_url']).query)
    assert query['client_id'] == ['dynamic_agent_client']
    assert 'login_hint' not in query
    assert auth.active()['access_token'] == 'synthetic-access'
    assert client.post('/api/v1/auth/cancel', json={}).json()['data']['cancelled']
    assert auth.active()['access_token'] == 'synthetic-access'

    assert client.post('/api/v1/auth/login', json={'replace_account': True},
                       headers={'x-csrf-token': 'wrong'}).status_code == 403
    assert not client.get('/api/v1/settings').json()['data']['auth']['pending_login']
