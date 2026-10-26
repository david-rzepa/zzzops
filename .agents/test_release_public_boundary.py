"""Exercise release routing and the portfolio/provider boundary used by users."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import test_zzzops as fixtures
from test_release_planning import MemoryPlanAdapter

z = fixtures.zzzops


class ReleasePublicBoundaryTests(unittest.TestCase):
    def test_trunk_preview_fetches_valid_remote_oids_absent_from_local_repository(self):
        project = {'backend': 'github_issues',
                   'repository': {'identity': 'owner/repo'}}
        policy = {'enabled': True, 'publication_branch': 'main',
                  'integration_branch': 'dev',
                  'release_branch_prefix': 'release/'}
        plan = z._releases.new_release_plan(1)
        plan['releases'] = {'1': {'state': 'open'}}
        adapter = mock.Mock()
        adapter.read.return_value = plan
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / 'origin.git'
            seed = root / 'seed'
            repo = root / 'repo'
            subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True)
            subprocess.run(['git', 'init', '-q', '-b', 'main', str(seed)], check=True)
            subprocess.run(['git', '-C', str(seed), 'config', 'user.name', 'Release Test'], check=True)
            subprocess.run(['git', '-C', str(seed), 'config', 'user.email', 'release@example.test'], check=True)
            (seed / 'product.txt').write_text('main\n')
            subprocess.run(['git', '-C', str(seed), 'add', 'product.txt'], check=True)
            subprocess.run(['git', '-C', str(seed), 'commit', '-qm', 'main'], check=True)
            subprocess.run(['git', '-C', str(seed), 'branch', 'release/1'], check=True)
            subprocess.run(['git', '-C', str(seed), 'branch', 'dev'], check=True)
            subprocess.run(['git', '-C', str(seed), 'remote', 'add', 'origin', str(remote)], check=True)
            subprocess.run(['git', '-C', str(seed), 'push', '-q', 'origin',
                            'main', 'release/1', 'dev'], check=True)
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            subprocess.run(['git', '-C', str(repo), 'remote', 'add', 'origin', str(remote)], check=True)
            request = root / 'preview.json'
            request.write_text(json.dumps({'request_id': 'preview-remote-only-trunks'}))
            with mock.patch.object(z, 'reviewed_project_state', return_value=project), \
                 mock.patch.object(z, '_release_policy', return_value=policy), \
                 mock.patch.object(z, 'GitHubReleasePlanAdapter', return_value=adapter):
                result = z.release_cli(repo, 'propagate', request)

        self.assertIn(result['status'], {'current', 'propagate'})
        self.assertEqual(['main', 'release/1', 'dev'],
                         [name for name, _commit in result['trunks']])

    def test_trunk_preview_fails_closed_when_remote_ref_moves_during_observation(self):
        project = {'backend': 'github_issues',
                   'repository': {'identity': 'owner/repo'}}
        policy = {'enabled': True, 'publication_branch': 'main',
                  'integration_branch': 'dev',
                  'release_branch_prefix': 'release/'}
        plan = z._releases.new_release_plan(1)
        plan['releases'] = {'1': {'state': 'open'}}
        adapter = mock.Mock()
        adapter.read.return_value = plan
        first = {'main': 'a' * 40, 'release/1': 'b' * 40, 'dev': 'c' * 40}
        moved = {**first, 'release/1': 'd' * 40}
        observations = {name: 0 for name in first}
        def remote(command, **_kwargs):
            ref = command[-1]
            branch = ref.removeprefix('refs/heads/')
            observations[branch] += 1
            values = first if observations[branch] == 1 else moved
            return subprocess.CompletedProcess(
                command, 0, values[branch] + '\t' + ref + '\n', '')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = root / 'preview.json'
            request.write_text(json.dumps({'request_id': 'moving-remote-trunks'}))
            with mock.patch.object(z, 'reviewed_project_state', return_value=project), \
                 mock.patch.object(z, '_release_policy', return_value=policy), \
                 mock.patch.object(z, 'GitHubReleasePlanAdapter', return_value=adapter), \
                 mock.patch.object(z.subprocess, 'run', side_effect=remote), \
                 mock.patch.object(z._releases, 'preview_trunk_propagation',
                                   return_value={'status': 'current'}):
                with self.assertRaisesRegex(ValueError, 'moved|changed|remote'):
                    z.release_cli(root, 'propagate', request)

        self.assertEqual({'main': 2, 'release/1': 2, 'dev': 2}, observations)

    def test_public_trunk_propagation_derives_plan_and_remote_refs_on_host(self):
        plan = z._releases.new_release_plan(1)
        plan['releases'] = {
            '1': {'state': 'open'},
            '2': {'state': 'open'},
        }
        project = {'backend': 'github_issues',
                   'repository': {'identity': 'owner/repo'}}
        policy = {'enabled': True, 'publication_branch': 'main',
                  'integration_branch': 'dev',
                  'release_branch_prefix': 'release/'}
        adapter = mock.Mock()
        adapter.read.return_value = plan
        commits = {
            'main': 'a' * 40,
            'release/1': 'b' * 40,
            'release/2': 'c' * 40,
            'dev': 'd' * 40,
        }
        observed = []
        def remote(command, **_kwargs):
            self.assertEqual(['git', 'ls-remote', '--exit-code', '--refs',
                              'origin'], command[:5])
            ref = command[5]
            branch = ref.removeprefix('refs/heads/')
            observed.append(branch)
            return subprocess.CompletedProcess(
                command, 0, commits[branch] + '\t' + ref + '\n', '')

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = root / 'propagate.json'
            request.write_text(json.dumps({'request_id': 'propagate-reviewed-trunks'}))
            with mock.patch.object(z, 'reviewed_project_state', return_value=project), \
                 mock.patch.object(z, '_release_policy', return_value=policy), \
                 mock.patch.object(z, 'GitHubReleasePlanAdapter', return_value=adapter), \
                 mock.patch.object(z.subprocess, 'run', side_effect=remote), \
                 mock.patch.object(z._releases, 'preview_trunk_propagation',
                    return_value={'status': 'propagate', 'source': 'main',
                                  'target': 'release/1'}) as preview:
                result = z.release_cli(root, 'propagate', request)

        expected = [('main', commits['main']),
                    ('release/1', commits['release/1']),
                    ('release/2', commits['release/2']),
                    ('dev', commits['dev'])]
        self.assertEqual(['main', 'release/1', 'release/2', 'dev'], observed)
        preview.assert_called_once_with(root, expected)
        self.assertEqual({'status': 'propagate', 'source': 'main',
                          'target': 'release/1', 'trunks': expected}, result)

    def test_configure_retry_reuses_enrollment_after_audit_failure(self):
        adapter = MemoryPlanAdapter()
        adapter.open_goal_ids = mock.Mock(return_value=[7, 8])
        project = {'backend': 'github_issues', 'repository': {'identity': 'owner/repo'}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'request.json'
            request = {'request_id': 'configure', 'expected_revision': None,
                       'plan': z._releases.new_release_plan(1)}
            path.write_text(json.dumps(request))
            with mock.patch.object(z, 'reviewed_project_state', return_value=project), \
                 mock.patch.object(z, '_release_policy', return_value={'enabled': True}), \
                 mock.patch.object(z, 'GitHubReleasePlanAdapter', return_value=adapter), \
                 mock.patch.object(adapter, 'append_artifact', side_effect=ValueError('audit unavailable')):
                with self.assertRaisesRegex(ValueError, 'audit unavailable'):
                    z.release_cli(Path(directory), 'configure', path)
                self.assertEqual({'7': 1, '8': 1}, adapter.record['cohorts'])
                adapter.open_goal_ids.return_value = [7, 8, 9]
                replay = z.release_cli(Path(directory), 'configure', path)
                self.assertEqual({'7': 1, '8': 1}, replay['plan']['cohorts'])
                self.assertEqual(1, adapter.open_goal_ids.call_count)
                request['plan']['next_release'] = 2
                path.write_text(json.dumps(request))
                with self.assertRaisesRegex(ValueError, 'payload changed'):
                    z.release_cli(Path(directory), 'configure', path)

    def test_reassigned_goal_is_not_its_own_forbidden_future_commit(self):
        plan = z._releases.new_release_plan(1)
        plan['cohorts'] = {'7': 2}
        plan = z._releases.assign_release(plan, 7, 1, expected_revision=0)
        transport = z._GitHubReleaseTransport(Path('.'), 'owner/repo')
        engine = mock.Mock()
        engine.node_snapshot.return_value = {'projection': {'states': {
            'publication': {'publication': {'provider': {'head_oid': 'a' * 40}}}}}}
        with mock.patch.object(z, 'reviewed_project_state', return_value={}), \
             mock.patch.object(z._releases.GitHubReleasePlanAdapter, 'read', return_value=plan), \
             mock.patch.object(z, 'workflow_engine', return_value=engine), \
             mock.patch.object(transport.goals, '_run',
                 return_value=subprocess.CompletedProcess([], 0, '{"status":"identical"}', '')):
            result = transport.observe_integration('owner/repo', 7, 'a' * 40)
            self.assertEqual([], result['forbidden_commits'])
            engine.node_snapshot.assert_not_called()

    def test_release_membership_uses_explicit_assignment_over_old_enrollment(self):
        plan = z._releases.new_release_plan(1)
        plan['cohorts'] = {'7': 1}
        plan = z._releases.assign_release(plan, 7, 2, expected_revision=0)
        transport = z._GitHubReleaseTransport(Path('.'), 'owner/repo')
        engine = mock.Mock()
        engine.node_snapshot.return_value = {'payload': {'operational': {'leases': []}},
            'projection': {'states': {}, 'complete': False}, 'envelope': {}}
        project = {'policy': {'sections': [{'id': 'git_review_release',
                   'configuration': {'release_planning': {'integration_branch': 'dev'}}}]}}
        with mock.patch.object(z, 'reviewed_project_state', return_value=project), \
             mock.patch.object(z, 'portfolio_snapshot', return_value={'goals': []}), \
             mock.patch.object(z._releases.GitHubReleasePlanAdapter, 'read', return_value=plan), \
             mock.patch.object(z, 'workflow_engine', return_value=engine), \
             mock.patch.object(transport.goals, 'get_issue', return_value={}), \
             mock.patch.object(z, 'github_goal_record', return_value={'key': 7, 'schema_version': 2}), \
             mock.patch.object(z.subprocess, 'run', return_value=subprocess.CompletedProcess(
                 [], 0, 'a' * 40 + '\trefs/heads/dev\n', '')):
            self.assertEqual({}, transport.observe_release('owner/repo', 1)['members'])
            self.assertEqual({'7'}, set(transport.observe_release('owner/repo', 2)['members']))

    def test_documented_command_help_is_reachable_in_subprocess(self):
        result = subprocess.run([sys.executable, str(fixtures.MODULE_PATH),
                                 'release', '--help'], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        for command in ('status', 'configure', 'assign', 'checkpoint', 'approve', 'publication'):
            self.assertIn(command, result.stdout)

    def test_public_commands_dispatch_with_input_and_repo(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            payload = repo / 'request.json'
            payload.write_text('{}')
            for command in ('status', 'configure', 'assign', 'checkpoint', 'approve', 'publication'):
                for prefix in (True, False):
                    args = ['--repo', str(repo), 'release', command] if prefix else ['release', command, '--repo', str(repo)]
                    if command != 'status': args += ['--input', str(payload)]
                    with self.subTest(command=command, prefix=prefix), \
                         mock.patch.object(sys, 'argv', [str(fixtures.MODULE_PATH), *args]), \
                         mock.patch.object(z, 'release_cli', return_value={'ok': True}) as operation, \
                         contextlib.redirect_stdout(io.StringIO()) as out:
                        self.assertEqual(0, z.main())
                        self.assertEqual({'ok': True}, json.loads(out.getvalue()))
                        operation.assert_called_once_with(repo, command, None if command == 'status' else payload)

    def test_enabled_portfolio_passes_identity_to_real_transport(self):
        project = {'backend': 'github_issues', 'repository': {'identity': 'owner/repo'}, 'policy': {'sections': [
            {'id': 'git_review_release', 'configuration': {'release_planning':
                {'enabled': True, 'execution_scope': 'active_only'}}}]}}
        with mock.patch.object(z, '_validated_portfolio_project', return_value=project), \
             mock.patch.object(z, 'github_repository_portfolio_snapshot',
                 return_value=({'identity': 'owner/repo', 'usable': True}, {'goals': []})), \
             mock.patch.object(z.GitHubGoalTransitionAdapter, '_run',
                 return_value=subprocess.CompletedProcess([], 0, '[[]]', '')) as provider:
            with self.assertRaisesRegex(ValueError, 'release plan is missing'):
                z.portfolio_snapshot(Path('.'))
            self.assertIn('repos/owner/repo/issues?', provider.call_args.args[0][-1])


if __name__ == '__main__':
    unittest.main()
