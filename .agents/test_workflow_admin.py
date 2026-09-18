"""Tests for public administrative workflow intent handlers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "plugins" / "zzzops" / "zzzops" / "workflow_admin.py"
SPEC = importlib.util.spec_from_file_location("zzzops_workflow_admin_test", MODULE)
assert SPEC and SPEC.loader
admin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(admin)


class WorkflowAdminTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.project = {"policy": {"sections": []}}
        self.api = SimpleNamespace(
            workflow_instruction=mock.Mock(side_effect=lambda source: {"path": source, "sha256": "a" * 64}),
            load_execution_reports=mock.Mock(return_value=[{"id": "report-" + "1" * 64}]),
            list_diagnostics=mock.Mock(return_value={"count": 1, "diagnostics": [{"id": "2" * 64}]}),
            prepare_feedback=mock.Mock(), submit_feedback=mock.Mock(),
            list_entropy_observations=mock.Mock(return_value={"enabled": True, "observations": [{"category": "documentation"}]}),
            timing_suggestion=mock.Mock(return_value={"schema_version": 1, "available": False, "reason": "missing"}),
            _goals=SimpleNamespace(
                GOAL_CREATE_SCHEMA_VERSION=7,
                GOAL_CREATE_FIELDS={"schema_version", "title", "body", "labels", "goal"},
            ),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_unowned_source_returns_none(self) -> None:
        self.assertIsNone(admin.handle(self.api, self.repo, self.project, "$execute-zzzops", None, None))

    def test_capture_returns_the_actual_public_goal_schema_without_writing(self) -> None:
        result = admin.handle(self.api, self.repo, self.project, admin.CAPTURE_SOURCE, None, None)
        step = result["next_steps"][0]
        self.assertEqual("capture", step["kind"])
        self.assertEqual(7, step["schema"]["schema_version"])
        self.assertEqual(sorted(self.api._goals.GOAL_CREATE_FIELDS), step["schema"]["fields"])
        self.assertEqual(7, step["request_schema_version"])
        self.assertEqual(sorted(self.api._goals.GOAL_CREATE_FIELDS), step["request_fields"])
        self.assertEqual({"operation": "capture_propose", "request": "<validated goal-create request>"}, step["submission"])
        self.assertIsNone(admin.handle(
            self.api, self.repo, self.project, admin.CAPTURE_SOURCE, None,
            {"operation": "capture", "request": {}},
        ))

    def test_suggestion_returns_read_only_evidence_and_only_actionable_diagnostic(self) -> None:
        result = admin.handle(self.api, self.repo, self.project, admin.SUGGEST_SOURCE, None, None)
        evidence = result["next_steps"][0]["evidence"]
        self.assertEqual("missing", evidence["timing_status"])
        self.assertNotIn("diagnostic", evidence)
        self.api.list_entropy_observations.assert_called_once_with(self.repo, self.project)
        self.api.timing_suggestion.assert_called_once_with(self.repo)

        timing = {"schema_version": 1, "available": True, "reason": "available", "dominant_phase": "github_discovery"}
        self.api.timing_suggestion.return_value = timing
        evidence = admin.handle(self.api, self.repo, self.project, admin.SUGGEST_SOURCE, None, None)["next_steps"][0]["evidence"]
        self.assertEqual(timing, evidence["diagnostic"])
        with self.assertRaisesRegex(ValueError, "read-only"):
            admin.handle(self.api, self.repo, self.project, admin.SUGGEST_SOURCE, None, {"operation": "apply"})

    def test_feedback_inventory_is_safe_readiness_evidence(self) -> None:
        result = admin.handle(self.api, self.repo, self.project, admin.FEEDBACK_SOURCE, None, None)
        step = result["next_steps"][0]
        self.assertEqual("feedback_prepare", step["kind"])
        self.assertEqual(self.api.load_execution_reports.return_value, step["evidence"]["reports"])
        self.assertEqual(self.api.list_diagnostics.return_value, step["evidence"]["timing_diagnostics"])
        self.assertEqual("feedback_prepare", step["submission"]["operation"])

    def test_feedback_prepare_returns_exact_preview_and_bound_followup(self) -> None:
        preview = {
            "target": "david-rzepa/zzzops", "title": "ZzzOps feedback", "labels": ["zzzops-feedback"],
            "body": "exact body", "report_ids": ["report-" + "1" * 64], "diagnostic_ids": [],
            "digest": "sha256:" + "3" * 64,
        }
        self.api.prepare_feedback.return_value = preview
        request = {
            "operation": "feedback_prepare", "prompt": "Please improve this.",
            "report_ids": preview["report_ids"], "diagnostic_id": None, "diagnostic_runtime": None,
        }
        result = admin.handle(self.api, self.repo, self.project, admin.FEEDBACK_SOURCE, None, request)
        step = result["next_steps"][0]
        self.assertEqual("human_approval", step["kind"])
        self.assertEqual(preview, step["preview"])
        self.assertEqual(preview["digest"], step["submission"]["confirmation"])
        self.assertEqual("<explicit human approver>", step["submission"]["approved_by"])
        self.api.prepare_feedback.assert_called_once_with(
            self.repo, request["prompt"], request["report_ids"],
            diagnostic_id=None, diagnostic_runtime=None,
        )

    def test_feedback_submit_requires_root_and_explicit_human_approval(self) -> None:
        request = {
            "operation": "feedback_submit", "prompt": "Please improve this.", "report_ids": None,
            "diagnostic_id": None, "diagnostic_runtime": None,
            "confirmation": "sha256:" + "3" * 64, "approved_by": "person@example.test",
        }
        with self.assertRaisesRegex(ValueError, "root agent"):
            admin.handle(self.api, self.repo, self.project, admin.FEEDBACK_SOURCE, None, request)
        self.api.submit_feedback.assert_not_called()

        placeholder = {**request, "approved_by": "<explicit human approver>"}
        with self.assertRaisesRegex(ValueError, "explicit human approval"):
            admin.handle(self.api, self.repo, self.project, admin.FEEDBACK_SOURCE, {"root_id": "root"}, placeholder)
        self.api.submit_feedback.assert_not_called()

    def test_feedback_submit_uses_existing_digest_guarded_provider_boundary(self) -> None:
        request = {
            "operation": "feedback_submit", "prompt": "Please improve this.",
            "report_ids": ["report-" + "1" * 64], "diagnostic_id": "2" * 64,
            "diagnostic_runtime": {"agent": "codex", "platform": "linux", "python": "3.14"},
            "confirmation": "sha256:" + "3" * 64, "approved_by": "person@example.test",
        }
        submitted = {"submitted": True, "url": "https://github.com/david-rzepa/zzzops/issues/1"}
        self.api.submit_feedback.return_value = submitted
        result = admin.handle(
            self.api, self.repo, self.project, admin.FEEDBACK_SOURCE, {"root_id": "root-thread"}, request,
        )
        self.api.submit_feedback.assert_called_once_with(
            self.repo, request["prompt"], request["confirmation"], request["report_ids"],
            diagnostic_id=request["diagnostic_id"], diagnostic_runtime=request["diagnostic_runtime"],
        )
        self.assertEqual(submitted, result["next_steps"][0]["result"])

        self.api.submit_feedback.reset_mock()
        self.api.submit_feedback.side_effect = ValueError("feedback confirmation does not match the exact current payload")
        with self.assertRaisesRegex(ValueError, "exact current payload"):
            admin.handle(
                self.api, self.repo, self.project, admin.FEEDBACK_SOURCE, {"root_id": "root-thread"}, request,
            )


if __name__ == "__main__":
    unittest.main()
