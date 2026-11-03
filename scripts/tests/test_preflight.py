"""Publication guard regressions using isolated directories, never the real repo."""
import importlib.util
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('preflight', Path(__file__).parents[1] / 'preflight.py')
preflight = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = preflight
spec.loader.exec_module(preflight)


class PreflightTests(unittest.TestCase):
    def test_before_git_init_ignore_rules_apply_without_workspace_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.gitignore').write_text('credentials.json\nnode_modules/\n')
            (root / 'credentials.json').write_text('{}')
            (root / 'app.py').write_text('pass')
            names, initialized = preflight.candidate_files(root)
            self.assertFalse(initialized)
            self.assertEqual(names, ['.gitignore', 'app.py'])
            self.assertFalse((root / '.git').exists())

    def test_tracked_secret_is_caught_even_after_being_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', directory], check=True)
            (root / 'credentials.json').write_text('{}')
            subprocess.run(['git', '-C', directory, 'add', 'credentials.json'], check=True)
            (root / '.gitignore').write_text('credentials.json\n')
            names, initialized = preflight.candidate_files(root)
            self.assertTrue(initialized)
            report = preflight.inspect(root, names)
            self.assertEqual(report['findings'][0]['rule'], 'runtime-or-sensitive-file')

    def test_secrets_are_reported_without_their_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = 'sk-' + 'a' * 40
            (root / 'config.py').write_text('TOKEN = "' + value + '"')
            report = preflight.inspect(root, ['config.py'])
            self.assertEqual(report['findings'][0]['rule'], 'provider-key')
            self.assertNotIn(value, str(report))

    def test_local_existing_but_ignored_doc_target_is_not_publishable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.md').write_text('[output](output.txt)\n[web](https://example.com)\n')
            (root / 'output.txt').write_text('local-only')
            report = preflight.inspect(root, ['index.md'])
            self.assertEqual([f['rule'] for f in report['findings']], ['missing-or-excluded-link-target'])

    def test_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            try:
                (root / 'linked').symlink_to(root.parent / 'unrelated-data')
            except OSError:
                self.skipTest('OS does not permit this user to create symlinks')
            report = preflight.inspect(root, ['linked'])
            self.assertEqual(report['findings'][0]['rule'], 'symlink-requires-review')

    def test_index_secret_is_caught_after_working_copy_is_cleaned_or_deleted(self):
        for delete_working_copy in (False, True):
            with self.subTest(delete_working_copy=delete_working_copy), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / 'repository with spaces'
                root.mkdir()
                subprocess.run(['git', 'init', '-q', str(root)], check=True)
                path = root / 'config.py'
                secret = 'sk-' + 'a' * 40
                path.write_text('TOKEN = "' + secret + '"')
                subprocess.run(['git', '-C', str(root), 'add', 'config.py'], check=True)
                index_before = (root / '.git' / 'index').read_bytes()
                path.unlink() if delete_working_copy else path.write_text('TOKEN = None')
                names, initialized = preflight.candidate_files(root)
                self.assertTrue(initialized)
                self.assertEqual(preflight.inspect(root, names)['findings'], [])
                report = preflight.inspect_index(root)
                self.assertEqual(report['files'], 1)
                self.assertEqual(report['findings'], [{'path': 'config.py', 'rule': 'provider-key', 'line': 1, 'source': 'index'}])
                self.assertNotIn(secret, str(report))
                completed = subprocess.run([sys.executable, str(Path(preflight.__file__).resolve()), '--root', str(root)],
                                           capture_output=True, text=True)
                self.assertEqual(completed.returncode, 1)
                self.assertEqual(json.loads(completed.stdout)['findings'][0]['source'], 'index')
                self.assertNotIn(secret, completed.stdout + completed.stderr)
                self.assertEqual(index_before, (root / '.git' / 'index').read_bytes())
                if delete_working_copy:
                    self.assertFalse(path.exists())
                else:
                    self.assertEqual(path.read_text(), 'TOKEN = None')

    def test_staged_removal_does_not_scan_a_removed_blob(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', directory], check=True)
            path = root / 'config.py'
            path.write_text('TOKEN = "sk-' + 'a' * 40 + '"')
            subprocess.run(['git', '-C', directory, 'add', 'config.py'], check=True)
            subprocess.run(['git', '-C', directory, 'rm', '--cached', '-q', 'config.py'], check=True)
            report = preflight.inspect_index(root)
            self.assertEqual(report, {'files': 0, 'bytes': 0, 'findings': []})
            # The remaining working copy is still inspected independently.
            self.assertEqual(preflight.inspect(root, ['config.py'])['findings'][0]['rule'], 'provider-key')

    def test_minimal_standard_jwt_header_is_recognized_without_echoing_token(self):
        def encode(value):
            return base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).decode().rstrip('=')
        token = '.'.join((encode({'alg': 'HS256'}), encode({'sub': 'synthetic-user', 'exp': 9999999999}), 'a' * 43))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'output.log').write_text('Authorization: Bearer ' + token)
            report = preflight.inspect(root, ['output.log'])
            self.assertEqual(report['findings'][0]['rule'], 'jwt')
            self.assertNotIn(token, str(report))

    def test_index_blob_binary_and_no_newline_do_not_desynchronize_next_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', directory], check=True)
            (root / 'a.bin').write_bytes(b'\xff\x00\n')
            (root / 'b.txt').write_text('No trailing newline')
            (root / 'c.py').write_text('TOKEN = "sk-' + 'a' * 40 + '"')
            subprocess.run(['git', '-C', directory, 'add', '.'], check=True)
            report = preflight.inspect_index(root)
            self.assertEqual(report['files'], 3)
            self.assertEqual([item['path'] for item in report['findings']], ['c.py'])

    def test_repository_root_alias_is_resolved_before_index_and_link_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root, alias = parent / 'real', parent / 'alias'
            root.mkdir()
            try:
                alias.symlink_to(root, target_is_directory=True)
            except OSError:
                self.skipTest('OS does not permit this user to create directory symlinks')
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (root / 'index.md').write_text('[code](app.py)')
            (root / 'app.py').write_text('pass')
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            files, initialized = preflight.candidate_files(alias)
            self.assertTrue(initialized)
            self.assertEqual(preflight.inspect(alias, files)['findings'], [])
            self.assertEqual(preflight.inspect_index(alias)['files'], 2)


if __name__ == '__main__':
    unittest.main()
