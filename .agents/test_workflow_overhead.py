"""Bounded public workflow measurements; fake transport, real validation/proofs.

Run this file with --report PATH for both machine-readable transcripts. Normal
unittest discovery runs the same finite comparison with no wall-clock ceiling.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

import test_evidence_dag_journeys as journeys
from test_workflow_reservations import FakeAdapter


def wire_bytes(value):
    """Canonical fixture serialization, not HTTP framing or model tokens."""
    return len(json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, default=str).encode())


class Meter:
    def __init__(self, session, *, request_ids=True):
        self.session = session
        self.request_ids = request_ids
        self.phase = "authority_setup"
        self.calls, self.provider, self.checks, self.policies = [], [], [], []
        self.processes = []
        self.current = None

    def boundary(self, name, function):
        def observed(*args, **kwargs):
            result = function(*args, **kwargs)
            self.provider.append({"phase": self.phase, "invocation": self.current,
                "method": name, "request_bytes": wire_bytes([args, kwargs]),
                "response_bytes": wire_bytes(result)})
            return result
        return observed

    def call(self, number, payload=None, **kwargs):
        invocation = len(self.calls) + 1
        request = copy.deepcopy(payload)
        if request is not None and self.request_ids:
            request.setdefault("request_id", f"measurement-{invocation}")
        self.current = invocation
        started = time.perf_counter()
        try:
            response = self.original_call(number, request, **kwargs)
        finally:
            elapsed = time.perf_counter() - started
            self.current = None
        self.calls.append({"invocation": invocation, "phase": self.phase,
            "operation": (request or {}).get("operation", kwargs.get("intent", "checkpoint")),
            "intent": kwargs.get("intent", "execute"),
            "node": (request or {}).get("node"), "actor": (request or {}).get("actor"),
            "request_id": (request or {}).get("request_id"),
            "request_bytes": wire_bytes(request), "response_bytes": wire_bytes(response),
            "elapsed_seconds": elapsed, "exit_code": self.session.calls[-1]["code"],
            "next_steps": [{key: step[key] for key in ("kind", "node") if key in step}
                           for step in response["next_steps"]],
            "submitted": response.get("submitted")})
        return response

    def install(self, stack):
        self.original_call = self.session.call
        stack.enter_context(mock.patch.object(self.session, "call", side_effect=self.call))
        for name in ("get_issue", "get_issue_comments", "create_issue_comment", "update_issue"):
            provider = self.session.provider
            stack.enter_context(mock.patch.object(provider, name,
                side_effect=self.boundary(name, getattr(provider, name))))
        # Exercise production reservation logic; only its transport is in memory.
        adapter = self.session.reservation_adapter = FakeAdapter()
        for name in ("get_label", "create_label", "delete_label"):
            stack.enter_context(mock.patch.object(adapter, name,
                side_effect=self.boundary(name, getattr(adapter, name))))
        self.session.provider_issue_snapshot = self.boundary("provider_issue_snapshot",
            lambda _repo, _repository, number: copy.deepcopy(self.session.provider.issues[number]))
        # Match production's lazy ownership inventory rather than fixture hydration.
        snapshot = self.session.portfolio_snapshot
        def unhydrated(*args, **kwargs):
            result = snapshot(*args, **kwargs)
            for goal in result["goals"]:
                goal.pop("operational_leases", None)
            return result
        self.session.portfolio_snapshot = unhydrated
        run = subprocess.run
        def observed(command, *args, **kwargs):
            result = run(command, *args, **kwargs)
            self.processes.append({"phase": self.phase, "invocation": self.current,
                "command": list(command), "exit_code": result.returncode})
            if list(command) == [sys.executable, "-B", "behavior_test.py"]:
                self.checks.append({"phase": self.phase, "invocation": self.current,
                    "command": list(command), "exit_code": result.returncode})
            return result
        stack.enter_context(mock.patch.object(subprocess, "run", side_effect=observed))

    def summary(self, phases):
        calls = [row for row in self.calls if row["phase"] in phases]
        events = [row for row in self.provider if row["phase"] in phases and row["invocation"] is not None]
        outside = [row for row in self.provider if row["phase"] in phases and row["invocation"] is None]
        return {"public_invocations": len(calls),
            "operations": dict(Counter(row["operation"] for row in calls)),
            "provider_calls": dict(Counter(row["method"] for row in events)),
            "provider_call_count": len(events),
            "public_request_bytes": sum(row["request_bytes"] for row in calls),
            "public_response_bytes": sum(row["response_bytes"] for row in calls),
            "provider_request_bytes": sum(row["request_bytes"] for row in events),
            "provider_response_bytes": sum(row["response_bytes"] for row in events),
            "out_of_band_provider_calls": dict(Counter(row["method"] for row in outside)),
            "out_of_band_provider_request_bytes": sum(row["request_bytes"] for row in outside),
            "out_of_band_provider_response_bytes": sum(row["response_bytes"] for row in outside),
            "local_process_count": sum(row["phase"] in phases for row in self.processes),
            "authoritative_check_count": sum(row["phase"] in phases for row in self.checks),
            "public_elapsed_seconds": sum(row["elapsed_seconds"] for row in calls)}


PHASES = {"alpha": "test_design", "observe_alpha": "test_verification_review",
          "accept_alpha": "test_independent_acceptance", "beta": "implementation",
          "observe_beta": "implementation_verification_review",
          "accept_beta": "implementation_independent_acceptance"}


def measure_journey(*, checkpoints=False):
    case = journeys.WorkspaceAuthorityPublicTests()
    case.setUp()
    try:
        session = case.session
        meter = Meter(session)
        with ExitStack() as stack:
            meter.install(stack)
            case.setup_workspace()
            meter.phase = "initial_discovery"
            frontier = session.call(100)
            for name, phase in PHASES.items():
                meter.phase = phase
                step = next(row for row in frontier["next_steps"]
                            if row["kind"] == "execute" and row["node"]["node"] == name)
                raw = Path(step["policy"]["path"]).read_bytes()
                meter.policies.append({"phase": phase, "bytes": len(raw),
                                       "sha256": hashlib.sha256(raw).hexdigest()})
                receipt = json.loads(raw)["policy_receipt"]
                work = session.call(100, {**step["start"], "policy_receipt": receipt})["next_steps"][0]
                actor = "measured-" + name
                session.call(100, {**work["bind"], "actor": actor,
                    "selection": work["lease"]["selection"], "policy_receipt": receipt})
                work["bound_actor"] = actor
                # Inspection is part of reviewer cost, not an uncounted helper.
                for binding in step["input_envelope"]["inputs"]:
                    if binding["name"] not in {"subject", "checks"}:
                        continue
                    artifact = session.read(100, binding["source"])
                    proof_ref = artifact.get("provenance", {}).get("source")
                    if proof_ref:
                        proof = session.read(100, proof_ref)
                        case.assertNotEqual(actor, proof["actor"])
                        case.assertEqual(1 if name.endswith("alpha") else 0,
                                         proof["commands"][0]["exit_code"])
                request = session.submission(work, {"value": "Measured " + name}, "submit-" + name)
                if name in {"alpha", "beta"}:
                    path = "behavior_test.py" if name == "alpha" else "source.py"
                    text = ("from source import value\nassert value() == 2\n" if name == "alpha"
                            else "def value():\n    return 2\n")
                    (case.fixture.repo / path).write_text(text)
                    request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
                frontier = session.call(100, request)
                case.assertEqual(work["node"], frontier["submitted"]["node"])
                if checkpoints:
                    frontier = session.call(100)
            case.assertIn("gamma", {row.get("node", {}).get("node") for row in frontier["next_steps"]})
            case.assertEqual([1, 0], [row["exit_code"] for row in meter.checks])
            case.assertEqual({}, session.reservation_adapter.labels)
        phases = {"initial_discovery", *PHASES.values()}
        return {"mode": "post_submit_checkpoints" if checkpoints else "direct_continuations",
            "normal_journey": meter.summary(phases),
            "authority_setup": meter.summary({"authority_setup"}),
            "phases": {name: meter.summary({name}) for name in ["initial_discovery", *PHASES.values()]},
            "transcript": meter.calls, "provider_events": meter.provider,
            "authoritative_checks": meter.checks, "policy_reads": meter.policies,
            "fixture_seed_events": sum(row["invocation"] is None for row in meter.provider),
            "model_tokens": {"root_input": None, "root_output": None,
                             "worker_input": None, "worker_output": None,
                             "reason": "No model runs or model usage records in this fixture."}}
    finally:
        case.doCleanups()


def comparison():
    source = Path(__file__).resolve()
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source.parents[1],
                              capture_output=True, text=True, check=True).stdout.strip()
    return {"schema_version": 1, "source_revision": revision,
        "harness_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "python_version": sys.version,
        "scope": "verified test-design and implementation with independent reviews",
        "comparison": "Same current engine and evidence; comparator adds one checkpoint after each submit. Not a historical-engine CPU benchmark.",
        "units": {"bytes": "canonical UTF-8 fixture JSON, including repeated response payloads; not HTTP wire bytes",
                  "time": "in-process public CLI dispatch with real local Git/check processes; no Python startup or network latency"},
        "boundaries": ["Prerequisite allocation/independent authorization/root approval recorded separately, not free authority.",
                       "Provider issue/comment/snapshot and reservation-label boundaries are metered; graph/repository fixture seeding is separate.",
                       "PublicSession fakes reviewed configuration, package freshness, workflow-context validation and heartbeat cleanup; this is not installed-plugin or multi-machine acceptance.",
                       "Policy file bytes are recorded for measured phase acquisitions. CLI bytes are not full agent contexts or model-token estimates."],
        "direct": measure_journey(), "with_checkpoints": measure_journey(checkpoints=True),
        "remaining_acceptance": ["Final integrated correction and ordinary journey remeasurement",
                                 "Automatic long-phase renewal after heartbeat integration",
                                 "Full self-upgrade journey beyond local validation boundary",
                                 "Actual root/worker input-output tokens and agent transcripts",
                                 "All goal510 children and referenced disclosure/review/recovery owners integrated",
                                 "Final integrated stale-input, human-approval, idempotency and multi-machine acceptance",
                                 "Re-measure after remaining optimization children; three-interaction target not yet reached"]}


class WorkflowOverheadTests(unittest.TestCase):
    def test_verified_journey_has_bounded_coordination_and_payload_repetition(self):
        report = comparison()
        direct = report["direct"]["normal_journey"]
        baseline = report["with_checkpoints"]["normal_journey"]
        self.assertLessEqual(direct["public_invocations"], 29)
        self.assertEqual(6, baseline["public_invocations"] - direct["public_invocations"])
        self.assertEqual({"checkpoint": 1, "start": 6, "bind": 6, "submit": 6, "read": 10}, direct["operations"])
        for method in ("update_issue", "create_issue_comment", "create_label", "delete_label"):
            self.assertEqual(18, direct["provider_calls"][method])
            self.assertEqual(direct["provider_calls"][method], baseline["provider_calls"][method])
        # Headroom tolerates compression/UUID/path differences, not an extra
        # history round-trip on every phase. Wall time is diagnostic only.
        self.assertLessEqual(direct["provider_response_bytes"], baseline["provider_response_bytes"] * 1.10 + 16384)
        self.assertLessEqual(direct["provider_response_bytes"], 12 * 1024 * 1024)
        self.assertLessEqual(direct["public_response_bytes"], 256 * 1024)
        self.assertLessEqual(direct["provider_call_count"], 400)
        self.assertLess(direct["provider_call_count"], baseline["provider_call_count"])
        self.assertEqual(10, direct["operations"]["read"], "Review evidence inspection remains counted")

    def test_goal499_lightweight_and_strict_coordination_remain_proportional(self):
        """Compare public transcripts, including an explicit stricter checkpoint pass."""
        report = comparison()
        lightweight = report["direct"]["normal_journey"]
        strict = report["with_checkpoints"]["normal_journey"]
        self.assertEqual(lightweight["authoritative_check_count"],
                         strict["authoritative_check_count"])
        self.assertEqual(lightweight["operations"]["read"], strict["operations"]["read"],
                         "Stricter coordination must not duplicate reviewed context")
        self.assertEqual(6, strict["operations"].get("checkpoint", 0)
                         - lightweight["operations"].get("checkpoint", 0))
        for operation in ("create_issue_comment", "update_issue", "create_label", "delete_label"):
            self.assertEqual(lightweight["provider_calls"][operation],
                             strict["provider_calls"][operation],
                             "Assurance checkpoints must not add provider mutations")
        added_provider_reads = strict["provider_call_count"] - lightweight["provider_call_count"]
        self.assertLessEqual(added_provider_reads, 36,
                             "Six stricter checkpoints get a bounded fresh provider view")
        duplicated_context = strict["public_response_bytes"] - lightweight["public_response_bytes"]
        self.assertLessEqual(duplicated_context, 96 * 1024)
        lightweight_token_estimate = (lightweight["public_request_bytes"]
                                      + lightweight["public_response_bytes"] + 3) // 4
        strict_token_estimate = (strict["public_request_bytes"]
                                 + strict["public_response_bytes"] + 3) // 4
        self.assertLessEqual(strict_token_estimate - lightweight_token_estimate, 24 * 1024)
        self.assertLessEqual(strict["provider_call_count"], 400)
        self.assertLessEqual(strict["public_elapsed_seconds"],
                             max(10.0, lightweight["public_elapsed_seconds"] * 8),
                             "Elapsed time is a generous regression bound, not a speed claim")


if __name__ == "__main__":
    if "--report" in sys.argv:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--report", type=Path, required=True)
        args = parser.parse_args()
        report = comparison()
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({key: report[key]["normal_journey"] for key in ("direct", "with_checkpoints")}, indent=2))
    else:
        unittest.main()
