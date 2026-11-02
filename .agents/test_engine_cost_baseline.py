"""G1043 bounded informational baseline selection, without portfolio journeys.

Internal test seams: engine.test_cost.select_baseline(candidates, history,
 target=..., current=..., code_tree=..., clock=...) and
 supervise_lookup(argv, popen=..., kill_group=..., clock=...). Candidates carry
 accepted goal metadata, its decoded document and configured Graph. These small
 seams keep selection, budgets and subprocess supervision independently testable.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import subprocess
import unittest
from unittest import mock

import engine_fixtures as fx
import test_engine_schemas as schema_fixtures
from engine.schemas import build_graph


def sha(value):
    return hashlib.sha1(str(value).encode()).hexdigest()


def measured(total=1000, verification=800, plan="a" * 64, cpus=20, verification_plan="c" * 64):
    return {"total_ms": total, "goal_ms": 200, "verification_ms": verification,
            "parallel_commands": True, "cpu_budget": 4, "workers": {"goal": 2, "verification": 2},
            "plan_sha256": plan, "verification_plan_sha256": verification_plan, "environment": {"platform": "linux", "python": "3.10", "cpus": cpus}}


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.current = measured(1500, 1100)
        self.target = {"branch": "release/1", "tip": sha("captured-tip")}
        mapping = {"run_tests": "verify", "integrate": "publish", "merge": "land"}
        wf = fx.renamed_workflow(mapping=mapping)
        self.graph = build_graph("custom", wf["graphs"]["default"])
        self.lookups = []

    def api(self):
        try:
            module = importlib.import_module("engine.test_cost")
        except ImportError:
            self.fail("test_cost baseline helper is required for bounded selection tests")
        self.assertTrue(callable(getattr(module, "select_baseline", None)))
        return module.select_baseline

    def candidate(self, gid=1001, merge=None, timing="default", target=None, finished="2026-11-02T10:00:00Z"):
        merge = merge or sha(f"merge-{gid}")
        doc = schema_fixtures.default_goal(id=gid, graph="custom", state="closed",
                    closed={"reason": "done", "note": "merged", "by": "reviewer", "at": finished})
        result = {"passed": True, "tree": sha(f"tree-{gid}"), "details": []}
        if timing == "default":
            result["timing"] = measured()
        elif timing is not None:
            result["timing"] = timing
        doc["records"] = {
            "verify": schema_fixtures.record(finished_at=finished, output={"result": result}),
            "publish": schema_fixtures.record(output={"pr": {"number": gid, "head": sha(f"head-{gid}"),
                "base": target or self.target["branch"], "tree": result["tree"]}, "ci": {}}),
            "land": schema_fixtures.record(output={"merge_commit": merge, "merged_at": finished}),
        }
        return {"goal": gid, "goal_commit": sha(f"goal-{gid}"), "document": doc, "graph": self.graph}

    def select(self, candidates, history=None, trees=None, clock=lambda: 0.0):
        history = history if history is not None else [self.target["tip"],
                    *[c["document"]["records"]["land"]["output"]["merge_commit"] for c in candidates]]
        trees = trees if trees is not None else {
            c["document"]["records"]["land"]["output"]["merge_commit"]:
            c["document"]["records"]["verify"]["output"]["result"]["tree"] for c in candidates}
        def code_tree(commit):
            self.lookups.append(commit)
            value = trees[commit]
            if isinstance(value, Exception):
                raise value
            return value
        before = [copy.deepcopy(c["document"]) for c in candidates]
        result = self.api()(candidates, history, target=self.target, current=self.current,
                            code_tree=code_tree, clock=clock)
        self.assertEqual(before, [c["document"] for c in candidates], "timing lookup must not mutate historical goals")
        return result

    def unavailable(self, value, reason=None, limit=None):
        self.assertEqual("unavailable", value["status"])
        if reason:
            self.assertEqual(reason, value["reason"])
        if limit:
            self.assertEqual(limit, value["limit"])
        self.assertNotIn("delta_ms", value, "unavailable evidence has no invented zero/delta")

    def test_exact_landed_tree_on_captured_target_gives_qualified_provenance_and_signed_delta(self):
        c = self.candidate()
        value = self.select([c])
        self.assertEqual("available", value["status"])
        self.assertEqual(1001, value["goal"])
        self.assertEqual("verify", value["node"], "configured op kind, not run_tests, finds the producer")
        for provenance in (c["goal_commit"], sha("merge-1001"), sha("tree-1001"), "release/1"):
            self.assertIn(provenance, value.values())
        self.assertEqual(1000, value["total_ms"])
        self.assertEqual(800, value["verification_ms"])
        self.assertEqual(500, value["delta_ms"])
        self.assertEqual(300, value["verification_delta_ms"])
        self.assertEqual("available", value["verification"]["status"])
        self.assertEqual(300, value["verification"]["delta_ms"])
        self.assertEqual(1, len(self.lookups), "both scopes reuse the same source-tree comparison")
        self.current = measured(500, 300)
        self.assertEqual(-500, self.select([c])["delta_ms"])
        self.assertEqual(-500, self.select([c])["verification_delta_ms"])

    def test_nearest_merge_wins_and_latest_success_at_same_merge_breaks_ties(self):
        old = self.candidate(1001, timing=measured(9999, 9999))
        merge = sha("newest-merge")
        new = self.candidate(1002, merge=merge, timing=measured(1200, 900))
        later = self.candidate(1003, merge=merge, timing=measured(1300, 950), finished="2026-11-02T11:00:00Z")
        # Both attest the same tested tree at the same merge.
        later["document"]["records"]["verify"]["output"]["result"]["tree"] = sha("tree-1002")
        later["document"]["records"]["publish"]["output"]["pr"]["tree"] = sha("tree-1002")
        value = self.select([old, new, later], history=[self.target["tip"], merge, sha("merge-1001")],
                            trees={merge: sha("tree-1002"), sha("merge-1001"): sha("tree-1001")})
        self.assertEqual(1003, value["goal"])
        self.assertEqual(1300, value["total_ms"])

    def test_newest_incompatible_evidence_never_falls_back_to_an_older_match(self):
        for timing, reason in ((measured(plan="b" * 64), "changed_commands_or_allocation"),
                               (measured(cpus=4), "changed_environment"), (None, "legacy_timing")):
            with self.subTest(reason=reason):
                old, new = self.candidate(1001), self.candidate(1002, timing=timing)
                out = self.select([old, new], history=[self.target["tip"], sha("merge-1002"), sha("merge-1001")])
                self.unavailable(out, reason)

    def test_different_goal_plan_keeps_repository_delta_from_the_same_newest_source(self):
        old = self.candidate(1001)
        newer = self.candidate(1002, timing=measured(2000, 900, plan="b" * 64))
        out = self.select([old, newer], history=[self.target["tip"], sha("merge-1002"), sha("merge-1001")])
        self.unavailable(out, "changed_commands_or_allocation")
        self.assertNotIn("verification_delta_ms", out)
        verification = out["verification"]
        self.assertEqual("available", verification["status"])
        self.assertEqual(900, verification["verification_ms"])
        self.assertEqual(200, verification["delta_ms"])
        self.assertEqual("c" * 64, verification["verification_plan_sha256"])
        self.assertEqual({"goal": 1002, "node": "verify", "goal_commit": newer["goal_commit"],
                          "merge_commit": sha("merge-1002"), "tree": sha("tree-1002"), "target": "release/1",
                          "finished_at": "2026-11-02T10:00:00Z"}, verification["source"])
        caveat = verification["caveat"].lower()
        for term in ("informational", "load", "concurrent"):
            self.assertIn(term, caveat)

    def test_newest_repository_mismatch_never_falls_back_to_an_older_matching_source(self):
        old = self.candidate(1001)
        newer = self.candidate(1002, timing=measured(plan="b" * 64, verification_plan="d" * 64))
        out = self.select([old, newer], history=[self.target["tip"], sha("merge-1002"), sha("merge-1001")])
        self.unavailable(out, "changed_commands_or_allocation")
        self.unavailable(out["verification"], "changed_commands_or_allocation")
        if "source" in out["verification"]:
            self.assertEqual(1002, out["verification"]["source"]["goal"])

    def test_missing_hash_metadata_qualifies_each_scope_independently(self):
        narrow_missing = measured()
        narrow_missing.pop("verification_plan_sha256")
        out = self.select([self.candidate(timing=narrow_missing)])
        self.assertEqual("available", out["status"])
        self.assertEqual(500, out["delta_ms"])
        self.assertEqual(800, out["verification_ms"])
        self.assertNotIn("verification_delta_ms", out, "flat verification delta only mirrors available narrow evidence")
        self.unavailable(out["verification"], "legacy_timing")
        whole_missing = measured()
        whole_missing.pop("plan_sha256")
        out = self.select([self.candidate(timing=whole_missing)])
        self.unavailable(out, "legacy_timing")
        self.assertEqual("available", out["verification"]["status"])
        self.assertEqual(300, out["verification"]["delta_ms"])
        self.assertNotIn("verification_delta_ms", out)

    def test_environment_and_incomplete_lookup_make_both_scopes_unavailable(self):
        c = self.candidate(timing=measured(cpus=4))
        out = self.select([c])
        self.unavailable(out, "changed_environment")
        self.unavailable(out["verification"], "changed_environment")
        for reason_case in ("no source", "document cap", "history cap", "deadline"):
            with self.subTest(case=reason_case):
                if reason_case == "no source":
                    value = self.select([], history=[self.target["tip"]])
                    reason, limit = "no_prior_run", None
                elif reason_case == "document cap":
                    value = self.select([self.candidate(1000+i) for i in range(65)])
                    reason, limit = "lookup_budget_exhausted", "documents"
                elif reason_case == "history cap":
                    value = self.select([self.candidate()], history=[sha(f"history-{i}") for i in range(257)])
                    reason, limit = "lookup_budget_exhausted", "history"
                else:
                    ticks = iter((0.0, 0.0, 2.1))
                    value = self.select([self.candidate()], clock=lambda: next(ticks, 2.1))
                    reason, limit = "lookup_budget_exhausted", "deadline"
                self.unavailable(value, reason, limit)
                self.unavailable(value["verification"], reason, limit)

    def test_failed_unmerged_wrong_target_second_parent_and_mismatched_tree_are_not_baselines(self):
        for case in ("failed record", "failed result", "failed merge", "unmerged", "wrong target", "second parent", "actual tree mismatch"):
            with self.subTest(case=case):
                c = self.candidate()
                history = [self.target["tip"], sha("merge-1001")]
                trees = None
                if case == "failed record":
                    c["document"]["records"]["verify"]["ok"] = False
                elif case == "failed result":
                    c["document"]["records"]["verify"]["output"]["result"]["passed"] = False
                elif case == "failed merge":
                    c["document"]["records"]["land"]["ok"] = False
                elif case == "unmerged":
                    c["document"]["records"].pop("land")
                elif case == "wrong target":
                    c["document"]["records"]["publish"]["output"]["pr"]["base"] = "dev"
                elif case == "second parent":
                    history = [self.target["tip"], sha("first-parent-only")]
                else:
                    trees = {sha("merge-1001"): sha("different actual tree")}
                # Default helpers need the merge metadata even for a document
                # without a completed land record; supply history/tree explicitly.
                out = self.select([c], history=history, trees=trees or {sha("merge-1001"): sha("tree-1001")})
                self.unavailable(out)

    def test_missing_history_and_invalid_or_newer_evidence_are_truthfully_unavailable(self):
        for case in ("missing object", "newer schema", "malformed document"):
            with self.subTest(case=case):
                c = self.candidate()
                trees = {sha("merge-1001"): sha("tree-1001")}
                if case == "missing object":
                    trees[sha("merge-1001")] = RuntimeError("object unavailable")
                elif case == "newer schema":
                    c["document"]["schema"] = 999
                else:
                    c["document"]["records"]["verify"]["output"]["result"] = "not an object"
                out = self.select([c], history=[self.target["tip"], sha("merge-1001")], trees=trees)
                self.unavailable(out)
                self.assertIn(out["reason"], ("missing_history", "invalid_evidence"))

    def test_zero_baseline_gives_absolute_delta_without_percentage(self):
        out = self.select([self.candidate(timing=measured(0, 0))])
        self.assertEqual("available", out["status"])
        self.assertEqual(1500, out["delta_ms"])
        self.assertEqual(1100, out["verification_delta_ms"])
        self.assertEqual(1100, out["verification"]["delta_ms"])
        self.assertFalse(any("percent" in k for k in out))

    def test_release_and_hotfix_targets_are_never_reinterpreted_as_dev(self):
        for target in ("release/1", "hotfix/repair"):
            with self.subTest(target=target):
                self.target["branch"] = target
                out = self.select([self.candidate(target=target)])
                self.assertEqual("available", out["status"])
                self.assertIn(target, out.values())

    def test_document_history_and_tree_work_caps_return_no_partial_baseline(self):
        out = self.select([self.candidate(1000 + i) for i in range(65)])
        self.unavailable(out, "lookup_budget_exhausted", "documents")
        self.assertEqual([], self.lookups, "oversized accepted document sets should short-circuit")
        c = self.candidate()
        history = [sha(f"history-{i}") for i in range(256)] + [sha("merge-1001")]
        self.unavailable(self.select([c], history=history), "lookup_budget_exhausted", "history")
        candidates = [self.candidate(2000 + i) for i in range(17)]
        trees = {sha(f"merge-{2000+i}"): sha("mismatch") for i in range(16)}
        trees[sha("merge-2016")] = sha("tree-2016")
        self.lookups.clear()
        out = self.select(candidates, history=[sha(f"merge-{2000+i}") for i in range(17)], trees=trees)
        self.unavailable(out, "lookup_budget_exhausted", "trees")
        self.assertLessEqual(len(self.lookups), 16)
        self.unavailable(out["verification"], "lookup_budget_exhausted", "trees")

    def test_fake_clock_deadline_is_checked_before_additional_git_work(self):
        ticks = iter((0.0, 0.0, 2.1, 2.1, 2.1))
        out = self.select([self.candidate()], clock=lambda: next(ticks, 2.1))
        self.unavailable(out, "lookup_budget_exhausted", "deadline")


class LookupSupervisionTests(unittest.TestCase):
    def api(self):
        try:
            module = importlib.import_module("engine.test_cost")
        except ImportError:
            self.fail("test_cost supervisor is required to bound blocked Git reads")
        value = getattr(module, "supervise_lookup", None)
        self.assertTrue(callable(value))
        return value

    def test_blocked_lookup_is_killed_joined_and_reported_with_bounded_timeouts(self):
        events = []
        proc = mock.Mock(pid=1234)
        def communicate(timeout, input=None):
            events.append(("communicate", timeout))
            if ("kill", None) in events:
                self.assertIsNone(input, "cleanup must not resend lookup input")
            if len(events) == 1:
                raise subprocess.TimeoutExpired("lookup", timeout)
            return b"", b""
        proc.communicate.side_effect = communicate
        proc.wait.return_value = -9
        def kill(value):
            self.assertIs(proc, value)
            events.append(("kill", None))
        launch = mock.Mock(return_value=proc)
        out = self.api()(["python", "readonly-lookup"], popen=launch, kill_group=kill, clock=lambda: 0.0)
        self.assertEqual(("unavailable", "lookup_budget_exhausted", "deadline"),
                         (out["status"], out["reason"], out["limit"]))
        self.assertEqual(("unavailable", "lookup_budget_exhausted", "deadline"),
                         (out["verification"]["status"], out["verification"]["reason"], out["verification"]["limit"]))
        self.assertLessEqual(events[0][1], 2.0)
        self.assertIn(("kill", None), events)
        for kind, timeout in events[events.index(("kill", None)) + 1:]:
            if kind == "communicate":
                self.assertLessEqual(timeout, 1.0)
        self.assertTrue(proc.communicate.call_count > 1 or proc.wait.called)
        if proc.wait.called:
            timeout = proc.wait.call_args.kwargs.get("timeout", proc.wait.call_args.args[0] if proc.wait.call_args.args else None)
            self.assertIsNotNone(timeout, "lookup cleanup wait must itself be bounded")
            self.assertLessEqual(timeout, 1.0)
        kwargs = launch.call_args.kwargs
        self.assertTrue(kwargs.get("start_new_session") or kwargs.get("creationflags"), "lookup owns its process group")

    def test_lookup_failure_is_unavailable_evidence_and_not_a_test_failure(self):
        proc = mock.Mock()
        proc.communicate.return_value = (b"broken json", b"failed")
        proc.returncode = 1
        out = self.api()(["python", "readonly-lookup"], popen=lambda *a, **k: proc,
                         kill_group=lambda p: None, clock=lambda: 0.0)
        self.assertEqual("unavailable", out["status"])
        self.assertIn(out["reason"], ("invalid_evidence", "missing_history"))
        self.assertNotIn("passed", out, "baseline lookup cannot change a command outcome")
        self.assertEqual("unavailable", out["verification"]["status"])


if __name__ == "__main__":
    unittest.main()
