"""Behavioral contract for the bounded native CI validation legs."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / ".github" / "scripts" / "run_product_validation.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "validate.yml"


def assert_required_gate_contract(testcase, workflow):
    match = re.search(
        r"(?ms)^  required:\s*\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\s*$|\Z)",
        workflow,
    )
    testcase.assertIsNotNone(match, "workflow must define the required job")
    body = match.group("body")
    testcase.assertRegex(body, r"(?m)^    if: \$\{\{ always\(\) \}\}\s*$")
    testcase.assertRegex(
        body,
        r"(?m)^    needs: \[validate-linux, validate-windows, validate-macos, validate-claude\]\s*$",
    )
    run = re.search(r"(?m)^        run: >-\s*\n(?P<command>(?:^          \S.*\n?)+)", body)
    testcase.assertIsNotNone(run, "required job must execute one folded aggregation command")
    command = " ".join(line.strip() for line in run.group("command").splitlines())
    expected = " ".join((
        "python .github/scripts/require_validation.py",
        "linux=${{ needs.validate-linux.result }}",
        "windows=${{ needs.validate-windows.result }}",
        "macos=${{ needs.validate-macos.result }}",
        "claude=${{ needs.validate-claude.result }}",
    ))
    testcase.assertEqual(expected, command)

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

    def test_real_loader_discovery_selects_allowlist_and_excludes_extra_tests(self):
        discover = self.require_api("discover_native_tests")
        select = self.require_api("select_native_tests")
        repository_discovery = discover(root=ROOT)
        repository_selection = tuple(select(repository_discovery))
        self.assertEqual(REQUIRED_NATIVE_IDS, set(repository_selection))
        self.assertEqual(len(repository_selection), len(set(repository_selection)))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / ".agents"
            tests.mkdir()
            (tests / "test_selected.py").write_text(textwrap.dedent("""
                import unittest
                class Selected(unittest.TestCase):
                    def test_kept(self): pass
                    def test_extra(self): pass
            """), encoding="utf-8")
            discovered = discover(root=root)
        kept = "test_selected.Selected.test_kept"
        extra = "test_selected.Selected.test_extra"
        self.assertIn(kept, discovered)
        self.assertIn(extra, discovered)
        with mock.patch.object(
            self.runner, "NATIVE_COVERAGE", {"installation_cleanup": (kept,)}
        ):
            selected = tuple(select(discovered))
        self.assertEqual((kept,), selected)
        self.assertNotIn(extra, selected, "discovery must not expand the explicit allowlist")

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

    def test_real_loader_errors_are_rejected(self):
        discover = self.require_api("discover_native_tests")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / ".agents"
            tests.mkdir()
            (tests / "test_broken_native_fixture.py").write_text(
                "raise RuntimeError('native discovery fixture exploded')\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "discovery|fixture exploded|loader"):
                discover(root=root)

    def test_default_native_run_stops_on_loader_error_before_child_execution(self):
        run_native = self.require_api("run_native_validation")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / ".agents"
            tests.mkdir()
            marker = root / "executed"
            (tests / "test_selected_before_error.py").write_text(textwrap.dedent(f"""
                import pathlib, unittest
                class Selected(unittest.TestCase):
                    def test_never_runs(self): pathlib.Path({str(marker)!r}).write_text('ran')
            """), encoding="utf-8")
            (tests / "test_broken_after_selection.py").write_text(
                "raise RuntimeError('default discovery exploded')\n", encoding="utf-8"
            )
            selected_id = "test_selected_before_error.Selected.test_never_runs"
            with mock.patch.object(
                self.runner,
                "NATIVE_COVERAGE",
                {"installation_cleanup": (selected_id,)},
            ):
                with self.assertRaisesRegex(RuntimeError, "discovery|exploded|loader"):
                    run_native("windows", root=root, emit=lambda value: None)
            self.assertFalse(marker.exists(), "loader errors must stop before test execution")

    def test_default_native_run_uses_fresh_interpreter_and_cleans_fixtures(self):
        run_native = self.require_api("run_native_validation")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / ".agents"
            tests.mkdir()
            evidence = root / "child.json"
            residue = root / "fixture-residue"
            (tests / "test_process_boundary.py").write_text(textwrap.dedent(f"""
                import json, os, pathlib, unittest
                EVIDENCE = pathlib.Path({str(evidence)!r})
                RESIDUE = pathlib.Path({str(residue)!r})
                class ProcessBoundary(unittest.TestCase):
                    def setUp(self): RESIDUE.write_text('live')
                    def tearDown(self): RESIDUE.unlink()
                    def test_child(self):
                        EVIDENCE.write_text(json.dumps({{'pid': os.getpid(), 'residue': RESIDUE.exists()}}))
            """), encoding="utf-8")
            selected_id = "test_process_boundary.ProcessBoundary.test_child"
            emitted = []
            with mock.patch.object(
                self.runner,
                "NATIVE_COVERAGE",
                {"installation_cleanup": (selected_id,)},
            ):
                report = run_native("windows", root=root, emit=emitted.append)
            child = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertNotEqual(os.getpid(), child["pid"])
            self.assertTrue(child["residue"], "setUp must execute in the child test process")
            self.assertFalse(residue.exists(), "tearDown must clean the isolated fixture")
            self.assertEqual([report], emitted)
            self.assertEqual([selected_id], report["selected_ids"])
            self.assertEqual(1, report["tests_run"])

    def test_default_native_run_rejects_ordinary_skip_from_child_process(self):
        run_native = self.require_api("run_native_validation")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / ".agents"
            tests.mkdir()
            (tests / "test_ordinary_skip.py").write_text(textwrap.dedent("""
                import unittest
                class OrdinarySkip(unittest.TestCase):
                    @unittest.skip("developer preference")
                    def test_skipped(self): pass
            """), encoding="utf-8")
            selected_id = "test_ordinary_skip.OrdinarySkip.test_skipped"
            with mock.patch.object(
                self.runner,
                "NATIVE_COVERAGE",
                {"installation_cleanup": (selected_id,)},
            ):
                with self.assertRaisesRegex(ValueError, "skip|facility|evidence"):
                    run_native("macos", root=root, emit=lambda value: None)

    def test_native_run_reports_selected_tests_from_fresh_launcher(self):
        run_native = self.require_api("run_native_validation")
        observation = {
            "returncode": 0, "tests_run": len(REQUIRED_NATIVE_IDS),
            "executed_ids": sorted(REQUIRED_NATIVE_IDS),
            "failures": 0, "errors": 0, "skips": [],
            "durations": {test_id: 0.01 for test_id in REQUIRED_NATIVE_IDS},
        }
        report = run_native(
            "macos", discover=lambda: set(REQUIRED_NATIVE_IDS),
            launch=lambda selected: observation,
            clock=iter((10.0, 10.5)).__next__, emit=lambda value: None,
        )
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
            "executed_ids": sorted(REQUIRED_NATIVE_IDS),
            "failures": 0,
            "errors": 0,
            "skips": [
                {
                    "id": sorted(REQUIRED_NATIVE_IDS)[0],
                    "kind": "unavailable_native_facility",
                    "reason": "Windows symlink privilege unavailable",
                    "evidence": "OSError: privilege not held",
                },
                {
                    "id": sorted(REQUIRED_NATIVE_IDS)[1],
                    "kind": "unavailable_native_facility",
                    "reason": "native process signals unavailable",
                    "evidence": "platform has no SIGUSR1",
                },
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

    def test_execution_observation_rejects_empty_partial_mismatch_and_duplicates(self):
        run_native = self.require_api("run_native_validation")
        selected = sorted(REQUIRED_NATIVE_IDS)
        valid = {
            "returncode": 0, "tests_run": len(selected), "executed_ids": selected,
            "failures": 0, "errors": 0, "skips": [], "durations": {},
        }
        invalid = {
            "empty": {**valid, "tests_run": 0, "executed_ids": []},
            "partial": {**valid, "tests_run": len(selected) - 1, "executed_ids": selected[:-1]},
            "count mismatch": {**valid, "tests_run": len(selected) - 1},
            "duplicate": {**valid, "executed_ids": selected[:-1] + [selected[0]]},
        }
        for label, observation in invalid.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "empty|partial|count|mismatch|duplicate|executed"):
                    run_native(
                        "windows", discover=lambda: set(REQUIRED_NATIVE_IDS),
                        launch=lambda _selected, value=observation: value,
                        clock=iter((1.0, 1.1)).__next__, emit=lambda value: None,
                    )

    def test_skips_require_selected_id_reason_and_native_facility_evidence(self):
        run_native = self.require_api("run_native_validation")
        selected = sorted(REQUIRED_NATIVE_IDS)
        base = {
            "returncode": 0, "tests_run": len(selected), "executed_ids": selected,
            "failures": 0, "errors": 0, "durations": {},
        }
        invalid_skips = (
            [{"id": "not.selected", "kind": "unavailable_native_facility", "reason": "facility unavailable", "evidence": "probe failed"}],
            [{"id": selected[0], "kind": "unavailable_native_facility", "reason": "", "evidence": "probe failed"}],
            [{"id": selected[0], "kind": "unavailable_native_facility", "reason": "facility unavailable", "evidence": ""}],
            [{"id": selected[0], "kind": "ordinary_skip", "reason": "not requested today", "evidence": "developer preference"}],
        )
        for skips in invalid_skips:
            with self.subTest(skips=skips):
                with self.assertRaisesRegex(ValueError, "skip|selected|reason|evidence|facility"):
                    run_native(
                        "macos", discover=lambda: set(REQUIRED_NATIVE_IDS),
                        launch=lambda _selected, value={**base, "skips": skips}: value,
                        clock=iter((1.0, 1.1)).__next__, emit=lambda value: None,
                    )

    def test_failed_execution_is_reported_then_propagated(self):
        run_native = self.require_api("run_native_validation")
        emitted = []
        observation = {
            "returncode": 1,
            "tests_run": len(REQUIRED_NATIVE_IDS),
            "executed_ids": sorted(REQUIRED_NATIVE_IDS),
            "failures": 1,
            "errors": 2,
            "skips": [{
                "id": sorted(REQUIRED_NATIVE_IDS)[0],
                "kind": "unavailable_native_facility",
                "reason": "native facility unavailable",
                "evidence": "OSError from facility probe",
            }],
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
                {
                    "id": sorted(REQUIRED_NATIVE_IDS)[0],
                    "kind": "unavailable_native_facility",
                    "reason": "facility unavailable",
                    "evidence": "native probe returned ENOTSUP",
                }
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
            sorted(REQUIRED_NATIVE_IDS)[0],
            "facility unavailable",
            "native probe returned ENOTSUP",
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
        assert_required_gate_contract(self, workflow)

        mutations = {
            "echo no-op": workflow.replace(
                "          python .github/scripts/require_validation.py",
                "          echo python .github/scripts/require_validation.py",
                1,
            ),
            "comment-only decoy": workflow.replace(
                "        run: >-",
                "        run: echo no-op",
                1,
            ) + "\n# python .github/scripts/require_validation.py linux=${{ needs.validate-linux.result }} windows=${{ needs.validate-windows.result }} macos=${{ needs.validate-macos.result }} claude=${{ needs.validate-claude.result }}\n",
            "other-job decoy": workflow.replace(
                "        run: >-",
                "        run: echo no-op",
                1,
            ) + """

  decoy-aggregation:
    runs-on: ubuntu-latest
    steps:
      - run: >-
          python .github/scripts/require_validation.py
          linux=${{ needs.validate-linux.result }}
          windows=${{ needs.validate-windows.result }}
          macos=${{ needs.validate-macos.result }}
          claude=${{ needs.validate-claude.result }}
""",
            "missing result": workflow.replace(
                "          claude=${{ needs.validate-claude.result }}\n", "", 1
            ),
        }
        for label, mutated in mutations.items():
            with self.subTest(label=label):
                with self.assertRaises(AssertionError):
                    assert_required_gate_contract(self, mutated)

    def test_required_gate_propagates_every_result_state_and_missing_input(self):
        script = ROOT / ".github" / "scripts" / "require_validation.py"

        def invoke(*results):
            return subprocess.run(
                [sys.executable, str(script), *results], cwd=ROOT,
                text=True, capture_output=True, check=False,
            )

        success = invoke("linux=success", "windows=success", "macos=success", "claude=success")
        self.assertEqual(0, success.returncode, success.stderr)
        for state in ("failure", "cancelled", "skipped"):
            with self.subTest(state=state):
                failed = invoke(
                    "linux=success", f"windows={state}",
                    "macos=success", "claude=success",
                )
                self.assertNotEqual(0, failed.returncode)
                self.assertIn(f"windows={state}", failed.stderr)
        for missing in (
            (),
            ("linux=success", "windows=success", "macos=success", "claude="),
            ("linux=success", "windows=success", "macos=success", "claude"),
        ):
            with self.subTest(missing=missing):
                failed = invoke(*missing)
                self.assertNotEqual(0, failed.returncode)


if __name__ == "__main__":
    unittest.main()
