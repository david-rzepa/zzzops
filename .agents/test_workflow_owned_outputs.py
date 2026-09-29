"""Owned source/test outputs, exercised through the real public CLI dispatcher.

Only provider, reviewed configuration, package and heartbeat boundaries are faked.
ZZZOPS_OLD_CLI_ARCHIVE optionally supplies a pristine checkout archive for the
actual-version handoff test. The archive stays outside the repository.
"""
from __future__ import annotations

import contextlib
import base64
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time
from types import SimpleNamespace
import unittest
import zlib
from unittest import mock

import test_workflow_journey as fixtures
from test_goal_history_delta import legacy_history_body, semantic_predecessor

z = fixtures.z


def content_hash(value):
    return 'sha256:' + hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
    ).encode()).hexdigest()


def file_hash(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else 'missing'


class PublicSession:
    """Public dispatch against real files and an in-memory remote provider."""

    def __init__(self, repo, project, runtime, provider, control, api=z, pull_request_states=None):
        self.repo, self.project, self.runtime = Path(repo), project, runtime
        self.provider, self.control, self.api = provider, Path(control), api
        self.pull_request_states = pull_request_states
        self.sequence = 0
        self.calls = []
        self.consumed = ['source.py', 'behavior_test.py', 'read_dependency.txt']
        self.test_path = 'behavior_test.py'
        self.plan = {
            'behavior': 'The function returns two; tests and source may be edited under owned execution.',
            'output_scope': {'parent': 100, 'child': 101,
                             'test_design': [self.test_path], 'implement': ['source.py']},
        }
        self.plan_review = {'decision': 'approved', 'finding': 'Scope and verification satisfy the requested behavior.'}

    def goal(self, number):
        return self.api.github_goal_record(self.provider.get_issue(number))

    def portfolio_snapshot(self, *_args, **_kwargs):
        """Mirror the production gateway, including hydrated PR evidence."""
        goals = [self.goal(number) for number in sorted(self.provider.issues)]
        targets = [goal for goal in goals if isinstance((goal.get('implementation') or {}).get('pr'), str)]
        if targets and self.pull_request_states is not None:
            selected = [{'number': goal['key']} for goal in targets]
            bodies = {goal['key']: {'body': self.provider.get_issue(goal['key'])['body']} for goal in targets}
            states, _bytes, _processes = self.pull_request_states(self.repo, 'gh', selected, bodies)
            for goal in targets:
                goal['pull_request'] = states.get(goal['key'])
        return {'complete': True, 'valid': True, 'goals': goals}

    def call(self, number, payload=None, *, expected=0, intent="execute"):
        self.sequence += 1
        runtime = self.control / 'runtime.json'
        runtime.write_text(json.dumps(self.runtime))
        argv = ['zzzops', '--repo', str(self.repo), 'workflow', '--intent', intent,
                '--goal', str(number), '--runtime', str(runtime)]
        if payload is not None:
            payload = copy.deepcopy(payload)
            payload.setdefault('request_id', f'public-{time.time_ns()}-{self.sequence}')
            request = self.control / 'input.json'
            request.write_text(json.dumps(payload))
            argv += ['--input', str(request)]
        api = self.api
        real_run = subprocess.run

        def provider_command(command, *args, **kwargs):
            custom = getattr(self, 'provider_command', None)
            if custom is not None:
                observed = custom(command, *args, **kwargs)
                if observed is not None:
                    return observed
            if list(command[:3]) == ['gh', 'pr', 'list']:
                return subprocess.CompletedProcess(command, 0, stdout='[]', stderr='')
            return real_run(command, *args, **kwargs)
        with contextlib.ExitStack() as stack:
            # These are external configuration/provider boundaries, never workflow decisions.
            patches = [
                mock.patch.object(subprocess, 'run', side_effect=provider_command),
                mock.patch.object(api, 'configure_cli_stdout'),
                mock.patch.object(api._package, 'package_status', return_value={'ok': True}),
                mock.patch.object(api, 'workflow_context_step', return_value=None),
                mock.patch.object(api, 'reviewed_project_state', side_effect=lambda _repo: copy.deepcopy(self.project)),
                mock.patch.object(api, 'GitHubGoalTransitionAdapter', return_value=self.provider),
                mock.patch.object(api, 'GitHubReservationAdapter', return_value=getattr(self, 'reservation_adapter', SimpleNamespace())),
                mock.patch.object(api, 'portfolio_snapshot', side_effect=self.portfolio_snapshot),
                *([] if getattr(self, 'reservation_adapter', None) is not None else [
                    mock.patch.object(api, 'acquire_storage_lock', side_effect=lambda *_a, **_k: {'acquired': True, 'expires_at': time.time() + 300}),
                    mock.patch.object(api, 'renew_storage_lock', side_effect=lambda *_a, **_k: {'acquired': True, 'expires_at': time.time() + 300}),
                    mock.patch.object(api, 'release_storage_lock', return_value={'released': True}),
                ]),
                mock.patch.object(api._heartbeat, 'stop_heartbeat',
                                  side_effect=getattr(self, 'heartbeat_stop', None)),
                mock.patch.object(sys, 'argv', argv),
                mock.patch.object(sys, 'stdout', io.StringIO()),
            ]
            for patch in patches:
                stack.enter_context(patch)
            try:
                code = api.main()
            except StopIteration as exc:
                raise AssertionError('Public verify lost its eligible phase after an owned edit '
                                     '(frontier StopIteration); complete reviewed fixture supplied') from exc
            response = json.loads(sys.stdout.getvalue())
        self.calls.append({'operation': (payload or {}).get('operation', 'checkpoint'),
                           'goal': number, 'code': code, 'response': response})
        if expected is not None and code != expected:
            raise AssertionError(f'public {number} {(payload or {}).get("operation", "checkpoint")}: '
                                 f'expected exit {expected}, got {code}: {response}')
        return response

    def checkpoint(self, number):
        return self.call(number)['next_steps']

    def assess(self, number, phase):
        step = next(s for s in self.checkpoint(number) if s.get('phase') == phase)
        self.call(number, {'operation': 'assess', 'phase': phase, 'input_hash': step['input_hash'],
                          'files': list(self.consumed),
                          'dimensions': {'consequence': 'bounded', 'boundedness': 'atomic',
                                         'engineering_rigor': 'structured'}})

    def start(self, number, phase, kind='execute'):
        steps = self.checkpoint(number)
        step = next((s for s in steps if s.get('phase') == phase), None)
        if step and step['kind'] == 'assess':
            self.assess(number, phase)
            steps = self.checkpoint(number)
            step = next(s for s in steps if s.get('phase') == phase)
        if not step or step['kind'] != kind:
            raise AssertionError(f'Expected {phase}:{kind}, got {steps}')
        receipt = json.loads(Path(step['policy']['path']).read_text())['policy_receipt']
        request = {**step['start'], 'policy_receipt': receipt}
        request.pop('request_id', None)
        perform = self.call(number, request)['next_steps'][0]
        actor = 'root-thread' if step['assignment'] == 'root' else f'{number}-{phase}-{kind}-{self.sequence}'
        lease = perform['lease']
        if lease['worker'] is None:
            self.call(number, {'operation': 'bind', 'phase': phase, 'lease': lease['token'],
                               'actor': actor, 'selection': lease['selection'], 'policy_receipt': receipt})
        perform['bound_actor'] = actor
        return perform

    def artifact(self, number, step, content):
        return self.call(number, {'operation': 'artifact', 'lease': step['lease']['token'],
                                 'actor': step['bound_actor'], 'content': content})['next_steps'][0]['artifact']

    def read(self, number, artifact):
        return self.call(number, {'operation': 'read', 'artifact': artifact})['next_steps'][0]['content']

    def verify(self, step, *, expected=0, envelope=None):
        request = {'operation': 'verify', 'phase': step['phase'], 'lease': step['lease']['token'],
                   'actor': step['bound_actor'], 'commands': [[sys.executable, '-B', self.test_path]],
                   'input_envelope': copy.deepcopy(envelope or step['input_envelope'])}
        return self.call(step.get('goal', 101), request, expected=expected)

    def result(self, number, step, content, verification=None, *, expected=0):
        output = self.artifact(number, step, content)
        record = copy.deepcopy(step['result_contract']['record'])
        record.update(actor=step['bound_actor'], output=output)
        if step['phase'] == 'test_design':
            record['test_design'] = {
                'baseline_failure': verification,
                'coverage': [{'criterion': c, 'test': output, 'exclusion': None}
                             for c in step['input_envelope']['acceptance_criteria']],
            }
        elif step['phase'] in {'implement', 'publish'}:
            record['verification'] = verification
        return self.call(number, {'operation': 'record_result', 'phase': step['phase'],
                                 'lease': step['lease']['token'], 'actor': step['bound_actor'],
                                 'files': list(self.consumed), 'record': record}, expected=expected)

    def review(self, number, phase, content=None, *, acceptance='approved'):
        step = self.start(number, phase, 'review')
        output = self.artifact(number, step, content or self.plan_review)
        self.call(number, {'operation': 'record_review', 'phase': phase, 'lease': step['lease']['token'],
                           'actor': step['bound_actor'], 'artifact': output,
                           'outcomes': {'acceptance': acceptance, 'entropy': {
                               'outcome': 'no_findings', 'evidence': 'Examined the exact current result and behavior.', 'goals': []}}})
        return output

    def phase(self, number, phase, content):
        step = self.start(number, phase)
        self.result(number, step, content)
        self.review(number, phase)
        steps = self.checkpoint(number)
        approvals = [s for s in steps if s.get('phase') == phase and s['kind'] == 'human_approval']
        if approvals:
            approval = self.start(number, phase, 'human_approval')
            self.call(number, {'operation': 'approve', 'phase': phase, 'lease': approval['lease']['token'],
                               'actor': approval['bound_actor'], 'approval': {
                                   'actor': approval['bound_actor'], 'approval_token': 'user: synthetic fixture approval'}})
        return step

    def prepare(self, parent_plan=None):
        self.phase(100, 'understand', {'requirements': 'Return two.'})
        self.phase(101, 'understand', {'requirements': 'Return two.'})
        self.phase(100, 'decompose', {'child': 101})
        self.phase(100, 'plan', parent_plan or self.plan)
        self.phase(101, 'plan', self.plan)
        child = self.goal(101)
        metadata = copy.deepcopy(child['implementation'])
        metadata.update(branch='goal-child', base='dev', target='dev')
        self.call(101, {'operation': 'revise', 'expected_digest': child['digest'],
                        'changes': {'implementation': metadata}})

    def design(self):
        step = self.start(101, 'test_design')
        (self.repo / self.test_path).write_text('from source import answer\nassert answer() == 2, "expected the required behavior"\n')
        verified = self.verify(step)
        proof_ref = verified['next_steps'][0]['verification']
        proof = self.read(101, proof_ref)
        if proof['passed']:
            raise AssertionError('The test must genuinely fail before source implementation')
        log = Path(proof['commands'][0]['log']).read_text()
        if 'expected the required behavior' not in log:
            raise AssertionError(f'Invalid behavioral baseline: {log}')
        self.result(101, step, {'files': {self.test_path: file_hash(self.repo / self.test_path)},
                               'behavior': 'Assert the required value.'}, proof_ref)
        self.review(101, 'test_design')
        self.git('add', self.test_path)
        self.git('commit', '-qm', 'test: require the new behavior')
        # A created output becomes a real consumed dependency of implementation.
        if self.test_path not in self.consumed:
            self.consumed.append(self.test_path)
        return step, proof_ref

    def implement(self):
        step = self.start(101, 'implement')
        (self.repo / 'source.py').write_text('def answer():\n    return 2\n')
        verified = self.verify(step)
        proof_ref = verified['next_steps'][0]['verification']
        self.result(101, step, {'files': {'source.py': file_hash(self.repo / 'source.py')},
                               'behavior': 'Return the required value.'}, proof_ref)
        self.review(101, 'implement')
        return step, proof_ref

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, text=True).strip()


class OwnedOutputPublicTests(unittest.TestCase):
    def test_publication_changes_requested_with_unfinished_ci_reaches_correction(self):
        # Exact publication safeguards now consume ordinary current generic evidence.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_workflow_publication_contract.GenericPublicationPublicTests.test_negative_ci_observation_is_recordable_and_review_can_admit_correction_without_approval',
        )

    def use_shipped_dag(self):
        template = json.loads((fixtures.fixtures.PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        dag = z._workflow_section({'policy': template['policy']}, 'workflow_adherence')['configuration']['phase_dag']
        z._workflow_section(self.session.project, 'workflow_adherence')['configuration']['phase_dag'] = dag
        self.assertEqual(['understand', 'decompose', 'test_design', 'implement', 'publish'], [n['id'] for n in dag['phases']])

    def test_five_phase_default_leaf_red_to_green_and_publication(self):
        # One connected generic delivery graph retains red/green, review and publication guards.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag.EvidenceGraphGrammarTests.test_shipped_default_is_one_valid_generic_graph',
            'test_workflow_publication_contract.GenericDeliveryPublicTests.test_reviewed_red_green_proofs_commit_and_exact_publication_form_one_delivery_graph',
        )

    def test_five_phase_parent_allocates_scope_in_decomposition(self):
        # Current parent grants and all-child completion use the same generic evidence graph.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_workflow_publication_contract.GenericDeliveryPublicTests.test_parent_requires_both_children_current_terminals_and_archived_merge_evidence',
        )

    def setUp(self):
        self.fixture = fixtures.FullWorkflowJourneyTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        control = tempfile.TemporaryDirectory()
        self.addCleanup(control.cleanup)
        self.repo = self.fixture.repo
        (self.repo / 'source.py').write_text('def answer():\n    return 1\n')
        (self.repo / 'behavior_test.py').write_text('from source import answer\nassert answer() == 1\n')
        (self.repo / 'read_dependency.txt').write_text('unchanged dependency\n')
        self.session = PublicSession(self.repo, self.fixture.project, self.fixture.runtime,
                                     self.fixture.provider, control.name,
                                     pull_request_states=self.fixture.pull_request_states)
        self.session.git('add', 'source.py', 'behavior_test.py', 'read_dependency.txt')
        self.session.git('commit', '-qm', 'fixture: existing source and test')
        self.session.git('checkout', '-q', '-B', 'goal-child')

    def test_pending_entropy_correction_routes_to_same_goal_without_false_approval(self):
        # Ordinary findings/admissions preserve exact correction and root acceptance guards.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_corrected_workspace_candidate_preserves_prior_proofs_and_requires_fresh_root_acceptance',
            'test_zzzops.PhaseEvidenceTests.test_pending_entropy_correction_requires_rejection_and_stays_in_goal',
        )

    def test_verification_accepts_gateway_rigor_projection_without_scope_drift(self):
        s = self.session
        original = s.portfolio_snapshot
        def projected(*args, **kwargs):
            snapshot = original(*args, **kwargs)
            for goal in snapshot['goals']:
                goal['engineering_rigor_inputs'] = copy.deepcopy(goal.get('engineering_rigor'))
                goal['engineering_rigor'] = {**(goal.get('engineering_rigor') or {}),
                    'effective': 'agentic', 'valid': True, 'errors': [],
                    'provenance': {'status': 'derived'}}
            return snapshot
        s.portfolio_snapshot = projected
        s.prepare()
        # This follows public start/bind/verify/result/review, rather than
        # treating a matching hash alone as proof of accepted verification.
        s.design()

    def test_mixed_checkout_raw_drift_and_dirty_acquisition(self):
        # Exact generic workspace guards; standalone legacy verification grants no authority.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_mixed_clean_checkout_rejects_raw_consumed_drift_and_restores_exact_acquisition',
        )

    def test_non_equivalent_dirty_checkout_rejects_acquisition(self):
        # Preserve this concrete guard through the single generic public engine.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_dirty_unreviewed_source_cannot_be_adopted_as_acquisition_baseline',
        )

    def test_crlf_correction_preserves_frozen_checkout_overrides(self):
        # Exact generic workspace guards; standalone legacy verification grants no authority.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_crlf_design_correction_retains_frozen_raw_checkout_overrides',
        )

    def test_crlf_clean_checkout_public_acquisition(self):
        # Preserve this concrete guard through the single generic public engine.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_clean_crlf_checkout_pins_raw_consumed_bytes_and_allows_owned_red_edit',
        )

    def test_orphan_verification_proof_does_not_invalidate_new_acquisition(self):
        # Exact generic workspace guards; standalone legacy verification grants no authority.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_unreferenced_proof_artifact_does_not_change_acquisition_inputs',
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_pending_workspace_submission_reuses_exact_observed_proof_and_log',
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_workspace_owner_requires_observed_stop_then_fresh_committed_acquisition',
            'test_evidence_dag_journeys.GenericStoragePublicTests.test_pending_start_retry_retains_generated_identity_and_completed_replay_never_resurrects',
        )

    def test_existing_consumed_test_and_source_red_to_green(self):
        # Preserve this concrete guard through the single generic public engine.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_permitted_red_to_green_edits_keep_fingerprints_and_downstream_proof_reuse',
        )

    def test_no_edit_control_and_wrong_actor_or_lease_reject(self):
        # Preserve this concrete guard through the single generic public engine.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.EvidenceDagPublicTests.test_wrong_actor_cannot_submit_and_valid_owner_still_can',
            'test_evidence_dag_journeys.EvidenceDagPublicTests.test_wrong_lease_cannot_submit_and_valid_lease_still_can',
        )

    def test_actual_changed_provenance_reuses_identical_plan_and_review_bytes(self):
        s = self.session
        s.prepare()
        parent = s.goal(100)['phase_evidence']
        before_record = copy.deepcopy(parent['records']['plan'])
        before_review = copy.deepcopy(parent['reviews']['plan'])
        child_identity = s.goal(101)['phase_evidence']['records']['plan']['output']
        (self.repo / 'read_dependency.txt').write_text('changed evidence; same requested behavior\n')
        # Reassessment is explicit, including the earlier parent evidence now stale.
        for number, phase, content in [(100, 'understand', {'requirements': 'Return two.'}),
                                        (101, 'understand', {'requirements': 'Return two.'}),
                                        (100, 'decompose', {'child': 101})]:
            s.phase(number, phase, content)
        step = s.start(100, 'plan')
        s.result(100, step, s.plan)
        middle = s.goal(100)['phase_evidence']
        self.assertNotEqual(before_record['input_hash'], middle['records']['plan']['input_hash'])
        self.assertNotEqual(content_hash(before_record), content_hash(middle['records']['plan']))
        self.assertEqual(before_record['output'], middle['records']['plan']['output'])
        self.assertNotIn('plan', middle['reviews'])
        self.assertNotIn('plan', middle['human_approvals'])
        s.review(100, 'plan', s.plan_review)
        after_review = s.goal(100)['phase_evidence']['reviews']['plan']
        self.assertEqual(before_review['artifact'], after_review['artifact'])
        self.assertNotEqual(before_review['record_hash'], after_review['record_hash'])
        self.assertNotEqual(before_review['input_hash'], after_review['input_hash'])
        s.phase(101, 'plan', s.plan)
        self.assertEqual(child_identity, s.goal(101)['phase_evidence']['records']['plan']['output'])

    def test_read_dependency_and_unexpected_output_reject_during_edit(self):
        # Preserve this concrete guard through the single generic public engine.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_unowned_and_consumed_drift_reject_without_partial_candidate_then_allow_owned_edit',
        )

    def test_undeclared_deletion_rejects_with_restored_valid_control(self):
        # Preserve this concrete guard through the single generic public engine.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_unsafe_allocation_paths_and_undeclared_deletion_never_authorize_edits',
        )

    def test_live_policy_change_invalidates_active_assignment(self):
        # Preserve this concrete guard through the single generic public engine.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.EvidenceDagPublicTests.test_generic_task_rejects_policy_drift_without_partial_semantic_publication',
        )

    def test_reviewed_test_edit_and_post_verify_source_edit_reject(self):
        s = self.session
        s.prepare()
        s.design()
        step = s.start(101, 'implement')
        original = (self.repo / s.test_path).read_bytes()
        (self.repo / 'source.py').write_text('def answer():\n    return 2\n')
        (self.repo / s.test_path).write_text('raise SystemExit(0)\n')
        self.assertRegex(s.verify(step, expected=2)['next_steps'][0]['reason'],
                         r'(?i)(review|test|scope|output|changed)')
        (self.repo / s.test_path).write_bytes(original)
        proof = s.verify(step)['next_steps'][0]['verification']
        (self.repo / 'source.py').write_text('def answer():\n    return 3\n')
        self.assertRegex(s.result(101, step, {'files': {'source.py': file_hash(self.repo / 'source.py')}},
                                  proof, expected=2)['next_steps'][0]['reason'],
                         r'(?i)(verification|workspace|proof|changed|stale)')

    def test_completed_proof_survives_lease_deletion_and_detects_later_output_drift(self):
        # Preserve this concrete guard through the single generic public engine.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_completed_output_and_consumed_drift_block_reuse_after_lease_removal',
        )

    def test_reacquiring_phase_keeps_stale_proof_drift_in_its_frozen_input(self):
        s = self.session
        s.prepare()
        s.design()
        goal = s.goal(101)
        goal.update(parent=None, depends_on=[], implementation={})
        graph, _ = z._workflow_phase_configuration(s.project, goal)
        engine = z.workflow_engine(s.repo, s.project, s.runtime)
        engine.adapter = s.provider
        engine.owned_versions = lambda *_args: {'source.py': {'sha256:' + '0' * 64}}
        engine.workspace_digest = lambda: 'sha256:' + 'a' * 64

        acquired = engine.inputs(goal, graph)['test_design']
        self.assertIn('output_drift', acquired['repository']['snapshot'])
        goal['workflow']['leases']['test_design:execute'] = {
            'acquisition': {'input_envelope': copy.deepcopy(acquired)},
        }
        current = engine.inputs(goal, graph)['test_design']

        self.assertEqual(content_hash(acquired), content_hash(current))

        goal['phase_evidence']['records']['test_design']['input_envelope'] = copy.deepcopy(acquired)
        goal['phase_evidence']['records']['test_design']['input_hash'] = content_hash(acquired)
        goal['phase_evidence']['reviews'].pop('test_design', None)
        goal['workflow']['artifacts']['test_design'] = {'workspace': engine.workspace_digest()}
        del goal['workflow']['leases']['test_design:execute']
        completed = engine.inputs(goal, graph)['test_design']

        self.assertEqual(content_hash(acquired), content_hash(completed))

    def test_durable_proof_rejects_tampered_acquisition_and_outputs(self):
        s = self.session
        s.prepare()
        s.design()
        step = s.start(101, 'implement')
        (self.repo / 'source.py').write_text('def answer():\n    return 2\n')
        reference = s.verify(step)['next_steps'][0]['verification']
        proof = s.read(101, reference)
        mutations = [
            lambda value: value.update(acquisition=None),
            lambda value: value['acquisition'].update(checkout_overrides=None),
            lambda value: value['acquisition'].update(checkout_overrides={'../escape': 'sha256:' + '0' * 64}),
            lambda value: value['acquisition'].update(checkout_overrides={'source.py': 'sha256:' + '0' * 64}),
            lambda value: value.update(acquisition={'git_commit': '0' * 40}),
            lambda value: value['acquisition'].update(git_commit='0' * 40),
            lambda value: value['acquisition'].update(workspace_digest='sha256:' + '0' * 64),
            lambda value: value['acquisition'].update(input_hash='sha256:' + '0' * 64),
            lambda value: value['outputs'].update({'source.py': 'sha256:' + '0' * 64}),
            lambda value: value.update(actor='unbound-worker'),
            lambda value: value.update(lease='different-lease'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                changed = copy.deepcopy(proof)
                mutate(changed)
                forged_reference = s.artifact(101, step, changed)
                response = s.result(101, step, {'files': {'source.py': file_hash(self.repo / 'source.py')}},
                                    forged_reference, expected=2)
                self.assertRegex(response['next_steps'][0]['reason'],
                                 r'(?i)(proof|verification|acquisition|input|lease|actor)')
        # A valid matched submission succeeds after each forged-proof rejection.
        s.result(101, step, {'files': {'source.py': file_hash(self.repo / 'source.py')}}, reference)
        self.assertNotIn('implement:execute', s.goal(101)['workflow']['leases'])

    def test_spec_change_and_unapproved_plan_cannot_authorize_source_edits(self):
        s = self.session
        s.prepare()
        before = s.checkpoint(101)
        self.assertTrue(any(x.get('phase') == 'test_design' and x['kind'] in {'assess', 'execute'}
                            for x in before), before)
        record = s.goal(100)['phase_evidence']['records']['plan']
        s.call(100, {'operation': 'withdraw', 'phase': 'plan', 'record_hash': content_hash(record),
                     'reason': 'Independent review must be current.'})
        steps = s.checkpoint(101)
        self.assertFalse(any(x.get('phase') == 'test_design' and x['kind'] in {'assess', 'execute'}
                             for x in steps), steps)
        blocked = [item for step in steps for item in step.get('blocked', [])]
        self.assertTrue(any(item['phase'] == 'test_design' and 'plan' in item['parent_gates']
                            for item in blocked), blocked)
        # A real public specification revision makes the source approval stale.
        parent = s.goal(100)
        s.call(100, {'operation': 'specify', 'expected_digest': parent['digest'],
                     'human_spec': '## Acceptance criteria\n- Return three instead of two.\n'})
        changed = s.checkpoint(100)
        self.assertTrue(any(x.get('phase') == 'understand' and x['kind'] in {'assess', 'execute'}
                            for x in changed), changed)

    def test_unauthorized_approval_is_rejected_before_valid_matched_control(self):
        s = self.session
        step = s.start(100, 'understand')
        s.result(100, step, {'requirements': 'Return two.'})
        s.review(100, 'understand')
        approval = s.start(100, 'understand', 'human_approval')
        request = {'operation': 'approve', 'phase': 'understand', 'lease': approval['lease']['token'],
                   'actor': 'root-thread', 'approval': {'actor': 'root-thread', 'approval_token': '<user>'}}
        response = s.call(100, request, expected=2)
        self.assertRegex(response['next_steps'][0]['reason'], r'(?i)(approval|placeholder|explicit)')
        request['approval']['approval_token'] = 'user: explicit fixture approval'
        s.call(100, request)
        self.assertIn('understand', s.goal(100)['phase_evidence']['human_approvals'])

    def test_duplicate_writer_and_uncertain_recovery_are_rejected(self):
        # Exact generic workspace guards; standalone legacy verification grants no authority.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_workspace_owner_requires_observed_stop_then_fresh_committed_acquisition',
        )

    def test_missing_output_scope_cannot_exempt_an_existing_input(self):
        s = self.session
        s.plan.pop('output_scope')
        s.prepare()
        self.assert_scope_gate(s)

    def assert_scope_gate(self, s):
        steps = s.checkpoint(101)
        writable = [x for x in steps if x.get('phase') in {'test_design', 'implement'}
                    and x['kind'] in {'execute', 'perform'}]
        self.assertFalse(writable, steps)
        self.assertRegex(json.dumps(steps), r'(?i)scope')
        self.assertRegex(json.dumps(steps), r'(?i)plan')
        repair = next(x for x in steps if 'scope' in json.dumps(x).lower())
        details = repair['scope_repair']
        self.assertEqual({'goal': 101, 'parent': 100, 'phase': 'test_design'},
                         {k: details[k] for k in ['goal', 'parent', 'phase']})
        self.assertIn(details['field'], {'output_scope', 'output_scopes'})
        self.assertEqual('plan', details['required_phase'])
        # This checks the public actionable gate. Direct verification rejection is covered
        # with an acquired valid contract when the reviewed plan is withdrawn.

    def test_valid_acquired_contract_cannot_verify_after_scope_plan_withdrawal(self):
        s = self.session
        s.prepare()
        step = s.start(101, 'test_design')
        # Valid unchanged-workspace control with the exact bound actor/token/hash.
        reference = s.verify(step)['next_steps'][0]['verification']
        self.assertTrue(s.read(101, reference)['passed'])
        record = s.goal(100)['phase_evidence']['records']['plan']
        s.call(100, {'operation': 'withdraw', 'phase': 'plan', 'record_hash': content_hash(record),
                     'reason': 'Withdraw scope authority before any test edit.'})
        rejected = s.verify(step, expected=2)
        self.assertRegex(json.dumps(rejected), r'(?i)(plan|review|ancestor|scope|eligible|input)')

    def test_mismatched_selected_parent_scope_requires_plan_repair(self):
        # Preserve this concrete guard through the single generic public engine.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_parent_grant_omission_and_mismatch_cannot_expand_child_authority',
        )

    def test_explicit_empty_scope_rejects_new_file_but_allows_unchanged_proof(self):
        # Preserve this concrete guard through the single generic public engine.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_readonly_allocation_accepts_unchanged_workspace_but_rejects_new_file',
        )

    def test_sibling_scopes_connect_completed_first_child_without_rewriting_history(self):
        # Independently reviewed sibling allocations consume exact connected first-child proof.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_workflow_publication_contract.GenericDeliveryPublicTests.test_second_sibling_consumes_reviewed_committed_first_proof_without_rewriting_history',
        )

    def test_declared_deletion_has_same_proof_identity_after_commit(self):
        # Preserve the exact workspace guard through the generic public engine.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_permitted_red_to_green_edits_keep_fingerprints_and_downstream_proof_reuse')

    def test_recorded_output_exposes_own_review_and_correction_without_consumer_authority(self):
        s = self.session
        s.prepare()
        s.design()
        step = s.start(101, 'implement')
        (s.repo / 'source.py').write_text('def answer():\n    return 2\n')
        reference = s.verify(step)['next_steps'][0]['verification']
        s.result(101, step, {'files': {'source.py': file_hash(s.repo / 'source.py')}}, reference)
        self.assertNotIn('implement:execute', s.goal(101)['workflow']['leases'])
        ancestors = copy.deepcopy(s.goal(100)['phase_evidence'])
        steps = s.checkpoint(101)
        self.assertTrue(any(x.get('phase') == 'implement' and x['kind'] == 'review' for x in steps), steps)
        self.assertFalse(any(x.get('phase') == 'publish' and x['kind'] == 'execute' for x in steps), steps)
        s.review(101, 'implement', {'finding': 'Add explanation before acceptance.'}, acceptance='changes_requested')
        rejected_record = copy.deepcopy(s.goal(101)['phase_evidence']['records']['implement'])
        rejected_review = copy.deepcopy(s.goal(101)['phase_evidence']['reviews']['implement'])
        self.assertFalse(any(x.get('phase') == 'publish' and x['kind'] == 'execute' for x in s.checkpoint(101)))
        s.git('add', 'source.py')
        s.git('commit', '-qm', 'checkpoint: exact rejected output for correction')
        original_dependency = (s.repo / 'read_dependency.txt').read_bytes()
        (s.repo / 'read_dependency.txt').write_text('not the exact correction baseline\n')
        invalid = s.checkpoint(101)
        self.assertFalse(any(x.get('phase') == 'implement' and x['kind'] == 'execute' for x in invalid), invalid)
        (s.repo / 'read_dependency.txt').write_bytes(original_dependency)
        # Corrupt only the external provider read: no private workflow mutation.
        real_get = s.provider.get_issue
        def missing_recorded_proof(number):
            issue = real_get(number)
            if number == 101:
                raw = z.parse_managed_goal(issue['body'], number)
                raw['phase_evidence']['records']['implement']['verification'] = None
                issue['body'] = z.render_managed_goal(raw, s.goal_spec_for_fault, number)
            return issue
        s.goal_spec_for_fault = s.goal(101)['human_spec']
        with mock.patch.object(s.provider, 'get_issue', side_effect=missing_recorded_proof):
            missing = s.call(101, expected=None)
            self.assertFalse(any(x.get('phase') == 'implement' and x['kind'] == 'execute'
                                 for x in missing['next_steps']), missing)
            self.assertRegex(json.dumps(missing), r'(?i)(proof|verification|invalid|missing|evidence)')
        correction = s.start(101, 'implement')
        self.assertEqual(rejected_review['reviewer'], correction['correction']['prior_reviewer'])
        self.assertEqual(rejected_review['outcomes'], correction['correction']['prior_findings'])
        self.assertEqual(rejected_review['record_hash'], correction['correction']['prior_record_hash'])
        self.assertIn('Reuse the current assessment', correction['correction']['routing'])
        self.assertNotEqual(step['lease']['token'], correction['lease']['token'])
        self.assertNotEqual(step['input_hash'], correction['input_hash'])
        self.assertEqual(rejected_record, s.goal(101)['phase_evidence']['records']['implement'])
        predecessor_ref = correction['lease']['acquisition']['predecessor']
        predecessor = s.read(101, predecessor_ref)
        self.assertEqual({'goal', 'phase', 'record', 'review', 'scope'}, set(predecessor))
        self.assertEqual(101, predecessor['goal'])
        self.assertEqual('implement', predecessor['phase'])
        self.assertEqual(rejected_record, predecessor['record'])
        self.assertEqual(rejected_review, predecessor['review'])
        self.assertEqual('changes_requested', predecessor['review']['decision'])
        self.assertEqual(s.plan['output_scope'], predecessor['scope'])
        self.assertEqual(file_hash(s.repo / 'source.py'),
                         correction['input_envelope']['repository']['snapshot']['files']['source.py'])
        self.predecessor_fault_controls(s, correction, predecessor_ref, predecessor)
        (s.repo / 'source.py').write_text('def answer():\n    # Required observable value.\n    return 2\n')
        corrected_proof = s.verify(correction)['next_steps'][0]['verification']
        s.result(101, correction, {'files': {'source.py': file_hash(s.repo / 'source.py')}}, corrected_proof)
        self.assertNotIn('implement:execute', s.goal(101)['workflow']['leases'])
        corrected = s.read(101, corrected_proof)
        self.assertEqual(predecessor_ref, corrected['acquisition']['predecessor'])
        self.assertEqual(rejected_record, s.read(101, corrected['acquisition']['predecessor'])['record'])
        self.assertFalse(any(x.get('phase') == 'publish' and x['kind'] in {'assess', 'execute'}
                             for x in s.checkpoint(101)))
        # A second actual public correction traverses history after both overwrites.
        s.review(101, 'implement', {'finding': 'Clarify the explanation further.'}, acceptance='changes_requested')
        second_rejected = copy.deepcopy(s.goal(101)['phase_evidence']['records']['implement'])
        s.git('add', 'source.py')
        s.git('commit', '-qm', 'checkpoint: second exact rejected output')
        second = s.start(101, 'implement')
        second_predecessor = s.read(101, second['lease']['acquisition']['predecessor'])
        self.assertEqual(second_rejected, second_predecessor['record'])
        nested_proof = s.read(101, second_predecessor['record']['verification'])
        self.assertEqual(predecessor_ref, nested_proof['acquisition']['predecessor'])
        (s.repo / 'source.py').write_text('def answer():\n    # Return exactly the requested value.\n    return 2\n')
        second_proof = s.verify(second)['next_steps'][0]['verification']
        s.result(101, second, {'files': {'source.py': file_hash(s.repo / 'source.py')}}, second_proof)
        self.assertFalse(any(x.get('phase') == 'publish' and x['kind'] in {'assess', 'execute'}
                             for x in s.checkpoint(101)))
        s.review(101, 'implement')
        self.assertEqual('changes_requested', s.read(101, predecessor_ref)['review']['decision'])
        self.assertEqual(ancestors, s.goal(100)['phase_evidence'])
        self.assertTrue(any(x.get('phase') == 'publish' for x in s.checkpoint(101)))
        record = s.goal(101)['phase_evidence']['records']['implement']
        s.call(101, {'operation': 'withdraw', 'phase': 'implement', 'record_hash': content_hash(record),
                     'reason': 'Withdraw reviewed result; consumers must block.'})
        self.assertFalse(any(x.get('phase') == 'publish' and x['kind'] in {'assess', 'execute'}
                             for x in s.checkpoint(101)))

    def test_explicit_withdrawal_restarts_from_clean_prior_checkout_without_stale_proof(self):
        s = self.session
        s.prepare()
        design, _ = s.design()
        before_commit = design['lease']['acquisition']['git_commit']
        step = s.start(101, 'implement')
        (s.repo / 'source.py').write_text('def answer():\n    return 2\n')
        proof = s.verify(step)['next_steps'][0]['verification']
        s.result(101, step, {'files': {'source.py': file_hash(s.repo / 'source.py')}}, proof)
        s.review(101, 'implement', {'finding': 'Permanent regression required.'}, acceptance='changes_requested')
        rejected = copy.deepcopy(s.goal(101)['phase_evidence']['records']['implement'])
        previous_design = copy.deepcopy(s.goal(101)['phase_evidence']['records']['test_design'])
        # Stage a separate clean owned checkout. Existing reviewed checkout bytes
        # and rejected source output are preserved; no test edit occurs before lease.
        previous_checkout = s.repo
        previous_bytes = {p: (previous_checkout / p).read_bytes() for p in s.consumed}
        checkout = tempfile.TemporaryDirectory()
        self.addCleanup(checkout.cleanup)
        s.git('worktree', 'add', '--detach', checkout.name, before_commit)
        s.repo = Path(checkout.name)
        s.git('checkout', '-q', '-b', 'goal-restart')
        goal = s.goal(101)
        metadata = copy.deepcopy(goal['implementation'])
        metadata['branch'] = 'goal-restart'
        s.call(101, {'operation': 'revise', 'expected_digest': goal['digest'], 'changes': {'implementation': metadata}})
        for phase, record in [('implement', rejected), ('test_design', previous_design)]:
            s.call(101, {'operation': 'withdraw', 'phase': phase, 'record_hash': content_hash(record),
                         'reason': 'Explicitly restart from authenticated clean prior test baseline.'})
        withdrawn = copy.deepcopy(s.goal(101)['phase_evidence'])
        self.assertEqual(rejected, withdrawn['records']['implement'])
        self.assertEqual(previous_design, withdrawn['records']['test_design'])
        self.assertTrue({'implement', 'test_design'} <= {x['phase'] for x in withdrawn['withdrawals']})
        self.assertFalse(any(x.get('phase') == 'publish' and x['kind'] in {'assess', 'execute'}
                             for x in s.checkpoint(101)))
        reopened = s.start(101, 'test_design')
        self.assertNotIn('output_drift', reopened['input_envelope']['repository']['snapshot'])
        self.assertNotIn('predecessor', reopened['lease']['acquisition'])
        self.assertEqual(set(s.consumed), set(reopened['input_envelope']['repository']['snapshot']['files']))
        (s.repo / s.test_path).write_text('from source import answer\n# Permanent amended regression.\nassert answer() == 2\n')
        failed = s.verify(reopened)['next_steps'][0]['verification']
        self.assertFalse(s.read(101, failed)['passed'])
        s.result(101, reopened, {'files': {s.test_path: file_hash(s.repo / s.test_path)}}, failed)
        s.review(101, 'test_design')
        actual = s.goal(101)['phase_evidence']['records']['test_design']
        self.assertEqual(reopened['input_envelope'], actual['input_envelope'])
        self.assertEqual(reopened['input_hash'], actual['input_hash'])
        s.git('add', s.test_path)
        s.git('commit', '-qm', 'test: reviewed amended regression')
        fresh = s.start(101, 'implement')
        self.assertNotIn('predecessor', fresh['lease']['acquisition'])
        self.assertNotEqual(step['lease']['token'], fresh['lease']['token'])
        (s.repo / 'source.py').write_text('def answer():\n    # Corrected required behavior.\n    return 2\n')
        passed = s.verify(fresh)['next_steps'][0]['verification']
        self.assertTrue(s.read(101, passed)['passed'])
        s.result(101, fresh, {'files': {'source.py': file_hash(s.repo / 'source.py')}}, passed)
        s.review(101, 'implement')
        actual = s.goal(101)['phase_evidence']['records']['implement']
        self.assertEqual(fresh['input_envelope'], actual['input_envelope'])
        self.assertEqual(fresh['input_hash'], actual['input_hash'])
        self.assertEqual(previous_bytes, {p: (previous_checkout / p).read_bytes() for p in s.consumed})

    def require_implementation_human_approval(self):
        configuration = z._workflow_section(self.session.project, 'workflow_adherence')['configuration']
        implementation = next(node for node in configuration['phase_dag']['phases'] if node['id'] == 'implement')
        implementation['review']['human_approval'] = True

    def test_required_human_approval_blocks_sibling_consumption_until_current_approval(self):
        # Independently reviewed sibling allocations consume exact connected first-child proof.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_workflow_publication_contract.GenericDeliveryPublicTests.test_second_sibling_consumes_reviewed_committed_first_proof_without_rewriting_history',
        )

    def test_composed_correction_requires_current_human_approval_after_record_replacement(self):
        # Ordinary findings/admissions preserve exact correction and root acceptance guards.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_corrected_workspace_candidate_preserves_prior_proofs_and_requires_fresh_root_acceptance',
            'test_phase_review_contract.GenericReviewGateTests.test_identical_output_cannot_bypass_current_ancestor_review_and_reapproval',
        )

    def test_test_design_correction_retains_baseline_failure_predecessor(self):
        # Exact generic workspace guards; standalone legacy verification grants no authority.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_design_correction_retains_exact_observed_red_predecessor',
        )

    def predecessor_fault_controls(self, s, correction, reference, predecessor):
        """Corrupt provider reads, never workflow decisions or positive state."""
        real_get = s.provider.get_issue
        human_spec = s.goal(101)['human_spec']
        mutations = []
        for field, value in [('goal', 102), ('phase', 'test_design')]:
            changed = copy.deepcopy(predecessor)
            changed[field] = value
            mutations.append((field, s.artifact(101, correction, changed)))
        changed = copy.deepcopy(predecessor)
        changed['scope']['implement'] = ['read_dependency.txt']
        mutations.append(('scope', s.artifact(101, correction, changed)))
        # Fully content-addressed but disconnected prior proof/record/review.
        changed = copy.deepcopy(predecessor)
        proof = s.read(101, changed['record']['verification'])
        proof['workspace'] = 'sha256:' + '0' * 64
        changed['record']['verification'] = s.artifact(101, correction, proof)
        changed['review']['record_hash'] = content_hash(changed['record'])
        mutations.append(('disconnected', s.artifact(101, correction, changed)))
        # Provider-fault history is content-addressed and acyclic. It repeats a
        # no-op snapshot to exceed the reviewed 32-hop bound; no invented SHA cycle.
        deep_reference = reference
        for _ in range(33):
            item = copy.deepcopy(predecessor)
            prior_proof = s.read(101, predecessor['record']['verification'])
            prior_proof['acquisition'] = {
                'git_commit': correction['lease']['acquisition']['git_commit'],
                'workspace_digest': correction['lease']['acquisition']['workspace_digest'],
                'input_hash': correction['input_hash'], 'predecessor': deep_reference,
            }
            if 'checkout_overrides' in correction['lease']['acquisition']:
                prior_proof['acquisition']['checkout_overrides'] = copy.deepcopy(
                    correction['lease']['acquisition']['checkout_overrides'])
            prior_proof['workspace'] = correction['lease']['acquisition']['workspace_digest']
            prior_proof['outputs'] = {'source.py': file_hash(s.repo / 'source.py')}
            item['record']['input_envelope'] = copy.deepcopy(correction['input_envelope'])
            item['record']['input_hash'] = correction['input_hash']
            item['record']['verification'] = s.artifact(101, correction, prior_proof)
            item['review']['input_hash'] = correction['input_hash']
            item['review']['record_hash'] = content_hash(item['record'])
            deep_reference = s.artifact(101, correction, item)
        mutations.append(('depth', deep_reference))
        mutations += [('null', None), ('partial', {'hash': reference['hash']}),
                      ('missing', {'hash': 'sha256:' + '0' * 64, 'reference': 'urn:sha256:' + '0' * 64})]
        for label, replacement in mutations:
            with self.subTest(predecessor=label):
                def damaged_issue(number):
                    issue = real_get(number)
                    if number == 101:
                        raw = z.parse_managed_goal(issue['body'], number)
                        raw['workflow']['leases']['implement:execute']['acquisition']['predecessor'] = replacement
                        issue['body'] = z.render_managed_goal(raw, human_spec, number)
                    return issue
                with mock.patch.object(s.provider, 'get_issue', side_effect=damaged_issue):
                    rejected = s.verify(correction, expected=2)
                    self.assertRegex(json.dumps(rejected), r'(?i)(predecessor|acquisition|snapshot|artifact|scope|record|proof|phase|depth)')
                    if label == 'depth':
                        self.assertRegex(json.dumps(rejected), r'(?i)(depth|limit|chain)')
        # Broken stored contents under an unchanged claimed hash reject; this is
        # NOT a claim that a valid cryptographic self-referential artifact exists.
        real_comments = s.provider.get_issue_comments
        damaged_records = 0
        def damaged_comments(number):
            nonlocal damaged_records
            comments = real_comments(number)
            for comment in comments:
                if comment['body'].startswith('<!-- zzzops-artifact ' + reference['hash'] + ' -->'):
                    comment['body'] = '<!-- zzzops-artifact ' + reference['hash'] + ' -->\ninvalid cyclic/tampered bytes'
                    damaged_records += 1
                elif comment['body'].startswith('<!-- zzzops-envelope\n'):
                    path = Path(z.__file__).parent / 'comment_store.py'
                    spec = importlib.util.spec_from_file_location('predecessor_envelope_test', path)
                    codec = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(codec)
                    envelope = codec.decode_envelope(comment['body'])
                    for record in envelope['artifacts']:
                        if record['hash'] == reference['hash']:
                            # Keep the claimed artifact identity but give it
                            # different content under a valid transport checksum.
                            record.clear()
                            record.update(hash=reference['hash'], kind='full', type='json', text='null')
                            comment['body'] = codec.encode_envelope(envelope)
                            damaged_records += 1
            return comments
        with mock.patch.object(s.provider, 'get_issue_comments', side_effect=damaged_comments):
            rejected = s.verify(correction, expected=2)
            self.assertGreater(damaged_records, 0, 'The referenced predecessor must actually be corrupted')
            self.assertRegex(json.dumps(rejected), r'(?i)(artifact|predecessor|malformed|hash)')
        restored = s.verify(correction)['next_steps'][0]['verification']
        self.assertTrue(s.read(101, restored)['passed'])

    @unittest.skipUnless(hasattr(os, 'symlink'), 'Platform cannot create symlinks')
    def test_owned_output_symlink_cannot_escape_the_worktree(self):
        # Preserve the exact workspace guard through the generic public engine.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_acquired_owned_path_cannot_be_replaced_by_escaping_symlink')

    def test_read_only_checkpoint_preserves_closed_goal_and_has_no_cursor(self):
        s = self.session
        closed = copy.deepcopy(s.provider.issues[100])
        closed['number'] = 102
        closed['state'] = 'closed'
        # Provider-side fixture construction only; no simulated workflow completion.
        raw = z.parse_managed_goal(closed['body'], 102)
        raw['status'] = 'done'
        closed['body'] = z.render_managed_goal(raw, '## Acceptance\n- Historical completion.\n', 102)
        s.provider.issues[102] = closed
        s.provider.comments[102] = []
        original = copy.deepcopy(closed)
        s.prepare()
        self.assertEqual(original, s.provider.issues[102])
        self.assertEqual({'leases', 'receipts', 'workers', 'assessments', 'artifacts', 'routing_choices'},
                         set(s.goal(101)['workflow']))

    def legacy_handoff(self):
        archive = os.environ.get('ZZZOPS_OLD_CLI_ARCHIVE')
        if not archive:
            self.skipTest('Set ZZZOPS_OLD_CLI_ARCHIVE to the external pristine archive for actual-version proof')
        s = self.session
        config = s.control / 'legacy-request.json'
        result = s.control / 'legacy-result.json'
        config.write_text(json.dumps({'archive': archive, 'repo': str(s.repo), 'control': str(s.control),
                                      'project': s.project, 'runtime': s.runtime,
                                      'issues': list(s.provider.issues.values()), 'result': str(result)}))
        run = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--legacy-prepare', str(config)],
                             capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        self.assertEqual(0, run.returncode, run.stdout + run.stderr)
        data = json.loads(result.read_text())
        s.provider.issues = {int(k): v for k, v in data['issues'].items()}
        s.provider.comments = {int(k): v for k, v in data['comments'].items()}
        s.test_path = 'new_behavior_test.py'
        s.consumed = data['consumed']
        s.plan['output_scope']['test_design'] = [s.test_path]
        self.assertNotIn('acquisition', data['start']['lease'], 'The old code must really acquire the lease')
        self.assertTrue(data['old_code_hash'])
        self.assertEqual('implement', data['start']['phase'])
        self.assertIn('test_design', s.goal(101)['phase_evidence']['reviews'])
        return data['start']

    def test_actual_old_dispatch_start_to_repaired_dispatch_same_lease(self):
        # Predecessor input never authorizes active v1 same-lease dispatch.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_goal_schema_conversion.MigrationEntryPublicTests.test_predecessor_owner_must_be_observed_stopped_before_fresh_generic_entry_lease',
            'test_goal_schema_conversion.MigrationEntryPublicTests.test_v1_cutover_rejects_phase_operations_and_uses_only_generic_submission',
        )

    def test_actual_old_dispatch_rejects_wrong_envelope_and_unrelated_output(self):
        # Predecessor input never authorizes active v1 same-lease dispatch.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_caller_cannot_replace_authenticated_acquisition_with_supplied_envelope',
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_unowned_and_consumed_drift_reject_without_partial_candidate_then_allow_owned_edit',
        )

    def test_actual_old_dispatch_requires_current_reviewed_baseline(self):
        # Ordinary findings/admissions preserve exact correction and root acceptance guards.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_admitted_baseline_correction_rejects_already_acquired_consumer_without_takeover',
        )

    def test_legacy_candidate_git_tree_must_match_reviewed_baseline(self):
        # Predecessor input never authorizes active v1 same-lease dispatch.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_unrelated_committed_candidate_cannot_replace_acquired_git_baseline',
        )



def legacy_prepare(config_path):
    """Run unmodified old main in its own process, sharing only provider data."""
    data = json.loads(Path(config_path).read_text())
    with tempfile.TemporaryDirectory() as extracted:
        with tarfile.open(data['archive']) as archive:
            archive.extractall(extracted, filter='data')
        source = Path(extracted) / 'plugins/zzzops/zzzops/zzzops.py'
        spec = importlib.util.spec_from_file_location('pristine_zzzops', source)
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        provider = fixtures.MemoryGoalProvider(data['issues'])
        s = PublicSession(data['repo'], data['project'], data['runtime'], provider, data['control'], api)
        s.test_path = 'new_behavior_test.py'
        s.plan['output_scope']['test_design'] = [s.test_path]
        s.prepare()
        s.design()
        acquired = s.start(101, 'implement')
        Path(data['result']).write_text(json.dumps({'issues': provider.issues, 'comments': provider.comments,
                                                    'start': acquired, 'consumed': s.consumed,
                                                    'old_code_hash': file_hash(source)}))


class CommentCheckpointPublicTests(unittest.TestCase):
    """#539 uses the existing public dispatcher and provider fixtures.

    The implemented request shapes use artifacts=[{content, hash}]
    on result/review; artifact={phase, slot, revision?} on read. Inline values
    carry data only; the ordinary record and lease still confer all authority.
    """

    setUp = OwnedOutputPublicTests.setUp

    def reference(self, content):
        identity = content_hash(content)
        return {'reference': 'urn:' + identity, 'hash': identity}

    def legacy_body(self, content, *, raw=None, compressed=None):
        identity = content_hash(content)
        raw = raw if raw is not None else json.dumps({'hash': identity, 'content': content}, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        encoded = base64.b64encode(compressed if compressed is not None else zlib.compress(raw, level=0)).decode()
        return '<!-- zzzops-artifact ' + identity + ' -->\n<details><summary>Immutable phase artifact</summary>\n\n```text\n' + encoded + '\n```\n</details>'

    def test_legacy_alternate_compression_reuses_complete_content_identity(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_evidence_dag_journeys.GenericStoragePublicTests.test_alternate_legacy_compression_preserves_typed_output_identity_and_retry')

    def test_public_artifact_reads_reject_duplicate_keys_trailing_and_expansion(self):
        s = self.session
        content = {'text': 'value'}
        identity = content_hash(content)
        valid = json.dumps({'hash': identity, 'content': content}, separators=(',', ':')).encode()
        cases = {
            'duplicate_keys': ('{"hash":' + json.dumps(identity) + ',"content":null,"content":{"text":"value"}}').encode(),
            'trailing_json': valid + b' {}',
            'expansion': b' ' * 1_000_001 + valid,
        }
        for name, raw in cases.items():
            with self.subTest(name=name):
                s.provider.comments[101] = []
                s.provider.create_issue_comment(101, self.legacy_body(content, raw=raw))
                response = s.call(101, {'operation': 'read', 'artifact': self.reference(content)}, expected=None)
                self.assertNotEqual(0, s.calls[-1]['code'], 'Must reject ' + name)
                self.assertTrue(response['next_steps'])
        s.provider.comments[101] = []
        s.provider.create_issue_comment(101, self.legacy_body(content, compressed=zlib.compress(valid) + b'trailing'))
        s.call(101, {'operation': 'read', 'artifact': self.reference(content)}, expected=None)
        self.assertNotEqual(0, s.calls[-1]['code'])

    def test_conflicting_stored_identity_is_not_hidden_by_first_match(self):
        s = self.session
        content = {'text': 'verified'}
        reference = self.reference(content)
        s.provider.create_issue_comment(101, self.legacy_body(content))
        raw = json.dumps({'hash': reference['hash'], 'content': 'tampered'}).encode()
        s.provider.create_issue_comment(101, self.legacy_body(content, raw=raw))
        s.call(101, {'operation': 'read', 'artifact': reference}, expected=None)
        self.assertNotEqual(0, s.calls[-1]['code'], 'All definitions of an immutable identity must be checked')

    def test_latest_advances_and_unchanged_revisions_remain_pinnable(self):
        # Exact storage/ownership guard through public generic host output transactions.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.GenericStoragePublicTests.test_logical_latest_and_exact_historical_revisions_preserve_host_refs',
        )

    def test_sparse_changed_artifact_is_smaller_and_missing_base_fails_closed(self):
        # Same storage guard, now using host-issued generic output artifact identities.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_evidence_dag_journeys.GenericStoragePublicTests.test_sparse_output_delta_is_smaller_and_missing_base_fails_closed')

    def test_new_envelope_cycles_duplicate_records_and_patch_tampering_fail_closed(self):
        # Same storage guard, now using host-issued generic output artifact identities.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_evidence_dag_journeys.GenericStoragePublicTests.test_output_delta_cycle_missing_base_duplicate_patch_and_version_reject')

    def test_reconstruction_work_limit_is_enforced_even_for_compressible_content(self):
        # Same storage guard, now using host-issued generic output artifact identities.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_evidence_dag_journeys.GenericStoragePublicTests.test_decoded_reconstruction_work_bound_applies_to_compressible_output')

    def test_unfavorable_delta_uses_independent_full_checkpoint(self):
        # Same storage guard, now using host-issued generic output artifact identities.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_evidence_dag_journeys.GenericStoragePublicTests.test_unfavorable_output_delta_is_independent_full_record')

    def test_checkpoint_rollover_breaks_dependency_before_ninth_delta_edge(self):
        # Same storage guard, now using host-issued generic output artifact identities.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_evidence_dag_journeys.GenericStoragePublicTests.test_output_chain_rollover_preserves_latest_without_initial_base')

    def test_cached_immutable_read_does_not_pin_logical_head(self):
        # Exact storage/ownership guard through public generic host output transactions.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.GenericStoragePublicTests.test_immutable_cache_does_not_freeze_logical_latest_output',
        )

    def test_partial_multipart_envelope_retry_preserves_one_logical_operation(self):
        # Exact storage/ownership guard through public generic host output transactions.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.GenericStoragePublicTests.test_multipart_retry_reuses_partial_bytes_and_publishes_one_atomic_output_bundle',
        )

    def test_partial_upload_cannot_bypass_live_actor_or_stale_input_checks(self):
        # Exact storage/ownership guard through public generic host output transactions.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.GenericStoragePublicTests.test_partial_upload_still_requires_actual_actor_and_current_input',
        )

    def test_start_and_bind_remain_separate_durable_checkpoints(self):
        # Exact storage/ownership guard through public generic host output transactions.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.GenericStoragePublicTests.test_start_and_bind_persist_distinct_unbound_then_actual_worker_checkpoints',
        )

    def test_historical_semantic_projection_never_restores_live_coordination(self):
        # Historical predecessor transport is decoded before trusted conversion;
        # exact immutable refs never restore current leases or receipts.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_goal_schema_conversion.MigrationEntryPublicTests.test_mixed_history_exact_refs_preserve_predecessor_snapshots_and_live_coordination',
            'test_goal_schema_conversion.MigrationEntryPublicTests.test_approval_bearing_historical_snapshots_remain_data_after_conversion',
        )

    def test_pending_start_retry_preserves_generated_lease_and_completed_retry_does_not_resurrect(self):
        # Exact storage/ownership guard through public generic host output transactions.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.GenericStoragePublicTests.test_pending_start_retry_retains_generated_identity_and_completed_replay_never_resurrects',
        )

    def inline_result(self, step, contents, request_id='inline-result'):
        record = copy.deepcopy(step['result_contract']['record'])
        record.update(actor=step['bound_actor'], output=self.reference(contents[0]))
        return {'operation': 'record_result', 'phase': step['phase'], 'lease': step['lease']['token'],
                'actor': step['bound_actor'], 'files': list(self.session.consumed), 'record': record,
                'request_id': request_id,
                'artifacts': [{'content': content, 'hash': content_hash(content)} for content in contents]}

    def test_inline_multiple_artifacts_result_release_share_one_durable_checkpoint(self):
        # Exact storage/ownership guard through public generic host output transactions.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.GenericStoragePublicTests.test_inline_outputs_result_receipt_and_lease_release_share_one_checkpoint',
        )

    def test_inline_request_conflicting_hash_and_actor_fail_before_writes(self):
        # Generic host issuance preserves transport/reconstruction budgets and atomic preflight.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_evidence_dag_journeys.GenericStoragePublicTests.test_caller_hash_or_extra_operation_cannot_authorize_inline_outputs')

    def test_full_transaction_oversize_preflight_precedes_first_artifact_write(self):
        # Generic host issuance preserves transport/reconstruction budgets and atomic preflight.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_evidence_dag_journeys.GenericStoragePublicTests.test_oversized_single_record_preflight_precedes_every_bundle_write')

    def test_standalone_artifact_budget_preflight_preserves_usable_existing_comments(self):
        # Generic host issuance preserves transport/reconstruction budgets and atomic preflight.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_evidence_dag_journeys.GenericStoragePublicTests.test_existing_storage_budget_rejection_preserves_readable_history_and_usable_lease')

    def test_inline_aggregate_budget_rejection_has_no_provider_mutations(self):
        # Generic host issuance preserves transport/reconstruction budgets and atomic preflight.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_evidence_dag_journeys.GenericStoragePublicTests.test_aggregate_output_budget_rejects_all_slots_without_mutation_then_accepts_small_bundle')

    def test_latest_historical_and_pinned_reads_exclude_pending_uploads(self):
        # Exact storage/ownership guard through public generic host output transactions.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.GenericStoragePublicTests.test_pending_multipart_outputs_cannot_replace_latest_historical_or_pinned_reads',
        )

    def test_inline_review_does_not_imply_human_approval(self):
        # Exact storage/ownership guard through public generic host output transactions.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_phase_review_contract.GenericReviewGateTests.test_review_is_not_human_approval_and_root_binds_current_subject_and_review',
        )

    def test_pending_variable_verification_reuses_exact_proof_and_log(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_pending_workspace_submission_reuses_exact_observed_proof_and_log')

    def test_renew_retry_preserves_expiry_before_body_publication(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_workflow_renewal.GenericRenewalTests.test_renewal_retry_before_body_preserves_generated_expiry')

    def test_renew_retry_preserves_expiry_after_body_publication(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_workflow_renewal.GenericRenewalTests.test_renewal_retry_after_body_preserves_generated_expiry')

    def check_renew_retry(self, boundary):
        s = self.session
        step = s.start(101, 'understand')
        request = {'operation': 'renew', 'phase': 'understand', 'lease': step['lease']['token'],
                   'actor': step['bound_actor'], 'worker_status': 'active',
                   'request_id': 'renew-retry-' + boundary}
        attempted = []
        original = s.provider.update_issue
        before_comments = len(s.provider.comments[101])
        before_updates = len(s.provider.updates)
        def unavailable(number, payload):
            attempted.append(copy.deepcopy(payload))
            if boundary == 'after':
                original(number, payload)
            raise z.GoalTransitionProviderError('lost ' + boundary + ' body publication')
        with mock.patch.object(s.provider, 'update_issue', side_effect=unavailable):
            s.call(101, request, expected=None)
        self.assertEqual(1, len(attempted))
        persisted = z.parse_managed_goal(attempted[0]['body'], 101)['workflow']['leases']['understand:execute']
        response = s.call(101, request, expected=None)
        self.assertEqual(0, s.calls[-1]['code'], response)
        self.assertEqual(persisted['expires_at'], response['next_steps'][0]['expires_at'])
        self.assertEqual(persisted, s.goal(101)['workflow']['leases']['understand:execute'])
        self.assertEqual(before_comments + 1, len(s.provider.comments[101]))
        self.assertEqual(before_updates + 1, len(s.provider.updates))

    def test_verification_proof_and_transition_share_one_comment(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_workspace_proof_output_result_and_transition_share_one_checkpoint')

    def test_partial_envelope_and_lost_body_responses_reuse_inline_transaction(self):
        for boundary in ('append', 'body'):
            with self.subTest(boundary=boundary):
                # Each scenario has independent authority and durable provider state.
                case = CommentCheckpointPublicTests()
                case.setUp()
                try:
                    s = case.session
                    step = s.start(101, 'understand')
                    contents = [{'requirements': 'Crash-safe result.'}, {'proof': 'Additional evidence.'}]
                    request = case.inline_result(step, contents)
                    before_comments, before_updates = len(s.provider.comments[101]), len(s.provider.updates)
                    method = 'create_issue_comment' if boundary == 'append' else 'update_issue'
                    original = getattr(s.provider, method)
                    failed = False
                    def lost(*args):
                        nonlocal failed
                        result = original(*args)
                        if not failed:
                            failed = True
                            raise z.GoalTransitionProviderError('injected lost response')
                        return result
                    with mock.patch.object(s.provider, method, side_effect=lost):
                        s.call(101, request, expected=None)
                    s.call(101, request)
                    self.assertEqual(1, len(s.provider.comments[101]) - before_comments)
                    self.assertEqual(1, len(s.provider.updates) - before_updates)
                    self.assertEqual(contents[0], s.read(101, case.reference(contents[0])))
                finally:
                    case.doCleanups()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--legacy-prepare':
        legacy_prepare(sys.argv[2])
    else:
        unittest.main()
