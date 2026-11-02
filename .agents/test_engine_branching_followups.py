"""G1025 review_impl round 1 follow-ups (not frozen; the frozen suite is test_engine_branching.py).

- 1:1 a hotfix member with no line waits at `base` even when `base` is current, and `ops/run.target_of` never falls
  back to the integration branch for a line target without a branch;
- 1:2 `flow` needs settings.branching, a line goal's `flow` is immutable, and clearing `flow` writes schema 1;
- 1:4 the second fetch round runs only with an open line or a pending line item.
"""

from __future__ import annotations

import json
import sys
import unittest
from types import SimpleNamespace

import engine_fixtures as fx  # noqa: F401  (puts the engine on sys.path)
import test_engine_branching as tb  # module import: a module-level TestCase import would be collected twice
from test_engine_branching import BSim, Branching, ledger_of


class HotfixWaitFrontierTests(unittest.TestCase):
    drive_to_ready = tb.FrontierTests.drive_to_ready

    def test_current_base_waits_once_the_goal_moves_onto_an_unstarted_hotfix_line(self):
        s = BSim()
        s.goal(1001, release=1)
        self.drive_to_ready(s, 1001, "implement")
        self.assertEqual("current", s.st(1001, "base")["name"])
        d = s.docs[1001]
        d["schema"], d["flow"] = 2, {"hotfix": "x"}
        res = s.eval().goals[1001]
        self.assertEqual({"branch": None, "kind": "hotfix", "name": "x"}, res.target)
        self.assertEqual("waiting", res.st["base"]["name"], res.st["base"])
        self.assertEqual("hotfix_start", res.st["base"]["reason"])
        self.assertNotIn(res.st["implement"]["name"], ("ready", "needs_human", "current"), res.st["implement"])
        # the line starts: base restacks onto hotfix/x through the target part
        s.line(9000, kind="hotfix", name="x")
        res = s.eval().goals[1001]
        self.assertEqual("hotfix/x", res.target["branch"])
        st = res.st["base"]
        self.assertEqual("ready", st["name"], st)
        self.assertEqual("hotfix/x", st["parts"]["target"])


class TargetOfTests(unittest.TestCase):
    def session(self):
        return SimpleNamespace(snap=SimpleNamespace(I="dev", integration="d" * 40),
                               target_tip=lambda b: {"release/1": "r" * 40}.get(b))

    def test_no_branch_is_refused_not_mapped_to_the_integration_branch(self):
        from engine.errors import Refused
        from engine.ops.run import target_of
        s = self.session()
        res = SimpleNamespace(goal=7, target={"branch": None, "kind": "hotfix", "name": "x"})
        with self.assertRaises(Refused) as cm:
            target_of(s, res)
        self.assertEqual("not_ready", cm.exception.code)

    def test_integration_and_line_targets(self):
        from engine.ops.run import target_of
        s = self.session()
        self.assertEqual({"branch": "dev", "tip": "d" * 40}, target_of(s, SimpleNamespace(goal=1, target=None)))
        self.assertEqual({"branch": "dev", "tip": "d" * 40},
                         target_of(s, SimpleNamespace(goal=1, target={"branch": "dev", "kind": "integration"})))
        self.assertEqual({"branch": "release/1", "tip": "r" * 40},
                         target_of(s, SimpleNamespace(goal=1, target={"branch": "release/1", "kind": "release"})))


class FetchRoundTests(unittest.TestCase):
    def session(self, docs, branching=True):
        from engine.session import Session
        s = BSim(branching=branching)
        s.docs.update(docs(s))
        sess = Session.__new__(Session)
        sess.state = SimpleNamespace(settings=s.settings, ledger=ledger_of(s.docs), docs=s.docs)
        sess.snap = SimpleNamespace(targets={})
        sess.fetched = []
        sess.fetch_branches = lambda branches: sess.fetched.append(list(branches))
        return sess

    def test_no_fetch_without_an_open_line_or_a_pending_item(self):
        sess = self.session(lambda s: {1001: s.goal(1001, release=1)})
        sess.fetch_lines()
        self.assertEqual([], sess.fetched)

    def test_no_fetch_without_branching(self):
        sess = self.session(lambda s: {1001: s.goal(1001, release=1)}, branching=False)
        sess.fetch_lines()
        self.assertEqual([], sess.fetched)

    def test_open_line_fetches_production_and_the_line(self):
        sess = self.session(lambda s: {9000: s.line(9000)})
        sess.fetch_lines()
        self.assertEqual([["main", "release/1"]], sess.fetched)

    def test_pending_hotfix_start_fetches_production(self):
        def docs(s):
            d = s.goal(1001, release=1)
            d["schema"], d["flow"] = 2, {"hotfix": "x"}
            return {1001: d}
        sess = self.session(docs)
        sess.fetch_lines()
        self.assertEqual([["main"]], sess.fetched)

    def test_pending_release_cut_fetches_production(self):
        def docs(s):
            d = s.goal(1001, release=1)
            s.close(1001)
            return {1001: d}
        sess = self.session(docs)
        sess.fetch_lines()
        self.assertEqual([["main"]], sess.fetched)


class FlowGateTests(Branching):
    def test_line_goal_flow_is_immutable_and_cleared_flow_writes_schema_1(self):
        _, line = self.cut_release_1()
        for path, value in (("flow.name", "2"), ("flow.branch", "release/9"), ("flow", None),
                            ("flow", {"hotfix": "y"})):
            rc, err = self.w.run("a", "edit", str(line), "--set", f"{path}={json.dumps(value)}",
                                 "--base", self.goal_tip(line))
            self.assertNotEqual(0, rc, (path, value))
            self.assertEqual("validation", err["error"]["code"], err)
            self.assertIn("immutable", json.dumps(err))
        g = self.goal(release=2)
        rc, err = self.w.run("a", "edit", str(g), "--set", "flow=" + json.dumps(
            {"line": "release", "name": "2", "branch": "release/2", "from": "dev", "cut": "a" * 40}),
            "--base", self.goal_tip(g))
        self.assertEqual("validation", err["error"]["code"], err)
        self.w.ok("a", "edit", str(g), "--set", 'flow={"hotfix": "y"}', "--base", self.goal_tip(g))
        doc = self.show(g)["goal"]
        self.assertEqual((2, {"hotfix": "y"}), (doc["schema"], doc["flow"]))
        self.w.ok("a", "edit", str(g), "--set", "flow=null", "--base", self.goal_tip(g))
        doc = self.show(g)["goal"]
        self.assertEqual(1, doc["schema"])
        self.assertNotIn("flow", doc)


class FlowWithoutBranchingTests(Branching):
    branching = False

    def test_new_and_edit_refuse_flow(self):
        rc, err = self.w.run("a", "new", "--file", self.w.file({"title": "hf", "spec": "s", "flow": {"hotfix": "x"}}))
        self.assertNotEqual(0, rc)
        self.assertEqual("validation", err["error"]["code"], err)
        self.assertIn("settings.branching", json.dumps(err))
        g = self.goal()
        rc, err = self.w.run("a", "edit", str(g), "--set", 'flow={"hotfix": "x"}', "--base", self.goal_tip(g))
        self.assertEqual("validation", err["error"]["code"], err)
        self.assertEqual(1, self.show(g)["goal"]["schema"])


if __name__ == "__main__":
    unittest.main()
