"""Step 2: fingerprints and the two-pass frontier (SPEC §4.8, §4.9), on the default and the renamed graph."""

from __future__ import annotations

import ast
import unittest

import engine_fixtures as fx
from engine_sim import Sim
from engine import frontier
from engine.fingerprint import fp, fp_parts, input_fp, node_def_fp, stale_keys


class Base(unittest.TestCase):
    renamed = False

    def setUp(self):
        wf = fx.renamed_workflow() if self.renamed else None
        self.s = Sim(workflow=wf)
        self.m = fx.RENAME if self.renamed else {n: n for n in fx.DEFAULT_NODES}

    def n(self, name):
        return self.m[name]

    def name(self, g, node):
        return self.s.st(g, self.n(node))["name"]

    def state(self, g, node):
        return self.s.st(g, self.n(node))

    def to(self, g, node):
        """Drive goal g until `node` is ready or needs a human (and nothing before it is)."""
        s = self.s
        for _ in range(60):
            st = s.st(g, self.n(node))
            if st["name"] in ("ready", "needs_human"):
                return st
            acts = [a for a in s.actionable(g) if a != self.n(node)]
            if not acts:
                raise AssertionError(s.names(g))
            s.step(g, acts[0])
        raise AssertionError("did not reach " + node)


class FrontierTests(Base):
    def test_new_goal_offers_only_design(self):
        self.s.goal(1)
        ready = [n for n, x in self.s.st(1).items() if x["name"] == "ready"]
        self.assertEqual([self.n("design")], ready)
        self.assertEqual("blocked", self.name(1, "review_design"))

    def test_happy_path_reaches_every_terminal(self):
        self.s.goal(1)
        self.assertTrue(self.s.drive(1, until=self.n("merge")))
        self.assertTrue(all(x["name"] == "current" for x in self.s.st(1).values()))

    def test_changes_requested_reopens_target_with_no_extra_phase(self):
        s = self.s
        s.goal(1)
        self.to(1, "review_impl")
        s.start(1, self.n("review_impl"))
        s.submit(1, self.n("review_impl"), findings=[{"text": "null check missing"}])
        st = self.state(1, "implement")
        self.assertEqual(("ready", "reopened"), (st["name"], st["reason"]))
        self.assertEqual(["review_impl:%s" % "x"][:0], [])
        self.assertEqual(1, len(st["corrections"]))
        self.assertEqual(self.n("review_impl") + ":1:1", st["corrections"][0]["id"])
        # the reviewer itself is blocked on its own live finding, not ready
        rv = self.state(1, "review_impl")
        self.assertEqual("blocked", rv["name"])
        # implement fixes it; the reviewer re-runs and resolves
        s.step(1, self.n("implement"))
        s.step(1, self.n("run_tests"))
        rv = self.state(1, "review_impl")
        self.assertEqual(("ready", "stale"), (rv["name"], rv["reason"]))
        s.step(1, self.n("review_impl"))
        self.assertEqual("current", self.name(1, "review_impl"))

    def test_dispute_reaches_reviewer_then_escalates_on_second_round(self):
        s = self.s
        s.goal(1)
        self.to(1, "review_impl")
        rid = self.n("review_impl")
        s.start(1, rid)
        s.submit(1, rid, findings=[{"text": "rename x"}])
        fid = f"{rid}:1:1"
        s.start(1, self.n("implement"))
        s.submit(1, self.n("implement"), responses={fid: "disputed: x is the domain term"}, same=True)
        # the dispute answers the finding (target_fp no longer matches): the reviewer is ready (not_ok)
        rv = self.state(1, "review_impl")
        self.assertEqual(("ready", "not_ok"), (rv["name"], rv["reason"]))
        self.assertEqual("current", self.name(1, "implement"))
        # the reviewer keeps it open: round 2 -> a human dispute item
        s.start(1, rid)
        s.submit(1, rid, findings=[{"id": fid, "status": "open"}], decision="changes_requested")
        st = self.state(1, "implement")
        self.assertEqual(("needs_human", "dispute"), (st["name"], st["kind"]))
        self.assertEqual(2, st["escalated"][0][1]["rounds"])

    def test_new_finding_starts_at_round_one_and_human_findings_never_escalate(self):
        s = self.s
        s.goal(1)
        self.to(1, "approve_design")
        s.answer(1, self.n("approve_design"), decision="changes_requested", quote="simpler please")
        st = self.state(1, "design")
        self.assertEqual(("ready", "reopened"), (st["name"], st["reason"]))
        self.assertEqual(1, st["corrections"][0]["rounds"])

    def test_human_rejection_reopens_the_subject(self):
        s = self.s
        s.goal(1)
        self.to(1, "approve_merge")
        s.answer(1, self.n("approve_merge"), decision="changes_requested", quote="handle the empty case")
        st = self.state(1, "implement")
        self.assertEqual("reopened", st["reason"])

    def test_stale_review_findings_stay_live_while_the_target_is_unchanged(self):
        # G1028 §3.1 (replaces "stale review findings are not live"): the finding is carried
        s = self.s
        s.goal(1)
        self.to(1, "review_design")
        rid = self.n("review_design")
        s.start(1, rid)
        s.submit(1, rid, findings=[{"text": "missing risks"}])
        # the spec changes: the review is stale, but design's output is unchanged, so its finding stays live
        s.docs[1]["spec"] = "a different spec"
        self.assertEqual(("ready", "stale"), (self.state(1, "design")["name"], self.state(1, "design")["reason"]))
        self.assertEqual([rid + ":1:1"], [f["id"] for f in self.state(1, "design")["corrections"]])

    def test_finding_submitted_while_subject_running_keeps_target_fp(self):
        # H1: a running state's fp is computed from recorded values
        s = self.s
        s.goal(1)
        self.to(1, "review_impl")
        rid = self.n("review_impl")
        s.start(1, rid)
        self.assertEqual("running", self.name(1, "review_impl"))
        self.assertIsNotNone(self.state(1, "review_impl")["fp"])
        rec = s.submit(1, rid, findings=[{"text": "bug"}])
        self.assertIsNotNone(rec["findings"][0]["target_fp"])
        self.assertEqual(s.docs[1]["records"][self.n("implement")]["attempt"], rec["findings"][0]["target_attempt"])

    def test_reopen_of_a_stale_node_is_not_dropped(self):
        s = self.s
        s.goal(1)
        self.to(1, "review_tests")
        s.reopen(1, self.n("design"), "rethink")
        s.docs[1]["spec"] = "changed"
        st = self.state(1, "design")
        self.assertEqual("ready", st["name"])
        self.assertEqual([self.n("design") + ":reopen:1"], [f["id"] for f in st["corrections"]])

    def test_op_target_finding_dies_on_a_later_attempt_with_identical_output(self):
        # H22/H24: answered by re-running, no clock comparison
        s = self.s
        s.goal(1)
        self.to(1, "merge")
        mid = self.n("merge")
        s.op(1, mid, ok=False, raised=[{"key": "conflict", "input": "pr", "text": "conflicts with dev"}])
        st = self.state(1, "integrate")
        self.assertEqual(("ready", "reopened"), (st["name"], st["reason"]))
        s.op(1, self.n("integrate"), same=True)                    # byte-identical rebuild
        self.assertEqual("current", self.name(1, "integrate"))
        self.assertEqual(("ready", "not_ok"), (self.state(1, "merge")["name"], self.state(1, "merge")["reason"]))

    def test_op_finding_cap_with_unchanged_inputs(self):
        s = self.s
        s.goal(1)
        self.to(1, "merge")
        mid = self.n("merge")
        for i in range(3):
            s.op(1, mid, ok=False, raised=[{"key": "conflict", "input": "pr", "text": "conflict"}])
            s.op(1, self.n("integrate"), same=True)
        st = self.state(1, "merge")
        self.assertEqual(("needs_human", "crash_loop"), (st["name"], st["kind"]))
        self.assertEqual("op_finding", st["cap"])

    def test_op_finding_count_restarts_when_inputs_change(self):
        s = self.s
        s.goal(1)
        self.to(1, "merge")
        mid = self.n("merge")
        for i in range(4):
            s.op(1, mid, ok=False, raised=[{"key": "conflict", "input": "pr", "text": "conflict"}])
            s.op(1, self.n("integrate"))                            # a new PR head each time: inputs change
            self.assertNotEqual("needs_human", self.name(1, "merge"))
        self.assertEqual(1, s.docs[1]["records"][mid]["findings"][0]["repeats"])

    def test_repeat_cap_ignores_wording_and_skips_dependency_waits(self):
        s = self.s
        s.goal(1)
        self.to(1, "test_design")
        tid = self.n("test_design")
        for reason in ("a", "b", "c"):
            s.start(1, tid)
            s.blocked(1, tid, "agent", reason)
        st = self.state(1, "test_design")
        self.assertEqual(("needs_human", "crash_loop", "repeat"), (st["name"], st["kind"], st["cap"]))

    def test_deps_conflict_three_times_is_still_a_wait(self):
        s = self.s
        s.goal(1)
        self.to(1, "base")
        bid = self.n("base")
        s.start(1, bid)
        s.blocked(1, bid, "dependency", "deps_conflict", category="dependency")
        s.docs[1]["records"][bid]["blocked"]["repeats"] = 3
        self.assertEqual("waiting", self.name(1, "base"))

    def test_time_wait_then_retry(self):
        s = self.s
        s.goal(1)
        self.to(1, "integrate")
        iid = self.n("integrate")
        s.start(1, iid)
        s.blocked(1, iid, "time", "required checks pending", delay=300, category="external")
        self.assertEqual("waiting", self.name(1, "integrate"))
        s.tick(301)
        st = self.state(1, "integrate")
        self.assertEqual(("ready", "retry"), (st["name"], st["reason"]))

    def test_lease_crash_loop_cap_counts_abandons(self):
        s = self.s
        s.goal(1)
        did = self.n("design")
        for _ in range(3):
            s.start(1, did)
            s.abandon(1, did)
        st = self.state(1, "design")
        self.assertEqual(("needs_human", "crash_loop", "lease"), (st["name"], st["kind"], st["cap"]))

    def test_live_lease_renders_running_and_expired_is_reclaimable(self):
        s = self.s
        s.goal(1)
        s.start(1, self.n("design"))
        self.assertEqual("running", self.name(1, "design"))
        s.tick(121 * 60)
        self.assertEqual("reclaimable", self.name(1, "design"))

    def test_skip_and_optional_inputs(self):
        s = self.s
        s.goal(1, skip={self.n("approve_design"): "docs only"})
        self.to(1, "base")
        self.assertEqual("skipped", self.name(1, "approve_design"))

    def test_release_gate(self):
        s = self.s
        s.goal(1, release=2)
        s.drive(1)
        st = self.state(1, "merge")
        self.assertEqual(("waiting", "release 2"), (st["name"], st["until"]))

    def test_policy_and_def_staleness(self):
        s = self.s
        s.goal(1)
        s.drive(1, until=self.n("merge"))
        s.settings["verification"]["commands"] = ["make lint"]
        st = self.state(1, "run_tests")
        self.assertEqual(["policy.verification.commands"], st["stale_because"])
        # an undeclared setting stales nothing
        s.settings["verification"]["commands"] = ["make test"]
        s.settings["parallelism"]["max_workers"] = 3
        s.settings["verification"]["commands"] = s.settings["verification"]["commands"]
        s.graphs[s.docs[1]["graph"]].nodes[self.n("design")]["description"] = "changed text"
        self.assertEqual("ready", self.name(1, "run_tests"))   # still stale on the commands change
        self.assertEqual("current", self.name(1, "design"))

    def test_context_edge_change_stales_nothing(self):
        s = self.s
        s.goal(1)
        s.drive(1, until=self.n("merge"))
        nd = s.graphs["default"].nodes[self.n("implement")]
        nd["inputs"].pop("tests_review")
        from engine.schemas import build_graph
        s.graphs["default"] = build_graph("default", {"nodes": s.graphs["default"].nodes,
                                                      "terminal": s.graphs["default"].terminal})
        self.assertTrue(all(x["name"] == "current" for x in s.st(1).values()), s.names(1))


class RenamedFrontierTests(FrontierTests):
    renamed = True


class FingerprintTests(unittest.TestCase):
    def test_checkpoint_and_artifact_identities(self):
        cp = {"commit": "c" * 40, "base": "b" * 40, "tree": "t" * 40, "change": "d" * 40}
        self.assertEqual("v1:change:" + "d" * 40, fp(cp, "checkpoint"))
        self.assertEqual("v1:blob:" + "e" * 40, fp({"path": "p", "blob": "e" * 40, "commit": "c" * 40}, "artifact"))
        self.assertTrue(fp("x", "text").startswith("v1:sha256:"))

    def test_def_fp_ignores_context_edges_and_prose(self):
        nd = fx.load_template("workflow.json")["graphs"]["default"]["nodes"]["implement"]
        a = node_def_fp(nd)
        nd2 = dict(nd, description="other", capability="routine", timeout=30, instructions=[], prompt="x.md")
        nd2["inputs"] = {k: v for k, v in nd["inputs"].items() if not v.get("context")}
        self.assertEqual(a, node_def_fp(nd2))
        self.assertNotEqual(a, node_def_fp(dict(nd, rev=1)))

    def test_stale_keys(self):
        old = {"def": "a", "inputs": {"x": "1", "y": "2"}, "policy": {"p": 1}, "subject": "s"}
        new = {"def": "b", "inputs": {"x": "1", "y": "3", "z": "4"}, "policy": {"p": 2}, "subject": "s"}
        self.assertEqual(["def", "inputs.y", "inputs.z", "policy.p"], stale_keys(old, new))

    def test_frontier_module_is_pure(self):
        src = (fx.PLUGIN_CODE / "engine" / "frontier.py").read_text()
        imported = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & {"subprocess", "os", "time", "datetime", "random", "socket"}, imported)


if __name__ == "__main__":
    unittest.main()
