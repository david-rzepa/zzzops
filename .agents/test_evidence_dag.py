"""Approved #498 graph grammar against the production policy boundary.

These fixtures contain data only. No prototype evaluator or reference scheduler
is imported. Every rejection first proves acceptance of its unmodified control,
so an unsupported-schema error cannot count as evidence for a specific guard.
"""

from __future__ import annotations

import copy
import unittest

import test_zzzops as fixtures


z = fixtures.zzzops


def selector(name):
    return {"kind": "node", "goal": 100, "node": name}


def scope(name, output="value"):
    return {"subject": selector(name), "output": output}


def task(name, predecessors=(), *, role="worker"):
    return {
        "id": name,
        "prompt": "Read the exact declared evidence and return the requested value.",
        "inputs": {},
        "outputs": {"value": {"type": "text", "schema": {"kind": "string"}}},
        "requires": [selector(item) for item in predecessors],
        "executor": {
            "role": role, "capability": "bounded", "resources": [],
            "authority": scope(name),
        },
        "independent_of": [], "gates": [], "resolves": [], "permits": [],
    }


def subject_input(name, *, mode="identity"):
    return {
        "producer": {"node": selector(name)}, "output": "value",
        "path": [], "mode": mode, "type": {"kind": "string"},
    }


def review_graph():
    producer = task("produce")
    reviews = [task(name, ["produce"]) for name in ("review_a", "review_b")]
    for review in reviews:
        review["inputs"] = {"subject": subject_input("produce")}
        review["independent_of"] = [selector("produce")]
    finish = task("finish", ["review_a", "review_b"], role="root")
    return {"nodes": [producer, *reviews, finish], "task_sets": [],
            "terminals": [selector("finish")]}


class EvidenceGraphGrammarTests(unittest.TestCase):
    def errors(self, graph):
        # Existing production configuration seam; its implementation is replaced
        # in place by #498. The approved Graph is the value being validated.
        return z._policy._workflow_phase_dag_errors(graph)

    def accepted(self, graph):
        self.assertEqual([], self.errors(graph), "Approved Graph must be accepted")

    def rejected_mutation(self, mutate, diagnostic):
        graph = review_graph()
        self.accepted(graph)
        invalid = copy.deepcopy(graph)
        mutate(invalid)
        errors = self.errors(invalid)
        self.assertTrue(errors, "Invalid graph was accepted")
        self.assertRegex("; ".join(errors), diagnostic)
        self.assertEqual(graph, review_graph(), "Validation mutated its input")

    def test_two_review_tasks_share_behavior_without_sharing_identity(self):
        graph = review_graph()
        self.accepted(graph)
        self.assertEqual(graph["nodes"][1]["prompt"], graph["nodes"][2]["prompt"])

    def test_duplicate_identity_is_rejected_after_valid_control(self):
        self.rejected_mutation(lambda g: g["nodes"].append(copy.deepcopy(g["nodes"][1])),
                               r"(?i)duplicate|unique")

    def test_missing_prerequisite_is_rejected_after_valid_control(self):
        self.rejected_mutation(lambda g: g["nodes"][1]["requires"].append(selector("missing")),
                               r"(?i)missing|unknown|reference")

    def test_cycle_is_rejected_after_valid_control(self):
        self.rejected_mutation(lambda g: g["nodes"][0]["requires"].append(selector("finish")),
                               r"(?i)cycle|acyclic")

    def test_missing_review_subject_is_rejected_after_valid_control(self):
        self.rejected_mutation(lambda g: g["nodes"][1]["inputs"].update(subject=subject_input("missing")),
                               r"(?i)missing|unknown|reference")

    def test_self_independence_is_unsatisfiable(self):
        self.rejected_mutation(lambda g: g["nodes"][1].update(independent_of=[selector("review_a")]),
                               r"(?i)independen|self|unsatisfiable")

    def test_terminal_must_resolve(self):
        self.rejected_mutation(lambda g: g.update(terminals=[selector("missing")]),
                               r"(?i)missing|unknown|terminal|reference")

    def test_unknown_fields_do_not_create_an_extension_language(self):
        self.rejected_mutation(lambda g: g["nodes"][0].update(script="return True"),
                               r"(?i)field|unsupported|unknown")

    def test_executable_type_contract_is_rejected(self):
        self.rejected_mutation(lambda g: g["nodes"][0]["outputs"]["value"].update(schema={"kind": "python", "code": "True"}),
                               r"(?i)type|contract|unsupported|kind")

    def test_closed_nested_types_are_accepted(self):
        graph = review_graph()
        graph["nodes"][0]["outputs"]["detail"] = {"type": "detail", "schema": {
            "kind": "object", "fields": {
                "items": {"kind": "array", "items": {"kind": "integer"}},
                "decision": {"kind": "enum", "values": ["yes", "no", None]},
            },
        }}
        self.accepted(graph)

    def test_plain_string_cannot_ambiguously_select_a_member_or_join(self):
        self.rejected_mutation(lambda g: g["nodes"][1].update(requires=["produce"]),
                               r"(?i)selector|reference|requires")

    def test_script_predicate_is_not_an_applicability_contract(self):
        self.rejected_mutation(lambda g: g["nodes"][1].update(when="eval(user_input)"),
                               r"(?i)field|unsupported|unknown")

    def test_renaming_domain_phases_does_not_change_graph_validity(self):
        graph = review_graph()
        self.accepted(graph)
        replacement = {"produce": "investigation", "review_a": "synthesis",
                       "review_b": "migration_analysis", "finish": "human_decision"}
        def rename(value):
            if isinstance(value, list):
                return [rename(item) for item in value]
            if isinstance(value, dict):
                return {key: replacement.get(item, item) if key in {"id", "node"}
                        and isinstance(item, str) else rename(item)
                        for key, item in value.items()}
            return value
        self.accepted(rename(graph))

    def test_root_role_is_explicit_not_inferred_from_task_name(self):
        graph = review_graph()
        graph["nodes"][0]["executor"]["role"] = "root"
        self.accepted(graph)

    def test_maps_accept_dynamic_keys_but_do_not_open_fixed_objects(self):
        graph = review_graph()
        graph["nodes"][0]["outputs"]["buckets"] = {"type": "selection", "schema": {
            "kind": "object", "fields": {
                "items": {"kind": "map", "values": {"kind": "string"}},
                "rationale": {"kind": "string"}}}}
        self.accepted(graph)
        invalid = copy.deepcopy(graph)
        invalid["nodes"][0]["outputs"]["buckets"]["schema"]["extra"] = True
        self.assertRegex("; ".join(self.errors(invalid)), r"(?i)field|unknown|schema")

    def test_reserved_result_type_cannot_be_declared_as_an_output(self):
        self.rejected_mutation(lambda g: g["nodes"][0]["outputs"]["value"].update(type="result"),
                               r"(?i)reserved|host|result")

    def test_map_union_overlaps_on_empty_object(self):
        self.rejected_mutation(lambda g: g["nodes"][0]["outputs"]["value"].update(schema={
            "kind": "union", "variants": [
                {"kind": "map", "values": {"kind": "string"}},
                {"kind": "map", "values": {"kind": "integer"}}]}), r"(?i)overlap|disjoint|union")

    def test_resolver_cannot_depend_on_its_own_gated_consumer(self):
        producer = task("produce")
        gated = task("gated", ["produce"])
        resolver = task("resolver", ["gated"])
        resolver["resolves"] = [scope("produce")]
        graph = {"nodes": [producer, gated, resolver], "task_sets": [], "terminals": [selector("resolver")]}
        self.accepted(graph)
        # requires remains produce -> gated -> resolver: only the implicit
        # resolution/gate relationship makes the resulting work unsatisfiable.
        graph["nodes"][1]["gates"] = [scope("produce")]
        self.assertRegex("; ".join(self.errors(graph)), r"(?i)cycle|gate|resolver")

    def test_template_identity_is_unique_across_task_sets_and_static_nodes(self):
        from test_evidence_dag_journeys import selected_graph
        graph = selected_graph()
        self.accepted(graph)
        duplicate = copy.deepcopy(graph["task_sets"][0])
        duplicate["id"] = "other_buckets"
        graph["task_sets"].append(duplicate)
        self.assertRegex("; ".join(self.errors(graph)), r"(?i)duplicate|identity|unique|template")
        graph = selected_graph()
        graph["nodes"].append(task("investigate"))
        self.assertRegex("; ".join(self.errors(graph)), r"(?i)duplicate|identity|unique|template")


if __name__ == "__main__":
    unittest.main()
