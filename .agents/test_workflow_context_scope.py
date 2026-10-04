"""Local authority gates omit unconsumed remote capability inspection."""
import contextlib
import unittest
from unittest import mock

import test_zzzops as fixtures

z = fixtures.zzzops


class WorkflowContextScopeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.InitializationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.repo = self.fixture.repo
        with self.capabilities():
            applied = z.apply_plan(self.repo, self.fixture.plan())
            z.confirm_project(self.repo, applied['policy_digest'], 'test-user', [], True)

    @contextlib.contextmanager
    def capabilities(self):
        with contextlib.ExitStack() as stack:
            observations = {}
            for name, value in {
                'command_probe': {'available': False, 'ok': False},
                'github_repository_probe': {'available': False, 'usable': False},
                'github_release_evidence': {'status': 'unavailable', 'releases': None},
                'github_stack_probe': {'available': False, 'usable': False},
            }.items():
                observations[name] = stack.enter_context(mock.patch.object(z, name, return_value=value))
            observations['native_plugin_inventory'] = stack.enter_context(mock.patch.object(
                z._plugin_freshness, 'native_plugin_inventory',
                return_value={'cache_path': str(self.repo / 'absent-inventory-cache')}))
            yield observations

    def test_ready_context_gate_never_reads_unconsumed_capabilities(self):
        with self.capabilities() as observations:
            for _ in range(2):
                self.assertIsNone(z.workflow_context_step(self.repo, {}))
        self.assertEqual({}, {name: call.call_count for name, call in observations.items() if call.called})

    def test_full_inspection_preserves_capabilities_and_identical_readiness(self):
        with self.capabilities() as observations:
            full = z.inspect_initialization(self.repo)
            self.assertTrue(full['initialized'], 'Remote uncertainty never contributed to this local authority gate')
            self.assertEqual('unavailable', full['capabilities']['github_release_evidence']['status'])
            self.assertTrue(all(call.called for call in observations.values()))
            local = z.inspect_initialization(self.repo, include_capabilities=False)
        for field in ('state', 'initialized', 'valid_state', 'state_error', 'decision_blockers'):
            self.assertEqual(full[field], local[field])
        self.assertNotIn('capabilities', local)

    def test_local_policy_artifact_drift_is_rechecked_on_each_call(self):
        with self.capabilities() as observations:
            self.assertIsNone(z.workflow_context_step(self.repo, {}))
            audit = self.repo / '.zzzops' / 'PROJECT_AUDIT.md'
            audit.write_text(audit.read_text() + '\nchanged externally\n')
            gate = z.workflow_context_step(self.repo, {})
            self.assertEqual('policy-review', gate['id'])
            self.assertIn('policy:invalid_configuration', gate['reason'])
        self.assertFalse(any(call.called for call in observations.values()))

    def test_installation_upgrade_blocks_before_even_local_inspection(self):
        with self.capabilities() as observations, \
             mock.patch.object(z._installation, 'validation_status', return_value={'required': True, 'reason': 'package_changed'}), \
             mock.patch.object(z, 'inspect_initialization', side_effect=AssertionError('Must first validate installation')):
            gate = z.workflow_context_step(self.repo, {'version': 'next', 'revision': 'a' * 40})
        self.assertEqual('installation-validation', gate['id'])
        self.assertFalse(any(call.called for call in observations.values()))

    def test_public_mutation_with_policy_drift_stops_before_provider_authority(self):
        audit = self.repo / '.zzzops' / 'PROJECT_AUDIT.md'
        audit.write_text(audit.read_text() + '\nchanged externally\n')
        with self.capabilities(), \
             mock.patch.object(z._package, 'package_status', return_value={'ok': True}), \
             mock.patch.object(z, 'GitHubGoalTransitionAdapter', side_effect=AssertionError('Invalid policy must not reach provider')):
            response = z._workflow.public_run(z, self.repo, 'execute', '$execute-zzzops', {},
                {'operation': 'start', 'request_id': 'unchanged-retry-id'}, 100)
        self.assertEqual('policy-review', response['next_steps'][0]['id'])


if __name__ == '__main__':
    unittest.main()
