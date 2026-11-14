"""Regressions for the findings of the pre-push review of the reset branch."""

from __future__ import annotations

import types
import unittest

import engine_fixtures as fx
from engine_sim import Sim
from engine import render
from engine.card import previous
from engine.errors import Refused
from engine.frontier import goal_order
from engine.schemas import build_graph


def drive_to(s, g, node):
    for _ in range(60):
        st = s.st(g, node)
        if st["name"] in ("ready", "needs_human"):
            return st
        s.step(g, [a for a in s.actionable(g) if a != node][0])
    raise AssertionError(node)


class ReviewFixTests(unittest.TestCase):
    def test_crash_loop_state_carries_its_live_findings(self):
        s = Sim()
        s.goal(1)
        drive_to(s, 1, "review_impl")
        s.start(1, "review_impl")
        s.submit(1, "review_impl", findings=[{"text": "bug"}])
        for _ in range(3):
            s.start(1, "implement")
            s.tick(130 * 60)
        st = s.st(1, "implement")
        self.assertEqual(("needs_human", "crash_loop", "lease"), (st["name"], st["kind"], st["cap"]))
        self.assertEqual(["review_impl:1:1"], [f["id"] for f in st["corrections"]])

    def test_human_finding_on_a_skipped_node_is_refused(self):
        s = Sim()
        s.goal(1, skip={"approve_design": "small"})
        drive_to(s, 1, "approve_merge")
        with self.assertRaises(Refused):
            s.answer(1, "approve_merge", decision="changes_requested",
                     findings=[{"target": "approve_design", "text": "x"}])

    def test_previous_findings_show_the_target_response(self):
        s = Sim()
        s.goal(1)
        drive_to(s, 1, "review_impl")
        s.start(1, "review_impl")
        s.submit(1, "review_impl", findings=[{"target": "test_design", "text": "add an edge test"}])
        s.start(1, "test_design")
        s.submit(1, "test_design", responses={"review_impl:1:1": "fixed: added the edge test"})
        res = s.eval().goals[1]
        fake = types.SimpleNamespace(git=types.SimpleNamespace(exists=lambda oid: False))
        prev = previous(fake, res, "review_impl", {"stale_because": ["subject"]})
        self.assertEqual("fixed: added the edge test", prev["findings"][0]["response"])

    def test_reasked_approval_shows_the_interdiff(self):
        s = Sim()
        s.goal(1)
        s.drive(1, until="approve_merge") if False else drive_to(s, 1, "approve_merge")
        s.answer(1, "approve_merge")
        s.reopen(1, "implement", "one more change")
        s.start(1, "implement")
        s.submit(1, "implement", responses={"implement:reopen:1": "fixed: changed"})   # the goal's diff changes
        for n in ("run_tests", "review_impl"):
            s.step(1, n)
        class R(render.Reader):
            def has(self, oid):
                return True
        ctx = render.Ctx(prefix="zzzops", now=s.now, settings=s.settings, coordinator={}, reader=R(),
                         goal_commits={1: "a" * 40})
        item = render.approve_item(ctx, s.eval().goals[1], "approve_merge", True)
        self.assertTrue(item["previous"]["interdiff"].startswith("git range-diff "))

    def test_every_member_of_a_dependency_cycle_is_found(self):
        docs = {g: {"depends_on": d} for g, d in {2: [3, 5], 3: [4], 4: [2], 5: [3]}.items()}
        order, cyclic = goal_order(docs)
        self.assertEqual({2, 3, 4, 5}, cyclic)
        self.assertEqual([], order)

    def test_topological_order_breaks_ties_by_declaration(self):
        nodes = {n: {"kind": "agent", "stage": "discovery", "prompt": "p.md", "outputs": {"x": "text"}} for n in "abc"}
        nodes["a"]["inputs"] = {"y": {"from": "c.x"}}
        g = build_graph("g", {"nodes": nodes, "terminal": ["a"]})
        self.assertEqual(["b", "c", "a"], g.topo)


if __name__ == "__main__":
    unittest.main()


import json as _json
import shutil as _shutil
import tempfile as _tempfile

from test_engine_lifecycle import Journey
from test_engine_sync_edit import tiny_workflow


class StoreReviewFixTests(Journey):
    def test_renew_under_an_invalid_policy_is_policy_invalid_not_superseded(self):
        g = self.goal()
        self.A.start(g, self.n("design"))
        self.w.push_dev({".zzzops/POLICY.json": _json.dumps({"schema_version": 2, "nope": 1})})
        rc, err = self.w.run("a", "renew", str(g), self.n("design"), "--attempt", "1")
        self.assertEqual((4, "policy_invalid"), (rc, err["error"]["code"]))

    def test_offline_next_offers_nothing(self):
        g = self.goal()
        self.w.ok("b", "next")
        _shutil.move(self.w.remote, self.w.remote + ".away")
        try:
            out = self.w.ok("b", "next")
        finally:
            _shutil.move(self.w.remote + ".away", self.w.remote)
        self.assertFalse(out["coordinator"]["current"])
        self.assertEqual([], out["actions"])
        self.assertIn("offline", [x["kind"] for x in out["warnings"]])

    def test_policy_branch_is_refused_first(self):
        g = self.goal()
        s = self.w.seed
        s.git("pull", "-q", "--ff-only", "origin", "dev")
        s.git("checkout", "-q", "-b", "zzzops/policy/x")
        s.commit({".zzzops/prompts/design.md": "x\n"}, "chore: policy")
        s.git("push", "-q", "origin", "HEAD:refs/heads/zzzops/policy/x")
        s.git("checkout", "-q", "dev")
        p = _json.loads(_json.dumps(self.w.policy))
        p["settings"]["engine"] = {"requires": ["no_such_cap"]}
        self.w.push_dev({".zzzops/POLICY.json": _json.dumps(p)})
        rc, err = self.w.run("a", "start", str(g), self.n("design"), "--as", self.A.label)
        self.assertEqual((4, "policy_branch"), (rc, err["error"]["code"]))

    def test_embedded_next_has_no_stale_orphan_warning(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        out = self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        self.assertNotIn("orphan_lease", [x["kind"] for x in out["next"]["warnings"]])

    def test_forced_abandon_respects_a_rewritten_goal(self):
        g = self.goal()
        self.A.start(g, self.n("design"))
        self.w.ok("b", "next")
        self.w.seed.git("fetch", "-q", "origin", f"refs/heads/zzzops/goal/g{g}")
        doc = _json.loads(self.w.seed.git("show", "FETCH_HEAD:goal.json"))
        from test_engine_store import push_goal_doc
        push_goal_doc(self.w, dict(doc, title="evil"), force=True)
        rc, err = self.w.run("b", "abandon", str(g), self.n("design"), "--force", "--note", "x")
        self.assertEqual("goal_rewritten", err["error"]["code"])


class ClosingSubmitTests(unittest.TestCase):
    def test_resubmit_after_a_closing_submit_is_applied(self):
        tmp = _tempfile.mkdtemp()
        self.addCleanup(_shutil.rmtree, tmp, True)
        w = fx.World(tmp)
        w.bootstrap(workflow=tiny_workflow())
        A, B = fx.Agent(w, "a", "claude:aaaa/w-1"), fx.Agent(w, "b", "codex:bbbb/w-2")
        g = w.new(title="t")["created"]["id"]
        c = A.start(g, "write")
        A.submit(g, "write", c, {"summary": "W"}, artifact="# W\n")
        c = B.start(g, "check")
        B.submit(g, "check", c, {"decision": "approved", "summary": "ok"}, artifact="ok\n")
        again = B.submit(g, "check", c, {"decision": "approved", "summary": "ok"}, artifact="ok\n")
        self.assertTrue(again["applied"])


class PackagingReviewFixTests(unittest.TestCase):
    def test_gh_repo_comes_from_the_remote(self):
        import os
        from engine.gh import gh_repo
        fake = types.SimpleNamespace(R="origin", git=types.SimpleNamespace(
            config=lambda k: "https://github.com/acme/widgets.git"))
        old = os.environ.get("GH_REPO")
        os.environ["GH_REPO"] = "other/repo"
        try:
            self.assertEqual("acme/widgets", gh_repo(fake))
        finally:
            if old is None:
                os.environ.pop("GH_REPO")
            else:
                os.environ["GH_REPO"] = old

    def test_launcher_is_executable_in_the_bundle(self):
        import importlib.util
        import sys
        from zipfile import ZipFile
        path = fx.ROOT / ".github" / "scripts" / "build_marketplace_bundle.py"
        sys.path.insert(0, str(path.parent))
        spec = importlib.util.spec_from_file_location("bundle_for_mode", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        data = mod.zip_bytes({"bin/zzzops": b"#!/bin/sh\n", "README.md": b"x"})
        import io
        with ZipFile(io.BytesIO(data)) as z:
            modes = {i.filename: (i.external_attr >> 16) & 0o777 for i in z.infolist()}
        self.assertEqual({"bin/zzzops": 0o755, "README.md": 0o644}, modes)


from test_engine_base import BaseJourney
from test_engine_github import GitHubJourney


class MergedOtherCodeTests(GitHubJourney):
    def test_a_pr_merged_with_other_code_is_a_human_item(self):
        g = self.goal()
        self.deliver(g)
        self.op(g, "integrate")
        self.approve(g, "approve_merge")
        s = self.w.seed                                          # someone pushes to the PR head, then merges by hand
        s.git("fetch", "-q", "origin", f"refs/heads/zzzops/pr/g{g}")
        s.git("checkout", "-q", "-B", "tmp-pr", "FETCH_HEAD")
        s.commit({"src/extra.py": "unreviewed = True\n"}, "feat: unreviewed")
        s.git("push", "-q", "origin", f"HEAD:refs/heads/zzzops/pr/g{g}")
        s.git("checkout", "-q", "dev")
        self.gh.merge_by_hand(1)
        out = self.op(g, "merge")
        self.assertEqual("human", out["ran"]["blocked"]["waiting_for"])
        self.assertIn("other than the reviewed checkpoint", out["ran"]["blocked"]["question"])


class InProcess:
    """Run engine code in this process with a World clone's CLI environment."""

    def __init__(self, w, clone):
        self.w, self.clone = w, clone

    def __enter__(self):
        import os
        self.env = fx.env_of(self.w.cli_env())
        self.env.__enter__()
        self.cwd = os.getcwd()
        os.chdir(self.w.clones[self.clone].path)
        return self

    def __exit__(self, *exc):
        import os
        os.chdir(self.cwd)
        self.env.__exit__(*exc)


class RestackRaceTests(BaseJourney):
    def race(self, g, edit_during_run):
        """Run `start base` in-process; while git.base runs, another clone changes the goal document."""
        import engine.ops.base as base_op
        from engine import verbs
        from engine.session import Session
        original = base_op.run
        calls = []

        def wrapped(ctx):
            result = original(ctx)
            calls.append(type(result).__name__)
            if len(calls) == 1 and edit_during_run:
                tip = self.w.ok("b", "show", str(g), "--json")["goal_commit"]
                self.w.ok("b", "edit", str(g), "--set", 'priority="P1"', "--base", tip)
            return result

        base_op.run = wrapped
        try:
            with InProcess(self.w, "a"):
                out = verbs.start(Session(), g, "base", "claude:aaaa/op")
        finally:
            base_op.run = original
        return out, calls

    def test_a_conflict_finishes_with_its_op_state_when_the_goal_changes_meanwhile(self):
        g = self.goal()
        wtd = self.deliver(g, code={"src/app.py": "def app():\n    return 2\n"})
        self.w.push_dev({"src/app.py": "def app():\n    return 3\n"})
        self.w.ok("a", "reopen", str(g), "base", "--note", "dev moved")
        out, calls = self.race(g, edit_during_run=True)
        self.assertEqual(["Blocked"], calls)                       # a Blocked result is never re-run
        st = self.record(g, "base")["blocked"]
        self.assertEqual({"work", "onto", "old"}, set(st["op_state"]))
        self.resolve_conflict(wtd)
        out = self.op(g, "base")
        self.assertEqual("done", out["ran"]["outcome"], out["ran"])

    def resolve_conflict(self, wtd):
        wtd.write({"src/app.py": "def app():\n    return 23\n"})
        wtd.git("add", "-A")
        wtd.git("-c", "core.editor=true", "rebase", "--continue")

    def test_a_clean_restack_is_rerun_when_the_goal_changes_meanwhile(self):
        g = self.goal()
        self.deliver(g)
        self.w.push_dev({"other.txt": "o\n"})
        self.w.ok("a", "reopen", str(g), "base", "--note", "dev moved")
        out, calls = self.race(g, edit_during_run=True)
        self.assertEqual(["Done", "Done"], calls)
        self.assertEqual("done", out["ran"]["outcome"])
        self.assertEqual(["test_design", "implement"], out["carried"])
        self.assertEqual("P1", self.show(g)["goal"]["priority"])   # the concurrent edit survived


class OlderEngineReadTests(unittest.TestCase):
    def test_an_engine_lacking_a_capability_still_reads(self):
        """G1027 §3.2: an engine without a required capability reads goals but refuses writes."""
        tmp = _tempfile.mkdtemp()
        self.addCleanup(_shutil.rmtree, tmp, True)
        w = fx.World(tmp)
        w.bootstrap()
        g = w.new(title="t")["created"]["id"]
        p = _json.loads(_json.dumps(w.policy))
        p["settings"]["engine"] = {"requires": ["no_such_cap"]}
        w.push_dev({".zzzops/POLICY.json": _json.dumps(p)})
        from engine.session import Session
        with InProcess(w, "a"):
            s = Session()
            s.open(readonly=True)
            out = s.render_next(all_=True)
            with self.assertRaises(Refused) as e:
                s.require_writable([g])
        self.assertEqual(["engine_too_old"], [b["kind"] for b in out["blockers"]])
        self.assertEqual(["no_such_cap"], out["blockers"][0]["missing"])
        self.assertEqual([g], [x["id"] for x in out["goals"]])
        self.assertEqual("engine_too_old", e.exception.code)
        self.assertEqual(["no_such_cap"], e.exception.details["missing"])


class HousekeepingTests(BaseJourney):
    def test_a_closed_goals_worktree_is_removed_after_a_later_write(self):
        import os
        g = self.goal()
        self.discovery(g)
        self.op(g, "base")                                         # creates the local worktree
        tip = self.show(g)["goal_commit"]
        f = self.w.file({"set": {"state": "closed", "closed.reason": "cancelled", "closed.note": "not needed"}})
        self.w.ok("b", "edit", str(g), "--file", f, "--base", tip)  # closed elsewhere
        path = os.path.join(self.w.clones["a"].path, ".zzzops", "worktrees", f"g{g}")
        self.assertTrue(os.path.isdir(path))
        self.w.new("a", title="another")                            # new does not write through write_goals
        other = self.goal()
        c = self.A.start(other, "design")
        self.A.submit(other, "design", c, {"summary": "D"}, artifact="# D\n")
        self.assertFalse(os.path.isdir(path))
