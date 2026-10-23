"""Managed Git worktrees stay ignored and leave no dirty work behind."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).parents[1] / 'plugins/zzzops/zzzops'
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module

managed = load('managed_worktrees')
phase = load('git_phase_state')
sys.modules['zzzops_git_phase_state'] = phase


class ManagedWorktreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'repository'
        self.repo.mkdir()
        self.git('init', '-q', '-b', 'dev')
        self.git('config', 'user.email', 'worktree@example.test')
        self.git('config', 'user.name', 'Worktree')
        self.git('config', 'gc.auto', '0')
        self.git('config', 'commit.gpgsign', 'false')
        (self.repo / 'input.txt').write_text('base\n')
        self.git('add', 'input.txt')
        self.git('commit', '-qm', 'base')
        self.base = self.git('rev-parse', 'HEAD').strip()
        self.bare = Path(self.temp.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(self.bare)], check=True)
        self.git('remote', 'add', 'origin', str(self.bare))

    def git(self, *args, cwd=None):
        return subprocess.run(['git', *args], cwd=cwd or self.repo,
                              capture_output=True, text=True, check=True).stdout

    def prepare(self):
        return managed.prepare_worktree(self.repo, goal=566, node='implement',
                                        attempt='a' * 32, base_commit=self.base)

    def test_prepare_is_ignored_idempotent_and_cleanup_requires_integration(self):
        prepared = self.prepare()
        path = Path(prepared['path'])
        self.assertEqual(self.repo / '.zzzops/worktrees/566/implement' / ('a' * 32), path)
        self.assertEqual(self.base, self.git('rev-parse', 'HEAD', cwd=path).strip())
        self.assertEqual('', self.git('status', '--porcelain'))
        self.assertEqual('existing', self.prepare()['outcome'])
        (path / 'output.txt').write_text('result\n')
        self.git('add', 'output.txt', cwd=path)
        self.git('commit', '-qm', 'feat: complete goal', cwd=path)
        head = self.git('rev-parse', 'HEAD', cwd=path).strip()
        ref = phase.retain_attempt_ref(path, remote='origin', goal=566, node='implement',
                                       attempt='a' * 32, commit=head)['ref']
        with self.assertRaisesRegex(ValueError, 'integrated'):
            managed.cleanup_integrated_worktree(self.repo, goal=566, node='implement',
                attempt='a' * 32, expected_head=head, integrated_commit=self.base,
                remote='origin', retained_ref=ref)
        self.git('merge', '--ff-only', prepared['branch'])
        result = managed.cleanup_integrated_worktree(self.repo, goal=566, node='implement',
            attempt='a' * 32, expected_head=head, integrated_commit=head,
            remote='origin', retained_ref=ref)
        self.assertEqual('removed', result['outcome'])
        self.assertFalse(path.exists())
        self.assertEqual(head, self.git('ls-remote', 'origin', ref).split()[0])

    def test_dirty_managed_worktree_is_preserved(self):
        prepared = self.prepare()
        path = Path(prepared['path'])
        (path / 'unverified.txt').write_text('dirty\n')
        with self.assertRaisesRegex(ValueError, 'dirty'):
            managed.cleanup_integrated_worktree(self.repo, goal=566, node='implement',
                attempt='a' * 32, expected_head=self.base, integrated_commit=self.base,
                remote='origin', retained_ref='refs/heads/zzzops/attempts/566/implement/' + 'a' * 32)
        self.assertTrue((path / 'unverified.txt').exists())


if __name__ == '__main__':
    unittest.main()
