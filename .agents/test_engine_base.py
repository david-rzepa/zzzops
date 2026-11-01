"""Step 7: git.base, stacking and carry-forward (SPEC §5.2, §4.21; DESIGN §10 items 5, 13, 25, 26)."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest

import engine_fixtures as fx
from test_engine_lifecycle import Journey

OP = "claude:aaaa/op"


class BaseJourney(Journey):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.m = {n: n for n in fx.DEFAULT_NODES}
        self.w.bootstrap(workflow=fx.stub_github_workflow())
        self.A = fx.Agent(self.w, "a", "claude:aaaa/w-1")
        self.B = fx.Agent(self.w, "b", "codex:bbbb/w-2")

    def op(self, g, node, *extra, clone="a"):
        return self.w.ok(clone, "start", str(g), node, "--as", OP, *extra)

    def discovery(self, g):
        c = self.A.start(g, "design")
        self.A.submit(g, "design", c, {"summary": "D"}, artifact=f"# Design {g}\n")
        self.review(self.B, g, "review_design")
        self.approve(g, "approve_design")

    def deliver(self, g, tests=None, code=None):
        """From base through review_impl; returns the work-tree helper."""
        self.discovery(g)
        out = self.op(g, "base")
        self.assertEqual("done", out["ran"]["outcome"], out["ran"])
        wtd = self.A.worktree(g)
        c = self.A.start(g, "test_design")
        wtd.commit(tests or {f"tests/t{g}.txt": "t1\n"}, f"test: G{g}")
        self.A.submit(g, "test_design", c, {"commands": ["true"]})
        self.review(self.B, g, "review_tests")
        c = self.A.start(g, "implement")
        wtd.commit(code or {f"src/m{g}.py": "x = 1\n"}, f"feat: G{g}")
        self.A.submit(g, "implement", c, {"summary": "Built."})
        self.assertTrue(self.op(g, "run_tests")["ran"]["ok"])
        self.review(self.B, g, "review_impl")
        return wtd

    def integrate(self, g):
        """The stub integrate: push the work tip as the PR head (the real op rebuilds without review commits)."""
        head = self.w.remote_git("rev-parse", f"refs/heads/zzzops/work/g{g}")
        self.w.remote_git("update-ref", f"refs/heads/zzzops/pr/g{g}", head)
        c = self.A.start(g, "integrate")
        self.A.submit(g, "integrate", c, {"pr": {"number": g, "url": f"https://github.com/test/repo/pull/{g}",
                                                 "head": head, "tree": head, "base": "dev"},
                                          "ci": {"stacked": False, "required": [], "passed": [], "failed": []}})
        return head

    def merge(self, g):
        """The stub merge: merge the PR head into dev with a merge commit."""
        s = self.w.seed
        s.git("pull", "-q", "--ff-only", "origin", "dev")
        s.git("fetch", "-q", "origin", f"refs/heads/zzzops/pr/g{g}")
        s.git("merge", "-q", "--no-ff", "-m", f"Merge PR #{g}", "FETCH_HEAD")
        s.git("push", "-q", "origin", "HEAD:dev")
        mc = s.git("rev-parse", "HEAD")
        self.approve(g, "approve_merge")
        c = self.A.start(g, "merge")
        self.A.submit(g, "merge", c, {"merge_commit": mc, "merged_at": "2027-01-15T08:00:00Z"})
        return mc

    def states(self, g):
        return self.show(g)["states"]

    def record(self, g, n):
        return self.show(g)["goal"]["records"][n]


class RestackTests(BaseJourney):
    def test_first_run_rebases_onto_the_current_integration_tip(self):
        g = self.goal()
        self.discovery(g)
        dev = self.w.push_dev({"README.md": "# moved\n"})
        out = self.op(g, "base")
        self.assertEqual(dev, out["ran"]["output"]["base_commit"])
        wtd = self.A.worktree(g)
        self.assertEqual(wtd.git("rev-parse", "HEAD"), self.w.remote_git("rev-parse", f"refs/heads/zzzops/work/g{g}"))
        self.assertTrue(wtd.git("merge-base", "--is-ancestor", dev, "HEAD") == "")

    def test_clean_restack_carries_and_reruns_only_tree_bound_nodes(self):
        g = self.goal()
        self.deliver(g)
        before = {n: self.record(g, n)["attempt"] for n in ("design", "approve_design", "review_tests", "review_impl")}
        self.w.push_dev({"other.txt": "o\n"})
        self.w.ok("a", "reopen", str(g), "base", "--note", "dev moved")
        out = self.op(g, "base")
        self.assertEqual(["test_design", "implement"], out["carried"])
        st = self.states(g)
        self.assertEqual("ready (stale: inputs.code)", st["run_tests"])
        self.assertTrue(self.op(g, "run_tests")["ran"]["ok"])
        st = self.states(g)
        for n in ("review_tests", "review_impl", "test_design", "implement", "design", "approve_design"):
            self.assertEqual("current", st[n], (n, st))
        self.assertEqual("needs_human (approve)", st["approve_merge"])
        after = {n: self.record(g, n)["attempt"] for n in before}
        self.assertEqual(before, after)
        self.assertEqual("base", self.record(g, "implement")["carried_by"])

    def resolve(self, wtd, files):
        wtd.write(files)
        wtd.git("add", "-A")
        wtd.git("-c", "core.editor=true", "rebase", "--continue")

    def test_conflict_in_implement_hand_resolved_keeps_test_design_carried(self):
        g = self.goal()
        wtd = self.deliver(g, code={"src/app.py": "def app():\n    return 2\n"})
        self.w.push_dev({"src/app.py": "def app():\n    return 3\n"})
        self.w.ok("a", "reopen", str(g), "base", "--note", "dev moved")
        out = self.op(g, "base")
        self.assertEqual("blocked", out["ran"]["outcome"])
        self.assertIn("rebase conflict in src/app.py", out["ran"]["blocked"]["reason"])
        nxt = self.w.ok("a", "next", "--goal", str(g))
        act = [a for a in nxt["actions"] if a["node"] == "base"][0]
        self.assertEqual(("retry", "reasoning"), (act["reason"], act["capability"]))
        self.resolve(wtd, {"src/app.py": "def app():\n    return 23\n"})
        out = self.op(g, "base")
        self.assertEqual("done", out["ran"]["outcome"], out["ran"])
        self.assertEqual(["test_design"], out["carried"])
        st = self.states(g)
        self.assertEqual("current", st["test_design"])
        self.assertTrue(st["implement"].startswith("ready (stale"), st["implement"])
        # the no-commit re-run of implement follows replay_pos to the hand-rebased commit
        c = self.A.start(g, "implement")
        self.A.submit(g, "implement", c, {"summary": "Built."})
        rec = self.record(g, "implement")["output"]["code"]
        self.assertEqual("feat: G%d" % g, wtd.git("log", "-1", "--format=%s", rec["commit"]))
        self.assertEqual("def app():\n    return 23", wtd.git("show", f"{rec['commit']}:src/app.py"))
        self.assertTrue(self.op(g, "run_tests")["ran"]["ok"])
        self.assertTrue(self.states(g)["review_impl"].startswith("ready (stale"))      # the diff changed

    def test_conflict_in_the_tests_commit_suggests_the_hand_rebased_checkpoint(self):
        g = self.goal()
        wtd = self.deliver(g, tests={"tests/shared.txt": "goal tests\n"})
        self.w.push_dev({"tests/shared.txt": "dev tests\n"})
        self.w.ok("a", "reopen", str(g), "base", "--note", "dev moved")
        self.assertEqual("blocked", self.op(g, "base")["ran"]["outcome"])
        self.resolve(wtd, {"tests/shared.txt": "dev tests\ngoal tests\n"})
        out = self.op(g, "base")
        self.assertEqual([], out.get("carried") or [])
        c = self.A.start(g, "test_design")
        self.A.submit(g, "test_design", c, {"commands": ["true"]})
        tests = self.record(g, "test_design")["output"]["tests"]["commit"]
        self.assertEqual("test: G%d" % g, wtd.git("log", "-1", "--format=%s", tests))   # not HEAD with implement's code
        self.assertEqual("dev tests\ngoal tests", wtd.git("show", f"{tests}:tests/shared.txt"))
        self.assertNotIn(f"src/m{g}.py", wtd.git("ls-tree", "-r", "--name-only", tests))

    def test_review_commit_during_a_hand_resolved_conflict_is_reapplied(self):
        g = self.goal()
        wtd = self.deliver(g, code={"src/app.py": "def app():\n    return 2\n"})
        self.w.push_dev({"src/app.py": "def app():\n    return 3\n"})
        self.w.ok("a", "reopen", str(g), "base", "--note", "dev moved")
        self.assertEqual("blocked", self.op(g, "base")["ran"]["outcome"])
        # a reviewer's artifact lands on the remote work branch meanwhile
        from test_engine_sync_edit import SyncTests
        SyncTests.push_review_commit(self, g)
        self.resolve(wtd, {"src/app.py": "def app():\n    return 23\n"})
        out = self.op(g, "base")
        self.assertEqual("done", out["ran"]["outcome"], out["ran"])
        self.assertIn("extra.md", wtd.git("ls-tree", "-r", "--name-only", "HEAD", ".zzzops/reviews/%d" % g))


class StackTests(BaseJourney):
    def test_stacks_on_an_unmerged_dependency_head(self):
        a = self.goal()
        self.deliver(a)
        head = self.integrate(a)
        b = self.w.new(title="B", depends_on=[a])["created"]["id"]
        self.discovery(b)
        out = self.op(b, "base")
        self.assertEqual(head, out["ran"]["output"]["base_commit"])
        self.assertEqual([{"goal": a, "head": head, "pr": a}], out["ran"]["output"]["stack"])

    def test_dependency_correction_restacks_without_reasks(self):
        a = self.goal()
        self.deliver(a)
        self.integrate(a)
        b = self.w.new(title="B", depends_on=[a])["created"]["id"]
        self.deliver(b)
        approve_attempts = self.record(b, "review_impl")["attempt"]
        # the dependency's PR head moves (a correction): b's base goes stale and restacks cleanly
        wa = self.A.worktree(a)
        self.w.ok("a", "reopen", str(a), "implement", "--note", "polish")
        c = self.A.start(a, "implement")
        wa.commit({f"src/m{a}.py": "x = 2\n"}, "fix: polish")
        self.A.submit(a, "implement", c, {"summary": "Built.", "responses": {c["corrections"][0]["id"]: "fixed: polished"}})
        self.op(a, "run_tests")
        self.review(self.B, a, "review_impl")
        self.integrate(a)
        self.assertTrue(self.states(b)["base"].startswith("ready (stale"))
        out = self.op(b, "base")
        self.assertEqual(["test_design", "implement"], out["carried"])
        self.op(b, "run_tests")
        self.assertEqual("current", self.states(b)["review_impl"])
        self.assertEqual(approve_attempts, self.record(b, "review_impl")["attempt"])

    def test_two_dependencies_combine_and_transitive_ones_do_not(self):
        a = self.goal()
        self.deliver(a, code={"src/a.py": "a = 1\n"})
        ha = self.integrate(a)
        b = self.w.new(title="B")["created"]["id"]
        self.deliver(b, code={"src/b.py": "b = 1\n"})
        hb = self.integrate(b)
        c = self.w.new(title="C", depends_on=[a, b])["created"]["id"]
        self.discovery(c)
        out = self.op(c, "base")
        onto = out["ran"]["output"]["base_commit"]
        stack_tip = self.w.remote_git("rev-parse", f"refs/heads/zzzops/stack/g{c}")
        self.assertEqual(onto, stack_tip)
        self.assertEqual([ha, hb], self.w.remote_git("rev-list", "--parents", "-n", "1", onto).split()[1:])
        names = self.w.remote_git("ls-tree", "-r", "--name-only", onto).split()
        self.assertIn("src/a.py", names)
        self.assertIn("src/b.py", names)
        # transitive: D depends on A and on E, which is stacked on A: E's head alone, no combine commit
        e = self.w.new(title="E", depends_on=[a])["created"]["id"]
        self.deliver(e, code={"src/e.py": "e = 1\n"})
        he = self.integrate(e)
        d = self.w.new(title="D", depends_on=[a, e])["created"]["id"]
        self.discovery(d)
        out = self.op(d, "base")
        self.assertEqual(he, out["ran"]["output"]["base_commit"])
        self.assertNotIn(f"zzzops/stack/g{d}", self.w.remote_git("for-each-ref", "--format=%(refname)"))

    def test_conflicting_dependencies_wait_and_never_get_stuck(self):
        a = self.goal()
        self.deliver(a, code={"src/same.py": "a\n"})
        self.integrate(a)
        b = self.w.new(title="B")["created"]["id"]
        self.deliver(b, code={"src/same.py": "b\n"})
        self.integrate(b)
        c = self.w.new(title="C", depends_on=[a, b])["created"]["id"]
        self.discovery(c)
        out = self.op(c, "base")
        self.assertEqual(("blocked", "deps_conflict"), (out["ran"]["outcome"], out["ran"]["blocked"]["reason"]))
        nxt = self.w.ok("a", "next")
        self.assertIn((c, "the dependencies combine cleanly"), [(x["goal"], x["until"]) for x in nxt["waiting"]])
        self.assertNotIn(c, [i["goal"] for i in nxt["needs_human"] if i["kind"] == "stuck"])

    def test_after_one_dependency_merges_the_base_contains_its_code(self):
        a = self.goal()
        self.deliver(a, code={"src/a.py": "a = 1\n"})
        self.integrate(a)
        b = self.w.new(title="B")["created"]["id"]
        self.deliver(b, code={"src/b.py": "b = 1\n"})
        hb = self.integrate(b)
        c = self.w.new(title="C", depends_on=[a, b])["created"]["id"]
        self.discovery(c)
        self.op(c, "base")
        self.merge(a)
        self.assertTrue(self.states(c)["base"].startswith("ready (stale"))
        out = self.op(c, "base")
        onto = out["ran"]["output"]["base_commit"]
        names = self.w.remote_git("ls-tree", "-r", "--name-only", onto).split()
        self.assertIn("src/a.py", names)                                 # the merged dependency's code
        self.assertIn("src/b.py", names)
        self.assertEqual([{"goal": b, "head": hb, "pr": b}], out["ran"]["output"]["stack"])


if __name__ == "__main__":
    unittest.main()
