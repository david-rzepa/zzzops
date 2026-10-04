"""Bounded goal-body transport through the shared public provider gateway."""
import copy
import json
import re
import subprocess
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import test_zzzops as fixtures
import test_evidence_dag_journeys as dag

z = fixtures.zzzops


class BodyTransport:
    def __init__(self, issues=None):
        self.gateway = dag.GatewayTransport(issues or {})
        self.calls = []
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()
        self.barrier = None
        self.failures = {}
        self.change = None

    def __call__(self, command, **kwargs):
        query = next((v for v in command if v.startswith('query=')), '')
        numbers = [int(v) for v in re.findall(r'goal_(\d+):issue', query)]
        if not numbers:
            return self.gateway(command, **kwargs)
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.calls.append({'numbers': numbers, 'timeout': kwargs['timeout'], 'bytes': 0})
            record = self.calls[-1]
            failure = self.failures.get(numbers[0], [])
            failure = failure.pop(0) if failure else None
        try:
            if self.barrier is not None:
                self.barrier.wait(timeout=2)
            if failure == 'timeout':
                threading.Event().wait(kwargs['timeout'])
                raise subprocess.TimeoutExpired(command, kwargs['timeout'])
            if failure:
                return subprocess.CompletedProcess(command, 1, '', failure)
            if len(numbers) > 5:
                return subprocess.CompletedProcess(command, 1, '', 'HTTP2 stream cancellation: unexpected EOF')
            rows = {f'goal_{n}': {'number': n,
                    'body': self.gateway.issues[n]['body'] if n in self.gateway.issues else ('😀\r\n' + 'x' * 181323),
                    'updatedAt': self.gateway.issues[n]['updated_at'] if n in self.gateway.issues else '2026-10-04T00:00:00Z'} for n in numbers}
            value = {'data': {'repository': rows}}
            if self.change: self.change(value)
            raw = json.dumps(value)
            record['bytes'] = len(raw.encode('utf-8'))
            return subprocess.CompletedProcess(command, 0, raw, '')
        finally:
            with self.lock: self.active -= 1


class GoalBodyHydrationTests(unittest.TestCase):
    def hydrate(self, transport, numbers):
        with mock.patch.object(z.subprocess, 'run', side_effect=transport):
            return z._github_goal_bodies(Path('.'), 'gh', 'owner', 'repo', numbers)

    def test_observed_88_large_bodies_complete_with_bounded_parallelism_and_exact_bytes(self):
        transport = BodyTransport()
        # Every full wave must really overlap. 88 gives eighteen batches; use
        # only the first four calls for the barrier to avoid an incomplete wave.
        barrier = threading.Barrier(4)
        original = transport.__call__
        first_lock = threading.Lock(); waiting = [0]
        def concurrent(command, **kwargs):
            with first_lock:
                waiting[0] += 1
                first_wave = waiting[0] <= 4
            if first_wave: barrier.wait(timeout=2)
            return original(command, **kwargs)
        started = time.monotonic()
        rows, size, count = self.hydrate(concurrent, list(range(100, 188)) + [100])
        self.assertEqual(list(range(100, 188)), list(rows))
        self.assertEqual(18, count)
        self.assertEqual(18, len(transport.calls))
        self.assertEqual(list(range(100, 188)), sorted(n for call in transport.calls for n in call['numbers']))
        self.assertTrue(all(len(call['numbers']) <= 5 for call in transport.calls))
        self.assertTrue(all(0 < call['timeout'] <= 60 for call in transport.calls))
        self.assertTrue(all(row == {'body': '😀\r\n' + 'x' * 181323, 'updated_at': '2026-10-04T00:00:00Z'} for row in rows.values()))
        self.assertEqual(sum(call['bytes'] for call in transport.calls), size)
        self.assertEqual(0, transport.active)
        self.metrics = {'requests': count, 'response_bytes': size, 'elapsed': time.monotonic() - started}

    def test_retry_is_finite_transient_only_and_does_not_duplicate_logical_results(self):
        transport = BodyTransport(); transport.failures[1] = ['unexpected EOF']
        rows, size, count = self.hydrate(transport, [1, 2])
        self.assertEqual([1, 2], list(rows)); self.assertEqual(2, count)
        self.assertGreater(size, 0)
        for errors, expected in ((['HTTP 503', 'HTTP 503'], 2), (['HTTP 403 forbidden'], 1)):
            transport = BodyTransport(); transport.failures[1] = errors
            with self.assertRaises(ValueError): self.hydrate(transport, [1])
            self.assertEqual(expected, len(transport.calls))
            self.assertEqual(0, transport.active)

    def test_partial_wrong_alias_identity_marker_and_graphql_errors_fail_closed(self):
        def rows(value): return value['data']['repository']
        changes = [lambda v: rows(v).pop('goal_2'),
                   lambda v: rows(v)['goal_1'].update(number=2),
                   lambda v: rows(v)['goal_1'].update(updatedAt=None),
                   lambda v: rows(v)['goal_1'].update(body=None),
                   lambda v: rows(v).update(goal_99=rows(v)['goal_1']),
                   lambda v: v.update(errors=[{'message': 'partial provider error'}])]
        for change in changes:
            with self.subTest(change=change):
                transport = BodyTransport(); transport.change = change
                with self.assertRaises(ValueError): self.hydrate(transport, [1, 2])
                self.assertEqual(1, len(transport.calls)); self.assertEqual(0, transport.active)

    def test_short_parent_deadline_bounds_running_calls_and_cleans_up(self):
        transport = BodyTransport()
        transport.failures = {n: ['timeout'] for n in (1, 6, 11, 16)}
        started = time.monotonic()
        with mock.patch.object(z, 'provider_operation_remaining', return_value=.05, create=True):
            with self.assertRaisesRegex(ValueError, 'deadline|TimeoutExpired|cancelled'):
                self.hydrate(transport, list(range(1, 89)))
        self.assertLess(time.monotonic() - started, 1)
        self.assertLessEqual(len(transport.calls), 4)
        self.assertTrue(all(0 < call['timeout'] <= .05 for call in transport.calls))
        self.assertEqual(4, transport.peak)
        self.assertEqual(0, transport.active)

    def test_invalid_numbers_never_start_transport(self):
        for numbers in ([True], [0], ['1'], [-1]):
            transport = BodyTransport()
            with self.assertRaises(ValueError): self.hydrate(transport, numbers)
            self.assertEqual([], transport.calls)

    def test_public_checkpoint_large_portfolio_preserves_ownership_and_warm_cache(self):
        fixture = dag.DagFixture(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        work = fixture.session.acquire('produce')
        # One actual owned v2 goal plus 87 large siblings, consumed only as
        # portfolio records. Their canonical bodies and markers stay exact.
        for number in range(101, 188):
            issue = fixtures.PortfolioTests().issue(number)
            issue['body'] = 'Large human specification\n' + 'x' * 181323 + '\n' + issue['body']
            fixture.provider.issues[number] = issue
            fixture.provider.comments[number] = []
        transport = BodyTransport(fixture.provider.issues)
        real_run = z.subprocess.run
        def dispatch(command, *args, **kwargs):
            if command[0] in ('gh', 'synthetic-gh'):
                return transport(command, **kwargs)
            return real_run(command, *args, **kwargs)
        fixture.session.portfolio_snapshot = lambda *_a, **_k: z.github_repository_portfolio_snapshot(fixture.fixture.repo, fixture.session.project, **_k)[1]
        before = copy.deepcopy((fixture.provider.issues, fixture.provider.comments))
        with mock.patch.object(z.shutil, 'which', return_value='synthetic-gh'), mock.patch.object(z.subprocess, 'run', side_effect=dispatch):
            with mock.patch.object(z, 'GOAL_HYDRATION_BATCH_SIZE', 100):
                failed = fixture.session.call(100, expected=None)
            self.assertIn('HTTP2', json.dumps(failed))
            self.assertTrue(all(len(call['numbers']) == 88 for call in transport.calls))
            self.assertEqual(before, (fixture.provider.issues, fixture.provider.comments))
            transport.calls.clear()
            cold_started = time.monotonic()
            steps = fixture.session.checkpoint(100)
            owned = next(step for step in steps if step.get('kind') == 'await_worker')
            self.assertEqual(work['lease']['token'], owned['lease']['token'])
            self.assertEqual(work['bound_actor'], owned['lease']['worker'])
            self.assertEqual(18, len(transport.calls))
            self.metrics = {'public_checkpoint': True, 'cold_requests': len(transport.calls),
                            'response_bytes': sum(call['bytes'] for call in transport.calls),
                            'elapsed': time.monotonic() - cold_started,
                            'preserved_lease_token': work['lease']['token'] == owned['lease']['token']}
            transport.calls.clear()
            fixture.session.checkpoint(100)
            self.assertEqual([], transport.calls)
            fixture.provider.issues[101]['updated_at'] = '2026-10-05T00:00:00Z'
            fixture.session.checkpoint(100)
            self.assertEqual([[101]], [call['numbers'] for call in transport.calls])
        before[0][101]['updated_at'] = '2026-10-05T00:00:00Z'
        self.assertEqual(before, (fixture.provider.issues, fixture.provider.comments))


if __name__ == '__main__':
    unittest.main()
