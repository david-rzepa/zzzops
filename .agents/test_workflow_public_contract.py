"""Negative-path coverage for the single public ZzzOps workflow entrypoint."""

from __future__ import annotations

import base64
import contextlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zlib

import test_zzzops as fixtures


z = fixtures.zzzops


class PublicWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)

    def run_main(self, *arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        argv = [str(fixtures.MODULE_PATH), "--repo", str(self.repo), *arguments]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = z.main()
        output = stdout.getvalue().strip()
        return status, json.loads(output), stderr.getvalue()

    def write_json(self, name, value):
        path = self.repo / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def assert_repair(self, status, response, expected):
        self.assertEqual(2, status)
        self.assertEqual("repair", response["next_steps"][0]["kind"])
        self.assertEqual("root", response["next_steps"][0]["assignment"])
        self.assertIn(expected, response["next_steps"][0]["reason"])

    def test_malformed_json_and_non_object_documents_are_rejected(self):
        malformed = self.repo / "malformed.json"
        malformed.write_text("{", encoding="utf-8")
        cases = (
            (("--intent", "execute", "--runtime", str(malformed)), "Expecting"),
            (("--intent", "execute", "--input", str(malformed)), "Expecting"),
            (("--intent", "execute", "--runtime", str(self.write_json("runtime-list.json", []))), "Runtime evidence must be a JSON object"),
            (("--intent", "execute", "--input", str(self.write_json("input-list.json", []))), "Submission must be a JSON object"),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                status, response, stderr = self.run_main(*arguments)
                self.assertEqual("", stderr)
                self.assert_repair(status, response, expected)

    def test_retired_subcommands_are_not_public_routes(self):
        for arguments in (
            ("--intent", "execute", "init", "inspect"),
            ("--intent", "execute", "feedback", "prepare"),
            ("--intent", "execute", "goal", "create"),
            ("--intent", "execute", "installation", "audit"),
            ("--intent", "execute", "portfolio"),
            ("--intent", "execute", "report", "list"),
        ):
            with self.subTest(arguments=arguments):
                status, response, stderr = self.run_main(*arguments)
                self.assertEqual("", stderr)
                self.assert_repair(status, response, "unrecognized arguments")

    def test_source_skill_must_be_authorized_for_intent(self):
        status, response, stderr = self.run_main(
            "--intent", "capture", "--source-skill", "$execute-zzzops",
        )
        self.assertEqual("", stderr)
        self.assert_repair(status, response, "source skill cannot initiate this intent")

    def test_preview_rejects_payload_before_context_or_mutation(self):
        payload = self.write_json("preview-input.json", {"operation": "adopt", "limit": 25})
        with (
            mock.patch.object(z._package, "package_status", return_value={"ok": True, "version": "1", "revision": "abc"}),
            mock.patch.object(z, "workflow_context_step") as context_step,
            mock.patch.object(z._workflow.Workflow, "mutate") as mutate,
        ):
            status, response, stderr = self.run_main("--intent", "preview", "--input", str(payload))
        self.assertEqual("", stderr)
        self.assert_repair(status, response, "Preview never accepts mutations")
        context_step.assert_not_called()
        mutate.assert_not_called()

    def public_batch(self, items, records):
        engine = SimpleNamespace(
            portfolio=mock.Mock(return_value=[]),
            read=mock.Mock(side_effect=lambda number: ({"number": number}, records[number])),
            mutate=mock.Mock(),
        )
        project = {"backend": "github_issues", "repository": {"identity": "owner/repo"}}
        with (
            mock.patch.object(z._package, "package_status", return_value={"ok": True, "version": "1", "revision": "abc"}),
            mock.patch.object(z._installation, "validation_status", return_value={"required": False}),
            mock.patch.object(z, "workflow_context_step", return_value=None),
            mock.patch.object(z, "reviewed_project_state", return_value=project),
            mock.patch.object(z._workflow, "Workflow", return_value=engine),
            mock.patch.object(z._workflow_admin, "handle", return_value=None),
            mock.patch.object(z, "apply_independent_batch") as apply_batch,
        ):
            result = z._workflow.public_run(
                z, self.repo, "execute", "$execute-zzzops", {},
                {"operation": "batch", "items": items}, None,
            )
        return result, engine, apply_batch

    def test_batch_validates_item_shapes_before_building_goal_set(self):
        malformed = (
            (["not-an-object"], "Each batch item must be a JSON object"),
            ([{"id": "a", "goal": [], "payload": {}}], "positive integer goal"),
            ([{"id": "a", "goal": True, "payload": {}}], "positive integer goal"),
            ([{"id": "a", "goal": 1, "payload": []}], "payload must be a JSON object"),
            ([{"id": [], "goal": 1, "payload": {}}], "non-empty string id"),
            ([{"id": "a", "goal": 1, "payload": {}, "depends_on": "b"}], "depends_on value must be a JSON array"),
        )
        for items, expected in malformed:
            with self.subTest(items=items), self.assertRaisesRegex(ValueError, expected):
                self.public_batch(items, {})

    def test_batch_rejects_transitively_related_goals(self):
        records = {
            1: {"key": 1, "parent": None, "depends_on": []},
            2: {"key": 2, "parent": None, "depends_on": [1]},
            3: {"key": 3, "parent": None, "depends_on": [2]},
        }
        items = [
            {"id": "ancestor", "goal": 1, "payload": {"operation": "heartbeat"}},
            {"id": "descendant", "goal": 3, "payload": {"operation": "heartbeat"}},
        ]
        with self.assertRaisesRegex(ValueError, "Dependent or parent/child goals"):
            self.public_batch(items, records)

    def test_batch_rejects_transitive_parent_ancestry(self):
        records = {
            1: {"key": 1, "parent": None, "depends_on": []},
            2: {"key": 2, "parent": 1, "depends_on": []},
            3: {"key": 3, "parent": 2, "depends_on": []},
        }
        items = [
            {"id": "parent", "goal": 1, "payload": {"operation": "heartbeat"}},
            {"id": "grandchild", "goal": 3, "payload": {"operation": "heartbeat"}},
        ]
        with self.assertRaisesRegex(ValueError, "Dependent or parent/child goals"):
            self.public_batch(items, records)


class ArtifactIntegrityContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.adapter = fixtures.FakeGoalTransitionAdapter({
            "number": 42,
            "title": "Artifact integrity",
            "body": "",
            "state": "open",
            "labels": [],
        })
        project = {"backend": "github_issues", "repository": {"identity": "owner/repo"}}
        with mock.patch.object(z, "GitHubGoalTransitionAdapter", return_value=self.adapter):
            self.engine = z._workflow.Workflow(z, self.repo, project, {})

    def test_artifact_round_trip_is_exact_and_missing_reference_is_rejected(self):
        content = {"summary": "Observed result", "evidence": ["probe passed"], "count": 3}
        artifact = self.engine.artifact(42, content)
        self.assertEqual(content, self.engine.read_artifact(42, artifact))

        missing = {"reference": "urn:sha256:" + "0" * 64, "hash": "sha256:" + "0" * 64}
        with self.assertRaisesRegex(ValueError, "Persist the phase artifact through operation=artifact"):
            self.engine.read_artifact(42, missing)

    def test_artifact_content_tampering_is_rejected(self):
        artifact = self.engine.artifact(42, {"summary": "reviewed evidence"})
        body = self.adapter.comments[0]["body"]
        encoded = re.search(r"```text\n([A-Za-z0-9+/=]+)\n```", body).group(1)
        stored = json.loads(zlib.decompress(base64.b64decode(encoded)))
        stored["content"] = {"summary": "altered evidence"}
        tampered = base64.b64encode(zlib.compress(json.dumps(
            stored, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8"))).decode("ascii")
        self.adapter.comments[0]["body"] = body.replace(encoded, tampered)

        with self.assertRaisesRegex(ValueError, "Stored artifact content changed"):
            self.engine.read_artifact(42, artifact)


if __name__ == "__main__":
    unittest.main()
