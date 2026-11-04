"""Install the local skill and secret-free Codex HTTP MCP configuration."""
from __future__ import annotations

import argparse
from dataclasses import replace as replace_settings
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import tomllib

from filelock import FileLock

from .config import Settings
from .brand import PRODUCT_NAME, DEFAULT_PORT
from .runtime import inspect_runtime

START = '# BEGIN SECOND BRAIN MANAGED MCP\n'
END = '# END SECOND BRAIN MANAGED MCP\n'
SKILL_NAME = 'cache-me'
SKILL_SLUG = 'cache-me'
# Only this project's unmodified previous releases are eligible for automatic migration.
LEGACY_SKILLS_SHA256 = {
    'second-brain': frozenset({'7fedb37a9057bcc7fa0f9b5b36893d5ae52dc23cf6c48de5a07fe9257e416590'}),
    'cacheme': frozenset({'e585fd63752ddf758a45d0cf5a77db338a0c22d7a40c40ee6a89b018baa3f96c'}),
}


def header_value(data_dir: Path) -> dict[str, str]:
    # Never fall back to Codex credentials or the application's OAuth store.
    value = json.loads((data_dir / 'local-access.json').read_text(encoding='utf-8'))
    token = value.get('mcp_token') if isinstance(value, dict) else None
    if not isinstance(token, str) or not token or any(c.isspace() for c in token):
        raise ValueError('Invalid local MCP credential')
    return {'Authorization': 'Bearer ' + token}


def server_config(python: Path, data_dir: Path, port: int) -> dict:
    if not 1 <= port <= 65535:
        raise ValueError('Invalid port')
    command = [str(python.absolute()), '-m', 'second_brain.codex_integration',
               'headers', '--data-dir', str(data_dir.absolute())]
    helper = subprocess.list2cmdline(command) if os.name == 'nt' else shlex.join(command)
    return {'url': f'http://127.0.0.1:{port}/mcp/', 'http_headers_helper': helper,
            'startup_timeout_sec': 20, 'tool_timeout_sec': 120}


def runtime_config(python: Path, data_dir: Path, port: int, codex_home: Path) -> dict:
    """Installed recovery commands use the same interpreter, store and endpoint."""
    python, data_dir, codex_home = python.absolute(), data_dir.resolve(), codex_home.absolute()
    server = server_config(python, data_dir, port)
    common = ['--data-dir', str(data_dir), '--port', str(port)]
    return {'schema_version': 1, 'python': str(python), 'data_dir': str(data_dir),
            'port': port, 'web_url': f'http://127.0.0.1:{port}/', 'mcp_url': server['url'],
            'commands': {
                'doctor': [str(python), '-m', 'second_brain.codex_integration', 'doctor',
                           *common, '--codex-home', str(codex_home)],
                'start': [str(python), '-m', 'second_brain.runtime', 'start', *common]}}


def doctor(settings: Settings, codex_home: Path, *, python: Path | None = None) -> dict:
    """Read-only diagnostics. Never print credentials or arbitrary config values."""
    runtime = inspect_runtime(settings)
    try:
        header_value(settings.data_dir)
        authentication = {'status': 'ready', 'message': '로컬 MCP 인증 파일을 사용할 수 있습니다.'}
    except (OSError, ValueError):
        authentication = {'status': 'unavailable', 'message': '로컬 MCP 인증 파일을 사용할 수 없습니다.'}

    expected = server_config(python or Path(sys.executable), settings.data_dir, settings.port)
    config_path = codex_home / 'config.toml'
    try:
        parsed = tomllib.loads(config_path.read_text(encoding='utf-8'))
        servers = parsed.get('mcp_servers', {})
        configured = servers.get('second_brain') if isinstance(servers, dict) else None
        if configured is None:
            config = {'status': 'missing', 'message': 'second_brain MCP 설정이 없습니다.'}
        elif not isinstance(configured, dict):
            config = {'status': 'invalid', 'message': 'second_brain MCP 설정 형식이 올바르지 않습니다.'}
        else:
            differences = [key for key in ('url', 'http_headers_helper') if configured.get(key) != expected[key]]
            if configured.get('enabled') is False:
                differences.append('enabled')
            for key in ('bearer_token_env_var', 'http_headers', 'env_http_headers'):
                if configured.get(key):
                    differences.append(key)
            config = {'status': 'mismatch' if differences else 'ready',
                      'message': '설치한 MCP 설정을 확인하세요.' if differences else 'MCP 주소와 인증 helper 설정이 일치합니다.',
                      'different_fields': differences}
    except FileNotFoundError:
        config = {'status': 'missing', 'message': 'Codex 설정 파일이 없습니다.'}
    except (OSError, ValueError):
        config = {'status': 'invalid', 'message': 'Codex 설정 파일을 읽거나 해석할 수 없습니다.'}

    next_steps = []
    if runtime['status'] == 'stopped':
        next_steps.append('준비된 환경에서 start 명령으로 서버를 시작하세요.')
    elif runtime['status'] != 'ready':
        next_steps.append(runtime['message'])
    if authentication['status'] != 'ready':
        next_steps.append('최초 실행 전이라면 start를 실행하세요. 기존 인증 문제는 파일 내용을 공유하지 말고 확인하세요.')
    if config['status'] != 'ready':
        next_steps.append('같은 데이터 경로와 포트로 install-codex를 실행하세요. 관리 설정을 갱신하려면 --replace가 필요합니다.')
    success = all(item['status'] == 'ready' for item in (runtime, authentication, config))
    if success:
        next_steps.append('도구가 보이지 않으면 Codex 연결을 다시 읽거나 새 세션을 여세요. 서버 정상 상태만으로 현재 대화의 도구 목록은 갱신되지 않습니다.')
    return {'ok': success, 'data': {'runtime': runtime, 'authentication': authentication,
            'codex': config, 'next_steps': next_steps,
            'scope': '로컬 서버·인증 파일·설정 진단입니다. 현재 Codex 대화의 MCP 연결 성공 여부는 검사하지 않습니다.'}}


def updated_config(original: str, server: dict, *, replace: bool = False) -> str:
    parsed = tomllib.loads(original)
    existing = parsed.get('mcp_servers', {}).get('second_brain')
    if existing == server:
        return original
    if existing is not None:
        if not replace:
            raise ValueError(f'{PRODUCT_NAME} MCP 설정이 다릅니다. 확인 후 --replace를 사용하세요.')
        if original.count(START) != 1 or original.count(END) != 1:
            raise ValueError(f'외부에서 작성한 {PRODUCT_NAME} MCP 설정은 자동 교체하지 않습니다.')
        begin, finish = original.index(START), original.index(END) + len(END)
        if finish <= begin:
            raise ValueError('잘못된 관리 설정 구간입니다.')
        # Only our managed server may reside in the replacement span.
        block = tomllib.loads(original[begin + len(START):finish - len(END)])
        if set(block) != {'mcp_servers'} or set(block['mcp_servers']) != {'second_brain'}:
            raise ValueError('관리 구간에 다른 설정이 있어 교체하지 않습니다.')
        remainder = original[:begin] + original[finish:]
        if 'second_brain' in tomllib.loads(remainder).get('mcp_servers', {}):
            raise ValueError(f'관리 구간 밖에 {PRODUCT_NAME} MCP 설정이 있습니다.')
        original = remainder
    elif START in original or END in original:
        raise ValueError('불완전한 관리 설정 구간입니다.')
    block = START + '[mcp_servers.second_brain]\n'
    for key, value in server.items():
        block += f'{key} = {json.dumps(value, ensure_ascii=True)}\n'
    result = original.rstrip() + '\n\n' + block + END
    expected = dict(parsed.get('mcp_servers', {}))
    expected['second_brain'] = server
    verified = tomllib.loads(result)
    assert verified.get('mcp_servers') == expected
    assert {k: v for k, v in verified.items() if k != 'mcp_servers'} == {
        k: v for k, v in parsed.items() if k != 'mcp_servers'}
    return result


def atomic_write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def install(codex_home: Path, skill_source: Path, server: dict, *, replace: bool = False,
            runtime_metadata: dict | None = None) -> dict:
    config = codex_home / 'config.toml'
    package = codex_home / 'skills' / SKILL_SLUG
    skill = package / 'SKILL.md'
    artifacts = {skill: skill_source.read_text(encoding='utf-8')}
    runtime_path = package / 'runtime.json'
    if runtime_metadata is not None:
        if runtime_metadata.get('mcp_url') != server['url']:
            raise ValueError('런타임 정보와 MCP 주소가 일치하지 않습니다.')
        artifacts[runtime_path] = json.dumps(runtime_metadata, ensure_ascii=False, indent=2) + '\n'
    metadata_source = skill_source.parent / 'agents' / 'openai.yaml'
    metadata = package / 'agents' / 'openai.yaml'
    if metadata_source.exists():
        artifacts[metadata] = metadata_source.read_text(encoding='utf-8')
    codex_home.mkdir(parents=True, exist_ok=True)
    with FileLock(str(codex_home / '.second-brain-install.lock')):
        original = config.read_text(encoding='utf-8') if config.exists() else ''
        result = updated_config(original, server, replace=replace)

        def check_directory(path: Path) -> None:
            for parent in (path, *path.parents):
                if parent == codex_home:
                    break
                if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                    raise ValueError(f'설치 경로가 일반 디렉터리가 아닙니다: {parent}')

        writes = {}
        for path, canonical in artifacts.items():
            check_directory(path.parent)
            installed = path.read_text(encoding='utf-8') if path.exists() else None
            if installed != canonical:
                if path.exists() and not replace:
                    raise ValueError(f'설치된 {SKILL_NAME} 파일이 다릅니다: {path}. 확인 후 --replace를 사용하세요.')
                writes[path] = canonical

        legacy_statuses = {}
        migrations = []
        for slug, known_fingerprints in LEGACY_SKILLS_SHA256.items():
            legacy = codex_home / 'skills' / slug
            legacy_skill = legacy / 'SKILL.md'
            legacy_status = {'status': 'absent', 'path': str(legacy)}
            legacy_statuses[slug] = legacy_status
            if legacy.exists() or legacy.is_symlink():
                legacy_status['status'] = 'preserved'
                if legacy.is_dir() and not legacy.is_symlink() and legacy_skill.is_file() and not legacy_skill.is_symlink():
                    fingerprint = hashlib.sha256(legacy_skill.read_bytes()).hexdigest()
                    if fingerprint in known_fingerprints:
                        backups = codex_home / '.skill-backups'
                        check_directory(backups)
                        stem = f'{slug}-{fingerprint[:12]}'
                        backup = backups / stem
                        suffix = 1
                        while backup.exists() or backup.is_symlink():
                            backup = backups / f'{stem}-{suffix}'
                            suffix += 1
                        migrations.append((legacy, backup, legacy_status))

        # Preflight the whole package, config, and migration before changing any of them.
        for path, canonical in writes.items():
            atomic_write(path, canonical)
        if result != original:
            atomic_write(config, result)
        for legacy, backup, legacy_status in migrations:
            backup.parent.mkdir(parents=True, exist_ok=True)
            legacy.rename(backup)
            legacy_status.update(status='backed_up', backup=str(backup))
    return {'config': str(config), 'skill': str(skill), 'server': 'second_brain',
            'skill_name': SKILL_NAME, 'skill_slug': SKILL_SLUG,
            'metadata': str(metadata) if metadata in artifacts else None,
            'runtime_metadata': str(runtime_path) if runtime_path in artifacts else None,
            'legacy_skill': legacy_statuses['second-brain'],
            'legacy_skills': legacy_statuses,
            'restart_required': True}


def main() -> None:
    parser = argparse.ArgumentParser(description=f'{PRODUCT_NAME} Codex 연결')
    parser.add_argument('action', choices=['install', 'headers', 'doctor'])
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--codex-home', type=Path)
    parser.add_argument('--skill-source', type=Path)
    parser.add_argument('--replace', action='store_true')
    parser.add_argument('--port', type=int)
    args = parser.parse_args()
    try:
        if args.action == 'headers':
            # This output is the Codex header-helper protocol, never a user-facing command.
            # Credential lookup is independent of the server's port configuration.
            data_dir = args.data_dir if args.data_dir is not None else Settings.load(port=DEFAULT_PORT).data_dir
            print(json.dumps(header_value(data_dir)))
            return
        settings = Settings.load(data_dir=args.data_dir, port=args.port)
        settings = replace_settings(settings, data_dir=settings.data_dir.resolve())
        data_dir = settings.data_dir
        home = args.codex_home or Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
        if args.action == 'doctor':
            result = doctor(settings, home)
            print(json.dumps(result, ensure_ascii=False))
            raise SystemExit(0 if result['ok'] else 1)
        source = args.skill_source or Path(__file__).resolve().parents[3] / 'docs/skills' / SKILL_SLUG / 'SKILL.md'
        try:
            header_value(data_dir)  # Validate existence without printing or copying the secret.
        except (OSError, ValueError):
            raise ValueError('로컬 MCP 인증 파일을 사용할 수 없습니다. 서버를 먼저 실행하세요.') from None
        result = install(home, source, server_config(Path(sys.executable), data_dir, settings.port),
                         replace=args.replace,
                         runtime_metadata=runtime_config(Path(sys.executable), data_dir, settings.port, home))
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError) as exc:
        # JSON/parser exceptions can contain credentials, so print only a fixed error for headers.
        if args.action == 'headers':
            raise SystemExit(f'{PRODUCT_NAME} MCP 인증 파일을 사용할 수 없습니다. 서버를 먼저 실행하세요.') from None
        if args.action == 'doctor':
            print(json.dumps({'ok': False, 'error': {'code': 'invalid_configuration',
                  'message': '데이터 경로와 포트 설정을 확인하세요.'}}, ensure_ascii=False))
            raise SystemExit(1) from None
        if isinstance(exc, tomllib.TOMLDecodeError):
            raise SystemExit('Codex 설정 파일을 해석할 수 없습니다.') from None
        raise SystemExit(str(exc)) from None


if __name__ == '__main__':
    main()
