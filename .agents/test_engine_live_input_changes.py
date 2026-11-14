"""G1014: `edit`, `renew` and `validate --policy-ref` warn when the inputs of a running phase change.

Derived from .zzzops/reviews/1014/design.md (attempt 2), section "Tests" items 1-7, plus the scope, held-goal and
additive-output promises of the Approach and Risks sections.
"""

from __future__ import annotations

import copy
import json
import os
import shlex
import unittest

import engine_fixtures as fx
from test_engine_lifecycle import LONG, Journey

LABEL = "<LABEL>"
RENEW_KEYS = {"ok", "coordinator", "attempt", "expires_at", "renew_every_minutes"}


class LiveInputChangeBase(Journey):
    def tip(self, g):
        return self.show(g)["goal_commit"]

    def edit(self, g, *sets, apply=False, now=None):
        argv = ["edit", str(g)]
        for s in sets:
            argv += ["--set", s]
        if apply:
            argv += ["--base", self.tip(g)]
        return self.w.ok("a", *argv, now=now)

    def edit_file(self, g, content, now=None):
        return self.w.ok("a", "edit", str(g), "--file", self.w.file(content), "--base", self.tip(g), now=now)

    def renew(self, g, node, attempt=1, clone="a", now=None):
        return self.w.ok(clone, "renew", str(g), self.n(node), "--attempt", str(attempt), now=now)

    def keys(self, entries):
        return [(e["goal"], e["node"]) for e in entries]

    def assert_entry(self, e, g, node, card, holder, stale_because):
        n = self.n(node)
        self.assertEqual(g, e["goal"])
        self.assertEqual(n, e["node"])
        self.assertEqual(card["lease"]["attempt"], e["attempt"])
        self.assertEqual(holder, e["holder"])
        self.assertEqual(card["lease"]["expires_at"], e["expires_at"])
        self.assertEqual(stale_because, e["stale_because"])
        self.assert_commands(e, g, node, card["lease"]["attempt"])
        self.assertIsInstance(e.get("note"), str)

    def assert_commands(self, e, g, node, attempt, repo=False):
        """`repo`: worker-facing output (renew) carries `--repo <primary>` (G1028); edit's root-facing entries do not."""
        n = self.n(node)
        tail, text = [], ""
        if repo:
            self.assertEqual("--repo", e["abandon"]["argv"][-2], e["abandon"])
            tail = ["--repo", e["abandon"]["argv"][-1]]
            self.assertTrue(os.path.samefile(self.w.clones["a"].path, tail[1]), tail)
            text = " --repo " + shlex.quote(tail[1])
        self.assertEqual(["abandon", str(g), n, "--attempt", str(attempt)] + tail, e["abandon"]["argv"])
        self.assertEqual(f"zzzops abandon {g} {n} --attempt {attempt}" + text, e["abandon"]["command"])
        self.assertEqual(["start", str(g), n, "--as", LABEL, "--reclaim"] + tail, e["restart"]["argv"])
        self.assertEqual(f"zzzops start {g} {n} --as {LABEL} --reclaim" + text, e["restart"]["command"])


class EditLiveLeaseTests(LiveInputChangeBase):
    # ---- design test 1: dry run and applied edit list the running phase
    def test_spec_edit_lists_the_running_design_in_preview_and_applied_result(self):
        g = self.goal()
        card = self.A.start(g, self.n("design"))
        dry = self.edit(g, 'spec="a new spec"')
        self.assertFalse(dry["applied"])
        self.assertEqual(1, len(dry["live_leases_on_changed_nodes"]), dry)
        self.assert_entry(dry["live_leases_on_changed_nodes"][0], g, "design", card, self.A.label, ["inputs.spec"])
        self.assertIn("live_leases_on_changed_nodes", dry["warning"])
        self.assertTrue(dry["warning"].startswith("1 running phase"), dry["warning"])
        self.assertEqual(0, dry["stale_agent_phases"])         # its meaning is unchanged
        applied = self.edit(g, 'spec="a new spec"', apply=True)
        self.assertTrue(applied["applied"])
        self.assertEqual(dry["live_leases_on_changed_nodes"], applied["live_leases_on_changed_nodes"])
        self.assertIn("live_leases_on_changed_nodes", applied["warning"])
        self.assertEqual(0, applied["stale_agent_phases"])

    def test_existing_stale_count_still_counts_current_phases_only(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        card = self.B.start(g, self.n("review_design"))
        out = self.edit(g, 'spec="another"')
        self.assertEqual(1, out["stale_agent_phases"])            # design: current -> ready (stale)
        self.assertEqual([(g, self.n("review_design"))], self.keys(out["live_leases_on_changed_nodes"]))
        self.assert_entry(out["live_leases_on_changed_nodes"][0], g, "review_design", card, self.B.label,
                          ["inputs.spec"])

    # ---- design test 3: an edit that touches no consumed input lists nothing
    def test_edit_of_unconsumed_fields_lists_nothing_and_renew_is_unchanged(self):
        g = self.goal()
        self.A.start(g, self.n("design"))
        for s in ('priority="P1"', 'links={"issue": 77}'):
            dry = self.edit(g, s)
            self.assertEqual([], dry["live_leases_on_changed_nodes"], s)
            self.assertNotIn("warning", dry, s)
        out = self.edit(g, 'priority="P1"', apply=True)
        self.assertEqual([], out["live_leases_on_changed_nodes"])
        self.assertNotIn("warning", out)
        r = self.renew(g, "design")
        self.assertNotIn("inputs_changed", r)
        self.assertEqual(RENEW_KEYS, set(r))

    def test_edit_without_any_lease_has_an_empty_list(self):
        g = self.goal()
        out = self.edit(g, 'spec="x"')
        self.assertEqual([], out["live_leases_on_changed_nodes"])
        self.assertNotIn("warning", out)

    # ---- design test 4: held and closed goals
    def test_hold_and_close_list_nothing(self):
        g = self.goal()
        self.A.start(g, self.n("design"))
        out = self.edit(g, 'state="held"')
        self.assertEqual([], out["live_leases_on_changed_nodes"])
        out = self.edit(g, 'state="held"', apply=True)
        self.assertEqual([], out["live_leases_on_changed_nodes"])
        self.assertNotIn("warning", out)
        h = self.goal()
        self.A.start(h, self.n("design"))
        out = self.edit_file(h, {"set": {"state": "closed", "closed.reason": "cancelled", "closed.note": "not needed"}})
        self.assertTrue(out["applied"])
        self.assertEqual([], out["live_leases_on_changed_nodes"])
        self.assertNotIn("warning", out)

    def test_spec_edit_of_a_held_goal_with_a_live_lease_is_listed(self):
        g = self.goal()
        card = self.A.start(g, self.n("design"))
        self.edit(g, 'state="held"', apply=True)
        out = self.edit(g, 'spec="changed while held"')
        self.assertEqual(1, len(out["live_leases_on_changed_nodes"]), out)
        self.assert_entry(out["live_leases_on_changed_nodes"][0], g, "design", card, self.A.label, ["inputs.spec"])

    # ---- design test 5: dependents are in scope
    def test_edit_of_a_dependency_lists_the_dependent_running_phase(self):
        g1 = self.goal()
        c = self.A.start(g1, self.n("design"))
        self.A.submit(g1, self.n("design"), c, {"summary": "D1"}, artifact="# D1\n")
        self.review(self.B, g1, "review_design")
        g2 = self.goal(depends_on=[g1])
        card = self.B.start(g2, self.n("design"))
        dry = self.edit(g1, 'spec="the dependency changes"')
        self.assertEqual([(g2, self.n("design"))], self.keys(dry["live_leases_on_changed_nodes"]))
        # G1's design goes stale, so G2's dep_designs input no longer resolves
        self.assert_entry(dry["live_leases_on_changed_nodes"][0], g2, "design", card, self.B.label, ["unresolved"])
        self.assertIn("warning", dry)
        applied = self.edit(g1, 'spec="the dependency changes"', apply=True)
        self.assertEqual(dry["live_leases_on_changed_nodes"], applied["live_leases_on_changed_nodes"])
        r = self.renew(g2, "design", clone="b")
        self.assertTrue(r["inputs_changed"])
        self.assertEqual(["unresolved"], r["stale_because"])

    def test_an_unrelated_goal_is_out_of_scope(self):
        g1 = self.goal()
        g2 = self.goal()
        self.B.start(g2, self.n("design"))
        out = self.edit(g1, 'spec="only g1"')
        self.assertEqual([], out["live_leases_on_changed_nodes"])

    # ---- design test 7: the printed commands work end to end
    def test_abandon_then_restart_command_succeeds(self):
        g = self.goal()
        self.A.start(g, self.n("design"))
        out = self.edit(g, 'spec="a new spec"', apply=True)
        e = out["live_leases_on_changed_nodes"][0]
        self.w.ok("a", *e["abandon"]["argv"])
        argv = [self.B.label if x == LABEL else x for x in e["restart"]["argv"]]
        c2 = self.w.ok("b", *argv)
        self.assertEqual(2, c2["lease"]["attempt"])
        self.assertEqual("reclaim", c2["reason"])


class RenewInputsChangedTests(LiveInputChangeBase):
    # ---- design test 2: renew after the edit reports the change
    def test_renew_reports_inputs_changed_after_an_edit(self):
        g = self.goal()
        self.A.start(g, self.n("design"))
        before = self.renew(g, "design", now=fx.NOW + 60)
        self.assertNotIn("inputs_changed", before)
        self.assertEqual(RENEW_KEYS, set(before))                # byte-identical shape when nothing changed
        edit = self.edit(g, 'spec="a new spec"', apply=True)
        e = edit["live_leases_on_changed_nodes"][0]
        r = self.renew(g, "design", now=fx.NOW + 120)
        self.assertTrue(r["ok"])
        self.assertIs(True, r["inputs_changed"])
        self.assertEqual(["inputs.spec"], r["stale_because"])
        # the same commands as edit's entry, plus --repo (renew is worker-facing, G1028)
        self.assertEqual(e["abandon"]["argv"], r["abandon"]["argv"][:-2])
        self.assertEqual(e["restart"]["argv"], r["restart"]["argv"][:-2])
        self.assertIsInstance(r["hint"], str)
        self.assert_commands(r, g, "design", 1, repo=True)
        # it keeps reporting on later renewals: the comparison is against the fingerprint recorded at start
        self.assertTrue(self.renew(g, "design", now=fx.NOW + 180)["inputs_changed"])

    def test_renew_still_extends_the_lease_when_inputs_changed(self):
        g = self.goal()
        self.A.start(g, self.n("design"))
        self.edit(g, 'spec="a new spec"', apply=True)
        r = self.renew(g, "design", now=fx.NOW + 3000)
        self.assertTrue(r["inputs_changed"])
        out = self.w.ok("b", "next", now=fx.NOW + 3000 + 120 * 60 - 60)
        self.assertEqual([self.n("design")], [x["node"] for x in out["running"]])

    # ---- design test 2b: an expired (not abandoned) lease is evaluated as renewed
    def test_renew_of_an_expired_lease_reports_inputs_changed(self):
        g = self.goal()
        self.A.start(g, self.n("design"))
        late = fx.NOW + LONG
        out = self.edit(g, 'spec="changed while the worker was away"', apply=True, now=late)
        self.assertEqual([], out["live_leases_on_changed_nodes"])   # the lease is reclaimable, not running
        r = self.renew(g, "design", now=late + 60)
        self.assertTrue(r["ok"])
        self.assertIs(True, r["inputs_changed"])
        self.assertEqual(["inputs.spec"], r["stale_because"])
        self.assert_commands(r, g, "design", 1, repo=True)

    def test_renew_of_an_expired_lease_without_an_edit_reports_nothing(self):
        g = self.goal()
        self.A.start(g, self.n("design"))
        r = self.renew(g, "design", now=fx.NOW + LONG + 60)
        self.assertNotIn("inputs_changed", r)
        self.assertEqual(RENEW_KEYS, set(r))

    def test_renew_reports_an_upstream_rerun(self):
        """A change since start from a re-run upstream (not an edit of this goal) is reported too."""
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        self.B.start(g, self.n("review_design"))
        self.w.ok("a", "reopen", str(g), self.n("design"), "--note", "redo")
        c2 = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c2, {"summary": "D2", "responses": {f"{self.n('design')}:reopen:1": "fixed: redone"}},
                      artifact="# D2\n")
        r = self.renew(g, "review_design", clone="b")
        self.assertTrue(r["inputs_changed"])
        self.assertTrue(r["stale_because"])


class PolicyLiveLeaseTests(LiveInputChangeBase):
    def policy_branch(self, files, topic="rev"):
        s = self.w.seed
        s.git("pull", "-q", "--ff-only", "origin", "dev")
        s.git("checkout", "-q", "-b", f"zzzops/policy/{topic}")
        c = s.commit(files, "chore(zzzops): policy change")
        s.git("push", "-q", "origin", f"HEAD:refs/heads/zzzops/policy/{topic}")
        s.git("checkout", "-q", "dev")
        return c

    # ---- design test 6: a definition-only change on a running node is listed
    def test_validate_policy_ref_lists_a_running_node_whose_definition_changes(self):
        g = self.goal()
        card = self.A.start(g, self.n("design"))
        wf = copy.deepcopy(self.w.workflow)
        wf["graphs"]["default"]["nodes"][self.n("design")]["rev"] = 1
        self.policy_branch({".zzzops/workflow.json": json.dumps(wf, indent=2) + "\n"})
        _, out = self.w.run("b", "validate", "--policy-ref", "rev")   # environment checks (gh) may fail on CI
        self.assertEqual([], out["policy"])
        live = out["impact"]["live_leases_on_changed_nodes"]
        self.assertEqual([(g, self.n("design"))], self.keys(live), out["impact"])
        self.assert_entry(live[0], g, "design", card, self.A.label, ["def"])

    # ---- design section 5: the state-change rule stays in the union (a removed running node)
    def test_validate_policy_ref_lists_a_running_node_the_policy_removes(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        card = self.B.start(g, self.n("review_design"))
        wf = copy.deepcopy(self.w.workflow)
        nodes = wf["graphs"]["default"]["nodes"]
        rd = self.n("review_design")
        del nodes[rd]
        for nd in nodes.values():                       # drop every input that references the removed node
            ins = nd.get("inputs") or {}
            for k in [k for k, spec in ins.items() if rd in spec["from"].split(".")[:2]]:
                del ins[k]
        self.assertNotIn(rd, json.dumps(wf["graphs"]["default"]))
        self.policy_branch({".zzzops/workflow.json": json.dumps(wf, indent=2) + "\n"}, topic="drop")
        _, out = self.w.run("b", "validate", "--policy-ref", "drop")  # must not crash on the missing after-side node
        self.assertEqual([], out["policy"], out)
        live = out["impact"]["live_leases_on_changed_nodes"]
        # exactly one entry: the state rule (running -> removed) and the fingerprint rule are de-duplicated
        self.assertEqual([(g, rd)], self.keys(live), out["impact"])
        self.assert_entry(live[0], g, "review_design", card, self.B.label, [])

    def test_unchanged_policy_lists_no_live_lease(self):
        g = self.goal()
        self.A.start(g, self.n("design"))
        wf = copy.deepcopy(self.w.workflow)
        wf["graphs"]["default"]["nodes"][self.n("design")]["description"] = "wording only"   # not fingerprinted
        self.policy_branch({".zzzops/workflow.json": json.dumps(wf, indent=2) + "\n"}, topic="words")
        _, out = self.w.run("b", "validate", "--policy-ref", "words")
        self.assertEqual([], out["impact"]["live_leases_on_changed_nodes"])


class RenamedEditLiveLeaseTests(EditLiveLeaseTests):
    renamed = True


if __name__ == "__main__":
    unittest.main()
