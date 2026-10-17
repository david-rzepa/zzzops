"""Fast contract tests for bounded, unlocked workspace verification.

The fixture drives the public submit/renew wires.  Command execution is always
mocked: these tests must never wait for the production 300 second default.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import test_evidence_dag_journeys as journeys


z = journeys.z


class VerificationDurationTests(journeys.DagFixture):
    workspace_graph = journeys.WorkspaceAuthorityPublicTests.workspace_graph
    setup_workspace = journeys.WorkspaceAuthorityPublicTests.setup_workspace
    acquire_workspace = journeys.WorkspaceAuthorityPublicTests.acquire_workspace

    def setUp(self):
        super().setUp()
        mutation = (self.add_coordinator_probe
                    if self._testMethodName == "test_distinct_coordinator_operation_completes_while_command_is_running"
                    else None)
        self.setup_workspace(mutate=mutation)
        self.work = self.acquire_workspace("alpha")
        self.counter = 0

    def add_coordinator_probe(self, graph, _allocations):
        graph["nodes"].append(journeys.task("coordinator_probe", ["consent"], role="root"))

    def command(self, label="one"):
        return [sys.executable, "-c", f"print({label!r})"]

    def request(self, identity, *, commands=None, timeout_marker=...):
        request = self.session.submission(
            self.work, {"value": "bounded verification candidate"}, identity
        )
        request["workspace_checks"] = commands or [self.command()]
        request["verification_expectation"] = "passed"
        if timeout_marker is not ...:
            request["verification_timeout_seconds"] = timeout_marker
        return request

    def fake_run(self, expected_timeout, *, returncode=0, callback=None):
        real = subprocess.run

        def run(argv, *args, **kwargs):
            if argv and argv[0] == "git":
                return real(argv, *args, **kwargs)
            self.counter += 1
            self.assertEqual(expected_timeout, kwargs.get("timeout"))
            if callback:
                callback()
            return subprocess.CompletedProcess(argv, returncode)

        return run

    def replace_payload(self, mutate, *, revision_only=False):
        """Apply a synthetic concurrent provider revision during local work."""
        envelope, payload = self.payload()
        changed = copy.deepcopy(payload)
        mutate(changed)
        if not revision_only:
            envelope["payload"] = self.blob(changed)
        envelope["revision"] += 1
        prefix = self.provider.issues[100]["body"].split("<!-- zzzops-goal", 1)[0]
        self.provider.issues[100]["body"] = (
            prefix + "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"
        )

    def test_omitted_timeout_uses_300_seconds_per_command(self):
        request = self.request("default-duration")
        with mock.patch.object(subprocess, "run", side_effect=self.fake_run(300)):
            response = self.session.call(100, request)
        self.assertTrue(response["verification"]["passed"])
        self.assertEqual(1, self.counter)

    def test_positive_finite_timeout_is_passed_exactly_to_every_command(self):
        request = self.request(
            "explicit-duration",
            commands=[self.command("first"), self.command("second")],
            timeout_marker=0.125,
        )
        with mock.patch.object(subprocess, "run", side_effect=self.fake_run(0.125)):
            response = self.session.call(100, request)
        self.assertTrue(response["verification"]["passed"])
        self.assertEqual(2, self.counter)
        proof = self.read_blob(response["verification"]["proof"])
        self.assertEqual(request["workspace_checks"], [row["command"] for row in proof["commands"]])

    def test_invalid_timeout_and_timeout_without_checks_reject_before_execution(self):
        invalid = [True, False, 0, -1, float("nan"), float("inf"), "30", None]
        for index, value in enumerate(invalid):
            with self.subTest(value=value):
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(
                    100, self.request(f"invalid-{index}", timeout_marker=value), expected=2
                )
                self.assertRegex(json.dumps(response), r"(?i)verification|timeout|finite|positive")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        no_checks = self.request("timeout-without-checks", timeout_marker=1)
        no_checks["workspace_checks"] = []
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, no_checks, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)verification|timeout|checks")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertEqual(0, self.counter)

    def test_timeout_is_failed_evidence_and_exact_replay_runs_zero_commands(self):
        request = self.request("bounded-timeout", timeout_marker=2.5)
        real = subprocess.run

        def timeout(argv, *args, **kwargs):
            if argv and argv[0] == "git":
                return real(argv, *args, **kwargs)
            self.counter += 1
            self.assertEqual(2.5, kwargs["timeout"])
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

        with mock.patch.object(subprocess, "run", side_effect=timeout):
            response = self.session.call(100, request)
        proof = self.read_blob(response["next_steps"][0]["proof"])
        self.assertTrue(proof["commands"][0]["timed_out"])
        self.assertFalse(proof["passed"])
        self.assertEqual(response, self.session.call(100, request))
        self.assertEqual(1, self.counter)

    def test_command_runs_without_repository_storage_reservation_and_owner_can_renew(self):
        request = self.request("unlocked-renewal", timeout_marker=10)

        def renew_while_running():
            engine = getattr(self.session, "engine", None)
            if engine is not None:
                self.assertIsNone(engine._storage_reservation)
            renewal = {
                "operation": "renew", "node": self.work["node"],
                "lease": self.work["lease"]["token"], "actor": self.work["bound_actor"],
                "worker_status": "active", "request_id": "renew-during-verification",
            }
            step = self.session.call(100, renewal)["next_steps"][0]
            self.assertEqual("renewed", step["kind"])

        with mock.patch.object(
            subprocess, "run", side_effect=self.fake_run(10, callback=renew_while_running)
        ):
            response = self.session.call(100, request)
        self.assertTrue(response["verification"]["passed"])

    def test_distinct_coordinator_operation_completes_while_command_is_running(self):
        request = self.request("unlocked-distinct-coordinator", timeout_marker=10)
        alternate_control = tempfile.TemporaryDirectory()
        self.addCleanup(alternate_control.cleanup)
        alternate = journeys.TaskSession(
            self.fixture.repo, self.session.project, self.session.runtime,
            self.provider, alternate_control.name,
        )
        probe = alternate.acquire("coordinator_probe")
        completed = []
        clock = [0.0]

        def submit_distinct_operation():
            engine = getattr(self.session, "engine", None)
            if engine is not None:
                self.assertIsNone(engine._storage_reservation)
            response = alternate.finish(
                probe, {"value": "distinct coordinator storage operation completed"},
                "coordinator-operation-during-verification",
            )
            self.assertNotEqual("blocked", response.get("outcome"))
            completed.append(self.produced("coordinator_probe"))

        with mock.patch.object(
            subprocess, "run",
            side_effect=self.fake_run(10, callback=submit_distinct_operation),
        ), mock.patch.object(
            z._workflow.time, "monotonic", side_effect=lambda: clock[0]
        ), mock.patch.object(
            z._workflow.time, "sleep", side_effect=lambda _seconds: clock.__setitem__(0, 11.0)
        ):
            response = self.session.call(100, request)
        self.assertTrue(response["verification"]["passed"])
        self.assertEqual(1, self.counter)
        self.assertEqual(1, len(completed))
        self.assertEqual(completed[0], self.produced("coordinator_probe"))

    def test_unrelated_goal_revision_during_commands_is_revalidated_and_accepted(self):
        request = self.request("unrelated-revision", timeout_marker=10)
        with mock.patch.object(
            subprocess, "run",
            side_effect=self.fake_run(10, callback=lambda: self.replace_payload(lambda _p: None, revision_only=True)),
        ):
            response = self.session.call(100, request)
        self.assertTrue(response["verification"]["passed"])

    def test_expired_lease_at_fresh_finalize_rejects_publication(self):
        request = self.request("expired-at-finalize", timeout_marker=10)

        def expire(payload):
            lease = next(row for row in payload["operational"]["leases"]
                         if row["token"] == self.work["lease"]["token"])
            lease["expires_at"] = 1

        before_results = len(self.provider.updates)
        with mock.patch.object(
            subprocess, "run", side_effect=self.fake_run(10, callback=lambda: self.replace_payload(expire))
        ):
            response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)lease|expired|authority|ownership")
        self.assertEqual(before_results, len(self.provider.updates))
        self.assertEqual(1, self.counter)

    def test_each_substantive_authority_drift_rejects_fresh_finalize(self):
        mutations = {
            "actor": lambda lease: lease.__setitem__("worker", "different-worker"),
            "token": lambda lease: lease.__setitem__("token", "f" * 32),
            "attempt": lambda lease: lease.__setitem__("attempt", "different-attempt"),
            "acquisition": lambda lease: lease["acquisition"].__setitem__("git_commit", "f" * 40),
            "contract": lambda lease: lease["acquisition"].__setitem__("contract", "sha256:" + "f" * 64),
            "inputs": lambda lease: lease.__setitem__("fingerprint", "sha256:" + "f" * 64),
        }
        for name, mutate_lease in mutations.items():
            with self.subTest(drift=name):
                original = copy.deepcopy((self.provider.issues, self.provider.comments))
                before_count = self.counter
                request = self.request("drift-" + name, timeout_marker=4)

                def drift(payload, change=mutate_lease):
                    lease = next(row for row in payload["operational"]["leases"]
                                 if row["token"] == self.work["lease"]["token"])
                    change(lease)

                with mock.patch.object(
                    subprocess, "run", side_effect=self.fake_run(4, callback=lambda: self.replace_payload(drift))
                ):
                    response = self.session.call(100, request, expected=2)
                self.assertRegex(json.dumps(response), r"(?i)lease|actor|acquisition|contract|input|drift|authority")
                self.assertEqual(before_count + 1, self.counter)
                self.provider.issues, self.provider.comments = copy.deepcopy(original)

    def test_policy_and_reviewed_allocation_drift_reject_fresh_finalize(self):
        for name in ("policy", "allocation"):
            with self.subTest(drift=name):
                request = self.request("review-drift-" + name, timeout_marker=4)
                original_project = copy.deepcopy(self.session.project)
                original_provider = copy.deepcopy((self.provider.issues, self.provider.comments))
                before_count = self.counter
                before_updates = len(self.provider.updates)
                before_alpha_results = sum(
                    1 for ref in self.payload()[1]["evidence"]
                    if (artifact := self.read_blob(ref)).get("type") == "result"
                    and artifact.get("content", {}).get("node", {}).get("node") == "alpha"
                )
                drift_evidence = {}

                def drift():
                    if name == "policy":
                        self.session.project["policy"]["reviewed"] = False
                    else:
                        envelope, payload = self.payload()
                        charter_ref, _charter = self.result("charter")
                        positions = [position for position, ref in enumerate(payload["evidence"])
                                     if ref == charter_ref]
                        self.assertEqual(1, len(positions))
                        original_grant = self.read_blob(self.produced("charter", "grant"))
                        grant = copy.deepcopy(original_grant)
                        grant["content"]["allocations"]["alpha"]["owned"].append(
                            "reviewed-allocation-drift.py"
                        )
                        fixture_comments_before = len(self.provider.comments[100])
                        changed_grant = self.blob(grant)
                        charter_result = copy.deepcopy(self.read_blob(charter_ref))
                        charter_result["content"]["outputs"]["grant"] = changed_grant
                        changed_charter = self.blob(charter_result)
                        payload["evidence"][positions[0]] = changed_charter
                        changed_payload = self.blob(payload)
                        envelope["payload"] = changed_payload
                        fixture_comments = self.provider.comments[100][fixture_comments_before:]
                        self.assertEqual(3, len(fixture_comments))
                        self.assertEqual(
                            [changed_grant["hash"], changed_charter["hash"], changed_payload["hash"]],
                            [comment["body"].split("<!-- zzzops-artifact ", 1)[1].split(" -->", 1)[0]
                             for comment in fixture_comments],
                        )
                        envelope["revision"] += 1
                        prefix = self.provider.issues[100]["body"].split("<!-- zzzops-goal", 1)[0]
                        self.provider.issues[100]["body"] = (
                            prefix + "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"
                        )
                        drift_evidence.update(
                            original_grant=original_grant, changed_grant=changed_grant,
                            changed_charter=changed_charter, changed_payload=changed_payload,
                            old_charter=charter_ref,
                            replacement_count=len(positions),
                            comments_after_drift=copy.deepcopy(self.provider.comments),
                        )

                with mock.patch.object(
                    subprocess, "run", side_effect=self.fake_run(4, callback=drift)
                ):
                    response = self.session.call(100, request, expected=2)
                if name == "policy":
                    self.assertRegex(json.dumps(response), r"(?i)policy|review|allocation|authority|drift")
                else:
                    step = response["next_steps"][0]
                    self.assertIn("Stale substantive input/contract/prerequisite", step["reason"])
                    self.assertRegex(step["reason"], r"inspect_charter|consent")
                    self.assertEqual("generic_provenance", step["diagnostic"]["failed_invariant"])
                    self.assertEqual(1, drift_evidence["replacement_count"])
                    changed_grant = self.read_blob(drift_evidence["changed_grant"])
                    expected_grant = copy.deepcopy(drift_evidence["original_grant"])
                    expected_grant["content"]["allocations"]["alpha"]["owned"].append(
                        "reviewed-allocation-drift.py"
                    )
                    self.assertEqual(expected_grant, changed_grant)
                    changed_charter = self.read_blob(drift_evidence["changed_charter"])
                    self.assertEqual(drift_evidence["changed_grant"],
                                     changed_charter["content"]["outputs"]["grant"])
                    self.assertNotEqual(drift_evidence["old_charter"],
                                        drift_evidence["changed_charter"])
                    after_alpha_results = sum(
                        1 for ref in self.payload()[1]["evidence"]
                        if (artifact := self.read_blob(ref)).get("type") == "result"
                        and artifact.get("content", {}).get("node", {}).get("node") == "alpha"
                    )
                    self.assertEqual(before_alpha_results, after_alpha_results)
                    self.assertEqual(drift_evidence["comments_after_drift"], self.provider.comments)
                    self.assertEqual(before_updates, len(self.provider.updates))
                self.assertEqual(before_count + 1, self.counter)
                self.session.project = original_project
                self.provider.issues, self.provider.comments = copy.deepcopy(original_provider)

    def test_goal_closure_during_commands_rejects_fresh_finalize(self):
        request = self.request("closed-at-finalize", timeout_marker=5)
        original_envelope, _payload = self.payload()

        def close_goal():
            envelope = copy.deepcopy(original_envelope)
            envelope["revision"] += 1
            envelope["state"] = "closed"
            prefix = self.provider.issues[100]["body"].split("<!-- zzzops-goal", 1)[0]
            self.provider.issues[100]["body"] = (
                prefix + "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"
            )

        with mock.patch.object(
            subprocess, "run", side_effect=self.fake_run(5, callback=close_goal)
        ):
            response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)closed|lease|authority|state")
        self.assertEqual(1, self.counter)

    def test_local_elapsed_time_gets_a_fresh_bounded_finalize_reservation(self):
        request = self.request("fresh-provider-budget", timeout_marker=600)
        self.session.reservation_adapter = object()
        acquisitions = []
        clock = [10.0]

        def acquire(*args, **kwargs):
            acquisitions.append(clock[0])
            return {"acquired": True, "expires_at": z._workflow.time.time() + 300}

        def advance():
            clock[0] = 410.0

        with mock.patch.object(z, "acquire_storage_lock", side_effect=acquire), \
             mock.patch.object(z, "renew_storage_lock", side_effect=lambda *_a, **_k: {"acquired": True, "expires_at": z._workflow.time.time() + 300}), \
             mock.patch.object(z, "release_storage_lock", return_value={"released": True}), \
             mock.patch.object(z._workflow.time, "monotonic", side_effect=lambda: clock[0]), \
             mock.patch.object(subprocess, "run", side_effect=self.fake_run(600, callback=advance)):
            response = self.session.call(100, request)
        self.assertTrue(response["verification"]["passed"])
        self.assertEqual([10.0, 410.0], acquisitions)

    def test_finalize_reservation_failure_preserves_completed_journal_for_exact_retry(self):
        request = self.request("finalize-reacquire-failures", timeout_marker=7)
        self.session.reservation_adapter = object()
        real_run = subprocess.run
        acquisition_count = 0
        clock = [0.0]

        def acquire(*_args, **_kwargs):
            nonlocal acquisition_count
            acquisition_count += 1
            if acquisition_count in {1, 4} or acquisition_count >= 6:
                return {"acquired": True, "expires_at": 1_000_000_000_000}
            if acquisition_count == 5:
                raise z.ReservationProviderError("synthetic finalize provider timeout")
            return {"acquired": False}

        def advance_clock(_seconds):
            clock[0] = 11.0

        def reject_workspace_rerun(argv, *args, **kwargs):
            if argv and argv[0] == "git":
                return real_run(argv, *args, **kwargs)
            raise AssertionError("completed workspace command reran")

        patches = lambda: (
            mock.patch.object(z, "acquire_storage_lock", side_effect=acquire),
            mock.patch.object(z, "renew_storage_lock", return_value={"acquired": True, "expires_at": 1_000_000_000_000}),
            mock.patch.object(z, "release_storage_lock", return_value={"released": True}),
        )
        before_comments = copy.deepcopy(self.provider.comments)
        before_updates = len(self.provider.updates)
        before_commands = self.counter
        acquisition, renewal, release = patches()
        with acquisition, renewal, release, \
             mock.patch.object(z._workflow.time, "monotonic", side_effect=lambda: clock[0]), \
             mock.patch.object(z._workflow.time, "sleep", side_effect=advance_clock), \
             mock.patch.object(subprocess, "run", side_effect=self.fake_run(7)):
            contention = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(contention), r"(?i)coordinator|reservation|retry")
        self.assertEqual(before_commands + 1, self.counter)
        self.assertEqual(before_comments, self.provider.comments)
        self.assertEqual(before_updates, len(self.provider.updates))

        journals = list(
            (self.fixture.repo / ".git" / "zzzops" / "verification" / "100").glob("*.json")
        )
        self.assertEqual(1, len(journals))
        journal = json.loads(journals[0].read_text())
        self.assertEqual("complete", journal["record"]["status"])
        self.assertEqual(1, len(journal["record"]["results"]))
        self.assertTrue(Path(journal["record"]["results"][0]["log"]).is_file())

        acquisition, renewal, release = patches()
        with acquisition, renewal, release, \
             mock.patch.object(subprocess, "run", side_effect=reject_workspace_rerun):
            provider_timeout = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(provider_timeout), r"(?i)provider|timeout|reservation|retry")
        self.assertEqual(before_commands + 1, self.counter)
        self.assertEqual(before_comments, self.provider.comments)
        self.assertEqual(before_updates, len(self.provider.updates))

        acquisition, renewal, release = patches()
        with acquisition, renewal, release, \
             mock.patch.object(subprocess, "run", side_effect=reject_workspace_rerun):
            replay = self.session.call(100, request)
        self.assertTrue(replay["verification"]["passed"])
        self.assertEqual(before_commands + 1, self.counter)

    def test_changed_timeout_cannot_bypass_a_durable_running_journal(self):
        first = self.request("running-fence", timeout_marker=5)
        original = subprocess.run

        def interrupted(argv, *args, **kwargs):
            if argv and argv[0] == "git":
                return original(argv, *args, **kwargs)
            self.counter += 1
            raise KeyboardInterrupt("synthetic host interruption")

        with mock.patch.object(subprocess, "run", side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            self.session.call(100, first)
        different_id = self.request("different-id", timeout_marker=5)
        changed_timeout = self.request("changed-timeout", timeout_marker=6)
        for attempted in (first, different_id, changed_timeout):
            response = self.session.call(100, attempted)
            self.assertEqual("await_worker", response["next_steps"][0]["kind"])
        self.assertEqual(1, self.counter)

    def test_whole_batch_claim_blocks_identical_and_different_requests_between_commands(self):
        request = self.request(
            "whole-batch", commands=[self.command("first"), self.command("second")], timeout_marker=8
        )
        attempted = []
        alternate_control = tempfile.TemporaryDirectory()
        self.addCleanup(alternate_control.cleanup)
        alternate = journeys.TaskSession(
            self.fixture.repo, self.session.project, self.session.runtime,
            self.provider, alternate_control.name,
        )

        def compete():
            if self.counter != 2:  # Enter on the second command, after one durable result.
                return
            for candidate in (request, self.request("competing-request", timeout_marker=8)):
                response = alternate.call(100, candidate)
                attempted.append(response["next_steps"][0]["kind"])

        with mock.patch.object(subprocess, "run", side_effect=self.fake_run(8, callback=compete)):
            response = self.session.call(100, request)
        self.assertTrue(response["verification"]["passed"])
        self.assertEqual(["await_worker", "await_worker"], attempted)
        self.assertEqual(2, self.counter)

    def test_workspace_mutation_during_unlocked_command_prevents_publication(self):
        request = self.request("tamper-workspace", timeout_marker=3)

        def tamper():
            (self.fixture.repo / "source.py").write_text("def value():\n    return 99\n")

        with mock.patch.object(subprocess, "run", side_effect=self.fake_run(3, callback=tamper)):
            response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)workspace|changed|verification")
        self.assertEqual(1, self.counter)

    def test_completed_journal_log_tampering_rejects_replay_without_reexecution(self):
        request = self.request("tamper-log", timeout_marker=3)
        with mock.patch.object(subprocess, "run", side_effect=self.fake_run(3)), mock.patch.object(
            self.provider, "create_issue_comment", side_effect=RuntimeError("synthetic publication failure")
        ):
            self.session.call(100, request, expected=2)
        logs = list((self.fixture.repo / ".zzzops" / "diagnostics").glob("node-*.log"))
        self.assertEqual(1, len(logs))
        logs[0].write_text("tampered")
        response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)log|changed|integrity")
        self.assertEqual(1, self.counter)

    def test_uncertain_provider_outcome_replays_completed_journal_without_commands(self):
        request = self.request("uncertain-publication", timeout_marker=3)
        original = self.provider.update_issue

        def applied_but_uncertain(number, payload):
            original(number, payload)
            raise z.GoalTransitionProviderError("synthetic lost provider acknowledgement")

        with mock.patch.object(subprocess, "run", side_effect=self.fake_run(3)), mock.patch.object(
            self.provider, "update_issue", side_effect=applied_but_uncertain
        ):
            self.session.call(100, request, expected=None)
        response = self.session.call(100, request)
        self.assertTrue(response["verification"]["passed"])
        self.assertEqual(1, self.counter)


if __name__ == "__main__":
    unittest.main()
