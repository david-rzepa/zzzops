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
import threading
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

    def test_repository_discovery_contains_each_canonical_test_once(self):
        loader = unittest.TestLoader()
        suite = loader.discover(
            str(ROOT / ".agents"), pattern="test_*.py",
            top_level_dir=str(ROOT / ".agents"),
        )
        self.assertEqual([], loader.errors)

        def test_ids(group):
            for test in group:
                if isinstance(test, unittest.TestSuite):
                    yield from test_ids(test)
                else:
                    yield test.id()

        discovered = list(test_ids(suite))
        self.assertEqual(
            len(discovered), len(set(discovered)),
            "imported TestCase classes must not be collected a second time",
        )

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


class NativeWorkerContractTests(unittest.TestCase):
    def setUp(self):
        self.runner = load_runner()
        self.selected = sorted(REQUIRED_NATIVE_IDS)

    def observation(self, batch):
        return {"returncode": 0, "tests_run": len(batch), "executed_ids": list(batch),
                "completed_ids": list(batch), "failures": 0, "errors": 0,
                "skips": [], "invalid_skips": [], "durations": {item: .1 for item in batch}}

    def invoke(self, launch, emit=lambda report: None):
        return self.runner.run_native_validation("windows", discover=lambda: self.selected,
                                                  launch=launch, workers=2, emit=emit)

    def test_native_workers_overlap_and_complete_exact_selection(self):
        barrier = threading.Barrier(2)
        def launch(batch):
            barrier.wait(timeout=5)
            return self.observation(batch)
        report = self.invoke(launch)
        self.assertEqual(self.selected, sorted(report["executed_ids"]))
        self.assertEqual(self.selected, sorted(report["completed_ids"]))
        self.assertEqual(11, report["tests_run"])
        self.assertEqual(2, report["workers"])
        self.assertEqual(2, len(report["worker_reports"]))

    def test_native_child_failure_and_invalid_execution_fail_closed(self):
        for field, value, error in (
            ("returncode", 1, subprocess.CalledProcessError),
            ("failures", 1, subprocess.CalledProcessError),
            ("errors", 1, subprocess.CalledProcessError),
            ("executed_ids", [], ValueError),
            ("completed_ids", [], ValueError),
            ("executed_ids", ["unknown"], ValueError),
            ("executed_ids", ["duplicate", "duplicate"], ValueError),
            ("invalid_skips", [{"id": self.selected[0], "reason": "unsupported"}], ValueError),
        ):
            with self.subTest(field=field, value=value):
                def launch(batch):
                    observation = self.observation(batch)
                    if self.selected[0] in batch:
                        observation[field] = value
                    return observation
                with self.assertRaises(error):
                    self.invoke(launch)

    def test_native_workers_preserve_only_evidenced_facility_skips(self):
        def launch(batch):
            observation = self.observation(batch)
            if self.selected[0] in batch:
                observation["skips"] = [{"id": self.selected[0],
                    "kind": "unavailable_native_facility", "reason": "unavailable",
                    "evidence": "probe ENOTSUP"}]
            return observation
        report = self.invoke(launch)
        self.assertEqual(1, report["skipped"])
        self.assertEqual("probe ENOTSUP", report["coverage_limits"][0]["evidence"])
        def invalid_launch(batch):
            observation = launch(batch)
            for skip in observation["skips"]:
                skip.pop("evidence")
            return observation
        with self.assertRaisesRegex(ValueError, "evidence"):
            self.invoke(invalid_launch)

    def test_native_worker_exception_joins_sibling_before_propagating(self):
        barrier = threading.Barrier(2)
        finished = threading.Event()
        def launch(batch):
            barrier.wait(timeout=5)
            if self.selected[0] in batch:
                raise RuntimeError("native child crashed")
            finished.set()
            return self.observation(batch)
        with self.assertRaisesRegex(RuntimeError, "native child crashed"):
            self.invoke(launch)
        self.assertTrue(finished.is_set())

    def test_cli_allows_native_workers_without_linux_shard_options(self):
        with mock.patch.object(sys, "argv", ["runner", "--platform", "windows", "--workers", "2"]), \
                mock.patch.object(self.runner, "run_native_validation") as native:
            self.assertEqual(0, self.runner.main())
        native.assert_called_once_with("windows", workers=2)


class LinuxShardContractTests(unittest.TestCase):
    def setUp(self):
        self.runner = load_runner()

    def test_balanced_partition_is_deterministic_complete_disjoint_and_includes_new_tests(self):
        inventory = [f"test_module.Case.test_{index:02}" for index in range(24)]
        weights = {test: float(index + 1) for index, test in enumerate(inventory[:-1])}
        # A historical timing entry cannot select an absent test.
        weights["removed.test"] = 9999
        shards = self.runner.partition_linux_tests(inventory, 4, weights)
        self.assertEqual(shards, self.runner.partition_linux_tests(reversed(inventory), 4, weights))
        flattened = [test for shard in shards for test in shard]
        self.assertEqual(sorted(inventory), sorted(flattened))
        self.assertEqual(len(flattened), len(set(flattened)))
        self.assertTrue(all(shard == sorted(shard) and shard for shard in shards))
        loads = [sum(weights.get(test, 10) for test in shard) for shard in shards]
        loads[0] += self.runner.LINUX_AUXILIARY_SECONDS
        self.assertLessEqual(max(loads) - min(loads), max(weights[test] for test in inventory[:-1]))
        small = self.runner.partition_linux_tests(["a", "b", "c"], 3, {}, fallback=1)
        self.assertTrue(all(len(shard) == 1 for shard in small),
                        "Auxiliary overhead cannot starve shard zero in a small inventory")

    def test_partition_rejects_empty_duplicate_and_invalid_shard_counts(self):
        for inventory, count in (([], 1), (["a", "a"], 1), (["a"], 0), (["a"], 2), (["a"], True)):
            with self.subTest(inventory=inventory, count=count):
                with self.assertRaises(ValueError):
                    self.runner.partition_linux_tests(inventory, count, {})

    def test_real_linux_discovery_rejects_duplicate_aliases_and_loader_errors(self):
        for source, error in (
            ("import unittest\nclass Case(unittest.TestCase):\n def test_one(self): pass\nAlias = Case\n", "duplicate"),
            ("raise RuntimeError('broken Linux inventory')\n", "loader"),
        ):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                tests = Path(directory) / ".agents"
                tests.mkdir()
                name = "test_linux_discovery_" + error
                (tests / (name + ".py")).write_text(source, encoding="utf-8")
                try:
                    with self.assertRaisesRegex((ValueError, RuntimeError), error):
                        self.runner.discover_linux_tests(Path(directory))
                finally:
                    sys.modules.pop(name, None)

    def test_each_python_inventory_partitions_exactly_once_and_timings_only_guide_balance(self):
        inventory = self.runner.discover_linux_tests()
        weights, fallback = self.runner.load_linux_timings()
        shards = self.runner.partition_linux_tests(inventory, 8, weights, fallback)
        self.assertEqual(inventory, sorted(test for shard in shards for test in shard))
        # Even an entirely stale or absent timing inventory cannot omit a test.
        unprofiled = self.runner.partition_linux_tests(inventory, 8, {}, fallback)
        self.assertEqual(inventory, sorted(test for shard in unprofiled for test in shard))

    def test_linux_observation_rejects_missing_duplicate_partial_and_unfinished_execution(self):
        selected = ["test_one.Case.test_one", "test_two.Case.test_two"]
        valid = {"returncode": 0, "tests_run": 2, "executed_ids": selected,
                 "completed_ids": selected, "failures": 0, "errors": 0,
                 "invalid_skips": [], "skips": []}
        self.runner._validate_linux_observation(selected, valid)
        mutations = (
            {"executed_ids": []}, {"executed_ids": selected[:1], "tests_run": 1},
            {"executed_ids": [selected[0], selected[0]]},
            {"executed_ids": [selected[0], "unexpected.Case.test_extra"]},
            {"completed_ids": selected[:1]}, {"completed_ids": [selected[0], selected[0]]},
            {"completed_ids": []}, {"failures": None}, {"returncode": False},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.runner._validate_linux_observation(selected, {**valid, **mutation})

    def test_shard_reports_exact_execution_and_runs_auxiliary_checks_only_on_zero(self):
        selected = ["test_one.Case.test_one"]
        observation = {"returncode": 0, "tests_run": 1, "executed_ids": selected,
                       "completed_ids": selected, "failures": 0, "errors": 0,
                       "invalid_skips": [], "skips": [], "durations": {selected[0]: .01}}
        with tempfile.TemporaryDirectory() as directory:
            for index in (0, 1):
                plan = {"python_version": "3.14", "shard_index": index, "shard_count": 8,
                        "selected_ids": selected, "selected_count": 1, "inventory_count": 8,
                        "auxiliary_checks": index == 0, "estimated_test_seconds": .01}
                path = Path(directory) / f"python-3.14-shard-{index}.json"
                with mock.patch.object(self.runner, "linux_shard_plan", return_value=plan), \
                        mock.patch.object(self.runner, "_launch_native", return_value=observation), \
                        mock.patch.object(self.runner, "linux_auxiliary_validation") as auxiliary, \
                        mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(Path(directory) / "summary")}), \
                        mock.patch("builtins.print"):
                    report = self.runner.run_linux_shard(index, 8, path)
                self.assertEqual("success", report["status"])
                self.assertEqual(selected, json.loads(path.read_text())["completed_ids"])
                self.assertEqual(index == 0, auxiliary.called)
            self.assertIn("selected/executed/completed: 1/1/1", (Path(directory) / "summary").read_text())

    def test_failed_shard_keeps_failure_report_and_never_runs_auxiliary_checks(self):
        selected = ["test_one.Case.test_one"]
        plan = {"python_version": "3.14", "selected_ids": selected, "selected_count": 1,
                "inventory_count": 8, "auxiliary_checks": True, "estimated_test_seconds": .01}
        failed = {"returncode": 0, "tests_run": 1, "executed_ids": selected,
                  "completed_ids": selected, "failures": 1, "errors": 0}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "failed.json"
            with mock.patch.object(self.runner, "linux_shard_plan", return_value=plan), \
                    mock.patch.object(self.runner, "_launch_native", return_value=failed), \
                    mock.patch.object(self.runner, "linux_auxiliary_validation") as auxiliary, \
                    mock.patch.dict(os.environ, {}, clear=True), mock.patch("builtins.print"):
                with self.assertRaises(subprocess.CalledProcessError):
                    self.runner.run_linux_shard(0, 8, path)
            self.assertEqual("failed", json.loads(path.read_text())["status"])
            auxiliary.assert_not_called()

    def test_worker_partitions_balance_without_auxiliary_reserve_and_guard_exclusive_ids(self):
        selected = ["a", "b", "c", "d", *self.runner.LINUX_EXCLUSIVE_TESTS]
        with mock.patch.object(self.runner, "load_linux_timings", return_value=({}, 1)):
            batches, exclusive = self.runner.linux_worker_plan(selected, 2)
            reversed_batches, _ = self.runner.linux_worker_plan(list(reversed(selected)), 2)
        self.assertEqual(batches, reversed_batches)
        self.assertEqual([2, 2], [len(batch) for batch in batches])
        self.assertEqual(list(self.runner.LINUX_EXCLUSIVE_TESTS), exclusive)
        self.assertEqual(sorted(selected), sorted(sum(batches, []) + exclusive))
        self.assertEqual(([selected], []), self.runner.linux_worker_plan(selected, 1))
        for invalid in (0, 3, True):
            with self.assertRaises(ValueError):
                self.runner.linux_worker_plan(selected, invalid)
        with mock.patch.object(self.runner, "discover_linux_tests", return_value=["a"]):
            with self.assertRaisesRegex(ValueError, "exclusive test IDs missing"):
                self.runner.linux_shard_plan(0, 1)

    def test_two_workers_overlap_and_exclusive_test_runs_only_after_both_finish(self):
        exclusive = list(self.runner.LINUX_EXCLUSIVE_TESTS)
        selected = ["a", "b", *exclusive]
        barrier = threading.Barrier(2)
        finished = []
        def launch(batch, root):
            if batch == exclusive:
                self.assertEqual(["a", "b"], sorted(finished))
            else:
                barrier.wait(timeout=5)
                finished.extend(batch)
            return {"returncode": 0, "tests_run": len(batch), "executed_ids": batch,
                    "completed_ids": batch, "failures": 0, "errors": 0,
                    "durations": {item: .1 for item in batch}}
        plan = {"selected_ids": selected, "auxiliary_checks": False}
        with mock.patch.object(self.runner, "linux_shard_plan", return_value=plan), \
                mock.patch.object(self.runner, "_launch_native", side_effect=launch), \
                mock.patch.dict(os.environ, {}, clear=True), mock.patch("builtins.print"):
            report = self.runner.run_linux_shard(1, 8, workers=2)
        self.assertEqual("success", report["status"])
        self.assertEqual(2, report["workers"])
        self.assertEqual(exclusive, report["serial_ids"])
        self.assertEqual(sorted(selected), sorted(report["executed_ids"]))
        self.assertEqual(sorted(selected), sorted(report["completed_ids"]))
        self.assertEqual([False, False, True], [item["serial"] for item in report["worker_reports"]])

    def test_worker_merge_preserves_failures_and_rejects_duplicate_observations(self):
        def observation(test_id, failures=0):
            return {"returncode": failures, "tests_run": 1, "executed_ids": [test_id],
                    "completed_ids": [test_id], "failures": failures, "errors": 0,
                    "durations": {test_id: .1}}
        merged = self.runner._combine_linux_observations([observation("a", 1), observation("b")])
        self.assertEqual(1, merged["returncode"])
        self.assertEqual(1, merged["failures"])
        self.assertEqual(2, merged["tests_run"])
        self.assertEqual({"a": .1, "b": .1}, merged["durations"])
        with self.assertRaisesRegex(ValueError, "duplicate duration"):
            self.runner._combine_linux_observations([observation("a"), observation("a")])
        duplicate = observation("a")
        duplicate.pop("durations")
        merged = self.runner._combine_linux_observations([duplicate, duplicate])
        with self.assertRaisesRegex(ValueError, "duplicate executed"):
            self.runner._validate_linux_observation(["a", "b"], merged)

    def test_worker_failure_cannot_be_overwritten_by_successful_sibling(self):
        plan = {"selected_ids": ["a", "b"], "auxiliary_checks": True}
        def launch(batch, root):
            failed = int("a" in batch)
            return {"returncode": failed, "tests_run": len(batch), "executed_ids": batch,
                    "completed_ids": batch, "failures": failed, "errors": 0,
                    "selected_ids": ["malicious overwrite"], "workers": 999}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "failed.json"
            with mock.patch.object(self.runner, "linux_shard_plan", return_value=plan), \
                    mock.patch.object(self.runner, "_launch_native", side_effect=launch), \
                    mock.patch.object(self.runner, "linux_auxiliary_validation") as auxiliary, \
                    mock.patch.dict(os.environ, {}, clear=True), mock.patch("builtins.print"):
                with self.assertRaises(subprocess.CalledProcessError):
                    self.runner.run_linux_shard(0, 8, path, workers=2)
            report = json.loads(path.read_text())
        self.assertEqual("failed", report["status"])
        self.assertEqual(1, report["failures"])
        self.assertEqual(["a", "b"], report["selected_ids"])
        self.assertEqual(2, report["workers"])
        self.assertEqual(2, len(report["worker_reports"]))
        auxiliary.assert_not_called()

    def test_crashed_worker_retains_successful_sibling_evidence(self):
        exclusive = self.runner.LINUX_EXCLUSIVE_TESTS[0]
        for crashing_id in ("a", exclusive):
            with self.subTest(crashing_id=crashing_id):
                plan = {"selected_ids": ["a", "b", exclusive], "auxiliary_checks": False}
                def launch(batch, root):
                    if crashing_id in batch:
                        raise RuntimeError("child exited without a report")
                    return {"returncode": 0, "tests_run": len(batch), "executed_ids": batch,
                            "completed_ids": batch, "failures": 0, "errors": 0}
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "crashed.json"
                    with mock.patch.object(self.runner, "linux_shard_plan", return_value=plan), \
                            mock.patch.object(self.runner, "_launch_native", side_effect=launch), \
                            mock.patch.dict(os.environ, {}, clear=True), mock.patch("builtins.print"):
                        with self.assertRaisesRegex(RuntimeError, "without a report"):
                            self.runner.run_linux_shard(1, 8, path, workers=2)
                    report = json.loads(path.read_text())
                self.assertEqual("failed", report["status"])
                self.assertEqual(3, len(report["worker_reports"]))
                self.assertEqual(["b"], report["worker_reports"][1]["observation"]["completed_ids"])
                failed = [worker for worker in report["worker_reports"] if "error" in worker]
                self.assertEqual(1, len(failed))
                self.assertEqual([crashing_id], failed[0]["selected_ids"])
                self.assertEqual(crashing_id == exclusive, failed[0]["serial"])
                self.assertNotIn("observation", failed[0])

    def test_workflow_runs_eight_shards_on_both_pythons_with_unique_reports(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        linux = workflow.split("  validate-linux:", 1)[1].split("  validate-windows:", 1)[0]
        self.assertIn("uses: actions/checkout@v4\n        with:\n          fetch-depth: 0", linux,
                      "Published-tag contracts must execute rather than skip in shallow checkouts")
        self.assertIn("fail-fast: false", linux)
        self.assertIn("python-version: ['3.10', '3.14']", linux)
        self.assertIn("shard: [0, 1, 2, 3, 4, 5, 6, 7]", linux)
        self.assertIn("--shard-index ${{ matrix.shard }} --shard-count 8", linux)
        self.assertIn("--workers 2", linux)
        self.assertIn("if-no-files-found: error", linux)
        self.assertEqual(2, linux.count("if: matrix.shard == 0"))
        self.assertIn("name: linux-python-${{ matrix.python-version }}-shard-${{ matrix.shard }}", linux)
        assert_required_gate_contract(self, workflow)


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

        def replace_required_run():
            # Linux also uses a folded command now; mutate the required gate.
            prefix, required = workflow.split("  required:", 1)
            return prefix + "  required:" + required.replace("        run: >-", "        run: echo no-op", 1)

        mutations = {
            "echo no-op": workflow.replace(
                "          python .github/scripts/require_validation.py",
                "          echo python .github/scripts/require_validation.py",
                1,
            ),
            "comment-only decoy": replace_required_run() + "\n# python .github/scripts/require_validation.py linux=${{ needs.validate-linux.result }} windows=${{ needs.validate-windows.result }} macos=${{ needs.validate-macos.result }} claude=${{ needs.validate-claude.result }}\n",
            "other-job decoy": replace_required_run() + """

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
