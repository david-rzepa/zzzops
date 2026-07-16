from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from semantic_release import Change, bump_for, next_version, release_notes


def change(subject: str, body: str = "") -> Change:
    return Change("1234567890abcdef", subject, body)


class SemanticReleaseTests(unittest.TestCase):
    def test_first_feature_release(self) -> None:
        self.assertEqual(next_version((0, 0, 0), bump_for([change("feat: begin")]) or ""), (0, 1, 0))

    def test_patch_minor_and_major_precedence(self) -> None:
        self.assertEqual(bump_for([change("fix: correct")]), "patch")
        self.assertEqual(bump_for([change("fix: correct"), change("feat(ui): add")]), "minor")
        self.assertEqual(bump_for([change("feat: add"), change("fix!: remove API")]), "major")
        self.assertEqual(bump_for([change("fix: alter", "BREAKING CHANGE: protocol")]), "major")

    def test_non_release_commits_and_idempotent_empty_range(self) -> None:
        self.assertIsNone(bump_for([change("docs: explain"), change("chore: tidy")]))
        self.assertIsNone(bump_for([]))

    def test_version_resets_lower_components(self) -> None:
        self.assertEqual(next_version((1, 2, 3), "patch"), (1, 2, 4))
        self.assertEqual(next_version((1, 2, 3), "minor"), (1, 3, 0))
        self.assertEqual(next_version((1, 2, 3), "major"), (2, 0, 0))

    def test_notes_include_releasable_changes(self) -> None:
        notes = release_notes("v1.2.3", [change("feat: add queue"), change("docs: explain")])
        self.assertIn("# v1.2.3", notes)
        self.assertIn("## Features", notes)
        self.assertIn("add queue", notes)
        self.assertNotIn("explain", notes)

    def test_git_history_first_release_bumps_and_idempotency(self) -> None:
        script = Path(__file__).with_name("semantic_release.py").resolve()
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)

            def git(*args: str) -> None:
                subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.DEVNULL)

            def commit(subject: str) -> None:
                git("commit", "--allow-empty", "-m", subject)

            def plan(expected: str) -> None:
                result = subprocess.run(
                    [sys.executable, str(script), "--notes", str(repo / "notes.md")],
                    cwd=repo,
                    check=True,
                    text=True,
                    encoding="utf-8",
                    stdout=subprocess.PIPE,
                )
                self.assertIn(expected, result.stdout)

            git("init", "-q")
            git("config", "user.name", "ZzzOps test")
            git("config", "user.email", "test@zzzops.invalid")
            commit("feat: initial")
            plan("none -> v0.1.0 (minor)")
            git("tag", "v0.1.0")
            plan("No releasable")
            commit("fix: patch")
            plan("v0.1.0 -> v0.1.1 (patch)")
            git("tag", "v0.1.1")
            commit("feat: minor")
            plan("v0.1.1 -> v0.2.0 (minor)")
            git("tag", "v0.2.0")
            commit("feat!: major")
            plan("v0.2.0 -> v1.0.0 (major)")
            git("tag", "v1.0.0")
            commit("docs: no release")
            plan("No releasable")


if __name__ == "__main__":
    unittest.main()
