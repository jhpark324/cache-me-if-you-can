import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import tomllib

import pytest

from second_brain import codex_integration
from second_brain.codex_integration import header_value, install, server_config, updated_config
from second_brain.config import Settings
from second_brain.brand import DEFAULT_PORT


def test_runtime_metadata_preserves_exact_paths_and_endpoint(tmp_path, source_package, monkeypatch):
    python = tmp_path / 'Python 공백' / 'bin' / 'python'
    data = tmp_path / 'private data'
    home = tmp_path / 'codex home'
    runtime = codex_integration.runtime_config(python, data, 54321, home)
    server = server_config(python, data, 54321)
    assert runtime['mcp_url'] == server['url'] == 'http://127.0.0.1:54321/mcp/'
    assert runtime['commands']['start'] == [str(python), '-m', 'second_brain.runtime', 'start',
                                          '--data-dir', str(data), '--port', '54321']
    assert runtime['commands']['doctor'][-2:] == ['--codex-home', str(home)]
    assert not data.exists()  # Metadata generation does not initialize auth or storage.
    result = install(home, source_package, server, runtime_metadata=runtime)
    artifact = Path(result['runtime_metadata'])
    assert json.loads(artifact.read_text()) == runtime
    if os.name != 'nt':
        assert artifact.stat().st_mode & 0o077 == 0
    monkeypatch.setattr(codex_integration, 'atomic_write', lambda *_: pytest.fail('Identical install rewrote files'))
    install(home, source_package, server, runtime_metadata=runtime)


def test_runtime_metadata_conflict_is_preflighted_and_migration_is_explicit(tmp_path, source_package):
    home, data = tmp_path / 'codex', tmp_path / 'data'
    python = Path(sys.executable)
    old_server = server_config(python, data, 8000)
    old_runtime = codex_integration.runtime_config(python, data, 8000, home)
    install(home, source_package, old_server, runtime_metadata=old_runtime)
    before = {path: path.read_bytes() for path in home.rglob('*') if path.is_file()}
    new_server = server_config(python, data, DEFAULT_PORT)
    new_runtime = codex_integration.runtime_config(python, data, DEFAULT_PORT, home)
    with pytest.raises(ValueError, match='--replace'):
        install(home, source_package, new_server, runtime_metadata=new_runtime)
    assert all(path.read_bytes() == value for path, value in before.items())
    install(home, source_package, new_server, runtime_metadata=new_runtime, replace=True)
    assert json.loads((home / 'skills/cache-me/runtime.json').read_text()) == new_runtime
    assert tomllib.loads((home / 'config.toml').read_text())['mcp_servers']['second_brain'] == new_server
    # A runtime-only customization also blocks all package writes before replacement.
    (home / 'skills/cache-me/runtime.json').write_text('customized runtime')
    source_package.write_text('new canonical skill')
    with pytest.raises(ValueError, match='--replace'):
        install(home, source_package, new_server, runtime_metadata=new_runtime)
    assert (home / 'skills/cache-me/SKILL.md').read_text() != 'new canonical skill'
    assert (home / 'skills/cache-me/runtime.json').read_text() == 'customized runtime'


def test_doctor_missing_install_is_read_only(tmp_path, monkeypatch):
    settings = Settings(tmp_path / 'data')
    home = tmp_path / 'codex'
    monkeypatch.setattr(codex_integration, 'inspect_runtime', lambda _: {'status': 'stopped', 'message': 'stopped'})
    result = codex_integration.doctor(settings, home)
    assert not result['ok']
    assert result['data']['runtime']['status'] == 'stopped'
    assert result['data']['authentication']['status'] == 'unavailable'
    assert result['data']['codex']['status'] == 'missing'
    assert not home.exists() and not settings.data_dir.exists()


@pytest.mark.parametrize('change,expected', [({}, 'ready'), ({'url': 'http://localhost:8000/mcp/'}, 'mismatch'),
                                          ({'enabled': False}, 'mismatch'),
                                          ({'http_headers_helper': 'different-helper'}, 'mismatch'),
                                          ({'http_headers': {'Authorization': 'secret'}}, 'mismatch')])
def test_doctor_distinguishes_configuration_and_never_echoes_secrets(tmp_path, monkeypatch, change, expected):
    settings = Settings(tmp_path / 'data')
    settings.data_dir.mkdir()
    secret = 'synthetic-private-mcp-secret'
    (settings.data_dir / 'local-access.json').write_text(json.dumps({'mcp_token': secret}))
    home = tmp_path / 'codex'
    home.mkdir()
    server = {**server_config(Path(sys.executable), settings.data_dir, settings.port), **change}
    headers = server.pop('http_headers', None)
    config_text = updated_config('', server)
    if headers:
        config_text += '\n[mcp_servers.second_brain.http_headers]\nAuthorization = "secret"\n'
    (home / 'config.toml').write_text(config_text)
    monkeypatch.setattr(codex_integration, 'inspect_runtime', lambda _: {'status': 'ready', 'message': 'ready'})
    before = {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    result = codex_integration.doctor(settings, home)
    assert result['ok'] == (expected == 'ready')
    assert result['data']['codex']['status'] == expected
    assert secret not in json.dumps(result) and 'Authorization' not in json.dumps(result)
    assert all(path.read_bytes() == value for path, value in before.items())
    if expected == 'ready':
        assert '새 세션' in result['data']['next_steps'][0]


@pytest.mark.parametrize('credential', ['[]', '{invalid-synthetic-secret', '{"mcp_token": "secret with space"}'])
def test_doctor_malformed_credentials_and_config_are_sanitized(tmp_path, monkeypatch, credential):
    (tmp_path / 'local-access.json').write_text(credential)
    (tmp_path / 'config.toml').write_text('token = invalid-synthetic-secret')
    monkeypatch.setattr(codex_integration, 'inspect_runtime', lambda _: {'status': 'ready', 'message': 'ready'})
    result = codex_integration.doctor(Settings(tmp_path), tmp_path)
    assert not result['ok']
    assert result['data']['authentication']['status'] == 'unavailable'
    assert result['data']['codex']['status'] == 'invalid'
    assert 'synthetic-secret' not in json.dumps(result)


def test_doctor_cli_invalid_port_is_structured_and_sanitized(tmp_path):
    env = dict(os.environ, SECOND_BRAIN_PORT='synthetic-secret-invalid-port')
    result = subprocess.run([sys.executable, '-m', 'second_brain.codex_integration', 'doctor',
                             '--data-dir', str(tmp_path / 'data'), '--codex-home', str(tmp_path / 'codex')],
                            capture_output=True, text=True, env=env)
    assert result.returncode == 1
    assert json.loads(result.stdout)['error']['code'] == 'invalid_configuration'
    assert 'synthetic-secret' not in result.stdout + result.stderr
    assert list(tmp_path.iterdir()) == []


def test_explicit_cli_port_takes_precedence_and_headers_are_port_independent(tmp_path):
    env = dict(os.environ, SECOND_BRAIN_PORT='invalid-ambient-port', SECOND_BRAIN_DATA_DIR=str(tmp_path))
    (tmp_path / 'local-access.json').write_text(json.dumps({'mcp_token': 'synthetic-test-token'}))
    for extra in ([], ['--data-dir', str(tmp_path)]):
        result = subprocess.run([sys.executable, '-m', 'second_brain.codex_integration', 'headers', *extra],
                                capture_output=True, text=True, env=env)
        assert result.returncode == 0 and not result.stderr
        assert json.loads(result.stdout) == {'Authorization': 'Bearer synthetic-test-token'}
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    result = subprocess.run([sys.executable, '-m', 'second_brain.codex_integration', 'doctor',
                             '--port', str(port), '--data-dir', str(tmp_path),
                             '--codex-home', str(tmp_path / 'codex')], capture_output=True, text=True, env=env)
    payload = json.loads(result.stdout)
    assert result.returncode == 1 and not result.stderr
    assert payload['data']['authentication']['status'] == 'ready'
    assert payload['data']['codex']['status'] == 'missing'


@pytest.fixture
def source_package(tmp_path):
    source = tmp_path / 'source' / 'SKILL.md'
    source.parent.mkdir()
    source.write_text('---\nname: cache-me\ndescription: cache-me, 저장해줘\n---\nInstructions', encoding='utf-8')
    agents = source.parent / 'agents'
    agents.mkdir()
    (agents / 'openai.yaml').write_text('interface:\n  display_name: "cache-me"\npolicy:\n  allow_implicit_invocation: true\n', encoding='utf-8')
    return source


@pytest.fixture(params=['second-brain', 'cacheme'])
def legacy_package(tmp_path, monkeypatch, request):
    package = tmp_path / 'codex' / 'skills' / request.param
    package.mkdir(parents=True)
    content = f'---\nname: {request.param}\n---\nKnown previous project release\n'.encode()
    (package / 'SKILL.md').write_bytes(content)
    (package / 'extra.txt').write_text('Preserve the complete old package')
    # Exercise byte-for-byte ownership checks without copying the retired skill into tests.
    monkeypatch.setitem(codex_integration.LEGACY_SKILLS_SHA256, request.param, {hashlib.sha256(content).hexdigest()})
    return package


def test_install_preserves_unrelated_config_and_idempotency(tmp_path, source_package, monkeypatch):
    home = tmp_path / 'codex'
    home.mkdir()
    before = '# 사용자 설정\nmodel = "user-choice"\n[mcp_servers.existing]\nurl = "https://example.invalid/mcp"\n'
    (home / 'config.toml').write_text(before)
    unrelated = home / 'skills' / 'unrelated' / 'SKILL.md'
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text('User-owned skill')
    server = server_config(Path(sys.executable), tmp_path / 'private data', 8000)
    result = install(home, source_package, server)
    config = (home / 'config.toml').read_text()
    assert config.startswith(before.rstrip())
    assert tomllib.loads(config)['model'] == 'user-choice'
    assert tomllib.loads(config)['mcp_servers']['existing']['url'] == 'https://example.invalid/mcp'
    assert result['skill_name'] == 'cache-me'
    assert result['skill_slug'] == 'cache-me'
    assert result['server'] == 'second_brain'
    assert Path(result['metadata']).read_bytes() == (source_package.parent / 'agents/openai.yaml').read_bytes()
    assert result['legacy_skill']['status'] == 'absent'
    assert set(result['legacy_skills']) == {'second-brain', 'cacheme'}
    assert all(state['status'] == 'absent' for state in result['legacy_skills'].values())
    assert unrelated.read_text() == 'User-owned skill'
    # A repeated install must not replace identical files (including UI metadata).
    def unexpected_write(*args):
        pytest.fail('Identical artifacts must not be rewritten')
    monkeypatch.setattr(codex_integration, 'atomic_write', unexpected_write)
    install(home, source_package, server)
    assert (home / 'config.toml').read_text() == config
    assert (home / 'skills/cache-me/SKILL.md').read_bytes() == source_package.read_bytes()
    if os.name != 'nt':
        assert (home / 'config.toml').stat().st_mode & 0o077 == 0


def test_install_conflicts_do_not_change_files(tmp_path):
    home = tmp_path / 'codex'
    home.mkdir()
    original = '[mcp_servers.second_brain]\nurl = "http://other.invalid"\n'
    (home / 'config.toml').write_text(original)
    source = tmp_path / 'SKILL.md'
    source.write_text('canonical')
    for replace in (False, True):
        with pytest.raises(ValueError):
            install(home, source, server_config(Path(sys.executable), tmp_path, 8000), replace=replace)
        assert (home / 'config.toml').read_text() == original
        assert not (home / 'skills/cache-me/SKILL.md').exists()


def test_install_without_optional_metadata(tmp_path):
    source = tmp_path / 'SKILL.md'
    source.write_text('canonical')
    result = install(tmp_path / 'codex', source, server_config(Path(sys.executable), tmp_path, 8000))
    assert Path(result['skill']).read_text() == 'canonical'
    assert result['metadata'] is None
    assert not (Path(result['skill']).parent / 'agents').exists()


@pytest.mark.parametrize('conflict', ['SKILL.md', 'agents/openai.yaml'])
def test_package_conflict_preserves_config_and_legacy(tmp_path, source_package, legacy_package, conflict):
    home = tmp_path / 'codex'
    config = home / 'config.toml'
    config.write_text('model = "keep"\n')
    installed = home / 'skills/cache-me' / conflict
    installed.parent.mkdir(parents=True)
    installed.write_text('User customization')
    with pytest.raises(ValueError, match='--replace'):
        install(home, source_package, server_config(Path(sys.executable), tmp_path, 8000))
    assert config.read_text() == 'model = "keep"\n'
    assert installed.read_text() == 'User customization'
    assert legacy_package.is_dir()
    assert not (home / '.skill-backups').exists()
    other = 'SKILL.md' if conflict != 'SKILL.md' else 'agents/openai.yaml'
    assert not (home / 'skills/cache-me' / other).exists()


def test_replace_updates_package_and_managed_config(tmp_path, source_package, legacy_package):
    home = tmp_path / 'codex'
    config = home / 'config.toml'
    first_server = server_config(Path(sys.executable), tmp_path, 8000)
    config.write_text(updated_config('model = "keep"\n', first_server))
    installed = home / 'skills/cache-me'
    (installed / 'agents').mkdir(parents=True)
    (installed / 'SKILL.md').write_text('Old skill')
    (installed / 'agents/openai.yaml').write_text('Old metadata')
    second_server = server_config(Path(sys.executable), tmp_path, 8011)
    result = install(home, source_package, second_server, replace=True)
    assert (installed / 'SKILL.md').read_bytes() == source_package.read_bytes()
    assert (installed / 'agents/openai.yaml').read_bytes() == (source_package.parent / 'agents/openai.yaml').read_bytes()
    parsed = tomllib.loads(config.read_text())
    assert parsed['model'] == 'keep'
    assert parsed['mcp_servers']['second_brain'] == second_server
    assert result['legacy_skills'][legacy_package.name]['status'] == 'backed_up'


def test_recognized_legacy_package_is_backed_up_once_without_overwriting(tmp_path, source_package, legacy_package):
    home = tmp_path / 'codex'
    original = (legacy_package / 'SKILL.md').read_bytes()
    fingerprint = hashlib.sha256(original).hexdigest()
    occupied = home / '.skill-backups' / f'{legacy_package.name}-{fingerprint[:12]}'
    occupied.mkdir(parents=True)
    (occupied / 'existing.txt').write_text('Prior backup')
    server = server_config(Path(sys.executable), tmp_path, 8000)
    result = install(home, source_package, server)
    assert result['legacy_skills'][legacy_package.name]['status'] == 'backed_up'
    backup = Path(result['legacy_skills'][legacy_package.name]['backup'])
    assert backup.parent == home / '.skill-backups'
    assert backup != occupied
    assert (occupied / 'existing.txt').read_text() == 'Prior backup'
    assert (backup / 'SKILL.md').read_bytes() == original
    assert (backup / 'extra.txt').read_text() == 'Preserve the complete old package'
    assert not legacy_package.exists()
    first_backups = set((home / '.skill-backups').iterdir())
    repeated = install(home, source_package, server)
    assert repeated['legacy_skills'][legacy_package.name]['status'] == 'absent'
    assert set((home / '.skill-backups').iterdir()) == first_backups
    # The complete previous package can be restored by moving its backup back.
    backup.rename(legacy_package)
    assert (legacy_package / 'SKILL.md').read_bytes() == original


def test_both_previous_packages_are_migrated_together(tmp_path, source_package, monkeypatch):
    home = tmp_path / 'codex'
    originals = {}
    for slug in ('second-brain', 'cacheme'):
        package = home / 'skills' / slug
        package.mkdir(parents=True)
        originals[slug] = f'Known previous {slug} package'.encode()
        (package / 'SKILL.md').write_bytes(originals[slug])
        monkeypatch.setitem(codex_integration.LEGACY_SKILLS_SHA256, slug, {hashlib.sha256(originals[slug]).hexdigest()})
    result = install(home, source_package, server_config(Path(sys.executable), tmp_path, 8000))
    for slug, status in result['legacy_skills'].items():
        assert status['status'] == 'backed_up'
        assert (Path(status['backup']) / 'SKILL.md').read_bytes() == originals[slug]
        assert not (home / 'skills' / slug).exists()
    assert result['legacy_skill'] == result['legacy_skills']['second-brain']
    assert (home / 'skills/cache-me/SKILL.md').read_bytes() == source_package.read_bytes()


@pytest.mark.parametrize('replace', [False, True])
def test_custom_legacy_is_preserved_even_with_replace(tmp_path, source_package, legacy_package, replace):
    customized = (legacy_package / 'SKILL.md').read_bytes() + b'User customization\n'
    (legacy_package / 'SKILL.md').write_bytes(customized)
    home = tmp_path / 'codex'
    result = install(home, source_package, server_config(Path(sys.executable), tmp_path, 8000), replace=replace)
    assert result['legacy_skills'][legacy_package.name]['status'] == 'preserved'
    assert (legacy_package / 'SKILL.md').read_bytes() == customized
    assert not (home / '.skill-backups').exists()
    assert Path(result['skill']).is_file()


@pytest.mark.parametrize('blocked_path', ['skills/cache-me/agents', '.skill-backups'])
def test_directory_conflicts_are_preflighted_before_writes(tmp_path, source_package, legacy_package, blocked_path):
    home = tmp_path / 'codex'
    config = home / 'config.toml'
    config.write_text('model = "keep"\n')
    blocked = home / blocked_path
    blocked.parent.mkdir(parents=True, exist_ok=True)
    blocked.write_text('Keep this file')
    with pytest.raises(ValueError, match='디렉터리'):
        install(home, source_package, server_config(Path(sys.executable), tmp_path, 8000), replace=True)
    assert blocked.read_text() == 'Keep this file'
    assert config.read_text() == 'model = "keep"\n'
    assert legacy_package.is_dir()
    assert not (home / 'skills/cache-me/SKILL.md').exists()


def test_managed_config_updates_only_with_explicit_replace(tmp_path):
    first = server_config(Path(sys.executable), tmp_path, 8000)
    second = server_config(Path(sys.executable), tmp_path, 8011)
    original = updated_config('model = "keep"\n', first)
    with pytest.raises(ValueError):
        updated_config(original, second)
    updated = updated_config(original, second, replace=True)
    assert tomllib.loads(updated)['mcp_servers']['second_brain'] == second
    assert tomllib.loads(updated)['model'] == 'keep'


def test_helper_uses_only_app_mcp_token_and_quotes_paths(tmp_path):
    data = tmp_path / '공백 $(touch unexpected) `command`'
    data.mkdir()
    token = 'synthetic-local-mcp-secret'
    (data / 'local-access.json').write_text(json.dumps({'mcp_token': token}))
    (data / 'credentials.json').write_text('not valid; must never read')
    config = server_config(Path(sys.executable), data, 8000)
    assert token not in json.dumps(config)
    assert header_value(data) == {'Authorization': f'Bearer {token}'}
    command = shlex.split(config['http_headers_helper'])
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == {'Authorization': f'Bearer {token}'}
    assert not result.stderr


def test_broken_helper_fails_without_echoing_secret(tmp_path):
    secret = 'do-not-echo-this-secret'
    (tmp_path / 'local-access.json').write_text(json.dumps({'mcp_token': secret + '\n'}))
    result = subprocess.run([sys.executable, '-m', 'second_brain.codex_integration', 'headers',
                             '--data-dir', str(tmp_path)], capture_output=True, text=True)
    assert result.returncode != 0 and result.stdout == ''
    assert secret not in result.stderr
