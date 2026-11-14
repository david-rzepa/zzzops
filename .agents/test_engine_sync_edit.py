"""Step 5: the sync rule, edit, reopen and the generic close (SPEC §4.13, §4.18, §4.19; DESIGN §10 items 12, 15, 17,
18, 20)."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import unittest

import engine_fixtures as fx
from test_engine_lifecycle import Journey


def tiny_workflow():
    """Two agent nodes; the review is terminal (generic close under a non-default graph)."""
    return {"schema": 1, "graphs": {"default": {"terminal": ["check"], "nodes": {
        "write": {"kind": "agent", "stage": "discovery", "prompt": "design.md", "inputs": {"spec": {"from": "goal.spec"}},
                  "outputs": {"summary": "text", "doc": "artifact"}},
        "check": {"kind": "agent", "stage": "discovery", "prompt": "review_design.md", "review": {"subject": "write"},
                  "inputs": {"doc": {"from": "write.doc"}}}}}}}


class SyncTests(Journey):
    def push_review_commit(self, g):
        """A reviewer's artifact commit lands on the remote work branch (plumbing, as submit does)."""
        s = self.w.seed
        s.git("fetch", "-q", "origin", f"refs/heads/zzzops/work/g{g}")
        tip = s.git("rev-parse", "FETCH_HEAD")
        blob = s.git("hash-object", "-w", "--stdin", input="# late review\n")
        s.git("read-tree", tip)
        s.git("update-index", "--add", "--cacheinfo", f"100644,{blob},.zzzops/reviews/{g}/extra.md")
        tree = s.git("write-tree")
        c = s.git("commit-tree", tree, "-p", tip, "-m", "docs(review): extra for G%d" % g)
        s.git("push", "-q", "origin", f"{c}:refs/heads/zzzops/work/g{g}")
        s.git("read-tree", "HEAD")
        return c

    def test_remote_only_review_commits_are_rebased_over(self):
        g = self.goal()
        self.through_tests(g)
        c = self.A.start(g, self.n("implement"))
        wtd = self.A.worktree(g)
        wtd.commit({"src/cut.py": "def cut():\n    return 1\n"}, "feat: cut")
        local = wtd.git("rev-parse", "HEAD")
        self.push_review_commit(g)
        self.A.submit(g, self.n("implement"), c, {"summary": "Built."})
        rec = self.show(g)["goal"]["records"][self.n("implement")]["output"]["code"]
        ident_tree = wtd.git("rev-parse", f"{local}^{{tree}}")
        self.assertNotEqual(local, rec["commit"])                       # rebased onto the review commit
        self.assertEqual("docs(review): extra for G%d" % g, wtd.git("log", "-1", "--format=%s", f"{rec['commit']}~1"))
        self.assertEqual(wtd.git("rev-parse", f"{rec['commit']}:src/cut.py"), wtd.git("rev-parse", f"{local}:src/cut.py"))

    def test_patch_equivalent_local_commits_reset_to_remote(self):
        g = self.goal()
        self.through_tests(g)
        c = self.A.start(g, self.n("implement"))
        wtd = self.A.worktree(g)
        wtd.commit({"src/cut.py": "def cut():\n    return 1\n"}, "feat: cut")
        # the same change lands on the remote from elsewhere (a cherry-pick: different commit, same patch)
        s = self.w.seed
        s.git("fetch", "-q", "origin", f"refs/heads/zzzops/work/g{g}")
        s.git("checkout", "-q", "-B", "tmpw", "FETCH_HEAD")
        s.commit({"src/cut.py": "def cut():\n    return 1\n"}, "feat: cut (elsewhere)")
        s.git("push", "-q", "origin", f"HEAD:refs/heads/zzzops/work/g{g}")
        s.git("checkout", "-q", "dev")
        self.A.submit(g, self.n("implement"), c, {"summary": "Built."})
        self.assertEqual(wtd.git("rev-parse", "HEAD"), self.w.remote_git("rev-parse", f"refs/heads/zzzops/work/g{g}"))

    def test_whitespace_difference_diverges_and_salvage_works(self):
        g = self.goal()
        self.through_tests(g)
        c = self.A.start(g, self.n("implement"))
        wtd = self.A.worktree(g)
        wtd.commit({"src/cut.py": "def cut():\n    return 1\n"}, "feat: cut")
        s = self.w.seed
        s.git("fetch", "-q", "origin", f"refs/heads/zzzops/work/g{g}")
        s.git("checkout", "-q", "-B", "tmpw", "FETCH_HEAD")
        s.commit({"src/cut.py": "def cut():\n  return 1\n"}, "feat: cut (two-space indent)")
        s.git("push", "-q", "origin", f"HEAD:refs/heads/zzzops/work/g{g}")
        s.git("checkout", "-q", "dev")
        rc, err = self.A.submit(g, self.n("implement"), c, {"summary": "Built."}, ok=False)
        self.assertEqual("sync_refused", err["error"]["code"])
        self.assertFalse(err["error"]["details"]["local_only"][0]["patch_equivalent_on_remote"])
        lines = [l for l in err["error"]["hint"].splitlines() if l.startswith("git ")]
        wtd.git("fetch", "-q", "origin", f"+refs/heads/zzzops/work/g{g}:refs/remotes/origin/zzzops/work/g{g}")
        for line in lines:
            subprocess.run(line, shell=True, check=True, env=self.w.env, capture_output=True)
        saved = wtd.git("log", "-1", "--format=%s", f"zzzops-salvage/g{g}-{self.n('implement')}-a1")
        self.assertEqual("feat: cut", saved)
        self.assertEqual(wtd.git("rev-parse", "HEAD"), self.w.remote_git("rev-parse", f"refs/heads/zzzops/work/g{g}"))


class EditTests(Journey):
    def tip(self, g):
        return self.show(g)["goal_commit"]

    def test_dry_run_apply_and_stale_base(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        base = self.tip(g)
        out = self.w.ok("a", "edit", str(g), "--set", 'spec="a new spec"')
        self.assertFalse(out["applied"])
        self.assertEqual("ready (stale: inputs.spec)", out["preview"][f"G{g}"][self.n("design")]["after"])
        self.assertEqual(1, out["stale_agent_phases"])
        self.assertEqual(base, self.tip(g))
        out = self.w.ok("a", "edit", str(g), "--set", 'spec="a new spec"', "--base", base)
        self.assertTrue(out["applied"])
        rc, err = self.w.run("a", "edit", str(g), "--set", 'priority="P1"', "--base", base)
        self.assertEqual("goal_changed", err["error"]["code"])

    def test_edit_errors(self):
        a = self.goal()
        b = self.w.new(title="B", depends_on=[a])["created"]["id"]
        rc, err = self.w.run("a", "edit", str(a), "--set", f"depends_on=[{b}]", "--base", self.tip(a))
        self.assertEqual("validation", err["error"]["code"])
        self.assertIn("cycle", err["error"]["message"])
        rc, err = self.w.run("a", "edit", str(a), "--set", "release=2", "--base", self.tip(a))
        self.assertIn("release", err["error"]["message"])
        rc, err = self.w.run("a", "edit", str(b), "--set", f'skip.{self.n("design")}="{"x" * 70000}"', "--base", self.tip(b))
        self.assertEqual("too_large", err["error"]["code"])
        rc, err = self.w.run("a", "edit", str(b), "--set", f'skip.{self.n("merge")}="no"', "--base", self.tip(b))
        self.assertIn("terminal node cannot be skipped", err["error"]["message"])
        f = self.w.file({"set": {"state": "closed", "closed.reason": "done", "closed.note": "done?"}})
        rc, err = self.w.run("a", "edit", str(b), "--file", f, "--base", self.tip(b))
        self.assertIn("superseded or cancelled", err["error"]["message"])

    def test_cancel_prints_follow_up_and_reopen_of_done_goal_is_refused(self):
        g = self.goal(links={"issue": 812})
        f = self.w.file({"set": {"state": "closed", "closed.reason": "cancelled", "closed.note": "not needed"}})
        out = self.w.ok("a", "edit", str(g), "--file", f, "--base", self.tip(g))
        self.assertEqual(["gh issue close 812"], out["follow_up"])
        self.assertEqual("closed", self.show(g)["goal"]["state"])
        # a cancelled goal may be reopened
        self.w.ok("a", "edit", str(g), "--set", 'state="open"', "--base", self.tip(g))

    def test_editing_an_invalid_document(self):
        g = self.goal()
        tip = self.w.remote_git("rev-parse", f"refs/heads/zzzops/goal/g{g}")
        self.w.seed.git("fetch", "-q", "origin", f"refs/heads/zzzops/goal/g{g}")
        doc = json.loads(self.w.seed.git("show", "FETCH_HEAD:goal.json"))
        doc["priority"] = "urgent"
        from test_engine_store import push_goal_doc
        bad = push_goal_doc(self.w, doc, parent=tip)
        out = self.w.ok("a", "next")
        self.assertIn("invalid_goal", [x["kind"] for x in out["warnings"]])
        self.w.ok("a", "edit", str(g), "--set", 'priority="P1"', "--base", bad)
        out = self.w.ok("a", "next")
        self.assertNotIn("invalid_goal", [x["kind"] for x in out["warnings"]])

    def test_reopen_waives_own_findings_and_reruns(self):
        g = self.goal()
        self.through_impl(g)
        self.review(self.B, g, "review_impl", "changes_requested", [{"text": "x"}])
        out = self.w.ok("a", "reopen", str(g), self.n("review_impl"), "--note", "flaky reviewer")
        self.assertEqual(1, len(out["waived"]))
        self.assertEqual(f"{self.n('review_impl')}:reopen:1", out["finding"]["id"])
        nxt = self.w.ok("a", "next", "--goal", str(g))
        self.assertIn((self.n("review_impl"), "reopened"), [(a["node"], a["reason"]) for a in nxt["actions"]])
        self.assertEqual("current", self.show(g)["states"][self.n("implement")])

    def test_writes_to_a_rewritten_goal_are_refused(self):
        g = self.goal()
        other = self.goal()
        self.w.ok("b", "next")
        self.w.seed.git("fetch", "-q", "origin", f"refs/heads/zzzops/goal/g{g}")
        doc = json.loads(self.w.seed.git("show", "FETCH_HEAD:goal.json"))
        from test_engine_store import push_goal_doc
        push_goal_doc(self.w, dict(doc, title="evil"), force=True)
        rc, err = self.w.run("b", "edit", str(g), "--set", 'priority="P1"', "--base", self.w.remote_git(
            "rev-parse", f"refs/heads/zzzops/goal/g{g}"))
        self.assertIn(err["error"]["code"], ("goal_rewritten", "usage"))
        rc, err = self.w.run("b", "start", str(g), self.n("design"), "--as", self.B.label)
        self.assertEqual("goal_rewritten", err["error"]["code"])
        self.B.start(other, self.n("design"))                       # other goals are unaffected

    def test_concurrent_writes_to_one_goal_and_to_different_goals(self):
        gs = [self.goal() for _ in range(2)]
        for g in gs:
            c = self.A.start(g, self.n("design"))
            self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        results = []

        def reopen(g, note):
            results.append(self.w.run("a" if note.endswith("a") else "b", "reopen", str(g), self.n("design"), "--note", note))

        threads = [threading.Thread(target=reopen, args=(g, f"n{i}{c}")) for g in gs for i, c in enumerate("ab")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual([0] * 4, [rc for rc, _ in results], [o for rc, o in results if rc][:1])
        for g in gs:
            ids = [f["id"] for f in self.show(g)["goal"]["records"][self.n("design")]["findings"]]
            self.assertEqual(2, len(ids))


class CloseTests(unittest.TestCase):
    def setUp(self):
        import shutil
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.w.bootstrap(workflow=tiny_workflow())
        self.A = fx.Agent(self.w, "a", "claude:aaaa/w-1")
        self.B = fx.Agent(self.w, "b", "codex:bbbb/w-2")

    def test_generic_close_in_the_same_push(self):
        g = self.w.new(title="tiny")["created"]["id"]
        c = self.A.start(g, "write")
        self.A.submit(g, "write", c, {"summary": "W"}, artifact="# W\n")
        c = self.B.start(g, "check")
        out = self.B.submit(g, "check", c, {"decision": "approved", "summary": "ok"}, artifact="ok\n")
        self.assertEqual("done", out["closed"]["reason"])
        self.assertEqual("deleted", out["pushed"][f"zzzops/lease/g{g}/check"])
        doc = self.w.ok("a", "show", str(g), "--json")["goal"]
        self.assertEqual("closed", doc["state"])
        log = self.w.remote_git("log", "-1", "--format=%B", f"refs/heads/zzzops/goal/g{g}")
        self.assertIn("State: closed", log)
        self.assertIn("Engine: ", log)
        # a goal closed as done stays closed (§3.3 rule 5)
        tip = self.w.ok("a", "show", str(g), "--json")["goal_commit"]
        rc, err = self.w.run("a", "edit", str(g), "--set", 'state="open"', "--base", tip)
        self.assertEqual(1, rc)
        self.assertIn("stays closed", err["error"]["message"])


class RenamedSyncTests(SyncTests):
    renamed = True


if __name__ == "__main__":
    unittest.main()
