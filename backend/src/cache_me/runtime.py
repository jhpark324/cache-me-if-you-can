"""Explicit local server startup and credential-free readiness diagnostics."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import time

from filelock import FileLock, Timeout
import httpx

from .brand import PRODUCT_ID
from .config import Settings


class RuntimeStartError(RuntimeError):
    def __init__(self, status: str, message: str):
        self.status = status
        super().__init__(message)


def storage_fingerprint(data_dir: Path) -> str:
    """Identify a configured location without publishing its filesystem path."""
    location = os.path.normcase(str(Path(data_dir).resolve()))
    return hashlib.sha256(location.encode('utf-8')).hexdigest()


def _result(settings: Settings, status: str, message: str) -> dict:
    return {'status': status, 'url': settings.origin, 'message': message}


def inspect_runtime(settings: Settings, *, timeout: float = 1.0) -> dict:
    """Inspect only the selected loopback endpoint, without credentials or writes."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('진단 제한 시간은 양수여야 합니다.')
    deadline = time.monotonic() + timeout
    try:
        with socket.create_connection(('127.0.0.1', settings.port), timeout=timeout):
            pass
    except ConnectionRefusedError:
        return _result(settings, 'stopped', '캐시미 서버가 실행 중이지 않습니다. start 명령으로 시작하세요.')
    except OSError:
        return _result(settings, 'unreachable', '지정한 로컬 주소의 연결 상태를 확인하지 못했습니다.')

    try:
        # Ignore proxy environment settings; never forward credentials or redirects.
        remaining = max(.001, deadline - time.monotonic())
        with httpx.Client(timeout=remaining, trust_env=False, follow_redirects=False) as client:
            with client.stream('GET', settings.origin + '/health') as response:
                if response.status_code != 200:
                    return _result(settings, 'port_in_use', '지정한 포트의 서비스가 캐시미 준비 상태를 반환하지 않습니다.')
                body = bytearray()
                for chunk in response.iter_bytes():
                    if time.monotonic() >= deadline:
                        return _result(settings, 'unreachable', '서비스가 제한 시간 안에 준비 상태를 응답하지 않았습니다.')
                    body.extend(chunk)
                    if len(body) > 65536:
                        return _result(settings, 'port_in_use', '지정한 포트에서 예상하지 못한 응답을 받았습니다.')
                payload = json.loads(body)
    except httpx.ConnectError:
        return _result(settings, 'stopped', '캐시미 서버가 연결 확인 중 종료되었습니다. start 명령으로 시작하세요.')
    except (httpx.TimeoutException, httpx.NetworkError):
        return _result(settings, 'unreachable', '서비스가 제한 시간 안에 준비 상태를 응답하지 않았습니다.')
    except (httpx.HTTPError, ValueError, UnicodeError):
        return _result(settings, 'port_in_use', '지정한 포트에서 캐시미가 아닌 응답을 받았습니다.')

    data = payload.get('data') if isinstance(payload, dict) else None
    if not isinstance(data, dict) or payload.get('ok') is not True or data.get('application') != PRODUCT_ID:
        return _result(settings, 'port_in_use', '다른 서비스 또는 이전 버전이 포트를 사용 중입니다. 자동으로 종료하지 않습니다.')
    if data.get('storage_id') != storage_fingerprint(settings.data_dir):
        return _result(settings, 'data_dir_mismatch', '실행 중인 캐시미의 데이터 경로가 현재 설정과 다릅니다.')
    if data.get('status') != 'ready':
        return _result(settings, 'unreachable', '캐시미 서버가 아직 준비되지 않았습니다.')
    return _result(settings, 'ready', '지정한 데이터 경로의 캐시미 서버가 준비되었습니다.')


def _raise_result(result: dict) -> None:
    raise RuntimeStartError(result['status'], result['message'])


def _spawn_server(settings: Settings):
    log_path = settings.data_dir / 'runtime.log'
    try:
        existing = log_path.lstat()
    except FileNotFoundError:
        existing = None
    if existing is not None and not stat.S_ISREG(existing.st_mode):
        raise RuntimeStartError('start_failed', 'runtime.log가 일반 파일 경로가 아닙니다.')
    # Nonblocking open and a descriptor check also cover a path changed to a
    # FIFO/device after lstat; a preflight path check alone cannot guarantee it.
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(log_path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RuntimeStartError('start_failed', 'runtime.log가 일반 파일 경로가 아닙니다.')
        if os.name != 'nt':
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'ab') as log:
            fd = None
            env = dict(os.environ, CACHE_ME_DATA_DIR=str(settings.data_dir.resolve()),
                       CACHE_ME_PORT=str(settings.port))
            options = {'creationflags': subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP} \
                if os.name == 'nt' else {'start_new_session': True}
            return subprocess.Popen([sys.executable, '-m', 'cache_me.main'],
                cwd=Path(__file__).resolve().parents[1], env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, close_fds=True, **options)
    finally:
        if fd is not None:
            os.close(fd)


def _stop_owned_child(process) -> None:
    """Only clean up the child returned by our own Popen call."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def ensure_running(settings: Settings, *, timeout: float = 15.0) -> dict:
    """Start one detached backend, or reuse a matching backend already running."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('시작 제한 시간은 양수여야 합니다.')
    deadline = time.monotonic() + timeout

    def inspect():
        return inspect_runtime(settings, timeout=max(.001, min(.5, deadline - time.monotonic())))

    result = inspect()
    if result['status'] == 'ready':
        return {**result, 'started': False}
    if result['status'] != 'stopped':
        _raise_result(result)

    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with FileLock(str(settings.data_dir / 'runtime-start.lock'), mode=0o600).acquire(
                timeout=max(0, deadline - time.monotonic())):
            result = inspect()
            if result['status'] == 'ready':
                return {**result, 'started': False}
            if result['status'] != 'stopped':
                _raise_result(result)
            try:
                # A server on another port may own this same store. Never start
                # another process against it merely because this endpoint is down.
                with FileLock(str(settings.data_dir / 'server.lock'), mode=0o600).acquire(timeout=0):
                    pass
            except Timeout:
                raise RuntimeStartError('data_dir_in_use',
                    '이 데이터 경로의 서버가 이미 실행 중입니다. 기존 서버의 포트와 설정을 확인하세요.') from None

            if time.monotonic() >= deadline:
                raise RuntimeStartError('start_timeout', '서버 시작 대기 시간이 초과되었습니다.')
            process = _spawn_server(settings)
            try:
                while time.monotonic() < deadline:
                    result = inspect()
                    if result['status'] == 'ready':
                        alive = process.poll() is None
                        return {**result, 'started': alive, **({'pid': process.pid} if alive else {})}
                    if process.poll() is not None:
                        raise RuntimeStartError('start_failed',
                            '캐시미 서버가 준비 전에 종료되었습니다. 데이터 경로의 runtime.log를 확인하세요.')
                    if result['status'] not in ('stopped', 'unreachable'):
                        _raise_result(result)
                    remaining = deadline - time.monotonic()
                    if remaining > 0:
                        time.sleep(min(.1, remaining))
                raise RuntimeStartError('start_timeout',
                    '캐시미 서버 준비 시간이 초과되어 이번에 시작한 프로세스를 종료했습니다. runtime.log를 확인하세요.')
            except BaseException:
                _stop_owned_child(process)
                raise
    except Timeout:
        raise RuntimeStartError('start_timeout', '다른 시작 작업을 기다리는 시간이 초과되었습니다.') from None
    except OSError:
        raise RuntimeStartError('start_failed',
            '캐시미 서버를 시작하지 못했습니다. Python 실행 경로와 데이터 폴더 권한을 확인하세요.') from None


def main() -> None:
    parser = argparse.ArgumentParser(description='캐시미 로컬 서버 시작과 진단')
    parser.add_argument('action', choices=['start', 'doctor'])
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--port', type=int)
    parser.add_argument('--timeout', type=float, default=15.0)
    args = parser.parse_args()
    try:
        settings = Settings.load(data_dir=args.data_dir, port=args.port)
        result = ensure_running(settings, timeout=args.timeout) if args.action == 'start' \
            else inspect_runtime(settings, timeout=min(args.timeout, 1.0))
        success = result['status'] == 'ready'
        print(json.dumps({'ok': success, 'data': result}, ensure_ascii=False))
        if not success:
            raise SystemExit(1)
    except (RuntimeStartError, ValueError) as exc:
        code = exc.status if isinstance(exc, RuntimeStartError) else 'invalid_configuration'
        message = str(exc) if isinstance(exc, RuntimeStartError) else '포트와 제한 시간 설정을 확인하세요.'
        print(json.dumps({'ok': False, 'error': {'code': code, 'message': message}}, ensure_ascii=False))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
