"""A routing policy must keep older writers from interpreting a new graph."""
import copy
import unittest

import engine_fixtures as fx
from engine import schemas


class ConditionalRoutingPolicyTests(unittest.TestCase):
    def test_default_graph_rejects_policy_without_the_capability(self):
        workflow = fx.load_template('workflow.json')
        policy = copy.deepcopy(fx.load_template('POLICY.json'))
        policy['settings']['engine']['requires'].remove('conditional_review_routes')
        errors = schemas.validate_workflow(workflow, policy)
        self.assertTrue(any('conditional_review_routes' in error for error in errors), errors)
