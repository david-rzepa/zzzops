"""Contracts for policy settings retained by the unified phase workflow."""

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "plugins" / "zzzops" / "zzzops" / "policy.py"
PLAN_PATH = ROOT / "plugins" / "zzzops" / "zzzops" / "templates" / "project-goals" / "INIT_PLAN.json"
SPEC = importlib.util.spec_from_file_location("policy_cleanup_subject", POLICY_PATH)
policy = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(policy)


class PolicyCleanupTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    def section(self, identifier):
        return next(item for item in self.plan["policy"]["sections"] if item["id"] == identifier)

    def test_obsolete_continuation_category_is_not_in_current_taxonomy(self):
        self.assertNotIn("execution_continuation", policy.POLICY_SECTION_IDS)
        self.assertNotIn("execution_continuation", [item["id"] for item in self.plan["policy"]["sections"]])

    def test_quality_and_autonomy_defaults_expose_only_active_choices(self):
        self.assertEqual({
            "non_behavioral_only_without_feature_goal", "dead_code", "dynamic_generated_vendor",
        }, set(self.section("code_quality")["settings"]))
        self.assertEqual({
            "requirements_interview", "project_parallel_ceiling", "max_workers", "parallelization",
            "execution_reports", "resource_reservations", "worktree_lifecycle", "refill", "capture_defaults",
        }, set(self.section("autonomy_approval_parallelism")["settings"]))

    def test_customized_worker_resource_constraints_remain_valid(self):
        customized = copy.deepcopy(self.plan["policy"])
        autonomy = next(item for item in customized["sections"] if item["id"] == "autonomy_approval_parallelism")
        autonomy["default_disposition"] = "changed"
        autonomy["settings"]["max_workers"] = 2
        autonomy["settings"]["parallelization"]["threshold_bytes"] = 52428800
        autonomy["settings"]["resource_reservations"]["mode"] = "strict"
        autonomy["settings"]["worktree_lifecycle"]["after_task"] = "retain_clean_for_reuse"
        self.assertEqual([], policy.validate_policy(customized, True))

    def test_required_ci_modes_are_explicit(self):
        for mode in ("inspect_exact_pr_head", "disabled", "existing_only"):
            candidate = copy.deepcopy(self.plan["policy"])
            verification = next(item for item in candidate["sections"] if item["id"] == "verification_testing")
            verification["settings"]["ci_deduplication"]["required_ci"] = mode
            self.assertEqual([], policy.validate_policy(candidate, True))
        invalid = copy.deepcopy(self.plan["policy"])
        verification = next(item for item in invalid["sections"] if item["id"] == "verification_testing")
        verification["settings"]["ci_deduplication"]["required_ci"] = "assume_green"
        self.assertTrue(any("required_ci is invalid" in error for error in policy.validate_policy(invalid, True)))

    def test_removed_knobs_make_an_old_policy_require_review(self):
        stale = copy.deepcopy(self.plan["policy"])
        quality = next(item for item in stale["sections"] if item["id"] == "code_quality")
        quality["settings"]["completion_self_review"] = "required_before_review_or_done"
        autonomy = next(item for item in stale["sections"] if item["id"] == "autonomy_approval_parallelism")
        autonomy["settings"]["claim_ttl_hours"] = 4
        errors = policy.validate_policy(stale, True)
        self.assertTrue(any("code_quality.settings" in error for error in errors))
        self.assertTrue(any("autonomy_approval_parallelism.settings" in error for error in errors))

    def test_adopted_old_default_is_reported_as_update_available(self):
        quality = self.section("code_quality")
        current = policy.policy_default_catalog()["zzzops.policy.code_quality"]
        legacy_content = copy.deepcopy(current["content"])
        legacy_content["settings"]["completion_self_review"] = "required_before_review_or_done"
        quality.pop("default_id")
        quality["decision"] = legacy_content["decision"]
        quality["settings"] = legacy_content["settings"]
        quality["default_provenance"] = {
            "status": "adopted", "default_id": current["id"], "schema_version": 1,
            "source": {"version": "1.0.0", "revision": "a" * 40},
            "digest": policy.policy_content_digest(legacy_content), "snapshot": legacy_content,
        }
        comparison = next(
            item for item in policy.compare_policy_defaults(self.plan["policy"])
            if item["section_id"] == "code_quality"
        )
        self.assertEqual("update_available", comparison["status"])


if __name__ == "__main__":
    unittest.main()
