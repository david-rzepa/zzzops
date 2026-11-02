"""Retained runner evidence must identify failing children without canonical failing tests."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_ci_selection as ci


class LocalDiagnosticsTests(unittest.TestCase):
    def test_temporary_failing_child_retains_ids_tracebacks_and_completed_inventory(self):
        runner = ci.load_runner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agents = root / ".agents"
            agents.mkdir()
            name = "test_temporary_runner_diagnostics"
            self.addCleanup(sys.modules.pop, name, None)
            (agents / (name + ".py")).write_text(
                "import unittest\n"
                "class Probe(unittest.TestCase):\n"
                "    def test_a_failure(self): self.fail('unique child assertion evidence')\n"
                "    def test_b_error(self): raise RuntimeError('unique child error evidence')\n"
                "    def test_c_success(self): self.assertEqual(2, 1 + 1)\n",
                encoding="utf-8",
            )
            path = root / "report.json"
            stdout = io.StringIO()
            with mock.patch.object(runner, "LINUX_EXCLUSIVE_TESTS", ()), \
                    mock.patch.object(runner, "load_linux_timings", return_value=({}, 1)), \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(subprocess.CalledProcessError):
                    runner.run_local_validation(root=root, workers=1, report_path=path)
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("failed", report["status"])
            self.assertEqual((3, 1, 1), (report["tests_run"], report["failures"], report["errors"]))
            self.assertEqual(sorted(report["selected_ids"]), sorted(report["completed_ids"]))
            self.assertEqual(3, len(set(report["executed_ids"])))
            observed = report["worker_reports"][0]["observation"]
            for container in (report, observed):
                [failure] = container["failure_details"]
                self.assertEqual(name + ".Probe.test_a_failure", failure["id"])
                self.assertIn("unique child assertion evidence", failure["traceback"])
                [error] = container["error_details"]
                self.assertEqual(name + ".Probe.test_b_error", error["id"])
                self.assertIn("unique child error evidence", error["traceback"])
            self.assertIn("unique child assertion evidence", observed["stderr"])
            self.assertIn("unique child error evidence", observed["stderr"])
            summary = json.loads(stdout.getvalue())
            self.assertEqual("failed", summary["status"])
            self.assertNotIn("failure_details", summary)
            self.assertNotIn("unique child assertion evidence", stdout.getvalue())

    def test_crashed_temporary_child_retains_stderr_in_failure_report(self):
        runner = ci.load_runner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agents = root / ".agents"
            agents.mkdir()
            name = "test_temporary_runner_crash"
            self.addCleanup(sys.modules.pop, name, None)
            (agents / (name + ".py")).write_text(
                "import os, sys, unittest\n"
                "class Probe(unittest.TestCase):\n"
                "    def test_crash(self):\n"
                "        sys.stderr.write('unique child crash diagnostic\\n')\n"
                "        sys.stderr.flush()\n"
                "        os._exit(7)\n", encoding="utf-8",
            )
            path = root / "report.json"
            with mock.patch.object(runner, "LINUX_EXCLUSIVE_TESTS", ()), \
                    mock.patch.object(runner, "load_linux_timings", return_value=({}, 1)), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "without a report"):
                    runner.run_local_validation(root=root, workers=1, report_path=path)
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("failed", report["status"])
            self.assertNotEqual(0, report["returncode"])
            [worker] = report["worker_reports"]
            self.assertEqual([name + ".Probe.test_crash"], worker["selected_ids"])
            self.assertIn("unique child crash diagnostic", worker["error"])
            self.assertIn("exited 7", worker["error"])
