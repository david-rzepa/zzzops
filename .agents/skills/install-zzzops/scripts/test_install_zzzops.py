import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("install_zzzops.py")


class InstallerInitializationTests(unittest.TestCase):
    def run_installer(self, target, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(target), *args],
            text=True, capture_output=True, check=False,
        )

    def test_clean_install_delivers_but_does_not_run_initialization(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / ".git").mkdir()
            preview = self.run_installer(target)
            self.assertEqual(0, preview.returncode, preview.stderr + preview.stdout)
            fingerprint = re.search(r"Plan fingerprint: ([0-9a-f]+)", preview.stdout).group(1)
            applied = self.run_installer(target, "--apply", "--confirm-plan", fingerprint)
            self.assertEqual(0, applied.returncode, applied.stderr + applied.stdout)
            self.assertTrue((target / ".zzzops" / "rules" / "INITIALIZATION.md").is_file())
            self.assertTrue((target / ".zzzops" / "rules" / "BACKENDS.md").is_file())
            self.assertTrue((target / ".zzzops" / "rules" / "HEALTH.md").is_file())
            self.assertTrue((target / ".agents" / "zzzops_health.py").is_file())
            self.assertTrue((target / ".agents" / "templates" / "project-goals" / "INIT_PLAN.json").is_file())
            project = (target / "goals" / "PROJECT.md").read_text(encoding="utf-8")
            self.assertIn('"initialized": false', project)
            self.assertFalse((target / ".zzzops" / "init" / "plan.json").exists())
            self.assertFalse((target / ".zzzops" / "HEALTH_STATE.json").exists())
            self.assertFalse((target / ".zzzops" / "health_preferences.json").exists())
            env = os.environ.copy()
            env["ZZZOPS_USER_CONFIG_DIR"] = str(target / ".test-user-config")
            env["ZZZOPS_MACHINE_STATE_DIR"] = str(target / ".test-machine-state")
            status = subprocess.run(
                [sys.executable, str(target / ".agents" / "zzzops.py"), "--repo", str(target), "health", "status"],
                env=env, text=True, encoding="utf-8", capture_output=True, check=False,
            )
            self.assertEqual(0, status.returncode, status.stderr + status.stdout)
            self.assertFalse(json.loads(status.stdout)["enabled"])
            self.assertFalse((target / ".test-user-config").exists())
            self.assertFalse((target / ".test-machine-state").exists())
            rerun = self.run_installer(target)
            self.assertEqual(0, rerun.returncode, rerun.stderr + rerun.stdout)
            self.assertIn("unchanged=", rerun.stdout)
            self.assertIn("Template diff: none", rerun.stdout)

    def test_update_preserves_local_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / ".git").mkdir()
            prefs = target / ".zzzops" / "PREFERENCES.json"
            prefs.parent.mkdir()
            prefs.write_text('{"personal": true}\n', encoding="utf-8")
            preview = self.run_installer(target)
            fingerprint = re.search(r"Plan fingerprint: ([0-9a-f]+)", preview.stdout).group(1)
            applied = self.run_installer(target, "--apply", "--confirm-plan", fingerprint)
            self.assertEqual(0, applied.returncode, applied.stderr + applied.stdout)
            self.assertEqual('{"personal": true}\n', prefs.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
