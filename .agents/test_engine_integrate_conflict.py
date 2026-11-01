"""G1021: git.integrate detects a PR that conflicts with the integration branch instead of waiting for checks.

GitHub computes `mergeable` lazily, so the first view of a new or pushed PR reads UNKNOWN (the fake gh's
`mergeable_lag` fault), and it may not have seen a just-pushed head yet (`head_lag`). Integrate checks the conflict
locally with `git merge-tree` against its fetched integration tip, waits explicitly on UNKNOWN or an unseen head, and
asks a human when no checks at all appear on a mergeable PR."""

from __future__ import annotations

import re
import unittest

from test_engine_github import GitHubJourney, MIN                    # puts the engine on sys.path
from engine.canon import parse_iso

CONFLICT_CODE = {"src/app.py": "def app():\n    return 9\n"}
DEV_CODE = {"src/app.py": "def app():\n    return 7\n"}


class ConflictBase(GitHubJourney):
    settings = {"verification.required_ci": ["ci"]}

    def fault(self, **faults):
        self.gh.update(lambda st: st.setdefault("faults", {}).update(faults))

    def blocked(self, g):
        return self.record(g, "integrate")["blocked"]

    def assert_conflict_on_base(self, out, files=()):
        findings = out["ran"].get("findings") or []
        self.assertTrue(findings, out["ran"])
        f = findings[0]
        self.assertEqual(("integrate:conflict", "base"), (f["id"], f["target"]), out["ran"])
        self.assertFalse(out["ran"]["ok"])
        for name in files:
            self.assertIn(name, f["text"])
        return f

    def assert_base_reopened(self, g):
        st = self.states(g)["base"]
        self.assertTrue(st.startswith("ready"), st)
        self.assertIn("reopen", st)

    def assert_waits_not_on_checks(self, out, phrase):
        b = out["ran"]["blocked"]
        self.assertEqual(("blocked", "time"), (out["ran"]["outcome"], b["waiting_for"]), out["ran"])
        self.assertIn(phrase, b["reason"])
        self.assertNotIn("checks pending", b["reason"])


class IntegrateConflictTests(ConflictBase):
    def test_conflict_with_mergeability_lag_is_a_base_finding_on_the_first_run(self):
        """The incident (#747/#748): the first view after `pr create` reads UNKNOWN; the local check still finds it."""
        g = self.goal()
        self.deliver(g, code=CONFLICT_CODE)
        self.w.push_dev(DEV_CODE)
        self.fault(mergeable_lag=1)
        out = self.op(g, "integrate")
        self.assert_conflict_on_base(out, files=["src/app.py"])
        self.assert_base_reopened(g)
        views = [c for c in self.gh.calls() if c[:2] == ["pr", "view"]]
        self.assertEqual(1, len(views))                            # the first and only view read UNKNOWN

    def test_conflict_seen_only_by_github_is_a_base_finding(self):
        """dev moves after integrate's fetch and before GitHub answers: merge-tree is clean, GitHub says CONFLICTING."""
        g = self.goal()
        self.deliver(g, code=CONFLICT_CODE)
        old = self.w.remote_git("rev-parse", "refs/heads/dev")
        moved = self.w.push_dev(DEV_CODE)
        self.w.remote_git("update-ref", "refs/heads/dev", old, moved)
        self.fault(advance_before_view={"ref": "dev", "to": moved})
        out = self.op(g, "integrate")
        self.assert_conflict_on_base(out)
        self.assertEqual(moved, self.w.remote_git("rev-parse", "refs/heads/dev"))
        self.assert_base_reopened(g)

    def test_unknown_mergeability_waits_then_proceeds_to_checks(self):
        g = self.goal()
        self.deliver(g)
        self.fault(mergeable_lag=1)
        out = self.op(g, "integrate")
        self.assert_waits_not_on_checks(out, "computing mergeability")
        self.gh.set_checks(self.pr_head(g), ci=["pass"])
        out = self.op(g, "integrate")                               # after retry_after: a real value, checks pass
        self.assertTrue(out["ran"]["ok"], out["ran"])
        self.assertEqual(["ci"], out["ran"]["output"]["ci"]["passed"])

    def test_mergeable_with_pending_checks_waits_and_names_the_merge_state(self):
        g = self.goal()
        self.deliver(g)
        out = self.op(g, "integrate")
        b = out["ran"]["blocked"]
        self.assertEqual("time", b["waiting_for"])
        self.assertIn("required checks pending: ci", b["reason"])
        self.assertIn("mergeable: MERGEABLE/CLEAN", b["reason"])

    def test_no_checks_at_all_asks_the_human_after_fifteen_minutes(self):
        g = self.goal()
        self.deliver(g)
        start = self.w.now
        out = self.op(g, "integrate")                               # t = 0
        self.assertEqual("time", out["ran"]["blocked"]["waiting_for"])
        head = self.pr_head(g)
        t5 = parse_iso(self.blocked(g)["retry_after"])
        self.assertEqual(5, (t5 - start) // MIN)
        out = self.op_at(g, "integrate", t5)                        # t = 5: still waiting
        self.assertEqual("time", out["ran"]["blocked"]["waiting_for"], out["ran"])
        t15 = parse_iso(self.blocked(g)["retry_after"])
        self.assertEqual(15, (t15 - start) // MIN)
        out = self.op_at(g, "integrate", t15)                       # t = 15: no check of any name ever appeared
        b = out["ran"]["blocked"]
        self.assertEqual(("blocked", "human"), (out["ran"]["outcome"], b["waiting_for"]), out["ran"])
        q = b["question"]
        self.assertRegex(q, re.compile(r"no checks", re.I))
        self.assertIn("#1", q)
        self.assertIn(head[:7], q)
        self.assertIn("MERGEABLE", q)
        self.assertNotIn("have not finished", q)                    # not the 120-minute question
        opts = " ".join(b.get("options") or [])
        self.assertIn("wait", opts)
        self.assertIn("verification.required_ci", opts)

    def test_pending_required_check_in_the_rollup_keeps_waiting_past_fifteen_minutes(self):
        g = self.goal()
        self.deliver(g)
        start = self.w.now
        self.op(g, "integrate")
        self.gh.set_checks(self.pr_head(g), ci=["pending"])
        for _ in range(3):                                          # t = 5, 15, 35
            nxt = parse_iso(self.blocked(g)["retry_after"])
            out = self.op_at(g, "integrate", nxt)
            self.assertEqual("time", out["ran"]["blocked"]["waiting_for"], out["ran"])
        self.assertGreaterEqual(self.w.now - start, 35 * MIN)

    def test_head_not_yet_seen_waits_instead_of_reporting_checks_pending(self):
        g = self.goal()
        self.fault(head_lag=1)
        self.deliver(g)
        self.op(g, "integrate")                                     # the PR exists; GitHub has shown head H1
        h1 = self.pr_head(g)
        self.gh.set_checks(h1, ci=["pass"])
        # dev moves; a clean restack gives a new PR head H2, which GitHub has not seen on the next view
        self.w.push_dev({"other.txt": "o\n"})
        self.w.ok("a", "reopen", str(g), "base", "--note", "dev moved")
        self.assertEqual("done", self.op(g, "base")["ran"]["outcome"])
        self.assertTrue(self.op(g, "run_tests")["ran"]["ok"])
        out = self.op(g, "integrate")
        h2 = self.pr_head(g)
        self.assertNotEqual(h1, h2)
        self.assert_waits_not_on_checks(out, "has not seen the PR head")
        self.gh.set_checks(h2, ci=["pass"])
        out = self.op(g, "integrate")                               # now GitHub shows H2
        self.assertTrue(out["ran"]["ok"], out["ran"])
        self.assertEqual(h2, out["ran"]["output"]["pr"]["head"])


class SameFileJourney(ConflictBase):
    def resolve(self, wtd, files):
        wtd.write(files)
        wtd.git("add", "-A")
        wtd.git("-c", "core.editor=true", "rebase", "--continue")

    def integrate_until_ok(self, g, tries=4):
        out = None
        for _ in range(tries):
            out = self.op(g, "integrate")
            if out["ran"]["outcome"] == "done":
                return out
            self.gh.set_checks(self.pr_head(g), ci=["pass"])
        return out

    def test_two_goals_change_the_same_line_and_the_second_rebases_by_hand(self):
        a = self.goal()
        self.deliver(a, code={"src/app.py": "def app():\n    return 2\n"})
        b = self.goal()
        wtb = self.deliver(b, code={"src/app.py": "def app():\n    return 3\n"})
        # A integrates and merges into dev
        out = self.integrate_until_ok(a)
        self.assertTrue(out["ran"]["ok"], out["ran"])
        self.approve(a, "approve_merge")
        self.assertEqual("done", self.op(a, "merge")["closed"]["reason"])
        # B's PR conflicts; GitHub's first view reads UNKNOWN, as in the incident
        self.fault(mergeable_lag={"2": 1})
        out = self.op(b, "integrate")
        self.assert_conflict_on_base(out, files=["src/app.py"])
        self.assert_base_reopened(b)
        # base rebases onto the new tip and blocks on the conflict; it is resolved by hand in B's worktree
        out = self.op(b, "base")
        self.assertEqual("blocked", out["ran"]["outcome"], out["ran"])
        self.assertIn("rebase conflict in src/app.py", out["ran"]["blocked"]["reason"])
        self.resolve(wtb, {"src/app.py": "def app():\n    return 23\n"})
        out = self.op(b, "base")
        self.assertEqual("done", out["ran"]["outcome"], out["ran"])
        dev = self.w.remote_git("rev-parse", "refs/heads/dev")
        self.assertEqual(dev, out["ran"]["output"]["base_commit"])
        st = self.states(b)
        self.assertTrue(st["implement"].startswith("ready (stale"), st["implement"])
        self.assertNotEqual("current", st["integrate"])
        # implement follows the replay rules to the hand-rebased commit; then tests and review
        c = self.A.start(b, "implement")
        self.A.submit(b, "implement", c, {"summary": "Built."})
        self.assertTrue(self.op(b, "run_tests")["ran"]["ok"])
        if self.states(b)["review_impl"] != "current":
            self.review(self.B, b, "review_impl")
        # integrate rebuilds the PR, which is now mergeable, and finishes once the checks pass
        out = self.integrate_until_ok(b)
        self.assertTrue(out["ran"]["ok"], out["ran"])
        head = out["ran"]["output"]["pr"]["head"]
        self.assertEqual("", self.w.remote_git("merge-base", "--is-ancestor", dev, head))   # on the merged tip
        self.assertEqual("def app():\n    return 23", self.w.remote_git("show", f"{head}:src/app.py"))
        self.approve(b, "approve_merge")
        self.assertEqual("done", self.op(b, "merge")["closed"]["reason"])
        self.assertEqual("def app():\n    return 23", self.w.remote_git("show", "refs/heads/dev:src/app.py"))


if __name__ == "__main__":
    unittest.main()
