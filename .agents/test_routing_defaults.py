"""Regression contracts for the shipped capability-routing defaults."""

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "plugins" / "zzzops" / "zzzops" / "policy.py"
PLAN_PATH = ROOT / "plugins" / "zzzops" / "zzzops" / "templates" / "project-goals" / "INIT_PLAN.json"
SPEC = importlib.util.spec_from_file_location("routing_defaults_policy_subject", POLICY_PATH)
policy = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(policy)


class RoutingDefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        cls.settings = next(
            section["settings"] for section in plan["policy"]["sections"]
            if section["id"] == "model_routing"
        )

    def tier(self, **dimensions):
        return policy.capability_tier(self.settings, dimensions)["tier"]

    def test_architectural_test_design_escalates_before_phase_floor(self):
        self.assertEqual(
            "architectural",
            self.tier(
                phase_type="test_design", consequence="architectural",
                boundedness="atomic", engineering_rigor="structured",
            ),
        )

    def test_unbounded_work_escalates_before_phase_defaults(self):
        self.assertEqual(
            "architectural",
            self.tier(
                phase_type="understand", consequence="bounded",
                boundedness="unbounded", engineering_rigor="structured",
            ),
        )

    def test_ordinary_test_design_has_reasoning_floor_and_understanding_stays_routine(self):
        ordinary = {
            "consequence": "bounded", "boundedness": "atomic",
            "engineering_rigor": "structured",
        }
        self.assertEqual("reasoning", self.tier(phase_type="test_design", **ordinary))
        self.assertEqual("routine", self.tier(phase_type="understand", **ordinary))


if __name__ == "__main__":
    unittest.main()
