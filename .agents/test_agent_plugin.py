from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "zzzops"
SHIPPED_SKILLS = {
    "add-zzzops-goal",
    "execute-zzzops",
    "migrate-to-zzzops",
    "review-zzzops-policy",
    "send-zzzops-feedback",
    "suggest-zzzops-work",
}


class AgentPluginTests(unittest.TestCase):
    def test_open_and_codex_manifests_describe_the_same_release(self) -> None:
        open_manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
        codex_manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", open_manifest["$schema"])
        self.assertEqual(
            (open_manifest["name"], open_manifest["version"]),
            (codex_manifest["name"], codex_manifest["version"]),
        )
        self.assertEqual("./skills/", codex_manifest["skills"])

    def test_marketplace_points_to_the_self_contained_package(self) -> None:
        marketplace = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual("zzzops", marketplace["name"])
        entry = marketplace["plugins"][0]
        self.assertEqual("zzzops", entry["name"])
        self.assertEqual({"source": "local", "path": "./plugins/zzzops"}, entry["source"])
        self.assertEqual("AVAILABLE", entry["policy"]["installation"])
        self.assertEqual("ON_USE", entry["policy"]["authentication"])

    def test_package_contains_exactly_the_six_product_skills(self) -> None:
        actual = {path.name for path in (PLUGIN / "skills").iterdir() if (path / "SKILL.md").is_file()}
        self.assertEqual(SHIPPED_SKILLS, actual)
        self.assertFalse((PLUGIN / "skills" / "run-zzzops-acceptance").exists())

    def test_legacy_installer_surfaces_are_absent(self) -> None:
        for relative in (
            "install.ps1",
            "install.sh",
            "CLAUDE.md",
            ".zzzops/ZZZOPS_LOCK.json",
            "plugins/zzzops/zzzops/installer.py",
            "plugins/zzzops/zzzops/install_lock.py",
        ):
            self.assertFalse((ROOT / relative).exists(), relative)


if __name__ == "__main__":
    unittest.main()
