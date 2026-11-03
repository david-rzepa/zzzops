"""Seed actual integration snapshots without importing transient side-branch versions."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import engine_fixtures as fx


class IntegrationTemplateHistoryTests(unittest.TestCase):
    def test_merge_keeps_published_snapshots_and_existing_history_but_not_transient_goal_version(self):
        updater = fx.ROOT / ".agents/template_history.py"
        rel = "plugins/zzzops/zzzops/templates/default/prompts/design.md"
        history_rel = "plugins/zzzops/zzzops/templates/history"
        def name(content):
            data = content.encode()
            return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() + ".md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = fx.make_repo(tmp)
            old, first, transient, final = "historic\n", "integration V1\n", "unshipped V2\n", "merged V3\n"
            repo.commit({".agents/template_history.py": updater.read_text(), rel: first,
                         f"{history_rel}/{name(old)}": old}, "chore: integration template V1")
            repo.git("checkout", "-q", "-b", "goal/template")
            intermediate = repo.commit({rel: transient}, "chore: transient goal template V2")
            repo.commit({rel: final}, "chore: final goal template V3")
            repo.git("checkout", "-q", "dev")
            repo.git("merge", "--no-ff", "-m", "chore: merge template V3", "goal/template")
            repo.git("merge-base", "--is-ancestor", intermediate, "HEAD")
            result = subprocess.run([sys.executable, str(Path(repo.path) / ".agents/template_history.py"),
                                     "--write", "--seed-ref", "HEAD"],
                                    cwd=repo.path, env=repo.env, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            history = Path(repo.path) / history_rel
            self.assertEqual({name(old), name(first), name(final)}, {p.name for p in history.iterdir()})
            self.assertFalse((history / name(transient)).exists())
            for content in (old, first, final):
                self.assertEqual(content.encode(), (history / name(content)).read_bytes())


if __name__ == "__main__":
    unittest.main()
