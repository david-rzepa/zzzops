"""Cost-output adoption intentionally stales delivery; review-only migration stays separate."""
from __future__ import annotations

import copy
import unittest

import engine_fixtures
from engine_sim import Sim
from engine.schemas import build_graph


class CostAdoptionTests(unittest.TestCase):
    def test_adding_required_cost_output_stales_writer_and_preserves_prior_evidence(self):
        sim = Sim()
        sim.goal(1)
        self.assertTrue(sim.drive(1, until="review_impl"))
        previous = copy.deepcopy(sim.docs[1]["records"]["test_design"])
        workflow = copy.deepcopy(sim.workflow)
        nodes = workflow["graphs"]["default"]["nodes"]
        nodes["test_design"]["outputs"]["cost"] = "object"
        for node in ("review_tests", "review_impl"):
            nodes[node]["inputs"]["cost"] = {"from": "test_design.cost", "context": True}
        sim.workflow = workflow
        sim.graphs = {name: build_graph(name, graph) for name, graph in workflow["graphs"].items()}
        state = sim.st(1)
        self.assertEqual(("ready", "stale"), (state["test_design"]["name"], state["test_design"]["reason"]))
        self.assertIn("def", state["test_design"]["stale_because"])
        self.assertEqual("blocked", state["implement"]["name"])
        self.assertEqual("blocked", state["review_tests"]["name"])
        self.assertEqual(previous, sim.docs[1]["records"]["test_design"], "adoption preserves historical evidence")
        sim.step(1, "test_design")
        self.assertIn("cost", sim.docs[1]["records"]["test_design"]["output"])


if __name__ == "__main__":
    unittest.main()
