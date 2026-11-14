"""G1043 local individual-ID execution: tiny inventories, fake children and one real child."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

import test_ci_selection as ci


def observation(batch, **over):
    value = {"returncode": 0, "tests_run": len(batch), "executed_ids": list(batch),
             "completed_ids": list(batch), "failures": 0, "errors": 0,
             "skips": [], "invalid_skips": [], "durations": {item: 0.01 for item in batch}}
    value.update(over)
    return value


class LocalRunnerTests(unittest.TestCase):
    def setUp(self):
        self.runner = ci.load_runner()
        self.inventory = [f"test_tiny.Case.test_{i}" for i in range(7)]
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.report_path = Path(self.tmp.name, "report.json")

    def api(self):
        value = getattr(self.runner, "run_local_validation", None)
        self.assertTrue(callable(value), "local mode exposes run_local_validation(root, workers, report_path)")
        return value

    def invoke(self, workers=None, inventory=None, launch=None, parent=None, cpus=4, exclusive=()):
        affinity = mock.patch.object(os, "sched_getaffinity", return_value=set(range(cpus)), create=True)
        env = {k: v for k, v in os.environ.items() if k not in ("ZZZOPS_TEST_WORKERS", "GITHUB_STEP_SUMMARY")}
        if parent is not None:
            env["ZZZOPS_TEST_WORKERS"] = str(parent)
        with mock.patch.dict(os.environ, env, clear=True), affinity, \
                mock.patch.object(os, "cpu_count", return_value=cpus), \
                mock.patch.object(self.runner, "discover_linux_tests", return_value=self.inventory if inventory is None else inventory), \
                mock.patch.object(self.runner, "load_linux_timings", return_value=({"removed.test": 9999}, 1)), \
                mock.patch.object(self.runner, "LINUX_EXCLUSIVE_TESTS", exclusive), \
                mock.patch.object(self.runner, "linux_auxiliary_validation") as auxiliary, \
                mock.patch.object(self.runner, "_launch_native", side_effect=launch or (lambda batch, root: observation(batch))), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            value = self.api()(root=Path(self.tmp.name), workers=workers, report_path=self.report_path)
        auxiliary.assert_not_called()
        return value, stdout.getvalue()

    def assert_inventory(self, report, expected):
        self.assertEqual("success", report["status"])
        self.assertEqual(len(expected), report["inventory_count"])
        self.assertEqual(sorted(expected), sorted(report["executed_ids"]))
        self.assertEqual(sorted(expected), sorted(report["completed_ids"]))
        self.assertEqual(len(expected), len(set(report["executed_ids"])))
        self.assertEqual(64, len(report["inventory_sha256"]))

    def test_one_auto_explicit_and_parent_limits_never_change_membership(self):
        for requested, parent, cpus, expected in ((1, None, 4, 1), (None, None, 4, 4),
                                                (6, None, 4, 4), (6, 2, 20, 2),
                                                (None, 1, 20, 1), (99, None, 99, 7)):
            with self.subTest(workers=requested, parent=parent, cpus=cpus):
                report, _ = self.invoke(workers=requested, parent=parent, cpus=cpus)
                self.assert_inventory(report, self.inventory)
                self.assertEqual(expected, report["workers"])
                self.assertTrue(all(w["selected_ids"] for w in report["worker_reports"]))
                self.assertTrue(all("wall_seconds" in w for w in report["worker_reports"]))

    def test_affinity_fallback_uses_cpu_count_then_one(self):
        for count, expected in ((3, 3), (None, 1)):
            with self.subTest(cpu_count=count), \
                    mock.patch.object(os, "sched_getaffinity", side_effect=OSError("not available"), create=True), \
                    mock.patch.object(os, "cpu_count", return_value=count), \
                    mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(self.runner, "discover_linux_tests", return_value=self.inventory), \
                    mock.patch.object(self.runner, "load_linux_timings", return_value=({}, 1)), \
                    mock.patch.object(self.runner, "LINUX_EXCLUSIVE_TESTS", ()), \
                    mock.patch.object(self.runner, "_launch_native", side_effect=lambda batch, root: observation(batch)), \
                    mock.patch("builtins.print"):
                report = self.api()(root=Path(self.tmp.name))
                self.assertEqual(expected, report["workers"])
                self.assert_inventory(report, self.inventory)

    def test_invalid_budget_and_workers_fail_before_child_launch(self):
        for worker, parent in ((0, None), (-1, None), (True, None), (None, "0"),
                               (None, "-1"), (None, "x"), (None, "1.5")):
            calls = []
            with self.subTest(worker=worker, parent=parent):
                with self.assertRaises((ValueError, SystemExit)):
                    self.invoke(workers=worker, parent=parent, launch=lambda b, r: calls.append(b))
                self.assertEqual([], calls)

    def test_empty_duplicate_and_loader_error_fail_before_launch(self):
        for inventory in ([], ["duplicate", "duplicate"]):
            calls = []
            with self.subTest(inventory=inventory), self.assertRaises((ValueError, RuntimeError)):
                self.invoke(inventory=inventory, launch=lambda b, r: calls.append(b))
            self.assertEqual([], calls)
        self.api()
        with mock.patch.object(self.runner, "discover_linux_tests", side_effect=RuntimeError("loader failed")), \
                mock.patch.object(self.runner, "_launch_native") as launch:
            with self.assertRaisesRegex(RuntimeError, "loader failed"):
                self.runner.run_local_validation(root=Path(self.tmp.name))
            launch.assert_not_called()

    def test_compact_stdout_and_complete_report(self):
        report, stdout = self.invoke()
        written = json.loads(self.report_path.read_text())
        self.assert_inventory(written, self.inventory)
        self.assertTrue(stdout.strip(), "local invocation prints one compact outcome")
        self.assertFalse(all(test_id in stdout for test_id in self.inventory), "default stdout may show slowest IDs but not the full inventory")
        for full_payload in ("selected_ids", "executed_ids", "completed_ids"):
            self.assertNotIn(full_payload, stdout, "full ID inventories belong in the report")
        self.assertEqual(report["inventory_sha256"], written["inventory_sha256"])
        self.assertIn("wall_seconds", written)
        self.assertIn("aggregate_test_seconds", written)
        self.assertIn("worker_reports", written)

    def test_invalid_completion_and_failures_write_reports_and_join_all_children(self):
        self.api()
        mutations = {
            "missing completion": lambda b: observation(b, completed_ids=list(b)[:-1]),
            "duplicate completion": lambda b: observation(b, completed_ids=[*b, b[0]]),
            "unexpected completion": lambda b: observation(b, completed_ids=[*b, "unexpected"]),
            "ordinary skip": lambda b: observation(b, invalid_skips=[{"id": b[0], "reason": "unsupported guess"}]),
            "test failure": lambda b: observation(b, returncode=1, failures=1),
            "crash": lambda b: (_ for _ in ()).throw(RuntimeError("child crashed without report")),
        }
        for label, mutate in mutations.items():
            joined = []
            def launch(batch, root):
                try:
                    return mutate(batch) if self.inventory[0] in batch else observation(batch)
                finally:
                    joined.extend(batch)
            with self.subTest(case=label):
                with self.assertRaises(Exception):
                    self.invoke(workers=3, launch=launch)
                report = json.loads(self.report_path.read_text())
                self.assertEqual("failed", report["status"])
                self.assertEqual(sorted(self.inventory), sorted(joined))
                self.assertEqual(3, len(report["worker_reports"]))
                self.assertTrue(any("observation" in w for w in report["worker_reports"]))

    def test_pool_workers_overlap_and_synthetic_exclusive_runs_after_every_join(self):
        barrier = threading.Barrier(2)
        exclusive = "test_synthetic.Exclusive.test_serial"
        finished = []
        lock = threading.Lock()
        def launch(batch, root):
            if batch == [exclusive]:
                self.assertEqual(["a", "b"], sorted(finished))
            else:
                barrier.wait(timeout=5)
                with lock:
                    finished.extend(batch)
            return observation(batch)
        report, _ = self.invoke(workers=2, inventory=["a", "b", exclusive], exclusive=(exclusive,), launch=launch)
        self.assert_inventory(report, ["a", "b", exclusive])
        self.assertEqual([exclusive], report["serial_ids"])
        self.assertEqual([False, False, True], [w["serial"] for w in report["worker_reports"]])

    def test_exclusive_only_inventory_needs_no_concurrent_pool(self):
        exclusive = "test_synthetic.Exclusive.test_serial"
        report, _ = self.invoke(inventory=[exclusive], exclusive=(exclusive,))
        self.assert_inventory(report, [exclusive])
        self.assertEqual(1, len(report["worker_reports"]))
        self.assertTrue(report["worker_reports"][0]["serial"])

    def test_stale_property_is_not_configured_as_exclusive(self):
        self.assertNotIn("test_engine_property.NoDeadEndPropertyTests.test_random_portfolios",
                         self.runner.LINUX_EXCLUSIVE_TESTS)
        source = ci.RUNNER_PATH.read_text()
        self.assertNotIn("one-second wall-clock contract", source)

    def test_real_child_completes_tiny_inventory_once(self):
        self.api()
        agents = Path(self.tmp.name, ".agents")
        agents.mkdir()
        (agents / "test_g1043_tiny.py").write_text("import unittest\nclass Tiny(unittest.TestCase):\n    def test_one(self): self.assertEqual(2, 1+1)\n    def test_two(self): self.assertTrue(True)\n")
        inventory = ["test_g1043_tiny.Tiny.test_one", "test_g1043_tiny.Tiny.test_two"]
        # Preserve the actual fresh-interpreter child runner in this one probe.
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(self.runner, "LINUX_EXCLUSIVE_TESTS", ()), \
                mock.patch.object(self.runner, "load_linux_timings", return_value=({}, 1)), \
                mock.patch("builtins.print"):
            report = self.runner.run_local_validation(root=Path(self.tmp.name), workers=2, report_path=self.report_path)
        self.assert_inventory(report, inventory)
        self.assertEqual(set(inventory), set(report["durations"]))


class LocalCliTests(unittest.TestCase):
    def test_local_explicit_workers_and_report_dispatch_without_ci_or_auxiliary(self):
        runner = ci.load_runner()
        self.assertTrue(hasattr(runner, "run_local_validation"))
        path = Path("local.json")
        with mock.patch.object(sys, "argv", ["runner", "--platform", "linux", "--local", "--workers", "7", "--report", str(path)]), \
                mock.patch.object(runner, "run_local_validation") as local, \
                mock.patch.object(runner, "run_linux_shard") as shard, \
                mock.patch.object(runner, "linux_auxiliary_validation") as auxiliary:
            self.assertEqual(0, runner.main())
        self.assertEqual(1, local.call_count)
        self.assertEqual(7, local.call_args.kwargs.get("workers", local.call_args.args[0] if local.call_args.args else None))
        self.assertIn(path, [*local.call_args.args, *local.call_args.kwargs.values()])
        shard.assert_not_called()
        auxiliary.assert_not_called()

    def test_native_and_ci_keep_existing_worker_limits_and_local_is_linux_only(self):
        for args in (["--platform", "windows", "--workers", "3"],
                     ["--platform", "linux", "--shard-index", "0", "--shard-count", "1", "--workers", "3"],
                     ["--platform", "windows", "--local"],
                     ["--platform", "linux", "--local", "--shard-index", "0", "--shard-count", "2"]):
            runner = ci.load_runner()
            with self.subTest(args=args), mock.patch.object(sys, "argv", ["runner", *args]), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                runner.main()
            self.assertEqual(2, error.exception.code)


if __name__ == "__main__":
    unittest.main()
