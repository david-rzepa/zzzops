"""Step 1: file formats, validation and the shipped templates (SPEC §1.3, §3, §7, §8)."""

from __future__ import annotations

import copy
import json
import unittest

import engine_fixtures as fx
from engine import canon, schemas
from engine.errors import EXIT, Refused
from engine.ops import OPS


def default_goal(**over):
    doc = {"schema": 1, "id": 1002, "title": "Add `release cut` command", "graph": "default", "state": "open",
           "closed": None, "spec": "## Outcome\nA cut command.", "priority": "P2", "release": 1, "depends_on": [],
           "skip": {}, "links": {"issue": None}, "budget": None, "records": {}}
    doc.update(over)
    return doc


def record(**over):
    r = {"status": "done", "ok": True, "attempt": 1, "holder": "claude:9c1d/design-1", "reason": "new",
         "correction_runs": 0, "input_fp": "v1:sha256:" + "a" * 64,
         "fp_parts": {"def": "v1:sha256:x", "inputs": {}, "policy": {}}, "output": {"summary": "s"},
         "findings": [], "finished_at": "2026-11-02T10:35:12Z"}
    r.update(over)
    return r


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.wf = fx.load_template("workflow.json")
        self.policy = fx.load_template("POLICY.json")

    def test_shipped_templates_validate(self):
        self.assertEqual([], schemas.validate_policy(self.policy))
        self.assertEqual([], schemas.validate_workflow(self.wf, self.policy, fx.prompt_exists, OPS))

    def test_default_graph_has_twelve_nodes_and_replay_pos(self):
        nodes = self.wf["graphs"]["default"]["nodes"]
        self.assertEqual(fx.DEFAULT_NODES, list(nodes))
        self.assertIn("replay_pos", nodes["base"]["outputs"])

    def test_renamed_graph_validates(self):
        wf = fx.renamed_workflow(self.wf)
        self.assertEqual([], schemas.validate_workflow(wf, self.policy, fx.prompt_exists, OPS))
        g = schemas.build_graph("default", wf["graphs"]["default"])
        self.assertEqual([fx.RENAME[n] for n in fx.DEFAULT_NODES], g.topo)

    def test_topological_order_breaks_ties_by_declaration(self):
        g = schemas.build_graph("default", self.wf["graphs"]["default"])
        self.assertEqual(fx.DEFAULT_NODES, g.topo)
        self.assertEqual(["design", "test_design", "base", "review_tests"], g.producers("implement"))

    def test_every_prompt_file_exists(self):
        for nd in self.wf["graphs"]["default"]["nodes"].values():
            if nd["kind"] != "op":
                self.assertTrue(fx.prompt_exists(nd["prompt"]), nd["prompt"])

    def test_human_prompts_start_with_the_question(self):
        for name in ("approve_design.md", "approve_merge.md"):
            first = (fx.TEMPLATES / "prompts" / name).read_text().splitlines()[0]
            self.assertTrue(first.startswith("# ") and first.endswith("?"), first)


class GraphErrorTests(unittest.TestCase):
    def setUp(self):
        self.wf = fx.load_template("workflow.json")
        self.policy = fx.load_template("POLICY.json")

    def errors(self, mutate):
        wf = copy.deepcopy(self.wf)
        mutate(wf["graphs"]["default"]["nodes"], wf["graphs"]["default"])
        return schemas.validate_workflow(wf, self.policy, fx.prompt_exists, OPS)

    def assertError(self, mutate, fragment):
        errs = self.errors(mutate)
        self.assertTrue(any(fragment in e for e in errs), errs)

    def test_cycle(self):
        self.assertError(lambda n, g: n["design"]["inputs"].update({"x": {"from": "implement.summary"}}), "cycle")

    def test_unknown_selector_node_and_output(self):
        self.assertError(lambda n, g: n["design"]["inputs"].update({"x": {"from": "nope.summary"}}), "unknown node")
        self.assertError(lambda n, g: n["design"]["inputs"].update({"x": {"from": "goal.nope"}}), "does not parse")
        self.assertError(lambda n, g: n["review_tests"]["inputs"].update({"x": {"from": "test_design.nope"}}),
                         "has no output")

    def test_responses_cannot_be_selected_or_declared(self):
        self.assertError(lambda n, g: n["review_tests"]["inputs"].update({"x": {"from": "test_design.responses"}}),
                         "has no output")
        self.assertError(lambda n, g: n["implement"]["outputs"].update({"responses": "object"}), "engine-reserved")

    def test_two_checkpoint_outputs(self):
        self.assertError(lambda n, g: n["implement"]["outputs"].update({"more": "checkpoint"}), "at most one checkpoint")

    def test_checkpoint_needs_sha_base(self):
        self.assertError(lambda n, g: n["implement"]["inputs"].pop("base"), "input `base`")
        self.assertError(lambda n, g: n["implement"]["inputs"].update({"base": {"from": "design.summary"}}), "input `base`")

    def test_preserve_must_name_a_checkpoint_producer(self):
        self.assertError(lambda n, g: n["implement"].update({"preserve": "design"}), "exactly one checkpoint output")
        self.assertError(lambda n, g: n["implement"].update({"preserve": "run_tests"}), "not a transitive producer")

    def test_stage_rule(self):
        self.assertError(lambda n, g: n["design"]["inputs"].update({"x": {"from": "deps.implement.summary"}}),
                         "delivery producer")

    def test_fields_per_kind_and_ranges(self):
        self.assertError(lambda n, g: n["merge"].update({"prompt": "x.md"}), "not allowed on op")
        self.assertError(lambda n, g: n["approve_merge"].update({"timeout": 30}), "not allowed on human")
        self.assertError(lambda n, g: n["implement"].update({"timeout": 5}), "10-1440")
        self.assertError(lambda n, g: n["run_tests"].update({"timeout": 500}), "2-240")
        self.assertError(lambda n, g: n["review_impl"].update({"outputs": {"x": "text"}}), "implicit outputs only")
        self.assertError(lambda n, g: n["design"]["inputs"]["spec"].update({"pending": True}), "only on deps.")

    def test_policy_keys_instructions_and_capabilities(self):
        self.assertError(lambda n, g: n["run_tests"].update({"policy": ["verification.nope"]}), "settings has no key")
        self.assertError(lambda n, g: n["design"].update({"instructions": ["nope"]}), "no key 'nope'")
        self.assertError(lambda n, g: n["design"].update({"capability": "nope"}), "routing.tiers")
        self.assertError(lambda n, g: n["design"].update({"prompt": "missing.md"}), "does not exist")

    def test_op_validators(self):
        self.assertError(lambda n, g: n["base"].update({"op": "git.nope"}), "unknown op")
        self.assertError(lambda n, g: n["base"]["outputs"].pop("replay_pos"), "replay_pos")
        self.assertError(lambda n, g: n["run_tests"].update({"workspace": False}), "workspace: true")

    def test_terminal_and_useless_nodes(self):
        self.assertError(lambda n, g: g.update({"terminal": []}), "non-empty")
        self.assertError(lambda n, g: g.update({"terminal": ["nope"]}), "unknown node")

        def orphan(n, g):
            n["extra"] = {"kind": "agent", "stage": "delivery", "prompt": "design.md", "outputs": {"x": "text"}}
        self.assertError(orphan, "neither terminal")

    def test_unknown_keys_and_floats(self):
        self.assertError(lambda n, g: n["design"].update({"colour": "red"}), "unknown field")
        self.assertError(lambda n, g: n["implement"].update({"rev": 1.5}), "floats")


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = fx.load_template("POLICY.json")

    def check(self, mutate, fragment):
        p = copy.deepcopy(self.policy)
        mutate(p)
        errs = schemas.validate_policy(p)
        self.assertTrue(any(fragment in e for e in errs), errs)

    def test_out_of_range_settings(self):
        self.check(lambda p: p["settings"]["verification"].update({"timeout_minutes": 0}), "1-240")
        self.check(lambda p: p["settings"]["verification"].update({"ci_timeout_minutes": -1}), "10-1440")
        self.check(lambda p: p["settings"]["merge"].update({"method": "octopus"}), "one of")
        self.check(lambda p: p["settings"]["parallelism"].update({"max_workers": 51}), "1-50")
        self.check(lambda p: p["settings"]["engine"].update({"min": "1.0"}), "MAJOR.MINOR.PATCH")

    def test_missing_and_unknown_keys(self):
        self.check(lambda p: p["settings"].pop("leases"), "missing key 'leases'")
        self.check(lambda p: p["settings"].update({"refill": {}}), "unknown key 'refill'")
        self.check(lambda p: p["instructions"].update({"Bad-Key": "x"}), "keys match")
        self.check(lambda p: p["instructions"].update({"empty": " "}), "non-empty")

    def test_schema_versions(self):
        self.check(lambda p: p.update({"schema_version": 1}), "MIGRATING.md")
        self.check(lambda p: p.update({"schema_version": 3}), "must be 2")
        self.assertEqual((3, "9.0.0", None),
                         schemas.policy_floor({"schema_version": 3, "settings": {"engine": {"min": "9.0.0"}}}))
        self.assertEqual((2, None, ["a", "b"]),
                         schemas.policy_floor({"schema_version": 2, "settings": {"engine": {"requires": ["a", "b"]}}}))
        self.assertEqual((2, None, None),            # a malformed list is left to validation (G1027 §3.2)
                         schemas.policy_floor({"schema_version": 2, "settings": {"engine": {"requires": "a"}}}))
        self.assertEqual((None, None, None), schemas.policy_floor("garbage"))


class GoalTests(unittest.TestCase):
    def setUp(self):
        self.wf = fx.load_template("workflow.json")

    def errs(self, doc, old=None, docs=None, ok=None):
        return schemas.validate_goal(doc, old, docs, self.wf, ok)[0]

    def test_valid_goal(self):
        self.assertEqual([], self.errs(default_goal(records={"design": record()})))

    def test_too_large(self):
        doc = default_goal(records={f"design": record(output={"summary": "x" * 70000})})
        errs = self.errs(doc)
        self.assertTrue(any("too_large" in e and "records.design.output.summary" in e for e in errs), errs)

    def test_skip_of_terminal_node(self):
        self.assertTrue(any("terminal node cannot be skipped" in e for e in self.errs(default_goal(skip={"merge": "x"}))))

    def test_closed_done_requires_current_terminals(self):
        closed = {"reason": "done", "note": "n", "by": "d", "at": "2026-11-02T10:35:12Z"}
        doc = default_goal(state="closed", closed=closed)
        self.assertTrue(any("superseded or cancelled" in e for e in self.errs(doc, ok=lambda d: False)))
        self.assertEqual([], self.errs(doc, ok=lambda d: True))
        cancelled = dict(closed, reason="cancelled")
        self.assertEqual([], self.errs(default_goal(state="closed", closed=cancelled), ok=lambda d: False))

    def test_done_goal_stays_closed(self):
        old = default_goal(state="closed", closed={"reason": "done", "note": "n", "by": "d", "at": "2026-11-02T10:35:12Z"})
        self.assertTrue(any("stays closed" in e for e in self.errs(default_goal(), old=old)))

    def test_dependencies(self):
        docs = {1001: default_goal(id=1001, release=2), 1002: default_goal()}
        errs = self.errs(default_goal(depends_on=[1001]), docs=docs)
        self.assertTrue(any("release 2" in e for e in errs), errs)
        docs = {1001: default_goal(id=1001, depends_on=[1002]), 1002: default_goal()}
        errs = self.errs(default_goal(depends_on=[1001]), docs=docs)
        self.assertTrue(any("cycle: G1002 -> G1001 -> G1002" in e for e in errs), errs)
        self.assertTrue(any("does not exist" in e for e in self.errs(default_goal(depends_on=[7]), docs={})))

    def test_state_closed_consistency_and_floats(self):
        self.assertTrue(self.errs(default_goal(state="closed")))
        self.assertTrue(any("floats" in e for e in self.errs(default_goal(budget=1.0))))

    def test_orphan_records_are_warnings(self):
        errs, warns = schemas.validate_goal(default_goal(records={"gone": record()}), None, None, self.wf)
        self.assertEqual([], errs)
        self.assertEqual("orphan_record", warns[0]["kind"])

    def test_record_and_finding_shapes(self):
        f = {"id": "review_impl:2:1", "target": "implement", "target_fp": None, "target_attempt": 2, "text": "t",
             "status": "open", "response": None, "rounds": 1, "upheld": False, "note": None}
        errs = self.errs(default_goal(records={"review_impl": record(findings=[f])}))
        self.assertTrue(any("null exactly when" in e for e in errs), errs)
        blocked = record(status="blocked", ok=False, output=None,
                         blocked={"category": "decision", "waiting_for": "human", "reason": "r", "repeats": 1})
        self.assertTrue(any("question" in e for e in self.errs(default_goal(records={"design": blocked}))))


class InputFileTests(unittest.TestCase):
    def setUp(self):
        self.g = schemas.build_graph("default", fx.load_template("workflow.json")["graphs"]["default"])

    def test_submit_outputs(self):
        self.assertEqual([], schemas.validate_submit_output(self.g, "test_design", {"commands": ["make test"]}))
        self.assertEqual([], schemas.validate_submit_output(
            self.g, "implement", {"summary": "s", "code": {"commit": "a" * 40}, "responses": {"x:1:1": "fixed: done"}}))
        self.assertTrue(schemas.validate_submit_output(self.g, "implement", {"summary": "s", "responses": {"x": "ok"}}))
        self.assertTrue(schemas.validate_submit_output(self.g, "design", {"summary": "s", "doc": {}}))
        self.assertEqual([], schemas.validate_submit_output(
            self.g, "review_impl", {"decision": "approved", "summary": "s", "findings": [{"id": "review_impl:1:1", "status": "resolved"}]}))
        big = schemas.validate_submit_output(self.g, "implement", {"summary": "x" * 5000})
        self.assertTrue(any("too_large" in e for e in big), big)

    def test_answer_blocked_and_new_files(self):
        self.assertEqual([], schemas.validate_answer_file("approve", {"decision": "approved", "summary": "s", "quote": "q", "decided_by": "D"}))
        self.assertTrue(schemas.validate_answer_file("dispute", {"finding": "f", "decision": "maybe", "quote": "q", "decided_by": "D"}))
        self.assertEqual([], schemas.validate_blocked_file({"waiting_for": "agent", "instructions": "do x"}))
        self.assertTrue(schemas.validate_blocked_file({"waiting_for": "human"}))
        self.assertEqual([], schemas.validate_new_file({"title": "T", "spec": "S"}))
        self.assertTrue(schemas.validate_new_file({"title": "T\nU", "spec": "S"}))


class CanonTests(unittest.TestCase):
    def test_canonical_is_key_order_independent_and_utf8(self):
        a = {"b": 1, "a": {"y": "é", "x": [1, 2]}}
        b = {"a": {"x": [1, 2], "y": "é"}, "b": 1}
        self.assertEqual(canon.canonical(a), canon.canonical(b))
        self.assertEqual('{"a":{"x":[1,2],"y":"é"},"b":1}'.encode(), canon.canonical(a))
        self.assertEqual(canon.H(a), canon.H(b))

    def test_goal_bytes_and_time(self):
        self.assertTrue(canon.goal_bytes({"b": 1, "a": 2}).endswith(b"\n"))
        self.assertEqual("2026-10-30T10:03:40Z", canon.iso(canon.parse_iso("2026-10-30T10:03:40Z")))
        self.assertEqual("@5 +0000", canon.git_date(5))
        self.assertEqual("1970-01-01T00:00:00Z", canon.iso(0))

    def test_errors_have_exit_codes(self):
        self.assertEqual(1, Refused("checkpoint_required").exit)
        self.assertEqual(2, Refused("push_refused").exit)
        self.assertEqual(3, Refused("superseded").exit)
        self.assertEqual(4, Refused("not_bootstrapped").exit)
        self.assertEqual(27, len([c for c, x in EXIT.items() if x == 1]))   # G1027 removed engine_too_new
        with self.assertRaises(ValueError):
            Refused("nope")
        env = Refused("sync_refused", "m", hint="h").envelope({"commit": "c"})
        self.assertEqual({"ok": False, "error": {"code": "sync_refused", "message": "m", "details": {}, "hint": "h"},
                          "coordinator": {"commit": "c"}}, env)


if __name__ == "__main__":
    unittest.main()
