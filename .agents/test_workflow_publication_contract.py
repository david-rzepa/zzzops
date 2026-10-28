"""Contracts for deterministic work bases and provider-bound publication."""

import importlib.util
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# Bootstrap the production module aliases before loading the isolated adapter.
import test_zzzops as fixtures


MODULE_PATH = Path(__file__).parents[1] / "plugins" / "zzzops" / "zzzops" / "workflow.py"
SPEC = importlib.util.spec_from_file_location("workflow_publication_contract_subject", MODULE_PATH)
workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(workflow)


class StepAPI:
    @staticmethod
    def workflow_step_plan(*_args, **_kwargs):
        return {
            "next_steps": [{
                "kind": "execute", "phase": "implement", "assignment": "delegate",
                "selection": {"model": "worker-model", "effort": "medium"},
            }],
            "frontier": {"blocked": []},
        }

    @staticmethod
    def _workflow_phase_configuration(_project, _goal):
        return {"phases": [{"id": "implement"}]}, {}

    @staticmethod
    def workflow_live_inputs(_repo, _project, _goal, _intent, _graph):
        return {"plan": {"goal_spec": "sha256:" + "1" * 64,
                         "policy": "sha256:" + "2" * 64,
                         "phase_dag": "sha256:" + "3" * 64}}

    @staticmethod
    def _workflow_section(_project, _section):
        return {"configuration": {}}

    @staticmethod
    def workflow_instruction(name):
        return {"name": name}


class PublicationAPI:
    def __init__(self):
        self.calls = []

    def linear_publication_next_step(self, ordered, candidate, *, trunk):
        self.calls.append((ordered, candidate, trunk))
        return {"action": "publish_linear"}


class WorkflowPublicationContractTests(unittest.TestCase):
    def test_stack_member_rejects_unresolved_findings_before_dispatch(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.node_snapshot = lambda _goal: {
            'payload': {'operational': {'leases': []}},
            'projection': {'unresolved_obligations': [(7, 'changed-contract')]},
        }
        with self.assertRaisesRegex(ValueError, 'unresolved findings: changed-contract'):
            engine.node_stack_member_snapshot({'goal': 7})

    def test_stack_observation_requires_exact_merge_commit_and_time(self):
        facts = {'merge_commit': 'a' * 40, 'merged_at': '2026-10-24T00:00:00Z'}
        self.assertEqual(('a' * 40, facts['merged_at']),
                         workflow.Workflow.node_stack_verified_merge(facts))
        for changed in ({'merge_commit': None}, {'merged_at': None},
                        {'merged_at': '2026-10-24T00:00:00'}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                workflow.Workflow.node_stack_verified_merge({**facts, **changed})

    def test_native_delivery_is_derived_from_goal_evidence(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        proof = {'hash': 'proof'}
        output = {'hash': 'output'}
        result = {'hash': 'result'}
        artifacts = {
            'result': {'content': {'node': {'goal': 7}, 'outputs': {'value': output}}},
            'output': {'provenance': {'source': proof}},
            'proof': {'kind': 'git_phase_proof'},
        }
        snapshot = {'number': 7, 'payload': {'evidence': [result]}, 'artifacts': artifacts}
        self.assertTrue(engine.node_native_delivery(snapshot))
        artifacts['proof']['kind'] = 'repository_workspace_proof'
        self.assertFalse(engine.node_native_delivery(snapshot))

    def test_native_sources_require_current_phase_results(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        artifacts = {}
        current = {}
        for phase, commit in (('test_design', 'c' * 40), ('implement', 'd' * 40)):
            output = {'hash': phase + '-output'}
            proof = {'hash': phase + '-proof'}
            artifacts[output['hash']] = {'provenance': {'source': proof}}
            artifacts[proof['hash']] = {'kind': 'git_phase_proof',
                                        'checkpoint': {'result_commit': commit}}
            current[phase] = ({'hash': phase + '-result'},
                              {'node': {'goal': 7, 'node': phase}, 'outputs': {'value': output}})
        snapshot = {'number': 7, 'projection': {'current': current}, 'artifacts': artifacts}
        self.assertEqual({'test_source': 'c' * 40, 'implementation_source': 'd' * 40},
                         engine.node_native_sources(snapshot))
        del current['test_design']
        with self.assertRaisesRegex(ValueError, 'current reviewed RED and GREEN'):
            engine.node_native_sources(snapshot)

    def test_compaction_inputs_derive_from_current_proofs_and_retained_history(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.repo = Path('/repo')
        engine.node_native_sources = lambda _snapshot: {
            'test_source': 'c' * 40, 'implementation_source': 'd' * 40}
        artifacts, current, evidence, workspaces = {}, {}, [], {}
        for phase, commit, owned in (('test_design', 'c' * 40, ['behavior_test.py']),
                                     ('implement', 'd' * 40, ['source.py'])):
            output = {'hash': phase + '-output'}
            proof = {'hash': phase + '-proof'}
            result = {'hash': phase + '-result'}
            ref = f'refs/heads/zzzops/attempts/7/{phase}/' + ('a' if phase == 'test_design' else 'b') * 32
            artifacts[output['hash']] = {'provenance': {'source': proof}}
            artifacts[proof['hash']] = {'kind': 'git_phase_proof', 'retained_ref': ref,
                                        'checkpoint': {'result_commit': commit}}
            value = {'node': {'goal': 7, 'node': phase}, 'outputs': {'value': output}}
            artifacts[result['hash']] = {'content': value}
            current[phase] = (result, value)
            evidence.append(result)
            workspaces[phase] = {'git_workspace': True, 'entry': {'owned': owned}}
        recovery = {'hash': 'recovery-response'}
        recovered_ref = 'refs/heads/zzzops/attempts/7/test_design/' + 'f' * 32
        recovered = {'next_steps': [{'kind': 'checkpoint', 'goal': 7,
                                     'retained_attempt': {'ref': recovered_ref,
                                                          'commit': 'f' * 40}}]}
        snapshot = {'number': 7, 'graph': {'nodes': []}, 'projection': {'current': current},
                    'payload': {'evidence': evidence, 'operational': {'receipts': []}},
                    'artifacts': artifacts, 'workspaces': workspaces,
                    'resolve': lambda ref: recovered if ref == recovery else artifacts[ref['hash']]}
        snapshot['payload']['operational']['receipts'].append({'result': recovery})
        with mock.patch.object(workflow.git_phase_state, 'compaction_base_from_attempts',
                               return_value='e' * 40) as derive:
            inputs = engine.node_compaction_inputs(snapshot)
        self.assertEqual('e' * 40, inputs['base_commit'])
        self.assertEqual(['behavior_test.py'], inputs['test_owned'])
        self.assertEqual(['source.py'], inputs['implementation_owned'])
        self.assertEqual(3, len(inputs['retained_attempts']))
        self.assertIn({'ref': recovered_ref, 'commit': 'f' * 40}, inputs['retained_attempts'])
        derive.assert_called_once()

    def test_composition_inputs_derive_one_reviewed_integration_source(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.repo = Path('/repo')
        output = {'hash': 'integration-output'}
        proof = {'hash': 'integration-proof'}
        result = {'hash': 'integration-result'}
        source = 'd' * 40
        ref = 'refs/heads/zzzops/attempts/7/integration_verification/' + 'a' * 32
        content = {'node': {'goal': 7, 'node': 'integration_verification'},
                   'outputs': {'value': output}}
        snapshot = {'number': 7, 'graph': {'nodes': []},
            'projection': {'current': {'integration': (result, content)}},
            'payload': {'evidence': [result], 'operational': {'receipts': []}},
            'artifacts': {output['hash']: {'provenance': {'source': proof}},
                          proof['hash']: {'kind': 'git_phase_proof', 'retained_ref': ref,
                              'checkpoint': {'result_commit': source}},
                          result['hash']: {'content': content}},
            'workspaces': {'integration': {'git_workspace': True,
                'entry': {'owned': ['integration.txt']}}}}
        with mock.patch.object(workflow.git_phase_state, 'compaction_base_from_attempts',
                               return_value='b' * 40) as derive:
            inputs = engine.node_compaction_inputs(snapshot)
        self.assertEqual('composition', inputs['delivery_class'])
        self.assertEqual(source, inputs['integration_source'])
        self.assertEqual(['integration.txt'], inputs['integration_owned'])
        self.assertEqual([{'ref': ref, 'commit': source}], inputs['retained_attempts'])
        derive.assert_called_once_with(Path('/repo'), goal=7, test_source=source,
            attempts=[{'ref': ref, 'commit': source}], remote='origin',
            phase='integration_verification')

    def test_compaction_requires_current_root_repository_authorization(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.runtime = {'root_id': 'root'}
        engine.node_authorization_policy_matches = lambda *_args: True
        authorization = {'hash': 'authorization'}
        manifest = {'hash': 'manifest'}
        implementation = {'hash': 'implementation'}
        review = {'hash': 'review'}
        artifacts = {
            'authorization': {'type': 'repository_authorization', 'content': {
                'decision': 'approved', 'manifest': manifest}},
            'manifest': {'type': 'delivery_candidate', 'content': {
                'delivery_class': 'leaf', 'candidate': implementation}},
            'review': {'content': {'one': {'decision': 'approved'}}},
        }
        auth_result = {'node': {'goal': 7, 'node': 'authorize_repository'},
                       'executor': 'root', 'outputs': {'authorization': authorization},
                       'inputs': [{'name': 'approved_implementation_reviews', 'source': review}]}
        implementation_result = {'node': {'goal': 7, 'node': 'implement'},
                                 'outputs': {'value': implementation}}
        current = {'authorize': ({'hash': 'auth-result'}, auth_result),
                   'select': ({'hash': 'selection-result'}, {'node': {'goal': 7, 'node': 'select_delivery_candidate'},
                                                           'outputs': {'value': manifest}}),
                   'implement': ({'hash': 'implementation-result'}, implementation_result)}
        states = {'authorize': {'contract': {'executor': {'role': 'root'}}}}
        snapshot = {'number': 7, 'graph': {'nodes': []},
                    'projection': {'current': current, 'states': states},
                    'artifacts': artifacts}
        self.assertEqual(authorization,
                         engine.node_compaction_authorization(snapshot, authorization))
        artifacts['review']['content']['one']['decision'] = 'changes_requested'
        with self.assertRaisesRegex(ValueError, 'approved independent reviews'):
            engine.node_compaction_authorization(snapshot, authorization)

    def test_composition_compaction_requires_current_integration_review(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.runtime = {'root_id': 'root'}
        engine.node_authorization_policy_matches = lambda *_args: True
        authorization = {'hash': 'authorization'}
        manifest = {'hash': 'manifest'}
        integration = {'hash': 'integration'}
        review = {'hash': 'review'}
        artifacts = {
            'authorization': {'type': 'repository_authorization', 'content': {
                'decision': 'approved', 'manifest': manifest}},
            'manifest': {'type': 'delivery_candidate', 'content': {
                'delivery_class': 'composition', 'candidate': integration}},
            'review': {'content': {'one': {'decision': 'approved'}}},
        }
        result = {'node': {'goal': 7, 'node': 'authorize_repository'},
                  'executor': 'root', 'outputs': {'authorization': authorization},
                  'inputs': [{'name': 'approved_integration_reviews', 'source': review}]}
        current = {'authorize': ({'hash': 'auth-result'}, result),
                   'select': ({'hash': 'selection-result'}, {'node': {'goal': 7,
                       'node': 'select_delivery_candidate'},
                       'outputs': {'value': manifest}}),
                   'integration': ({'hash': 'integration-result'}, {'node': {'goal': 7,
                       'node': 'integration_verification'},
                       'outputs': {'value': integration}})}
        snapshot = {'number': 7, 'graph': {'nodes': []},
            'projection': {'current': current,
            'states': {'authorize': {'contract': {'executor': {'role': 'root'}}}}},
            'artifacts': artifacts}
        self.assertEqual(authorization,
                         engine.node_compaction_authorization(snapshot, authorization))
        artifacts['review']['content']['one']['decision'] = 'changes_requested'
        with self.assertRaisesRegex(ValueError, 'approved independent reviews'):
            engine.node_compaction_authorization(snapshot, authorization)

    def test_candidate_compaction_uses_managed_branch_and_returns_bounded_receipt(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.repo = Path('/repo')
        authorization = {'hash': 'sha256:' + 'a' * 64, 'uri': 'urn:sha256:' + 'a' * 64}
        engine.node_compaction_authorization = lambda _snapshot, ref: ref
        engine.node_compaction_inputs = lambda _snapshot: {
            'goal': 7, 'base_commit': 'b' * 40, 'test_source': 'c' * 40,
            'implementation_source': 'd' * 40, 'test_owned': ['behavior_test.py'],
            'implementation_owned': ['source.py'], 'retained_attempts': []}
        engine.node_persist = lambda _snapshot, _payload, response, _request: response
        snapshot = {'number': 7}
        payload = {'operational': {'leases': []}}
        request = {'operation': 'compact_candidate', 'request_id': 'compact-7',
                   'authorization': authorization}
        worktree = {'status': 'clean', 'path': '/repo/.zzzops/worktrees/7/candidate/' + 'a' * 32,
                    'branch': 'zzzops/goal-7/candidate/' + 'a' * 32, 'head': 'd' * 40}
        preview = {'branch_ref': 'refs/heads/' + worktree['branch']}
        pair = {'outcome': 'created', 'test_commit': 'e' * 40,
                'implementation_commit': 'f' * 40}
        with mock.patch.object(workflow.managed_worktrees, 'inspect_attempt_worktree',
                               side_effect=[{'status': 'missing'}, worktree]) as inspect, \
             mock.patch.object(workflow.managed_worktrees, 'prepare_worktree') as prepare, \
             mock.patch.object(workflow.git_phase_state, 'preview_two_commit_candidate',
                               return_value=preview) as preview_call, \
             mock.patch.object(workflow.git_phase_state, 'apply_two_commit_candidate',
                               return_value=pair):
            response = engine.node_compact_candidate(snapshot, payload, request)
        prepare.assert_called_once_with(Path('/repo'), goal=7, node='candidate',
                                        attempt='a' * 32, base_commit='d' * 40)
        self.assertEqual(2, inspect.call_count)
        preview_call.assert_called_once()
        step = response['next_steps'][0]
        self.assertEqual('candidate_compacted', step['kind'])
        self.assertEqual('f' * 40, step['head_oid'])
        self.assertNotIn('retained_attempts', step)

    def test_composition_compaction_uses_single_commit_contract(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.repo = Path('/repo')
        auth = {'hash': 'sha256:' + 'a' * 64, 'uri': 'urn:sha256:' + 'a' * 64}
        engine.node_compaction_authorization = lambda _snapshot, ref: ref
        engine.node_compaction_inputs = lambda _snapshot: {
            'goal': 7, 'delivery_class': 'composition',
            'base_commit': 'b' * 40, 'integration_source': 'c' * 40,
            'integration_owned': ['integration.txt'], 'retained_attempts': []}
        engine.node_persist = lambda _snapshot, _payload, response, _request: response
        worktree = {'status': 'clean', 'path': '/repo/.zzzops/worktrees/7/candidate/' + 'a' * 32,
                    'branch': 'zzzops/goal-7/candidate/' + 'a' * 32, 'head': 'c' * 40}
        with mock.patch.object(workflow.managed_worktrees, 'inspect_attempt_worktree',
                               side_effect=[{'status': 'missing'}, worktree]), \
             mock.patch.object(workflow.managed_worktrees, 'prepare_worktree') as prepare, \
             mock.patch.object(workflow.git_phase_state, 'preview_single_commit_candidate',
                               return_value={'branch_ref': 'refs/heads/' + worktree['branch']}) as preview, \
             mock.patch.object(workflow.git_phase_state, 'apply_single_commit_candidate',
                               return_value={'outcome': 'created', 'candidate_commit': 'd' * 40}) as apply:
            response = engine.node_compact_candidate({'number': 7},
                {'operational': {'leases': []}},
                {'operation': 'compact_candidate', 'request_id': 'composition-7',
                 'authorization': auth})
        prepare.assert_called_once_with(Path('/repo'), goal=7, node='candidate',
                                        attempt='a' * 32, base_commit='c' * 40)
        preview.assert_called_once()
        apply.assert_called_once()
        step = response['next_steps'][0]
        self.assertEqual('d' * 40, step['head_oid'])
        self.assertNotIn('test_commit', step)

    def test_candidate_readiness_is_inferred_from_exact_managed_head(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.repo = Path('/repo')
        auth = {'hash': 'sha256:' + 'a' * 64}
        engine.node_compaction_authorization = lambda _snapshot, ref: ref
        engine.node_native_sources = lambda _snapshot: {
            'test_source': 'c' * 40, 'implementation_source': 'd' * 40}
        engine.node_compaction_inputs = lambda _snapshot: {
            'goal': 7, 'base_commit': 'b' * 40, 'test_source': 'c' * 40,
            'implementation_source': 'd' * 40, 'test_owned': ['behavior_test.py'],
            'implementation_owned': ['source.py'], 'retained_attempts': []}
        snapshot = {'number': 7, 'artifacts': {auth['hash']: {
            'type': 'repository_authorization'}},
            'projection': {'current': {'auth': ({'hash': 'result'},
                {'outputs': {'authorization': auth}})}}}
        with mock.patch.object(workflow.managed_worktrees, 'inspect_attempt_worktree',
                               return_value={'status': 'missing'}):
            self.assertEqual('needs_compaction', engine.node_candidate_state(snapshot)['status'])
        observed = {'status': 'clean', 'path': '/repo/candidate',
                    'branch': 'zzzops/goal-7/candidate/' + 'a' * 32, 'head': 'f' * 40}
        with mock.patch.object(workflow.managed_worktrees, 'inspect_attempt_worktree',
                               return_value=observed), \
             mock.patch.object(workflow.git_phase_state, 'preview_two_commit_candidate'), \
             mock.patch.object(workflow.git_phase_state, 'verify_two_commit_candidate',
                               return_value={'test_source': 'c' * 40,
                                             'implementation_source': 'd' * 40}):
            self.assertEqual({
                'status': 'ready', 'authorization': auth,
                'path': observed['path'], 'branch': observed['branch'],
                'head_oid': observed['head'],
            }, engine.node_candidate_state(snapshot))
        with mock.patch.object(workflow.managed_worktrees, 'inspect_attempt_worktree',
                               return_value={**observed, 'status': 'dirty'}):
            with self.assertRaisesRegex(ValueError, 'dirty'):
                engine.node_candidate_state(snapshot)

    def test_composition_readiness_uses_one_commit_and_current_source(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.repo = Path('/repo')
        auth = {'hash': 'sha256:' + 'a' * 64}
        source = 'c' * 40
        engine.node_compaction_authorization = lambda _snapshot, ref: ref
        engine.node_composition_source = lambda _snapshot: source
        engine.node_compaction_inputs = lambda _snapshot: {
            'goal': 7, 'delivery_class': 'composition', 'base_commit': 'b' * 40,
            'integration_source': source, 'integration_owned': ['integration.txt'],
            'retained_attempts': []}
        snapshot = {'number': 7, 'artifacts': {auth['hash']: {
            'type': 'repository_authorization'}},
            'projection': {'current': {'auth': ({'hash': 'result'},
                {'outputs': {'authorization': auth}})}}}
        observed = {'status': 'clean', 'path': '/repo/candidate',
                    'branch': 'zzzops/goal-7/candidate/' + 'a' * 32, 'head': 'd' * 40}
        with mock.patch.object(workflow.managed_worktrees, 'inspect_attempt_worktree',
                               return_value=observed), \
             mock.patch.object(workflow.git_phase_state, 'preview_single_commit_candidate') as preview, \
             mock.patch.object(workflow.git_phase_state, 'verify_single_commit_candidate',
                               return_value={'source_commit': source}) as verify:
            self.assertEqual('ready', engine.node_candidate_state(snapshot)['status'])
        preview.assert_called_once()
        verify.assert_called_once()

    def test_post_merge_cleanup_preserves_dirty_local_attempts(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.repo = Path('/repo')
        engine.node_compaction_inputs = lambda _snapshot: {
            'base_commit': 'b' * 40,
            'retained_attempts': [{'ref': 'refs/heads/zzzops/attempts/7/test_design/' + 'a' * 32,
                                   'commit': 'c' * 40}]}
        engine.node_compaction_authorization = lambda _snapshot, ref: ref
        auth = {'hash': 'sha256:' + 'f' * 64}
        facts = {'merged': True, 'merge_commit': 'e' * 40,
                 'head_oid': 'd' * 40, 'base_ref': 'dev'}
        snapshot = {'number': 7, 'artifacts': {auth['hash']: {'type': 'repository_authorization'}},
                    'payload': {'operational': {'receipts': []}},
                    'projection': {'states': {
                        'merge': {'node': {'goal': 7}, 'publication': {'provider': facts}},
                        'related_merge': {'node': {'goal': 8}, 'publication': {'provider': {
                            **facts, 'merge_commit': '9' * 40}}}},
                                   'current': {'auth': ({'hash': 'result'},
                                       {'outputs': {'authorization': auth}})}}}
        def run(command, **_kwargs):
            if command[1:3] == ['rev-parse', 'FETCH_HEAD']:
                return SimpleNamespace(returncode=0, stdout='e' * 40)
            return SimpleNamespace(returncode=0, stdout='')
        with mock.patch.object(workflow.subprocess, 'run', side_effect=run), \
             mock.patch.object(workflow.git_phase_state, 'verify_two_commit_candidate'), \
             mock.patch.object(workflow.managed_worktrees, 'inspect_attempt_worktree',
                               side_effect=[{'status': 'clean'}, {'status': 'dirty'}]), \
             mock.patch.object(workflow.managed_worktrees,
                               'cleanup_delivered_attempt_worktree') as cleanup:
            outcome = engine.node_cleanup_delivered_worktrees(snapshot)
        self.assertEqual({'status': 'preserved_dirty', 'removed': 1,
                          'preserved_dirty': 1}, outcome)
        cleanup.assert_called_once()

    def test_composition_cleanup_verifies_one_commit_and_retains_remote_attempt(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.repo = Path('/repo')
        ref = 'refs/heads/zzzops/attempts/7/integration_verification/' + 'a' * 32
        engine.node_compaction_inputs = lambda _snapshot: {
            'delivery_class': 'composition', 'base_commit': 'b' * 40,
            'retained_attempts': [{'ref': ref, 'commit': 'c' * 40}]}
        engine.node_compaction_authorization = lambda _snapshot, reference: reference
        auth = {'hash': 'sha256:' + 'f' * 64}
        facts = {'merged': True, 'merge_commit': 'e' * 40,
                 'head_oid': 'd' * 40, 'base_ref': 'dev'}
        snapshot = {'number': 7, 'artifacts': {auth['hash']: {
            'type': 'repository_authorization'}},
            'payload': {'operational': {'receipts': [{'result': {'hash': 'readonly-receipt'}}]}},
            'resolve': lambda _ref: {'next_steps': [{'kind': 'perform', 'lease': {
                'node': {'goal': 7, 'node': 'understand'}, 'attempt': 'b' * 32,
                'acquisition': {'read_commit': 'b' * 40}}}]},
            'projection': {'states': {'merge': {'node': {'goal': 7}, 'publication': {'provider': facts}}},
                           'current': {'auth': ({'hash': 'result'},
                               {'outputs': {'authorization': auth}})}}}
        def run(command, **_kwargs):
            if command[1:3] == ['rev-parse', 'FETCH_HEAD']:
                return SimpleNamespace(returncode=0, stdout='e' * 40)
            return SimpleNamespace(returncode=0, stdout='')
        with mock.patch.object(workflow.subprocess, 'run', side_effect=run), \
             mock.patch.object(workflow.git_phase_state,
                               'verify_single_commit_candidate') as verify, \
             mock.patch.object(workflow.managed_worktrees, 'inspect_attempt_worktree',
                               side_effect=[{'status': 'clean'}, {'status': 'clean'},
                                            {'status': 'clean'}]), \
             mock.patch.object(workflow.managed_worktrees,
                               'cleanup_delivered_attempt_worktree') as attempt_cleanup, \
             mock.patch.object(workflow.managed_worktrees,
                               'cleanup_delivered_candidate_worktree') as candidate_cleanup, \
             mock.patch.object(workflow.managed_worktrees,
                               'cleanup_delivered_readonly_worktree') as readonly_cleanup:
            self.assertEqual(3, engine.node_cleanup_delivered_worktrees(snapshot)['removed'])
        verify.assert_called_once()
        self.assertEqual('composition', attempt_cleanup.call_args.kwargs['delivery_class'])
        self.assertEqual(ref, attempt_cleanup.call_args.kwargs['retained_ref'])
        self.assertEqual('composition', candidate_cleanup.call_args.kwargs['delivery_class'])
        self.assertEqual('b' * 40, readonly_cleanup.call_args.kwargs['expected_head'])

    def test_grouped_cleanup_uses_declared_node_and_exact_group_proof(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.repo = Path('/repo')
        ref = 'refs/heads/zzzops/attempts/7/custom_check/' + 'a' * 32
        groups = [{'id': 'checks', 'order': 0, 'commit_type': 'test',
                   'summary': 'reviewed checks', 'nodes': [{
                       'node': 'custom_check', 'source': 'c' * 40,
                       'owned': ['checks.py']}]}]
        attempts = [{'ref': ref, 'commit': 'c' * 40}]
        engine.node_compaction_inputs = lambda _snapshot: {
            'delivery_class': 'grouped', 'base_commit': 'b' * 40,
            'groups': groups, 'retained_attempts': attempts}
        engine.node_compaction_authorization = lambda _snapshot, reference: reference
        auth = {'hash': 'sha256:' + 'f' * 64}
        facts = {'merged': True, 'merge_commit': 'e' * 40,
                 'head_oid': 'd' * 40, 'base_ref': 'dev'}
        snapshot = {'number': 7, 'artifacts': {auth['hash']: {
            'type': 'repository_authorization'}},
            'payload': {'operational': {'receipts': []}},
            'projection': {'states': {'merge': {'node': {'goal': 7}, 'publication': {'provider': facts}}},
                           'current': {'auth': ({'hash': 'result'},
                               {'outputs': {'authorization': auth}})}}}
        def run(command, **_kwargs):
            if command[1:3] == ['rev-parse', 'FETCH_HEAD']:
                return SimpleNamespace(returncode=0, stdout='e' * 40)
            return SimpleNamespace(returncode=0, stdout='')
        with mock.patch.object(workflow.subprocess, 'run', side_effect=run), \
             mock.patch.object(workflow.git_phase_state,
                               'verify_grouped_candidate') as verify, \
             mock.patch.object(workflow.managed_worktrees, 'inspect_attempt_worktree',
                               side_effect=[{'status': 'clean'}, {'status': 'clean'}]), \
             mock.patch.object(workflow.managed_worktrees,
                               'cleanup_delivered_attempt_worktree') as attempt_cleanup, \
             mock.patch.object(workflow.managed_worktrees,
                               'cleanup_delivered_candidate_worktree') as candidate_cleanup:
            self.assertEqual(2, engine.node_cleanup_delivered_worktrees(snapshot)['removed'])
        verify.assert_called_once()
        self.assertEqual('custom_check', attempt_cleanup.call_args.kwargs['node'])
        self.assertEqual(groups, candidate_cleanup.call_args.kwargs['groups'])

    def test_legacy_delivery_cleans_commit_pinned_readonly_attempt(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.repo = Path('/repo')
        facts = {'merged': True, 'merge_commit': 'e' * 40,
                 'head_oid': 'd' * 40, 'base_ref': 'dev'}
        snapshot = {'number': 7, 'projection': {'states': {
            'merge': {'node': {'goal': 7}, 'publication': {'provider': facts}}}},
            'payload': {'operational': {'receipts': [{'result': {'hash': 'receipt'}}]}},
            'resolve': lambda _ref: {'next_steps': [{'kind': 'perform', 'lease': {
                'node': {'goal': 7, 'node': 'understand'}, 'attempt': 'a' * 32,
                'acquisition': {'read_commit': 'b' * 40}}}]}}
        def run(command, **_kwargs):
            if command[1:3] == ['rev-parse', 'FETCH_HEAD']:
                return SimpleNamespace(returncode=0, stdout='e' * 40)
            return SimpleNamespace(returncode=0, stdout='')
        with mock.patch.object(workflow.subprocess, 'run', side_effect=run), \
             mock.patch.object(workflow.managed_worktrees, 'inspect_attempt_worktree',
                               return_value={'status': 'clean'}), \
             mock.patch.object(workflow.managed_worktrees,
                               'cleanup_delivered_readonly_worktree') as cleanup:
            result = engine.node_cleanup_delivered_readonly_worktrees(snapshot)
        self.assertEqual({'status': 'complete', 'removed': 1, 'preserved_dirty': 0}, result)
        cleanup.assert_called_once_with(Path('/repo'), goal=7, node='understand',
            attempt='a' * 32, expected_head='b' * 40, integrated_commit='e' * 40)

    def test_legacy_delivery_without_readonly_attempts_needs_no_git_cleanup(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.repo = Path('/repo')
        snapshot = {'number': 7, 'payload': {'operational': {'receipts': []}}}
        with mock.patch.object(workflow.subprocess, 'run',
                               side_effect=AssertionError('unnecessary Git fetch')):
            self.assertEqual({'status': 'complete', 'removed': 0,
                              'preserved_dirty': 0},
                             engine.node_cleanup_delivered_readonly_worktrees(snapshot))

    def legacy_project(self):
        dag = json.loads((Path(__file__).parent / 'fixtures/legacy_phase_dag.json').read_text())
        return {'policy': {'sections': [{'id': 'workflow_adherence', 'configuration': {'phase_dag': dag}}]}}

    def git(self, repo, *args):
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True,
        ).stdout.strip()


    def publication_engine(self, *, local_head, local_base, provider_head, provider_base):
        api = PublicationAPI()
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.api, engine.repo = api, Path("/repo")
        engine.project = self.legacy_project()
        engine.portfolio = lambda: [{"key": 7, "parent": 1, "implementation": {"branch": "goal-7"}}]
        engine.publication_identity = lambda _goal: {
            "head_oid": provider_head, "base_oid": provider_base, "base_ref": "dev",
        }

        def run(command, **_kwargs):
            if command[:3] == ["gh", "pr", "list"]:
                return SimpleNamespace(stdout=json.dumps([{
                    "headRefName": "goal-7", "baseRefName": "dev", "headRefOid": provider_head,
                }]))
            if command[:2] == ["git", "rev-parse"]:
                return SimpleNamespace(stdout=(local_head if command[2] == "goal-7" else local_base) + "\n")
            raise AssertionError(command)

        return engine, api, run

    def goal(self):
        return {
            "key": 7, "parent": 1,
            "implementation": {
                "branch": "goal-7", "base": "dev", "target": "dev",
                "pr": "https://example.test/pull/7",
            },
        }

    def test_provider_head_or_base_drift_requires_local_sync(self):
        provider_head, provider_base = "a" * 40, "b" * 40
        cases = (("c" * 40, provider_base), (provider_head, "d" * 40))
        for local_head, local_base in cases:
            with self.subTest(local_head=local_head, local_base=local_base):
                engine, api, run = self.publication_engine(
                    local_head=local_head, local_base=local_base,
                    provider_head=provider_head, provider_base=provider_base,
                )
                with mock.patch.object(workflow.subprocess, "run", side_effect=run), \
                     mock.patch.object(workflow.git_phase_state, 'classify_base_move',
                                       side_effect=ValueError('base observation unavailable')):
                    result = engine.publication_gate(self.goal())
                self.assertEqual("repair_stack", result["kind"])
                self.assertIn("Synchronize", result["action"])
                self.assertEqual(provider_head, result["head"])
                self.assertEqual(provider_base, result["base"])
                self.assertEqual([], api.calls)

    def test_equivalent_tree_base_advance_requests_fetch_without_staling(self):
        head, old_base, new_base = 'a' * 40, 'b' * 40, 'c' * 40
        engine, api, run = self.publication_engine(
            local_head=head, local_base=old_base,
            provider_head=head, provider_base=new_base)
        movement = {'action': 'retarget_only', 'old_base': old_base,
                    'new_base': new_base, 'old_tree': 'd' * 40,
                    'new_tree': 'd' * 40, 'preserves_ancestry': True}
        with mock.patch.object(workflow.subprocess, 'run', side_effect=run), \
             mock.patch.object(workflow.git_phase_state, 'classify_base_move',
                               return_value=movement) as classify:
            result = engine.publication_gate(self.goal())
        classify.assert_called_once_with(Path('/repo'), old_base=old_base,
                                         new_base=new_base)
        self.assertEqual('repair_stack', result['kind'])
        self.assertEqual('retarget_only', result['base_movement']['action'])
        self.assertFalse(result['requires_phase_reverification'])
        self.assertIn('fetch', result['action'].lower())
        self.assertEqual([], api.calls)

    def test_changed_or_rewritten_base_previews_affected_verification(self):
        head, old_base, new_base = 'a' * 40, 'b' * 40, 'c' * 40
        for action, reverify in (('topology_rewrite', False),
                                 ('rebase_and_reverify', True)):
            with self.subTest(action=action):
                engine, api, run = self.publication_engine(
                    local_head=head, local_base=old_base,
                    provider_head=head, provider_base=new_base)
                movement = {'action': action, 'old_base': old_base,
                            'new_base': new_base,
                            'old_tree': 'd' * 40,
                            'new_tree': ('d' if not reverify else 'e') * 40,
                            'preserves_ancestry': False}
                with mock.patch.object(workflow.subprocess, 'run', side_effect=run), \
                     mock.patch.object(workflow.git_phase_state, 'classify_base_move',
                                       return_value=movement):
                    result = engine.publication_gate(self.goal())
                self.assertEqual('repair_stack', result['kind'])
                self.assertEqual(movement, result['base_movement'])
                self.assertIs(reverify, result['requires_phase_reverification'])
                self.assertIn('preview', result['action'].lower())
                self.assertEqual([], api.calls)

    def test_exact_provider_identity_drives_publication_topology(self):
        provider_head, provider_base = "a" * 40, "b" * 40
        engine, api, run = self.publication_engine(
            local_head=provider_head, local_base=provider_base,
            provider_head=provider_head, provider_base=provider_base,
        )
        with mock.patch.object(workflow.subprocess, "run", side_effect=run):
            self.assertIsNone(engine.publication_gate(self.goal()))

        self.assertEqual(1, len(api.calls))
        ordered, candidate, trunk = api.calls[0]
        self.assertEqual([], ordered)
        self.assertEqual("dev", trunk)
        self.assertEqual({
            "branch": "goal-7", "base": "dev",
            "base_head": provider_base, "head": provider_head,
        }, candidate)

    def test_independent_release_lanes_do_not_form_one_pr_fork(self):
        engine, api, _run = self.publication_engine(
            local_head='a' * 40, local_base='b' * 40,
            provider_head='a' * 40, provider_base='b' * 40)
        engine.repository = 'owner/repo'
        engine.portfolio = lambda: [
            {'key': 7, 'implementation': {'branch': 'goal-7'}},
            {'key': 8, 'implementation': {'branch': 'goal-8'}}]
        plan = {'next_release': 1, 'assignments': {'7': 1, '8': 2}}
        api._releases = SimpleNamespace(target_release=lambda value, goal: value['assignments'][str(goal)])
        api.GitHubReleasePlanAdapter = lambda *_args: SimpleNamespace(read=lambda *_args: plan)
        rows = [{'number': 7, 'headRefName': 'goal-7', 'baseRefName': 'dev', 'headRefOid': 'a' * 40},
                {'number': 8, 'headRefName': 'goal-8', 'baseRefName': 'dev', 'headRefOid': 'c' * 40}]
        def run(command, **_kwargs):
            if command[:3] == ['gh', 'pr', 'list']:
                return SimpleNamespace(stdout=json.dumps(rows))
            raise AssertionError(command)
        with mock.patch.object(workflow, 'policy_section', return_value={
                'configuration': {'release_planning': {'enabled': True}}}), \
             mock.patch.object(workflow.subprocess, 'run', side_effect=run):
            self.assertIsNone(engine.publication_topology(
                {'branch': 'goal-7', 'base': 'dev', 'target': 'dev', 'pr': None},
                {'head_oid': 'a' * 40, 'base_oid': 'b' * 40, 'base_ref': 'dev'},
                {'goal-7', 'goal-8'}, goal_number=7))
            plan['assignments']['8'] = 1
            same_lane = engine.publication_topology(
                {'branch': 'goal-7', 'base': 'dev', 'target': 'dev', 'pr': None},
                {'head_oid': 'a' * 40, 'base_oid': 'b' * 40, 'base_ref': 'dev'},
                {'goal-7', 'goal-8'}, goal_number=7)
        self.assertEqual([], api.calls[0][0])
        self.assertEqual('goal-7', api.calls[0][1]['branch'])
        self.assertEqual('repair_stack', same_lane['kind'])
        self.assertIn('multiple successors', same_lane['action'])

    def test_reviewed_release_assignment_selects_release_lane_trunk(self):
        engine, api, _run = self.publication_engine(
            local_head='a' * 40, local_base='b' * 40,
            provider_head='a' * 40, provider_base='b' * 40)
        engine.repository = 'owner/repo'
        engine.portfolio = lambda: [
            {'key': 7, 'implementation': {'branch': 'goal-7'}}]
        plan = {'next_release': 1, 'assignments': {'7': 2}}
        api._releases = SimpleNamespace(
            target_release=lambda value, goal: value['assignments'][str(goal)])
        api.GitHubReleasePlanAdapter = lambda *_args: SimpleNamespace(
            read=lambda *_args: plan)
        rows = [{'number': 7, 'headRefName': 'goal-7',
                 'baseRefName': 'release/2', 'headRefOid': 'a' * 40}]
        def run(command, **_kwargs):
            if command[:3] == ['gh', 'pr', 'list']:
                return SimpleNamespace(stdout=json.dumps(rows))
            if command[:3] == ['git', 'fetch', '--no-tags']:
                return SimpleNamespace(returncode=1, stdout='', stderr='wrong trunk')
            raise AssertionError(command)

        with mock.patch.object(workflow, 'policy_section', return_value={
                'configuration': {'release_planning': {
                    'enabled': True, 'integration_branch': 'dev',
                    'release_branch_prefix': 'release/'}}}), \
             mock.patch.object(workflow.subprocess, 'run', side_effect=run):
            self.assertIsNone(engine.publication_topology(
                {'branch': 'goal-7', 'base': 'release/2',
                 'target': 'release/2', 'pr': None},
                {'head_oid': 'a' * 40, 'base_oid': 'b' * 40,
                 'base_ref': 'release/2'},
                {'goal-7'}, goal_number=7))

        self.assertEqual(1, len(api.calls))
        ordered, candidate, trunk = api.calls[0]
        self.assertEqual([], ordered)
        self.assertEqual('release/2', trunk)
        self.assertEqual('release/2', candidate['base'])

    def test_native_published_heads_participate_in_their_release_stack(self):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.runtime = {'root_id': 'root'}
        engine.node_authorization_policy_matches = lambda *_args: True
        auth = {'hash': 'authorization'}
        published = {'hash': 'published'}
        auth_result = {'node': {'goal': 7, 'node': 'authorize_repository'},
                       'executor': 'root', 'outputs': {'authorization': auth}, 'inputs': []}
        publish_result = {'node': {'goal': 7, 'node': 'publish'}, 'executor': 'root',
                          'outputs': {'value': published},
                          'inputs': [{'source': auth, 'mode': 'identity', 'path': []}]}
        snapshot = {'projection': {'current': {'auth': ({'hash': 'r1'}, auth_result),
                                               'publish': ({'hash': 'r2'}, publish_result)},
                                   'states': {'auth': {'contract': {'executor': {'role': 'root'}}},
                                              'publish': {'contract': {'executor': {'role': 'root'}}}}},
                    'artifacts': {'authorization': {'type': 'repository_authorization',
                                                    'content': {'decision': 'approved'}},
                                  'published': {'type': 'published_candidate',
                                                'content': {'branch': 'goal-7'}}}}
        engine.node_snapshot = lambda _number, **_kwargs: snapshot
        engine.node_compaction_authorization = lambda _snapshot, ref: ref
        self.assertEqual({'goal-7'}, engine.node_authenticate_publication_candidates([7]))

    def test_merged_ancestor_retains_candidate_head_and_retargets_pr_base(self):
        engine, api, _ = self.publication_engine(
            local_head='a' * 40, local_base='b' * 40,
            provider_head='a' * 40, provider_base='b' * 40)
        candidate = {'branch': 'goal-7', 'base': 'goal-6', 'target': 'dev',
                     'pr': 'https://example.test/pull/7'}
        identity = {'head_oid': 'a' * 40, 'base_oid': 'b' * 40,
                    'base_ref': 'goal-6'}
        calls = []
        def run(command, **_kwargs):
            calls.append(command)
            if command[:3] == ['gh', 'pr', 'list']:
                return SimpleNamespace(stdout=json.dumps([{
                    'number': 7, 'headRefName': 'goal-7',
                    'baseRefName': 'goal-6', 'headRefOid': 'a' * 40}]))
            if command[:4] == ['git', 'fetch', '--no-tags', 'origin']:
                return SimpleNamespace(returncode=0)
            if command[:3] == ['git', 'rev-parse', 'FETCH_HEAD']:
                return SimpleNamespace(returncode=0, stdout='c' * 40 + '\n')
            if command[:3] == ['git', 'merge-base', '--is-ancestor']:
                return SimpleNamespace(returncode=0)
            raise AssertionError(command)
        for action, expected_retarget in (('retarget_only', True),
                                          ('rebase_and_reverify', False)):
            with self.subTest(action=action):
                movement = {'action': action,
                            'old_base': 'b' * 40, 'new_base': 'c' * 40,
                            'old_tree': 'd' * 40,
                            'new_tree': ('d' if expected_retarget else 'e') * 40,
                            'preserves_ancestry': True}
                with mock.patch.object(workflow.subprocess, 'run', side_effect=run), \
                     mock.patch.object(workflow.git_phase_state, 'classify_base_move',
                                       return_value=movement):
                    result = engine.publication_topology(candidate, identity,
                                                         {'goal-7', 'goal-6'}, goal_number=7)
                self.assertEqual('repair_stack', result['kind'])
                if expected_retarget:
                    self.assertEqual('retarget_pr_base', result['publication_directive']['action'])
                    self.assertFalse(result['requires_phase_reverification'])
                    self.assertIn('without rewriting', result['action'])
                else:
                    self.assertNotIn('publication_directive', result)
                    self.assertIn('missing', result['action'])
                self.assertEqual([], api.calls)

    def test_published_candidate_adopts_only_exact_oid_retarget_to_policy_trunk(self):
        old_base = 'main'
        new_base = 'dev'
        base_oid = 'b' * 40
        head_oid = 'a' * 40
        reference = {'hash': 'published', 'uri': 'urn:published'}
        authorization = {'hash': 'authorization', 'uri': 'urn:authorization'}
        historical = {'repository': 'owner/repo', 'branch': 'goal-1',
                      'base': old_base, 'pr': 'https://github.com/owner/repo/pull/2',
                      'head_oid': head_oid}
        facts = {'repository': 'owner/repo', 'base_ref': new_base,
                 'base_oid': base_oid, 'head_oid': head_oid,
                 'checks_present': False, 'merged': False}
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.repo = Path('/repo')
        engine.repository = 'owner/repo'
        engine.runtime = {'root_id': 'root'}
        engine.project = {'policy': {'sections': [
            {'id': 'git_review_release', 'configuration': {'release_planning': {
                'enabled': False, 'integration_branch': new_base}}},
            {'id': 'verification_testing', 'configuration': {'required_ci': 'disabled'}},
        ]}}
        engine.api = SimpleNamespace(_phase_evidence=None,
                                     _github_pull_request_states=lambda *_args:
                                     ({1: facts}, None, None))
        engine.node_evidence_policy = lambda: 'sha256:' + 'c' * 64
        engine.node_managed_publication_branches = lambda *_args: set()
        engine.publication_topology = lambda *_args, **_kwargs: None
        publisher = {'executor': 'root', 'outputs': {'value': reference},
                     'inputs': [{'source': authorization, 'mode': 'identity', 'path': []}]}
        projection = {'current': {'publish': (reference, publisher)}, 'states': {
            'publish': {'state': 'done', 'contract': {'executor': {'role': 'root',
                                                                 'resources': []}}},
            (1, 'integrate'): {'state': 'ready', 'contract': {'executor': {
                'resources': ['repository_publication']}},
                'inputs': [{'source': reference, 'mode': 'identity', 'path': []}]},
        }}
        artifacts = {'published': {'type': 'published_candidate', 'content': historical},
                     'authorization': {'type': 'repository_authorization',
                                       'content': {'decision': 'approved'}}}

        def observe(old_oid):
            output = f'{old_oid}\trefs/heads/main\n{base_oid}\trefs/heads/dev\n'
            with mock.patch.object(workflow.subprocess, 'run',
                                   return_value=SimpleNamespace(returncode=0, stdout=output)):
                return engine.node_publication_context({}, projection, artifacts)

        adopted = observe(base_oid)[(1, 'integrate')]
        self.assertNotIn('error', adopted)
        self.assertEqual(new_base, adopted['observed']['base_ref'])
        self.assertEqual(new_base, adopted['context']['base'])
        self.assertEqual(old_base, artifacts['published']['content']['base'])
        rejected = observe('d' * 40)[(1, 'integrate')]
        self.assertIn('base identity mismatch', rejected['error'])
        engine.project['policy']['sections'][0]['configuration']['release_planning'] = None
        unsupported = observe(base_oid)[(1, 'integrate')]
        self.assertIn('base identity mismatch', unsupported['error'])


from test_evidence_dag_journeys import DagFixture, REF_TYPE, FINDING_TYPE, ADMISSION_TYPE, content_hash, output, shape, spec_input, z
import test_evidence_dag_journeys as dag_fixtures
from test_evidence_dag import task, selector, scope


class GenericPublicationPublicTests(DagFixture):
    """Finite adapter wire proposal; no domain phase or envelope metadata.

    repository_context is {branch,base,target,pr:null|string}. Its authenticated
    root output needs configured independent review and current root authorization.
    repository_authorization is {context:Ref,policy:Hash,decision:'approved'}.
    publication_evidence is {repository,pr,head_oid,base_oid,base_ref,ci}, where ci is
    verified|unverified|absent|unknown. Negative observations remain recordable;
    authorization/effects/completion enforce CI. Absent requires known complete
    provider evidence; unknown/incomplete is never absent. The adapter
    obtains provider facts, exact CI and policy itself. Caller booleans confer none.
    publication_authorization is {subject:Ref,review:Ref,policy,decision:'approved'}.
    Operational integrate accepts authorization:Ref and expected_head, and cannot
    issue missing semantic Results. All such calls target a synthetic provider.
    """

    def setUp(self):
        super().setUp()
        self.setup_publication()

    setup_relationship_transport = dag_fixtures.RelationshipPublicTests.setup_relationship_transport
    envelope_for = dag_fixtures.RelationshipPublicTests.envelope_for
    put_envelope = dag_fixtures.RelationshipPublicTests.put_envelope
    add_goal = dag_fixtures.RelationshipPublicTests.add_goal
    read_at = dag_fixtures.RelationshipPublicTests.read_at
    result_at = dag_fixtures.RelationshipPublicTests.result_at

    def setup_publication(self):
        self.observation = {"repository": "owner/repo", "head_oid": self.fixture.head_oid,
            "base_oid": self.fixture.base_oid, "base_ref": "dev", "merged": False,
            "merged_at": None, "merge_commit": None, "checks_present": True,
            "checks_verified": True, "review_verified": True}
        def provider_facts(_repo, executable, selected, bodies):
            self.assertEqual("gh", executable)
            selected_numbers = [entry["number"] for entry in selected]
            if 100 in selected_numbers:
                self.assertIn(100, bodies)
            observations = getattr(self, "stack_observations", {100: self.observation})
            return ({number: copy.deepcopy(observations[number]) for number in selected_numbers
                     if number in observations}, 512, 1)
        patch = mock.patch.object(z, "_github_pull_request_states", side_effect=provider_facts)
        patch.start()
        self.addCleanup(patch.stop)
        z._workflow_section(self.session.project, "verification_testing")["configuration"]["required_ci"] = "inspect_exact_pr_head"
        self.merge_calls = []
        self.session.provider_command = self.provider_command
        self.context = {"branch": "goal-child", "base": "dev", "target": "dev",
                        "pr": "https://github.com/owner/repo/pull/9"}
        self.configure()

    def test_direct_integration_rejects_later_unresolved_finding(self):
        engine = z._workflow.Workflow.__new__(z._workflow.Workflow)
        engine.runtime = {"root_id": "root"}
        authorization = {"hash": "sha256:" + "a" * 64, "uri": "urn:sha256:" + "a" * 64}
        engine.node_publication_authorities = lambda snapshot: [(authorization, {
            "observed": {}, "provider": {"head_oid": "b" * 40}})]
        engine.node_ci_required = lambda observed: None
        snapshot = {"number": 100, "projection": {"states": {},
            "unresolved_obligations": [(100, "finding-after-review")]}}
        payload = {"operational": {"leases": []}}
        with self.assertRaisesRegex(ValueError, "unresolved findings"):
            engine.node_publication_operation(snapshot, payload, {
                "operation": "integrate", "request_id": "finding-gate",
                "authorization": authorization, "expected_head": "b" * 40})

    def test_terminal_reconciliation_selects_only_addressed_goal_in_related_closure(self):
        engine = z._workflow.Workflow.__new__(z._workflow.Workflow)
        engine.runtime = {"root_id": "root"}
        engine.invalidate = lambda: None
        def state(goal):
            return {"node": {"goal": goal, "node": "observed_merge"},
                "contract": {"outputs": {"value": {"type": "merge_observation"}},
                             "executor": {"role": "worker"}},
                "publication": {"provider": {"merged": True,
                    "merge_commit": "f" * 40, "merged_at": "2026-09-29T15:00:00Z"}}}
        engine.node_snapshot = lambda goal: {"envelope": {"state": "open"},
            "projection": {"states": {(100, "observed_merge"): state(100),
                                      (101, "observed_merge"): state(101)}}}
        with self.assertRaisesRegex(ValueError, "assigned to root"):
            engine.node_terminal_merge_reconcile(100)

    def provider_command(self, command, *args, **kwargs):
        if list(command[:1]) != ["gh"]:
            return None
        if list(command[:3]) == ["gh", "pr", "list"]:
            if hasattr(self, "stack_observations"):
                values = [{"headRefName": row["branch"], "baseRefName": row["base_ref"],
                           "headRefOid": row["head_oid"]}
                          for row in self.stack_observations.values() if not row["merged"]]
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(values), stderr="")
            values = [] if self.observation["merged"] else [{"headRefName": "goal-child", "baseRefName": "dev", "headRefOid": self.observation["head_oid"]}]
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(values), stderr="")
        if list(command[:3]) == ["gh", "pr", "merge"]:
            self.assertIn("--match-head-commit", command)
            expected_head = command[command.index("--match-head-commit") + 1]
            observations = getattr(self, "stack_observations", {100: self.observation})
            matches = [row for row in observations.values() if row["head_oid"] == expected_head]
            self.assertEqual(1, len(matches), command)
            self.merge_calls.append(list(command))
            matches[0].update(merged=True, merged_at="2026-09-29T15:00:00Z",
                              merge_commit="f" * 40, review_verified=True,
                              merge_message=command[command.index("--body") + 1]
                              if "--body" in command else None,
                              merge_parents=[matches[0]["base_oid"], expected_head]
                              if "--merge" in command else [matches[0]["base_oid"]])
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError("Unexpected provider command in synthetic publication fixture: %r" % command)

    def mark_merged(self):
        self.observation.update(merged=True, merged_at="2026-09-29T15:00:00Z", merge_commit="f" * 40, review_verified=True)

    def configure(self, renamed=False):
        self.provider.issues[100]["state"] = "open"  # Independent fixture scenario, never a CLI reopen.
        roles = ("context", "inspect", "consent", "observe", "review", "approve", "finish")
        self.ids = {name: ("n%d" % i if renamed else name) for i, name in enumerate(roles)}
        n = self.ids
        context_type = {"kind": "object", "fields": {
            **{key: {"kind": "string"} for key in ("branch", "base", "target")},
            "pr": {"kind": "union", "variants": [{"kind": "null"}, {"kind": "string"}]}}}
        permit_type = {"kind": "object", "fields": {"context": REF_TYPE,
            "policy": {"kind": "string"}, "decision": {"kind": "enum", "values": ["approved"]}}}
        published_type = shape({"repository": "owner/repo", "pr": self.context["pr"],
            "head_oid": "head", "base_oid": "base", "base_ref": "dev", "ci": "verified",
            "review_verified": False})
        published_type["fields"]["ci"] = {"kind": "enum", "values": ["verified", "unverified", "absent", "unknown"]}
        approval_type = {"kind": "object", "fields": {"subject": REF_TYPE, "review": REF_TYPE,
            "policy": {"kind": "string"}, "decision": {"kind": "enum", "values": ["approved"]}}}
        def binding(role, schema):
            return {"producer": {"node": selector(n[role])}, "output": "value", "path": [],
                    "mode": "identity", "type": schema}
        context = task(n["context"], role="root")
        context["inputs"] = {"request": spec_input()}
        context["outputs"] = {"value": output("repository_context", context_type)}
        inspect = task(n["inspect"], [n["context"]])
        inspect["inputs"] = {"subject": binding("context", context_type)}
        inspect["independent_of"] = [selector(n["context"])]
        consent = task(n["consent"], [n["inspect"]], role="root")
        consent["inputs"] = {"subject": binding("context", context_type), "review": binding("inspect", {"kind": "string"})}
        consent["outputs"] = {"value": output("repository_authorization", permit_type)}
        observe = task(n["observe"], [n["consent"]])
        observe["inputs"] = {"context": binding("context", context_type), "authority": binding("consent", permit_type)}
        observe["executor"].update(resources=["repository_publication"], authority=scope(n["context"]))
        observe["outputs"] = {"value": output("publication_evidence", published_type)}
        review = task(n["review"], [n["observe"]])
        review["inputs"] = {"subject": binding("observe", published_type)}
        review["independent_of"] = [selector(n["observe"])]
        approve = task(n["approve"], [n["review"]], role="root")
        approve["inputs"] = {"subject": binding("observe", published_type), "review": binding("review", {"kind": "string"})}
        approve["outputs"] = {"value": output("publication_authorization", approval_type)}
        finish = task(n["finish"], [n["approve"]])
        finish["inputs"] = {"authorization": binding("approve", approval_type)}
        self.install({"nodes": [context, inspect, consent, observe, review, approve, finish],
                      "task_sets": [], "terminals": [selector(n["finish"])]})

    def submit_role(self, role, value, actor=None):
        work = self.session.acquire(self.ids[role], actor=actor)
        self.session.finish(work, {"value": value})
        return work

    def authorize_context(self):
        self.submit_role("context", self.context)
        self.assertNotIn(self.ids["observe"], self.names())
        self.submit_role("inspect", "Exact repository context reviewed", actor="context-reviewer")
        self.assertNotIn(self.ids["observe"], self.names())
        self.submit_role("consent", {"context": self.produced(self.ids["context"]),
            "policy": content_hash(self.session.project["policy"]), "decision": "approved"})
        self.assertIn(self.ids["observe"], self.names())

    def observed_value(self):
        ci = ("verified" if self.observation["checks_verified"] else
              "absent" if self.observation["checks_present"] is False else
              "unverified" if self.observation["checks_present"] is True else "unknown")
        return {**{key: (self.context["pr"] if key == "pr" else self.observation[key])
                for key in ("repository", "pr", "head_oid", "base_oid", "base_ref")},
                "ci": ci, "review_verified": self.observation["review_verified"]}

    def approve_publication(self):
        self.submit_role("observe", self.observed_value())
        self.assertNotIn(self.ids["finish"], self.names())
        self.submit_role("review", "Exact observed publication reviewed", actor="publication-reviewer")
        self.assertNotIn(self.ids["finish"], self.names())
        self.submit_role("approve", {"subject": self.produced(self.ids["observe"]),
            "review": self.produced(self.ids["review"]), "policy": content_hash(self.session.project["policy"]),
            "decision": "approved"})
        return self.produced(self.ids["approve"])

    def with_merge_observation(self, graph):
        """Finite post-effect wire; no archive flag or submitted boolean authority.

        merge_observation has exactly authorization:Ref, repository:string,
        pr:string, head_oid:string, base_oid:string, base_ref:string,
        merge_commit:string, merged_at:string. Its identity inputs pin the
        authenticated repository context, publication subject and current root
        authorization. The repository_publication adapter compares every field
        with provider facts. Integrate consumes current authorization before
        this post-effect Result exists; configured terminals still require it.
        """
        n = self.ids
        by_id = {node["id"]: node for node in graph["nodes"]}
        observe = task("observed_merge", [n["approve"]])
        def exact(role):
            return {"producer": {"node": selector(n[role])}, "output": "value",
                    "path": [], "mode": "identity",
                    "type": copy.deepcopy(by_id[n[role]]["outputs"]["value"]["schema"])}
        observe["inputs"] = {"context": exact("context"), "subject": exact("observe"),
                             "authorization": exact("approve")}
        observe["executor"].update(resources=["repository_publication"], authority=scope(n["context"]))
        schema = {"kind": "object", "fields": {"authorization": REF_TYPE,
            **{key: {"kind": "string"} for key in
               ("repository", "pr", "head_oid", "base_oid", "base_ref", "merge_commit", "merged_at")}}}
        observe["outputs"] = {"value": output("merge_observation", schema)}
        graph["nodes"].append(observe)
        finish = by_id[n["finish"]]
        finish["requires"].append(selector("observed_merge"))
        finish["inputs"]["merge"] = {"producer": {"node": selector("observed_merge")},
            "output": "value", "path": [], "mode": "identity", "type": schema}
        return graph

    def merge_value(self):
        return {"authorization": self.produced(self.ids["approve"]),
                **{key: (self.context["pr"] if key == "pr" else self.observation[key])
                   for key in ("repository", "pr", "head_oid", "base_oid", "base_ref", "merge_commit", "merged_at")}}

    def test_integrate_closes_root_terminal_and_exact_retry_does_not_merge_again(self):
        self.observation["updated_at"] = "2026-09-29T14:00:00Z"
        provider_command = self.provider_command
        def merge_updates_provider_marker(command, *args, **kwargs):
            result = provider_command(command, *args, **kwargs)
            if list(command[:3]) == ["gh", "pr", "merge"]:
                self.observation["updated_at"] = "2026-09-29T15:00:00Z"
            return result
        self.session.provider_command = merge_updates_provider_marker
        graph = self.with_merge_observation(copy.deepcopy(self.graph))
        graph["nodes"][-1]["executor"]["role"] = "root"
        graph["terminals"] = [selector("observed_merge")]
        self.install(graph)
        self.authorize_context()
        authority = self.approve_publication()
        request = self.integration_request(authority)
        request["request_id"] = "root-terminal-merge"
        first = self.session.call(100, request)
        self.assertIn("closed", json.dumps(first))
        self.assertEqual("closed", self.provider.issues[100]["state"])
        self.assertEqual(1, len(self.merge_calls))
        replay = self.session.call(100, request)
        self.assertIn("closed", json.dumps(replay))
        self.assertEqual(1, len(self.merge_calls))

    def test_native_merge_retains_certified_gates_when_provider_projection_changes(self):
        self.observation["updated_at"] = "2026-09-29T14:00:00Z"
        graph = self.with_merge_observation(copy.deepcopy(self.graph))
        graph["nodes"][-1]["executor"]["role"] = "root"
        graph["terminals"] = [selector("observed_merge")]
        self.install(graph)
        self.authorize_context()
        authority = self.approve_publication()
        request = self.integration_request(authority)
        request["request_id"] = "native-certified-gates"
        provider_command = self.provider_command
        def change_postmerge_projection(command, *args, **kwargs):
            result = provider_command(command, *args, **kwargs)
            if list(command[:3]) == ["gh", "pr", "merge"]:
                self.observation["updated_at"] = "2026-09-29T15:00:00Z"
                self.observation["review_verified"] = False
                self.observation["checks_verified"] = False
            return result
        self.session.provider_command = change_postmerge_projection
        with mock.patch.object(z._workflow.Workflow, 'node_native_delivery', return_value=True), \
             mock.patch.object(z._workflow.Workflow, 'node_candidate_state', return_value={
                 'status': 'ready', 'branch': 'goal-child',
                 'head_oid': self.observation['head_oid']}):
            first = self.session.call(100, request)
            replay = self.session.call(100, request)
        self.assertIn("closed", json.dumps(first))
        self.assertIn("closed", json.dumps(replay))
        self.assertEqual(1, len(self.merge_calls))

    def test_squash_parent_mismatch_cannot_retain_premerge_gates(self):
        self.observation["updated_at"] = "2026-09-29T14:00:00Z"
        graph = self.with_merge_observation(copy.deepcopy(self.graph))
        graph["nodes"][-1]["executor"]["role"] = "root"
        graph["terminals"] = [selector("observed_merge")]
        self.install(graph)
        self.authorize_context()
        authority = self.approve_publication()
        request = self.integration_request(authority)
        request["request_id"] = "squash-wrong-parent"
        provider_command = self.provider_command
        def wrong_parent_after_merge(command, *args, **kwargs):
            result = provider_command(command, *args, **kwargs)
            if list(command[:3]) == ["gh", "pr", "merge"]:
                self.observation["updated_at"] = "2026-09-29T15:00:00Z"
                self.observation["review_verified"] = False
                self.observation["checks_verified"] = False
                self.observation["merge_parents"] = ["e" * 40]
            return result
        self.session.provider_command = wrong_parent_after_merge
        first = self.session.call(100, request)
        self.assertRegex(json.dumps(first), r"(?i)terminal_reconciliation|pending|stale")
        self.assertEqual("open", self.provider.issues[100]["state"])

    def test_integrate_recovers_provider_merge_before_goal_receipt(self):
        graph = self.with_merge_observation(copy.deepcopy(self.graph))
        graph["nodes"][-1]["executor"]["role"] = "root"
        graph["terminals"] = [selector("observed_merge")]
        self.install(graph)
        self.authorize_context()
        authority = self.approve_publication()
        request = self.integration_request(authority)
        request["request_id"] = "merged-before-goal-write"
        update = self.provider.update_issue
        interrupted = []
        def fail_once_after_merge(number, payload):
            if self.observation["merged"] and not interrupted:
                interrupted.append(True)
                raise RuntimeError("goal receipt write interrupted after provider merge")
            return update(number, payload)
        self.provider.update_issue = fail_once_after_merge
        first = self.session.call(100, request, expected=2)
        self.assertTrue(interrupted)
        self.assertRegex(json.dumps(first), r"(?i)retry|repair|unconfirmed")
        self.assertEqual(1, len(self.merge_calls))
        self.assertEqual("open", self.provider.issues[100]["state"])
        replay = self.session.call(100, request)
        self.assertIn("closed", json.dumps(replay))
        self.assertEqual("closed", self.provider.issues[100]["state"])
        self.assertEqual(1, len(self.merge_calls))

    def test_postspawn_oserror_keeps_dispatch_uncertain(self):
        self.observation["updated_at"] = "2026-09-29T14:00:00Z"
        graph = self.with_merge_observation(copy.deepcopy(self.graph))
        graph["nodes"][-1]["executor"]["role"] = "root"
        graph["terminals"] = [selector("observed_merge")]
        self.install(graph)
        self.authorize_context()
        authority = self.approve_publication()
        request = self.integration_request(authority)
        request["request_id"] = "oserror-after-spawn"
        provider_command = self.provider_command
        interrupted = []
        def stop_once_after_spawn(command, *args, **kwargs):
            if list(command[:3]) == ["gh", "pr", "merge"] and not interrupted:
                interrupted.append("child started")
                raise OSError("output read failed after child started")
            return provider_command(command, *args, **kwargs)
        self.session.provider_command = stop_once_after_spawn
        first = self.session.call(100, request, expected=2)
        self.assertTrue(interrupted)
        self.assertRegex(json.dumps(first), r"(?i)uncertain|observe")
        self.assertEqual([], self.merge_calls)
        replay = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(replay), r"(?i)prior merge dispatch|uncertain")
        blocked = self.session.call(100, {**request,
            "request_id": "fresh-while-oserror-uncertain"}, expected=2)
        self.assertRegex(json.dumps(blocked), r"(?i)prior merge dispatch|uncertain")
        certificate = self.payload()[1]["publication_certificate"]
        self.session.call(100, {"operation": "publication_attempt_retire",
            "request_id": "retire-oserror-attempt", "certificate": certificate,
            "expected_head": self.observation["head_oid"],
            "expected_marker": self.observation["updated_at"],
            "approved_by": "User explicitly approved exact no-effect recovery",
            "attribution": "Reviewed open PR after output failure",
            "reason": "No merge effect was observed"})
        fresh = self.session.call(100, {**request, "request_id": "fresh-private-merge-nonce"})
        self.assertIn("closed", json.dumps(fresh))
        self.assertEqual(1, len(self.merge_calls))

    def test_uncertain_direct_dispatch_blocks_new_effect_request(self):
        self.observation["updated_at"] = "2026-09-29T14:00:00Z"
        self.authorize_context()
        authority = self.approve_publication()
        request = self.integration_request(authority)
        request["request_id"] = "uncertain-direct-effect"
        calls = []
        def uncertain(command, *args, **kwargs):
            if list(command[:3]) == ["gh", "pr", "merge"]:
                calls.append(list(command))
                raise subprocess.TimeoutExpired(command, 5)
            return self.provider_command(command, *args, **kwargs)
        self.session.provider_command = uncertain
        first = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(first), r"(?i)uncertain|observe")
        second = self.session.call(100, {**request, "request_id": "new-while-uncertain"}, expected=2)
        self.assertRegex(json.dumps(second), r"(?i)prior merge dispatch|uncertain")
        self.assertEqual(1, len(calls), "No second provider effect is dispatched")
        certificate = self.payload()[1]["publication_certificate"]
        frontier = self.session.checkpoint(100)
        self.assertTrue(any(step.get("kind") == "human_approval" and
            step.get("submission", {}).get("certificate") == certificate for step in frontier),
            "The CLI must expose the exact reviewed no-effect recovery")
        retirement = {"operation": "publication_attempt_retire",
            "request_id": "reviewed-retirement", "certificate": certificate,
            "expected_head": self.observation["head_oid"],
            "expected_marker": self.observation["updated_at"],
            "approved_by": "User explicitly approved this exact no-effect recovery",
            "attribution": "Reviewed open PR after timeout", "reason": "No merge effect was observed"}
        rejected = self.session.call(100, {**retirement,
            "request_id": "wrong-retirement-marker", "expected_marker": "stale"}, expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)provider|marker|exact")
        self.session.call(100, retirement)
        self.session.provider_command = self.provider_command
        fresh = self.session.call(100, {**request, "request_id": "after-reviewed-retirement"})
        self.assertIn("merged", json.dumps(fresh))
        self.assertEqual(1, len(self.merge_calls))

    def test_feedback_change_after_certificate_blocks_provider_merge(self):
        self.observation["updated_at"] = "2026-09-29T14:00:00Z"
        graph = self.with_merge_observation(copy.deepcopy(self.graph))
        graph["nodes"][-1]["executor"]["role"] = "root"
        graph["terminals"] = [selector("observed_merge")]
        self.install(graph)
        self.authorize_context()
        authority = self.approve_publication()
        request = self.integration_request(authority)
        request["request_id"] = "feedback-after-certificate"
        update = self.provider.update_issue
        changed = []
        def change_feedback_after_certificate(number, payload):
            observed = update(number, payload)
            if not self.observation['merged'] and not changed:
                changed.append(True)
                self.observation["updated_at"] = "2026-09-29T14:01:00Z"
            return observed
        self.provider.update_issue = change_feedback_after_certificate
        rejected = self.session.call(100, request, expected=2)
        self.assertTrue(changed)
        self.assertRegex(json.dumps(rejected), r"(?i)provider changed|feedback|review")
        self.assertEqual([], self.merge_calls)
        self.assertEqual("open", self.provider.issues[100]["state"])

    def test_external_merge_after_seal_cannot_reuse_stale_premerge_gates(self):
        self.observation["updated_at"] = "2026-09-29T14:00:00Z"
        graph = self.with_merge_observation(copy.deepcopy(self.graph))
        graph["nodes"][-1]["executor"]["role"] = "root"
        graph["terminals"] = [selector("observed_merge")]
        self.install(graph)
        self.authorize_context()
        authority = self.approve_publication()
        request = self.integration_request(authority)
        request["request_id"] = "external-merge-after-seal"
        update = self.provider.update_issue
        changed = []
        def external_merge_after_seal(number, payload):
            result = update(number, payload)
            if not changed:
                changed.append(True)
                self.mark_merged()
                self.observation["updated_at"] = "2026-09-29T14:01:00Z"
                self.observation["review_verified"] = False
                self.observation["checks_verified"] = False
            return result
        self.provider.update_issue = external_merge_after_seal
        first = self.session.call(100, request, expected=2)
        self.assertTrue(changed)
        self.assertRegex(json.dumps(first), r"(?i)provider changed|feedback|review")
        retry = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(retry), r"(?i)stale|authority|current|review|provider")
        self.assertEqual("open", self.provider.issues[100]["state"])
        self.assertEqual([], self.merge_calls)

    def test_external_merge_after_dispatch_intent_lacks_effect_marker(self):
        self.observation["updated_at"] = "2026-09-29T14:00:00Z"
        graph = self.with_merge_observation(copy.deepcopy(self.graph))
        graph["nodes"][-1]["executor"]["role"] = "root"
        graph["terminals"] = [selector("observed_merge")]
        self.install(graph)
        self.authorize_context()
        authority = self.approve_publication()
        request = self.integration_request(authority)
        request["request_id"] = "external-merge-after-dispatch-intent"
        update = self.provider.update_issue
        def merge_after_dispatch_intent(number, payload):
            result = update(number, payload)
            certificate = self.payload()[1].get("publication_certificate")
            if (certificate and self.read_blob(certificate)["content"].get("stage") == "dispatch"
                    and not self.observation["merged"]):
                sealed = self.read_blob(certificate)["content"]
                self.mark_merged()
                self.observation["updated_at"] = "2026-09-29T14:01:00Z"
                self.observation["review_verified"] = False
                self.observation["checks_verified"] = False
                self.observation["merge_message"] = "ZzzOps-Effect: " + sealed["effect_hash"]
                self.observation["merge_parents"] = [sealed["base_oid"], sealed["head_oid"]]
            return result
        self.provider.update_issue = merge_after_dispatch_intent
        def no_command_after_external_merge(command, *args, **kwargs):
            if list(command[:3]) == ["gh", "pr", "merge"] and self.observation["merged"]:
                raise OSError("provider already merged externally")
            return self.provider_command(command, *args, **kwargs)
        self.session.provider_command = no_command_after_external_merge
        self.session.call(100, request, expected=2)
        retry = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(retry), r"(?i)stale|authority|current|review|provider")
        self.assertEqual("open", self.provider.issues[100]["state"])
        self.assertEqual([], self.merge_calls)

    def test_retry_finishes_archived_body_with_provider_issue_still_open(self):
        graph = self.with_merge_observation(copy.deepcopy(self.graph))
        graph["nodes"][-1]["executor"]["role"] = "root"
        graph["terminals"] = [selector("observed_merge")]
        self.install(graph)
        self.authorize_context()
        authority = self.approve_publication()
        request = self.integration_request(authority)
        request["request_id"] = "partial-issue-close"
        update = self.provider.update_issue
        partial = []
        def close_body_without_state(number, payload):
            if payload.get("state") == "closed" and not partial:
                partial.append(True)
                return update(number, {"body": payload["body"]})
            return update(number, payload)
        self.provider.update_issue = close_body_without_state
        first = self.session.call(100, request)
        self.assertTrue(partial)
        self.assertEqual("open", self.provider.issues[100]["state"])
        self.assertRegex(json.dumps(first), r"(?i)pending|unconfirmed")
        replay = self.session.call(100, request)
        self.assertIn("closed", json.dumps(replay))
        self.assertEqual("closed", self.provider.issues[100]["state"])
        self.assertEqual(1, len(self.merge_calls))

    def test_integrate_precedes_post_effect_terminal_and_observation_is_exact(self):
        self.install(self.with_merge_observation(copy.deepcopy(self.graph)))
        self.authorize_context()
        authority = self.approve_publication()
        self.assertNotIn(self.ids["finish"], self.names())
        request = self.integration_request(authority)
        request["request_id"] = "before-post-effect-terminal"
        self.session.call(100, request)
        self.assertEqual(1, len(self.merge_calls))
        self.assertEqual("open", self.provider.issues[100]["state"], "Merge cannot mint the pending observation Result or complete goal")
        self.assertNotIn(self.ids["finish"], self.names())
        work = self.session.acquire("observed_merge")
        acquisition = json.dumps(work["lease"]["acquisition"])
        for role in ("context", "observe", "approve"):
            self.assertIn(self.produced(self.ids[role])["hash"], acquisition)
        value = self.merge_value()
        for key, wrong in (("head_oid", "a" * 40), ("base_oid", "b" * 40),
                           ("merge_commit", "c" * 40), ("merged_at", "2020-01-01T00:00:00Z"),
                           ("authorization", self.produced(self.ids["context"]))):
            with self.subTest(field=key):
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                self.session.call(100, self.session.submission(work, {"value": {**value, key: wrong}}, "wrong-merge-" + key), expected=2)
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(work, {"value": value})
        self.assertIn(self.ids["finish"], self.names())
        self.submit_role("finish", "Exact post-effect evidence consumed")
        self.assertEqual(set(), self.names())

    def test_unmerged_provider_cannot_issue_merge_observation_then_external_merge_is_readable(self):
        self.install(self.with_merge_observation(copy.deepcopy(self.graph)))
        self.authorize_context()
        self.approve_publication()
        work = self.session.acquire("observed_merge")
        forged = {**self.merge_value(), "merge_commit": "f" * 40, "merged_at": "2026-09-29T15:00:00Z"}
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, self.session.submission(work, {"value": forged}, "forged-merge"), expected=2)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertNotIn(self.ids["finish"], self.names())
        self.mark_merged()  # External provider event; no lease takeover or semantic Result fabrication.
        self.session.finish(work, {"value": self.merge_value()})
        self.assertEqual(0, len(self.merge_calls))
        self.submit_role("finish", "Observed external merge has exact evidence")

    def test_declared_base_is_not_replaced_by_unrelated_checkout_head(self):
        self.authorize_context()
        self.session.git("checkout", "-qb", "unrelated")
        (self.fixture.repo / "unrelated.txt").write_text("Unrelated committed checkout\n")
        self.session.git("add", "unrelated.txt")
        self.session.git("commit", "-qm", "unrelated checkout")
        head = self.session.git("rev-parse", "HEAD")
        self.assertNotEqual(self.fixture.base_oid, head)
        work = self.session.acquire(self.ids["observe"])
        self.assertEqual("dev", work["base_branch"])
        self.assertEqual(self.fixture.base_oid, work["base_commit"])
        self.assertNotEqual(head, work["base_commit"])
        self.session.finish(work, {"value": self.observed_value()})

    def test_renamed_graph_requires_current_review_and_root_before_completion(self):
        for renamed in (False, True):
            with self.subTest(renamed=renamed):
                self.configure(renamed)
                self.authorize_context()
                self.approve_publication()
                self.submit_role("finish", "All configured exact evidence accepted")
                self.assertEqual(set(), self.names())
                self.assertEqual(self.ids["finish"], self.result(self.ids["finish"])[1]["node"]["node"])
                self.assertEqual("open", self.provider.issues[100]["state"], "Semantic completion alone cannot claim a provider merge")

    def test_live_head_base_ci_and_caller_approval_flags_reject_before_valid_control(self):
        self.authorize_context()
        work = self.session.acquire(self.ids["observe"])
        original = copy.deepcopy(self.observation)
        declared = self.observed_value()
        for field, value in (("head_oid", "a" * 40), ("base_oid", "b" * 40), ("checks_verified", False)):
            with self.subTest(field=field):
                self.observation = {**original, field: value}
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, self.session.submission(work, {"value": declared}, "changed-" + field), expected=2)
                self.assertRegex(json.dumps(response), r"(?i)head|base|checks|CI|stale|provider|input")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.observation = original
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        forged = {**self.observed_value(), "approved": True, "checks_verified": True}
        self.session.call(100, self.session.submission(work, {"value": forged}, "forged-approval"), expected=2)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(work, {"value": self.observed_value()})

    def test_publication_submission_compares_only_declared_evidence_fields(self):
        graph = copy.deepcopy(self.graph)
        observe = next(node for node in graph["nodes"] if node["id"] == self.ids["observe"])
        observe["outputs"]["value"]["schema"]["fields"].pop("review_verified")
        self.install(graph)
        self.authorize_context()
        declared = self.observed_value()
        declared.pop("review_verified")

        self.submit_role("observe", declared)
        self.assertEqual(declared, self.read_blob(self.produced(self.ids["observe"]))["content"])

    def test_negative_ci_observation_is_recordable_and_review_can_admit_correction_without_approval(self):
        graph = copy.deepcopy(self.graph)
        observed = self.ids["observe"]
        source_input = copy.deepcopy(next(node for node in graph["nodes"] if node["id"] == self.ids["review"])["inputs"])
        finder = task("describe_defect", [self.ids["review"]])
        finder["inputs"] = copy.deepcopy(source_input)
        finder["independent_of"] = [selector(observed)]
        finder["outputs"] = {"value": output("finding", FINDING_TYPE)}
        finder["permits"] = [{"type": "finding", "scope": scope(observed)}]
        authorize = task("authorize_correction", ["describe_defect"], role="root")
        authorize["inputs"] = copy.deepcopy(source_input)
        admit = task("admit_correction", ["describe_defect", "authorize_correction"], role="root")
        admit["inputs"] = copy.deepcopy(source_input)
        admit["outputs"] = {"value": output("admission", ADMISSION_TYPE)}
        admit["permits"] = [{"type": "admission", "scope": scope(observed)}]
        graph["nodes"].extend([finder, authorize, admit])
        self.install(graph)
        self.authorize_context()
        self.observation["checks_verified"] = False
        self.submit_role("observe", self.observed_value())
        subject = self.produced(observed)
        self.assertEqual("unverified", self.read_blob(subject)["content"]["ci"])
        self.submit_role("review", "Observed failed checks require correction", actor="publication-reviewer")
        finding = {"id": "failed-ci", "revision": 1, "source": subject, "subjects": [subject],
            "target": scope(observed), "request": "Correct the failing checks and publish current provider evidence",
            "rationale": "Exact authenticated publication observation reports unverified CI", "supersedes": None}
        self.session.finish(self.session.acquire("describe_defect", actor="defect-reviewer"), {"value": finding})
        self.session.finish(self.session.acquire("authorize_correction"), {"value": "Authorize in-scope correction"})
        admission = {"finding": self.produced("describe_defect"), "target_inputs": self.result(observed)[1]["inputs"],
            "authority": self.result("authorize_correction")[0], "applicability": "applicable", "rationale": "Current failing subject needs correction"}
        self.session.finish(self.session.acquire("admit_correction"), {"value": admission})
        self.assertIn(observed, self.names())
        self.assertNotIn(self.ids["finish"], self.names())
        self.assertFalse(any(step.get("kind") == "complete" for step in self.session.checkpoint(100)))
        self.assertEqual([], self.merge_calls)

    def test_ci_absent_unknown_unverified_and_disabled_authorization_are_distinct(self):
        cases = [("inspect_exact_pr_head", True, True, True),
                 ("inspect_exact_pr_head", False, False, False),
                 ("existing_only", False, False, True),
                 ("existing_only", None, False, False),
                 ("existing_only", True, False, False),
                 ("disabled", None, False, True)]
        for mode, present, verified, allowed in cases:
            with self.subTest(mode=mode, present=present, verified=verified):
                z._workflow_section(self.session.project, "verification_testing")["configuration"]["required_ci"] = mode
                self.observation.update(checks_present=present, checks_verified=verified, merged=False)
                self.configure()
                self.authorize_context()
                self.submit_role("observe", self.observed_value())
                self.assertEqual(self.observed_value(), self.read_blob(self.produced(self.ids["observe"]))["content"])
                self.submit_role("review", "Reviewed current observation, including negative CI", actor="publication-reviewer")
                value = {"subject": self.produced(self.ids["observe"]), "review": self.produced(self.ids["review"]),
                    "policy": content_hash(self.session.project["policy"]), "decision": "approved"}
                if allowed:
                    self.submit_role("approve", value)
                    self.assertIn(self.ids["finish"], self.names())
                else:
                    ready = self.names()
                    if self.ids["approve"] in ready:
                        work = self.session.acquire(self.ids["approve"])
                        before = copy.deepcopy((self.provider.issues, self.provider.comments))
                        response = self.session.call(100, self.session.submission(work, {"value": value}, "ci-block-" + str(len(self.session.calls))), expected=2)
                        self.assertEqual(before, (self.provider.issues, self.provider.comments))
                    else:
                        response = self.session.call(100)
                    self.assertRegex(json.dumps(response), r"(?i)CI|checks|unknown|unverified|incomplete")
                    self.assertNotIn(self.ids["finish"], self.names())
                    before = copy.deepcopy((self.provider.issues, self.provider.comments))
                    self.session.call(100, {"operation": "complete", "request_id": "premature-ci-complete-" + str(len(self.session.calls))}, expected=2)
                    self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_changed_root_context_stales_acquired_publication(self):
        self.authorize_context()
        work = self.session.acquire(self.ids["observe"])
        self.replace_spec("Changed required repository target; current context must be reconsidered")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, self.session.submission(work, {"value": self.observed_value()}, "stale-context"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)stale|context|input|ancestor|authority")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertNotIn(self.ids["finish"], self.names())

    def test_publication_submit_lost_body_response_reuses_exact_result(self):
        self.authorize_context()
        work = self.session.acquire(self.ids["observe"])
        request = self.session.submission(work, {"value": self.observed_value()}, "publication-lost-response")
        update = self.provider.update_issue
        lost = []
        def uncertain(number, payload):
            result = update(number, payload)
            if number == 100 and not lost:
                lost.append(True)
                raise z.GoalTransitionProviderError("Publication body committed; response lost")
            return result
        with mock.patch.object(self.provider, "update_issue", side_effect=uncertain):
            self.session.call(100, request, expected=None)
        self.assertTrue(lost, "Fault must reach the actual durable provider boundary")
        self.session.call(100, request)
        reference = self.produced(self.ids["observe"])
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, request)
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))
        self.assertEqual(reference, self.produced(self.ids["observe"]))
        self.assertNotIn(self.ids["finish"], self.names())

    def integration_request(self, authorization):
        steps = self.session.checkpoint(100)
        candidates = [step for step in steps if step.get("submission", {}).get("operation") == "integrate"]
        self.assertTrue(candidates, "Current exact publication authorization must expose operational integration contract")
        request = copy.deepcopy(candidates[0]["submission"])
        self.assertEqual(authorization, request["authorization"])
        self.assertEqual(self.observation["head_oid"], request["expected_head"])
        return request

    def test_native_post_merge_cleanup_failure_is_replayable_without_second_merge(self):
        self.authorize_context()
        authority = self.approve_publication()
        self.submit_role("finish", "Exact configured graph complete")
        request = self.integration_request(authority)
        request["request_id"] = "native-cleanup-retry"
        native_after_merge = lambda _snapshot: self.observation["merged"]
        with mock.patch.object(z._workflow.Workflow, "node_native_delivery",
                               side_effect=native_after_merge), \
             mock.patch.object(z._workflow.Workflow, "node_cleanup_delivered_worktrees",
                               side_effect=ValueError("simulated local cleanup failure")):
            first = self.session.call(100, request)
            self.assertIn("pending", json.dumps(first))
            self.assertEqual(1, len(self.merge_calls))
            stable = copy.deepcopy((self.provider.issues, self.provider.comments))
            replay = self.session.call(100, request)
            self.assertIn("pending", json.dumps(replay))
            self.assertEqual(stable, (self.provider.issues, self.provider.comments))
            self.assertEqual(1, len(self.merge_calls))

    def test_exact_root_authorization_rejects_wrong_subject_review_policy_and_forged_integration(self):
        self.authorize_context()
        self.submit_role("observe", self.observed_value())
        self.submit_role("review", "Reviewed exact subject", actor="publication-reviewer")
        root = self.session.acquire(self.ids["approve"])
        value = {"subject": self.produced(self.ids["observe"]), "review": self.produced(self.ids["review"]),
                 "policy": content_hash(self.session.project["policy"]), "decision": "approved"}
        wrong = self.produced(self.ids["context"])
        for changes in ({"subject": wrong}, {"review": wrong}, {"policy": "sha256:" + "0" * 64}):
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            response = self.session.call(100, self.session.submission(root, {"value": {**value, **changes}}, "wrong-approval-" + next(iter(changes))), expected=2)
            self.assertRegex(json.dumps(response), r"(?i)subject|review|policy|current|authority|stale")
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
        request = self.session.submission(root, {"value": value}, "nonroot-approval")
        request["actor"] = "publication-reviewer"
        self.session.call(100, request, expected=2)
        self.session.finish(root, {"value": value})
        authority = self.produced(self.ids["approve"])
        self.submit_role("finish", "Exact configured graph complete")
        request = self.integration_request(authority)
        forged = self.blob({"type": "publication_authorization", "content": value, "producer": None,
            "provenance": {"actor": "root-thread", "source": None, "policy": value["policy"]}})
        for bad in (None, wrong, forged):
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            rejected = {**request, "request_id": "bad-integration-" + str(len(self.session.calls)), "authorization": bad}
            response = self.session.call(100, rejected, expected=2)
            self.assertRegex(json.dumps(response), r"(?i)authoriz|approval|root|subject|reference|current")
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
            self.assertEqual([], self.merge_calls)
        request["request_id"] = "exact-integration"
        self.session.call(100, request)
        self.assertEqual(1, len(self.merge_calls))
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, request)
        self.assertEqual(1, len(self.merge_calls))
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))

    def test_stale_root_authorization_cannot_integrate_after_context_drift(self):
        self.authorize_context()
        authority = self.approve_publication()
        self.submit_role("finish", "Current terminal evidence")
        request = self.integration_request(authority)
        old_body = self.provider.issues[100]["body"]
        self.replace_spec("Different repository target requiring new current authorization")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, {**request, "request_id": "stale-root-context"}, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)stale|current|context|authority|evidence|input")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertEqual([], self.merge_calls)
        # Fixture restores the exact external substantive input; added immutable
        # source bytes remain unreferenced history, not an authority bypass.
        self.provider.issues[100]["body"] = old_body
        self.session.call(100, {**request, "request_id": "restored-current-context"})
        self.assertEqual(1, len(self.merge_calls))

    def test_public_stack_prepare_status_and_advance_preserve_publication_gates(self):
        """Minimal public journey; stack administration issues no phase Results."""
        self.authorize_context()
        authority = self.approve_publication()
        self.submit_role("finish", "Current terminal evidence for the exact reviewed head")
        evidence_before = copy.deepcopy(self.payload()[1]["evidence"])
        prepare = {
            "operation": "stack_prepare", "request_id": "public-stack-prepare",
            "repository": "owner/repo", "target": "dev", "method": "merge",
            "members": [{
                "goal": 100, "pr": 100, "branch": "goal-child", "base": "dev",
                "head": self.observation["head_oid"], "base_head": self.observation["base_oid"],
                "implementation_review": "current", "ci": "verified",
                "release": "eligible", "authorization": authority, "owner": None,
            }],
        }
        prepared = self.session.call(100, prepare)
        step = prepared["next_steps"][0]
        self.assertEqual("stack_plan", step["kind"])
        self.assertEqual("sha256:", step["plan_id"][:7])
        self.assertEqual(evidence_before, self.payload()[1]["evidence"])

        status = self.session.call(100, {
            "operation": "stack_status", "request_id": "public-stack-status",
            "plan_id": step["plan_id"],
        })
        self.assertEqual(step["plan_id"], status["next_steps"][0]["plan_id"])
        self.assertEqual([], self.merge_calls)

        advanced = self.session.call(100, {
            "operation": "stack_advance", "request_id": "public-stack-advance",
            "plan_id": step["plan_id"], "expected_revision": step["revision"],
        })
        self.assertEqual(1, len(self.merge_calls))
        self.assertRegex(json.dumps(advanced), r"(?i)observ|reconcile|pending")
        self.assertEqual(evidence_before, self.payload()[1]["evidence"],
                         "Stack administration cannot fabricate semantic Results")

    def test_stack_dispatch_certificate_without_coordinator_intent_recovers(self):
        self.authorize_context()
        authority = self.approve_publication()
        self.submit_role("finish", "Current terminal evidence")
        prepared = self.session.call(100, {
            "operation": "stack_prepare", "request_id": "stack-no-intent-prepare",
            "repository": "owner/repo", "target": "dev", "method": "merge",
            "members": [{
                "goal": 100, "pr": 100, "branch": "goal-child", "base": "dev",
                "head": self.observation["head_oid"],
                "base_head": self.observation["base_oid"],
                "implementation_review": "current", "ci": "verified",
                "release": "eligible", "authorization": authority, "owner": None,
            }],
        })["next_steps"][0]
        advance = {"operation": "stack_advance", "request_id": "stack-no-intent",
                   "plan_id": prepared["plan_id"], "expected_revision": prepared["revision"]}
        with mock.patch.object(z._workflow.Workflow, 'node_stack_followup_capacity',
                               side_effect=ValueError('capacity unavailable')):
            self.session.call(100, advance, expected=2)
        self.assertEqual([], self.merge_calls)
        self.assertEqual("dispatch", self.read_blob(
            self.payload()[1]["publication_certificate"])["content"]["stage"])
        retry = self.session.call(100, advance, expected=2)
        self.assertRegex(json.dumps(retry), r"(?i)no coordinator dispatch intent|fresh exact request")
        self.assertEqual("aborted", self.read_blob(
            self.payload()[1]["publication_certificate"])["content"]["stage"])
        fresh = self.session.call(100, {**advance, "request_id": "stack-after-no-intent"})
        self.assertRegex(json.dumps(fresh), r"(?i)observ|reconcil|pending")
        self.assertEqual(1, len(self.merge_calls))

    def test_uncertain_stack_effect_can_be_reviewed_and_retired(self):
        self.observation["updated_at"] = "2026-09-29T14:00:00Z"
        self.authorize_context()
        authority = self.approve_publication()
        self.submit_role("finish", "Current terminal evidence")
        prepared = self.session.call(100, {
            "operation": "stack_prepare", "request_id": "stack-retire-prepare",
            "repository": "owner/repo", "target": "dev", "method": "merge",
            "members": [{
                "goal": 100, "pr": 100, "branch": "goal-child", "base": "dev",
                "head": self.observation["head_oid"],
                "base_head": self.observation["base_oid"],
                "implementation_review": "current", "ci": "verified",
                "release": "eligible", "authorization": authority, "owner": None,
            }],
        })["next_steps"][0]
        advance = {"operation": "stack_advance", "request_id": "uncertain-stack-effect",
                   "plan_id": prepared["plan_id"], "expected_revision": prepared["revision"]}
        def timeout_without_merge(command, *args, **kwargs):
            if list(command[:3]) == ["gh", "pr", "merge"]:
                raise subprocess.TimeoutExpired(command, 5)
            return self.provider_command(command, *args, **kwargs)
        self.session.provider_command = timeout_without_merge
        uncertain = self.session.call(100, advance)
        self.assertRegex(json.dumps(uncertain), r"(?i)uncertain|observe")
        self.assertEqual([], self.merge_calls)
        certificate = self.payload()[1]["publication_certificate"]
        self.session.call(100, {"operation": "publication_attempt_retire",
            "request_id": "retire-stack-member", "certificate": certificate,
            "expected_head": self.observation["head_oid"],
            "expected_marker": self.observation["updated_at"],
            "approved_by": "User approved exact no-effect retirement",
            "attribution": "Reviewed open member after timeout",
            "reason": "No stack merge effect was observed"})
        status = self.session.call(100, {"operation": "stack_status",
            "request_id": "stack-retire-status", "plan_id": prepared["plan_id"]})
        recovery = status["next_steps"][0]["recovery_contract"]
        recovery["request_id"] = "retire-coordinator-attempt"
        retired = self.session.call(100, recovery)
        self.assertEqual("stack_attempt_retired", retired["next_steps"][0]["kind"])
        self.session.provider_command = self.provider_command
        fresh = self.session.call(100, {**advance,
            "request_id": "fresh-stack-after-retirement",
            "expected_revision": retired["next_steps"][0]["revision"]})
        self.assertRegex(json.dumps(fresh), r"(?i)observ|reconcil|pending")
        self.assertEqual(1, len(self.merge_calls))

    def test_public_stack_rejects_squash_for_exact_git_candidate(self):
        self.authorize_context()
        authority = self.approve_publication()
        self.submit_role("finish", "Current terminal evidence for the exact reviewed head")
        prepared = self.session.call(100, {
            "operation": "stack_prepare", "request_id": "native-squash-prepare",
            "repository": "owner/repo", "target": "dev", "method": "squash",
            "members": [{
                "goal": 100, "pr": 100, "branch": "goal-child", "base": "dev",
                "head": self.observation["head_oid"],
                "base_head": self.observation["base_oid"],
                "implementation_review": "current", "ci": "verified",
                "release": "eligible", "authorization": authority, "owner": None,
            }],
        })["next_steps"][0]
        with mock.patch.object(z._workflow.Workflow, 'node_native_delivery', return_value=True), \
             mock.patch.object(z._workflow.Workflow, 'node_candidate_state',
                               return_value={'status': 'ready', 'branch': 'goal-child',
                                             'head_oid': self.observation['head_oid']}):
            rejected = self.session.call(100, {
                "operation": "stack_advance", "request_id": "native-squash-advance",
                "plan_id": prepared["plan_id"], "expected_revision": prepared["revision"],
            }, expected=2)
        self.assertIn('ancestry-preserving merge', json.dumps(rejected))
        self.assertEqual([], self.merge_calls)

    def test_public_stack_rejects_rebase_without_terminal_effect_proof(self):
        self.authorize_context()
        authority = self.approve_publication()
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        rejected = self.session.call(100, {
            "operation": "stack_prepare", "request_id": "unsupported-rebase-stack",
            "repository": "owner/repo", "target": "dev", "method": "rebase",
            "members": [{
                "goal": 100, "pr": 100, "branch": "goal-child", "base": "dev",
                "head": self.observation["head_oid"],
                "base_head": self.observation["base_oid"],
                "implementation_review": "current", "ci": "verified",
                "release": "eligible", "authorization": authority, "owner": None,
            }],
        }, expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)stack prepare|method|invalid")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_public_abc_stack_persists_and_resumes_each_authorized_effect(self):
        graph = self.with_merge_observation(copy.deepcopy(self.graph))
        graph["nodes"][-1]["executor"]["role"] = "root"
        graph["terminals"] = [selector("observed_merge")]
        def symbolic(value):
            if isinstance(value, dict):
                return {key: ("#this" if key == "goal" and child == 100 else symbolic(child))
                        for key, child in value.items()}
            if isinstance(value, list):
                return [symbolic(child) for child in value]
            return value
        graph = symbolic(graph)
        self.install(graph)
        self.setup_relationship_transport()
        self.add_goal(101, graph)
        self.add_goal(102, graph)
        branches = {100: "A", 101: "B", 102: "C"}
        self.session.git("checkout", "-q", "dev")
        trunk = self.session.git("rev-parse", "dev")
        heads, previous = {}, "dev"
        for number in (100, 101, 102):
            self.session.git("checkout", "-qb", branches[number], previous)
            self.session.git("commit", "--allow-empty", "-qm", f"stack member {branches[number]}")
            heads[number] = self.session.git("rev-parse", "HEAD")
            previous = branches[number]
        bases = {100: ("dev", trunk), 101: ("A", heads[100]),
                 102: ("B", heads[101])}
        self.stack_observations = {number: {
            "repository": "owner/repo", "branch": branches[number],
            "head_oid": heads[number], "base_oid": bases[number][1],
            "base_ref": bases[number][0], "merged": False, "merged_at": None,
            "merge_commit": None, "checks_present": True, "checks_verified": True,
            "review_verified": True, "updated_at": "2026-09-29T14:00:00Z",
        } for number in (100, 101, 102)}

        def produced(number, role):
            return self.result_at(number, self.ids[role])[1]["outputs"]["value"]

        def submit(number, role, value, actor=None, session=None):
            session = session or self.session
            frontier = session.checkpoint(number)
            if not any(step.get("kind") == "execute" and step.get("node", {}).get("node") == self.ids[role]
                       for step in frontier):
                raise AssertionError(json.dumps(frontier))
            work = session.acquire(self.ids[role], number=number, actor=actor, frontier=frontier)
            session.finish(work, {"value": value}, number=number)

        def context_value(number):
            return {"branch": branches[number], "base": bases[number][0], "target": "dev",
                    "pr": f"https://github.com/owner/repo/pull/{number}"}

        def prepare_publication(number, *, approve):
            context = context_value(number)
            submit(number, "context", context)
            submit(number, "inspect", "Exact repository context reviewed",
                   actor=f"context-reviewer-{number}")
            submit(number, "consent", {"context": produced(number, "context"),
                "policy": content_hash(self.session.project["policy"]), "decision": "approved"})
            observed = {"repository": "owner/repo", "pr": context["pr"],
                        "head_oid": heads[number], "base_oid": bases[number][1],
                        "base_ref": bases[number][0], "ci": "verified",
                        "review_verified": True}
            submit(number, "observe", observed)
            submit(number, "review", "Exact observed publication reviewed",
                   actor=f"publication-reviewer-{number}")
            if approve:
                submit(number, "approve", {"subject": produced(number, "observe"),
                    "review": produced(number, "review"),
                    "policy": content_hash(self.session.project["policy"]),
                    "decision": "approved"})

        prepare_publication(100, approve=True)
        prepare_publication(101, approve=True)
        prepare_publication(102, approve=False)
        evidence_before = {number: copy.deepcopy(self.read_at(
            number, self.envelope_for(number)["payload"])["evidence"])
            for number in (100, 101, 102)}
        members = [{
            "goal": number, "pr": number, "branch": branches[number],
            "base": bases[number][0], "head": heads[number],
            "base_head": bases[number][1], "implementation_review": "current",
            "ci": "verified", "release": "eligible",
            "authorization": produced(number, "approve") if number in (100, 101) else None,
            "review": produced(number, "review"), "owner": None,
        } for number in (102, 100, 101)]
        before_rejection = copy.deepcopy((self.provider.issues, self.provider.comments))
        incomplete = [row for row in members if row["goal"] != 101]
        rejected = self.session.call(100, {
            "operation": "stack_prepare", "request_id": "public-abc-incomplete",
            "repository": "owner/repo", "target": "dev", "method": "merge",
            "members": incomplete,
        }, expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)member|complete|descendant|topology|provider|unsupported")
        self.assertEqual(before_rejection, (self.provider.issues, self.provider.comments),
                         "Incomplete caller membership cannot persist a plan")
        self.assertEqual([], self.merge_calls)
        prepared = self.session.call(100, {
            "operation": "stack_prepare", "request_id": "public-abc-prepare",
            "repository": "owner/repo", "target": "dev", "method": "merge",
            "members": members,
        })["next_steps"][0]
        self.assertEqual([100, 101, 102], prepared["goals"],
                         "Provider topology, not caller order, freezes the plan")
        plan = self.session.read(100, prepared["plan"])
        self.assertEqual([100, 101, 102], [row["goal"] for row in plan["members"]])
        self.assertEqual([heads[n] for n in (100, 101, 102)],
                         [row["head"] for row in plan["members"]])
        proposal_receipt = self.session.read(100, prepared["receipt"])
        self.assertEqual(prepared["plan_id"], proposal_receipt["content"]["plan_id"])
        self.assertEqual("public-abc-prepare", proposal_receipt["provenance"]["request_id"])

        advance = {"operation": "stack_advance", "request_id": "public-abc-a",
                   "plan_id": prepared["plan_id"], "expected_revision": prepared["revision"]}
        provider_command = self.provider_command
        lost = []
        def committed_but_uncertain(command, *args, **kwargs):
            if list(command[:3]) == ["gh", "pr", "merge"]:
                marker = command[command.index("--body") + 1].splitlines()[-1]
                self.assertNotIn(marker, json.dumps(self.provider.comments),
                                 "The secret nonce must not enter public intent records")
            result = provider_command(command, *args, **kwargs)
            if list(command[:3]) == ["gh", "pr", "merge"] and not lost:
                lost.append(True)
                self.stack_observations[100]["review_verified"] = False
                self.stack_observations[100]["checks_verified"] = False
                raise subprocess.TimeoutExpired(command, 5)
            return result
        self.session.provider_command = committed_but_uncertain
        uncertain = self.session.call(100, advance, expected=None)
        self.assertTrue(lost)
        self.assertEqual(1, len(self.merge_calls))
        self.assertRegex(json.dumps(uncertain), r"(?i)uncertain|observe|reconcile|retry")

        replacement_runtime = copy.deepcopy(self.session.runtime)
        replacement_runtime["root_id"] = "replacement-root"
        resumed = dag_fixtures.TaskSession(self.fixture.repo, self.session.project,
                                           replacement_runtime, self.provider,
                                           self.session.control)
        resumed.provider_command = self.provider_command
        resumed.provider_issue_snapshot = self.session.provider_issue_snapshot
        resumed.portfolio_snapshot = self.session.portfolio_snapshot
        status = resumed.call(100, {"operation": "stack_status",
            "request_id": "public-abc-resume-status", "plan_id": prepared["plan_id"]})
        self.assertRegex(json.dumps(status), r"(?i)observ|reconcil|uncertain")
        attempt_ref = status["next_steps"][0]["attempt"]
        attempt = resumed.read(100, attempt_ref)
        self.assertEqual(prepared["plan_id"], attempt["content"]["plan_id"])
        self.assertEqual("public-abc-a", attempt["content"]["request_id"])
        replay = resumed.call(100, advance)
        self.assertEqual(1, len(self.merge_calls), "Uncertain exact replay cannot dispatch A twice")
        self.assertRegex(json.dumps(replay), r"(?i)observ|reconcil")
        observation_ref = replay["next_steps"][0]["observation"]
        observation = resumed.read(100, observation_ref)
        self.assertEqual(heads[100], observation["content"]["head"])
        self.assertEqual("merged", observation["content"]["state"])
        self.assertEqual(evidence_before[101], self.read_at(
            101, self.envelope_for(101)["payload"])["evidence"])
        self.assertEqual(evidence_before[102], self.read_at(
            102, self.envelope_for(102)["payload"])["evidence"])
        self.assertEqual(len(evidence_before[100]) + 1, len(self.read_at(
            100, self.envelope_for(100)["payload"])["evidence"]),
            "The terminal Result belongs to the merged member, not the coordinator observation")

        self.assertEqual("closed", self.provider.issues[100]["state"])
        reconciled_a = resumed.call(100, {"operation": "stack_advance",
            "request_id": "public-abc-a-reconcile", "plan_id": prepared["plan_id"],
            "expected_revision": prepared["revision"] + 1})
        self.assertRegex(json.dumps(reconciled_a), r"(?i)reconcil|semantic|next effect")
        self.assertEqual(prepared["revision"] + 2,
                         reconciled_a["next_steps"][0]["revision"])
        self.assertEqual(1, len(self.merge_calls),
                         "A reconciliation cannot dispatch B in the same advance")
        old_root = resumed.call(100, {"operation": "stack_advance",
            "request_id": "public-abc-b-old-root", "plan_id": prepared["plan_id"],
            "expected_revision": prepared["revision"] + 2}, expected=2)
        self.assertRegex(json.dumps(old_root), r"(?i)root|authorization|current|stale|reacquire")
        self.assertEqual(1, len(self.merge_calls))
        submit(101, "approve", {"subject": produced(101, "observe"),
            "review": produced(101, "review"),
            "policy": content_hash(self.session.project["policy"]), "decision": "approved"},
            actor="replacement-root", session=resumed)
        def timeout_b(command, *args, **kwargs):
            if list(command[:3]) == ["gh", "pr", "merge"]:
                raise subprocess.TimeoutExpired(command, 5)
            return self.provider_command(command, *args, **kwargs)
        resumed.provider_command = timeout_b
        uncertain_b = resumed.call(100, {"operation": "stack_advance",
            "request_id": "public-abc-b-uncertain", "plan_id": prepared["plan_id"],
            "expected_revision": prepared["revision"] + 2})
        self.assertRegex(json.dumps(uncertain_b), r"(?i)uncertain|observe")
        self.assertEqual(1, len(self.merge_calls))
        member_certificate = self.read_at(101,
            self.envelope_for(101)["payload"])["publication_certificate"]
        resumed.call(101, {"operation": "publication_attempt_retire",
            "request_id": "public-abc-b-member-retire", "certificate": member_certificate,
            "expected_head": heads[101], "expected_marker": self.stack_observations[101]["updated_at"],
            "approved_by": "User approved exact no-effect retirement",
            "attribution": "Reviewed open B after timeout", "reason": "No B merge effect observed"})
        status_b = resumed.call(100, {"operation": "stack_status",
            "request_id": "public-abc-b-retire-status", "plan_id": prepared["plan_id"]})
        recovery = status_b["next_steps"][0]["recovery_contract"]
        recovery["request_id"] = "public-abc-b-coordinator-retire"
        retired_b = resumed.call(100, recovery)
        resumed.provider_command = self.provider_command
        advanced_b = resumed.call(100, {"operation": "stack_advance",
            "request_id": "public-abc-b", "plan_id": prepared["plan_id"],
            "expected_revision": retired_b["next_steps"][0]["revision"]})
        self.assertEqual(2, len(self.merge_calls))
        self.assertRegex(json.dumps(advanced_b), r"(?i)dispatch|observ|reconcile|pending")

    def test_strict_ci_blocks_integration_and_only_reviewed_disabled_configuration_permits_it(self):
        for mode in ("inspect_exact_pr_head", "disabled"):
            with self.subTest(mode=mode):
                self.observation.update(checks_verified=True, merged=False, merged_at=None, merge_commit=None, review_verified=True)
                z._workflow_section(self.session.project, "verification_testing")["configuration"]["required_ci"] = mode
                self.configure()
                self.authorize_context()
                authority = self.approve_publication()
                self.submit_role("finish", "Complete exact evidence")
                request = self.integration_request(authority)
                self.observation["checks_verified"] = False
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                previous_merges = len(self.merge_calls)
                if mode == "inspect_exact_pr_head":
                    response = self.session.call(100, request, expected=2)
                    self.assertRegex(json.dumps(response), r"(?i)CI|checks|stale|current|evidence")
                    self.assertEqual(before, (self.provider.issues, self.provider.comments))
                    self.assertEqual(previous_merges, len(self.merge_calls))
                    self.observation["checks_verified"] = True
                self.session.call(100, request)
                self.assertEqual(previous_merges + 1, len(self.merge_calls))

    def test_strict_ci_blocks_complete_and_reviewed_disabled_ci_preserves_current_terminal_requirement(self):
        for mode in ("inspect_exact_pr_head", "disabled"):
            with self.subTest(mode=mode):
                self.observation.update(checks_verified=True, merged=False, merged_at=None, merge_commit=None, review_verified=True)
                z._workflow_section(self.session.project, "verification_testing")["configuration"]["required_ci"] = mode
                self.configure()
                self.authorize_context()
                authority = self.approve_publication()
                self.mark_merged()
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                request = {"operation": "complete", "authorization": authority, "request_id": "complete-" + mode}
                self.session.call(100, request, expected=2)
                self.assertEqual(before, (self.provider.issues, self.provider.comments), "Even disabled CI cannot replace missing terminal Result")
                self.submit_role("finish", "Current complete graph")
                self.observation["checks_verified"] = False
                if mode == "inspect_exact_pr_head":
                    before = copy.deepcopy((self.provider.issues, self.provider.comments))
                    response = self.session.call(100, request, expected=2)
                    self.assertRegex(json.dumps(response), r"(?i)CI|checks|stale|current|evidence")
                    self.assertEqual(before, (self.provider.issues, self.provider.comments))
                    self.observation["checks_verified"] = True
                self.session.call(100, request)
                self.assertEqual("closed", self.provider.issues[100]["state"])

    def reconciliation_request(self):
        steps = self.session.checkpoint(100)
        candidates = [step for step in steps if step.get("submission", {}).get("operation") == "reconcile"]
        self.assertTrue(candidates, "External merge must expose exact readback reconciliation")
        return copy.deepcopy(candidates[0]["submission"])

    def test_external_merge_cannot_mint_missing_results_and_exact_replay_preserves_history(self):
        self.authorize_context()
        self.mark_merged()
        request = self.reconciliation_request()
        prior = copy.deepcopy(self.payload()[1]["evidence"])
        for change in ({"expected_digest": "0" * 64}, {"expected_merge": "sha256:" + "0" * 64}):
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            self.session.call(100, {**request, **change}, expected=2)
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
        request["request_id"] = "incomplete-external-merge"
        self.session.call(100, request)
        self.assertEqual("open", self.provider.issues[100]["state"])
        self.assertEqual(prior, self.payload()[1]["evidence"], "Reconciliation cannot issue semantic Results")
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, request)
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))
        self.assertFalse(any(step.get("kind") == "complete" for step in self.session.checkpoint(100)))

    def test_external_merge_preserves_owned_worker_until_exact_observed_stop(self):
        self.authorize_context()
        work = self.session.acquire(self.ids["observe"])
        self.mark_merged()
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        steps = self.session.checkpoint(100)
        reconcile = [step for step in steps if step.get("submission", {}).get("operation") == "reconcile"]
        if reconcile:
            response = self.session.call(100, reconcile[0]["submission"], expected=2)
            self.assertRegex(json.dumps(response), r"(?i)worker|lease|stopped|owner")
        else:
            self.assertRegex(json.dumps(steps), r"(?i)worker|lease|stopped|owner")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertTrue(any(lease["token"] == work["lease"]["token"] for lease in self.payload()[1]["operational"]["leases"]))
        with mock.patch.object(z._workflow.time, "time", return_value=work["lease"]["expires_at"] + 1):
            steps = self.session.checkpoint(100)
            recovery = [step for step in steps if "recovery_contract" in step or step.get("kind") == "recover"]
            self.assertTrue(recovery)
            request = copy.deepcopy(recovery[0].get("submission", recovery[0].get("recovery_contract")))
            request.update(worker_status="stopped", evidence="Observed publication worker terminal state")
            self.session.call(100, request)
        request = self.reconciliation_request()
        self.session.call(100, request)
        self.assertEqual("open", self.provider.issues[100]["state"], "Stopped work still supplies no missing Result")

    def test_external_merge_closes_only_current_terminal_and_partial_close_replay_repairs(self):
        self.authorize_context()
        self.approve_publication()
        self.submit_role("finish", "Current complete graph")
        self.mark_merged()
        request = self.reconciliation_request()
        request["request_id"] = "complete-external-merge"
        prior = copy.deepcopy(self.payload()[1]["evidence"])
        self.session.call(100, request)
        self.assertEqual("closed", self.provider.issues[100]["state"])
        self.assertEqual(prior, self.payload()[1]["evidence"])
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, request)
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))
        self.provider.issues[100]["state"] = "open"
        body = self.provider.issues[100]["body"]
        response = self.session.call(100, request, expected=None)
        self.assertTrue(any(step.get("kind") == "repair" for step in response["next_steps"]))
        self.assertEqual(body, self.provider.issues[100]["body"], "Stored receipt cannot silently claim closure after provider partial state")


class GenericDeliveryPublicTests(DagFixture):
    # Reuse fixture helpers, not test-case inheritance or semantic engine answers.
    def setUp(self):
        super().setUp()
        self.setup_publication()

    setup_publication = GenericPublicationPublicTests.setup_publication
    configure = GenericPublicationPublicTests.configure
    provider_command = GenericPublicationPublicTests.provider_command
    mark_merged = GenericPublicationPublicTests.mark_merged
    submit_role = GenericPublicationPublicTests.submit_role
    observed_value = GenericPublicationPublicTests.observed_value
    integration_request = GenericPublicationPublicTests.integration_request
    with_merge_observation = GenericPublicationPublicTests.with_merge_observation
    merge_value = GenericPublicationPublicTests.merge_value
    workspace_graph = dag_fixtures.WorkspaceAuthorityPublicTests.workspace_graph
    setup_workspace = dag_fixtures.WorkspaceAuthorityPublicTests.setup_workspace
    acquire_workspace = dag_fixtures.WorkspaceAuthorityPublicTests.acquire_workspace
    candidate = dag_fixtures.WorkspaceAuthorityPublicTests.candidate
    review_candidate = dag_fixtures.WorkspaceAuthorityPublicTests.review_candidate
    red_candidate = dag_fixtures.WorkspaceAuthorityPublicTests.red_candidate

    setup_parent_workspace = dag_fixtures.WorkspaceAuthorityPublicTests.setup_parent_workspace
    setup_relationship_transport = dag_fixtures.RelationshipPublicTests.setup_relationship_transport
    envelope_for = dag_fixtures.RelationshipPublicTests.envelope_for
    put_envelope = dag_fixtures.RelationshipPublicTests.put_envelope
    add_goal = dag_fixtures.RelationshipPublicTests.add_goal
    read_at = dag_fixtures.RelationshipPublicTests.read_at
    result_at = dag_fixtures.RelationshipPublicTests.result_at
    resolutions = dag_fixtures.RelationshipPublicTests.resolutions

    def test_reviewed_red_green_proofs_commit_and_exact_publication_form_one_delivery_graph(self):
        self.connected_delivery()

    def connected_delivery(self):
        self.configure(renamed=True)
        publication = self.with_merge_observation(copy.deepcopy(self.graph))
        self.session.git("checkout", "-q", "goal-child")
        def composed(graph, _allocations):
            observer = next(node for node in publication["nodes"] if node["id"] == self.ids["observe"])
            observer["requires"].append(selector("accept_beta"))
            observer["inputs"]["candidate"] = {"producer": {"node": selector("beta")}, "output": "value", "path": [], "mode": "identity", "type": {"kind": "string"}}
            graph["nodes"].extend(copy.deepcopy(publication["nodes"]))
            graph["terminals"] = copy.deepcopy(publication["terminals"])
        self.setup_workspace(composed)
        self.submit_role("context", self.context)
        self.submit_role("inspect", "Independent exact repository context", actor="context-reviewer")
        self.submit_role("consent", {"context": self.produced(self.ids["context"]), "policy": content_hash(self.session.project["policy"]), "decision": "approved"})
        self.assertNotIn(self.ids["observe"], self.names(), "Repository authority cannot substitute for implementation evidence")
        alpha = self.acquire_workspace("alpha")
        (self.fixture.repo / "behavior_test.py").write_text("from source import value\nassert value() == 2\n")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        fabricated = self.session.submission(alpha, {"value": "Claimed failing tests without observed checks"}, "unobserved-red")
        response = self.session.call(100, fabricated, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)proof|verification|check|baseline")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        red_reference, red = self.candidate(alpha, 1)
        self.review_candidate("alpha", 1)
        self.assertEqual(1, red["commands"][0]["exit_code"])
        beta = self.acquire_workspace("beta")
        self.assertIn(red_reference["hash"], json.dumps(beta["lease"]["acquisition"]))
        (self.fixture.repo / "source.py").write_text("def value():\n    return 2\n")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, self.session.submission(beta, {"value": "Claimed passing implementation without observed checks"}, "unobserved-green"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)proof|verification|check")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        green_reference, green = self.candidate(beta, 0)
        self.assertNotIn(self.ids["observe"], self.names(), "Candidate must receive its separate verification and review")
        self.review_candidate("beta", 0)
        self.session.git("add", "source.py", "behavior_test.py")
        self.session.git("commit", "-qm", "verified generic delivery")
        self.observation["head_oid"] = self.session.git("rev-parse", "HEAD")
        self.assertEqual(self.fixture.base_oid, self.session.git("rev-parse", "dev"))
        observer = self.session.acquire(self.ids["observe"])
        self.assertIn(self.produced("beta")["hash"], json.dumps(observer["lease"]["acquisition"]))
        self.session.finish(observer, {"value": self.observed_value()})
        self.assertEqual(red, self.read_blob(red_reference))
        self.assertEqual(green, self.read_blob(green_reference))
        self.submit_role("review", "Reviewed exact head and connected passing proof", actor="publication-reviewer")
        self.assertNotIn(self.ids["finish"], self.names())
        self.submit_role("approve", {"subject": self.produced(self.ids["observe"]), "review": self.produced(self.ids["review"]), "policy": content_hash(self.session.project["policy"]), "decision": "approved"})
        self.assertNotIn(self.ids["finish"], self.names())
        request = self.integration_request(self.produced(self.ids["approve"]))
        request["request_id"] = "connected-delivery-integration"
        self.session.call(100, request)
        self.assertEqual(1, len(self.merge_calls))
        self.assertTrue(self.observation["merged"])
        post_effect = self.session.acquire("observed_merge")
        self.session.finish(post_effect, {"value": self.merge_value()})
        self.submit_role("finish", "Current connected delivery and observed merge evidence")
        self.assertEqual(red, self.read_blob(red_reference))
        self.assertEqual(green, self.read_blob(green_reference))
        self.assertEqual(0, green["commands"][0]["exit_code"])

    def prepare_reviewed_first_sibling(self, allocation_mutator, observer):
        """Exercise the workspace consumer contract without publishing a PR.

        Exact Git bytes, observed checks, parent grants, review/root authority,
        and historical provider reads remain real. Publication is a separate
        producer contract covered by connected_delivery, not a sibling input.
        """
        self.setup_relationship_transport()
        self.session.git("checkout", "-q", "goal-child")
        deferred = []

        def allocate(graph, manifest):
            deferred.append(allocation_mutator(graph, manifest))

        def extend(graph):
            for mutate in deferred:
                mutate(graph)

        self.setup_parent_workspace(allocate, extend)
        observer("prepared")
        alpha = self.acquire_workspace("alpha")
        (self.fixture.repo / "behavior_test.py").write_text("from source import value\nassert value() == 2\n")
        red_ref, red = self.candidate(alpha, 1)
        self.review_candidate("alpha", 1)
        beta = self.acquire_workspace("beta")
        self.assertIn(red_ref["hash"], json.dumps(beta["lease"]["acquisition"]))
        (self.fixture.repo / "source.py").write_text("def value():\n    return 2\n")
        green_ref, green = self.candidate(beta, 0)
        observer("candidate")
        self.review_candidate("beta", 0)
        observer("reviewed")
        self.session.git("add", "source.py", "behavior_test.py")
        self.session.git("commit", "-qm", "reviewed first sibling workspace")
        self.assertEqual(self.fixture.base_oid, self.session.git("rev-parse", "dev"))
        self.assertEqual(red, self.read_blob(red_ref))
        self.assertEqual(green, self.read_blob(green_ref))

    def test_second_sibling_consumes_reviewed_committed_first_proof_without_rewriting_history(self):
        import sys
        (self.fixture.repo / "second_source.py").write_text("value = 1\n")
        self.session.git("add", "second_source.py")
        self.session.git("commit", "-qm", "second sibling baseline")
        # Setup changed dev before any delivery work; bind the actual new base.
        self.fixture.base_oid = self.session.git("rev-parse", "dev")
        self.observation["base_oid"] = self.fixture.base_oid
        prepared = {}
        def allocation(graph, manifest):
            second_manifest = copy.deepcopy(manifest)
            for name, entry in second_manifest["allocations"].items():
                entry["task"]["goal"] = 102
                entry["task"]["node"] = "second_" + name
                entry["owned"] = {"alpha": ["second_test.py"], "beta": ["second_source.py"], "gamma": []}[name]
                entry["consumed"] = ["source.py", "behavior_test.py", "read_dependency.txt", "second_source.py", "second_test.py"]
                manifest["allocations"]["second_" + name] = copy.deepcopy(entry)
            approval = task("accept_first_root", ["accept_beta"], role="root")
            approval["inputs"] = {"candidate": dag_fixtures.subject_input("beta"),
                                  "review": dag_fixtures.subject_input("accept_beta")}
            graph["nodes"].append(approval)
            def add_second(shared):
                names = {"alpha", "observe_alpha", "accept_alpha", "beta", "observe_beta", "accept_beta", "gamma"}
                clones = [copy.deepcopy(node) for node in shared["nodes"] if node["id"] in names]
                def rename(value):
                    if isinstance(value, dict):
                        for key, child in value.items():
                            if key == "node" and isinstance(child, str) and child in names:
                                value[key] = "second_" + child
                            else:
                                rename(child)
                    elif isinstance(value, list):
                        for child in value: rename(child)
                rename(clones)
                for node in clones:
                    node["id"] = "second_" + node["id"] if not node["id"].startswith("second_") else node["id"]
                for node in clones:
                    if node["id"] not in ("second_alpha", "second_beta", "second_gamma"):
                        continue
                    node["requires"].append({"kind": "node", "goal": 100, "node": "accept_first_root"})
                    for key, name in (("first_candidate", "beta"), ("first_review", "accept_beta"), ("first_root", "accept_first_root")):
                        node["inputs"][key] = dag_fixtures.subject_input(name)
                        node["inputs"][key]["producer"]["node"]["goal"] = 100
                    for slot, original in (("parent_allocation", "allocation"), ("parent_authorization", "authorization"), ("parent_approval", "approval")):
                        node["inputs"][slot] = copy.deepcopy(node["inputs"][original])
                        node["inputs"][slot]["producer"]["node"]["goal"] = 99
                        if slot == "parent_allocation":
                            node["inputs"][slot]["path"] = ["allocations", node["id"]]
                second_approval = task("accept_second_root", role="root")
                second_approval["executor"]["authority"]["subject"]["goal"] = "#this"
                second_approval["requires"] = [{**selector("second_accept_beta"), "goal": "#this"}]
                second_approval["inputs"] = {"candidate": dag_fixtures.subject_input("second_beta"),
                                             "review": dag_fixtures.subject_input("second_accept_beta")}
                for binding in second_approval["inputs"].values():
                    binding["producer"]["node"]["goal"] = "#this"
                gamma = next(node for node in clones if node["id"] == "second_gamma")
                gamma["requires"].append({**selector("accept_second_root"), "goal": "#this"})
                gamma["inputs"]["second_root"] = dag_fixtures.subject_input("accept_second_root")
                gamma["inputs"]["second_root"]["producer"]["node"]["goal"] = "#this"
                shared["nodes"].extend([*clones, second_approval])
                prepared.update(graph=shared, manifest=second_manifest)
            return add_second
        def second_output(name, slot="value"):
            return self.result_at(102, name)[1]["outputs"][slot]
        def observe(stage):
            if stage == "prepared":
                self.add_goal(102, prepared["graph"], parent=99)
                self.session.finish(self.session.acquire("charter", number=102), {"grant": prepared["manifest"]}, number=102)
                permit = {"manifest": second_output("charter", "grant"),
                          "tasks": [entry["task"] for entry in prepared["manifest"]["allocations"].values()],
                          "policy": content_hash(self.session.project["policy"]), "decision": "approved"}
                self.session.finish(self.session.acquire("inspect_charter", number=102, actor="second-allocation-reviewer"), {"permit": permit}, number=102)
                self.session.finish(self.session.acquire("consent", number=102), {"permit": permit}, number=102)
            self.assertFalse(any(step["node"]["node"] == "second_alpha" for step in self.session.ready(102)),
                             "First candidate needs both current independent review and root acceptance")
            if stage == "reviewed":
                self.session.finish(self.session.acquire("accept_first_root"), {"value": "Root accepts exact independently reviewed first sibling"})
                self.assertTrue(any(step["node"]["node"] == "second_alpha" for step in self.session.ready(102)))
        self.prepare_reviewed_first_sibling(allocation, observe)
        first_envelope = self.envelope_for(100)
        first_envelope["state"] = "archived"
        first_envelope["revision"] += 1
        self.put_envelope(100, first_envelope)
        self.provider.issues[100]["state"] = "closed"
        # Seed a fully addressed but disconnected historical Result/proof chain
        # before freezing history. Current payload selection, not cache eviction,
        # makes the corrupt predecessor observable to the second child.
        valid_payload = self.read_blob(first_envelope["payload"])
        beta_result_ref, beta_result = self.result("beta")
        bad_artifact = copy.deepcopy(self.read_blob(beta_result["outputs"]["value"]))
        bad_proof = copy.deepcopy(self.read_blob(bad_artifact["provenance"]["source"]))
        bad_proof["acquisition_hash"] = "sha256:" + "0" * 64
        bad_artifact["provenance"]["source"] = self.blob(bad_proof)
        bad_result = copy.deepcopy(self.read_blob(beta_result_ref))
        bad_result["content"]["outputs"]["value"] = self.blob(bad_artifact)
        bad_result_ref = self.blob(bad_result)
        bad_payload = copy.deepcopy(valid_payload)
        bad_payload["evidence"] = [bad_result_ref if ref == beta_result_ref else ref for ref in bad_payload["evidence"]]
        bad_payload_ref = self.blob(bad_payload)
        unknown_artifact = copy.deepcopy(self.read_blob(beta_result["outputs"]["value"]))
        unknown_artifact["provenance"]["source"] = {"hash": "sha256:" + "9" * 64, "uri": "urn:sha256:" + "9" * 64}
        unknown_result = copy.deepcopy(self.read_blob(beta_result_ref))
        unknown_result["content"]["outputs"]["value"] = self.blob(unknown_artifact)
        unknown_result_ref = self.blob(unknown_result)
        unknown_payload = copy.deepcopy(valid_payload)
        unknown_payload["evidence"] = [unknown_result_ref if ref == beta_result_ref else ref for ref in unknown_payload["evidence"]]
        unknown_payload_ref = self.blob(unknown_payload)
        second_envelope = self.envelope_for(102)
        second_payload = copy.deepcopy(self.read_at(102, second_envelope["payload"]))
        changed_spec = copy.deepcopy(self.read_at(102, second_payload["spec"]))
        changed_spec["content"] = "Different second allocation requires new independent authorization"
        offset = len(self.provider.comments[100])
        second_payload["spec"] = self.blob(changed_spec)
        stale_second_ref = self.blob(second_payload)
        for comment in copy.deepcopy(self.provider.comments[100][offset:]):
            self.provider.create_issue_comment(102, comment["body"])
        frozen_first = copy.deepcopy((self.provider.issues[100], self.provider.comments[100]))
        frozen_parent = copy.deepcopy((self.provider.issues[99], self.provider.comments[99]))
        first_candidate = self.produced("beta")
        first_proof = self.read_blob(first_candidate)["provenance"]["source"]
        proof_bytes = self.read_blob(first_proof)
        self.session.git("checkout", "-qb", "second-sibling")
        start_step = next(step for step in self.session.ready(102) if step["node"]["node"] == "second_alpha")
        stale_start = {**start_step["start"], "policy_receipt": json.loads(Path(start_step["policy"]["path"]).read_text())["policy_receipt"]}
        stale_start.pop("request_id", None)
        stable_second = copy.deepcopy(self.provider.issues[102])
        for label, number, envelope, payload_ref in (
                ("disconnected_first_proof", 100, first_envelope, bad_payload_ref),
                ("unknown_first_proof", 100, first_envelope, unknown_payload_ref),
                ("stale_second_allocation_contract", 102, second_envelope, stale_second_ref)):
            with self.subTest(boundary=label):
                self.put_envelope(number, {**envelope, "payload": payload_ref, "revision": envelope["revision"] + 1})
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                self.session.call(102, stale_start, expected=2)
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
                self.provider.issues[100] = copy.deepcopy(frozen_first[0])
                self.provider.issues[102] = copy.deepcopy(stable_second)
                self.assertEqual(start_step["input_hash"], next(step["input_hash"] for step in self.session.ready(102) if step["node"]["node"] == "second_alpha"))
        def candidate(name, expected):
            work = self.session.acquire(name, number=102, actor="second-writer-" + name)
            self.assertIn(first_candidate["hash"], json.dumps(work["lease"]["acquisition"]))
            self.assertIn(first_proof["hash"], json.dumps(work["lease"]["acquisition"]))
            if name == "second_alpha":
                (self.fixture.repo / "second_test.py").write_text("from second_source import value\nassert value == 2\n")
            else:
                (self.fixture.repo / "second_source.py").write_text("value = 2\n")
            request = self.session.submission(work, {"value": "Exact second " + name}, "second-" + name)
            request["workspace_checks"] = [[sys.executable, "-B", "second_test.py"]]
            self.session.call(102, request)
            ref = self.read_at(102, second_output(name))["provenance"]["source"]
            self.assertEqual(expected, self.read_at(102, ref)["commands"][0]["exit_code"])
            for check, actor in (("observe_", "second-checker"), ("accept_", "second-reviewer")):
                self.session.finish(self.session.acquire("second_" + check + name.removeprefix("second_"), number=102, actor=actor), {"value": "Exact second proof reviewed"}, number=102)
            self.assertEqual(frozen_first, (self.provider.issues[100], self.provider.comments[100]))
            self.assertEqual(frozen_parent, (self.provider.issues[99], self.provider.comments[99]))
            self.assertEqual(proof_bytes, self.read_blob(first_proof))
        candidate("second_alpha", 1)
        self.session.git("add", "second_test.py")
        self.session.git("commit", "-qm", "second sibling observed red test")
        candidate("second_beta", 0)
        self.assertFalse(any(step["node"]["node"] == "second_gamma" for step in self.session.ready(102)),
                         "Second sibling independent review cannot replace its configured root approval")
        self.session.finish(self.session.acquire("accept_second_root", number=102),
                            {"value": "Root accepts exact second candidate and independent review"}, number=102)
        self.session.git("add", "second_source.py")
        self.session.git("commit", "-qm", "second sibling observed green implementation")
        ready = next(step for step in self.session.ready(102) if step["node"]["node"] == "second_gamma")
        corrupt = {**first_envelope, "payload": bad_payload_ref, "revision": first_envelope["revision"] + 1}
        self.put_envelope(100, corrupt)
        self.assertFalse(any(step.get("kind") == "execute" and step.get("node", {}).get("node") == "second_gamma"
                             for step in self.session.checkpoint(102)))
        # Restore the exact provider snapshot; no workflow decision is patched.
        self.provider.issues[100] = copy.deepcopy(frozen_first[0])
        self.assertEqual(ready["input_hash"], next(step["input_hash"] for step in self.session.ready(102) if step["node"]["node"] == "second_gamma"))
        for name, changed in (("source.py", "def value():\n    return 1\n"), ("read_dependency.txt", "unrelated consumed drift\n")):
            path = self.fixture.repo / name
            original = path.read_bytes()
            path.write_text(changed)
            steps = self.session.checkpoint(102)
            self.assertFalse(any(step.get("kind") == "execute" and step.get("node", {}).get("node") == "second_gamma" for step in steps))
            path.write_bytes(original)
            self.assertEqual(ready["input_hash"], next(step["input_hash"] for step in self.session.ready(102) if step["node"]["node"] == "second_gamma"))
        final = self.session.acquire("second_gamma", number=102)
        self.session.finish(final, {"value": "Both sibling transformations remain connected"}, number=102)
        self.assertEqual(frozen_first, (self.provider.issues[100], self.provider.comments[100]))
        self.assertEqual(proof_bytes, self.read_blob(first_proof))



class RelationshipDeliveryContractTests(DagFixture):
    """Consume delivered evidence without replaying its production journey.

    GenericDeliveryPublicTests proves red/green checks and publication issue the
    evidence. This contract exercises the independent consumer boundary through
    real dispatch, immutable storage and targeted archived-provider reads.
    """

    setup_relationship_transport = dag_fixtures.RelationshipPublicTests.setup_relationship_transport
    envelope_for = dag_fixtures.RelationshipPublicTests.envelope_for
    put_envelope = dag_fixtures.RelationshipPublicTests.put_envelope
    add_goal = dag_fixtures.RelationshipPublicTests.add_goal
    read_at = dag_fixtures.RelationshipPublicTests.read_at
    result_at = dag_fixtures.RelationshipPublicTests.result_at
    resolutions = dag_fixtures.RelationshipPublicTests.resolutions

    def prepare_children(self):
        self.setup_relationship_transport()
        observed = task("observed_merge")
        shared = selector("observed_merge")
        inspect = task("inspect_shared_merge")
        inspect["executor"]["authority"]["subject"]["goal"] = "#this"
        inspect["requires"] = [shared]
        inspect["inputs"] = {"merge": dag_fixtures.subject_input("observed_merge")}
        inspect["independent_of"] = [shared]
        finish = task("finish", role="root")
        finish["executor"]["authority"]["subject"]["goal"] = "#this"
        finish["requires"] = [shared, {**selector("inspect_shared_merge"), "goal": "#this"}]
        finish["inputs"] = {
            "merge": dag_fixtures.subject_input("observed_merge"),
            "shared_merge_review": dag_fixtures.subject_input("inspect_shared_merge"),
        }
        finish["inputs"]["shared_merge_review"]["producer"]["node"]["goal"] = "#this"
        children = {"kind": "node", "goal": "#children", "node": "finish"}
        collect = task("collect", role="root")
        collect["executor"]["authority"]["subject"]["goal"] = 99
        collect["requires"] = [children]
        collect["inputs"] = {"children": {"producer": {"node": children}, "output": "value",
            "path": [], "mode": "identity", "type": {"kind": "map", "values": {"kind": "string"}}}}
        graph = {"nodes": [observed, inspect, finish, collect], "task_sets": [],
                 "terminals": [{**selector("collect"), "goal": 99}]}
        self.install(graph)
        self.add_goal(99, graph)
        envelope = self.envelope_for(100)
        envelope["parent"] = 99
        self.put_envelope(100, envelope)
        self.add_goal(101, graph, parent=99)
        self.session.finish(self.session.acquire("observed_merge", actor="merge-observer"),
                            {"value": "Delivered merge evidence supplied at the consumer boundary"})
        self.assertFalse(any(step["node"]["node"] == "collect" for step in self.session.ready(99)))
        review = self.session.acquire("inspect_shared_merge", actor="first-independent-reviewer")
        self.session.finish(review, {"value": "Independent review of exact delivered evidence"})
        self.session.finish(self.session.acquire("finish"), {"value": "First child accepted exact delivery"})

    def test_parent_requires_both_children_current_terminals_and_archived_evidence(self):
        self.prepare_children()
        self.assertFalse(any(step["node"]["node"] == "collect" for step in self.session.ready(99)),
                         "One delivered child cannot replace its still-unreviewed sibling")
        inspect = self.session.acquire("inspect_shared_merge", number=101, actor="shared-merge-reviewer")
        self.assertIn(self.produced("observed_merge")["hash"], json.dumps(inspect["lease"]["acquisition"]))
        self.session.finish(inspect, {"value": "Independent review of exact shared delivered merge"}, number=101)
        self.assertFalse(any(step["node"]["node"] == "collect" for step in self.session.ready(99)))
        checkpoint = self.session.checkpoint(101)
        if len(checkpoint) == 1 and checkpoint[0]["kind"] == "hydration_checkpoint":
            self.session.call(101, checkpoint[0]["submission"])
        finish = self.session.acquire("finish", number=101)
        self.session.finish(finish, {"value": "Second child root accepted exact reviewed delivery"}, number=101)
        self.assertTrue(any(step["node"]["node"] == "collect" for step in self.session.ready(99)))
        sibling_output = self.result_at(101, "finish")[1]["outputs"]["value"]
        envelope = self.envelope_for(101)
        envelope["state"] = "archived"
        envelope["revision"] += 1
        self.put_envelope(101, envelope)
        self.provider.issues[101]["state"] = "closed"
        self.assertTrue(any(step["node"]["node"] == "collect" for step in self.session.ready(99)),
                        "Archived required child keeps exact usable terminal evidence")
        exact = copy.deepcopy(envelope)
        unknown = copy.deepcopy(envelope)
        unknown["revision"] += 1
        unknown["payload"] = {"hash": "sha256:" + "0" * 64, "uri": "urn:sha256:" + "0" * 64}
        self.put_envelope(101, unknown)
        blocked = self.session.call(99, expected=None)
        self.assertFalse(any(step.get("node", {}).get("node") == "collect" and step.get("kind") == "execute"
                             for step in blocked["next_steps"]))
        self.assertRegex(json.dumps(blocked), r"(?i)unknown|artifact|unavailable|missing|relationship")
        self.assertEqual("closed", self.provider.issues[101]["state"])
        exact["revision"] = unknown["revision"] + 1
        self.put_envelope(101, exact)
        aggregate = self.session.acquire("collect", number=99)
        acquisition = json.dumps(aggregate["lease"]["acquisition"])
        self.assertIn(self.produced("finish")["hash"], acquisition)
        self.assertIn(sibling_output["hash"], acquisition)
        selected = [r for r in self.resolutions(aggregate) if r["selector"]["goal"] == "#children"]
        self.assertTrue(selected)
        self.assertTrue(all({100, 101} == {t["goal"] for t in r["targets"]} for r in selected))
        self.session.finish(aggregate, {"value": "Both canonical children delivered and currently accepted"}, number=99)
        self.assertFalse(any(step.get("kind") == "execute" and step.get("node", {}).get("node") == "collect"
                             for step in self.session.ready(99)))
        aggregate_output = self.result_at(99, "collect")[1]["outputs"]["value"]
        self.assertEqual("Both canonical children delivered and currently accepted",
                         self.read_at(99, aggregate_output)["content"])


if __name__ == "__main__":
    unittest.main()
