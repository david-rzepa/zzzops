"""Regression journeys through actual goal projection and workflow evidence."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_zzzops as fixtures
z = fixtures.zzzops


class WorkflowIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.GoalTransitionTests()
        self.adapter = fixtures.FakeGoalTransitionAdapter(self.fixture.issue())
        self.graph = {'phases': [{'id': 'plan'}]}
        self.nodes = {'plan': {'review': {'independent': True}}}
        self.project = {'backend': 'github_issues', 'repository': {'identity': 'owner/repo'},
                        'policy': {'sections': [{'id': 'workflow_adherence', 'configuration': {'phase_dag': self.graph}}]}}

    def test_rendered_goal_produces_live_inputs_without_phase_evidence(self):
        goal = z.github_goal_record(self.adapter.issue)
        self.assertIn('plan', z.workflow_live_inputs(Path('.'), self.project, goal, 'execute', self.graph))

    def test_operational_revision_and_preview_do_not_change_inputs(self):
        goal = z.github_goal_record(self.adapter.issue)
        first = z.workflow_live_inputs(Path('.'), self.project, goal, 'execute', self.graph)
        goal['revision'] += 1
        self.assertEqual(first, z.workflow_live_inputs(Path('.'), self.project, goal, 'preview', self.graph))

    def test_configuration_and_instruction_changes_each_invalidate_open_evidence(self):
        self.project['policy']['sections'].append({
            'id': 'verification_testing', 'configuration': {'required_ci': 'inspect_exact_pr_head'},
            'instructions': 'Inspect failures before retrying.',
        })
        goal = z.github_goal_record(self.adapter.issue)
        live = z.workflow_live_inputs(Path('.'), self.project, goal, 'execute', self.graph)
        goal['phase_evidence'] = z.record_phase_result(
            z.empty_phase_evidence(), 'plan', fixtures.PhaseEvidenceTests().record('plan', live['plan']), live['plan'],
        )
        for field in ('configuration', 'instructions'):
            project = copy.deepcopy(self.project)
            section = project['policy']['sections'][-1]
            if field == 'configuration':
                section[field]['required_ci'] = 'disabled'
            else:
                section[field] += ' Preserve the failing evidence.'
            changed = z.workflow_live_inputs(Path('.'), project, goal, 'execute', self.graph)
            with self.subTest(field=field):
                self.assertNotEqual(live['plan']['policy'], changed['plan']['policy'])
                frontier = z.derive_phase_steps(goal, self.graph, changed)
                self.assertEqual(['plan'], [item['phase'] for item in frontier['execute']])
                closed = {**goal, 'status': 'done'}
                self.assertEqual([], z.derive_phase_steps(closed, self.graph, changed)['execute'])

    def test_submission_then_backend_reread_requires_review_not_reexecution(self):
        goal = z.github_goal_record(self.adapter.issue)
        live = z.workflow_live_inputs(Path('.'), self.project, goal, 'execute', self.graph)
        record = fixtures.PhaseEvidenceTests().record('plan', live['plan'])
        with mock.patch.object(z, 'reviewed_project_state', return_value=self.project), \
             mock.patch.object(z, 'GitHubGoalTransitionAdapter', return_value=self.adapter), \
             mock.patch.object(z, '_workflow_phase_configuration', return_value=(self.graph, self.nodes)):
            z.workflow_submit(Path('.'), 42, 'execute', {'operation': 'record_result', 'phase': 'plan', 'record': record})
        updated = z.github_goal_record(self.adapter.issue)
        next_live = z.workflow_live_inputs(Path('.'), self.project, updated, 'execute', self.graph)
        frontier = z.derive_phase_steps(updated, self.graph, next_live)
        self.assertEqual([], frontier['execute'])
        self.assertEqual(['plan'], [item['phase'] for item in frontier['review']])

    def test_every_acceptance_bullet_is_required(self):
        body = '## Acceptance\n- [ ] Must work\n- Preserve data\n- [x] Already done\n\n## Constraints\n- Out of scope\n'
        self.assertEqual(['Must work', 'Preserve data', 'Already done'], z._goals.goal_acceptance_criteria(body))

    def test_execute_semantic_intent_reaches_workflow(self):
        self.assertEqual(['zzzops.py', 'workflow', '--intent', 'execute', '--source-skill', '$execute-zzzops'],
                         z.normalize_workflow_entrypoint(['zzzops.py', '--intent', 'execute']))

    def test_rejected_review_returns_phase_for_correction(self):
        fixture = fixtures.PhaseEvidenceTests()
        envelope = fixture.envelope('plan')
        evidence = z.record_phase_result(z.empty_phase_evidence(), 'plan', fixture.record('plan', envelope), envelope)
        artifact = {'reference': 'urn:sha256:' + 'a' * 64, 'hash': 'sha256:' + 'a' * 64}
        evidence = z.record_phase_review(evidence, 'plan', artifact, 'reviewer', decision='changes_requested')
        frontier = z.derive_phase_steps({'status': 'ready', 'phase_evidence': evidence}, self.graph, {'plan': envelope})
        self.assertEqual(['plan'], [item['phase'] for item in frontier['execute']])
        self.assertEqual([], frontier['review'])

class PublicWorkflowJourneyTests(unittest.TestCase):
    def setUp(self):
        import json
        import contextlib
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.adapter = fixtures.FakeGoalTransitionAdapter(fixtures.GoalTransitionTests().issue())
        template = json.loads((fixtures.PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        self.project = {'backend': 'github_issues', 'repository': {'identity': 'owner/repo'}, 'policy': template['policy']}
        routing = next(s for s in self.project['policy']['sections'] if s['id'] == 'model_routing')['configuration']
        routing['model_inventory']['reviewed_pairs'] = [
            {'model': 'root', 'effort': 'high', 'tier': 'architectural', 'cost': 10},
            {'model': 'worker', 'effort': 'medium', 'tier': 'bounded', 'cost': 2}]
        self.runtime = {'root_pair': {'model': 'root', 'effort': 'high'}, 'available_pairs': [{'model': 'root', 'effort': 'high'}, {'model': 'worker', 'effort': 'medium'}], 'root_id': 'root-thread', 'delegation': {'available': True, 'tool': 'spawn_agent', 'discovery_complete': True}}
        # Restrict the graph for this transition-focused fixture; projection,
        # live inputs, routing, records, and persisted transitions remain real.
        self.graph = {'phases': [{'id': 'plan'}]}
        self.nodes = {'plan': {'assignment_group': 'planning', 'review': {'independent': True, 'human_approval': True, 'assignment_group': 'review'}}}
        self.patches = [mock.patch.object(z, 'GitHubGoalTransitionAdapter', return_value=self.adapter), mock.patch.object(z, '_workflow_phase_configuration', return_value=(self.graph, self.nodes)), mock.patch.object(z, 'portfolio_snapshot', side_effect=lambda repo: {'valid': True, 'complete': True, 'goals': [z.github_goal_record(self.adapter.issue)]})]
        for patch in self.patches:
            patch.start(); self.addCleanup(patch.stop)
        self.engine = z.workflow_engine(self.repo, self.project, self.runtime)
        self.engine.locked = contextlib.nullcontext
        self.seq = 0

    def mutate(self, **payload):
        self.seq += 1
        if payload.get('operation') in {'start', 'bind'}:
            import json
            kind = payload.get('kind')
            if kind is None:
                goal = z.github_goal_record(self.adapter.issue)
                kind = next(v['kind'] for v in goal['workflow']['leases'].values() if v['token'] == payload['lease'])
            step = {'phase': payload['phase'], 'kind': kind}
            z._policy_context.attach({'next_steps': [step]}, self.repo, self.project, source='$execute-zzzops')
            payload.setdefault('policy_receipt', json.loads(Path(step['policy']['path']).read_text())['policy_receipt'])
        return self.engine.mutate(42, {'request_id': str(self.seq), **payload})

    def start(self, kind):
        step = self.engine.step(42)[0]
        self.assertEqual(kind, step['kind'])
        return self.mutate(operation='start', phase='plan', kind=kind, input_hash=step['input_hash'])['next_steps'][0]

    def prepare(self):
        step = self.engine.step(42)[0]
        self.assertEqual('assess', step['kind'])
        self.mutate(operation='assess', phase='plan', input_hash=step['input_hash'], files=[], dimensions={'consequence': 'bounded', 'boundedness': 'atomic', 'engineering_rigor': 'structured'})
        step = self.start('execute')
        lease = step['lease']
        self.mutate(operation='bind', phase='plan', lease=lease['token'], actor='builder', selection=lease['selection'])
        record = fixtures.PhaseEvidenceTests().record('plan', step['input_envelope'])
        record.update(actor='builder', selection=lease['selection'], routing=step['result_contract']['record']['routing'], output=self.engine.artifact(42, {'output': 'output'}))
        return lease, record

    def test_start_and_worker_bind_require_current_policy_read_without_writes_on_rejection(self):
        import json
        assessment = self.engine.step(42)[0]
        self.mutate(operation='assess', phase='plan', input_hash=assessment['input_hash'], files=[], dimensions={'consequence': 'bounded', 'boundedness': 'atomic', 'engineering_rigor': 'structured'})
        step = self.engine.step(42)[0]
        request = {**step['start'], 'request_id': 'policy-start'}
        before = self.adapter.issue['body']
        for receipt in (None, 'stale-receipt'):
            with self.assertRaisesRegex(ValueError, 'policy_receipt'):
                self.engine.mutate(42, {**request, 'policy_receipt': receipt})
            self.assertEqual(before, self.adapter.issue['body'])
        z._policy_context.attach({'next_steps': [step]}, self.repo, self.project, source='$execute-zzzops')
        document = json.loads(Path(step['policy']['path']).read_text())
        receipt = document['policy_receipt']
        self.assertNotIn(receipt, json.dumps(step))
        self.assertNotEqual(receipt, step['policy']['sha256'])
        with self.assertRaisesRegex(ValueError, 'policy_receipt'):
            self.engine.mutate(42, {**request, 'policy_receipt': step['policy']['sha256']})
        result = self.engine.mutate(42, {**request, 'policy_receipt': receipt})
        perform = result['next_steps'][0]
        before = self.adapter.issue['body']
        bind = {**perform['bind'], 'actor': 'builder', 'request_id': 'policy-bind'}
        with self.assertRaisesRegex(ValueError, 'policy_receipt'):
            self.engine.mutate(42, bind)
        self.assertEqual(before, self.adapter.issue['body'])
        self.engine.mutate(42, {**bind, 'policy_receipt': receipt})
        # The acknowledgment is not copied into goal state or returned lease data.
        self.assertNotIn(receipt, self.adapter.issue['body'])
        self.assertNotIn(receipt, json.dumps(result))

    def test_persisted_execute_review_human_approval_journey(self):
        lease, record = self.prepare()
        result = self.mutate(operation='record_result', phase='plan', lease=lease['token'], actor='builder', record=record)
        self.assertEqual('checkpoint', result['next_steps'][0]['kind'])
        step = self.start('review')
        reviewer = step['lease']
        self.mutate(operation='bind', phase='plan', lease=reviewer['token'], actor='reviewer', selection=reviewer['selection'])
        self.mutate(operation='record_review', phase='plan', lease=reviewer['token'], actor='reviewer', artifact=record['output'], outcomes={'acceptance': 'approved', 'entropy': {'outcome': 'no_findings', 'evidence': 'Reviewed implementation and adjacent tests.'}})
        step = self.start('human_approval')
        self.mutate(operation='approve', phase='plan', lease=step['lease']['token'], actor='root-thread', approval={'actor': 'root-thread', 'approval_token': 'user:explicit-approval'})
        goal = z.github_goal_record(self.adapter.issue)
        frontier = z.derive_phase_steps(goal, self.graph, self.engine.inputs(goal, self.graph), review_policy=self.nodes)
        self.assertEqual([], frontier['execute'])
        self.assertEqual([], frontier['review'])
        self.assertIn('plan', goal['phase_evidence']['human_approvals'])

    def test_actor_selection_and_duplicate_submission_are_guarded(self):
        lease, record = self.prepare()
        with self.assertRaisesRegex(ValueError, 'bound executor'):
            self.mutate(operation='record_result', phase='plan', lease=lease['token'], actor='someone-else', record=record)
        altered = copy.deepcopy(record); altered['selection']['effort'] = 'high'
        with self.assertRaisesRegex(ValueError, 'model/effort'):
            self.mutate(operation='record_result', phase='plan', lease=lease['token'], actor='builder', record=altered)
        altered = copy.deepcopy(record); altered['routing'] = None
        with self.assertRaisesRegex(ValueError, 'capability assessment'):
            self.mutate(operation='record_result', phase='plan', lease=lease['token'], actor='builder', record=altered)
        payload = {'operation': 'record_result', 'phase': 'plan', 'lease': lease['token'], 'actor': 'builder', 'record': record, 'request_id': 'retry-safe'}
        first = self.engine.mutate(42, payload)
        revision = z.github_goal_record(self.adapter.issue)['revision']
        self.assertEqual('checkpoint', self.engine.mutate(42, payload)['next_steps'][0]['kind'])
        self.assertEqual(revision, z.github_goal_record(self.adapter.issue)['revision'])

    def test_expiry_requires_recovery_and_missing_delegation_blocks(self):
        self.runtime['delegation']['available'] = False
        self.assertEqual('capability_discovery', self.engine.step(42)[0]['kind'])
        self.runtime['delegation']['available'] = True
        lease, record = self.prepare()
        with self.assertRaisesRegex(ValueError, 'stopped'):
            self.mutate(operation='recover', phase='plan', lease=lease['token'], worker_status='unknown', evidence='timeout')
        self.mutate(operation='recover', phase='plan', lease=lease['token'], worker_status='stopped', evidence='thread terminal')
        self.assertEqual('execute', self.engine.step(42)[0]['kind'])

    def test_blocker_step_supplies_exact_resolution_request(self):
        self.mutate(operation='block', category='access-approval', reason='User must approve access')
        step = self.engine.step(42)[0]
        self.assertEqual('blocker', step['kind'])
        request = step['submission']
        self.assertEqual('User must approve access', request['changes']['blockers'][0]['reason'])
        request['changes'] = {'blockers': [], 'next_action': 'User explicitly approved access'}
        self.mutate(**request)
        self.assertNotEqual('blocker', self.engine.step(42)[0]['kind'])
