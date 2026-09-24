"""CLI checks consume external task bundles without modifying package or inputs."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_evidence_v3 import BundleFixture
from evidence import digest


class ArtifactIsolationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.skill = self.root / 'installed skill'
        source = Path(__file__).resolve().parents[1]
        shutil.copytree(source / 'scripts', self.skill / 'scripts',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        self.project = self.root / 'target 项目'
        self.screen = self.project / 'specs' / 'sample-task' / 'ui-implement' / 'screen'
        self.screen.mkdir(parents=True)
        self.fixture = BundleFixture(self.screen)
        self.fixture.write('restoration.md', 'Historical prose is not acceptance.')
        self.unrelated = self.root / 'unrelated cwd'
        self.unrelated.mkdir()

    def snapshot(self):
        # Include empty directories as well as byte hashes: even an empty evals
        # or cache directory would violate this read-only command contract.
        return {str(path.relative_to(self.root)): digest(path) if path.is_file() else None
                for path in self.root.rglob('*')}

    def assert_checks_read_only(self, checks, env=None):
        before = self.snapshot()
        for command, target, expected_exit in checks:
            previous = None
            for cwd in (self.skill, self.project, self.unrelated):
                with self.subTest(command=command, target=target.name, cwd=cwd.name):
                    result = subprocess.run(
                        [sys.executable, '-B', str(self.skill / 'scripts' / 'uir.py'),
                         command, str(target)], cwd=cwd, capture_output=True,
                        text=True, encoding='utf-8', check=False, timeout=30, env=env)
                    actual = (result.returncode, result.stdout, result.stderr)
                    self.assertEqual(expected_exit, result.returncode, actual)
                    if previous is not None:
                        self.assertEqual(previous, actual)
                    previous = actual
                    self.assertEqual(before, self.snapshot())

    def test_complete_external_bundle_is_cwd_independent_and_read_only(self):
        evidence = self.fixture.save()
        self.assert_checks_read_only([
            ('check-map', evidence, 0), ('verify', evidence, 0),
            ('status', evidence, 0), ('status', self.screen, 0),
            ('status', self.screen / 'restoration.md', 0),
            # Fixture Markdown contains only requirement rows, not a full spec.
            ('check-spec', self.screen / 'design-spec.md', 2),
        ])

    def test_incomplete_external_bundle_is_read_only(self):
        self.fixture.data.update(captures=[], observations=[], sweeps=[],
                                 implementation={'status': 'pending'})
        evidence = self.fixture.save()
        self.assert_checks_read_only([
            ('check-map', evidence, 0), ('verify', evidence, 1),
            ('status', self.screen, 1),
        ])

    def test_malformed_external_bundle_is_read_only(self):
        evidence = self.fixture.save()
        self.fixture.write('evidence.json', '{invalid JSON')
        self.assert_checks_read_only([
            ('check-map', evidence, 2), ('verify', evidence, 2),
            ('status', self.screen, 2),
        ])

    def test_cli_uses_utf8_even_with_non_utf8_host_streams(self):
        self.fixture.data['states'] = ['默认']
        for row in (self.fixture.data['captures'] + self.fixture.data['sweeps']
                    + self.fixture.data['observations']):
            row['state'] = '默认'
        evidence = self.fixture.save()
        for encoding in ('cp1252', 'ascii'):
            env = dict(os.environ, PYTHONIOENCODING=encoding)
            with self.subTest(encoding=encoding):
                self.assert_checks_read_only([
                    ('check-map', evidence, 0), ('verify', evidence, 0),
                    ('status', self.screen, 0),
                    ('check-spec', self.screen / 'design-spec.md', 2),
                ], env=env)
                result = subprocess.run(
                    [sys.executable, '-B', str(self.skill / 'scripts' / 'uir.py'), 'verify', str(evidence)],
                    capture_output=True, text=True, encoding='utf-8', env=env, check=False, timeout=30)
                self.assertIn('默认', result.stdout)
                self.assertTrue(json.loads(result.stdout)['complete'])

    def test_both_clis_encode_argument_errors_as_utf8(self):
        before = self.snapshot()
        for name in ('uir.py', 'resources.py'):
            with self.subTest(script=name):
                result = subprocess.run(
                    [sys.executable, '-B', str(self.skill / 'scripts' / name), '无效命令'],
                    capture_output=True, text=True, encoding='utf-8', check=False, timeout=30,
                    env=dict(os.environ, PYTHONIOENCODING='ascii'))
                self.assertEqual(2, result.returncode)
                self.assertIn('无效命令', result.stderr)
                self.assertNotIn('UnicodeEncodeError', result.stderr)
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
