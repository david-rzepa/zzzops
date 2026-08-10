"""Safety regression tests for the retired per-project installation cleaner."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from pathlib import PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "zzzops" / "scripts" / "cleanup_legacy.py"
CATALOG = ROOT / "plugins" / "zzzops" / "assets" / "legacy_install_fingerprints.json"


def load_cleaner():
    spec = importlib.util.spec_from_file_location("cleanup_legacy", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LegacyCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cleaner = load_cleaner()

    def make_repo(self, directory: str) -> Path:
        repo = Path(directory)
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        return repo

    def write_fixture(self, repo: Path, files: dict[str, bytes]) -> None:
        for relative, data in files.items():
            target = repo.joinpath(*relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def tiny_catalog(self, files: dict[str, bytes]) -> dict[str, object]:
        return {
            "schema_version": 1,
            "releases": {
                "fixture": {
                    "files": {
                        relative: self.cleaner.file_digest_bytes(data)
                        for relative, data in files.items()
                    }
                }
            },
        }

    def test_exact_catalog_match_is_actionable_and_one_byte_change_blocks_everything(self) -> None:
        files = {
            ".agents/zzzops/zzzops.py": b"print('legacy')\n",
            ".zzzops/rules/GOAL_SYSTEM.md": b"legacy rules\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            self.write_fixture(repo, files)
            exact = self.cleaner.build_plan(repo, self.tiny_catalog(files))
            self.assertTrue(exact.safe, exact.errors)
            self.assertEqual(sorted(files), exact.remove_files)

            (repo / ".agents" / "zzzops" / "zzzops.py").write_bytes(b"print('changed')\n")
            changed = self.cleaner.build_plan(repo, self.tiny_catalog(files))
            self.assertFalse(changed.safe)
            self.assertIn("does not match", " ".join(changed.errors))
            self.assertEqual([], changed.remove_files)
            self.assertTrue((repo / ".zzzops" / "rules" / "GOAL_SYSTEM.md").exists())

    def test_default_cli_is_dry_run_and_interrupted_cleanup_converges(self) -> None:
        files = {
            ".agents/zzzops/zzzops.py": b"print('legacy')\n",
            ".zzzops/rules/GOAL_SYSTEM.md": b"legacy rules\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            catalog = self.tiny_catalog(files)
            ignore = repo / ".gitignore"
            ignore.write_text(
                "keep\n# BEGIN ZZZOPS DISPOSABLE MACHINERY\n/.agents/zzzops/\n# END ZZZOPS DISPOSABLE MACHINERY\n",
                encoding="utf-8",
            )
            before = ignore.read_bytes()
            self.assertEqual(0, self.cleaner.main([str(repo)]))
            self.assertEqual(before, ignore.read_bytes())

            self.write_fixture(repo, files)
            (repo / ".zzzops" / "rules" / "GOAL_SYSTEM.md").unlink()
            resumed = self.cleaner.build_plan(repo, catalog)
            self.assertTrue(resumed.safe, resumed.errors)
            self.cleaner.apply_plan(repo, resumed)
            self.assertTrue(self.cleaner.build_plan(repo, catalog).safe)
            self.assertFalse((repo / ".agents" / "zzzops" / "zzzops.py").exists())

    def test_apply_preserves_durable_state_and_git_index(self) -> None:
        files = {
            ".agents/zzzops/zzzops.py": b"print('legacy')\n",
            ".zzzops/rules/GOAL_SYSTEM.md": b"legacy rules\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            self.write_fixture(repo, files)
            project = repo / ".zzzops" / "PROJECT.md"
            project.write_text("keep\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", ".agents/zzzops/zzzops.py"], check=True)
            before_index = subprocess.check_output(["git", "-C", str(repo), "ls-files", "-s"])

            plan = self.cleaner.build_plan(repo, self.tiny_catalog(files))
            self.assertEqual([".agents/zzzops/zzzops.py"], plan.tracked)
            self.cleaner.apply_plan(repo, plan)

            self.assertFalse((repo / ".agents" / "zzzops" / "zzzops.py").exists())
            self.assertFalse((repo / ".zzzops" / "rules").exists())
            self.assertEqual("keep\n", project.read_text(encoding="utf-8"))
            self.assertEqual(before_index, subprocess.check_output(["git", "-C", str(repo), "ls-files", "-s"]))

    def test_lock_and_manifest_provenance_are_verified(self) -> None:
        data = b"print('locked')\n"
        relative = ".agents/zzzops/zzzops.py"
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            self.write_fixture(repo, {relative: data})
            lock = repo / ".zzzops" / "ZZZOPS_LOCK.json"
            lock.parent.mkdir(parents=True)
            lock.write_text(json.dumps({
                "schema_version": 1,
                "revision": "a" * 40,
                "version": "v1.2.0",
                "files": {relative: self.cleaner.file_digest_bytes(data)},
            }), encoding="utf-8")
            plan = self.cleaner.build_plan(repo, self.tiny_catalog({relative: b"other"}))
            self.assertTrue(plan.safe, plan.errors)
            self.assertEqual("installation lock", plan.source)
            (repo / ".agents" / "zzzops" / "zzzops.py").write_bytes(b"modified\n")
            self.assertFalse(self.cleaner.build_plan(repo, self.tiny_catalog({relative: b"other"})).safe)

        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            self.write_fixture(repo, {relative: data})
            blob = subprocess.check_output(["git", "hash-object", "--stdin"], input=data).decode().strip()
            manifest = repo / ".agents" / "zzzops" / "INSTALL_MANIFEST"
            manifest.write_text(
                "zzzops-install-manifest-v1\n"
                f"revision\t{'b' * 40}\n"
                f"file\t{blob}\t{relative}\n",
                encoding="utf-8",
            )
            plan = self.cleaner.build_plan(repo, self.tiny_catalog({relative: b"other"}))
            self.assertTrue(plan.safe, plan.errors)
            self.assertEqual("legacy install manifest", plan.source)

    def test_preview_drift_and_unknown_files_stop_before_removal(self) -> None:
        files = {".agents/zzzops/zzzops.py": b"legacy\n"}
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            self.write_fixture(repo, files)
            catalog = self.tiny_catalog(files)
            plan = self.cleaner.build_plan(repo, catalog)
            unknown = repo / ".agents" / "zzzops" / "personal.txt"
            unknown.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(self.cleaner.CleanupError, "changed after preview"):
                self.cleaner.apply_plan(repo, plan)
            self.assertTrue((repo / ".agents" / "zzzops" / "zzzops.py").exists())
            self.assertFalse(self.cleaner.build_plan(repo, catalog).safe)
            self.assertEqual("keep", unknown.read_text(encoding="utf-8"))

    def test_marker_cleanup_preserves_unrelated_ignore_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            (repo / ".gitignore").write_text(
                "keep.local\n# BEGIN ZZZOPS DISPOSABLE MACHINERY\n/.agents/zzzops/\n# END ZZZOPS DISPOSABLE MACHINERY\nother.tmp\n",
                encoding="utf-8",
            )
            state = repo / ".zzzops" / ".gitignore"
            state.parent.mkdir(parents=True)
            state.write_text(
                "keep-state\n# BEGIN ZZZOPS LOCAL STATE\ninit/\nexecution-reports/\n# END ZZZOPS LOCAL STATE\n",
                encoding="utf-8",
            )
            plan = self.cleaner.build_plan(
                repo,
                self.tiny_catalog({".agents/zzzops/zzzops.py": b"catalog-only"}),
            )
            self.assertTrue(plan.safe, plan.errors)
            self.cleaner.apply_plan(repo, plan)
            self.assertEqual("keep.local\nother.tmp\n", (repo / ".gitignore").read_text(encoding="utf-8"))
            self.assertEqual("keep-state\n", state.read_text(encoding="utf-8"))

    def test_symlink_or_unsafe_catalog_path_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            outside = repo / "outside"
            outside.write_text("keep", encoding="utf-8")
            link = repo / ".agents"
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest("symlinks are unavailable")
            plan = self.cleaner.build_plan(
                repo,
                self.tiny_catalog({".agents/zzzops/zzzops.py": b"legacy"}),
            )
            self.assertFalse(plan.safe)
            self.assertIn("symlink", " ".join(plan.errors).lower())
            self.assertEqual("keep", outside.read_text(encoding="utf-8"))

        unsafe = {"schema_version": 1, "releases": {"bad": {"files": {"../escape": "0" * 64}}}}
        with self.assertRaisesRegex(self.cleaner.CleanupError, "unsafe"):
            self.cleaner.validate_catalog(unsafe)

    def test_shipped_v1_catalog_is_well_formed(self) -> None:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        validated = self.cleaner.validate_catalog(catalog)
        self.assertEqual({"v1.0.0"}, set(validated["releases"]))
        self.assertGreater(len(validated["releases"]["v1.0.0"]["files"]), 40)

    def test_shipped_v1_catalog_matches_the_published_tag(self) -> None:
        if subprocess.run(["git", "cat-file", "-e", "v1.0.0^{commit}"], cwd=ROOT).returncode:
            self.skipTest("published tag is unavailable in this checkout")
        names = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", "v1.0.0"], cwd=ROOT, text=True
        ).splitlines()
        skills = (
            "add-zzzops-goal", "execute-zzzops", "migrate-to-zzzops",
            "review-zzzops-policy", "suggest-zzzops-work",
        )
        pairs = [(path, path) for path in (
            ".zzzops/rules/BACKENDS.md", ".zzzops/rules/BLOCKERS.md",
            ".zzzops/rules/CONTINUATION.md", ".zzzops/rules/EXECUTION_STRATEGY.md",
            ".zzzops/rules/GOAL_SYSTEM.md", ".zzzops/rules/INITIALIZATION.md",
            ".agents/zzzops/zzzops.py",
        )]
        pairs.append((".agents/.gitignore", ".agents/zzzops/.gitignore"))
        for path in names:
            if path.startswith(".agents/zzzops/templates/project-goals/") and not PurePosixPath(path).name.startswith("test_"):
                pairs.append((path, path))
        for skill in skills:
            prefix = f".agents/skills/{skill}/"
            for path in names:
                if path.startswith(prefix) and not PurePosixPath(path).name.startswith("test_"):
                    pairs.append((path, path))
                    pairs.append((path, f".claude/skills/{skill}/{path[len(prefix):]}"))
        pairs.append((".agents/zzzops/templates/project-goals/ZZZOPS_GITIGNORE", ".zzzops/.gitignore"))
        actual = {
            destination: self.cleaner.file_digest_bytes(
                subprocess.check_output(["git", "show", f"v1.0.0:{source}"], cwd=ROOT)
            )
            for source, destination in pairs
        }
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        self.assertEqual(actual, catalog["releases"]["v1.0.0"]["files"])


if __name__ == "__main__":
    unittest.main()
