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
        observed = managed.inspect_attempt_worktree(self.repo, goal=566,
            node='implement', attempt='a' * 32)
        self.assertEqual('dirty', observed['status'])
        self.assertEqual(self.base, observed['head'])
        with self.assertRaisesRegex(ValueError, 'dirty'):
            managed.cleanup_integrated_worktree(self.repo, goal=566, node='implement',
                attempt='a' * 32, expected_head=self.base, integrated_commit=self.base,
                remote='origin', retained_ref='refs/heads/zzzops/attempts/566/implement/' + 'a' * 32)
        self.assertTrue((path / 'unverified.txt').exists())

    def test_compacted_delivery_can_cleanup_retained_correction_worktree(self):
        first = managed.prepare_worktree(self.repo, goal=566, node='test_design',
                                         attempt='b' * 32, base_commit=self.base)
        first_path = Path(first['path'])
        (first_path / 'behavior_test.py').write_text('assert False\n')
        self.git('add', 'behavior_test.py', cwd=first_path)
        self.git('commit', '-qm', 'test: first attempt', cwd=first_path)
        rejected = self.git('rev-parse', 'HEAD', cwd=first_path).strip()
        first_ref = phase.retain_attempt_ref(first_path, remote='origin', goal=566,
            node='test_design', attempt='b' * 32, commit=rejected)['ref']
        corrected = managed.prepare_worktree(self.repo, goal=566, node='test_design',
                                             attempt='c' * 32, base_commit=rejected)
        corrected_path = Path(corrected['path'])
        (corrected_path / 'behavior_test.py').write_text('assert True\n')
        self.git('add', 'behavior_test.py', cwd=corrected_path)
        self.git('commit', '-qm', 'test: corrected attempt', cwd=corrected_path)
        test_source = self.git('rev-parse', 'HEAD', cwd=corrected_path).strip()
        test_ref = phase.retain_attempt_ref(corrected_path, remote='origin', goal=566,
            node='test_design', attempt='c' * 32, commit=test_source)['ref']
        implementation = managed.prepare_worktree(self.repo, goal=566, node='implement',
                                                  attempt='a' * 32, base_commit=test_source)
        implementation_path = Path(implementation['path'])
        (implementation_path / 'source.py').write_text('value = 1\n')
        self.git('add', 'source.py', cwd=implementation_path)
        self.git('commit', '-qm', 'feat: implementation', cwd=implementation_path)
        implementation_source = self.git('rev-parse', 'HEAD', cwd=implementation_path).strip()
        implementation_ref = phase.retain_attempt_ref(implementation_path, remote='origin',
            goal=566, node='implement', attempt='a' * 32,
            commit=implementation_source)['ref']
        attempts = [{'ref': ref, 'commit': commit} for ref, commit in (
            (first_ref, rejected), (test_ref, test_source),
            (implementation_ref, implementation_source))]
        candidate = managed.prepare_worktree(self.repo, goal=566, node='candidate',
                                             attempt='d' * 32, base_commit=implementation_source)
        candidate_path = Path(candidate['path'])
        preview = phase.preview_two_commit_candidate(candidate_path, goal=566,
            base_commit=self.base, test_source=test_source,
            implementation_source=implementation_source,
            test_owned=['behavior_test.py'], implementation_owned=['source.py'],
            retained_attempts=attempts, remote='origin')
        pair = phase.apply_two_commit_candidate(candidate_path, preview,
            test_owned=['behavior_test.py'], implementation_owned=['source.py'],
            retained_attempts=attempts, remote='origin')
        self.git('merge', '--no-ff', '-qm', 'merge reviewed candidate', candidate['branch'])
        integrated = self.git('rev-parse', 'HEAD').strip()
        removed = managed.cleanup_delivered_attempt_worktree(self.repo, goal=566,
            node='test_design', attempt='b' * 32, expected_head=rejected,
            delivery_base=self.base, delivery_head=pair['implementation_commit'],
            integrated_commit=integrated, remote='origin', retained_ref=first_ref)
        self.assertEqual('removed', removed['outcome'])
        self.assertFalse(first_path.exists())
        self.assertEqual(rejected, self.git('ls-remote', 'origin', first_ref).split()[0])
        self.assertEqual('already_removed', managed.cleanup_delivered_attempt_worktree(
            self.repo, goal=566, node='test_design', attempt='b' * 32,
            expected_head=rejected, delivery_base=self.base,
            delivery_head=pair['implementation_commit'], integrated_commit=integrated,
            remote='origin', retained_ref=first_ref)['outcome'])
        (corrected_path / 'unverified.txt').write_text('dirty local draft\n')
        with self.assertRaisesRegex(ValueError, 'dirty'):
            managed.cleanup_delivered_attempt_worktree(self.repo, goal=566,
                node='test_design', attempt='c' * 32, expected_head=test_source,
                delivery_base=self.base, delivery_head=pair['implementation_commit'],
                integrated_commit=integrated, remote='origin', retained_ref=test_ref)
        self.assertTrue((corrected_path / 'unverified.txt').exists())
        candidate_removed = managed.cleanup_delivered_candidate_worktree(
            self.repo, goal=566, attempt='d' * 32,
            expected_head=pair['implementation_commit'], delivery_base=self.base,
            integrated_commit=integrated)
        self.assertEqual('removed', candidate_removed['outcome'])
        self.assertFalse(candidate_path.exists())


    def test_composition_cleanup_preserves_remote_attempt_and_removes_clean_worktrees(self):
        attempt = managed.prepare_worktree(self.repo, goal=566,
            node='integration_verification', attempt='a' * 32, base_commit=self.base)
        attempt_path = Path(attempt['path'])
        (attempt_path / 'integration.txt').write_text('combined behavior verified\n')
        self.git('add', 'integration.txt', cwd=attempt_path)
        self.git('commit', '-qm', 'test(goal-566): verify composition', cwd=attempt_path)
        source = self.git('rev-parse', 'HEAD', cwd=attempt_path).strip()
        retained = phase.retain_attempt_ref(attempt_path, remote='origin', goal=566,
            node='integration_verification', attempt='a' * 32, commit=source)['ref']
        candidate = managed.prepare_worktree(self.repo, goal=566, node='candidate',
            attempt='b' * 32, base_commit=source)
        candidate_path = Path(candidate['path'])
        attempts = [{'ref': retained, 'commit': source}]
        preview = phase.preview_single_commit_candidate(candidate_path, goal=566,
            base_commit=self.base, source_commit=source,
            owned_paths=['integration.txt'], retained_attempts=attempts, remote='origin')
        compacted = phase.apply_single_commit_candidate(candidate_path, preview,
            owned_paths=['integration.txt'], retained_attempts=attempts, remote='origin')
        head = compacted['candidate_commit']
        self.git('merge', '--no-ff', '-qm', 'merge reviewed composition', candidate['branch'])
        integrated = self.git('rev-parse', 'HEAD').strip()
        removed = managed.cleanup_delivered_attempt_worktree(self.repo, goal=566,
            node='integration_verification', attempt='a' * 32, expected_head=source,
            delivery_base=self.base, delivery_head=head, integrated_commit=integrated,
            remote='origin', retained_ref=retained, delivery_class='composition')
        self.assertEqual('removed', removed['outcome'])
        self.assertFalse(attempt_path.exists())
        self.assertEqual(source, self.git('ls-remote', 'origin', retained).split()[0])
        removed_candidate = managed.cleanup_delivered_candidate_worktree(self.repo,
            goal=566, attempt='b' * 32, expected_head=head,
            delivery_base=self.base, integrated_commit=integrated,
            delivery_class='composition')
        self.assertEqual('removed', removed_candidate['outcome'])
        self.assertFalse(candidate_path.exists())


if __name__ == '__main__':
    unittest.main()
