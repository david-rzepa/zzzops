"""G1026: design review flags owner questions; the design blocks for an interview to answer them (design revision 3).

These tests run on the SHIPPED template (`fx.SHIPPED`, G1022's 15-node graph) unless they say otherwise. They are
written before the implementation and define these contracts (design §2-§6, §10):

- POLICY instruction `owner_questions` (the undo-reach test), listed on `design`, `review_design`, `adversary_design`
  and `review_impl`. The `review` instruction gains the sentence "an owner question targets the design, even on code".
  design.md step 4 blocks (`--blocked`, `waiting_for: human`) with every owner question of the round.
- `schemas.is_owner_question(f)`: the text, leading whitespace stripped, starts with exactly `owner question:`
  (case-sensitive: "Owner question:" is not one). A new finding of a filtered reviewer that is an owner question
  with `material: false` is refused at submit: "an owner question is always material: set material: true".
- `render.human_decisions(git, tip, g, graph, nodes)`: reads the goal's `zzzops: answer G<g> <node>` commits
  (`git log --reverse --first-parent --grep='^zzzops: answer G<g> '`), keeps those whose `goal.json` has
  `records[node]` blocked with an `answer`, for a node in `nodes`, and returns, in commit order,
  [{node, kind, question, text, quote, decided_by, decided_at, commit}]; None when the log fails.
- Approve items (full form) gain `human_decisions` over their ancestor nodes (text clipped to 300 characters), omitted
  when empty, and the string "unavailable" when the history cannot be read. An agent card gains `human_decisions` for
  its own node (a list, or a blob view of it after shrink). The card's `answer` is shown for any card whose node's
  record is blocked and answered, not only on a retry card.
- The PR body gains `## Human decisions` after `## Reviews`, only when non-empty, one line per entry:
  `- **<node>** (<kind>; <decided_by>, <date>): <question, one line> → "<quote, one line>"`.
- Nothing new is stored: the record schema, fingerprints and node_def_fp values are unchanged.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import engine_fixtures as fx
from engine import schemas
from test_engine_lenses import Pilot
from test_engine_review_lenses import (GOLDEN, ReviewWorld, fixture, prompt_text, read_text_view, shipped, tag)

OWNER_Q = ("owner question: Q1 (from review): should the new CLI output key be called `decisions` or "
           "`human_decisions`? Options: A `human_decisions`, B `decisions`. Recommendation: A.")
TARGETING = "an owner question targets the design, even on code"
ENTRY_KEYS = {"node", "kind", "question", "text", "quote", "decided_by", "decided_at", "commit"}
OP = "claude:aaaa/op"


def owner_finding(text=OWNER_Q, material=True, lens="intent"):
    return tag(text, material, lens, impact="the owner's choice would be made by an agent")


def blocked_file(fids, question=None):
    q = question or ("owner question: " + "; ".join(f"Q{i} ({fid}): which name?" for i, fid in enumerate(fids, 1)))
    return {"waiting_for": "human", "question": q,
            "options": [f"Q{i}: A or B" for i in range(1, len(fids) + 1)], "recommendation": "Q1: A"}


def decisions_of(w: fx.World, v):
    """A card's `human_decisions`: a list, or a blob view of the JSON list after shrink."""
    if isinstance(v, list):
        return v
    return json.loads(read_text_view(w, v))


def card_size(card) -> int:
    from engine.canon import canonical
    return len(canonical({k: v for k, v in card.items() if k not in ("ok", "coordinator")}))


# --------------------------------------------------------------------------------------------- 1: policy and prompts


class OwnerQuestionsTemplateTests(unittest.TestCase):
    def setUp(self):
        self.policy = shipped("POLICY.json")
        self.nodes = shipped("workflow.json")["graphs"]["default"]["nodes"]

    def test_the_instruction_states_the_undo_reach_test(self):
        text = self.policy["instructions"].get("owner_questions")
        self.assertIsInstance(text, str, "POLICY.json has no `owner_questions` instruction")
        for needle in ("undo", "owner question:", "clearly dominates", "always material", "--blocked"):
            self.assertIn(needle, text, needle)
        self.assertGreater(len(text.encode("utf-8")), 600)         # shown as a blob view on cards (INLINE is 600)

    def test_the_instruction_is_listed_on_the_four_nodes(self):
        for n in ("design", "review_design", "adversary_design", "review_impl"):
            self.assertIn("owner_questions", self.nodes[n].get("instructions") or [], n)
        for n, nd in self.nodes.items():
            if n not in ("design", "review_design", "adversary_design", "review_impl"):
                self.assertNotIn("owner_questions", nd.get("instructions") or [], n)

    def test_the_review_instruction_has_the_targeting_sentence(self):
        text = self.policy["instructions"]["review"]
        self.assertIn("owner_questions", text)
        self.assertIn(TARGETING, text)

    def test_design_prompt_step_4_blocks_with_every_owner_question(self):
        text = prompt_text("design.md")
        for needle in ("owner_questions", "owner question:", "--blocked", "waiting_for: human", "Q1: ",
                       "## Owner decisions", "human_decisions", "fixed: owner chose"):
            self.assertIn(needle, text, needle)

    def test_implement_prompt_does_not_handle_owner_questions(self):
        self.assertNotIn("owner question:", prompt_text("implement.md"))           # D2

    def test_intent_lens_raises_decisions_taken_on_the_owners_behalf(self):
        self.assertIn("decisions taken on the owner's behalf (raise each as an owner question)",
                      prompt_text("lens_intent.md"))

    def test_approve_prompts_show_human_decisions_and_delegates(self):
        for name in ("approve_design.md", "approve_merge.md"):
            text = prompt_text(name)
            self.assertIn("human_decisions", text, name)
            self.assertIn("decided_by", text, name)
            self.assertIn("delegate", text, name)

    def test_shipped_templates_still_validate(self):
        from engine.ops import OPS
        from test_engine_review_lenses import shipped_prompt_exists
        self.assertEqual([], schemas.validate_policy(self.policy))
        self.assertEqual([], schemas.validate_workflow(shipped("workflow.json"), self.policy,
                                                       shipped_prompt_exists, OPS))


class ExecuteSkillTests(unittest.TestCase):
    SKILL = fx.ROOT / "plugins" / "zzzops" / "skills" / "execute-zzzops" / "SKILL.md"

    def test_execute_skill_batches_owner_questions_and_never_answers_them_as_a_delegate(self):
        text = self.SKILL.read_text(encoding="utf-8")
        self.assertIn("owner question:", text)
        self.assertIn("one sitting", text)
        self.assertIn("delegated by", text)
        self.assertRegex(text, r"never use that form for an owner question")

    def test_execution_doc_has_the_same_paragraph(self):
        text = (fx.ROOT / "docs" / "EXECUTION.md").read_text(encoding="utf-8")
        self.assertIn("owner question:", text)
        self.assertIn("delegated by", text)

    def test_prompt_stats_check_passes(self):
        p = subprocess.run([sys.executable, str(fx.ROOT / ".agents" / "prompt_stats.py"), "--check"],
                           cwd=fx.ROOT, capture_output=True, text=True)
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)


# --------------------------------------------------------------------------------------------- 4: is_owner_question


class IsOwnerQuestionTests(unittest.TestCase):
    def test_prefix_is_exact_and_case_sensitive(self):
        f = getattr(schemas, "is_owner_question", None)
        self.assertIsNotNone(f, "schemas.is_owner_question is missing")
        self.assertTrue(f({"text": "owner question: which name?"}))
        self.assertTrue(f({"text": "  \n owner question: which name?"}))
        for text in ("Owner question: none", "OWNER QUESTION: x", "an owner question: x", "owner question x",
                     "owner-question: x", ""):
            self.assertFalse(f({"text": text}), text)


# --------------------------------------------------------------------------------------------- 5/6: format and names


class NoFormatChangeTests(unittest.TestCase):
    def test_record_schema_is_unchanged(self):
        self.assertNotIn("answers", schemas.RECORD_KEYS)
        self.assertNotIn("human_decisions", schemas.RECORD_KEYS)

    def test_golden_node_def_fp_values_are_unchanged(self):
        from engine.fingerprint import node_def_fp
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        for graph in ("graph12", "graph26"):
            nodes = fixture(graph, "workflow.json")["graphs"]["default"]["nodes"]
            self.assertEqual(golden[graph], {n: node_def_fp(nd) for n, nd in nodes.items()}, graph)

    def test_listing_the_instruction_changes_no_node_def_fp(self):
        """D1: `instructions` is not fingerprinted, so listing `owner_questions` stales no record."""
        from engine.fingerprint import node_def_fp
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        nodes = shipped("workflow.json")["graphs"]["default"]["nodes"]
        self.assertEqual(golden["graph26"]["adversary_design"], node_def_fp(nodes["adversary_design"]))
        for n in ("design", "review_design", "adversary_design", "review_impl"):
            bare = copy.deepcopy(nodes[n])
            bare["instructions"] = [i for i in bare.get("instructions") or [] if i != "owner_questions"]
            self.assertEqual(node_def_fp(bare), node_def_fp(nodes[n]), n)

    def test_engine_holds_the_prefix(self):
        hits = [p for p in sorted((fx.PLUGIN_CODE / "engine").rglob("*.py"))
                if "owner question:" in p.read_text(encoding="utf-8")]
        self.assertTrue(hits, "the engine does not hold the `owner question:` prefix")

    def test_no_capability_file(self):
        self.assertFalse((fx.PLUGIN_CODE / "engine" / "capabilities" / "owner_answers.txt").exists())
        self.assertNotIn("owner_answers", shipped("POLICY.json")["settings"]["engine"].get("requires") or [])


# --------------------------------------------------------------------------------------------- 8: docs


class ContractDocsTests(unittest.TestCase):
    def test_g1026_landed_its_contract_edits(self):
        import test_design_docs as dd
        rows = dd.parse_pending_table(dd.read_doc("README.md"))
        self.assertNotIn(1026, [r.goal for r in rows])
        log = dd.section(dd.read_doc("HISTORY.md"), r"amendments after approval")
        self.assertTrue(any(re.search(r"\bG1026\b", l) for l in log.splitlines() if l.strip().startswith("|")))

    def test_spec_names_the_new_shapes(self):
        import test_design_docs as dd
        spec = dd.read_doc("SPEC.md")
        for needle in ("owner question:", "human_decisions", "## Human decisions", "owner_questions",
                       "zzzops: answer G"):
            self.assertIn(needle, spec, needle)


# --------------------------------------------------------------------------------------------- 3: the history read


class HumanDecisionsHelperTests(unittest.TestCase):
    """`render.human_decisions` over a hand-built goal history (one goal.json per commit)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = fx.make_repo(self.tmp)
        self.graph = schemas.build_graph("default", shipped("workflow.json")["graphs"]["default"])
        self.helper = getattr(__import__("engine.render", fromlist=["render"]), "human_decisions", None)
        self.assertIsNotNone(self.helper, "engine.render.human_decisions is missing")

    def doc(self, g, records):
        from test_engine_schemas import default_goal
        return default_goal(id=g, records=records)

    @staticmethod
    def blocked(question, answer=None, holder="claude:9c1d/design-1"):
        from test_engine_schemas import record
        r = record(status="blocked", ok=False, holder=holder, output=None,
                   blocked={"category": "decision", "waiting_for": "agent" if answer else "human",
                            "question": question, "options": ["A", "B"], "recommendation": "A"})
        if answer:
            r["answer"] = dict({"decided_at": "2026-11-02T10:00:00Z"}, **answer)
        return r

    def commit(self, doc, subject):
        return self.repo.commit({"goal.json": json.dumps(doc, indent=2, sort_keys=True) + "\n"},
                                f"{subject}\n\nOutcome: ok\nState: open\nEngine: 1.3.0")

    def run_helper(self, tip, g, nodes):
        git = fx.engine_git(self.repo)
        with fx.env_of(self.repo.env):
            return self.helper(git, tip, g, self.graph, nodes)

    def test_entries_in_commit_order_with_kinds_and_only_blocked_answers(self):
        from test_engine_schemas import record
        g = 10
        ans1 = {"text": "A", "quote": "Take A.", "decided_by": "Dave"}
        ans2 = {"text": "rebase", "quote": "Rebase it.", "decided_by": "Claude (root agent), delegated by Dave"}
        recs = {}
        self.commit(self.doc(g, recs), f"zzzops: new G{g}")
        recs["design"] = self.blocked("owner question: Q1?")
        self.commit(self.doc(g, recs), f"zzzops: submit G{g} design attempt 1 by claude:9c1d/design-1")
        recs["design"] = self.blocked("owner question: Q1?", ans1)
        c1 = self.commit(self.doc(g, recs), f"zzzops: answer G{g} design")
        recs["design"] = record()
        recs["approve_design"] = record(holder="human", output={"decision": "approved", "summary": "s",
                                                                 "quote": "yes", "decided_by": "Dave"})
        self.commit(self.doc(g, recs), f"zzzops: answer G{g} approve_design")       # an approval: not listed
        recs["review_design"] = record(findings=[])
        self.commit(self.doc(g, recs), f"zzzops: answer G{g} review_design")        # a dispute answer: not listed
        recs["integrate"] = self.blocked("No checks appeared on #1. Rebase it?", ans2, holder="op")
        c2 = self.commit(self.doc(g, recs), f"zzzops: answer G{g} integrate")
        other = copy.deepcopy(recs)
        other["design"] = self.blocked("owner question: G100's question", ans1)
        self.commit(self.doc(100, other), "zzzops: answer G100 design")             # G100's subject: not G10's
        recs["design"] = record()
        tip = self.commit(self.doc(g, recs), f"zzzops: submit G{g} design attempt 2 by claude:9c1d/design-1")
        out = self.run_helper(tip, g, list(self.graph.nodes))
        self.assertEqual([("design", "agent", c1), ("integrate", "op", c2)],
                         [(e["node"], e["kind"], e["commit"]) for e in out], out)
        for e in out:
            self.assertEqual(ENTRY_KEYS, set(e), e)
        d, i = out
        self.assertEqual(("owner question: Q1?", "A", "Take A.", "Dave", "2026-11-02T10:00:00Z"),
                         (d["question"], d["text"], d["quote"], d["decided_by"], d["decided_at"]))
        self.assertEqual("Claude (root agent), delegated by Dave", i["decided_by"])
        only_design = self.run_helper(tip, g, ["design", "review_design"])
        self.assertEqual(["design"], [e["node"] for e in only_design])

    def test_no_answers_is_an_empty_list_and_a_failing_log_is_none(self):
        g = 10
        tip = self.commit(self.doc(g, {}), f"zzzops: new G{g}")
        self.assertEqual([], self.run_helper(tip, g, list(self.graph.nodes)))
        self.assertIsNone(self.run_helper("0" * 40, g, list(self.graph.nodes)))


# --------------------------------------------------------------------------------------------- World tests


class OwnerWorld(ReviewWorld):
    """The shipped 15-node graph, with helpers to raise, block on and answer an owner question."""

    def raise_owner_question(self, g, text=OWNER_Q):
        """Design is current; review_design raises one owner question, adversary approves, the filter runs.
        Returns the finding id; design is ready (reopened)."""
        self.p.run(g, "review_design", findings=[owner_finding(text)])
        fid = [f["id"] for f in self.p.record(g, "review_design")["findings"]
               if f["status"] == "open" and f["text"] == text][0]
        self.p.drive(g, lambda st: st["filter_design"].startswith("ready"))
        self.p.run(g, "filter_design")
        self.assertEqual("ready (reopened)", self.p.states(g)["design"])
        return fid

    def block(self, g, fids):
        ag, card = self.p.start(g, "design")
        self.assertTrue(set(fids) <= {c["id"] for c in card["corrections"]}, card["corrections"])
        out = ag.submit(g, self.n("design"), card, blocked=blocked_file(fids))
        return card, out

    def blocked_item(self, g):
        nxt = self.w.ok("a", "next", "--goal", str(g))
        return next((x for x in nxt["needs_human"] if x["node"] == self.n("design") and x["kind"] == "blocked"), None)

    def answer_block(self, g, text="A", quote="Go with A: `human_decisions`.", decided_by="Dave"):
        it = self.blocked_item(g)
        self.assertIsNotNone(it, self.p.states(g))
        return self.w.ok("a", "answer", str(g), self.n("design"), "--fp", it["fp"], "--file",
                         self.w.file({"text": text, "quote": quote, "decided_by": decided_by}))

    def answer_commits(self, g, node="design"):
        log = self.w.remote_git("log", "--reverse", "--first-parent", "--format=%H%x1f%s",
                                f"refs/heads/zzzops/goal/g{g}")
        return [l.split("\x1f")[0] for l in log.splitlines() if l.split("\x1f")[1] == f"zzzops: answer G{g} {node}"]

    def resubmit_design(self, g, fids, note="owner chose A"):
        ag, card = self.p.start(g, "design")
        out = self.p.output(self.n("design"), card)
        live = {c["id"] for c in card["corrections"]}                 # the journey test pins that fids are live
        out["responses"] = dict(out.get("responses") or {}, **{f: f"fixed: {note}" for f in fids if f in live})
        ag.submit(g, self.n("design"), card, out, artifact=f"# design\n\n## Owner decisions\n\n{note}\n")
        return card

    def to_approve_design(self, g):
        return self.p.drive(g, lambda st: st["approve_design"] == "needs_human (approve)")


class OwnerJourneyTests(OwnerWorld):
    def test_cards_carry_the_instruction_and_stay_within_the_limit(self):
        from engine.card import CARD_LIMIT
        g = self.goal()
        ag, dcard = self.p.start(g, "design")
        self.assertIn("owner_questions", dcard["instructions"])
        text = self.instruction_text(dcard, "owner_questions")
        self.assertIn("undo", text)
        self.assertIn("owner question:", text)
        prompt = read_text_view(self.w, dcard["prompt"])
        self.assertIn("owner question:", prompt)
        self.assertIn("--blocked", prompt)
        self.assertNotIn("human_decisions", dcard)                      # no answers: no key
        self.assertLessEqual(card_size(dcard), CARD_LIMIT)
        ag.submit(g, self.n("design"), dcard, self.p.output(self.n("design"), dcard), artifact="# design\n")
        for node in ("review_design", "adversary_design"):
            _, card = self.p.start(g, node, avoid=(ag.label,))
            self.assertIn("owner_questions", card["instructions"], node)
            self.assertIn(TARGETING, self.instruction_text(card, "review"), node)
            self.assertLessEqual(card_size(card), CARD_LIMIT, node)
            self.w.ok("a", "abandon", str(g), self.n(node), "--attempt", str(card["lease"]["attempt"]))
        self.until_ready(g, "review_impl")
        _, card = self.p.start(g, "review_impl")
        self.assertIn("owner_questions", card["instructions"])
        self.assertIn(TARGETING, self.instruction_text(card, "review"))
        self.assertLessEqual(card_size(card), CARD_LIMIT)

    def test_the_acceptance_journey(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["design"] == "current")
        fid = self.raise_owner_question(g)
        self.assertTrue(self.p.record(g, "review_design")["findings"][0]["material"])
        _, out = self.block(g, [fid])
        st = self.p.states(g)["design"]
        self.assertTrue(st.startswith("needs_human"), st)
        it = self.blocked_item(g)
        self.assertTrue(it["question"].startswith("owner question:"), it)
        self.assertIn(fid, it["question"])
        self.assertEqual("Q1: A", it["recommendation"])
        self.answer_block(g)
        [commit] = self.answer_commits(g)
        ag, card = self.p.start(g, "design")
        self.assertEqual("retry", card["reason"])
        # design.md step 4: the retry answers the owner-question finding `fixed: owner chose …`, so it is a correction
        self.assertIn(fid, [c["id"] for c in card["corrections"]], card["corrections"])
        self.assertEqual(("A", "Go with A: `human_decisions`.", "Dave"),
                         (card["answer"]["text"], card["answer"]["quote"], card["answer"]["decided_by"]))
        decisions = decisions_of(self.w, card["human_decisions"])
        self.assertEqual(1, len(decisions), decisions)
        self.assertEqual(("design", "agent", commit), (decisions[0]["node"], decisions[0]["kind"],
                                                        decisions[0]["commit"]))
        out = self.p.output(self.n("design"), card)
        out["responses"] = dict(out.get("responses") or {}, **{fid: "fixed: owner chose A"})
        ag.submit(g, self.n("design"), card, out, artifact="# design\n\n## Owner decisions\n\nA\n")
        rcard, _ = self.p.run(g, "review_design")                     # resolves the finding and approves
        self.assertIn(fid, [f["id"] for f in rcard["previous"]["findings"] if f["status"] == "open"])
        self.to_approve_design(g)
        self.assertEqual("resolved", next(f for f in self.p.record(g, "review_design")["findings"]
                                          if f["id"] == fid)["status"])
        item = self.p.item(g, "approve_design")
        rec = self.p.record(g, "design")
        self.assertEqual("done", rec["status"])
        question = blocked_file([fid])["question"]
        self.assertEqual([{"node": self.n("design"), "kind": "agent", "question": question, "text": "A",
                           "quote": "Go with A: `human_decisions`.", "decided_by": "Dave",
                           "decided_at": item["human_decisions"][0]["decided_at"], "commit": commit}],
                         item["human_decisions"])
        self.assertRegex(item["human_decisions"][0]["decided_at"], r"^\d{4}-\d\d-\d\dT")
        self.assertLessEqual(set(rec), set(schemas.RECORD_KEYS))            # nothing new is stored

    def test_no_answers_no_key_and_no_pr_section(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["approve_design"] == "needs_human (approve)")
        self.assertNotIn("human_decisions", self.p.item(g, "approve_design"))
        self.p.drive(g, lambda st: st["approve_merge"] == "needs_human (approve)" and st["integrate"] == "current",
                     limit=200)
        self.assertNotIn("human_decisions", self.p.item(g, "approve_merge"))
        body = next(iter(self.gh.load()["prs"].values()))["body"]
        self.assertIn("## Reviews", body)
        self.assertNotIn("## Human decisions", body)

    def test_long_answer_text_is_clipped_on_the_item(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["design"] == "current")
        fid = self.raise_owner_question(g)
        self.block(g, [fid])
        self.answer_block(g, text="A " + "x" * 400)
        self.resubmit_design(g, [fid])
        self.to_approve_design(g)
        [e] = self.p.item(g, "approve_design")["human_decisions"]
        self.assertLessEqual(len(e["text"]), 300)
        self.assertTrue(e["text"].startswith("A xxx"), e["text"])


class DurabilityTests(OwnerWorld):
    def answered_goal(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["design"] == "current")
        fid = self.raise_owner_question(g)
        self.block(g, [fid])
        self.answer_block(g)
        return g, fid

    def test_the_decision_survives_a_reopen_a_stale_rerun_and_a_second_round(self):
        g, fid = self.answered_goal()
        self.resubmit_design(g, [fid])
        self.to_approve_design(g)
        first = self.answer_commits(g)
        # a second, ordinary reopen of design
        self.w.ok("a", "reopen", str(g), self.n("design"), "--note", "tighten section 4")
        ag, card = self.p.start(g, "design")
        self.assertEqual(first, [e["commit"] for e in decisions_of(self.w, card["human_decisions"])])
        ag.submit(g, self.n("design"), card, self.p.output(self.n("design"), card), artifact="# design v3\n")
        self.to_approve_design(g)
        self.assertEqual(first, [e["commit"] for e in self.p.item(g, "approve_design")["human_decisions"]])
        # a stale re-run from a spec edit
        self.edit(g, 'spec="a revised spec"')
        self.assertTrue(self.p.states(g)["design"].startswith("ready (stale"), self.p.states(g)["design"])
        ag, card = self.p.start(g, "design")
        self.assertEqual("stale", card["reason"])
        self.assertEqual(first, [e["commit"] for e in decisions_of(self.w, card["human_decisions"])])
        ag.submit(g, self.n("design"), card, self.p.output(self.n("design"), card), artifact="# design v4\n")
        # a second owner-question round
        self.p.drive(g, lambda st: st["review_design"].startswith("ready"))
        fid2 = self.raise_owner_question(g, OWNER_Q.replace("Q1", "Q2").replace("`decisions`", "`answers`"))
        self.block(g, [fid2])
        self.answer_block(g, text="B", quote="B this time.")
        both = self.answer_commits(g)
        self.assertEqual(2, len(both))
        self.resubmit_design(g, [fid2], note="owner chose B")
        self.to_approve_design(g)
        item = self.p.item(g, "approve_design")
        self.assertEqual([("A", both[0]), ("B", both[1])], [(e["text"], e["commit"]) for e in item["human_decisions"]])
        self.p.drive(g, lambda st: st["approve_merge"] == "needs_human (approve)" and st["integrate"] == "current",
                     limit=250)
        merge_item = self.p.item(g, "approve_merge")
        self.assertEqual(both, [e["commit"] for e in merge_item["human_decisions"]])    # approvals are not listed
        body = next(iter(self.gh.load()["prs"].values()))["body"]
        self.assertIn("## Human decisions", body)
        self.assertLess(body.index("## Reviews"), body.index("## Human decisions"))
        section = body[body.index("## Human decisions"):]
        lines = [l for l in section.splitlines() if l.startswith("- **")]
        self.assertEqual(2, len(lines), section)
        self.assertRegex(lines[0], r'^- \*\*%s\*\* \(agent; Dave, \d{4}-\d\d-\d\d[^)]*\): owner question: .+ → '
                                   r'"Go with A: `human_decisions`\."$' % re.escape(self.n("design")))
        self.assertTrue(lines[1].endswith('→ "B this time."'), lines[1])

    def test_answered_then_spec_edit_before_the_retry_gives_a_stale_card_with_the_answer(self):
        g, fid = self.answered_goal()
        self.edit(g, 'spec="the owner widened the spec"')
        st = self.p.states(g)["design"]
        self.assertTrue(st.startswith("ready (stale"), st)
        ag, card = self.p.start(g, "design")
        self.assertEqual("stale", card["reason"])
        self.assertEqual("Go with A: `human_decisions`.", card["answer"]["quote"])
        self.assertEqual(1, len(decisions_of(self.w, card["human_decisions"])))

    def test_spec_edit_while_blocked_unanswered_keeps_the_owner_question(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["design"] == "current")
        fid = self.raise_owner_question(g)
        self.block(g, [fid])
        self.edit(g, 'spec="edited while the owner is away"')
        st = self.p.states(g)["design"]
        self.assertTrue(st.startswith("ready (stale"), st)
        ag, card = self.p.start(g, "design")
        self.assertNotIn("answer", card)
        self.assertNotIn("human_decisions", card)
        self.assertIn(fid, [c["id"] for c in card["corrections"]])              # G1028 carries it
        ag.submit(g, self.n("design"), card, blocked=blocked_file([fid]))
        self.assertIsNotNone(self.blocked_item(g))

    def test_the_answer_commit_subject_is_the_index(self):
        g, _ = self.answered_goal()
        log = self.w.remote_git("log", "-1", "--format=%s", f"refs/heads/zzzops/goal/g{g}")
        self.assertEqual(f"zzzops: answer G{g} {self.n('design')}", log)


class UnavailableHistoryTests(OwnerWorld):
    def test_a_failing_log_says_unavailable(self):
        from engine import gitrun
        from engine.session import Session
        from test_engine_review_fixes import InProcess
        g = self.goal()
        self.p.drive(g, lambda st: st["design"] == "current")
        fid = self.raise_owner_question(g)
        self.block(g, [fid])
        self.answer_block(g)
        self.resubmit_design(g, [fid])
        self.to_approve_design(g)
        original = gitrun.Git.run

        def failing(self_, *args, **kw):
            if args and args[0] == "log" and any("zzzops: answer G" in str(a) for a in args):
                args = ("log", "refs/heads/no/such/ref")
            return original(self_, *args, **kw)

        gitrun.Git.run = failing
        try:
            with InProcess(self.w, "a"):
                s = Session()
                s.open(goals=[g], readonly=True)
                out = s.render_next(scope=[g])
        finally:
            gitrun.Git.run = original
        item = next(x for x in out["needs_human"] if x["node"] == self.n("approve_design"))
        self.assertEqual("unavailable", item.get("human_decisions"), item)


class OpDecisionTests(OwnerWorld):
    """An answered op block (integrate's "no checks" question) is a human decision with kind `op`."""

    def bootstrap(self):
        from test_engine_review_lenses import policy_with_intent
        policy = policy_with_intent()
        self.w.bootstrap(policy=policy, workflow=shipped("workflow.json"), prompts=False,
                         settings={"verification.required_ci": ["ci"]})
        self.push_prompts(fx.SHIPPED)

    def op_at(self, g, node, now):
        self.w.now = max(self.w.now, now)
        return self.w.ok("a", "start", str(g), self.n(node), "--as", OP, now=self.w.now)

    def test_an_answered_integrate_question_is_listed_with_kind_op(self):
        from engine.canon import parse_iso
        g = self.goal()
        self.until_ready(g, "integrate", limit=250)
        out = self.op_at(g, "integrate", self.w.now)
        for _ in range(4):
            b = out["ran"].get("blocked") or {}
            if b.get("waiting_for") == "human":
                break
            out = self.op_at(g, "integrate", parse_iso(self.p.record(g, "integrate")["blocked"]["retry_after"]))
        self.assertEqual("human", out["ran"]["blocked"]["waiting_for"], out["ran"])
        nxt = self.w.ok("a", "next", "--goal", str(g))
        it = next(x for x in nxt["needs_human"] if x["node"] == self.n("integrate") and x["kind"] == "blocked")
        self.w.ok("a", "answer", str(g), self.n("integrate"), "--fp", it["fp"], "--file", self.w.file(
            {"text": "wait for ci", "quote": "Wait for it.", "decided_by": "Claude (root agent), delegated by Dave"}))
        [commit] = self.answer_commits(g, self.n("integrate"))
        head = self.w.remote_git("rev-parse", f"refs/heads/zzzops/pr/g{g}")
        self.gh.set_checks(head, ci=["pass"])
        out = self.op_at(g, "integrate", self.w.now + 60)
        self.assertTrue(out["ran"]["ok"], out["ran"])
        self.p.drive(g, lambda st: st["approve_merge"] == "needs_human (approve)")
        item = self.p.item(g, "approve_merge")
        self.assertEqual([(self.n("integrate"), "op", commit, "Claude (root agent), delegated by Dave")],
                         [(e["node"], e["kind"], e["commit"], e["decided_by"]) for e in item["human_decisions"]])


# --------------------------------------------------------------------------------------------- 4: the filter


class OwnerFilterTests(OwnerWorld):
    def test_a_non_material_owner_question_is_refused_and_the_capitalised_note_is_not(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["design"] == "current")
        ag, card = self.p.start(g, "review_design")
        bad = {"decision": "changes_requested", "summary": "s", "findings": [owner_finding(material=False)]}
        rc, err = self.submit(ag, g, "review_design", card, bad, ok=False)
        self.assertNotEqual(0, rc, err)
        self.assertEqual("validation", err["error"]["code"], err)
        self.assertIn("an owner question is always material: set material: true", json.dumps(err))
        self.assertIsNone(self.p.record(g, "review_design"))
        note = {"decision": "approved", "summary": "s",
                "findings": [owner_finding("Owner question: none in this design.", material=False)]}
        self.submit(ag, g, "review_design", card, note)
        [f] = self.p.record(g, "review_design")["findings"]
        self.assertIs(False, f["material"])

    def test_adversary_is_held_to_the_same_rule(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["design"] == "current")
        ag, card = self.p.start(g, "adversary_design")
        bad = {"decision": "changes_requested", "summary": "s",
               "findings": [{"text": OWNER_Q, "impact": "x", "material": False}]}
        rc, err = self.submit(ag, g, "adversary_design", card, bad, ok=False)
        self.assertNotEqual(0, rc, err)
        self.assertIn("always material", json.dumps(err))

    def test_a_material_owner_question_cannot_be_demoted_by_the_filter(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["design"] == "current")
        self.p.run(g, "review_design", findings=[owner_finding()])
        fid = self.open_ids(g, "review_design")[0]
        self.p.drive(g, lambda st: st["filter_design"].startswith("ready"))
        ag, card = self.p.start(g, "filter_design")
        self.assertEqual([[fid, True]], [[c["id"], c["material"]] for c in card["candidates"]])
        demote = {"summary": "s", "verdicts": {fid: {"verdict": "note", "reason": "just a nit"}}}
        rc, err = ag.submit(g, self.n("filter_design"), card, demote, ok=False)
        self.assertNotEqual(0, rc, err)
        ag.submit(g, self.n("filter_design"), card, {"summary": "s", "verdicts": {}})
        self.assertEqual("ready (reopened)", self.p.states(g)["design"])


class Graph12OwnerQuestionTests(unittest.TestCase):
    """On graph12 (unfiltered review_design, no `material` key) an owner question is accepted and is material."""

    def test_accepted_and_material(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        w = fx.World(tmp)
        w.bootstrap(workflow=fx.stub_ops_workflow())
        A, B = fx.Agent(w, "a", "claude:aaaa/w-1"), fx.Agent(w, "b", "codex:bbbb/w-2")
        g = w.new(title="Cut")["created"]["id"]
        c = A.start(g, "design")
        A.submit(g, "design", c, {"summary": "D"}, artifact="# D\n")
        c = B.start(g, "review_design")
        B.submit(g, "review_design", c, {"decision": "changes_requested", "summary": "r",
                                         "findings": [{"text": OWNER_Q}]}, artifact="# review\n")
        [f] = w.ok("a", "show", str(g), "--json")["goal"]["records"]["review_design"]["findings"]
        self.assertNotIn("material", f)
        self.assertTrue(schemas.is_material(f))
        self.assertTrue(schemas.is_owner_question(f))


if __name__ == "__main__":
    unittest.main()
