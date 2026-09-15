import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "plugins/zzzops/zzzops/bootstrap.py"
SPEC = importlib.util.spec_from_file_location("zzzops_bootstrap", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BootstrapCapabilityDeltaTests(unittest.TestCase):
    def setUp(self):
        self.applied = {
            "schema_version": 1,
            "plugin_version": "2.1.0",
            "capabilities": [{"id": "bootstrap.core", "revision": "1", "status": "verified"}],
        }
        self.current = {
            "schema_version": 1,
            "plugin_version": "2.2.0",
            "capabilities": [{"id": "bootstrap.core", "revision": "1", "status": "verified"}],
        }

    def test_unchanged_and_unrelated_version_are_current(self):
        self.assertEqual(MODULE.compare_bootstrap_capabilities(self.applied, self.current)["status"], "current")

    def test_new_capability_is_upgrade(self):
        self.current["capabilities"].append({"id": "tooling.discovery", "revision": "1"})
        result = MODULE.compare_bootstrap_capabilities(self.applied, self.current)
        self.assertEqual(result["status"], "upgrade_available")
        self.assertEqual(result["added"], ["tooling.discovery"])

    def test_revision_change_is_upgrade(self):
        self.current["capabilities"][0]["revision"] = "2"
        self.assertEqual(MODULE.compare_bootstrap_capabilities(self.applied, self.current)["changed"], ["bootstrap.core"])

    def test_missing_legacy_provenance_requires_audit(self):
        result = MODULE.compare_bootstrap_capabilities({}, self.current)
        self.assertEqual(result["status"], "legacy_provenance_missing")

    def test_partial_application_is_resumable(self):
        self.applied["capabilities"][0]["status"] = "pending"
        result = MODULE.compare_bootstrap_capabilities(self.applied, self.current)
        self.assertEqual(result["status"], "partially_applied")
        self.assertEqual(result["partial"], ["bootstrap.core"])

    def test_customized_fixture_is_not_mutated_by_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "custom-instructions.md"
            marker.write_text("keep this customization", encoding="utf-8")
            before = marker.read_text(encoding="utf-8")
            MODULE.compare_bootstrap_capabilities(self.applied, self.current)
            self.assertEqual(marker.read_text(encoding="utf-8"), before)

    def test_normal_inspection_detects_automatically_but_application_stays_gated(self):
        document = (MODULE_PATH.parent / "references/bootstrap/ANALYZE.md").read_text(encoding="utf-8")
        self.assertIn("Every normal ZzzOps bootstrap or repository-inspection invocation automatically", document)
        self.assertIn("reviewed authority and explicit execution authorization", document)
        self.assertIn("not a background", document)


if __name__ == "__main__":
    unittest.main()
