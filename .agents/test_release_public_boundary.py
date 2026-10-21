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

z = fixtures.zzzops


class ReleasePublicBoundaryTests(unittest.TestCase):
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
