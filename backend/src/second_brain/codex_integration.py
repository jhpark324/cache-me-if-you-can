"""Install the local skill and secret-free Codex HTTP MCP configuration."""
from __future__ import annotations

import argparse
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
from .brand import PRODUCT_NAME

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
    token = value.get('mcp_token')
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


def install(codex_home: Path, skill_source: Path, server: dict, *, replace: bool = False) -> dict:
    config = codex_home / 'config.toml'
    package = codex_home / 'skills' / SKILL_SLUG
    skill = package / 'SKILL.md'
    artifacts = {skill: skill_source.read_text(encoding='utf-8')}
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
            'legacy_skill': legacy_statuses['second-brain'],
            'legacy_skills': legacy_statuses,
            'restart_required': True}


def main() -> None:
    parser = argparse.ArgumentParser(description=f'{PRODUCT_NAME} Codex 연결')
    parser.add_argument('action', choices=['install', 'headers'])
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--codex-home', type=Path)
    parser.add_argument('--skill-source', type=Path)
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    settings = Settings.load()
    data_dir = args.data_dir or settings.data_dir
    try:
        if args.action == 'headers':
            # This output is the Codex header-helper protocol, never a user-facing command.
            print(json.dumps(header_value(data_dir)))
            return
        home = args.codex_home or Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
        source = args.skill_source or Path(__file__).resolve().parents[3] / 'docs/skills' / SKILL_SLUG / 'SKILL.md'
        header_value(data_dir)  # Validate existence without printing or copying the secret.
        result = install(home, source, server_config(Path(sys.executable), data_dir, settings.port), replace=args.replace)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError) as exc:
        # JSON/parser exceptions can contain credentials, so print only a fixed error for headers.
        if args.action == 'headers':
            raise SystemExit(f'{PRODUCT_NAME} MCP 인증 파일을 사용할 수 없습니다. 서버를 먼저 실행하세요.') from None
        raise SystemExit(str(exc)) from None


if __name__ == '__main__':
    main()
