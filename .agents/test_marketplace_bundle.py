"""Regression tests for deterministic OpenAI submission bundles."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / ".github" / "scripts" / "build_marketplace_bundle.py"
CLAUDE_BUILDER = ROOT / ".github" / "scripts" / "build_claude_plugin.py"
SKILL_UI = {
    "add-zzzops-goal": ("Add Goal", "Capture one durable project goal safely"),
    "bootstrap-zzzops-repository": ("Bootstrap Repository", "Create or strengthen an agent-ready repository"),
    "execute-zzzops": ("Execute", "Run the primary autonomous ZzzOps goal loop"),
    "migrate-to-zzzops": ("Migrate TODOs", "Discover and migrate repository TODOs safely"),
    "review-agentic-engineering": ("Review Agentic Engineering", "Improve how you work with software agents"),
    "review-zzzops-policy": ("Review Policy", "Initialize or review project operating policy"),
    "send-zzzops-feedback": ("Send Feedback", "Preview and send privacy-safe ZzzOps feedback"),
    "suggest-zzzops-work": ("Suggest Work", "Audit project gaps and suggest durable work"),
    "validate-zzzops-installation": ("Validate Installation", "Validate one repository after install or upgrade"),
}
SHIPPED_SKILLS = set(SKILL_UI)


def quoted_yaml_value(data: bytes, field: str) -> str:
    prefix = field + ":"
    line = next(line for line in data.decode("utf-8").splitlines() if line.lstrip().startswith(prefix))
    return json.loads(line.split(":", 1)[1].strip())


def load_builder(path: Path = BUILDER, name: str = "build_marketplace_bundle"):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MarketplaceBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_builder()
        cls.claude_builder = load_builder(CLAUDE_BUILDER, "build_claude_plugin")

    def test_fixed_version_build_is_deterministic_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            notes = "Initial skills-only submission.\n"
            one = self.builder.build_bundles(ROOT, Path(first), "2.0.0", notes)
            two = self.builder.build_bundles(ROOT, Path(second), "2.0.0", notes)
            self.assertEqual({"plugin", "submission", "claude_plugin"}, set(one))
            for key in ("plugin", "submission", "claude_plugin"):
                self.assertEqual(
                    hashlib.sha256(one[key].read_bytes()).hexdigest(),
                    hashlib.sha256(two[key].read_bytes()).hexdigest(),
                )

            self.assertEqual("zzzops-claude-plugin-v2.0.0.zip", one["claude_plugin"].name)
            with ZipFile(one["claude_plugin"]) as archive:
                names = archive.namelist()
                self.assertIn(".claude-plugin/plugin.json", names)
                self.assertIn("zzzops/zzzops.py", names)
                self.assertNotIn(".claude-plugin/marketplace.json", names)
                packaged_manifest = json.loads(archive.read(".claude-plugin/plugin.json"))
                committed_manifest = json.loads(
                    (ROOT / "plugins" / "zzzops" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
                )
                expected_manifest = {**committed_manifest, "version": "2.0.0"}
                self.assertEqual(expected_manifest, packaged_manifest)
            with ZipFile(one["plugin"]) as archive:
                names = archive.namelist()
                self.assertIn("plugin.json", names)
                self.assertIn(".codex-plugin/plugin.json", names)
                self.assertIn("scripts/cleanup_legacy.py", names)
                self.assertNotIn("skills/run-zzzops-acceptance/SKILL.md", names)
                self.assertIn("zzzops/references/bootstrap/ANALYZE.md", names)
                self.assertIn("zzzops/references/bootstrap/PLAN.md", names)
                self.assertIn("zzzops/references/bootstrap/GREENFIELD.md", names)
                self.assertIn("zzzops/references/bootstrap/BROWNFIELD.md", names)
                self.assertFalse(any("__pycache__" in name or name.endswith((".pyc", ".pyo")) for name in names))
                self.assertEqual("2.0.0", json.loads(archive.read("plugin.json"))["version"])
                self.assertEqual("2.0.0", json.loads(archive.read(".codex-plugin/plugin.json"))["version"])
                for skill in SHIPPED_SKILLS:
                    description = quoted_yaml_value(archive.read(f"skills/{skill}/SKILL.md"), "description")
                    agent = archive.read(f"skills/{skill}/agents/openai.yaml")
                    display = quoted_yaml_value(agent, "display_name")
                    short = quoted_yaml_value(agent, "short_description")
                    self.assertTrue(description.startswith("ZzzOps v2.0.0 — official plugin. "), skill)
                    action, expected_short = SKILL_UI[skill]
                    self.assertEqual(f"[ZzzOps] {action}", display, skill)
                    self.assertEqual(expected_short, short, skill)
                for name in (
                    "assets/composer-icon-dark.png", "assets/composer-icon.png",
                    "assets/logo-dark.png", "assets/logo.png",
                ):
                    packaged = archive.read(name)
                    self.builder.validate_portal_png(name, packaged)
                    self.assertEqual((ROOT / "plugins" / "zzzops" / name).read_bytes(), packaged)

            with ZipFile(one["submission"]) as archive:
                names = set(archive.namelist())
                self.assertEqual({
                    "ATTESTATIONS.md", "LISTING.md", "RELEASE_NOTES.md", "TEST_CASES.md",
                    "assets/composer-icon-dark.png", "assets/composer-icon.png",
                    "assets/logo-dark.png", "assets/logo.png", "manifest.json", "submission.json",
                }, names)
                submission = json.loads(archive.read("submission.json"))
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual("skills_only", submission["submission_type"])
                self.assertEqual("2.0.0", submission["version"])
                self.assertLessEqual(len(submission["listing"]["short_description"]), 30)
                self.assertEqual("https://github.com/david-rzepa/zzzops", submission["listing"]["website_url"])
                self.assertGreaterEqual(len(submission["tests"]["positive"]), 5)
                self.assertGreaterEqual(len(submission["tests"]["negative"]), 3)
                self.assertEqual(
                    hashlib.sha256(one["plugin"].read_bytes()).hexdigest(),
                    submission["plugin_archive"]["sha256"],
                )
                self.assertEqual("2.0.0", manifest["version"])
                self.assertEqual(
                    hashlib.sha256(archive.read("submission.json")).hexdigest(),
                    manifest["files"]["submission.json"],
                )

    def test_invalid_version_or_incomplete_sources_fail_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaisesRegex(self.builder.BundleError, "version"):
                self.builder.build_bundles(ROOT, output, "latest", "notes")
            self.assertEqual([], list(output.iterdir()))
        with self.assertRaisesRegex(self.builder.BundleError, "secret-like"):
            self.builder.scan_for_secrets("config.txt", b"OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz")
        image = (ROOT / "plugins" / "zzzops" / "assets" / "logo.png").read_bytes()
        with self.assertRaisesRegex(self.builder.BundleError, "not a PNG"):
            self.builder.validate_portal_png("assets/logo.png", image.replace(b"\r\n", b"\n"))
        with self.assertRaisesRegex(self.builder.BundleError, "truncated|checksum|decoded"):
            self.builder.validate_portal_png("assets/logo.png", image[:-20])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "plugins" / "zzzops", root / "plugins" / "zzzops")
            manifest_path = root / "plugins" / "zzzops" / "plugin.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["version"] = "2.0.0"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(self.builder.BundleError, "canonical development manifest"):
                self.builder.plugin_files(root, "2.0.0")

    def test_stale_release_output_is_rejected_before_any_partial_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "marketplace"
            output.mkdir()
            stale = output / "zzzops-claude-plugin-v1.9.0.zip"
            stale.write_bytes(b"stale")
            with self.assertRaisesRegex(self.builder.BundleError, "output directory must be empty"):
                self.builder.build_bundles(ROOT, output, "2.0.0", "notes")
            self.assertEqual({stale.name}, {path.name for path in output.iterdir()})

    def test_release_validation_rejects_missing_divergent_and_invalid_archives(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(self.builder.BundleError, "missing or stale"):
                self.builder.validate_release_artifacts(
                    Path(directory), {"required.zip": ({"file": b"expected"}, "required")},
                )
        divergent = self.builder.zip_bytes({"file": b"observed"})
        with self.assertRaisesRegex(self.builder.BundleError, "content mismatch"):
            self.builder.validate_archive(divergent, {"file": b"expected"}, "Claude plugin")
        with self.assertRaisesRegex(self.builder.BundleError, "not a valid ZIP"):
            self.builder.validate_archive(b"invalid", {}, "Claude plugin")

    def test_claude_marketplace_is_derived_from_the_canonical_plugin(self) -> None:
        files = self.builder.claude_marketplace_files(ROOT, "2.0.0")
        manifest = json.loads(files["zzzops/.claude-plugin/plugin.json"])
        marketplace = json.loads(files[".claude-plugin/marketplace.json"])

        self.assertEqual("zzzops", manifest["name"])
        self.assertEqual("2.0.0", manifest["version"])
        self.assertEqual("zzzops", marketplace["name"])
        self.assertEqual(manifest["description"], marketplace["metadata"]["description"])
        self.assertEqual("2.0.0", marketplace["metadata"]["version"])
        self.assertEqual("./zzzops", marketplace["plugins"][0]["source"])
        self.assertEqual("2.0.0", marketplace["plugins"][0]["version"])
        self.assertEqual(manifest["keywords"], marketplace["plugins"][0]["keywords"])
        self.assertEqual("development", marketplace["plugins"][0]["category"])
        self.assertEqual(
            ["agentic-engineering", "coding-agents", "repository-bootstrap"],
            marketplace["plugins"][0]["tags"],
        )

        canonical = self.builder.plugin_files(ROOT, "2.0.0")
        for relative, content in canonical.items():
            self.assertEqual(content, files[f"zzzops/{relative}"], relative)

    def test_committed_claude_marketplace_targets_the_canonical_plugin_tree(self) -> None:
        canonical = json.loads((ROOT / "plugins" / "zzzops" / "plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        manifest = json.loads(
            (ROOT / "plugins" / "zzzops" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )

        self.assertEqual("./plugins/zzzops", marketplace["plugins"][0]["source"])
        self.assertEqual(canonical["name"], marketplace["name"])
        self.assertEqual(canonical["author"], marketplace["owner"])
        self.assertEqual(
            {"description": canonical["description"], "version": canonical["version"]},
            marketplace["metadata"],
        )
        self.assertEqual(canonical["name"], marketplace["plugins"][0]["name"])
        self.assertEqual(canonical["description"], marketplace["plugins"][0]["description"])
        self.assertEqual(canonical["version"], marketplace["plugins"][0]["version"])
        self.assertEqual(canonical["name"], manifest["name"])
        for field in ("version", "description", "author", "homepage", "repository", "license", "keywords"):
            self.assertEqual(canonical[field], manifest[field], field)

    def test_public_discovery_metadata_keeps_one_truthful_positioning(self) -> None:
        canonical = json.loads((ROOT / "plugins" / "zzzops" / "plugin.json").read_text(encoding="utf-8"))
        codex = json.loads(
            (ROOT / "plugins" / "zzzops" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        claude = json.loads(
            (ROOT / "plugins" / "zzzops" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        claude_marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        openai = json.loads((ROOT / "marketplace" / "listing.json").read_text(encoding="utf-8"))
        readme_opening = (ROOT / "README.md").read_text(encoding="utf-8")[:1200].casefold()

        expected_keywords = [
            "agentic-engineering", "coding-agents", "autonomous-development", "repository-bootstrap",
            "goal-management", "github-issues", "codex", "claude-code",
        ]
        self.assertEqual("Agentic engineering with durable goals for autonomous coding agents", canonical["description"])
        self.assertEqual(expected_keywords, canonical["keywords"])
        for manifest in (codex, claude):
            self.assertEqual(canonical["description"], manifest["description"])
            self.assertEqual(expected_keywords, manifest["keywords"])

        entry = claude_marketplace["plugins"][0]
        self.assertEqual(expected_keywords, entry["keywords"])
        self.assertEqual("development", entry["category"])
        self.assertEqual(["agentic-engineering", "coding-agents", "repository-bootstrap"], entry["tags"])
        self.assertEqual("Agentic engineering goals", openai["listing"]["short_description"])
        for phrase in ("agentic engineering", "autonomous coding agents", "repository bootstrapping"):
            self.assertIn(phrase, openai["listing"]["long_description"].casefold())
        for phrase in ("agentic-engineering", "autonomous coding agents", "bootstrap repositories"):
            self.assertIn(phrase, readme_opening)

    def test_claude_generation_rejects_missing_or_invalid_canonical_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "plugins" / "zzzops", root / "plugins" / "zzzops")
            (root / "plugins" / "zzzops" / "skills" / "add-zzzops-goal" / "SKILL.md").unlink()
            with self.assertRaisesRegex(self.builder.BundleError, "skill discovery metadata"):
                self.builder.claude_marketplace_files(root, "2.0.0")
        with self.assertRaisesRegex(self.builder.BundleError, "version"):
            self.builder.claude_marketplace_files(ROOT, "latest")

    def test_claude_marketplace_writer_is_deterministic_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            self.claude_builder.write_marketplace(ROOT, first, "2.0.0")
            self.claude_builder.write_marketplace(ROOT, second, "2.0.0")
            first_files = {
                path.relative_to(first).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in first.rglob("*") if path.is_file()
            }
            second_files = {
                path.relative_to(second).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in second.rglob("*") if path.is_file()
            }
            self.assertEqual(first_files, second_files)
            with self.assertRaisesRegex(self.builder.BundleError, "must not already exist"):
                self.claude_builder.write_marketplace(ROOT, first, "2.0.0")
            with mock.patch.object(
                self.claude_builder.bundles,
                "claude_marketplace_files",
                return_value={"../escape": b"unsafe"},
            ):
                with self.assertRaisesRegex(self.builder.BundleError, "unsafe generated path"):
                    self.claude_builder.write_marketplace(ROOT, Path(directory) / "unsafe", "2.0.0")


if __name__ == "__main__":
    unittest.main()
