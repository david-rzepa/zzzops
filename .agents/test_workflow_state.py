"""Validation contract for durable public-workflow coordination state."""

import copy
import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "plugins" / "zzzops" / "zzzops" / "workflow.py"
SPEC = importlib.util.spec_from_file_location("workflow_state_contract_subject", MODULE_PATH)
workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(workflow)


class WorkflowStateValidationTests(unittest.TestCase):
    sha = "sha256:" + "a" * 64

    def valid(self):
        return {
            "leases": {
                "plan:review": {
                    "token": "lease-token", "owner": "root-thread", "worker": "reviewer-2",
                    "selection": {"model": "review-model", "effort": "medium"},
                    "kind": "review", "input_hash": self.sha, "expires_at": 1_800_000_000,
                    "group": "review", "record_hash": self.sha, "review_hash": None,
                },
            },
            "receipts": {"request-1": {"hash": self.sha}},
            "workers": {
                "reviewer-2": {
                    "id": "reviewer-2", "group": "review",
                    "selection": {"model": "review-model", "effort": "medium"},
                },
            },
            "assessments": {
                "plan": {
                    "dimensions": {
                        "consequence": "bounded", "boundedness": "atomic",
                        "engineering_rigor": "structured",
                    },
                    "goal_spec": self.sha, "policy": self.sha,
                    "files": ["src/app.py", "tests/test_app.py"],
                },
            },
            "artifacts": {
                "implement": {
                    "commands": [{
                        "command": ["python3", "-m", "unittest"], "exit_code": 0,
                        "log_hash": "b" * 64, "log": ".zzzops/diagnostics/verify-token-0.log",
                    }],
                    "workspace": self.sha, "passed": True,
                },
            },
        }

    def test_accepts_exact_current_state_and_optional_assessment_files(self):
        self.assertEqual([], workflow.validate_state(self.valid()))
        without_files = self.valid()
        del without_files["assessments"]["plan"]["files"]
        self.assertEqual([], workflow.validate_state(without_files))

    def test_rejects_malformed_or_cross_bound_lease_state(self):
        mutations = [
            lambda state: state["leases"].update({"bad-key": state["leases"].pop("plan:review")}),
            lambda state: state["leases"]["plan:review"].update(kind="execute"),
            lambda state: state["leases"]["plan:review"].update(input_hash="a" * 64),
            lambda state: state["leases"]["plan:review"].update(worker=7),
            lambda state: state["leases"]["plan:review"].update(review_hash=self.sha),
            lambda state: state["leases"]["plan:review"]["selection"].update(extra="unexpected"),
        ]
        for mutation in mutations:
            candidate = self.valid()
            mutation(candidate)
            with self.subTest(candidate=candidate):
                self.assertTrue(workflow.validate_state(candidate))

    def test_rejects_malformed_worker_assessment_and_receipt_state(self):
        mutations = [
            lambda state: state["workers"]["reviewer-2"].update(id="someone-else"),
            lambda state: state["workers"]["reviewer-2"].update(group=" "),
            lambda state: state["assessments"]["plan"].update(goal_spec="sha256:short"),
            lambda state: state["assessments"]["plan"]["dimensions"].update(extra="unknown"),
            lambda state: state["assessments"]["plan"].update(files=["src/app.py", "src/app.py"]),
            lambda state: state["receipts"]["request-1"].update(hash="not-a-digest"),
            lambda state: state["receipts"].update({" ": {"hash": self.sha}}),
        ]
        for mutation in mutations:
            candidate = self.valid()
            mutation(candidate)
            with self.subTest(candidate=candidate):
                self.assertTrue(workflow.validate_state(candidate))

    def test_rejects_malformed_or_inconsistent_verification_proof(self):
        mutations = [
            lambda state: state["artifacts"]["implement"].update(workspace="missing"),
            lambda state: state["artifacts"]["implement"].update(passed=False),
            lambda state: state["artifacts"]["implement"].update(commands=[]),
            lambda state: state["artifacts"]["implement"]["commands"][0].update(exit_code=True),
            lambda state: state["artifacts"]["implement"]["commands"][0].update(log_hash=self.sha),
            lambda state: state["artifacts"]["implement"]["commands"][0].update(command=["python3", ""]),
        ]
        for mutation in mutations:
            candidate = self.valid()
            mutation(candidate)
            with self.subTest(candidate=candidate):
                self.assertTrue(workflow.validate_state(candidate))

    def test_rejects_unknown_or_non_object_collections(self):
        unknown = self.valid()
        unknown["cursor"] = {}
        self.assertTrue(workflow.validate_state(unknown))
        malformed = self.valid()
        malformed["leases"] = []
        self.assertTrue(workflow.validate_state(malformed))


if __name__ == "__main__":
    unittest.main()
