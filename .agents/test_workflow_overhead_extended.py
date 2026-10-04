"""Finite correction, renewal and post-upgrade validation boundary baselines."""
import argparse
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import test_evidence_dag_journeys as journeys
from test_workflow_overhead import Meter


def report(meter, phases, *, scope, limits):
    return {"scope": scope, "measured": meter.summary(set(phases)),
        "prerequisite_setup": meter.summary({"authority_setup"}),
        "phases": {phase: meter.summary({phase}) for phase in phases},
        "transcript": meter.calls, "provider_events": meter.provider,
        "local_processes": meter.processes, "authoritative_checks": meter.checks,
        "model_tokens": None,
        "unmetered_context": "Fixture helpers read local policy files; extended byte totals cover serialized CLI/provider boundaries, not total agent context.",
        "limits": limits}


def atomic_correction():
    case = journeys.WorkspaceAuthorityPublicTests()
    case.setUp()
    try:
        session = case.session
        meter = Meter(session)
        with ExitStack() as stack:
            meter.install(stack)
            case.setup_workspace_corrections(root_gate=True, correction_rounds=1)
            case.red_candidate()
            work = case.acquire_workspace("beta")
            (case.fixture.repo / "source.py").write_text("def value():\n    return 2\n")
            prior_ref, prior_proof = case.candidate(work, 0)
            case.review_candidate("beta", 0)
            session.finish(session.acquire("accept_root_beta"), {"value": "Accepted initial candidate"})
            meter.phase = "intake_and_admission"
            admissions = case.admit_workspace_correction()
            case.assertNotIn("gamma", case.names())
            meter.phase = "verified_correction"
            work = case.acquire_workspace("beta")
            (case.fixture.repo / "source.py").write_text("def value():\n    # Bounded correction.\n    return 2\n")
            case.candidate(work, 0)
            meter.phase = "independent_review_and_resolution"
            case.review_candidate("beta", 0)
            case.resolve_workspace_correction(admissions)
            case.assertNotIn("gamma", case.names(), "Fresh root acceptance remains required")
            meter.phase = "root_acceptance_and_inspection"
            session.finish(session.acquire("accept_root_beta"), {"value": "Accept exact corrected candidate"})
            case.assertIn("gamma", case.names())
            case.assertEqual(prior_proof, case.read_blob(prior_ref), "Historical proof remains immutable")
        return report(meter, ["intake_and_admission", "verified_correction",
            "independent_review_and_resolution", "root_acceptance_and_inspection"],
            scope="One atomic workspace correction with two retained findings, one host check and fresh reviews/root acceptance.",
            limits=["Existing correctness helpers intentionally perform repeated checkpoints and targeted artifact inspections; this is their measured baseline, not a minimal correction protocol.",
                    "Synthetic external reviewer comment is an out-of-band fixture provider event, reported separately from public CLI provider traffic.",
                    "Prerequisite setup includes reviewed initial test and implementation candidates; no preapproved authority is hidden.",
                    "Same PublicSession external configuration/package/heartbeat fakes as the ordinary baseline; no actual model calls."])
    finally:
        case.doCleanups()


def delegated_renewal():
    case = journeys.DagFixture()
    case.setUp()
    worker = None
    try:
        session = case.session
        meter = Meter(session)
        # A real local child supplies liveness. Its stdin closes during cleanup;
        # there is no artificial lease-duration sleep and no invented worker PID.
        worker = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
        actor = "measured-child-" + str(worker.pid)
        with ExitStack() as stack:
            meter.install(stack)
            meter.phase = "delegated_acquisition"
            work = session.acquire("produce", actor=actor)
            case.assertIsNone(worker.poll())
            meter.phase = "live_renewal_boundary"
            # Simulate elapsed lease time, not transport latency or worker work.
            observed_time = work["lease"]["expires_at"] - 60
            with mock.patch.object(journeys.z._workflow.time, "time", return_value=observed_time):
                renewal = session.call(100, {"operation": "renew", "node": work["node"],
                    "lease": work["lease"]["token"], "actor": actor, "request_id": "long-phase-renewal"})
            renewed = renewal["next_steps"][0]
            case.assertEqual("renewed", renewed["kind"])
            case.assertEqual(work["node"], renewed["node"])
            case.assertGreater(renewed["expires_at"], work["lease"]["expires_at"])
            case.assertIsNone(worker.poll())
            meter.phase = "delegated_completion"
            session.finish(work, {"value": "Completed by live delegated owner"})
            case.assertFalse(case.payload()[1]["operational"]["leases"])
        result = report(meter, ["delegated_acquisition", "live_renewal_boundary", "delegated_completion"],
            scope="One exact public renewal of a live local delegated owner and normal completion.",
            limits=["Lease clock advances virtually; worker is a lightweight real local process, not a model or long-running product task.",
                    "Measures the public renewal protocol, not automatic heartbeat scheduling. This branch predates504; final automatic-runner measurement remains required after integration.",
                    "PublicSession heartbeat cleanup is faked; actual worker shutdown is independently confirmed below.",
                    "No network delay, concurrent-machine race or model tokens are measured."])
        worker.stdin.close()
        worker.wait(timeout=3)
        result["worker_exit_code"] = worker.returncode
        result["liveness_process_spawns"] = 1
        result["virtual_seconds_before_original_expiry"] = 60
        return result
    finally:
        if worker is not None and worker.poll() is None:
            worker.terminate()
            worker.wait(timeout=3)
        case.doCleanups()


def self_upgrade_boundary():
    case = journeys.DagFixture()
    case.setUp()
    try:
        session, api = case.session, journeys.z
        package = {"ok": True, "version": "2.0.0", "revision": "a" * 64}
        def invoke(number, payload=None, **_kwargs):
            argv = ["zzzops", "--repo", str(session.repo), "--intent", "validate_installation"]
            if payload is not None:
                source = session.control / "installation-input.json"
                source.write_text(json.dumps(payload))
                argv += ["--input", str(source)]
            with mock.patch.object(api._package, "package_status", return_value=package), \
                 mock.patch.object(api, "configure_cli_stdout"), \
                 mock.patch.object(sys, "argv", argv), mock.patch.object(sys, "stdout", io.StringIO()) as stream:
                code = api.main()
                response = json.loads(stream.getvalue())
            case.assertEqual(0, code, response)
            session.calls.append({"code": code})
            return response
        session.call = invoke
        meter = Meter(session, request_ids=False)
        with ExitStack() as stack:
            meter.install(stack)
            first = session.call(100, intent="validate_installation")["next_steps"][0]
            case.assertTrue(first["audit"]["safe"])
            session.call(100, {**first["submission"], "outcome": "clean"}, intent="validate_installation")
            old = api._installation.record_path(session.repo).read_bytes()
            package.update(version="2.0.1", revision="b" * 64)
            meter.phase = "changed_package_validation"
            provenance = {key: package[key] for key in ("version", "revision")}
            case.assertEqual("package_changed", api._installation.validation_status(session.repo, provenance)["reason"])
            audit = session.call(100, intent="validate_installation")["next_steps"][0]
            case.assertEqual("installation_validation", audit["kind"])
            case.assertTrue(audit["audit"]["safe"])
            session.call(100, {**audit["submission"], "outcome": "clean"}, intent="validate_installation")
            case.assertFalse(api._installation.validation_status(session.repo, provenance)["required"])
            current = api._installation.record_path(session.repo).read_bytes()
            case.assertNotEqual(old, current)
            case.assertEqual(provenance, json.loads(current)["package"])
        result = report(meter, ["changed_package_validation"],
            scope="Public per-repository validation boundary after installed package provenance changes.",
            limits=["Package metadata change models the external installer boundary; no plugin download, copy, install, restart or full resumed workflow is claimed.",
                    "Installation audit and validation record are real local operations in a temporary Git repository. No remote provider action is required.",
                    "Two pre-upgrade audit/record calls appear as prerequisite setup. Full self-upgrade end-to-end and model-token evidence remain required."])
        result["validation_record_bytes"] = len(current)
        return result
    finally:
        case.doCleanups()


def extended_baselines():
    source = Path(__file__).resolve()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source.parents[1],
                          capture_output=True, text=True, check=True).stdout.strip()
    return {"schema_version": 1, "source_revision": head, "python_version": sys.version,
        "harness_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "meter_sha256": hashlib.sha256(source.with_name("test_workflow_overhead.py").read_bytes()).hexdigest(),
        "bytes": "Canonical UTF-8 JSON as in the ordinary baseline; no HTTP framing or model-token estimates.",
        "atomic_correction": atomic_correction(), "delegated_renewal": delegated_renewal(),
        "self_upgrade_boundary": self_upgrade_boundary()}


class ExtendedWorkflowOverheadTests(unittest.TestCase):
    def test_finite_acceptance_boundaries_have_count_and_byte_budgets(self):
        values = extended_baselines()
        correction = values["atomic_correction"]["measured"]
        self.assertLessEqual(correction["public_invocations"], 160)
        self.assertEqual(11, correction["operations"]["submit"])
        self.assertEqual(28, correction["provider_calls"]["update_issue"])
        self.assertEqual(1, correction["authoritative_check_count"])
        self.assertLessEqual(correction["provider_response_bytes"], 120 * 1024 * 1024)
        self.assertEqual({"create_issue_comment": 1}, correction["out_of_band_provider_calls"])
        renewal = values["delegated_renewal"]
        self.assertEqual(0, renewal["worker_exit_code"])
        self.assertEqual(1, renewal["measured"]["operations"]["renew"])
        self.assertLessEqual(renewal["measured"]["public_invocations"], 6)
        self.assertEqual(4, renewal["measured"]["provider_calls"]["update_issue"])
        upgrade = values["self_upgrade_boundary"]
        self.assertEqual(2, upgrade["measured"]["public_invocations"])
        self.assertEqual({"validate_installation": 1, "installation_record": 1}, upgrade["measured"]["operations"])
        self.assertEqual(2, upgrade["prerequisite_setup"]["public_invocations"])
        self.assertEqual(0, upgrade["measured"]["provider_call_count"])
        self.assertLessEqual(upgrade["measured"]["public_response_bytes"], 16384)


if __name__ == "__main__":
    if "--report" in sys.argv:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--report", type=Path, required=True)
        args = parser.parse_args()
        values = extended_baselines()
        args.report.write_text(json.dumps(values, indent=2) + "\n")
        print(json.dumps({key: values[key]["measured"] for key in
            ("atomic_correction", "delegated_renewal", "self_upgrade_boundary")}, indent=2))
    else:
        unittest.main()
