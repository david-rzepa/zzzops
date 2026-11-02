"""G1040 design revision 2: held outputs, truthful refusals, and op failure identity.

Pure checks exercise the real record writer and frontier; two shipped-graph CLI journeys
pin the public cards/submission contract. Existing G1026 fixtures stay capability-off.
No production implementation or frozen-test edits belong in this file.
"""
from __future__ import annotations

import copy
import json
import types
import unittest
from unittest.mock import patch

import engine_fixtures as fx
from engine_sim import Sim
from engine import card, records as rec, render, schemas, verbs
from engine.errors import Refused
import test_engine_owner_questions as oq
import test_engine_review_lenses as rl
import test_engine_schemas as schema_tests

CAP = "blocked_findings"
PAIR = "that no entry in `human_decisions` answers"


def to(s, node):
    for _ in range(100):
        st = s.st(1, node)
        if st["name"] in ("ready", "needs_human"):
            return st
        acts = [n for n in s.actionable(1) if n != node]
        if not acts:
            raise AssertionError(s.names(1))
        s.step(1, acts[0])
    raise AssertionError("did not reach " + node)


def sim(cap=True, shipped=False):
    s = Sim(workflow=rl.shipped("workflow.json") if shipped else None,
            policy=rl.shipped("POLICY.json") if shipped else None)
    if cap:
        s.settings["engine"] = {"requires": [CAP]}
    s.goal(1)
    return s


def block(s, node="design", waiting_for="agent"):
    """Use verbs.blocked_record, not Sim's older block implementation.

    Only filesystem sync is stubbed; output retention and its capability check run
    in production code. The returned record is then evaluated by the pure frontier.
    """
    L = s.start(1, node)
    L.prompt = None
    res = s.eval().goals[1]
    session = types.SimpleNamespace(settings=s.settings, now=s.now, git=None, snap=None)
    b = {"waiting_for": waiting_for}
    b["question" if waiting_for == "human" else "instructions"] = "Choose A or B" if waiting_for == "human" else "retry"
    with patch("engine.verbs.wt.sync", return_value="same"):
        r = verbs.blocked_record(session, res, s.docs[1], node, L,
                                 s.docs[1]["records"].get(node), b, None, {})
    s.leases.pop((1, node))
    s.docs[1]["records"][node] = r
    s.tick()
    return r


def corrections(s, node="design"):
    res = s.eval().goals[1]
    return [card.correction(res, f) for _, f in res.live.get(node, [])]


def review(s, node="review_design", findings=None):
    to(s, node)
    s.start(1, node)
    return s.submit(1, node, findings=findings or [{"text": "ordinary defect"}])


def refusal(s, node, responses):
    """Run submit's actual early validation with a minimal session (no Git needed)."""
    res = s.eval().goals[1]
    session = types.SimpleNamespace(settings=s.settings, ctx=lambda: types.SimpleNamespace(reader=render.Reader()))
    out = {"summary": "revision", "responses": responses}
    try:
        verbs.done_record(session, res, s.docs[1], node, None,
                          s.docs[1]["records"].get(node), out, None, None, {})
    except Refused as e:
        return e
    raise AssertionError("submission unexpectedly accepted")


class HeldOutputTests(unittest.TestCase):
    def test_block_retains_the_replaced_output_only_when_required(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                s = sim(enabled)
                review(s)
                old = copy.deepcopy(s.docs[1]["records"]["design"]["output"])
                r = block(s)
                self.assertIsNone(r["output"])
                if enabled:
                    self.assertEqual(old, r.get("last_output"))
                    self.assertEqual(["review_design:1:1"], [c["id"] for c in corrections(s)])
                    self.assertNotIn("review_design", s.eval().goals[1].stale)
                    self.assertNotIn("stale_review", corrections(s)[0])
                else:
                    self.assertNotIn("last_output", r)
                    self.assertEqual([], corrections(s))

    def test_second_block_copies_the_same_held_output(self):
        s = sim()
        review(s)
        old = copy.deepcopy(s.docs[1]["records"]["design"]["output"])
        block(s)
        r = block(s)
        self.assertEqual(old, r.get("last_output"))
        self.assertEqual(["review_design:1:1"], [c["id"] for c in corrections(s)])

    def test_carrier_and_filter_are_fresh_but_consumers_still_wait(self):
        s = sim(shipped=True)
        to(s, "review_design")
        s.start(1, "review_design")
        s.submit(1, "review_design", findings=[rl.tag("owner question: choose A or B", True, "intent"),
                                               rl.tag("ordinary defect", False, "truth")])
        to(s, "filter_design")
        s.step(1, "filter_design", outputs={"summary": "keep", "verdicts": {
            "review_design:1:2": {"verdict": "keep", "reason": "blocks the user"}}})
        block(s)
        res = s.eval().goals[1]
        self.assertEqual(2, len(corrections(s)))
        self.assertFalse({"review_design", "filter_design"} & res.stale)
        self.assertTrue(all("stale_review" not in c for c in corrections(s)))
        self.assertEqual("blocked", res.st["review_design"]["name"])
        self.assertEqual("blocked", res.st["filter_design"]["name"])
        self.assertNotIn("made it moot", card.output_schema(res.graph, "design",
                         dict(res.st["design"], corrections=corrections(s))).get("responses", ""))
        self.assertEqual([], verbs.carried_findings(s.eval(), [1]))

    def test_spec_edit_makes_held_carrier_genuinely_stale_and_carried(self):
        s = sim()
        review(s)
        block(s, waiting_for="human")
        s.docs[1]["spec"] += " changed"
        res = s.eval().goals[1]
        self.assertIn("review_design", res.stale)
        cs = corrections(s)
        self.assertEqual(1, len(cs))
        [c] = cs
        self.assertTrue(c.get("stale_review"))
        self.assertEqual([c["id"]], [f["id"] for f in verbs.carried_findings(s.eval(), [1])])
        self.assertEqual(("ready", "stale"), (res.st["design"]["name"], res.st["design"].get("reason")))
        block(s, waiting_for="human")
        self.assertEqual("blocked", s.st(1, "design").get("kind"))
        self.assertEqual("needs_human", s.st(1, "design")["name"])

    def test_unread_edit_does_not_mark_fresh_findings_carried(self):
        s = sim()
        review(s)
        block(s)
        s.docs[1]["links"] = {"issue": "https://example.test/issue/1"}
        self.assertEqual([], verbs.carried_findings(s.eval(), [1]))
        cs = corrections(s)
        self.assertEqual(1, len(cs))
        self.assertNotIn("stale_review", cs[0])

    def test_answered_old_finding_never_resurrects_after_later_block(self):
        s = sim()
        review(s, "review_tests", [{"target": "design", "text": "old defect"}])
        old_fid = "review_tests:1:1"
        s.step(1, "design", responses={old_fid: "fixed: first revision"})
        review(s, findings=[{"text": "new owner question"}])
        new_fid = s.docs[1]["records"]["review_design"]["findings"][-1]["id"]
        block(s)
        self.assertEqual([new_fid], [c["id"] for c in corrections(s)])
        self.assertNotIn(old_fid, [c["id"] for c in corrections(s)])

    def test_consumer_of_older_output_stays_stale_and_finding_dead(self):
        s = sim()
        review(s)
        s.step(1, "design", responses={"review_design:1:1": "fixed: B"})
        b = copy.deepcopy(s.docs[1]["records"]["design"]["output"])
        s.reopen(1, "design", "block before new review")
        block(s)
        self.assertEqual(b, s.docs[1]["records"]["design"].get("last_output"))
        self.assertIn("review_design", s.eval().goals[1].stale)
        self.assertNotIn("review_design:1:1", [c["id"] for c in corrections(s)])

    def test_fresh_op_failure_survives_implement_block_only_with_capability(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                s = sim(enabled)
                to(s, "run_tests")
                s.op(1, "run_tests", ok=False, raised=[{"key": "failed", "input": "code", "text": "FAIL alpha"}])
                block(s, "implement")
                cs = corrections(s, "implement")
                self.assertEqual(["run_tests:failed"] if enabled else [], [c["id"] for c in cs])
                if enabled:
                    self.assertNotIn("run_tests", s.eval().goals[1].stale)
                    self.assertNotIn("stale_review", cs[0])

    def test_op_wait_has_no_held_output(self):
        from engine.ops.run import Blocked, finish
        s = sim()
        to(s, "run_tests")
        s.op(1, "run_tests")
        s.reopen(1, "run_tests")
        L = s.start(1, "run_tests")
        session = types.SimpleNamespace(settings=s.settings, now=s.now, portfolio=s.eval)
        saved = {}

        def write_goals(verb, goals, mutate, extra, **kwargs):
            saved.update(mutate(session, s.docs))
            return "updated", {}, []

        session.write_goals = write_goals
        wait = Blocked({"category": "external", "waiting_for": "time", "reason": "CI pending",
                        "retry_after": "2026-11-02T23:00:00Z"})
        ctx = types.SimpleNamespace(node_def=s.graph(1).nodes["run_tests"])
        with patch("engine.verbs.valid_lease", return_value=L), patch("engine.verbs.finish_output"):
            finish(session, 1, "run_tests", L.holder, {"attempt": L.attempt}, wait, None, ctx)
        self.assertEqual("blocked", saved[1]["records"]["run_tests"]["status"])
        self.assertNotIn("last_output", saved[1]["records"]["run_tests"])


class HeldSchemaTests(unittest.TestCase):
    def test_last_output_is_an_object_on_blocked_agent_records_only(self):
        r = schema_tests.record(status="blocked", ok=False, output=None, last_output={"summary": "old"},
                blocked={"category": "decision", "waiting_for": "agent", "instructions": "retry", "reason": "retry"})
        self.assertEqual([], schemas.validate_record(r))
        for value in (None, "old", [], 3):
            with self.subTest(value=value):
                self.assertTrue(schemas.validate_record(dict(r, last_output=value)))
        done = dict(r, status="done", ok=True, output={"summary": "new"})
        done.pop("blocked")
        self.assertTrue(schemas.validate_record(done))
        s = sim()
        doc = schema_tests.default_goal(records={"run_tests": r})
        errors, _ = schemas.validate_goal(doc, workflow=s.workflow)
        self.assertTrue(errors, "an op record must never store last_output")

    def test_capability_is_shipped_and_pinned_without_enabling_template(self):
        path = fx.PLUGIN_CODE / "engine" / "capabilities" / (CAP + ".txt")
        self.assertTrue(path.is_file())
        import test_engine_capabilities as caps
        self.assertIn(CAP, caps.SHIPPED)
        self.assertNotIn(CAP, rl.shipped("POLICY.json")["settings"]["engine"].get("requires", []))


class ResponseRefusalTests(unittest.TestCase):
    def test_reason_codes_come_from_the_actual_submit_path(self):
        # Each stale-response reason is tested without a round trip to Git.
        for why in ("superseded", "resolved", "waived", "other_target", "target_blocked", "target_changed", "not_live"):
            with self.subTest(why=why):
                s = sim(False)
                review(s)
                f = s.docs[1]["records"]["review_design"]["findings"][0]
                fid = f["id"]
                if why == "superseded":
                    s.docs[1]["records"]["review_design"]["findings"] = []
                elif why in ("resolved", "waived"):
                    f["status"] = why
                elif why == "other_target":
                    f["target"] = "test_design"
                elif why == "target_blocked":
                    block(s)
                elif why == "target_changed":
                    s.step(1, "design", responses={fid: "fixed: changed"})
                else:
                    # An op carrier is not carried when its own policy inputs change.
                    s = sim(False)
                    to(s, "run_tests")
                    s.op(1, "run_tests", ok=False, raised=[{"key": "failed", "input": "code", "text": "failure"}])
                    fid = "run_tests:failed"
                    s.settings["verification"]["commands"] = ["changed command"]
                node = "implement" if why == "not_live" else "design"
                e = refusal(s, node, {fid: "fixed: stale response"})
                self.assertEqual([fid], e.details.get("no_longer_live"))
                self.assertEqual({fid: why}, e.details.get("why"))
                self.assertIn("Drop", e.hint or "")
                self.assertNotIn("arrived while you ran", e.hint or "")

    def test_missing_response_hint_is_separate_from_drop_hint(self):
        s = sim(False)
        review(s)
        e = refusal(s, "design", {})
        self.assertEqual(["review_design:1:1"], [f["id"] for f in e.details["respond_to"]])
        self.assertIn("Answer each", e.hint or "")
        self.assertNotIn("arrived while you ran", e.hint or "")


class OpRecurrenceTests(unittest.TestCase):
    def failure(self, s, text):
        to(s, "run_tests")
        r = s.op(1, "run_tests", ok=False, raised=[{"key": "failed", "input": "code", "text": text}])
        return r["findings"][0]

    def test_different_failure_is_new_then_equivalent_failure_escalates_with_response(self):
        s = sim()
        self.failure(s, "FAIL: test_alpha")
        s.step(1, "implement", responses={"run_tests:failed": "fixed: alpha"})
        b = "FAIL: test_beta Ran 12 in 1.234s abcdef123 <Repo object at 0x7f3a9c0d1e20> /tmp/tmpk3j_9x2a/ zzzops-card-budget-ab12cd_e/"
        f = self.failure(s, b)
        self.assertEqual(1, f["rounds"])
        self.assertFalse(f["upheld"])
        self.assertEqual(("ready", "reopened"), (s.st(1, "implement")["name"], s.st(1, "implement").get("reason")))
        answer = "fixed: repaired beta's command"
        s.step(1, "implement", responses={"run_tests:failed": answer})
        bp = "FAIL: test_beta Ran 99 in 9.876s fedcba987 <Repo object at 0x7f00aa11bb22> /tmp/tmpzz8_q1w0/ zzzops-card-budget-q9w8e7r6/"
        f = self.failure(s, bp)
        self.assertEqual(2, f["rounds"])
        self.assertEqual(answer, f["response"])
        res = s.eval().goals[1]
        self.assertEqual("dispute", res.st["implement"].get("kind"))
        ctx = render.Ctx("zzzops", s.now, s.settings, {})
        self.assertIn(answer, render.dispute_item(ctx, res, "implement", True)["question"])
        # Historical findings with response=None still show the target's real response.
        f["response"] = None
        self.assertIn(answer, render.dispute_item(ctx, s.eval().goals[1], "implement", True)["question"])

    def test_normalization_covers_all_five_token_kinds_without_merging_test_names(self):
        norm = getattr(rec, "norm", None)
        self.assertIsNotNone(norm, "the design's op-failure normalizer is missing")
        for a, b in [("Ran 12 in 1.234s", "Ran 99 in 9.876s"),
                     ("head=abcdef123!", "head=fedcba987!"),
                     ("at 0x7f3a9c0d1e20", "at 0X7F00AA11BB22"),
                     ("/tmp/tmpk3j_9x2a/", "/tmp/tmpzz8_q1w0/"),
                     ("zzzops-card-budget-ab12cd_e/", "zzzops-card-budget-q9w8e7r6/"),
                     (".zzzops-cleanup-ab12cd_e.tmp", ".zzzops-cleanup-q9w8e7r6.tmp")]:
            with self.subTest(a=a):
                self.assertEqual(norm(a), norm(b))
        self.assertNotEqual(norm("FAIL: test_alpha"), norm("FAIL: test_beta"))
        self.assertNotEqual(norm("python test.py"), norm("node test.js"))

    def test_upheld_follows_only_the_same_failure(self):
        for same in (False, True):
            with self.subTest(same=same):
                s = sim()
                f = self.failure(s, "FAIL: alpha 12")
                f["upheld"] = True
                s.step(1, "implement", responses={f["id"]: "fixed: tried"})
                f2 = self.failure(s, "FAIL: alpha 99" if same else "FAIL: beta 99")
                self.assertEqual(same, f2["upheld"])
                self.assertEqual(2 if same else 1, f2["rounds"])


class CapabilityJourneyTests(oq.OwnerWorld):
    """One public CLI acceptance journey, on the actual shipped graph and records."""
    def bootstrap(self):
        p = rl.policy_with_intent()
        p["settings"]["engine"] = {"requires": [CAP]}
        self.w.bootstrap(policy=p, workflow=rl.shipped("workflow.json"), prompts=False)
        self.push_prompts(fx.SHIPPED)

    def test_owner_round_retry_card_requires_all_findings_then_review_sees_answer(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["design"] == "current")
        self.p.run(g, "review_design", findings=[oq.owner_finding(), rl.tag("ordinary defect", True, "truth")])
        fids = self.open_ids(g, "review_design")
        self.p.drive(g, lambda st: st["filter_design"].startswith("ready"))
        self.p.run(g, "filter_design")
        old = copy.deepcopy(self.p.record(g, "design")["output"])
        self.block(g, fids)
        self.assertEqual(old, self.p.record(g, "design").get("last_output"))
        self.answer_block(g)
        ag, c = self.p.start(g, "design")
        self.assertEqual(set(fids), {f["id"] for f in c["corrections"]})
        self.assertTrue(all(not f.get("stale_review") for f in c["corrections"]))
        self.assertNotIn("made it moot", c["output_schema"].get("responses", ""))
        out = self.p.output("design", c)
        out.pop("responses", None)
        rc, refused = ag.submit(g, "design", c, out, artifact="# design\n", ok=False)
        self.assertEqual(set(fids), {f["id"] for f in refused["error"]["details"]["respond_to"]})
        out["responses"] = {fid: "fixed: recorded as owner decision Q1" for fid in fids}
        ag.submit(g, "design", c, out, artifact="# design\n\n## Owner decisions\n\nGo with A: `human_decisions`.\n")
        rcard, _ = self.p.run(g, "review_design")
        self.assertTrue(oq.decisions_of(self.w, rcard["human_decisions"]))
        self.to_approve_design(g)
        self.assertTrue(self.p.item(g, "approve_design")["human_decisions"])


class StaleReplayTests(oq.OwnerWorld):
    def test_stale_test_design_card_keeps_two_findings_and_requires_responses(self):
        g = self.goal()
        self.until_ready(g, "review_tests")
        self.p.run(g, "review_tests", findings=[{"target": "test_design", "text": "edge A"},
                                               {"target": "test_design", "text": "edge B"}])
        fids = self.open_ids(g, "review_tests")
        self.w.ok("a", "reopen", str(g), "design", "--note", "design revision")
        self.p.run(g, "design")
        self.until_ready(g, "test_design")
        ag, c = self.p.start(g, "test_design")
        self.assertEqual(set(fids), {f["id"] for f in c["corrections"]})
        self.assertTrue(all(f.get("stale_review") for f in c["corrections"]))
        out = self.p.output("test_design", c)
        out.pop("responses", None)
        rc, refused = ag.submit(g, "test_design", c, out, ok=False)
        self.assertEqual(set(fids), {f["id"] for f in refused["error"]["details"]["respond_to"]})
        out["responses"] = {fid: "fixed: covered " + fid for fid in fids}
        ag.submit(g, "test_design", c, out)
        rcard, _ = self.p.run(g, "review_tests")
        prior = {f["id"]: f for f in rcard["previous"]["findings"]}
        self.assertTrue(all(prior[fid]["response"].startswith("fixed:") for fid in fids))


class ContractTests(unittest.TestCase):
    def test_docs_state_the_changed_contract(self):
        import test_design_docs as dd
        spec, design = dd.read_doc("SPEC.md"), dd.read_doc("DESIGN.md")
        for text, needles in [(spec, ("last_output", CAP, "details.why", "same normalized text", "0x", "tempfile")),
                              (design, ("last_output", "same normalized text"))]:
            for needle in needles:
                with self.subTest(needle=needle):
                    self.assertTrue(needle in text, "missing contract needle: " + needle)
        history = dd.section(dd.read_doc("HISTORY.md"), r"amendments after approval")
        self.assertTrue(any("G1040" in row for row in history.splitlines() if row.strip().startswith("|")))
        usage = (fx.PLUGIN_CODE / "references" / "CLI_USAGE.md").read_text()
        cap_path = fx.PLUGIN_CODE / "engine" / "capabilities" / (CAP + ".txt")
        for text in (spec, usage, cap_path.read_text() if cap_path.exists() else ""):
            self.assertIn("revised design step 4", text)

    def test_rollout_requires_the_paired_prompt_and_template_is_ready(self):
        self.assertTrue(PAIR in rl.prompt_text("design.md"), "template design prompt lacks answered-question exception")
        policy = json.loads((fx.ROOT / ".zzzops" / "POLICY.json").read_text())
        if CAP in policy["settings"]["engine"].get("requires", []):
            self.assertIn(PAIR, (fx.ROOT / ".zzzops" / "prompts" / "design.md").read_text())


if __name__ == "__main__":
    unittest.main()
