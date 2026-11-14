"""G1024 regression probes: advisory priority and actual PowerShell commands."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import engine_fixtures as fx
from engine_sim import Sim
from engine import defaults, render
from engine.canon import canonical


class DefaultNoticeFollowups(unittest.TestCase):
    def test_advisory_paths_shrink_before_actions_and_human_items(self):
        sim = Sim()
        sim.goal(1)
        sim.goal(2)
        while sim.st(2, "approve_design")["name"] != "needs_human":
            sim.step(2, sim.actionable(2)[0])
        ctx = render.Ctx(prefix="zzzops", now=sim.now, settings=sim.settings,
                         coordinator={"commit": sim.dev, "current": True})
        baseline = render.render_next(ctx, sim.eval())
        self.assertTrue(baseline["actions"])
        self.assertTrue(baseline["needs_human"])
        notice = {"kind": "update", "message": "default changed", "template": "a" * 12,
                  "counts": {"files": 10, "edited_here": 0}, "expand": "zzzops validate",
                  "files": [".zzzops/prompts/" + "long-directory/" * 70 + f"{i}.md" for i in range(10)]}
        original = copy.deepcopy(notice)
        out = render.render_next(ctx, sim.eval(), policy_update=notice)
        self.assertEqual(baseline["actions"], out["actions"])
        self.assertEqual(baseline["needs_human"], out["needs_human"])
        self.assertNotIn("truncated", out)
        self.assertLessEqual(len(canonical(out)), render.NEXT_LIMIT)
        self.assertLess(len(out["policy_update"]["files"]), 10)
        self.assertEqual(original, notice, "rendering must not mutate the caller's notice")

    def test_powershell_literal_arguments_preserve_apostrophes(self):
        with patch.object(defaults, "POWERSHELL", True):
            command = defaults.shell("git", "diff", "--", "Dave's defaults/$literal.md")
            self.assertTrue(command.startswith("& 'git' "))
            self.assertIn("'Dave''s defaults/$literal.md'", command)

    def test_manual_diff_and_recheck_run_in_powershell(self):
        executable = shutil.which("pwsh") or shutil.which("powershell")
        if not executable:
            self.skipTest("PowerShell is unavailable; native Windows runners provide it")
        with tempfile.TemporaryDirectory(prefix="Dave's defaults $literal ") as tmp:
            root = Path(tmp)
            shipped, local = [root / p for p in ("current default.md", "here.md")]
            shipped.write_text("after\n")
            local.write_text("before\n")
            def run(command):
                return subprocess.run([executable, "-NoProfile", "-NonInteractive", "-Command", command],
                                      cwd=tmp, capture_output=True, text=True)
            with patch.object(defaults, "POWERSHELL", True):
                result = run(defaults.shell("git", "diff", "--no-index", "--", local, shipped))
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertIn("+after", result.stdout)
                self.assertEqual("before\n", local.read_text(), "manual comparison preserves the local choice")
                policy = root / "repository policy"
                shutil.copytree(fx.TEMPLATES, policy)
                # Without an override, Python/entrypoint paths are quoted too.
                with patch.dict(os.environ):
                    os.environ.pop("ZZZOPS_PREFIX", None)
                    result = run(defaults.cli_shell("unused", "validate", "--policy", "--dir", policy))
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertTrue(json.loads(result.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
