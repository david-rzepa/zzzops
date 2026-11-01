"""Step 4: the goal store, policy and the read-only verbs plus `new` (SPEC §4.2–§4.5, §4.17; DESIGN §10 items 2,
10, 17, 20, 21, 24)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

import engine_fixtures as fx


def push_goal_doc(w: fx.World, doc: dict, parent=None, force=False):
    """Write a goal document straight to the remote, as another engine (or a human) would."""
    s = w.seed
    data = (json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    blob = s.git("hash-object", "-w", "--stdin", input=data)
    tree = s.git("mktree", input=f"100644 blob {blob}\tgoal.json\n")
    args = ["commit-tree", tree, "-m", f"zzzops: edit G{doc['id']}\n\nOutcome: edited\nState: {doc['state']}\nEngine: 9.9.9"]
    if parent:
        args += ["-p", parent]
    c = s.git(*args)
    s.git("push", "-q", *(["--force"] if force else []), "origin", f"{c}:refs/heads/zzzops/goal/g{doc['id']}")
    return c


class StoreBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.w.bootstrap()


class NewAndNextTests(StoreBase):
    def test_new_returns_discovery_action_and_creates_no_work_branch(self):
        out = self.w.new(title="Add cut")
        self.assertEqual(1000, out["created"]["id"])
        self.assertEqual([(1000, "design")], [(a["goal"], a["node"]) for a in out["next"]["actions"]])
        self.assertEqual("worker" if False else False, out["next"]["actions"][0]["root"])
        refs = self.w.remote_git("for-each-ref", "--format=%(refname)")
        self.assertIn("refs/heads/zzzops/goal/g1000", refs)
        self.assertNotIn("zzzops/work", refs)
        self.assertFalse(os.path.exists(os.path.join(self.w.clones["a"].path, ".zzzops", "worktrees")))

    def test_next_is_one_fetch_and_no_gh(self):
        self.w.new(title="one")
        self.w.reset_trace()
        self.w.ok("b", "next")
        lines = self.w.trace_lines()
        self.assertEqual(1, len(lines))
        self.assertEqual(["git", "fetch"], lines[0]["cmd"][:2])
        for i in range(10):
            self.w.new(title=f"g{i}")
        self.w.reset_trace()
        self.w.ok("b", "next")
        self.assertEqual(1, len(self.w.trace_lines()))

    def test_next_is_deterministic(self):
        self.w.new(title="a")
        self.w.new(title="b")
        a = self.w.ok("a", "next")
        b = self.w.ok("a", "next")
        self.assertEqual(a, b)

    def test_coordinator_commit_equals_fetched_dev_from_a_linked_worktree(self):
        a = self.w.clones["a"]
        linked = os.path.join(self.tmp, "linked")
        a.git("worktree", "add", "-q", "--detach", linked, "HEAD")
        dev = self.w.push_dev({"x.txt": "1\n"})
        out = self.w.ok("a", "next", cwd=linked)
        self.assertEqual(dev, out["coordinator"]["commit"])
        mirror = os.path.join(a.path, ".git", "zzzops", "coordinator")
        self.assertTrue(os.path.isdir(mirror))
        self.assertEqual(dev, a.git("-C", mirror, "rev-parse", "HEAD"))

    def test_concurrent_new_gets_distinct_ids(self):
        results = []

        def make(clone, i):
            results.append(self.w.run(clone, "new", "--file", self.w.file({"title": f"t{clone}{i}", "spec": "s"})))

        threads = [threading.Thread(target=make, args=(c, i)) for i in range(5) for c in ("a", "b")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertTrue(all(rc == 0 for rc, _ in results), [o for rc, o in results if rc])
        ids = sorted(o["created"]["id"] for _, o in results)
        self.assertEqual(list(range(1000, 1010)), ids)

    def test_ids_are_never_reused_after_a_goal_ref_disappears(self):
        self.w.new(title="x")
        self.w.new(title="y")
        self.w.ok("b", "next")                                # b has seen both
        self.w.remote_git("update-ref", "-d", "refs/heads/zzzops/goal/g1001")
        out = self.w.new("b", title="z")
        self.assertEqual(1002, out["created"]["id"])
        rc, nxt = self.w.run("b", "next")
        self.assertIn("goal_deleted", [x["kind"] for x in nxt["warnings"]])

    def test_concurrent_fetch_during_writes_loses_nothing(self):
        stop = threading.Event()

        def fetch_loop():
            while not stop.is_set():
                subprocess.run(["git", "-C", self.w.clones["a"].path, "fetch", "-q", "origin",
                                "+refs/heads/*:refs/remotes/origin/*"], env=self.w.env, capture_output=True)

        t = threading.Thread(target=fetch_loop)
        t.start()
        try:
            for i in range(4):
                self.w.new("a", title=f"w{i}")
        finally:
            stop.set()
            t.join()
        refs = self.w.remote_git("for-each-ref", "--format=%(refname)", "refs/heads/zzzops/goal/")
        self.assertEqual(4, len(refs.split()))


class PolicyTests(StoreBase):
    def policy_branch(self, files, topic="ci-lint"):
        s = self.w.seed
        s.git("pull", "-q", "--ff-only", "origin", "dev")
        s.git("checkout", "-q", "-b", f"zzzops/policy/{topic}")
        c = s.commit(files, "chore(zzzops): policy change")
        s.git("push", "-q", "origin", f"HEAD:refs/heads/zzzops/policy/{topic}")
        s.git("checkout", "-q", "dev")
        return c

    def test_policy_branch_blocks_and_unblocks(self):
        self.w.new(title="x")
        self.policy_branch({".zzzops/prompts/design.md": "new prompt\n"})
        out = self.w.ok("b", "next")
        self.assertEqual([], out["actions"])
        self.assertEqual("policy_branch", out["blockers"][0]["kind"])
        self.assertIn("zzzops/policy/ci-lint", out["blockers"][0]["message"])
        self.assertIn("1 actions paused", out["blockers"][0]["message"])
        self.assertEqual("zzzops/policy/ci-lint", out["coordinator"]["policy_branches"][0]["name"])
        # new is still allowed while a policy branch exists
        self.w.new("b", title="during")
        # deleting it unblocks
        self.w.remote_git("update-ref", "-d", "refs/heads/zzzops/policy/ci-lint")
        out = self.w.ok("b", "next")
        self.assertEqual([], out["blockers"])
        self.assertTrue(out["actions"])

    def test_landing_by_ancestry_or_squash_unblocks(self):
        self.w.new(title="x")
        tip = self.policy_branch({".zzzops/prompts/design.md": "landed\n"})
        s = self.w.seed
        s.git("merge", "-q", "--ff-only", tip)
        s.git("push", "-q", "origin", "HEAD:dev")
        out = self.w.ok("b", "next")
        self.assertEqual([], out["blockers"])
        self.assertIn("policy_branch_landed", [x["kind"] for x in out["warnings"]])
        # squash landing: same .zzzops/ content, different commit
        self.policy_branch({".zzzops/prompts/review_impl.md": "squashed\n"}, topic="sq")
        self.w.push_dev({".zzzops/prompts/review_impl.md": "squashed\n"}, "chore(zzzops): squash")
        out = self.w.ok("b", "next")
        self.assertEqual([], out["blockers"])

    def test_invalid_policy_blocks_writes_and_reads_still_work(self):
        self.w.new(title="x")
        self.w.push_dev({".zzzops/POLICY.json": "{\"schema_version\": 2}"})
        out = self.w.ok("b", "next")
        self.assertEqual("policy_invalid", out["blockers"][0]["kind"])
        rc, err = self.w.run("b", "new", "--file", self.w.file({"title": "t", "spec": "s"}))
        self.assertEqual(4, rc)
        self.assertEqual("policy_invalid", err["error"]["code"])

    def test_wrong_integration_branch(self):
        self.w.new(title="x")
        self.w.seed.git("push", "-q", "origin", "dev:main")
        rc, out = self.w.run("b", "next", "--integration", "main")
        self.assertEqual(0, rc)
        self.assertEqual("wrong_integration_branch", out["blockers"][0]["kind"])
        rc, err = self.w.run("b", "new", "--integration", "main", "--file", self.w.file({"title": "t", "spec": "s"}))
        self.assertEqual("wrong_integration_branch", err["error"]["code"])

    def test_not_bootstrapped(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        w = fx.World(tmp)
        out = w.ok("a", "next")
        self.assertEqual("not_bootstrapped", out["blockers"][0]["kind"])
        rc, err = w.run("a", "new", "--file", w.file({"title": "t", "spec": "s"}))
        self.assertEqual((4, "not_bootstrapped"), (rc, err["error"]["code"]))

    def test_validate_policy_dir_needs_no_repository(self):
        nowhere = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, nowhere, True)
        rc, out = self.w.run("a", "validate", "--policy", "--dir", str(fx.TEMPLATES), cwd=nowhere)
        self.assertEqual(0, rc, out)
        bad = os.path.join(nowhere, "bad")
        shutil.copytree(fx.TEMPLATES, bad)
        os.remove(os.path.join(bad, "prompts", "design.md"))
        rc, out = self.w.run("a", "validate", "--policy", "--dir", bad, cwd=nowhere)
        self.assertEqual(1, rc)
        self.assertTrue(any("design.md" in e for e in out["policy"]), out)

    def test_twenty_concurrent_next_after_dev_moves(self):
        self.w.new(title="x")
        self.w.push_dev({"y.txt": "1\n"})
        results = []
        threads = [threading.Thread(target=lambda: results.append(self.w.run("a", "next"))) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual([0] * 20, [rc for rc, _ in results], [o for rc, o in results if rc][:1])
        commits = {o["coordinator"]["commit"] for _, o in results}
        self.assertEqual(1, len(commits))


class EngineVersionTests(StoreBase):
    def test_engine_min_above_version_refuses_writes_reads_work(self):
        self.w.new(title="x")
        p = json.loads(json.dumps(self.w.policy))
        p["settings"]["engine"]["min"] = "99.0.0"
        self.w.push_dev({".zzzops/POLICY.json": json.dumps(p)})
        out = self.w.ok("b", "next")
        self.assertEqual("engine_too_old", out["blockers"][0]["kind"])
        rc, err = self.w.run("b", "new", "--file", self.w.file({"title": "t", "spec": "s"}))
        self.assertEqual((1, "engine_too_old"), (rc, err["error"]["code"]))
        self.w.ok("b", "show", "1000")

    def test_newer_goal_schema_makes_dependents_wait(self):
        self.w.new(title="dep")
        self.w.new(title="child", depends_on=[1000])
        doc = {"schema": 7, "id": 1000, "title": "dep", "state": "open"}
        tip = self.w.remote_git("rev-parse", "refs/heads/zzzops/goal/g1000")
        self.w.seed.git("fetch", "-q", "origin", "refs/heads/zzzops/goal/g1000")
        push_goal_doc(self.w, doc, parent=tip)
        out = self.w.ok("b", "next")
        waits = {(x["goal"], x["until"]) for x in out["waiting"]}
        self.assertIn((1001, "engine upgrade"), waits)
        self.assertNotIn(1001, [i["goal"] for i in out["needs_human"] if i["kind"] == "stuck"])


class GoalIntegrityTests(StoreBase):
    def test_force_pushed_goal_is_detected_per_goal(self):
        self.w.new(title="x")
        self.w.new(title="y")
        self.w.ok("b", "next")
        self.w.seed.git("fetch", "-q", "origin", "refs/heads/zzzops/goal/g1000")
        doc = json.loads(self.w.seed.git("show", "FETCH_HEAD:goal.json"))
        doc["title"] = "rewritten"
        push_goal_doc(self.w, doc, force=True)                       # parentless: not a descendant
        out = self.w.ok("b", "next")
        kinds = [x["kind"] for x in out["warnings"]]
        self.assertIn("goal_rewritten", kinds)
        # reads use the accepted tip; other goals are unaffected
        show = self.w.ok("b", "show", "1000", "--json")
        self.assertEqual("x", show["goal"]["title"])
        self.assertIn("rewritten", show)
        self.assertEqual({1000, 1001}, {a["goal"] for a in out["actions"]})


if __name__ == "__main__":
    unittest.main()
