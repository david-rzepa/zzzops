import importlib.util
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
