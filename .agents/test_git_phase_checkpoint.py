"""Commit-backed workspace checkpoints use Git trees rather than file maps."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


MODULE = Path(__file__).parents[1] / 'plugins/zzzops/zzzops/git_phase_state.py'
SPEC = importlib.util.spec_from_file_location('git_phase_state_under_test', MODULE)
git_phase_state = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(git_phase_state)


class GitPhaseCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git('init', '-q', '-b', 'dev')
        self.git('config', 'user.email', 'checkpoint@example.test')
        self.git('config', 'user.name', 'Checkpoint')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'gc.auto', '0')
        self.git('config', 'maintenance.auto', 'false')
        (self.repo / 'input.txt').write_text('base\n')
        self.git('add', 'input.txt')
        self.git('commit', '-qm', 'base')
        self.base = self.git('rev-parse', 'HEAD').strip()

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, capture_output=True,
                              text=True, check=True).stdout

    def result(self, path='output.txt', value='result\n'):
        (self.repo / path).write_text(value)
        self.git('add', path)
        self.git('commit', '-qm', 'phase result')
        return self.git('rev-parse', 'HEAD').strip()

    def test_verified_result_has_exact_base_tree_and_owned_diff(self):
        result = self.result()
        proof = git_phase_state.validate_checkpoint(
            self.repo, base_commit=self.base, result_commit=result,
            owned_paths=['output.txt'])
        self.assertEqual(self.base, proof['base_commit'])
        self.assertEqual(result, proof['result_commit'])
        self.assertEqual(1, proof['change_count'])
        self.assertEqual(40, len(proof['base_tree']))
        self.assertEqual(40, len(proof['result_tree']))
        self.assertNotIn('files', proof)

    def test_checkpoint_size_does_not_grow_with_unchanged_repository_files(self):
        large = self.repo / 'many'
        large.mkdir()
        for index in range(2200):
            (large / f'fixture_{index:04d}.txt').write_text(f'file {index}\n')
        self.git('add', 'many')
        self.git('commit', '-qm', 'large base')
        base = self.git('rev-parse', 'HEAD').strip()
        result = self.result()
        proof = git_phase_state.validate_checkpoint(
            self.repo, base_commit=base, result_commit=result,
            owned_paths=['output.txt'])
        self.assertLess(len(json.dumps(proof)), 500)
        self.assertEqual(1, proof['change_count'])

    def test_unowned_change_and_dirty_worktree_are_rejected(self):
        result = self.result()
        with self.assertRaisesRegex(ValueError, 'outside reviewed owned paths'):
            git_phase_state.validate_checkpoint(
                self.repo, base_commit=self.base, result_commit=result,
                owned_paths=['different.txt'])
        (self.repo / 'untracked.txt').write_text('dirty\n')
        with self.assertRaisesRegex(ValueError, 'clean worktree'):
            git_phase_state.validate_checkpoint(
                self.repo, base_commit=self.base, result_commit=result,
                owned_paths=['output.txt'])

    def test_wrong_base_and_nonordinary_output_are_rejected(self):
        result = self.result()
        with self.assertRaisesRegex(ValueError, 'exact parent'):
            git_phase_state.validate_checkpoint(
                self.repo, base_commit=result, result_commit=result,
                owned_paths=['output.txt'])
        self.git('reset', '--hard', self.base)
        (self.repo / 'link.txt').symlink_to('input.txt')
        self.git('add', 'link.txt')
        self.git('commit', '-qm', 'symlink result')
        link_result = self.git('rev-parse', 'HEAD').strip()
        with self.assertRaisesRegex(ValueError, 'ordinary files'):
            git_phase_state.validate_checkpoint(
                self.repo, base_commit=self.base, result_commit=link_result,
                owned_paths=['link.txt'])


if __name__ == '__main__':
    unittest.main()
