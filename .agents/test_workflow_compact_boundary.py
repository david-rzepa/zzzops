import importlib.util
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "plugins" / "zzzops" / "zzzops" / "zzzops.py"
SPEC = importlib.util.spec_from_file_location("zzzops_compact_boundary", MODULE_PATH)
zzzops = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(zzzops)


class CompactWorkflowBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.response = {"next_steps": [{
            "kind": "perform", "goal": 543,
            "node": {"goal": 543, "node": "implement", "item": None, "generation": 1},
            "lease": {
                "token": "lease-1", "worker": "worker-1",
                "acquisition": {
                    "input_hash": "sha256:" + "1" * 64,
                    "files": {"src/a.py": "sha256:" + "2" * 64, "tests/a.py": "sha256:" + "3" * 64},
                    "inputs": [{"name": "design", "source": {"hash": "sha256:" + "4" * 64}}],
                },
            },
            "submission": {"operation": "submit", "node": {"goal": 543, "node": "implement", "item": None, "generation": 1}},
            "unused_contract": {"large": "x" * 10000},
        }]}

    def tearDown(self):
        self.temp.cleanup()

    def test_compact_response_persists_full_integrity_checked_payload_without_extra_workflow_read(self):
        compact = zzzops.compact_workflow_response(self.repo, 543, "execute", self.response)
        self.assertEqual("success", compact["outcome"])
        self.assertEqual(self.response["next_steps"][0]["unused_contract"], compact["next_steps"][0]["unused_contract"])
        self.assertEqual(["src/a.py", "tests/a.py"], compact["next_steps"][0]["lease"]["acquisition"]["workspace_paths"])
        reference = compact["full_response"]
        self.assertEqual(self.response, zzzops.read_workflow_response(
            self.repo, Path(reference["path"]), reference["sha256"], goal=543, selectors=[]))
        selected = zzzops.read_workflow_response(
            self.repo, Path(reference["path"]), reference["sha256"], goal=543,
            selectors=["/next_steps/0/submission"],
        )
        self.assertEqual(self.response["next_steps"][0]["submission"], selected["/next_steps/0/submission"])

    def test_minimal_request_hydrates_only_cli_owned_action_identity(self):
        reference = zzzops.compact_workflow_response(self.repo, 543, "execute", self.response)["full_response"]
        request = zzzops.hydrate_workflow_request(self.repo, 543, "execute", {
            "context": reference, "operation": "submit", "request_id": "retry-1", "outputs": {"value": "done"},
        })
        self.assertEqual("lease-1", request["lease"])
        self.assertEqual("worker-1", request["actor"])
        self.assertEqual(self.response["next_steps"][0]["submission"]["node"], request["node"])
        self.assertEqual({"value": "done"}, request["outputs"])

    def test_minimal_request_hydrates_start_and_bind_actions(self):
        node = {"goal": 543, "node": "implement", "item": None, "generation": 1}
        for operation, action in (
            ("start", {"operation": "start", "node": node, "input_hash": "sha256:" + "5" * 64}),
            ("bind", {"operation": "bind", "node": node, "lease": "lease-1", "actor": "<actual worker>", "selection": {"model": "m", "effort": "low"}}),
        ):
            with self.subTest(operation=operation):
                response = {"next_steps": [{"kind": "perform", operation: action}]}
                reference = zzzops.compact_workflow_response(self.repo, 543, "execute", response).get("full_response")
                if reference is None:
                    reference = zzzops._response_reference(self.repo, 543, "execute", response)
                supplied = {"context": reference, "operation": operation, "request_id": operation + "-1"}
                if operation == "bind":
                    supplied.update(actor="worker", policy_receipt="sha256:" + "6" * 64)
                hydrated = zzzops.hydrate_workflow_request(self.repo, 543, "execute", supplied)
                self.assertEqual(node, hydrated["node"])
                self.assertEqual(action.get("input_hash"), hydrated.get("input_hash"))
                self.assertEqual("worker" if operation == "bind" else None, hydrated.get("actor"))

    def test_preview_context_can_start_execute_and_ambiguous_actions_require_node(self):
        one = {"goal": 543, "node": "one", "item": None, "generation": 1}
        two = {"goal": 543, "node": "two", "item": None, "generation": 1}
        response = {"next_steps": [
            {"kind": "execute", "node": one, "start": {"operation": "start", "node": one, "input_hash": "sha256:" + "1" * 64}},
            {"kind": "execute", "node": two, "start": {"operation": "start", "node": two, "input_hash": "sha256:" + "2" * 64}},
        ]}
        reference = zzzops._response_reference(self.repo, 543, "preview", response)
        with self.assertRaisesRegex(ValueError, "supply the exact node"):
            zzzops.hydrate_workflow_request(self.repo, 543, "execute", {"context": reference, "operation": "start"})
        hydrated = zzzops.hydrate_workflow_request(self.repo, 543, "execute", {
            "context": reference, "operation": "start", "node": two, "request_id": "start-two",
        })
        self.assertEqual(two, hydrated["node"])
        self.assertEqual("sha256:" + "2" * 64, hydrated["input_hash"])

    def test_missing_corrupt_wrong_goal_and_conflicting_context_fail_closed(self):
        reference = zzzops.compact_workflow_response(self.repo, 543, "execute", self.response)["full_response"]
        with self.assertRaisesRegex(ValueError, "different goal"):
            zzzops.hydrate_workflow_request(self.repo, 544, "execute", {"context": reference, "operation": "submit"})
        with self.assertRaisesRegex(ValueError, "conflicts"):
            zzzops.hydrate_workflow_request(self.repo, 543, "execute", {
                "context": reference, "operation": "submit", "node": {"goal": 999},
            })
        path = Path(reference["path"])
        path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "corrupt"):
            zzzops.hydrate_workflow_request(self.repo, 543, "execute", {"context": reference, "operation": "submit"})
        path.unlink()
        with self.assertRaisesRegex(ValueError, "unavailable"):
            zzzops.hydrate_workflow_request(self.repo, 543, "execute", {"context": reference, "operation": "submit"})

    def test_cli_defaults_to_compact_and_explicit_full_preserves_legacy_json(self):
        runtime = self.repo / "runtime.json"
        runtime.write_text(json.dumps({"root_id": "root", "available_pairs": []}), encoding="utf-8")
        base = ["zzzops", "--repo", str(self.repo), "--goal", "543", "--intent", "execute", "--runtime", str(runtime)]
        with (
            mock.patch.object(zzzops, "configure_cli_stdout"),
            mock.patch.object(zzzops._workflow, "public_run", return_value=self.response) as run,
            mock.patch.object(sys, "argv", base),
            mock.patch.object(sys, "stdout", io.StringIO()) as stream,
        ):
            self.assertEqual(0, zzzops.main())
        compact = json.loads(stream.getvalue())
        self.assertEqual("success", compact["outcome"])
        self.assertEqual(self.response, zzzops.read_workflow_response(
            self.repo, Path(compact["full_response"]["path"]), compact["full_response"]["sha256"],
            goal=543, selectors=[],
        ))
        self.assertEqual(1, run.call_count)

        with (
            mock.patch.object(zzzops, "configure_cli_stdout"),
            mock.patch.object(zzzops._workflow, "public_run", return_value=self.response),
            mock.patch.object(sys, "argv", [*base, "--response", "full"]),
            mock.patch.object(sys, "stdout", io.StringIO()) as stream,
        ):
            self.assertEqual(0, zzzops.main())
        self.assertEqual(self.response, json.loads(stream.getvalue()))

    def test_public_cli_hydrates_minimal_input_before_existing_submit_validation(self):
        reference = zzzops._response_reference(self.repo, 543, "execute", self.response)
        request = self.repo / "minimal.json"
        request.write_text(json.dumps({
            "context": reference, "operation": "submit", "request_id": "same-retry",
            "outputs": {"value": "reviewed"},
        }), encoding="utf-8")
        runtime = self.repo / "runtime.json"
        runtime.write_text(json.dumps({"root_id": "root", "available_pairs": []}), encoding="utf-8")
        expected = {"next_steps": [{"kind": "checkpoint", "goal": 543}]}
        argv = ["zzzops", "--repo", str(self.repo), "--goal", "543", "--intent", "execute",
                "--runtime", str(runtime), "--input", str(request), "--response", "full"]
        with (
            mock.patch.object(zzzops, "configure_cli_stdout"),
            mock.patch.object(zzzops, "workflow_submit", return_value=expected) as submit,
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(sys, "stdout", io.StringIO()) as stream,
        ):
            self.assertEqual(0, zzzops.main())
        submitted = submit.call_args.args[3]
        self.assertEqual("lease-1", submitted["lease"])
        self.assertEqual("worker-1", submitted["actor"])
        self.assertEqual(self.response["next_steps"][0]["submission"]["node"], submitted["node"])
        self.assertEqual(expected, json.loads(stream.getvalue()))

    def test_public_read_response_subprocess_selects_content_and_repairs_invalid_envelope(self):
        response = {"next_steps": [{"kind": "read", "goal": 543, "content": {"large": "x" * 2000}}]}
        compact = zzzops.compact_workflow_response(self.repo, 543, "execute", response)
        self.assertEqual(response["next_steps"][0]["content"], compact["next_steps"][0]["content"])
        reference = zzzops._response_reference(self.repo, 543, "execute", response)
        command = [sys.executable, str(MODULE_PATH), "--repo", str(self.repo), "--goal", "543",
                   "--read-response", reference["path"], "--response-hash", reference["sha256"],
                   "--select", "/next_steps/0/content"]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(response["next_steps"][0]["content"], json.loads(result.stdout)["/next_steps/0/content"])

        raw = b"[]"
        identity = "sha256:" + hashlib.sha256(raw).hexdigest()
        bad = Path(reference["path"]).parent / (identity.split(":", 1)[1] + ".json")
        bad.write_bytes(raw)
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--repo", str(self.repo), "--read-response", str(bad),
             "--response-hash", identity], capture_output=True, text=True, check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stderr)
        self.assertEqual("repair", json.loads(result.stdout)["next_steps"][0]["kind"])

    def test_compact_capture_batch_error_and_resume_steps_keep_actionable_fields(self):
        samples = [
            {"kind": "capture", "assignment": "root", "action": "Capture", "request_fields": ["title", "goal"],
             "submission": {"operation": "capture", "request": "<validated>"}},
            {"kind": "batch", "action": "Continue batch", "complete": False, "cursor": "next",
             "members": {"1": {"status": "blocked", "reason": "parent unavailable"}},
             "remaining": [2], "submission": {"operation": "migration_batch", "action": "migrate"}},
            {"kind": "repair", "action": "Retry", "reason": "stale owner", "diagnostic": {"failed_invariant": "lease"},
             "recovery_contract": {"operation": "recover", "worker_status": "<observed>"}},
            {"kind": "await_worker", "action": "Resume", "reason": "owner active",
             "renewal": {"operation": "renew", "lease": "token"}, "recheck": {"after_seconds": 30}},
        ]
        for index, step in enumerate(samples):
            with self.subTest(kind=step["kind"]):
                response = {"next_steps": [{**step, "future_action_field": {"required": True}}]}
                compact = zzzops.compact_workflow_response(self.repo, 543, "execute", response)
                observed = compact["next_steps"][0]
                for key in step:
                    self.assertEqual(step[key], observed[key])
                self.assertEqual({"required": True}, observed["future_action_field"])
                if step["kind"] == "batch":
                    self.assertEqual("blocked", compact["outcome"])


if __name__ == "__main__":
    unittest.main()
