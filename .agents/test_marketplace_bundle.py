"""Regression tests for deterministic OpenAI submission bundles."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / ".github" / "scripts" / "build_marketplace_bundle.py"
SHIPPED_SKILLS = {
    "add-zzzops-goal", "bootstrap-zzzops-repository", "execute-zzzops", "migrate-to-zzzops",
    "review-agentic-engineering", "review-zzzops-policy", "send-zzzops-feedback", "suggest-zzzops-work",
    "validate-zzzops-installation",
}


def quoted_yaml_value(data: bytes, field: str) -> str:
    prefix = field + ":"
    line = next(line for line in data.decode("utf-8").splitlines() if line.lstrip().startswith(prefix))
    return json.loads(line.split(":", 1)[1].strip())


def load_builder():
    spec = importlib.util.spec_from_file_location("build_marketplace_bundle", BUILDER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MarketplaceBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_builder()

    def test_fixed_version_build_is_deterministic_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            notes = "Initial skills-only submission.\n"
            one = self.builder.build_bundles(ROOT, Path(first), "2.0.0", notes)
            two = self.builder.build_bundles(ROOT, Path(second), "2.0.0", notes)
            for key in ("plugin", "submission"):
                self.assertEqual(
                    hashlib.sha256(one[key].read_bytes()).hexdigest(),
                    hashlib.sha256(two[key].read_bytes()).hexdigest(),
                )

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
                    short = quoted_yaml_value(archive.read(f"skills/{skill}/agents/openai.yaml"), "short_description")
                    self.assertTrue(description.startswith("ZzzOps v2.0.0 — official plugin. "), skill)
                    self.assertTrue(short.startswith("ZzzOps v2.0.0 [official] · "), skill)
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


if __name__ == "__main__":
    unittest.main()
