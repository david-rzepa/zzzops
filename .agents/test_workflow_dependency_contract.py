"""Generic dependency freshness and empty-selection approval contracts.

Retained regression IDs now exercise public generic evidence. Domain phase
records are no longer a normal dependency evaluator in this suite.
"""

import json
import unittest

from test_evidence_dag import selector, task
from test_evidence_dag_journeys import DagFixture, RelationshipPublicTests, spec_input


class WorkflowDependencyContractTests(unittest.TestCase):
    def test_dependency_identity_binds_spec_and_semantic_results_only(self):
        # Generic evidence preserves freshness and explicit empty-set review gates.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.EvidenceDagPublicTests.test_semantic_input_drift_rejects_inflight_result_and_bookkeeping_does_not',
            'test_evidence_dag_journeys.RelationshipPublicTests.test_consumed_child_evidence_drift_rejects_acquired_worker',
        )

    def test_parent_aggregate_ignores_provenance_but_binds_results(self):
        # Generic evidence preserves freshness and explicit empty-set review gates.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.RelationshipPublicTests.test_unrelated_and_bookkeeping_changes_preserve_relevant_consumer',
            'test_evidence_dag_journeys.RelationshipPublicTests.test_consumed_child_evidence_drift_rejects_acquired_worker',
        )

    def test_zero_child_parent_requires_current_fully_approved_decompose_skip(self):
        # Generic evidence preserves freshness and explicit empty-set review gates.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.RelationshipPublicTests.test_known_empty_is_aggregate_not_unknown_and_does_not_manufacture_artifact',
            'test_phase_review_contract.GenericReviewGateTests.test_empty_selection_still_requires_configured_independent_review_and_root_consent',
        )


class InvalidatedAncestorGatePublicTests(DagFixture):
    """Consumer contract for additive generic-frontier invalidation diagnostics."""

    @staticmethod
    def identity(node, goal=100):
        return {"generation": 1, "goal": goal, "item": None, "node": node}

    def envelope_for(self, number):
        import re
        return json.loads(re.search(
            r"<!-- zzzops-goal\s*\n(.*?)\nzzzops-goal -->",
            self.provider.issues[number]["body"], re.S)[1])

    def put_envelope(self, number, envelope):
        self.provider.issues[number]["body"] = (
            "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->")
        self.provider.issues[number]["updated_at"] = (
            "2026-09-29T12:%02d:00Z" % envelope["revision"])

    def diagnostic_graph(self):
        ancestor = task("ancestor")
        ancestor["inputs"] = {"request": spec_input()}
        left = task("left", ["ancestor"])
        transitive = task("transitive", ["left"])
        right = task("right", ["ancestor"])
        never_executed = task("never_executed")
        return {"nodes": [ancestor, left, transitive, right, never_executed],
                "task_sets": [],
                "terminals": [selector("transitive"), selector("right"),
                              selector("never_executed")]}

    def finish_named(self, *names):
        for name in names:
            work = self.session.acquire(name)
            self.session.finish(work, {"value": name})

    def assert_same_diagnostics(self, response, expected):
        steps = response["next_steps"]
        self.assertTrue(steps)
        for step in steps:
            self.assertIn("invalidated_ancestor_gates", step)
            self.assertEqual(expected, step["invalidated_ancestor_gates"])

    def test_stale_ancestor_reports_ordered_transitive_and_branching_impact(self):
        self.install(self.diagnostic_graph())
        self.finish_named("ancestor", "left", "transitive", "right")
        self.replace_spec("A changed requirement invalidates the completed ancestor.")

        first = self.session.call(100)
        second = self.session.call(100)
        expected = [{
            "ancestor": self.identity("ancestor"),
            "reason": "stale_input",
            "affected_descendants": [
                {"blocked_task": self.identity("left"),
                 "dependencies": [self.identity("ancestor")], "parent_gates": []},
                {"blocked_task": self.identity("transitive"),
                 "dependencies": [self.identity("left")], "parent_gates": []},
                {"blocked_task": self.identity("right"),
                 "dependencies": [self.identity("ancestor")], "parent_gates": []},
            ],
        }]
        self.assertEqual(first, second, "Repeated public reads must be deterministic")
        self.assert_same_diagnostics(first, expected)

        kinds = {(step["node"]["node"], step["kind"])
                 for step in first["next_steps"] if "node" in step}
        self.assertIn(("ancestor", "execute"), kinds)
        self.assertIn(("never_executed", "execute"), kinds)
        for blocked in ("left", "transitive", "right"):
            self.assertIn((blocked, "dependency"), kinds)
        self.assertNotIn(self.identity("never_executed"), [
            item["blocked_task"] for gate in expected
            for item in gate["affected_descendants"]])

    def test_content_equivalent_evidence_keeps_empty_diagnostics_and_eligibility(self):
        self.install(self.diagnostic_graph())
        self.finish_named("ancestor", "left", "transitive", "right")
        before = self.session.call(100)
        self.replace_spec("Produce and review a value.")
        after = self.session.call(100)

        self.assert_same_diagnostics(before, [])
        self.assert_same_diagnostics(after, [])
        self.assertEqual(
            [(step.get("kind"), step.get("node")) for step in before["next_steps"]],
            [(step.get("kind"), step.get("node")) for step in after["next_steps"]],
        )
        self.assertEqual({"never_executed"}, {
            step["node"]["node"] for step in after["next_steps"]
            if step.get("kind") == "execute"})

    def test_unknown_reference_blocks_without_inventing_ancestor_impact(self):
        self.install(self.diagnostic_graph())
        self.finish_named("ancestor", "left", "transitive", "right")
        envelope, payload = self.payload()
        original_spec = payload["spec"]
        payload["spec"] = {"hash": "sha256:" + "f" * 64,
                           "uri": "urn:sha256:" + "f" * 64}
        envelope["payload"] = self.blob(payload)
        envelope["revision"] += 1
        self.provider.issues[100]["body"] = (
            "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->")

        response = self.session.call(100)
        self.assertRegex(json.dumps(response), r"(?i)unknown|reference|artifact")
        self.assert_same_diagnostics(response, [])

        payload["spec"] = {"hash": original_spec["hash"], "uri": "invalid"}
        envelope["payload"] = self.blob(payload)
        envelope["revision"] += 1
        self.put_envelope(100, envelope)
        invalid = self.session.call(100)
        self.assertRegex(json.dumps(invalid), r"(?i)invalid|reference|artifact")
        self.assert_same_diagnostics(invalid, [])

    def test_cross_goal_parent_gate_retains_qualified_relationship_identity(self):
        RelationshipPublicTests.setup_relationship_transport(self)
        parent = task("parent_source")
        parent["inputs"] = {"request": spec_input()}
        child = task("child")
        parent_gate = {"kind": "node", "goal": "#parent", "node": "parent_source"}
        child["requires"] = [parent_gate]
        child["inputs"] = {"parent": {
            "producer": {"node": parent_gate}, "output": "value", "path": [],
            "mode": "identity", "type": {"kind": "string"}}}
        graph = {"nodes": [parent, child], "task_sets": [],
                 "terminals": [selector("child")]}
        self.install(graph)
        RelationshipPublicTests.add_goal(self, 101, graph, 100)
        parent_work = self.session.acquire("parent_source", number=100)
        self.session.finish(parent_work, {"value": "parent version one"}, number=100)
        child_work = self.session.acquire("child", number=101)
        self.session.finish(child_work, {"value": "child"}, number=101)
        self.replace_spec("changed parent source")
        response = self.session.call(101)
        gates = response["next_steps"][0]["invalidated_ancestor_gates"]
        self.assertEqual(self.identity("parent_source", 100), gates[0]["ancestor"])
        self.assertEqual(self.identity("child", 101),
                         gates[0]["affected_descendants"][0]["blocked_task"])
        self.assertEqual([self.identity("parent_source", 100)],
                         gates[0]["affected_descendants"][0]["parent_gates"])


if __name__ == "__main__":
    unittest.main()
