"""Launcher argv checks; these do not claim native OS execution coverage."""
import importlib.util
import json
from pathlib import Path, PureWindowsPath
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('manage', Path(__file__).parents[1] / 'manage.py')
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class ManageTests(unittest.TestCase):
    def test_install_codex_passes_canonical_package_and_optional_replace(self):
        for replace in (False, True):
            with self.subTest(replace=replace), \
                    patch.object(sys, 'argv', ['manage.py', 'install-codex'] + (['--replace'] if replace else [])), \
                    patch.object(manage, 'executable', return_value='/tools bin/uv'), \
                    patch.object(manage, 'execute') as execute:
                manage.main()
                command = execute.call_args.args[0]
                self.assertEqual(command[command.index('--skill-source') + 1], str(manage.ROOT / 'docs/skills/cache-me/SKILL.md'))
                self.assertEqual('--replace' in command, replace)
                self.assertIn('second_brain.codex_integration', command)

    def test_setup_preserves_spaced_posix_and_windows_paths_and_locked_install(self):
        # PureWindowsPath checks argument construction on any host, not whether
        # Windows can execute npm.cmd or its native embedding dependencies.
        for root in (Path('/tmp/프로젝트 with spaces'), PureWindowsPath('C:/Users/사용자/My Project')):
            with self.subTest(root=str(root)), patch.object(manage, 'ROOT', root), \
                    patch.object(sys, 'argv', ['manage.py', 'setup']), \
                    patch.object(manage, 'executable', side_effect=lambda name: str(root / 'tools bin' / name)), \
                    patch.object(manage, 'execute') as execute:
                manage.main()
                commands = [call.args[0] for call in execute.call_args_list]
                self.assertEqual(len(commands), 3)
                self.assertIn('--locked', commands[0])
                self.assertEqual(commands[0][commands[0].index('--project') + 1], str(root / 'backend'))
                self.assertEqual(commands[1], [str(root / 'tools bin' / 'npm'), '--prefix', str(root / 'frontend'), 'ci'])
                self.assertEqual(commands[2][-2:], ['run', 'build'])

    def test_codex_bearer_is_only_passed_in_child_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / 'data with spaces'
            data.mkdir()
            secret = 'synthetic-test-bearer'
            (data / 'local-access.json').write_text(json.dumps({'mcp_token': secret}))
            with patch.object(sys, 'argv', ['manage.py', 'codex']), \
                    patch.object(manage, 'executable', side_effect=lambda name: '/tools bin/' + name), \
                    patch.object(manage.subprocess, 'check_output', return_value=str(data) + '\n'), \
                    patch.object(manage, 'execute') as execute, \
                    patch.dict(manage.os.environ, {'SECOND_BRAIN_PORT': '8123'}):
                manage.main()
                command = execute.call_args.args[0]
                self.assertNotIn(secret, ' '.join(command))
                self.assertIn('mcp_servers.second_brain.url="http://127.0.0.1:8123/mcp/"', command)
                self.assertEqual(execute.call_args.kwargs['env']['SECOND_BRAIN_MCP_TOKEN'], secret)


if __name__ == '__main__':
    unittest.main()
