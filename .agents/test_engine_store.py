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


class EngineFloorTests(StoreBase):
    def test_missing_capability_refuses_writes_reads_work(self):
        self.w.new(title="x")
        p = json.loads(json.dumps(self.w.policy))
        p["settings"]["engine"] = {"requires": ["no_such_cap"]}
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



# --------------------------------------------------------------------------------------------- G1001: idempotent `new`

def default_key(title, spec, depends_on=()):
    """The default request key (G1001 design §1): sha256 over the canonical title, spec and sorted, unique depends_on."""
    from engine import canon
    return "sha256:" + canon.H({"v": 1, "title": title, "spec": spec, "depends_on": sorted(set(depends_on))})


def push_root(w: fx.World, gid: int, key=None, head_id=None, **fields):
    """Push a parentless goal commit for G<gid>, as `new` writes it, optionally with a Request-Key trailer."""
    from engine import build_id
    doc = {"schema": 1, "id": gid, "title": "Forged", "graph": "default", "state": "open", "closed": None,
           "spec": "forged spec", "priority": "P2", "release": 1, "depends_on": [], "skip": {},
           "links": {"issue": None}, "budget": None, "records": {}}
    doc.update(fields)
    s = w.seed
    data = json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    blob = s.git("hash-object", "-w", "--stdin", input=data)
    tree = s.git("mktree", input=f"100644 blob {blob}\tgoal.json\n")
    trailer = f"Request-Key: {key}\n" if key else ""
    msg = f"zzzops: new G{head_id or gid}\n\nOutcome: created\nState: open\n{trailer}Engine: {build_id()}\n"
    c = s.git("commit-tree", tree, "-m", msg)
    s.git("push", "-q", "origin", f"{c}:refs/heads/zzzops/goal/g{gid}")
    return c


class InProcess:
    """Run the CLI in this process with a World clone's environment (so engine functions can be patched)."""

    def __init__(self, w: fx.World, clone: str):
        self.w, self.clone = w, clone

    def run(self, *argv):
        import contextlib
        import io
        from engine import cli
        buf = io.StringIO()
        cwd = os.getcwd()
        try:
            with fx.env_of(self.w.cli_env()), contextlib.redirect_stdout(buf):
                os.chdir(self.w.clones[self.clone].path)
                rc = cli.main(list(argv))
        finally:
            os.chdir(cwd)
        return rc, json.loads(buf.getvalue())


class IdempotentNewTests(StoreBase):
    """G1001: `zzzops new` returns the goal that already exists for the same request."""

    def goal_refs(self):
        return self.w.remote_git("for-each-ref", "--format=%(refname)", "refs/heads/zzzops/goal/").split()

    def root_of(self, gid):
        return self.w.remote_git("rev-list", "--max-parents=0", f"refs/heads/zzzops/goal/g{gid}")

    def tip(self, gid):
        return self.w.remote_git("rev-parse", f"refs/heads/zzzops/goal/g{gid}")

    def pushes(self):
        return [l for l in self.w.trace_lines() if l["cmd"][:2] == ["git", "push"]]

    # 1. exact retry

    def test_exact_retry_recovers_the_same_goal_without_a_push(self):
        f = self.w.file({"title": "Retry me", "spec": "same request"})
        first = self.w.ok("a", "new", "--file", f)
        self.assertIs(False, first["created"]["recovered"])
        key = default_key("Retry me", "same request")
        self.assertEqual(key, first["created"]["request_key"])
        self.w.reset_trace()
        again = self.w.ok("a", "new", "--file", f)
        self.assertEqual(first["created"]["id"], again["created"]["id"])
        self.assertIs(True, again["created"]["recovered"])
        self.assertEqual(key, again["created"]["request_key"])
        self.assertEqual(first["created"]["goal_commit"], again["created"]["goal_commit"])
        for k in ("display", "title", "graph", "release", "priority", "depends_on"):
            self.assertEqual(first["created"][k], again["created"][k], k)
        self.assertEqual([], self.pushes())
        self.assertEqual(["refs/heads/zzzops/goal/g1000"], self.goal_refs())
        self.assertEqual([(1000, "design")], [(a["goal"], a["node"]) for a in again["next"]["actions"]])

    def test_retry_from_another_clone_with_a_copy_of_the_file_recovers(self):
        body = {"title": "Copied", "spec": "s", "depends_on": []}
        first = self.w.ok("a", "new", "--file", self.w.file(body))
        again = self.w.ok("b", "new", "--file", self.w.file(dict(body)))
        self.assertEqual((first["created"]["id"], True), (again["created"]["id"], again["created"]["recovered"]))
        self.assertEqual(1, len(self.goal_refs()))

    def test_root_commit_carries_the_request_key_trailer_before_engine(self):
        out = self.w.ok("a", "new", "--file", self.w.file({"title": "T", "spec": "S", "request_key": "my-key.1"}))
        self.assertEqual("my-key.1", out["created"]["request_key"])
        msg = self.w.remote_git("log", "-1", "--format=%B", out["created"]["goal_commit"])
        lines = msg.splitlines()
        self.assertEqual("zzzops: new G1000", lines[0])
        self.assertIn("Request-Key: my-key.1", lines)
        self.assertLess(lines.index("Request-Key: my-key.1"), next(i for i, l in enumerate(lines) if l.startswith("Engine: ")))
        # no other verb writes the trailer
        self.w.ok("a", "edit", "1000", "--set", 'priority="P1"', "--base", self.tip(1000))
        self.assertNotIn("Request-Key:", self.w.remote_git("log", "-1", "--format=%B", self.tip(1000)))

    def test_default_key_ignores_depends_on_order(self):
        self.w.new(title="dep a")
        self.w.new(title="dep b")
        first = self.w.ok("a", "new", "--file", self.w.file({"title": "child", "spec": "c", "depends_on": [1001, 1000]}))
        self.assertEqual(default_key("child", "c", [1000, 1001]), first["created"]["request_key"])
        again = self.w.ok("a", "new", "--file", self.w.file({"title": "child", "spec": "c", "depends_on": [1000, 1001]}))
        self.assertEqual((1002, True), (again["created"]["id"], again["created"]["recovered"]))
        self.assertEqual(3, len(self.goal_refs()))

    def test_title_and_spec_are_hashed_exactly_as_given(self):
        a = self.w.ok("a", "new", "--file", self.w.file({"title": "T", "spec": "S"}))
        b = self.w.ok("a", "new", "--file", self.w.file({"title": "T", "spec": "S\n"}))
        self.assertNotEqual(a["created"]["id"], b["created"]["id"])
        self.assertIs(False, b["created"]["recovered"])

    # 2. a push that lands but reports failure

    def test_push_that_landed_but_reported_remote_failure_is_recovered(self):
        import engine.store
        from unittest import mock
        real = engine.store.push_atomic
        calls = []

        def landed_then_failed(git, R, updates, **kw):
            calls.append(updates)
            real(git, R, updates, **kw)
            return "remote", "simulated"

        f = self.w.file({"title": "Flaky", "spec": "network"})
        with mock.patch("engine.store.push_atomic", landed_then_failed):
            rc, out = InProcess(self.w, "a").run("new", "--file", f)
        self.assertEqual(0, rc, out)
        self.assertEqual(1, len(calls))
        self.assertIs(True, out["created"]["recovered"])
        self.assertEqual(1000, out["created"]["id"])
        self.assertEqual(self.root_of(1000), out["created"]["goal_commit"])
        self.assertEqual(["refs/heads/zzzops/goal/g1000"], self.goal_refs())
        # a later retry is an ordinary recovery
        again = self.w.ok("b", "new", "--file", f)
        self.assertEqual((1000, True), (again["created"]["id"], again["created"]["recovered"]))

    def test_push_that_did_not_land_still_reports_remote(self):
        from unittest import mock
        f = self.w.file({"title": "Down", "spec": "network"})
        with mock.patch("engine.store.push_atomic", lambda git, R, updates, **kw: ("remote", "simulated")):
            rc, out = InProcess(self.w, "a").run("new", "--file", f)
        self.assertEqual(2, rc, out)
        self.assertEqual("remote", out["error"]["code"])
        self.assertIn("retry", out["error"].get("hint", ""))
        self.assertEqual([], self.goal_refs())
        # rerunning once the remote is back creates the goal
        out = self.w.ok("a", "new", "--file", f)
        self.assertEqual((1000, False), (out["created"]["id"], out["created"]["recovered"]))

    def test_rejected_push_recovers_a_twin_that_won_the_race(self):
        import engine.store
        from unittest import mock
        real = engine.store.push_atomic
        f = self.w.file({"title": "Twin", "spec": "race"})
        twin = {}

        def twin_lands_first(git, R, updates, **kw):
            if not twin:
                twin.update(self.w.ok("b", "new", "--file", f, now=self.w.now + 1))     # a distinct root commit
            return real(git, R, updates, **kw)

        with mock.patch("engine.store.push_atomic", twin_lands_first):
            rc, out = InProcess(self.w, "a").run("new", "--file", f)
        self.assertEqual(0, rc, out)
        self.assertIs(False, twin["created"]["recovered"])
        self.assertEqual(twin["created"]["id"], out["created"]["id"])
        self.assertIs(True, out["created"]["recovered"])
        self.assertEqual(twin["created"]["goal_commit"], out["created"]["goal_commit"])
        self.assertEqual(1, len(self.goal_refs()))

    def test_a_goal_whose_local_ref_outran_this_fetch_is_recovered_not_duplicated(self):
        """Two `new` calls in one clone: the other call's fetch wrote refs/zzzops/goal/origin/g1000 after this call's
        fetch listed the remote, so this snapshot sees G1000 only as a local ref (`deleted`). The goal exists on the
        remote; the request must recover it, not allocate G1001 (seen as a flaky duplicate in the threaded test)."""
        import engine.store
        from unittest import mock
        f = self.w.file({"title": "Outran", "spec": "fetch race"})
        first = self.w.ok("b", "new", "--file", f)
        self.w.ok("a", "next")                                        # a's local goal ref exists
        real = engine.store.build_snapshot
        calls = []

        def stale_first(git, R, I, lines, rewritten, goals, deps):
            if not calls:
                lines = [l for l in lines if not l[3].endswith("/g1000")]
            calls.append(1)
            return real(git, R, I, lines, rewritten, goals, deps)

        self.w.reset_trace()
        with mock.patch("engine.store.build_snapshot", stale_first):
            rc, out = InProcess(self.w, "a").run("new", "--file", f)
        self.assertEqual(0, rc, out)
        self.assertEqual((1000, True), (out["created"]["id"], out["created"]["recovered"]))
        self.assertEqual(first["created"]["goal_commit"], out["created"]["goal_commit"])
        self.assertEqual(["refs/heads/zzzops/goal/g1000"], self.goal_refs())
        self.assertGreaterEqual(len(calls), 2, "the call must refetch once before allocating")
        self.assertEqual([], self.pushes())                          # recovered before any id was allocated

    # 3. concurrent identical calls

    def test_concurrent_identical_new_creates_one_goal(self):
        # distinct clocks, so each call builds a distinct root commit
        self.race_identical(lambda i: self.w.now + i)

    def test_concurrent_identical_new_with_one_clock_reports_exactly_one_fresh_create(self):
        """Design §4: identical calls in the same second build the same root commit; the losers' create-only pushes
        are `up_to_date` and must count as recoveries, so exactly one call reports recovered:false."""
        self.race_identical(lambda i: self.w.now)

    def race_identical(self, clock):
        f = self.w.file({"title": "Same", "spec": "same request"})
        results = []

        def make(clone, i):
            results.append(self.w.run(clone, "new", "--file", f, now=clock(i)))

        threads = [threading.Thread(target=make, args=(c, 2 * i + j)) for i in range(5) for j, c in enumerate(("a", "b"))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual([0] * 10, [rc for rc, _ in results], [o for rc, o in results if rc][:2])
        self.assertEqual({1000}, {o["created"]["id"] for _, o in results})
        self.assertEqual(1, len({o["created"]["goal_commit"] for _, o in results}))
        self.assertEqual(["refs/heads/zzzops/goal/g1000"], self.goal_refs())
        self.assertEqual(1, sum(1 for _, o in results if o["created"]["recovered"] is False))
        self.assertTrue(any(o["created"]["recovered"] for _, o in results))

    # 9. an up-to-date create push

    def test_an_up_to_date_create_push_counts_as_recovered(self):
        """A twin with the same file and the same ZZZOPS_NOW pushes the identical root first. This call's scans are
        patched to miss, so only the `up_to_date` push result can make it a recovery."""
        import engine.store
        from unittest import mock
        real = engine.store.push_atomic
        f = self.w.file({"title": "Twin", "spec": "same second"})
        twin, results, kws = {}, [], []

        def twin_lands_first(git, R, updates, **kw):
            if not twin:
                twin.update(self.w.ok("b", "new", "--file", f))         # same clock: the identical root commit
            kws.append(kw)
            r = real(git, R, updates, **kw)
            results.append(r[0])
            return r

        with mock.patch("engine.store.push_atomic", twin_lands_first), \
                mock.patch("engine.store.find_request_key", lambda git, snap, key: []):
            rc, out = InProcess(self.w, "a").run("new", "--file", f)
        self.assertEqual(0, rc, out)
        self.assertEqual([{"report_up_to_date": True}], kws)
        self.assertEqual(["up_to_date"], results)
        self.assertIs(False, twin["created"]["recovered"])
        self.assertEqual((1000, True), (out["created"]["id"], out["created"]["recovered"]))
        self.assertEqual(twin["created"]["goal_commit"], out["created"]["goal_commit"])
        self.assertEqual(default_key("Twin", "same second"), out["created"]["request_key"])
        self.assertEqual([(1000, "design")], [(a["goal"], a["node"]) for a in out["next"]["actions"]])
        self.assertEqual(["refs/heads/zzzops/goal/g1000"], self.goal_refs())

    def test_a_failed_request_key_scan_is_an_engine_bug_and_pushes_nothing(self):
        """A non-zero `git log --stdin --max-parents=0` must not read as "no match" (that could allocate a duplicate
        of a goal that already landed): `new` reports engine_bug, exit 1, and pushes no goal ref."""
        from engine.gitrun import Git
        from unittest import mock
        self.w.new(title="existing")                                  # a goal tip, so the scan runs a log
        real = Git.run
        scans = []

        def broken_scan(git, *args, **kw):
            if "log" in args and "--stdin" in args and "--max-parents=0" in args:
                scans.append(list(args))
                args = (*args, "--no-such-option")                    # real git, real non-zero exit
            return real(git, *args, **kw)

        f = self.w.file({"title": "Scan", "spec": "broken"})
        self.w.reset_trace()
        with mock.patch.object(Git, "run", broken_scan):
            rc, out = InProcess(self.w, "a").run("new", "--file", f)
        self.assertEqual((1, "engine_bug"), (rc, out["error"]["code"]), out)
        self.assertGreaterEqual(len(scans), 1)
        self.assertEqual(["refs/heads/zzzops/goal/g1000"], self.goal_refs())
        self.assertEqual([], self.pushes())

    def test_push_atomic_reports_up_to_date_only_when_asked(self):
        from engine import store
        from engine.session import Session
        out = self.w.ok("a", "new", "--file", self.w.file({"title": "U", "spec": "s"}))
        c, ref = out["created"]["goal_commit"], "refs/heads/zzzops/goal/g1000"
        with fx.env_of(self.w.cli_env()):
            cwd = os.getcwd()
            os.chdir(self.w.clones["a"].path)
            try:
                s = Session()
                s.open()
                self.assertEqual("ok", store.push_atomic(s.git, s.R, [(ref, None, c)])[0])
                self.assertEqual("up_to_date", store.push_atomic(s.git, s.R, [(ref, None, c)], report_up_to_date=True)[0])
                # a real create still reports ok with the keyword; a lost create-only lease is still rejected
                self.w.seed.git("fetch", "-q", "origin", ref)
                other = self.w.seed.git("commit-tree", self.w.seed.git("rev-parse", "FETCH_HEAD^{tree}"), "-m", "x")
                self.w.seed.git("push", "-q", "origin", f"{other}:refs/heads/zzzops/goal/g1001")
                self.assertEqual("ok", store.push_atomic(s.git, s.R, [("refs/heads/zzzops/goal/g1002", None, c)],
                                                         report_up_to_date=True)[0])
                self.assertEqual("rejected", store.push_atomic(s.git, s.R, [("refs/heads/zzzops/goal/g1001", None, c)],
                                                               report_up_to_date=True)[0])
            finally:
                os.chdir(cwd)

    # 4. a key reused with different contents

    def test_explicit_key_reused_with_a_different_spec_is_refused(self):
        self.w.ok("a", "new", "--file", self.w.file({"title": "K", "spec": "one", "request_key": "rk-1"}))
        rc, err = self.w.run("b", "new", "--file", self.w.file({"title": "K", "spec": "two", "request_key": "rk-1"}))
        self.assertEqual(1, rc, err)
        self.assertEqual("validation", err["error"]["code"])
        self.assertEqual(1000, err["error"]["details"]["goal"])
        self.assertIn("spec", err["error"]["details"]["fields"])
        self.assertNotIn("title", err["error"]["details"]["fields"])
        self.assertIn("rk-1", err["error"]["message"])
        self.assertIn("G1000", err["error"]["message"])
        self.assertEqual(1, len(self.goal_refs()))

    def test_default_key_with_a_different_explicit_priority_is_refused(self):
        self.w.ok("a", "new", "--file", self.w.file({"title": "P", "spec": "s"}))
        rc, err = self.w.run("a", "new", "--file", self.w.file({"title": "P", "spec": "s", "priority": "P1"}))
        self.assertEqual((1, "validation"), (rc, err["error"]["code"]), err)
        self.assertEqual(1000, err["error"]["details"]["goal"])
        self.assertEqual(["priority"], err["error"]["details"]["fields"])
        self.assertEqual(1, len(self.goal_refs()))

    def test_retry_that_omits_an_optional_field_the_original_set_is_recovered(self):
        first = self.w.ok("a", "new", "--file", self.w.file({"title": "O", "spec": "s", "priority": "P1",
                                                              "links": {"issue": 7}, "state": "held"}))
        again = self.w.ok("a", "new", "--file", self.w.file({"title": "O", "spec": "s"}))
        self.assertEqual((first["created"]["id"], True), (again["created"]["id"], again["created"]["recovered"]))
        self.assertEqual("P1", again["created"]["priority"])                 # built from the root document

    def test_retry_that_sets_a_field_to_the_value_the_original_defaulted_to_is_recovered(self):
        first = self.w.ok("a", "new", "--file", self.w.file({"title": "D", "spec": "s"}))
        again = self.w.ok("a", "new", "--file", self.w.file({"title": "D", "spec": "s", "priority": "P2",
                                                              "graph": "default"}))
        self.assertEqual((first["created"]["id"], True), (again["created"]["id"], again["created"]["recovered"]))

    def test_retry_after_the_current_release_moved_is_recovered(self):
        f = self.w.file({"title": "R", "spec": "s"})
        first = self.w.ok("a", "new", "--file", f)
        p = json.loads(json.dumps(self.w.policy))
        p["settings"]["releases"]["current"] = 2
        self.w.push_dev({".zzzops/POLICY.json": json.dumps(p, indent=2) + "\n"})
        again = self.w.ok("a", "new", "--file", f)
        self.assertEqual((first["created"]["id"], True), (again["created"]["id"], again["created"]["recovered"]))
        self.assertEqual(first["created"]["release"], again["created"]["release"])

    # 5. distinct requests stay distinct

    def test_same_title_with_distinct_specs_makes_two_goals(self):
        a = self.w.ok("a", "new", "--file", self.w.file({"title": "Same title", "spec": "first"}))
        b = self.w.ok("a", "new", "--file", self.w.file({"title": "Same title", "spec": "second"}))
        self.assertEqual([1000, 1001], [a["created"]["id"], b["created"]["id"]])
        self.assertEqual([False, False], [a["created"]["recovered"], b["created"]["recovered"]])
        self.assertEqual(2, len(self.goal_refs()))

    def test_identical_contents_with_distinct_explicit_keys_make_two_goals(self):
        a = self.w.ok("a", "new", "--file", self.w.file({"title": "T", "spec": "S", "request_key": "first"}))
        b = self.w.ok("a", "new", "--file", self.w.file({"title": "T", "spec": "S", "request_key": "second"}))
        self.assertEqual([1000, 1001], [a["created"]["id"], b["created"]["id"]])
        self.assertIs(False, b["created"]["recovered"])

    def test_distinct_depends_on_makes_a_distinct_request(self):
        self.w.new(title="dep")
        a = self.w.ok("a", "new", "--file", self.w.file({"title": "T", "spec": "S"}))
        b = self.w.ok("a", "new", "--file", self.w.file({"title": "T", "spec": "S", "depends_on": [1000]}))
        self.assertEqual([1001, 1002], [a["created"]["id"], b["created"]["id"]])

    # 6. recovery reads the root, not the tip

    def test_recovery_after_the_title_was_edited(self):
        f = self.w.file({"title": "Original", "spec": "s"})
        first = self.w.ok("a", "new", "--file", f)
        self.w.ok("a", "edit", "1000", "--set", 'title="Renamed"', "--base", self.tip(1000))
        self.assertNotEqual(first["created"]["goal_commit"], self.tip(1000))
        again = self.w.ok("b", "new", "--file", f)
        self.assertEqual((1000, True), (again["created"]["id"], again["created"]["recovered"]))
        self.assertEqual(first["created"]["goal_commit"], again["created"]["goal_commit"])
        self.assertEqual(self.root_of(1000), again["created"]["goal_commit"])
        self.assertEqual("Original", again["created"]["title"])          # the response the first call printed
        self.assertEqual(1, len(self.goal_refs()))

    def test_recovery_of_a_closed_goal(self):
        f = self.w.file({"title": "Closed later", "spec": "s"})
        first = self.w.ok("a", "new", "--file", f)
        close = self.w.file({"set": {"state": "closed", "closed.reason": "cancelled", "closed.note": "not needed"}})
        self.w.ok("a", "edit", "1000", "--file", close, "--base", self.tip(1000))
        rc, again = self.w.run("b", "new", "--file", f)
        self.assertEqual(0, rc, again)
        self.assertEqual((1000, True), (again["created"]["id"], again["created"]["recovered"]))
        self.assertEqual(first["created"]["goal_commit"], again["created"]["goal_commit"])
        self.assertEqual([], again["next"]["actions"])                  # a closed goal has an empty scoped `next`
        self.assertEqual(1, len(self.goal_refs()))

    # scan scope

    def test_legacy_roots_without_a_trailer_never_match(self):
        push_root(self.w, 1000, title="Legacy", spec="old request")
        out = self.w.ok("a", "new", "--file", self.w.file({"title": "Legacy", "spec": "old request"}))
        self.assertEqual((1001, False), (out["created"]["id"], out["created"]["recovered"]))

    def test_a_root_whose_head_names_another_goal_never_matches(self):
        push_root(self.w, 1000, key="k1", head_id=1005, title="T", spec="S")
        out = self.w.ok("a", "new", "--file", self.w.file({"title": "T", "spec": "S", "request_key": "k1"}))
        self.assertIs(False, out["created"]["recovered"])
        self.assertNotEqual(1000, out["created"]["id"])

    def test_a_root_whose_document_id_differs_never_matches(self):
        push_root(self.w, 1000, key="k1", title="T", spec="S", id=1003)
        rc, out = self.w.run("a", "new", "--file", self.w.file({"title": "T", "spec": "S", "request_key": "k1"}))
        self.assertFalse(rc == 0 and out["created"]["recovered"] and out["created"]["id"] == 1000, out)

    def fetches(self):
        return [l for l in self.w.trace_lines() if l["cmd"][:2] == ["git", "fetch"]]

    def test_a_deleted_goal_is_not_recovered(self):
        """Design §3: a goal still in `snap.deleted` after the one refetch really is gone, and stays excluded."""
        f = self.w.file({"title": "Gone", "spec": "s"})
        self.w.ok("a", "new", "--file", f)
        self.w.ok("b", "next")                                        # b has seen it
        self.w.reset_trace()
        self.w.ok("b", "new", "--file", self.w.file({"title": "Baseline", "spec": "nothing deleted yet"}))
        baseline = len(self.fetches())                                # fetches of a `new` with snap.deleted empty
        self.w.remote_git("update-ref", "-d", "refs/heads/zzzops/goal/g1000")
        self.w.reset_trace()
        out = self.w.ok("b", "new", "--file", f)
        self.assertEqual((1002, False), (out["created"]["id"], out["created"]["recovered"]))
        self.assertEqual(baseline + 1, len(self.fetches()), "exactly one refetch, then allocate")
        self.assertEqual(1, len(self.pushes()))

    def test_several_matches_return_the_lowest_id_with_a_warning(self):
        push_root(self.w, 1000, key="dup-key", title="T", spec="S")
        push_root(self.w, 1001, key="dup-key", title="T", spec="S")
        out = self.w.ok("a", "new", "--file", self.w.file({"title": "T", "spec": "S", "request_key": "dup-key"}))
        self.assertEqual((1000, True), (out["created"]["id"], out["created"]["recovered"]))
        warnings = list(out.get("warnings") or []) + list(out["next"].get("warnings") or [])
        dup = [x for x in warnings if x.get("kind") == "duplicate_request_key"]
        self.assertEqual(1, len(dup), warnings)
        self.assertIn("1000", json.dumps(dup[0]))
        self.assertIn("1001", json.dumps(dup[0]))
        self.assertEqual(2, len(self.goal_refs()))

    def scan(self, *keys):
        """Run store.find_request_key in process on clone a; returns ([hits per key], [git log argvs])."""
        from engine import store
        from engine.session import Session
        logs = []
        with fx.env_of(self.w.cli_env()):
            cwd = os.getcwd()
            os.chdir(self.w.clones["a"].path)
            try:
                s = Session()
                s.open()
                run = s.git.run

                def spy(*args, **kw):
                    if next((a for a in args if not a.startswith("-")), "") == "log":
                        logs.append(list(args))
                    return run(*args, **kw)

                s.git.run = spy
                hits = [store.find_request_key(s.git, s.snap, k) for k in keys]
            finally:
                os.chdir(cwd)
        return hits, logs

    def test_find_request_key_with_no_goals_returns_nothing_and_runs_no_log(self):
        hits, logs = self.scan(default_key("T", "S"))
        self.assertEqual([[]], hits)
        self.assertEqual([], logs)                                    # `git log --stdin` with no tips would walk HEAD

    def test_find_request_key_returns_the_root_and_its_document(self):
        f = self.w.file({"title": "Found", "spec": "s", "request_key": "find-me"})
        first = self.w.ok("a", "new", "--file", f)
        self.w.ok("a", "edit", "1000", "--set", 'title="Edited"', "--base", self.tip(1000))
        self.w.new(title="other")
        (hits, missing), logs = self.scan("find-me", "missing")
        self.assertEqual([], missing)
        self.assertEqual(1, len(hits))
        gid, root, doc = hits[0]
        self.assertEqual((1000, first["created"]["goal_commit"]), (gid, root))
        self.assertEqual(("Found", 1000), (doc["title"], doc["id"]))
        self.assertEqual(2, len(logs), logs)                          # one git invocation per scan
        for argv in logs:
            self.assertIn("--max-parents=0", argv)
            self.assertIn("--stdin", argv)

    # writes and previews

    def test_exact_retry_recovers_while_writes_are_blocked(self):
        f = self.w.file({"title": "Blocked", "spec": "s"})
        first = self.w.ok("a", "new", "--file", f)
        p = json.loads(json.dumps(self.w.policy))
        p["settings"]["engine"] = {"requires": ["no_such_cap"]}
        self.w.push_dev({".zzzops/POLICY.json": json.dumps(p)})
        again = self.w.ok("b", "new", "--file", f)                     # recovering writes nothing
        self.assertEqual((first["created"]["id"], True), (again["created"]["id"], again["created"]["recovered"]))
        rc, err = self.w.run("b", "new", "--file", self.w.file({"title": "Blocked", "spec": "other"}))
        self.assertEqual((1, "engine_too_old"), (rc, err["error"]["code"]))

    def test_policy_ref_is_refused_even_for_a_retry(self):
        f = self.w.file({"title": "Preview", "spec": "s"})
        self.w.ok("a", "new", "--file", f)
        rc, err = self.w.run("a", "new", "--policy-ref", "dev", "--file", f)
        self.assertEqual((1, "usage"), (rc, err["error"]["code"]), err)


class NewReleaseOrderTests(StoreBase):
    """G1034 design, Testing 2: the backstop the migrate skill relies on. `new` refuses a dependency on a later
    release and writes no goal ref."""

    def goal_refs(self):
        return self.w.remote_git("for-each-ref", "--format=%(refname)", "refs/heads/zzzops/goal/").split()

    def test_new_stores_an_explicit_release(self):
        out = self.w.ok("a", "new", "--file", self.w.file({"title": "Later", "spec": "s", "release": 2}))
        self.assertEqual(2, out["created"]["release"])

    def test_new_refuses_a_dependency_on_a_later_release_and_writes_no_goal_ref(self):
        first = self.w.ok("a", "new", "--file", self.w.file({"title": "Later", "spec": "s", "release": 2}))
        dep = first["created"]["id"]
        before = self.goal_refs()
        rc, err = self.w.run("a", "new", "--file", self.w.file(
            {"title": "Earlier", "spec": "s", "release": 1, "depends_on": [dep]}))
        self.assertEqual((1, "validation"), (rc, err["error"]["code"]), err)
        self.assertIn("release 2", json.dumps(err))
        self.assertEqual(before, self.goal_refs())
        self.assertEqual(1, len(self.goal_refs()))


class NewFileSchemaTests(unittest.TestCase):
    """G1001 design §1: the optional `request_key` of a new-goal file."""

    def errs(self, key):
        from engine import schemas
        return schemas.validate_new_file({"title": "T", "spec": "S", "request_key": key})

    def test_valid_keys_are_accepted(self):
        for key in ("a", "Z", "0", "issue-812", "my_key.v2", "a" * 128, "A1._-z"):
            self.assertEqual([], self.errs(key), key)

    def test_invalid_keys_are_rejected(self):
        for key in ("", "sha256:abc", "a:b", "a" * 129, "a" * 200, "-lead", ".lead", "_lead", "has space",
                    "new\nline", "é", 5, None, ["k"]):
            self.assertTrue(self.errs(key), key)
            self.assertTrue(any("request_key" in str(e) for e in self.errs(key)), (key, self.errs(key)))

    def test_absent_key_is_still_valid(self):
        from engine import schemas
        self.assertEqual([], schemas.validate_new_file({"title": "T", "spec": "S"}))

if __name__ == "__main__":
    unittest.main()
