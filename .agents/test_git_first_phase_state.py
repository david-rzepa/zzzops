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

    def test_inactive_legacy_composition_phase_does_not_force_repository_file_map(self):
        self.default_graph()
        with mock.patch.object(z._workflow.Workflow, 'workspace_files',
                               side_effect=AssertionError('inactive legacy phase scanned files')):
            self.session.acquire('requirements')

    def test_fresh_commit_only_acquisition_is_bounded_with_active_legacy_sibling(self):
        paths = self.fixture.repo / 'large-coexistence'
        paths.mkdir()
        for index in range(2200):
            (paths / f'fixture_{index:04d}.txt').write_text(f'file {index}\n')
        self.session.git('add', 'large-coexistence')
        self.session.git('commit', '-qm', 'large mixed workspace base')
        template = json.loads((fixtures.PLUGIN_ROOT /
                               'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        graph = z._workflow_section(
            template, 'workflow_adherence')['configuration']['phase_dag']
        legacy = journeys.task('legacy_sibling')
        legacy['executor']['resources'] = ['repository_workspace']
        graph['nodes'].append(legacy)
        graph['terminals'].append(journeys.selector('legacy_sibling'))
        z._workflow_section(self.session.project, 'workflow_adherence')[
            'configuration']['phase_dag'] = graph
        self.install(graph)
        frontier = self.session.ready()
        self.assertIn('requirements', {step['node']['node'] for step in frontier})
        self.assertEqual([], legacy['requires'])
        self.assertIn(journeys.selector('legacy_sibling'), graph['terminals'])

        original = z._workflow.Workflow.workspace_files
        scans = []
        def observe_legacy_scan(engine):
            scans.append(True)
            return original(engine)
        with mock.patch.object(z._workflow.Workflow, 'workspace_files',
                               autospec=True, side_effect=observe_legacy_scan):
            work = self.session.acquire('requirements', frontier=frontier)

        acquisition = work['lease']['acquisition']
        self.assertEqual(self.session.git('rev-parse', 'HEAD').strip(),
                         acquisition['read_commit'])
        self.assertNotIn('files', acquisition)
        self.assertNotIn('read_files', acquisition)
        self.assertEqual([], scans, 'Fresh commit-only acquisition scanned active legacy scope')
        serialized = json.dumps(self.provider.comments[100], sort_keys=True)
        self.assertNotIn('fixture_2199.txt', serialized)
        self.assertTrue(all(len(comment['body']) <= 65536
                            for comment in self.provider.comments[100]))

    def test_fresh_readonly_acquisition_skips_future_legacy_scopes_and_dirty_primary(self):
        paths = self.fixture.repo / 'many'
        paths.mkdir()
        for index in range(2200):
            (paths / f'fixture_{index:04d}.txt').write_text(f'file {index}\n')
        self.session.git('add', 'many')
        self.session.git('commit', '-qm', 'large committed goal input')
        dirty = self.fixture.repo / 'local-draft.txt'
        dirty.write_text('uncommitted local work\n')
        template = json.loads((fixtures.PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        graph = z._workflow_section(template, 'workflow_adherence')['configuration']['phase_dag']
        for node in graph['nodes']:
            if node['id'] in {'test_design', 'implement'}:
                node['executor']['resources'] = ['repository_workspace']
                node.pop('git_publish', None)
        self.install(graph)
        with mock.patch.object(z._workflow.Workflow, 'workspace_files',
                               side_effect=AssertionError('future legacy task scanned files')):
            work = self.session.acquire('requirements')
        self.assertEqual(self.session.git('rev-parse', 'HEAD').strip(),
                         work['lease']['acquisition']['read_commit'])
        self.assertNotIn('files', work['lease']['acquisition'])
        self.assertFalse((Path(work['managed_worktree']['path']) / dirty.name).exists())
        self.assertTrue(dirty.exists())
        self.assertEqual([100], sorted(self.provider.issues))
        self.assertTrue(all(len(comment['body']) <= 65536
                            for comment in self.provider.comments[100]))

    def test_fresh_readonly_acquisition_from_nonowning_checkout_uses_registered_owner(self):
        sibling_root = tempfile.TemporaryDirectory()
        self.addCleanup(sibling_root.cleanup)
        sibling = Path(sibling_root.name) / 'unmanaged-sibling'
        self.session.git('worktree', 'add', '-q', '--detach', str(sibling), 'HEAD')
        self.addCleanup(subprocess.run, ['git', '-C', str(self.fixture.repo),
                                        'worktree', 'remove', '--force', str(sibling)],
                        capture_output=True)
        (sibling / 'local-review-notes.txt').write_text('not part of the committed input\n')
        self.session.repo = sibling
        self.default_graph()

        work = self.session.acquire('requirements')

        self.assertEqual(self.session.git('rev-parse', 'HEAD').strip(),
                         work['lease']['acquisition']['read_commit'])
        self.assertEqual(self.fixture.repo / '.zzzops/worktrees/100/requirements' /
                         work['lease']['attempt'], Path(work['managed_worktree']['path']))
        self.assertFalse((Path(work['managed_worktree']['path']) /
                          'local-review-notes.txt').exists())
        self.assertTrue((sibling / 'local-review-notes.txt').exists())
        self.assertNotIn('files', work['lease']['acquisition'])
        self.assertEqual([100], sorted(self.provider.issues))

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

    def test_literal_shipped_dag_uses_reviewed_cutover_contract(self):
        template = json.loads((fixtures.PLUGIN_ROOT /
                               'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        shipped = copy.deepcopy(z._workflow_section(
            template, 'workflow_adherence')['configuration']['phase_dag'])
        self.install(shipped)
        work = self.session.acquire('requirements')
        self.session.finish(work, {'value': {
            'statements': ['Retain exact shipped-DAG evidence.'], 'questions': [],
            'investigations': {'items': {}, 'rationale': 'No unknowns.'},
        }}, 'shipped-cutover-requirements')
        result = self.result('requirements')[0]

        changed = copy.deepcopy(shipped)
        audit = journeys.task('shipped_cutover_audit', ['requirements'])
        audit['inputs'] = {'subject': journeys.subject_input('requirements')}
        requirements = next(node for node in shipped['nodes'] if node['id'] == 'requirements')
        audit['inputs']['subject']['type'] = copy.deepcopy(requirements['outputs']['value']['schema'])
        audit['independent_of'] = [journeys.selector('requirements')]
        changed['nodes'].append(audit)
        changed['terminals'].append(journeys.selector('shipped_cutover_audit'))
        z._workflow_section(self.session.project, 'workflow_adherence')[
            'configuration']['phase_dag'] = changed
        cutover = self.session.checkpoint(100)[0]
        self.assertEqual('policy_dag_cutover', cutover['kind'])
        compiled = z._static_workflow.definition(shipped, z._graph_compiler)['graph']
        self.assertEqual(compiled, self.read_blob(cutover['contract']['old_graph']))
        self.assertIn('prepare', cutover)
        mapping = [{'old': {'node': 'requirements', 'output': 'value'},
                    'new': {'node': 'requirements', 'output': 'value'},
                    'result': result, 'equivalence': {
                        'inputs': True, 'outputs': True, 'scope': True,
                        'role': True, 'independence': True, 'approval': True}}]
        proposed = self.session.call(100, {**cutover['prepare'], 'actor': 'root-thread',
            'mapping': mapping, 'request_id': 'prepare-shipped-cutover'})['next_steps'][0]
        reviewed = self.session.call(100, {**proposed['review'],
            'actor': 'independent-shipped-cutover-reviewer', 'decision': 'approved',
            'report': 'Literal shipped result retains its exact contract',
            'request_id': 'review-shipped-cutover'})['next_steps'][0]
        applied = self.session.call(100, {**reviewed['apply'], 'actor': 'root-thread',
            'request_id': 'apply-shipped-cutover'})['next_steps'][0]
        self.assertEqual('policy_dag_cutover_applied', applied['kind'])
        self.assertEqual(result, self.result('requirements')[0])
        self.assertIn('shipped_cutover_audit', self.names())

    def test_readonly_managed_worktree_must_remain_at_exact_clean_commit(self):
        self.default_graph()
        work = self.session.acquire('requirements')
        path = Path(work['managed_worktree']['path'])
        (path / 'unreviewed.txt').write_text('uncommitted draft\n')
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        request = self.session.submission(work, {'value': {
            'statements': ['This must not be accepted.'], 'questions': [],
            'investigations': {'items': {}, 'rationale': 'None.'},
        }}, 'dirty-readonly-worktree')
        response = self.session.call(100, request, expected=2)
        self.assertIn('Read-only managed worktree changed', json.dumps(response))
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertTrue((path / 'unreviewed.txt').exists())

    def test_start_replay_never_resumes_dirty_readonly_worktree(self):
        self.default_graph()
        step = next(s for s in self.session.ready() if s['node']['node'] == 'requirements')
        receipt = json.loads(Path(step['policy']['path']).read_text())['policy_receipt']
        request = {**step['start'], 'policy_receipt': receipt,
                   'request_id': 'dirty-readonly-start-replay'}
        started = self.session.call(100, request)['next_steps'][0]
        path = Path(started['managed_worktree']['path'])
        (path / 'unreviewed.txt').write_text('dirty reviewer draft\n')
        comments = len(self.provider.comments[100])
        replay = self.session.call(100, request, expected=2)
        self.assertIn('Managed worktree changed', json.dumps(replay))
        self.assertEqual(comments, len(self.provider.comments[100]))
        self.assertTrue((path / 'unreviewed.txt').exists())

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
    def fixture_with_git_workspace(self, *, many_files=0):
        fixture = journeys.WorkspaceAuthorityPublicTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        if many_files:
            paths = fixture.fixture.repo / 'many'
            paths.mkdir()
            for index in range(many_files):
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
        fixture = self.fixture_with_git_workspace(many_files=2200)

        work = fixture.acquire_workspace('alpha')
        acquisition = work['lease']['acquisition']
        managed = work['managed_worktree']
        self.assertEqual(fixture.session.git('rev-parse', 'HEAD').strip(), acquisition['git_commit'])
        self.assertEqual('created', managed['outcome'])
        self.assertEqual(acquisition['git_commit'],
                         subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=managed['path'],
                                        capture_output=True, text=True, check=True).stdout.strip())
        self.assertEqual('', fixture.session.git('status', '--porcelain'))
        self.assertNotIn('files', acquisition)
        self.assertNotIn('workspace_digest', acquisition)
        self.assertEqual([100], sorted(fixture.provider.issues))
        self.assertTrue(all(len(comment['body']) <= 65536 for comment in fixture.provider.comments[100]))

    def test_large_workspace_does_not_scale_first_acquisition_provider_writes(self):
        observations = []
        for many_files in (0, 2200):
            fixture = self.fixture_with_git_workspace(many_files=many_files)
            work = fixture.acquire_workspace('alpha')
            comments = fixture.provider.comments[100]
            serialized = json.dumps({
                'issue': fixture.provider.issues[100],
                'comments': comments,
            }, sort_keys=True, separators=(',', ':'))
            observations.append({
                'writes': len(comments),
                'acquisition_bytes': len(json.dumps(
                    work['lease']['acquisition'], sort_keys=True,
                    separators=(',', ':')).encode()),
                'acquisition': work['lease']['acquisition'],
                'serialized': serialized,
            })

        small, large = observations
        self.assertEqual(small['writes'], large['writes'])
        self.assertEqual(small['acquisition_bytes'], large['acquisition_bytes'])
        self.assertNotIn('files', large['acquisition'])
        self.assertNotIn('workspace_digest', large['acquisition'])
        self.assertNotIn('fixture_2199.txt', large['serialized'])
        self.assertTrue(all(len(comment['body']) <= 65536
                            for comment in fixture.provider.comments[100]))

    def test_dirty_primary_checkout_does_not_enter_isolated_git_attempt(self):
        fixture = self.fixture_with_git_workspace()
        dirty = fixture.fixture.repo / 'local-uncommitted.txt'
        dirty.write_text('user draft outside the managed attempt\n')
        work = fixture.acquire_workspace('alpha')
        self.assertEqual(fixture.session.git('rev-parse', 'HEAD').strip(),
                         work['lease']['acquisition']['git_commit'])
        self.assertFalse((Path(work['managed_worktree']['path']) / dirty.name).exists())
        self.assertTrue(dirty.exists())
        self.assertEqual([100], sorted(fixture.provider.issues))
        self.assertTrue(all(len(comment['body']) <= 65536
                            for comment in fixture.provider.comments[100]))

    def test_public_start_retry_reuses_exact_worktree_and_receipt(self):
        fixture = self.fixture_with_git_workspace()
        step = next(s for s in fixture.session.ready() if s['node']['node'] == 'alpha')
        receipt = json.loads(Path(step['policy']['path']).read_text())['policy_receipt']
        request = {**step['start'], 'policy_receipt': receipt,
                   'request_id': 'managed-worktree-retry'}
        first = fixture.session.call(100, request)['next_steps'][0]
        comments = len(fixture.provider.comments[100])
        second = fixture.session.call(100, request)['next_steps'][0]
        self.assertEqual(first['lease'], second['lease'])
        self.assertEqual('existing', second['managed_worktree']['outcome'])
        self.assertEqual(first['managed_worktree']['path'], second['managed_worktree']['path'])
        self.assertEqual(comments, len(fixture.provider.comments[100]))
        self.assertEqual([100], sorted(fixture.provider.issues))

    def test_public_compaction_rejects_missing_repository_review_authority(self):
        fixture = self.fixture_with_git_workspace()
        before = copy.deepcopy((fixture.provider.issues, fixture.provider.comments))
        response = fixture.session.call(100, {
            'operation': 'compact_candidate', 'request_id': 'unreviewed-compaction',
            'authorization': {'hash': 'sha256:' + 'a' * 64,
                              'uri': 'urn:sha256:' + 'a' * 64},
        }, expected=2)
        self.assertIn('current repository authorization', json.dumps(response))
        self.assertEqual(before, (fixture.provider.issues, fixture.provider.comments))

    def test_public_compaction_persists_exact_candidate_without_duplicate_goal(self):
        fixture = self.fixture_with_git_workspace()
        repo = fixture.fixture.repo
        remote = Path(tempfile.mkdtemp()) / 'remote.git'
        self.addCleanup(lambda: __import__('shutil').rmtree(remote.parent))
        subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True)
        fixture.session.git('remote', 'add', 'origin', str(remote))
        base = fixture.session.git('rev-parse', 'HEAD').strip()
        (repo / 'behavior_test.py').write_text('assert True\n')
        fixture.session.git('add', 'behavior_test.py')
        fixture.session.git('commit', '-qm', 'test(goal-100): reviewed RED source')
        red = fixture.session.git('rev-parse', 'HEAD').strip()
        (repo / 'source.py').write_text('def value():\n    return 2\n')
        fixture.session.git('add', 'source.py')
        fixture.session.git('commit', '-qm', 'feat(goal-100): reviewed GREEN source')
        green = fixture.session.git('rev-parse', 'HEAD').strip()
        red_ref = 'refs/heads/zzzops/attempts/100/test_design/' + 'a' * 32
        green_ref = 'refs/heads/zzzops/attempts/100/implement/' + 'b' * 32
        fixture.session.git('push', 'origin', red + ':' + red_ref,
                            green + ':' + green_ref)
        inputs = {'goal': 100, 'base_commit': base,
                  'test_source': red, 'implementation_source': green,
                  'test_owned': ['behavior_test.py'],
                  'implementation_owned': ['source.py'],
                  'retained_attempts': [{'ref': red_ref, 'commit': red},
                                        {'ref': green_ref, 'commit': green}]}
        authority = {'hash': 'sha256:' + 'c' * 64,
                     'uri': 'urn:sha256:' + 'c' * 64}
        request = {'operation': 'compact_candidate',
                   'request_id': 'public-real-compaction',
                   'authorization': authority}
        receipts_before = len(fixture.payload()[1]['operational']['receipts'])
        create_comment = fixture.provider.create_issue_comment
        lost = []
        def uncertain_comment(number, body):
            result = create_comment(number, body)
            if number == 100 and not lost:
                lost.append(True)
                raise z.GoalTransitionProviderError('Compaction comment committed; response lost')
            return result
        with mock.patch.object(z._workflow.Workflow, 'node_compaction_authorization',
                               return_value=authority), \
             mock.patch.object(z._workflow.Workflow, 'node_compaction_inputs',
                               return_value=inputs):
            with mock.patch.object(fixture.provider, 'create_issue_comment',
                                   side_effect=uncertain_comment):
                fixture.session.call(100, request, expected=None)
            self.assertTrue(lost)
            first = fixture.session.call(100, request)
            comments = len(fixture.provider.comments[100])
            replay = fixture.session.call(100, request)
        self.assertEqual(first, replay)
        self.assertEqual(comments, len(fixture.provider.comments[100]))
        self.assertEqual([100], sorted(fixture.provider.issues))
        self.assertEqual(receipts_before + 1,
                         len(fixture.payload()[1]['operational']['receipts']))
        step = first['next_steps'][0]
        self.assertEqual('candidate_compacted', step['kind'])
        self.assertEqual('created', step['outcome'])
        self.assertNotEqual(green, step['head_oid'])
        self.assertTrue(all(len(comment['body']) <= 65536 for comment in fixture.provider.comments[100]))

    def test_public_compaction_accepts_reviewed_group_plan_without_duplicate_goal(self):
        fixture = self.fixture_with_git_workspace()
        remote_dir = tempfile.TemporaryDirectory()
        self.addCleanup(remote_dir.cleanup)
        remote = Path(remote_dir.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True)
        fixture.session.git('remote', 'add', 'origin', str(remote))
        base = fixture.session.git('rev-parse', 'HEAD').strip()
        attempts, members = [], []
        for number, (node, path) in enumerate((('checks', 'behavior_test.py'),
                                                ('ship', 'source.py')), start=1):
            (fixture.fixture.repo / path).write_text(f'{node} = True\n')
            fixture.session.git('add', path)
            fixture.session.git('commit', '-qm', f'feat(goal-100): record {node}')
            commit = fixture.session.git('rev-parse', 'HEAD').strip()
            ref = f'refs/heads/zzzops/attempts/100/{node}/{number:032x}'
            fixture.session.git('push', 'origin', commit + ':' + ref)
            attempts.append({'ref': ref, 'commit': commit})
            members.append({'node': node, 'source': commit, 'owned': [path]})
        groups = [
            {'id': 'checks', 'order': 0, 'nodes': [members[0]],
             'commit_type': 'test', 'summary': 'reviewed checks'},
            {'id': 'ship', 'order': 1, 'nodes': [members[1]],
             'commit_type': 'feat', 'summary': 'reviewed behavior'},
        ]
        authority = {'hash': 'sha256:' + 'd' * 64,
                     'uri': 'urn:sha256:' + 'd' * 64}
        inputs = {'goal': 100, 'delivery_class': 'grouped', 'base_commit': base,
                  'groups': groups, 'retained_attempts': attempts}
        request = {'operation': 'compact_candidate', 'request_id': 'grouped-public-compaction',
                   'authorization': authority}
        with mock.patch.object(z._workflow.Workflow, 'node_compaction_authorization',
                               return_value=authority), \
             mock.patch.object(z._workflow.Workflow, 'node_compaction_inputs',
                               return_value=inputs):
            first = fixture.session.call(100, request)
            comments = len(fixture.provider.comments[100])
            self.assertEqual(first, fixture.session.call(100, request))
        self.assertEqual(comments, len(fixture.provider.comments[100]))
        self.assertEqual([100], sorted(fixture.provider.issues))
        step = first['next_steps'][0]
        self.assertEqual('candidate_compacted', step['kind'])
        self.assertEqual(2, len(step['group_commits']))
        self.assertEqual(step['head_oid'], z._git_phase_state.verify_grouped_candidate(
            fixture.fixture.repo, goal=100, base_commit=base,
            head_commit=step['head_oid'], groups=groups,
            retained_attempts=attempts, remote='origin')['head_commit'])
        cleaned = z._workflow.managed_worktrees.cleanup_delivered_candidate_worktree(
            fixture.fixture.repo, goal=100, attempt='d' * 32,
            expected_head=step['head_oid'], delivery_base=base,
            integrated_commit=step['head_oid'], delivery_class='grouped',
            groups=groups, retained_attempts=attempts, remote='origin')
        self.assertEqual('removed', cleaned['outcome'])
        for attempt in attempts:
            self.assertEqual(attempt['commit'], fixture.session.git(
                'ls-remote', 'origin', attempt['ref']).split()[0])

    def test_worktree_creation_failure_after_start_replays_without_new_lease(self):
        fixture = self.fixture_with_git_workspace()
        step = next(s for s in fixture.session.ready() if s['node']['node'] == 'alpha')
        receipt = json.loads(Path(step['policy']['path']).read_text())['policy_receipt']
        request = {**step['start'], 'policy_receipt': receipt,
                   'request_id': 'managed-worktree-interrupted'}
        with mock.patch.object(z._workflow.managed_worktrees, 'prepare_worktree',
                               side_effect=ValueError('simulated local interruption')):
            failed = fixture.session.call(100, request, expected=2)
        self.assertIn('simulated local interruption', json.dumps(failed))
        comments = len(fixture.provider.comments[100])
        resumed = fixture.session.call(100, request)['next_steps'][0]
        self.assertEqual('created', resumed['managed_worktree']['outcome'])
        self.assertEqual(comments, len(fixture.provider.comments[100]))
        self.assertEqual(1, len(fixture.payload()[1]['operational']['leases']))

    def test_start_replay_resumes_dirty_writable_attempt_without_new_lease(self):
        fixture = self.fixture_with_git_workspace()
        step = next(s for s in fixture.session.ready() if s['node']['node'] == 'alpha')
        receipt = json.loads(Path(step['policy']['path']).read_text())['policy_receipt']
        request = {**step['start'], 'policy_receipt': receipt,
                   'request_id': 'managed-dirty-attempt-replay'}
        started = fixture.session.call(100, request)['next_steps'][0]
        path = Path(started['managed_worktree']['path'])
        (path / 'behavior_test.py').write_text('local draft survives replay\n')
        comments = len(fixture.provider.comments[100])
        resumed = fixture.session.call(100, request)['next_steps'][0]
        self.assertEqual('existing_dirty', resumed['managed_worktree']['outcome'])
        self.assertEqual(started['lease']['token'], resumed['lease']['token'])
        self.assertEqual('local draft survives replay\n',
                         (path / 'behavior_test.py').read_text())
        self.assertEqual(comments, len(fixture.provider.comments[100]))
        self.assertEqual(1, len(fixture.payload()[1]['operational']['leases']))

    def test_stopped_dirty_attempt_cannot_resume_from_old_start_receipt(self):
        fixture = self.fixture_with_git_workspace()
        step = next(s for s in fixture.session.ready() if s['node']['node'] == 'alpha')
        receipt = json.loads(Path(step['policy']['path']).read_text())['policy_receipt']
        request = {**step['start'], 'policy_receipt': receipt,
                   'request_id': 'stopped-dirty-start-replay'}
        started = fixture.session.call(100, request)['next_steps'][0]
        lease = started['lease']
        actor = 'worker-alpha-stopped'
        fixture.session.call(100, {**started['bind'], 'lease': lease['token'],
            'actor': actor, 'selection': lease['selection'], 'policy_receipt': receipt,
            'request_id': 'bind-stopped-dirty-attempt'})
        path = Path(started['managed_worktree']['path'])
        (path / 'behavior_test.py').write_text('dirty stopped draft\n')
        fixture.session.call(100, {'operation': 'recover', 'node': started['node'],
            'lease': lease['token'], 'actor': actor, 'worker_status': 'stopped',
            'evidence': 'Worker process exited.', 'request_id': 'recover-stopped-dirty'})
        replay = fixture.session.call(100, request, expected=2)
        self.assertIn('lease', json.dumps(replay).lower())
        self.assertEqual([], fixture.payload()[1]['operational']['leases'])
        self.assertEqual('dirty stopped draft\n', (path / 'behavior_test.py').read_text())

    def test_stopped_worker_recovery_preserves_dirty_managed_attempt(self):
        fixture = self.fixture_with_git_workspace()
        work = fixture.acquire_workspace('alpha')
        path = Path(work['managed_worktree']['path'])
        (path / 'behavior_test.py').write_text('unverified local draft\n')
        response = fixture.session.call(100, {
            'operation': 'recover', 'node': work['node'],
            'lease': work['lease']['token'], 'actor': work['bound_actor'],
            'worker_status': 'stopped', 'evidence': 'Worker process exited; local file observed.',
            'request_id': 'stopped-managed-attempt',
        })['next_steps'][0]
        self.assertEqual('dirty', response['preserved_attempt']['status'])
        self.assertEqual(str(path), response['preserved_attempt']['path'])
        self.assertTrue((path / 'behavior_test.py').exists())
        self.assertEqual([], fixture.payload()[1]['operational']['leases'])

    def test_stopped_clean_commit_is_retained_before_lease_release(self):
        fixture = self.fixture_with_git_workspace()
        remote_dir = tempfile.TemporaryDirectory()
        self.addCleanup(remote_dir.cleanup)
        bare = Path(remote_dir.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        fixture.session.git('remote', 'add', 'origin', str(bare))
        work = fixture.acquire_workspace('alpha')
        path = Path(work['managed_worktree']['path'])
        (path / 'behavior_test.py').write_text('assert True\n')
        subprocess.run(['git', 'add', 'behavior_test.py'], cwd=path, check=True)
        subprocess.run(['git', 'commit', '-qm', 'test: retained stopped attempt'], cwd=path, check=True)
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=path,
                              capture_output=True, text=True, check=True).stdout.strip()
        request = {'operation': 'recover', 'node': work['node'],
                   'lease': work['lease']['token'], 'actor': work['bound_actor'],
                   'worker_status': 'stopped', 'evidence': 'Worker process exited after commit.',
                   'request_id': 'stopped-clean-attempt'}
        first = fixture.session.call(100, request)['next_steps'][0]
        ref = f"refs/heads/zzzops/attempts/100/alpha/{work['lease']['attempt']}"
        self.assertEqual({'ref': ref, 'commit': head, 'outcome': 'created'}, first['retained_attempt'])
        self.assertEqual(head, subprocess.run(['git', 'ls-remote', '--exit-code', '--refs',
                                               str(bare), ref], capture_output=True,
                                              text=True, check=True).stdout.split()[0])
        self.assertEqual([], fixture.payload()[1]['operational']['leases'])
        comments = len(fixture.provider.comments[100])
        second = fixture.session.call(100, request)['next_steps'][0]
        self.assertEqual(ref, second['retained_attempt']['ref'])
        self.assertEqual(comments, len(fixture.provider.comments[100]))

    def test_failed_attempt_retention_does_not_release_lease(self):
        fixture = self.fixture_with_git_workspace()
        remote_dir = tempfile.TemporaryDirectory()
        self.addCleanup(remote_dir.cleanup)
        bare = Path(remote_dir.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        fixture.session.git('remote', 'add', 'origin', str(bare))
        work = fixture.acquire_workspace('alpha')
        path = Path(work['managed_worktree']['path'])
        (path / 'behavior_test.py').write_text('assert True\n')
        subprocess.run(['git', 'add', 'behavior_test.py'], cwd=path, check=True)
        subprocess.run(['git', 'commit', '-qm', 'test: retry stopped attempt'], cwd=path, check=True)
        request = {'operation': 'recover', 'node': work['node'],
                   'lease': work['lease']['token'], 'actor': work['bound_actor'],
                   'worker_status': 'stopped', 'evidence': 'Worker process exited after commit.',
                   'request_id': 'retry-retention'}
        comments = len(fixture.provider.comments[100])
        with mock.patch.object(z._workflow.git_phase_state, 'retain_attempt_ref',
                               side_effect=ValueError('remote unavailable')):
            failed = fixture.session.call(100, request, expected=2)
        self.assertIn('remote unavailable', json.dumps(failed))
        self.assertEqual(comments, len(fixture.provider.comments[100]))
        self.assertEqual(1, len(fixture.payload()[1]['operational']['leases']))
        recovered = fixture.session.call(100, request)['next_steps'][0]
        self.assertEqual('created', recovered['retained_attempt']['outcome'])
        self.assertEqual([], fixture.payload()[1]['operational']['leases'])

    def public_same_node_conflicting_restack(self):
        fixture = journeys.WorkspaceAuthorityPublicTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        original_install = fixture.install
        def install_git_graph(graph):
            for node in graph['nodes']:
                resources = node['executor']['resources']
                if 'repository_workspace' in resources:
                    resources[resources.index(
                        'repository_workspace')] = 'repository_git_workspace'
            return original_install(graph)
        fixture.install = install_git_graph
        remote_dir = tempfile.TemporaryDirectory()
        self.addCleanup(remote_dir.cleanup)
        bare = Path(remote_dir.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        fixture.session.git('remote', 'add', 'origin', str(bare))
        fixture.setup_workspace_corrections(target='alpha')

        first = fixture.acquire_workspace('alpha')
        first_tree = Path(first['managed_worktree']['path'])
        (first_tree / 'behavior_test.py').write_text('assert True\n')
        subprocess.run(['git', 'add', 'behavior_test.py'], cwd=first_tree, check=True)
        subprocess.run(['git', 'commit', '-qm', 'test: verified source attempt'],
                       cwd=first_tree, check=True)
        source_commit = subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=first_tree,
            capture_output=True, text=True, check=True).stdout.strip()
        submission = fixture.session.submission(
            first, {'value': 'Verified alpha source'}, 'verified-source-before-restack')
        submission['workspace_checks'] = [[sys.executable, '-B', 'behavior_test.py']]
        submission['verification_expectation'] = 'passed'
        fixture.session.call(100, submission)
        result_ref, _ = fixture.result('alpha')
        proof_ref = fixture.read_blob(fixture.produced('alpha'))['provenance']['source']
        proof = fixture.read_blob(proof_ref)
        self.assertTrue(proof['passed'])
        self.assertEqual(0, proof['commands'][0]['exit_code'])
        self.assertEqual(source_commit, proof['checkpoint']['result_commit'])
        expected_ref = (f"refs/heads/zzzops/attempts/100/alpha/"
                        f"{first['lease']['attempt']}")
        self.assertEqual(expected_ref, proof['retained_ref'])
        self.assertEqual(source_commit, fixture.session.git(
            'ls-remote', 'origin', expected_ref).split()[0])
        fixture.review_candidate('alpha', 0)

        fixture.admit_workspace_correction('alpha')
        moved_dir = tempfile.TemporaryDirectory()
        self.addCleanup(moved_dir.cleanup)
        moved = Path(moved_dir.name) / 'moved-base'
        fixture.session.git('worktree', 'add', '-q', '--detach', str(moved),
                            fixture.session.git('rev-parse', 'HEAD').strip())
        (moved / 'behavior_test.py').write_text('moved accepted base\n')
        subprocess.run(['git', 'add', 'behavior_test.py'], cwd=moved, check=True)
        subprocess.run(['git', 'commit', '-qm', 'test: conflicting accepted base'],
                       cwd=moved, check=True)
        new_base = subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=moved,
            capture_output=True, text=True, check=True).stdout.strip()
        workspace_context = z._workflow.Workflow.node_workspace_context
        def accepted_moved_base(engine, snapshots, projection, artifacts,
                                *, workspace_target=None):
            contexts = workspace_context(
                engine, snapshots, projection, artifacts,
                workspace_target=workspace_target)
            for key, context in contexts.items():
                if key[1] == 'alpha' and context.get('git_workspace'):
                    context['acquisition']['git_commit'] = new_base
            return contexts
        observations = []
        apply_restack = z._workflow.git_phase_state.apply_attempt_restack
        def observe_committed_start(repo, plan, owned_paths):
            payload = fixture.payload()[1]
            leases = [lease for lease in payload['operational']['leases']
                      if lease['node'] == step['node']]
            receipts = [row for row in payload['operational']['receipts']
                        if row['request'] == request['request_id']]
            observations.append({
                'leases': copy.deepcopy(leases),
                'receipts': copy.deepcopy(receipts),
                'plan': copy.deepcopy(plan),
                'owned_paths': copy.deepcopy(owned_paths),
            })
            return apply_restack(repo, plan, owned_paths)

        with mock.patch.object(z._workflow.Workflow, 'node_workspace_context',
                               autospec=True, side_effect=accepted_moved_base):
            step = next(s for s in fixture.session.ready()
                        if s['node']['node'] == 'alpha')
            receipt = json.loads(Path(step['policy']['path']).read_text())['policy_receipt']
            request = {**step['start'], 'policy_receipt': receipt,
                       'request_id': 'start-conflicting-restack'}
            with mock.patch.object(z._workflow.git_phase_state, 'apply_attempt_restack',
                                   side_effect=observe_committed_start):
                started = fixture.session.call(100, request)['next_steps'][0]

        self.assertEqual(1, len(observations),
                         'Public start must apply its host-derived restack plan')
        observed = observations[0]
        self.assertEqual(1, len(observed['leases']))
        self.assertEqual(started['lease']['token'], observed['leases'][0]['token'])
        self.assertEqual(1, len(observed['receipts']))
        self.assertEqual(['behavior_test.py'], observed['owned_paths'])
        expected_plan = z._git_phase_state.preview_attempt_restack(
            Path(started['managed_worktree']['path']),
            old_base=first['lease']['acquisition']['git_commit'],
            new_base=new_base, attempt_commit=source_commit,
            owned_paths=['behavior_test.py'])
        self.assertEqual(expected_plan, observed['plan'])
        self.assertEqual('conflict', started['restack']['status'])
        self.assertEqual({'result': result_ref, 'proof': proof_ref,
                          'ref': expected_ref, 'commit': source_commit},
                         started['restack']['source'])
        self.assertEqual(expected_plan, started['restack']['plan'])
        self.assertEqual(['behavior_test.py'], started['restack']['conflicts'])
        common = {'node': started['node'], 'lease': started['lease']['token'],
                  'actor': '<actual worker>',
                  'plan_hash': journeys.content_hash(expected_plan)}
        self.assertEqual({'operation': 'restack_continue', **common,
                          'request_id': '<unique request>'},
                         started['restack']['continue'])
        self.assertEqual({'operation': 'restack_abort', **common,
                          'request_id': '<unique request>'},
                         started['restack']['abort'])
        self.assertNotEqual(first['lease']['attempt'], started['lease']['attempt'])
        self.assertEqual(source_commit, subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=first_tree,
            capture_output=True, text=True, check=True).stdout.strip())
        self.assertEqual(source_commit, fixture.session.git(
            'ls-remote', 'origin', expected_ref).split()[0])
        self.assertEqual([100], sorted(fixture.provider.issues))
        fixture.session.call(100, {**started['bind'], 'actor': 'restack-worker',
            'selection': started['lease']['selection'], 'policy_receipt': receipt})
        started['bound_actor'] = 'restack-worker'
        return fixture, first, started, expected_plan, expected_ref, source_commit

    def test_public_same_node_start_commits_lease_before_conflicting_restack(self):
        self.public_same_node_conflicting_restack()

    def test_public_restack_continue_binds_exact_contract_and_replays_one_candidate(self):
        fixture, first, started, plan, source_ref, source_commit = \
            self.public_same_node_conflicting_restack()
        template = {**started['restack']['continue'], 'actor': 'restack-worker',
                    'request_id': 'continue-exact-restack'}
        provider_before = copy.deepcopy(
            (fixture.provider.issues, fixture.provider.comments))
        for label, changes in (
                ('lease', {'lease': 'wrong-lease'}),
                ('actor', {'actor': 'wrong-actor'}),
                ('plan', {'plan_hash': 'sha256:' + '0' * 64})):
            rejected = fixture.session.call(100, {
                **template, **changes, 'request_id': 'reject-' + label}, expected=2)
            self.assertIn('unsupported', json.dumps(rejected).lower())
        self.assertEqual(provider_before,
                         (fixture.provider.issues, fixture.provider.comments))
        worktree = Path(started['managed_worktree']['path'])
        (worktree / 'behavior_test.py').write_text('assert True\n')
        evidence_before = len(fixture.payload()[1]['evidence'])

        continued = fixture.session.call(100, template)['next_steps'][0]
        candidate = subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=worktree,
            capture_output=True, text=True, check=True).stdout.strip()
        replay = fixture.session.call(100, template)['next_steps'][0]

        self.assertEqual(continued, replay)
        self.assertEqual(candidate, continued['result_commit'])
        self.assertEqual(plan['new_base'], subprocess.run(
            ['git', 'rev-parse', candidate + '^'], cwd=worktree,
            capture_output=True, text=True, check=True).stdout.strip())
        self.assertEqual(1, int(subprocess.run(
            ['git', 'rev-list', '--count', plan['new_base'] + '..' + candidate],
            cwd=worktree, capture_output=True, text=True, check=True).stdout.strip()))
        self.assertEqual(evidence_before, len(fixture.payload()[1]['evidence']))
        self.assertEqual(source_commit, subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=first['managed_worktree']['path'],
            capture_output=True, text=True, check=True).stdout.strip())
        self.assertEqual(source_commit, fixture.session.git(
            'ls-remote', 'origin', source_ref).split()[0])
        self.assertEqual([100], sorted(fixture.provider.issues))

    def test_public_restack_abort_restores_new_base_and_preserves_source_attempt(self):
        fixture, first, started, plan, source_ref, source_commit = \
            self.public_same_node_conflicting_restack()
        template = {**started['restack']['abort'], 'actor': 'restack-worker',
                    'request_id': 'abort-exact-restack'}

        aborted = fixture.session.call(100, template)['next_steps'][0]
        replay = fixture.session.call(100, template)['next_steps'][0]
        worktree = Path(started['managed_worktree']['path'])

        self.assertEqual(aborted, replay)
        self.assertEqual('restack_aborted', aborted['kind'])
        self.assertEqual(plan['new_base'], aborted['head_commit'])
        self.assertEqual(plan['new_base'], subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=worktree,
            capture_output=True, text=True, check=True).stdout.strip())
        self.assertEqual('', subprocess.run(
            ['git', 'status', '--porcelain'], cwd=worktree,
            capture_output=True, text=True, check=True).stdout)
        self.assertEqual(source_commit, subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=first['managed_worktree']['path'],
            capture_output=True, text=True, check=True).stdout.strip())
        self.assertEqual(source_commit, fixture.session.git(
            'ls-remote', 'origin', source_ref).split()[0])
        self.assertEqual([100], sorted(fixture.provider.issues))

    def test_public_restack_continue_rejects_clean_child_without_replay_proof(self):
        fixture, _first, started, plan, _source_ref, _source_commit = \
            self.public_same_node_conflicting_restack()
        worktree = Path(started['managed_worktree']['path'])
        z._git_phase_state.abort_attempt_restack(
            worktree, plan, owned_paths=['behavior_test.py'])
        (worktree / 'behavior_test.py').write_text('assert True\n')
        subprocess.run(['git', 'add', 'behavior_test.py'], cwd=worktree, check=True)
        subprocess.run(['git', 'commit', '-qm', 'test: arbitrary clean child'],
                       cwd=worktree, check=True)
        arbitrary = subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=worktree,
            capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(plan['new_base'], subprocess.run(
            ['git', 'rev-parse', arbitrary + '^'], cwd=worktree,
            capture_output=True, text=True, check=True).stdout.strip())
        self.assertNotEqual(0, subprocess.run(
            ['git', 'rev-parse', '--verify', 'CHERRY_PICK_HEAD'], cwd=worktree,
            capture_output=True).returncode)
        template = {**started['restack']['continue'], 'actor': 'restack-worker',
                    'request_id': 'reject-unproven-clean-restack'}
        evidence_before = copy.deepcopy(fixture.payload()[1]['evidence'])

        rejected = fixture.session.call(100, template, expected=2)

        self.assertRegex(json.dumps(rejected), r'(?i)replay|sequencer|restack|proof')
        self.assertEqual(evidence_before, fixture.payload()[1]['evidence'])
        lease = next(item for item in fixture.payload()[1]['operational']['leases']
                     if item['token'] == started['lease']['token'])
        self.assertNotEqual('ready', lease['restack'].get('status'))
        self.assertNotIn('result_commit', lease['restack'])
        self.assertEqual([100], sorted(fixture.provider.issues))

    def test_public_restack_continue_rejects_worker_forged_replay_trailer(self):
        fixture, _first, started, plan, _source_ref, _source_commit = \
            self.public_same_node_conflicting_restack()
        worktree = Path(started['managed_worktree']['path'])
        z._git_phase_state.abort_attempt_restack(
            worktree, plan, owned_paths=['behavior_test.py'])
        template = {**started['restack']['continue'], 'actor': 'restack-worker',
                    'request_id': 'forged-clean-restack-proof'}
        replay_proof = journeys.content_hash({
            'lease': template['lease'], 'actor': template['actor'],
            'attempt': started['lease']['attempt'],
            'plan_hash': template['plan_hash'],
            'authorized_request': template['request_id'],
        })
        trailer = 'ZzzOps-Restack-Proof: ' + replay_proof
        (worktree / 'behavior_test.py').write_text('assert True\n')
        subprocess.run(['git', 'add', 'behavior_test.py'], cwd=worktree, check=True)
        subprocess.run(['git', 'commit', '-qm', 'test: arbitrary forged child',
                        '-m', trailer], cwd=worktree, check=True)
        message = subprocess.run(
            ['git', 'show', '-s', '--format=%B', 'HEAD'], cwd=worktree,
            capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertEqual(1, message.count(trailer))
        self.assertNotEqual(0, subprocess.run(
            ['git', 'rev-parse', '--verify', 'CHERRY_PICK_HEAD'], cwd=worktree,
            capture_output=True).returncode)
        evidence_before = copy.deepcopy(fixture.payload()[1]['evidence'])

        rejected = fixture.session.call(100, template, expected=2)

        self.assertRegex(json.dumps(rejected), r'(?i)replay|sequencer|restack|proof')
        self.assertEqual(evidence_before, fixture.payload()[1]['evidence'])
        lease = next(item for item in fixture.payload()[1]['operational']['leases']
                     if item['token'] == started['lease']['token'])
        self.assertNotEqual('ready', lease['restack'].get('status'))
        self.assertNotIn('result_commit', lease['restack'])
        self.assertEqual([100], sorted(fixture.provider.issues))

    def test_submission_uses_managed_worktree_commit_and_checks(self):
        fixture = self.fixture_with_git_workspace()
        remote_dir = tempfile.TemporaryDirectory()
        self.addCleanup(remote_dir.cleanup)
        bare = Path(remote_dir.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        fixture.session.git('remote', 'add', 'origin', str(bare))
        work = fixture.acquire_workspace('alpha')
        path = Path(work['managed_worktree']['path'])
        (path / 'behavior_test.py').write_text('from source import value\nassert value() == 1\n')
        subprocess.run(['git', 'add', 'behavior_test.py'], cwd=path, check=True)
        subprocess.run(['git', 'commit', '-qm', 'test: implement goal 100 alpha'], cwd=path, check=True)
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=path, capture_output=True,
                              text=True, check=True).stdout.strip()
        request = fixture.session.submission(work, {'value': 'Managed alpha result'}, 'managed-alpha-result')
        request['workspace_checks'] = [[sys.executable, '-B', 'behavior_test.py']]
        request['verification_expectation'] = 'passed'
        fixture.session.call(100, request)
        ref = f"refs/heads/zzzops/attempts/100/alpha/{work['lease']['attempt']}"
        self.assertEqual(head, fixture.session.git('ls-remote', 'origin', ref).split()[0])
        self.assertNotEqual(head, fixture.session.git('rev-parse', 'HEAD').strip())


class GitWorkspaceJourneyTests(unittest.TestCase):
    fixture_with_git_workspace = GitWorkspaceAcquisitionTests.fixture_with_git_workspace

    def test_same_owner_can_renew_stale_implement_lease_after_late_test_review(self):
        case = journeys.DefaultCorrectionPublicTests('runTest')
        case.setUp()
        self.addCleanup(case.doCleanups)
        remote_dir = tempfile.TemporaryDirectory()
        self.addCleanup(remote_dir.cleanup)
        bare = Path(remote_dir.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        case.session.git('remote', 'add', 'origin', str(bare))
        z._workflow_section(
            case.session.project, 'autonomy_approval_parallelism')[
                'configuration']['max_workers'] = 2
        case.default_decomposition()
        case.session.finish(case.session.acquire('decomposition_review'), {
            'value': case.review('approved', 'Atomic disposition accepted'),
            'authorization': case.decomposition_authorization()})
        case.session.finish(case.session.acquire('retain_decomposition_findings'), {
            'value': {'items': {}, 'rationale': 'No decomposition findings'}})

        test_work = case.session.acquire('test_design')
        test_tree = Path(test_work['managed_worktree']['path'])
        (test_tree / 'behavior_test.py').write_text(
            "from pathlib import Path\nassert Path('source.py').is_file()\n")
        subprocess.run(['git', 'add', 'behavior_test.py'], cwd=test_tree, check=True)
        subprocess.run(['git', 'commit', '-qm', 'test: first red'], cwd=test_tree, check=True)
        test_request = case.session.submission(
            test_work, {'value': 'Initial RED contract'}, 'initial-red-contract')
        test_request['workspace_checks'] = [[sys.executable, '-B', 'behavior_test.py']]
        test_request['verification_expectation'] = 'observed'
        case.session.call(100, test_request)
        case.verify_test_design(test_tree / 'behavior_test.py', 'initial-red-proof')
        case.session.finish(case.session.acquire('test_design_review'), {
            'value': case.review('approved', 'Initial RED proof accepted')})
        case.session.finish(case.session.acquire('retain_test_design_findings'), {
            'value': {'items': {}, 'rationale': 'No initial findings'}})

        implementation = case.session.acquire('implement', actor='bound-implementer')
        lease = implementation['lease']
        implementation_tree = Path(implementation['managed_worktree']['path'])
        (implementation_tree / 'unowned-local-note.txt').write_text(
            'This dirty unowned path must not silently transfer custody.\n')

        test_result, test_record = case.result('test_design')
        test_subject = test_record['outputs']['value']
        finding_request = {
            'operation': 'phase_finding', 'request_id': 'late-test-after-implement-start',
            'actor': 'root-thread',
            'target': {'node': 'test_design', 'output': 'value'},
            'subject': test_subject, 'source': test_result,
            'rationale': 'The accepted test misses a behavior regression.',
            'id': 'late-test-defect',
        }
        original_phase_finding = z._workflow.Workflow.node_phase_finding
        class ConcurrentLeases(list):
            def __bool__(self):
                return False
        def record_concurrent_finding(engine, snapshot, payload, request):
            payload['operational']['leases'] = ConcurrentLeases(
                payload['operational']['leases'])
            return original_phase_finding(engine, snapshot, payload, request)
        with (mock.patch.dict('os.environ', {'CODEX_THREAD_ID': 'root-thread'}),
              mock.patch.object(z._workflow.Workflow, 'node_phase_finding', autospec=True,
                                side_effect=record_concurrent_finding)):
            response = case.session.call(100, finding_request)
        review_step = next(
            step for step in response['next_steps']
            if step.get('kind') == 'execute'
            and step.get('node', {}).get('node', '').startswith('sw_review_'))
        review = case.session.acquire(
            review_step['node']['node'], item=review_step['node']['item'],
            actor='late-reviewer', frontier=response)
        case.session.finish(review, {'value': {
            'decision': 'changes_requested',
            'report': 'Add the missing regression assertion.'}})

        renewal = {
            'operation': 'renew', 'node': implementation['node'],
            'lease': lease['token'], 'actor': implementation['bound_actor'],
            'worker_status': 'active', 'request_id': 'renew-stale-implement',
        }
        case.session.call(100, {**renewal, 'request_id': 'wrong-renewal-token',
                               'lease': 'wrong-token'}, expected=2)
        case.session.call(100, {**renewal, 'request_id': 'wrong-renewal-actor',
                               'actor': 'wrong-actor'}, expected=2)

        renewed = case.session.call(100, renewal)['next_steps'][0]

        self.assertEqual('renewed', renewed['kind'])
        self.assertEqual(lease['token'], renewed['lease'])
        self.assertEqual(implementation['bound_actor'], renewed['actor'])
        current_lease = case.payload()[1]['operational']['leases'][0]
        self.assertEqual(lease['token'], current_lease['token'])
        self.assertEqual(implementation['bound_actor'], current_lease['worker'])
        self.assertTrue((implementation_tree / 'unowned-local-note.txt').is_file())

        stale_submission = case.session.submission(
            implementation, {'value': 'Must not submit stale work'},
            'stale-implement-result')
        case.session.call(100, stale_submission, expected=2)
        frontier = case.session.checkpoint(100)
        self.assertNotIn('publish', {
            step.get('node', {}).get('node') for step in frontier
            if step.get('kind') in {'execute', 'perform'}})

    def acceptance_late_test_finding_rebases_t2_on_i1_then_i2_on_t2(self):
        """Opt-in full shipped-DAG journey; focused CI contracts cover each boundary."""
        case = journeys.DefaultCorrectionPublicTests('runTest')
        case.setUp()
        self.addCleanup(case.doCleanups)
        remote_dir = tempfile.TemporaryDirectory()
        self.addCleanup(remote_dir.cleanup)
        bare = Path(remote_dir.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        case.session.git('remote', 'add', 'origin', str(bare))
        case.default_decomposition(implementation_review_members={
            'items': {'acceptance_contracts': 'Review the exact corrected behavior'},
            'rationale': 'Independent implementation review is required'})
        case.session.finish(case.session.acquire('decomposition_review'), {
            'value': case.review('approved', 'Atomic disposition accepted'),
            'authorization': case.decomposition_authorization()})
        case.session.finish(case.session.acquire('retain_decomposition_findings'), {
            'value': {'items': {}, 'rationale': 'No decomposition findings'}})

        def commit(work, path, content, message, expectation):
            tree = Path(work['managed_worktree']['path'])
            (tree / path).write_text(content)
            subprocess.run(['git', 'add', path], cwd=tree, check=True)
            subprocess.run(['git', 'commit', '-qm', message], cwd=tree, check=True)
            head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=tree,
                                  capture_output=True, text=True, check=True).stdout.strip()
            request = case.session.submission(work, {'value': message}, message)
            request['workspace_checks'] = [[sys.executable, '-B', 'behavior_test.py']]
            request['verification_expectation'] = expectation
            case.session.call(100, request)
            return head

        t1 = case.session.acquire('test_design')
        base = t1['lease']['acquisition']['git_commit']
        t1_head = commit(t1, 'behavior_test.py',
                         "from pathlib import Path\nassert Path('source.py').is_file()\n",
                         'test: first red', 'observed')
        case.verify_test_design(Path(t1['managed_worktree']['path']) / 'behavior_test.py', 't1-proof')
        case.session.finish(case.session.acquire('test_design_review'), {
            'value': case.review('approved', 'Exact RED proof accepted')})
        case.session.finish(case.session.acquire('retain_test_design_findings'), {
            'value': {'items': {}, 'rationale': 'No initial findings'}})
        i1 = case.session.acquire('implement')
        self.assertEqual(t1_head, i1['lease']['acquisition']['git_commit'])
        i1_head = commit(i1, 'source.py', 'def value():\n    return 1\n',
                         'feat: first green', 'passed')
        i1_result = case.result('implement')[0]

        t1_result, t1_record = case.result('test_design')
        t1_subject = t1_record['outputs']['value']
        finding_request = {'operation': 'phase_finding', 'request_id': 'late-test-after-i1',
                           'actor': 'root-thread', 'target': {'node': 'test_design', 'output': 'value'},
                           'subject': t1_subject, 'source': t1_result,
                           'rationale': 'The accepted test misses a behavior regression after I1.',
                           'id': 'late-test-defect'}
        with mock.patch.dict('os.environ', {'CODEX_THREAD_ID': 'root-thread'}):
            response = case.session.call(100, finding_request)
        review_step = next(step for step in response['next_steps'] if step.get('kind') == 'execute'
                           and step.get('node', {}).get('node', '').startswith('sw_review_'))
        review_name = review_step['node']['node']
        item = review_step['node']['item']
        case.session.finish(case.session.acquire(review_name, item=item, actor='late-reviewer'), {
            'value': {'decision': 'changes_requested', 'report': 'Add an assertion on value().'}})

        def acquire_prefix(prefix):
            step = next(step for step in case.session.ready()
                        if step['node']['node'].startswith(prefix) and step['node'].get('item') == item)
            return case.session.acquire(step['node']['node'], item=item, actor='root-thread')

        interpret = acquire_prefix('gc_interpret_')
        case.session.finish(interpret, {'value': {
            'id': 'late-test-defect', 'revision': 1,
            'source': case.produced(review_name, item=item), 'subjects': [t1_subject],
            'target': {'subject': {'kind': 'node', 'goal': 100, 'node': 'test_design'},
                       'output': 'value'},
            'request': 'Assert the corrected behavior', 'rationale': 'Independent late review',
            'supersedes': None}})
        finding = case.produced(interpret['node']['node'], item=item)
        admit = acquire_prefix('gc_admit_')
        case.session.finish(admit, {'value': {
            'finding': finding, 'target_inputs': t1_record['inputs'],
            'authority': case.result(interpret['node']['node'], item)[0],
            'applicability': 'applicable', 'rationale': 'Same reviewed test allocation'},
            'transfer': None})
        t2 = case.session.acquire('test_design')
        self.assertEqual(i1_head, t2['lease']['acquisition']['git_commit'])
        t2_head = commit(t2, 'behavior_test.py',
                         'from source import value\nassert value() == 2\n',
                         'test: corrected red', 'observed')
        t2_proof_ref = case.read_blob(case.produced('test_design'))['provenance']['source']
        self.assertEqual(1, case.read_blob(t2_proof_ref)['commands'][0]['exit_code'])
        fresh = case.session.acquire(review_name, item=item, actor='fresh-reviewer')
        case.session.finish(fresh, {'value': {
            'decision': 'approved', 'report': 'Current corrected test resolves the finding.'}})
        case.verify_test_design(Path(t2['managed_worktree']['path']) / 'behavior_test.py', 't2-proof')
        case.session.finish(case.session.acquire('test_design_review'), {
            'value': case.review('approved', 'Current corrected RED proof accepted')})
        case.session.finish(case.session.acquire('retain_test_design_findings'), {
            'value': {'items': {'late-test-defect': finding},
                      'rationale': 'Retain the exact admitted late test finding'}})
        resolve = acquire_prefix('gc_resolve_')
        case.session.finish(resolve, {'value': {
            'finding': finding, 'subjects': [case.produced('test_design')],
            'reviewer_result': case.result(review_name, item)[0],
            'decision': 'resolved', 'rationale': 'Independent late review accepted T2'}})
        case.session.finish(case.session.acquire('resolve_test_design_finding', item='late-test-defect'), {
            'value': {'finding': finding, 'subjects': [case.produced('test_design')],
                      'reviewer_result': case.result('test_design_review')[0],
                      'decision': 'resolved', 'rationale': 'Fresh independent test review accepted T2'}})
        i2 = case.session.acquire('implement')
        self.assertEqual(t2_head, i2['lease']['acquisition']['git_commit'])
        i2_head = commit(i2, 'source.py', 'def value():\n    return 2\n',
                         'feat: corrected green', 'passed')
        self.assertEqual(4, len({t1_head, i1_head, t2_head, i2_head}))
        self.assertEqual([100], sorted(case.provider.issues))
        case.read_blob(t1_result)
        case.read_blob(i1_result)
        for work, head in ((t1, t1_head), (i1, i1_head), (t2, t2_head), (i2, i2_head)):
            ref = f"refs/heads/zzzops/attempts/100/{work['node']['node']}/{work['lease']['attempt']}"
            self.assertEqual(head, case.session.git('ls-remote', 'origin', ref).split()[0])
        self.assertEqual(base, z._git_phase_state.compaction_base_from_attempts(
            case.fixture.repo, goal=100, test_source=t2_head,
            attempts=[{'ref': f"refs/heads/zzzops/attempts/100/test_design/{w['lease']['attempt']}",
                       'commit': h} for w, h in ((t1, t1_head), (t2, t2_head))], remote='origin'))
        case.session.finish(case.session.acquire('implementation_verification'), {
            'value': 'Observed GREEN check against the exact I2 commit'})
        case.session.finish(case.session.acquire('select_delivery_candidate'), {'value': {
            'delivery_class': 'atomic', 'candidate': case.produced('implement'),
            'integration_applicability': 'not_applicable',
            'rationale': 'Select the reviewed corrected implementation'}})
        case.session.finish(case.session.acquire('migration_verification'), {'value': {
            'applicability': 'not_applicable', 'transition': 'none',
            'compatibility': 'No released compatibility obligation',
            'recovery': 'none', 'rationale': 'This fixture changes no released schema'}})
        case.session.finish(case.session.acquire('migration_review'), {
            'value': case.review('approved', 'Migration non-applicability confirmed')})
        if 'retain_migration_findings' in case.names():
            case.session.finish(case.session.acquire('retain_migration_findings'), {
                'value': {'items': {}, 'rationale': 'No migration findings'}})
        case.session.finish(case.session.acquire('implementation_review', item='acceptance_contracts',
                                                 actor='independent-implementation-reviewer'), {
            'value': case.review('approved', 'I2 passes the corrected T2 behavior contract')})
        for registry in ('retain_implementation_review_findings',
                         'retain_integration_review_findings'):
            if registry in case.names():
                case.session.finish(case.session.acquire(registry), {
                    'value': {'items': {}, 'rationale': 'No admitted findings in this review'}})
        authorization = {'manifest': case.produced('select_delivery_candidate'),
                         'tasks': [{'goal': 100, 'node': 'publish', 'item': None, 'generation': 1}],
                         'policy': journeys.content_hash(case.session.project['policy']),
                         'decision': 'approved'}
        response = case.session.finish(case.session.acquire('authorize_repository'), {
            'authorization': authorization})
        compaction = next(step for step in response['next_steps']
                          if step.get('kind') == 'compact_candidate')
        compacted = case.session.call(100, compaction['submission'])['next_steps'][0]
        self.assertEqual('candidate_compacted', compacted['kind'])
        self.assertEqual(2, len(compacted['group_commits']))
        self.assertEqual(i2_head, case.session.git('ls-remote', 'origin',
            f"refs/heads/zzzops/attempts/100/implement/{i2['lease']['attempt']}").split()[0])
        self.assertEqual([100], sorted(case.provider.issues))
        frontier = case.session.checkpoint(100)
        self.assertEqual({'publish'}, {step['node']['node'] for step in frontier
            if step.get('kind') == 'execute'}, frontier)

    def test_correction_attempts_compact_to_two_final_commits(self):
        case = journeys.DefaultCorrectionPublicTests('runTest')
        case.setUp()
        self.addCleanup(case.doCleanups)
        original_install = case.install
        def install_git_graph(graph):
            for node in graph['nodes']:
                if node['id'] in {'test_design', 'implement'}:
                    resources = node['executor']['resources']
                    if 'repository_workspace' in resources:
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
        first_tree = Path(first['managed_worktree']['path'])
        path = first_tree / 'behavior_test.py'
        path.write_text("raise AssertionError('unconditional red')\n")
        subprocess.run(['git', 'add', path.name], cwd=first_tree, check=True)
        subprocess.run(['git', 'commit', '-qm', 'test: first red attempt'], cwd=first_tree, check=True)
        rejected_commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=first_tree,
                                         capture_output=True, text=True, check=True).stdout.strip()
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
        corrected_tree = Path(corrected['managed_worktree']['path'])
        corrected_path = corrected_tree / 'behavior_test.py'
        corrected_path.write_text("from pathlib import Path\nassert Path('product.txt').is_file()\n")
        subprocess.run(['git', 'add', corrected_path.name], cwd=corrected_tree, check=True)
        subprocess.run(['git', 'commit', '-qm', 'test: correct red attempt'], cwd=corrected_tree, check=True)
        corrected_commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=corrected_tree,
                                          capture_output=True, text=True, check=True).stdout.strip()
        request = case.session.submission(corrected, {'value': 'Meaningful RED probe'}, 'git-correction-second')
        request['workspace_checks'] = [[sys.executable, str(corrected_path)]]
        case.session.call(100, request)
        case.verify_test_design(corrected_path, 'git-correction-green-verification')
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
        original_base = first['lease']['acquisition']['git_commit']
        self.assertIn('implement', case.names())
        implementation = case.session.acquire('implement')
        self.assertEqual(corrected_commit, implementation['lease']['acquisition']['git_commit'])
        implementation_tree = Path(implementation['managed_worktree']['path'])
        (implementation_tree / 'source.py').write_text('def value():\n    return 2\n')
        subprocess.run(['git', 'add', 'source.py'], cwd=implementation_tree, check=True)
        subprocess.run(['git', 'commit', '-qm', 'feat: final GREEN implementation'],
                       cwd=implementation_tree, check=True)
        implementation_commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=implementation_tree,
                                               capture_output=True, text=True, check=True).stdout.strip()
        request = case.session.submission(implementation, {'value': 'GREEN implementation'}, 'git-two-commit-final')
        request['workspace_checks'] = [[sys.executable, str(corrected_path)]]
        request['verification_expectation'] = 'passed'
        case.session.call(100, request)
        retained = [{'ref': f"refs/heads/zzzops/attempts/100/{work['node']['node']}/{work['lease']['attempt']}",
                     'commit': commit} for work, commit in
                    ((first, rejected_commit), (corrected, corrected_commit),
                     (implementation, implementation_commit))]
        self.assertEqual(original_base, z._git_phase_state.compaction_base_from_attempts(
            case.fixture.repo, goal=100, test_source=corrected_commit,
            attempts=retained[:2], remote='origin'))
        candidate_dir = tempfile.TemporaryDirectory()
        self.addCleanup(candidate_dir.cleanup)
        candidate = Path(candidate_dir.name) / 'candidate'
        case.session.git('worktree', 'add', '-q', '-b', 'candidate-566', str(candidate), implementation_commit)
        preview = z._git_phase_state.preview_two_commit_candidate(candidate, goal=100,
            base_commit=original_base, test_source=corrected_commit,
            implementation_source=implementation_commit, test_owned=['behavior_test.py'],
            implementation_owned=['source.py'], retained_attempts=retained, remote='origin')
        compacted = z._git_phase_state.apply_two_commit_candidate(candidate, preview,
            test_owned=['behavior_test.py'], implementation_owned=['source.py'],
            retained_attempts=retained, remote='origin')
        self.assertEqual('2', subprocess.run(['git', 'rev-list', '--count',
                         f"{original_base}..{compacted['implementation_commit']}"], cwd=candidate,
                         capture_output=True, text=True, check=True).stdout.strip())
        self.assertNotEqual(rejected_commit, corrected_commit)
        for work, commit in ((first, rejected_commit), (corrected, corrected_commit)):
            ref = f"refs/heads/zzzops/attempts/100/test_design/{work['lease']['attempt']}"
            self.assertEqual(commit, case.session.git('ls-remote', 'origin', ref).split()[0])
        self.assertNotEqual(first['lease']['attempt'], corrected['lease']['attempt'])
        authorization = {'hash': 'sha256:' + 'e' * 64,
                         'uri': 'urn:sha256:' + 'e' * 64}
        with mock.patch.object(z._workflow.Workflow, 'node_compaction_authorization',
                               return_value=authorization):
            response = case.session.call(100, {
                'operation': 'compact_candidate', 'request_id': 'declared-correction-compaction',
                'authorization': authorization})
        step = response['next_steps'][0]
        self.assertEqual('candidate_compacted', step['kind'])
        self.assertEqual(2, len(step['group_commits']))
        self.assertEqual(self.session_tree(candidate, compacted['implementation_commit']),
                         self.session_tree(case.fixture.repo, step['head_oid']))
        self.assertEqual([100], sorted(case.provider.issues))

    @staticmethod
    def session_tree(repo, commit):
        return subprocess.run(['git', 'rev-parse', commit + '^{tree}'], cwd=repo,
                              capture_output=True, text=True, check=True).stdout.strip()

    def test_clean_git_workspace_acquisition_does_not_hash_every_file(self):
        fixture = self.fixture_with_git_workspace(many_files=2200)
        with (mock.patch.object(z._workflow.Workflow, 'workspace_files',
                                side_effect=AssertionError('repository file scan')),
              mock.patch.object(z._workflow.Workflow, 'git_files',
                                side_effect=AssertionError('Git blob scan'))):
            work = fixture.acquire_workspace('alpha')
        self.assertIn('git_commit', work['lease']['acquisition'])

    def test_unowned_commit_cannot_be_submitted_under_git_workspace_lease(self):
        fixture = self.fixture_with_git_workspace()
        work = fixture.acquire_workspace('alpha')
        worktree = Path(work['managed_worktree']['path'])
        (worktree / 'unowned.txt').write_text('outside allocation\n')
        subprocess.run(['git', 'add', 'unowned.txt'], cwd=worktree, check=True)
        subprocess.run(['git', 'commit', '-qm', 'unowned change'], cwd=worktree, check=True)
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
        worktree = Path(work['managed_worktree']['path'])
        (worktree / 'behavior_test.py').write_text('from source import value\nassert value() == 1\n')
        subprocess.run(['git', 'add', 'behavior_test.py'], cwd=worktree, check=True)
        subprocess.run(['git', 'commit', '-qm', 'test: implement goal 100 alpha'], cwd=worktree, check=True)
        result_commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=worktree,
                                       capture_output=True, text=True, check=True).stdout.strip()
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

    def test_retry_after_git_retention_before_provider_result_adopts_exact_commit(self):
        fixture = self.fixture_with_git_workspace()
        remote_dir = tempfile.TemporaryDirectory()
        self.addCleanup(remote_dir.cleanup)
        bare = Path(remote_dir.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        fixture.session.git('remote', 'add', 'origin', str(bare))
        work = fixture.acquire_workspace('alpha')
        path = Path(work['managed_worktree']['path'])
        (path / 'behavior_test.py').write_text('assert True\n')
        subprocess.run(['git', 'add', 'behavior_test.py'], cwd=path, check=True)
        subprocess.run(['git', 'commit', '-qm', 'test: crash boundary result'],
                       cwd=path, check=True)
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=path,
                              capture_output=True, text=True, check=True).stdout.strip()
        request = fixture.session.submission(
            work, {'value': 'Result surviving provider interruption'},
            'git-retained-provider-interrupted')
        request['workspace_checks'] = [[sys.executable, '-B', 'behavior_test.py']]
        request['verification_expectation'] = 'passed'

        with mock.patch.object(fixture.provider, 'create_issue_comment',
                               side_effect=z.GoalTransitionProviderError(
                                   'Provider unavailable after Git retention')):
            fixture.session.call(100, request, expected=None)

        ref = f"refs/heads/zzzops/attempts/100/alpha/{work['lease']['attempt']}"
        self.assertEqual(head, fixture.session.git('ls-remote', 'origin', ref).split()[0])
        before_retry_comments = len(fixture.provider.comments[100])
        first = fixture.session.call(100, request)
        comments = len(fixture.provider.comments[100])
        second = fixture.session.call(100, request)
        self.assertEqual(first, second)
        self.assertEqual(comments, len(fixture.provider.comments[100]))
        self.assertGreater(comments, before_retry_comments)
        output = fixture.read_blob(fixture.produced('alpha'))
        proof = fixture.read_blob(output['provenance']['source'])
        self.assertEqual(head, proof['checkpoint']['result_commit'])

    def test_red_test_commit_then_green_implementation_commit(self):
        fixture = self.fixture_with_git_workspace()
        remote_dir = tempfile.TemporaryDirectory()
        self.addCleanup(remote_dir.cleanup)
        bare = Path(remote_dir.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        fixture.session.git('remote', 'add', 'origin', str(bare))
        alpha = fixture.acquire_workspace('alpha')
        alpha_tree = Path(alpha['managed_worktree']['path'])
        (alpha_tree / 'behavior_test.py').write_text('from source import value\nassert value() == 2\n')
        subprocess.run(['git', 'add', 'behavior_test.py'], cwd=alpha_tree, check=True)
        subprocess.run(['git', 'commit', '-qm', 'test: capture required behavior'], cwd=alpha_tree, check=True)
        test_commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=alpha_tree,
                                     capture_output=True, text=True, check=True).stdout.strip()
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
        beta_tree = Path(beta['managed_worktree']['path'])
        (beta_tree / 'source.py').write_text('def value():\n    return 2\n')
        subprocess.run(['git', 'add', 'source.py'], cwd=beta_tree, check=True)
        subprocess.run(['git', 'commit', '-qm', 'feat: satisfy reviewed test'], cwd=beta_tree, check=True)
        implementation_commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=beta_tree,
                                               capture_output=True, text=True, check=True).stdout.strip()
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
