"""One fenced submit against real GitHub over HTTPS (DESIGN §10 item 23). A manual check, outside test discovery:

    ZZZOPS_GH_SMOKE_REPO=<owner>/<scratch repo> python3 .agents/engine_gh_smoke.py

It needs ZZZOPS_GH_SMOKE_REPO=<owner>/<repo> to name a scratch repository the human chose, whose integration
branch already carries a ZzzOps policy (the bootstrap checklist). It writes goal and lease branches there and never
deletes anything; it prints the cleanup commands instead."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import engine_fixtures as fx

REPO = os.environ.get("ZZZOPS_GH_SMOKE_REPO")


@unittest.skipUnless(REPO, "set ZZZOPS_GH_SMOKE_REPO=<owner>/<scratch repo> to run against real GitHub")
class RealGitHubSmokeTest(unittest.TestCase):
    def test_fenced_submit(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        url = f"https://github.com/{REPO}.git"
        clones = {}
        for name in ("a", "b"):
            path = os.path.join(tmp, name)
            subprocess.run(["git", "clone", "-q", url, path], check=True)
            clones[name] = path
        env = dict(os.environ, PYTHONPATH=str(fx.PLUGIN_CODE), ZZZOPS_PREFIX="zzzops")

        def run(clone, *argv):
            p = subprocess.run([sys.executable, str(fx.PLUGIN_CODE / "zzzops.py"), *argv], cwd=clones[clone], capture_output=True, text=True,
                               env=env)
            return p.returncode, json.loads(p.stdout) if p.stdout.strip().startswith("{") else {"_": p.stderr}

        spec = os.path.join(tmp, "goal.json")
        with open(spec, "w") as fh:
            json.dump({"title": "ZzzOps smoke test", "spec": "A throwaway goal for the fenced-submit smoke test."}, fh)
        rc, out = run("a", "new", "--file", spec)
        self.assertEqual(0, rc, out)
        g = out["created"]["id"]
        rc, card = run("a", "start", str(g), out["next"]["actions"][0]["node"], "--as", "claude:smoke/a")
        self.assertEqual(0, rc, card)
        node = card["node"]
        rc, card_b = run("b", "start", str(g), node, "--as", "claude:smoke/b", "--reclaim", "--force")
        self.assertEqual(0, rc, card_b)
        output = os.path.join(tmp, "out.json")
        with open(output, "w") as fh:
            json.dump({"summary": "smoke"}, fh)
        art = os.path.join(tmp, "doc.md")
        with open(art, "w") as fh:
            fh.write("# smoke\n")
        rc, late = run("a", "submit", str(g), node, "--attempt", str(card["lease"]["attempt"]), "--as", "claude:smoke/a",
                       "--output", output, "--artifact", art)
        self.assertEqual((3, "superseded"), (rc, late["error"]["code"]))
        rc, ok = run("b", "submit", str(g), node, "--attempt", str(card_b["lease"]["attempt"]), "--as", "claude:smoke/b",
                     "--output", output, "--artifact", art)
        self.assertEqual(0, rc, ok)
        print(f"\ncleanup (run by hand if wanted): git push {url} :refs/heads/zzzops/goal/g{g} "
              f":refs/heads/zzzops/work/g{g}")


if __name__ == "__main__":
    unittest.main()
