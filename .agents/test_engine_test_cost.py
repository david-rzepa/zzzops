"""G1043 checks execution/cost contract with fake processes and a controlled clock."""
from __future__ import annotations

import copy
import os
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

import engine_fixtures as fx
import test_engine_schemas as schema_fixtures
from engine import schemas
from engine.ops import checks
from engine.ops.run import OpContext


class Clock:
    def __init__(self):
        self.value = 100.0
        self.lock = threading.Lock()

    def now(self):
        with self.lock:
            return self.value

    def advance(self, value):
        with self.lock:
            self.value += value

    def finish_at(self, value):
        with self.lock:
            self.value = max(self.value, value)


class Process:
    def __init__(self, command, suite, kwargs):
        self.command, self.suite = command, suite
        self.returncode = suite.exits.get(command, 0)
        self.pid = 10000 + len(suite.processes)
        self.killed = False
        self.started = suite.clock.now()
        self.waited = False
        self.env = dict(kwargs.get("env") or os.environ)
        self.stdout = None
        suite.processes.append(self)
        suite.events.append(("start", command))

    def communicate(self, timeout=None):
        if self.command in self.suite.barrier_commands and not self.waited:
            self.waited = True
            self.suite.barrier.wait(timeout=5)
        if self.command in self.suite.timeouts and not self.killed:
            self.suite.clock.advance(60)
            raise subprocess.TimeoutExpired(self.command, timeout)
        self.suite.clock.finish_at(self.started + self.suite.durations.get(self.command, 1.25))
        self.suite.events.append(("joined", self.command))
        return (self.suite.output.get(self.command, self.command).encode(), None)

    def wait(self, timeout=None):
        self.suite.events.append(("joined", self.command))
        return self.returncode

    def poll(self):
        return self.returncode if self.killed else None


class ChecksCostTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.processes, self.events = [], []
        self.exits, self.output, self.durations = {}, {}, {}
        self.timeouts, self.barrier_commands = set(), set()
        self.barrier = threading.Barrier(2)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.git = SimpleNamespace(primary=self.tmp.name, out=lambda *a, **k: "head",
                                   run=self.git_run, config=lambda *a: None)

    def git_run(self, *args, **kwargs):
        self.assertNotIn(args[0], ("fetch", "push"), "informational baseline lookup must stay local")
        self.events.append(("git", args[0]))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def context(self, goals=("goal-one",), verification=("repository-one",), mode=None, target="dev"):
        settings = copy.deepcopy(fx.load_template("POLICY.json")["settings"])
        settings["verification"].update(commands=list(verification), timeout_minutes=1)
        if mode is not None:
            settings["verification"]["parallel_commands"] = mode
            settings["engine"] = {"requires": ["test_cost"]}
        snap = SimpleNamespace(goals={}, I="dev", R="origin", integration="target-tip")
        session = SimpleNamespace(snap=snap, git=self.git, graphs={},
                                  state=SimpleNamespace(docs={}, graphs={}))
        return OpContext(goal=1000, doc={}, node="check", node_def={}, inputs={"code": "tree", "commands": list(goals)},
                         producers={"code": "build"}, dep_kinds={}, record=None, corrections=[], answer=None,
                         settings=settings, snap=snap, git=self.git, gh=None, worktree=self.tmp.name,
                         now=1800000000, renew=lambda: None, session=session,
                         target={"branch": target, "tip": "target-tip"})

    def execute(self, context=None, cpus=20, parent=None):
        context = context or self.context()
        def popen(args, **kwargs):
            command = args[-1]
            if command == "launch-error":
                raise OSError("launch refused")
            return Process(command, self, kwargs)
        def kill(proc):
            proc.killed = True
            self.events.append(("kill", proc.command))
        env = {k: v for k, v in os.environ.items() if k != "ZZZOPS_TEST_WORKERS"}
        if parent is not None:
            env["ZZZOPS_TEST_WORKERS"] = str(parent)
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(checks, "Identity", return_value=SimpleNamespace(code_tree=lambda c: "tree")), \
                mock.patch.object(checks, "shell", return_value="fake-shell"), \
                mock.patch.object(checks.subprocess, "Popen", side_effect=popen), \
                mock.patch.object(checks, "kill_group", side_effect=kill), \
                mock.patch.object(checks.time, "monotonic", side_effect=self.clock.now), \
                mock.patch.object(os, "sched_getaffinity", return_value=set(range(cpus)), create=True), \
                mock.patch.object(os, "cpu_count", return_value=cpus):
            return checks.run(context)

    def require_timing(self):
        result = self.execute(self.context(goals=(), verification=())).output["result"]
        self.assertIn("timing", result, "checks.run must expose measured timing before concurrency probes")
        self.events.clear()
        self.processes.clear()

    def timing(self, result):
        self.assertIn("timing", result)
        timing = result["timing"]
        for key in ("total_ms", "goal_ms", "verification_ms", "cpu_budget"):
            self.assertIs(type(timing[key]), int, key)
        return timing

    def test_default_serial_order_and_integer_measurement_are_preserved(self):
        result = self.execute(self.context(goals=("g1", "g2"), verification=("v1",))).output["result"]
        self.assertEqual(["g1", "g2", "v1"], [p.command for p in self.processes])
        self.assertEqual(["g1", "g2", "v1"], [d["cmd"] for d in result["details"]])
        self.assertEqual(["goal", "goal", "verification"], [d.get("source") for d in result["details"]])
        self.assertTrue(all(type(d.get("milliseconds")) is int and d["milliseconds"] == 1250 for d in result["details"]))
        timing = self.timing(result)
        self.assertFalse(timing["parallel_commands"])
        self.assertEqual(20, timing["environment"]["cpus"])
        self.assertEqual(20, timing["cpu_budget"])
        self.assertNotIn("hostname", timing["environment"])
        self.assertEqual({"platform", "python", "cpus"}, set(timing["environment"]))
        self.assertEqual(3750, timing["total_ms"])
        self.assertEqual(2500, timing["goal_ms"])
        self.assertEqual(1250, timing["verification_ms"])
        self.assertEqual(64, len(timing["plan_sha256"]))
        self.assertEqual(64, len(timing["verification_plan_sha256"]))
        self.assertEqual("unavailable", timing["baseline"]["status"])
        self.assertEqual("no_prior_run", timing["baseline"]["reason"])
        self.assertEqual({"status": "unavailable", "reason": "no_prior_run"}, timing["baseline"]["verification"])
        self.assertTrue(result["passed"])

    def test_effective_total_is_parent_clamped_before_mode_choice_and_split(self):
        for parent, expected_mode, budget, lane in ((4, True, 4, {"goal": 2, "verification": 2}),
                                                   (1, False, 1, {"goal": 1, "verification": 1}),
                                                   (None, True, 20, {"goal": 10, "verification": 10})):
            with self.subTest(parent=parent):
                self.processes.clear()
                result = self.execute(self.context(mode=True), parent=parent).output["result"]
                timing = self.timing(result)
                self.assertEqual(expected_mode, timing["parallel_commands"])
                self.assertEqual(20, timing["environment"]["cpus"])
                self.assertEqual(budget, timing["cpu_budget"])
                self.assertEqual(lane, timing["workers"])
                for proc in self.processes:
                    source = "goal" if proc.command.startswith("goal") else "verification"
                    self.assertEqual(lane[source], int(proc.env["ZZZOPS_TEST_WORKERS"]))
                if expected_mode:
                    self.assertEqual(budget, sum(timing["workers"].values()))

    def test_one_empty_lane_falls_back_to_serial_with_the_full_effective_budget(self):
        result = self.execute(self.context(goals=(), verification=("repository-one",), mode=True), parent=4).output["result"]
        timing = self.timing(result)
        self.assertFalse(timing["parallel_commands"])
        self.assertEqual(4, timing["cpu_budget"])
        self.assertEqual(4, int(self.processes[0].env["ZZZOPS_TEST_WORKERS"]))
        self.assertEqual(1, len(self.processes))

    def test_malformed_inherited_budget_is_rejected_before_commands(self):
        for value in ("0", "-2", "bad", "1.5"):
            with self.subTest(value=value), self.assertRaises(Exception):
                self.execute(self.context(mode=True), parent=value)
            self.assertEqual([], self.processes)

    def test_parallel_lanes_overlap_but_keep_internal_and_result_order(self):
        self.require_timing()
        self.barrier_commands = {"g1", "v1"}
        self.exits = {"g1": 3, "v1": 9}
        result = self.execute(self.context(goals=("g1", "g2"), verification=("v1", "v2"), mode=True))
        details = result.output["result"]["details"]
        self.assertEqual(["g1", "g2", "v1", "v2"], [d["cmd"] for d in details])
        self.assertEqual([3, 0, 9, 0], [d["exit"] for d in details])
        self.assertEqual(4, len(self.processes))
        self.assertFalse(result.ok)
        self.assertIn("g1", result.findings[0]["text"])
        for first, second in (("g1", "g2"), ("v1", "v2")):
            self.assertLess(self.events.index(("joined", first)), self.events.index(("start", second)))
        self.assertIn(("start", "v1"), self.events[:self.events.index(("joined", "g1"))])
        self.assertIn(("start", "g1"), self.events[:self.events.index(("joined", "v1"))])

    def test_parallel_lane_sums_are_separate_from_elapsed_wall_time(self):
        self.require_timing()
        self.barrier_commands = {"goal-one", "repository-one"}
        result = self.execute(self.context(mode=True)).output["result"]
        timing = self.timing(result)
        self.assertEqual(1250, timing["total_ms"])
        self.assertEqual(1250, timing["goal_ms"])
        self.assertEqual(1250, timing["verification_ms"])
        self.assertGreater(timing["goal_ms"] + timing["verification_ms"], timing["total_ms"])

    def test_timeout_kills_and_joins_both_lanes_before_single_cleanup(self):
        self.require_timing()
        self.barrier_commands = {"g1", "v1"}
        self.timeouts = {"g1", "v1"}
        out = self.execute(self.context(goals=("g1", "g2"), verification=("v1", "v2"), mode=True))
        self.assertFalse(out.ok)
        self.assertEqual({"g1", "v1"}, {p.command for p in self.processes})
        self.assertTrue(all(p.killed for p in self.processes))
        for command in ("g1", "v1"):
            self.assertLess(self.events.index(("joined", command)), self.events.index(("git", "reset")))
        self.assertEqual(1, self.events.count(("git", "reset")))
        self.assertEqual(1, self.events.count(("git", "clean")))
        self.assertIn("timing", out.output["result"])
        self.assertTrue(any(d["exit"] != 0 for d in out.output["result"]["details"]))

    def test_launch_failure_is_reported_without_losing_a_siblings_result(self):
        try:
            out = self.execute(self.context(goals=("launch-error",), verification=("verification",), mode=True))
        except OSError as error:
            self.fail(f"launch failures must be recorded with sibling evidence: {error}")
        self.assertFalse(out.ok)
        details = out.output["result"]["details"]
        self.assertEqual(["launch-error", "verification"], [d["cmd"] for d in details])
        self.assertNotEqual(0, details[0]["exit"])
        self.assertEqual(0, details[1]["exit"])
        self.assertIn("launch refused", details[0]["tail"])
        self.assertEqual(1, self.events.count(("git", "clean")))

    def test_plan_hash_changes_with_commands_mode_and_effective_allocation(self):
        values = []
        for ctx, parent in ((self.context(), None), (self.context(goals=("different",)), None),
                            (self.context(mode=True), None), (self.context(mode=True), 4)):
            timing = self.timing(self.execute(ctx, parent=parent).output["result"])
            values.append(timing["plan_sha256"])
        self.assertEqual(4, len(set(values)))

    def test_repository_hash_excludes_goal_text_but_tracks_repository_order_mode_and_allocation(self):
        first = self.timing(self.execute(self.context(goals=("g1",), verification=("v1", "v2"), mode=True), parent=4).output["result"])
        different_goal = self.timing(self.execute(self.context(goals=("different-goal",), verification=("v1", "v2"), mode=True), parent=4).output["result"])
        self.assertNotEqual(first["plan_sha256"], different_goal["plan_sha256"])
        self.assertEqual(first["verification_plan_sha256"], different_goal["verification_plan_sha256"])
        for ctx, parent in ((self.context(goals=("g1",), verification=("v2", "v1"), mode=True), 4),
                            (self.context(goals=("g1",), verification=("different-repository",), mode=True), 4),
                            (self.context(goals=("g1",), verification=("v1", "v2"), mode=False), 4),
                            (self.context(goals=("g1",), verification=("v1", "v2"), mode=True), 6)):
            compared = self.timing(self.execute(ctx, parent=parent).output["result"])
            self.assertNotEqual(first["verification_plan_sha256"], compared["verification_plan_sha256"])

    def test_logs_are_trimmed_without_removing_command_cost_or_outcomes(self):
        commands = tuple(f"goal-{i}" for i in range(10))
        self.output = {cmd: "long log " * 2000 for cmd in commands}
        result = self.execute(self.context(goals=commands, verification=())).output["result"]
        self.assertEqual(list(commands), [d["cmd"] for d in result["details"]])
        self.assertTrue(all(d["exit"] == 0 and isinstance(d.get("milliseconds"), int) for d in result["details"]))
        self.assertTrue(all(len(d["tail"]) < checks.TAIL for d in result["details"]))
        self.timing(result)
        doc = schema_fixtures.default_goal()
        doc["records"]["run_tests"] = schema_fixtures.record(output={"result": result})
        errors, _ = schemas.validate_goal(doc)
        self.assertEqual([], errors, "durable durations must never contain floats")

    def test_tree_mismatch_runs_nothing_and_marks_timing_unavailable(self):
        ctx = self.context()
        ctx.inputs["code"] = "different-tree"
        out = self.execute(ctx)
        self.assertFalse(out.ok)
        self.assertEqual([], self.processes)
        timing = out.output["result"].get("timing")
        self.assertIsInstance(timing, dict)
        self.assertEqual("tree_mismatch", timing["reason"])
        self.assertEqual("unavailable", timing["status"])
        self.assertNotIn("total_ms", timing)


if __name__ == "__main__":
    unittest.main()
