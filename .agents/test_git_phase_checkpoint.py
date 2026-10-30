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

    def test_projected_phase_uses_bounded_pathspec_and_ignores_unchanged_owned_paths(self):
        (self.repo / 'input.txt').unlink()
        (self.repo / 'output.txt').write_text('new result\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'replace reviewed paths')
        source = self.git('rev-parse', 'HEAD').strip()
        owned = ['input.txt', 'output.txt'] + [f'allowed_{index:04d}.txt' for index in range(1800)]
        commands = []
        original_run = subprocess.run

        def record(command, **kwargs):
            commands.append(command)
            return original_run(command, **kwargs)

        with mock.patch.object(git_phase_state.subprocess, 'run', side_effect=record):
            tree = git_phase_state._project_owned_tree(
                self.repo, base_commit=self.base, source_commit=source, owned_paths=owned)
        self.assertEqual(self.git('rev-parse', source + '^{tree}').strip(), tree)
        self.assertTrue(all(len(command) < 12 for command in commands))

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

    def test_restack_preview_reports_clean_tree_or_exact_owned_conflict_without_moving_head(self):
        self.git('checkout', '-q', '-b', 'attempt', self.base)
        attempt = self.result('input.txt', 'attempt\n')
        self.git('checkout', '-q', '-b', 'advanced-base', self.base)
        self.git('commit', '--allow-empty', '-qm', 'same-tree trunk movement')
        same_tree_base = self.git('rev-parse', 'HEAD').strip()
        same_tree = git_phase_state.preview_attempt_restack(self.repo,
            old_base=self.base, new_base=same_tree_base, attempt_commit=attempt,
            owned_paths=['input.txt'])
        self.assertEqual('clean', same_tree['status'])
        self.assertFalse(same_tree['content_stale'])
        self.assertTrue(same_tree['topology_changed'])
        advanced = self.result('other.txt', 'independent\n')
        clean = git_phase_state.preview_attempt_restack(self.repo,
            old_base=self.base, new_base=advanced, attempt_commit=attempt,
            owned_paths=['input.txt'])
        self.assertEqual('clean', clean['status'])
        self.assertTrue(clean['content_stale'])
        self.assertEqual([], clean['conflicts'])
        self.assertEqual(advanced, self.git('rev-parse', 'HEAD').strip())
        conflicted = self.result('input.txt', 'different base\n')
        conflict = git_phase_state.preview_attempt_restack(self.repo,
            old_base=self.base, new_base=conflicted, attempt_commit=attempt,
            owned_paths=['input.txt'])
        self.assertEqual('conflict', conflict['status'])
        self.assertEqual(['input.txt'], conflict['conflicts'])
        self.assertEqual(conflicted, self.git('rev-parse', 'HEAD').strip())
        self.assertEqual(attempt, self.git('rev-parse', 'attempt').strip())

    def restack_case(self, *, conflict=False):
        self.git('checkout', '-q', '-b', 'original-attempt', self.base)
        source = self.result('input.txt', 'attempt result\n')
        source_tree = self.git('rev-parse', source + '^{tree}').strip()
        self.git('checkout', '-q', '-b', 'moved-base', self.base)
        if conflict:
            new_base = self.result('input.txt', 'upstream result\n')
        else:
            new_base = self.result('upstream.txt', 'upstream result\n')
        self.git('checkout', '-q', '-b', 'replacement-attempt', new_base)
        preview = git_phase_state.preview_attempt_restack(
            self.repo, old_base=self.base, new_base=new_base,
            attempt_commit=source, owned_paths=['input.txt'])
        return preview, source, source_tree, new_base

    def begin_restack_conflict(self):
        preview, source, source_tree, new_base = self.restack_case(conflict=True)
        applied = git_phase_state.apply_attempt_restack(
            self.repo, preview, owned_paths=['input.txt'])
        self.assertEqual('conflict', applied['status'])
        self.assertEqual(['input.txt'], applied['conflicts'])
        self.assertEqual(source, self.git('rev-parse', 'CHERRY_PICK_HEAD').strip())
        return preview, source, source_tree, new_base

    def test_apply_attempt_restack_replays_one_exact_commit_on_moved_base(self):
        preview, source, source_tree, new_base = self.restack_case()

        result = git_phase_state.apply_attempt_restack(
            self.repo, preview, owned_paths=['input.txt'])

        restacked = result['result_commit']
        self.assertEqual('clean', result['status'])
        self.assertEqual(restacked, self.git('rev-parse', 'HEAD').strip())
        self.assertEqual(new_base, self.git('rev-parse', restacked + '^').strip())
        self.assertEqual(preview['proposed_tree'],
                         self.git('rev-parse', restacked + '^{tree}').strip())
        self.assertEqual(1, int(self.git('rev-list', '--count',
                                         new_base + '..' + restacked).strip()))
        self.assertEqual(source_tree, self.git('rev-parse', source + '^{tree}').strip())
        self.assertEqual(source, self.git('rev-parse', 'original-attempt').strip())

        replay = git_phase_state.apply_attempt_restack(
            self.repo, preview, owned_paths=['input.txt'])
        self.assertEqual(restacked, replay['result_commit'])
        self.assertEqual(restacked, self.git('rev-parse', 'HEAD').strip())
        self.assertEqual(1, int(self.git('rev-list', '--count',
                                         new_base + '..' + restacked).strip()))

    def test_apply_attempt_restack_preserves_owned_conflict_and_sequencer(self):
        preview, source, source_tree, new_base = self.restack_case(conflict=True)

        result = git_phase_state.apply_attempt_restack(
            self.repo, preview, owned_paths=['input.txt'])

        self.assertEqual('conflict', result['status'])
        self.assertEqual(['input.txt'], result['conflicts'])
        self.assertEqual(source, self.git('rev-parse', 'CHERRY_PICK_HEAD').strip())
        self.assertEqual(new_base, self.git('rev-parse', 'HEAD').strip())
        self.assertEqual(['input.txt'], [line[3:] for line in
            self.git('status', '--short').splitlines()])
        self.assertEqual(source_tree, self.git('rev-parse', source + '^{tree}').strip())
        self.assertEqual(source, self.git('rev-parse', 'original-attempt').strip())

    def test_continue_attempt_restack_rejects_unowned_and_symlink_dirt_then_verifies(self):
        preview, source, source_tree, new_base = self.begin_restack_conflict()
        (self.repo / 'input.txt').write_text('resolved result\n')
        (self.repo / 'unowned.txt').write_text('unreviewed dirt\n')
        with self.assertRaisesRegex(ValueError, 'unowned|outside reviewed owned paths'):
            git_phase_state.continue_attempt_restack(
                self.repo, preview, owned_paths=['input.txt'])
        (self.repo / 'unowned.txt').unlink()
        (self.repo / 'input.txt').unlink()
        (self.repo / 'input.txt').symlink_to('upstream.txt')
        with self.assertRaisesRegex(ValueError, 'ordinary|symlink'):
            git_phase_state.continue_attempt_restack(
                self.repo, preview, owned_paths=['input.txt'])
        (self.repo / 'input.txt').unlink()
        (self.repo / 'input.txt').write_text('resolved result\n')

        result = git_phase_state.continue_attempt_restack(
            self.repo, preview, owned_paths=['input.txt'])

        restacked = result['result_commit']
        self.assertEqual('clean', result['status'])
        self.assertEqual(new_base, self.git('rev-parse', restacked + '^').strip())
        self.assertEqual(1, int(self.git('rev-list', '--count',
                                         new_base + '..' + restacked).strip()))
        self.assertFalse((self.repo / '.git/CHERRY_PICK_HEAD').exists())
        git_phase_state.validate_checkpoint(
            self.repo, base_commit=new_base, result_commit=restacked,
            owned_paths=['input.txt'])
        self.assertEqual(source_tree, self.git('rev-parse', source + '^{tree}').strip())

    def test_prepare_restack_retry_after_staging_preserves_exact_head_and_sequencer(self):
        preview, source, _source_tree, new_base = self.begin_restack_conflict()
        (self.repo / 'input.txt').write_text(self.git('show', new_base + ':input.txt'))
        first = git_phase_state.prepare_attempt_restack_continue(
            self.repo, preview, owned_paths=['input.txt'])
        self.assertEqual(new_base, self.git('rev-parse', 'HEAD').strip())
        self.assertEqual(source, self.git('rev-parse', 'CHERRY_PICK_HEAD').strip())
        self.assertEqual(first['result_tree'], self.git('write-tree').strip())
        self.assertEqual(first['result_tree'], self.git('rev-parse', 'HEAD^{tree}').strip())
        retry = git_phase_state.prepare_attempt_restack_continue(
            self.repo, preview, owned_paths=['input.txt'])
        self.assertEqual(first, retry)
        self.assertEqual(new_base, self.git('rev-parse', 'HEAD').strip())
        self.assertEqual(source, self.git('rev-parse', 'CHERRY_PICK_HEAD').strip())
        adopted = git_phase_state.complete_attempt_restack_continue(
            self.repo, preview, owned_paths=['input.txt'], intent=retry)
        self.assertEqual(first['candidate_commit'], adopted['result_commit'])
        self.assertFalse((self.repo / '.git/CHERRY_PICK_HEAD').exists())

    def test_worker_prestaged_same_tree_restack_resolution_remains_recoverable(self):
        preview, source, _source_tree, new_base = self.begin_restack_conflict()
        (self.repo / 'input.txt').write_text(self.git('show', new_base + ':input.txt'))
        self.git('add', 'input.txt')
        self.assertEqual(new_base, self.git('rev-parse', 'HEAD').strip())
        self.assertEqual(source, self.git('rev-parse', 'CHERRY_PICK_HEAD').strip())
        self.assertEqual(self.git('rev-parse', 'HEAD^{tree}').strip(),
                         self.git('write-tree').strip())
        intent = git_phase_state.prepare_attempt_restack_continue(
            self.repo, preview, owned_paths=['input.txt'])
        self.assertEqual(self.git('rev-parse', 'HEAD^{tree}').strip(), intent['result_tree'])
        self.assertEqual(new_base, self.git('rev-parse', 'HEAD').strip())
        self.assertEqual(source, self.git('rev-parse', 'CHERRY_PICK_HEAD').strip())

    def test_abort_attempt_restack_restores_new_base_and_original_attempt(self):
        preview, source, source_tree, new_base = self.begin_restack_conflict()

        result = git_phase_state.abort_attempt_restack(
            self.repo, preview, owned_paths=['input.txt'])

        self.assertEqual('aborted', result['status'])
        self.assertEqual(new_base, result['head_commit'])
        self.assertEqual(new_base, self.git('rev-parse', 'HEAD').strip())
        self.assertEqual('', self.git('status', '--porcelain'))
        self.assertFalse((self.repo / '.git/CHERRY_PICK_HEAD').exists())
        self.assertEqual(source_tree, self.git('rev-parse', source + '^{tree}').strip())
        self.assertEqual(source, self.git('rev-parse', 'original-attempt').strip())

        replay = git_phase_state.abort_attempt_restack(
            self.repo, preview, owned_paths=['input.txt'])
        self.assertEqual(result, replay)
        self.assertEqual(new_base, self.git('rev-parse', 'HEAD').strip())
        self.assertEqual('', self.git('status', '--porcelain'))

    def test_restack_rejects_arbitrary_owned_child_without_exact_replay_sequencer(self):
        preview, _, _, new_base = self.restack_case(conflict=True)
        arbitrary = self.result('input.txt', 'arbitrary owned result\n')
        self.assertEqual(new_base, self.git('rev-parse', arbitrary + '^').strip())
        self.assertNotEqual(preview['proposed_tree'],
                            self.git('rev-parse', arbitrary + '^{tree}').strip())
        self.assertNotEqual(0, subprocess.run(
            ['git', 'rev-parse', '--verify', 'CHERRY_PICK_HEAD'], cwd=self.repo,
            capture_output=True).returncode)

        accepted = []
        for name, operation in (
                ('apply', git_phase_state.apply_attempt_restack),
                ('continue', git_phase_state.continue_attempt_restack)):
            self.git('reset', '--hard', arbitrary)
            try:
                operation(self.repo, preview, owned_paths=['input.txt'])
            except ValueError:
                pass
            else:
                accepted.append(name)

        self.assertEqual([], accepted,
                         'An arbitrary child is not proof of the exact previewed replay')

    def test_restack_rejects_owned_scope_substitution_for_apply_and_continue(self):
        preview, _, _, _ = self.restack_case(conflict=True)
        expanded = ['input.txt', 'extra.txt']
        accepted = []
        try:
            git_phase_state.apply_attempt_restack(
                self.repo, preview, owned_paths=expanded)
        except ValueError:
            pass
        else:
            accepted.append('apply')

        git_phase_state.abort_attempt_restack(
            self.repo, preview, owned_paths=['input.txt'])
        git_phase_state.apply_attempt_restack(
            self.repo, preview, owned_paths=['input.txt'])
        (self.repo / 'input.txt').write_text('resolved result\n')
        (self.repo / 'extra.txt').write_text('scope substitution dirt\n')
        self.git('add', 'extra.txt')
        try:
            git_phase_state.continue_attempt_restack(
                self.repo, preview, owned_paths=expanded)
        except ValueError:
            pass
        else:
            accepted.append('continue')

        self.assertEqual([], accepted,
                         'Restack execution must retain the exact previewed owned scope')

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

    def test_compaction_base_accepts_a_reviewed_custom_git_node(self):
        self.remote()
        result = self.result('custom.txt')
        retained = git_phase_state.retain_attempt_ref(
            self.repo, remote='origin', goal=566, node='custom_phase',
            attempt='c' * 32, commit=result)
        self.assertEqual(self.base, git_phase_state.compaction_base_from_attempts(
            self.repo, goal=566, test_source=result,
            attempts=[{'ref': retained['ref'], 'commit': result}],
            remote='origin', phase='custom_phase'))
        with self.assertRaisesRegex(ValueError, 'retained phase attempts'):
            git_phase_state.compaction_base_from_attempts(
                self.repo, goal=566, test_source=result,
                attempts=[{'ref': retained['ref'], 'commit': result}],
                remote='origin', phase='../unsafe')

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

    def test_interleaved_t1_i1_t2_i2_compacts_to_final_red_and_green(self):
        self.remote()
        self.git('switch', '-c', 'feat/interleaved')
        attempts = []
        sequence = (
            ('test_design', 'behavior_test.py', 'assert value() == 1\n'),
            ('implement', 'output.py', 'def value(): return 1\n'),
            ('test_design', 'behavior_test.py', 'assert value() == 2\n'),
            ('implement', 'output.py', 'def value(): return 2\n'),
        )
        for number, (phase, path, value) in enumerate(sequence, start=1):
            commit = self.result(path, value)
            retained = git_phase_state.retain_attempt_ref(self.repo, remote='origin',
                goal=566, node=phase, attempt=f'{number:032x}', commit=commit)
            attempts.append({'ref': retained['ref'], 'commit': commit})
        test_source = attempts[2]['commit']
        implementation_source = attempts[3]['commit']
        self.assertEqual(self.base, git_phase_state.compaction_base_from_attempts(
            self.repo, goal=566, test_source=test_source,
            attempts=[attempts[0], attempts[2]], remote='origin'))
        preview = git_phase_state.preview_two_commit_candidate(self.repo,
            goal=566, base_commit=self.base, test_source=test_source,
            implementation_source=implementation_source,
            test_owned=['behavior_test.py'], implementation_owned=['output.py'],
            retained_attempts=attempts, remote='origin')
        compacted = git_phase_state.apply_two_commit_candidate(self.repo, preview,
            test_owned=['behavior_test.py'], implementation_owned=['output.py'],
            retained_attempts=attempts, remote='origin')
        self.assertEqual('2', self.git('rev-list', '--count',
                                     f"{self.base}..{compacted['implementation_commit']}").strip())
        self.assertEqual('assert value() == 2\n',
            self.git('show', compacted['test_commit'] + ':behavior_test.py'))
        self.assertNotEqual(self.git('rev-parse', test_source + '^{tree}').strip(),
                            self.git('rev-parse', compacted['test_commit'] + '^{tree}').strip())
        self.assertEqual(implementation_source,
            git_phase_state.verify_two_commit_candidate(self.repo, goal=566,
                base_commit=self.base, head_commit=compacted['implementation_commit'],
                test_owned=['behavior_test.py'])['implementation_source'])
        with self.assertRaisesRegex(ValueError, 'Candidate tree differs'):
            git_phase_state.verify_two_commit_candidate(self.repo, goal=566,
                base_commit=self.base, head_commit=compacted['implementation_commit'])
        self.assertEqual(preview, git_phase_state.preview_two_commit_candidate(self.repo,
            goal=566, base_commit=self.base, test_source=test_source,
            implementation_source=implementation_source,
            test_owned=['behavior_test.py'], implementation_owned=['output.py'],
            retained_attempts=attempts, remote='origin'))
        self.assertEqual('existing', git_phase_state.apply_two_commit_candidate(self.repo,
            preview, test_owned=['behavior_test.py'], implementation_owned=['output.py'],
            retained_attempts=attempts, remote='origin')['outcome'])
        self.git('switch', '-c', 'feat/interleaved-declared', implementation_source)
        groups = [
            {'id': 'red', 'order': 0, 'commit_type': 'test', 'summary': 'reviewed RED checks',
             'nodes': [{'node': 'test_design', 'source': test_source,
                        'owned': ['behavior_test.py']}]},
            {'id': 'green', 'order': 1, 'commit_type': 'feat', 'summary': 'reviewed GREEN behavior',
             'nodes': [{'node': 'implement', 'source': implementation_source,
                        'owned': ['output.py']}]},
        ]
        grouped = git_phase_state.preview_grouped_candidate(self.repo, goal=566,
            base_commit=self.base, groups=groups, retained_attempts=attempts,
            remote='origin')
        compacted_grouped = git_phase_state.apply_grouped_candidate(self.repo, grouped,
            groups=groups, retained_attempts=attempts, remote='origin')
        self.assertEqual(preview['test_tree'],
                         self.git('rev-parse', compacted_grouped['commits'][0] + '^{tree}').strip())
        self.assertEqual(preview['implementation_tree'],
                         self.git('rev-parse', compacted_grouped['head_commit'] + '^{tree}').strip())
        for row in attempts:
            self.assertEqual(row['commit'], self.git('ls-remote', 'origin', row['ref']).split()[0])

    def test_declarative_groups_compact_custom_nodes_and_bind_exact_plan(self):
        self.remote()
        self.git('switch', '-c', 'feat/custom-groups')
        attempts, sources = [], {}
        for number, (node, path) in enumerate((
                ('checks_a', 'a_test.py'), ('checks_b', 'b_test.py'),
                ('ship', 'source.py')), start=1):
            source = self.result(path, f'{node} = True\n')
            retained = git_phase_state.retain_attempt_ref(
                self.repo, remote='origin', goal=566, node=node,
                attempt=f'{number:032x}', commit=source)
            attempts.append({'ref': retained['ref'], 'commit': source})
            sources[node] = source
        groups = [
            {'id': 'checks', 'order': 0, 'commit_type': 'test',
             'summary': 'consolidate reviewed checks', 'nodes': [
                 {'node': 'checks_a', 'source': sources['checks_a'], 'owned': ['a_test.py']},
                 {'node': 'checks_b', 'source': sources['checks_b'], 'owned': ['b_test.py']}]},
            {'id': 'code', 'order': 1, 'commit_type': 'feat',
             'summary': 'deliver reviewed behavior', 'nodes': [
                 {'node': 'ship', 'source': sources['ship'], 'owned': ['source.py']}]},
        ]
        preview = git_phase_state.preview_grouped_candidate(
            self.repo, goal=566, base_commit=self.base, groups=groups,
            retained_attempts=attempts, remote='origin')
        result = git_phase_state.apply_grouped_candidate(self.repo, preview,
            groups=groups, retained_attempts=attempts, remote='origin')
        self.assertEqual('created', result['outcome'])
        self.assertEqual(2, len(result['commits']))
        self.assertEqual('2', self.git('rev-list', '--count', f"{self.base}..HEAD").strip())
        for path in ('a_test.py', 'b_test.py'):
            self.assertTrue(self.git('show', result['commits'][0] + ':' + path))
        self.assertEqual(result['head_commit'], git_phase_state.verify_grouped_candidate(
            self.repo, goal=566, base_commit=self.base, head_commit=result['head_commit'],
            groups=groups, retained_attempts=attempts, remote='origin')['head_commit'])
        self.assertEqual('existing', git_phase_state.apply_grouped_candidate(
            self.repo, preview, groups=groups, retained_attempts=attempts,
            remote='origin')['outcome'])
        changed = [{**groups[0], 'summary': 'different reviewed claim'}, groups[1]]
        with self.assertRaisesRegex(ValueError, 'reviewed compacted plan'):
            git_phase_state.verify_grouped_candidate(
                self.repo, goal=566, base_commit=self.base, head_commit=result['head_commit'],
                groups=changed, retained_attempts=attempts, remote='origin')
        self.git('push', '--force', 'origin', self.base + ':' + attempts[0]['ref'])
        with self.assertRaisesRegex(ValueError, 'missing or moved'):
            git_phase_state.verify_grouped_candidate(
                self.repo, goal=566, base_commit=self.base, head_commit=result['head_commit'],
                groups=groups, retained_attempts=attempts, remote='origin')

    def test_current_graph_declarations_select_exact_reviewed_sources(self):
        import test_evidence_dag_journeys as journeys
        self.remote()
        self.git('switch', '-c', 'feat/declared-sources')
        artifacts, current, workspaces, evidence, nodes = {}, {}, {}, [], []
        for order, (name, path) in enumerate((('checks', 'behavior_test.py'),
                                               ('ship', 'source.py'))):
            source_commit = self.result(path, f'{name} = True\n')
            retained = git_phase_state.retain_attempt_ref(self.repo,
                remote='origin', goal=566, node=name,
                attempt=f'{order + 1:032x}', commit=source_commit)
            result_ref = {'hash': f'result-{name}'}
            output_ref = {'hash': f'output-{name}'}
            proof_ref = {'hash': f'proof-{name}'}
            identity = {'goal': 566, 'node': name, 'item': None, 'generation': 1}
            result = {'node': identity, 'outputs': {'value': output_ref}}
            artifacts[result_ref['hash']] = {'content': result}
            artifacts[output_ref['hash']] = {'provenance': {'source': proof_ref}}
            artifacts[proof_ref['hash']] = {'kind': 'git_phase_proof',
                'checkpoint': {'result_commit': source_commit},
                'retained_ref': retained['ref']}
            key = (566, name, None, 1)
            current[key] = (result_ref, result)
            workspaces[key] = {'git_workspace': True, 'entry': {'owned': [path]}}
            evidence.append(result_ref)
            nodes.append({'id': name, 'git_publish': {
                'series': 'release', 'group': name, 'order': order,
                'output': 'value', 'commit_type': 'test' if order == 0 else 'feat',
                'summary': 'publish ' + name}})
        workflow = object.__new__(journeys.z._workflow.Workflow)
        workflow.repo = self.repo
        snapshot = {'number': 566, 'graph': {'nodes': nodes}, 'artifacts': artifacts,
                    'projection': {'current': current}, 'workspaces': workspaces,
                    'payload': {'evidence': evidence, 'operational': {'receipts': []}},
                    'resolve': lambda ref: artifacts[ref['hash']]}
        inputs = workflow.node_compaction_inputs(snapshot)
        self.assertEqual('grouped', inputs['delivery_class'])
        self.assertEqual(self.base, inputs['base_commit'])
        self.assertEqual(['checks', 'ship'], [group['id'] for group in inputs['groups']])
        self.assertEqual(2, len(inputs['retained_attempts']))

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

    def test_composition_compacts_retained_corrections_to_one_commit(self):
        self.remote()
        self.git('switch', '-c', 'feat/composition')
        attempts = []
        for number, value in enumerate(('first integration\n', 'corrected integration\n'), start=1):
            source = self.result('integration.txt', value)
            retained = git_phase_state.retain_attempt_ref(self.repo, remote='origin',
                goal=566, node='integration_verification',
                attempt=f'{number:032x}', commit=source)
            attempts.append({'ref': retained['ref'], 'commit': source})
        source = attempts[-1]['commit']
        base = git_phase_state.compaction_base_from_attempts(
            self.repo, goal=566, test_source=source, attempts=attempts,
            remote='origin', phase='integration_verification')
        self.assertEqual(self.base, base)
        preview = git_phase_state.preview_single_commit_candidate(
            self.repo, goal=566, base_commit=base, source_commit=source,
            owned_paths=['integration.txt'], retained_attempts=attempts,
            remote='origin')
        first = git_phase_state.apply_single_commit_candidate(
            self.repo, preview, owned_paths=['integration.txt'],
            retained_attempts=attempts, remote='origin')
        self.assertEqual('created', first['outcome'])
        self.assertEqual('1', self.git('rev-list', '--count', f'{base}..HEAD').strip())
        self.assertEqual(source, git_phase_state.verify_single_commit_candidate(
            self.repo, goal=566, base_commit=base,
            head_commit=first['candidate_commit'])['source_commit'])
        self.assertEqual('existing', git_phase_state.apply_single_commit_candidate(
            self.repo, preview, owned_paths=['integration.txt'],
            retained_attempts=attempts, remote='origin')['outcome'])
        for row in attempts:
            self.assertEqual(row['commit'], self.git('ls-remote', 'origin', row['ref']).split()[0])

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
