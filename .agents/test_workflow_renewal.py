"""Renewal regressions using real workflow mutations and subprocess deadlines."""
import subprocess
import copy
import contextlib
import io
import json
import sys
import time
import unittest
from pathlib import Path
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
import test_evidence_dag_journeys as dag_fixtures


class GenericRenewalTests(DagFixture):
    def request(self, work, **changes):
        return {"operation": "renew", "node": work["node"], "lease": work["lease"]["token"],
                "actor": work["bound_actor"], "worker_status": "active", **changes}

    payload_from_body = dag_fixtures.GenericStoragePublicTests.payload_from_body

    def test_renewal_retry_before_body_preserves_generated_expiry(self):
        self.renewal_lost_response("before")

    def test_renewal_retry_after_body_preserves_generated_expiry(self):
        self.renewal_lost_response("after")

    def renewal_lost_response(self, boundary):
        work = self.session.acquire("produce")
        request = self.request(work, request_id="exact-renewal-" + boundary)
        attempted = []
        original = self.provider.update_issue
        initial_comments = len(self.provider.comments[100])
        initial_updates = len(self.provider.updates)
        def uncertain(number, payload):
            attempted.append(copy.deepcopy(payload))
            if boundary == "after":
                original(number, payload)
            raise z.GoalTransitionProviderError("lost " + boundary + " renewal body response")
        with mock.patch.object(self.provider, "update_issue", side_effect=uncertain):
            self.session.call(100, request, expected=None)
        self.assertEqual(1, len(attempted), "Fault must reach exactly one actual durable body write")
        proposed = self.payload_from_body(attempted[0]["body"])
        lease = next(item for item in proposed["operational"]["leases"] if item["token"] == work["lease"]["token"])
        with mock.patch.object(z._workflow.time, "time", return_value=lease["expires_at"] - 1):
            response = self.session.call(100, request)
        ack = response["next_steps"][0]
        self.assertEqual("renewed", ack["kind"])
        self.assertEqual(lease["expires_at"], ack["expires_at"], "Retry cannot mint a fresh later expiry")
        saved = next(item for item in self.payload()[1]["operational"]["leases"] if item["token"] == work["lease"]["token"])
        self.assertEqual(lease, saved)
        self.assertEqual(initial_comments + 1, len(self.provider.comments[100]))
        self.assertEqual(initial_updates + 1, len(self.provider.updates))
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, request)
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))

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

    def test_exact_live_owner_can_renew_after_deadline_without_takeover(self):
        work = self.session.acquire("produce")
        before = self.payload()[1]
        lease = next(v for v in before["operational"]["leases"] if v["token"] == work["lease"]["token"])
        with mock.patch.object(z._workflow.time, "time", return_value=lease["expires_at"] + 1):
            response = self.session.call(100, self.request(work, request_id="late-exact-renewal"))
        step = response["next_steps"][0]
        self.assertEqual("renewed", step["kind"])
        self.assertEqual(work["lease"]["token"], step["lease"])
        self.assertGreater(step["expires_at"], lease["expires_at"])
        saved = next(v for v in self.payload()[1]["operational"]["leases"] if v["token"] == work["lease"]["token"])
        self.assertEqual(step["expires_at"], saved["expires_at"])

    def test_expired_unbound_lease_cannot_bind_or_be_renewed(self):
        step = next(v for v in self.session.ready() if v["node"]["node"] == "produce")
        receipt = json.loads(Path(step["policy"]["path"]).read_text())["policy_receipt"]
        request = {**step["start"], "policy_receipt": receipt}
        request.pop("request_id", None)
        acquired = self.session.call(100, request)["next_steps"][0]
        lease = acquired["lease"]
        self.assertIsNone(lease["worker"])
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        bind = {**acquired["bind"], "lease": lease["token"], "actor": "late-worker",
                "selection": lease["selection"], "policy_receipt": receipt}
        bind.pop("request_id", None)
        with mock.patch.object(z._workflow.time, "time", return_value=lease["expires_at"] + 1):
            denied = self.session.call(100, bind, expected=2)
            self.assertRegex(json.dumps(denied), r"(?i)expired|recovery")
            renewal = {"operation": "renew", "node": acquired["node"], "lease": lease["token"],
                       "actor": "late-worker", "worker_status": "active", "request_id": "late-unbound-renewal"}
            self.session.call(100, renewal, expected=2)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_exact_bound_owner_can_relinquish_expired_lease_without_result(self):
        work = self.session.acquire("produce")
        original_portfolio = self.session.portfolio_snapshot
        def forbidden(*_args, **_kwargs):
            raise AssertionError("release hydrated unrelated portfolio")
        self.session.portfolio_snapshot = forbidden
        stop = mock.Mock(return_value={})
        self.session.heartbeat_stop = stop
        request = {"operation": "release", "node": work["node"], "lease": work["lease"]["token"],
                   "actor": work["bound_actor"], "request_id": "exact-expired-release"}
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        denied = {**request, "actor": "intruder", "request_id": "wrong-expired-release"}
        with mock.patch.object(z._workflow.time, "time", return_value=work["lease"]["expires_at"] + 1):
            self.session.call(100, denied, expected=2)
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
            response = self.session.call(100, request)
        self.assertEqual("released", response["next_steps"][0]["kind"])
        self.assertNotIn(work["lease"]["token"],
                         {v["token"] for v in self.payload()[1]["operational"]["leases"]})
        self.assertEqual([], self.payload()[1]["evidence"])
        self.session.portfolio_snapshot = original_portfolio
        self.assertIn("produce", {v["node"]["node"] for v in self.session.ready()})
        self.assertEqual(1, stop.call_count)

    def test_release_replay_after_lost_provider_response_does_not_rewrite(self):
        work = self.session.acquire("produce")
        request = {"operation": "release", "node": work["node"], "lease": work["lease"]["token"],
                   "actor": work["bound_actor"], "request_id": "release-lost-response"}
        original = self.provider.update_issue
        def uncertain(number, payload):
            original(number, payload)
            raise z.GoalTransitionProviderError("lost release response")
        with mock.patch.object(self.provider, "update_issue", side_effect=uncertain):
            self.session.call(100, request, expected=None)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        replay = self.session.call(100, request)
        self.assertEqual("released", replay["next_steps"][0]["kind"])
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_release_replay_retries_failed_local_cleanup_without_rewriting(self):
        work = self.session.acquire("produce")
        request = {"operation": "release", "node": work["node"], "lease": work["lease"]["token"],
                   "actor": work["bound_actor"], "request_id": "release-cleanup-retry"}
        stop = mock.Mock(side_effect=[OSError("local cleanup failed"), {}])
        self.session.heartbeat_stop = stop
        first = self.session.call(100, request)
        self.assertRegex(json.dumps(first), r"(?i)durable.*succeed|cleanup|retry")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        replay = self.session.call(100, request)
        self.assertEqual("released", replay["next_steps"][0]["kind"])
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertEqual(2, stop.call_count)

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
