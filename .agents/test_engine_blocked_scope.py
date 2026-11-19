"""Real Git/CLI regressions for G1049's preserved test scope.

The repository and agent worktrees are local Git repositories.  These tests use
normal CLI leases, blocked submissions, retry and independent test review.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest

import engine_fixtures as fx
from engine import identity, verbs
from engine.errors import Refused
from test_engine_conventional import checkpoint_workflow


class BlockedScopeJourney(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.w.bootstrap(workflow=checkpoint_workflow())
        self.a = fx.Agent(self.w, "a", "codex:aaaa/tester")
        self.b = fx.Agent(self.w, "b", "codex:bbbb/reviewer")
        self.g = self.w.new(title="Preserved blocked tests")["created"]["id"]
        self.w.ok("a", "start", str(self.g), "base", "--as", "codex:aaaa/op")
        self.wt = self.a.worktree(self.g)

    def record(self, node="test_design"):
        return self.w.ok("a", "show", str(self.g), "--json")["goal"]["records"][node]

    def review(self):
        card = self.b.start(self.g, "review_tests")
        old = [{"id": f["id"], "status": "resolved"} for f in
               (card.get("previous") or {}).get("findings", []) if f["status"] == "open"]
        self.b.submit(self.g, "review_tests", card,
                      {"decision": "approved", "summary": "Reviewed", "findings": old},
                      artifact="Independent review.\n")
        return card

    def accept_tests(self):
        card = self.a.start(self.g, "test_design")
        self.wt.commit({"tests/one.py": "assert 1\n", "tests/two.py": "assert 2\n"}, "test: initial")
        self.a.submit(self.g, "test_design", card, {"commands": ["true"]})
        self.review()
        return self.record()

    def reopen_and_block(self):
        self.w.ok("a", "reopen", str(self.g), "test_design", "--note", "reconsider tests")
        card = self.a.start(self.g, "test_design")
        self.a.submit(self.g, "test_design", card,
                      blocked={"waiting_for": "agent", "instructions": "Retry after investigation."})
        return card

    def test_repeated_blocks_retain_accepted_scope_without_blocked_findings(self):
        original = self.accept_tests()
        self.assertEqual(["tests/one.py", "tests/two.py"], original["frozen"])
        self.reopen_and_block()
        first = self.record()
        self.assertEqual("blocked", first["status"])
        self.assertEqual(original["frozen"], first.get("frozen"))
        self.assertIsNone(first["output"])
        again = self.a.start(self.g, "test_design")
        self.a.submit(self.g, "test_design", again,
                      blocked={"waiting_for": "agent", "instructions": "Retry after investigation."})
        self.assertEqual(original["frozen"], self.record().get("frozen"))
        retry = self.a.start(self.g, "test_design")
        responses = {f["id"]: "disputed: tests unchanged" for f in retry.get("corrections", [])}
        self.a.submit(self.g, "test_design", retry, {"commands": ["true"], "responses": responses})
        final = self.record()
        self.assertEqual(original["frozen"], final["frozen"])
        self.review()
        c = self.a.start(self.g, "implement")
        self.wt.commit({"tests/one.py": "assert False\n"}, "fix: weaken test")
        rc, out = self.a.submit(self.g, "implement", c, {"summary": "Attempt"}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertEqual("test_freeze", out["error"]["code"])

    def test_before_capability_pending_blocked_work_is_not_published(self):
        self.accept_tests()
        self.w.ok("a", "reopen", str(self.g), "test_design", "--note", "new test")
        card = self.a.start(self.g, "test_design")
        old_tip = self.w.remote_git("rev-parse", f"refs/heads/zzzops/work/g{self.g}")
        self.wt.commit({"tests/new.py": "assert 3\n"}, "test: new test before block")
        rc, out = self.a.submit(self.g, "test_design", card,
                                blocked={"waiting_for": "agent", "instructions": "Retry"}, ok=False)
        self.assertNotEqual(0, rc, out)
        text = str(out).lower()
        self.assertIn("capabilit", text)
        self.assertEqual(old_tip, self.w.remote_git("rev-parse", f"refs/heads/zzzops/work/g{self.g}"))


class ScopeProtectionTests(unittest.TestCase):
    def test_blocked_producer_refuses_consumer_even_with_empty_commit_range(self):
        # The old code silently returns for blocked producers, bypassing final-tree
        # checks if a previously published implementation commit is already HEAD.
        graph = type("Graph", (), {"nodes": {"implement": {"preserve": "test_design"}}})()
        result = type("Result", (), {"graph": graph})()
        session = type("Session", (), {})()
        doc = {"records": {"test_design": {"status": "blocked", "frozen": ["tests/one.py"]}}}
        with self.assertRaises(Refused) as caught:
            verbs.preserve_check(session, result, doc, "implement", {"commit": "f" * 40}, object())
        self.assertIn("test_design", str(caught.exception))

    def test_previous_blocked_scope_survives_noop_retry(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        repo = fx.make_repo(tmp)
        base = repo.commit({"tests/old.py": "assert 1\n"}, "test: first")
        head = repo.commit({"src/app.py": "value = 1\n"}, "feat: implementation")
        git = fx.engine_git(repo)
        session = type("Session", (), {"git": git})()
        lease = type("Lease", (), {"work": head})()
        old = {"status": "blocked", "frozen": ["tests/old.py"]}
        scope = verbs.frozen_paths(session, old, lease, {"base": base, "commit": head}, identity.Identity(git))
        self.assertEqual(["tests/old.py"], scope)


if __name__ == "__main__":
    unittest.main()
