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
            backend_rules = (target / ".zzzops" / "rules" / "BACKENDS.md").read_text(encoding="utf-8")
            self.assertIn("Repository plus issue number/URL is identity", backend_rules)
            self.assertIn("compact hidden", backend_rules)
            self.assertTrue((target / ".zzzops" / "rules" / "HEALTH.md").is_file())
            self.assertTrue((target / ".zzzops" / "rules" / "CONTINUATION.md").is_file())
            self.assertTrue((target / ".agents" / "zzzops_health.py").is_file())
            self.assertTrue((target / ".agents" / "templates" / "project-goals" / "INIT_PLAN.json").is_file())
            self.assertTrue((target / ".agents" / "templates" / "project-goals" / "GOAL.md").is_file())
            self.assertFalse((target / ".agents" / "templates" / "project-goals" / "USAGE_LEDGER.md").exists())
            self.assertFalse((target / ".zzzops" / "rules" / "USAGE_ACCOUNTING.md").exists())
            self.assertFalse((target / ".agents" / "skills" / "analyze-zzzops-usage").exists())
            self.assertFalse((target / ".claude" / "skills" / "analyze-zzzops-usage").exists())
            self.assertTrue((target / ".agents" / "skills" / "add-zzzops-goal" / "SKILL.md").is_file())
            self.assertTrue((target / ".claude" / "skills" / "add-zzzops-goal" / "SKILL.md").is_file())
            self.assertTrue((target / ".agents" / "skills" / "execute-zzzops" / "references" / "BRANCH_REVIEW.md").is_file())
            self.assertTrue((target / ".claude" / "skills" / "execute-zzzops" / "references" / "BRANCH_REVIEW.md").is_file())
            for harness in (".agents", ".claude"):
                branch_review = (target / harness / "skills" / "execute-zzzops" / "references" / "BRANCH_REVIEW.md").read_text(encoding="utf-8")
                self.assertIn("each source-changing goal owns one branch and one PR", branch_review)
                self.assertIn("explicit user instruction may authorize a shared PR", branch_review)
            self.assertTrue((target / ".agents" / "skills" / "execute-zzzops" / "references" / "SELF_REVIEW.md").is_file())
            self.assertTrue((target / ".claude" / "skills" / "execute-zzzops" / "references" / "SELF_REVIEW.md").is_file())
            obsolete = "-".join(("add", "zzzops", "todo"))
            self.assertFalse((target / ".agents" / "skills" / obsolete).exists())
            self.assertFalse((target / ".claude" / "skills" / obsolete).exists())
            ignore = (target / ".zzzops" / ".gitignore").read_text(encoding="utf-8")
            self.assertNotIn("USAGE_LEDGER.md", ignore.splitlines())
            self.assertFalse((target / ".zzzops" / "PROJECT.md").exists())
            self.assertFalse((target / ".zzzops" / "USAGE_LEDGER.md").exists())
            self.assertFalse((target / ".zzzops" / "PREFERENCES.json").exists())
            self.assertFalse((target / ".zzzops" / "migration" / "STATE.json").exists())
            self.assertFalse((target / "goals").exists())
            self.assertFalse((target / ".zzzops" / "init" / "plan.json").exists())
            self.assertFalse((target / ".zzzops" / "HEALTH_STATE.json").exists())
            self.assertFalse((target / ".zzzops" / "health_preferences.json").exists())
            portfolio_help = subprocess.run(
                [sys.executable, str(target / ".agents" / "zzzops.py"), "--repo", str(target), "portfolio", "--help"],
                text=True, encoding="utf-8", capture_output=True, check=False,
            )
            self.assertEqual(0, portfolio_help.returncode, portfolio_help.stderr + portfolio_help.stdout)
            self.assertIn("--format {summary,json}", portfolio_help.stdout)
            self.assertIn("--compare", portfolio_help.stdout)
            retired_usage = subprocess.run(
                [sys.executable, str(target / ".agents" / "zzzops.py"), "--repo", str(target), "usage", "ensure"],
                text=True, encoding="utf-8", capture_output=True, check=False,
            )
            self.assertEqual(2, retired_usage.returncode)
            self.assertIn("invalid choice", retired_usage.stderr)
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
            self.assertNotIn("State:", rerun.stdout)

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

    def test_update_preserves_all_live_state(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / ".git").mkdir()
            state = {
                target / ".zzzops" / "PROJECT.md": b"project\n",
                target / "goals" / "items" / "G-example.md": b"goal\n",
            }
            for path, data in state.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            preview = self.run_installer(target)
            fingerprint = re.search(r"Plan fingerprint: ([0-9a-f]+)", preview.stdout).group(1)
            applied = self.run_installer(target, "--apply", "--confirm-plan", fingerprint)
            self.assertEqual(0, applied.returncode, applied.stderr + applied.stdout)
            for path, data in state.items():
                self.assertEqual(data, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
