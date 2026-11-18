"""G1051: inserted release contracts against an isolated real Git remote.

The integer source release is built by the existing real release workflow.
Only the approved `release insert` interface is used for the feature under test;
no production or GitHub service is contacted.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

import engine_fixtures as fx

from test_engine_branching import Branching
from test_engine_capabilities import plugin_copy

CAPABILITY = "insertable_release_targets"


class InsertedReleaseJourneys(Branching):
    def finished_source(self):
        """Produce genuine finished source provenance, not a fabricated line record."""
        self.gh.update(lambda state: state.update(auto_delete=False))
        _, line = self.cut_release_1()
        self.op(line, "sync")
        self.approve(line, "approve_finish")
        result = self.op(line, "finish")
        self.assertEqual("done", result["closed"]["reason"])
        source = result["ran"]["output"]["production_merge"]
        self.assertEqual(source, self.tip("main"))
        return line, source

    def activate(self):
        # Follow the approved upgrade order: engine first, then a policy that
        # requires the feature. A pre-feature engine must refuse to write it.
        policy = copy.deepcopy(self.w.policy)
        policy["settings"]["engine"].setdefault("requires", []).append(CAPABILITY)
        self.w.push_dev({".zzzops/POLICY.json": json.dumps(policy, indent=2) + "\n"},
                        "chore: opt in to insertable targets")

    def preview(self, target="1.1", source="1"):
        return self.w.ok("a", "release", "insert", target, "--from", source)

    def answer(self, preview):
        template = dict(preview["answer_template"])
        template.update(decision="approved", quote="approve patch", decided_by="Dave")
        return template

    def insert(self, preview, target="1.1", source="1", ok=True):
        args = ["release", "insert", target, "--from", source, "--answer", self.w.file(self.answer(preview))]
        return self.w.ok("a", *args) if ok else self.w.run("a", *args)

    def test_preview_is_read_only_and_insert_uses_finished_source_not_later_work(self):
        source_goal, source = self.finished_source()
        later = self.goal(release=2)
        self.done(later, code={"src/later_only.py": "later = True\n"})
        self.cut(2)
        self.assertTrue(self.tip("release/2"))
        self.assertNotEqual(source, self.tip("dev"))
        self.activate()
        patch = self.goal(release="1.1")

        refs_before = self.w.remote_git("for-each-ref", "--format=%(refname):%(objectname)", "refs/heads")
        preview = self.preview(target="1.1.0")
        refs_after = self.w.remote_git("for-each-ref", "--format=%(refname):%(objectname)", "refs/heads")
        self.assertEqual(refs_before, refs_after, "preview must not mutate any remote ref")
        p = preview["insert_preview"]
        self.assertEqual("1.1", str(p["target"]))
        self.assertEqual("1", str(p["source_release"]))
        self.assertEqual(source_goal, p["source_goal"])
        self.assertEqual(source, p["source_commit"])
        self.assertEqual(source, p["production_commit"])
        self.assertEqual("release/1.1", p["branch"])
        self.assertEqual("production_patch", p["mode"])
        self.assertTrue(p["fingerprint"])
        self.assertIn("2", json.dumps(p["later_lines"]))

        pending = self.nxt(patch)
        self.assertFalse(any(a.get("goal") == patch for a in pending["actions"]),
                         "patch members must not start before their isolated line exists")
        self.insert(preview, target="1.1.0")
        self.assertEqual(source, self.tip("release/1.1"))
        self.assertIsNone(self.tip("release/1.1.0"))
        self.assertIsNone(self.tip("release/1.01"))
        source_tree = self.w.remote_git("ls-tree", "-r", "--name-only", "refs/heads/release/1.1")
        self.assertNotIn("src/later_only.py", source_tree.splitlines())
        self.assertIn("src/later_only.py", self.w.remote_git("ls-tree", "-r", "--name-only", "refs/heads/release/2").splitlines())
        self.assertEqual(2, self.show(later)["goal"]["release"])
        # The same approved preview must be idempotent across aliases.
        self.insert(preview, target="1.01.0")
        self.assertIsNone(self.tip("release/1.01.0"))
        self.assertEqual(source, self.tip("release/1.1"))

    def test_uncut_later_integration_work_does_not_enter_patch_base(self):
        _, source = self.finished_source()
        later = self.goal(release=2)
        self.done(later, code={"src/not_in_patch.py": "later = True\n"})
        self.assertIsNone(self.tip("release/2"))
        self.activate()
        self.goal(release="1.0.1")
        preview = self.preview(target="1.0.1")
        self.assertEqual(source, preview["insert_preview"]["source_commit"])
        self.insert(preview, target="1.0.1")
        self.assertEqual(source, self.tip("release/1.0.1"))
        tree = self.w.remote_git("ls-tree", "-r", "--name-only", "refs/heads/release/1.0.1")
        self.assertNotIn("src/not_in_patch.py", tree.splitlines())
        self.assertIn("src/not_in_patch.py", self.w.remote_git("ls-tree", "-r", "--name-only", "refs/heads/dev").splitlines())

    def test_older_maintenance_finishes_without_rewinding_production(self):
        source_goal, source = self.finished_source()
        later = self.goal(release=2)
        self.done(later, code={"src/new_production.py": "version = 2\n"})
        line2 = self.cut(2)["goal"]
        self.op(line2, "sync")
        self.approve(line2, "approve_finish")
        self.op(line2, "finish")
        current_production = self.tip("main")
        self.assertNotEqual(source, current_production)
        self.activate()
        patch = self.goal(release="1.1")
        preview = self.preview()
        self.assertEqual(source_goal, preview["insert_preview"]["source_goal"])
        self.assertEqual(source, preview["insert_preview"]["source_commit"])
        self.assertEqual("maintenance", preview["insert_preview"]["mode"])
        inserted = self.insert(preview)
        line = inserted["goal"]
        self.assertEqual(source, self.tip("release/1.1"))
        self.done(patch, code={"src/maintenance.py": "fix = True\n"})
        before = {branch: self.tip(branch) for branch in ("main", "dev", "release/2")}
        self.op(line, "sync")
        self.assertEqual(before, {branch: self.tip(branch) for branch in before},
                         "pre-approval sync must not forward the patch")
        self.approve(line, "approve_finish")
        finished = self.op(line, "finish")
        self.assertFalse(finished["ran"]["output"].get("production_merge"),
                         "maintenance completion must not fabricate a production merge")
        self.assertEqual(current_production, self.tip("main"))
        self.assertNotIn("src/maintenance.py", self.w.remote_git("ls-tree", "-r", "--name-only", "refs/heads/main").splitlines())
        self.assertIn("src/maintenance.py", self.w.remote_git("ls-tree", "-r", "--name-only", "refs/heads/release/1.1").splitlines())
        self.assertEqual(2, self.show(later)["goal"]["release"])

        # A nested maintenance source is the approved immutable finish tip,
        # not the later mutable release ref.
        maintenance_tip = self.tip("release/1.1")
        self.push_branch("release/1.1", {"src/after_finish.py": "unapproved = True\n"},
                         "fix: external line move after finish")
        self.assertNotEqual(maintenance_tip, self.tip("release/1.1"))
        self.goal(release="1.1.1")
        nested = self.preview(target="1.1.1", source="1.1")
        self.assertEqual(maintenance_tip, nested["insert_preview"]["source_commit"])
        self.assertEqual("maintenance", nested["insert_preview"]["mode"])
        self.insert(nested, target="1.1.1", source="1.1")
        self.assertEqual(maintenance_tip, self.tip("release/1.1.1"))
        self.assertEqual(current_production, self.tip("main"))

    def test_changed_production_after_preview_refuses_stale_approval(self):
        _, source = self.finished_source()
        self.activate()
        self.goal(release="1.1")
        preview = self.preview()
        self.assertEqual(source, preview["insert_preview"]["production_commit"])
        advanced = self.push_branch("main", {"src/external.py": "external = True\n"},
                                    "fix: external production advance")
        self.assertNotEqual(source, advanced)
        rc, result = self.insert(preview, ok=False)
        self.assertNotEqual(0, rc, result)
        self.assertEqual("preview_stale", result.get("error", {}).get("code"), result)
        self.assertIsNone(self.tip("release/1.1"))
        self.assertEqual(advanced, self.tip("main"))

    def test_external_production_advance_during_atomic_line_creation_stays_pending(self):
        # This precondition is itself a red observation on the unimplemented
        # baseline; it avoids starting a test-process barrier that cannot be hit.
        capability = fx.PLUGIN_CODE / "engine/capabilities/insertable_release_targets.txt"
        self.assertTrue(capability.is_file(), "insertable release capability is not implemented")
        _, source = self.finished_source()
        self.activate()
        patch = self.goal(release="1.1")
        preview = self.preview()
        answer_file = self.w.file(self.answer(preview))
        race_dir = Path(self.tmp) / "controlled-git-race"
        race_dir.mkdir()
        race_ready = race_dir / "atomic-push-ready"
        race_continue = race_dir / "continue"
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        wrapper = race_dir / "git"
        wrapper.write_text(
            f"#!{sys.executable}\n"
            "import os, sys, time\n"
            "from pathlib import Path\n"
            "args = sys.argv[1:]\n"
            "if 'push' in args and '--atomic' in args and "
            "any(x.endswith(':refs/heads/release/1.1') for x in args):\n"
            "    Path(os.environ['G1051_RACE_READY']).write_text('ready')\n"
            "    deadline = time.monotonic() + 20\n"
            "    while not Path(os.environ['G1051_RACE_CONTINUE']).exists():\n"
            "        if time.monotonic() >= deadline: sys.exit(124)\n"
            "        time.sleep(0.01)\n"
            f"os.execv({real_git!r}, [{real_git!r}] + args)\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        env = self.w.cli_env(extra={
            "PATH": str(race_dir) + os.pathsep + os.environ.get("PATH", ""),
            "G1051_RACE_READY": str(race_ready),
            "G1051_RACE_CONTINUE": str(race_continue),
        })
        proc = subprocess.Popen(
            [sys.executable, str(fx.PLUGIN_CODE / "zzzops.py"), "release", "insert", "1.1",
             "--from", "1", "--answer", answer_file],
            cwd=self.w.clones["a"].path, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            deadline = time.monotonic() + 20
            while not race_ready.exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(race_ready.exists(), "insert did not reach the real atomic line-creation push")
            advanced = self.push_branch("main", {"src/after_final_read.py": "external = True\n"},
                                        "fix: advance production during insert")
            self.assertNotEqual(source, advanced)
            race_continue.write_text("continue", encoding="utf-8")
            stdout, stderr = proc.communicate(timeout=30)
            result = json.loads(stdout)
            self.assertEqual(advanced, self.tip("main"), (result, stderr))
            if self.tip("release/1.1"):
                self.assertEqual(source, self.tip("release/1.1"), "line must keep the approved immutable source")
            self.assertFalse(any(a.get("goal") == patch for a in self.nxt(patch)["actions"]),
                             "a production move before post-push verification must keep members blocked")
            self.assertIsNone(self.tip("release/1.1.0"))
        finally:
            race_continue.write_text("continue", encoding="utf-8")
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate(timeout=5)

    def test_old_writer_cannot_mutate_a_capability_enabled_repository(self):
        self.activate()
        old_engine = plugin_copy(self.tmp)
        (old_engine / "engine/capabilities/insertable_release_targets.txt").unlink(missing_ok=True)
        refs_before = self.w.remote_git("for-each-ref", "--format=%(refname):%(objectname)", "refs/heads")
        goal_file = self.w.file({"title": "Patch", "spec": "Patch", "release": "1.1"})
        proc = subprocess.run([sys.executable, str(old_engine / "zzzops.py"), "new", "--file", goal_file],
                              cwd=self.w.clones["a"].path, env=self.w.cli_env(), capture_output=True, text=True,
                              timeout=30)
        result = json.loads(proc.stdout)
        self.assertNotEqual(0, proc.returncode, result)
        self.assertEqual("engine_too_old", result.get("error", {}).get("code"), result)
        self.assertEqual(refs_before, self.w.remote_git("for-each-ref", "--format=%(refname):%(objectname)", "refs/heads"))

    def test_insert_and_dotted_writes_rejected_before_policy_opt_in(self):
        refs_before = self.w.remote_git("for-each-ref", "--format=%(refname):%(objectname)", "refs/heads")
        rc, output = self.w.run("a", "release", "insert", "1.1", "--from", "1")
        self.assertNotEqual(0, rc, output)
        rc, output = self.w.run("a", "new", "--file", self.w.file({"title": "Patch", "spec": "Patch", "release": "1.1"}))
        self.assertNotEqual(0, rc, output)
        self.assertEqual(refs_before, self.w.remote_git("for-each-ref", "--format=%(refname):%(objectname)", "refs/heads"))


if __name__ == "__main__":
    unittest.main()
