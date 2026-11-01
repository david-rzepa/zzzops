"""G1028: keep findings and their status straight across review rounds and goal edits.

Derived from .zzzops/reviews/1028/design.md (revision 2), section 7 "Tests", items 1-13 (with 9a and 9b). They are
written before the implementation and pin these contracts:

- Carry (SPEC §4.9): an open finding of a stale agent or human carrier on another node stays live while its target's
  output is unchanged; op findings are not carried; a filtered lens's finding is carried when material, or when
  non-material with the filter's latest verdict `keep`. `frontier.portfolio(...).goals[g].stale` is the set of
  carriers with a done record that is not fresh. Card corrections from such a carrier carry `stale_review: true`.
- `edit` (dry run and applied) lists `carried_findings` [{goal, id, from, target, text, waive}] and, applied with
  carried findings and nothing waived, a `warning` naming carried_findings.
- Review cards: `previous.findings` is open findings only; `previous.resolved` lists the closed ones
  [{id, status, text}]. Submit: a restated `resolved` for a closed id is a no-op; a restated `open` is refused
  "already resolved" / "already waived" with a `follows` hint; unknown ids keep "unknown finding ids" and add
  `details.needs_status`.
- `follows`: a new review finding may name a prior finding of the same reviewer's latest record; it inherits the
  target and `rounds` (never `upheld`). Shown as card `follows`/`follows_text`, on `previous.findings`, and in the
  approve item's `facts`. Submit refuses it unless the policy requires capability `finding_follows` (G1027 form) or,
  in the G1028-first merge order, `engine.min` is at least this engine's new version. The write gate lives in
  submit (it reads the policy); `records.process_findings` keeps its signature, so the in-memory Sim exercises the
  record rules directly.
- `--repo DIR`: a global flag; worker-facing commands (card commands, renew's and abandon's restart) carry
  `--repo <primary worktree>`; `next` does not.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import tempfile
import types
import unittest

import engine_fixtures as fx
from engine_sim import Sim
from engine import ENGINE_VERSION
from engine import records as rec
from engine import schemas
from engine.card import previous
from engine.canon import canonical
from engine.errors import Refused
from test_engine_lifecycle import Journey

CAPS_DIR = fx.PLUGIN_CODE / "engine" / "capabilities"
G1027_MERGED = CAPS_DIR.is_dir()


def vtuple(v):
    return tuple(int(x) for x in v.split("."))


def follows_settings() -> dict:
    """Bootstrap settings under which the policy requires `finding_follows` (either merge order, design §6a)."""
    if G1027_MERGED:
        return {"engine.requires": ["finding_follows"]}
    return {"engine.min": ENGINE_VERSION}


def fake_session():
    return types.SimpleNamespace(git=types.SimpleNamespace(exists=lambda oid: False), fetch_work_of=lambda g: None)


def same_dir(a, b) -> bool:
    return os.path.realpath(a) == os.path.realpath(b)


# --------------------------------------------------------------------------------------------- Sim helpers


class SimBase(unittest.TestCase):
    workflow = None

    def setUp(self):
        self.s = Sim(workflow=self.workflow)

    def st(self, n, g=1):
        return self.s.st(g, n)

    def res(self, g=1):
        return self.s.eval().goals[g]

    def to(self, node, g=1):
        s = self.s
        for _ in range(80):
            x = s.st(g, node)
            if x["name"] in ("ready", "needs_human"):
                return x
            acts = [a for a in s.actionable(g) if a != node]
            if not acts:
                raise AssertionError(s.names(g))
            s.step(g, acts[0])
        raise AssertionError("did not reach " + node)

    def corr_ids(self, n, g=1):
        return [f["id"] for f in self.st(n, g).get("corrections") or []]

    def review(self, n, findings, decision=None, g=1):
        self.s.start(g, n)
        return self.s.submit(g, n, findings=findings, decision=decision)

    def refused(self, n, findings, decision=None, g=1) -> Refused:
        self.s.start(g, n)
        with self.assertRaises(Refused) as e:
            self.s.submit(g, n, findings=findings, decision=decision)
        return e.exception


def lens_workflow():
    """design -> one filtered lens -> its filter -> a human approval (independent of the shipped graph)."""
    return {"schema": 1, "graphs": {"default": {"terminal": ["approve"], "nodes": {
        "design": {"kind": "agent", "stage": "discovery", "prompt": "design.md",
                   "inputs": {"spec": {"from": "goal.spec"}}, "outputs": {"summary": "text", "doc": "artifact"}},
        "lens": {"kind": "agent", "stage": "discovery", "prompt": "review_design.md",
                 "review": {"subject": "design", "filter": "filt"},
                 "inputs": {"spec": {"from": "goal.spec"}, "doc": {"from": "design.doc"}}},
        "filt": {"kind": "agent", "stage": "discovery", "prompt": "design.md", "skippable": False,
                 "inputs": {"spec": {"from": "goal.spec"}, "doc": {"from": "design.doc"},
                            "lens": {"from": "lens.summary"}},
                 "outputs": {"summary": "text", "verdicts": "object"}},
        "approve": {"kind": "human", "stage": "discovery", "prompt": "approve_design.md", "review": {"subject": "design"},
                    "inputs": {"summary": {"from": "design.summary"}, "filter": {"from": "filt.summary"}}}}}}}


# --------------------------------------------------------------------------------------------- 1-5: carry


class CarryTests(SimBase):
    def test_1_spec_edit_keeps_open_review_findings_live_on_an_unchanged_target(self):
        self.s.goal(1)
        self.to("review_design")
        self.review("review_design", [{"text": "missing risks"}, {"text": "no rollback"}])
        self.assertEqual(["review_design:1:1", "review_design:1:2"], self.corr_ids("design"))
        self.s.docs[1]["spec"] = "a different spec"
        st = self.st("design")
        self.assertEqual(("ready", "stale"), (st["name"], st["reason"]))
        self.assertEqual(["review_design:1:1", "review_design:1:2"], self.corr_ids("design"))
        self.assertIn("review_design", self.res().stale)

    def test_1_depends_on_edit_keeps_them_too(self):
        self.s.goal(2)
        self.s.drive(2, until="approve_design")
        self.s.goal(1)
        self.to("review_design")
        self.review("review_design", [{"text": "missing risks"}])
        self.s.docs[1]["depends_on"] = [2]
        self.assertIn("review_design:1:1", [f["id"] for _, f in self.res().live["design"]])

    def test_3_dogfood_29_sibling_reopen_carries_the_other_finding(self):
        self.s.goal(1)
        self.to("review_tests")
        self.review("review_tests", [{"target": "design", "text": "A: the design misses a case"},
                                     {"target": "test_design", "text": "B: add an edge test"}])
        a, b = "review_tests:1:1", "review_tests:1:2"
        self.s.step(1, "design")                                   # answers A: design's output changes
        self.assertIn("review_tests", self.res().stale)
        self.assertIn(b, [f["id"] for _, f in self.res().live["test_design"]])
        self.assertNotIn(a, [f["id"] for _, f in self.res().live["design"]])
        for _ in range(20):
            if self.st("test_design")["name"] == "ready":
                break
            self.s.step(1, [n for n in self.s.actionable(1) if n != "test_design"][0])
        self.assertEqual([b], self.corr_ids("test_design"))

    def test_4_carry_ends_when_the_target_resubmits(self):
        self.s.goal(1)
        self.to("review_design")
        self.review("review_design", [{"text": "missing risks"}])
        self.s.docs[1]["spec"] = "a different spec"
        self.assertEqual(["review_design:1:1"], self.corr_ids("design"))
        self.s.step(1, "design", responses={"review_design:1:1": "fixed: added the risks"})
        self.assertEqual([], self.res().live["design"])
        self.assertEqual("current", self.st("design")["name"])
        self.assertEqual(("ready", "stale"), (self.st("review_design")["name"], self.st("review_design")["reason"]))
        self.assertIn("review_design", self.res().stale)

    def test_5_op_findings_are_not_carried(self):
        self.s.goal(1)
        self.to("run_tests")
        self.s.op(1, "run_tests", ok=False, raised=[{"key": "failed", "input": "code", "text": "tests fail"}])
        ids = self.corr_ids("implement")
        self.assertEqual(1, len(ids))
        self.assertTrue(ids[0].startswith("run_tests"), ids)
        self.s.settings["verification"]["commands"] = ["make check"]          # run_tests is stale, implement is not
        self.assertIn("run_tests", self.res().stale)
        self.assertEqual([], self.res().live["implement"])
        self.assertEqual("current", self.st("implement")["name"])


class LensCarryTests(SimBase):
    workflow = lens_workflow()

    def lens_round(self, findings):
        self.s.goal(1)
        self.to("lens")
        r = self.review("lens", findings)
        return [f["id"] for f in r["findings"]]

    def test_6_stale_lens_carries_material_and_keep_only(self):
        m, k, n, u = self.lens_round([
            {"text": "M", "impact": "breaks", "material": True},
            {"text": "K", "impact": "confuses", "material": False},
            {"text": "N", "impact": "cosmetic", "material": False},
            {"text": "U", "impact": "unjudged", "material": False}])
        self.s.start(1, "filt")
        self.s.submit(1, "filt", outputs={"verdicts": {k: {"verdict": "keep", "reason": "real"},
                                                         n: {"verdict": "note", "reason": "minor"}}})
        self.s.docs[1]["spec"] = "a different spec"                        # lens and filter go stale
        res = self.res()
        self.assertIn("lens", res.stale)
        self.assertEqual(sorted([m, k]), sorted(self.corr_ids("design")))
        self.assertNotIn(n, self.corr_ids("design"))                       # a note stays a note
        self.assertNotIn(u, self.corr_ids("design"))                       # unjudged non-material: not carried

    def test_6_material_lens_finding_is_carried_before_its_filter_ran(self):
        (m,) = self.lens_round([{"text": "M", "impact": "breaks", "material": True}])
        self.assertEqual([], self.res().live["design"])                     # waits for the filter (G1000)
        self.s.docs[1]["spec"] = "a different spec"
        self.assertEqual([m], self.corr_ids("design"))


# --------------------------------------------------------------------------------------------- 7: closed ids


class RestatementTests(SimBase):
    def setup_rounds(self):
        """review_design:1 raises F1, F2, F3; round 2 resolves F1, keeps F2, and F3 is waived (as edit does)."""
        self.s.goal(1)
        self.to("review_design")
        self.review("review_design", [{"text": "F1 risks"}, {"text": "F2 rollback"}, {"text": "F3 naming"}])
        self.f1, self.f2, self.f3 = "review_design:1:1", "review_design:1:2", "review_design:1:3"
        self.s.step(1, "design")
        self.review("review_design", [{"id": self.f1, "status": "resolved"}, {"id": self.f2, "status": "open"},
                                      {"id": self.f3, "status": "open"}], decision="changes_requested")
        r2 = self.s.docs[1]["records"]["review_design"]
        f3 = next(f for f in r2["findings"] if f["id"] == self.f3)
        f3["status"], f3["note"] = "waived", "Dave: not worth it"
        self.s.step(1, "design")
        self.assertEqual(("ready", "stale"), (self.st("review_design")["name"], self.st("review_design")["reason"]))

    def test_7_card_lists_open_findings_and_closed_ones_apart(self):
        self.setup_rounds()
        prev = previous(fake_session(), self.res(), "review_design", {})
        self.assertEqual([self.f2], [f["id"] for f in prev["findings"]])
        self.assertEqual({self.f1: "resolved", self.f3: "waived"}, {f["id"]: f["status"] for f in prev["resolved"]})
        for f in prev["resolved"]:
            self.assertEqual({"id", "status", "text"}, set(f))

    def test_7_restated_resolved_is_a_no_op(self):
        self.setup_rounds()
        r = self.review("review_design", [{"id": self.f1, "status": "resolved"}, {"id": self.f2, "status": "resolved"},
                                          {"id": self.f3, "status": "resolved"}])
        self.assertEqual([(self.f2, "resolved")], [(f["id"], f["status"]) for f in r["findings"]])

    def test_7_restated_open_for_a_closed_id_is_refused(self):
        self.setup_rounds()
        e = self.refused("review_design", [{"id": self.f1, "status": "open"}, {"id": self.f2, "status": "resolved"}],
                         decision="changes_requested")
        self.assertEqual("validation", e.code)
        self.assertIn("already resolved", e.message)
        self.assertIn(self.f1, e.message)
        self.assertIn("follows", e.hint or "")
        e = self.refused("review_design", [{"id": self.f3, "status": "open"}, {"id": self.f2, "status": "resolved"}],
                         decision="changes_requested")
        self.assertIn("already waived", e.message)

    def test_7_unknown_id_lists_the_ids_that_need_a_status(self):
        self.setup_rounds()
        e = self.refused("review_design", [{"id": "review_design:9:9", "status": "resolved"},
                                           {"id": self.f2, "status": "resolved"}])
        self.assertIn("unknown finding ids", e.message)
        self.assertEqual([self.f2], e.details.get("needs_status"))


# --------------------------------------------------------------------------------------------- 9, 9a: follows rules


class FollowsRuleTests(SimBase):
    def impl_finding(self, text="rename x", target=None):
        self.s.goal(1)
        self.to("review_impl")
        f = {"text": text}
        if target:
            f["target"] = target
        self.review("review_impl", [f])
        return "review_impl:1:1"

    def rerun_review(self, fid, response="fixed: done"):
        """The target answers fid; run_tests re-runs; review_impl becomes ready again."""
        target = next(f for f in self.s.docs[1]["records"]["review_impl"]["findings"] if f["id"] == fid)["target"]
        self.s.step(1, target, responses={fid: response}, **({"same": True} if response.startswith("disputed") else {}))
        self.to("review_impl")

    def test_9_follows_is_refused_for_an_unknown_or_open_id_and_on_a_non_review_node(self):
        fid = self.impl_finding()
        self.rerun_review(fid)
        e = self.refused("review_impl", [{"id": fid, "status": "resolved"},
                                         {"text": "rest", "follows": "review_design:1:1"}], "changes_requested")
        self.assertIn("is not a finding of review_impl's previous review", e.message)
        e = self.refused("review_impl", [{"id": fid, "status": "open"}, {"text": "rest", "follows": fid}],
                         "changes_requested")
        self.assertIn("still open", e.message)
        # a non-review node's finding with `follows` is refused
        s2 = Sim()
        s2.goal(1)
        for _ in range(40):
            if s2.st(1, "test_design")["name"] == "ready":
                break
            s2.step(1, [n for n in s2.actionable(1) if n != "test_design"][0])
        s2.start(1, "test_design")
        with self.assertRaises(Refused):
            s2.submit(1, "test_design", findings=[{"target": "design", "text": "x", "follows": "review_design:1:1"}])

    def test_9_follows_inherits_target_and_rounds_never_upheld(self):
        fid = self.impl_finding("add an edge test", target="test_design")
        self.rerun_review(fid)
        r = self.review("review_impl", [{"id": fid, "status": "resolved"}, {"text": "still one case", "follows": fid}],
                        "changes_requested")
        g = next(f for f in r["findings"] if f["id"] == "review_impl:2:1")
        self.assertEqual((fid, "test_design", 1, False), (g["follows"], g["target"], g["rounds"], g["upheld"]))
        self.assertEqual([], schemas.validate_finding(g))

    def test_9_a_disputed_finding_followed_keeps_its_dispute_count(self):
        fid = self.impl_finding()
        self.rerun_review(fid, "disputed: x is the domain term")
        r = self.review("review_impl", [{"id": fid, "status": "resolved"}, {"text": "rename y", "follows": fid}],
                        "changes_requested")
        g = next(f for f in r["findings"] if f["id"] == "review_impl:2:1")
        self.assertEqual((2, False, "implement"), (g["rounds"], g["upheld"], g["target"]))
        st = self.st("implement")
        self.assertEqual(("needs_human", "dispute"), (st["name"], st["kind"]))

    def test_9_a_different_target_starts_at_round_one(self):
        fid = self.impl_finding()
        self.rerun_review(fid, "disputed: x is the domain term")
        r = self.review("review_impl", [{"id": fid, "status": "resolved"},
                                        {"target": "test_design", "text": "test it", "follows": fid}],
                        "changes_requested")
        g = next(f for f in r["findings"] if f["id"] == "review_impl:2:1")
        self.assertEqual(("test_design", 1), (g["target"], g["rounds"]))

    def test_9_two_new_findings_may_follow_one(self):
        fid = self.impl_finding()
        self.rerun_review(fid)
        r = self.review("review_impl", [{"id": fid, "status": "resolved"}, {"text": "half a", "follows": fid},
                                        {"text": "half b", "follows": fid}], "changes_requested")
        self.assertEqual([fid, fid], [f.get("follows") for f in r["findings"] if f["status"] == "open"])

    def test_9a_following_an_upheld_finding_is_disputable_and_escalates_at_once(self):
        fid = self.impl_finding()
        self.rerun_review(fid, "disputed: x is the domain term")
        self.review("review_impl", [{"id": fid, "status": "open"}], "changes_requested")
        self.assertEqual("dispute", self.st("implement").get("kind"))
        f = next(f for f in self.s.docs[1]["records"]["review_impl"]["findings"] if f["id"] == fid)
        f["upheld"] = True                                                  # the human upholds F (answer verb)
        self.assertEqual(("ready", "reopened"), (self.st("implement")["name"], self.st("implement")["reason"]))
        self.rerun_review(fid, "fixed: renamed")
        r = self.review("review_impl", [{"id": fid, "status": "resolved"}, {"text": "and rename z", "follows": fid}],
                        "changes_requested")
        g = next(x for x in r["findings"] if x.get("follows") == fid)
        self.assertFalse(g["upheld"])
        self.assertGreaterEqual(g["rounds"], 2)
        st = self.st("implement")
        self.assertEqual(("needs_human", "dispute"), (st["name"], st["kind"]))
        self.assertEqual([g["id"]], [x["id"] for _, x in st["escalated"]])
        self.assertEqual("and rename z", st["escalated"][0][1]["text"])
        rec.check_responses({g["id"]: "disputed: z is right"}, [g])          # disputable
        upheld = dict(g, upheld=True)
        with self.assertRaises(Refused):
            rec.check_responses({g["id"]: "disputed: z is right"}, [upheld])

    def test_9a_follow_up_of_a_never_disputed_finding_waits_for_a_dispute(self):
        fid = self.impl_finding()
        self.rerun_review(fid)
        r = self.review("review_impl", [{"id": fid, "status": "resolved"}, {"text": "rest", "follows": fid}],
                        "changes_requested")
        g = next(x for x in r["findings"] if x.get("follows") == fid)
        self.assertEqual(1, g["rounds"])
        self.assertEqual(("ready", "reopened"), (self.st("implement")["name"], self.st("implement")["reason"]))


# --------------------------------------------------------------------------------------------- CLI journeys


class EditCarryJourney(Journey):
    def tip(self, g):
        return self.show(g)["goal_commit"]

    def changes_requested(self, g, texts):
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "Design."}, artifact="# Design\n")
        self.review(self.B, g, "review_design", "changes_requested", [{"text": t} for t in texts])

    def test_1_edit_previews_carried_findings_and_the_target_answers_them(self):
        g = self.goal()
        self.changes_requested(g, ["missing risks", "no rollback"])
        ids = ["review_design:1:1", "review_design:1:2"]
        dry = self.w.ok("a", "edit", str(g), "--set", 'spec="a new spec"')
        carried = dry["carried_findings"]
        self.assertEqual(ids, [x["id"] for x in carried])
        for i, x in enumerate(carried):
            self.assertEqual((g, "review_design", "design"), (x["goal"], x["from"], x["target"]))
            self.assertLessEqual(len(x["text"]), 120)
            self.assertIn(f"records.review_design.findings[{i}].status=\"waived\"", x["waive"])
            self.assertIn(f"records.review_design.findings[{i}].note=", x["waive"])
        out = self.w.ok("a", "edit", str(g), "--set", 'spec="a new spec"', "--base", self.tip(g))
        self.assertEqual(ids, [x["id"] for x in out["carried_findings"]])
        self.assertIn("carried_findings", out.get("warning", ""))
        self.assertIn("2 open finding", out.get("warning", ""))
        c = self.A.start(g, self.n("design"))
        self.assertEqual(ids, [x["id"] for x in c["corrections"]])
        self.assertTrue(all(x.get("stale_review") is True for x in c["corrections"]), c["corrections"])
        self.assertIn("stale_review", c["output_schema"]["responses"])
        rc, err = self.A.submit(g, self.n("design"), c, {"summary": "Design 2."}, artifact="# Design 2\n", ok=False)
        self.assertEqual("validation", err["error"]["code"])
        self.assertEqual(ids, [x["id"] for x in err["error"]["details"]["respond_to"]])
        self.A.submit(g, self.n("design"), c, {"summary": "Design 2.", "responses": {
            ids[0]: "fixed: added the risks", ids[1]: "disputed: the spec edit removed rollback"}}, artifact="# D2\n")
        # test 4: the carry ends with the target's new output; next offers the review, not design
        out = self.w.ok("b", "next", "--goal", str(g))
        nodes = [a["node"] for a in out["actions"]]
        self.assertIn(self.n("review_design"), nodes)
        self.assertNotIn(self.n("design"), nodes)
        c = self.B.start(g, self.n("review_design"))
        prev = {f["id"]: f["response"] for f in c["previous"]["findings"]}
        self.assertEqual({ids[0]: "fixed: added the risks", ids[1]: "disputed: the spec edit removed rollback"}, prev)

    def test_2_waiving_in_the_same_edit_carries_nothing(self):
        g = self.goal()
        self.changes_requested(g, ["missing risks"])
        dry = self.w.ok("a", "edit", str(g), "--set", 'spec="a new spec"')
        waive = shlex.split(dry["carried_findings"][0]["waive"])
        waive = [w.replace("<who waived it, and why>", "Dave: the new spec drops this") for w in waive]
        out = self.w.ok("a", "edit", str(g), "--set", 'spec="a new spec"', *waive, "--base", self.tip(g))
        self.assertEqual([], out["carried_findings"])
        self.assertNotIn("carried_findings", out.get("warning", ""))
        c = self.A.start(g, self.n("design"))
        self.assertEqual([], c["corrections"])


class RoundTwoCardTests(Journey):
    def test_7_and_12_round_two_review_card_lists_resolved_apart_and_fits(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "Design."}, artifact="# Design\n")
        self.review(self.B, g, "review_design", "changes_requested", [{"text": "F1 missing risks"}])
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D2.", "responses": {"review_design:1:1": "fixed: added"}},
                      artifact="# D2\n")
        self.review(self.B, g, "review_design", "changes_requested", [{"text": "F2 no rollback"}])
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D3.", "responses": {"review_design:2:1": "fixed: added"}},
                      artifact="# D3\n")
        c = self.B.start(g, self.n("review_design"))
        self.assertEqual(["review_design:2:1"], [f["id"] for f in c["previous"]["findings"]])
        self.assertEqual([{"id": "review_design:1:1", "status": "resolved", "text": "F1 missing risks"}],
                         c["previous"]["resolved"])
        self.assertIn("previous.resolved", c["output_schema"]["findings"])
        from engine.card import shrink_candidates
        self.assertTrue(len(canonical(c)) <= 4096 or not shrink_candidates(c), len(canonical(c)))
        # a restated `resolved` for the closed id is accepted
        out = {"decision": "approved", "summary": "ok", "findings": [
            {"id": "review_design:1:1", "status": "resolved"}, {"id": "review_design:2:1", "status": "resolved"}]}
        self.B.submit(g, self.n("review_design"), c, out, artifact="# ok\n")


class FollowsJourney(Journey):
    settings = None

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.m = {n: n for n in fx.DEFAULT_NODES}
        self.w.bootstrap(workflow=fx.stub_ops_workflow(), settings=self.settings)
        self.A = fx.Agent(self.w, "a", "claude:aaaa/w-1")
        self.B = fx.Agent(self.w, "b", "codex:bbbb/w-2")

    def first_round(self, g):
        c = self.A.start(g, "design")
        self.A.submit(g, "design", c, {"summary": "Design."}, artifact="# Design\n")
        self.review(self.B, g, "review_design", "changes_requested", [{"text": "F1: risks and rollback are missing"}])
        c = self.A.start(g, "design")
        self.A.submit(g, "design", c, {"summary": "D2.", "responses": {"review_design:1:1": "fixed: added risks"}},
                      artifact="# D2\n")
        return self.B.start(g, "review_design")

    def follow_up(self):
        return {"decision": "changes_requested", "summary": "half done", "findings": [
            {"id": "review_design:1:1", "status": "resolved"},
            {"text": "the rollback half is still missing", "follows": "review_design:1:1"}]}


class FollowsGateTests(FollowsJourney):
    def test_9b_follows_is_refused_until_the_policy_requires_the_capability(self):
        g = self.goal()
        c = self.first_round(g)
        self.assertNotIn("follows", c["output_schema"]["findings"])
        rc, err = self.B.submit(g, "review_design", c, self.follow_up(), artifact="# r\n", ok=False)
        self.assertEqual("validation", err["error"]["code"], err)
        msg = err["error"]["message"]
        if G1027_MERGED:
            self.assertIn("finding_follows", msg)
        else:
            self.assertTrue("finding_follows" in msg or "engine.min" in msg, msg)

    def test_9b_capability_form_matches_the_merge_order(self):
        if G1027_MERGED:
            self.assertTrue((CAPS_DIR / "finding_follows.txt").is_file())
            src = (fx.ROOT / ".agents" / "test_engine_capabilities.py").read_text(encoding="utf-8")
            self.assertIn('"finding_follows"', src)
        else:
            self.assertGreater(vtuple(ENGINE_VERSION), (1, 1, 0))         # the next minor ships the key


class FollowsRoundTripTests(FollowsJourney):
    settings = follows_settings()

    def test_8_follows_is_stored_shown_and_listed(self):
        g = self.goal()
        c = self.first_round(g)
        self.assertIn("follows", c["output_schema"]["findings"])          # mentioned once it is required
        self.B.submit(g, "review_design", c, self.follow_up(), artifact="# r\n")
        doc = self.show(g)["goal"]
        new = next(f for f in doc["records"]["review_design"]["findings"] if f["id"] == "review_design:2:1")
        self.assertEqual(("review_design:1:1", "design", False), (new["follows"], new["target"], new["upheld"]))
        self.assertEqual([], schemas.validate_finding(new))
        c = self.A.start(g, "design")
        corr = c["corrections"][0]
        self.assertEqual(("review_design:2:1", "review_design:1:1"), (corr["id"], corr["follows"]))
        self.assertEqual("F1: risks and rollback are missing", corr["follows_text"])
        self.A.submit(g, "design", c, {"summary": "D3.", "responses": {"review_design:2:1": "fixed: rollback"}},
                      artifact="# D3\n")
        c = self.B.start(g, "review_design")
        entry = next(f for f in c["previous"]["findings"] if f["id"] == "review_design:2:1")
        self.assertEqual("review_design:1:1", entry["follows"])
        self.B.submit(g, "review_design", c, {"decision": "approved", "summary": "ok",
                                              "findings": [{"id": "review_design:2:1", "status": "resolved"}]},
                      artifact="# ok\n")
        item = self.item(self.w.ok("a", "next", "--goal", str(g)), "approve_design")
        self.assertIn("follows: review_design:2:1 ← review_design:1:1", item["facts"])


# --------------------------------------------------------------------------------------------- 10, 11: --repo


class RepoFlagTests(Journey):
    def outside(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def assert_repo(self, cmd, clone="a"):
        argv = cmd["argv"]
        self.assertEqual("--repo", argv[-2], argv)
        self.assertTrue(same_dir(self.w.clones[clone].path, argv[-1]), argv)
        self.assertTrue(cmd["command"].endswith("--repo " + shlex.quote(argv[-1])), cmd["command"])

    def test_10_card_commands_run_from_outside_the_repository(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        away = self.outside()
        out = self.w.ok("a", *c["commands"]["renew"]["argv"], cwd=away)
        self.assertTrue(out["ok"])
        with open(os.path.join(away, "out.json"), "w") as fh:
            json.dump({"summary": "Design from elsewhere."}, fh)
        with open(os.path.join(away, "art.md"), "w") as fh:
            fh.write("# Design\n")
        argv = [{"<F>": "out.json", "<A>": "art.md"}.get(a, a) for a in c["commands"]["submit"]["argv"]]
        out = self.w.ok("a", *argv, cwd=away)                               # relative --output: the caller's dir
        self.assertTrue(out["ok"])
        self.assertEqual("Design from elsewhere.",
                         self.show(g)["goal"]["records"][self.n("design")]["output"]["summary"])

    def test_10_a_linked_worktree_works_as_repo(self):
        self.goal()
        wt = os.path.join(self.tmp, "linked")
        self.w.clones["a"].git("worktree", "add", "-q", "--detach", wt)
        out = self.w.ok("a", "next", "--repo", wt, cwd=self.outside())
        self.assertTrue(out["ok"])

    def test_10_errors_name_the_directory_and_the_flag(self):
        away = self.outside()
        rc, err = self.w.run("a", "next", cwd=away)
        self.assertEqual("environment", err["error"]["code"], err)
        self.assertIn(os.path.realpath(away), os.path.realpath(err["error"]["message"].split(": ", 1)[-1].strip()))
        self.assertIn("--repo", err["error"].get("hint", ""))
        rc, err = self.w.run("a", "next", "--repo", away, cwd=away)
        self.assertEqual("environment", err["error"]["code"], err)
        self.assertIn("--repo", err["error"]["message"])
        self.assertIn("is not inside a Git repository", err["error"]["message"])

    def test_11_worker_commands_carry_repo_and_next_does_not(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        for k in ("submit", "blocked", "renew", "abandon"):
            with self.subTest(command=k):
                self.assert_repo(c["commands"][k])
        out = self.w.ok("a", "abandon", str(g), self.n("design"), "--attempt", "1")
        self.assert_repo(out["restart"])
        nxt = self.w.ok("a", "next")
        self.assertNotIn("--repo", json.dumps(nxt["actions"]))
        self.assertTrue(nxt["actions"])


# --------------------------------------------------------------------------------------------- 13: docs


class DocsTests(unittest.TestCase):
    def read(self, rel):
        return (fx.ROOT / rel).read_text(encoding="utf-8")

    def test_13_contract_docs_carry_the_amendment(self):
        spec = self.read("docs/design/SPEC.md")
        for term in ("stale_review", "carried_findings", "previous.resolved", "follows", "follows_text",
                     "already resolved", "--repo", "finding_follows"):
            with self.subTest(term=term):
                self.assertIn(term, spec)
        history = self.read("docs/design/HISTORY.md").split("## 4.", 1)[1]
        self.assertTrue(re.search(r"^\| G1028 \|", history, re.M), "HISTORY §4 has no G1028 row")
        readme = self.read("docs/design/README.md")
        self.assertFalse(re.search(r"^\| G1028\b", readme, re.M), "README still lists G1028 as pending")

    def test_13_cli_usage_lists_repo_and_follows(self):
        usage = self.read("plugins/zzzops/zzzops/references/CLI_USAGE.md")
        self.assertIn("--repo", usage)
        self.assertIn("follows", usage)
        self.assertIn("carried_findings", usage)


if __name__ == "__main__":
    unittest.main()
