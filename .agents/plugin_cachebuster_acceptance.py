"""Explicit acceptance against a separately obtained upstream Codex helper."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_plugin_cachebuster as contracts


# Verified upstream source: openai/codex commit
# 9265701b7ff81d83d813eb3d4f6aeb2e0f9a6583, codex-rs/skills/src/assets/
# samples/plugin-creator/scripts/update_plugin_cachebuster.py.
class UpstreamHelperAcceptance(contracts.PluginCachebusterTests):
    helper: Path

    def test_real_upstream_helper_default_and_custom_update(self):
        original = self.status()
        self.assertTrue(original["ok"], original)
        manifest = self.plugin / "plugin.json"
        canonical = manifest.read_bytes()
        skill_metadata = {
            path: path.read_bytes()
            for path in (self.plugin / "skills").rglob("*")
            if path.name in {"SKILL.md", "openai.yaml"}
        }
        revisions = {original["revision"]}
        for arguments in ([], ["--cachebuster", " Release candidate__2 "]):
            subprocess.run(
                [sys.executable, str(self.helper), str(self.plugin), *arguments],
                check=True, capture_output=True, text=True,
            )
            status = self.status()
            self.assertTrue(status["ok"], status)
            self.assertEqual("0.0.0-dev", status["version"])
            self.assertEqual(
                json.loads(self.manifest.read_text())["version"], status["codex_version"],
            )
            self.assertNotIn(status["revision"], revisions)
            revisions.add(status["revision"])
            self.assertEqual(canonical, manifest.read_bytes())
            for path, content in skill_metadata.items():
                self.assertEqual(content, path.read_bytes(), str(path))
        self.assertEqual("0.0.0-dev+codex.release-candidate-2", status["codex_version"])
        self.assert_current_package_validation()


def helper_path(value: str) -> Path:
    path = Path(value).expanduser()
    try:
        path = path.resolve(strict=True)
        if not path.is_file() or path.name != "update_plugin_cachebuster.py":
            raise ValueError("expected a file named update_plugin_cachebuster.py")
        if not path.read_bytes():
            raise ValueError("helper file is empty")
    except (OSError, ValueError) as error:
        raise argparse.ArgumentTypeError(f"upstream helper is unavailable: {error}") from error
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--helper", type=helper_path, required=True,
                        help="Path to the actual trusted upstream update_plugin_cachebuster.py")
    arguments = parser.parse_args()
    UpstreamHelperAcceptance.helper = arguments.helper
    print(f"Upstream helper: {arguments.helper}", flush=True)
    print(f"Helper SHA-256: {hashlib.sha256(arguments.helper.read_bytes()).hexdigest()}", flush=True)
    # Explicit selection avoids running the inherited self-contained contracts
    # again and keeps this external dependency outside ordinary discovery.
    suite = unittest.TestSuite([
        UpstreamHelperAcceptance("test_real_upstream_helper_default_and_custom_update"),
    ])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(f"Upstream acceptance: {result.testsRun} test(s), {len(result.skipped)} skip(s)", flush=True)
    return 0 if result.testsRun == 1 and result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
