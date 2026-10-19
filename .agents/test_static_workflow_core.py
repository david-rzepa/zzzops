"""Fixed workflow definition and repeatable phase-data contracts."""
import importlib.util
from pathlib import Path
import unittest
import test_evidence_dag_journeys as dag

PATH = Path(__file__).parents[1] / 'plugins/zzzops/zzzops/static_workflow.py'

class StaticWorkflowCoreTests(unittest.TestCase):
    def service(self):
        self.assertTrue(PATH.exists(), 'Missing canonical static workflow service')
        spec = importlib.util.spec_from_file_location('static_workflow_core', PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def graph(self):
        tests = dag.task('tests', role='worker')
        code = dag.task('code', ['tests'])
        code['inputs'] = {'tests': dag.subject_input('tests')}
        return {'nodes': [tests, code], 'task_sets': [], 'terminals': [dag.selector('code')]}

    def test_absolute_policy_scope_is_preserved_without_goal_localization(self):
        graph = dag.correction_graph()
        canonical = self.service().canonical(graph, dag.z._graph_compiler)
        dag.z._phase_evidence.validate_graph(canonical)
        self.assertEqual(graph['nodes'], canonical['nodes'][:len(graph['nodes'])])
        assessments = [permit for row in canonical['task_sets']
                       for permit in row['template']['permits']
                       if permit['type'] == 'applicability_assessment']
        self.assertTrue(any(permit['scope'] == dag.scope('produce') for permit in assessments))

    def test_inferred_absolute_review_correction_keeps_exact_target(self):
        producer = dag.task('produce')
        reviewer = dag.task('review', ['produce'])
        reviewer['inputs'] = {'subject': dag.subject_input('produce')}
        reviewer['inputs']['subject']['producer']['node']['goal'] = 100
        reviewer['independent_of'] = [{'kind': 'node', 'goal': 100, 'node': 'produce'}]
        reviewer['outputs'] = {'value': {'type': 'review_decision', 'schema': {'kind': 'object',
            'fields': {'decision': {'kind': 'enum', 'values': ['approved', 'changes_requested']},
                       'report': {'kind': 'string'}}}}}
        graph = {'nodes': [producer, reviewer], 'task_sets': [], 'terminals': [dag.selector('review')]}
        canonical = self.service().canonical(graph, dag.z._graph_compiler)
        dag.z._phase_evidence.validate_graph(canonical)
        generated = canonical['nodes'][2:]
        permits = [permit for node in generated for permit in node['permits']]
        self.assertTrue(any(permit['scope']['subject'].get('goal') == 100 for permit in permits))
        self.assertFalse(any(permit['scope']['subject'].get('goal') == '#this' for permit in permits))

    def test_custom_member_unresolved_admission_fails_preflight(self):
        import test_graph_normalization_public as cases
        with self.assertRaisesRegex(ValueError, 'Unsupported unresolved member admission'):
            self.service().canonical(cases.unsupported_member_retirement_graph(), dag.z._graph_compiler)

    def test_late_events_do_not_change_graph_or_original_contracts(self):
        s = self.service(); graph = self.graph()
        compiled = s.canonical(graph, dag.z._graph_compiler)
        dag.z._phase_evidence.validate_graph(compiled)
        self.assertEqual(graph['nodes'], compiled['nodes'][:2])
        event = {'id': 'late-regression', 'revision': 1, 'source': dag.REF,
                 'subject': dag.REF, 'rationale': 'Accepted test missed provider authority'}
        first = s.phase_data([{'target': {'node': 'tests', 'output': 'value'}, **event}], graph, 100)
        event['revision'] = 2
        second = s.phase_data([{'target': {'node': 'tests', 'output': 'value'}, **event}], graph, 100)
        self.assertNotEqual(first, second)
        self.assertEqual(compiled, s.canonical(graph, dag.z._graph_compiler))
        self.assertEqual(compiled, s.canonical(compiled, dag.z._graph_compiler))
        self.assertEqual({s.event_key({**event, 'revision': 1})}, set(first['tests']['value']['items']))
        self.assertEqual(graph['terminals'], compiled['terminals'])

    def test_phase_events_reject_unknown_target_and_conflicting_revision(self):
        s = self.service(); graph = self.graph()
        event = {'id': 'late', 'revision': 1, 'source': dag.REF, 'subject': dag.REF,
                 'rationale': 'diagnostic', 'target': {'node': 'tests', 'output': 'value'}}
        with self.assertRaises(ValueError):
            s.phase_data([{**event, 'target': {'node': 'unknown', 'output': 'value'}}], graph, 100)
        with self.assertRaises(ValueError):
            s.phase_data([event, {**event, 'rationale': 'changed exact revision'}], graph, 100)


    def projection(self, graph, events=(), policy=None, payload=None, artifacts=None, goal_context=None):
        s = self.service()
        payload = payload or {'evidence': [], 'operational': {'leases': [], 'receipts': []}}
        snapshot = {'graph': graph, 'payload': payload, 'phase_data': s.phase_data(list(events), graph, 100)}
        if goal_context is not None: snapshot['goal_context'] = goal_context
        context = {'goal': 100, 'policy': policy or {}, 'artifacts': artifacts or {},
                   'goals': {100: snapshot}}
        return dag.z._phase_evidence.derive_task_steps(graph, payload, context)

    def completed(self, graph, name, policy):
        s = self.service(); p = self.projection(graph, policy=policy)
        state = p['states'][(100, name, None, 1)]
        output = {'type': 'text', 'content': 'accepted', 'producer': 'attempt',
                  'provenance': {'actor': 'producer', 'source': None, 'policy': 'original'}}
        out_ref = {'hash': s.digest(output), 'uri': 'urn:' + s.digest(output)}
        result = {'type': 'result', 'content': {'node': state['node'], 'attempt': 'attempt',
            'contract': state['contract_hash'], 'inputs': state['inputs'],
            'executor': 'producer', 'outputs': {'value': out_ref}, 'resolutions': state['resolutions']},
            'producer': 'attempt', 'provenance': {'actor': 'producer', 'source': None, 'policy': 'original'}}
        ref = {'hash': s.digest(result), 'uri': 'urn:' + s.digest(result)}
        return {'evidence': [ref], 'operational': {'leases': [], 'receipts': []}}, {
            out_ref['hash']: output, ref['hash']: result}, out_ref

    def test_event_members_expand_with_valid_identity_after_approved_subject(self):
        s = self.service(); graph = s.canonical(self.graph(), dag.z._graph_compiler)
        payload, artifacts, subject = self.completed(graph, 'tests', {})
        event = {'id': 'late.regression', 'revision': 1, 'source': dag.REF,
                 'subject': subject, 'rationale': 'late failure',
                 'target': {'node': 'tests', 'output': 'value'}}
        result = self.projection(graph, [event], payload=payload, artifacts=artifacts)
        key = (100, s.review_name('tests', 'value'), s.event_key(event), 1)
        self.assertIn(key, result['states'])
        self.assertEqual('ready', result['states'][key]['state'])
        self.assertEqual(event, result['states'][key]['values']['event'])
        self.assertIn((100, 'tests', None, 1), result['current'])

    def test_empty_events_need_no_retention_and_pending_event_blocks_completion(self):
        s = self.service(); graph = self.graph(); graph['nodes'] = graph['nodes'][:1]
        graph['terminals'] = [dag.selector('tests')]
        graph = s.canonical(graph, dag.z._graph_compiler)
        first = self.projection(graph)
        self.assertEqual(['tests'], [row['node']['node'] for row in first['ready']])
        payload, artifacts, subject = self.completed(graph, 'tests', {})
        self.assertTrue(self.projection(graph, payload=payload, artifacts=artifacts)['complete'])
        event = {'id': 'late', 'revision': 1, 'source': dag.REF, 'subject': subject,
                 'rationale': 'late failure', 'target': {'node': 'tests', 'output': 'value'}}
        self.assertFalse(self.projection(graph, [event], payload=payload, artifacts=artifacts)['complete'])

    def test_added_policy_phase_preserves_result_but_changed_own_contract_stales(self):
        import copy
        s = self.service(); graph = self.graph()
        policy = {'sections': [{'id': 'workflow_adherence', 'configuration': {'phase_dag': graph},
                                'instructions': 'Preserve independent review.'}]}
        payload, artifacts, _ = self.completed(graph, 'tests', policy)
        changed = copy.deepcopy(graph); changed['nodes'].append(dag.task('unrelated'))
        updated = copy.deepcopy(policy); updated['sections'][0]['configuration']['phase_dag'] = changed
        self.assertIn((100, 'tests', None, 1), self.projection(changed, policy=updated,
                      payload=payload, artifacts=artifacts)['current'])
        changed['nodes'][0]['prompt'] += ' New substantive requirement.'
        self.assertNotIn((100, 'tests', None, 1), self.projection(changed, policy=updated,
                         payload=payload, artifacts=artifacts)['current'])

    def test_preserves_explicit_legacy_routes_without_fingerprint_repair(self):
        import json
        s = self.service()
        graph = json.loads((PATH.parents[3] / '.agents/fixtures/legacy_evidence_dag.json').read_text())
        compiled = s.canonical(graph, dag.z._graph_compiler)
        dag.z._phase_evidence.validate_graph(compiled)
        self.assertEqual(graph['nodes'], compiled['nodes'][:len(graph['nodes'])])
        self.assertEqual(graph['task_sets'], compiled['task_sets'][:len(graph['task_sets'])])
        self.assertEqual(compiled, s.canonical(compiled, dag.z._graph_compiler))

    def test_unknown_goal_context_blocks_only_resource_phase(self):
        graph = self.graph(); graph['nodes'][0]['executor']['resources'] = ['repository_publication']
        result = self.projection(graph, goal_context={'version': 2, 'depends_on': [], 'blockers': []})
        self.assertIn('Unsupported', result['states'][(100, 'tests', None, 1)]['reason'])
        context = {'version': 1, 'depends_on': [], 'blockers': [{'status': 'open', 'reason': 'human input'}]}
        result = self.projection(graph, goal_context=context)
        self.assertIn('blocker', result['states'][(100, 'tests', None, 1)]['reason'])

    def test_cache_returns_detached_graph_without_recompiling(self):
        from unittest import mock
        s = self.service(); graph = self.graph()
        first = s.canonical(graph, dag.z._graph_compiler)
        with mock.patch.object(dag.z._graph_compiler, '_route_family', side_effect=AssertionError('recompiled')):
            second = s.canonical(graph, dag.z._graph_compiler)
            second['nodes'][0]['prompt'] = 'caller mutation'
            self.assertEqual(first, s.canonical(graph, dag.z._graph_compiler))

    def test_pending_event_blocks_publication_but_leaves_target_and_review_current(self):
        s = self.service(); graph = self.graph()
        graph['nodes'][1]['executor']['resources'] = ['repository_publication']
        graph = s.canonical(graph, dag.z._graph_compiler)
        payload, artifacts, subject = self.completed(graph, 'tests', {})
        self.assertEqual('ready', self.projection(graph, payload=payload, artifacts=artifacts)['states'][(100, 'code', None, 1)]['state'])
        event = {'id': 'late', 'revision': 1, 'source': dag.REF, 'subject': subject,
                 'rationale': 'late failure', 'target': {'node': 'tests', 'output': 'value'}}
        projected = self.projection(graph, [event], payload=payload, artifacts=artifacts)
        self.assertIn('Pending late finding', projected['states'][(100, 'code', None, 1)]['reason'])
        self.assertIn((100, 'tests', None, 1), projected['current'])
        key = (100, s.review_name('tests', 'value'), s.event_key(event), 1)
        self.assertEqual('ready', projected['states'][key]['state'])

    def test_fixed_member_family_and_authenticated_selector_markers(self):
        import copy
        s = self.service(); graph = dag.selected_graph()
        canonical = s.canonical(graph, dag.z._graph_compiler)
        dag.z._phase_evidence.validate_graph(canonical)
        self.assertEqual(canonical, s.canonical(canonical, dag.z._graph_compiler))
        event = {'id': 'late-member', 'revision': 1, 'source': dag.REF, 'subject': dag.REF,
                 'rationale': 'member defect', 'target': {'node': 'investigate', 'output': 'value',
                 'expansion': 'buckets', 'item': 'alpha', 'generation': 1}}
        data = s.phase_data([event], graph, 100)
        self.assertEqual(event, data['investigate']['value']['items'][s.event_key(event)])
        member_admissions = [output for row in canonical['task_sets']
            if row['source']['producer'] == {'slot': 'phase_data'}
            and row['source']['path'] == ['investigate', 'value']
            for output in row['template']['outputs'].values() if output['type'] == 'admission']
        self.assertTrue(member_admissions)
        for output in member_admissions:
            self.assertEqual(['applicable', 'not_applicable'],
                             output['schema']['fields']['applicability']['values'])
        bad = copy.deepcopy(canonical)
        expansion = next(row for row in bad['task_sets'] if row['template']['id'] == s.review_name('investigate', 'value'))
        expansion['source']['producer'] = {'slot': 'forged_events'}
        with self.assertRaisesRegex(ValueError, 'authenticated phase-event'):
            dag.z._phase_evidence.validate_graph(bad)
        with self.assertRaises(ValueError):
            s.phase_data([{**event, 'target': {**event['target'], 'generation': True}}], graph, 100)

if __name__ == '__main__': unittest.main()
