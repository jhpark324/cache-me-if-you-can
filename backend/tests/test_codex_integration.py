import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tomllib

import pytest

from second_brain.codex_integration import header_value, install, server_config, updated_config


def test_install_preserves_unrelated_config_and_idempotency(tmp_path):
    home = tmp_path / 'codex'
    home.mkdir()
    before = '# 사용자 설정\nmodel = "user-choice"\n[mcp_servers.existing]\nurl = "https://example.invalid/mcp"\n'
    (home / 'config.toml').write_text(before)
    skill = tmp_path / 'SKILL.md'
    skill.write_text('---\nname: second-brain\ndescription: Remember records\n---\nInstructions')
    server = server_config(Path(sys.executable), tmp_path / 'private data', 8000)
    install(home, skill, server)
    config = (home / 'config.toml').read_text()
    assert config.startswith(before.rstrip())
    assert tomllib.loads(config)['model'] == 'user-choice'
    assert tomllib.loads(config)['mcp_servers']['existing']['url'] == 'https://example.invalid/mcp'
    install(home, skill, server)
    assert (home / 'config.toml').read_text() == config
    assert (home / 'skills/second-brain/SKILL.md').read_text() == skill.read_text()
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
        assert not (home / 'skills/second-brain/SKILL.md').exists()


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
