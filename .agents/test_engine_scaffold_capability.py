"""A routing policy must keep older writers from interpreting a new graph."""
import copy
import unittest

import engine_fixtures as fx
from engine import schemas


class ConditionalRoutingPolicyTests(unittest.TestCase):
    def test_default_graph_rejects_policy_without_the_capability(self):
        workflow = fx.load_template('workflow.json')
        policy = copy.deepcopy(fx.load_template('POLICY.json'))
        policy['settings']['engine']['requires'].remove('conditional_review_routes')
        errors = schemas.validate_workflow(workflow, policy)
        self.assertTrue(any('conditional_review_routes' in error for error in errors), errors)

class TransientChildHistoryTests(unittest.TestCase):
    def test_added_and_removed_submodule_cannot_evade_baseline(self):
        import shutil
        import tempfile
        from engine.gitrun import Git
        from engine.child_scope import capture
        from engine.errors import Refused
        from types import SimpleNamespace

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        parent = fx.make_repo(tmp, 'parent')
        child = fx.make_repo(tmp, 'child')
        child.commit({'test.py': 'assert True\n'}, 'test: initial child')
        parent.commit({'README': 'parent\n'}, 'chore: parent')
        start = parent.git('rev-parse', 'HEAD')
        parent.git('-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', child.path, 'pkg')
        parent.git('commit', '-q', '-m', 'test: add child')
        parent.git('rm', '-q', '-f', 'pkg')
        parent.git('commit', '-q', '-a', '-m', 'test: remove child')
        end = parent.git('rev-parse', 'HEAD')
        common = parent.git('rev-parse', '--absolute-git-dir')
        session = SimpleNamespace(git=Git(parent.path, common, 0))
        with self.assertRaisesRegex(Refused, 'added and removed'):
            capture(session, SimpleNamespace(work=start, goal=1), end, None)
