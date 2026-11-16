"""Provider failures and explicit recovery using synthetic streams and storage."""
import asyncio
import json
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.client import Client
from openai import APIError, APIConnectionError, APITimeoutError

import cache_me.auth as auth_module
from cache_me.api import install_error_handlers, router
from cache_me.auth import AuthError, ModelAuth
from cache_me.db import Database
from cache_me.enrichment import ConceptEnrichment
from cache_me.mcp_server import create_mcp
from cache_me.models import ConceptEnrichmentJob
from cache_me.records import RecordService
from cache_me.search import SearchService
from test_auth_contract import FakeStream, prepare_expired_account


def provider_error(code, *, nested=False):
    body = {'code': code, 'param': 'model', 'message': 'private-provider-message'}
    error = APIError('private-provider-message', httpx.Request('POST', 'https://api.openai.com/v1/responses'),
                     body={'error': body} if nested else body)
    error.request_id = 'req_synthetic'
    return error


def install_streams(monkeypatch, streams):
    requests = []
    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(create=self.create)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def create(self, **kwargs):
            requests.append(kwargs)
            stream = streams.pop(0)
            return stream if isinstance(stream, FakeStream) else FakeStream(stream)
    monkeypatch.setattr(auth_module, 'AsyncOpenAI', FakeClient)
    return requests


def install_sdk_sse(monkeypatch, proposal):
    """Exercise the real SDK's SSE error-to-APIError conversion offline."""
    real_openai = auth_module.AsyncOpenAI
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            events = [{'error': {'code': 'subscription_sharing_usage_limit_exceeded',
                                'type': 'invalid_request_error', 'message': 'private-provider-message'}}]
        else:
            events = [{'type': 'response.completed', 'response': {
                'id': 'resp_test', 'object': 'response', 'created_at': 0,
                'status': 'completed', 'model': 'catalog-model', 'output': [{
                    'id': 'msg_test', 'type': 'message', 'role': 'assistant', 'status': 'completed',
                    'content': [{'type': 'output_text', 'text': proposal, 'annotations': []}],
                }],
            }}]
        content = ''.join('data: ' + json.dumps(event) + '\n\n' for event in events) + 'data: [DONE]\n\n'
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, text=content)
    def client(**kwargs):
        return real_openai(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(auth_module, 'AsyncOpenAI', client)
    return requests


@pytest.fixture
def auth(tmp_path):
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    prepare_expired_account(auth, expires_at=time.time() + 3600)
    auth.models = [{'slug': 'catalog-model'}, {'slug': 'other-model'}]
    return auth


@pytest.mark.parametrize('provider_code,code', [
    ('subscription_sharing_usage_limit_exceeded', 'MODEL_USAGE_LIMIT'),
    ('subscription_sharing_user_not_eligible', 'MODEL_PERMISSION_DENIED'),
    ('chatpass_v2_scope_not_authorized', 'MODEL_PERMISSION_DENIED'),
    ('chatpass_v2_invalid_authorization_context', 'MODEL_PERMISSION_DENIED'),
    ('subscription_sharing_invalid_user', 'MODEL_AUTH_REJECTED'),
    ('subscription_sharing_unsupported_capability', 'MODEL_REQUEST_INVALID'),
    ('subscription_sharing_route_not_supported', 'MODEL_REQUEST_INVALID'),
])
@pytest.mark.parametrize('nested', [False, True])
def test_sdk_midstream_errors_preserve_safe_cause_and_pause_new_requests(auth, monkeypatch, provider_code, code, nested):
    requests = install_streams(monkeypatch, [[
        {'type': 'response.output_text.delta', 'delta': 'uncommitted-partial'},
        provider_error(provider_code, nested=nested),
    ]])
    for _ in range(2):
        with pytest.raises(AuthError) as caught:
            asyncio.run(auth.generate('synthetic question', 'instruction'))
        assert caught.value.code == code
        assert caught.value.details == {'provider_code': provider_code, 'parameter': 'model', 'request_id': 'req_synthetic'}
        assert 'private-provider-message' not in str(caught.value)
    assert len(requests) == 1
    assert auth.status()['request_blocked']['code'] == code
    assert auth.status()['request_blocked']['retryable'] is False
    assert 'private-provider-message' not in json.dumps(auth.status())
    assert code not in auth.path.read_text()


@pytest.mark.parametrize('kind,code', [('connection', 'MODEL_UNAVAILABLE'), ('timeout', 'MODEL_TIMEOUT'),
                                       ('temporary', 'MODEL_TEMPORARILY_UNAVAILABLE')])
def test_transient_errors_remain_retryable_without_account_pause(auth, monkeypatch, kind, code):
    request = httpx.Request('POST', 'https://api.openai.com/v1/responses')
    error = APIConnectionError(request=request, message='private-connection') if kind == 'connection' else (
        APITimeoutError(request) if kind == 'timeout' else provider_error('subscription_sharing_usage_unavailable'))
    install_streams(monkeypatch, [[error]])
    with pytest.raises(AuthError) as caught:
        asyncio.run(auth.generate('question', 'instruction'))
    assert caught.value.code == code and caught.value.retryable
    assert auth.status()['request_blocked'] is None
    assert 'private' not in caught.value.message


def test_invalid_selection_does_not_resume_but_valid_explicit_selection_does(auth, monkeypatch):
    requests = install_streams(monkeypatch, [[provider_error('subscription_sharing_usage_limit_exceeded')],
        [{'type': 'response.output_text.delta', 'delta': 'recovered'}, {'type': 'response.completed'}]])
    with pytest.raises(AuthError):
        asyncio.run(auth.generate('question', 'instruction'))
    with pytest.raises(AuthError):
        auth.select_model('unavailable')
    assert auth.status()['request_blocked']
    auth.select_model('catalog-model')
    assert auth.status()['request_blocked'] is None
    assert asyncio.run(auth.generate('question', 'instruction')) == 'recovered'
    assert len(requests) == 2


@pytest.mark.parametrize('change', ['model', 'resume', 'account'])
def test_late_error_cannot_pause_new_context(auth, monkeypatch, change):
    class LateError(FakeStream):
        def __aiter__(self):
            async def iterate():
                yield SimpleNamespace(type='response.output_text.delta', delta='partial')
                if change == 'model':
                    auth.select_model('other-model')
                elif change == 'resume':
                    auth.resume_requests()
                else:
                    auth.auth_generation += 1
                raise provider_error('subscription_sharing_usage_limit_exceeded')
            return iterate()
    install_streams(monkeypatch, [LateError([])])
    with pytest.raises(AuthError):
        asyncio.run(auth.generate('question', 'instruction'))
    assert auth.status()['request_blocked'] is None


def test_pause_during_client_setup_prevents_a_new_provider_request(auth, monkeypatch):
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        class DelayedClient:
            def __init__(self, **kwargs):
                self.responses = SimpleNamespace(create=self.create)
            async def __aenter__(self):
                entered.set()
                await release.wait()
                return self
            async def __aexit__(self, *args):
                return False
            async def create(self, **kwargs):
                pytest.fail('Paused requests must not reach the provider')
        monkeypatch.setattr(auth_module, 'AsyncOpenAI', DelayedClient)
        task = asyncio.create_task(auth.generate('question', 'instruction'))
        await entered.wait()
        auth.request_blocked = AuthError('MODEL_USAGE_LIMIT', 'safe usage limit message')
        release.set()
        with pytest.raises(AuthError) as caught:
            await task
        assert caught.value.code == 'MODEL_USAGE_LIMIT'
    asyncio.run(run())


@pytest.fixture
def services(tmp_path, auth):
    db = Database(tmp_path / 'recovery.sqlite3')
    records = RecordService(db)
    search = SearchService(records, tmp_path / 'unused-index')
    yield records, search, auth
    db.close()


def create(records):
    return records.create({'request_id': str(uuid4()), 'body_markdown': '합성 자료의 검색 학습 기록입니다.'})['capture']


def retry_input(capture):
    return {'request_id': str(uuid4()), 'capture_id': capture['id'],
            'expected_revision_id': capture['revision_id'], 'expected_state_version': capture['state_version'],
            'job_id': capture['concept_state']['job_id']}


def retry_via(via, records, search, auth, payload, *, replay=False, rejected=False):
    if via == 'web':
        app = FastAPI()
        app.state.records, app.state.auth = records, auth
        app.include_router(router)
        install_error_handlers(app)
        with TestClient(app) as client:
            response = client.post(f"/api/v1/captures/{payload['capture_id']}/concept-retry", json=payload)
            assert response.status_code == (409 if rejected else 200)
            if not rejected:
                assert response.json()['data']['replayed'] is replay
    else:
        async def retry():
            async with Client(create_mcp(records, search, on_concept_retry=auth.resume_requests)) as client:
                result = await client.call_tool('capture_retry_concepts', {'input': payload})
                assert bool(result.is_error) is rejected
                if not rejected:
                    assert result.structured_content['data']['replayed'] is replay
        asyncio.run(retry())


@pytest.mark.parametrize('via', ['web', 'mcp', 'sdk-web'])
def test_usage_limit_stops_queue_and_explicit_retry_restores_topic_edges(services, monkeypatch, via):
    records, search, auth = services
    capture = create(records)
    proposal = json.dumps({'new_concepts': [{'name': '합성 검색 학습', 'description': '합성 자료로 검색 방법을 학습하는 기록'}]})
    requests = install_sdk_sse(monkeypatch, proposal) if via == 'sdk-web' else install_streams(monkeypatch, [
        [provider_error('subscription_sharing_usage_limit_exceeded')],
        [{'type': 'response.output_text.delta', 'delta': proposal}, {'type': 'response.completed'}]])
    worker = ConceptEnrichment(records, auth)
    asyncio.run(worker.process_one())
    failed = records.get(capture['id'])
    assert failed['concept_state']['status'] == 'failed'
    assert failed['concept_state']['error_code'] == 'MODEL_USAGE_LIMIT'
    assert 'private-provider-message' not in json.dumps(failed)
    assert 'private-provider-message' not in json.dumps(auth.status())
    assert search.home_graph()['edges'] == []
    with records.db.write() as session:
        row = session.get(ConceptEnrichmentJob, failed['concept_state']['job_id'])
        row.available_at = '2000-01-01T00:00:00.000Z'
    assert records.claim_concept_job() is None
    second = create(records)
    for _ in range(3):
        asyncio.run(worker.process_one())
    assert len(requests) == 1
    with records.db.read() as session:
        assert session.get(ConceptEnrichmentJob, failed['concept_state']['job_id']).attempt_count == 1
        assert session.get(ConceptEnrichmentJob, second['concept_state']['job_id']).attempt_count == 0
    retry_via('web' if via == 'sdk-web' else via, records, search, auth, retry_input(failed))
    assert auth.status()['request_blocked'] is None
    asyncio.run(worker.process_one())
    recovered = records.get(capture['id'])
    assert recovered['concept_state']['status'] == 'ready'
    assert recovered['body_markdown'] == capture['body_markdown']
    assert [edge['kind'] for edge in search.home_graph()['edges']] == ['has_topic']
    assert len(requests) == 2


@pytest.mark.parametrize('via', ['web', 'mcp'])
def test_retry_rejection_or_receipt_replay_cannot_clear_new_pause(services, via):
    records, search, auth = services
    capture = create(records)
    job = records.claim_concept_job()
    records.fail_concept_job(job['job_id'], job['lease_token'], error_code='MODEL_USAGE_LIMIT')
    payload = retry_input(capture)
    records.retry_concepts(payload)
    auth.request_blocked = AuthError('MODEL_USAGE_LIMIT', 'safe limit message')
    generation = auth.request_generation
    retry_via(via, records, search, auth, payload, replay=True)
    retry_via(via, records, search, auth, payload | {'request_id': str(uuid4())}, rejected=True)
    assert auth.request_generation == generation and auth.status()['request_blocked']
