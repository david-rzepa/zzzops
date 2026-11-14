"""Failed process-tree termination must never race shared-worktree cleanup."""
from __future__ import annotations

import subprocess
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import engine_fixtures
from engine.ops import checks
from engine.ops.run import Blocked
from engine import test_cost


class TerminationTests(unittest.TestCase):
    def test_windows_nonzero_tree_kill_tries_parent_fallback_in_both_supervisors(self):
        for module, kill in ((checks, checks.kill_group), (test_cost, test_cost._kill_lookup)):
            process = mock.Mock(pid=1234)
            with self.subTest(module=module.__name__), mock.patch.object(module.os, "name", "nt"), \
                    mock.patch.object(module.subprocess, "run", return_value=SimpleNamespace(returncode=1)) as taskkill:
                kill(process)
            process.kill.assert_called_once_with()
            self.assertLessEqual(taskkill.call_args.kwargs["timeout"], 0.5)

    def test_timeout_drain_has_a_bound_and_failed_tree_kill_stays_unconfirmed(self):
        process = mock.Mock(pid=1234, returncode=-1)
        process.communicate.side_effect = [subprocess.TimeoutExpired("cmd", 1), (b"", None)]
        with mock.patch.object(checks.subprocess, "Popen", return_value=process), \
                mock.patch.object(checks, "kill_group", return_value=False):
            runner = checks._Commands("shell", "unused", time.monotonic() + 1)
            detail, timeout = runner.command("cmd", {})
        self.assertTrue(timeout)
        self.assertEqual(-1, detail["exit"])
        self.assertEqual({1234}, runner.unconfirmed)
        self.assertLessEqual(process.communicate.call_args_list[1].kwargs["timeout"], 1)

    def test_stubborn_pipe_blocks_and_preserves_worktree_instead_of_resetting_under_child(self):
        process = mock.Mock(pid=1234)
        process.communicate.side_effect = subprocess.TimeoutExpired("cmd", 1)
        git = SimpleNamespace(out=lambda *a, **k: "head", run=mock.Mock())
        ctx = SimpleNamespace(worktree="unused", git=git, inputs={"code": "tree", "commands": ["cmd"]},
                              settings={"verification": {"commands": [], "timeout_minutes": 1}})
        with mock.patch.object(checks, "Identity", return_value=SimpleNamespace(code_tree=lambda c: "tree")), \
                mock.patch.object(checks, "shell", return_value="shell"), \
                mock.patch.object(checks.subprocess, "Popen", return_value=process), \
                mock.patch.object(checks, "kill_group", return_value=True):
            result = checks.run(ctx)
        self.assertIsInstance(result, Blocked)
        self.assertEqual("human", result.blocked["waiting_for"])
        self.assertEqual([1234], result.blocked["op_state"]["unconfirmed_pids"])
        git.run.assert_not_called()
        self.assertEqual(2, process.communicate.call_count)
        self.assertTrue(all(call.kwargs.get("timeout") is not None for call in process.communicate.call_args_list))


if __name__ == "__main__":
    unittest.main()
