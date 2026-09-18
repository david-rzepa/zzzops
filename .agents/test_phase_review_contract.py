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
        plan_input, child_input = self.envelope("plan"), self.envelope("deliver")
        evidence = phase_evidence.record_phase_result(
            None, "plan", self.record("plan", plan_input), plan_input,
        )
        evidence = phase_evidence.record_phase_review(
            evidence, "plan", self.artifact("self review"), "worker-1", require_independent=False,
        )
        goal = {"status": "ready", "phase_evidence": evidence}
        strict = phase_evidence.derive_phase_steps(
            goal, self.graph(), {"plan": plan_input, "deliver": child_input},
            review_policy={"plan": {"review": {"independent": True}}},
        )
        self.assertEqual(["plan"], [item["phase"] for item in strict["review"]])
        self.assertEqual(["deliver"], [item["phase"] for item in strict["blocked"]])
        relaxed = phase_evidence.derive_phase_steps(
            goal, self.graph(), {"plan": plan_input, "deliver": child_input},
            review_policy={"plan": {"review": {"independent": False}}},
        )
        self.assertEqual(["deliver"], [item["phase"] for item in relaxed["execute"]])

    def test_human_approval_is_additional_and_bound_to_review(self):
        plan_input, child_input = self.envelope("plan"), self.envelope("deliver")
        evidence = phase_evidence.record_phase_result(None, "plan", self.record("plan", plan_input), plan_input)
        evidence = phase_evidence.record_phase_review(evidence, "plan", self.artifact("review"), "reviewer-2")
        policy = {"plan": {"review": {"independent": True, "human_approval": True}}}
        waiting = phase_evidence.derive_phase_steps(
            {"status": "ready", "phase_evidence": evidence}, self.graph(),
            {"plan": plan_input, "deliver": child_input}, review_policy=policy,
        )
        self.assertEqual([{"phase": "plan", "reason": "missing_human_approval"}], waiting["review"])
        self.assertEqual(["deliver"], [item["phase"] for item in waiting["blocked"]])
        with self.assertRaisesRegex(phase_evidence.PhaseEvidenceError, "root"):
            phase_evidence.record_phase_approval(evidence, "plan", "worker-1", "approval-42")
        approved = phase_evidence.record_phase_approval(evidence, "plan", "root", "approval-42")
        ready = phase_evidence.derive_phase_steps(
            {"status": "ready", "phase_evidence": approved}, self.graph(),
            {"plan": plan_input, "deliver": child_input}, review_policy=policy,
        )
        self.assertEqual(["deliver"], [item["phase"] for item in ready["execute"]])
        rereviewed = phase_evidence.record_phase_review(approved, "plan", self.artifact("new review"), "reviewer-3")
        self.assertNotIn("plan", rereviewed["human_approvals"])

    def test_human_approval_without_independent_review_binds_record_only(self):
        plan_input, child_input = self.envelope("plan"), self.envelope("deliver")
        evidence = phase_evidence.record_phase_result(None, "plan", self.record("plan", plan_input), plan_input)
        evidence = phase_evidence.record_phase_approval(evidence, "plan", "root", "approval-43")
        self.assertIsNone(evidence["human_approvals"]["plan"]["review_hash"])
        ready = phase_evidence.derive_phase_steps(
            {"status": "ready", "phase_evidence": evidence}, self.graph(),
            {"plan": plan_input, "deliver": child_input},
            review_policy={"plan": {"review": {"independent": False, "human_approval": True}}},
        )
        self.assertEqual(["deliver"], [item["phase"] for item in ready["execute"]])

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
        plan_input, child_input = self.envelope("plan"), self.envelope("deliver")
        skipped = self.record("plan", plan_input, status="not_required", policy_rule="atomic_goal")
        evidence = phase_evidence.record_phase_result(None, "plan", skipped, plan_input)
        evidence = phase_evidence.record_phase_review(evidence, "plan", self.artifact("skip review"), "reviewer-2")
        self.assertEqual(
            phase_evidence.sha256_digest(skipped["not_required"]),
            evidence["reviews"]["plan"]["decision_hash"],
        )
        goal = {"status": "ready", "phase_evidence": evidence}
        forbidden = phase_evidence.derive_phase_steps(
            goal, self.graph(), {"plan": plan_input, "deliver": child_input},
            review_policy={"plan": {"not_required": "never"}},
        )
        self.assertEqual(["plan"], forbidden["stale"])
        permitted = phase_evidence.derive_phase_steps(
            goal, self.graph(), {"plan": plan_input, "deliver": child_input},
            review_policy={"plan": {"not_required": "atomic_goal"}},
        )
        self.assertEqual(["deliver"], [item["phase"] for item in permitted["execute"]])

    def test_current_descendant_blocks_until_identical_ancestor_is_reapproved(self):
        graph = {"phases": [
            {"id": "plan"},
            {"id": "deliver", "depends_on": ["plan"]},
            {"id": "release", "depends_on": ["deliver"]},
        ]}
        plan_input = self.envelope("plan")
        plan_record = self.record("plan", plan_input, "stable-output")
        evidence = phase_evidence.record_phase_result(None, "plan", plan_record, plan_input)
        evidence = phase_evidence.record_phase_review(evidence, "plan", self.artifact("plan review"), "reviewer-2")
        child_input = self.envelope("deliver", upstream_outputs=[{
            "phase": "plan", "hash": plan_record["output"]["hash"],
        }])
        evidence = phase_evidence.record_phase_result(evidence, "deliver", self.record("deliver", child_input), child_input)
        evidence = phase_evidence.record_phase_review(evidence, "deliver", self.artifact("child review"), "reviewer-2")
        release_input = self.envelope("release", upstream_outputs=[{
            "phase": "deliver", "hash": evidence["records"]["deliver"]["output"]["hash"],
        }])
        evidence = phase_evidence.record_phase_result(evidence, "release", self.record("release", release_input), release_input)
        evidence = phase_evidence.record_phase_review(evidence, "release", self.artifact("release review"), "reviewer-2")

        changed_input = self.envelope("plan", policy="policy-2")
        stale = phase_evidence.derive_phase_steps(
            {"status": "ready", "phase_evidence": evidence}, graph,
            {"plan": changed_input, "deliver": child_input, "release": release_input},
        )
        self.assertEqual(["plan"], stale["stale"])
        self.assertEqual(["deliver", "release"], [item["phase"] for item in stale["blocked"]])
        reassessed = self.record("plan", changed_input, "stable-output")
        evidence = phase_evidence.record_phase_result(evidence, "plan", reassessed, changed_input)
        blocked = phase_evidence.derive_phase_steps(
            {"status": "ready", "phase_evidence": evidence}, graph,
            {"plan": changed_input, "deliver": child_input, "release": release_input},
        )
        self.assertEqual(["deliver", "release"], [item["phase"] for item in blocked["blocked"]])
        evidence = phase_evidence.record_phase_review(evidence, "plan", self.artifact("reassessment"), "reviewer-3")
        restored = phase_evidence.derive_phase_steps(
            {"status": "ready", "phase_evidence": evidence}, graph,
            {"plan": changed_input, "deliver": child_input, "release": release_input},
        )
        self.assertEqual([], restored["blocked"])
        self.assertEqual([], restored["execute"])
        self.assertEqual([], restored["review"])
        evidence = phase_evidence.record_phase_review(
            evidence, "plan", self.artifact("rejected reassessment"), "reviewer-3",
            decision="changes_requested",
        )
        rejected = phase_evidence.derive_phase_steps(
            {"status": "ready", "phase_evidence": evidence}, graph,
            {"plan": changed_input, "deliver": child_input, "release": release_input},
        )
        self.assertEqual(["plan"], [item["phase"] for item in rejected["execute"]])
        self.assertEqual(["deliver", "release"], [item["phase"] for item in rejected["blocked"]])


if __name__ == "__main__":
    unittest.main()
