"""G1051 release identity contracts against the production engine.

These tests deliberately use existing entry points: goal validation, request-key
creation, line membership, branch naming and scheduler ordering.  They avoid
inventing the proposed insertion CLI or storage/activation interfaces.
"""
from __future__ import annotations

import copy
import json
import unittest

import engine_fixtures as fx
from engine import frontier, lines, lineverbs, schemas
from test_engine_branching import BSim, BRANCHING, Branching, release_workflow


class IdentityTests(unittest.TestCase):
    def goal(self, release):
        s = BSim()
        return s.goal(1001, release=release)

    def test_legacy_integers_and_dotted_targets_validate(self):
        for value in (1, 2, "2", "2.0", "2.1", "2.10", "2.0.0.1", "2.0.0.0.0.0.1"):
            with self.subTest(release=value):
                doc = self.goal(value)
                errors, _ = schemas.validate_goal(doc, None, {1001: doc}, release_workflow())
                self.assertFalse(errors, list(errors))

    def test_invalid_identifiers_and_json_floats_are_rejected(self):
        for value in (True, False, 0, -1, 2.1, float('nan'), "", "0", "-2", ".2", "2.",
                      "2..1", "2.-1", "2.1-rc1", "2.1+meta", "2/1", " 2.1"):
            with self.subTest(release=value):
                doc = self.goal(value)
                errors, _ = schemas.validate_goal(doc, None, {1001: doc}, release_workflow())
                self.assertTrue(errors, f"accepted invalid release {value!r}")

    def test_canonical_idempotence_key_keeps_internal_zero_and_distinguishes_ten(self):
        key = lambda label: lineverbs.line_key("release", label)
        self.assertEqual(key("2"), key("2.0"))
        self.assertEqual(key("2"), key("2.0.0"))
        self.assertEqual(key("2.01"), key("2.1.0"))
        self.assertEqual(key("2.0.1"), key("2.0.1.0"))
        self.assertNotEqual(key("2.1"), key("2.10"))
        self.assertNotEqual(key("2.1"), key("2.0.1"))

    def test_release_branch_uses_one_ref_for_aliases_and_keeps_internal_zero(self):
        branch = lambda label: lines.line_branch(BRANCHING, "release", label)
        self.assertEqual("release/2", branch("2.0"))
        self.assertEqual("release/2.1", branch("2.01.0"))
        self.assertEqual("release/2.0.0.1", branch("2.0.0.1"))
        self.assertNotEqual(branch("2.1"), branch("2.10"))

    def test_membership_uses_numeric_aliases_not_text_or_float(self):
        line = lines.Line(9000, "release", "2", "release/2", "open", None)
        ledger = {
            1001: {"release": 2, "state": "open"},
            1002: {"release": "2.0", "state": "open"},
            1003: {"release": "2.0.0", "state": "closed"},
            1004: {"release": "2.1", "state": "open"},
            1005: {"release": "2.10", "state": "open"},
        }
        self.assertEqual([1001, 1002, 1003], lines.members(ledger, line))
        self.assertEqual([1001, 1002], lines.open_members(ledger, line))

    def test_scheduler_orders_unbounded_components_numerically(self):
        s = BSim()
        labels = ["3", "2.10", "2.1", "2.0.1", "2.0.0.1", 2,
                  "2.0.0.0.0.0.1"]
        docs = [s.goal(1000+i, release=value) for i, value in enumerate(labels)]
        graph = s.graph(1000)
        ordered = sorted(docs, key=lambda doc: frontier.order_key(s.settings, doc, graph, "design"))
        self.assertEqual([2, "2.0.0.0.0.0.1", "2.0.0.1", "2.0.1", "2.1", "2.10", "3"],
                         [doc["release"] for doc in ordered])

    def test_canonical_alias_lines_are_detected_as_duplicate(self):
        ledger = {
            9001: {"release": 2, "state": "open", "line": "release:2"},
            9002: {"release": "2.0", "state": "open", "line": "release:2.0"},
        }
        settings = BSim().settings
        found = lines.duplicates(lines.lines_of(ledger, settings))
        self.assertEqual([("release/2", [9001, 9002])], found)


class GitRemoteReleaseTests(Branching):
    """Exercise the opted-in CLI against throwaway bare Git and fake GitHub only."""

    def setUp(self):
        super().setUp()
        policy = copy.deepcopy(self.w.policy)
        policy["settings"]["engine"].setdefault("requires", []).append("insertable_release_targets")
        self.w.push_dev({".zzzops/POLICY.json": json.dumps(policy, indent=2) + "\n"},
                        "chore: opt in to insertable targets")

    def test_new_dotted_goal_roundtrips_without_reassigning_later_goal(self):
        later = self.goal(release=3)
        patch = self.goal(release="2.0.0.1")
        self.assertEqual(3, self.show(later)["goal"]["release"])
        self.assertEqual("2.0.0.1", self.show(patch)["goal"]["release"])
        self.assertTrue(self.goal_tip(later))
        self.assertTrue(self.goal_tip(patch))

    def test_dotted_goal_roundtrips_via_show_and_edit_without_losing_internal_zero(self):
        patch = self.goal(release="2.0.1")
        tip = self.goal_tip(patch)
        self.w.ok("a", "edit", str(patch), "--set", 'release="2.0.1.0"', "--base", tip)
        self.assertEqual("2.0.1", self.show(patch)["goal"]["release"])


if __name__ == "__main__":
    unittest.main()
