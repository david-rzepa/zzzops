from __future__ import annotations

import importlib.util
import copy
import json
import sys
import unittest
from pathlib import Path

import test_zzzops as fixtures


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / ".agents" / "policy_default_inventory.py"
SPEC = importlib.util.spec_from_file_location("zzzops_policy_default_inventory_test", MODULE)
assert SPEC and SPEC.loader
inventory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inventory
SPEC.loader.exec_module(inventory)

policy = fixtures.zzzops._policy
PLAN = ROOT / "plugins" / "zzzops" / "zzzops" / "templates" / "project-goals" / "INIT_PLAN.json"


class PolicyDefaultInventoryTests(unittest.TestCase):
    def test_repository_boundary_is_complete_and_has_no_hot_default_leakage(self) -> None:
        report = inventory.validate(ROOT)
        boundary = report["boundary"]
        self.assertIn("AGENTS.md", boundary["hot_prompt_paths"])
        self.assertIn(inventory.DEFAULT_CATALOG_PATH, boundary["cold_policy_review_paths"])
        self.assertNotIn("docs/EXECUTION.md", boundary["hot_prompt_paths"])
        self.assertEqual("docs", boundary["public_documentation_root"])
        self.assertEqual("plugins/zzzops/zzzops", boundary["runtime_schema_interpreter_root"])
        self.assertTrue(report["classified_families"])

    def test_new_catalog_value_in_hot_prompt_requires_explicit_classification(self) -> None:
        report = inventory.inventory(
            catalog={"example": {"instructions": "new_unique_operational_default", "configuration": {}}},
            hot_texts={"plugins/zzzops/rules/EXAMPLE.md": "Use new_unique_operational_default."},
        )
        self.assertFalse(report["valid"])
        self.assertEqual("new_unique_operational_default", report["unclassified_catalog_occurrences"][0]["value"])

    def test_known_fallback_wording_is_rejected_even_without_catalog_match(self) -> None:
        report = inventory.inventory(
            catalog={},
            hot_texts={"plugins/zzzops/rules/EXAMPLE.md": "Fallback waits for `done`."},
        )
        self.assertFalse(report["valid"])
        self.assertEqual("branch_done_fallback", report["forbidden_hot_defaults"][0]["family"])

    def test_migration_prompts_do_not_reintroduce_project_wide_release_policy(self):
        paths = [
            'plugins/zzzops/zzzops/references/next_steps/policy-review.md',
            'plugins/zzzops/zzzops/references/bootstrap/ANALYZE.md',
            'plugins/zzzops/skills/execute-zzzops/references/EXECUTE.md',
            'plugins/zzzops/skills/execute-zzzops/references/UNBLOCK.md',
        ]
        stale = ['never_released` stales at first release',
                 'Only an explicitly confirmed never-released project',
                 'stale `never_released` blocks migration pending review',
                 'Migration blockers require `legacy_migration`']
        for path, obsolete in zip(paths, stale):
            with self.subTest(path=path):
                text = (ROOT / path).read_text()
                self.assertNotIn(obsolete, text)
                self.assertIn('contract', text.lower())

    def test_explicit_accept_restores_canonical_adoption_without_value_inference(self) -> None:
        proposed = json.loads(PLAN.read_text(encoding="utf-8"))["policy"]
        adopted = policy.prepare_policy_defaults(ROOT, copy.deepcopy(proposed), None)
        section_id = "workflow_adherence"
        default_id = "zzzops.policy.workflow_adherence"
        catalog = policy.policy_default_catalog()

        customized_proposal = copy.deepcopy(adopted)
        customized = next(item for item in customized_proposal["sections"] if item["id"] == section_id)
        customized["instructions"] += " Temporary reviewed conversion constraint."
        customized["default_disposition"] = "changed"
        customized_policy = policy.prepare_policy_defaults(ROOT, customized_proposal, adopted)
        customized = next(item for item in customized_policy["sections"] if item["id"] == section_id)
        self.assertEqual("customized", customized["default_provenance"]["status"])

        matching_proposal = copy.deepcopy(customized_policy)
        matching = next(item for item in matching_proposal["sections"] if item["id"] == section_id)
        matching.update(copy.deepcopy(catalog[default_id]["content"]))
        still_customized = policy.prepare_policy_defaults(ROOT, matching_proposal, customized_policy)
        matching = next(item for item in still_customized["sections"] if item["id"] == section_id)
        self.assertEqual("customized", matching["default_provenance"]["status"])

        accepting_proposal = copy.deepcopy(customized_policy)
        accepting = next(item for item in accepting_proposal["sections"] if item["id"] == section_id)
        accepting["default_resolution"] = {"action": "accept", "digest": catalog[default_id]["digest"]}
        readopted = policy.prepare_policy_defaults(ROOT, accepting_proposal, customized_policy)
        accepted = next(item for item in readopted["sections"] if item["id"] == section_id)
        provenance = accepted["default_provenance"]
        self.assertEqual({
            "status", "default_id", "schema_version", "source", "digest", "snapshot",
        }, set(provenance))
        self.assertEqual("adopted", provenance["status"])
        self.assertEqual(default_id, provenance["default_id"])
        self.assertEqual(catalog[default_id]["digest"], provenance["digest"])
        self.assertEqual(catalog[default_id]["content"], provenance["snapshot"])
        self.assertEqual(policy.POLICY_DEFAULT_SCHEMA_VERSION, provenance["schema_version"])
        self.assertEqual(policy.machinery_provenance(ROOT), provenance["source"])

        classification = policy.classify_policy_upgrade(None, readopted)
        classified = next(
            item for item in classification["sections"] if item["section_id"] == section_id
        )
        self.assertEqual("adopted", classified["target_provenance"]["status"])
        self.assertEqual("current", classified["target_default_status"])

        changed_catalog = copy.deepcopy(catalog)
        changed_catalog[default_id]["content"]["instructions"] += " A later installed default."
        changed_catalog[default_id]["digest"] = policy.policy_content_digest(
            changed_catalog[default_id]["content"]
        )
        comparison = next(
            item for item in policy.compare_policy_defaults(readopted, changed_catalog)
            if item["section_id"] == section_id
        )
        self.assertEqual("update_available", comparison["status"])


if __name__ == "__main__":
    unittest.main()
