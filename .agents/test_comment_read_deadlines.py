"""Real public workflow and comment transport with deterministic provider latency."""
import contextlib
import copy
import json
import os
import subprocess
import types
from unittest import mock

from test_evidence_dag_journeys import DagFixture, z
from test_workflow_renewal import GenericRenewalTests

ADAPTER = z.GitHubGoalTransitionAdapter


class CommentReadDeadlineTests(DagFixture):
    request = GenericRenewalTests.request

    @contextlib.contextmanager
    def delayed_history(self, *, delay=40, failure=None, budget=90):
        original = self.provider.get_issue_comments
        elapsed, calls, cleanup = [0.0], [], []
        def command(cmd, *args, **kwargs):
            if '/comments?per_page=100' not in ' '.join(cmd): return None
            rows = original(100)
            rows += [{'id': 10000 + i, 'body': 'Retained historical comment'} for i in range(332 - len(rows))]
            pages = [rows[i:i + 100] for i in range(0, len(rows), 100)]
            calls.append({'timeout': kwargs['timeout'], 'ids': [r['id'] for r in rows]})
            cleanup.append(z.release_storage_lock)
            cost = delay if len(calls) == 1 else 0
            elapsed[0] += min(cost, kwargs['timeout'])
            if cost >= kwargs['timeout']:
                raise subprocess.TimeoutExpired(cmd, kwargs['timeout'], output=json.dumps(pages[:2]))
            if failure == 'provider':
                return subprocess.CompletedProcess(cmd, 1, json.dumps(pages[:2]), 'connection lost after two pages')
            if failure == 'partial': pages[1] = pages[1][:1]
            if failure == 'duplicate': pages[-1][-1] = pages[0][0]
            if failure == 'malformed': return subprocess.CompletedProcess(cmd, 0, '[[]', '')
            return subprocess.CompletedProcess(cmd, 0, json.dumps(pages), '')
        self.session.provider_command = command
        with mock.patch.dict(os.environ, {'ZZZOPS_RENEWAL_TIMEOUT_SECONDS': str(budget),
                                         'ZZZOPS_WORKFLOW_TIMEOUT_SECONDS': str(budget)}), \
             mock.patch.object(z._workflow.time, 'monotonic', side_effect=lambda: elapsed[0]), \
             mock.patch.object(self.provider, 'get_issue_comments', side_effect=lambda n: ADAPTER.get_issue_comments(self.provider, n)), \
             mock.patch.object(self.provider, 'get_issue_comments_full', side_effect=lambda n: ADAPTER.get_issue_comments_full(self.provider, n), create=True), \
             mock.patch.object(self.provider, '_comment_pages', ADAPTER._comment_pages, create=True), \
             mock.patch.object(self.provider, '_record_comment_read', types.MethodType(ADAPTER._record_comment_read, self.provider), create=True), \
             mock.patch.object(self.provider, 'comment_read_counters', {}, create=True), \
             mock.patch.object(self.provider, 'ensure_identity', create=True), \
             mock.patch.object(self.provider, '_run', types.MethodType(ADAPTER._run, self.provider), create=True), \
             mock.patch.object(self.provider, 'executable', 'gh', create=True), \
             mock.patch.object(self.provider, 'repo', self.fixture.repo, create=True), \
             mock.patch.object(self.provider, '_provider_error', ADAPTER._provider_error, create=True):
            yield calls, elapsed, cleanup
        del self.session.provider_command
        # The fixture reuses one adapter across invocations; production creates it.
        if hasattr(self.provider, 'timeout_budget'): del self.provider.timeout_budget

    def test_checkpoint_reads_four_slow_pages_completely_within_deadline(self):
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        with self.delayed_history() as (calls, elapsed, _):
            response = self.session.call(100)
        self.assertTrue(any(s['kind'] == 'execute' for s in response['next_steps']))
        self.assertEqual(40, elapsed[0])
        self.assertEqual(90, calls[0]['timeout'])
        self.assertEqual(332, len(calls[0]['ids']))
        self.assertEqual(sorted(set(calls[0]['ids'])), calls[0]['ids'])
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertIsNone(z.provider_operation_remaining())

    def test_delayed_renewal_preserves_exact_lease_and_retry_is_idempotent(self):
        work = self.session.acquire('produce')
        request = self.request(work, request_id='delayed-renewal')
        before_updates = len(self.provider.updates)
        with self.delayed_history(delay=100, budget=120) as (calls, elapsed, cleanup):
            response = self.session.call(100, request)
            self.assertEqual(1, cleanup[0].call_count)
        ack = response['next_steps'][0]
        self.assertEqual(('renewed', work['lease']['token'], work['bound_actor']),
                         (ack['kind'], ack['lease'], ack['actor']))
        self.assertEqual([120, 20, 20], [c['timeout'] for c in calls])
        self.assertEqual(100, elapsed[0])
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.assertEqual(response, self.session.call(100, request))
        self.assertEqual(before_updates + 1, len(self.provider.updates))
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_real_deadline_exhaustion_cleans_up_and_supports_same_lease_retry(self):
        work = self.session.acquire('produce')
        request = self.request(work, request_id='exhausted-renewal')
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        with self.delayed_history(delay=100, budget=60) as (calls, elapsed, cleanup):
            response = self.session.call(100, request, expected=2)
            self.assertEqual(1, cleanup[0].call_count)
        self.assertEqual(60, elapsed[0])
        self.assertEqual(60, calls[0]['timeout'])
        step = response['next_steps'][0]
        self.assertIn('comment-history read for goal #100', step['reason'])
        self.assertIn('does not authorize takeover', step['action'])
        self.assertEqual(request, step['submission'])
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        with self.delayed_history(delay=40):
            renewed = self.session.call(100, request)
        self.assertEqual(work['lease']['token'], renewed['next_steps'][0]['lease'])

    def test_partial_malformed_or_failed_pages_never_publish_renewal(self):
        work = self.session.acquire('produce')
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        for failure in ('provider', 'partial', 'duplicate', 'malformed'):
            with self.subTest(failure=failure), self.delayed_history(delay=1, failure=failure) as (_, _, cleanup):
                response = self.session.call(100, self.request(work), expected=2)
                self.assertEqual(1, cleanup[0].call_count)
                self.assertFalse(any(s['kind'] == 'renewed' for s in response['next_steps']))
                self.assertIn('100', response['next_steps'][0]['reason'])
            self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_checkpoint_deadline_failure_is_readonly_and_retryable(self):
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        with self.delayed_history(delay=100, budget=60) as (calls, elapsed, _):
            response = self.session.call(100, expected=2)
        self.assertEqual((60, 60), (calls[0]['timeout'], elapsed[0]))
        step = response['next_steps'][0]
        self.assertIn('goal #100', step['reason'])
        self.assertIn('--goal', step['command'])
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertIsNone(z.provider_operation_remaining())
        with self.delayed_history():
            self.session.call(100)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_expired_budget_rejects_before_starting_another_read(self):
        with mock.patch.object(z._workflow.time, 'monotonic', return_value=1):
            budget = z._workflow.RenewalBudget(1)
        adapter = ADAPTER.__new__(ADAPTER)
        adapter._identity_checked = True
        adapter.timeout_budget = budget.timeout
        adapter.repository, adapter.repo, adapter.executable = 'owner/repo', self.fixture.repo, 'gh'
        with mock.patch.object(z._workflow.time, 'monotonic', return_value=3), mock.patch.object(z.subprocess, 'run') as run:
            with self.assertRaisesRegex(z.GoalTransitionProviderError, 'goal #100.*deadline exhausted'):
                adapter.get_issue_comments(100)
        run.assert_not_called()
