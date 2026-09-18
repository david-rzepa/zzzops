"""Public next-step policy disclosure without inline or repository artifacts."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

MODULE = Path(__file__).parents[1] / 'plugins/zzzops/zzzops/policy_context.py'
spec = importlib.util.spec_from_file_location('policy_context_subject', MODULE)
context = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context)


class PolicyContextTests(unittest.TestCase):
    def project(self):
        return {'policy': {'sections': [
            {'id': name, 'decision': 'custom ' + name, 'settings': {'custom': name},
             'exceptions': ['Keep this project-specific exception']}
            for name in ('security_privacy_compliance', 'documentation_style', 'code_quality',
                         'verification_testing', 'git_review_release', 'model_routing',
                         'workflow_adherence', 'autonomy_approval_parallelism')
        ]}}

    def test_phase_extracts_exact_blocks_without_inlining_or_repository_writes(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as output:
            repo = Path(root)
            result = {'next_steps': [{'kind': 'execute', 'phase': 'implement', 'goal': 1}]}
            context.attach(result, repo, self.project(), source='$execute-zzzops', temporary_root=output)
            ref = result['next_steps'][0]['policy']
            path = Path(ref['path'])
            self.assertFalse(path.is_relative_to(repo))
            self.assertEqual([], list(repo.iterdir()))
            text = path.read_text()
            self.assertIn('custom code_quality', text)
            self.assertIn('Keep this project-specific exception', text)
            self.assertNotIn('custom model_routing', text)
            self.assertNotIn('custom code_quality', json.dumps(result))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), ref['sha256'])
            self.assertEqual(self.project()['policy']['sections'][2], json.loads(text)['sections'][2])

    def test_policy_change_changes_excerpt_digest_and_review_gets_quality_policy(self):
        with tempfile.TemporaryDirectory() as output:
            project = self.project()
            first = {'next_steps': [{'kind': 'review', 'phase': 'plan'}]}
            second = {'next_steps': [{'kind': 'review', 'phase': 'plan'}]}
            context.attach(first, Path('.'), project, source='$execute-zzzops', temporary_root=output)
            project['policy']['sections'][2]['decision'] = 'new reviewed boundary'
            context.attach(second, Path('.'), project, source='$execute-zzzops', temporary_root=output)
            self.assertNotEqual(first['next_steps'][0]['policy']['sha256'], second['next_steps'][0]['policy']['sha256'])
            self.assertIn('new reviewed boundary', Path(second['next_steps'][0]['policy']['path']).read_text())

    def test_batch_steps_share_identical_extract_and_unknown_phase_keeps_all_blocks(self):
        with tempfile.TemporaryDirectory() as output:
            result = {'next_steps': [{'kind': 'batch_item', 'next_steps': [
                {'kind': 'execute', 'phase': 'implement'}, {'kind': 'review', 'phase': 'implement'},
                {'kind': 'execute', 'phase': 'custom_phase'}]}]}
            context.attach(result, Path('.'), self.project(), source='$execute-zzzops', temporary_root=output)
            steps = result['next_steps'][0]['next_steps']
            self.assertEqual(steps[0]['policy'], steps[1]['policy'])
            self.assertEqual(8, len(json.loads(Path(steps[2]['policy']['path']).read_text())['sections']))

    def test_gates_waits_and_receipts_do_not_generate_policy_files(self):
        with tempfile.TemporaryDirectory() as output:
            result = {'next_steps': [{'kind': name} for name in
                ('policy_review', 'installation_validation', 'checkpoint', 'await_worker', 'dependency')]}
            self.assertFalse(context.needs_context(result))
            context.attach(result, Path('.'), self.project(), source='$execute-zzzops', temporary_root=output)
            self.assertEqual([], list(Path(output).iterdir()))

    def test_assessment_and_feedback_receive_applicable_policy(self):
        with tempfile.TemporaryDirectory() as output:
            result = {'next_steps': [{'kind': 'assess', 'phase': 'plan'}]}
            context.attach(result, Path('.'), self.project(), source='$execute-zzzops', temporary_root=output)
            self.assertIn('model_routing', result['next_steps'][0]['policy']['sections'])
            feedback = {'next_steps': [{'kind': 'dispatch'}]}
            context.attach(feedback, Path('.'), self.project(), source='$send-zzzops-feedback', temporary_root=output)
            self.assertIn('security_privacy_compliance', feedback['next_steps'][0]['policy']['sections'])
            self.assertNotIn('verification_testing', feedback['next_steps'][0]['policy']['sections'])

    def test_all_phase_assignments_and_human_capture_have_disclosure(self):
        with tempfile.TemporaryDirectory() as output:
            result = {'next_steps': [
                {'kind': kind, 'phase': phase} for phase in context.PHASES
                for kind in ('execute', 'review', 'perform', 'human_approval')
            ] + [{'kind': 'human_approval', 'submission': {'operation': 'capture'}}]}
            context.attach(result, Path('.'), self.project(), source='$execute-zzzops', temporary_root=output)
            for step in result['next_steps']:
                self.assertIn('security_privacy_compliance', step['policy']['sections'])
                self.assertIn('autonomy_approval_parallelism', step['policy']['sections'])
                self.assertTrue(Path(step['policy']['path']).is_file())

    def test_policy_approval_is_never_disclosed_as_already_reviewed(self):
        result = {'next_steps': [{'kind': 'human_approval', 'submission': {'operation': 'policy_approve'}}]}
        self.assertFalse(context.needs_context(result))

    def test_public_boundary_attaches_policy_and_new_call_recovers_deleted_file(self):
        import test_zzzops as fixtures
        workflow = fixtures.zzzops._workflow
        api = SimpleNamespace(_policy_context=context, reviewed_project_state=mock.Mock(side_effect=AssertionError('Must not reread a newer policy')))
        with tempfile.TemporaryDirectory() as output:
            real_mkdtemp = tempfile.mkdtemp
            def local_temp(**kwargs):
                return real_mkdtemp(prefix=kwargs['prefix'], dir=output)
            with mock.patch.object(context.tempfile, 'mkdtemp', side_effect=local_temp):
                for attempt in range(2):
                    raw = {'next_steps': [{'kind': 'execute', 'phase': 'implement'}]}
                    def evaluate(*args, policy_snapshot):
                        policy_snapshot['project'] = self.project()
                        return raw
                    with mock.patch.object(workflow, '_public_run', side_effect=evaluate):
                        result = workflow.public_run(api, Path('.'), 'execute', '$execute-zzzops', {}, None, 1)
                    path = Path(result['next_steps'][0]['policy']['path'])
                    self.assertTrue(path.is_file())
                    path.unlink()
            api.reviewed_project_state.assert_not_called()

    def test_followup_verification_and_dispatch_steps_receive_policy(self):
        with tempfile.TemporaryDirectory() as output:
            kinds = ('heartbeat', 'record_result', 'record_review', 'correct',
                     'capability_discovery', 'inspect_evidence', 'integration',
                     'feedback_prepare', 'suggest', 'recover_legacy')
            result = {'next_steps': [{'kind': kind, 'phase': 'implement'} for kind in kinds]}
            context.attach(result, Path('.'), self.project(), source='$execute-zzzops', temporary_root=output)
            self.assertTrue(all('policy' in step for step in result['next_steps']))

    def test_misconfigured_temporary_root_cannot_write_policy_into_repository(self):
        with tempfile.TemporaryDirectory() as root:
            result = {'next_steps': [{'kind': 'execute', 'phase': 'implement'}]}
            with self.assertRaisesRegex(ValueError, 'outside the repository'):
                context.attach(result, Path(root), self.project(), source='$execute-zzzops', temporary_root=root)
            self.assertEqual([], list(Path(root).iterdir()))

    def test_capability_and_override_steps_disclose_routing_with_or_without_phase(self):
        with tempfile.TemporaryDirectory() as output:
            result = {'next_steps': [
                {'kind': kind, **phase} for kind in ('capability_discovery', 'session_override')
                for phase in ({}, {'phase': 'plan'})
            ]}
            context.attach(result, Path('.'), self.project(), source='$execute-zzzops', temporary_root=output)
            for step in result['next_steps']:
                self.assertIn('model_routing', step['policy']['sections'])

    def test_preview_policy_review_keeps_unreviewed_inspection_out_of_stdout_and_repo(self):
        import test_zzzops as fixtures
        z = fixtures.zzzops
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as output:
            repo = Path(root)
            inspection = {'state': self.project(), 'state_error': 'obsolete policy'}
            real_mkdtemp = tempfile.mkdtemp
            with (
                mock.patch.object(z._package, 'package_status', return_value={'ok': True, 'version': '1', 'revision': 'abc'}),
                mock.patch.object(z._installation, 'validation_status', return_value={'required': False}),
                mock.patch.object(z, 'workflow_context_step', return_value={'id': 'policy-review'}),
                mock.patch.object(z, 'inspect_initialization', return_value=inspection),
                mock.patch.object(z._policy_context.tempfile, 'mkdtemp', side_effect=lambda **kw: real_mkdtemp(prefix=kw['prefix'], dir=output)),
            ):
                result = z._workflow.public_run(z, repo, 'preview', '$execute-zzzops', {}, None, None)
            step = result['next_steps'][0]
            self.assertNotIn('custom code_quality', json.dumps(result))
            self.assertNotIn('policy', step)
            path = Path(step['inspection'])
            self.assertEqual(inspection, json.loads(path.read_text()))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), step['inspection_sha256'])
            self.assertEqual([], list(repo.iterdir()))

if __name__ == '__main__':
    unittest.main()
