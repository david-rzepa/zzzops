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
from engine import store

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

    def test_approved_patch_reaches_production_and_later_line_only_after_approval(self):
        _, source = self.finished_source()
        later = self.goal(release=2)
        self.done(later, code={"src/later_only.py": "later = True\n"})
        self.cut(2)
        self.activate()
        patch = self.goal(release="1.0.1")
        preview = self.preview(target="1.0.1")
        inserted = self.insert(preview, target="1.0.1")
        line = inserted["goal"]
        self.done(patch, code={"src/isolated_patch.py": "patched = True\n"})
        patch_tip = self.tip("release/1.0.1")
        self.assertTrue(self.is_ancestor(source, patch_tip))
        before = {branch: self.tip(branch) for branch in ("main", "dev", "release/2")}
        self.op(line, "sync")
        self.assertEqual(before, {branch: self.tip(branch) for branch in before},
                         "inserted line sync must be record-only before owner approval")
        self.approve(line, "approve_finish")
        finished = self.op(line, "finish")
        self.assertEqual("done", finished["closed"]["reason"], finished)
        self.assertTrue(self.is_ancestor(patch_tip, self.tip("main")))
        self.assertTrue(self.is_ancestor(patch_tip, self.tip("dev")))
        self.assertTrue(self.is_ancestor(patch_tip, self.tip("release/2")))
        prod_tree = self.w.remote_git("ls-tree", "-r", "--name-only", "refs/heads/main").splitlines()
        later_tree = self.w.remote_git("ls-tree", "-r", "--name-only", "refs/heads/release/2").splitlines()
        self.assertIn("src/isolated_patch.py", prod_tree)
        self.assertNotIn("src/later_only.py", prod_tree)
        self.assertIn("src/isolated_patch.py", later_tree)
        self.assertIn("src/later_only.py", later_tree)
        self.assertEqual(2, self.show(later)["goal"]["release"])

    def test_conflicting_forward_port_preserves_later_line_and_exposes_partial_state(self):
        self.finished_source()
        later = self.goal(release=2)
        self.done(later, code={"src/conflict.txt": "later side\n"})
        self.cut(2)
        self.activate()
        patch = self.goal(release="1.1")
        inserted = self.insert(self.preview())
        line = inserted["goal"]
        self.done(patch, code={"src/conflict.txt": "patch side\n"})
        self.op(line, "sync")
        self.approve(line, "approve_finish")
        dev_before = self.tip("dev")
        later_before = self.tip("release/2")
        result = self.op(line, "finish")
        self.assertNotEqual("done", (result.get("closed") or {}).get("reason"), result)
        self.assertEqual(dev_before, self.tip("dev"), "conflicting integration must not be overwritten")
        self.assertEqual(later_before, self.tip("release/2"), "later release must not be overwritten")
        self.assertTrue(result.get("ran", {}).get("blocked") or result.get("next", {}).get("needs_human"), result)

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

    def test_production_advance_after_finish_approval_cannot_be_overwritten(self):
        _, source = self.finished_source()
        self.activate()
        patch = self.goal(release="1.1")
        preview = self.preview()
        inserted = self.insert(preview)
        line = inserted["goal"]
        self.done(patch, code={"src/approved_patch.py": "fixed = True\n"})
        self.op(line, "sync")
        self.approve(line, "approve_finish")
        advanced = self.push_branch("main", {"src/concurrent_production.py": "newer = True\n"},
                                    "fix: advance production after approval")
        self.assertNotEqual(source, advanced)
        rc, result = self.w.run("a", "start", str(line), "finish", "--as", "claude:aaaa/op")
        self.assertFalse(rc == 0 and result.get("ran", {}).get("outcome") == "done", result)
        self.assertEqual(advanced, self.tip("main"), "finish must not overwrite newer production")
        self.assertNotIn("src/approved_patch.py", self.w.remote_git("ls-tree", "-r", "--name-only", "refs/heads/main").splitlines())

    def test_revoked_source_after_actual_finish_approval_blocks_promotion(self):
        capability = fx.PLUGIN_CODE / "engine/capabilities/insertable_release_targets.txt"
        self.assertTrue(capability.is_file(), "insertable release capability is not implemented")
        source_goal, source = self.finished_source()
        self.activate()
        patch = self.goal(release="1.1")
        line = self.insert(self.preview())["goal"]
        self.done(patch, code={"src/provenance_patch.py": "fixed = True\n"})
        self.op(line, "sync")
        self.approve(line, "approve_finish")
        before = {branch: self.tip(branch) for branch in ("main", "dev", "release/1.1")}
        self.assertEqual(source, before["main"])

        # An external writer reopens the exact source release after the owner
        # approved finish. This preserves history but revokes closed provenance.
        ref = f"refs/heads/zzzops/goal/g{source_goal}"
        writer = self.w.add_clone("reopen-source")
        writer.git("fetch", "-q", "origin", ref)
        writer.git("checkout", "-q", "--detach", "FETCH_HEAD")
        doc = json.loads(writer.git("show", "HEAD:goal.json"))
        doc["state"], doc["closed"] = "open", None
        msg = store.with_trailers(store.goal_message("edit", source_goal, "reopened", "open"),
                                  doc, self.w.policy["settings"])
        reopened = writer.commit({"goal.json": json.dumps(doc, indent=2) + "\n"}, msg)
        writer.git("push", "-q", "origin", f"HEAD:{ref}")
        self.assertEqual(reopened, self.goal_tip(source_goal))

        # This is an actual finish attempt after a real recorded approval, not
        # a check that a never-approved node happens to be unready.
        rc, result = self.w.run("a", "start", str(line), "finish", "--as", "claude:aaaa/op")
        status = self.nxt(line)
        self.assertFalse(rc == 0 and result.get("ran", {}).get("outcome") == "done", result)
        self.assertEqual(before, {branch: self.tip(branch) for branch in before},
                         "revoked source must not promote or forward")
        detail = json.dumps({"finish": result, "next": status}).lower()
        self.assertTrue("source" in detail or "provenance" in detail, detail)
        self.assertIn(str(source_goal), detail, "recovery must identify the revoked source")

    def test_external_production_move_at_actual_finish_update_is_not_overwritten(self):
        capability = fx.PLUGIN_CODE / "engine/capabilities/insertable_release_targets.txt"
        self.assertTrue(capability.is_file(), "insertable release capability is not implemented")
        self.finished_source()
        self.activate()
        patch = self.goal(release="1.1")
        line = self.insert(self.preview())["goal"]
        self.done(patch, code={"src/final_write_patch.py": "fixed = True\n"})
        self.op(line, "sync")
        self.approve(line, "approve_finish")
        dev_before = self.tip("dev")
        race_dir = Path(self.tmp) / "finish-write-race"
        race_dir.mkdir()
        ready, proceed = race_dir / "ready", race_dir / "proceed"
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        wrapper = race_dir / "git"
        wrapper.write_text(
            f"#!{sys.executable}\n"
            "import os, subprocess, sys, time\n"
            "from pathlib import Path\n"
            "args = sys.argv[1:]\n"
            "transaction = 'update-ref' in args and '--stdin' in args\n"
            "data = sys.stdin.buffer.read() if transaction else None\n"
            "targeted = ('push' in args and any('refs/heads/main' in x for x in args)) or "
            "(transaction and b'refs/heads/main' in data)\n"
            "if targeted:\n"
            "    Path(os.environ['G1051_RACE_READY']).write_text('ready')\n"
            "    deadline = time.monotonic() + 20\n"
            "    while not Path(os.environ['G1051_RACE_CONTINUE']).exists():\n"
            "        if time.monotonic() >= deadline: sys.exit(124)\n"
            "        time.sleep(0.01)\n"
            f"p = subprocess.run([{real_git!r}] + args, input=data)\n"
            "sys.exit(p.returncode)\n", encoding="utf-8")
        wrapper.chmod(0o755)
        env = self.w.cli_env(extra={"PATH": str(race_dir) + os.pathsep + self.w.extra_env["PATH"],
                                   "G1051_RACE_READY": str(ready), "G1051_RACE_CONTINUE": str(proceed)})
        proc = subprocess.Popen([sys.executable, str(fx.PLUGIN_CODE / "zzzops.py"), "start", str(line),
                                 "finish", "--as", "claude:aaaa/op"], cwd=self.w.clones["a"].path,
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 20
            while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists(), "finish did not reach an actual guarded production update")
            moved = self.push_branch("main", {"src/external_finish.py": "external = True\n"},
                                     "fix: external production write during finish")
            proceed.write_text("continue", encoding="utf-8")
            stdout, stderr = proc.communicate(timeout=30)
            result = json.loads(stdout)
            self.assertEqual(moved, self.tip("main"), (result, stderr))
            self.assertEqual(dev_before, self.tip("dev"), "failed promotion must not forward patch")
            self.assertFalse((result.get("closed") or {}).get("reason") == "done", result)
        finally:
            proceed.write_text("continue", encoding="utf-8")
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate(timeout=5)

    def test_protected_remote_refusal_does_not_fall_back_to_unguarded_production_write(self):
        capability = fx.PLUGIN_CODE / "engine/capabilities/insertable_release_targets.txt"
        self.assertTrue(capability.is_file(), "insertable release capability is not implemented")
        self.finished_source()
        self.activate()
        patch = self.goal(release="1.1")
        line = self.insert(self.preview())["goal"]
        self.done(patch, code={"src/protected_patch.py": "fixed = True\n"})
        self.op(line, "sync")
        self.approve(line, "approve_finish")
        main_before, dev_before = self.tip("main"), self.tip("dev")
        hook = Path(self.w.remote) / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\nwhile read old new ref; do\n"
                        "  if [ \"$ref\" = refs/heads/main ]; then\n"
                        "    echo 'protected main: atomic update refused' >&2; exit 1\n"
                        "  fi\ndone\nexit 0\n", encoding="utf-8")
        hook.chmod(0o755)
        rc, result = self.w.run("a", "start", str(line), "finish", "--as", "claude:aaaa/op")
        self.assertFalse(rc == 0 and result.get("ran", {}).get("outcome") == "done", result)
        self.assertEqual(main_before, self.tip("main"), "protected main must not be bypassed")
        self.assertEqual(dev_before, self.tip("dev"), "failed promotion must not forward patch")

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
            "PATH": str(race_dir) + os.pathsep + self.w.extra_env["PATH"],
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

    def _interleave_patch_merge(self, changed_ref):
        capability = fx.PLUGIN_CODE / "engine/capabilities/insertable_release_targets.txt"
        self.assertTrue(capability.is_file(), "insertable release capability is not implemented")
        source_goal, source = self.finished_source()
        self.activate()
        patch = self.goal(release="1.1")
        line = self.insert(self.preview())["goal"]
        self.deliver(patch, code={"src/patch_race.py": "fixed = True\n"})
        self.op(patch, "integrate")
        self.approve(patch, "approve_merge")
        dev_before = self.tip("dev")
        main_before = self.tip("main")
        race_dir = Path(self.tmp) / ("patch-race-" + changed_ref)
        race_dir.mkdir()
        ready = race_dir / "ready"
        proceed = race_dir / "proceed"
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        wrapper = race_dir / "git"
        wrapper.write_text(
            f"#!{sys.executable}\n"
            "import os, sys, time\n"
            "from pathlib import Path\n"
            "args = sys.argv[1:]\n"
            "if 'push' in args and any('release/1.1' in x for x in args):\n"
            "    Path(os.environ['G1051_RACE_READY']).write_text('ready')\n"
            "    deadline = time.monotonic() + 20\n"
            "    while not Path(os.environ['G1051_RACE_CONTINUE']).exists():\n"
            "        if time.monotonic() >= deadline: sys.exit(124)\n"
            "        time.sleep(0.01)\n"
            f"os.execv({real_git!r}, [{real_git!r}] + args)\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        env = self.w.cli_env(extra={"PATH": str(race_dir) + os.pathsep + self.w.extra_env["PATH"],
                                   "G1051_RACE_READY": str(ready), "G1051_RACE_CONTINUE": str(proceed)})
        proc = subprocess.Popen([sys.executable, str(fx.PLUGIN_CODE / "zzzops.py"), "start", str(patch),
                                 "merge", "--as", "claude:aaaa/op"], cwd=self.w.clones["a"].path,
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 20
            while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists(), "patch merge never reached an actual Git destination update")
            if changed_ref == "target":
                moved = self.push_branch("release/1.1", {"src/external_line.py": "external = True\n"},
                                         "fix: external target race")
            elif changed_ref == "production":
                moved = self.push_branch("main", {"src/external_main.py": "external = True\n"},
                                         "fix: external production race")
            else:
                # A fast-forward by a separate writer changes source-goal
                # provenance after the engine's read, before the actual push.
                ref = f"refs/heads/zzzops/goal/g{source_goal}"
                writer = self.w.add_clone("source-writer")
                writer.git("fetch", "-q", "origin", ref)
                writer.git("checkout", "-q", "--detach", "FETCH_HEAD")
                doc = json.loads(writer.git("show", "HEAD:goal.json"))
                doc["state"], doc["closed"] = "open", None
                msg = store.with_trailers(store.goal_message("edit", source_goal, "reopened", "open"),
                                          doc, self.w.policy["settings"])
                moved = writer.commit({"goal.json": json.dumps(doc, indent=2) + "\n"}, msg)
                writer.git("push", "-q", "origin", f"HEAD:{ref}")
                self.assertEqual(moved, self.goal_tip(source_goal))
            proceed.write_text("continue", encoding="utf-8")
            stdout, stderr = proc.communicate(timeout=30)
            result = json.loads(stdout)
            self.assertEqual(dev_before, self.tip("dev"), (result, stderr))
            self.assertEqual(moved if changed_ref == "production" else main_before, self.tip("main"))
            if changed_ref == "target":
                self.assertEqual(moved, self.tip("release/1.1"), "destination CAS must not overwrite the external tip")
                self.assertFalse((result.get("closed") or {}).get("reason") == "done", result)
            else:
                # The isolated line may advance provisionally: a CAS on that
                # destination cannot detect a different ref's concurrent move.
                self.assertIsNotNone(self.tip("release/1.1"))
                line_status = self.nxt(line)
                self.assertFalse(any(a.get("goal") == line and a.get("node") == "finish"
                                     for a in line_status.get("actions", [])), line_status)
        finally:
            proceed.write_text("continue", encoding="utf-8")
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate(timeout=5)

    def test_patch_destination_move_at_actual_push_is_not_overwritten(self):
        self._interleave_patch_merge("target")

    def test_only_production_move_can_leave_patch_line_provisional(self):
        self._interleave_patch_merge("production")

    def test_only_source_goal_move_can_leave_patch_line_provisional(self):
        self._interleave_patch_merge("source")

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

    def test_completed_integration_member_requires_explicit_recovery_before_insertion(self):
        capability = fx.PLUGIN_CODE / "engine/capabilities/insertable_release_targets.txt"
        self.assertTrue(capability.is_file(), "insertable release capability is not implemented")
        self.finished_source()
        completed = self.goal(release=2)
        self.done(completed, code={"src/already_integrated.py": "prior = True\n"})
        prior_dev = self.tip("dev")
        self.activate()
        patch = self.goal(release="1.1")
        clean_preview = self.preview()
        # An older external writer/import may already have recorded a closed
        # patch-target member after delivering it to integration. Preserve the
        # real completed checkpoint and its parent history when modeling it.
        ref = f"refs/heads/zzzops/goal/g{completed}"
        writer = self.w.add_clone("imported-completion")
        writer.git("fetch", "-q", "origin", ref)
        writer.git("checkout", "-q", "--detach", "FETCH_HEAD")
        doc = json.loads(writer.git("show", "HEAD:goal.json"))
        doc["release"] = "1.1"
        msg = store.with_trailers(store.goal_message("edit", completed, "edited", "closed"),
                                  doc, self.w.policy["settings"])
        new_tip = writer.commit({"goal.json": json.dumps(doc, indent=2) + "\n"}, msg)
        writer.git("push", "-q", "origin", f"HEAD:{ref}")
        rc, out = self.w.run("a", "release", "insert", "1.1", "--from", "1")
        self.assertIn(str(completed), json.dumps(out), "preview must identify the completed member requiring recovery")
        if rc == 0:
            self.assertIn(completed, out["insert_preview"]["already_completed_members"])
        # If the blocked preview exposes an approval template, try that exact
        # newly approved fingerprint. Otherwise submit the genuine previously
        # approved preview, which became stale when the completed member arrived.
        approval = out if rc == 0 and out.get("answer_template") else clean_preview
        insert_rc, inserted = self.insert(approval, ok=False)
        self.assertEqual(new_tip, self.goal_tip(completed), "insertion must not rewrite completed history")
        if insert_rc == 0:
            # A provisional ref is permitted only while member dispatch remains
            # blocked and the completed integration work is not mistaken for patch work.
            self.assertFalse(any(a.get("goal") == patch for a in self.nxt(patch)["actions"]), inserted)
            self.assertEqual(clean_preview["insert_preview"]["source_commit"], self.tip("release/1.1"))
            tree = self.w.remote_git("ls-tree", "-r", "--name-only", "refs/heads/release/1.1").splitlines()
            self.assertNotIn("src/already_integrated.py", tree)
        else:
            self.assertIsNone(self.tip("release/1.1"))
        self.assertTrue(self.is_ancestor(prior_dev, self.tip("dev")))

    def test_retargeted_inflight_work_cannot_integrate_into_old_patch_line(self):
        capability = fx.PLUGIN_CODE / "engine/capabilities/insertable_release_targets.txt"
        self.assertTrue(capability.is_file(), "insertable release capability is not implemented")
        self.finished_source()
        self.activate()
        patch = self.goal(release="1.1")
        self.insert(self.preview())
        self.deliver(patch, code={"src/retargeted_work.py": "pending = True\n"})
        work = self.tip(f"zzzops/work/g{patch}")
        old_line = self.tip("release/1.1")
        self.w.ok("a", "edit", str(patch), "--set", 'release="1.0.1"', "--base", self.goal_tip(patch))
        status = self.nxt(patch)
        self.assertFalse(any(a.get("goal") == patch and a.get("node") in ("integrate", "merge")
                             for a in status.get("actions", [])), status)
        self.assertEqual(old_line, self.tip("release/1.1"), "retargeting must not mutate the old patch line")
        self.assertEqual(work, self.tip(f"zzzops/work/g{patch}"), "in-flight work must be retained")
        self.assertIsNone(self.tip("release/1.0.1"))

    def test_alias_collision_blocks_capability_activation_without_renaming_refs(self):
        base = self.tip("main")
        self.w.remote_git("update-ref", "refs/heads/release/1", base)
        self.w.remote_git("update-ref", "refs/heads/release/1.0", base)
        self.activate()
        refs_before = self.w.remote_git("for-each-ref", "--format=%(refname):%(objectname)", "refs/heads")
        result = self.w.ok("a", "next")
        self.assertIn("collision", json.dumps(result.get("blockers", [])).lower(), result)
        rc, output = self.w.run("a", "release", "insert", "1.1", "--from", "1")
        self.assertNotEqual(0, rc, output)
        self.assertEqual(refs_before, self.w.remote_git("for-each-ref", "--format=%(refname):%(objectname)", "refs/heads"))
        self.assertEqual(base, self.tip("release/1"))
        self.assertEqual(base, self.tip("release/1.0"))

    def test_later_dependency_is_explicitly_refused_or_shown_as_blocker(self):
        self.finished_source()
        self.activate()
        later = self.goal(release=2)
        requested = {"title": "Patch with later dependency", "spec": "s", "release": "1.1", "depends_on": [later]}
        rc, created = self.w.run("a", "new", "--file", self.w.file(requested))
        if rc:
            self.assertIn("depend", json.dumps(created).lower(), created)
            return
        patch = created["created"]["id"]
        status = self.nxt(patch)
        self.assertFalse(any(a.get("goal") == patch and a.get("node") in ("base", "integrate", "merge")
                             for a in status.get("actions", [])), status)
        self.assertIn(str(later), json.dumps(status), "dependency must be visible rather than silently ignored")

    def test_insert_and_dotted_writes_rejected_before_policy_opt_in(self):
        refs_before = self.w.remote_git("for-each-ref", "--format=%(refname):%(objectname)", "refs/heads")
        rc, output = self.w.run("a", "release", "insert", "1.1", "--from", "1")
        self.assertNotEqual(0, rc, output)
        rc, output = self.w.run("a", "new", "--file", self.w.file({"title": "Patch", "spec": "Patch", "release": "1.1"}))
        self.assertNotEqual(0, rc, output)
        self.assertEqual(refs_before, self.w.remote_git("for-each-ref", "--format=%(refname):%(objectname)", "refs/heads"))


class InsertWithoutBranching(Branching):
    branching = False

    def test_identity_remains_available_but_insertion_requires_isolated_line_policy(self):
        policy = copy.deepcopy(self.w.policy)
        policy["settings"]["engine"].setdefault("requires", []).append(CAPABILITY)
        self.w.push_dev({".zzzops/POLICY.json": json.dumps(policy, indent=2) + "\n"},
                        "chore: opt in to insertable targets")
        patch = self.goal(release="1.1")
        self.assertEqual("1.1", self.show(patch)["goal"]["release"])
        before = self.w.remote_git("for-each-ref", "--format=%(refname):%(objectname)", "refs/heads")
        rc, out = self.w.run("a", "release", "insert", "1.1", "--from", "1")
        self.assertNotEqual(0, rc, out)
        self.assertIn("branch", json.dumps(out).lower(), out)
        self.assertEqual(before, self.w.remote_git("for-each-ref", "--format=%(refname):%(objectname)", "refs/heads"))


if __name__ == "__main__":
    unittest.main()
