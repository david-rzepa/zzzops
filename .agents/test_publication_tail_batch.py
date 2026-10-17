"""Bounded publication tail reads preserve identity and serial hydration."""
import copy
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from test_evidence_dag_journeys import z
import test_publication_cache_scan as cache_tests


class TailBatchTests(unittest.TestCase):
    def adapter(self):
        adapter = z.GitHubGoalTransitionAdapter.__new__(z.GitHubGoalTransitionAdapter)
        adapter.repository = 'owner/repo'
        adapter.repo = Path('/unused')
        adapter._identity_checked = True
        adapter.comment_read_counters = {}
        adapter.ensure_identity = mock.Mock()
        return adapter

    def response(self, numbers):
        return {'data': {'repository': {'nameWithOwner': 'owner/repo', **{
            'goal_' + str(n): {'number': n, 'comments': {'nodes': [{
                'databaseId': n, 'body': 'body-' + str(n),
                'createdAt': '2026-10-13T00:00:00Z', 'updatedAt': '2026-10-13T00:00:00Z'}]}}
            for n in numbers}}}}

    def test_94_goals_require_24_transport_calls_with_exact_rows_and_bytes(self):
        adapter = self.adapter()
        total = 0
        def transport(args, **kwargs):
            nonlocal total
            self.assertIsNone(kwargs['timeout'])
            query = next(arg[6:] for arg in args if arg.startswith('query='))
            self.assertEqual(query.count('{'), query.count('}'))
            import re
            numbers = [int(n) for n in re.findall(r'goal_(\d+):', query)]
            self.assertLessEqual(len(numbers), 4)
            raw = json.dumps(self.response(numbers))
            total += len(raw.encode())
            return subprocess.CompletedProcess(args, 0, raw, '')
        adapter._run = mock.Mock(side_effect=transport)
        observed = {}
        for offset in range(1, 95, 4):
            observed.update(adapter.get_issue_comment_tails(list(range(offset, min(offset + 4, 95)))))
        self.assertEqual(24, adapter._run.call_count)
        self.assertEqual(set(range(1, 95)), set(observed))
        for n, rows in observed.items():
            self.assertEqual([{'id': n, 'body': 'body-' + str(n),
                              'created_at': '2026-10-13T00:00:00Z', 'updated_at': '2026-10-13T00:00:00Z'}], rows)
            self.assertEqual({'tail': 1}, adapter.comment_read_counters[n]['modes'])
        self.assertEqual(total, sum(row['bytes'] for row in adapter.comment_read_counters.values()))

    def test_entire_batch_validated_before_any_observation_is_exposed(self):
        original = self.response([1, 2])
        def change_alias(value): value['data']['repository'].pop('goal_2')
        def wrong_goal(value): value['data']['repository']['goal_2']['number'] = 1
        def wrong_repo(value): value['data']['repository']['nameWithOwner'] = 'other/repo'
        def null_issue(value): value['data']['repository']['goal_2'] = None
        def errors(value): value['errors'] = [{'message': 'denied'}]
        def extra_alias(value): value['data']['repository']['goal_3'] = {}
        controls = [change_alias, wrong_goal, wrong_repo, null_issue, errors, extra_alias]
        for field, replacement in [('databaseId', True), ('databaseId', -1), ('body', None),
                                   ('createdAt', None), ('updatedAt', 'not-a-timestamp'),
                                   ('updatedAt', '2026-02-30T00:00:00Z')]:
            controls.append(lambda value, f=field, r=replacement:
                            value['data']['repository']['goal_2']['comments']['nodes'][0].update({f: r}))
        for ids in ([2, 2], [3, 2], list(range(1, 102))):
            controls.append(lambda value, ids=ids: value['data']['repository']['goal_2']['comments'].update(
                nodes=[dict(original['data']['repository']['goal_2']['comments']['nodes'][0], databaseId=n)
                       for n in ids]))
        for mutate in controls:
            adapter = self.adapter()
            value = copy.deepcopy(original)
            mutate(value)
            adapter._run = mock.Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(value), ''))
            with self.subTest(control=mutate), self.assertRaises(z.GoalHistoryReadError):
                adapter.get_issue_comment_tails([1, 2])
            self.assertEqual({}, adapter.comment_read_counters, 'valid first alias must not leak')
            self.assertEqual(1, adapter._run.call_count, 'no implicit retry')
        for code, raw in [(0, '{broken'), (0, '[]'), (1, '{}')]:
            adapter = self.adapter()
            adapter._run = mock.Mock(return_value=subprocess.CompletedProcess([], code, raw, 'provider denied'))
            with self.assertRaises(z.GoalHistoryReadError): adapter.get_issue_comment_tails([1, 2])
            self.assertEqual({}, adapter.comment_read_counters)

    def test_alias_wire_order_does_not_change_binding_and_empty_tail_is_explicit(self):
        adapter = self.adapter()
        value = self.response([2, 1])
        value['data']['repository']['goal_2']['comments']['nodes'] = []
        adapter._run = mock.Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(value), ''))
        rows = adapter.get_issue_comment_tails([1, 2])
        self.assertEqual('body-1', rows[1][0]['body'])
        self.assertEqual([], rows[2])

    def test_hundred_rows_match_existing_single_tail_normalization(self):
        adapter = self.adapter()
        value = self.response([1])
        issue = value['data']['repository']['goal_1']
        prototype = issue['comments']['nodes'][0]
        issue['comments']['nodes'] = [dict(prototype, databaseId=n) for n in range(1, 101)]
        def transport(args, **kwargs):
            query = next(arg[6:] for arg in args if arg.startswith('query='))
            if 'goal_1:' in query:
                self.assertEqual('query($owner:String!,$name:String!,$limit:Int!){'
                                 'repository(owner:$owner,name:$name){nameWithOwner '
                                 'goal_1:issue(number:1){number comments(last:$limit){'
                                 'nodes{databaseId body createdAt updatedAt}}}}}', query)
                response = value
            else:
                response = {'data': {'repository': {'issue': issue}}}
            return subprocess.CompletedProcess(args, 0, json.dumps(response), '')
        adapter._run = mock.Mock(side_effect=transport)
        self.assertEqual(adapter.get_issue_comment_tail(1), adapter.get_issue_comment_tails([1])[1])

    def test_invalid_bounds_never_launch_provider(self):
        adapter = self.adapter(); adapter._run = mock.Mock()
        for numbers in ([], [1] * 2, [True], [0], [1, 2, 3, 4, 5], (1,)):
            with self.assertRaises(z.GoalHistoryReadError): adapter.get_issue_comment_tails(numbers)
        for limit in (0, 101, True):
            with self.assertRaises(z.GoalHistoryReadError): adapter.get_issue_comment_tails([1], limit)
        adapter._run.assert_not_called(); adapter.ensure_identity.assert_not_called()

    def test_actual_run_uses_remaining_budget_and_does_not_reset_timeout(self):
        adapter = self.adapter(); adapter.executable = 'gh'
        remaining = mock.Mock(return_value=2.75)
        response = subprocess.CompletedProcess([], 0, json.dumps(self.response([1])), '')
        with mock.patch.object(z, 'provider_operation_remaining', remaining), mock.patch.object(
                z.subprocess, 'run', return_value=response) as run:
            adapter.get_issue_comment_tails([1])
            self.assertEqual(2.75, run.call_args.kwargs['timeout'])
            self.assertEqual(1, run.call_count)
        # The existing budget callback enforces exhaustion before subprocess launch.
        adapter.timeout_budget = mock.Mock(side_effect=z.GoalTransitionProviderError('deadline exhausted'))
        with mock.patch.object(z.subprocess, 'run') as run, self.assertRaises(z.GoalHistoryReadError):
            adapter.get_issue_comment_tails([1])
        run.assert_not_called()
        del adapter.timeout_budget
        with mock.patch.object(z.subprocess, 'run', side_effect=subprocess.TimeoutExpired('gh', 1)) as run:
            with self.assertRaises(z.GoalHistoryReadError): adapter.get_issue_comment_tails([1])
            self.assertEqual(1, run.call_count)


class TailWindowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = cache_tests.PublicationCacheScanTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.engine = z._workflow.Workflow.__new__(z._workflow.Workflow)
        self.engine.repository, self.engine.runtime, self.engine.api = 'owner/repo', {'root_id': 'root'}, z
        self.engine.repo = Path('/unused-test-repository')
        self.engine.portfolio = lambda: self.fixture.goals
        self.events = []
        outer = self
        class Adapter:
            def get_issue_comment_tails(self, numbers):
                outer.events.append(('batch', list(numbers)))
                outer.assertEqual({}, outer.engine._publication_tails)
                return {n: [{'id': n, 'body': 'tail-' + str(n)}] for n in numbers}
            def get_issue_comment_tail(self, number):
                outer.fail('prefetched goal must not retry a single tail')
            def get_issue_comments(self, number): return []
        self.engine.adapter = Adapter()
        self.visited = []
        def read(number, ref):
            if number not in self.visited:
                self.visited.append(number)
                outer.assertLessEqual(len(self.engine._publication_tails), 4)
                key = (number, self.fixture.issue_hash(number))
                self.assertEqual('tail-' + str(number), self.engine._publication_tails.pop(key)[0]['body'])
                self.events.append(('hydrate', number))
            return self.fixture.blobs[ref['hash']]
        self.engine.read_artifact = read

    def scan(self):
        with mock.patch.object(z, 'provider_issue_snapshot', side_effect=lambda repo, repository, n:
                               {'body': self.fixture.bodies[n]}):
            return self.engine.node_managed_publication_branches([])

    def test_94_goals_are_hydrated_sequentially_in_24_bounded_windows(self):
        for number in range(1, 95): self.fixture.store(number)
        excluded = [{'key': n, 'schema_version': schema, 'status': status}
                    for n, schema, status in [(95, 1, 'in_progress'), (96, 2, 'done'), (97, 2, 'cancelled')]]
        self.fixture.goals.extend(excluded)
        self.assertEqual(set(), self.scan())
        self.assertEqual(24, sum(event[0] == 'batch' for event in self.events))
        self.assertEqual(list(range(31, 95)) + list(range(1, 31)), self.visited)
        self.assertEqual({}, self.engine._publication_tails)
        pending = []
        for kind, value in self.events:
            if kind == 'batch':
                self.assertEqual([], pending)
                pending = value[:]
            else: self.assertEqual(pending.pop(0), value)
        self.assertEqual([], pending)

    def test_real_artifact_cache_keeps_64_hits_and_30_complete_history_misses(self):
        engine = self.engine
        engine._artifact_indexes = {}
        rows = [{'id': 1, 'body': 'immutable history',
                 'created_at': '2026-10-13T00:00:00Z', 'updated_at': '2026-10-13T00:00:00Z'}]
        contract = z._workflow.materialized_state_contract()
        for number in range(1, 95):
            self.fixture.cache.store('owner/repo', number, self.fixture.issue_hash(number),
                                     rows, rows, contract, __import__('time').time())
        engine.adapter.get_issue_comment_tails = mock.Mock(side_effect=lambda numbers:
                                                         {n: copy.deepcopy(rows) for n in numbers})
        engine.adapter.get_issue_comments = mock.Mock(return_value=copy.deepcopy(rows))
        hits, misses = [], []
        def read(number, ref):
            if number not in hits + misses:
                index = engine._artifact_index(number)
                (hits if index._materialized_state_cache else misses).append(number)
            return self.fixture.blobs[ref['hash']]
        engine.read_artifact = read
        self.assertEqual(set(), self.scan())
        self.assertEqual(64, len(hits))
        self.assertEqual(30, len(misses))
        self.assertEqual(30, engine.adapter.get_issue_comments.call_count)
        self.assertEqual(24, engine.adapter.get_issue_comment_tails.call_count)
        self.assertEqual(64, len(list(self.fixture.cache._root().glob('*.json'))))

    def test_exception_clears_window_and_does_not_launch_later_windows(self):
        self.engine.read_artifact = mock.Mock(side_effect=ValueError('required artifact invalid'))
        with self.assertRaisesRegex(ValueError, 'required artifact invalid'): self.scan()
        self.assertEqual(1, len(self.events))
        self.assertEqual({}, self.engine._publication_tails)
        # A resumed call obtains fresh observations, rather than retaining leftovers.
        with self.assertRaises(ValueError): self.scan()
        self.assertEqual(2, len(self.events))

    def test_failed_batch_uses_existing_full_history_without_tail_retry(self):
        self.fixture.goals = self.fixture.goals[:4]
        self.engine._artifact_indexes = {}
        self.engine.adapter.get_issue_comment_tails = mock.Mock(side_effect=z.GoalHistoryReadError('partial batch'))
        self.engine.adapter.get_issue_comment_tail = mock.Mock(side_effect=AssertionError('extra tail retry'))
        self.engine.adapter.get_issue_comments = mock.Mock(return_value=[])
        def read(number, ref):
            self.engine._artifact_index(number)
            return self.fixture.blobs[ref['hash']]
        self.engine.read_artifact = read
        self.assertEqual(set(), self.scan())
        self.assertEqual(4, self.engine.adapter.get_issue_comments.call_count)
        self.engine.adapter.get_issue_comment_tail.assert_not_called()
        self.assertEqual({}, self.engine._publication_tails)
        self.engine._artifact_indexes = {}
        self.engine.adapter.get_issue_comments.side_effect = z.GoalHistoryReadError('complete history unavailable')
        with self.assertRaisesRegex(z.GoalHistoryReadError, 'complete history unavailable'): self.scan()
        self.assertEqual({}, self.engine._publication_tails)

    def test_body_hash_binding_invalidation_and_read_only_capability(self):
        engine = self.engine
        engine._artifact_indexes = {}
        number = 1
        old = self.fixture.issue_hash(number)
        engine._publication_tails = {(number, old): [{'id': 10, 'body': 'old'}]}
        engine._issue_observations = {number: {'body': self.fixture.bodies[number] + '\nnew body'}}
        engine.adapter.get_issue_comment_tail = mock.Mock(return_value=[])
        engine._artifact_index(number)
        engine.adapter.get_issue_comment_tail.assert_called_once_with(number)
        engine.invalidate()
        self.assertEqual({}, engine._publication_tails)
        gateway = z._workflow.ProviderReadGateway(engine, engine.adapter)
        self.assertTrue(callable(gateway.get_issue_comment_tails))
        self.assertFalse(hasattr(gateway, 'update_issue'))
        self.assertFalse(hasattr(gateway, 'create_issue_comment'))

    def test_adapter_without_explicit_capability_keeps_single_read_path(self):
        engine = self.engine
        engine.adapter = mock.Mock()
        engine.read_artifact = lambda number, ref: self.fixture.blobs[ref['hash']]
        self.assertEqual(set(), self.scan())
        engine.adapter.get_issue_comment_tails.assert_not_called()


if __name__ == '__main__':
    unittest.main()
