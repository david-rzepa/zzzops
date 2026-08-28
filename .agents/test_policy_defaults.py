from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / ".agents" / "policy_default_inventory.py"
SPEC = importlib.util.spec_from_file_location("zzzops_policy_default_inventory_test", MODULE)
assert SPEC and SPEC.loader
inventory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inventory
SPEC.loader.exec_module(inventory)


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
            catalog={"example": {"decision": "new_unique_operational_default", "settings": {}}},
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


if __name__ == "__main__":
    unittest.main()
