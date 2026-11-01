"""Step 2: the suggested checkpoint (SPEC §4.20; REV6 H3, H23, H26, H30), with a dict-backed GitView."""

from __future__ import annotations

import unittest

import engine_fixtures as fx
from engine.errors import Refused
from engine.records import GitView, suggested_checkpoint
from engine.schemas import build_graph


class Chain(GitView):
    """A linear history: commits listed oldest first; review commits named 'rv*'."""

    def __init__(self, *commits):
        self.order = list(commits)

    def is_ancestor(self, a, b):
        return a in self.order and b in self.order and self.order.index(a) <= self.order.index(b)

    def committed_since(self, work, head):
        seg = self.order[self.order.index(work) + 1: self.order.index(head) + 1]
        return any(not c.startswith("rv") for c in seg)


class SuggestedCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.g = build_graph("default", fx.load_template("workflow.json")["graphs"]["default"])

    def doc(self, base_out, tests_commit="t1", tests_base="b0", impl_commit=None):
        recs = {"base": {"status": "done", "output": dict({"base_commit": "b1"}, **base_out)},
                "test_design": {"status": "done", "output": {"tests": {"commit": tests_commit, "base": tests_base}},
                                "fp_parts": {"def": "d", "inputs": {"base": "old", "doc": "x"}, "policy": {}}}}
        if impl_commit:
            recs["implement"] = {"status": "done", "output": {"code": {"commit": impl_commit, "base": tests_base}}}
        return {"records": recs, "skip": {}}

    def call(self, doc, X, k, work, head, git, base_value="b1", parts=None):
        r0 = doc["records"][X]
        parts = parts or {"def": "d", "inputs": {"base": "new", "doc": "x"}, "policy": {}}
        return suggested_checkpoint(self.g, doc, X, k, r0, work, parts, base_value, head, git)

    def test_base_move_with_replay_map(self):
        git = Chain("b1", "t1'", "i1'")
        d = self.doc({"replay_map": {"t1": "t1'"}, "replay_pos": {}})
        self.assertEqual("t1'", self.call(d, "test_design", "tests", "i1'", "i1'x", Chain("b1", "t1'", "i1'", "i1'x")))

    def test_base_move_with_only_replay_pos(self):
        d = self.doc({"replay_map": {}, "replay_pos": {"t1": "t1h"}})
        git = Chain("b1", "t1h", "i1h", "new")
        self.assertEqual("t1h", self.call(d, "test_design", "tests", "i1h", "new", git))

    def test_containment_failure_defaults_to_head(self):
        d = self.doc({"replay_map": {"i1": "i1'"}}, impl_commit="i1")
        d["records"]["implement"]["fp_parts"] = {"def": "d", "inputs": {"base": "old"}, "policy": {}}
        d["records"]["test_design"]["output"]["tests"]["commit"] = "t2"           # tests fixed after the restack
        git = Chain("b1", "i1'", "t2", "w")
        r = suggested_checkpoint(self.g, d, "implement", "code", d["records"]["implement"], "i1'",
                                 {"def": "d", "inputs": {"base": "new"}, "policy": {}}, "b1", "w", git)
        self.assertIsNone(r)

    def test_no_commit_phase_keeps_previous_checkpoint(self):
        # H26: a dispute after implement committed; base unchanged
        d = self.doc({}, tests_base="b1")
        git = Chain("b1", "t1", "i1", "rv1")
        parts = {"def": "d", "inputs": {"base": "old", "doc": "x"}, "policy": {}}
        self.assertEqual("t1", self.call(d, "test_design", "tests", "i1", "rv1", git, parts=parts))

    def test_no_commit_phase_after_base_move_maps_or_refuses(self):
        d = self.doc({"replay_map": {"t1": "t1'"}})
        git = Chain("b1", "t1'", "i1'")
        self.assertEqual("t1'", self.call(d, "test_design", "tests", "i1'", "i1'", git))
        d = self.doc({"replay_map": {}, "replay_pos": {}})
        with self.assertRaises(Refused) as e:
            self.call(d, "test_design", "tests", "i1'", "i1'", git)
        self.assertEqual("checkpoint_required", e.exception.code)
        self.assertIn("base commit", e.exception.hint)

    def test_committed_phase_not_stale_on_base_defaults_to_head(self):
        d = self.doc({"replay_map": {"t1": "t1'"}})
        git = Chain("b1", "t1", "t2")
        parts = {"def": "d", "inputs": {"base": "old", "doc": "y"}, "policy": {}}
        self.assertIsNone(self.call(d, "test_design", "tests", "t1", "t2", git, base_value="b0", parts=parts))

    def test_computed_from_lease_parts_not_the_card(self):
        # H30: the same answer whatever the card said; only record vs lease parts matter
        d = self.doc({"replay_map": {"t1": "t1'"}})
        git = Chain("b1", "t1'", "t2")
        self.assertEqual("t1'", self.call(d, "test_design", "tests", "t1'", "t2", git))


if __name__ == "__main__":
    unittest.main()
