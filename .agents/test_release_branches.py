"""Real temporary-Git release branch creation, retry, and conflict contracts."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "plugins" / "zzzops" / "zzzops" / "releases.py"


def load_subject():
    if not SUBJECT.exists(): raise AssertionError("release planning requires releases.py")
    spec = importlib.util.spec_from_file_location("release_branch_subject", SUBJECT)
    module = importlib.util.module_from_spec(spec); assert spec and spec.loader
    spec.loader.exec_module(module); return module


class ReleaseBranchContractTests(unittest.TestCase):
    def git(self, cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()

    def test_create_only_remote_branch_is_retry_safe_and_rejects_different_sha(self):
        r = load_subject()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); remote = root / "remote.git"; work = root / "work"
            self.git(root, "init", "--bare", str(remote)); self.git(root, "clone", str(remote), str(work))
            self.git(work, "config", "user.email", "test@example.test"); self.git(work, "config", "user.name", "Test")
            (work / "value").write_text("one", encoding="utf-8"); self.git(work, "add", "value"); self.git(work, "commit", "-m", "one")
            first_sha = self.git(work, "rev-parse", "HEAD")
            adapter = r.GitReleaseBranchAdapter(work, remote="origin")
            self.assertEqual("created", adapter.create_only("release/1", first_sha)["status"])
            self.assertEqual("confirmed", adapter.create_only("release/1", first_sha)["status"])
            (work / "value").write_text("two", encoding="utf-8"); self.git(work, "commit", "-am", "two")
            with self.assertRaisesRegex(ValueError, "different|conflict"):
                adapter.create_only("release/1", self.git(work, "rev-parse", "HEAD"))

    def test_branch_creation_revalidates_source_and_membership_after_persisted_intent(self):
        r = load_subject()
        intent = r.freeze_intent(repository="owner/repo", release=1, members={1: "a" * 40},
            policy="sha256:" + "b" * 64, source_branch="dev", source_sha="c" * 40,
            destination="release/1", authority="sha256:" + "d" * 64)
        self.assertEqual("ready", r.revalidate_frozen_intent(intent, source_sha="c" * 40,
            members={1: "a" * 40})["status"])
        self.assertEqual("blocked", r.revalidate_frozen_intent(intent, source_sha="e" * 40,
            members={1: "a" * 40})["status"])
        self.assertEqual("blocked", r.revalidate_frozen_intent(intent, source_sha="c" * 40,
            members={1: "f" * 40})["status"])

    def test_uncertain_provider_write_reconciles_before_retry(self):
        r = load_subject()
        class Adapter:
            def __init__(self): self.ref = None; self.calls = 0
            def observe(self, _name): return self.ref
            def create_only(self, name, sha): self.calls += 1; self.ref = sha; raise TimeoutError("unknown")
        adapter = Adapter()
        result = r.create_branch_reconciled(adapter, "release/1", "a" * 40)
        self.assertEqual("confirmed", result["status"])
        self.assertEqual(1, adapter.calls)


if __name__ == "__main__": unittest.main()
