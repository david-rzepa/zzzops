from __future__ import annotations

import json
import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "zzzops"
SKILL_UI = {
    "add-zzzops-goal": ("Add Goal", "Capture one durable project goal safely"),
    "bootstrap-zzzops-repository": ("Bootstrap Repository", "Create or strengthen an agent-ready repository"),
    "execute-zzzops": ("Execute", "Run the primary autonomous ZzzOps goal loop"),
    "migrate-to-zzzops": ("Migrate TODOs", "Discover and migrate repository TODOs safely"),
    "review-agentic-engineering": ("Review Agentic Engineering", "Improve how you work with software agents"),
    "review-zzzops-entropy": ("Review Entropy", "Review recent or full repository entropy"),
    "review-zzzops-policy": ("Review Policy", "Initialize or review project operating policy"),
    "send-zzzops-feedback": ("Send Feedback", "Preview and send privacy-safe ZzzOps feedback"),
    "suggest-zzzops-work": ("Suggest Work", "Audit project gaps and suggest durable work"),
    "validate-zzzops-installation": ("Validate Installation", "Validate one repository after install or upgrade"),
}
SHIPPED_SKILLS = set(SKILL_UI)
SUPPORT_EMAIL = "zzzops.support@gmail.com"


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

        stale_agent = (
            'interface:\n  display_name: "[ZzzOps 1.0.0-dev] Example"\n'
            '  short_description: "ZzzOps v1.0.0 [development] · Purpose"\n'
        ).encode("utf-8")
        rendered_agent = render("skills/example/agents/openai.yaml", stale_agent, "2.1.0", "official")
        self.assertEqual("[ZzzOps] Example", quoted_yaml_value(rendered_agent, "display_name"))
        self.assertEqual("Purpose", quoted_yaml_value(rendered_agent, "short_description"))
        self.assertEqual(
            rendered_agent,
            render("skills/example/agents/openai.yaml", rendered_agent, "2.1.0", "official"),
        )

    def test_canonical_source_identifies_every_skill_as_development(self) -> None:
        package = runpy.run_path(str(PLUGIN / "zzzops" / "package.py"))
        versioned_manifest_paths = (
            PLUGIN / "plugin.json",
            PLUGIN / ".codex-plugin" / "plugin.json",
        )
        for path in versioned_manifest_paths:
            self.assertEqual("0.0.0-dev", json.loads(path.read_text(encoding="utf-8"))["version"])
        claude = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertNotIn("version", claude)
        marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertNotIn("version", marketplace["metadata"])
        self.assertNotIn("version", marketplace["plugins"][0])
        for skill in SHIPPED_SKILLS:
            skill_path = PLUGIN / "skills" / skill / "SKILL.md"
            agent_path = PLUGIN / "skills" / skill / "agents" / "openai.yaml"
            skill_data = skill_path.read_bytes().replace(b"\r\n", b"\n")
            agent_data = agent_path.read_bytes().replace(b"\r\n", b"\n")
            self.assertIn(b"ZzzOps v0.0.0-dev \xe2\x80\x94 development plugin. ", skill_data, skill)
            action, short = SKILL_UI[skill]
            self.assertEqual(f"[ZzzOps 0.0.0-dev] {action}", quoted_yaml_value(agent_data, "display_name"), skill)
            self.assertEqual(short, quoted_yaml_value(agent_data, "short_description"), skill)
        status = package["package_status"]()
        self.assertTrue(status["ok"], status["detail"])
        self.assertEqual("0.0.0-dev", status["version"])

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

    def test_package_contains_exactly_the_ten_product_skills(self) -> None:
        actual = {path.name for path in (PLUGIN / "skills").iterdir() if (path / "SKILL.md").is_file()}
        self.assertEqual(SHIPPED_SKILLS, actual)
        self.assertFalse((PLUGIN / "skills" / "run-zzzops-acceptance").exists())

    def test_all_product_skills_load_shared_communication_contract(self) -> None:
        guide = PLUGIN / "rules" / "COMMUNICATION.md"
        self.assertTrue(guide.is_file(), "the shared communication guide is missing")
        guide_text = guide.read_text(encoding="utf-8")
        for signal in (
            "[policy:documentation_style]",
            "Lead with the outcome",
            "Keep internal machinery internal",
            "Do not hide",
            "progressive detail",
        ):
            self.assertIn(signal, guide_text)
        for skill in SHIPPED_SKILLS:
            text = (PLUGIN / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("../../rules/COMMUNICATION.md", text, skill)

    def test_package_contains_valid_progressively_disclosed_concepts(self) -> None:
        package = runpy.run_path(str(PLUGIN / "zzzops" / "package.py"))
        status = package["package_status"]()
        self.assertTrue(status["ok"], status["detail"])
        self.assertTrue((PLUGIN / "concepts" / "bounded-commitment.md").is_file())
        self.assertTrue((PLUGIN / "zzzops" / "concepts.py").is_file())

    def test_agentic_coaching_requires_explicit_invocation(self) -> None:
        metadata = (PLUGIN / "skills" / "review-agentic-engineering" / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", metadata)

    def test_legacy_installer_surfaces_are_absent(self) -> None:
        for relative in (
            "install.ps1",
            "install.sh",
            "CLAUDE.md",
            ".zzzops/ZZZOPS_LOCK.json",
            ".agents/skills/install-zzzops-dev",
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
