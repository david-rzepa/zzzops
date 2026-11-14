"""G1020: polish the lens prompts (design revision 2, tests 1-6), on the frozen 26-node template (`fx.GRAPH26`).

Written before the implementation. Contracts:

- The template `review` instruction tells code-stage lenses to target `test_design` for a problem in the tests;
  the sentence sits after the filter sentence and before "On a re-review".
- `lens_truth.md` has exactly one "On code:" sentence.
- A filtered lens may answer `approved` when its only open findings are notes (`material: false`); its submit
  outcome reads "approved with N note(s) → <targets>". An open finding is material unless it says
  `material: false`, so a prior finding without the key blocks `approved` ("approved requires no open material
  finding").
- Unfiltered reviews (`review_tests`) keep "approved requires no open findings".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

import engine_fixtures as fx
from test_engine_lenses import LENSES, LensWorld, lens_finding, push_goal_doc, shipped, verdict

SENTENCE = "On code, target `test_design` for a problem in the tests; `implement` cannot change them."
FILTER_SENTENCE = "An independent filter may promote a note; it never demotes a material finding."
TRUTH_ON_CODE = "On code: judge the diff against the approved design, and ask whether the tests check what it promises."


def prompt_text(name: str) -> str:
    return (fx.GRAPH26 / "prompts" / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------------- static template


class TemplateTextTests(unittest.TestCase):
    def test_review_instruction_targets_test_design_after_the_filter_sentence(self):
        text = shipped("POLICY.json")["instructions"]["review"]
        self.assertEqual(1, text.count(SENTENCE), text)
        self.assertLess(text.index(FILTER_SENTENCE), text.index(SENTENCE), text)
        self.assertLess(text.index(SENTENCE), text.index("On a re-review"), text)

    def test_lens_truth_has_one_on_code_sentence(self):
        text = prompt_text("lens_truth.md")
        self.assertEqual(1, text.count("On code:"), text)
        self.assertIn(TRUTH_ON_CODE, text)
        self.assertNotIn("On code: do the tests check what the design promises?", text)

    def test_other_lens_prompts_keep_their_single_on_code_line(self):
        for lens in LENSES:
            if lens == "truth":
                continue
            text = prompt_text(f"lens_{lens}.md")
            self.assertEqual(1, text.count("On code:"), lens)
            self.assertIn("On code: judge the diff against the approved design.", text, lens)
            self.assertNotIn("test_design", text, lens)        # the targeting sentence lives in the instruction

    def test_prompt_stats_check_passes(self):
        p = subprocess.run([sys.executable, str(fx.ROOT / ".agents" / "prompt_stats.py"), "--check"],
                           cwd=fx.ROOT, capture_output=True, text=True)
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)


# --------------------------------------------------------------------------------------------- world tests


class LensPolishWorld(LensWorld):
    def outcome(self, g) -> str:
        """The `Outcome:` trailer of the goal's tip commit."""
        tip = self.p.tip(g)
        self.w.seed.git("fetch", "-q", "origin", f"refs/heads/zzzops/goal/g{g}")
        msg = self.w.seed.git("show", "-s", "--format=%B", tip)
        return next(l[len("Outcome: "):] for l in msg.splitlines() if l.startswith("Outcome: "))

    def submit_lens(self, g, lens, decision, findings, summary="lens verdict", ok=True):
        ag, card = self.p.start(g, lens)
        out = {"decision": decision, "summary": summary, "findings": list(findings)}
        res = ag.submit(g, self.n(lens), card, out, artifact="# review\n", ok=ok)
        return ag, card, res

    def approve_with_note(self, g, lens, text, summary):
        self.submit_lens(g, lens, "approved", [lens_finding(text, False)], summary=summary)
        ids = self.lens_finding_ids(g, lens)
        self.assertEqual(1, len(ids))
        return ids[0]


class CodeLensCardTests(LensPolishWorld):
    """Test 1: code-stage lens cards carry the targeting sentence (inline or by blob)."""

    def review_instruction_matches(self, card, text):
        ins = card["instructions"]["review"]
        if "text" in ins:
            return SENTENCE in ins["text"]
        return ins["blob"] == self.w.seed.git("hash-object", "--stdin", input=text)

    def test_code_lens_cards_carry_the_test_design_sentence(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["truth_impl"].startswith("ready") and st["intent_impl"].startswith("ready"),
                     limit=200)
        self.w.seed.git("pull", "-q", "--ff-only", "origin", "dev")
        with open(os.path.join(self.w.seed.path, ".zzzops", "POLICY.json"), encoding="utf-8") as fh:
            policy = json.load(fh)
        text = policy["instructions"]["review"]
        self.assertIn(SENTENCE, text)
        held = []
        for lens in ("truth_impl", "intent_impl"):                  # a skippable and a non-skippable lens
            ag, card = self.p.start(g, lens, avoid=held)
            held.append(ag.label)
            self.assertIn("review", card["instructions"], lens)
            self.assertTrue(self.review_instruction_matches(card, text), (lens, card["instructions"]["review"]))
            self.assertIn("approve with notes", card["output_schema"]["decision"], lens)


class NotesOnlyApprovalTests(LensPolishWorld):
    def test_2_a_filtered_lens_approves_with_only_notes(self):
        g = self.goal()
        self.through_design(g)
        nid = self.approve_with_note(g, "truth_design", "a wording nit", "truth: approved with one note")
        r = self.p.record(g, "truth_design")
        self.assertEqual(("done", True, "approved"), (r["status"], r["ok"], r["output"]["decision"]))
        out = self.outcome(g)
        self.assertTrue(out.startswith("approved with 1 note"), out)
        self.assertNotIn("failed", out)
        self.assertIn(self.n("design"), out)
        self.lenses_done(g)
        ag, card = self.p.start(g, "filter_design")
        c = self.candidates_of(card)[nid]
        self.assertEqual((False, self.n("truth_design"), "a wording nit"), (c["material"], c["lens"], c["text"]))

    def test_2_two_notes_read_plural(self):
        g = self.goal()
        self.through_design(g)
        self.submit_lens(g, "simplicity_design", "approved",
                         [lens_finding("note one", False), lens_finding("note two", False)])
        out = self.outcome(g)
        self.assertTrue(out.startswith("approved with 2 notes"), out)

    def test_3_approved_with_a_material_finding_is_refused(self):
        g = self.goal()
        self.through_design(g)
        ag, card, (rc, err) = self.submit_lens(g, "truth_design", "approved", [lens_finding("a real bug", True)],
                                               ok=False)
        self.assertNotEqual(0, rc, err)
        self.assertEqual("validation", err["error"]["code"], err)
        self.assertIn("approved requires no open material finding", json.dumps(err))
        self.assertIsNone(self.p.record(g, "truth_design"))
        # a material finding with changes_requested is still accepted (the refused submit kept the lease)
        ag.submit(g, self.n("truth_design"), card, {"decision": "changes_requested", "summary": "a real bug",
                                                    "findings": [lens_finding("a real bug", True)]}, artifact="# r\n")

    def test_3_an_open_prior_finding_without_material_blocks_approved(self):
        g = self.goal()
        self.lenses_done(g, {"truth_design": [{"findings": [lens_finding("claims are untestable", True)]}]})
        fid = self.lens_finding_ids(g, "truth_design")[0]
        self.p.run(g, "filter_design")
        self.assertEqual("ready (reopened)", self.p.states(g)["design"])
        # an in-flight goal: the prior finding was recorded without `material`
        tip = self.p.tip(g)
        self.w.seed.git("fetch", "-q", "origin", f"refs/heads/zzzops/goal/g{g}")
        doc = json.loads(self.w.seed.git("show", "FETCH_HEAD:goal.json"))
        f = next(x for x in doc["records"][self.n("truth_design")]["findings"] if x["id"] == fid)
        del f["material"]
        push_goal_doc(self.w, doc, tip)
        self.assertNotIn("material", next(x for x in self.p.record(g, "truth_design")["findings"] if x["id"] == fid))
        self.p.run(g, "design")
        self.assertTrue(self.p.states(g)["truth_design"].startswith("ready"), self.p.states(g)["truth_design"])
        ag, card = self.p.start(g, "truth_design")
        self.assertIn(fid, [x["id"] for x in (card.get("previous") or {}).get("findings", [])])
        out = {"decision": "approved", "summary": "keeps the old finding open",
               "findings": [{"id": fid, "status": "open"}]}
        rc, err = ag.submit(g, self.n("truth_design"), card, out, artifact="# review\n", ok=False)
        self.assertNotEqual(0, rc, err)
        self.assertEqual("validation", err["error"]["code"], err)
        self.assertIn("approved requires no open material finding", json.dumps(err))
        # resolving it lets the lens approve
        ag.submit(g, self.n("truth_design"), card,
                  {"decision": "approved", "summary": "fixed", "findings": [{"id": fid, "status": "resolved"}]},
                  artifact="# review\n")


class UnfilteredReviewTests(LensPolishWorld):
    def test_5_review_tests_approved_with_an_open_finding_is_still_refused(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["review_tests"].startswith("ready"))
        ag, card = self.p.start(g, "review_tests")
        self.assertNotIn("approve with notes", card["output_schema"]["decision"])
        for f in ({"text": "a test is missing"}, lens_finding("a nit in a test name", False)):
            out = {"decision": "approved", "summary": "approved", "findings": [f]}
            rc, err = ag.submit(g, self.n("review_tests"), card, out,
                                artifact="# review\n" if card.get("artifact") else None, ok=False)
            self.assertNotEqual(0, rc, (f, err))
            self.assertEqual("validation", err["error"]["code"], err)
        self.assertIsNone(self.p.record(g, "review_tests"))
        rc, err = ag.submit(g, self.n("review_tests"), card,
                            {"decision": "approved", "summary": "approved", "findings": [{"text": "a test is missing"}]},
                            artifact="# review\n" if card.get("artifact") else None, ok=False)
        self.assertIn("approved requires no open findings", json.dumps(err))
        self.assertNotIn("material", err["error"].get("message", ""))


class NotesOnlyApprovalItemTests(LensPolishWorld):
    def test_4_approval_item_for_a_notes_only_lens(self):
        g = self.goal()
        self.through_design(g)
        summary = "truth: approved; one wording note"
        nid = self.approve_with_note(g, "truth_design", "a wording nit", summary)
        self.p.drive(g, lambda st: st["approve_design"] == "needs_human (approve)",
                     {"filter_design": [{"verdicts": {nid: verdict("note", "wording only")}}]})
        self.assertEqual("current", self.p.states(g)["design"])
        item = self.p.item(g, "approve_design")
        notes = (item.get("notes") or {}).get(self.n("truth_design")) or []
        self.assertEqual([(nid, "a wording nit", "wording only")], [(x["id"], x["text"], x["reason"]) for x in notes],
                         item.get("notes"))
        self.assertIn(summary, json.dumps(item))
        self.assertNotIn("changes_requested", json.dumps(item.get("context")))

    def test_4_a_kept_note_from_an_approving_lens_reopens_the_subject(self):
        g = self.goal()
        self.through_design(g)
        nid = self.approve_with_note(g, "truth_design", "the error message is wrong", "truth: approved with a note")
        self.lenses_done(g)
        self.p.run(g, "filter_design", verdicts={nid: verdict("keep", "the operator gets stuck")})
        self.assertEqual("ready (reopened)", self.p.states(g)["design"])
        ag, dcard = self.p.start(g, "design")
        self.assertEqual([nid], [c["id"] for c in dcard["corrections"]])


if __name__ == "__main__":
    unittest.main()
