"""Actual-package compatibility with Codex's bounded cachebuster output."""

from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "zzzops"
# Helper contract: openai/codex commit
# 9265701b7ff81d83d813eb3d4f6aeb2e0f9a6583, codex-rs/skills/src/assets/
# samples/plugin-creator/scripts/update_plugin_cachebuster.py.
HELPER = os.environ.get("CODEX_PLUGIN_CACHEBUSTER_UPDATER")


class PluginCachebusterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.plugin = self.root / "plugin"
        shutil.copytree(PLUGIN, self.plugin, ignore=shutil.ignore_patterns("__pycache__"))
        self.package = runpy.run_path(str(self.plugin / "zzzops/package.py"))
        self.manifest = self.plugin / ".codex-plugin/plugin.json"

    def update(self, **fields):
        manifest = json.loads(self.manifest.read_text())
        manifest.update(fields)
        self.manifest.write_text(json.dumps(manifest, indent=2) + "\n")

    def status(self):
        return self.package["package_status"]()

    def test_helper_output_preserves_product_version_and_complete_digest(self):
        original = self.status()
        self.assertTrue(original["ok"], original)
        revisions = {original["revision"]}
        for token in ("20260929050007", "release-candidate-2", "a", "0"):
            with self.subTest(token=token):
                version = "0.0.0-dev+codex." + token
                self.update(version=version)
                status = self.status()
                self.assertTrue(status["ok"], status)
                self.assertEqual("0.0.0-dev", status["version"])
                self.assertEqual(version, status["codex_version"])
                self.assertNotIn(status["revision"], revisions)
                revisions.add(status["revision"])
        self.update(description="other manifest content")
        changed = self.status()
        self.assertTrue(changed["ok"], changed)
        self.assertNotIn(changed["revision"], revisions)
        (self.plugin / "zzzops/package.py").write_text("# changed implementation\n")
        self.assertNotEqual(changed["revision"], self.status()["revision"])

    def test_unrelated_or_malformed_versions_and_identity_fail(self):
        for version in (
            "0.0.1+codex.20260929050007", "0.0.1", "0.0.0-dev+other.123",
            "0.0.0-dev+codex.", "0.0.0-dev+codex.A", "0.0.0-dev+codex.a.b",
            "0.0.0-dev+codex.-a", "0.0.0-dev+codex.a-", "0.0.0-dev+codex.a--b",
            "0.0.0-dev+codex.a+b", "0.0.0-dev+codex.１２３", "0.0.0-dev+codex.a\n",
        ):
            with self.subTest(version=version):
                self.update(version=version)
                self.assertFalse(self.status()["ok"])
        self.update(version="0.0.0-dev+codex.123", name="other")
        self.assertFalse(self.status()["ok"])
        self.manifest.write_text("[]")
        self.assertFalse(self.status()["ok"])

    def test_released_product_versions_keep_their_metadata_contract(self):
        manifest = self.plugin / "plugin.json"
        canonical = json.loads(manifest.read_text())
        canonical["version"] = "1.2.3"
        manifest.write_text(json.dumps(canonical))
        for skill in self.package["SHIPPED_SKILLS"]:
            for relative in (f"skills/{skill}/SKILL.md", f"skills/{skill}/agents/openai.yaml"):
                path = self.plugin / relative
                path.write_bytes(self.package["render_skill_metadata"](
                    relative, path.read_bytes(), "1.2.3", "official",
                ))
        for version in ("1.2.3", "1.2.3+codex.release-2"):
            self.update(version=version)
            status = self.status()
            self.assertTrue(status["ok"], status)
            self.assertEqual("1.2.3", status["version"])
        agent = self.plugin / "skills/execute-zzzops/agents/openai.yaml"
        agent.write_text(agent.read_text().replace("[ZzzOps]", "[ZzzOps 9.9.9]", 1))
        self.assertIn("skill discovery metadata", self.status()["detail"])

    def test_cachebuster_does_not_hide_stale_metadata_missing_files_or_symlinks(self):
        self.update(version="0.0.0-dev+codex.123")
        skill = self.plugin / "skills/execute-zzzops/SKILL.md"
        original = skill.read_text()
        skill.write_text(original.replace("v0.0.0-dev", "v9.9.9", 1))
        self.assertIn("skill discovery metadata", self.status()["detail"])
        skill.write_text(original)
        required = self.plugin / "rules/GOAL_SYSTEM.md"
        required.unlink()
        self.assertIn("missing package files", self.status()["detail"])
        required.symlink_to(skill)
        self.assertIn("symlink", self.status()["detail"])

    @unittest.skipUnless(HELPER, "set CODEX_PLUGIN_CACHEBUSTER_UPDATER to run the upstream helper")
    def test_real_upstream_helper_default_and_custom_update(self):
        for arguments in ([], ["--cachebuster", " Release candidate__2 "]):
            subprocess.run([sys.executable, HELPER, str(self.plugin), *arguments], check=True, capture_output=True)
            status = self.status()
            self.assertTrue(status["ok"], status)
            self.assertEqual("0.0.0-dev", status["version"])
        self.assertEqual("0.0.0-dev+codex.release-candidate-2", status["codex_version"])

    def test_public_validation_accepts_cachebuster_and_invalidates_changed_package(self):
        self.update(version="0.0.0-dev+codex.20260929050007")
        repo = self.root / "repo"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        cli = self.plugin / "zzzops/zzzops.py"

        def invoke(payload=None):
            arguments = [sys.executable, str(cli), "--repo", str(repo), "--intent", "inspect",
                         "--source-skill", "$validate-zzzops-installation", "--response", "full"]
            if payload is not None:
                request = self.root / "input.json"
                request.write_text(json.dumps(payload))
                arguments.extend(["--input", str(request)])
            result = subprocess.run(arguments, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            return json.loads(result.stdout)

        first = invoke()
        step = first["next_steps"][0]
        self.assertEqual("installation_validation", step["kind"])
        invoke({**step["submission"], "outcome": "clean"})
        installation = runpy.run_path(str(self.plugin / "zzzops/installation.py"))
        provenance = self.package["package_provenance"]()
        self.assertFalse(installation["validation_status"](repo, provenance)["required"])
        for change in ({"version": "0.0.0-dev+codex.20260929050008"}, {"description": "changed"}):
            self.update(**change)
            status = installation["validation_status"](repo, self.package["package_provenance"]())
            self.assertTrue(status["required"])
            self.assertEqual("package_changed", status["reason"])


if __name__ == "__main__":
    unittest.main()
