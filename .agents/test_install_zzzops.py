import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_VALIDATION = ROOT / ".github" / "scripts" / "require_validation.py"


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
        return target

    def command(self, installer: tuple[str, Path], target: Path, *options: str) -> list[str]:
        runtime, script = installer
        if script.suffix == ".ps1":
            translated = {"--dry-run": "-DryRun", "--overwrite-mechanical": "-OverwriteMechanical", "--yes": "-Yes"}
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
        if os.name == "nt" and installer[1].suffix == ".sh" and answer in {"y\n", "yes\n"}:
            options = (*options, "--yes")
            answer = None
        return subprocess.run(
            self.command(installer, target, *options), input=answer, text=True,
            encoding="utf-8", errors="replace", capture_output=True, check=False,
            env=self.environment(installer), timeout=45,
        )

    def git_blob_hash(self, data: bytes) -> str:
        result = subprocess.run(
            ["git", "hash-object", "--stdin"], input=data, capture_output=True, check=True,
        )
        return result.stdout.decode("ascii").strip()

    def simulate_older_managed_install(self, target: Path, relative: str) -> tuple[bytes, bytes]:
        manifest = target / ".agents" / "zzzops" / "INSTALL_MANIFEST"
        before_manifest = manifest.read_bytes()
        old_data = b"older managed ZzzOps mechanics\n"
        (target / relative).write_bytes(old_data)
        older_revision = "0" * 40  # Deliberately unavailable in shallow clones; preview must fall back safely.
        lines = before_manifest.decode("utf-8").splitlines()
        rewritten = []
        for line in lines:
            fields = line.split("\t", 2)
            if fields[0] == "revision":
                line = f"revision\t{older_revision}"
            elif fields[0] == "version":
                continue  # Exercise the supported revision-only manifest upgrade path.
            elif len(fields) == 3 and fields[0] == "file" and fields[2] == relative:
                line = f"file\t{self.git_blob_hash(old_data)}\t{relative}"
            rewritten.append(line)
        manifest.write_text("\n".join(rewritten) + "\n", encoding="utf-8", newline="\n")
        return old_data, manifest.read_bytes()

    def test_dry_run_cancel_and_confirm_install(self):
        installed_versions = {}
        for name, installer in self.installers.items():
            with self.subTest(installer=name), tempfile.TemporaryDirectory() as directory:
                target = self.make_repo(directory)
                preview = self.run_installer(installer, target, "--dry-run")
                self.assertEqual(0, preview.returncode, preview.stderr + preview.stdout)
                self.assertIn("installation preview", preview.stdout)
                self.assertIn("tracked project skills", preview.stdout)
                self.assertIn("workflow rules", preview.stdout)
                self.assertIn("blank templates", preview.stdout)
                self.assertRegex(preview.stdout, r"ZzzOps version: not installed -> [A-Za-z0-9][A-Za-z0-9._+-]+ \([0-9a-f]{7}\)\.")
                self.assertIn("No files were changed.", preview.stdout)
                self.assertFalse((target / ".agents").exists())

                if not (os.name == "nt" and installer[1].suffix == ".sh"):
                    cancelled = self.run_installer(installer, target, answer="\n")
                    self.assertEqual(0, cancelled.returncode, cancelled.stderr + cancelled.stdout)
                    self.assertIn("cancelled", cancelled.stdout)
                    self.assertFalse((target / ".agents").exists())

                applied = self.run_installer(installer, target, answer="y\n")
                self.assertEqual(0, applied.returncode, applied.stderr + applied.stdout)
                self.assertIn("ZzzOps is installed.", applied.stdout)
                self.assertIn("Codex or Claude Code", applied.stdout)
                self.assertIn("restart or reopen", applied.stdout)
                self.assertIn("review-zzzops-policy", applied.stdout)
                self.assertTrue((target / ".zzzops" / "rules" / "INITIALIZATION.md").is_file())
                self.assertTrue((target / ".agents" / "zzzops" / "templates" / "project-goals" / "INIT_PLAN.json").is_file())
                self.assertTrue((target / ".agents" / "zzzops" / ".gitignore").is_file())
                self.assertTrue((target / ".agents" / "zzzops" / "policy.py").is_file())
                self.assertTrue((target / ".agents" / "zzzops" / "reservation.py").is_file())
                self.assertTrue((target / ".agents" / "zzzops" / "feedback.py").is_file())
                self.assertTrue((target / ".agents" / "zzzops" / "goals.py").is_file())
                self.assertTrue((target / ".agents" / "zzzops" / "portfolio.py").is_file())
                self.assertEqual((ROOT / "LICENSE").read_bytes(), (target / ".agents" / "zzzops" / "LICENSE").read_bytes())
                self.assertTrue((target / ".agents" / "zzzops" / "INSTALL_MANIFEST").is_file())
                manifest_text = (target / ".agents" / "zzzops" / "INSTALL_MANIFEST").read_text(encoding="utf-8")
                self.assertIn("\nversion\t", manifest_text)
                fields = dict(line.split("\t", 1) for line in manifest_text.splitlines()[1:] if line.count("\t") == 1)
                self.assertRegex(fields["revision"], r"^[0-9a-f]{40,64}$")
                installed_versions[name] = (fields["version"], fields["revision"])
                self.assertTrue((target / ".agents" / "skills" / "add-zzzops-goal" / "SKILL.md").is_file())
                self.assertTrue((target / ".claude" / "skills" / "add-zzzops-goal" / "SKILL.md").is_file())
                self.assertTrue((target / ".agents" / "skills" / "review-zzzops-policy" / "SKILL.md").is_file())
                self.assertTrue((target / ".claude" / "skills" / "review-zzzops-policy" / "SKILL.md").is_file())
                self.assertTrue((target / ".agents" / "skills" / "send-zzzops-feedback" / "SKILL.md").is_file())
                self.assertTrue((target / ".claude" / "skills" / "send-zzzops-feedback" / "SKILL.md").is_file())
                self.assertTrue((target / ".zzzops" / "rules" / "FEEDBACK.md").is_file())
                installed_ignore = (target / ".zzzops" / ".gitignore").read_text(encoding="utf-8")
                self.assertIn("execution-reports/", installed_ignore)
                self.assertEqual({"skills", "zzzops"}, {path.name for path in (target / ".agents").iterdir()})
                self.assertEqual({"skills"}, {path.name for path in (target / ".claude").iterdir()})
                self.assertFalse((target / ".gitignore").exists())
                self.assertFalse((target / ".zzzops" / "PROJECT.md").exists())
                help_result = subprocess.run(
                    [sys.executable, str(target / ".agents" / "zzzops" / "zzzops.py"), "--repo", str(target), "portfolio", "--help"],
                    text=True, encoding="utf-8", capture_output=True, check=False,
                )
                self.assertEqual(0, help_result.returncode, help_result.stderr + help_result.stdout)
                self.assertIn("--format {summary,json}", help_result.stdout)
                checkpoint = subprocess.run(
                    [sys.executable, str(target / ".agents" / "zzzops" / "zzzops.py"), "--repo", str(target), "checkpoint"],
                    text=True, encoding="utf-8", capture_output=True, check=False,
                )
                self.assertEqual(2, checkpoint.returncode, checkpoint.stderr + checkpoint.stdout)
                self.assertFalse(json.loads(checkpoint.stdout)["ready"])
                repeated = self.run_installer(installer, target, "--dry-run")
                self.assertEqual(0, repeated.returncode, repeated.stderr + repeated.stdout)
                self.assertIn("already up to date", repeated.stdout)
                current = self.run_installer(installer, target)
                self.assertEqual(0, current.returncode, current.stderr + current.stdout)
                self.assertIn("No further action is necessary", current.stdout)
                self.assertNotIn("Install these changes?", current.stdout)
                self.assertNotIn("cancelled", current.stdout)
        self.assertEqual(1, len(set(installed_versions.values())))

    def test_declined_and_accepted_upgrade_are_distinct_from_local_divergence(self):
        relative = ".agents/zzzops/zzzops.py"
        source_data = (ROOT / relative).read_bytes()
        for name, installer in self.installers.items():
            with self.subTest(installer=name), tempfile.TemporaryDirectory() as directory:
                if os.name == "nt" and installer[1].suffix == ".sh":
                    continue  # Native Windows Git Bash has no redirected interactive prompt transport; --yes covers executable paths.
                target = self.make_repo(directory)
                installed = self.run_installer(installer, target, answer="y\n")
                self.assertEqual(0, installed.returncode, installed.stderr + installed.stdout)

                old_data, old_manifest = self.simulate_older_managed_install(target, relative)
                before_decline = {
                    path.relative_to(target).as_posix(): path.read_bytes()
                    for path in target.rglob("*") if path.is_file() and ".git/" not in path.relative_to(target).as_posix()
                }
                declined = self.run_installer(installer, target, answer="\n")
                self.assertEqual(0, declined.returncode, declined.stderr + declined.stdout)
                self.assertIn("Upgrade available", declined.stdout)
                self.assertIn("ZzzOps version: revision 0000000 ->", declined.stdout)
                self.assertIn("Managed files to update", declined.stdout)
                self.assertIn(relative, declined.stdout)
                self.assertIn("Changes since installed version", declined.stdout)
                if installer[1].suffix == ".sh" and os.name != "nt":
                    self.assertIn("Upgrade ZzzOps? [y/N]", declined.stdout)
                self.assertIn("cancelled", declined.stdout)
                self.assertEqual(old_data, (target / relative).read_bytes())
                self.assertEqual(old_manifest, (target / ".agents" / "zzzops" / "INSTALL_MANIFEST").read_bytes())
                self.assertEqual(before_decline, {
                    path.relative_to(target).as_posix(): path.read_bytes()
                    for path in target.rglob("*") if path.is_file() and ".git/" not in path.relative_to(target).as_posix()
                })

                upgraded = self.run_installer(installer, target, answer="yes\n")
                self.assertEqual(0, upgraded.returncode, upgraded.stderr + upgraded.stdout)
                self.assertIn("ZzzOps was upgraded.", upgraded.stdout)
                self.assertEqual(source_data, (target / relative).read_bytes())
                self.assertNotEqual(old_manifest, (target / ".agents" / "zzzops" / "INSTALL_MANIFEST").read_bytes())
                self.assertIn("\nversion\t", (target / ".agents" / "zzzops" / "INSTALL_MANIFEST").read_text(encoding="utf-8"))

                (target / relative).write_bytes(b"local project customization\n")
                conflict = self.run_installer(installer, target, "--dry-run")
                self.assertEqual(2, conflict.returncode, conflict.stderr + conflict.stdout)
                self.assertIn("locally divergent", conflict.stdout)
                self.assertNotIn("already up to date", conflict.stdout)
                self.assertEqual(b"local project customization\n", (target / relative).read_bytes())
                explicit = self.run_installer(installer, target, "--overwrite-mechanical", answer="y\n")
                self.assertEqual(0, explicit.returncode, explicit.stderr + explicit.stdout)
                self.assertEqual(source_data, (target / relative).read_bytes())

    def test_revision_only_manifest_receives_version_metadata_upgrade(self):
        for name, installer in self.installers.items():
            with self.subTest(installer=name), tempfile.TemporaryDirectory() as directory:
                target = self.make_repo(directory)
                installed = self.run_installer(installer, target, answer="y\n")
                self.assertEqual(0, installed.returncode, installed.stderr + installed.stdout)
                manifest = target / ".agents" / "zzzops" / "INSTALL_MANIFEST"
                revision_only = "\n".join(
                    line for line in manifest.read_text(encoding="utf-8").splitlines()
                    if not line.startswith("version\t")
                ) + "\n"
                manifest.write_text(revision_only, encoding="utf-8", newline="\n")

                preview = self.run_installer(installer, target, "--dry-run")
                self.assertEqual(0, preview.returncode, preview.stderr + preview.stdout)
                self.assertIn("Upgrade available", preview.stdout)
                self.assertIn("ZzzOps version: revision ", preview.stdout)
                upgraded = self.run_installer(installer, target, answer="yes\n")
                self.assertEqual(0, upgraded.returncode, upgraded.stderr + upgraded.stdout)
                self.assertIn("ZzzOps was upgraded", upgraded.stdout)
                self.assertIn("\nversion\t", manifest.read_text(encoding="utf-8"))

    def test_ignore_warning_and_local_state_preservation(self):
        for name, installer in self.installers.items():
            with self.subTest(installer=name), tempfile.TemporaryDirectory() as directory:
                target = self.make_repo(directory)
                ignore = target / ".gitignore"
                ignore.write_text(".agents/\n.claude/\nkeep.local\n", encoding="utf-8")
                preview = self.run_installer(installer, target, "--dry-run")
                self.assertEqual(0, preview.returncode, preview.stderr + preview.stdout)
                self.assertIn("Warning: Git ignores", preview.stdout)
                self.assertIn(".agents/", preview.stdout)
                self.assertIn(".claude/", preview.stdout)
                self.assertEqual(".agents/\n.claude/\nkeep.local\n", ignore.read_text(encoding="utf-8"))

                state = {
                    target / ".zzzops" / "LOCAL_NOTES.md": b"personal notes\n",
                    target / ".zzzops" / "PROJECT.md": b"project\n",
                    target / "AGENTS.md": b"project instructions\n",
                }
                for path, data in state.items():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                applied = self.run_installer(installer, target, answer="yes\n")
                self.assertEqual(0, applied.returncode, applied.stderr + applied.stdout)
                for path, data in state.items():
                    self.assertEqual(data, path.read_bytes())

    def test_target_drift_during_prompt_is_rejected(self):
        for name, installer in self.installers.items():
            with self.subTest(installer=name), tempfile.TemporaryDirectory() as directory:
                if os.name == "nt":
                    continue  # Native Windows Git Bash cannot exercise a redirected interactive prompt; --yes covers its install path.
                target = self.make_repo(directory)
                process = subprocess.Popen(
                    self.command(installer, target), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=0,
                    env=self.environment(installer),
                )
                output: list[str] = []
                prompted = threading.Event()

                def read_output():
                    assert process.stdout is not None
                    while character := process.stdout.read(1):
                        output.append(character)
                        if "[y/N]" in "".join(output[-12:]):
                            prompted.set()

                reader = threading.Thread(target=read_output, daemon=True)
                reader.start()
                self.assertTrue(prompted.wait(15), "installer did not prompt: " + "".join(output))
                changed = target / ".agents" / "zzzops" / "zzzops.py"
                changed.parent.mkdir(parents=True)
                changed.write_bytes(b"changed after preview\n")
                assert process.stdin is not None
                process.stdin.write("y\n")
                process.stdin.close()
                process.wait(timeout=15)
                reader.join(timeout=5)
                process.stdout.close()
                combined = "".join(output)
                self.assertNotEqual(0, process.returncode, combined)
                self.assertIn("target changed", combined.lower())
                self.assertEqual(b"changed after preview\n", changed.read_bytes())
                self.assertFalse((target / ".zzzops" / "rules" / "INITIALIZATION.md").exists())

    def test_injected_mid_write_failure_rolls_back(self):
        for name, installer in self.installers.items():
            with self.subTest(installer=name), tempfile.TemporaryDirectory() as directory:
                target = self.make_repo(directory)
                script = installer[1].read_text(encoding="utf-8")
                if installer[1].suffix == ".ps1":
                    quoted_root = str(ROOT).replace("'", "''")
                    script = script.replace("$SourceRoot = $PSScriptRoot", f"$SourceRoot = '{quoted_root}'", 1)
                    needle = "            Move-Item -LiteralPath $temporary -Destination $action.Destination -Force"
                    replacement = (
                        "            if ($null -eq $script:InjectedWrites) { $script:InjectedWrites = 0 }\n"
                        "            $script:InjectedWrites += 1\n"
                        "            if ($script:InjectedWrites -eq 2) { throw 'injected write failure' }\n" + needle
                    )
                else:
                    quoted_root = str(ROOT).replace("'", "'\\''")
                    script = script.replace(
                        'SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"',
                        f"SOURCE_ROOT='{quoted_root}'", 1,
                    )
                    needle = '        cp "$source" "$temporary" && mv -f "$temporary" "$destination" || {'
                    replacement = (
                        "        INJECTED_WRITES=$((INJECTED_WRITES + 1))\n"
                        "        [[ $INJECTED_WRITES -ne 2 ]] && cp \"$source\" \"$temporary\" && "
                        "mv -f \"$temporary\" \"$destination\" || {"
                    )
                    script = script.replace("WRITTEN_RELATIVE=()", "INJECTED_WRITES=0\nWRITTEN_RELATIVE=()", 1)
                self.assertIn(needle, script)
                script = script.replace(needle, replacement, 1)
                injected = Path(directory) / installer[1].name
                injected.write_text(script, encoding="utf-8", newline="\n")
                result = self.run_installer((installer[0], injected), target, answer="y\n")
                self.assertNotEqual(0, result.returncode, result.stderr + result.stdout)
                self.assertIn("rolled back", result.stdout)
                self.assertFalse((target / ".zzzops" / "rules" / "BACKENDS.md").exists())
                self.assertFalse((target / ".zzzops" / "rules" / "BLOCKERS.md").exists())


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
