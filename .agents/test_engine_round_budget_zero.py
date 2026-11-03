"""Zero is a valid explicit budget, including stages without agent nodes."""
import copy
import unittest

import engine_fixtures as fx
from engine import render, schemas
from engine_sim import Sim


class ZeroBudgetTests(unittest.TestCase):
    def test_only_existing_agent_stages_gate_at_zero(self):
        for stage, absent in [('delivery', 'discovery'), ('discovery', 'delivery')]:
            with self.subTest(stage=stage):
                workflow = fx.load_template('workflow.json')
                source = workflow['graphs']['default']['nodes']
                node = copy.deepcopy(source['design'])
                node.update(stage=stage, inputs={'spec': {'from': 'goal.spec'}})
                op, human = copy.deepcopy(source['base']), copy.deepcopy(source['approve_design'])
                op['inputs'] = {}
                human['inputs'] = {}
                human.pop('review')
                workflow['graphs']['default'] = {
                    'nodes': {'work': node, 'base': op, 'approve': human},
                    'terminal': ['work', 'base', 'approve']}
                policy = fx.load_template('POLICY.json')
                policy['settings'].setdefault('engine', {})['requires'] = ['round_budget']
                self.assertEqual([], schemas.validate_workflow(workflow, policy))
                sim = Sim(workflow=workflow, policy=policy)
                doc = sim.goal(1000, budget=0)
                self.assertEqual(([], []), schemas.validate_goal(doc))
                portfolio = sim.eval()
                res = portfolio.goals[1000]
                self.assertFalse(res.budget['stages'][absent]['over'])
                self.assertTrue(res.budget['stages'][stage]['over'])
                ctx = render.Ctx('zzzops', sim.now, sim.settings, {})
                items = [item for _, item in render.human_items(ctx, res, True)]
                budgets = [item for item in items if item['kind'] == 'budget']
                self.assertEqual([stage], [item['stage'] for item in budgets])
                self.assertEqual(10, budgets[0]['options'][0]['file']['set']['budget'])
                self.assertIn('approve', [item['node'] for item in items])
                actions, _ = render.goal_actions(ctx, portfolio, res)
                self.assertEqual(['base'], [item['node'] for _, item in actions])
                res.budget['stages'][absent]['over'] = True
                self.assertEqual(1, len([item for _, item in render.human_items(ctx, res, True)
                                         if item['kind'] == 'budget']))
                sim.settings['engine']['requires'] = []
                legacy = sim.eval().goals[1000]
                self.assertNotIn('stages', legacy.budget)
                self.assertFalse(legacy.budget['over'])
                actions, _ = render.goal_actions(ctx, sim.eval(), legacy)
                self.assertIn('work', [item['node'] for _, item in actions])


if __name__ == '__main__':
    unittest.main()
