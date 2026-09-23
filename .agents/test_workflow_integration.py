"""Regression journeys through actual goal projection and workflow evidence."""
import copy
import json
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

    def test_new_goal_with_null_rigor_reaches_assessment_and_assignment(self):
        goal = z.parse_managed_goal(self.adapter.issue['body'], 42)
        goal['engineering_rigor'] = None
        self.adapter.issue['body'] = z.render_managed_goal(goal, '## Acceptance\n- Preserve the expected behavior.\n', 42)
        self.engine.invalidate()
        step = self.engine.step(42)[0]
        self.assertEqual('assess', step['kind'])
        self.mutate(operation='assess', phase='plan', input_hash=step['input_hash'], files=[],
                    dimensions={'consequence': 'bounded', 'boundedness': 'atomic', 'engineering_rigor': 'structured'})
        assignment = self.engine.step(42)[0]
        self.assertEqual('execute', assignment['kind'])
        self.assertEqual('delegate', assignment['assignment'])
        self.assertEqual({'model': 'worker', 'effort': 'medium'}, assignment['selection'])

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


class MigrationEvidenceFreshnessTests(unittest.TestCase):
    """Actual input/review projection with synthetic provider observations."""
    def setUp(self):
        import json
        from test_migration_acceptance import assessment, releases
        self.fixture = PublicWorkflowJourneyTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.repo, self.engine = self.fixture.repo, self.fixture.engine
        self.goal = z.github_goal_record(self.fixture.adapter.issue)
        self.spec = z.goal_spec_digest(self.goal, title=self.goal['title'], human_spec=self.goal['human_spec'])
        self.path = self.repo / '.zzzops/migration/42.json'
        self.path.parent.mkdir(parents=True)
        self.document = assessment(42, self.spec)
        self.path.write_text(json.dumps(self.document))
        self.observation = releases()
        self.observer = mock.patch.object(z, 'github_release_evidence', side_effect=lambda *a, **k: copy.deepcopy(self.observation))
        self.observer.start(); self.addCleanup(self.observer.stop)
        self.repository = mock.patch.object(z, 'github_repository_probe', return_value={'identity': 'owner/repo', 'visibility': 'PUBLIC'})
        self.repository.start(); self.addCleanup(self.repository.stop)
        self.goal['workflow'] = {'artifacts': {}, 'leases': {}, 'receipts': {}, 'workers': {},
            'assessments': {'plan': {'dimensions': {'consequence': 'bounded', 'boundedness': 'atomic', 'engineering_rigor': 'structured'},
                                    'goal_spec': self.spec, 'policy': z.sha256_phase_evidence_digest(self.fixture.project['policy']),
                                    'files': ['.zzzops/migration/42.json']}}}

    def live(self, goal=None):
        self.engine.invalidate()
        return self.engine.inputs(self.goal if goal is None else goal, self.fixture.graph)

    def approved(self, live):
        record = fixtures.PhaseEvidenceTests().record('plan', live['plan'])
        evidence = z.record_phase_result(z.empty_phase_evidence(), 'plan', record, live['plan'])
        artifact = {'reference': 'urn:sha256:' + 'a' * 64, 'hash': 'sha256:' + 'a' * 64}
        evidence = z.record_phase_review(evidence, 'plan', artifact, 'independent-reviewer', decision='approved')
        return evidence

    def test_external_release_change_stales_review_without_file_or_policy_change(self):
        before = self.live(); raw = self.path.read_bytes()
        self.goal['phase_evidence'] = self.approved(before)
        unrelated = copy.deepcopy(self.goal)
        unrelated['workflow']['assessments']['plan']['files'] = []
        other_before = self.live(unrelated)
        self.observation['releases'][0]['commit'] = 'e' * 40
        after = self.live()
        self.assertNotEqual(before['plan'], after['plan'], 'Provider drift must invalidate consumed evidence even with unchanged file')
        self.assertEqual(raw, self.path.read_bytes())
        self.assertEqual(before['plan']['policy'], after['plan']['policy'])
        self.assertEqual(other_before, self.live(unrelated))
        frontier = z.derive_phase_steps(self.goal, self.fixture.graph, after)
        self.assertEqual(['plan'], [x['phase'] for x in frontier['execute']])
        closed = dict(self.goal, status='done')
        self.assertEqual([], z.derive_phase_steps(closed, self.fixture.graph, after)['execute'])

    def test_unavailable_provider_is_not_cached_as_fresh_and_restores(self):
        before = self.live()
        original = copy.deepcopy(self.observation)
        self.observation.clear(); self.observation.update(status='unavailable', releases=[])
        self.assertNotEqual(before, self.live())
        self.observation.clear(); self.observation.update(original)
        self.assertEqual(before, self.live())

    def test_attestation_revocation_and_deletion_stale_only_affected_goal(self):
        import json
        before = self.live(); original = self.path.read_bytes()
        unrelated = copy.deepcopy(self.goal)
        unrelated['workflow']['assessments']['plan']['files'] = []
        other = self.live(unrelated)
        changed = copy.deepcopy(self.document)
        changed['contracts'][0]['status'] = 'unknown'
        changed['contracts'][0]['evidence'][0]['statement'] = 'Owner explicitly revoked the claim.'
        self.path.write_text(json.dumps(changed))
        self.assertNotEqual(before, self.live())
        self.assertEqual(other, self.live(unrelated))
        self.path.unlink()
        self.assertNotEqual(before, self.live())
        self.path.write_bytes(original)
        self.assertEqual(before, self.live())

    def test_two_goal_assessments_cannot_substitute_on_resume(self):
        import json
        from test_migration_acceptance import assessment
        before = self.live(); original = self.path.read_bytes()
        other = self.path.with_name('43.json')
        other.write_text(json.dumps(assessment(43, self.spec)))
        self.assertEqual(before, self.live(), 'Independent assessment B must not alter A')
        self.path.write_bytes(other.read_bytes())
        changed = self.live()
        self.assertNotEqual(before, changed)
        # A mismatch must be an explicit provider decision, not only raw file drift.
        self.assertNotEqual(before['plan']['provider'], changed['plan']['provider'])
        self.path.write_bytes(original)
        self.assertEqual(before, self.live())

    def test_current_reassessment_reuses_substantive_output_with_new_review(self):
        import json
        before = self.live(); old = self.approved(before)
        original_output = old['records']['plan']['output']
        self.observation['releases'][0]['commit'] = 'e' * 40
        changed = self.live()
        self.assertNotEqual(before, changed)
        document = copy.deepcopy(self.document)
        document['release_snapshot'] = copy.deepcopy(self.observation)
        document['contracts'][0]['evidence'][0]['release_snapshot'] = copy.deepcopy(self.observation)
        self.path.write_text(json.dumps(document))
        current = self.live()
        record = fixtures.PhaseEvidenceTests().record('plan', current['plan'])
        record['output'] = original_output
        replaced = z.record_phase_result(old, 'plan', record, current['plan'])
        self.assertNotIn('plan', replaced['reviews'])
        fresh = z.record_phase_review(replaced, 'plan', old['reviews']['plan']['artifact'],
                                      'independent-reviewer', decision='approved')
        self.assertEqual(original_output, fresh['records']['plan']['output'])
        self.assertNotEqual(old['reviews']['plan']['record_hash'], fresh['reviews']['plan']['record_hash'])

    def test_public_dispatch_exposes_changed_release_input_identity(self):
        import json
        from test_workflow_public_contract import PublicWorkflowContractTests
        managed = z.parse_managed_goal(self.fixture.adapter.issue['body'], 42)
        managed['workflow'] = copy.deepcopy(self.goal['workflow'])
        self.fixture.adapter.issue['body'] = z.render_managed_goal(
            managed, self.goal['human_spec'], 42)
        harness = PublicWorkflowContractTests()
        harness.repo = self.repo
        with tempfile.TemporaryDirectory() as control:
            runtime = Path(control) / 'runtime.json'
            runtime.write_text(json.dumps(self.fixture.runtime))
            with mock.patch.object(z, 'reviewed_project_state', return_value=self.fixture.project), \
                 mock.patch.object(z, 'workflow_context_step', return_value=None), \
                 mock.patch.object(z._package, 'package_status', return_value={'ok': True, 'version': 'test', 'revision': 'synthetic'}), \
                 mock.patch.object(z._installation, 'validation_status', return_value={'required': False}):
                args = ('--intent', 'execute', '--goal', '42', '--runtime', str(runtime))
                code, before, stderr = harness.run_main(*args)
                self.assertEqual(0, code, before)
                self.assertEqual('', stderr)
                first = next(s for s in before['next_steps'] if s.get('phase') == 'plan')
                self.observation['releases'][0]['commit'] = 'e' * 40
                code, after, stderr = harness.run_main(*args)
                self.assertEqual(0, code, after)
                second = next(s for s in after['next_steps'] if s.get('phase') == 'plan')
                self.assertNotEqual(first['input_hash'], second['input_hash'])
                self.assertEqual(first['input_envelope']['policy'], second['input_envelope']['policy'])


    def test_affected_phases_share_one_observation_and_next_projection_refreshes(self):
        phase = copy.deepcopy(self.fixture.graph['phases'][0])
        phase.update(id='implement', depends_on=['plan'])
        self.fixture.graph['phases'].append(phase)
        self.goal['workflow']['assessments']['implement'] = copy.deepcopy(
            self.goal['workflow']['assessments']['plan'])
        with mock.patch.object(z, 'github_release_evidence', side_effect=lambda *a, **k: copy.deepcopy(self.observation)) as observer:
            first = self.live()
            self.assertEqual(1, observer.call_count, 'One goal projection must share one external release observation')
            self.assertEqual(first['plan']['provider']['snapshot']['migration'],
                             first['implement']['provider']['snapshot']['migration'])
            self.observation['releases'][0]['commit'] = 'e' * 40
            second = self.live()
            self.assertEqual(2, observer.call_count, 'Next projection must refresh rather than retain a persistent cache')
            self.assertEqual(second['plan']['provider']['snapshot']['migration'],
                             second['implement']['provider']['snapshot']['migration'])
            self.assertNotEqual(first['plan']['provider'], second['plan']['provider'])

    def test_public_migration_blocker_contract_persists_and_replays_receipt(self):
        import json
        from test_workflow_public_contract import PublicWorkflowContractTests
        managed = z.parse_managed_goal(self.fixture.adapter.issue['body'], 42)
        managed['workflow'] = copy.deepcopy(self.goal['workflow'])
        self.fixture.adapter.issue['body'] = z.render_managed_goal(managed, self.goal['human_spec'], 42)
        self.observation['releases'][0]['commit'] = 'e' * 40
        harness = PublicWorkflowContractTests(); harness.repo = self.repo
        reservation = fixtures.FakeReservationAdapter(repository='owner/repo')
        real_run = z.subprocess.run

        def reject_provider_escape(command, *args, **kwargs):
            if Path(command[0]).name.lower() in {'gh', 'gh.exe'}:
                raise AssertionError('Unexpected live provider call escaped the synthetic reservation boundary')
            return real_run(command, *args, **kwargs)

        with tempfile.TemporaryDirectory() as control:
            runtime = Path(control) / 'runtime.json'; runtime.write_text(json.dumps(self.fixture.runtime))
            submission = Path(control) / 'submission.json'
            with mock.patch.object(z, 'GitHubReservationAdapter', return_value=reservation), \
                 mock.patch.object(z.subprocess, 'run', side_effect=reject_provider_escape), \
                 mock.patch.object(z, 'reviewed_project_state', return_value=self.fixture.project), \
                 mock.patch.object(z, 'workflow_context_step', return_value=None), \
                 mock.patch.object(z._package, 'package_status', return_value={'ok': True, 'version': 'test', 'revision': 'synthetic'}), \
                 mock.patch.object(z._installation, 'validation_status', return_value={'required': False}):
                code, result, stderr = harness.run_main('--intent', 'execute', '--goal', '42', '--runtime', str(runtime))
                self.assertEqual(0, code, result)
                blocker = next(s for s in result['next_steps'] if s.get('phase') == 'plan')
                self.assertEqual('blocker', blocker['kind'])
                self.assertEqual(42, blocker['goal'])
                self.assertNotIn('start', blocker)
                self.assertIn('submission', blocker, 'Blocked work needs a supported copy-ready persistence contract')
                self.assertIn('command', blocker)
                payload = copy.deepcopy(blocker['submission'])
                self.assertEqual('block', payload['operation'])
                payload['request_id'] = 'migration-evidence-unresolved'
                submission.write_text(json.dumps(payload))
                args = [str(runtime) if a == '<runtime.json>' else str(submission) if a == '<submission.json>' else a
                        for a in blocker['command']]
                self.assertEqual('42', args[args.index('--goal') + 1])
                code, response, stderr = harness.run_main(*args)
                self.assertEqual(0, code, response)
                persisted = z.github_goal_record(self.fixture.adapter.issue)
                self.assertEqual('blocked', persisted['status'])
                self.assertEqual(1, len(persisted['blockers']))
                self.assertEqual(payload['reason'], persisted['blockers'][0]['reason'])
                self.assertTrue(any('independent' in s.get('action', '').lower() for s in response['next_steps']))
                body = self.fixture.adapter.issue['body']
                code, replay, stderr = harness.run_main(*args)
                self.assertEqual(0, code, replay)
                self.assertEqual(body, self.fixture.adapter.issue['body'])
                self.assertTrue(any('already applied' in s.get('action', '').lower() for s in replay['next_steps']))
                self.assertGreater(reservation.next_id, 1, 'Real storage-lock logic must use the fake provider')
                self.assertEqual({}, reservation.labels, 'Both public mutations must release their exact reservation')


class MigrationDiscoveryJourneyTests(unittest.TestCase):
    """Use only public output contracts to discover and prepare local evidence."""
    def setUp(self):
        self.fixture = MigrationEvidenceFreshnessTests()
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.repo = self.fixture.repo
        self.adapter = self.fixture.fixture.adapter
        self.project = self.fixture.fixture.project
        self.fixture.path.unlink()
        managed = z.parse_managed_goal(self.adapter.issue['body'], 42)
        managed['workflow'] = {'artifacts': {}, 'leases': {}, 'receipts': {}, 'workers': {}, 'assessments': {}}
        self.adapter.issue['body'] = z.render_managed_goal(managed, self.fixture.goal['human_spec'], 42)
        from test_workflow_public_contract import PublicWorkflowContractTests
        self.harness = PublicWorkflowContractTests(); self.harness.repo = self.repo
        self.control = tempfile.TemporaryDirectory(); self.addCleanup(self.control.cleanup)
        self.runtime = Path(self.control.name) / 'runtime.json'
        self.runtime.write_text(json.dumps(self.fixture.fixture.runtime))
        self.payload = Path(self.control.name) / 'input.json'
        self.sequence = 0
        real_run = z.subprocess.run
        def guarded_run(command, *args, **kwargs):
            if Path(command[0]).name.lower() in {'gh', 'gh.exe'}:
                raise AssertionError('Unexpected provider escape in discovery journey')
            return real_run(command, *args, **kwargs)
        patches = [
            mock.patch.object(z, 'reviewed_project_state', return_value=self.project),
            mock.patch.object(z, 'workflow_context_step', return_value=None),
            mock.patch.object(z._package, 'package_status', return_value={'ok': True, 'version': 'test', 'revision': 'synthetic'}),
            mock.patch.object(z._installation, 'validation_status', return_value={'required': False}),
            mock.patch.object(z, 'GitHubReservationAdapter', return_value=fixtures.FakeReservationAdapter(repository='owner/repo')),
            mock.patch.object(z.subprocess, 'run', side_effect=guarded_run),
        ]
        for patch in patches:
            patch.start(); self.addCleanup(patch.stop)

    def step(self):
        code, result, error = self.harness.run_main('--intent', 'execute', '--goal', '42', '--runtime', str(self.runtime))
        self.assertEqual(0, code, result); self.assertEqual('', error)
        return next(s for s in result['next_steps'] if s.get('phase') == 'plan')

    def submit(self, step, payload):
        self.sequence += 1
        payload = dict(payload, request_id=f'discovery-{self.sequence}')
        self.payload.write_text(json.dumps(payload))
        args = [str(self.runtime) if a == '<runtime.json>' else str(self.payload) if a == '<submission.json>' else a
                for a in step['command']]
        code, result, error = self.harness.run_main(*args)
        self.assertEqual(0, code, result); self.assertEqual('', error)
        return result

    def missing(self):
        step = self.step()
        self.assertEqual('assess', step['kind'])
        self.assertIn('migration_evidence', step, 'Ordinary assess must disclose the conditional evidence dependency')
        guidance = step['migration_evidence']
        self.assertTrue(guidance.get('when'), 'Applicability remains reasoned root judgment')
        relative = guidance['path']
        self.assertEqual('.zzzops/migration/42.json', relative)
        request = copy.deepcopy(step['submission'])
        self.assertEqual('assess', request['operation'])
        request['files'].append(relative)
        self.submit(step, request)
        blocker = self.step()
        self.assertEqual('blocker', blocker['kind'])
        self.assertEqual(relative, blocker['path'])
        return self.repo / relative, blocker, self.resource(blocker)

    def resource(self, blocker):
        import hashlib
        self.assertIn('preparation', blocker, 'Missing evidence must link complete preparation guidance')
        link = blocker['preparation']
        raw = Path(link['path']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), link['sha256'].removeprefix('sha256:'))
        data = json.loads(raw)
        self.assertTrue(data.get('instructions'))
        template = data['template']
        for field in ('schema_version', 'repository', 'goal', 'goal_spec', 'action', 'release_snapshot', 'contracts'):
            self.assertIn(field, template)
        self.assertEqual('owner/repo', template['repository'])
        self.assertEqual(42, template['goal'])
        self.assertEqual(blocker['input_envelope']['goal_spec'], template['goal_spec'])
        self.assertEqual(blocker['evidence']['release_snapshot'], template['release_snapshot'])
        self.assertEqual('unknown', template['contracts'][0]['status'])
        self.assertFalse(template['contracts'][0]['evidence'])
        examples = data['evidence_templates']
        self.assertIn('contract_investigation', examples); self.assertIn('owner_attestation', examples)
        for example in examples.values():
            self.assertFalse(example.get('author'), 'Never manufacture an agent or owner statement')
        self.assertFalse(examples['owner_attestation'].get('statement'))
        self.assertFalse(examples['contract_investigation'].get('rationale'))
        self.observation_shapes(data)
        return data

    def observation_shapes(self, resource):
        observations = resource['evidence_templates']['contract_investigation'].get('observations')
        self.assertIsInstance(observations, list)
        presence = [o for o in observations if isinstance(o, dict) and
                    {'commit', 'path', 'release_id', 'contract_present'} <= set(o)]
        distribution = [o for o in observations if isinstance(o, dict) and
                        {'commit', 'path', 'finding'} <= set(o)]
        self.assertTrue(presence, 'Resource must expose fillable contract-presence observation fields')
        self.assertTrue(distribution, 'Resource must expose fillable distribution-inspection fields')
        for observation in observations:
            self.assertFalse(observation.get('commit'), 'Do not fabricate an inspected commit')
            self.assertFalse(observation.get('path'), 'Do not fabricate an inspected file')
            self.assertIsNone(observation.get('contract_present'), 'Do not fabricate presence or absence')
            self.assertFalse(observation.get('finding'), 'Do not fabricate a distribution finding')
        guidance = resource.get('observation_guidance', {})
        for kind in ('development', 'published', 'distribution', 'path'):
            self.assertTrue(guidance.get(kind), f'Resource must explain {kind} observation semantics')
        self.assertIn('release_id', guidance['development'])
        self.assertIn('null', guidance['development'].lower())
        for term in ('release_id', 'commit', 'release_snapshot', 'contract_present'):
            self.assertIn(term, guidance['published'])
        self.assertIn('finding', guidance['distribution'])
        self.assertIn('relative', guidance['path'].lower())
        return presence[0], distribution[0]

    def filled(self, resource, kind='contract_investigation'):
        # Fill only shapes disclosed by the public resource. Facts below are
        # explicit synthetic investigation, never private fixture wire format.
        document = copy.deepcopy(resource['template'])
        document['action'] = 'Replace only synthetic project cache-v2 records'
        contract = copy.deepcopy(document['contracts'][0])
        contract.update(id='cache-v2', boundary='Only experimental project cache records',
                        status='unreleased', scope=['project-cache/v2'])
        evidence = copy.deepcopy(resource['evidence_templates'][kind])
        evidence.update(kind=kind, author='synthetic-investigator' if kind == 'contract_investigation' else 'synthetic-owner',
                        goal=document['goal'], goal_spec=document['goal_spec'], release_snapshot=document['release_snapshot'],
                        contract=contract['id'], boundary=contract['boundary'], scope=contract['scope'])
        if kind == 'contract_investigation':
            for key in ('conclusion', 'rationale', 'distribution_boundary', 'observations'):
                self.assertIn(key, evidence)
            presence, distribution = self.observation_shapes(resource)
            development = copy.deepcopy(presence)
            development.update(commit='c' * 40, path='cache/schema-v2.json', release_id=None, contract_present=True)
            inspected_distribution = copy.deepcopy(distribution)
            inspected_distribution.update(commit='c' * 40, path='distribution.json',
                                          finding='Only published packages distribute this synthetic contract.')
            observations = [development, inspected_distribution]
            for release in document['release_snapshot']['releases']:
                published = copy.deepcopy(presence)
                published.update(commit=release['commit'], path='cache/schema-v2.json',
                                 release_id=release['id'], contract_present=False)
                observations.append(published)
            evidence.update(conclusion='unreleased',
                            rationale='Inspected the development schema and each published tree: this synthetic contract exists only in development.',
                            distribution_boundary='Synthetic cache formats are distributed only in published packages; no separate deployment.',
                            observations=observations)
        else:
            self.assertIn('statement', evidence)
            evidence['statement'] = 'I maintain this synthetic cache and confirm it has never been distributed.'
        contract['evidence'] = [evidence]; document['contracts'] = [contract]
        return document

    def test_public_discovery_preparation_and_both_evidence_alternatives_resume(self):
        path, blocker, resource = self.missing()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(resource['template']))
        self.assertEqual('blocker', self.step()['kind'], 'Unfilled instructions must not manufacture eligibility')
        for kind in ('contract_investigation', 'owner_attestation'):
            with self.subTest(kind=kind):
                path.write_text(json.dumps(self.filled(resource, kind)))
                resumed = self.step()
                self.assertNotEqual('blocker', resumed['kind'])
                self.assertEqual('replace_reset', resumed['input_envelope']['provider']['snapshot']['migration']['decision']['action'])

    def test_preparation_resource_is_stable_and_refreshes_with_facts_and_spec(self):
        path, first, resource = self.missing()
        same = self.step(); self.resource(same)
        self.assertEqual(first['preparation'], same['preparation'])
        self.fixture.observation['releases'][0]['commit'] = 'e' * 40
        changed = self.step(); new_resource = self.resource(changed)
        self.assertNotEqual(first['preparation'], changed['preparation'])
        self.assertNotEqual(resource['template']['release_snapshot'], new_resource['template']['release_snapshot'])
        managed = z.parse_managed_goal(self.adapter.issue['body'], 42)
        self.adapter.issue['body'] = z.render_managed_goal(managed, self.fixture.goal['human_spec'] + '\nAdditional synthetic contract constraint.\n', 42)
        rebound = self.step(); self.resource(rebound)
        self.assertNotEqual(changed['preparation'], rebound['preparation'])
        self.assertNotEqual(changed['input_envelope']['goal_spec'], rebound['input_envelope']['goal_spec'])

    def test_discovered_route_blocks_foreign_stale_ambiguous_and_unavailable_evidence(self):
        path, blocker, resource = self.missing()
        path.parent.mkdir(parents=True, exist_ok=True)
        valid = self.filled(resource)
        for mutate in (lambda d: d.update(goal=43), lambda d: d.update(goal_spec='sha256:' + 'f' * 64),
                       lambda d: d['contracts'][0].update(status='unknown')):
            document = copy.deepcopy(valid); mutate(document); path.write_text(json.dumps(document))
            self.assertEqual('blocker', self.step()['kind'])
        path.write_text(json.dumps(valid)); self.assertNotEqual('blocker', self.step()['kind'])
        self.fixture.observation = {'status': 'unavailable', 'releases': None}
        unavailable = self.step(); self.assertEqual('blocker', unavailable['kind']); self.resource(unavailable)
        self.assertIn('submission', unavailable)
        self.assertEqual('block', unavailable['submission']['operation'])
