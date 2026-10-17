"""Provider discovery can be reused; host authorization is always rechecked."""
import copy
import unittest
from unittest import mock

import test_publication_cache_scan as cache_tests
from test_evidence_dag_journeys import z


class BranchProjectionMemoTests(unittest.TestCase):
    def setUp(self):
        self.fixture = cache_tests.PublicationCacheScanTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.engine = z._workflow.Workflow.__new__(z._workflow.Workflow)
        engine = self.engine
        from pathlib import Path
        engine.repo = Path('/unused-projection-test')
        engine.repository = 'owner/repo'
        engine.api = z
        engine.runtime = {'root_id': 'root'}
        engine.project = {'policy': {'schema_version': 2, 'sections': []}}
        engine.portfolio = lambda: self.fixture.goals
        self.batch_calls = []
        self.reads = []
        calls = self.batch_calls
        class Adapter:
            def get_issue_comment_tails(self, numbers):
                calls.append(numbers[:])
                return {n: [] for n in numbers}
        engine.adapter = Adapter()
        self.projection = self.make_candidate(1, 'managed')
        engine.node_snapshot = mock.Mock(side_effect=lambda *_a, **_k: self.projection)
        def read(number, ref):
            self.reads.append(number)
            return self.fixture.blobs[ref['hash']]
        engine.read_artifact = read
        self.observed = [{'number': 10, 'url': 'https://github.com/owner/repo/pull/10',
                          'headRefName': 'managed', 'baseRefName': 'dev', 'headRefOid': 'a' * 40}]

    def make_candidate(self, number, branch):
        f = self.fixture
        context = {'type': 'repository_context', 'content': {'branch': branch}}
        context_ref = f.ref(context)
        authorization = {'type': 'repository_authorization', 'content': {
            'decision': 'approved', 'context': context_ref,
            'policy': self.engine.node_evidence_policy()}}
        auth_ref = f.ref(authorization)
        context_result = {'executor': 'root', 'outputs': {'value': context_ref}, 'inputs': []}
        auth_result = {'executor': 'root', 'outputs': {'value': auth_ref},
                       'inputs': [{'source': context_ref, 'mode': 'identity', 'path': []}]}
        graph_ref = f.ref({'nodes': [{'id': 'context', 'outputs': {'value': {'type': 'repository_context'}}}],
                          'task_sets': []})
        payload = f.ref({'graph': graph_ref, 'evidence': [f.ref({'type': 'result', 'content': {
            'node': {'node': 'context'}, 'outputs': {'value': context_ref}}})]})
        import json
        f.bodies[number] = '<!-- zzzops-goal\n' + json.dumps({'schema_version': 2,
            'repository': 'owner/repo', 'issue': number, 'revision': 1, 'state': 'open',
            'parent': None, 'payload': payload}) + '\nzzzops-goal -->'
        return {'projection': {'current': {'context': ({}, context_result), 'auth': ({}, auth_result)},
                              'states': {key: {'contract': {'executor': {'role': 'root'}}}
                                         for key in ('context', 'auth')}},
                'artifacts': {context_ref['hash']: context, auth_ref['hash']: authorization}}

    def scan(self):
        with mock.patch.object(z, 'provider_issue_snapshot', side_effect=lambda repo, repository, n:
                               {'body': self.fixture.bodies[n]}) as observe:
            result = self.engine.node_managed_publication_branches(self.observed)
            self.assertEqual(94, observe.call_count, 'fresh broadphase identities remain observed')
            return result

    def test_94_goal_scan_reuses_success_only_until_invalidation(self):
        self.assertEqual({'managed'}, self.scan())
        self.assertEqual(24, len(self.batch_calls))
        self.assertEqual(set(range(1, 95)), set(self.reads))
        result = self.scan()
        self.assertEqual({'managed'}, result)
        self.assertEqual(24, len(self.batch_calls), 'unchanged repeat must not launch another 24 batches')
        result.clear()
        self.assertEqual({'managed'}, self.scan(), 'returned set cannot corrupt the memo')
        self.engine.invalidate()
        self.assertEqual({'managed'}, self.scan())
        self.assertEqual(48, len(self.batch_calls))

    def test_host_currentness_rechecked_after_positive_provider_discovery(self):
        self.assertEqual({'managed'}, self.scan())
        saved = self.projection['projection']['current']
        self.projection['projection']['current'] = {}
        self.assertEqual(set(), self.scan(), 'unchanged provider bytes cannot preserve stale host authority')
        self.projection['projection']['current'] = saved
        self.assertEqual({'managed'}, self.scan())
        self.assertEqual(24, len(self.batch_calls))
        self.assertEqual(3, self.engine.node_snapshot.call_count)

    def test_previously_noncurrent_candidate_reauthenticated_without_provider_rescan(self):
        saved = self.projection['projection']['current']
        self.projection['projection']['current'] = {}
        self.assertEqual(set(), self.scan())
        self.projection['projection']['current'] = saved
        self.assertEqual({'managed'}, self.scan())
        self.assertEqual(24, len(self.batch_calls), 'negative host result still retains provider discovery')
        self.assertEqual(2, self.engine.node_snapshot.call_count)

    def test_fresh_topology_body_status_root_and_policy_change_force_new_scan(self):
        changes = [lambda: self.observed[0].update(headRefOid='b' * 40),
                   lambda: self.observed[0].update(baseRefName='other'),
                   lambda: self.fixture.bodies.update({1: self.fixture.bodies[1] + ' ' }),
                   lambda: self.fixture.goals[0].update(status='blocked'),
                   lambda: self.engine.runtime.update(root_id='other-root'),
                   lambda: self.engine.project['policy'].update(schema_version=3)]
        for change in changes:
            self.scan()
            before = len(self.batch_calls)
            change()
            self.scan()
            self.assertEqual(before + 24, len(self.batch_calls))

    def test_empty_and_partial_failed_projection_never_become_cached_success(self):
        self.engine.runtime['root_id'] = 'not-the-authenticated-root'
        self.assertEqual(set(), self.scan())
        self.assertEqual(set(), self.scan())
        self.assertEqual(24, len(self.batch_calls))
        self.assertEqual(2, self.engine.node_snapshot.call_count)
        self.engine.runtime['root_id'] = 'root'
        self.assertEqual({'managed'}, self.scan())
        self.fixture.bodies[2] += ' '
        original = self.engine.read_artifact
        self.engine.read_artifact = lambda number, ref: (_ for _ in ()).throw(
            ValueError('required evidence unavailable')) if number == 2 else original(number, ref)
        with self.assertRaisesRegex(ValueError, 'required evidence unavailable'): self.scan()
        self.assertIsNone(self.engine._publication_candidate_discovery)
        self.engine.read_artifact = original
        before = len(self.batch_calls)
        self.assertEqual({'managed'}, self.scan())
        self.assertEqual(before + 24, len(self.batch_calls))

    def test_all_94_potential_candidates_reauthenticate_including_previous_negatives(self):
        projections = {n: self.make_candidate(n, 'managed' if n == 1 else 'potential')
                       for n in range(1, 95)}
        original_current = {n: value['projection']['current'] for n, value in projections.items()}
        for n in range(2, 95): projections[n]['projection']['current'] = {}
        self.observed.append(dict(self.observed[0], number=11, headRefName='potential'))
        self.engine.node_snapshot.side_effect = lambda number, **kwargs: projections[number]
        self.assertEqual({'managed'}, self.scan())
        projections[1]['projection']['current'] = {}
        projections[94]['projection']['current'] = original_current[94]
        self.assertEqual({'potential'}, self.scan())
        self.assertEqual(24, len(self.batch_calls))
        calls = self.engine.node_snapshot.call_args_list
        self.assertEqual(188, len(calls), 'every potential candidate must reauthenticate on reuse')
        self.assertEqual(list(range(1, 95)) * 2, [call.args[0] for call in calls])
        self.assertTrue(all(call.kwargs == {'publication_probe': True} for call in calls))

    def test_runtime_and_relationship_currentness_are_not_memoized(self):
        projection = self.projection
        self.engine.node_snapshot.side_effect = lambda *_a, **_k: (
            {'projection': {'current': {}, 'states': {}}, 'artifacts': {}}
            if self.engine.runtime.get('host_unavailable') else projection)
        self.assertEqual({'managed'}, self.scan())
        self.engine.runtime['host_unavailable'] = True
        self.assertEqual(set(), self.scan())
        self.engine.runtime['host_unavailable'] = False
        projection['projection']['states']['auth']['contract']['executor']['role'] = 'worker'
        self.assertEqual(set(), self.scan())
        projection['projection']['states']['auth']['contract']['executor']['role'] = 'root'
        self.assertEqual({'managed'}, self.scan())
        self.assertEqual(24, len(self.batch_calls))
        self.assertEqual(4, self.engine.node_snapshot.call_count)

    def test_host_authentication_exception_discards_provider_discovery_memo(self):
        self.scan()
        self.engine.node_snapshot.side_effect = ValueError('workspace relationship unavailable')
        with self.assertRaisesRegex(ValueError, 'workspace relationship unavailable'): self.scan()
        self.assertIsNone(self.engine._publication_candidate_discovery)
        self.engine.node_snapshot.side_effect = lambda *_a, **_k: self.projection
        self.assertEqual({'managed'}, self.scan())
        self.assertEqual(48, len(self.batch_calls))

    def test_failed_batch_provider_discovery_is_not_reused_after_fallback(self):
        self.engine.adapter.get_issue_comment_tails = mock.Mock(
            side_effect=z.GoalHistoryReadError('batch unavailable; normal history fallback required'))
        self.assertEqual({'managed'}, self.scan())
        self.assertIsNone(self.engine._publication_candidate_discovery)
        self.assertEqual({'managed'}, self.scan())
        self.assertEqual(48, self.engine.adapter.get_issue_comment_tails.call_count)
        self.assertIsNone(self.engine._publication_candidate_discovery)

    def test_read_epoch_reset_drops_projection_and_tail_window(self):
        self.scan()
        self.engine._publication_tails = {(1, 'old-hash'): ['unused']}
        self.engine.clear_publication_projection()
        self.assertIsNone(self.engine._publication_candidate_discovery)
        self.assertEqual({}, self.engine._publication_tails)
        self.scan()
        self.assertEqual(48, len(self.batch_calls))


class GuardedMutationProjectionResetTests(unittest.TestCase):
    def run_mutation(self, fail_write=False, fail_boundary=False):
        import test_public_cli_github_checks as public_tests
        fixture = public_tests.PublicCliGithubCheckTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.publish_checkpoint()
        work = fixture.session.acquire('produce')
        payload = fixture.session.submission(work, {'value': 'projection-reset candidate'},
                                             'projection-reset-submit')
        engines, resets, writes = [], [], []
        cls = z._workflow.Workflow
        original_init, original_clear = cls.__init__, cls.clear_publication_projection
        def initialize(engine, *args, **kwargs):
            original_init(engine, *args, **kwargs)
            engine._publication_candidate_discovery = ('seed', frozenset({'stale'}))
            engines.append(engine)
        def clear(engine):
            resets.append(engine)
            original_clear(engine)
            if fail_boundary and getattr(engine, '_storage_reservation', {}).get('valid'):
                engine._storage_reservation['valid'] = False
        original_write = fixture.provider.create_issue_comment
        def write(*args, **kwargs):
            engine = engines[-1]
            self.assertIsNone(engine._publication_candidate_discovery,
                              'memo must be gone before fresh boundary/provider write')
            self.assertEqual({}, getattr(engine, '_publication_tails', {}))
            writes.append(engine)
            engine._publication_candidate_discovery = ('during-write', frozenset({'residue'}))
            if fail_write:
                raise z.GoalTransitionProviderError('provider write unconfirmed')
            return original_write(*args, **kwargs)
        with mock.patch.object(cls, '__init__', initialize), mock.patch.object(
                cls, 'clear_publication_projection', clear), mock.patch.object(
                fixture.provider, 'create_issue_comment', side_effect=write):
            if fail_write or fail_boundary:
                with self.assertRaises((ValueError, z.GoalTransitionProviderError)):
                    fixture.direct_public_mutation(payload, public_tests.Ledger())
            else:
                response = fixture.direct_public_mutation(payload, public_tests.Ledger())
                self.assertEqual('produce', response['submitted']['node']['node'])
        self.assertTrue(resets)
        self.assertIsNone(engines[-1]._publication_candidate_discovery)
        if fail_boundary:
            self.assertFalse(writes)
        else:
            self.assertTrue(writes)
            self.assertGreaterEqual(len(resets), 2, 'entry and finally both clear the epoch')

    def test_successful_provider_writes_clear_projection_immediately(self):
        self.run_mutation()

    def test_unconfirmed_provider_write_clears_projection_in_finally(self):
        self.run_mutation(fail_write=True)

    def test_failed_authority_boundary_clears_projection_without_provider_write(self):
        self.run_mutation(fail_boundary=True)


if __name__ == '__main__':
    unittest.main()
