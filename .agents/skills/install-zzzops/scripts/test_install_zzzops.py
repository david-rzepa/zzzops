import re
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock
from pathlib import Path
import importlib.util


SCRIPT = Path(__file__).with_name("install_zzzops.py")
SPEC = importlib.util.spec_from_file_location("install_zzzops_under_test", SCRIPT)
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


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
            self.assertIn("installation preview", preview.stdout)
            self.assertIn("goal-management skills", preview.stdout)
            self.assertIn("workflow rules", preview.stdout)
            self.assertIn("blank templates", preview.stdout)
            self.assertIn("No files were changed.", preview.stdout)
            fingerprint = re.search(r"Approval code: ([0-9a-f]+)", preview.stdout).group(1)
            applied = self.run_installer(target, "--apply", "--confirm-plan", fingerprint)
            self.assertEqual(0, applied.returncode, applied.stderr + applied.stdout)
            self.assertIn("ZzzOps is installed.", applied.stdout)
            self.assertNotIn("installation preview", applied.stdout)
            self.assertNotIn("Approval code", applied.stdout)
            self.assertTrue((target / ".zzzops" / "rules" / "INITIALIZATION.md").is_file())
            self.assertTrue((target / ".zzzops" / "rules" / "BACKENDS.md").is_file())
            self.assertTrue((target / ".zzzops" / "rules" / "CONTINUATION.md").is_file())
            self.assertTrue((target / ".agents" / "templates" / "project-goals" / "INIT_PLAN.json").is_file())
            self.assertTrue((target / ".agents" / "skills" / "add-zzzops-goal" / "SKILL.md").is_file())
            self.assertTrue((target / ".claude" / "skills" / "add-zzzops-goal" / "SKILL.md").is_file())
            self.assertTrue((target / ".agents" / "skills" / "execute-zzzops" / "references" / "BRANCH_REVIEW.md").is_file())
            self.assertTrue((target / ".claude" / "skills" / "execute-zzzops" / "references" / "BRANCH_REVIEW.md").is_file())
            self.assertTrue((target / ".agents" / "skills" / "execute-zzzops" / "references" / "SELF_REVIEW.md").is_file())
            self.assertTrue((target / ".claude" / "skills" / "execute-zzzops" / "references" / "SELF_REVIEW.md").is_file())
            self.assertTrue((target / ".zzzops" / ".gitignore").is_file())
            self.assertFalse((target / ".zzzops" / "PROJECT.md").exists())
            self.assertFalse((target / ".zzzops" / "PREFERENCES.json").exists())
            self.assertFalse((target / ".zzzops" / "migration" / "STATE.json").exists())
            self.assertFalse((target / ".zzzops" / "init" / "plan.json").exists())
            portfolio_help = subprocess.run(
                [sys.executable, str(target / ".agents" / "zzzops.py"), "--repo", str(target), "portfolio", "--help"],
                text=True, encoding="utf-8", capture_output=True, check=False,
            )
            self.assertEqual(0, portfolio_help.returncode, portfolio_help.stderr + portfolio_help.stdout)
            self.assertIn("--format {summary,json}", portfolio_help.stdout)
            self.assertIn("--compare", portfolio_help.stdout)
            checkpoint = subprocess.run(
                [sys.executable, str(target / ".agents" / "zzzops.py"), "--repo", str(target), "checkpoint"],
                text=True, encoding="utf-8", capture_output=True, check=False,
            )
            self.assertEqual(2, checkpoint.returncode, checkpoint.stderr + checkpoint.stdout)
            self.assertFalse(json.loads(checkpoint.stdout)["ready"])
            rerun = self.run_installer(target)
            self.assertEqual(0, rerun.returncode, rerun.stderr + rerun.stdout)
            self.assertIn("already up to date", rerun.stdout)

    def test_update_preserves_local_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / ".git").mkdir()
            prefs = target / ".zzzops" / "PREFERENCES.json"
            prefs.parent.mkdir()
            prefs.write_text('{"personal": true}\n', encoding="utf-8")
            preview = self.run_installer(target)
            fingerprint = re.search(r"Approval code: ([0-9a-f]+)", preview.stdout).group(1)
            applied = self.run_installer(target, "--apply", "--confirm-plan", fingerprint)
            self.assertEqual(0, applied.returncode, applied.stderr + applied.stdout)
            self.assertEqual('{"personal": true}\n', prefs.read_text(encoding="utf-8"))

    def test_update_preserves_all_live_state(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / ".git").mkdir()
            state = {
                target / ".zzzops" / "PROJECT.md": b"project\n",
                target / "AGENTS.md": b"project instructions\n",
            }
            for path, data in state.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            preview = self.run_installer(target)
            fingerprint = re.search(r"Approval code: ([0-9a-f]+)", preview.stdout).group(1)
            applied = self.run_installer(target, "--apply", "--confirm-plan", fingerprint)
            self.assertEqual(0, applied.returncode, applied.stderr + applied.stdout)
            for path, data in state.items():
                self.assertEqual(data, path.read_bytes())

    def test_mid_apply_failure_rolls_back_created_and_overwritten_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / ".git").mkdir()
            existing = target / ".agents" / "zzzops.py"
            existing.parent.mkdir()
            original = b"user mechanical override\n"
            existing.write_bytes(original)
            unrelated = target / "keep.txt"
            unrelated.write_bytes(b"untouched\n")
            preview = self.run_installer(target, "--overwrite-mechanical")
            fingerprint = re.search(r"Approval code: ([0-9a-f]+)", preview.stdout).group(1)
            real_write = INSTALLER.atomic_write
            calls = 0

            def fail_second(path, data):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected write failure")
                real_write(path, data)

            arguments = [str(SCRIPT), str(target), "--apply", "--overwrite-mechanical", "--confirm-plan", fingerprint]
            with mock.patch.object(INSTALLER, "atomic_write", side_effect=fail_second), mock.patch.object(sys, "argv", arguments), redirect_stdout(StringIO()):
                with self.assertRaisesRegex(OSError, "injected write failure"):
                    INSTALLER.main()
            self.assertEqual(original, existing.read_bytes())
            self.assertEqual(b"untouched\n", unrelated.read_bytes())

    def test_stale_apply_rejects_without_writing_any_planned_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / ".git").mkdir()
            preview = self.run_installer(target)
            fingerprint = re.search(r"Approval code: ([0-9a-f]+)", preview.stdout).group(1)
            changed = target / ".agents" / "zzzops.py"
            changed.parent.mkdir()
            changed.write_bytes(b"changed after preview\n")
            applied = self.run_installer(target, "--apply", "--confirm-plan", fingerprint)
            self.assertNotEqual(0, applied.returncode)
            self.assertIn("already manages", applied.stdout)
            self.assertEqual(b"changed after preview\n", changed.read_bytes())
            self.assertFalse((target / ".zzzops" / "rules" / "INITIALIZATION.md").exists())
            refreshed = self.run_installer(target)
            self.assertNotEqual(0, refreshed.returncode)
            self.assertIn("Cannot install yet", refreshed.stdout)
            self.assertIn(".agents/zzzops.py", refreshed.stdout)


if __name__ == "__main__":
    unittest.main()
