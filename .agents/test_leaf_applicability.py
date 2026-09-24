"""Leaf-owned phases apply independently of structural parenthood."""
import copy
import json
import unittest

from test_zzzops import PLUGIN_ROOT, zzzops


class LeafApplicabilityTests(unittest.TestCase):
    def setUp(self):
        plan = json.loads((PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        self.project = {'policy': plan['policy']}
        self.dag = next(s for s in plan['policy']['sections']
                        if s['id'] == 'workflow_adherence')['configuration']['phase_dag']

    def test_default_selects_leaf_owned_work(self):
        for node in self.dag['phases']:
            if node['id'] in {'test_design', 'implement'}:
                self.assertEqual('leaf_only', node['applicability'])
        self.assertEqual([], zzzops._policy._workflow_phase_dag_errors(self.dag))

    def test_leaf_and_composition_graphs_at_every_depth(self):
        for parent in (None, 430):
            for children in ([], [457]):
                with self.subTest(parent=parent, children=children):
                    goal = {'key': 456, 'parent': parent, 'children': children}
                    graph, nodes = zzzops._workflow_phase_configuration(self.project, goal)
                    projected = {n['id']: n for n in graph['phases']}
                    for phase in ('test_design', 'implement'):
                        self.assertEqual(not children, phase in nodes)
                    self.assertEqual(['plan'] if children else ['implement'],
                                     projected['publish']['depends_on'])
                    if parent and not children:
                        self.assertEqual(['plan'], projected['implement']['parent_gates'])
                    if not parent:
                        self.assertTrue(all(not n['parent_gates'] for n in graph['phases']))

    def test_existing_child_only_policy_keeps_its_reviewed_meaning(self):
        legacy = copy.deepcopy(self.dag)
        for node in legacy['phases']:
            if node['applicability'] == 'leaf_only':
                node['applicability'] = 'child_only'
        for parent in (False, True):
            graph = zzzops.phase_evidence_graph(legacy, has_parent=parent)
            self.assertEqual(parent, 'implement' in {n['id'] for n in graph['phases']})


if __name__ == '__main__':
    unittest.main()
