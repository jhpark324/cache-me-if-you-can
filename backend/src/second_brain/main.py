from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import hashlib
import json
import os
from pathlib import Path
from typing import Annotated
import secrets
import sqlite3
import tempfile
import time
from urllib.parse import urlparse
import zipfile

import httpx

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from filelock import FileLock
from pydantic import BaseModel, ConfigDict
from starlette.background import BackgroundTask

from .auth import ModelAuth, AuthError
from .brand import PRODUCT_NAME, PRODUCT_ID
from .background import run_periodic
from .config import Settings
from .db import Database, migrate_database
from .records import RecordService, DomainError
from . import api
from .questions import QuestionInput, QuestionService
from .search import SearchService, SearchInput, ContextInput, GraphInput
from .mcp_server import create_mcp
from .enrichment import ConceptEnrichment
from .runtime import storage_fingerprint


def ok(data):
    return {'schema_version': 1, 'ok': True, 'data': data}


def error(code, message, status=400):
    return JSONResponse({'schema_version': 1, 'ok': False, 'error': {'code': code, 'message': message, 'retryable': False}}, status_code=status)


class LoginInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    account_id: str | None = None
    replace_account: bool = False


class ModelInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model: str
    reasoning_effort: str | None = None


def create_app(settings: Settings | None = None, *, server_lock: FileLock | None = None):
    settings = settings or Settings.load()
    local = settings.initialize()
    database_path = settings.data_dir / 'brain.sqlite3'
    migrate_database(database_path)
    db = Database(database_path, initialize=False)
    records = RecordService(db)
    auth = ModelAuth(settings.data_dir, settings.origin)
    search = SearchService(records, settings.data_dir / 'index', model_path=os.environ.get('SECOND_BRAIN_MODEL_PATH'))
    questions = QuestionService(search, records, auth)
    enrichment = ConceptEnrichment(records, auth)
    mcp_records = RecordService(db, principal_scope='mcp:local', session_scope='mcp:local', created_via='mcp')
    # Use one loaded model and index manager across transports.
    mcp = create_mcp(mcp_records, search, on_concept_retry=auth.resume_requests)
    # SSE response transport is required for server-initiated deletion elicitation.
    mcp_app = mcp.streamable_http_app(streamable_http_path='/', json_response=False)
    sessions = {}
    tasks: set[asyncio.Task] = set()
    question_tasks: set[asyncio.Task] = set()
    lock = server_lock or FileLock(str(settings.data_dir / 'server.lock'))

    @asynccontextmanager
    async def lifespan(app):
        lock.acquire(timeout=0)
        task = asyncio.create_task(run_periodic(lambda: asyncio.to_thread(search.process_jobs),
            interval=1, name="index", ignored_codes=frozenset({"INDEX_NOT_READY"}))) if settings.background_jobs else None
        if settings.background_jobs:
            enrichment_task = asyncio.create_task(run_periodic(enrichment.process_one, interval=3, name="concepts"))
            tasks.add(enrichment_task)
        try:
            async with mcp.session_manager.run():
                yield
        finally:
            for item in list(tasks | question_tasks) + ([task] if task else []):
                item.cancel()
            for item in list(tasks | question_tasks) + ([task] if task else []):
                with suppress(asyncio.CancelledError, Exception):
                    await item
            db.close()
            lock.release()

    app = FastAPI(title=PRODUCT_NAME, version='0.1.0', lifespan=lifespan)
    app.state.records, app.state.db, app.state.search, app.state.auth = records, db, search, auth

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse({'schema_version': 1, 'ok': False, 'error': exc.as_dict()}, status_code=404 if exc.code == 'NOT_FOUND' else 409 if 'CONFLICT' in exc.code else 400)

    @app.exception_handler(AuthError)
    async def auth_error(request, exc):
        return JSONResponse({'schema_version': 1, 'ok': False, 'error': exc.as_dict()}, status_code=401 if exc.code == 'LOGIN_REQUIRED' else 400)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error('VALIDATION_ERROR', '입력 형식과 필수 항목을 확인해 주세요.', 422)

    @app.middleware('http')
    async def local_security(request: Request, call_next):
        host = request.headers.get('host', '').split(':')[0]
        if host not in ('127.0.0.1', 'localhost'):
            return error('INVALID_HOST', '로컬 주소로 접속해 주세요.', 421)
        if host == 'localhost' and request.url.path == '/':
            return RedirectResponse(settings.origin + '/', status_code=307)
        origin = request.headers.get('origin')
        allowed_origins = {settings.origin, settings.origin.replace('127.0.0.1', 'localhost')}
        # Development frontend proxies API requests; it still needs the session token.
        if os.environ.get('SECOND_BRAIN_DEV_ORIGIN'):
            allowed_origins.add(os.environ['SECOND_BRAIN_DEV_ORIGIN'])
        if origin and origin not in allowed_origins:
            return error('INVALID_ORIGIN', '허용되지 않은 요청 출처입니다.', 403)
        if request.url.path.startswith('/mcp'):
            provided = request.headers.get('authorization', '')
            if not secrets.compare_digest(provided, 'Bearer ' + local['mcp_token']):
                return error('UNAUTHORIZED', 'MCP 연결 인증이 필요합니다.', 401)
            return await call_next(request)
        sid = request.cookies.get('sb_session')
        session = sessions.get(sid)
        if session and session['expires'] <= time.time():
            sessions.pop(sid, None)
            session = None
        request.state.session_id = sid if session else None
        if session:
            request.state.records = RecordService(db, principal_scope='web:local', session_scope=sid, created_via='web')
        path = request.url.path
        if path.startswith('/api/') and path != '/api/v1/session':
            if not session:
                return error('SESSION_REQUIRED', '화면을 새로 고친 뒤 다시 시도해 주세요.', 401)
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                token = request.headers.get('x-csrf-token', '')
                if not secrets.compare_digest(token, session['csrf']):
                    return error('CSRF_REQUIRED', '요청을 확인하지 못했습니다. 화면을 새로 고쳐 주세요.', 403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        if path.startswith(('/api/', '/auth/')):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def confirm_deletion(request, data, service):
        if not getattr(request.state, 'session_id', None):
            raise DomainError('CONFIRMATION_REQUIRED', '웹에서 다시 확인해 주세요.')
        # Only the CSRF-protected, session-bound confirm button uses this endpoint.
        return service.confirm_deletion(data.confirmation_token)
    app.state.confirm_deletion = confirm_deletion
    api.install_error_handlers(app)
    app.include_router(api.router)

    @app.get('/api/v1/session')
    async def session(request: Request):
        sid = request.state.session_id
        if not sid:
            now = time.time()
            for key in list(sessions):
                if sessions[key]['expires'] <= now:
                    sessions.pop(key, None)
            sid = secrets.token_urlsafe(40)
            sessions[sid] = {'csrf': secrets.token_urlsafe(40), 'expires': now + 43200}
        response = JSONResponse(ok({'csrf_token': sessions[sid]['csrf']}))
        response.set_cookie('sb_session', sid, httponly=True, samesite='lax', max_age=43200, path='/')
        return response

    @app.get('/health')
    async def health():
        return ok({'status': 'ready', 'version': '0.1.0', 'application': PRODUCT_ID,
                   'storage_id': storage_fingerprint(settings.data_dir)})

    @app.get('/api/v1/settings')
    async def get_settings(request: Request):
        return ok({'auth': auth.status(request.state.session_id), 'index': await asyncio.to_thread(search.status), 'data_dir': str(settings.data_dir)})

    @app.patch('/api/v1/settings')
    async def set_settings(data: ModelInput):
        previous_generation = auth.model_generation
        if 'reasoning_effort' in data.model_fields_set:
            auth.select_model(data.model, reasoning_effort=data.reasoning_effort)
        else:
            auth.select_model(data.model)
        if auth.model_generation != previous_generation:
            for task in list(question_tasks):
                task.cancel()
        return ok(auth.status())

    @app.post('/api/v1/auth/login')
    async def login(data: LoginInput, request: Request):
        return ok({'authorization_url': auth.begin(request.state.session_id, data.account_id,
                                                   replace_account=data.replace_account)})

    @app.post('/api/v1/auth/cancel')
    async def cancel_login(request: Request):
        return ok(auth.cancel_login(request.state.session_id))

    @app.get('/auth/callback')
    async def callback(request: Request):
        try:
            await auth.callback(dict(request.query_params), request.state.session_id)
            try:
                await auth.list_models()
            except (AuthError, httpx.HTTPError):
                auth.last_error = '모델 목록을 가져오지 못했습니다. 설정에서 다시 시도해 주세요.'
            return RedirectResponse('/?login=complete', status_code=303)
        except AuthError as exc:
            auth.last_error = exc.message
            return RedirectResponse('/?login=failed', status_code=303)

    @app.post('/api/v1/auth/logout')
    async def logout():
        for task in list(question_tasks):
            task.cancel()
        return ok(await auth.logout())

    @app.get('/api/v1/auth/models')
    async def models():
        return ok({'models': await auth.list_models()})

    @app.post('/api/v1/index/prepare')
    async def prepare():
        if any(getattr(t, 'get_name', lambda: '')() == 'prepare' and not t.done() for t in tasks):
            return ok({'status': 'preparing'})
        async def run_prepare():
            try:
                await asyncio.to_thread(search.prepare)
            except Exception:
                pass  # SearchService records its sanitized failure state.
        task = asyncio.create_task(run_prepare(), name='prepare')
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return ok({'status': 'preparing'})

    @app.post('/api/v1/index/retry')
    async def retry():
        return ok(await asyncio.to_thread(search.retry))

    @app.post('/api/v1/search')
    async def search_route(data: SearchInput):
        return ok(await asyncio.to_thread(search.search, data))

    @app.post('/api/v1/context')
    async def context_route(data: ContextInput):
        return ok(await asyncio.to_thread(search.context, data))

    @app.get('/api/v1/graph')
    async def home_graph(data: Annotated[GraphInput, Query()]):
        return ok(await asyncio.to_thread(search.home_graph, data))

    @app.get('/api/v1/captures/{capture_id}/neighbors')
    async def neighbors(capture_id: str):
        return ok(await asyncio.to_thread(search.neighbors, capture_id))

    @app.post('/api/v1/questions')
    async def ask(data: QuestionInput, request: Request):
        def event(name, payload):
            return 'event: ' + name + '\ndata: ' + json.dumps({'request_id': str(data.request_id), **payload}, ensure_ascii=False) + '\n\n'
        async def stream():
            yield event('started', {})
            yield event('progress', {'stage': 'searching'})
            task = asyncio.create_task(questions.run(data))
            question_tasks.add(task)
            try:
                while not task.done():
                    if await request.is_disconnected():
                        task.cancel()
                        return
                    done, _ = await asyncio.wait([task], timeout=1)
                    if not done:
                        yield ': keepalive\n\n'
                result = task.result()
                questions.revalidate(result)
                for part in result['parts']:
                    try:
                        questions.revalidate(result)
                    except (AuthError, DomainError):
                        yield event('invalidated', {'part_ids': [p['part_id'] for p in result['parts']], 'reason': 'source_changed'})
                        return
                    yield event('answer_part', {'part': part})
                try:
                    questions.revalidate(result)
                except (AuthError, DomainError):
                    yield event('invalidated', {'part_ids': [p['part_id'] for p in result['parts']], 'reason': 'source_changed'})
                    return
                yield event('completed', {'result': {k: v for k, v in result.items() if not k.startswith('_')}})
            except (AuthError, DomainError) as exc:
                yield event('error', {'error': exc.as_dict()})
            except TimeoutError:
                yield event('error', {'error': {'code': 'REQUEST_TIMEOUT', 'message': '검색 시간이 초과되었습니다. 질문을 나누어 주세요.', 'retryable': True}})
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise
                yield event('cancelled', {})
            except Exception:
                yield event('error', {'error': {'code': 'ANSWER_FAILED', 'message': '답변을 완료하지 못했습니다.', 'retryable': True}})
            finally:
                question_tasks.discard(task)
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})

    @app.post('/api/v1/backups')
    async def backup():
        def create_backup():
            directory = tempfile.TemporaryDirectory(prefix='second-brain-backup-')
            folder = Path(directory.name)
            snapshot = folder / 'brain.sqlite3'
            with sqlite3.connect(db.path) as source, sqlite3.connect(snapshot) as target:
                source.backup(target)
                schema_revision = target.execute('SELECT version_num FROM alembic_version').fetchone()[0]
                profiles = [{'id': row[0], 'model_id': row[1], 'model_revision': row[2], 'configuration': json.loads(row[3])}
                            for row in target.execute('SELECT id, model_id, model_revision, configuration FROM embedding_profiles')]
            manifest = {'schema_version': 1, 'app_version': '0.1.0', 'created_at': time.time(),
                        'includes_soft_deleted_history': True, 'schema_revision': schema_revision, 'embedding_profiles': profiles, 'database_sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                        'excluded': ['credentials', 'models', 'search_index']}
            archive = folder / 'second-brain-backup.zip'
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
                zipped.write(snapshot, 'brain.sqlite3')
                zipped.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
            return directory, archive
        directory, archive = await asyncio.to_thread(create_backup)
        return FileResponse(archive, filename='second-brain-backup.zip', media_type='application/zip', background=BackgroundTask(directory.cleanup))

    app.mount('/mcp', mcp_app)
    if settings.frontend_dir and settings.frontend_dir.is_dir():
        app.mount('/', StaticFiles(directory=settings.frontend_dir, html=True), name='web')
    return app


def run():
    import uvicorn
    settings = Settings.load()
    settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Acquire before auth initialization and migrations, including foreground run.
    # The lifespan reuses this reentrant lock and releases only its acquisition.
    lock = FileLock(str(settings.data_dir / 'server.lock'), mode=0o600)
    with lock.acquire(timeout=0):
        uvicorn.run(create_app(settings, server_lock=lock), host='127.0.0.1', port=settings.port, access_log=False)


if __name__ == '__main__':
    run()
