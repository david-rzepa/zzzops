from __future__ import annotations

import json
import importlib.util
import runpy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "zzzops"
SHIPPED_SKILLS = {
    "add-zzzops-goal",
    "bootstrap-zzzops-repository",
    "execute-zzzops",
    "migrate-to-zzzops",
    "review-zzzops-policy",
    "review-agentic-engineering",
    "send-zzzops-feedback",
    "suggest-zzzops-work",
    "validate-zzzops-installation",
}
SUPPORT_EMAIL = "zzzops.support@gmail.com"
DEV_INSTALLER = ROOT / ".agents" / "skills" / "install-zzzops-dev" / "scripts" / "install_dev.py"


def load_dev_installer():
    spec = importlib.util.spec_from_file_location("install_zzzops_dev", DEV_INSTALLER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def quoted_yaml_value(data: bytes, field: str) -> str:
    prefix = field + ":"
    line = next(line for line in data.decode("utf-8").splitlines() if line.lstrip().startswith(prefix))
    return json.loads(line.split(":", 1)[1].strip())


class AgentPluginTests(unittest.TestCase):
    def test_skill_provenance_replaces_stale_values_idempotently(self) -> None:
        render = runpy.run_path(str(PLUGIN / "zzzops" / "package.py"))["render_skill_metadata"]
        stale = '---\nname: example\ndescription: "ZzzOps v1.0.0 — official plugin. Purpose"\n---\n'.encode("utf-8")
        expected = "ZzzOps v2.1.0 — official plugin. Purpose"
        rendered = render("skills/example/SKILL.md", stale, "2.1.0", "official")
        self.assertEqual(expected, quoted_yaml_value(rendered, "description"))
        self.assertEqual(rendered, render("skills/example/SKILL.md", rendered, "2.1.0", "official"))

    def test_development_projection_versions_every_skill_description(self) -> None:
        projected = load_dev_installer().development_plugin_files(PLUGIN, "local-20260824-010203")
        manifest_paths = (PLUGIN / "plugin.json", PLUGIN / ".codex-plugin" / "plugin.json")
        for path in manifest_paths:
            self.assertEqual("2.0.0+codex.local-20260824-010203", json.loads(projected[path])["version"])
        for skill in SHIPPED_SKILLS:
            skill_path = PLUGIN / "skills" / skill / "SKILL.md"
            agent_path = PLUGIN / "skills" / skill / "agents" / "openai.yaml"
            self.assertTrue(
                quoted_yaml_value(projected[skill_path], "description").startswith(
                    "ZzzOps v2.0.0-dev — development plugin. "
                ),
                skill,
            )
            self.assertTrue(
                quoted_yaml_value(projected[agent_path], "short_description").startswith(
                    "ZzzOps v2.0.0-dev [development] · "
                ),
                skill,
            )
            self.assertNotIn(b"ZzzOps v2.0.0-dev", skill_path.read_bytes())

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

    def test_package_contains_exactly_the_nine_product_skills(self) -> None:
        actual = {path.name for path in (PLUGIN / "skills").iterdir() if (path / "SKILL.md").is_file()}
        self.assertEqual(SHIPPED_SKILLS, actual)
        self.assertFalse((PLUGIN / "skills" / "run-zzzops-acceptance").exists())

    def test_agentic_coaching_requires_explicit_invocation(self) -> None:
        metadata = (PLUGIN / "skills" / "review-agentic-engineering" / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", metadata)

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

    def test_portal_package_contains_the_legacy_cleanup_tool(self) -> None:
        script = PLUGIN / "scripts" / "cleanup_legacy.py"
        catalog = PLUGIN / "assets" / "legacy_install_fingerprints.json"
        self.assertTrue(script.is_file())
        self.assertTrue(catalog.is_file())
        self.assertIn("--apply", script.read_text(encoding="utf-8"))
        self.assertEqual({"v1.0.0"}, set(json.loads(catalog.read_text(encoding="utf-8"))["releases"]))
        package_module = (PLUGIN / "zzzops" / "package.py").read_text(encoding="utf-8")
        self.assertIn('"scripts/cleanup_legacy.py"', package_module)
        self.assertIn('"assets/legacy_install_fingerprints.json"', package_module)

    def test_published_compliance_disclosures_are_complete(self) -> None:
        privacy = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
        compliance = (ROOT / "docs" / "OPENAI_COMPLIANCE.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        codex_manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))

        for required in (
            SUPPORT_EMAIL,
            "## Data ZzzOps processes",
            "## Why data is processed",
            "## Who receives data",
            "## Retention",
            "## Your choices and controls",
            "GitHub Issues",
            "OpenAI processes",
            "public feedback",
            "no ZzzOps-operated server",
        ):
            self.assertIn(required, privacy)
        self.assertIn("[Privacy policy](PRIVACY.md)", readme)
        self.assertIn("[OpenAI compliance review](docs/OPENAI_COMPLIANCE.md)", readme)
        self.assertIn(SUPPORT_EMAIL, readme)
        self.assertIn("not created, supported, certified, endorsed by, or affiliated with OpenAI", readme)
        self.assertIn("no ZzzOps-operated server, telemetry, advertising, or commerce", readme)
        self.assertIn(SUPPORT_EMAIL, compliance)
        self.assertIn("https://openai.com/policies/developer-apps-terms/", compliance)
        self.assertIn("https://developers.openai.com/plugins/app-guidelines", compliance)
        self.assertIn("## Owner checklist before submission or publication", compliance)
        self.assertIn("GitHub Issues", codex_manifest["interface"]["longDescription"])
        self.assertEqual(["Write"], codex_manifest["interface"]["capabilities"])

    def test_restricted_data_boundary_is_shipped(self) -> None:
        goal_rules = (PLUGIN / "rules" / "GOAL_SYSTEM.md").read_text(encoding="utf-8")
        feedback_skill = (PLUGIN / "skills" / "send-zzzops-feedback" / "SKILL.md").read_text(encoding="utf-8")
        for restricted in (
            "credentials",
            "payment cards",
            "health data",
            "government IDs",
        ):
            self.assertIn(restricted, goal_rules)
            self.assertIn(restricted, feedback_skill)


if __name__ == "__main__":
    unittest.main()
