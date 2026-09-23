"""Renewal regressions using real workflow mutations and subprocess deadlines."""
import subprocess
import contextlib
import io
import json
import sys
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import test_workflow_integration as journeys

z = journeys.z


class RenewalTests(unittest.TestCase):
    def journey(self):
        fixture = journeys.PublicWorkflowJourneyTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def test_renewal_acknowledges_exact_saved_lease_without_rehydrating_portfolio(self):
        f = self.journey()
        lease, _ = f.prepare()
        with mock.patch.object(f.engine, 'portfolio', side_effect=AssertionError('redundant portfolio read')):
            result = f.mutate(operation='renew', phase='plan', lease=lease['token'], actor='builder', worker_status='active')
        step = result['next_steps'][0]
        stored = z.github_goal_record(f.adapter.issue)['workflow']['leases']['plan:execute']
        self.assertEqual('renewed', step['kind'])
        self.assertEqual((42, 'plan', 'builder', lease['token'], stored['expires_at']),
                         tuple(step[k] for k in ('goal', 'phase', 'actor', 'lease', 'expires_at')))

    def test_wrong_actor_cannot_renew_and_failed_save_does_not_acknowledge(self):
        f = self.journey()
        lease, _ = f.prepare()
        before = f.adapter.issue['body']
        with self.assertRaisesRegex(ValueError, 'bound worker'):
            f.mutate(operation='renew', phase='plan', lease=lease['token'], actor='intruder', worker_status='active')
        self.assertEqual(before, f.adapter.issue['body'])
        with mock.patch.object(f.engine, 'save', side_effect=ValueError('provider failure')):
            with self.assertRaisesRegex(ValueError, 'provider failure'):
                f.mutate(operation='renew', phase='plan', lease=lease['token'], actor='builder', worker_status='active')

    def test_provider_timeout_unwinds_storage_with_fresh_cleanup_budget(self):
        f = self.journey()
        budget = z._workflow.RenewalBudget(.15, 1)
        f.engine.budget = budget
        adapter = SimpleNamespace()
        released = []
        def release(*args):
            # A real subprocess must still be possible after work budget expires.
            subprocess.run([sys.executable, '-c', 'pass'], timeout=adapter.timeout_budget(30), check=True)
            released.append(args[-1])
        with mock.patch.object(f.engine.api, 'GitHubReservationAdapter', return_value=adapter), \
             mock.patch.object(f.engine.api, 'acquire_storage_lock', return_value={'acquired': True, 'expires_at': time.time() + 300}), \
             mock.patch.object(f.engine.api, 'release_storage_lock', side_effect=release):
            with self.assertRaises(subprocess.TimeoutExpired):
                with z._workflow.Workflow.locked(f.engine):
                    subprocess.run([sys.executable, '-c', 'import time; time.sleep(5)'], timeout=budget.timeout(30), check=True)
        self.assertEqual(1, len(released))
        self.assertIsNone(f.engine._storage_reservation)

    def test_uncertain_acquisition_also_attempts_exact_owner_cleanup(self):
        f = self.journey()
        f.engine.budget = z._workflow.RenewalBudget(1, 1)
        adapter = SimpleNamespace()
        with mock.patch.object(f.engine.api, 'GitHubReservationAdapter', return_value=adapter), \
             mock.patch.object(f.engine.api, 'acquire_storage_lock', side_effect=ValueError('confirmation lost')) as acquire, \
             mock.patch.object(f.engine.api, 'release_storage_lock') as release:
            with self.assertRaisesRegex(ValueError, 'confirmation lost'):
                with z._workflow.Workflow.locked(f.engine):
                    self.fail('must not enter')
        self.assertEqual(acquire.call_args.args[:5], release.call_args.args)

    def test_saved_result_replay_retries_failed_local_shutdown_without_rewriting(self):
        f = self.journey()
        lease, record = f.prepare()
        payload = dict(operation='record_result', phase='plan', lease=lease['token'],
                       actor='builder', record=record, request_id='terminal-replay')
        with mock.patch.object(f.engine.api._heartbeat, 'stop_heartbeat', side_effect=[OSError('local failure'), {}]) as stop:
            result = f.engine.mutate(42, payload)
            saved = f.adapter.issue['body']
            self.assertIn('durable submission succeeded', result['next_steps'][-1]['action'])
            self.assertEqual(payload, result['next_steps'][-1]['submission'])
            replay = f.engine.mutate(42, payload)
        self.assertEqual(saved, f.adapter.issue['body'])
        self.assertEqual(2, stop.call_count)
        self.assertEqual('checkpoint', replay['next_steps'][0]['kind'])

    def test_cli_renewal_error_identifies_request_and_preserves_uncertainty(self):
        f = self.journey()
        path = f.repo / 'renew.json'
        path.write_text(json.dumps(dict(operation='renew', phase='plan', actor='builder', lease='token')))
        argv = ['zzzops.py', '--intent', 'execute', '--goal', '42', '--input', str(path)]
        output = io.StringIO()
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(z._workflow, 'public_run', side_effect=ValueError('provider timeout')), contextlib.redirect_stdout(output):
            self.assertEqual(2, z.main())
        step = json.loads(output.getvalue())['next_steps'][0]
        self.assertEqual((42, 'plan', 'builder'), tuple(step[k] for k in ('goal', 'phase', 'actor')))
        self.assertEqual([*argv[1:-1], '<submission.json>', '--source-skill', '$execute-zzzops'], step['command'][2:])
        self.assertEqual(json.loads(path.read_text()), step['submission'])
        self.assertIn('does not authorize takeover', step['action'])


if __name__ == '__main__':
    unittest.main()
