"""Local lifecycle tests use synthetic stores and ephemeral loopback ports only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading

from filelock import FileLock
import pytest

from cache_me import runtime
from cache_me.brand import PRODUCT_ID
from cache_me.config import Settings


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def health_payload(data_dir, **changes):
    return {'ok': True, 'data': {'status': 'ready', 'version': '0.1.0',
        'application': PRODUCT_ID, 'storage_id': runtime.storage_fingerprint(data_dir), **changes}}


@contextmanager
def health_server(payload, *, port=0, response_status=200):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append({'path': self.path, 'authorization': self.headers.get('authorization')})
            body = json.dumps(payload).encode()
            self.send_response(response_status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        yield server.server_port, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class FakeProcess:
    pid = 12345

    def __init__(self, returncode=None, stubborn=False):
        self.returncode = returncode
        self.stubborn = stubborn
        self.terminations = 0
        self.kills = 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminations += 1
        if not self.stubborn:
            self.returncode = -15

    def kill(self):
        self.kills += 1
        self.returncode = -9

    def wait(self, timeout):
        if self.returncode is None:
            raise subprocess.TimeoutExpired('synthetic child', timeout)
        return self.returncode


def stopped(settings, **kwargs):
    return {'status': 'stopped', 'url': settings.origin, 'message': 'stopped'}


def test_storage_fingerprint_normalizes_paths_without_reading_store(tmp_path):
    missing = tmp_path / 'does-not-exist'
    assert runtime.storage_fingerprint(missing / '..' / missing.name) == runtime.storage_fingerprint(missing)
    assert runtime.storage_fingerprint(missing) != runtime.storage_fingerprint(tmp_path / 'other')
    assert not missing.exists()


def test_stopped_diagnostic_does_not_create_data_directory(tmp_path):
    data = tmp_path / 'new-store'
    result = runtime.inspect_runtime(Settings(data, port=free_port()))
    assert result['status'] == 'stopped'
    assert not data.exists()


def test_ready_diagnostic_ignores_proxies_and_sends_no_credentials(tmp_path, monkeypatch):
    data = tmp_path / 'new-store'
    monkeypatch.setenv('HTTP_PROXY', 'http://127.0.0.1:1')
    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:1')
    with health_server(health_payload(data)) as (port, requests):
        result = runtime.inspect_runtime(Settings(data, port=port))
    assert result['status'] == 'ready'
    assert requests == [{'path': '/health', 'authorization': None}]
    assert not data.exists()


@pytest.mark.parametrize('payload,status,expected', [
    ({'ok': True, 'data': {'status': 'ready', 'version': '0.1.0'}}, 200, 'port_in_use'),
    ({'ok': True, 'data': {'application': 'another-app'}}, 200, 'port_in_use'),
    ({'ok': False}, 200, 'port_in_use'),
    (['not', 'an', 'object'], 200, 'port_in_use'),
    ({}, 302, 'port_in_use'),
])
def test_wrong_services_are_not_reused(tmp_path, payload, status, expected):
    with health_server(payload, response_status=status) as (port, _):
        settings = Settings(tmp_path, port=port)
        assert runtime.inspect_runtime(settings)['status'] == expected
        with pytest.raises(runtime.RuntimeStartError) as exc:
            runtime.ensure_running(settings)
        assert exc.value.status == expected


def test_another_store_is_not_reused_or_started(tmp_path, monkeypatch):
    data = tmp_path / 'wanted'
    monkeypatch.setattr(runtime, '_spawn_server', lambda _: pytest.fail('Must not launch another server'))
    with health_server(health_payload(tmp_path / 'other')) as (port, _):
        settings = Settings(data, port=port)
        assert runtime.inspect_runtime(settings)['status'] == 'data_dir_mismatch'
        with pytest.raises(runtime.RuntimeStartError) as exc:
            runtime.ensure_running(settings)
    assert exc.value.status == 'data_dir_mismatch'
    assert not data.exists()


def test_matching_server_is_reused_without_filesystem_mutation(tmp_path, monkeypatch):
    data = tmp_path / 'new-store'
    monkeypatch.setattr(runtime, '_spawn_server', lambda _: pytest.fail('Must reuse matching server'))
    with health_server(health_payload(data)) as (port, _):
        result = runtime.ensure_running(Settings(data, port=port))
    assert result['status'] == 'ready' and result['started'] is False
    assert 'pid' not in result
    assert not data.exists()


def test_store_already_running_on_another_port_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, '_spawn_server', lambda _: pytest.fail('Must not start against locked data'))
    with FileLock(str(tmp_path / 'server.lock')):
        with pytest.raises(runtime.RuntimeStartError) as exc:
            runtime.ensure_running(Settings(tmp_path, port=free_port()))
    assert exc.value.status == 'data_dir_in_use'


def test_simultaneous_starts_launch_one_child(tmp_path, monkeypatch):
    settings = Settings(tmp_path, port=free_port())
    first_checks = threading.Barrier(2)
    seen = threading.local()
    inspect = runtime.inspect_runtime
    servers = []
    processes = []

    def synchronized_initial_check(current, **kwargs):
        result = inspect(current, **kwargs)
        if not getattr(seen, 'checked', False):
            seen.checked = True
            first_checks.wait(timeout=3)
        return result

    def spawn(current):
        server = health_server(health_payload(current.data_dir), port=current.port)
        server.__enter__()
        servers.append(server)
        process = FakeProcess()
        processes.append(process)
        return process

    monkeypatch.setattr(runtime, 'inspect_runtime', synchronized_initial_check)
    monkeypatch.setattr(runtime, '_spawn_server', spawn)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: runtime.ensure_running(settings, timeout=5), range(2)))
        assert len(processes) == 1
        assert sorted(item['started'] for item in results) == [False, True]
        assert all(item['status'] == 'ready' for item in results)
        assert processes[0].terminations == 0
    finally:
        for server in servers:
            server.__exit__(None, None, None)


@pytest.mark.parametrize('stubborn', [False, True])
def test_start_timeout_only_cleans_up_owned_child(tmp_path, monkeypatch, stubborn):
    process = FakeProcess(stubborn=stubborn)
    monkeypatch.setattr(runtime, 'inspect_runtime', stopped)
    monkeypatch.setattr(runtime, '_spawn_server', lambda _: process)
    with pytest.raises(runtime.RuntimeStartError) as exc:
        runtime.ensure_running(Settings(tmp_path, port=free_port()), timeout=.03)
    assert exc.value.status == 'start_timeout'
    assert process.terminations == 1
    assert process.kills == int(stubborn)


def test_child_exit_has_safe_error_and_does_not_terminate_again(tmp_path, monkeypatch):
    process = FakeProcess(returncode=3)
    monkeypatch.setattr(runtime, 'inspect_runtime', stopped)
    monkeypatch.setattr(runtime, '_spawn_server', lambda _: process)
    with pytest.raises(runtime.RuntimeStartError) as exc:
        runtime.ensure_running(Settings(tmp_path, port=free_port()), timeout=1)
    assert exc.value.status == 'start_failed'
    assert 'runtime.log' in str(exc.value)
    assert process.terminations == 0


def test_spawn_uses_exact_runtime_store_and_private_log(tmp_path, monkeypatch):
    data = tmp_path / '한글 with spaces'
    data.mkdir()
    log = data / 'runtime.log'
    log.write_text('previous log\n')
    log.chmod(0o666)
    settings = Settings(data, port=free_port())
    calls = []
    process = FakeProcess()

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return process

    monkeypatch.setattr(runtime.subprocess, 'Popen', popen)
    assert runtime._spawn_server(settings) is process
    command, options = calls[0]
    assert command == [sys.executable, '-m', 'cache_me.main']
    assert options['env']['CACHE_ME_DATA_DIR'] == str(data.resolve())
    assert options['env']['CACHE_ME_PORT'] == str(settings.port)
    assert options['stdin'] == subprocess.DEVNULL
    assert options['stderr'] == subprocess.STDOUT
    assert options['close_fds'] is True
    if os.name != 'nt':
        assert options['start_new_session'] is True
        assert log.stat().st_mode & 0o777 == 0o600
    else:
        assert options['creationflags'] & subprocess.DETACHED_PROCESS
    assert log.read_text() == 'previous log\n'


def test_os_errors_do_not_echo_their_contents(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'inspect_runtime', stopped)

    def fail(_):
        raise OSError('a synthetic sensitive value')

    monkeypatch.setattr(runtime, '_spawn_server', fail)
    with pytest.raises(runtime.RuntimeStartError) as exc:
        runtime.ensure_running(Settings(tmp_path, port=free_port()))
    assert exc.value.status == 'start_failed'
    assert 'sensitive' not in str(exc.value)


@pytest.mark.parametrize('timeout', [0, -1, float('inf'), float('nan')])
def test_invalid_timeouts_do_not_start(tmp_path, timeout):
    settings = Settings(tmp_path / 'new-store', port=free_port())
    with pytest.raises(ValueError):
        runtime.ensure_running(settings, timeout=timeout)
    with pytest.raises(ValueError):
        runtime.inspect_runtime(settings, timeout=timeout)
    assert not settings.data_dir.exists()


def test_cli_doctor_is_read_only_and_returns_structured_failure(tmp_path):
    data = tmp_path / 'missing-store'
    result = subprocess.run([sys.executable, '-m', 'cache_me.runtime', 'doctor',
        '--data-dir', str(data), '--port', str(free_port())], capture_output=True, text=True)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload['ok'] is False and payload['data']['status'] == 'stopped'
    assert not data.exists()
    assert not result.stderr


def test_cli_explicit_port_overrides_invalid_ambient_port(tmp_path):
    data = tmp_path / 'missing-store'
    port = free_port()
    result = subprocess.run([sys.executable, '-m', 'cache_me.runtime', 'doctor',
        '--data-dir', str(data), '--port', str(port)], capture_output=True, text=True,
        env=dict(os.environ, CACHE_ME_PORT='invalid ambient port'))
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload['data']['status'] == 'stopped'
    assert payload['data']['url'] == f'http://127.0.0.1:{port}'
    assert not data.exists()
    assert not result.stderr


def test_real_backend_cold_start_reuse_and_owned_cleanup(tmp_path, monkeypatch):
    settings = Settings(tmp_path / 'isolated-store', port=free_port())
    spawn = runtime._spawn_server
    children = []

    def capture_child(current):
        child = spawn(current)
        children.append(child)
        return child

    monkeypatch.setattr(runtime, '_spawn_server', capture_child)
    try:
        first = runtime.ensure_running(settings, timeout=20)
        assert first['status'] == 'ready' and first['started'] is True
        assert first['pid'] == children[0].pid
        assert runtime.inspect_runtime(settings)['status'] == 'ready'
        again = runtime.ensure_running(settings, timeout=2)
        assert again['status'] == 'ready' and again['started'] is False
        assert len(children) == 1
        assert children[0].poll() is None
    finally:
        for child in children:
            runtime._stop_owned_child(child)
    assert children[0].poll() is not None
    assert runtime.inspect_runtime(settings)['status'] == 'stopped'


def test_foreground_run_locks_store_before_auth_or_database_initialization(tmp_path):
    # A store already served on another port must remain completely untouched.
    env = dict(os.environ, CACHE_ME_DATA_DIR=str(tmp_path), CACHE_ME_PORT=str(free_port()))
    with FileLock(str(tmp_path / 'server.lock')):
        result = subprocess.run([sys.executable, '-m', 'cache_me.main'],
            env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert {path.name for path in tmp_path.iterdir()} == {'server.lock'}


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='FIFO files require POSIX')
def test_existing_fifo_log_fails_without_blocking_or_starting(tmp_path):
    os.mkfifo(tmp_path / 'runtime.log')
    result = subprocess.run([sys.executable, '-m', 'cache_me.runtime', 'start',
        '--data-dir', str(tmp_path), '--port', str(free_port()), '--timeout', '.2'],
        capture_output=True, text=True, timeout=5)
    assert result.returncode == 1
    assert json.loads(result.stdout)['error']['code'] == 'start_failed'
    assert not (tmp_path / 'local-access.json').exists()
    assert not (tmp_path / 'cache-me.sqlite3').exists()


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='FIFO files require POSIX')
def test_log_replaced_by_fifo_after_preflight_is_rejected(tmp_path, monkeypatch):
    log = tmp_path / 'runtime.log'
    log.touch()
    real_open = os.open
    readers = []

    def race_open(path, flags, mode=0o777):
        assert flags & os.O_NONBLOCK
        log.unlink()
        os.mkfifo(log)
        # Keep one reader so opening the FIFO succeeds; fstat must still reject it.
        readers.append(real_open(log, os.O_RDONLY | os.O_NONBLOCK))
        return real_open(path, flags, mode)

    monkeypatch.setattr(runtime.os, 'open', race_open)
    monkeypatch.setattr(runtime.subprocess, 'Popen', lambda *a, **kw: pytest.fail('Must not spawn for FIFO'))
    try:
        with pytest.raises(runtime.RuntimeStartError) as exc:
            runtime._spawn_server(Settings(tmp_path, port=free_port()))
        assert exc.value.status == 'start_failed'
    finally:
        for fd in readers:
            os.close(fd)
