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

    def forward_port_item(self, line, destination, source):
        """Verify the human item names the actual PR's source, head and base."""
        status = self.nxt(line)
        items = [item for item in status["needs_human"]
                 if item.get("node") == "finish" and destination in item.get("question", "")]
        self.assertEqual(1, len(items), status)
        item = items[0]
        prs = [pr for pr in self.gh.load()["prs"].values()
               if pr["state"] == "OPEN" and pr["baseRefName"] == destination]
        self.assertEqual(1, len(prs), prs)
        pr = prs[0]
        question = item["question"]
        self.assertIn(str(pr["number"]), question)
        self.assertIn(self.tip(pr["headRefName"]), question)
        self.assertIn(self.tip(destination), question)
        self.assertIn(source, question)
        return item, pr

    def approved_patch_waiting_for_dev_forward(self):
        _, source = self.finished_source()
        later = self.goal(release=2)
        self.done(later, code={"src/later_only.py": "later = True\n"})
        self.cut(2)
        self.activate()
        patch = self.goal(release="1.0.1")
        line = self.insert(self.preview(target="1.0.1"), target="1.0.1")["goal"]
        self.done(patch, code={"src/isolated_patch.py": "patched = True\n"})
        patch_tip = self.tip("release/1.0.1")
        self.assertTrue(self.is_ancestor(source, patch_tip))
        before = {branch: self.tip(branch) for branch in ("main", "dev", "release/2")}
        self.op(line, "sync")
        self.assertEqual(before, {branch: self.tip(branch) for branch in before},
                         "inserted line sync must be record-only before owner approval")
        self.approve(line, "approve_finish")
        first = self.op(line, "finish")
        self.assertNotEqual("done", (first.get("closed") or {}).get("reason"), first)
        self.assertTrue(self.is_ancestor(patch_tip, self.tip("main")))
        self.assertEqual(before["dev"], self.tip("dev"), "dev waits for its own approval")
        self.assertEqual(before["release/2"], self.tip("release/2"), "later line waits for its own approval")
        item, pr = self.forward_port_item(line, "dev", patch_tip)
        return line, later, patch_tip, item, pr

    def test_approved_patch_reaches_production_and_later_line_only_after_approval(self):
        line, later, patch_tip, _, dev_pr = self.approved_patch_waiting_for_dev_forward()
        release_before = self.tip("release/2")
        self.answer_blocked(line, "finish", text="I approve this exact dev forward-port")
        second = self.op(line, "finish")
        self.assertNotEqual("done", (second.get("closed") or {}).get("reason"), second)
        self.assertEqual("MERGED", self.gh.pr(dev_pr["number"])["state"])
        self.assertTrue(self.is_ancestor(patch_tip, self.tip("dev")))
        self.assertEqual(release_before, self.tip("release/2"), "later line waits for its own approval")
        _, later_pr = self.forward_port_item(line, "release/2", patch_tip)
        self.answer_blocked(line, "finish", text="I approve this exact release/2 forward-port")
        finished = self.op(line, "finish")
        self.assertEqual("done", finished["closed"]["reason"], finished)
        self.assertEqual("MERGED", self.gh.pr(later_pr["number"])["state"])
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

    def test_changed_forward_port_pr_head_invalidates_previous_approval(self):
        line, _, patch_tip, _, pr = self.approved_patch_waiting_for_dev_forward()
        dev_before = self.tip("dev")
        old_head = self.tip(pr["headRefName"])
        self.answer_blocked(line, "finish", text="I approve the displayed dev forward-port")
        moved = self.push_branch(pr["headRefName"], {"src/unapproved_forward.py": "unapproved = True\n"},
                                 "fix: change forward-port head after approval")
        self.assertNotEqual(old_head, moved)
        result = self.op(line, "finish")
        self.assertNotEqual("done", (result.get("closed") or {}).get("reason"), result)
        self.assertEqual(dev_before, self.tip("dev"), "old approval must not authorize a changed PR")
        self.assertEqual("OPEN", self.gh.pr(pr["number"])["state"])
        refreshed, current = self.forward_port_item(line, "dev", patch_tip)
        self.assertEqual(pr["number"], current["number"])
        self.assertIn(self.tip(pr["headRefName"]), refreshed["question"])
        self.assertNotEqual(old_head, self.tip(pr["headRefName"]))

    def test_declined_forward_port_is_not_merged(self):
        line, _, _, item, pr = self.approved_patch_waiting_for_dev_forward()
        dev_before = self.tip("dev")
        self.w.ok("a", "answer", str(line), "finish", "--fp", item["fp"],
                  "--file", self.w.file({"text": "I do not approve this forward-port", "quote": "No", "decided_by": "Dave"}))
        rc, result = self.w.run("a", "start", str(line), "finish", "--as", "claude:aaaa/op")
        self.assertFalse(rc == 0 and (result.get("closed") or {}).get("reason") == "done", result)
        self.assertEqual(dev_before, self.tip("dev"), "a refusal must never approve or merge the PR")
        self.assertEqual("OPEN", self.gh.pr(pr["number"])["state"])

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

    def _reopen_source(self, source_goal, clone_name):
        ref = f"refs/heads/zzzops/goal/g{source_goal}"
        writer = self.w.add_clone(clone_name)
        writer.git("fetch", "-q", "origin", ref)
        writer.git("checkout", "-q", "--detach", "FETCH_HEAD")
        doc = json.loads(writer.git("show", "HEAD:goal.json"))
        doc["state"], doc["closed"] = "open", None
        msg = store.with_trailers(store.goal_message("edit", source_goal, "reopened", "open"),
                                  doc, self.w.policy["settings"])
        tip = writer.commit({"goal.json": json.dumps(doc, indent=2) + "\n"}, msg)
        writer.git("push", "-q", "origin", f"HEAD:{ref}")
        return tip

    def _at_provider_merge(self, goal, node, mutate, *, approved_head, target):
        """Hold the actual provider merge call after engine prechecks.

        FakeGitHub provides the local PR contract; this is not evidence of
        real GitHub branch-protection enforcement.
        """
        race_dir = Path(self.tmp) / f"provider-merge-{goal}-{node}"
        race_dir.mkdir()
        ready, proceed = race_dir / "ready", race_dir / "proceed"
        real_gh = str(Path(self.gh.bindir) / "gh")
        wrapper = race_dir / "gh"
        wrapper.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys, time\n"
            "from pathlib import Path\n"
            "args = sys.argv[1:]\n"
            "if args[:2] == ['pr', 'merge'] or "
            "(args[:2] == ['api', 'graphql'] and 'mergePullRequest' in ' '.join(args)):\n"
            "    ready = Path(os.environ['G1051_RACE_READY'])\n"
            "    pending = ready.with_suffix('.pending')\n"
            "    pending.write_text(json.dumps(args))\n"
            "    os.replace(pending, ready)\n"
            "    deadline = time.monotonic() + 20\n"
            "    while not Path(os.environ['G1051_RACE_CONTINUE']).exists():\n"
            "        if time.monotonic() >= deadline: sys.exit(124)\n"
            "        time.sleep(0.01)\n"
            f"os.execv({real_gh!r}, [{real_gh!r}] + args)\n", encoding="utf-8")
        wrapper.chmod(0o755)
        env = self.w.cli_env(extra={"PATH": str(race_dir) + os.pathsep + self.w.extra_env["PATH"],
                                   "G1051_RACE_READY": str(ready), "G1051_RACE_CONTINUE": str(proceed)})
        proc = subprocess.Popen([sys.executable, str(fx.PLUGIN_CODE / "zzzops.py"), "start", str(goal),
                                 node, "--as", "claude:aaaa/op"], cwd=self.w.clones["a"].path,
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 20
            while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists(), "operation did not reach a protected provider merge")
            call = json.loads(ready.read_text(encoding="utf-8"))
            # Check the intercepted call itself, not earlier fixture PR merges.
            # The provider's expected-head argument must bind the exact synced
            # subject the owner approved, and this must be the target PR.
            if call[:2] == ["pr", "merge"]:
                pr_number = int(call[2].rstrip("/").split("/")[-1])
                pr = self.gh.pr(pr_number)
                self.assertEqual(target, pr["baseRefName"])
                self.assertEqual(approved_head, self.tip(pr["headRefName"]))
                if "--match-head-commit" in call:
                    guard = call[call.index("--match-head-commit") + 1]
                else:
                    guard = next((x.split("=", 1)[1] for x in call
                                  if x.startswith("--match-head-commit=")), None)
                self.assertEqual(approved_head, guard, "finish PR must guard the exact approved head")
            else:
                payload = " ".join(call)
                self.assertIn("expectedHeadOid", payload)
                self.assertIn(approved_head, payload)
                candidates = [p for p in self.gh.load()["prs"].values()
                              if p["state"] == "OPEN" and p["baseRefName"] == target
                              and self.tip(p["headRefName"]) == approved_head]
                self.assertEqual(1, len(candidates), candidates)
                pr = candidates[0]
            changed = mutate(pr)
            proceed.write_text("continue", encoding="utf-8")
            stdout, stderr = proc.communicate(timeout=30)
            return changed, proc.returncode, json.loads(stdout), stderr
        finally:
            proceed.write_text("continue", encoding="utf-8")
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate(timeout=5)

    def test_source_revoked_during_protected_finish_records_merge_and_pauses_forwarding(self):
        capability = fx.PLUGIN_CODE / "engine/capabilities/insertable_release_targets.txt"
        self.assertTrue(capability.is_file(), "insertable release capability is not implemented")
        source_goal, _ = self.finished_source()
        self.activate()
        patch = self.goal(release="1.1")
        line = self.insert(self.preview())["goal"]
        self.done(patch, code={"src/source_race_patch.py": "fixed = True\n"})
        synced = self.op(line, "sync")["ran"]["output"]["merged"]
        self.assertEqual(self.tip("release/1.1"), synced)
        self.approve(line, "approve_finish")
        main_before, dev_before = self.tip("main"), self.tip("dev")
        existing_prs = set(self.gh.load()["prs"])
        moved, rc, result, stderr = self._at_provider_merge(
            line, "finish", lambda pr: self._reopen_source(source_goal, "finish-source-revoker"),
            approved_head=synced, target="main")
        self.assertEqual(moved, self.goal_tip(source_goal))
        self.assertEqual(dev_before, self.tip("dev"), "post-merge mismatch must pause forward-port")
        self.assertNotEqual(main_before, self.tip("main"), "protected PR may merge before the race is detected")
        self.assertTrue(self.is_ancestor(main_before, self.tip("main")), "do not roll production backward")
        self.assertIn("src/source_race_patch.py", self.w.remote_git("ls-tree", "-r", "--name-only", "refs/heads/main").splitlines())
        self.assertFalse((result.get("closed") or {}).get("reason") == "done", (result, stderr))
        details = json.dumps({"result": result, "next": self.nxt(line)}).lower()
        self.assertTrue("source" in details or "provenance" in details, details)
        new_prs = [p for key, p in self.gh.load()["prs"].items() if key not in existing_prs]
        self.assertTrue(any(p.get("baseRefName") == "main" and p.get("state") == "MERGED" for p in new_prs), new_prs)

    def test_production_move_during_protected_finish_is_reported_after_merge(self):
        capability = fx.PLUGIN_CODE / "engine/capabilities/insertable_release_targets.txt"
        self.assertTrue(capability.is_file(), "insertable release capability is not implemented")
        self.finished_source()
        self.activate()
        patch = self.goal(release="1.1")
        line = self.insert(self.preview())["goal"]
        self.done(patch, code={"src/base_race_patch.py": "fixed = True\n"})
        synced = self.op(line, "sync")["ran"]["output"]["merged"]
        self.assertEqual(self.tip("release/1.1"), synced)
        self.approve(line, "approve_finish")
        dev_before = self.tip("dev")
        moved, rc, result, stderr = self._at_provider_merge(
            line, "finish", lambda pr: self.push_branch("main", {"src/external_finish.py": "external = True\n"},
                                                        "fix: external production write during finish"),
            approved_head=synced, target="main")
        self.assertTrue(self.is_ancestor(moved, self.tip("main")), (result, stderr))
        self.assertNotEqual(moved, self.tip("main"), "the protected merge may succeed on the newer base")
        self.assertEqual(dev_before, self.tip("dev"), "detected base race must pause forward-port")
        self.assertFalse((result.get("closed") or {}).get("reason") == "done", result)
        details = json.dumps({"result": result, "next": self.nxt(line)}).lower()
        self.assertTrue("base" in details or "production" in details, details)

    def test_changed_finish_pr_head_is_refused_at_provider_boundary(self):
        capability = fx.PLUGIN_CODE / "engine/capabilities/insertable_release_targets.txt"
        self.assertTrue(capability.is_file(), "insertable release capability is not implemented")
        self.finished_source()
        self.activate()
        patch = self.goal(release="1.1")
        line = self.insert(self.preview())["goal"]
        self.done(patch, code={"src/approved_finish.py": "fixed = True\n"})
        approved_head = self.op(line, "sync")["ran"]["output"]["merged"]
        self.assertEqual(self.tip("release/1.1"), approved_head)
        self.approve(line, "approve_finish")
        main_before, dev_before = self.tip("main"), self.tip("dev")
        selected = {}

        def change_pr_head(pr):
            selected["number"] = pr["number"]
            return self.push_branch(pr["headRefName"], {"src/unapproved_finish.py": "unapproved = True\n"},
                                    "fix: external finish PR head change")

        moved, rc, result, stderr = self._at_provider_merge(
            line, "finish", change_pr_head, approved_head=approved_head, target="main")
        self.assertNotEqual(approved_head, moved)
        self.assertEqual(main_before, self.tip("main"), (result, stderr))
        self.assertEqual(dev_before, self.tip("dev"), "unapproved finish must not forward")
        self.assertFalse((result.get("closed") or {}).get("reason") == "done", result)
        pr = self.gh.pr(selected["number"])
        self.assertEqual("OPEN", pr["state"], "the provider must refuse the changed finish PR head")
        self.assertEqual(moved, self.tip(pr["headRefName"]))

    def test_protected_provider_refusal_does_not_bypass_pr(self):
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
        self.gh.update(lambda state: state.setdefault("faults", {}).update(
            merge_refuse="GraphQL: protected branch requires approving review"))
        rc, result = self.w.run("a", "start", str(line), "finish", "--as", "claude:aaaa/op")
        self.assertFalse(rc == 0 and result.get("ran", {}).get("outcome") == "done", result)
        self.assertEqual(main_before, self.tip("main"), "protected production must not be bypassed")
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
            if self.tip("release/1.1"):
                # Resume the existing pending line only after a fresh preview
                # and its own approval; aliases must not create another line.
                fresh = self.preview()
                self.insert(fresh)
                self.assertEqual(source, self.tip("release/1.1"))
                self.assertTrue(any(a.get("goal") == patch for a in self.nxt(patch)["actions"]))
                self.assertEqual(advanced, self.tip("main"))
        finally:
            race_continue.write_text("continue", encoding="utf-8")
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate(timeout=5)

    def test_changed_patch_pr_head_is_refused_by_expected_head_guard(self):
        capability = fx.PLUGIN_CODE / "engine/capabilities/insertable_release_targets.txt"
        self.assertTrue(capability.is_file(), "insertable release capability is not implemented")
        self.finished_source()
        self.activate()
        patch = self.goal(release="1.1")
        self.insert(self.preview())
        self.deliver(patch, code={"src/approved_patch.py": "fixed = True\n"})
        self.op(patch, "integrate")
        self.approve(patch, "approve_merge")
        patch_before = self.tip("release/1.1")
        approved_head = self.tip(f"zzzops/pr/g{patch}")
        moved, rc, result, stderr = self._at_provider_merge(
            patch, "merge", lambda pr: self.push_branch(pr["headRefName"],
                                                        {"src/unapproved_head.py": "unapproved = True\n"},
                                                        "fix: external PR-head change"),
            approved_head=approved_head, target="release/1.1")
        self.assertEqual(moved, self.tip(f"zzzops/pr/g{patch}"))
        self.assertEqual(patch_before, self.tip("release/1.1"), (result, stderr))
        self.assertFalse((result.get("closed") or {}).get("reason") == "done", result)

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

    def test_source_revocation_before_dispatch_blocks_inserted_members(self):
        source_goal, source = self.finished_source()
        self.activate()
        patch = self.goal(release="1.1")
        self.insert(self.preview())
        line_tip = self.tip("release/1.1")
        self.assertEqual(source, line_tip)
        self._reopen_source(source_goal, "dispatch-source-revoker")
        status = self.nxt(patch)
        self.assertFalse(any(a.get("goal") == patch and a.get("node") in ("base", "implement", "integrate", "merge")
                             for a in status.get("actions", [])), status)
        self.assertIn(str(source_goal), json.dumps(status))
        self.assertEqual(line_tip, self.tip("release/1.1"))
        self.assertEqual(source, self.tip("main"))

    def test_production_change_before_dispatch_blocks_inserted_members(self):
        _, source = self.finished_source()
        self.activate()
        patch = self.goal(release="1.1")
        self.insert(self.preview())
        moved = self.push_branch("main", {"src/new_production.py": "new = True\n"})
        self.assertNotEqual(source, moved)
        status = self.nxt(patch)
        self.assertFalse(any(a.get("goal") == patch and a.get("node") in ("base", "implement", "integrate", "merge")
                             for a in status.get("actions", [])), status)
        self.assertEqual(source, self.tip("release/1.1"))
        self.assertEqual(moved, self.tip("main"))

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


class MaintenanceForwardPortJourneys(Branching):
    """Post-finish operations are independently reviewed, durable release goals."""

    finished_source = InsertedReleaseJourneys.finished_source
    activate = InsertedReleaseJourneys.activate
    preview = InsertedReleaseJourneys.preview
    answer = InsertedReleaseJourneys.answer
    insert = InsertedReleaseJourneys.insert

    def finished_maintenance(self):
        self.finished_source()
        later = self.goal(release=2)
        self.done(later, code={"src/newer.py": "newer = True\n"})
        line2 = self.cut(2)["goal"]
        self.op(line2, "sync")
        self.approve(line2, "approve_finish")
        self.op(line2, "finish")
        production = self.tip("main")
        self.activate()
        patch = self.goal(release="1.1")
        line = self.insert(self.preview())["goal"]
        self.done(patch, code={"src/maintenance.py": "fixed = True\n"})
        source = self.tip("release/1.1")
        self.op(line, "sync")
        self.approve(line, "approve_finish")
        result = self.op(line, "finish")
        self.assertEqual("done", result["closed"]["reason"])
        self.assertEqual(production, self.tip("main"))
        return line, source, production

    def request_port(self, source="1.1", destination="dev"):
        result = self.w.ok("a", "release", "forward-port", source, "--to", destination)
        return result["goal"]

    def port_until_human(self, goal):
        for _ in range(8):
            status = self.nxt(goal)
            people = [item for item in status["needs_human"] if item.get("goal") == goal]
            if people:
                self.assertEqual(1, len(people), status)
                return people[0]
            actions = [a for a in status["actions"] if a.get("goal") == goal]
            self.assertEqual(1, len(actions), status)
            self.op(goal, actions[0]["node"])
        self.fail("forward-port did not reach a human decision")

    def answer_port(self, goal, item, decision="approved"):
        self.w.ok("a", "answer", str(goal), item["node"], "--fp", item["fp"],
                  "--file", self.w.file({"decision": decision, "text": decision,
                                       "quote": decision, "decided_by": "Dave"}))

    def drive_port(self, goal):
        for _ in range(8):
            status = self.nxt(goal)
            actions = [a for a in status["actions"] if a.get("goal") == goal]
            if not actions:
                return status
            self.op(goal, actions[0]["node"])
        self.fail("forward-port failed to reach a stable state")

    def test_separate_destinations_approve_and_resume_without_rewinding_production(self):
        line, source, production = self.finished_maintenance()
        closed = self.goal_tip(line)
        self.push_branch("release/1.1", {"src/unapproved.py": "bad = True\n"})
        dev = self.tip("dev")
        port = self.request_port("1.1.0", "dev")
        self.assertNotEqual(line, port)
        self.assertEqual(port, self.request_port("1.1", "dev"), "aliases must resume one goal")
        item = self.port_until_human(port)
        prs = [p for p in self.gh.load()["prs"].values()
               if p["state"] == "OPEN" and p["baseRefName"] == "dev"]
        self.assertEqual(1, len(prs), prs)
        pr = prs[0]
        self.assertEqual(source, self.tip(pr["headRefName"]))
        for value in (source, dev, str(pr["number"])):
            self.assertIn(value, json.dumps(item))
        self.assertEqual(dev, self.tip("dev"))
        self.assertEqual(production, self.tip("main"))
        self.assertEqual(closed, self.goal_tip(line))
        self.answer_port(port, item)
        self.drive_port(port)
        self.assertEqual("MERGED", self.gh.pr(pr["number"])["state"])
        self.assertTrue(self.is_ancestor(source, self.tip("dev")))
        self.assertEqual(production, self.tip("main"))
        self.assertEqual(closed, self.goal_tip(line))
        self.assertEqual(port, self.request_port("1.1", "dev"))
        self.assertEqual(1, len([p for p in self.gh.load()["prs"].values()
                                 if p["baseRefName"] == "dev" and p["headRefName"] == pr["headRefName"]]))

        # Production is a separate operation and remains newer until explicitly approved.
        prod_port = self.request_port(destination="main")
        self.assertNotEqual(port, prod_port)
        prod_item = self.port_until_human(prod_port)
        self.assertEqual(production, self.tip("main"))
        self.answer_port(prod_port, prod_item)
        self.drive_port(prod_port)
        self.assertTrue(self.is_ancestor(production, self.tip("main")), "production cannot rewind")
        self.assertTrue(self.is_ancestor(source, self.tip("main")))
        self.assertEqual(closed, self.goal_tip(line))

    def test_refusal_and_moved_destination_require_fresh_approval(self):
        line, source, production = self.finished_maintenance()
        closed = self.goal_tip(line)
        port = self.request_port()
        item = self.port_until_human(port)
        dev_before = self.tip("dev")
        self.answer_port(port, item, decision="rejected")
        self.drive_port(port)
        self.assertEqual(dev_before, self.tip("dev"))
        self.assertEqual(production, self.tip("main"))
        self.assertEqual(closed, self.goal_tip(line))

    def test_already_in_history_needs_evidence_and_separate_approval(self):
        line, source, production = self.finished_maintenance()
        closed = self.goal_tip(line)
        p = self.w.add_clone("history")
        p.git("fetch", "-q", "origin", "refs/heads/dev", "refs/heads/release/1.1")
        p.git("checkout", "-q", "--detach", "origin/dev")
        p.git("merge", "-q", "--no-ff", "-m", "manually integrate finished maintenance", source)
        p.git("push", "-q", "origin", "HEAD:refs/heads/dev")
        observed = self.tip("dev")
        self.assertTrue(self.is_ancestor(source, observed))
        prior_prs = len(self.gh.load()["prs"])
        port = self.request_port()
        item = self.port_until_human(port)
        evidence = json.dumps(item)
        self.assertIn("already_in_history", evidence)
        self.assertIn(source, evidence)
        self.assertIn(observed, evidence)
        self.assertEqual(prior_prs, len(self.gh.load()["prs"]))
        self.answer_port(port, item)
        self.drive_port(port)
        self.assertIn("already_in_history", json.dumps(self.show(port)))
        self.assertEqual(observed, self.tip("dev"))
        self.assertEqual(production, self.tip("main"))
        self.assertEqual(closed, self.goal_tip(line))

    def test_equal_trees_without_lineage_or_matching_pr_are_not_proof(self):
        line, source, production = self.finished_maintenance()
        closed = self.goal_tip(line)
        # Independently make the same maintenance content; cherry-pick-equivalent
        # trees do not prove that this exact finished source was integrated.
        self.push_branch("dev", {"src/maintenance.py": "fixed = True\n"})
        observed = self.tip("dev")
        self.assertFalse(self.is_ancestor(source, observed))
        # Simulate GitHub rejecting an apparently empty PR, while leaving all
        # other provider operations real within the fixture.
        gh = Path(self.gh.bindir) / "gh"
        real = Path(self.gh.bindir) / "gh-real"
        gh.rename(real)
        gh.write_text('#!/bin/sh\nif [ "$1" = pr ] && [ "$2" = create ]; then\n'
                      '  echo "No commits between branches" >&2; exit 1\nfi\n'
                      'exec "$(dirname "$0")/gh-real" "$@"\n')
        gh.chmod(0o755)
        before = len(self.gh.load()["prs"])
        port = self.request_port()
        state = self.drive_port(port)
        self.assertIn("no_diff_unproven", json.dumps(state) + json.dumps(self.show(port)))
        self.assertEqual(before, len(self.gh.load()["prs"]))
        self.assertEqual(observed, self.tip("dev"))
        self.assertEqual(production, self.tip("main"))
        self.assertEqual(closed, self.goal_tip(line))

    def test_changed_carrier_head_and_destination_invalidate_approval(self):
        line, source, production = self.finished_maintenance()
        closed = self.goal_tip(line)
        port = self.request_port()
        item = self.port_until_human(port)
        prs = [p for p in self.gh.load()["prs"].values()
               if p["state"] == "OPEN" and p["baseRefName"] == "dev"]
        self.assertEqual(1, len(prs))
        pr = prs[0]
        self.answer_port(port, item)
        moved_head = self.push_branch(pr["headRefName"], {"src/unapproved.py": "bad = True\n"})
        advanced_dev = self.push_branch("dev", {"src/new_base.py": "new = True\n"})
        self.drive_port(port)
        self.assertEqual(advanced_dev, self.tip("dev"))
        self.assertEqual("OPEN", self.gh.pr(pr["number"])["state"])
        fresh = self.port_until_human(port)
        self.assertNotEqual(item["fp"], fresh["fp"])
        self.assertIn(moved_head, json.dumps(fresh))
        self.assertIn(advanced_dev, json.dumps(fresh))
        self.assertEqual(closed, self.goal_tip(line))
        self.assertEqual(production, self.tip("main"))

    def test_source_revocation_after_port_approval_blocks_the_merge(self):
        line, source, production = self.finished_maintenance()
        port = self.request_port()
        item = self.port_until_human(port)
        before = self.tip("dev")
        self.answer_port(port, item)
        InsertedReleaseJourneys._reopen_source(self, line, "port-source-revoker")
        result = self.drive_port(port)
        self.assertEqual(before, self.tip("dev"))
        self.assertEqual(production, self.tip("main"))
        self.assertIn(str(line), json.dumps(result) + json.dumps(self.show(port)))

    def test_protected_merge_failure_can_resume_without_duplicate_pr(self):
        line, source, production = self.finished_maintenance()
        closed = self.goal_tip(line)
        port = self.request_port()
        item = self.port_until_human(port)
        prs = [p for p in self.gh.load()["prs"].values()
               if p["state"] == "OPEN" and p["baseRefName"] == "dev"]
        self.assertEqual(1, len(prs))
        before = self.tip("dev")
        self.answer_port(port, item)
        self.gh.update(lambda st: st.setdefault("faults", {}).update(
            merge_refuse="protected branch requires approving review"))
        self.drive_port(port)
        self.assertEqual(before, self.tip("dev"))
        self.assertEqual("OPEN", self.gh.pr(prs[0]["number"])["state"])
        self.assertEqual(port, self.request_port())
        self.assertEqual(1, len([p for p in self.gh.load()["prs"].values()
                                 if p["baseRefName"] == "dev" and p["headRefName"] == prs[0]["headRefName"]]))
        self.gh.update(lambda st: st["faults"].pop("merge_refuse", None))
        self.drive_port(port)
        self.assertEqual("MERGED", self.gh.pr(prs[0]["number"])["state"])
        self.assertTrue(self.is_ancestor(source, self.tip("dev")))
        self.assertEqual(production, self.tip("main"))
        self.assertEqual(closed, self.goal_tip(line))
