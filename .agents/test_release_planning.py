"""Behavioral contracts for repository-scoped release plans and assignments."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "plugins" / "zzzops" / "zzzops" / "releases.py"


def load_subject():
    if not SUBJECT.exists():
        raise AssertionError("release planning requires plugins/zzzops/zzzops/releases.py")
    spec = importlib.util.spec_from_file_location("release_planning_subject", SUBJECT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class MemoryPlanAdapter:
    """Faithful compare-and-swap control-record adapter, including uncertain writes."""

    def __init__(self):
        self.record = None
        self.artifacts = []
        self.uncertain = False
        self.locked = False
        self.lock_calls = []

    def acquire_repository_lock(self, repository, request_id):
        self.lock_calls.append(("acquire", repository, request_id))
        if self.locked: raise ValueError("repository release plan is locked")
        self.locked = True

    def release_repository_lock(self, repository, request_id):
        self.lock_calls.append(("release", repository, request_id))
        self.locked = False

    def read(self, repository):
        return copy.deepcopy(self.record)

    def create_only(self, repository, record):
        if self.record is not None:
            raise ValueError("duplicate control record")
        self.record = copy.deepcopy(record)
        if self.uncertain:
            raise TimeoutError("provider outcome unknown")
        return copy.deepcopy(self.record)

    def compare_exchange(self, repository, expected_revision, record):
        if self.record is None or self.record["revision"] != expected_revision:
            raise ValueError("revision changed")
        self.record = copy.deepcopy(record)
        if self.uncertain:
            raise TimeoutError("provider outcome unknown")
        return copy.deepcopy(self.record)

    def append_artifact(self, repository, artifact):
        if artifact not in self.artifacts:
            self.artifacts.append(copy.deepcopy(artifact))


class ReleasePlanContractTests(unittest.TestCase):
    def setUp(self):
        self.r = load_subject()
        self.plan = self.r.new_release_plan(next_release=1)

    def test_positive_integer_release_identity_and_numeric_order(self):
        for invalid in (True, False, 0, -1, 1.5, "1", None):
            candidate = copy.deepcopy(self.plan)
            candidate["next_release"] = invalid
            with self.subTest(invalid=invalid):
                self.assertTrue(self.r.validate_release_plan(candidate))
        candidate = copy.deepcopy(self.plan)
        candidate["assignments"] = {"7": 10, "8": 2}
        self.assertEqual([2, 10], self.r.open_release_ids(candidate))

    def test_missing_assignment_falls_back_until_membership_freezes(self):
        self.assertEqual(1, self.r.target_release(self.plan, 3))
        frozen = self.r.freeze_membership(self.plan, 1, {1: "a" * 40, 3: "b" * 40})
        self.assertEqual(1, self.r.target_release(frozen, 3))
        self.assertEqual(2, self.r.target_release(frozen, 9))

    def test_frozen_membership_preserves_exact_commits_and_never_reopens(self):
        frozen = self.r.freeze_membership(self.plan, 1, {3: "a" * 40})
        self.assertEqual({"3": "a" * 40}, frozen["releases"]["1"]["members"])
        with self.assertRaisesRegex(ValueError, "frozen|member"):
            self.r.freeze_membership(frozen, 1, {3: "b" * 40, 4: "c" * 40})

    def test_assignment_revision_conflict_never_overwrites(self):
        changed = self.r.assign_release(self.plan, 7, 2, expected_revision=0)
        self.assertEqual(2, changed["assignments"]["7"])
        with self.assertRaisesRegex(ValueError, "revision"):
            self.r.assign_release(changed, 7, 3, expected_revision=0)
        self.assertEqual(2, changed["assignments"]["7"])

    def test_batch_assignment_validates_every_item_before_effects(self):
        original = copy.deepcopy(self.plan)
        with self.assertRaises(ValueError):
            self.r.batch_assign(self.plan, [{"goal": 7, "release": 2}, {"goal": 8, "release": 0}], expected_revision=0)
        self.assertEqual(original, self.plan)
        result = self.r.batch_assign(self.plan, [{"goal": 7, "release": 2}, {"goal": 8, "release": 3}], expected_revision=0)
        self.assertEqual({"7": 2, "8": 3}, result["plan"]["assignments"])
        self.assertEqual(["applied", "applied"], [row["status"] for row in result["items"]])

    def test_control_record_is_deterministic_non_goal_and_create_only(self):
        adapter = MemoryPlanAdapter()
        created = self.r.persist_plan(adapter, "owner/repo", self.plan, expected_revision=None, request_id="create-1")
        self.assertEqual("release-plan", created["kind"])
        self.assertNotIn("goal", created.get("labels", []))
        replay = self.r.persist_plan(adapter, "owner/repo", self.plan, expected_revision=None, request_id="create-1")
        self.assertEqual(created, replay)
        self.assertEqual(["acquire", "release", "acquire", "release"],
                         [row[0] for row in adapter.lock_calls])
        with self.assertRaisesRegex(ValueError, "duplicate|conflict"):
            self.r.persist_plan(adapter, "owner/repo", self.r.assign_release(self.plan, 1, 2, expected_revision=0), expected_revision=None, request_id="create-2")

    def test_uncertain_write_reconciles_exact_state_or_reports_pending(self):
        adapter = MemoryPlanAdapter(); adapter.uncertain = True
        result = self.r.persist_plan(adapter, "owner/repo", self.plan, expected_revision=None, request_id="uncertain")
        self.assertEqual("applied", result["status"])
        adapter = MemoryPlanAdapter(); adapter.uncertain = True
        adapter.create_only = lambda *_args: (_ for _ in ()).throw(TimeoutError("unknown before effect"))
        result = self.r.persist_plan(adapter, "owner/repo", self.plan, expected_revision=None, request_id="pending")
        self.assertEqual("pending", result["status"])

    def test_batch_provider_failure_reports_applied_and_pending_without_overwrite(self):
        adapter = MemoryPlanAdapter()
        self.r.persist_plan(adapter, "owner/repo", self.plan, expected_revision=None, request_id="create")
        original_exchange = adapter.compare_exchange
        calls = 0
        def fail_second(repository, expected_revision, record):
            nonlocal calls
            calls += 1
            if calls == 2: raise TimeoutError("second assignment uncertain")
            return original_exchange(repository, expected_revision, record)
        adapter.compare_exchange = fail_second
        result = self.r.persist_batch_assignments(adapter, "owner/repo",
            [{"goal": 7, "release": 2}, {"goal": 8, "release": 3}],
            expected_revision=0, request_id="batch-1")
        self.assertEqual(["applied", "pending"], [row["status"] for row in result["items"]])
        self.assertEqual(2, adapter.record["assignments"]["7"])
        self.assertNotIn("8", adapter.record["assignments"])

    def test_public_capture_partial_result_preserves_created_goal_for_retry(self):
        result = self.r.capture_assignment_result(
            goal={"number": 91, "url": "https://example/91"}, assignment=None,
            target_release=2, error="provider outcome unknown", request_id="capture-91")
        self.assertEqual("created_pending_assignment", result["status"])
        self.assertEqual(91, result["goal"]["number"])
        self.assertEqual(2, result["pending_assignment"]["release"])
        self.assertEqual("capture-91", result["request_id"])

    def test_github_provider_adapter_uses_locked_create_only_control_record_and_cas(self):
        class GitHubTransport:
            def __init__(self):
                self.issues = []; self.comments = {}; self.labels = {}; self.next_number = 1
                self.lock_operations = []; self.comment_operations = []
            def list_control_issues(self, repository, marker):
                return [copy.deepcopy(row) for row in self.issues if marker in row["body"]]
            def create_issue(self, repository, payload):
                row = {**copy.deepcopy(payload), "number": self.next_number, "state": "open"}
                self.next_number += 1; self.issues.append(row); self.comments[row["number"]] = []
                return copy.deepcopy(row)
            def update_issue(self, repository, number, payload, expected_body_hash):
                row = next(item for item in self.issues if item["number"] == number)
                if self.r.text_hash(row["body"]) != expected_body_hash: raise ValueError("revision changed")
                row.update(copy.deepcopy(payload)); return copy.deepcopy(row)
            def read_comments(self, repository, number): return copy.deepcopy(self.comments[number])
            def append_comment(self, repository, number, body):
                row = {"id": len(self.comments[number]) + 1, "body": body}
                self.comments[number].append(row); self.comment_operations.append((repository, number, body))
                return copy.deepcopy(row)
            def acquire_label_lock(self, repository, name, description):
                self.lock_operations.append(("acquire", repository, name, description))
                if name in self.labels and self.labels[name] != description: raise ValueError("locked")
                self.labels[name] = description
            def release_label_lock(self, repository, name, description):
                self.lock_operations.append(("release", repository, name, description))
                if self.labels.get(name) == description: del self.labels[name]
        transport = GitHubTransport(); transport.r = self.r
        adapter = self.r.GitHubReleasePlanAdapter(transport)
        created = self.r.persist_plan(adapter, "owner/repo", self.plan,
                                      expected_revision=None, request_id="provider-create")
        self.assertEqual("applied", created["status"])
        self.assertEqual(1, len(transport.issues))
        issue = transport.issues[0]
        self.assertIn("zzzops-release-plan", issue["body"])
        self.assertNotIn("zzzops", issue.get("labels", []), "control record must not be schedulable")
        self.assertEqual(["acquire", "release"], [row[0] for row in transport.lock_operations])
        self.assertEqual(1, len(transport.comment_operations), "create must append immutable audit evidence")
        first_audit = transport.comment_operations[0][2]
        changed = self.r.assign_release(created["plan"], 7, 2, expected_revision=0)
        updated = self.r.persist_plan(adapter, "owner/repo", changed,
                                      expected_revision=0, request_id="provider-update")
        self.assertEqual(1, updated["plan"]["revision"])
        self.assertEqual(["acquire", "release", "acquire", "release"],
                         [row[0] for row in transport.lock_operations])
        self.assertEqual(2, len(transport.comment_operations))
        self.assertEqual(first_audit, transport.comments[issue["number"]][0]["body"],
                         "later CAS must preserve prior immutable audit bytes")
        stale = self.r.assign_release(updated["plan"], 8, 3, expected_revision=1)
        with self.assertRaisesRegex(ValueError, "revision"):
            self.r.persist_plan(adapter, "owner/repo", stale,
                                expected_revision=0, request_id="provider-stale")
        duplicate = copy.deepcopy(issue); duplicate["number"] = 2; transport.issues.append(duplicate)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            adapter.read("owner/repo")


if __name__ == "__main__":
    unittest.main()
