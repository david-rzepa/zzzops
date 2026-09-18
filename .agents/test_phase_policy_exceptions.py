import hashlib
import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "plugins" / "zzzops" / "zzzops" / "phase_evidence.py"
SPEC = importlib.util.spec_from_file_location("phase_policy_exceptions", MODULE_PATH)
phase = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(phase)


class TestDesignPolicyExceptionTests(unittest.TestCase):
    def envelope(self, name, upstream=None):
        digest = phase.sha256_digest
        return phase.phase_input_envelope(
            name, digest({"goal": 1}), digest({"policy": 1}), digest({"dag": 1}),
            repository={"identity": "owner/repo", "snapshot": {}},
            provider={"identity": "github", "snapshot": {"repository": "owner/repo"}},
            capabilities={"identity": "runtime", "snapshot": {}},
            invocation={"intent": "execute", "inputs": {"goal": 1}},
            upstream_outputs=upstream, acceptance_criteria=["Behavior is covered."],
        )

    def record(self, name, envelope):
        digest = phase.sha256_digest
        output = {"reference": "git:" + hashlib.sha1(name.encode()).hexdigest(), "hash": digest({"output": name})}
        return {
            "status": "completed", "input_envelope": envelope, "input_hash": digest(envelope),
            "output": output,
            "verification": ({"reference": "urn:sha256:" + "5" * 64, "hash": digest({"verification": name})}
                             if name == "implement" else None),
            "routing": None, "selection": {"model": "worker", "effort": "medium"},
            "actor": "worker-a", "not_required": None,
            "test_design": ({
                "baseline_failure": {"reference": "urn:sha256:" + "2" * 64, "hash": digest({"baseline": 1})},
                "coverage": [{
                    "criterion": "Behavior is covered.",
                    "test": {"reference": "git:" + "3" * 40, "hash": digest({"test": 1})},
                    "exclusion": None,
                }],
            } if name == "test_design" else None),
        }

    def evidence_and_implementation(self):
        design_input = self.envelope("test_design")
        design = self.record("test_design", design_input)
        evidence = phase.record_phase_result(None, "test_design", design, design_input)
        implement_input = self.envelope(
            "implement", upstream=[{"phase": "test_design", "hash": design["output"]["hash"]}],
        )
        return evidence, implement_input, self.record("implement", implement_input)

    def policy(self, *, independent, human_approval=False, not_required="never"):
        return {"test_design": {
            "not_required": not_required,
            "review": {"independent": independent, "human_approval": human_approval},
        }}

    def test_default_remains_strict_without_policy(self):
        evidence, envelope, implementation = self.evidence_and_implementation()
        with self.assertRaisesRegex(phase.PhaseEvidenceError, "approved test-design review"):
            phase.record_phase_result(evidence, "implement", implementation, envelope)

    def test_explicit_policy_can_disable_independent_test_design_review(self):
        evidence, envelope, implementation = self.evidence_and_implementation()
        result = phase.record_phase_result(
            evidence, "implement", implementation, envelope,
            phase_policy=self.policy(independent=False),
        )
        self.assertIn("implement", result["records"])

    def test_explicit_human_approval_and_requested_changes_still_block(self):
        evidence, envelope, implementation = self.evidence_and_implementation()
        with self.assertRaisesRegex(phase.PhaseEvidenceError, "human approval"):
            phase.record_phase_result(
                evidence, "implement", implementation, envelope,
                phase_policy=self.policy(independent=False, human_approval=True),
            )
        artifact = {"reference": "urn:sha256:" + "4" * 64, "hash": phase.sha256_digest({"review": 1})}
        changed = phase.record_phase_review(
            evidence, "test_design", artifact, "reviewer", decision="changes_requested",
        )
        with self.assertRaisesRegex(phase.PhaseEvidenceError, "requested test-design changes"):
            phase.record_phase_result(
                changed, "implement", implementation, envelope,
                phase_policy=self.policy(independent=False),
            )

    def test_unavailable_test_design_skip_cannot_be_enabled_by_helper_argument(self):
        evidence, envelope, implementation = self.evidence_and_implementation()
        with self.assertRaisesRegex(phase.PhaseEvidenceError, "phase policy is invalid"):
            phase.record_phase_result(
                evidence, "implement", implementation, envelope,
                phase_policy=self.policy(independent=False, not_required="atomic_goal"),
            )


if __name__ == "__main__":
    unittest.main()
