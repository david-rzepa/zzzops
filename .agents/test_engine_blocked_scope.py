"""Real Git/CLI regressions for G1049's preserved test scope.

The repository and agent worktrees are local Git repositories.  These tests use
normal CLI leases, blocked submissions, retry and independent test review.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
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

    def test_capability_enabled_two_blocked_attempts_then_noop_retry_protects_all_tests(self):
        self.accept_tests()
        policy = json.loads(json.dumps(self.w.policy))
        policy["settings"]["engine"]["requires"].append("preserved_test_provenance")
        self.w.push_dev({".zzzops/POLICY.json": json.dumps(policy, indent=2) + "\n"})
        self.w.ok("a", "reopen", str(self.g), "test_design", "--note", "more tests")
        first = self.a.start(self.g, "test_design")
        self.wt.commit({"tests/three.py": "assert 3\n"}, "test: before first block")
        self.a.submit(self.g, "test_design", first,
                      blocked={"waiting_for": "agent", "instructions": "first retry"})
        second = self.a.start(self.g, "test_design")
        self.wt.commit({"tests/four.py": "assert 4\n"}, "test: before second block")
        self.a.submit(self.g, "test_design", second,
                      blocked={"waiting_for": "agent", "instructions": "second retry"})
        last = self.a.start(self.g, "test_design")
        responses = {f["id"]: "fixed: added tests" for f in last.get("corrections", [])}
        self.a.submit(self.g, "test_design", last, {"commands": ["true"], "responses": responses})
        self.assertEqual(sorted(["tests/one.py", "tests/two.py", "tests/three.py", "tests/four.py"]),
                         self.record()["frozen"])
        self.review()
        c = self.a.start(self.g, "implement")
        for path in self.record()["frozen"]:
            self.wt.commit({path: "assert False\n"}, "fix: weaken accepted test")
            rc, out = self.a.submit(self.g, "implement", c, {"summary": "Attempt"}, ok=False)
            self.assertNotEqual(0, rc, out)
            self.assertEqual("test_freeze", out["error"]["code"])
            self.wt.git("reset", "--hard", "HEAD^")
        self.wt.commit({"src/good.py": "value = 1\n"}, "feat: permitted implementation")
        self.a.submit(self.g, "implement", c, {"summary": "Non-test implementation"})

    def enable_capability(self):
        policy = json.loads(json.dumps(self.w.policy))
        policy["settings"]["engine"]["requires"].append("preserved_test_provenance")
        self.w.push_dev({".zzzops/POLICY.json": json.dumps(policy, indent=2) + "\n"})

    def test_blocked_segment_survives_a_real_base_sync(self):
        self.accept_tests()
        self.enable_capability()
        self.w.ok("a", "reopen", str(self.g), "test_design", "--note", "new test")
        c = self.a.start(self.g, "test_design")
        self.wt.commit({"tests/before_sync.py": "assert 3\n"}, "test: before blocked sync")
        self.a.submit(self.g, "test_design", c,
                      blocked={"waiting_for": "agent", "instructions": "retry"})
        self.w.push_dev({"unrelated.txt": "upstream\n"})
        self.w.ok("a", "reopen", str(self.g), "base", "--note", "integration moved")
        synced = self.w.ok("a", "start", str(self.g), "base", "--as", "codex:aaaa/op")
        self.assertEqual("done", synced["ran"]["outcome"])
        self.assertIn("synced", synced["ran"]["output"])
        retry = self.a.start(self.g, "test_design")
        responses = {f["id"]: "fixed: retained blocked test" for f in retry.get("corrections", [])}
        self.a.submit(self.g, "test_design", retry, {"commands": ["true"], "responses": responses})
        self.assertIn("tests/before_sync.py", self.record()["frozen"])
        self.assertNotIn("unrelated.txt", self.record()["frozen"])
        self.review()

    def test_ambiguous_blocked_source_and_gitlink_are_not_silently_frozen(self):
        self.accept_tests()
        self.enable_capability()
        self.w.ok("a", "reopen", str(self.g), "test_design", "--note", "mixed pending work")
        c = self.a.start(self.g, "test_design")
        base = self.wt.git("rev-parse", "HEAD")
        self.wt.write({"tests/new.py": "assert 3\n", "src/unclear.py": "source = 1\n"})
        self.wt.git("add", "tests/new.py", "src/unclear.py")
        self.wt.git("update-index", "--add", "--cacheinfo", f"160000,{base},vendor/dependency")
        self.wt.git("commit", "-q", "-m", "test: mixed pending work")
        self.a.submit(self.g, "test_design", c,
                      blocked={"waiting_for": "agent", "instructions": "retry"})
        retry = self.a.start(self.g, "test_design")
        responses = {f["id"]: "fixed: test under review" for f in retry.get("corrections", [])}
        rc, out = self.a.submit(self.g, "test_design", retry,
                                {"commands": ["true"], "responses": responses}, ok=False)
        if rc == 0:
            scope = self.record()["frozen"]
            self.assertNotIn("src/unclear.py", scope)
            self.assertNotIn("vendor/dependency", scope)
            self.assertIn("tests/new.py", scope)
            review = self.review()
            self.assertIn("src/unclear.py", str(review), "review must see candidate exclusions")
        else:
            self.assertTrue(any(w in str(out).lower() for w in ("scope", "select", "candidate")), out)

    def test_older_writer_rejects_policy_requiring_capability(self):
        self.enable_capability()
        old = Path(self.tmp) / "old-plugin"
        shutil.copytree(fx.PLUGIN_CODE, old)
        (old / "engine" / "capabilities" / "preserved_test_provenance.txt").unlink(missing_ok=True)
        p = subprocess.run([sys.executable, str(old / "zzzops.py"), "next"],
                           cwd=self.w.clones["a"].path, env=self.w.cli_env(), capture_output=True, text=True)
        out = json.loads(p.stdout)
        self.assertTrue(any(item.get("kind") in ("policy_invalid", "engine_too_old")
                            for item in out.get("blockers", [])), out)

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
