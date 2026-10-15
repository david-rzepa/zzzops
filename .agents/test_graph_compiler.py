"""Behavioral contract for deterministic correction-graph compilation."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

import test_evidence_dag_journeys as dag


ROOT = Path(__file__).parents[1]


def compiler():
    value = getattr(dag.z, "_graph_compiler", None)
    if value is None:
        raise AssertionError("graph compiler service is not registered")
    return value


def default_graph():
    # Reconstruct the tracked 16-node pre-correction family from the tracked
    # historical graph. Permanent tests must not depend on ignored goal files.
    legacy = json.loads((ROOT / ".agents/fixtures/legacy_evidence_dag.json").read_text())
    graph = {"nodes": copy.deepcopy(legacy["nodes"][:16]), "task_sets": [],
             "terminals": copy.deepcopy(legacy["terminals"])}
    nodes = {node["id"]: node for node in graph["nodes"]}
    for name, predecessor in {
        "decompose": "approve_understanding", "test_design": "review_decomposition",
        "implement": "review_test_design", "publication_context": "review_implement",
        "authorize_repository": "review_publication_context",
        "authorize_publication": "review_publication",
    }.items():
        nodes[name]["requires"] = [{"kind": "node", "goal": "#this", "node": predecessor}]
        nodes[name]["gates"] = []
    review = nodes["review_understanding"]
    review["prompt"] = ("Independently review the exact design, acceptance criteria and finite allocation. "
        "Submit authorization only when all required findings are resolved; bind the exact manifest Ref, "
        "task identities and current policy hash. Emit an explicit approved or changes_requested decision "
        "and the review report. A rejected review is evidence, never downstream approval.")
    review["outputs"] = {
        "authorization": {"type": "workspace_authorization", "schema": {"kind": "object", "fields": {
            "decision": {"kind": "enum", "values": ["approved"]}, "manifest": dag.REF_TYPE,
            "policy": {"kind": "string"}, "tasks": {"kind": "array", "items": {"kind": "object", "fields": {
                "generation": {"kind": "integer"}, "goal": {"kind": "integer"},
                "item": {"kind": "union", "variants": [{"kind": "string"}, {"kind": "null"}]},
                "node": {"kind": "string"}}}}}}},
        "review": dag.output("review_decision", {"kind": "object", "fields": {
            "decision": {"kind": "enum", "values": ["approved", "changes_requested"]},
            "report": {"kind": "string"}}}),
    }
    return graph


def shipped_graph():
    plan = json.loads((ROOT / "plugins/zzzops/zzzops/templates/project-goals/INIT_PLAN.json").read_text())
    return dag.z._workflow_section(plan, "workflow_adherence")["configuration"]["phase_dag"]


def all_defs(graph):
    return graph["nodes"] + [item["template"] for item in graph["task_sets"]]


def rejectable_count(graph):
    return sum(
        output.get("type") == "review_decision"
        and "changes_requested" in output.get("schema", {}).get("fields", {}).get("decision", {}).get("values", [])
        for node in all_defs(graph) for output in node["outputs"].values()
    )


class GraphCompilerTests(unittest.TestCase):
    def compile(self, graph, **kwargs):
        result = compiler().compile_graph(graph, local_goal=674, **kwargs)
        self.assertEqual({"graph", "source_hash", "target_hash", "version", "routes", "diagnostics"}, set(result))
        return result

    def test_registered_default_and_shipped_contracts_compile_before_results(self):
        for graph, expected in ((default_graph(), 6), (shipped_graph(), 7)):
            with self.subTest(expected=expected):
                source = copy.deepcopy(graph)
                result = self.compile(graph)
                self.assertEqual(expected, rejectable_count(source))
                self.assertEqual([], result["diagnostics"])
                self.assertEqual(source, graph, "compiler mutated its input")
                self.assertEqual(source["nodes"], result["graph"]["nodes"][:len(source["nodes"])])
                self.assertEqual(source["task_sets"], result["graph"]["task_sets"][:len(source["task_sets"])])
                self.assertEqual(source["terminals"], result["graph"]["terminals"])
                compiler().validate_recovery(result["graph"], local_goal=674)

    def test_compilation_is_canonical_idempotent_and_order_independent(self):
        graph = default_graph()
        first = self.compile(copy.deepcopy(graph))
        second = self.compile(copy.deepcopy(graph))
        repeated = self.compile(copy.deepcopy(first["graph"]))
        self.assertEqual(first, second)
        self.assertEqual(first["graph"], repeated["graph"])
        self.assertEqual(first["target_hash"], repeated["target_hash"])
        self.assertEqual([], repeated["routes"], "idempotent compilation appended routes")
        reversed_source = copy.deepcopy(graph)
        reversed_source["nodes"] = list(reversed(reversed_source["nodes"]))
        reverse = self.compile(reversed_source)
        self.assertEqual(
            sorted(route.get("key") for route in first["routes"]),
            sorted(route.get("key") for route in reverse["routes"]),
        )

    def test_generated_contracts_are_authority_free_exact_and_include_applicability(self):
        source = default_graph()
        result = self.compile(source)
        added_nodes = result["graph"]["nodes"][len(source["nodes"]):]
        added_sets = result["graph"]["task_sets"][len(source["task_sets"]):]
        encoded = json.dumps({"nodes": added_nodes, "task_sets": added_sets}, sort_keys=True)
        self.assertIn("applicability_assessment", encoded)
        self.assertIn("obligation_selections", encoded)
        self.assertIn("atomic", encoded)
        for node in added_nodes + [item["template"] for item in added_sets]:
            self.assertEqual([], node["executor"]["resources"])
            for permit in node.get("permits", []):
                self.assertIn(permit["type"], {"finding", "admission", "resolution", "supersession",
                                                "finding_registry", "applicability_assessment"})
                self.assertEqual("#this", permit["scope"]["subject"]["goal"])
        applicability_sets = [item for item in added_sets
            if item["source"].get("producer", {}).get("slot") == "obligation_selections"]
        self.assertTrue(applicability_sets)
        scoped_paths = {tuple(item["source"]["path"][:2]) for item in applicability_sets}
        self.assertGreaterEqual(len(scoped_paths), 2, "trusted targets were collapsed into one applicability scope")
        for item in applicability_sets:
            target_node, target_output = item["source"]["path"][:2]
            for permit in item["template"].get("permits", []):
                self.assertEqual(target_node, permit["scope"]["subject"]["node"])
                self.assertEqual(target_output, permit["scope"]["output"])

    def test_complete_custom_routes_are_preserved_and_legacy_upgrade_adds_once(self):
        graph = shipped_graph()
        first = self.compile(copy.deepcopy(graph))
        prior = copy.deepcopy(first["graph"])
        second = self.compile(prior)
        self.assertEqual(prior, second["graph"])
        self.assertEqual([], second["routes"])
        self.assertEqual([], second["diagnostics"])

    def test_ambiguous_tampered_and_colliding_contracts_fail_closed(self):
        cases = {}
        changed = default_graph()
        review = next(n for n in changed["nodes"] if n["id"] == "review_understanding")
        review["independent_of"] = []
        cases["changed trusted fingerprint"] = changed
        wrong_slot = default_graph()
        review = next(n for n in wrong_slot["nodes"] if n["id"] == "review_understanding")
        review["inputs"]["design"]["output"] = "allocation"
        cases["wrong output slot"] = wrong_slot
        cross_goal = default_graph()
        review = next(n for n in cross_goal["nodes"] if n["id"] == "review_understanding")
        review["inputs"]["design"]["producer"]["node"]["goal"] = 999
        cases["cross goal"] = cross_goal
        collision = default_graph()
        compiled = self.compile(copy.deepcopy(collision))["graph"]
        generated = compiled["nodes"][len(collision["nodes"]):]
        self.assertTrue(generated)
        occupied = copy.deepcopy(collision)
        impostor = copy.deepcopy(generated[0])
        impostor["prompt"] += " forged collision"
        occupied["nodes"].append(impostor)
        cases["occupied generated identity"] = occupied
        for label, graph in cases.items():
            with self.subTest(label=label):
                source = copy.deepcopy(graph)
                result = self.compile(graph)
                self.assertEqual(source, result["graph"], "failed compilation partially appended a route")
                self.assertTrue(result["diagnostics"])
                with self.assertRaisesRegex(Exception, r"(?i)recover|route|contract|ambig|target"):
                    compiler().validate_recovery(result["graph"], local_goal=674)

    def test_unknown_compiler_version_is_rejected(self):
        with self.assertRaisesRegex(Exception, r"(?i)version|support"):
            self.compile(default_graph(), compiler_version="unsupported-test-version")


if __name__ == "__main__":
    unittest.main()
