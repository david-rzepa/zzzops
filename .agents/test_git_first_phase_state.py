"""Git-backed workspace identity at the public fresh-goal boundary."""

import json
import copy
import unittest
from unittest import mock
from pathlib import Path
import subprocess
import sys
import tempfile

import test_evidence_dag_journeys as journeys
from test_evidence_dag_journeys import DagFixture, z
from test_workflow_journey import fixtures


class FreshGoalGitCheckpointTests(DagFixture):
    def default_graph(self):
        template = json.loads((fixtures.PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        self.install(z._workflow_section(template, 'workflow_adherence')['configuration']['phase_dag'])

    def test_first_acquisition_with_many_files_is_bounded_and_replayable(self):
        paths = self.fixture.repo / 'many'
        paths.mkdir()
        for index in range(624):
            (paths / f'fixture_{index:04d}.txt').write_text(f'file {index}\n')
        self.session.git('add', 'many')
        self.session.git('commit', '-qm', 'fresh repository with many files')
        self.default_graph()

        work = self.session.acquire('requirements')
        acquisition = work['lease']['acquisition']
        self.assertEqual(self.session.git('rev-parse', 'HEAD').strip(), acquisition['read_commit'])
        self.assertNotIn('files', acquisition)
        self.assertNotIn('read_files', acquisition)
        self.assertTrue(all(len(comment['body']) <= 65536 for comment in self.provider.comments[100]))

        request = self.session.submission(work, {'value': {
            'statements': ['Preserve the fresh goal evidence.'], 'questions': [],
            'investigations': {'items': {}, 'rationale': 'No unknowns.'},
        }}, 'fresh-git-checkpoint-result')
        first = self.session.call(100, request)
        comments = len(self.provider.comments[100])
        second = self.session.call(100, request)
        self.assertEqual(first, second)
        self.assertEqual(comments, len(self.provider.comments[100]))
        self.assertEqual([100], sorted(self.provider.issues))
        self.assertEqual(1, len(self.payload()[1]['evidence']))
        next_work = self.session.acquire('spec')
        self.assertEqual(acquisition['read_commit'], next_work['lease']['acquisition']['read_commit'])
        self.assertTrue(all(len(comment['body']) <= 65536 for comment in self.provider.comments[100]))

    def test_moved_commit_cannot_accept_a_readonly_result(self):
        self.default_graph()
        work = self.session.acquire('requirements')
        (self.fixture.repo / 'product.txt').write_text('changed after acquisition\n')
        self.session.git('add', 'product.txt')
        self.session.git('commit', '-qm', 'move the input commit')
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        request = self.session.submission(work, {'value': {
            'statements': ['Stale evidence must be rejected.'], 'questions': [],
            'investigations': {'items': {}, 'rationale': 'No unknowns.'},
        }}, 'stale-commit-result')
        response = self.session.call(100, request, expected=2)
        self.assertIn('Git commit changed', json.dumps(response))
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_same_tree_new_commit_keeps_readonly_evidence_current(self):
        self.default_graph()
        work = self.session.acquire('requirements')
        pinned = work['lease']['acquisition']['read_commit']
        self.session.git('commit', '--allow-empty', '-qm', 'ancestry only')
        self.assertNotEqual(pinned, self.session.git('rev-parse', 'HEAD').strip())
        request = self.session.submission(work, {'value': {
            'statements': ['Ancestry-only movement retains this evidence.'], 'questions': [],
            'investigations': {'items': {}, 'rationale': 'No unknowns.'},
        }}, 'equivalent-tree-result')
        self.session.call(100, request)
        self.assertEqual(1, len(self.payload()[1]['evidence']))
        next_work = self.session.acquire('spec')
        self.assertEqual(self.session.git('rev-parse', 'HEAD').strip(),
                         next_work['lease']['acquisition']['read_commit'])


class GitWorkspaceAcquisitionTests(unittest.TestCase):
    def fixture_with_git_workspace(self):
        fixture = journeys.WorkspaceAuthorityPublicTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        paths = fixture.fixture.repo / 'many'
        paths.mkdir()
        for index in range(2200):
            (paths / f'fixture_{index:04d}.txt').write_text(f'file {index}\n')
        fixture.session.git('add', 'many')
        fixture.session.git('commit', '-qm', 'large workspace base')
        fixture.session.git('config', 'gc.auto', '0')
        def git_mode(graph, _allocations):
            for node in graph['nodes']:
                resources = node['executor']['resources']
                if 'repository_workspace' in resources:
                    resources[resources.index('repository_workspace')] = 'repository_git_workspace'
        fixture.setup_workspace(git_mode)
        return fixture

    def test_authorised_large_workspace_acquires_with_commit_only(self):
        fixture = self.fixture_with_git_workspace()

        work = fixture.acquire_workspace('alpha')
        acquisition = work['lease']['acquisition']
        self.assertEqual(fixture.session.git('rev-parse', 'HEAD').strip(), acquisition['git_commit'])
        self.assertNotIn('files', acquisition)
        self.assertNotIn('workspace_digest', acquisition)
        self.assertEqual([100], sorted(fixture.provider.issues))
        self.assertTrue(all(len(comment['body']) <= 65536 for comment in fixture.provider.comments[100]))


class GitWorkspaceJourneyTests(unittest.TestCase):
    fixture_with_git_workspace = GitWorkspaceAcquisitionTests.fixture_with_git_workspace

    def test_correction_attempts_compact_to_two_final_commits(self):
        case = journeys.DefaultCorrectionPublicTests('runTest')
        case.setUp()
        self.addCleanup(case.doCleanups)
        original_install = case.install
        def install_git_graph(graph):
            for node in graph['nodes']:
                if node['id'] in {'test_design', 'implement'}:
                    resources = node['executor']['resources']
                    resources[resources.index('repository_workspace')] = 'repository_git_workspace'
            return original_install(graph)
        case.install = install_git_graph
        remote_dir = tempfile.TemporaryDirectory()
        self.addCleanup(remote_dir.cleanup)
        bare = Path(remote_dir.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        case.session.git('remote', 'add', 'origin', str(bare))
        case.default_decomposition()
        case.session.finish(case.session.acquire('decomposition_review'), {
            'value': case.review('approved', 'Atomic disposition accepted'),
            'authorization': case.decomposition_authorization()})
        case.session.finish(case.session.acquire('retain_decomposition_findings'), {
            'value': {'items': {}, 'rationale': 'No decomposition findings'}})

        first = case.session.acquire('test_design')
        path = case.fixture.repo / 'behavior_test.py'
        path.write_text("raise AssertionError('unconditional red')\n")
        case.session.git('add', path.name)
        case.session.git('commit', '-qm', 'test: first red attempt')
        rejected_commit = case.session.git('rev-parse', 'HEAD').strip()
        request = case.session.submission(first, {'value': 'Initial RED candidate'}, 'git-correction-first')
        request['workspace_checks'] = [[sys.executable, str(path)]]
        case.session.call(100, request)
        rejected = case.produced('test_design')
        case.verify_test_design(path, 'git-correction-red-verification')
        case.session.finish(case.session.acquire('test_design_review'), {
            'value': case.review('changes_requested', 'Use a meaningful behavior probe')})
        case.session.finish(case.session.acquire('interpret_test_design_rejection'), {'value': {
            'id': 'meaningful_probe', 'revision': 1, 'source': case.produced('test_design_review'),
            'subjects': [rejected], 'target': journeys.scope('test_design'),
            'request': 'Probe repository behavior', 'rationale': 'Unconditional failure is insufficient',
            'supersedes': None}})
        finding = case.produced('interpret_test_design_rejection')
        case.session.finish(case.session.acquire('admit_test_design_correction'), {
            'value': {'finding': finding, 'target_inputs': case.result('test_design')[1]['inputs'],
                      'authority': case.result('interpret_test_design_rejection')[0],
                      'applicability': 'applicable', 'rationale': 'Same reviewed allocation'},
            'transfer': None})

        corrected = case.session.acquire('test_design')
        self.assertEqual(rejected_commit, corrected['lease']['acquisition']['git_commit'])
        path.write_text("from pathlib import Path\nassert Path('product.txt').is_file()\n")
        case.session.git('add', path.name)
        case.session.git('commit', '-qm', 'test: correct red attempt')
        corrected_commit = case.session.git('rev-parse', 'HEAD').strip()
        request = case.session.submission(corrected, {'value': 'Meaningful RED probe'}, 'git-correction-second')
        request['workspace_checks'] = [[sys.executable, str(path)]]
        case.session.call(100, request)
        case.verify_test_design(path, 'git-correction-green-verification')
        case.session.finish(case.session.acquire('test_design_review'), {
            'value': case.review('approved', 'Current bounded probe is adequate')})
        case.session.finish(case.session.acquire('retain_test_design_findings'), {
            'value': {'items': {'meaningful_probe': finding}, 'rationale': 'Retain rejected attempt finding'}})
        case.session.finish(case.session.acquire('resolve_test_design_finding', item='meaningful_probe'), {
            'value': {'finding': finding, 'subjects': [case.produced('test_design')],
                      'reviewer_result': case.result('test_design_review')[0],
                      'decision': 'resolved', 'rationale': 'Fresh independent review resolves this finding'}})
        self.assertIn('implement', case.names())
        case.read_blob(rejected)
        final_test_tree = case.session.git('rev-parse', corrected_commit + '^{tree}').strip()
        original_base = first['lease']['acquisition']['git_commit']
        case.session.git('reset', '--soft', original_base)
        case.session.git('commit', '-qm', 'test: final reviewed RED tests')
        compacted_test = case.session.git('rev-parse', 'HEAD').strip()
        self.assertEqual(final_test_tree, case.session.git('rev-parse', 'HEAD^{tree}').strip())
        self.assertIn('implement', case.names())
        implementation = case.session.acquire('implement')
        self.assertEqual(compacted_test, implementation['lease']['acquisition']['git_commit'])
        (case.fixture.repo / 'source.py').write_text('def value():\n    return 2\n')
        case.session.git('add', 'source.py')
        case.session.git('commit', '-qm', 'feat: final GREEN implementation')
        request = case.session.submission(implementation, {'value': 'GREEN implementation'}, 'git-two-commit-final')
        request['workspace_checks'] = [[sys.executable, str(path)]]
        request['verification_expectation'] = 'passed'
        case.session.call(100, request)
        self.assertEqual('2', case.session.git('rev-list', '--count', f'{original_base}..HEAD').strip())
        self.assertNotEqual(rejected_commit, corrected_commit)
        for work, commit in ((first, rejected_commit), (corrected, corrected_commit)):
            ref = f"refs/heads/zzzops/attempts/100/test_design/{work['lease']['attempt']}"
            self.assertEqual(commit, case.session.git('ls-remote', 'origin', ref).split()[0])
        self.assertNotEqual(first['lease']['attempt'], corrected['lease']['attempt'])

    def test_clean_git_workspace_acquisition_does_not_hash_every_file(self):
        fixture = self.fixture_with_git_workspace()
        with (mock.patch.object(z._workflow.Workflow, 'workspace_files',
                                side_effect=AssertionError('repository file scan')),
              mock.patch.object(z._workflow.Workflow, 'git_files',
                                side_effect=AssertionError('Git blob scan'))):
            work = fixture.acquire_workspace('alpha')
        self.assertIn('git_commit', work['lease']['acquisition'])

    def test_unowned_commit_cannot_be_submitted_under_git_workspace_lease(self):
        fixture = self.fixture_with_git_workspace()
        work = fixture.acquire_workspace('alpha')
        (fixture.fixture.repo / 'unowned.txt').write_text('outside allocation\n')
        fixture.session.git('add', 'unowned.txt')
        fixture.session.git('commit', '-qm', 'unowned change')
        before = copy.deepcopy((fixture.provider.issues, fixture.provider.comments))
        request = fixture.session.submission(work, {'value': 'Cannot accept unowned output'}, 'git-unowned-result')
        request['workspace_checks'] = [[sys.executable, '-c', 'pass']]
        response = fixture.session.call(100, request, expected=2)
        self.assertIn('outside reviewed owned paths', json.dumps(response))
        self.assertEqual(before, (fixture.provider.issues, fixture.provider.comments))

    def test_committed_writable_result_is_retained_and_submitted_without_file_map(self):
        fixture = self.fixture_with_git_workspace()
        remote_dir = tempfile.TemporaryDirectory()
        self.addCleanup(remote_dir.cleanup)
        bare = Path(remote_dir.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        fixture.session.git('remote', 'add', 'origin', str(bare))
        work = fixture.acquire_workspace('alpha')
        (fixture.fixture.repo / 'behavior_test.py').write_text('from source import value\nassert value() == 1\n')
        fixture.session.git('add', 'behavior_test.py')
        fixture.session.git('commit', '-qm', 'test: implement goal 100 alpha')
        result_commit = fixture.session.git('rev-parse', 'HEAD').strip()
        request = fixture.session.submission(work, {'value': 'Committed alpha result'}, 'git-alpha-result')
        request['workspace_checks'] = [[sys.executable, '-B', 'behavior_test.py']]
        request['verification_expectation'] = 'passed'
        fixture.session.call(100, request)
        self.assertEqual(4, len(fixture.payload()[1]['evidence']))
        self.assertIn('observe_alpha', fixture.names())
        self.assertNotIn('beta', fixture.names())
        fixture.session.finish(fixture.session.acquire('observe_alpha', actor='independent-checker'),
                               {'value': 'Observed the exact committed alpha result'})
        fixture.session.finish(fixture.session.acquire('accept_alpha', actor='independent-reviewer'),
                               {'value': 'Approved the exact alpha result and check evidence'})
        self.assertIn('beta', fixture.names())
        beta = fixture.acquire_workspace('beta')
        self.assertEqual(result_commit, beta['lease']['acquisition']['git_commit'])
        ref = f"refs/heads/zzzops/attempts/100/alpha/{work['lease']['attempt']}"
        self.assertEqual(result_commit, fixture.session.git('ls-remote', 'origin', ref).split()[0])
        self.assertTrue(all(len(comment['body']) <= 65536 for comment in fixture.provider.comments[100]))
        fixture.session.git('push', '--force', 'origin',
                            f"{work['lease']['acquisition']['git_commit']}:{ref}")
        before = copy.deepcopy((fixture.provider.issues, fixture.provider.comments))
        steps = fixture.session.checkpoint(100)
        self.assertIn('Retained attempt ref is missing or moved', json.dumps(steps))
        self.assertEqual(before, (fixture.provider.issues, fixture.provider.comments))

    def test_red_test_commit_then_green_implementation_commit(self):
        fixture = self.fixture_with_git_workspace()
        remote_dir = tempfile.TemporaryDirectory()
        self.addCleanup(remote_dir.cleanup)
        bare = Path(remote_dir.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        fixture.session.git('remote', 'add', 'origin', str(bare))
        alpha = fixture.acquire_workspace('alpha')
        (fixture.fixture.repo / 'behavior_test.py').write_text('from source import value\nassert value() == 2\n')
        fixture.session.git('add', 'behavior_test.py')
        fixture.session.git('commit', '-qm', 'test: capture required behavior')
        test_commit = fixture.session.git('rev-parse', 'HEAD').strip()
        red = fixture.session.submission(alpha, {'value': 'RED test candidate'}, 'git-red-test')
        red['workspace_checks'] = [[sys.executable, '-B', 'behavior_test.py']]
        fixture.session.call(100, red)
        proof_ref = fixture.read_blob(fixture.produced('alpha'))['provenance']['source']
        self.assertEqual(1, fixture.read_blob(proof_ref)['commands'][0]['exit_code'])
        fixture.session.finish(fixture.session.acquire('observe_alpha', actor='test-checker'),
                               {'value': 'Observed RED at the exact test commit'})
        fixture.session.finish(fixture.session.acquire('accept_alpha', actor='test-reviewer'),
                               {'value': 'Independently accepted the RED test'})

        beta = fixture.acquire_workspace('beta')
        self.assertEqual(test_commit, beta['lease']['acquisition']['git_commit'])
        (fixture.fixture.repo / 'source.py').write_text('def value():\n    return 2\n')
        fixture.session.git('add', 'source.py')
        fixture.session.git('commit', '-qm', 'feat: satisfy reviewed test')
        implementation_commit = fixture.session.git('rev-parse', 'HEAD').strip()
        green = fixture.session.submission(beta, {'value': 'GREEN implementation candidate'}, 'git-green-implementation')
        green['workspace_checks'] = [[sys.executable, '-B', 'behavior_test.py']]
        green['verification_expectation'] = 'passed'
        fixture.session.call(100, green)
        proof_ref = fixture.read_blob(fixture.produced('beta'))['provenance']['source']
        self.assertEqual(0, fixture.read_blob(proof_ref)['commands'][0]['exit_code'])
        self.assertIn('observe_beta', fixture.names())
        ref = f"refs/heads/zzzops/attempts/100/beta/{beta['lease']['attempt']}"
        self.assertEqual(implementation_commit, fixture.session.git('ls-remote', 'origin', ref).split()[0])
        self.assertTrue(all(len(comment['body']) <= 65536 for comment in fixture.provider.comments[100]))


if __name__ == '__main__':
    unittest.main()
