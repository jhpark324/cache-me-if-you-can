"""Launcher argv checks; these do not claim native OS execution coverage."""
import importlib.util
import json
from pathlib import Path, PureWindowsPath
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('manage', Path(__file__).parents[1] / 'manage.py')
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class ManageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='manage-isolated-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.codex_home = self.root / 'codex'
        self.codex_home.mkdir()
        self.project = self.root / 'project'
        self.project.mkdir()
        environment = patch.dict(manage.os.environ, {'CODEX_HOME': str(self.codex_home)})
        environment.start()
        self.addCleanup(environment.stop)
        root = patch.object(manage, 'ROOT', self.project)
        root.start()
        self.addCleanup(root.stop)

    def test_runtime_commands_use_prepared_python_without_dependency_install(self):
        with tempfile.TemporaryDirectory(prefix='manage spaced ') as directory:
            root = Path(directory)
            for platform, python_dir, python_name in (('posix', 'bin', 'python'), ('nt', 'Scripts', 'python.exe')):
                python = root / 'backend' / '.venv' / python_dir / python_name
                python.parent.mkdir(parents=True)
                python.touch()
                for action, module in (('start', 'cache_me.runtime'), ('doctor', 'cache_me.codex_integration')):
                    with self.subTest(platform=platform, action=action), \
                            patch.object(manage, 'ROOT', root), \
                            patch.object(manage, 'os', SimpleNamespace(name=platform)), \
                            patch.object(sys, 'argv', ['manage.py', action]), \
                            patch.object(manage, 'executable') as executable, \
                            patch.object(manage, 'execute') as execute:
                        manage.main()
                        executable.assert_not_called()
                        execute.assert_called_once_with([str(python), '-m', module, action])

    def test_runtime_commands_require_existing_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            for action in ('start', 'doctor'):
                with self.subTest(action=action), patch.object(manage, 'ROOT', Path(directory)), \
                        patch.object(sys, 'argv', ['manage.py', action]), \
                        patch.object(manage, 'executable') as executable, \
                        patch.object(manage, 'execute') as execute:
                    with self.assertRaisesRegex(SystemExit, 'manage.py setup'):
                        manage.main()
                    executable.assert_not_called()
                    execute.assert_not_called()

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
                self.assertIn('cache_me.codex_integration', command)

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
        config = self.codex_home / 'config.toml'
        original = '[mcp_servers.notes]\ncommand = "user-owned-server"\n'
        config.write_text(original)
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / 'data with spaces'
            data.mkdir()
            secret = 'synthetic-test-bearer'
            (data / 'local-access.json').write_text(json.dumps({'mcp_token': secret}))
            with patch.object(sys, 'argv', ['manage.py', 'codex']), \
                    patch.object(manage, 'executable', side_effect=lambda name: '/tools bin/' + name), \
                    patch.object(manage.subprocess, 'check_output', return_value=json.dumps({'data_dir': str(data), 'port': 8123}) + '\n'), \
                    patch.object(manage, 'execute') as execute, \
                    patch.dict(manage.os.environ, {'CACHE_ME_PORT': '9999'}):
                manage.main()
                command = execute.call_args.args[0]
                self.assertNotIn(secret, ' '.join(command))
                self.assertIn('mcp_servers.cache_me.url="http://127.0.0.1:8123/mcp/"', command)
                self.assertIn('mcp_servers.cache_me.bearer_token_env_var="CACHE_ME_MCP_TOKEN"', command)
                self.assertEqual(execute.call_args.kwargs['env']['CACHE_ME_MCP_TOKEN'], secret)
                self.assertEqual(config.read_text(), original)

    def test_codex_does_not_launch_if_settings_validation_fails(self):
        with patch.object(sys, 'argv', ['manage.py', 'codex']), \
                patch.object(manage, 'executable', return_value='/tools bin/uv'), \
                patch.object(manage.subprocess, 'check_output', side_effect=manage.subprocess.CalledProcessError(1, ['settings'])), \
                patch.object(manage, 'execute') as execute:
            with self.assertRaises(manage.subprocess.CalledProcessError):
                manage.main()
            execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
