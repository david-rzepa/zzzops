"""Public verification executes each exact request once across uncertainty."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

import test_evidence_dag_journeys as journeys

z = journeys.z


class AuthoritativeVerificationTests(journeys.DagFixture):
    workspace_graph = journeys.WorkspaceAuthorityPublicTests.workspace_graph
    setup_workspace = journeys.WorkspaceAuthorityPublicTests.setup_workspace
    acquire_workspace = journeys.WorkspaceAuthorityPublicTests.acquire_workspace

    def setUp(self):
        super().setUp()
        self.setup_workspace()
        self.work = self.acquire_workspace('alpha')
        self.counter = Path(self.session.control) / 'verification-count'

    def command(self, code=0):
        return [sys.executable, '-c', "from pathlib import Path; import sys; p=Path(%r); p.write_text(p.read_text()+'run\\n' if p.exists() else 'run\\n'); print('check stdout'); print('check stderr', file=sys.stderr); raise SystemExit(%d)" % (str(self.counter), code)]

    def request(self, identity, code=0, expectation='passed'):
        request = self.session.submission(self.work, {'value': 'exact checked candidate'}, identity)
        request.update(workspace_checks=[self.command(code)], verification_expectation=expectation)
        return request

    def count(self):
        return len(self.counter.read_text().splitlines()) if self.counter.exists() else 0

    def test_first_append_failure_reuses_command_proof_and_log(self):
        request = self.request('first-append')
        request.pop('verification_expectation')  # Existing submit wire also gets crash-safe execution.
        before = len(self.provider.updates)
        started = time.monotonic()
        with mock.patch.object(self.provider, 'create_issue_comment', side_effect=RuntimeError('unavailable before first append')):
            self.session.call(100, request, expected=2)
        self.assertEqual(1, self.count())
        response = self.session.call(100, request)
        self.assertEqual(1, self.count())
        self.assertEqual(before + 1, len(self.provider.updates))
        self.assertEqual(response, self.session.call(100, request))
        proof = self.read_blob(response['verification']['proof'])
        self.assertEqual(self.work['lease']['token'], proof['lease'])
        self.assertEqual(request['workspace_checks'], [row['command'] for row in proof['commands']])
        self.assertTrue(proof['passed'])
        self.assertIn('check stdout', Path(proof['commands'][0]['log']).read_text())
        self.assertIn('check stderr', Path(proof['commands'][0]['log']).read_text())
        self.assertGreaterEqual(time.monotonic() - started, sum(row['duration_seconds'] for row in proof['commands']))

    def test_failed_green_keeps_lease_and_corrected_request_executes_once(self):
        failed_request = self.request('green-failed', code=1)
        evidence = copy.deepcopy(self.payload()[1]['evidence'])
        failed = self.session.call(100, failed_request)
        self.assertEqual('verification_failed', failed['next_steps'][0]['kind'])
        self.assertEqual(evidence, self.payload()[1]['evidence'])
        self.assertEqual(self.work['lease']['token'], self.payload()[1]['operational']['leases'][0]['token'])
        self.assertEqual(failed, self.session.call(100, failed_request))
        self.assertEqual(1, self.count())
        corrected = self.session.call(100, self.request('green-corrected'))
        self.assertTrue(corrected['verification']['passed'])
        self.assertEqual(2, self.count())
        self.assertFalse(self.payload()[1]['operational']['leases'])

    def test_explicit_red_observation_records_failed_proof_without_rerun(self):
        request = self.request('red-baseline', code=1, expectation='observed')
        response = self.session.call(100, request)
        self.assertFalse(response['verification']['passed'])
        self.assertEqual(1, self.read_blob(response['verification']['proof'])['commands'][0]['exit_code'])
        self.assertEqual(self.result('alpha')[0], response['submitted']['result'])
        self.assertEqual(response, self.session.call(100, request))
        self.assertEqual(1, self.count())

    def test_timeout_is_not_repeated_and_next_request_can_retry_under_live_lease(self):
        request = self.request('timeout')
        original = subprocess.run
        def timeout(argv, *args, **kwargs):
            if argv == request['workspace_checks'][0]:
                original(argv, *args, **kwargs)
                raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
            return original(argv, *args, **kwargs)
        with mock.patch.object(subprocess, 'run', side_effect=timeout):
            response = self.session.call(100, request)
        self.assertEqual('verification_failed', response['next_steps'][0]['kind'])
        proof = self.read_blob(response['next_steps'][0]['proof'])
        self.assertTrue(proof['commands'][0]['timed_out'])
        self.assertFalse(proof['passed'])
        self.assertEqual(response, self.session.call(100, request))
        self.assertEqual(1, self.count())
        self.session.call(100, self.request('after-timeout'))
        self.assertEqual(2, self.count())

    def test_interrupted_running_request_requires_observed_recovery_then_new_owner_works(self):
        request = self.request('interrupted')
        original = subprocess.run
        def interrupted(argv, *args, **kwargs):
            if argv == request['workspace_checks'][0]:
                original(argv, *args, **kwargs)
                raise KeyboardInterrupt('host interrupted before result recorded')
            return original(argv, *args, **kwargs)
        with mock.patch.object(subprocess, 'run', side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            self.session.call(100, request)
        response = self.session.call(100, request)
        self.assertEqual('await_worker', response['next_steps'][0]['kind'])
        self.assertEqual('await_worker', self.session.call(100, self.request('attempted-bypass'))['next_steps'][0]['kind'])
        self.assertEqual(1, self.count())
        recovery = response['next_steps'][0]['recovery_contract']
        self.session.call(100, {**recovery, 'worker_status': 'stopped', 'evidence': 'Observed exact verifier and worker terminated'})
        self.work = self.acquire_workspace('alpha')
        response = self.session.call(100, self.request('new-owner'))
        self.assertTrue(response['verification']['passed'])
        self.assertEqual(2, self.count())

    def test_changed_request_workspace_or_logs_cannot_reuse_unpublished_proof(self):
        request = self.request('immutable-identity')
        with mock.patch.object(self.provider, 'create_issue_comment', side_effect=RuntimeError('unavailable')):
            self.session.call(100, request, expected=2)
        self.assertEqual(1, self.count())
        self.session.call(100, {**request, 'workspace_checks': [self.command(1)]}, expected=2)
        path = self.fixture.repo / 'behavior_test.py'
        original = path.read_bytes()
        path.write_text('assert True\n')
        self.session.call(100, request, expected=2)
        path.write_bytes(original)
        logs = list((self.fixture.repo / '.zzzops/diagnostics').glob('node-*.log'))
        self.assertTrue(logs)
        logs[-1].write_text('tampered log')
        self.session.call(100, request, expected=2)
        self.assertEqual(1, self.count())


if __name__ == '__main__':
    unittest.main()
