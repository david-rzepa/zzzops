import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "zzzops.py"
SPEC = importlib.util.spec_from_file_location("zzzops_cli_under_test", SCRIPT)
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


class InstallerCliTests(unittest.TestCase):
    def make_repo(self, directory: str) -> Path:
        target = Path(directory)
        result = subprocess.run(["git", "init", "--quiet", str(target)], text=True, capture_output=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        return target

    def run_installer(self, target: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "install", str(target), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def approval_code(self, preview: subprocess.CompletedProcess[str]) -> str:
        match = re.search(r"Approval code: ([0-9a-f]+)", preview.stdout)
        self.assertIsNotNone(match, preview.stdout)
        return match.group(1)

    def test_clean_install_delivers_tracked_mechanics_without_initializing(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.make_repo(directory)
            preview = self.run_installer(target)
            self.assertEqual(0, preview.returncode, preview.stderr + preview.stdout)
            self.assertIn("installation preview", preview.stdout)
            self.assertIn("tracked project skills", preview.stdout)
            self.assertIn("workflow rules", preview.stdout)
            self.assertIn("blank templates", preview.stdout)
            self.assertIn("No files were changed.", preview.stdout)
            applied = self.run_installer(target, "--apply", self.approval_code(preview))
            self.assertEqual(0, applied.returncode, applied.stderr + applied.stdout)
            self.assertIn("ZzzOps is installed.", applied.stdout)
            self.assertNotIn("installation preview", applied.stdout)
            self.assertNotIn("Approval code", applied.stdout)
            self.assertTrue((target / ".zzzops" / "rules" / "INITIALIZATION.md").is_file())
            self.assertTrue((target / ".agents" / "templates" / "project-goals" / "INIT_PLAN.json").is_file())
            self.assertTrue((target / ".agents" / "skills" / "add-zzzops-goal" / "SKILL.md").is_file())
            self.assertTrue((target / ".claude" / "skills" / "add-zzzops-goal" / "SKILL.md").is_file())
            self.assertTrue((target / ".agents" / "skills" / "execute-zzzops" / "references" / "SELF_REVIEW.md").is_file())
            self.assertTrue((target / ".claude" / "skills" / "execute-zzzops" / "references" / "SELF_REVIEW.md").is_file())
            self.assertFalse((target / ".gitignore").exists())
            self.assertFalse((target / ".zzzops" / "PROJECT.md").exists())
            self.assertFalse((target / ".zzzops" / "PREFERENCES.json").exists())
            portfolio_help = subprocess.run(
                [sys.executable, str(target / ".agents" / "zzzops.py"), "--repo", str(target), "portfolio", "--help"],
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, portfolio_help.returncode, portfolio_help.stderr + portfolio_help.stdout)
            self.assertIn("--format {summary,json}", portfolio_help.stdout)
            checkpoint = subprocess.run(
                [sys.executable, str(target / ".agents" / "zzzops.py"), "--repo", str(target), "checkpoint"],
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            self.assertEqual(2, checkpoint.returncode, checkpoint.stderr + checkpoint.stdout)
            self.assertFalse(json.loads(checkpoint.stdout)["ready"])
            rerun = self.run_installer(target)
            self.assertEqual(0, rerun.returncode, rerun.stderr + rerun.stdout)
            self.assertIn("already up to date", rerun.stdout)

    def test_preview_warns_for_ignored_project_skills_and_binds_ignore_state(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.make_repo(directory)
            ignore = target / ".gitignore"
            ignore.write_text(".agents/\n.claude/\nkeep.local\n", encoding="utf-8")
            preview = self.run_installer(target)
            self.assertEqual(0, preview.returncode, preview.stderr + preview.stdout)
            self.assertIn("Warning: Git ignores", preview.stdout)
            self.assertIn(".agents/", preview.stdout)
            self.assertIn(".claude/", preview.stdout)
            self.assertIn("collaborators", preview.stdout)
            self.assertEqual(".agents/\n.claude/\nkeep.local\n", ignore.read_text(encoding="utf-8"))
            ignore.write_text("keep.local\n", encoding="utf-8")
            stale = self.run_installer(target, "--apply", self.approval_code(preview))
            self.assertNotEqual(0, stale.returncode)
            self.assertIn("target changed", stale.stdout)
            self.assertFalse((target / ".agents" / "zzzops.py").exists())

    def test_preview_warns_when_only_the_agents_control_cli_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.make_repo(directory)
            (target / ".gitignore").write_text(".agents/zzzops.py\n", encoding="utf-8")
            preview = self.run_installer(target)
            self.assertEqual(0, preview.returncode, preview.stderr + preview.stdout)
            self.assertIn("Warning: Git ignores", preview.stdout)
            self.assertIn(".agents/", preview.stdout)
            self.assertNotIn(".claude/", preview.stdout)

    def test_update_preserves_local_preferences_and_live_state(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.make_repo(directory)
            state = {
                target / ".zzzops" / "PREFERENCES.json": b'{"personal": true}\n',
                target / ".zzzops" / "PROJECT.md": b"project\n",
                target / "AGENTS.md": b"project instructions\n",
            }
            for path, data in state.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            preview = self.run_installer(target)
            applied = self.run_installer(target, "--apply", self.approval_code(preview))
            self.assertEqual(0, applied.returncode, applied.stderr + applied.stdout)
            for path, data in state.items():
                self.assertEqual(data, path.read_bytes())

    def test_mid_apply_failure_rolls_back_created_and_overwritten_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.make_repo(directory)
            existing = target / ".agents" / "zzzops.py"
            existing.parent.mkdir()
            original = b"user mechanical override\n"
            existing.write_bytes(original)
            unrelated = target / "keep.txt"
            unrelated.write_bytes(b"untouched\n")
            preview = self.run_installer(target, "--overwrite-mechanical")
            code = self.approval_code(preview)
            real_write = CLI.atomic_write
            calls = 0

            def fail_second(path, data):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected write failure")
                real_write(path, data)

            with mock.patch.object(CLI, "atomic_write", side_effect=fail_second), redirect_stdout(StringIO()):
                with self.assertRaisesRegex(OSError, "injected write failure"):
                    CLI.main(["install", str(target), "--overwrite-mechanical", "--apply", code])
            self.assertEqual(original, existing.read_bytes())
            self.assertEqual(b"untouched\n", unrelated.read_bytes())

    def test_stale_apply_rejects_without_writing_any_planned_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.make_repo(directory)
            preview = self.run_installer(target)
            changed = target / ".agents" / "zzzops.py"
            changed.parent.mkdir()
            changed.write_bytes(b"changed after preview\n")
            applied = self.run_installer(target, "--apply", self.approval_code(preview))
            self.assertNotEqual(0, applied.returncode)
            self.assertIn("already manages", applied.stdout)
            self.assertEqual(b"changed after preview\n", changed.read_bytes())
            self.assertFalse((target / ".zzzops" / "rules" / "INITIALIZATION.md").exists())


if __name__ == "__main__":
    unittest.main()
