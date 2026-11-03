"""Install the local skill and secret-free Codex HTTP MCP configuration."""
from __future__ import annotations

import argparse
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
    skill = codex_home / 'skills' / 'second-brain' / 'SKILL.md'
    canonical = skill_source.read_text(encoding='utf-8')
    codex_home.mkdir(parents=True, exist_ok=True)
    with FileLock(str(codex_home / '.second-brain-install.lock')):
        original = config.read_text(encoding='utf-8') if config.exists() else ''
        result = updated_config(original, server, replace=replace)
        if skill.exists() and skill.read_text(encoding='utf-8') != canonical and not replace:
            raise ValueError(f'설치된 {PRODUCT_NAME} 스킬이 다릅니다. 확인 후 --replace를 사용하세요.')
        # Check all conflicts before writing either artifact.
        atomic_write(skill, canonical)
        if result != original:
            atomic_write(config, result)
    return {'config': str(config), 'skill': str(skill), 'server': 'second_brain',
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
        source = args.skill_source or Path(__file__).resolve().parents[3] / 'docs/skills/second-brain/SKILL.md'
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
