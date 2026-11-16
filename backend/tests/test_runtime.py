import asyncio
import io
import json
import time
import zipfile
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from mcp.client import Client
from mcp.types import ElicitResult
from mcp.shared.exceptions import MCPError

from cache_me.auth import ModelAuth, AuthError
from cache_me.config import Settings
from cache_me.db import Database
from cache_me.main import create_app
from cache_me.mcp_server import create_mcp
from cache_me.questions import QuestionInput, QuestionService
from cache_me.records import RecordService
from cache_me.schemas import CreateCaptureInput, PrepareDeletionInput, DeleteCaptureInput
from agent_fakes import OfflineModel


@pytest.fixture
def web(tmp_path):
    settings = Settings(tmp_path, background_jobs=False)
    app = create_app(settings)
    with TestClient(app, base_url=settings.origin) as client:
        session = client.get('/api/v1/session').json()['data']
        client.headers['x-csrf-token'] = session['csrf_token']
        yield client, app


def create(client, body='지식을 저장합니다.'):
    response = client.post('/api/v1/captures', json={'request_id': str(uuid4()), 'body_markdown': body})
    assert response.status_code == 200, response.text
    return response.json()['data']['capture']


def test_runtime_reports_installed_product_version(web):
    client, app = web
    expected = version('cache-me')
    assert app.version == expected
    assert client.get('/health').json()['data']['version'] == expected
    assert client.get('/openapi.json').json()['info']['version'] == expected


def test_web_security_and_delete_session_binding(web):
    client, app = web
    assert client.post('/api/v1/captures', headers={'x-csrf-token': 'wrong'}, json={}).status_code == 403
    assert client.get('/api/v1/captures', headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.get('/health', headers={'Host': 'evil.example'}).status_code == 421
    capture = create(client)
    expected = {'capture_id': capture['id'], 'expected_revision_id': capture['revision_id'], 'expected_state_version': capture['state_version']}
    preview = client.post(f"/api/v1/captures/{capture['id']}/deletion-preview", json=expected).json()['data']
    payload = {**expected, 'confirmation_token': preview['confirmation_token'], 'request_id': str(uuid4())}
    original_cookie = client.cookies.get('cache_me_session')
    original_csrf = client.headers['x-csrf-token']
    client.cookies.clear()
    client.headers['x-csrf-token'] = client.get('/api/v1/session').json()['data']['csrf_token']
    assert not client.post(f"/api/v1/captures/{capture['id']}/deletion", json=payload).json()['ok']
    client.cookies.clear()
    client.cookies.set('cache_me_session', original_cookie)
    client.headers['x-csrf-token'] = original_csrf
    assert client.post(f"/api/v1/captures/{capture['id']}/deletion", json=payload).json()['ok']
    assert client.get(f"/api/v1/captures/{capture['id']}").status_code == 404
    assert client.post('/api/v1/sources/resolve', json={'capture_id': capture['id'], 'revision_id': capture['revision_id']}).status_code == 404


def test_backup_is_snapshot_and_excludes_credentials(web, tmp_path):
    client, app = web
    capture = create(client, '백업의 정본')
    response = client.post('/api/v1/backups', json={})
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {'cache-me.sqlite3', 'manifest.json'}
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['app_version'] == version('cache-me')
        assert manifest['includes_soft_deleted_history'] is True
        assert manifest['schema_revision'] == '0001'
        assert manifest['embedding_profiles'][0]['model_id'] == 'nlpai-lab/KURE-v2'
        assert b'access_token' not in archive.read('manifest.json')
        assert archive.read('cache-me.sqlite3').startswith(b'SQLite format 3')
        restored_data = tmp_path / 'restored-store'
        restored_data.mkdir()
        (restored_data / 'cache-me.sqlite3').write_bytes(archive.read('cache-me.sqlite3'))

    settings = Settings(restored_data, background_jobs=False)
    with TestClient(create_app(settings), base_url=settings.origin) as restored:
        restored.get('/api/v1/session')
        result = restored.get(f"/api/v1/captures/{capture['id']}")
        assert result.status_code == 200
        saved = result.json()['data']
        assert saved['id'] == capture['id']
        assert saved['revision_id'] == capture['revision_id']
        assert saved['body_markdown'] == '백업의 정본'


def test_no_model_login_is_explicit_stream_error(web):
    client, app = web
    response = client.post('/api/v1/questions', json={'request_id': str(uuid4()), 'question': '내가 배운 내용은?'})
    assert 'event: error' in response.text
    assert 'LOGIN_REQUIRED' in response.text
    assert 'event: completed' not in response.text


def test_stream_rechecks_before_each_part_and_does_not_complete_invalidated(web, monkeypatch):
    client, app = web
    parts = [{'part_id': str(i), 'kind': 'stored_knowledge', 'text': f'근거 부분 {i}', 'sources': []} for i in range(2)]
    async def answer(_self, _request):
        return {'answer_id': str(uuid4()), 'parts': parts, 'sources': [], 'limitations': [], 'evidence_status': 'found'}
    calls = []
    def revalidate(_self, _result):
        calls.append(True)
        if len(calls) >= 3:
            raise AuthError('ANSWER_INVALIDATED', '근거가 변경되었습니다.')
    monkeypatch.setattr(QuestionService, 'run', answer)
    monkeypatch.setattr(QuestionService, 'revalidate', revalidate)
    response = client.post('/api/v1/questions', json={'request_id': str(uuid4()), 'question': '검증 질문'})
    assert response.text.count('event: answer_part') == 1
    assert 'event: invalidated' in response.text
    assert 'event: completed' not in response.text
    assert '근거 부분 1' not in response.text


def test_mcp_confirmation_is_hidden_and_required(tmp_path):
    async def run():
        db = Database(tmp_path / 'mcp.sqlite')
        records = RecordService(db, created_via='mcp')
        server = create_mcp(records, None)
        async with Client(server) as client:
            assert client.server_info is not None
            assert client.server_info.version == version('cache-me')
            schemas = await client.list_tools()
            deletion = next(t for t in schemas.tools if t.name == 'capture_delete')
            assert 'answer' not in deletion.input_schema['properties']
            assert all(tool.output_schema is not None for tool in schemas.tools)
            result = await client.call_tool('capture_create', {'input': {'request_id': str(uuid4()), 'body_markdown': 'MCP 저장'}})
            capture = result.structured_content['data']['capture']
            expected = {'capture_id': capture['id'], 'expected_revision_id': capture['revision_id'], 'expected_state_version': capture['state_version']}
            preview = await client.call_tool('capture_delete_prepare', {'input': expected})
            payload = {**expected, 'request_id': str(uuid4()), 'confirmation_token': preview.structured_content['data']['confirmation_token']}
            with pytest.raises(MCPError, match='elicitation capability'):
                await client.call_tool('capture_delete', {'input': payload})
            assert records.get(capture['id'])['body_markdown'] == 'MCP 저장'
        async def accept(context, params):
            return ElicitResult(action='accept', content={'delete': True})
        async with Client(server, elicitation_callback=accept) as client:
            result = await client.call_tool('capture_delete', {'input': payload})
            assert not result.is_error, result
            assert result.structured_content['data']['deleted_at']
            replay = await client.call_tool('capture_delete', {'input': payload})
            assert replay.structured_content['data']['replayed'] is True
        db.close()
    asyncio.run(run())


def test_oauth_state_is_session_bound_and_pkce_is_fresh(tmp_path):
    from urllib.parse import urlparse, parse_qs
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    first = parse_qs(urlparse(auth.begin('session-a')).query)
    second = parse_qs(urlparse(auth.begin('session-a')).query)
    assert first['state'] != second['state']
    assert first['code_challenge'] != second['code_challenge']
    assert second['client_id'] == ['dynamic_agent_client']
    assert second['redirect_uri'] == ['http://127.0.0.1:8000/auth/callback']
    with pytest.raises(AuthError):
        asyncio.run(auth.callback({'state': second['state'][0], 'code': 'unused'}, 'wrong-session'))
    assert not auth.status()['connected']
    mode = (tmp_path / 'credentials.json').stat().st_mode & 0o777
    assert mode == 0o600


def test_langgraph_keeps_requests_ephemeral_and_checks_deleted_sources(tmp_path):
    db = Database(tmp_path / 'qa.sqlite')
    records = RecordService(db)
    capture = records.create(CreateCaptureInput(request_id=uuid4(), body_markdown='트랜잭션은 원자적이다.'))['capture']
    source = {'capture_id': capture['id'], 'revision_id': capture['revision_id']}
    class Search:
        def context(self, _):
            return {'items': [{'source': source, 'text': capture['body_markdown']}], 'limitations': []}
    service = QuestionService(Search(), records, OfflineModel(final_text='원자적입니다.'))
    result = asyncio.run(service.run(QuestionInput(request_id=uuid4(), question='트랜잭션은?')))
    assert result['evidence_status'] == 'found'
    preview = records.prepare_delete(PrepareDeletionInput(capture_id=capture['id'], expected_revision_id=capture['revision_id'], expected_state_version=1))
    records.delete(DeleteCaptureInput(request_id=uuid4(), capture_id=capture['id'], expected_revision_id=capture['revision_id'], expected_state_version=1, confirmation_token=preview['confirmation_token']), confirmation=records.confirm_deletion(preview['confirmation_token']))
    with pytest.raises(Exception):
        service.revalidate(result)
    assert records.list()['items'] == []  # Answer/question were not saved as records.
    db.close()
