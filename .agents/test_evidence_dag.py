"""Approved #498 graph grammar against the production policy boundary.

These fixtures contain data only. No prototype evaluator or reference scheduler
is imported. Every rejection first proves acceptance of its unmodified control,
so an unsupported-schema error cannot count as evidence for a specific guard.
"""

from __future__ import annotations

import copy
import json
import unittest
from unittest import mock

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

    def test_shipped_default_is_one_valid_generic_graph(self):
        plan = json.loads((fixtures.PLUGIN_ROOT / "zzzops/templates/project-goals/INIT_PLAN.json").read_text())
        graph = next(section for section in plan["policy"]["sections"] if section["id"] == "workflow_adherence")["configuration"]["phase_dag"]
        self.assertEqual({"nodes", "task_sets", "terminals"}, set(graph), "Shipped active default must use the same generic Graph")
        self.accepted(graph)
        self.assertTrue(graph["nodes"])
        self.assertTrue(graph["terminals"])

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

    def test_reserved_host_policy_input_cannot_be_declared(self):
        self.rejected_mutation(
            lambda g: g["nodes"][0]["inputs"].update(__policy=subject_input("produce")),
            r"(?i)reserved|host|slot",
        )

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

    def test_symbolic_selectors_are_first_class_and_case_sensitive(self):
        for goal in ("#this", "#parent", "#children", 987):
            with self.subTest(goal=goal):
                graph = review_graph()
                graph["nodes"][1]["requires"] = [{**selector("produce"), "goal": goal}]
                self.accepted(graph)
                for invalid in ("#This", "#PARENT", "#child", "100", 0, -1, True, 1.5):
                    broken = copy.deepcopy(graph)
                    broken["nodes"][1]["requires"][0]["goal"] = invalid
                    self.assertRegex("; ".join(self.errors(broken)), r"(?i)selector|goal|identity|reference")

    def test_symbolic_static_member_and_join_in_all_reference_positions(self):
        # External declarations resolve at runtime; static validation checks the
        # selector grammar without guessing unknown relationship membership.
        for kind in ("node", "member", "join"):
            selected = ({"kind": "node", "node": "remote"} if kind == "node" else
                        {"kind": "member", "expansion": "remote_set", "item": "a", "generation": "current"}
                        if kind == "member" else {"kind": "join", "expansion": "remote_set"})
            selected["goal"] = "#children"
            for position in ("requires", "independent_of", "gates", "resolves", "permits", "inputs", "authority", "terminals"):
                with self.subTest(kind=kind, position=position):
                    node = task("local")
                    graph = {"nodes": [node], "task_sets": [], "terminals": [selector("local")]}
                    scoped = {"subject": selected, "output": "value"}
                    if position in ("requires", "independent_of"):
                        node[position] = [selected]
                    elif position in ("gates", "resolves"):
                        node[position] = [scoped]
                    elif position == "permits":
                        node[position] = [{"type": "finding", "scope": scoped}]
                    elif position == "inputs":
                        value_type = {"kind": "string"}
                        if kind == "join":
                            value_type = {"kind": "map", "values": value_type}
                        node[position] = {"children": {**subject_input("remote"), "producer": {"node": selected},
                                                      "type": {"kind": "map", "values": value_type}}}
                    elif position == "authority":
                        node["executor"]["authority"] = scoped
                    else:
                        graph[position] = [selected]
                    self.accepted(graph)
                    before = copy.deepcopy(graph)
                    self.errors(graph)
                    self.assertEqual(before, graph, "Validation must retain symbolic selectors")

    def test_child_selection_cannot_filter_required_decomposition_membership(self):
        self.rejected_mutation(lambda graph: graph.update(child_selection=subject_input("produce")),
                               r"(?i)field|unknown|child_selection")

    def test_relationship_context_is_reserved_for_host_issuance(self):
        self.rejected_mutation(lambda graph: graph["nodes"][0]["outputs"]["value"].update(type="relationship_context"),
                               r"(?i)reserved|host|relationship")


phase = fixtures.zzzops._phase_evidence


class Goal499DefaultGraphContractTests(unittest.TestCase):
    """Observable contract for the reviewed #499 default workflow."""

    @classmethod
    def setUpClass(cls):
        plan = json.loads(
            (fixtures.PLUGIN_ROOT / "zzzops/templates/project-goals/INIT_PLAN.json").read_text()
        )
        cls.graph = next(
            section for section in plan["policy"]["sections"]
            if section["id"] == "workflow_adherence"
        )["configuration"]["phase_dag"]
        cls.nodes = {node["id"]: node for node in cls.graph["nodes"]}
        cls.sets = {item["id"]: item for item in cls.graph["task_sets"]}
        cls.set_templates = {
            item["template"]["id"]: item for item in cls.graph["task_sets"]
        }

    def node(self, name):
        self.assertTrue(name in self.nodes, f"Shipped #499 graph is missing node {name!r}")
        return self.nodes[name]

    def task_set(self, template):
        self.assertTrue(template in self.set_templates,
                        f"Shipped #499 graph is missing expansion template {template!r}")
        return self.set_templates[template]

    def test_default_uses_reviewed_discovery_delivery_and_feedback_vocabulary(self):
        required = {
            "requirements", "spec", "approve_spec", "decompose",
            "decomposition_review", "test_design", "test_verification",
            "test_design_review", "implement", "implementation_verification",
            "migration_verification", "integration_verification", "publish",
            "integrate", "integration_feedback_review", "authorize_merge", "merge",
        }
        self.assertEqual(set(), required - set(self.nodes),
                         "Every concrete #499 phase must ship in the one default graph")
        obsolete = {
            "understand", "review_understanding", "approve_understanding",
            "review_decomposition", "review_test_design", "review_implement",
            "publication_context", "observe_publication", "observe_merge",
        }
        self.assertEqual(set(), obsolete & set(self.nodes),
                         "The old linear phase vocabulary must not remain active")
        self.assertEqual([], z._policy._workflow_phase_dag_errors(self.graph))

    def test_only_root_owns_human_answers_approvals_publication_and_merge(self):
        for name in ("requirements", "approve_spec", "publish", "authorize_merge", "merge"):
            with self.subTest(node=name):
                self.assertEqual("root", self.node(name)["executor"]["role"])
        for name in ("spec", "decompose", "decomposition_review", "integrate",
                     "integration_feedback_review"):
            with self.subTest(node=name):
                self.assertEqual("worker", self.node(name)["executor"]["role"])
        requirements = json.dumps(self.node("requirements")).casefold()
        for contract in ("question", "id", "provenance", "blocking", "status",
                         "answer", "revision", "settled"):
            self.assertIn(contract, requirements)
        self.assertRegex(requirements, r"stable|same id|preserve.{0,40}id")
        self.assertRegex(requirements, r"do not.{0,40}(repeat|re-ask)|no repeated")

    def test_review_expansions_declare_required_members_and_independent_templates(self):
        expected = {
            "spec_review": {"acceptance_contracts", "maintainability_entropy"},
            "implementation_review": {"correctness_acceptance", "maintainability_entropy"},
            "integration_review": {"acceptance_contracts", "maintainability_entropy"},
        }
        for family, required_members in expected.items():
            with self.subTest(family=family):
                task_set = self.task_set(family)
                encoded = json.dumps(task_set).casefold()
                for member in required_members:
                    self.assertIn(member, encoded)
                self.assertIn("independent_of", task_set["template"])
                self.assertIn("finding", encoded)
                self.assertIn("non-applic", encoded)
        self.assertTrue("spec_investigation" in self.set_templates,
                        "Shipped #499 graph is missing spec investigation expansion")
        self.assertTrue("child_delivery" in self.nodes,
                        "Shipped #499 graph is missing relationship-bound child delivery observer")

    def test_delivery_topologies_encode_atomic_leaf_and_child_to_parent_direction(self):
        decomposition = json.dumps(self.node("decompose")).casefold()
        self.assertIn("leaf", decomposition)
        self.assertIn("composition", decomposition)
        self.assertIn("atomic", decomposition)
        self.assertIn("indivisible", decomposition)
        for proof in ("no independently deliverable", "no useful parallel"):
            self.assertIn(proof, decomposition,
                          "Atomic non-applicability must demand the reviewed proof, not a shortcut")
        review = json.dumps(self.node("decomposition_review")).casefold()
        self.assertIn("atomic", review)
        self.assertRegex(review, r"reject|unjustified|non-applic")
        child_template = self.node("child_delivery")
        child = json.dumps(child_template).casefold()
        self.assertIn("delivery_result", child)
        self.assertEqual("#children", child_template["inputs"]["children"]["producer"]["node"]["goal"])
        self.assertEqual("merge", child_template["inputs"]["children"]["producer"]["node"]["node"])
        self.assertEqual("identity", child_template["inputs"]["children"]["mode"])
        self.assertEqual("child_delivery_join", child_template["outputs"]["value"]["type"])
        self.assertNotRegex(child, r'producer[^}]+(?:publish|integrate|merge)[^}]+#parent')
        for forbidden in ("parent publication", "parent integration", "parent merge"):
            self.assertNotIn(forbidden, child)
        self.assertEqual([], child_template["executor"]["resources"],
                         "Child delivery observation cannot own either workspace")
        integration = json.dumps(self.node("integration_verification")).casefold()
        self.assertRegex(integration, r"parent.{0,80}(owned|workspace)")
        self.assertRegex(integration, r"child.{0,80}(read.only|immutable|do not edit)")

    def test_migration_evidence_and_review_are_upstream_of_publication(self):
        publish = json.dumps(self.node("publish")).casefold()
        graph = json.dumps(self.graph).casefold()
        self.assertIn("migration_verification", graph)
        self.assertIn("migration_review", graph)
        self.assertIn("migration", publish)
        self.assertRegex(publish, r"review|approved|resolution")

    def test_feedback_assessment_is_fresh_before_root_merge_authorization(self):
        assessment = json.dumps(self.node("integrate")).casefold()
        approval = json.dumps(self.node("authorize_merge")).casefold()
        for word in ("actionable", "obsolete", "ambiguous", "provenance"):
            self.assertIn(word, assessment)
        self.assertIn("integration_feedback_review", approval)
        self.assertRegex(approval, r"fresh|current")


class ProjectionCacheTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(phase, "_PROJECTION_CACHE"), "Missing bounded projection-cache implementation")
        phase._PROJECTION_CACHE.clear()
        self.addCleanup(phase._PROJECTION_CACHE.clear)
        self.graph = {'task_sets': [{}]}

    def test_key_preserves_types_order_and_deep_output_independence(self):
        def project(graph, payload, context):
            return {'items': [(type(k).__name__, type(v).__name__, repr(v))
                              for k, v in context.items()], 'nested': [payload]}
        pairs = [({1: 'x'}, {'1': 'x'}), ({'x': 1}, {'x': True}),
                 ({'x': []}, {'x': ()}), ({'x': b'x'}, {'x': 'x'}),
                 ({'a': 1, 'b': 2}, {'b': 2, 'a': 1})]
        with mock.patch.object(phase, '_derive_task_steps', side_effect=project) as evaluate:
            for left, right in pairs:
                with self.subTest(left=left, right=right):
                    phase._PROJECTION_CACHE.clear()
                    before = evaluate.call_count
                    for context in (left, right):
                        expected = project(self.graph, {}, context)
                        self.assertEqual(expected, phase.derive_task_steps(self.graph, {}, context))
                        self.assertEqual(expected, phase.derive_task_steps(self.graph, {}, context))
                    self.assertEqual(before + 2, evaluate.call_count)
            result = phase.derive_task_steps(self.graph, {'value': [1]}, {})
            result['nested'][0]['value'].append(2)
            self.assertEqual([1], phase.derive_task_steps(self.graph, {'value': [1]}, {})['nested'][0]['value'])

    def test_changed_inputs_and_in_call_mutation_never_reuse_stale_result(self):
        def project(graph, payload, context):
            return {'value': graph['value'] + payload['value'] + context['artifacts']['value']}
        graph = {**self.graph, 'value': 1}
        payload, context = {'value': 2}, {'artifacts': {'value': 3}}
        with mock.patch.object(phase, '_derive_task_steps', side_effect=project) as evaluate:
            for target in (graph, payload, context['artifacts']):
                phase.derive_task_steps(graph, payload, context)
                target['value'] += 10
                before = evaluate.call_count
                self.assertEqual(project(graph, payload, context), phase.derive_task_steps(graph, payload, context))
                self.assertEqual(before + 1, evaluate.call_count)
        phase._PROJECTION_CACHE.clear()
        def mutate(graph, payload, context):
            payload['value'] += 1
            return {'value': payload['value']}
        with mock.patch.object(phase, '_derive_task_steps', side_effect=mutate):
            phase.derive_task_steps(graph, payload, context)
        self.assertFalse(phase._PROJECTION_CACHE)

    def test_errors_callbacks_and_fixed_graphs_bypass_reuse(self):
        with mock.patch.object(phase, '_derive_task_steps', side_effect=ValueError('invalid')) as evaluate:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, 'invalid'):
                    phase.derive_task_steps(self.graph, {}, {})
            self.assertEqual(2, evaluate.call_count)
        self.assertFalse(phase._PROJECTION_CACHE)
        with mock.patch.object(phase, '_derive_task_steps', return_value={}) as evaluate:
            for _ in range(2):
                phase.derive_task_steps(self.graph, {}, {'callback': lambda: None})
                phase.derive_task_steps({'task_sets': []}, {}, {})
            self.assertEqual(4, evaluate.call_count)
        self.assertFalse(phase._PROJECTION_CACHE)

    def test_cache_limits_entries_and_total_serialized_bytes(self):
        with mock.patch.object(phase, '_derive_task_steps', return_value={'value': 'x' * 128}):
            for n in range(10):
                phase.derive_task_steps(self.graph, {'n': n}, {})
            self.assertEqual(4, len(phase._PROJECTION_CACHE))
            phase._PROJECTION_CACHE.clear()
            with mock.patch.object(phase, '_PROJECTION_CACHE_BYTES', 512):
                for n in range(10):
                    phase.derive_task_steps(self.graph, {'n': n}, {})
                    self.assertLessEqual(sum(len(k) + len(v) for k, v in phase._PROJECTION_CACHE.items()), 512)
                before = dict(phase._PROJECTION_CACHE)
                phase.derive_task_steps(self.graph, {'huge': 'x' * 1024}, {})
                self.assertEqual(before, phase._PROJECTION_CACHE)


if __name__ == "__main__":
    unittest.main()
