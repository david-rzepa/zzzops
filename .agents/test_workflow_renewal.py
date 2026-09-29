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
        # Preserve the exact renewal or terminal-replay invariant through generic node ownership and public submit.
        # Preserve the exact renewal or terminal-replay invariant through generic node ownership and public submit.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_workflow_renewal.GenericRenewalTests.test_exact_renewal_acknowledges_saved_node_lease_without_portfolio_fetch',
        )

    def test_wrong_actor_cannot_renew_and_failed_save_does_not_acknowledge(self):
        # Preserve the exact renewal or terminal-replay invariant through generic node ownership and public submit.
        # Preserve the exact renewal or terminal-replay invariant through generic node ownership and public submit.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_workflow_renewal.GenericRenewalTests.test_wrong_renewal_actor_and_failed_provider_save_never_acknowledge',
        )

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
        # Preserve the exact renewal or terminal-replay invariant through generic node ownership and public submit.
        # Preserve the exact renewal or terminal-replay invariant through generic node ownership and public submit.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_workflow_renewal.GenericRenewalTests.test_exact_terminal_retry_retries_local_shutdown_without_durable_rewrite',
        )

    def test_cli_renewal_error_identifies_request_and_preserves_uncertainty(self):
        f = self.journey()
        path = f.repo / 'renew.json'
        node = {'goal': 42, 'node': 'planning', 'item': None, 'generation': 1}
        path.write_text(json.dumps(dict(operation='renew', node=node, actor='builder', lease='token')))
        argv = ['zzzops.py', '--intent', 'execute', '--goal', '42', '--input', str(path)]
        output = io.StringIO()
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(z._workflow, 'public_run', side_effect=ValueError('provider timeout')), contextlib.redirect_stdout(output):
            self.assertEqual(2, z.main())
        step = json.loads(output.getvalue())['next_steps'][0]
        self.assertIn('node', step, 'Generic renewal diagnostic must retain exact task identity')
        self.assertEqual((42, node, 'builder'), tuple(step[k] for k in ('goal', 'node', 'actor')))
        self.assertEqual([*argv[1:-1], '<submission.json>', '--source-skill', '$execute-zzzops'], step['command'][2:])
        self.assertEqual(json.loads(path.read_text()), step['submission'])
        self.assertIn('does not authorize takeover', step['action'])



from test_evidence_dag_journeys import DagFixture


class GenericRenewalTests(DagFixture):
    def request(self, work, **changes):
        return {"operation": "renew", "node": work["node"], "lease": work["lease"]["token"],
                "actor": work["bound_actor"], "worker_status": "active", **changes}

    def test_exact_renewal_acknowledges_saved_node_lease_without_portfolio_fetch(self):
        work = self.session.acquire("produce")
        def forbidden(*_args, **_kwargs):
            raise AssertionError("renewal rehydrated unrelated portfolio")
        self.session.portfolio_snapshot = forbidden
        response = self.session.call(100, self.request(work))
        saved = next(v for v in self.payload()[1]["operational"]["leases"] if v["token"] == work["lease"]["token"])
        step = response["next_steps"][0]
        self.assertEqual("renewed", step["kind"])
        self.assertEqual(work["node"], step["node"])
        self.assertEqual((work["bound_actor"], saved["token"], saved["expires_at"]),
                         (step["actor"], step["lease"], step["expires_at"]))

    def test_wrong_renewal_actor_and_failed_provider_save_never_acknowledge(self):
        work = self.session.acquire("produce")
        self.session.call(100, self.request(work))
        before = self.provider.issues[100]["body"]
        denied = self.session.call(100, self.request(work, actor="intruder"), expected=2)
        self.assertRegex(json.dumps(denied), r"(?i)actor|worker|bound")
        self.assertEqual(before, self.provider.issues[100]["body"])
        with mock.patch.object(self.provider, "update_issue", side_effect=ValueError("provider failure")):
            failed = self.session.call(100, self.request(work), expected=2)
        self.assertFalse(any(v.get("kind") == "renewed" for v in failed["next_steps"]))
        self.assertEqual(before, self.provider.issues[100]["body"])

    def test_exact_terminal_retry_retries_local_shutdown_without_durable_rewrite(self):
        work = self.session.acquire("produce")
        request = self.session.submission(work, {"value": "durably accepted"}, "terminal-shutdown")
        stop = mock.Mock(side_effect=[OSError("local shutdown failed"), {}])
        self.session.heartbeat_stop = stop
        response = self.session.call(100, request)
        before = json.dumps((self.provider.issues, self.provider.comments), sort_keys=True)
        self.assertRegex(json.dumps(response), r"(?i)durable.*succeed|shutdown|retry")
        retry = self.session.call(100, request)
        self.assertEqual(2, stop.call_count)
        self.assertEqual(before, json.dumps((self.provider.issues, self.provider.comments), sort_keys=True))
        self.assertNotIn("produce", {s["node"]["node"] for s in retry["next_steps"] if s.get("kind") == "execute"})

if __name__ == '__main__':
    unittest.main()
