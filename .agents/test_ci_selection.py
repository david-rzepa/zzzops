"""Behavioral contract for the bounded native CI validation legs."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / ".github" / "scripts" / "run_product_validation.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "validate.yml"

REQUIRED_OBLIGATIONS = {
    "installation_cleanup",
    "marketplace_package",
    "package_cli",
    "heartbeat_process",
    "git_crlf_drift",
    "path_confinement",
    "public_delivery",
}

REQUIRED_NATIVE_IDS = {
    "test_installation_validation.InstallationValidationTests.test_cli_clean_first_use_and_idempotent_status",
    "test_legacy_cleanup.LegacyCleanupTests.test_default_cli_is_dry_run_and_interrupted_cleanup_converges",
    "test_marketplace_bundle.MarketplaceBundleTests.test_fixed_version_build_is_deterministic_and_complete",
    "test_agent_plugin.AgentPluginTests.test_marketplace_points_to_the_self_contained_package",
    "test_zzzops.InitializationTests.test_cli_without_command_shows_help_without_writing_local_state",
    "test_workflow_heartbeat.HeartbeatProcessTests.test_one_coordinator_renews_multiple_leases_and_stops_tracking_workers",
    "test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_mixed_clean_checkout_rejects_raw_consumed_drift_and_restores_exact_acquisition",
    "test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_crlf_design_correction_retains_frozen_raw_checkout_overrides",
    "test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_clean_crlf_checkout_pins_raw_consumed_bytes_and_allows_owned_red_edit",
    "test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_acquired_owned_path_cannot_be_replaced_by_escaping_symlink",
    "test_workflow_publication_contract.GenericDeliveryPublicTests.test_reviewed_red_green_proofs_commit_and_exact_publication_form_one_delivery_graph",
}


def load_runner():
    spec = importlib.util.spec_from_file_location("ci_selection_runner", RUNNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeSelectionContractTests(unittest.TestCase):
    def setUp(self):
        self.runner = load_runner()

    def require_api(self, name):
        self.assertTrue(
            hasattr(self.runner, name),
            f"run_product_validation.py must provide {name}",
        )
        return getattr(self.runner, name)

    def test_native_coverage_is_explicit_complete_unique_and_bounded(self):
        coverage = self.require_api("NATIVE_COVERAGE")
        self.assertEqual(REQUIRED_OBLIGATIONS, set(coverage))
        selected = [test_id for ids in coverage.values() for test_id in ids]
        self.assertTrue(selected, "native selection must not be empty")
        self.assertEqual(len(selected), len(set(selected)), "native IDs must be unique")
        self.assertTrue(REQUIRED_NATIVE_IDS.issubset(selected))
        self.assertFalse(
            any("test_workflow_journey.FullWorkflowJourneyTests" in item for item in selected),
            "platform-independent full journeys belong to complete Linux discovery",
        )

    def test_selection_accepts_only_discovered_tests(self):
        select = self.require_api("select_native_tests")
        selected = tuple(select(set(REQUIRED_NATIVE_IDS)))
        self.assertEqual(REQUIRED_NATIVE_IDS, set(selected))
        self.assertEqual(len(selected), len(set(selected)))

    def test_selection_rejects_empty_duplicate_and_missing_ids(self):
        select = self.require_api("select_native_tests")
        with mock.patch.object(self.runner, "NATIVE_COVERAGE", {"installation_cleanup": ()}):
            with self.assertRaisesRegex(ValueError, "empty"):
                select(set())
        duplicate = next(iter(REQUIRED_NATIVE_IDS))
        with mock.patch.object(
            self.runner,
            "NATIVE_COVERAGE",
            {"installation_cleanup": (duplicate,), "package_cli": (duplicate,)},
        ):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                select({duplicate})
        with self.assertRaisesRegex(ValueError, "missing"):
            select(set())

    def test_discovery_error_stops_before_execution(self):
        run_native = self.require_api("run_native_validation")
        launch = mock.Mock()

        def failed_discovery():
            raise RuntimeError("bounded discovery failed")

        with self.assertRaisesRegex(RuntimeError, "discovery failed"):
            run_native(
                "windows",
                discover=failed_discovery,
                launch=launch,
                clock=lambda: 0.0,
                emit=lambda report: None,
            )
        launch.assert_not_called()

    def test_native_run_uses_separate_discovery_and_fresh_execution(self):
        run_native = self.require_api("run_native_validation")
        events = []

        def discover():
            events.append("discover")
            return set(REQUIRED_NATIVE_IDS)

        def launch(selected):
            events.append(("launch", tuple(selected)))
            return {
                "returncode": 0,
                "tests_run": len(selected),
                "failures": 0,
                "errors": 0,
                "skipped": 0,
                "durations": {test_id: 0.01 for test_id in selected},
            }

        report = run_native(
            "macos",
            discover=discover,
            launch=launch,
            clock=iter((10.0, 10.5)).__next__,
            emit=lambda value: events.append(("emit", value)),
        )
        self.assertEqual("discover", events[0])
        self.assertEqual("launch", events[1][0])
        self.assertEqual(REQUIRED_NATIVE_IDS, set(events[1][1]))
        self.assertEqual("emit", events[2][0])
        self.assertEqual("macos", report["platform"])
        self.assertEqual(len(REQUIRED_NATIVE_IDS), report["selected_count"])
        self.assertEqual(0.5, report["wall_seconds"])

    def test_public_discovery_mode_runs_in_a_fresh_process_without_tests(self):
        completed = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--platform", "windows", "--discover-native"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("windows", payload["platform"])
        self.assertEqual(sorted(REQUIRED_NATIVE_IDS), sorted(payload["selected_ids"]))
        self.assertEqual(len(REQUIRED_NATIVE_IDS), payload["selected_count"])
        self.assertEqual(0, payload["tests_run"], "discovery mode must not execute tests")

    def test_windows_and_macos_use_only_the_native_selector(self):
        run_native = self.require_api("run_native_validation")
        with mock.patch.object(self.runner, "run_native_validation", autospec=run_native) as native:
            with mock.patch.object(self.runner, "run") as legacy_run:
                self.runner.windows_validation()
                self.runner.macos_validation()
        self.assertEqual([mock.call("windows"), mock.call("macos")], native.call_args_list)
        legacy_run.assert_not_called()

    def test_timing_report_preserves_counts_skips_and_slowest_groups(self):
        run_native = self.require_api("run_native_validation")
        emitted = []
        durations = {test_id: float(index + 1) / 100 for index, test_id in enumerate(REQUIRED_NATIVE_IDS)}
        observation = {
            "returncode": 0,
            "tests_run": len(REQUIRED_NATIVE_IDS),
            "failures": 0,
            "errors": 0,
            "skips": [
                {"id": "native.facility.one", "reason": "facility unavailable"},
                {"id": "native.facility.two", "reason": "facility unavailable"},
            ],
            "durations": durations,
        }
        report = run_native(
            "windows",
            discover=lambda: set(REQUIRED_NATIVE_IDS),
            launch=lambda selected: observation,
            clock=iter((20.0, 21.25)).__next__,
            emit=emitted.append,
        )
        self.assertEqual([report], emitted)
        self.assertEqual(len(REQUIRED_NATIVE_IDS), report["tests_run"])
        self.assertEqual(0, report["failures"])
        self.assertEqual(0, report["errors"])
        self.assertEqual(2, report["skipped"])
        self.assertEqual(observation["skips"], report["coverage_limits"])
        self.assertEqual(1.25, report["wall_seconds"])
        self.assertAlmostEqual(sum(durations.values()), report["aggregate_test_seconds"])
        self.assertTrue(report["slowest_tests"])
        self.assertTrue(report["slowest_groups"])
        self.assertEqual(set(REQUIRED_NATIVE_IDS), set(report["selected_ids"]))

    def test_failed_execution_is_reported_then_propagated(self):
        run_native = self.require_api("run_native_validation")
        emitted = []
        observation = {
            "returncode": 1,
            "tests_run": 4,
            "failures": 1,
            "errors": 2,
            "skips": [{"id": "native.facility", "reason": "facility unavailable"}],
            "durations": {},
        }
        with self.assertRaises(subprocess.CalledProcessError) as raised:
            run_native(
                "windows",
                discover=lambda: set(REQUIRED_NATIVE_IDS),
                launch=lambda selected: observation,
                clock=iter((1.0, 1.1)).__next__,
                emit=emitted.append,
            )
        self.assertEqual(1, raised.exception.returncode)
        self.assertEqual(1, emitted[0]["failures"])
        self.assertEqual(2, emitted[0]["errors"])
        self.assertEqual(1, emitted[0]["skipped"])

    def test_step_summary_exposes_selection_timing_and_coverage_limits(self):
        write_summary = self.require_api("write_step_summary")
        report = {
            "platform": "windows",
            "selected_ids": sorted(REQUIRED_NATIVE_IDS),
            "selected_count": len(REQUIRED_NATIVE_IDS),
            "tests_run": len(REQUIRED_NATIVE_IDS),
            "failures": 0,
            "errors": 0,
            "skipped": 1,
            "coverage_limits": [
                {"id": "native.facility", "reason": "facility unavailable"}
            ],
            "wall_seconds": 1.25,
            "aggregate_test_seconds": 0.75,
            "slowest_tests": [("test.example", 0.5)],
            "slowest_groups": [("package_cli", 0.5)],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.md"
            write_summary(report, path)
            summary = path.read_text(encoding="utf-8")
        for value in (
            "windows",
            "selected",
            str(len(REQUIRED_NATIVE_IDS)),
            "1.25",
            "0.75",
            "test.example",
            "package_cli",
            "native.facility",
            "facility unavailable",
        ):
            self.assertIn(value, summary)


class ExistingCoverageControls(unittest.TestCase):
    def test_linux_validation_remains_complete_and_in_order(self):
        runner = load_runner()
        with mock.patch.object(runner, "run") as run:
            runner.linux_validation()
        self.assertEqual(
            [
                (sys.executable, "-m", "unittest", "discover", "-s", ".agents", "-p", "test_*.py"),
                (sys.executable, "-m", "unittest", "discover", "-s", "plugins/zzzops/skills/migrate-to-zzzops/scripts", "-p", "test_*.py"),
                (sys.executable, ".agents/manual_acceptance.py", "coverage"),
                ("npm", "run", "test:plugin"),
                ("npm", "run", "test:release"),
                (sys.executable, ".agents/prompt_stats.py", "--check"),
                (sys.executable, "-m", "compileall", "-q", ".agents", "plugins/zzzops", ".github/scripts"),
            ],
            [call.args for call in run.call_args_list],
        )

    def test_required_gate_keeps_all_results_truthful(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("if: ${{ always() }}", workflow)
        self.assertIn(
            "needs: [validate-linux, validate-windows, validate-macos, validate-claude]",
            workflow,
        )
        for leg in ("linux", "windows", "macos", "claude"):
            self.assertIn(f"{leg}=${{{{ needs.validate-{leg}.result }}}}", workflow)


if __name__ == "__main__":
    unittest.main()
