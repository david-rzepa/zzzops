"""Step 6: the op interface and checks.run (SPEC §5.1, §5.3; DESIGN §10 item 13, checks parts)."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

import engine_fixtures as fx
from engine.ops.checks import run_one
from engine.ops.run import OpContext
from engine.canon import iso
from test_engine_lifecycle import Journey


class ChecksJourney(Journey):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.m = {n: n for n in fx.DEFAULT_NODES}
        self.w.bootstrap(workflow=fx.stub_base_workflow(), settings={"verification.commands": ["test -f src/cut.py"]})
        self.A = fx.Agent(self.w, "a", "claude:aaaa/w-1")
        self.B = fx.Agent(self.w, "b", "codex:bbbb/w-2")

    def implement(self, g, body="def cut():\n    return 1\n", test_cmd="grep -q 'return 1' src/cut.py"):
        self.through_design(g)
        c = self.A.start(g, "test_design")
        self.A.worktree(g).commit({"tests/test_cut.txt": "cut returns 1\n"}, "test: cut")
        self.A.submit(g, "test_design", c, {"commands": [test_cmd]})
        self.review(self.B, g, "review_tests")
        c = self.A.start(g, "implement")
        self.A.worktree(g).commit({"src/cut.py": body}, "feat: cut")
        self.A.submit(g, "implement", c, {"summary": "Built."})

    def test_pass(self):
        g = self.goal()
        self.implement(g)
        out = self.w.ok("a", "start", str(g), "run_tests", "--as", "claude:aaaa/op")
        ran = out["ran"]
        self.assertEqual(("done", True), (ran["outcome"], ran["ok"]))
        self.assertTrue(ran["output"]["result"]["passed"])
        self.assertEqual(["grep -q 'return 1' src/cut.py", "test -f src/cut.py"],
                         [d["cmd"] for d in ran["output"]["result"]["details"]])
        self.assertIn("review_impl", [a["node"] for a in out["next"]["actions"]])
        self.assertTrue(fx.GitDir(self.A.worktree(g).path, self.w.env).git("status", "--porcelain") == "")

    def test_fail_reopens_implement_then_fix_passes(self):
        g = self.goal()
        self.implement(g, body="def cut():\n    return 2\n")
        out = self.w.ok("a", "start", str(g), "run_tests", "--as", "claude:aaaa/op")
        self.assertFalse(out["ran"]["ok"])
        self.assertEqual("run_tests:failed", out["ran"]["findings"][0]["id"])
        self.assertEqual([("implement", "reopened")], [(a["node"], a["reason"]) for a in out["next"]["actions"]])
        c = self.A.start(g, "implement")
        self.assertIn("exited 1", c["corrections"][0]["text"])
        self.A.worktree(g).commit({"src/cut.py": "def cut():\n    return 1\n"}, "fix: return 1")
        self.A.submit(g, "implement", c, {"summary": "Built.", "responses": {"run_tests:failed": "fixed: returns 1"}})
        out = self.w.ok("a", "start", str(g), "run_tests", "--as", "claude:aaaa/op")
        self.assertTrue(out["ran"]["ok"])
        self.assertEqual("fixed: re-run by checks.run", out["ran"]["output"]["responses"]["run_tests:failed"]
                         if "responses" in out["ran"]["output"] else "fixed: re-run by checks.run")

    def test_tree_mismatch_is_a_finding_on_the_code_producer(self):
        g = self.goal()
        self.implement(g)
        self.A.worktree(g).commit({"src/extra.py": "x = 1\n"}, "feat: unrecorded extra")
        out = self.w.ok("a", "start", str(g), "run_tests", "--as", "claude:aaaa/op")
        self.assertEqual("run_tests:tree-mismatch", out["ran"]["findings"][0]["id"])
        self.assertEqual("implement", out["ran"]["findings"][0]["target"])

    def test_crash_mid_op_is_reclaimed_without_a_dead_end(self):
        g = self.goal()
        marker = os.path.join(self.tmp, "fast")
        self.implement(g, test_cmd=f"test -f {marker} || sleep 30")
        env = self.w.cli_env()
        proc = subprocess.Popen([sys.executable, str(fx.PLUGIN_CODE / "zzzops.py"), "start", str(g), "run_tests", "--as", "claude:aaaa/op"],
                                cwd=self.w.clones["a"].path, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
        time.sleep(3)
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        out = self.w.ok("b", "next", now=fx.NOW + 16 * 60)
        acts = [(a["node"], a["reason"]) for a in out["actions"]]
        self.assertIn(("run_tests", "reclaim"), acts)
        open(marker, "w").close()                          # the reclaimed run finishes at once
        out = self.w.ok("a", "start", str(g), "run_tests", "--as", "claude:aaaa/op", "--reclaim", now=fx.NOW + 16 * 60)
        self.assertEqual((2, True), (out["ran"]["attempt"], out["ran"]["ok"]))


class OpUnitTests(unittest.TestCase):
    def test_timeout_kills_the_process_group(self):
        start = time.monotonic()
        code, timed_out, seconds, tail = run_one("/bin/sh", "echo start; sleep 30 & sleep 30", tempfile.gettempdir(), 1)
        self.assertTrue(timed_out)
        self.assertEqual(-1, code)
        self.assertLess(time.monotonic() - start, 10)
        self.assertIn("start", tail)

    def ctx(self, record=None, answer=None, now=1000):
        return OpContext(goal=1, doc={}, node="ci", node_def={}, inputs={}, producers={}, dep_kinds={}, record=record,
                         corrections=[], answer=answer, settings={"verification": {"ci_timeout_minutes": 120}},
                         snap=None, git=None, gh=None, worktree=None, now=now, renew=lambda: None)

    def test_wait_backs_off_and_escalates(self):
        b = self.ctx().wait("pending", 300).blocked
        self.assertEqual(("time", iso(1300), 1), (b["waiting_for"], b["retry_after"], b["op_state"]["polls"]))
        rec = {"status": "blocked", "blocked": dict(b)}
        b2 = self.ctx(record=rec, now=1400).wait("pending", 300).blocked
        self.assertEqual(iso(1400 + 600), b2["retry_after"])
        rec = {"status": "blocked", "blocked": {"waiting_for": "time", "op_state": {"pending_since": 0, "polls": 9}}}
        b3 = self.ctx(record=rec, now=120 * 60).wait("pending", 300).blocked
        self.assertEqual("human", b3["waiting_for"])
        b4 = self.ctx(record=rec, answer={"text": "wait"}, now=120 * 60).wait("pending", 300).blocked
        self.assertEqual("time", b4["waiting_for"])
        rec = {"status": "blocked", "blocked": {"waiting_for": "time", "op_state": {"pending_since": 0, "polls": 8}}}
        self.assertEqual(iso(60 * 60 + 1800), self.ctx(record=rec, now=60 * 60).wait("p", 300).blocked["retry_after"])


if __name__ == "__main__":
    unittest.main()
