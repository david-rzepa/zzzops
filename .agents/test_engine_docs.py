"""Step 10: the worked examples in REPAIR.md run (DESIGN §10 item 24), and the launcher works."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import engine_fixtures as fx

REFS = fx.PLUGIN_CODE / "references"
if not (REFS / "REPAIR.md").exists():
    REFS = fx.PLUGIN_CODE / "references-v2"


def recipe(title: str) -> str:
    text = (REFS / "REPAIR.md").read_text(encoding="utf-8")
    section = text.split("## " + title, 1)[1].split("\n## ", 1)[0]
    m = re.search(r"<!-- run -->\n```sh\n(.*?)```", section, re.S)
    return m.group(1)


class RepairRecipeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.w.bootstrap()

    def sh(self, clone, script, **subs):
        for k, v in subs.items():
            script = script.replace(f"<{k}>", str(v))
        subprocess.run(["sh", "-ec", script], cwd=self.w.clones[clone].path, env=self.w.env, check=True,
                       capture_output=True)

    def test_delete_an_orphan_lease(self):
        g = self.w.new(title="x")["created"]["id"]
        s = self.w.seed
        bad = s.git("commit-tree", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", "-m", "garbage")
        s.git("push", "-q", "origin", f"{bad}:refs/heads/zzzops/lease/g{g}/design")
        self.assertIn("orphan_lease", [x["kind"] for x in self.w.ok("a", "next")["warnings"]])
        self.sh("a", recipe("Delete an orphan or unparsable lease"), R="origin", id=g, node="design")
        self.assertNotIn("orphan_lease", [x["kind"] for x in self.w.ok("a", "next")["warnings"]])

    def test_forward_commit_for_a_force_pushed_goal(self):
        g = self.w.new(title="x")["created"]["id"]
        self.w.ok("b", "next")
        self.w.seed.git("fetch", "-q", "origin", f"refs/heads/zzzops/goal/g{g}")
        doc = json.loads(self.w.seed.git("show", "FETCH_HEAD:goal.json"))
        from test_engine_store import push_goal_doc
        push_goal_doc(self.w, dict(doc, title="evil"), force=True)
        self.assertIn("goal_rewritten", [x["kind"] for x in self.w.ok("b", "next")["warnings"]])
        self.sh("b", recipe("A force-pushed goal branch (`goal_rewritten`)"), R="origin", id=g)
        out = self.w.ok("b", "next")
        self.assertNotIn("goal_rewritten", [x["kind"] for x in out["warnings"]])
        self.assertEqual("x", self.w.ok("b", "show", str(g), "--json")["goal"]["title"])
        self.w.ok("b", "start", str(g), "design", "--as", "claude:aaaa/w-1")


class LauncherTests(unittest.TestCase):
    def test_launcher_runs_under_sh(self):
        launcher = fx.PLUGIN_CODE.parent / "bin" / "zzzops"
        p = subprocess.run(["sh", str(launcher), "--help"], capture_output=True, text=True)
        self.assertEqual(0, p.returncode, p.stderr)
        self.assertTrue(p.stdout.strip())


if __name__ == "__main__":
    unittest.main()
