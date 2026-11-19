"""G1050: optional scaffolding is chosen by the design reviewer, not guessed by the engine.

The journeys exercise the real CLI against isolated local bare Git remotes. In particular,
red results must reflect a missing routing contract rather than a simulated frontier.
"""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest

import engine_fixtures as fx
from test_engine_lenses import INTENT, Pilot


class ScaffoldRouteJourneys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.gh = fx.FakeGitHub(self.w)
        policy = fx.load_template('POLICY.json')
        policy['settings']['intent'] = copy.deepcopy(INTENT)
        self.w.bootstrap(policy=policy)
        self.p = Pilot(self.w, {})
        self.g = self.w.new(title='Callable contract before tests')['created']['id']
        self.p.run(self.g, 'design')

    def reviewer(self):
        ag, card = self.p.start(self.g, 'review_design')
        self.assertIn('scaffold_needed', card['output_schema'],
                      'design review must provide an explicit typed route decision')
        self.assertEqual('bool', card['output_schema']['scaffold_needed'])
        return ag, card

    def submit_review(self, needed):
        ag, card = self.reviewer()
        output = self.p.output('review_design', card, summary='unchanged design summary')
        output['scaffold_needed'] = needed
        ag.submit(self.g, 'review_design', card, output)

    def approve_and_base(self):
        self.p.run(self.g, 'adversary_design', summary='unchanged adversary summary')
        self.p.run(self.g, 'filter_design', summary='unchanged filter summary')
        self.p.answer(self.g, 'approve_design')
        self.w.ok('a', 'start', str(self.g), 'base', '--as', 'claude:aaaa/base')

    def next(self):
        return self.w.ok('a', 'next', '--goal', str(self.g))

    def test_review_requires_a_boolean_decision(self):
        ag, card = self.reviewer()
        output = self.p.output('review_design', card)
        rc, result = ag.submit(self.g, 'review_design', card, output, ok=False)
        self.assertNotEqual(0, rc, result)
        output['scaffold_needed'] = 'false'
        rc, result = ag.submit(self.g, 'review_design', card, output, ok=False)
        self.assertNotEqual(0, rc, result)
        output['scaffold_needed'] = False
        ag.submit(self.g, 'review_design', card, output)

    def test_false_path_dispatches_no_scaffold_worker_and_offers_test_design(self):
        self.submit_review(False)
        self.approve_and_base()
        next_ = self.next()
        actions = {a['node'] for a in next_['actions']}
        self.assertIn('test_design', actions, next_)
        self.assertNotIn('scaffold', actions, next_)
        self.assertNotIn('review_scaffold', actions, next_)
        states = self.p.states(self.g)
        self.assertTrue(states['scaffold'].startswith('skipped'), states)
        self.assertTrue(states['review_scaffold'].startswith('skipped'), states)
        self.assertEqual({}, self.p.show(self.g)['goal']['skip'])

    def test_true_path_waits_for_independent_scaffold_review(self):
        self.submit_review(True)
        self.approve_and_base()
        next_ = self.next()
        actions = {a['node'] for a in next_['actions']}
        self.assertIn('scaffold', actions, next_)
        self.assertNotIn('test_design', actions, next_)
        scaffold_agent, card = self.p.start(self.g, 'scaffold')
        output = self.p.output('scaffold', card)
        scaffold_agent.submit(self.g, 'scaffold', card, output)
        next_ = self.next()
        actions = {a['node'] for a in next_['actions']}
        self.assertIn('review_scaffold', actions, next_)
        self.assertNotIn('test_design', actions, next_)
        rc, refused = scaffold_agent.start(self.g, 'review_scaffold', ok=False)
        self.assertNotEqual(0, rc, refused)
        self.assertEqual('independence', refused['error']['code'])
        self.p.run(self.g, 'review_scaffold', avoid=(scaffold_agent.label,))
        self.assertIn('test_design', {a['node'] for a in self.next()['actions']})

    def test_route_change_stales_adversary_filter_and_owner_approval(self):
        self.submit_review(False)
        self.approve_and_base()
        # Reopen the completed review. A new decision on the same design must
        # invalidate its consumers even when all their prose remains identical.
        self.w.ok('a', 'reopen', str(self.g), 'review_design', '--note', 'reconsider contract')
        ag, card = self.reviewer()
        output = self.p.output('review_design', card, summary='unchanged design summary')
        output['scaffold_needed'] = True
        ag.submit(self.g, 'review_design', card, output)
        states = self.p.states(self.g)
        for node in ('adversary_design', 'filter_design', 'approve_design'):
            self.assertNotEqual('current', states[node], (node, states))
        next_ = self.next()
        actions = {a['node'] for a in next_['actions']}
        self.assertNotIn('scaffold', actions, next_)
        self.assertNotIn('test_design', actions, next_)


    def test_changing_to_false_does_not_bypass_open_scaffold_review_finding(self):
        self.submit_review(True)
        self.approve_and_base()
        self.p.run(self.g, 'scaffold')
        self.p.run(self.g, 'review_scaffold', findings=[{'text': 'Contract is incomplete'}])
        self.w.ok('a', 'reopen', str(self.g), 'review_design', '--note', 'reconsider scaffold')
        ag, card = self.reviewer()
        output = self.p.output('review_design', card, summary='unchanged design summary')
        output['scaffold_needed'] = False
        ag.submit(self.g, 'review_design', card, output)
        self.p.run(self.g, 'adversary_design', summary='unchanged adversary summary')
        self.p.run(self.g, 'filter_design', summary='unchanged filter summary')
        self.p.answer(self.g, 'approve_design')
        next_ = self.next()
        actions = {a['node'] for a in next_['actions']}
        self.assertNotIn('test_design', actions, next_)
        self.assertTrue(any(a['node'] in ('scaffold', 'review_scaffold') for a in next_['actions'])
                        or any(i.get('kind') in ('dispute', 'approve') for i in next_['needs_human']), next_)
        doc = self.p.show(self.g)['goal']
        self.assertTrue(any(f['status'] == 'open' for f in doc['records']['review_scaffold']['findings']), doc)

    def test_stale_or_missing_design_review_never_selects_the_false_path(self):
        next_ = self.next()
        actions = {a['node'] for a in next_['actions']}
        self.assertIn('review_design', actions, next_)
        self.assertNotIn('test_design', actions, next_)
        self.assertNotIn('scaffold', actions, next_)
        self.submit_review(False)
        self.w.ok('a', 'reopen', str(self.g), 'review_design', '--note', 'review route again')
        next_ = self.next()
        actions = {a['node'] for a in next_['actions']}
        self.assertNotIn('test_design', actions, next_)
        self.assertNotIn('scaffold', actions, next_)


class SubmoduleTestPreservation(unittest.TestCase):
    """Actual child repos and gitlinks, not simulated Git or a path named like a package."""

    def setUp(self):
        from engine import CAPABILITIES
        from test_engine_conventional import checkpoint_workflow
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.w.env['GIT_ALLOW_PROTOCOL'] = 'file:https'
        child_path = self.tmp + '/package'
        child = fx.make_repo(self.tmp, name='package', env=self.w.env)
        child.commit({'Runtime/value.py': 'value = 0\n'}, 'chore: base')
        self.w.seed.git('-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', child_path, 'Packages/example')
        self.w.seed.git('commit', '-q', '-m', 'chore: add package')
        self.w.seed.git('push', '-q', 'origin', 'HEAD:dev')
        policy = fx.load_template('POLICY.json')
        if 'conditional_review_routes' in CAPABILITIES:
            policy['settings']['engine']['requires'].append('conditional_review_routes')
        self.w.bootstrap(policy=policy, workflow=checkpoint_workflow())
        self.writer = fx.Agent(self.w, 'a', 'codex:aaaa/writer')
        self.reviewer = fx.Agent(self.w, 'b', 'codex:bbbb/reviewer')
        self.g = self.w.new(title='Package test protection')['created']['id']
        self.w.ok('a', 'start', str(self.g), 'base', '--as', 'codex:aaaa/op')
        self.parent = self.writer.worktree(self.g)
        self.parent.git('-c', 'protocol.file.allow=always', 'submodule', 'update', '--init', 'Packages/example')
        self.child = fx.GitDir(self.parent.path + '/Packages/example', self.w.env)

    def accepted_tests(self):
        card = self.writer.start(self.g, 'test_design')
        self.child.commit({'Tests/probe.py': 'from helper import expected\nassert expected() == 1\n',
                           'Tests/helper.py': 'def expected(): return 1\n'}, 'test: package behavior')
        self.parent.commit({}, 'test: update package tests')
        self.writer.submit(self.g, 'test_design', card, {'commands': ['true']})
        card = self.reviewer.start(self.g, 'review_tests')
        self.reviewer.submit(self.g, 'review_tests', card,
                             {'decision': 'approved', 'summary': 'Reviewed', 'findings': []}, artifact='Reviewed\n')

    def test_implementation_pointer_advances_with_accepted_child_tests_unchanged(self):
        self.accepted_tests()
        card = self.writer.start(self.g, 'implement')
        self.child.commit({'Runtime/value.py': 'value = 1\n'}, 'feat: implement behavior')
        self.parent.commit({}, 'feat: update package implementation')
        self.writer.submit(self.g, 'implement', card, {'summary': 'Implemented'})
        record = self.w.ok('a', 'show', str(self.g), '--json')['goal']['records']['implement']
        self.assertEqual('done', record['status'])
        self.assertTrue(record['ok'])

    def test_implementation_cannot_change_only_child_helper(self):
        self.accepted_tests()
        card = self.writer.start(self.g, 'implement')
        self.child.commit({'Tests/helper.py': 'def expected(): return 0\n'}, 'fix: weaken helper')
        self.parent.commit({}, 'fix: update package pointer')
        rc, out = self.writer.submit(self.g, 'implement', card, {'summary': 'Changed'}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertIn('helper.py', json.dumps(out), out)


    def test_implementation_cannot_delete_accepted_child_test(self):
        self.accepted_tests()
        card = self.writer.start(self.g, 'implement')
        self.child.commit({'Tests/probe.py': None}, 'fix: delete package test')
        self.parent.commit({}, 'fix: update package pointer')
        rc, out = self.writer.submit(self.g, 'implement', card, {'summary': 'Changed'}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertIn('probe.py', json.dumps(out), out)

    def test_implementation_cannot_rename_accepted_child_helper(self):
        self.accepted_tests()
        card = self.writer.start(self.g, 'implement')
        self.child.git('mv', 'Tests/helper.py', 'Tests/renamed.py')
        self.child.git('commit', '-q', '-m', 'fix: rename helper')
        self.parent.commit({}, 'fix: update package pointer')
        rc, out = self.writer.submit(self.g, 'implement', card, {'summary': 'Changed'}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertIn('helper.py', json.dumps(out), out)


if __name__ == '__main__':
    unittest.main()
