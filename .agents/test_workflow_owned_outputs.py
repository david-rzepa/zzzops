"""Owned source/test outputs, exercised through the real public CLI dispatcher.

Only provider, reviewed configuration, package and heartbeat boundaries are faked.
ZZZOPS_OLD_CLI_ARCHIVE optionally supplies a pristine checkout archive for the
actual-version handoff test. The archive stays outside the repository.
"""
from __future__ import annotations

import contextlib
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
from unittest import mock

import test_workflow_journey as fixtures

z = fixtures.z


def content_hash(value):
    return 'sha256:' + hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
    ).encode()).hexdigest()


def file_hash(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else 'missing'


class PublicSession:
    """Public dispatch against real files and an in-memory remote provider."""

    def __init__(self, repo, project, runtime, provider, control, api=z):
        self.repo, self.project, self.runtime = Path(repo), project, runtime
        self.provider, self.control, self.api = provider, Path(control), api
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

    def call(self, number, payload=None, *, expected=0):
        self.sequence += 1
        runtime = self.control / 'runtime.json'
        runtime.write_text(json.dumps(self.runtime))
        argv = ['zzzops', '--repo', str(self.repo), 'workflow', '--intent', 'execute',
                '--goal', str(number), '--runtime', str(runtime)]
        if payload is not None:
            payload = copy.deepcopy(payload)
            payload.setdefault('request_id', f'public-{time.time_ns()}-{self.sequence}')
            request = self.control / 'input.json'
            request.write_text(json.dumps(payload))
            argv += ['--input', str(request)]
        api = self.api
        with contextlib.ExitStack() as stack:
            # These are external configuration/provider boundaries, never workflow decisions.
            patches = [
                mock.patch.object(api, 'configure_cli_stdout'),
                mock.patch.object(api._package, 'package_status', return_value={'ok': True}),
                mock.patch.object(api, 'workflow_context_step', return_value=None),
                mock.patch.object(api, 'reviewed_project_state', side_effect=lambda _repo: copy.deepcopy(self.project)),
                mock.patch.object(api, 'GitHubGoalTransitionAdapter', return_value=self.provider),
                mock.patch.object(api, 'GitHubReservationAdapter', return_value=SimpleNamespace()),
                mock.patch.object(api, 'portfolio_snapshot', side_effect=lambda *_a, **_k: {
                    'complete': True, 'valid': True,
                    'goals': [self.goal(n) for n in sorted(self.provider.issues)],
                }),
                mock.patch.object(api, 'acquire_storage_lock', side_effect=lambda *_a, **_k: {'acquired': True, 'expires_at': time.time() + 300}),
                mock.patch.object(api, 'renew_storage_lock', side_effect=lambda *_a, **_k: {'acquired': True, 'expires_at': time.time() + 300}),
                mock.patch.object(api, 'release_storage_lock', return_value={'released': True}),
                mock.patch.object(api._heartbeat, 'stop_heartbeat'),
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
        return self.call(101, request, expected=expected)

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
        elif step['phase'] == 'implement':
            record['verification'] = verification
        return self.call(number, {'operation': 'record_result', 'phase': step['phase'],
                                 'lease': step['lease']['token'], 'actor': step['bound_actor'],
                                 'files': list(self.consumed), 'record': record}, expected=expected)

    def review(self, number, phase, content=None):
        step = self.start(number, phase, 'review')
        output = self.artifact(number, step, content or self.plan_review)
        self.call(number, {'operation': 'record_review', 'phase': phase, 'lease': step['lease']['token'],
                           'actor': step['bound_actor'], 'artifact': output,
                           'outcomes': {'acceptance': 'approved', 'entropy': {
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

    def prepare(self):
        self.phase(100, 'understand', {'requirements': 'Return two.'})
        self.phase(101, 'understand', {'requirements': 'Return two.'})
        self.phase(100, 'decompose', {'child': 101})
        self.phase(100, 'plan', self.plan)
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
                                     self.fixture.provider, control.name)
        self.session.git('add', 'source.py', 'behavior_test.py', 'read_dependency.txt')
        self.session.git('commit', '-qm', 'fixture: existing source and test')
        self.session.git('checkout', '-q', '-B', 'goal-child')

    def test_existing_consumed_test_and_source_red_to_green(self):
        s = self.session
        s.prepare()
        parent_before = copy.deepcopy(s.goal(100)['phase_evidence']['records'])
        design, _ = s.design()
        self.assertEqual(set(s.consumed), set(design['input_envelope']['repository']['snapshot']['files']))
        implementation, proof_ref = s.implement()
        goal = s.goal(101)
        for phase, start in [('test_design', design), ('implement', implementation)]:
            self.assertEqual(start['input_hash'], goal['phase_evidence']['records'][phase]['input_hash'])
            self.assertEqual(start['input_envelope'], goal['phase_evidence']['records'][phase]['input_envelope'])
            self.assertNotEqual(goal['phase_evidence']['records'][phase]['actor'],
                                goal['phase_evidence']['reviews'][phase]['reviewer'])
        self.assertEqual(parent_before, s.goal(100)['phase_evidence']['records'])
        self.assertFalse(s.goal(101)['workflow']['leases'])
        proof = s.read(101, proof_ref)
        self.assertTrue(proof['passed'])
        self.assertEqual(implementation['input_hash'], proof['acquisition']['input_hash'])
        self.assertEqual(implementation['lease']['token'], proof['lease'])
        self.assertEqual(implementation['bound_actor'], proof['actor'])
        self.assertEqual('implement', proof['phase'])
        self.assertTrue(proof['acquisition']['git_commit'])
        self.assertTrue(proof['acquisition']['workspace_digest'])
        self.assertEqual(file_hash(self.repo / 'source.py'), proof['outputs']['source.py'])
        # A new invocation validates completed proof even though the execution lease is gone.
        self.assertFalse(any(step.get('phase') in {'understand', 'plan', 'test_design', 'implement'}
                             and step['kind'] in {'execute', 'review'} for step in s.checkpoint(101)))

    def test_no_edit_control_and_wrong_actor_or_lease_reject(self):
        s = self.session
        step = s.start(100, 'understand')
        for mutation in [{'actor': 'impostor'}, {'lease': 'wrong-token'}]:
            request = {'operation': 'record_result', 'phase': 'understand', 'lease': step['lease']['token'],
                       'actor': step['bound_actor'], 'files': list(s.consumed),
                       'record': copy.deepcopy(step['result_contract']['record']), **mutation}
            response = s.call(100, request, expected=2)
            self.assertRegex(response['next_steps'][0]['reason'], r'(?i)(bound|executor|lease|actor)')
        s.result(100, step, {'requirements': 'Unchanged valid inputs.'})
        s.review(100, 'understand')

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
        s = self.session
        s.prepare()
        step = s.start(101, 'test_design')
        for path in ['read_dependency.txt', 'unexpected.py']:
            target = self.repo / path
            previous = target.read_bytes() if target.exists() else None
            target.write_text('unrelated drift\n')
            response = s.verify(step, expected=2)
            self.assertRegex(response['next_steps'][0]['reason'], r'(?i)(drift|scope|changed|input|unexpected|output)')
            if previous is None:
                target.unlink()
            else:
                target.write_bytes(previous)

    def test_live_policy_change_invalidates_active_assignment(self):
        s = self.session
        s.prepare()
        step = s.start(101, 'test_design')
        section = z._workflow_section(s.project, 'verification_testing')
        section['instructions'] += ' Changed verification requirements.'
        response = s.verify(step, expected=2)
        self.assertRegex(response['next_steps'][0]['reason'], r'(?i)(policy|input|changed|stale|assignment|ancestor)')

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
        s = self.session
        s.prepare()
        s.design()
        acquired, reference = s.implement()
        proof = s.read(101, reference)
        self.assertEqual(acquired['input_hash'], proof['acquisition']['input_hash'])
        self.assertEqual(acquired['lease']['token'], proof['lease'])
        self.assertFalse(s.goal(101)['workflow']['leases'])
        baseline = s.checkpoint(101)
        self.assertFalse(any(x.get('phase') == 'implement' and x['kind'] == 'execute' for x in baseline))
        (self.repo / 'source.py').write_text('def answer():\n    return 99\n')
        changed = s.checkpoint(101)
        self.assertTrue(any(x.get('phase') == 'implement' or x['kind'] in {'repair', 'blocker', 'dependency'}
                            for x in changed), changed)
        self.assertNotEqual(baseline, changed)

    def test_durable_proof_rejects_tampered_acquisition_and_outputs(self):
        s = self.session
        s.prepare()
        s.design()
        step = s.start(101, 'implement')
        (self.repo / 'source.py').write_text('def answer():\n    return 2\n')
        reference = s.verify(step)['next_steps'][0]['verification']
        proof = s.read(101, reference)
        mutations = [
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
        s = self.session
        s.prepare()
        step = s.start(101, 'test_design')
        request = copy.deepcopy(step['start'])
        request.pop('request_id', None)
        request['policy_receipt'] = json.loads(Path(step['policy']['path']).read_text())['policy_receipt']
        response = s.call(101, request, expected=2)
        self.assertRegex(response['next_steps'][0]['reason'], r'(?i)(eligible|lease|worker|owned|capacity)')
        response = s.call(101, {'operation': 'recover', 'phase': 'test_design', 'lease': step['lease']['token'],
                               'worker_status': 'unknown', 'evidence': 'Cannot observe writer.'}, expected=2)
        self.assertRegex(response['next_steps'][0]['reason'], r'(?i)(stopped|recovery|worker|evidence)')
        self.assertIn('test_design:execute', s.goal(101)['workflow']['leases'])
        s.call(101, {'operation': 'release', 'phase': 'test_design', 'lease': step['lease']['token'],
                    'actor': step['bound_actor'], 'worker_status': 'stopped', 'evidence': 'Fixture worker stopped before edits.'})
        replacement = s.start(101, 'test_design')
        self.assertNotEqual(step['lease']['token'], replacement['lease']['token'])

    def test_missing_output_scope_cannot_exempt_an_existing_input(self):
        s = self.session
        s.plan.pop('output_scope')
        s.prepare()
        step = s.start(101, 'test_design')
        (self.repo / 'behavior_test.py').write_text('from source import answer\nassert answer() == 2\n')
        response = s.verify(step, expected=2)
        self.assertRegex(response['next_steps'][0]['reason'], r'(?i)(scope|input|changed|plan|output|ancestor)')

    @unittest.skipUnless(hasattr(os, 'symlink'), 'Platform cannot create symlinks')
    def test_owned_output_symlink_cannot_escape_the_worktree(self):
        s = self.session
        s.prepare()
        step = s.start(101, 'test_design')
        outside = s.control / 'outside.py'
        outside.write_text('raise SystemExit(0)\n')
        original = outside.read_bytes()
        owned = self.repo / s.test_path
        owned.unlink()
        owned.symlink_to(outside)
        response = s.verify(step, expected=2)
        self.assertRegex(response['next_steps'][0]['reason'], r'(?i)(outside|inside|escape|repository|worktree|symlink)')
        self.assertEqual(original, outside.read_bytes())

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
        self.assertEqual({'leases', 'receipts', 'workers', 'assessments', 'artifacts'},
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
        s = self.session
        step = self.legacy_handoff()
        original = copy.deepcopy(step['input_envelope'])
        (self.repo / 'source.py').write_text('def answer():\n    return 2\n')
        reference = s.verify(step, envelope=original)['next_steps'][0]['verification']
        s.result(101, step, {'files': {'source.py': file_hash(self.repo / 'source.py')}}, reference)
        s.review(101, 'implement')
        record = s.goal(101)['phase_evidence']['records']['implement']
        self.assertEqual(original, record['input_envelope'])
        self.assertEqual(step['input_hash'], record['input_hash'])
        proof = s.read(101, reference)
        self.assertEqual(step['lease']['token'], proof['lease'])
        self.assertEqual(step['input_hash'], proof['acquisition']['input_hash'])
        self.assertFalse(s.goal(101)['workflow']['leases'])

    def test_actual_old_dispatch_rejects_wrong_envelope_and_unrelated_output(self):
        s = self.session
        step = self.legacy_handoff()
        wrong = copy.deepcopy(step['input_envelope'])
        wrong['repository']['snapshot']['files']['source.py'] = 'sha256:' + '0' * 64
        response = s.verify(step, envelope=wrong, expected=2)
        self.assertRegex(response['next_steps'][0]['reason'], r'(?i)(envelope|input|acquisition|hash)')
        (self.repo / 'unexpected.py').write_text('unrelated\n')
        response = s.verify(step, expected=2)
        self.assertRegex(response['next_steps'][0]['reason'], r'(?i)(scope|unexpected|output|workspace|drift)')

    def test_actual_old_dispatch_requires_current_reviewed_baseline(self):
        s = self.session
        step = self.legacy_handoff()
        baseline = s.goal(101)['phase_evidence']['records']['test_design']
        self.assertIn('test_design', s.goal(101)['phase_evidence']['reviews'])
        s.call(101, {'operation': 'withdraw', 'phase': 'test_design',
                     'record_hash': content_hash(baseline), 'reason': 'Baseline review was withdrawn.'})
        response = s.verify(step, expected=2)
        self.assertRegex(response['next_steps'][0]['reason'],
                         r'(?i)(baseline|review|test.design|ancestor|eligible|input|acquisition)')

    def test_legacy_candidate_git_tree_must_match_reviewed_baseline(self):
        s = self.session
        step = self.legacy_handoff()
        reviewed_head = s.git('rev-parse', 'HEAD')
        original = (self.repo / 'read_dependency.txt').read_bytes()
        expected_inputs = copy.deepcopy(step['input_envelope'])
        artifacts_before = copy.deepcopy(s.goal(101)['workflow']['artifacts'])
        # Change the Git candidate, then restore all unrelated WORKING bytes.
        # The supplied original envelope and independently reviewed tests stay valid.
        (self.repo / 'read_dependency.txt').write_text('not the reviewed Git tree\n')
        s.git('add', 'read_dependency.txt')
        s.git('commit', '-qm', 'fixture: corrupt candidate baseline')
        self.assertNotEqual(reviewed_head, s.git('rev-parse', 'HEAD'))
        (self.repo / 'read_dependency.txt').write_bytes(original)
        self.assertEqual(expected_inputs['repository']['snapshot']['files']['read_dependency.txt'],
                         file_hash(self.repo / 'read_dependency.txt'))
        (self.repo / 'source.py').write_text('def answer():\n    return 2\n')
        response = s.verify(step, envelope=expected_inputs, expected=2)
        self.assertRegex(response['next_steps'][0]['reason'],
                         r'(?i)(candidate|baseline|snapshot|acquisition)')
        self.assertEqual(artifacts_before, s.goal(101)['workflow']['artifacts'],
                         'An invalid acquisition must not persist a verification proof')
        # Restore only the candidate/index. Keep identical produced source bytes.
        s.git('reset', '--mixed', reviewed_head)
        self.assertEqual(reviewed_head, s.git('rev-parse', 'HEAD'))
        reference = s.verify(step, envelope=expected_inputs)['next_steps'][0]['verification']
        proof = s.read(101, reference)
        self.assertTrue(proof['passed'])
        self.assertEqual(step['input_hash'], proof['acquisition']['input_hash'])
        self.assertEqual(step['lease']['token'], proof['lease'])



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


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--legacy-prepare':
        legacy_prepare(sys.argv[2])
    else:
        unittest.main()
