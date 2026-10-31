"""Step 2: portfolio, stuck, budgets, ordering and `next` rendering (SPEC §4.10, §4.11, §3.15)."""

from __future__ import annotations

import unittest

import engine_fixtures as fx
from engine_sim import Sim
from engine import render
from engine.canon import canonical, iso
from engine.frontier import Lease


class FakeReader(render.Reader):
    def prompt(self, name):
        p = fx.TEMPLATES / "prompts" / name
        return p.read_text() if p.is_file() else None


def ctx(s, **kw):
    return render.Ctx(prefix="zzzops", now=s.now, settings=s.settings, coordinator={"commit": "c" * 40, "current": True},
                      reader=FakeReader(), goal_commits={g: "a" * 40 for g in s.docs}, **kw)


class Base(unittest.TestCase):
    renamed = False

    def setUp(self):
        self.s = Sim(workflow=fx.renamed_workflow() if self.renamed else None)
        self.m = fx.RENAME if self.renamed else {n: n for n in fx.DEFAULT_NODES}

    def n(self, x):
        return self.m[x]

    def next(self, scope=None, **kw):
        return render.render_next(ctx(self.s), self.s.eval(), scope=scope, **kw)

    def drive_to(self, g, node):
        s = self.s
        for _ in range(80):
            st = s.st(g, self.n(node))
            if st["name"] in ("ready", "needs_human", "current", "waiting"):
                return st
            acts = [a for a in s.actionable(g) if a != self.n(node)]
            if not acts:
                return st
            s.step(g, acts[0])


class DependencyTests(Base):
    def test_dependent_discovery_runs_while_dependency_is_unmerged(self):
        s = self.s
        s.goal(1001)
        s.goal(1002, deps=[1001])
        # the dependent's design waits for the dependency's reviewed design only
        self.assertEqual("blocked", s.st(1002, self.n("design"))["name"])
        s.step(1001, self.n("design"))
        s.step(1001, self.n("review_design"))
        self.assertEqual("ready", s.st(1002, self.n("design"))["name"])
        out = self.next()
        self.assertIn((1002, self.n("design")), [(a["goal"], a["node"]) for a in out["actions"]])

    def test_delivery_waits_for_dependency_integrate_as_a_named_wait(self):
        s = self.s
        s.goal(1001)
        s.goal(1002, deps=[1001])
        self.drive_to(1001, "base")
        for _ in range(10):
            acts = s.actionable(1002)
            if not acts:
                break
            s.step(1002, acts[0])
        st = s.st(1002, self.n("base"))
        self.assertEqual("blocked", st["name"])
        m = st["missing"][0]
        self.assertEqual(("dependency", 1001, True), (m["reason"], m["dep"], m["wait"]))
        res = s.eval().goals[1002]
        self.assertIsNone(res.stuck)
        waits = [w for w in self.next()["waiting"] if w["goal"] == 1002]
        self.assertEqual(f"G1001 {self.n('integrate')}", waits[0]["until"])

    def test_cancelled_dependency_makes_the_dependent_stuck_with_options(self):
        s = self.s
        s.goal(1001)
        s.goal(1002, deps=[1001])
        s.docs[1001].update(state="closed", closed={"reason": "cancelled", "note": "n", "by": "d", "at": iso(s.now)})
        res = s.eval().goals[1002]
        self.assertIsNotNone(res.stuck)
        self.assertEqual("dependency", res.stuck["missing"][0]["reason"])
        out = self.next(scope=[1002])
        item = [i for i in out["needs_human"] if i["kind"] == "stuck"][0]
        labels = [o["label"] for o in item["options"]]
        self.assertEqual(["drop G1001", "retarget G1001", "cancel the goal"], labels)
        self.assertEqual({"set": {"depends_on": []}}, item["options"][0]["file"])
        self.assertIn("--base", item["options"][0]["command"]["argv"])

    def test_held_dependency_is_a_wait_not_stuck(self):
        s = self.s
        s.goal(1001, state="held")
        s.goal(1002, deps=[1001])
        res = s.eval().goals[1002]
        self.assertIsNone(res.stuck)
        waits = [w for w in self.next()["waiting"] if w["goal"] == 1002]
        self.assertEqual("G1001 held", waits[0]["until"])

    def test_done_dependency_without_merge_resolves_optional_inputs_as_null(self):
        s = self.s
        s.goal(1001)
        self.drive_to(1001, "base")
        s.docs[1001].update(state="closed", closed={"reason": "done", "note": "n", "by": "d", "at": iso(s.now)})
        s.goal(1002, deps=[1001])
        for _ in range(10):
            acts = s.actionable(1002)
            if not acts or s.st(1002, self.n("base"))["name"] == "ready":
                break
            s.step(1002, acts[0])
        st = s.st(1002, self.n("base"))
        self.assertEqual("ready", st["name"], st)

    def test_newer_dependency_waits_for_an_engine_upgrade(self):
        s = self.s
        s.goal(1002, deps=[1001])
        s.newer.add(1001)
        res = s.eval().goals[1002]
        self.assertIsNone(res.stuck)
        self.assertEqual("engine upgrade", [w for w in self.next()["waiting"] if w["goal"] == 1002][0]["until"])

    def test_dependency_cycle_is_invalid(self):
        s = self.s
        s.goal(1001, deps=[1002])
        s.goal(1002, deps=[1001])
        p = s.eval()
        self.assertEqual({1001, 1002}, set(p.invalid))


class GoalLevelTests(Base):
    def test_close_item_when_every_terminal_is_current(self):
        s = self.s
        s.goal(1)
        s.drive(1, until=self.n("merge"))
        res = s.eval().goals[1]
        self.assertTrue(res.close)
        item = [i for i in self.next(scope=[1])["needs_human"] if i["kind"] == "close"][0]
        self.assertEqual({"state": "closed", "closed.reason": "done", "closed.note": "every terminal node is current"},
                         item["options"][0]["file"]["set"])

    def test_budget_suppresses_agent_actions_but_not_ops_or_humans(self):
        s = self.s
        s.goal(1, budget=0)
        s.step(1, self.n("design"))
        s.step(1, self.n("review_design"))
        s.start(1, self.n("approve_design"))if False else None
        s.answer(1, self.n("approve_design"), decision="changes_requested", quote="redo")
        s.step(1, self.n("design"))                                  # a counted re-run: 1 > 0
        res = s.eval().goals[1]
        self.assertTrue(res.budget["over"])
        out = self.next(scope=[1])
        self.assertEqual([], [a for a in out["actions"] if a["kind"] == "agent"])
        b = [i for i in out["needs_human"] if i["kind"] == "budget"][0]
        self.assertIn("used 1 correction runs (limit 0)", b["question"])
        self.assertEqual({"budget": 1 + 3 * 6}, b["options"][0]["file"]["set"])

    def test_default_budget_is_eighteen(self):
        s = self.s
        s.goal(1)
        self.assertEqual(18, s.eval().goals[1].budget["limit"])

    def test_stale_on_def_or_policy_does_not_count(self):
        s = self.s
        s.goal(1)
        s.drive(1, until=self.n("merge"))
        s.graphs["default"].nodes[self.n("implement")]["rev"] = 1
        s.step(1, self.n("implement"), same=True)
        self.assertEqual(0, s.docs[1]["records"][self.n("implement")]["correction_runs"])

    def test_crash_loop_on_over_budget_agent_prints_raise_first(self):
        s = self.s
        s.goal(1, budget=0)
        s.step(1, self.n("design"))
        s.step(1, self.n("review_design"))
        s.answer(1, self.n("approve_design"), decision="changes_requested", quote="redo")
        s.step(1, self.n("design"))
        s.answer(1, self.n("approve_design")) if s.st(1, self.n("approve_design"))["name"] == "needs_human" else None
        did = self.n("design")
        s.docs[1]["records"].pop(self.n("review_design"), None)
        for _ in range(3):
            s.leases[(1, did)] = Lease(1, did, s.docs[1]["records"][did]["attempt"] + 1 + _, "claude:x/y", "stale", 120,
                                       s.now - 10 ** 6)
        s.leases[(1, did)].attempt = s.docs[1]["records"][did]["attempt"] + 3
        s.graphs["default"].nodes[did]["rev"] = 5                    # make it ready again
        st = s.st(1, did)
        self.assertEqual(("needs_human", "crash_loop"), (st["name"], st["kind"]))
        item = [i for i in self.next(scope=[1])["needs_human"] if i["kind"] == "crash_loop"][0]
        first = item["options"][0]
        self.assertEqual("one more try (raise the budget first)", first["label"])
        self.assertEqual(["start", "1", did, "--as", "<LABEL>", "--reclaim", "--force"], first["then"]["argv"])

    def test_terminal_node_crash_loop_offers_no_skip(self):
        s = self.s
        s.goal(1)
        self.drive_to(1, "merge")
        mid = self.n("merge")
        s.leases[(1, mid)] = Lease(1, mid, 3, "claude:x/y", "new", 15, s.now - 10 ** 6)
        item = [i for i in self.next(scope=[1])["needs_human"] if i["kind"] == "crash_loop"][0]
        self.assertFalse(any(o["label"].startswith("skip") for o in item["options"]))


class RenderTests(Base):
    def test_determinism(self):
        s = self.s
        for g in (1001, 1002, 1003):
            s.goal(g, deps=[1001] if g != 1001 else [])
        self.assertEqual(canonical(self.next()), canonical(self.next()))

    def test_stage_first_puts_discovery_and_humans_first(self):
        s = self.s
        s.goal(1001)
        self.drive_to(1001, "test_design")
        s.goal(1002, priority="P3")
        out = self.next()
        stages = [a["stage"] for a in out["actions"]]
        self.assertEqual(sorted(stages, key=["discovery", "delivery"].index), stages)
        self.assertEqual("discovery", out["actions"][0]["stage"])
        s.settings["scheduling"]["order"] = "goal_first"
        out = self.next()
        self.assertEqual(1001, out["actions"][0]["goal"])

    def test_wake_at(self):
        s = self.s
        s.goal(1)
        self.assertIsNone(self.next()["wake_at"])
        s.start(1, self.n("design"))
        self.assertEqual(iso(s.now + 120 * 60), self.next()["wake_at"])
        s.goal(2, release=5)
        self.assertEqual(iso(s.now + 120 * 60), self.next()["wake_at"])  # release gates carry no time

    def test_scope_and_also_pending(self):
        s = self.s
        s.goal(1)
        s.goal(2)
        out = self.next(scope=[1])
        self.assertEqual([1], sorted({a["goal"] for a in out["actions"]}))
        self.assertEqual({"human": 0, "actions": 1}, out["also_pending"])

    def test_truncation_keeps_under_8k(self):
        s = self.s
        for g in range(1, 120):
            s.goal(g)
        out = self.next()
        self.assertLessEqual(len(canonical(out)), render.NEXT_LIMIT)
        self.assertIn("truncated", out)
        self.assertGreater(out["truncated"]["actions"], 0)
        everything = self.next(all_=True)
        self.assertEqual(119, len(everything["actions"]))
        self.assertEqual(119, len(everything["goals"]))

    def test_paused_by_policy_branch(self):
        s = self.s
        s.goal(1)
        out = self.next(blockers=[{"kind": "policy_branch", "message": "paused: {n} actions paused"}], paused=True)
        self.assertEqual([], out["actions"])
        self.assertEqual("paused: 1 actions paused", out["blockers"][0]["message"])

    def test_approve_item_full_form(self):
        s = self.s
        s.goal(1)
        self.drive_to(1, "approve_design")
        out = self.next(scope=[1])
        item = out["needs_human"][0]
        self.assertEqual("approve", item["kind"])
        self.assertEqual("Approve the design for G1 (Goal 1)?", item["question"])
        self.assertEqual(["approve", "request changes", "cancel the goal"], [o["label"] for o in item["options"]])
        self.assertTrue(item["fp"].startswith("v1:sha256:"))
        self.assertIn("--fp", item["options"][0]["command"]["argv"])
        compact = self.next()["needs_human"][0]
        self.assertEqual({"goal", "node", "kind", "question", "since", "expand"}, set(compact))

    def test_workspace_busy(self):
        s = self.s
        s.goal(1)
        self.drive_to(1, "implement")
        s.start(1, self.n("implement"))                                  # a live workspace lease
        s.graphs["default"].nodes[self.n("base")]["rev"] = 1             # base is ready again meanwhile
        self.assertEqual("ready", s.st(1, self.n("base"))["name"])
        out = self.next()
        self.assertNotIn(self.n("base"), [a["node"] for a in out["actions"]])
        self.assertIn(f"workspace busy: {self.n('implement')}", [w["reason"] for w in out["waiting"]])

    def test_mass_expiry_marks_reclaims(self):
        s = self.s
        for g in (1, 2, 3):
            s.goal(g)
            s.start(g, self.n("design"))
        s.tick(200 * 60)
        p = s.eval()
        self.assertTrue(p.mass_expiry)
        out = self.next()
        self.assertTrue(all(a.get("requires_force") for a in out["actions"] if a["reason"] == "reclaim"))


class RenamedDependencyTests(DependencyTests):
    renamed = True


class RenamedGoalLevelTests(GoalLevelTests):
    renamed = True


class RenamedRenderTests(RenderTests):
    renamed = True

    def test_approve_item_full_form(self):
        pass                                                    # the prompt files keep their default names


if __name__ == "__main__":
    unittest.main()
