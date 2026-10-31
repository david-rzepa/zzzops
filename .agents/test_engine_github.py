"""Step 8: the gh wrapper, git.integrate and github.merge against the fake GitHub (SPEC §5.4–§5.6; DESIGN §10 items
2, 13, 14, 15, 23, 25)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

import engine_fixtures as fx
from test_engine_base import BaseJourney, OP

MIN = 60


class GitHubJourney(BaseJourney):
    settings = {}

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.gh = fx.FakeGitHub(self.w)
        self.m = {n: n for n in fx.DEFAULT_NODES}
        self.w.bootstrap(settings=self.settings)
        self.A = fx.Agent(self.w, "a", "claude:aaaa/w-1")
        self.B = fx.Agent(self.w, "b", "codex:bbbb/w-2")

    def op_at(self, g, node, now, *extra):
        self.w.now = max(self.w.now, now)
        return self.w.ok("a", "start", str(g), node, "--as", OP, *extra, now=self.w.now)

    def op(self, g, node, *extra, clone="a"):
        """Run an op; when it is waiting on its own retry_after, move the world clock there first."""
        rc, out = self.w.run(clone, "start", str(g), node, "--as", OP, *extra)
        if rc == 1 and out.get("error", {}).get("code") == "not_ready" and "is waiting" in out["error"]["message"]:
            from engine.canon import parse_iso
            r = self.show(g)["goal"]["records"][node]
            self.w.now = max(self.w.now, parse_iso(r["blocked"]["retry_after"]))
            rc, out = self.w.run(clone, "start", str(g), node, "--as", OP, *extra)
        if rc != 0:
            raise AssertionError(f"start {g} {node} -> {rc}: {json.dumps(out, indent=1)[:2500]}")
        return out

    def pr_head(self, g):
        return self.w.remote_git("rev-parse", f"refs/heads/zzzops/pr/g{g}")


class IntegrateTests(GitHubJourney):
    settings = {"verification.required_ci": ["ci"]}

    def test_pending_backoff_then_human_question(self):
        from engine.canon import parse_iso
        g = self.goal()
        self.deliver(g)
        start = self.w.now
        out = self.op(g, "integrate")
        self.assertEqual("blocked", out["ran"]["outcome"])
        self.gh.set_checks(self.pr_head(g), ci=["pending"])
        gaps, prev = [], start
        for _ in range(5):
            b = self.show(g)["goal"]["records"]["integrate"]["blocked"]
            nxt = parse_iso(b["retry_after"])
            gaps.append((nxt - prev) // MIN)
            prev = nxt
            self.op_at(g, "integrate", nxt)
        self.assertEqual([5, 10, 20, 30, 30], gaps)
        last = parse_iso(self.show(g)["goal"]["records"]["integrate"]["blocked"]["retry_after"])
        self.assertGreaterEqual(last - start, 120 * MIN)
        out = self.op_at(g, "integrate", last)                  # past ci_timeout_minutes: a question for the human
        self.assertEqual("human", out["ran"]["blocked"]["waiting_for"])
        self.assertIn("have not finished", out["ran"]["blocked"]["question"])

    def test_failure_reruns_once_then_finding_then_escalation_and_reopen(self):
        g = self.goal()
        self.deliver(g)
        self.op(g, "integrate")
        head = self.pr_head(g)
        self.gh.set_checks(head, ci=["fail"])
        out = self.op(g, "integrate")
        self.assertIn("re-ran once", out["ran"]["blocked"]["reason"])
        self.assertEqual(1, len(self.gh.load().get("reruns", [])))
        out = self.op(g, "integrate")
        self.assertEqual("integrate:check-ci", out["ran"]["findings"][0]["id"])
        self.assertEqual("implement", out["ran"]["findings"][0]["target"])
        # reopen integrate (a flake): integrate re-runs without an implement run
        rv = self.w.ok("a", "reopen", str(g), "integrate", "--note", "flaky runner")
        self.assertEqual(["integrate:check-ci"], rv["waived"])
        st = self.states(g)
        self.assertEqual("current", st["implement"])
        self.gh.set_checks(head, ci=["pass"])
        out = self.op(g, "integrate")
        self.assertTrue(out["ran"]["ok"])

    def test_failure_after_a_fix_escalates(self):
        g = self.goal()
        wtd = self.deliver(g)
        self.op(g, "integrate")
        self.gh.set_checks(self.pr_head(g), ci=["fail"])
        self.op(g, "integrate")
        self.op(g, "integrate")
        c = self.A.start(g, "implement")
        wtd.commit({f"src/m{g}.py": "x = 3\n"}, "fix: ci")
        self.A.submit(g, "implement", c, {"summary": "Built.", "responses": {"integrate:check-ci": "fixed: ci fixed"}})
        self.op(g, "run_tests")
        self.review(self.B, g, "review_impl")
        self.op(g, "integrate")
        self.gh.set_checks(self.pr_head(g), ci=["fail"])
        self.op(g, "integrate")
        out = self.op(g, "integrate")
        self.assertEqual(2, out["ran"]["findings"][0]["rounds"])
        nxt = self.w.ok("a", "next", "--goal", str(g))
        self.assertIn("dispute", [i["kind"] for i in nxt["needs_human"]])

    def test_deterministic_rebuild_keeps_merge_current(self):
        g = self.goal()
        self.deliver(g)
        self.op(g, "integrate")
        head = self.pr_head(g)
        self.gh.set_checks(head, ci=["pass"])
        self.op(g, "integrate")
        self.approve(g, "approve_merge")
        before = self.states(g)["merge"]
        self.w.ok("a", "reopen", str(g), "integrate", "--note", "re-observe")
        self.op(g, "integrate")
        self.assertEqual(head, self.pr_head(g))
        self.assertEqual(before, self.states(g)["merge"])
        # the PR branch has no review files, and the work branch is unchanged
        files = self.w.remote_git("diff", "--name-only", self.record(g, "base")["output"]["base_commit"], head)
        self.assertNotIn(".zzzops/reviews", files)

    def test_conflicting_pr_into_dev_is_a_base_finding(self):
        g = self.goal()
        self.deliver(g, code={"src/app.py": "def app():\n    return 9\n"})
        self.w.push_dev({"src/app.py": "def app():\n    return 7\n"})
        out = self.op(g, "integrate")
        self.assertEqual("integrate:conflict", out["ran"]["findings"][0]["id"])
        self.assertEqual("base", out["ran"]["findings"][0]["target"])

    def test_pr_closed_by_hand_is_a_human_item(self):
        g = self.goal()
        self.deliver(g)
        self.op(g, "integrate")
        self.gh.close_by_hand(1)
        out = self.op(g, "integrate")
        self.assertEqual(("blocked", "human"), (out["ran"]["outcome"], out["ran"]["blocked"]["waiting_for"]))


class MergeTests(GitHubJourney):
    settings = {"merge.method": "squash"}

    def ready_to_merge(self, g, **kw):
        self.deliver(g, **kw)
        self.op(g, "integrate")
        self.approve(g, "approve_merge")

    def test_merge_uses_the_method_closes_the_goal_and_deletes_no_branch(self):
        g = self.goal(links={"issue": 812})
        self.ready_to_merge(g)
        out = self.op(g, "merge")
        self.assertEqual("done", out["closed"]["reason"])
        st = self.gh.load()
        self.assertEqual(["squash"], st["merge_methods_used"])
        self.assertEqual([812], st["closed_issues"])
        refs = self.w.remote_git("for-each-ref", "--format=%(refname)")
        self.assertIn(f"refs/heads/zzzops/work/g{g}", refs)
        self.assertNotIn(f"zzzops/lease/g{g}/", refs)
        doc = self.show(g)["goal"]
        self.assertEqual("closed", doc["state"])

    def test_merged_by_hand_is_recorded(self):
        g = self.goal()
        self.ready_to_merge(g)
        self.gh.merge_by_hand(1)
        out = self.op(g, "merge")
        self.assertEqual(("done", "done"), (out["ran"]["outcome"], out["closed"]["reason"]))
        self.assertEqual([], self.gh.load().get("merge_methods_used", []))

    def test_github_block_waits_then_asks(self):
        g = self.goal()
        self.ready_to_merge(g)
        self.gh.update(lambda st: st["faults"].update({"merge_state": {"1": "BLOCKED"}}))
        out = self.op(g, "merge")
        self.assertEqual("time", out["ran"]["blocked"]["waiting_for"])
        out = self.op_at(g, "merge", self.w.now + 121 * MIN)
        self.assertEqual("human", out["ran"]["blocked"]["waiting_for"])

    def test_queued_merge_is_waited_on(self):
        g = self.goal()
        self.ready_to_merge(g)
        self.gh.update(lambda st: st["prs"]["1"].update(autoMergeRequest={"enabledAt": "x"}))
        out = self.op(g, "merge")
        self.assertIn("queued", out["ran"]["blocked"]["reason"])
        self.assertEqual([], self.gh.load().get("merge_methods_used", []))

    def test_gh_missing_or_unauthenticated_refuses_before_claiming(self):
        g = self.goal()
        self.ready_to_merge(g)
        self.gh.update(lambda st: st["faults"].update({"auth": True}))
        rc, err = self.w.run("a", "start", str(g), "merge", "--as", OP)
        self.assertEqual("environment", err["error"]["code"])
        self.assertNotIn(f"zzzops/lease/g{g}/merge", self.w.remote_git("for-each-ref", "--format=%(refname)"))

    def test_transient_gh_failure_waits(self):
        g = self.goal()
        self.ready_to_merge(g)
        self.gh.update(lambda st: st["faults"].update({"transient": 1}))
        out = self.op(g, "merge")
        self.assertEqual("time", out["ran"]["blocked"]["waiting_for"])
        self.assertIn("502", out["ran"]["blocked"]["reason"])

    def test_only_ops_call_gh(self):
        g = self.goal()
        before = len(self.gh.calls())
        self.w.ok("a", "next")
        self.w.ok("a", "show", str(g))
        c = self.A.start(g, "design")
        self.A.submit(g, "design", c, {"summary": "D"}, artifact="# D\n")
        self.w.ok("a", "edit", str(g), "--set", 'priority="P1"', "--base", self.show(g)["goal_commit"])
        self.assertEqual(before, len(self.gh.calls()))


class StackedDeliveryTests(GitHubJourney):
    def test_chain_answered_in_one_sitting_then_merges_in_order(self):
        """DESIGN §4.4: G1000 -> G1001 -> G1002; all merge approvals before G1000 merges."""
        a = self.goal()
        self.deliver(a, code={"src/a.py": "a\n"})
        self.op(a, "integrate")
        b = self.w.new(title="B", depends_on=[a])["created"]["id"]
        self.deliver(b, code={"src/b.py": "b\n"})
        self.op(b, "integrate")
        c = self.w.new(title="C", depends_on=[b])["created"]["id"]
        self.deliver(c, code={"src/c.py": "c\n"})
        self.op(c, "integrate")
        for g in (a, b, c):
            self.approve(g, "approve_merge")
        prs = self.gh.load()["prs"]
        self.assertEqual(["dev", f"zzzops/pr/g{a}", f"zzzops/pr/g{b}"], [prs[k]["baseRefName"] for k in ("1", "2", "3")])
        # now no further human input: run every action until the three goals close
        for _ in range(40):
            nxt = self.w.ok("a", "next")
            self.assertEqual([], [i for i in nxt["needs_human"] if i["kind"] != "close"], nxt["needs_human"])
            ops = [x for x in nxt["actions"] if x["kind"] == "op"]
            if not ops:
                break
            x = ops[0]
            self.op(x["goal"], x["node"])
        for g in (a, b, c):
            self.assertEqual("closed", self.show(g)["goal"]["state"], g)
        log = self.w.remote_git("log", "--format=%s", "dev")
        self.assertLess(log.index("#3"), log.index("#2"))
        self.assertLess(log.index("#2"), log.index("#1"))

    def test_retarget_only_after_the_merge_is_observed(self):
        a = self.goal()
        self.deliver(a)
        self.op(a, "integrate")
        b = self.w.new(title="B", depends_on=[a])["created"]["id"]
        self.deliver(b)
        self.op(b, "integrate")
        self.approve(a, "approve_merge")
        self.gh.update(lambda st: st.update(auto_delete=False))
        self.gh.update(lambda st: st["faults"].update({"merge_refuse": "merge refused by rule"}))
        out = self.op(a, "merge")
        self.assertEqual("blocked", out["ran"]["outcome"])
        self.assertEqual(f"zzzops/pr/g{a}", self.gh.pr(2)["baseRefName"])          # nothing retargeted
        self.gh.update(lambda st: st["faults"].pop("merge_refuse"))
        self.gh.merge_by_hand(1)                                                  # merged on GitHub by hand
        out = self.w.ok("a", "answer", str(a), "merge", "--fp", self.w.ok("a", "next", "--goal", str(a))["needs_human"][0]["fp"],
                        "--file", self.w.file({"text": "merged by hand", "quote": "done", "decided_by": "Dave"}))
        out = self.op(a, "merge")
        self.assertEqual("done", out["ran"]["outcome"])
        self.assertEqual("dev", self.gh.pr(2)["baseRefName"])                      # merged() retargeted it

    def test_stacked_pr_merged_into_its_dependency_branch_is_a_human_item(self):
        a = self.goal()
        self.deliver(a)
        self.op(a, "integrate")
        b = self.w.new(title="B", depends_on=[a])["created"]["id"]
        self.deliver(b)
        self.op(b, "integrate")
        self.gh.update(lambda st: st.update(auto_delete=False))
        self.gh.merge_by_hand(2)                                                  # into zzzops/pr/g<a>
        self.w.ok("a", "reopen", str(b), "integrate", "--note", "re-observe")
        out = self.op(b, "integrate")
        self.assertEqual("human", out["ran"]["blocked"]["waiting_for"])
        self.assertIn("not `dev`", out["ran"]["blocked"]["question"])

    def test_two_dependency_stack_pr_is_retired_when_the_set_drops(self):
        a = self.goal()
        self.deliver(a, code={"src/a.py": "a\n"})
        self.op(a, "integrate")
        b = self.w.new(title="B")["created"]["id"]
        self.deliver(b, code={"src/b.py": "b\n"})
        self.op(b, "integrate")
        c = self.w.new(title="C", depends_on=[a, b])["created"]["id"]
        self.deliver(c, code={"src/c.py": "c\n"})
        self.op(c, "integrate")
        prs = self.gh.load()["prs"]
        stack_pr = [p for p in prs.values() if p["headRefName"] == f"zzzops/stack/g{c}"][0]
        goal_pr = [p for p in prs.values() if p["headRefName"] == f"zzzops/pr/g{c}"][0]
        self.assertTrue(stack_pr["draft"])
        self.assertEqual(f"zzzops/stack/g{c}", goal_pr["baseRefName"])
        for g in (a, b):
            self.approve(g, "approve_merge")
            self.op(g, "merge")
        out = self.op(c, "base")
        prs = self.gh.load()["prs"]
        self.assertEqual("CLOSED", prs[str(stack_pr["number"])]["state"])
        self.assertEqual("dev", prs[str(goal_pr["number"])]["baseRefName"])
        self.assertEqual("OPEN", prs[str(goal_pr["number"])]["state"])
        self.assertNotIn(f"zzzops/stack/g{c}", self.w.remote_git("for-each-ref", "--format=%(refname)"))


class RequiredChecksOnStacksTests(GitHubJourney):
    settings = {"verification.required_ci": ["ci"]}

    def test_dependent_stacks_only_after_the_root_checks_pass_and_stacked_prs_skip_checks(self):
        a = self.goal()
        self.deliver(a)
        self.op(a, "integrate")                                                  # pending: blocked
        b = self.w.new(title="B", depends_on=[a])["created"]["id"]
        self.discovery(b)
        nxt = self.w.ok("a", "next")
        self.assertIn((b, f"G{a} integrate"), [(x["goal"], x["until"]) for x in nxt["waiting"]])
        self.gh.set_checks(self.pr_head(a), ci=["pass"])
        self.op_at(a, "integrate", fx.NOW + 6 * MIN)
        out = self.op(b, "base")
        self.assertEqual(self.pr_head(a), out["ran"]["output"]["base_commit"])
        self.deliver_rest(b)
        out = self.op(b, "integrate")
        self.assertEqual({"stacked": True, "checks": {}}, out["ran"]["output"]["ci"])

    def deliver_rest(self, g):
        wtd = self.A.worktree(g)
        c = self.A.start(g, "test_design")
        wtd.commit({f"tests/t{g}.txt": "t\n"}, f"test: G{g}")
        self.A.submit(g, "test_design", c, {"commands": ["true"]})
        self.review(self.B, g, "review_tests")
        c = self.A.start(g, "implement")
        wtd.commit({f"src/m{g}.py": "x\n"}, f"feat: G{g}")
        self.A.submit(g, "implement", c, {"summary": "Built."})
        self.op(g, "run_tests")
        self.review(self.B, g, "review_impl")


if __name__ == "__main__":
    unittest.main()
