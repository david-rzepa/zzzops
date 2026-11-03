"""G1038: real Git merge sync, scoped checkpoints, carry and tree-overlay PRs.

The fixture calls the production ops with real Git and fake GitHub, without paying
for unrelated design/review/approval journeys in every case.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import engine_fixtures as fx
import merge_sync_fixtures as msf
from engine.canon import ZERO
from engine.errors import Refused
from engine.identity import Identity
from engine.ops.run import Blocked, Done
from engine import carry, records
from engine.schemas import build_graph


class MergeSyncTests(msf.OpFixture):
    def assert_sync(self, out, old, onto, work, resolved=()):
        self.assertIsInstance(out, Done, getattr(out, "blocked", out))
        self.assertTrue(out.ok, out)
        synced = out.output.get("synced")
        self.assertIsNotNone(synced, "merge-mode base must record synced")
        self.assertEqual({"old", "onto", "work", "tip", "merge", "resolved"}, set(synced))
        self.assertEqual((old, onto, work, list(resolved)),
                         (synced["old"], synced["onto"], synced["work"], synced["resolved"]))
        merge = synced["merge"]
        self.assertEqual(merge, synced["tip"])
        self.assertEqual([work, onto], self.git.out("rev-list", "--parents", "-n", "1", merge).split()[1:])
        self.assertTrue(self.git.is_ancestor(work, merge), "work push must be fast-forward")
        message = self.git.out("show", "-s", "--format=%B", merge)
        self.assertTrue(message.startswith("chore(sync): "), message)
        self.assertIn(f"Zzzops-Old-Base: {old}", message)
        self.assertEqual({}, out.output["replay_map"])
        self.assertEqual({}, out.output["replay_pos"])
        return synced

    def test_two_syncs_preserve_work_commits_and_only_fast_forward(self):
        work = self.publish({"goal.txt": "goal\n"}, "feat: goal")
        onto = self.trunk({"trunk.txt": "one\n"})
        first = self.run_base()
        s1 = self.assert_sync(first, self.base, onto, work)
        repeated = self.run_base()
        self.assertEqual(first.output["synced"], repeated.output["synced"], "sync commit identity is deterministic")
        self.apply(first)
        self.assertEqual(s1["tip"], self.wt.git("rev-parse", "HEAD"))
        onto2 = self.trunk({"trunk.txt": "two\n"})
        second = self.run_base(old=onto)
        s2 = self.assert_sync(second, onto, onto2, s1["tip"])
        self.apply(second)
        self.assertTrue(self.git.is_ancestor(work, s2["tip"]))
        self.assertEqual("goal", self.wt.git("show", "HEAD:goal.txt"))
        self.assertEqual("two", self.wt.git("show", "HEAD:trunk.txt"))
        self.assertEqual(2, len(self.git.out("rev-list", "--first-parent", "--merges", f"{self.base}..{s2['tip']}").split()))

    def conflict(self):
        work = self.publish({"src/app.py": "def app():\n    return 2\n"}, "fix: goal")
        onto = self.trunk({"src/app.py": "def app():\n    return 3\n", "trunk-only.txt": "keep trunk\n"})
        out = self.run_base()
        self.assertIsInstance(out, Blocked)
        self.assertIn("merge conflict in src/app.py", out.blocked["reason"])
        self.assertEqual("agent", out.blocked["waiting_for"])
        st = out.blocked["op_state"]
        self.assertEqual({"work", "onto", "old", "files", "tree"}, set(st))
        self.assertEqual(work, self.wt.git("rev-parse", "HEAD"))
        self.assertIn("<<<<<<< ", Path(self.path, "src/app.py").read_text())
        self.assertEqual("keep trunk", Path(self.path, "trunk-only.txt").read_text().strip())
        return work, onto, {"status": "blocked", "blocked": out.blocked}

    def test_conflict_resume_rejects_unlisted_edits_and_ignores_staged_trunk_changes(self):
        work, onto, rec = self.conflict()
        still_marked = self.run_base(record=rec)
        self.assertIsInstance(still_marked, Blocked)
        self.wt.write({"src/app.py": "def app():\n    return 23\n"})
        # These are separate bad paths, including a common editor backup suffix.
        for path in ("scratch.tmp", "src/app.py.orig", "README.md"):
            with self.subTest(path=path):
                before = Path(self.path, path).read_bytes() if Path(self.path, path).exists() else None
                self.wt.write({path: "outside conflict\n"})
                self.wt.git("add", "-A")
                refused = self.run_base(record=rec)
                self.assertIsInstance(refused, Blocked)
                self.assertIn(path, json.dumps(refused.blocked))
                self.assertEqual(work, self.w.remote_git("rev-parse", "refs/heads/zzzops/work/g1000"))
                self.wt.write({path: before})
                self.wt.git("add", "-A")
        # The index includes trunk's non-conflicting change and the resolved file.
        # Comparing against HEAD would reject trunk-only.txt; compare against T.
        self.wt.git("add", "trunk-only.txt", "src/app.py")
        out = self.run_base(record=rec)
        synced = self.assert_sync(out, self.base, onto, work, ["src/app.py"])
        self.apply(out)
        self.assertEqual("keep trunk", self.wt.git("show", "HEAD:trunk-only.txt"))
        self.assertNotIn("scratch.tmp", self.wt.git("ls-tree", "-r", "--name-only", "HEAD"))
        self.assertEqual("", self.wt.git("status", "--porcelain"))
        # A second sync changing another hunk must preserve the prior resolution.
        newer = self.trunk({"src/app.py": "# trunk adds comment\ndef app():\n    return 3\n"})
        next_out = self.run_base(old=onto)
        self.assert_sync(next_out, onto, newer, synced["tip"])
        self.apply(next_out)
        self.assertEqual("# trunk adds comment\ndef app():\n    return 23", self.wt.git("show", "HEAD:src/app.py"))

    def test_conflict_resume_accepts_review_only_remote_advance(self):
        work, onto, rec = self.conflict()
        current, _ = self.ident.artifact_commit(work, self.base, 1000, "late", b"late review\n")
        self.git.run("push", "-q", "origin", f"{current}:refs/heads/zzzops/work/g1000")
        self.snap.work[1000] = current
        self.wt.write({"src/app.py": "resolved\n"})
        out = self.run_base(record=rec)
        self.assert_sync(out, self.base, onto, current, ["src/app.py"])
        self.apply(out)
        self.assertEqual("late review", self.wt.git("show", "HEAD:.zzzops/reviews/1000/late.md"))

    def test_modify_delete_can_be_resolved_by_deleting_the_listed_path(self):
        work = self.publish({"src/app.py": "changed\n"}, "fix: change")
        onto = self.trunk({"src/app.py": None})
        blocked = self.run_base()
        self.assertIsInstance(blocked, Blocked)
        self.wt.write({"src/app.py": None})
        out = self.run_base(record={"status": "blocked", "blocked": blocked.blocked})
        self.assert_sync(out, self.base, onto, work, ["src/app.py"])
        self.apply(out)
        self.assertNotIn("src/app.py", self.wt.git("ls-tree", "-r", "--name-only", "HEAD"))

    def test_moved_onto_restarts_the_conflict_and_says_edits_were_lost(self):
        self.conflict_work, _, rec = self.conflict()
        self.wt.write({"src/app.py": "my now obsolete resolution\n"})
        newer = self.trunk({"src/app.py": "different trunk\n"})
        out = self.run_base(record=rec)
        self.assertIsInstance(out, Blocked)
        self.assertEqual(newer, out.blocked["op_state"]["onto"])
        self.assertRegex(json.dumps(out.blocked).lower(), r"(lost|discard|reset|restart)")
        self.assertNotIn("obsolete", Path(self.path, "src/app.py").read_text())

    def test_without_capability_base_rebases_and_records_no_sync(self):
        self.settings["engine"] = {"requires": []}
        work = self.publish({"own.txt": "own\n"}, "feat: own")
        onto = self.trunk({"other.txt": "new\n"})
        out = self.run_base()
        self.assertIsNone(out.output.get("synced"))
        self.apply(out)
        tip = self.snap.work[1000]
        self.assertFalse(self.git.is_ancestor(work, tip))
        self.assertEqual(onto, self.git.out("rev-parse", f"{tip}^"))
        self.assertTrue(out.output["replay_map"])

    def test_sticky_mode_refuses_rebase_before_touching_refs_or_worktree(self):
        work = self.publish({"own.txt": "own\n"}, "feat: own")
        onto = self.trunk({"other.txt": "new\n"})
        out = self.run_base()
        self.assert_sync(out, self.base, onto, work)
        self.apply(out)
        remote_before = self.snap.work[1000]
        local_before = self.wt.git("rev-parse", "HEAD")
        newer = self.trunk({"third.txt": "later\n"})
        self.settings["engine"] = {"requires": []}
        blocked = self.run_base(old=onto)
        self.assertIsInstance(blocked, Blocked)
        self.assertEqual(("policy", "human"), (blocked.blocked["category"], blocked.blocked["waiting_for"]))
        self.assertIn("merge_sync", blocked.blocked["question"])
        self.assertEqual(remote_before, self.w.remote_git("rev-parse", "refs/heads/zzzops/work/g1000"))
        self.assertEqual(local_before, self.wt.git("rev-parse", "HEAD"))
        self.assertEqual("", self.wt.git("status", "--porcelain"))
        self.settings["engine"] = {"requires": ["merge_sync"]}
        self.assert_sync(self.run_base(old=onto), onto, newer, remote_before)

    def test_midflight_rebase_is_aborted_before_merge_mode_resumes(self):
        work = self.publish({"src/app.py": "goal\n"}, "fix: goal")
        onto = self.trunk({"src/app.py": "trunk\n"})
        self.wt.git("rebase", "--onto", onto, self.base, check=False)
        from engine.worktree import rebase_in_progress
        self.assertTrue(rebase_in_progress(self.git, self.path))
        out = self.run_base()
        self.assertIsInstance(out, Blocked)
        self.assertIn("merge conflict", out.blocked["reason"])
        self.assertFalse(rebase_in_progress(self.git, self.path))
        self.assertEqual(work, self.wt.git("rev-parse", "HEAD"))
        self.assertEqual(onto, out.blocked["op_state"]["onto"])

    def test_onto_already_contained_moves_base_without_creating_a_merge(self):
        onto = self.publish({"contained.txt": "already in work\n"}, "fix: contained")
        work = self.publish({"own.txt": "own\n"}, "feat: own")
        out = self.run_base(target={"branch": "dev", "tip": onto})
        self.assertIsInstance(out, Done)
        synced = out.output.get("synced")
        self.assertEqual({"old": self.base, "onto": onto, "work": work, "tip": work,
                          "merge": None, "resolved": []}, synced)
        self.assertFalse(out.ref_updates)

    def test_target_change_and_dropped_dependency_do_not_resurrect_old_base(self):
        # Old base contains an upstream breaking feature that must not become the goal's own work.
        old_base = self.publish({"dep-only.txt": "old dependency\n"}, "feat!: upstream")
        work = self.publish({"own.txt": "goal\n"}, "fix: own")
        new_base = self.trunk({"release-only.txt": "new target\n"})
        out = self.run_base(old=old_base, target={"branch": "release/1", "tip": new_base})
        self.assert_sync(out, old_base, new_base, work)
        self.apply(out)
        names = self.wt.git("ls-tree", "-r", "--name-only", "HEAD").splitlines()
        self.assertIn("own.txt", names)
        self.assertIn("release-only.txt", names)
        self.assertNotIn("dep-only.txt", names)
        # Squash's own walk must also exclude old-base commits, not only the new base.
        self.base = new_base
        integrated = self.integrate()
        commits = self.pr_commits(integrated)
        self.assertEqual(1, len(commits))
        message = self.git.out("show", "-s", "--format=%B", commits[0])
        self.assertTrue(message.startswith("fix: "), message)
        self.assertNotIn("feat!", message)
        self.assertNotIn("upstream", message)


    def test_rewritten_then_dropped_dependency_keeps_only_the_goals_commits(self):
        old_dep = self.publish({"old-dependency.txt": "old\n"}, "feat!: old dependency")
        work = self.publish({"own.txt": "own\n"}, "fix: own")
        tree = self.ident.put(self.git.out("rev-parse", f"{self.base}^{{tree}}"),
                              ["new-dependency.txt"], self.git.hash_object(b"new dependency\n"))
        rewritten = self.git.commit_tree(tree, [self.base], "feat!: rewritten dependency\n")
        out = self.run_base(old=old_dep, inputs={"heads": {"999": rewritten},
                            "prs": {"999": {"number": 999}}, "merges": {}}, dep_kinds={999: "open"})
        self.assert_sync(out, old_dep, rewritten, work)
        self.apply(out)
        names = self.wt.git("ls-tree", "-r", "--name-only", "HEAD").splitlines()
        self.assertNotIn("old-dependency.txt", names)
        self.assertIn("new-dependency.txt", names)
        first_sync = self.snap.work[1000]
        # Dropping the dependency takes onto back to dev, which is not a
        # descendant of either dependency head. Excluding only onto is unsafe.
        dropped = self.run_base(old=rewritten)
        self.assert_sync(dropped, rewritten, self.base, first_sync)
        self.apply(dropped)
        names = self.wt.git("ls-tree", "-r", "--name-only", "HEAD").splitlines()
        self.assertIn("own.txt", names)
        self.assertNotIn("new-dependency.txt", names)
        self.assertNotIn("old-dependency.txt", names)
        integrated = self.integrate()
        commits = self.pr_commits(integrated)
        self.assertEqual(1, len(commits))
        message = self.git.out("show", "-s", "--format=%B", commits[0])
        self.assertTrue(message.startswith("fix: "), message)
        self.assertNotIn("dependency", message)


class ScopedIdentityTests(msf.OpFixture):
    def test_change_scope_is_literal_and_empty_scope_is_zero(self):
        test = "tests/[literal]*.txt"
        tests = self.publish({test: "before\n", "tests/literal-other.txt": "x\n"}, "test: literal")
        code = self.publish({"src/new.py": "code\n"}, "feat: code")
        expected = self.ident.change(self.base, tests)
        # Both test paths must be present for this exact legacy equivalence check.
        self.assertEqual(expected, self.ident.change(self.base, code, paths=[test, "tests/literal-other.txt"]))
        self.assertEqual(ZERO, self.ident.change(self.base, code, paths=[]))
        only_literal = self.ident.change(self.base, code, paths=[test])
        changed_other = self.publish({"tests/literal-other.txt": "changed\n"}, "test: other")
        self.assertEqual(only_literal, self.ident.change(self.base, changed_other, paths=[test]))
        self.assertNotEqual(expected, self.ident.change(self.base, changed_other, paths=[test, "tests/literal-other.txt"]))

    def test_engine_merge_is_allowed_but_agent_style_merge_or_review_change_is_not(self):
        work = self.publish({"goal.txt": "g\n"}, "feat: goal")
        onto = self.trunk({"upstream.txt": "u\n"})
        tree = self.git.out("merge-tree", "--write-tree", work, onto).splitlines()[0]
        good = self.git.commit_tree(tree, [work, onto], f"chore(sync): merge dev into G1000\n\nZzzops-Old-Base: {self.base}\n")
        self.ident.check_i1_i2(self.base, good)
        bad_subject = self.git.commit_tree(tree, [work, onto], "feat: agent merge\n")
        with self.assertRaises(Refused):
            self.ident.check_i1_i2(self.base, bad_subject)
        altered = self.ident.put(tree, [".zzzops", "reviews", "1000", "bad.md"], self.git.hash_object(b"bad\n"))
        bad_review = self.git.commit_tree(altered, [work, onto], "chore(sync): merge dev into G1000\n")
        with self.assertRaises(Refused):
            self.ident.check_i1_i2(self.base, bad_review)
        # Invalid I1 on the trunk side is deliberately outside the first-parent walk.
        bad_upstream_tree = self.ident.put(self.git.out("rev-parse", f"{onto}^{{tree}}"),
                                          [".zzzops", "reviews", "x.md"], self.git.hash_object(b"upstream\n"))
        bad_upstream = self.git.commit_tree(bad_upstream_tree, [onto], "feat: upstream mixed\n")
        same_reviews = self.git.commit_tree(tree, [work, bad_upstream], "chore(sync): merge dev into G1000\n")
        self.ident.check_i1_i2(self.base, same_reviews)


class CarryContractTests(unittest.TestCase):
    def setUp(self):
        self.graph = build_graph("default", fx.load_template("workflow.json")["graphs"]["default"])

    def required(self, module, name):
        value = getattr(module, name, None)
        self.assertTrue(callable(value), f"G1038 contract requires {module.__name__}.{name}")
        return value

    def test_checkpoint_scope_is_derived_only_for_preserved_producer(self):
        scope = self.required(records, "checkpoint_scope")
        record = {"frozen": {"tests/z": {}, "tests/a": {}}}
        self.assertEqual(["tests/a", "tests/z"], scope(self.graph, "test_design", record))
        self.assertIsNone(scope(self.graph, "implement", record))
        self.assertIsNone(scope(self.graph, "test_design", {}))
        self.assertEqual([], scope(self.graph, "test_design", {"frozen": {}}))
        renamed = build_graph("default", fx.renamed_workflow()["graphs"]["default"])
        self.assertEqual(["tests/a", "tests/z"], scope(renamed, fx.RENAME["test_design"], record))

    def test_unchanged_compares_both_scoped_u0_changes(self):
        unchanged = self.required(carry, "unchanged")
        ident = Mock()
        ident.change.return_value = "same"
        old = {"base": "b0", "commit": "t0", "change": "same"}
        new = {"base": "b1", "commit": "m1", "change": "recorded"}
        with patch.object(carry, "resolved_paths", return_value=[], create=True):
            self.assertTrue(unchanged(ident, "test_design", "tests", old, new, ["tests/a"]))
            self.assertEqual(2, ident.change.call_count)
            ident.change.assert_any_call("b0", "t0", paths=["tests/a"], unified=0)
            ident.change.assert_any_call("b1", "m1", paths=["tests/a"], unified=0)
            ident.change.side_effect = ["same", "different"]
            self.assertFalse(unchanged(ident, "test_design", "tests", old, new, ["tests/a"]))

    def test_relocate_with_no_sync_does_not_invent_a_checkpoint(self):
        relocate = self.required(carry, "relocate")
        # The contract omits an Identity parameter; real Git is exercised below in MergeCarryTests.
        self.assertIsNone(relocate({"commit": "a" * 40}, None))


class MergeCarryTests(msf.OpFixture):
    def test_clean_sync_carries_both_checkpoints_to_the_merge_and_preserves_frozen(self):
        from engine_sim import Sim
        sim = Sim()
        doc = sim.goal(1000)
        sim.drive(1000, until="implement")
        tests = self.publish({"tests/probe.txt": "tests\n"}, "test: probe")
        code = self.publish({"own.txt": "code\n"}, "feat: code")
        for node, key, c in (("test_design", "tests", tests), ("implement", "code", code)):
            doc["records"][node]["output"][key] = {"commit": c, "base": self.base,
                "tree": self.ident.code_tree(c), "change": self.ident.change(self.base, c)}
        frozen = ["tests/probe.txt"]
        doc["records"]["test_design"]["frozen"] = frozen
        onto = self.trunk({"unrelated.txt": "trunk\n"})
        outcome = self.run_base()
        self.assertIsInstance(outcome, Done)
        self.assertIn("synced", outcome.output, "base must publish a merge sync before carry")
        self.apply(outcome)
        base_record = copy.deepcopy(doc["records"]["base"])
        base_record["output"] = outcome.output
        # Call the public carry hook with the base record; the old replay argument stays
        # for backwards compatibility but must not drive the new merge path.
        nodes = carry.carry_forward(SimpleNamespace(git=self.git), self.graph, doc, "base", base_record, None, {})
        self.assertEqual(["test_design", "implement"], nodes)
        for node, key in (("test_design", "tests"), ("implement", "code")):
            r = doc["records"][node]
            self.assertEqual("base", r["carried_by"])
            self.assertEqual(outcome.output["synced"]["tip"], r["output"][key]["commit"])
            self.assertEqual(onto, r["output"][key]["base"])
            self.assertNotIn("scope", r["output"][key])
        self.assertEqual(frozen, doc["records"]["test_design"]["frozen"])
        from engine.verbs import preserve_check
        preserve_check(SimpleNamespace(git=self.git), SimpleNamespace(graph=self.graph), doc,
                       "implement", doc["records"]["implement"]["output"]["code"], self.ident)


    def test_resolution_in_code_only_carries_tests_but_changed_test_hunk_does_not(self):
        from engine_sim import Sim
        sim = Sim()
        doc = sim.goal(1000)
        sim.drive(1000, until="implement")
        tests = self.publish({"tests/probe.txt": "test goal\n"}, "test: probe")
        code = self.publish({"src/app.py": "goal code\n"}, "fix: probe")
        for node, key, c in (("test_design", "tests", tests), ("implement", "code", code)):
            doc["records"][node]["output"][key] = {"commit": c, "base": self.base,
                "tree": self.ident.code_tree(c), "change": self.ident.change(self.base, c)}
        doc["records"]["test_design"]["frozen"] = ["tests/probe.txt"]
        original = copy.deepcopy(doc)
        onto = self.trunk({"src/app.py": "trunk code\n"})
        blocked = self.run_base()
        self.assertIsInstance(blocked, Blocked)
        self.wt.write({"src/app.py": "resolved implementation\n"})
        outcome = self.run_base(record={"status": "blocked", "blocked": blocked.blocked})
        self.assertIsInstance(outcome, Done)
        self.assertIn("synced", outcome.output)
        self.apply(outcome)
        br = copy.deepcopy(doc["records"]["base"])
        br["output"] = outcome.output
        nodes = carry.carry_forward(SimpleNamespace(git=self.git), self.graph, doc, "base", br, None, {})
        self.assertEqual(["test_design"], nodes)
        # Same relocation, but a changed frozen path: the tests predicate must fail.
        resolved = self.publish({"tests/probe.txt": "different test hunk\n"}, "test: changed")
        second = copy.deepcopy(br)
        second["output"]["synced"]["tip"] = resolved
        second["output"]["synced"]["merge"] = resolved
        nodes = carry.carry_forward(SimpleNamespace(git=self.git), self.graph, original, "base", second, None, {})
        self.assertNotIn("test_design", nodes)

    def test_carry_dispatch_uses_the_shared_predicate_and_keeps_recorded_change(self):
        from engine_sim import Sim
        sim = Sim()
        doc = sim.goal(1000)
        sim.drive(1000, until="implement")
        tests = self.publish({"tests/probe.txt": "test\n"}, "test: probe")
        code = self.publish({"own.txt": "code\n"}, "feat: code")
        for node, key, c in (("test_design", "tests", tests), ("implement", "code", code)):
            doc["records"][node]["output"][key] = {"commit": c, "base": self.base,
                "tree": self.ident.code_tree(c), "change": "recorded-" + node}
        doc["records"]["test_design"]["frozen"] = ["tests/probe.txt"]
        onto = self.trunk({"trunk.txt": "new\n"})
        out = self.run_base()
        self.assertIn("synced", out.output)
        self.apply(out)
        br = copy.deepcopy(doc["records"]["base"])
        br["output"] = out.output
        predicate = getattr(carry, "unchanged", None)
        self.assertTrue(callable(predicate), "shared predicate is G1039's integration seam")
        with patch.object(carry, "unchanged", return_value=True) as check:
            nodes = carry.carry_forward(SimpleNamespace(git=self.git), self.graph, doc, "base", br, None, {})
        self.assertEqual(["test_design", "implement"], nodes)
        self.assertEqual(2, check.call_count)
        by_node = {call.args[1]: call.args for call in check.call_args_list}
        self.assertEqual(["tests/probe.txt"], by_node["test_design"][5])
        self.assertIsNone(by_node["implement"][5])
        for node, key in (("test_design", "tests"), ("implement", "code")):
            self.assertEqual("recorded-" + node, doc["records"][node]["output"][key]["change"])


    def test_unrelated_checkpoint_is_not_carried_even_when_predicate_accepts(self):
        from engine_sim import Sim
        sim = Sim()
        doc = sim.goal(1000)
        sim.drive(1000, until="implement")
        tests = self.publish({"tests/probe.txt": "tests\n"}, "test: probe")
        work = self.publish({"own.txt": "code\n"}, "feat: code")
        # Same code tree, different ancestry: diff equivalence must not turn a
        # checkpoint outside synced.work's history into work that was reviewed.
        unrelated = self.git.commit_tree(self.ident.code_tree(work), [self.base], "feat: unrelated checkpoint\n")
        self.assertFalse(self.git.is_ancestor(unrelated, work))
        for node, key, c in (("test_design", "tests", tests), ("implement", "code", unrelated)):
            doc["records"][node]["output"][key] = {"commit": c, "base": self.base,
                "tree": self.ident.code_tree(c), "change": self.ident.change(self.base, c)}
        doc["records"]["test_design"]["frozen"] = ["tests/probe.txt"]
        untouched = copy.deepcopy(doc["records"]["implement"])
        onto = self.trunk({"trunk.txt": "trunk\n"})
        tree = self.git.out("merge-tree", "--write-tree", work, onto).splitlines()[0]
        tip = self.git.commit_tree(tree, [work, onto], f"chore(sync): merge dev into G1000\n\nZzzops-Old-Base: {self.base}\n")
        br = copy.deepcopy(doc["records"]["base"])
        br["output"] = {"base_commit": onto, "branch": "zzzops/work/g1000", "stack": [],
                        "replay_map": {}, "replay_pos": {}, "synced": {
                            "old": self.base, "onto": onto, "work": work, "tip": tip,
                            "merge": tip, "resolved": []}}
        with patch.object(carry, "unchanged", return_value=True, create=True):
            nodes = carry.carry_forward(SimpleNamespace(git=self.git), self.graph, doc, "base", br, None, {})
        self.assertIn("test_design", nodes, "valid ancestor should carry with the accepting predicate")
        self.assertNotIn("implement", nodes, "non-ancestor checkpoint must never relocate")
        self.assertEqual(untouched, doc["records"]["implement"])


class InterdiffTests(msf.OpFixture):
    def previous(self, old, current):
        from engine.card import previous
        self.doc["records"]["implement"] = {"status": "done", "output": {"code": current}}
        self.doc["records"]["review_impl"] = {"status": "done", "findings": [], "reviewed": {"code": old}}
        res = SimpleNamespace(graph=self.graph, doc=self.doc, goal=1000)
        return previous(self.session, res, "review_impl", {})

    def test_moved_base_interdiff_uses_first_parent_log_and_separate_syncs(self):
        old = self.publish({"own.txt": "old\n"}, "feat: own")
        newer = self.publish({"own.txt": "new\n"}, "fix: correction")
        onto = self.trunk({"trunk.txt": "trunk\n"})
        synced = self.run_base()
        self.assertIsInstance(synced, Done)
        self.assertIn("synced", synced.output)
        self.apply(synced)
        tip = self.snap.work[1000]
        prior = self.previous({"base": self.base, "commit": old, "change": "old"},
                              {"base": onto, "commit": tip, "change": "new"})
        self.assertIn("git log -p --first-parent --no-merges", prior["interdiff"])
        self.assertNotIn("range-diff", prior["interdiff"])
        self.assertEqual([f"git show --remerge-diff {tip}"], prior["syncs"])
        self.assertIn(f"{old}..{tip}", prior["interdiff"])

    def test_same_base_interdiff_is_an_ordinary_scoped_diff(self):
        old = self.publish({"own.txt": "old\n"}, "feat: own")
        newer = self.publish({"own.txt": "new\n"}, "fix: correction")
        prior = self.previous({"base": self.base, "commit": old, "change": "old"},
                              {"base": self.base, "commit": newer, "change": "new"})
        self.assertIn(f"git diff {old} {newer}", prior["interdiff"])
        self.assertNotIn("syncs", prior)


class UpgradeAndFingerprintTests(unittest.TestCase):
    def test_node_and_journey_fingerprints_stay_at_the_pre_feature_baseline(self):
        import hashlib
        import test_engine_branching as branching
        from engine.fingerprint import node_def_fp
        golden = json.loads((fx.ROOT / ".agents/fixtures/g1038_fingerprints.json").read_text())
        for label, path in (("graph12", fx.TEMPLATES), ("graph26", fx.GRAPH26), ("shipped", fx.SHIPPED)):
            with self.subTest(graph=label):
                wf = json.loads((path / "workflow.json").read_text())
                policy = json.loads((path / "POLICY.json").read_text())
                values = {g: {n: node_def_fp(d) for n, d in data["nodes"].items()}
                          for g, data in wf["graphs"].items()}
                digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
                self.assertEqual(golden["node_defs"][label], digest)
                self.assertEqual(golden["journeys"][label], branching.journey_fps(wf, policy=policy))

    def test_a_package_without_merge_sync_is_paused_by_the_policy(self):
        import shutil
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            w = fx.World(tmp, clones=("a",))
            policy = fx.load_template("POLICY.json")
            policy["settings"]["engine"] = {"requires": ["merge_sync"]}
            w.bootstrap(policy=policy)
            copied = Path(tmp, "old-engine")
            shutil.copytree(fx.PLUGIN_CODE.parent, copied,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            Path(copied, "zzzops/engine/capabilities/merge_sync.txt").unlink(missing_ok=True)
            command = [sys.executable, str(copied / "zzzops/zzzops.py"), "next"]
            p = subprocess.run(command, cwd=w.clones["a"].path, env=w.cli_env(),
                               text=True, capture_output=True, check=True)
            out = json.loads(p.stdout)
            blocker = next(b for b in out["blockers"] if b["kind"] == "engine_too_old")
            self.assertIn("merge_sync", blocker["missing"])
            self.assertEqual([], out["actions"])


class SquashTests(msf.OpFixture):
    def build(self, messages=("feat: implement one", "fix: implement two"), tests=True):
        if tests:
            t = self.publish({"tests/probe.txt": "first\n"}, "test: first", timestamp=1700000100)
            self.checkpoint_record(t)
        for i, message in enumerate(messages):
            self.publish({f"src/part{i}.py": f"part = {i}\n"}, message, timestamp=1700000200 + i)
        # A tests correction after all implementation is the motivating hard case.
        if tests:
            self.publish({"tests/probe.txt": "corrected\n"}, "test: correction after code", timestamp=1700001000)
        return self.integrate()

    def test_exact_tests_then_code_tree_and_dates_with_late_test_fix(self):
        out = self.build()
        commits = self.pr_commits(out)
        self.assertEqual(2, len(commits), "integrate must collapse all work into tests and implementation")
        c1, c2 = commits
        self.assertEqual(self.base, self.git.out("rev-parse", f"{c1}^"))
        self.assertTrue(self.ident.subject(c1).startswith("test: "))
        self.assertTrue(self.ident.subject(c2).startswith("feat: "))
        self.assertEqual("tests/probe.txt", self.git.out("diff", "--name-only", self.base, c1))
        self.assertEqual("corrected", self.git.out("show", f"{c1}:tests/probe.txt"))
        self.assertEqual(self.ident.code_tree(self.snap.work[1000]), self.ident.code_tree(c2))
        times = [self.git.out("show", "-s", "--format=%at %ct", c).split() for c in commits]
        self.assertTrue(all(a == c for a, c in times), times)
        self.assertGreater(int(times[1][0]), int(times[0][0]))
        pr = self.fake.load()["prs"][str(out.output["pr"]["number"])]
        self.assertEqual(self.ident.subject(c2), pr["title"])
        before = self.snap.work[1000]
        trace_before = len([l for l in self.w.trace_lines() if l["cmd"][0:2] == ["git", "push"]])
        again = self.integrate()
        self.assertEqual(c2, again.output["pr"]["head"])
        self.assertEqual(before, self.wt.git("rev-parse", "HEAD"))
        trace_after = len([l for l in self.w.trace_lines() if l["cmd"][0:2] == ["git", "push"]])
        self.assertEqual(trace_before, trace_after, "unchanged integrate must not push")

    def test_reintegrate_after_sync_is_newer_than_the_previous_pr_head(self):
        first = self.build()
        previous = self.pr_commits(first)[-1]
        previous_time = max(map(int, self.git.out("show", "-s", "--format=%at %ct", previous).split()))
        onto = self.trunk({"trunk.txt": "later\n"})
        synced = self.run_base()
        self.apply(synced)
        self.base = onto
        again = self.integrate()
        commits = self.pr_commits(again)
        self.assertEqual(2, len(commits))
        for c in commits:
            self.assertGreater(int(self.git.out("show", "-s", "--format=%at", c)), previous_time)
        self.assertEqual(self.ident.code_tree(self.snap.work[1000]), self.ident.code_tree(commits[-1]))

    def test_release_type_revert_beats_nonrelease_and_tests_never_choose_type(self):
        out = self.build(("revert: remove broken behavior", "refactor: polish"))
        tip = self.pr_commits(out)[-1]
        self.assertTrue(self.ident.subject(tip).startswith("revert: "), self.ident.subject(tip))

    def test_breaking_footer_is_retained_in_implementation_squash(self):
        out = self.build(("fix: contract\n\nBREAKING CHANGE: users must migrate",))
        tip = self.pr_commits(out)[-1]
        body = self.git.out("show", "-s", "--format=%B", tip)
        self.assertTrue(body.startswith("fix!: "), body)
        self.assertIn("BREAKING CHANGE: users must migrate", body)

    def test_nonrelease_type_keeps_semantics_and_pr_title_changes_with_type(self):
        first = self.build(("refactor: polish",))
        self.assertTrue(self.ident.subject(self.pr_commits(first)[-1]).startswith("refactor: "))
        self.publish({"src/fix.py": "fix\n"}, "fix: defect")
        second = self.integrate()
        tip = self.pr_commits(second)[-1]
        self.assertTrue(self.ident.subject(tip).startswith("fix: "))
        pr = self.fake.load()["prs"][str(second.output["pr"]["number"])]
        self.assertEqual(self.ident.subject(tip), pr["title"])

    def test_tests_only_omits_empty_implementation_commit(self):
        out = self.build(())
        commits = self.pr_commits(out)
        self.assertEqual(1, len(commits))
        self.assertTrue(self.ident.subject(commits[0]).startswith("test: "))

    def test_implementation_only_omits_empty_tests_commit(self):
        out = self.build(tests=False)
        commits = self.pr_commits(out)
        self.assertEqual(1, len(commits))
        self.assertTrue(self.ident.subject(commits[0]).startswith("feat: "))

    def test_no_code_still_asks_the_human(self):
        out = self.integrate()
        self.assertIsInstance(out, Blocked)
        self.assertEqual("no code commits", out.blocked["reason"])


if __name__ == "__main__":
    unittest.main()
