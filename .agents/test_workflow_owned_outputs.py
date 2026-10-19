"""Owned source/test outputs, exercised through the real public CLI dispatcher.

Only provider, reviewed configuration, package and heartbeat boundaries are faked.
Supported predecessor parsing remains fixture data for trusted conversion;
current execution assertions use the single generic public engine.
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

    def call(self, number, payload=None, *, expected=0, intent="execute", response="full"):
        self.sequence += 1
        runtime = self.control / 'runtime.json'
        runtime.write_text(json.dumps(self.runtime))
        argv = ['zzzops', '--repo', str(self.repo), 'workflow', '--intent', intent,
                '--goal', str(number), '--runtime', str(runtime), '--response', response]
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
                mock.patch.object(api, 'provider_issue_snapshot',
                                  side_effect=getattr(self, 'provider_issue_snapshot',
                                                      lambda _repo, _repository, number: copy.deepcopy(self.provider.issues[number]))),
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

    def use_shipped_dag(self):
        template = json.loads((fixtures.fixtures.PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        dag = z._workflow_section({'policy': template['policy']}, 'workflow_adherence')['configuration']['phase_dag']
        z._workflow_section(self.session.project, 'workflow_adherence')['configuration']['phase_dag'] = dag
        self.assertEqual(['understand', 'decompose', 'test_design', 'implement', 'publish'], [n['id'] for n in dag['phases']])


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


    def require_implementation_human_approval(self):
        configuration = z._workflow_section(self.session.project, 'workflow_adherence')['configuration']
        implementation = next(node for node in configuration['phase_dag']['phases'] if node['id'] == 'implement')
        implementation['review']['human_approval'] = True


class CommentCheckpointPublicTests(unittest.TestCase):
    """#539 uses the existing public dispatcher and provider fixtures.

    Generic host-issued output transactions preserve immutable comment storage.
    Pure historical malformed-byte controls retain the shared read boundary;
    they confer no current phase execution or result authority.
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


if __name__ == '__main__':
    unittest.main()
