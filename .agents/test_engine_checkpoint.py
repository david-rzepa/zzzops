"""Checkpoint scope after G1038: HEAD is the default, tests retain path-scoped identity.

The old suggested-checkpoint/replay-map selection API was removed. CLI lifecycle
checks cover default selection; these small checks cover the identity it preserves.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest

import engine_fixtures as fx
from engine.canon import ZERO
from engine.identity import Identity
from engine.records import checkpoint_scope
from engine.schemas import build_graph


class CheckpointScopeTests(unittest.TestCase):
    def graph(self, renamed=False):
        wf = fx.renamed_workflow() if renamed else fx.load_template("workflow.json")
        return build_graph("default", wf["graphs"]["default"])

    def test_preserved_node_scope_is_sorted_without_mutating_frozen_paths(self):
        record = {"frozen": ["tests/z.py", "tests/a.py"]}
        self.assertEqual(["tests/a.py", "tests/z.py"], checkpoint_scope(self.graph(), "test_design", record))
        self.assertEqual(["tests/z.py", "tests/a.py"], record["frozen"])

    def test_scope_follows_preserve_under_renamed_nodes(self):
        self.assertEqual(["tests/t.py"], checkpoint_scope(self.graph(True), fx.RENAME["test_design"],
                                                         {"frozen": ["tests/t.py"]}))

    def test_legacy_checkpoint_without_frozen_paths_remains_unscoped(self):
        self.assertIsNone(checkpoint_scope(self.graph(), "test_design", {"output": {"tests": {}}}))

    def test_empty_frozen_set_is_distinct_from_unscoped(self):
        self.assertEqual([], checkpoint_scope(self.graph(), "test_design", {"frozen": []}))

    def test_implementation_identity_remains_whole_goal(self):
        self.assertIsNone(checkpoint_scope(self.graph(), "implement", {"frozen": ["tests/t.py"]}))


class ScopedIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = fx.make_repo(self.tmp)
        self.base = self.repo.commit({"src/app.py": "app = 0\n"}, "chore: base")
        self.tests = self.repo.commit({"tests/t.py": "expected = 1\n"}, "test: expected behavior")
        self.impl = self.repo.commit({"src/app.py": "app = 1\n"}, "feat: behavior")
        self.git = fx.engine_git(self.repo)
        self.ident = Identity(self.git)

    def test_later_code_and_review_commits_keep_scoped_test_change(self):
        head = self.repo.commit({".zzzops/reviews/1/review_impl.md": "changes requested\n"},
                                "docs(review): review_impl for G1")
        before = self.ident.change(self.base, self.tests, paths=["tests/t.py"])
        self.assertEqual(before, self.ident.change(self.base, head, paths=["tests/t.py"]))
        self.assertNotEqual(self.ident.change(self.base, self.tests), self.ident.change(self.base, head))
        self.assertNotEqual(self.ident.code_tree(self.tests), self.ident.code_tree(head))

    def test_test_fix_after_code_changes_only_its_scoped_identity(self):
        fix = self.repo.commit({"tests/t.py": "expected = 2\n"}, "test: revise expected behavior")
        before = self.ident.change(self.base, self.impl, paths=["tests/t.py"])
        self.assertNotEqual(before, self.ident.change(self.base, fix, paths=["tests/t.py"]))
        self.assertEqual(self.ident.change(self.base, self.impl, paths=["src/app.py"]),
                         self.ident.change(self.base, fix, paths=["src/app.py"]))
        self.assertTrue(self.git.is_ancestor(self.impl, fix))

    def test_empty_scope_has_zero_change_even_at_implementation_head(self):
        self.assertEqual(ZERO, self.ident.change(self.base, self.impl, paths=[]))
        self.assertNotEqual(ZERO, self.ident.change(self.base, self.impl))


if __name__ == "__main__":
    unittest.main()
