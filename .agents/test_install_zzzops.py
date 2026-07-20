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


def available_installers() -> dict[str, tuple[str, Path]]:
    installers: dict[str, tuple[str, Path]] = {}
    powershell = shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe")
    if powershell:
        installers["PowerShell"] = (powershell, ROOT / "install.ps1")
    bash = None if os.name == "nt" else shutil.which("bash")
    if shutil.which("git") and not bash:
        git = Path(shutil.which("git")).resolve()
        candidate = git.parents[1] / "bin" / "bash.exe"
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

    def make_repo(self, directory: str) -> Path:
        target = Path(directory)
        result = subprocess.run(["git", "init", "--quiet", str(target)], text=True, capture_output=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        return target

    def command(self, installer: tuple[str, Path], target: Path, *options: str) -> list[str]:
        runtime, script = installer
        if script.suffix == ".ps1":
            translated = {"--dry-run": "-DryRun", "--overwrite-mechanical": "-OverwriteMechanical"}
            return [runtime, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), str(target),
                    *(translated[option] for option in options)]
        return [runtime, str(script), str(target), *options]

    def environment(self, installer: tuple[str, Path]) -> dict[str, str]:
        environment = dict(os.environ)
        if os.name == "nt" and installer[1].suffix == ".sh":
            git_root = Path(installer[0]).resolve().parents[1]
            environment["PATH"] = os.pathsep.join(
                [str(git_root / "usr" / "bin"), str(git_root / "mingw64" / "bin"), environment.get("PATH", "")]
            )
        return environment

    def run_installer(self, installer, target: Path, *options: str, answer: str | None = None):
        return subprocess.run(
            self.command(installer, target, *options), input=answer, text=True,
            encoding="utf-8", errors="replace", capture_output=True, check=False,
            env=self.environment(installer),
        )

    def test_dry_run_cancel_and_confirm_install(self):
        for name, installer in self.installers.items():
            with self.subTest(installer=name), tempfile.TemporaryDirectory() as directory:
                target = self.make_repo(directory)
                preview = self.run_installer(installer, target, "--dry-run")
                self.assertEqual(0, preview.returncode, preview.stderr + preview.stdout)
                self.assertIn("installation preview", preview.stdout)
                self.assertIn("tracked project skills", preview.stdout)
                self.assertIn("workflow rules", preview.stdout)
                self.assertIn("blank templates", preview.stdout)
                self.assertIn("No files were changed.", preview.stdout)
                self.assertFalse((target / ".agents").exists())

                cancelled = self.run_installer(installer, target, answer="\n")
                self.assertEqual(0, cancelled.returncode, cancelled.stderr + cancelled.stdout)
                self.assertIn("cancelled", cancelled.stdout)
                self.assertFalse((target / ".agents").exists())

                applied = self.run_installer(installer, target, answer="y\n")
                self.assertEqual(0, applied.returncode, applied.stderr + applied.stdout)
                self.assertIn("ZzzOps is installed.", applied.stdout)
                self.assertTrue((target / ".zzzops" / "rules" / "INITIALIZATION.md").is_file())
                self.assertTrue((target / ".agents" / "templates" / "project-goals" / "INIT_PLAN.json").is_file())
                self.assertTrue((target / ".agents" / "skills" / "add-zzzops-goal" / "SKILL.md").is_file())
                self.assertTrue((target / ".claude" / "skills" / "add-zzzops-goal" / "SKILL.md").is_file())
                self.assertFalse((target / ".gitignore").exists())
                self.assertFalse((target / ".zzzops" / "PROJECT.md").exists())
                self.assertFalse((target / ".zzzops" / "PREFERENCES.json").exists())
                help_result = subprocess.run(
                    [sys.executable, str(target / ".agents" / "zzzops.py"), "--repo", str(target), "portfolio", "--help"],
                    text=True, encoding="utf-8", capture_output=True, check=False,
                )
                self.assertEqual(0, help_result.returncode, help_result.stderr + help_result.stdout)
                self.assertIn("--format {summary,json}", help_result.stdout)
                checkpoint = subprocess.run(
                    [sys.executable, str(target / ".agents" / "zzzops.py"), "--repo", str(target), "checkpoint"],
                    text=True, encoding="utf-8", capture_output=True, check=False,
                )
                self.assertEqual(2, checkpoint.returncode, checkpoint.stderr + checkpoint.stdout)
                self.assertFalse(json.loads(checkpoint.stdout)["ready"])

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
                    target / ".zzzops" / "PREFERENCES.json": b'{"personal": true}\n',
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
                if installer[1].suffix == ".ps1":
                    continue  # Read-Host deliberately writes its prompt to the host UI, not redirected stdout.
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
                changed = target / ".agents" / "zzzops.py"
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


if __name__ == "__main__":
    unittest.main()
