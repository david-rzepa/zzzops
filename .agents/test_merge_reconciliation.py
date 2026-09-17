import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "plugins/zzzops/zzzops/merge_reconciliation.py"
SPEC = importlib.util.spec_from_file_location("zzzops_merge_reconciliation", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def goal():
    return {
        "implementation": {
            "target": "dev", "pr": "https://github.com/example/project/pull/9",
            "review": {"status": "pending", "checkpoint": "head-1"},
        },
    }


def pull(**updates):
    value = {
        "merged": True, "merged_at": "2026-09-16T00:00:00Z", "head_oid": "head-1",
        "base_ref": "dev", "merge_commit": "merge-1", "repository": "example/project",
        "checks_verified": True, "review_verified": True,
    }
    value.update(updates)
    return value


class MergeReconciliationTests(unittest.TestCase):
    def test_exact_merged_pr_is_ready_once(self):
        result = MODULE.classify_pr_merge(goal(), pull(), "example/project")
        self.assertEqual(result["status"], "merged_verified")
        self.assertEqual(result["merge_commit"], "merge-1")

    def test_changed_head_never_auto_completes(self):
        result = MODULE.classify_pr_merge(goal(), pull(head_oid="head-2"), "example/project")
        self.assertEqual(result["status"], "merged_stale")
        self.assertIn("reviewed_head_mismatch", result["reasons"])

    def test_unverified_checks_and_review_remain_stale(self):
        result = MODULE.classify_pr_merge(goal(), pull(checks_verified=False, review_verified=False), "example/project")
        self.assertEqual(result["status"], "merged_stale")
        self.assertEqual(set(result["reasons"]), {"required_checks_unverified", "review_evidence_unverified"})

    def test_exact_managed_approval_satisfies_review_evidence(self):
        record = goal()
        record["implementation"]["review"]["status"] = "approved"
        result = MODULE.classify_pr_merge(record, pull(review_verified=False), "example/project")
        self.assertEqual("merged_verified", result["status"])

    def test_open_missing_and_wrong_repository_are_distinct(self):
        self.assertEqual(MODULE.classify_pr_merge(goal(), pull(merged=False), "example/project")["status"], "open")
        self.assertEqual(MODULE.classify_pr_merge(goal(), None, "example/project")["status"], "unavailable")
        result = MODULE.classify_pr_merge(goal(), pull(repository="other/project"), "example/project")
        self.assertIn("repository_mismatch", result["reasons"])

    def test_verified_merge_builds_one_guarded_idempotent_done_transition(self):
        record = goal()
        record.update({"status": "blocked", "revision": 4, "blockers": [{"status": "open", "category": "human-action"}], "claim": {"owner": "agent"}})
        merge = MODULE.classify_pr_merge(record, pull(), "example/project")
        transition = MODULE.build_reconciliation_transition(record, merge, "d" * 64)
        self.assertEqual(transition["expected_revision"], 4)
        self.assertEqual(transition["goal"]["status"], "done")
        self.assertIsNone(transition["goal"]["claim"])
        self.assertEqual(transition["goal"]["implementation"]["review"]["checkpoint"], "merge-1")
        with self.assertRaises(ValueError):
            MODULE.build_reconciliation_transition(record, {"status": "merged_stale"}, "d" * 64)


if __name__ == "__main__":
    unittest.main()
