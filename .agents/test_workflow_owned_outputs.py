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
        real_run = subprocess.run

        def provider_command(command, *args, **kwargs):
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

    def test_mixed_checkout_raw_drift_and_dirty_acquisition(self):
        s = self.session
        s.git('config', 'core.autocrlf', 'true')
        # Existing Windows fixture blobs may themselves contain CRLF.
        # Normalize the committed baseline before constructing mixed raw bytes.
        s.git('add', '--renormalize', '.')
        s.git('commit', '--allow-empty', '-qm', 'fixture: normalized mixed-checkout baseline')
        (self.repo / 'read_dependency.txt').unlink()
        s.git('checkout', '--', 'read_dependency.txt')
        self.assertIn(b'\r\n', (self.repo / 'read_dependency.txt').read_bytes())
        source = self.repo / 'source.py'
        source.write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
        self.assertNotIn(b'\r\n', source.read_bytes())
        # Refresh Git's index stat cache after changing raw checkout EOLs.
        s.git('add', 'source.py')
        self.assertEqual('', s.git('diff', '--cached', '--name-only'))
        self.assertEqual('', s.git('status', '--porcelain'))
        s.prepare()
        step = s.start(101, 'test_design')
        self.assertIn('acquisition', step['lease'], 'Owned execution must freeze exact checkout acquisition')
        acquired = step['lease']['acquisition']
        self.assertIn('checkout_overrides', acquired, 'Mixed Git-clean checkout requires frozen raw overrides')
        self.assertIn('read_dependency.txt', acquired['checkout_overrides'])
        self.assertNotIn('source.py', acquired['checkout_overrides'])
        original = (self.repo / 'read_dependency.txt').read_bytes()
        (self.repo / 'read_dependency.txt').write_bytes(original.replace(b'\r\n', b'\n'))
        response = s.verify(step, expected=2)
        self.assertRegex(response['next_steps'][0]['reason'], '(?i)(drift|changed)')
        (self.repo / 'read_dependency.txt').write_bytes(original)
        s.git('config', 'core.autocrlf', 'false')
        s.verify(step)

    def test_non_equivalent_dirty_checkout_rejects_acquisition(self):
        s = self.session
        s.git('config', 'core.autocrlf', 'true')
        (self.repo / 'source.py').write_bytes(b'def answer():\r\n    return 999\r\n')
        s.prepare()
        with self.assertRaisesRegex(AssertionError, 'clean committed worktree baseline'):
            s.start(101, 'test_design')

    def test_crlf_correction_preserves_frozen_checkout_overrides(self):
        s = self.session
        s.git('config', 'core.autocrlf', 'true')
        for path in ['source.py', 'behavior_test.py', 'read_dependency.txt']:
            (self.repo / path).unlink()
        s.git('checkout', '--', 'source.py', 'behavior_test.py', 'read_dependency.txt')
        self.test_test_design_correction_retains_baseline_failure_predecessor()

    def test_crlf_clean_checkout_public_acquisition(self):
        s = self.session
        s.git('config', 'core.autocrlf', 'true')
        for path in ['source.py', 'behavior_test.py', 'read_dependency.txt']:
            (self.repo / path).unlink()
        s.git('checkout', '--', 'source.py', 'behavior_test.py', 'read_dependency.txt')
        self.assertIn(b'\r\n', (self.repo / 'source.py').read_bytes())
        self.assertEqual('', s.git('status', '--porcelain'))
        s.prepare()
        design, _ = s.design()
        self.assertTrue(design['lease']['acquisition']['checkout_overrides'])
        s.implement()

    def test_existing_consumed_test_and_source_red_to_green(self):
        s = self.session
        s.prepare()
        parent_before = copy.deepcopy(s.goal(100)['phase_evidence']['records'])
        design, _ = s.design()
        self.assertEqual(set(s.consumed), set(design['input_envelope']['repository']['snapshot']['files']))
        implementation, proof_ref = s.implement()
        goal = s.goal(101)
        self.assertNotIn('predecessor', implementation['lease']['acquisition'])
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

    def test_undeclared_deletion_rejects_with_restored_valid_control(self):
        s = self.session
        s.prepare()
        step = s.start(101, 'test_design')
        original = (s.repo / 'read_dependency.txt').read_bytes()
        (s.repo / 'read_dependency.txt').unlink()
        rejected = s.verify(step, expected=2)
        self.assertRegex(json.dumps(rejected), r'(?i)(input|scope|drift|changed|output|ancestor)')
        (s.repo / 'read_dependency.txt').write_bytes(original)
        reference = s.verify(step)['next_steps'][0]['verification']
        self.assertTrue(s.read(101, reference)['passed'])

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
        self.assertTrue(any(x.get('phase') in {'understand', 'plan', 'implement'} or x['kind'] in {'repair', 'blocker', 'dependency'}
                            for x in changed), changed)
        self.assertNotEqual(baseline, changed)
        self.assertFalse(any(x.get('phase') == 'publish' and x['kind'] in {'assess', 'execute'} for x in changed))

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
        s = self.session
        parent = copy.deepcopy(s.plan)
        parent['output_scopes'] = [parent.pop('output_scope')]
        parent['output_scopes'][0]['implement'] = ['read_dependency.txt']
        s.prepare(parent)
        self.assert_scope_gate(s)

    def test_explicit_empty_scope_rejects_new_file_but_allows_unchanged_proof(self):
        s = self.session
        # This failing behavioral test already exists before the empty-output phase.
        (s.repo / s.test_path).write_text('from source import answer\nassert answer() == 2, "expected the required behavior"\n')
        s.git('add', s.test_path)
        s.git('commit', '-qm', 'fixture: pre-existing failing behavioral test')
        s.plan['output_scope']['test_design'] = []
        s.prepare()
        before = {path: file_hash(s.repo / path) for path in s.consumed}
        head = s.git('rev-parse', 'HEAD')
        step = s.start(101, 'test_design')
        control = s.verify(step)['next_steps'][0]['verification']
        baseline = s.read(101, control)
        self.assertFalse(baseline['passed'])
        self.assertIn('expected the required behavior', Path(baseline['commands'][0]['log']).read_text())
        (s.repo / 'unscoped_new.py').write_text('new = True\n')
        rejected = s.verify(step, expected=2)
        self.assertRegex(json.dumps(rejected), r'(?i)(scope|unexpected|workspace|output)')
        (s.repo / 'unscoped_new.py').unlink()
        restored = s.verify(step)['next_steps'][0]['verification']
        proof = s.read(101, restored)
        self.assertFalse(proof['passed'])
        self.assertEqual({}, proof['outputs'])
        self.assertEqual(baseline['workspace'], proof['workspace'])
        s.result(101, step, {'files': {}, 'behavior': 'Existing test specifies required behavior.'}, restored)
        s.review(101, 'test_design')
        self.assertEqual(before, {path: file_hash(s.repo / path) for path in s.consumed})
        self.assertEqual(head, s.git('rev-parse', 'HEAD'))
        record = s.goal(101)['phase_evidence']['records']['test_design']
        self.assertEqual(step['input_hash'], record['input_hash'])
        self.assertIn('test_design', s.goal(101)['phase_evidence']['reviews'])
        self.assertTrue(any(x.get('phase') == 'implement' and x['kind'] in {'assess', 'execute'}
                            for x in s.checkpoint(101)))

    def test_sibling_scopes_connect_completed_first_child_without_rewriting_history(self):
        s = self.session
        # Start-only provider construction: all later transitions are public main.
        sibling = self.fixture.issue(102, parent=100, title='Implement second source behavior')
        s.provider.issues[102] = sibling
        s.provider.comments[102] = []
        (s.repo / 'second_source.py').write_text('value = 1\n')
        (s.repo / 'second_test.py').write_text('from second_source import value\nassert value == 1\n')
        s.consumed += ['second_source.py', 'second_test.py']
        s.git('add', 'second_source.py', 'second_test.py')
        s.git('commit', '-qm', 'fixture: second existing source and test')
        second = copy.deepcopy(s.plan)
        second['output_scope'].update(child=102, test_design=['second_test.py'], implement=['second_source.py'])
        parent = {'behavior': 'Both child behaviors',
                  'output_scopes': [s.plan['output_scope'], second['output_scope']]}
        s.phase(100, 'understand', {'requirements': 'Both behaviors.'})
        for number in [101, 102]:
            s.phase(number, 'understand', {'requirements': 'Return two.'})
        s.phase(100, 'decompose', {'children': [101, 102]})
        s.phase(100, 'plan', parent)
        s.phase(101, 'plan', s.plan)
        s.phase(102, 'plan', second)
        s.git('branch', 'goal-second')
        for number in [101, 102]:
            goal = s.goal(number)
            metadata = copy.deepcopy(goal['implementation'])
            metadata.update(branch='goal-child' if number == 101 else 'goal-second', base='dev', target='dev')
            s.call(number, {'operation': 'revise', 'expected_digest': goal['digest'],
                            'changes': {'implementation': metadata}})
        parent_before = copy.deepcopy(s.goal(100)['phase_evidence'])
        s.assess(102, 'test_design')
        sibling_contract = next(x for x in s.checkpoint(102) if x.get('phase') == 'test_design')
        self.assertEqual('execute', sibling_contract['kind'])
        s.design()
        first = s.start(101, 'implement')
        (s.repo / 'source.py').write_text('def answer():\n    return 2\n')
        first_proof = s.verify(first)['next_steps'][0]['verification']
        s.result(101, first, {'files': {'source.py': file_hash(s.repo / 'source.py')}}, first_proof)
        self.assertNotIn('implement:execute', s.goal(101)['workflow']['leases'])
        blocked = s.checkpoint(102)
        self.assertFalse(any(x.get('phase') == 'test_design' and x['kind'] == 'execute' for x in blocked), blocked)
        direct = copy.deepcopy(sibling_contract['start'])
        direct['policy_receipt'] = json.loads(Path(sibling_contract['policy']['path']).read_text())['policy_receipt']
        direct.pop('request_id', None)
        rejected = s.call(102, direct, expected=2)
        self.assertRegex(json.dumps(rejected), r'(?i)(review|input|scope|ancestor|eligible|output)')
        s.review(101, 'implement')
        self.assertTrue(any(x.get('phase') == 'test_design' and x['kind'] == 'execute'
                            for x in s.checkpoint(102)))
        s.git('add', 'source.py')
        s.git('commit', '-qm', 'fix: first child behavior')
        # Real public publication and completion. Existing fixture supplies provider PR observations.
        self.fixture.head_oid = s.git('rev-parse', 'HEAD')
        self.fixture.base_oid = s.git('rev-parse', 'dev')
        child = s.goal(101)
        metadata = copy.deepcopy(child['implementation'])
        metadata['pr'] = 'https://github.com/owner/repo/pull/101'
        s.call(101, {'operation': 'revise', 'expected_digest': child['digest'],
                     'changes': {'implementation': metadata}})
        publication = s.start(101, 'publish')
        reference = s.verify(publication)['next_steps'][0]['verification']
        s.result(101, publication, {'publication': 'first exact produced head'}, reference)
        s.review(101, 'publish')
        # An actual remote merge is an external provider observation, not a goal-state mutation.
        self.fixture.pr_merged = True
        completion = next(x for x in s.checkpoint(101) if x['kind'] == 'complete')
        s.call(101, completion['submission'])
        self.assertEqual('done', s.goal(101)['status'])
        first_closed = copy.deepcopy(s.provider.issues[101])
        s.git('branch', '-f', 'goal-second', 'HEAD')
        s.git('checkout', '-q', 'goal-second')
        s.test_path = 'second_test.py'
        design = s.start(102, 'test_design')
        (s.repo / s.test_path).write_text('from second_source import value\nassert value == 2, "second required behavior"\n')
        failed = s.verify(design)['next_steps'][0]['verification']
        self.assertFalse(s.read(102, failed)['passed'])
        s.result(102, design, {'files': {s.test_path: file_hash(s.repo / s.test_path)}}, failed)
        s.review(102, 'test_design')
        s.git('add', s.test_path)
        s.git('commit', '-qm', 'test: second child behavior')
        implement = s.start(102, 'implement')
        (s.repo / 'second_source.py').write_text('value = 2\n')
        passed = s.verify(implement)['next_steps'][0]['verification']
        self.assertTrue(s.read(102, passed)['passed'])
        s.result(102, implement, {'files': {'second_source.py': file_hash(s.repo / 'second_source.py')}}, passed)
        s.review(102, 'implement')
        s.git('add', 'second_source.py')
        s.git('commit', '-qm', 'fix: second child behavior')
        self.assertEqual(first_closed, s.provider.issues[101])
        self.assertEqual(parent_before, s.goal(100)['phase_evidence'])
        baseline = s.checkpoint(102)
        self.assertFalse(any(x.get('phase') in {'understand', 'plan', 'test_design', 'implement'}
                             and x['kind'] in {'assess', 'execute', 'review'} for x in baseline), baseline)
        real_get = s.provider.get_issue
        first_spec = s.goal(101)['human_spec']
        def tampered_sibling_proof(number):
            issue = real_get(number)
            if number == 101:
                raw = z.parse_managed_goal(issue['body'], number)
                raw['workflow']['artifacts']['implement']['acquisition']['workspace_digest'] = 'sha256:' + '0' * 64
                issue['body'] = z.render_managed_goal(raw, first_spec, number)
            return issue
        with mock.patch.object(s.provider, 'get_issue', side_effect=tampered_sibling_proof):
            damaged = s.call(102, expected=None)
            self.assertFalse(any(x.get('phase') == 'publish' and x['kind'] in {'assess', 'execute'}
                                 for x in damaged['next_steps']), damaged)
            self.assertNotEqual(baseline, damaged['next_steps'])
        self.assertEqual(baseline, s.checkpoint(102))
        # Each value existed in authenticated history, but this mixed terminal
        # workspace is not connected by an authorized transformation.
        accepted_source = (s.repo / 'source.py').read_bytes()
        (s.repo / 'source.py').write_text('def answer():\n    return 1\n')
        disconnected = s.checkpoint(102)
        self.assertNotEqual(baseline, disconnected)
        self.assertFalse(any(x.get('phase') == 'publish' and x['kind'] in {'assess', 'execute'}
                             for x in disconnected), disconnected)
        (s.repo / 'source.py').write_bytes(accepted_source)
        restored = s.checkpoint(102)
        self.assertEqual(baseline, restored)
        (s.repo / 'read_dependency.txt').write_text('real unrelated drift\n')
        stale = s.checkpoint(102)
        self.assertNotEqual(baseline, stale)
        self.assertTrue(any(x['kind'] in {'dependency', 'repair', 'blocker'} or
                            x.get('phase') in {'understand', 'plan'} for x in stale), stale)

    def test_declared_deletion_has_same_proof_identity_after_commit(self):
        s = self.session
        s.prepare()
        design = s.start(101, 'test_design')
        (s.repo / s.test_path).write_text('from pathlib import Path\nassert not Path("source.py").exists(), "remove obsolete source"\n')
        failed = s.verify(design)['next_steps'][0]['verification']
        self.assertFalse(s.read(101, failed)['passed'])
        s.result(101, design, {'files': {s.test_path: file_hash(s.repo / s.test_path)}}, failed)
        s.review(101, 'test_design')
        s.git('add', s.test_path)
        s.git('commit', '-qm', 'test: require obsolete source deletion')
        step = s.start(101, 'implement')
        (s.repo / 'source.py').unlink()
        reference = s.verify(step)['next_steps'][0]['verification']
        proof = s.read(101, reference)
        self.assertTrue(proof['passed'])
        self.assertEqual('missing', proof['outputs']['source.py'])
        s.result(101, step, {'files': {'source.py': 'missing'}}, reference)
        s.review(101, 'implement')
        before = s.goal(101)['phase_evidence']['records']['implement']
        s.git('add', '-u')
        s.git('commit', '-qm', 'fix: delete obsolete source')
        after = s.checkpoint(101)
        self.assertFalse(any(x.get('phase') in {'understand', 'plan', 'test_design', 'implement'}
                             and x['kind'] in {'execute', 'review', 'assess'} for x in after), after)
        self.assertEqual(before, s.goal(101)['phase_evidence']['records']['implement'])

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
        s = self.session
        self.require_implementation_human_approval()
        public_review = s.review
        checked = []
        def review_and_approve(number, phase, content=None, *, acceptance='approved'):
            result = public_review(number, phase, content, acceptance=acceptance)
            if phase != 'implement' or acceptance != 'approved':
                return result
            producer = s.checkpoint(number)
            self.assertTrue(any(x.get('phase') == phase and x['kind'] == 'human_approval' for x in producer), producer)
            self.assertNotIn(phase, s.goal(number)['phase_evidence']['human_approvals'])
            if number == 101:
                blocked = s.checkpoint(102)
                self.assertFalse(any(x.get('phase') == 'test_design' and x['kind'] in {'assess', 'execute'}
                                     for x in blocked), blocked)
            approval = s.start(number, phase, 'human_approval')
            s.call(number, {'operation': 'approve', 'phase': phase, 'lease': approval['lease']['token'],
                            'actor': approval['bound_actor'], 'approval': {
                                'actor': approval['bound_actor'], 'approval_token': 'user: exact synthetic result approval'}})
            if number == 101:
                self.assertTrue(any(x.get('phase') == 'test_design' and x['kind'] == 'execute'
                                    for x in s.checkpoint(102)))
            checked.append(number)
            return result
        s.review = review_and_approve
        self.test_sibling_scopes_connect_completed_first_child_without_rewriting_history()
        self.assertEqual([101, 102], checked)

    def test_composed_correction_requires_current_human_approval_after_record_replacement(self):
        s = self.session
        self.require_implementation_human_approval()
        public_review = s.review
        replacements = []
        def review_and_approve(number, phase, content=None, *, acceptance='approved'):
            result = public_review(number, phase, content, acceptance=acceptance)
            if phase != 'implement':
                return result
            if acceptance == 'changes_requested':
                replacements.append(copy.deepcopy(s.goal(number)['phase_evidence']['records'][phase]))
                return result
            self.assertEqual(2, len(replacements))
            self.assertNotIn(phase, s.goal(number)['phase_evidence']['human_approvals'])
            steps = s.checkpoint(number)
            self.assertTrue(any(x.get('phase') == phase and x['kind'] == 'human_approval' for x in steps), steps)
            self.assertFalse(any(x.get('phase') == 'publish' and x['kind'] in {'assess', 'execute'} for x in steps), steps)
            approval = s.start(number, phase, 'human_approval')
            s.call(number, {'operation': 'approve', 'phase': phase, 'lease': approval['lease']['token'],
                            'actor': approval['bound_actor'], 'approval': {
                                'actor': approval['bound_actor'], 'approval_token': 'user: exact composed-result approval'}})
            valid = s.checkpoint(number)
            self.assertTrue(any(x.get('phase') == 'publish' for x in valid), valid)
            real_get = s.provider.get_issue
            spec = s.goal(number)['human_spec']
            def stale_approval(key):
                issue = real_get(key)
                if key == number:
                    raw = z.parse_managed_goal(issue['body'], key)
                    raw['phase_evidence']['human_approvals'][phase]['record_hash'] = content_hash(replacements[0])
                    issue['body'] = z.render_managed_goal(raw, spec, key)
                return issue
            with mock.patch.object(s.provider, 'get_issue', side_effect=stale_approval):
                rejected = s.call(number, expected=2)
                self.assertRegex(json.dumps(rejected), r'(?i)(approval.*stale|stale.*approval)')
            self.assertEqual(valid, s.checkpoint(number))
            return result
        s.review = review_and_approve
        self.test_recorded_output_exposes_own_review_and_correction_without_consumer_authority()

    def test_test_design_correction_retains_baseline_failure_predecessor(self):
        s = self.session
        s.prepare()
        first = s.start(101, 'test_design')
        (s.repo / s.test_path).write_text('from source import answer\nassert answer() == 2, "required value"\n')
        failed = s.verify(first)['next_steps'][0]['verification']
        self.assertFalse(s.read(101, failed)['passed'])
        s.result(101, first, {'files': {s.test_path: file_hash(s.repo / s.test_path)}}, failed)
        s.review(101, 'test_design', {'finding': 'Explain the regression assertion.'}, acceptance='changes_requested')
        rejected = copy.deepcopy(s.goal(101)['phase_evidence']['records']['test_design'])
        s.git('add', s.test_path)
        s.git('commit', '-qm', 'checkpoint: exact rejected test output')
        correction = s.start(101, 'test_design')
        self.assertNotEqual(first['input_hash'], correction['input_hash'])
        predecessor_ref = correction['lease']['acquisition']['predecessor']
        predecessor = s.read(101, predecessor_ref)
        self.assertEqual('test_design', predecessor['phase'])
        self.assertEqual(rejected, predecessor['record'])
        self.assertIsNone(predecessor['record']['verification'])
        self.assertEqual(failed, predecessor['record']['test_design']['baseline_failure'])
        (s.repo / s.test_path).write_text('from source import answer\n# The requested behavior returns two.\nassert answer() == 2, "required value"\n')
        corrected = s.verify(correction)['next_steps'][0]['verification']
        self.assertFalse(s.read(101, corrected)['passed'])
        self.assertEqual(predecessor_ref, s.read(101, corrected)['acquisition']['predecessor'])
        s.result(101, correction, {'files': {s.test_path: file_hash(s.repo / s.test_path)}}, corrected)
        steps = s.checkpoint(101)
        self.assertTrue(any(x.get('phase') == 'test_design' and x['kind'] == 'review' for x in steps), steps)
        self.assertFalse(any(x.get('phase') == 'implement' and x['kind'] in {'assess', 'execute'} for x in steps))
        # Public read exposes the exact failing proof reference for reviewer use.
        observed = s.call(101, {'operation': 'read', 'phase': 'test_design'})['next_steps'][0]['content']
        self.assertEqual(corrected, observed['phase_record']['test_design']['baseline_failure'])
        s.review(101, 'test_design')
        self.assertTrue(any(x.get('phase') == 'implement' and x['kind'] in {'assess', 'execute'}
                            for x in s.checkpoint(101)))

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
        def damaged_comments(number):
            comments = real_comments(number)
            for comment in comments:
                if comment['body'].startswith('<!-- zzzops-artifact ' + reference['hash'] + ' -->'):
                    comment['body'] = '<!-- zzzops-artifact ' + reference['hash'] + ' -->\ninvalid cyclic/tampered bytes'
            return comments
        with mock.patch.object(s.provider, 'get_issue_comments', side_effect=damaged_comments):
            rejected = s.verify(correction, expected=2)
            self.assertRegex(json.dumps(rejected), r'(?i)(artifact|predecessor|malformed|hash)')
        restored = s.verify(correction)['next_steps'][0]['verification']
        self.assertTrue(s.read(101, restored)['passed'])

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
        self.assertNotIn('predecessor', proof['acquisition'])
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
