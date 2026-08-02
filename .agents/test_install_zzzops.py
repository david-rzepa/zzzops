import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_VALIDATION = ROOT / ".github" / "scripts" / "require_validation.py"
sys.path.insert(0, str(ROOT / ".agents" / "zzzops"))
import installer as installer_engine  # noqa: E402


def available_installers() -> dict[str, tuple[str, Path]]:
    installers: dict[str, tuple[str, Path]] = {}
    powershell = shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe")
    if powershell:
        installers["PowerShell"] = (powershell, ROOT / "install.ps1")
    bash = None if os.name == "nt" else shutil.which("bash")
    if shutil.which("git") and not bash:
        git = Path(shutil.which("git")).resolve()
        candidate = git.parents[1] / "usr" / "bin" / "bash.exe"
        if candidate.is_file():
            bash = str(candidate)
    if bash:
        installers["Bash"] = (bash, ROOT / "install.sh")
    return installers


class NativeInstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.installers = available_installers()
        if not cls.installers:
            raise unittest.SkipTest("PowerShell and Bash are unavailable")
        expected = {name for name in os.environ.get("ZZZOPS_EXPECT_INSTALLERS", "").split(",") if name}
        missing = expected - set(cls.installers)
        if missing:
            raise AssertionError("Required native installers are unavailable: " + ", ".join(sorted(missing)))

    def make_repo(self, directory: str) -> Path:
        target = Path(directory)
        result = subprocess.run(["git", "init", "--quiet", str(target)], text=True, capture_output=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        subprocess.run(["git", "-C", str(target), "config", "user.email", "installer@test.invalid"], check=True)
        subprocess.run(["git", "-C", str(target), "config", "user.name", "Installer Test"], check=True)
        return target

    def command(self, installer: tuple[str, Path], target: Path, *options: str) -> list[str]:
        runtime, script = installer
        if script.suffix == ".ps1":
            translated = {"--dry-run": "-DryRun", "--yes": "-Yes"}
            return [runtime, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), str(target),
                    *(translated[option] for option in options)]
        return [runtime, str(script), str(target), *options]

    def environment(self, installer: tuple[str, Path]) -> dict[str, str]:
        environment = dict(os.environ)
        if os.name == "nt" and installer[1].suffix == ".sh":
            git_root = Path(installer[0]).resolve().parents[2]
            environment["PATH"] = os.pathsep.join(
                [str(git_root / "usr" / "bin"), str(git_root / "mingw64" / "bin"), environment.get("PATH", "")]
            )
        return environment

    def run_installer(self, installer, target: Path, *options: str, answer: str | None = None):
        return subprocess.run(
            self.command(installer, target, *options), input=answer, text=True,
            encoding="utf-8", errors="replace", capture_output=True, check=False,
            env=self.environment(installer), timeout=60,
        )

    def tracked_machinery(self, target: Path) -> list[str]:
        return subprocess.run(
            ["git", "-C", str(target), "ls-files", "--", ".agents/zzzops", ".agents/skills", ".claude/skills", ".zzzops/rules"],
            text=True, encoding="utf-8", capture_output=True, check=True,
        ).stdout.splitlines()

    def test_disposable_install_reconstructs_and_ignores_exact_roots(self):
        locks = []
        for name, installer in self.installers.items():
            with self.subTest(installer=name), tempfile.TemporaryDirectory() as directory:
                target = self.make_repo(directory)
                preview = self.run_installer(installer, target, "--dry-run")
                self.assertEqual(0, preview.returncode, preview.stderr + preview.stdout)
                self.assertIn("Operation: fresh install", preview.stdout)
                self.assertIn("No files or Git index entries were changed", preview.stdout)
                self.assertFalse((target / ".agents").exists())

                cancelled = self.run_installer(installer, target, answer="\n")
                self.assertEqual(0, cancelled.returncode, cancelled.stderr + cancelled.stdout)
                self.assertIn("cancelled", cancelled.stdout)
                self.assertFalse((target / ".agents").exists())

                installed = self.run_installer(installer, target, "--yes")
                self.assertEqual(0, installed.returncode, installed.stderr + installed.stdout)
                lock = json.loads((target / ".zzzops" / "ZZZOPS_LOCK.json").read_text(encoding="utf-8"))
                locks.append(lock)
                self.assertTrue((target / ".agents" / "zzzops" / "installer.py").is_file())
                self.assertTrue((target / ".claude" / "skills" / "execute-zzzops" / "SKILL.md").is_file())
                root_ignore = (target / ".gitignore").read_text(encoding="utf-8")
                self.assertIn("/.agents/zzzops/", root_ignore)
                self.assertIn("/.agents/skills/execute-zzzops/", root_ignore)
                self.assertIn("/.claude/skills/execute-zzzops/", root_ignore)
                self.assertIn("/.zzzops/rules/", root_ignore)
                self.assertNotIn("/.agents/\n", root_ignore)
                self.assertEqual([], self.tracked_machinery(target))
                self.assertEqual([], subprocess.run(
                    ["git", "-C", str(target), "status", "--short", "--untracked-files=all", "--", ".agents", ".claude", ".zzzops/rules"],
                    text=True, encoding="utf-8", capture_output=True, check=True,
                ).stdout.splitlines())

                scratch = target / ".zzzops" / "init" / "historical-transition.json"
                scratch.parent.mkdir(parents=True)
                scratch.write_text("preserve me\n", encoding="utf-8")
                changed = target / ".agents" / "zzzops" / "zzzops.py"
                changed.write_text("locally divergent\n", encoding="utf-8")
                repair = self.run_installer(installer, target, "--dry-run")
                self.assertEqual(0, repair.returncode, repair.stderr + repair.stdout)
                self.assertIn("Operation: repair", repair.stdout)
                self.assertEqual("locally divergent\n", changed.read_text(encoding="utf-8"))
                repaired = self.run_installer(installer, target, "--yes")
                self.assertEqual(0, repaired.returncode, repaired.stderr + repaired.stdout)
                self.assertNotEqual("locally divergent\n", changed.read_text(encoding="utf-8"))
                self.assertEqual("preserve me\n", scratch.read_text(encoding="utf-8"))
                self.assertEqual(0, subprocess.run(
                    ["git", "-C", str(target), "check-ignore", "--quiet", "--", ".zzzops/init/historical-transition.json"],
                    check=False,
                ).returncode)

                missing = target / ".agents" / "zzzops" / "policy.py"
                missing.unlink()
                partial = self.run_installer(installer, target, "--yes")
                self.assertEqual(0, partial.returncode, partial.stderr + partial.stdout)
                self.assertTrue(missing.is_file())
                reinstall = self.run_installer(installer, target, "--dry-run")
                self.assertEqual(0, reinstall.returncode, reinstall.stderr + reinstall.stdout)
                self.assertIn("Operation: reinstall", reinstall.stdout)
        self.assertTrue(locks)
        self.assertEqual(1, len({json.dumps(lock, sort_keys=True) for lock in locks}))

    def test_tracked_machinery_cleanup_requires_exact_consent_and_clean_index(self):
        for name, installer in self.installers.items():
            with self.subTest(installer=name), tempfile.TemporaryDirectory() as directory:
                target = self.make_repo(directory)
                installed = self.run_installer(installer, target, "--yes")
                self.assertEqual(0, installed.returncode, installed.stderr + installed.stdout)
                subprocess.run(["git", "-C", str(target), "add", ".gitignore", ".zzzops/.gitignore", ".zzzops/ZZZOPS_LOCK.json"], check=True)
                subprocess.run(["git", "-C", str(target), "add", "-f", ".agents/zzzops", ".agents/skills", ".claude/skills", ".zzzops/rules"], check=True)
                subprocess.run(["git", "-C", str(target), "commit", "--quiet", "-m", "legacy tracked install"], check=True)
                tracked_before = self.tracked_machinery(target)

                preview = self.run_installer(installer, target, "--dry-run")
                self.assertEqual(0, preview.returncode, preview.stderr + preview.stdout)
                self.assertIn("Tracked ZzzOps machinery requires explicit index cleanup", preview.stdout)
                self.assertIn(".agents/zzzops/zzzops.py", preview.stdout)
                self.assertEqual(tracked_before, self.tracked_machinery(target))

                declined = self.run_installer(installer, target, answer="\n")
                self.assertEqual(0, declined.returncode, declined.stderr + declined.stdout)
                self.assertIn("tracked files, working files, and ignore rules were unchanged", declined.stdout)
                self.assertEqual(tracked_before, self.tracked_machinery(target))

                cleaned = self.run_installer(installer, target, "--yes")
                self.assertEqual(0, cleaned.returncode, cleaned.stderr + cleaned.stdout)
                self.assertEqual([], self.tracked_machinery(target))
                self.assertTrue((target / ".agents" / "zzzops" / "zzzops.py").is_file())
                self.assertTrue((target / ".claude" / "skills" / "execute-zzzops" / "SKILL.md").is_file())

                subprocess.run(["git", "-C", str(target), "reset", "--quiet", "HEAD", "--", "."], check=True)
                (target / ".agents" / "zzzops" / "zzzops.py").write_text("staged divergence\n", encoding="utf-8")
                subprocess.run(["git", "-C", str(target), "add", "-f", ".agents/zzzops/zzzops.py"], check=True)
                blocked = self.run_installer(installer, target, "--yes")
                self.assertNotEqual(0, blocked.returncode, blocked.stderr + blocked.stdout)
                self.assertIn("staged changes overlap", blocked.stdout)
                self.assertIn(".agents/zzzops/zzzops.py", subprocess.run(
                    ["git", "-C", str(target), "diff", "--cached", "--name-only"],
                    text=True, encoding="utf-8", capture_output=True, check=True,
                ).stdout.splitlines())

    def test_invalid_legacy_ownership_stops_before_index_or_worktree_mutation(self):
        for name, installer in self.installers.items():
            with self.subTest(installer=name), tempfile.TemporaryDirectory() as directory:
                target = self.make_repo(directory)
                managed = target / ".agents" / "zzzops" / "zzzops.py"
                managed.parent.mkdir(parents=True)
                managed.write_text("unknown owner\n", encoding="utf-8")
                subprocess.run(["git", "-C", str(target), "add", "-f", ".agents/zzzops/zzzops.py"], check=True)
                subprocess.run(["git", "-C", str(target), "commit", "--quiet", "-m", "ambiguous tracked file"], check=True)
                before = managed.read_bytes()
                result = self.run_installer(installer, target, "--yes")
                self.assertNotEqual(0, result.returncode, result.stderr + result.stdout)
                self.assertIn("no valid previous lock or legacy install manifest", result.stdout)
                self.assertEqual(before, managed.read_bytes())
                self.assertEqual([".agents/zzzops/zzzops.py"], self.tracked_machinery(target))
                self.assertFalse((target / ".zzzops" / "ZZZOPS_LOCK.json").exists())

    def test_broad_existing_ignore_rule_is_rejected_without_mutation(self):
        for name, installer in self.installers.items():
            with self.subTest(installer=name), tempfile.TemporaryDirectory() as directory:
                target = self.make_repo(directory)
                ignore = target / ".gitignore"
                ignore.write_text(".agents/\nkeep.local\n", encoding="utf-8")
                result = self.run_installer(installer, target, "--dry-run")
                self.assertNotEqual(0, result.returncode, result.stderr + result.stdout)
                self.assertIn("existing ignore rule is broader", result.stdout)
                self.assertEqual(".agents/\nkeep.local\n", ignore.read_text(encoding="utf-8"))
                self.assertFalse((target / ".agents").exists())
                self.assertFalse((target / ".zzzops").exists())

    def test_legacy_manifest_keeps_project_ignore_metadata_outside_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.make_repo(directory)
            manifest = target / ".agents" / "zzzops" / "INSTALL_MANIFEST"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                "zzzops-install-manifest-v1\n"
                f"revision\t{'a' * 40}\n"
                "file\t1111111111111111111111111111111111111111\t.zzzops/.gitignore\n"
                "file\t2222222222222222222222222222222222222222\t.agents/zzzops/zzzops.py\n",
                encoding="utf-8",
            )
            files, error = installer_engine.read_legacy_manifest(target)
            self.assertIsNone(error)
            self.assertEqual({".agents/zzzops/INSTALL_MANIFEST", ".agents/zzzops/zzzops.py"}, files)

    def test_preview_drift_stops_before_mutation_and_copy_failure_keeps_project_state(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.make_repo(directory)
            sources = installer_engine.distribution_sources()
            lock = installer_engine.distribution_lock(sources)
            state = installer_engine.installation_state(target, lock)
            (target / ".gitignore").write_text("changed after preview\n", encoding="utf-8")
            with self.assertRaisesRegex(installer_engine.InstallError, "changed after the preview"):
                installer_engine.apply_install(target, sources, lock, state)
            self.assertFalse((target / ".agents").exists())

            (target / ".gitignore").unlink()
            state = installer_engine.installation_state(target, lock)
            project = target / ".zzzops" / "PROJECT.md"
            project.parent.mkdir(parents=True)
            project.write_text("project-owned\n", encoding="utf-8")
            real_copy = shutil.copyfile
            calls = 0

            def fail_second_copy(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected disposable copy failure")
                return real_copy(source, destination)

            with mock.patch.object(installer_engine.shutil, "copyfile", side_effect=fail_second_copy):
                with self.assertRaisesRegex(OSError, "injected disposable copy failure"):
                    installer_engine.apply_install(target, sources, lock, state)
            self.assertEqual("project-owned\n", project.read_text(encoding="utf-8"))
            self.assertFalse((target / ".zzzops" / "ZZZOPS_LOCK.json").exists())


class ValidationAggregateTests(unittest.TestCase):
    def run_required_validation(self, *results: str):
        return subprocess.run(
            [sys.executable, str(REQUIRED_VALIDATION), *results],
            text=True, encoding="utf-8", capture_output=True, check=False,
        )

    def test_required_validation_accepts_only_complete_success(self):
        success = self.run_required_validation("linux=success", "windows=success", "macos=success")
        self.assertEqual(0, success.returncode, success.stderr + success.stdout)
        for results in (
            ("linux=success", "windows=failure"),
            ("linux=failure", "windows=success"),
            ("linux=success", "windows=cancelled"),
            ("linux=success", "windows="),
            ("linux=success", "windows=success", "macos=failure"),
            (),
        ):
            with self.subTest(results=results):
                failure = self.run_required_validation(*results)
                self.assertNotEqual(0, failure.returncode, failure.stderr + failure.stdout)

    def test_workflow_preserves_stable_check_and_requires_native_installers(self):
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        self.assertIn("validate-linux:", workflow)
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertIn("validate-windows:", workflow)
        self.assertIn("runs-on: windows-latest", workflow)
        self.assertEqual(2, workflow.count("ZZZOPS_EXPECT_INSTALLERS: PowerShell,Bash"))
        self.assertIn("validate-macos:", workflow)
        self.assertIn("runs-on: macos-latest", workflow)
        self.assertIn("ZZZOPS_EXPECT_INSTALLERS: Bash", workflow)
        self.assertIn("name: dev-required-tests", workflow)
        self.assertIn("needs: [validate-linux, validate-windows, validate-macos]", workflow)
        self.assertIn("linux=${{ needs.validate-linux.result }}", workflow)
        self.assertIn("windows=${{ needs.validate-windows.result }}", workflow)
        self.assertIn("macos=${{ needs.validate-macos.result }}", workflow)

    def test_workflow_validates_supported_python_floor_and_current_runtime(self):
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        self.assertIn("python-version: ['3.10', '3.14']", workflow)
        self.assertEqual(2, workflow.count("python-version: '3.14'"))


if __name__ == "__main__":
    unittest.main()
