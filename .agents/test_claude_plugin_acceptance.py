"""Regression tests for the reusable Claude installed-cache acceptance harness."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / ".agents" / "claude_plugin_acceptance.py"
EXPECTED_SKILLS = {
    "add-zzzops-goal", "bootstrap-zzzops-repository", "execute-zzzops", "migrate-to-zzzops",
    "review-agentic-engineering", "review-zzzops-policy", "send-zzzops-feedback", "suggest-zzzops-work",
    "validate-zzzops-installation",
}


def load_harness():
    spec = importlib.util.spec_from_file_location("claude_plugin_acceptance", HARNESS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ClaudePluginAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.harness = load_harness()

    def test_inventory_requires_exact_marketplace_plugin_and_skills(self) -> None:
        available = [{
            "pluginId": "zzzops@zzzops", "name": "zzzops", "marketplaceName": "zzzops",
            "version": "2.0.0", "source": "./zzzops", "description": "ZzzOps",
        }]
        self.harness.validate_available(available, "2.0.0")
        details = "Skills (9)  " + ", ".join(sorted(EXPECTED_SKILLS)) + "\n  Agents (0)"
        self.harness.validate_details(details)
        with self.assertRaisesRegex(self.harness.AcceptanceError, "skill inventory"):
            self.harness.validate_details(details.replace("validate-zzzops-installation", "unexpected"))

    def test_install_must_resolve_inside_isolated_cache_with_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            install = config / "plugins" / "cache" / "zzzops" / "zzzops" / "2.0.0"
            (install / "zzzops").mkdir(parents=True)
            (install / "zzzops" / "zzzops.py").write_text("# runtime\n", encoding="utf-8")
            (install / ".claude-plugin").mkdir()
            (install / ".claude-plugin" / "plugin.json").write_text("{}\n", encoding="utf-8")
            record = [{"id": "zzzops@zzzops", "version": "2.0.0", "enabled": True, "installPath": str(install)}]
            self.assertEqual(install.resolve(), self.harness.validate_install(record, config, "2.0.0"))
            record[0]["installPath"] = str(Path(directory) / "source")
            with self.assertRaisesRegex(self.harness.AcceptanceError, "isolated Claude cache"):
                self.harness.validate_install(record, config, "2.0.0")

    def test_release_archive_extraction_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "unsafe.zip"
            with ZipFile(archive, "w") as output:
                output.writestr("../escape", "unsafe")
            with self.assertRaisesRegex(self.harness.AcceptanceError, "unsafe path"):
                self.harness.extract_archive(archive, Path(directory) / "output")


if __name__ == "__main__":
    unittest.main()
