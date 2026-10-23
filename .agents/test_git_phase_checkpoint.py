"""Commit-backed workspace checkpoints use Git trees rather than file maps."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


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

    def test_base_movement_separates_content_from_topology(self):
        self.git('commit', '--allow-empty', '-qm', 'merge topology only')
        same_tree = self.git('rev-parse', 'HEAD').strip()
        self.assertEqual('retarget_only', git_phase_state.classify_base_move(
            self.repo, old_base=self.base, new_base=same_tree)['action'])
        self.git('checkout', '-q', '-b', 'squashed-base', self.base)
        self.git('commit', '--allow-empty', '-qm', 'separate same-tree history')
        unrelated = self.git('rev-parse', 'HEAD').strip()
        self.assertEqual('topology_rewrite', git_phase_state.classify_base_move(
            self.repo, old_base=same_tree, new_base=unrelated)['action'])
        changed = self.result('input.txt', 'different base\n')
        self.assertEqual('rebase_and_reverify', git_phase_state.classify_base_move(
            self.repo, old_base=same_tree, new_base=changed)['action'])

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

    def remote(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        bare = Path(temporary.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        self.git('remote', 'add', 'origin', str(bare))
        return bare

    def test_attempt_ref_is_create_only_and_retry_is_idempotent(self):
        self.remote()
        result = self.result()
        arguments = dict(goal=566, node='implement', attempt='a' * 32, commit=result)
        first = git_phase_state.retain_attempt_ref(self.repo, remote='origin', **arguments)
        self.assertEqual('created', first['outcome'])
        self.assertEqual(result, self.git('ls-remote', 'origin', first['ref']).split()[0])
        second = git_phase_state.retain_attempt_ref(self.repo, remote='origin', **arguments)
        self.assertEqual('existing', second['outcome'])
        self.assertEqual(first['ref'], second['ref'])
        moved = self.result('second.txt', 'different result\n')
        with self.assertRaisesRegex(ValueError, 'different commit'):
            git_phase_state.retain_attempt_ref(self.repo, remote='origin',
                                               **{**arguments, 'commit': moved})
        self.assertEqual(result, self.git('ls-remote', 'origin', first['ref']).split()[0])

    def test_uncertain_push_observes_exact_remote_commit(self):
        self.remote()
        result = self.result()
        original_run = subprocess.run
        def accepted_then_timeout(command, *args, **kwargs):
            if command[:2] == ['git', 'push']:
                original_run(command, *args, **kwargs)
                raise subprocess.TimeoutExpired(command, 30)
            return original_run(command, *args, **kwargs)
        with mock.patch.object(git_phase_state.subprocess, 'run', side_effect=accepted_then_timeout):
            retained = git_phase_state.retain_attempt_ref(
                self.repo, remote='origin', goal=566, node='implement',
                attempt='b' * 32, commit=result)
        self.assertEqual('observed_after_uncertain_push', retained['outcome'])
        self.assertEqual(result, self.git('ls-remote', 'origin', retained['ref']).split()[0])

    def test_reviewed_attempts_compact_to_two_deterministic_candidate_commits(self):
        self.remote()
        self.git('switch', '-c', 'feat/566')
        attempts = []
        for number, (path, value) in enumerate((
                ('behavior_test.py', 'assert False\n'),
                ('behavior_test.py', 'assert True\n'),
                ('output.py', 'value = 1\n'),
                ('output.py', 'value = 2\n')), start=1):
            commit = self.result(path, value)
            retained = git_phase_state.retain_attempt_ref(
                self.repo, remote='origin', goal=566,
                node='test_design' if number <= 2 else 'implement',
                attempt=f'{number:032x}', commit=commit)
            attempts.append({'ref': retained['ref'], 'commit': commit})
            if number == 2:
                test_source = commit
        implementation_source = attempts[-1]['commit']
        self.assertEqual(self.base, git_phase_state.compaction_base_from_attempts(
            self.repo, goal=566, test_source=test_source,
            attempts=attempts[:2], remote='origin'))
        preview = git_phase_state.preview_two_commit_candidate(
            self.repo, goal=566, base_commit=self.base, test_source=test_source,
            implementation_source=implementation_source,
            test_owned=['behavior_test.py'], implementation_owned=['output.py'],
            retained_attempts=attempts, remote='origin')
        self.assertEqual(4, preview['retained_attempt_count'])
        compacted = git_phase_state.apply_two_commit_candidate(
            self.repo, preview, test_owned=['behavior_test.py'],
            implementation_owned=['output.py'], retained_attempts=attempts,
            remote='origin')
        self.assertEqual('created', compacted['outcome'])
        self.assertEqual('2', self.git('rev-list', '--count', f'{self.base}..HEAD').strip())
        self.assertEqual(preview['test_tree'], self.git('rev-parse', 'HEAD^^{tree}').strip())
        self.assertEqual(preview['implementation_tree'], self.git('rev-parse', 'HEAD^{tree}').strip())
        self.assertEqual(preview, git_phase_state.preview_two_commit_candidate(
            self.repo, goal=566, base_commit=self.base, test_source=test_source,
            implementation_source=implementation_source,
            test_owned=['behavior_test.py'], implementation_owned=['output.py'],
            retained_attempts=attempts, remote='origin'))
        self.assertEqual({'test_commit': compacted['test_commit'],
                          'implementation_commit': compacted['implementation_commit'],
                          'test_source': test_source,
                          'implementation_source': implementation_source},
                         git_phase_state.verify_two_commit_candidate(
                             self.repo, goal=566, base_commit=self.base,
                             head_commit=compacted['implementation_commit']))
        self.assertEqual('existing', git_phase_state.apply_two_commit_candidate(
            self.repo, preview, test_owned=['behavior_test.py'],
            implementation_owned=['output.py'], retained_attempts=attempts,
            remote='origin')['outcome'])
        self.git('switch', 'dev')
        changed_base = self.result('input.txt', 'new base content\n')
        with self.assertRaisesRegex(ValueError, 'base tree changed'):
            git_phase_state.verify_two_commit_candidate(
                self.repo, goal=566, base_commit=changed_base,
                head_commit=compacted['implementation_commit'])
        for row in attempts:
            self.assertEqual(row['commit'], self.git('ls-remote', 'origin', row['ref']).split()[0])

    def test_compaction_stops_if_attempt_ref_moves(self):
        self.remote()
        self.git('switch', '-c', 'feat/566')
        test_source = self.result('behavior_test.py', 'assert True\n')
        implementation_source = self.result('output.py', 'value = 2\n')
        attempts = []
        for number, (node, commit) in enumerate((('test_design', test_source), ('implement', implementation_source)), start=1):
            retained = git_phase_state.retain_attempt_ref(self.repo, remote='origin',
                goal=566, node=node, attempt=f'{number:032x}', commit=commit)
            attempts.append({'ref': retained['ref'], 'commit': commit})
        preview = git_phase_state.preview_two_commit_candidate(
            self.repo, goal=566, base_commit=self.base, test_source=test_source,
            implementation_source=implementation_source,
            test_owned=['behavior_test.py'], implementation_owned=['output.py'],
            retained_attempts=attempts, remote='origin')
        self.git('push', '--force', 'origin', f"{self.base}:{attempts[0]['ref']}")
        with self.assertRaisesRegex(ValueError, 'Retained attempt ref'):
            git_phase_state.apply_two_commit_candidate(
                self.repo, preview, test_owned=['behavior_test.py'],
                implementation_owned=['output.py'], retained_attempts=attempts,
                remote='origin')
        self.assertEqual(implementation_source, self.git('rev-parse', 'HEAD').strip())

    def test_compaction_stops_if_candidate_branch_moves_after_preview(self):
        self.remote()
        self.git('switch', '-c', 'feat/566')
        test_source = self.result('behavior_test.py', 'assert True\n')
        implementation_source = self.result('output.py', 'value = 2\n')
        attempts = []
        for number, (node, commit) in enumerate((('test_design', test_source), ('implement', implementation_source)), start=1):
            retained = git_phase_state.retain_attempt_ref(self.repo, remote='origin',
                goal=566, node=node, attempt=f'{number:032x}', commit=commit)
            attempts.append({'ref': retained['ref'], 'commit': commit})
        preview = git_phase_state.preview_two_commit_candidate(
            self.repo, goal=566, base_commit=self.base, test_source=test_source,
            implementation_source=implementation_source,
            test_owned=['behavior_test.py'], implementation_owned=['output.py'],
            retained_attempts=attempts, remote='origin')
        self.git('commit', '--allow-empty', '-qm', 'unexpected branch movement')
        moved = self.git('rev-parse', 'HEAD').strip()
        with self.assertRaisesRegex(ValueError, 'branch moved'):
            git_phase_state.apply_two_commit_candidate(
                self.repo, preview, test_owned=['behavior_test.py'],
                implementation_owned=['output.py'], retained_attempts=attempts,
                remote='origin')
        self.assertEqual(moved, self.git('rev-parse', 'HEAD').strip())


if __name__ == '__main__':
    unittest.main()
