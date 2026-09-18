"""Public policy proposal and exact-approval lifecycle regressions."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_zzzops as fixtures


z = fixtures.zzzops


class WorkflowPolicyApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / ".zzzops").mkdir()

    def plan(self):
        template = fixtures.PLUGIN_ROOT / "zzzops" / "templates" / "project-goals" / "INIT_PLAN.json"
        plan = json.loads(template.read_text(encoding="utf-8"))
        plan["base_digest"] = z.initialization_base_digest(self.repo)
        plan["repository"] = {"identity": "synthetic/project", "remote": "local"}
        plan["github"] = {"usable": True}
        backend = next(section for section in plan["policy"]["sections"] if section["id"] == "backend")
        backend["instructions"] = "Store canonical goals in GitHub Issues."
        backend["configuration"]["authority"] = "github_issues"
        backend["configuration"]["repository_identity"] = "synthetic/project"
        backend["default_disposition"] = "changed"
        return plan

    def public(self, payload):
        with (
            mock.patch.object(z._package, "package_status", return_value={"ok": True, "version": "1", "revision": "abc"}),
            mock.patch.object(z._installation, "validation_status", return_value={"required": False}),
            mock.patch.object(z, "workflow_context_step", return_value={"id": "policy-review"}),
        ):
            return z._workflow.public_run(
                z, self.repo, "inspect", "$review-zzzops-policy",
                {"root_id": "root-thread"}, payload, None,
            )

    def approve(self, proposal_result, reviewer="approved-user"):
        step = proposal_result["next_steps"][0]
        return self.public({
            "operation": "policy_approve",
            "proposal_hash": step["hash"],
            "approved_by": reviewer,
        })

    def test_exact_public_approval_applies_and_confirms_real_project_state(self):
        proposed = self.public({"operation": "policy_propose", "plan": self.plan()})
        self.assertEqual("human_approval", proposed["next_steps"][0]["kind"])

        result = self.approve(proposed)

        self.assertEqual("checkpoint", result["next_steps"][0]["kind"])
        state = z.read_project_state(self.repo)[2]
        self.assertTrue(state["initialized"])
        self.assertEqual("approved-user", state["approval"]["reviewer"])
        self.assertEqual([], z.validate_project_state(state))
        self.assertEqual([], z.validate_project_artifacts(self.repo, state))

    def test_tampered_stored_proposal_is_rejected_before_policy_write(self):
        proposed = self.public({"operation": "policy_propose", "plan": self.plan()})
        path = Path(proposed["next_steps"][0]["proposal"])
        changed = json.loads(path.read_text(encoding="utf-8"))
        changed["charter"]["outcome"] = "Changed after review"
        path.write_text(json.dumps(changed), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "changed after review"):
            self.approve(proposed)
        self.assertFalse((self.repo / ".zzzops" / "POLICY.json").exists())

    def test_invalid_proposal_preserves_existing_reviewed_policy_files(self):
        first = self.public({"operation": "policy_propose", "plan": self.plan()})
        self.approve(first, reviewer="initial-reviewer")
        paths = [
            self.repo / ".zzzops" / "PROJECT.md",
            self.repo / ".zzzops" / "PROJECT_AUDIT.md",
            self.repo / ".zzzops" / "POLICY.json",
        ]
        before = {path: path.read_bytes() for path in paths}
        invalid = copy.deepcopy(self.plan())
        invalid["charter"]["outcome"] = ""

        with self.assertRaisesRegex(ValueError, "charter.outcome is required"):
            self.public({"operation": "policy_propose", "plan": invalid})

        self.assertEqual(before, {path: path.read_bytes() for path in paths})

    def test_public_approval_repairs_legacy_invalid_routing_state(self):
        first = self.public({"operation": "policy_propose", "plan": self.plan()})
        self.approve(first, reviewer="initial-reviewer")
        policy_path = self.repo / ".zzzops" / "POLICY.json"
        legacy = json.loads(policy_path.read_text(encoding="utf-8"))
        routing = next(section for section in legacy["policy"]["sections"] if section["id"] == "model_routing")
        routing["configuration"]["model_inventory"]["reviewed_pairs"] = "legacy-invalid-value"
        policy_path.write_text(json.dumps(legacy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.assertNotEqual([], z.validate_project_state(legacy))

        repaired = self.public({"operation": "policy_propose", "plan": self.plan()})
        self.approve(repaired, reviewer="repair-reviewer")

        state = z.read_project_state(self.repo)[2]
        self.assertTrue(state["initialized"])
        self.assertEqual("repair-reviewer", state["approval"]["reviewer"])
        self.assertEqual([], z.validate_project_state(state))
        self.assertEqual([], z.validate_project_artifacts(self.repo, state))


if __name__ == "__main__":
    unittest.main()
