import importlib.util
import json
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).parent.parent / "plugins" / "zzzops" / "zzzops" / "reservation.py"
SPEC = importlib.util.spec_from_file_location("workflow_reservation", MODULE_PATH)
reservation = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(reservation)


class FakeAdapter:
    repository = "owner/repo"

    def __init__(self):
        self.labels = {}
        self.next_id = 1
        self.revision = 7
        self.on_delete = None

    def goal_revision(self, _goal, require_writable=False):
        return self.revision

    def get_label(self, name):
        label = self.labels.get(name)
        return dict(label) if label else None

    def create_label(self, name, description):
        if name in self.labels:
            return None
        label = {"name": name, "description": description, "node_id": f"L{self.next_id}"}
        self.next_id += 1
        self.labels[name] = label
        return dict(label)

    def delete_label(self, node_id):
        name = next((name for name, label in self.labels.items() if label["node_id"] == node_id), None)
        if name:
            del self.labels[name]
        if self.on_delete:
            self.on_delete(self, name)


class ExactLabelObservationTests(unittest.TestCase):
    """The exact GraphQL observation must authenticate both node and repository."""

    node_id = "LA_kwDOTasXu88AAAAC_0HWUA"

    def adapter(self, response):
        adapter = object.__new__(reservation.GitHubReservationAdapter)
        adapter.repository = "david-rzepa/zzzops"
        adapter._run = lambda arguments: response
        return adapter

    def observed(self, *, node=None, permission="ADMIN", repository="david-rzepa/zzzops",
                 repository_id="R_kgDOTasXuw", issues=True, errors=None, returncode=0):
        data = {"repository": {"id": repository_id, "nameWithOwner": repository,
                               "hasIssuesEnabled": issues, "viewerPermission": permission},
                "node": node}
        body = {"data": data}
        if errors is not None:
            body["errors"] = errors
        return subprocess.CompletedProcess([], returncode, json.dumps(body), "")

    def not_found(self):
        return [{"type": "NOT_FOUND", "path": ["node"],
                 "message": f"Could not resolve to a node with the global id of '{self.node_id}'."}]

    def test_exact_deleted_label_requires_fresh_repository_access(self):
        response = self.observed(errors=self.not_found(), returncode=1)
        try:
            deleted = self.adapter(response).get_label_node(self.node_id)
        except reservation.ReservationProviderError as exc:
            self.fail(f"exact authenticated NOT_FOUND remained unknown: {exc}")
        self.assertIsNone(deleted)
        self.assertIsNone(self.adapter(self.observed()).get_label_node(self.node_id))
        for response in (self.observed(permission="READ"),
                         self.observed(repository="other/repo"),
                         self.observed(repository_id=""),
                         self.observed(issues=False),
                         subprocess.CompletedProcess([], 0, "{}", ""),
                         subprocess.CompletedProcess([], 0, "{malformed", ""),
                         subprocess.CompletedProcess([], 1, "", "NOT_FOUND"),
                         self.observed(errors=[{**self.not_found()[0], "path": ["repository"]}], returncode=1),
                         self.observed(errors=[{**self.not_found()[0], "message": "Could not resolve another node."}], returncode=1),
                         self.observed(errors=[{**self.not_found()[0], "message": "Could not resolve to a node with the global id of 'LA_kwDOTasXu88AAAAC_0VtDA'."}], returncode=1),
                         self.observed(errors=self.not_found() + [{"type": "FORBIDDEN", "path": ["repository"]}], returncode=1)):
            with self.subTest(response=response):
                with self.assertRaises(reservation.ReservationProviderError):
                    self.adapter(response).get_label_node(self.node_id)
        for access in ({"permission": "READ"}, {"repository": "other/repo"},
                       {"repository_id": ""}, {"issues": False}):
            with self.subTest(nonzero_not_found_access=access):
                response = self.observed(**access, errors=self.not_found(), returncode=1)
                with self.assertRaises(reservation.ReservationProviderError):
                    self.adapter(response).get_label_node(self.node_id)

    def test_live_label_requires_exact_type_identity_repository_and_description(self):
        node = {"__typename": "Label", "id": self.node_id, "name": "lease",
                "description": "held", "repository": {"nameWithOwner": "david-rzepa/zzzops"}}
        observed = self.adapter(self.observed(node=node)).get_label_node(self.node_id)
        self.assertEqual({"node_id": self.node_id, "name": "lease", "description": "held"}, observed)
        for change in ({"__typename": "Issue"}, {"id": "other"},
                       {"repository": {"nameWithOwner": "other/repo"}}):
            with self.subTest(change=change):
                with self.assertRaises(reservation.ReservationProviderError):
                    self.adapter(self.observed(node={**node, **change})).get_label_node(self.node_id)


class PhaseLeaseRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.adapter = FakeAdapter()
        self.now = datetime(2026, 9, 17, tzinfo=timezone.utc)
        self.lease = reservation.acquire_phase_lease(
            self.adapter, "owner/repo", 42, "implement", 7, "worker-a", "run-a", 60, self.now,
        )
        self.later = self.now + timedelta(seconds=61)

    def recover(self, **changes):
        arguments = {
            "adapter": self.adapter, "repository": "owner/repo", "goal": 42,
            "phase": "implement", "revision": 7, "observed_owner": "worker-a",
            "observed_run_id": "run-a", "observed_generation": self.lease["generation"],
            "replacement_owner": "worker-b", "replacement_run_id": "run-b",
            "worker_stopped": True, "ttl_seconds": 60, "now": self.later,
        }
        arguments.update(changes)
        return reservation.recover_phase_lease(**arguments)

    def test_expiry_never_mutates_or_reassigns_the_lease(self):
        name = reservation.phase_lease_label_name(42, "implement")
        before = self.adapter.get_label(name)
        outcome = reservation.acquire_phase_lease(
            self.adapter, "owner/repo", 42, "implement", 7, "worker-b", "run-b", 60, self.later,
        )
        self.assertEqual("recovery_required", outcome["outcome"])
        self.assertEqual(before, self.adapter.get_label(name))

    def test_recovery_requires_confirmed_stop_and_exact_observation(self):
        name = reservation.phase_lease_label_name(42, "implement")
        before = self.adapter.get_label(name)
        for worker_stopped in (False, None, "unknown"):
            self.assertEqual(
                "worker_not_confirmed_stopped",
                self.recover(worker_stopped=worker_stopped)["outcome"],
            )
            self.assertEqual(before, self.adapter.get_label(name))
        self.assertEqual("observation_stale", self.recover(observed_generation=99)["outcome"])
        self.assertEqual(before, self.adapter.get_label(name))

    def test_confirmed_recovery_advances_generation(self):
        recovered = self.recover()
        self.assertTrue(recovered["acquired"])
        self.assertEqual("recovered", recovered["outcome"])
        self.assertEqual(self.lease["generation"] + 1, recovered["generation"])
        name = reservation.phase_lease_label_name(42, "implement")
        metadata = reservation.parse_phase_lease_description(self.adapter.get_label(name)["description"])
        self.assertEqual(("worker-b", "run-b"), (metadata["owner"], metadata["run_id"]))

    def test_recovery_preserves_a_concurrent_replacement(self):
        name = reservation.phase_lease_label_name(42, "implement")

        def replace(adapter, deleted_name):
            adapter.on_delete = None
            adapter.create_label(
                deleted_name,
                reservation.phase_lease_description(
                    "owner/repo", 42, "implement", 7, "worker-c", "run-c",
                    int((self.later + timedelta(seconds=60)).timestamp()), 2,
                ),
            )

        self.adapter.on_delete = replace
        outcome = self.recover()
        self.assertEqual("replacement_detected", outcome["outcome"])
        metadata = reservation.parse_phase_lease_description(self.adapter.get_label(name)["description"])
        self.assertEqual("worker-c", metadata["owner"])


class IndependentBatchTests(unittest.TestCase):
    def test_invalid_batch_is_rejected_before_any_item_runs(self):
        applied = []
        outcome = reservation.apply_independent_batch(
            [{"id": "one", "depends_on": []}, {"id": "two", "depends_on": ["one"]}],
            lambda item: applied.append(item["id"]),
        )
        self.assertFalse(outcome["applied"])
        self.assertEqual(["one"], [result["id"] for result in outcome["results"]])
        self.assertEqual("batch_rejected", outcome["results"][0]["result"]["outcome"])
        self.assertEqual([], applied)

        duplicate = reservation.apply_independent_batch(
            [{"id": "same", "depends_on": []}, {"id": "same", "depends_on": []}],
            lambda item: applied.append(item["id"]),
        )
        self.assertFalse(duplicate["applied"])
        self.assertEqual([], applied)

    def test_item_failures_are_recorded_without_stopping_independent_work(self):
        visited = []

        def apply(item):
            visited.append(item["id"])
            if item["id"] == "raises":
                raise RuntimeError("boom")
            return {"ok": item["id"] == "works", "value": item["id"]}

        outcome = reservation.apply_independent_batch(
            [{"id": item_id, "depends_on": []} for item_id in ("fails", "raises", "works")], apply,
        )
        self.assertFalse(outcome["applied"])
        self.assertEqual(["fails", "raises", "works"], visited)
        self.assertEqual(["fails", "raises", "works"], [item["id"] for item in outcome["results"]])
        self.assertIn("RuntimeError: boom", outcome["results"][1]["result"]["error"])
        self.assertTrue(outcome["results"][2]["result"]["ok"])


if __name__ == "__main__":
    unittest.main()
