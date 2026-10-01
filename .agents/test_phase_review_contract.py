"""Contract tests for review, approval, and ancestor phase evidence."""

import hashlib
import importlib.util
import copy
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "plugins" / "zzzops" / "zzzops" / "phase_evidence.py"
SPEC = importlib.util.spec_from_file_location("phase_review_contract_subject", MODULE_PATH)
phase_evidence = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(phase_evidence)


class PhaseReviewContractTests(unittest.TestCase):
    def envelope(self, phase, *, policy="policy-1", upstream_outputs=None):
        digest = phase_evidence.sha256_digest
        return phase_evidence.phase_input_envelope(
            phase, digest({"goal": 1}), digest({"policy": policy}), digest({"dag": 1}),
            repository={"identity": "owner/repo", "snapshot": {"branch": "dev"}},
            provider={"identity": "github", "snapshot": {"repository": "owner/repo"}},
            capabilities={"identity": "codex", "snapshot": {"models": ["test-model"]}},
            invocation={"intent": "execute", "inputs": {"goal": 1}},
            upstream_outputs=upstream_outputs,
            acceptance_criteria=["Goal works."],
        )

    def record(self, phase, envelope, output="output", *, status="completed", policy_rule=None):
        digest = phase_evidence.sha256_digest
        return {
            "status": status, "input_envelope": envelope, "input_hash": digest(envelope),
            "output": None if status == "not_required" else {
                "reference": "git:" + hashlib.sha1(output.encode()).hexdigest(),
                "hash": digest({"output": output}),
            },
            "verification": None, "routing": None,
            "selection": {"model": "test-model", "effort": "low"}, "actor": "worker-1",
            "not_required": (
                {"reason": "Policy permits skipping this phase.", "policy_rule": policy_rule}
                if status == "not_required" else None
            ),
            "test_design": None,
        }

    def artifact(self, label):
        digest = phase_evidence.sha256_digest
        return {"reference": "urn:sha256:" + hashlib.sha256(label.encode()).hexdigest(), "hash": digest({"artifact": label})}

    def graph(self):
        return {"phases": [{"id": "plan"}, {"id": "deliver", "depends_on": ["plan"]}]}

    def test_missing_evidence_and_legacy_shape_normalize_to_empty(self):
        self.assertEqual(phase_evidence.empty_phase_evidence(), phase_evidence.normalize_phase_evidence(None))
        legacy = {"schema_version": 2, "records": {}, "reviews": {}, "withdrawals": []}
        self.assertEqual({}, phase_evidence.normalize_phase_evidence(legacy)["human_approvals"])

    def test_independence_is_policy_controlled(self):
        # Replace active phase-slot scheduling with exact generic producer/review/root-gate evidence.
        # Replace active phase-slot scheduling with exact generic producer/review/root-gate evidence.
        # Replace active phase-slot scheduling with exact generic producer/review/root-gate evidence.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_phase_review_contract.GenericReviewGateTests.test_configured_independence_compares_actual_subject_actor',
        )

    def test_human_approval_is_additional_and_bound_to_review(self):
        # Replace active phase-slot scheduling with exact generic producer/review/root-gate evidence.
        # Replace active phase-slot scheduling with exact generic producer/review/root-gate evidence.
        # Replace active phase-slot scheduling with exact generic producer/review/root-gate evidence.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_phase_review_contract.GenericReviewGateTests.test_review_is_not_human_approval_and_root_binds_current_subject_and_review',
        )

    def test_human_approval_without_independent_review_binds_record_only(self):
        # Replace active phase-slot scheduling with exact generic producer/review/root-gate evidence.
        # Replace active phase-slot scheduling with exact generic producer/review/root-gate evidence.
        # Replace active phase-slot scheduling with exact generic producer/review/root-gate evidence.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_phase_review_contract.GenericReviewGateTests.test_root_gate_without_review_binds_exact_producer',
        )

    def test_review_outcomes_are_normalized_and_bound_by_human_approval(self):
        plan_input = self.envelope("plan")
        evidence = phase_evidence.record_phase_result(None, "plan", self.record("plan", plan_input), plan_input)
        outcomes = {
            "acceptance": "approved",
            "entropy": {"outcome": "follow_up", "evidence": "Goal 73 records the bounded cleanup.", "goals": [73]},
        }
        evidence = phase_evidence.record_phase_review(
            evidence, "plan", self.artifact("review with outcomes"), "reviewer-2", outcomes=outcomes,
        )
        self.assertEqual(outcomes, evidence["reviews"]["plan"]["outcomes"])
        evidence = phase_evidence.record_phase_approval(evidence, "plan", "root", "approval-with-outcomes")
        self.assertEqual(
            phase_evidence.sha256_digest(evidence["reviews"]["plan"]),
            evidence["human_approvals"]["plan"]["review_hash"],
        )

        tampered = copy.deepcopy(evidence)
        tampered["reviews"]["plan"]["outcomes"]["entropy"]["evidence"] = "Different follow-up evidence."
        with self.assertRaisesRegex(phase_evidence.PhaseEvidenceError, "human approval is stale"):
            phase_evidence.normalize_phase_evidence(tampered)

    def test_review_outcomes_reject_malformed_or_mismatched_evidence(self):
        plan_input = self.envelope("plan")
        evidence = phase_evidence.record_phase_result(None, "plan", self.record("plan", plan_input), plan_input)
        normalized = phase_evidence.record_phase_review(
            evidence, "plan", self.artifact("clean outcome"), "reviewer-2",
            outcomes={"acceptance": "approved", "entropy": {"outcome": "no_findings", "evidence": "Inspected the bounded scope.", "goals": []}},
        )
        self.assertEqual([], normalized["reviews"]["plan"]["outcomes"]["entropy"]["goals"])
        invalid = [
            ({"acceptance": "changes_requested", "entropy": {"outcome": "no_findings", "evidence": "Checked."}}, "match"),
            ({"acceptance": "approved", "entropy": {"outcome": "unknown", "evidence": "Checked."}}, "entropy outcome"),
            ({"acceptance": "approved", "entropy": {"outcome": "fixed", "evidence": ""}}, "entropy evidence"),
            ({"acceptance": "approved", "entropy": {"outcome": "follow_up", "evidence": "Deferred."}}, "positive integers"),
            ({"acceptance": "approved", "entropy": {"outcome": "follow_up", "evidence": "Deferred.", "goals": [0]}}, "positive integers"),
            ({"acceptance": "approved", "entropy": {"outcome": "no_findings", "evidence": "Checked.", "goals": [73]}}, "only allowed"),
        ]
        for index, (outcomes, message) in enumerate(invalid):
            with self.subTest(outcomes=outcomes), self.assertRaisesRegex(phase_evidence.PhaseEvidenceError, message):
                phase_evidence.record_phase_review(
                    evidence, "plan", self.artifact(f"invalid outcome {index}"), "reviewer-2", outcomes=outcomes,
                )

    def test_policy_authorized_not_required_decision_can_be_reviewed(self):
        # Superseded not_required phase mode becomes explicit current selected membership; unknown is not empty and retirement retains obligations.
        # Superseded not_required phase mode becomes explicit current selected membership; unknown is not empty and retirement retains obligations.
        # Superseded not_required phase mode becomes explicit current selected membership; unknown is not empty and retirement retains obligations.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.EvidenceDagPublicTests.test_selection_missing_empty_one_and_many_are_distinct',
            'test_evidence_dag_journeys.EvidenceDagPublicTests.test_authorized_member_retirement_retains_historical_debt_on_empty_and_reactivation',
        )

    def test_current_descendant_blocks_until_identical_ancestor_is_reapproved(self):
        # Replace active phase-slot scheduling with exact generic producer/review/root-gate evidence.
        # Replace active phase-slot scheduling with exact generic producer/review/root-gate evidence.
        # Replace active phase-slot scheduling with exact generic producer/review/root-gate evidence.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_phase_review_contract.GenericReviewGateTests.test_identical_output_cannot_bypass_current_ancestor_review_and_reapproval',
        )



# The helpers above construct/normalize predecessor evidence for conversion.
# Active review and approval behavior below uses only generic public tasks.
from test_evidence_dag_journeys import DagFixture, task, selector, subject_input, spec_input


class GenericReviewGateTests(DagFixture):
    def gate_graph(self, *, independent=True, review=True):
        producer = task("produce")
        producer["inputs"] = {"request": spec_input()}
        nodes = [producer]
        if review:
            inspector = task("inspect", ["produce"])
            inspector["inputs"] = {"subject": subject_input("produce")}
            inspector["independent_of"] = [selector("produce")] if independent else []
            nodes.append(inspector)
        approval = task("consent", ["inspect" if review else "produce"], role="root")
        approval["inputs"] = {"subject": subject_input("produce")}
        if review:
            approval["inputs"]["review"] = subject_input("inspect")
        finish = task("finish", ["consent"])
        finish["inputs"] = {"subject": subject_input("produce", mode="content")}
        nodes.extend([approval, finish])
        return {"nodes": nodes, "task_sets": [], "terminals": [selector("finish")]}

    def test_configured_independence_compares_actual_subject_actor(self):
        self.install(self.gate_graph())
        producer = self.produce()
        with self.assertRaisesRegex(AssertionError, r"(?i)independen|self.review"):
            work = self.session.acquire("inspect", actor=producer["bound_actor"])
            self.session.finish(work, {"value": "self-approved"})
        self.assertNotIn("consent", self.names())
        self.install(self.gate_graph(independent=False))
        producer = self.produce()
        work = self.session.acquire("inspect", actor=producer["bound_actor"])
        self.session.finish(work, {"value": "Policy allows this actor"})
        self.assertIn("consent", self.names())

    def test_review_is_not_human_approval_and_root_binds_current_subject_and_review(self):
        self.install(self.gate_graph())
        self.produce()
        self.session.finish(self.session.acquire("inspect", actor="independent-reviewer"), {"value": "inspected"})
        self.assertEqual({"consent"}, self.names())
        self.assertNotIn("finish", self.names())
        work = self.session.acquire("consent")
        self.assert_rejected(work, {"value": "approved exact review"}, {"actor": "independent-reviewer"}, r"(?i)root|actor|bound")
        result = self.result("consent")[1]
        refs = {binding["source"]["hash"] for binding in result["inputs"]}
        self.assertIn(self.produced("produce")["hash"], refs)
        self.assertIn(self.produced("inspect")["hash"], refs)
        self.assertEqual({"finish"}, self.names())

    def test_root_gate_without_review_binds_exact_producer(self):
        self.install(self.gate_graph(review=False))
        self.produce()
        self.assertEqual({"consent"}, self.names())
        self.session.finish(self.session.acquire("consent"), {"value": "approved exact producer"})
        result = self.result("consent")[1]
        self.assertEqual([self.produced("produce")["hash"]], [v["source"]["hash"] for v in result["inputs"]])
        self.assertEqual({"finish"}, self.names())

    def test_identical_output_cannot_bypass_current_ancestor_review_and_reapproval(self):
        self.install(self.gate_graph())
        self.produce()
        self.session.finish(self.session.acquire("inspect", actor="reviewer-a"), {"value": "inspected"})
        self.session.finish(self.session.acquire("consent"), {"value": "approved"})
        self.session.finish(self.session.acquire("finish"), {"value": "delivered"})
        prior = self.result("finish")[0]
        self.replace_spec("Reassess under changed substantive requirement")
        self.assertNotIn("finish", self.names())
        self.produce()  # exactly the same selected output bytes
        self.assertEqual({"inspect"}, self.names())
        self.session.finish(self.session.acquire("inspect", actor="reviewer-b"), {"value": "inspected"})
        self.assertEqual({"consent"}, self.names())
        self.assertFalse(any(step.get("kind") == "complete" for step in self.session.checkpoint(100)))
        self.session.finish(self.session.acquire("consent"), {"value": "approved"})
        self.assertEqual(prior, self.result("finish")[0], "Unchanged valid selected values can reuse descendant evidence after gates recover")
        self.assertTrue(any(step.get("kind") == "complete" for step in self.session.checkpoint(100)))


    def test_empty_selection_still_requires_configured_independent_review_and_root_consent(self):
        from test_evidence_dag_journeys import selected_graph, SELECTION_TYPE
        graph = selected_graph()
        graph["nodes"][0]["executor"]["role"] = "worker"
        chosen = {"producer": {"node": selector("select")}, "output": "chosen", "path": [],
                  "mode": "identity", "type": SELECTION_TYPE}
        review = task("inspect", ["select"])
        review["inputs"] = {"selection": chosen}
        review["independent_of"] = [selector("select")]
        consent = task("consent", ["inspect"], role="root")
        consent["inputs"] = {"selection": chosen, "review": subject_input("inspect")}
        graph["nodes"][1]["requires"].append(selector("consent"))
        graph["nodes"].extend([review, consent])
        self.install(graph)
        self.choose({})
        self.assertEqual({"inspect"}, self.names())
        self.session.finish(self.session.acquire("inspect", actor="independent-reviewer"), {"value": "Exact empty selection reviewed"})
        self.assertEqual({"consent"}, self.names())
        self.session.finish(self.session.acquire("consent"), {"value": "Root approves exact empty selection"})
        self.assertEqual({"synthesize"}, self.names())

if __name__ == "__main__":
    unittest.main()
