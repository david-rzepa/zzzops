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

    def test_review_types_and_consequence_overrides_are_policy_owned(self):
        node = next(n for n in self.dag['phases'] if n['id'] == 'implement')
        self.assertEqual(['acceptance', 'entropy'], node['review']['types'])
        node['review']['by_consequence'] = {'architectural': {'human_approval': True}}
        self.assertEqual([], zzzops._policy._workflow_phase_dag_errors(self.dag))
        goal = {'key': 1, 'workflow': {'assessments': {'implement': {'dimensions': {'consequence': 'architectural'}}}}}
        _, nodes = zzzops._workflow_phase_configuration(self.project, goal)
        self.assertTrue(nodes['implement']['review']['human_approval'])
        goal['workflow']['assessments']['implement']['dimensions']['consequence'] = 'bounded'
        _, nodes = zzzops._workflow_phase_configuration(self.project, goal)
        self.assertFalse(nodes['implement']['review']['human_approval'])
        self.assertFalse(node['review']['human_approval'], 'Resolution must not mutate reviewed policy')
        node['review']['by_consequence']['unknown'] = {'human_approval': True}
        self.assertTrue(zzzops._policy._workflow_phase_dag_errors(self.dag))

    def test_old_reviewed_dag_is_accepted_and_reported_stale(self):
        from pathlib import Path
        old = json.loads((Path(__file__).parent / 'fixtures/legacy_phase_dag.json').read_text())
        self.assertEqual([], zzzops._policy._workflow_phase_dag_errors(old))
        self.assertNotEqual(zzzops._phase_evidence.sha256_digest(old), zzzops._phase_evidence.sha256_digest(self.dag))
        self.assertNotIn('plan', {n['id'] for n in self.dag['phases']})
        section = next(s for s in self.project['policy']['sections'] if s['id'] == 'workflow_adherence')
        current = zzzops._policy.policy_default_catalog()['zzzops.policy.workflow_adherence']
        content = copy.deepcopy(current['content'])
        content['configuration']['phase_dag'] = old
        section.pop('default_id', None)
        section.update(content)
        section['default_provenance'] = {
            'status': 'adopted', 'default_id': current['id'], 'schema_version': zzzops._policy.POLICY_DEFAULT_SCHEMA_VERSION,
            'source': {'version': '0.0.0-dev', 'revision': 'a' * 40},
            'digest': zzzops._policy.policy_content_digest(content), 'snapshot': content,
        }
        comparison = next(row for row in zzzops._policy.compare_policy_defaults(self.project['policy']) if row['section_id'] == 'workflow_adherence')
        self.assertEqual('update_available', comparison['status'])

    def test_leaf_and_composition_graphs_at_every_depth(self):
        for parent in (None, 430):
            for children in ([], [457]):
                with self.subTest(parent=parent, children=children):
                    goal = {'key': 456, 'parent': parent, 'children': children}
                    graph, nodes = zzzops._workflow_phase_configuration(self.project, goal)
                    projected = {n['id']: n for n in graph['phases']}
                    for phase in ('test_design', 'implement'):
                        self.assertEqual(not children, phase in nodes)
                    self.assertEqual(['decompose'] if children else ['implement'],
                                     projected['publish']['depends_on'])
                    if parent and not children:
                        self.assertEqual(['decompose'], projected['implement']['parent_gates'])
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
