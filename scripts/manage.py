"""Cross-platform development launcher; operational documentation lives in docs/."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend' / 'src'))

from second_brain.brand import PRODUCT_NAME


def executable(name):
    path = shutil.which(name)
    if not path:
        raise SystemExit(f'{name} 실행 파일을 찾을 수 없습니다. docs/guides/local-development.md를 확인하세요.')
    return path


def execute(command, **kwargs):
    subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def prepared_python():
    relative = ('Scripts', 'python.exe') if os.name == 'nt' else ('bin', 'python')
    python = ROOT / 'backend' / '.venv' / Path(*relative)
    if not python.is_file():
        raise SystemExit('준비된 Python 환경이 없습니다. 먼저 python scripts/manage.py setup을 실행하세요.')
    return str(python)


def main():
    parser = argparse.ArgumentParser(description=f'{PRODUCT_NAME} 개발 실행 도구')
    parser.add_argument('action', choices=['setup', 'run', 'start', 'doctor', 'check', 'codex', 'install-codex'])
    parser.add_argument('--replace', action='store_true', help=f'이미 설치한 {PRODUCT_NAME} 설정/스킬 갱신')
    args = parser.parse_args()
    if args.action in {'start', 'doctor'}:
        module = 'second_brain.runtime' if args.action == 'start' else 'second_brain.codex_integration'
        execute([prepared_python(), '-m', module, args.action])
        return
    uv = executable('uv')
    base = [uv, 'run', '--locked', '--project', str(ROOT / 'backend'), '--python', '3.12', '--extra', 'embedding']
    if args.action == 'setup':
        execute([uv, 'sync', '--locked', '--project', str(ROOT / 'backend'), '--python', '3.12', '--extra', 'embedding', '--extra', 'test'])
        npm = executable('npm')
        execute([npm, '--prefix', str(ROOT / 'frontend'), 'ci'])
        execute([npm, '--prefix', str(ROOT / 'frontend'), 'run', 'build'])
    elif args.action == 'run':
        execute(base + ['second-brain'])
    elif args.action == 'install-codex':
        execute(base + ['python', '-m', 'second_brain.codex_integration', 'install',
                        '--skill-source', str(ROOT / 'docs/skills/cache-me/SKILL.md')]
                + (['--replace'] if args.replace else []))
    elif args.action == 'check':
        execute([sys.executable, str(ROOT / 'scripts' / 'preflight.py')])
        execute([sys.executable, '-m', 'unittest', 'discover', '-s', str(ROOT / 'scripts' / 'tests'), '-q'])
        execute(base + ['--extra', 'test', 'pytest', str(ROOT / 'backend' / 'tests'), '-q'])
        execute([executable('npm'), '--prefix', str(ROOT / 'frontend'), 'run', 'build'])
    else:
        # The child gets the MCP bearer in its environment; never print it.
        code = ('import json; from second_brain.config import Settings; settings = Settings.load(); '
                'print(json.dumps({"data_dir": str(settings.data_dir), "port": settings.port}))')
        settings = json.loads(subprocess.check_output(base + ['python', '-c', code], cwd=ROOT, text=True))
        path = Path(settings['data_dir']) / 'local-access.json'
        if not path.exists():
            raise SystemExit('서버를 먼저 한 번 실행해 주세요.')
        env = os.environ.copy()
        env['SECOND_BRAIN_MCP_TOKEN'] = json.loads(path.read_text())['mcp_token']
        port = settings['port']
        execute([executable('codex'), '-c', f'mcp_servers.second_brain.url="http://127.0.0.1:{port}/mcp/"',
                 '-c', 'mcp_servers.second_brain.bearer_token_env_var="SECOND_BRAIN_MCP_TOKEN"'], env=env)


if __name__ == '__main__':
    main()
