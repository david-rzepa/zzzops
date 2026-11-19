"""G1050: optional scaffolding is chosen by the design reviewer, not guessed by the engine.

The journeys exercise the real CLI against isolated local bare Git remotes. In particular,
red results must reflect a missing routing contract rather than a simulated frontier.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import subprocess
import time
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

    def flip_to_false(self):
        self.w.ok('a', 'reopen', str(self.g), 'review_design', '--note', 'reconsider scaffold')
        ag, card = self.reviewer()
        output = self.p.output('review_design', card, summary='unchanged design summary')
        output['scaffold_needed'] = False
        ag.submit(self.g, 'review_design', card, output)
        self.p.run(self.g, 'adversary_design', summary='unchanged adversary summary')
        self.p.run(self.g, 'filter_design', summary='unchanged filter summary')
        self.p.answer(self.g, 'approve_design')

    def test_live_scaffold_lease_prevents_switching_to_false(self):
        self.submit_review(True)
        self.approve_and_base()
        worker, card = self.p.start(self.g, 'scaffold')
        self.flip_to_false()
        next_ = self.next()
        self.assertNotIn('test_design', {a['node'] for a in next_['actions']}, next_)
        self.assertTrue(any(x['node'] == 'scaffold' for x in next_['running']), next_)

    def test_false_route_accepts_an_independently_reviewed_exact_scaffold(self):
        self.submit_review(True)
        self.approve_and_base()
        author, card = self.p.start(self.g, 'scaffold')
        output = self.p.output('scaffold', card)
        author.submit(self.g, 'scaffold', card, output)
        self.p.run(self.g, 'review_scaffold', avoid=(author.label,))
        self.flip_to_false()
        self.assertIn('test_design', {a['node'] for a in self.next()['actions']}, self.next())

    def test_waiving_scaffold_finding_does_not_approve_unreviewed_checkpoint(self):
        self.submit_review(True)
        self.approve_and_base()
        self.p.run(self.g, 'scaffold')
        self.p.run(self.g, 'review_scaffold', findings=[{'text': 'Contract is incomplete'}])
        doc = self.p.show(self.g)
        finding = next(f['id'] for f in doc['goal']['records']['review_scaffold']['findings'] if f['status'] == 'open')
        self.w.ok('a', 'edit', str(self.g),
                  '--set', f'records.review_scaffold.findings[{finding}].status="waived"',
                  '--set', f'records.review_scaffold.findings[{finding}].note="waived by owner"',
                  '--base', doc['goal_commit'])
        self.flip_to_false()
        next_ = self.next()
        self.assertNotIn('test_design', {a['node'] for a in next_['actions']}, next_)

    def test_false_route_requires_review_of_scaffold_removal(self):
        self.submit_review(True)
        self.approve_and_base()
        author, card = self.p.start(self.g, 'scaffold')
        output = self.p.output('scaffold', card)
        author.submit(self.g, 'scaffold', card, output)
        self.p.run(self.g, 'review_scaffold', findings=[{'text':'Remove unnecessary contract'}], avoid=(author.label,))
        self.flip_to_false()
        next_ = self.next()
        self.assertNotIn('test_design', {a['node'] for a in next_['actions']}, next_)
        repair, card = self.p.start(self.g, 'scaffold')
        wt = repair.worktree(self.g)
        wt.commit({'work/scaffold.txt': None}, 'refactor: remove scaffold')
        output = {'summary':'Removed scaffold', 'responses':{c['id']:'fixed: removed' for c in card.get('corrections', [])}}
        repair.submit(self.g, 'scaffold', card, output)
        self.assertNotIn('test_design', {a['node'] for a in self.next()['actions']}, self.next())
        self.p.run(self.g, 'review_scaffold', avoid=(repair.label,))
        self.assertIn('test_design', {a['node'] for a in self.next()['actions']}, self.next())

    def test_real_minimal_scaffold_then_red_behavior_then_separate_implementation(self):
        self.submit_review(True)
        self.approve_and_base()
        author, card = self.p.start(self.g, 'scaffold')
        wt = author.worktree(self.g)
        scaffold = wt.commit({'src/value.py':'def value():\n    raise NotImplementedError()\n'},
                             'feat: add unfinished callable contract')
        author.submit(self.g, 'scaffold', card, self.p.output('scaffold', card))
        self.p.run(self.g, 'review_scaffold', avoid=(author.label,))
        tester, card = self.p.start(self.g, 'test_design')
        wt = tester.worktree(self.g)
        test_commit = wt.commit({'tests/check_value.py': 'import sys\nsys.path.insert(0, ".")\nfrom src.value import value\nassert value() == 1\n'}, 'test: value behavior')
        cmd = 'python3 tests/check_value.py'
        start = time.monotonic_ns()
        red = subprocess.run(cmd, shell=True, cwd=wt.path, env=self.w.env, capture_output=True)
        duration = (time.monotonic_ns() - start) // 1000000
        self.assertNotEqual(0, red.returncode)
        self.assertIn(b'NotImplementedError', red.stderr)
        cost = {'checkpoint':test_commit, 'commands':[{'cmd':cmd,'duration_ms':duration,'exit':red.returncode}],
                'total_ms':duration, 'changed_tests':[{'id_or_scope':'tests/check_value.py','duration_ms':duration,
                'observation':'actual behavior test fails on unfinished scaffold'}], 'summary':'Measured red behavior test'}
        tester.submit(self.g, 'test_design', card, {'commands':[cmd], 'cost':cost})
        self.p.run(self.g, 'review_tests', avoid=(tester.label,))
        implementer, card = self.p.start(self.g, 'implement')
        wt = implementer.worktree(self.g)
        implementation = wt.commit({'src/value.py':'def value():\n    return 1\n'}, 'feat: implement behavior')
        implementer.submit(self.g, 'implement', card, self.p.output('implement', card))
        green = subprocess.run(cmd, shell=True, cwd=wt.path, env=self.w.env, capture_output=True)
        self.assertEqual(0, green.returncode, green.stderr)
        self.assertNotEqual(scaffold, implementation)
        self.assertNotEqual(test_commit, implementation)


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
        child.commit({'Runtime/value.py': 'value = 0\n', 'Tests/legacy.py':'assert True\n',
                      'Tests/rename_me.py':'assert 1 == 1\n'}, 'chore: base')
        self.w.seed.git('-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', child_path, 'Packages/example')
        self.w.seed.git('commit', '-q', '-m', 'chore: add package')
        self.w.seed.git('push', '-q', 'origin', 'HEAD:dev')
        policy = fx.load_template('POLICY.json')
        if ('conditional_review_routes' in CAPABILITIES
                and 'conditional_review_routes' not in policy['settings']['engine']['requires']):
            policy['settings']['engine']['requires'].append('conditional_review_routes')
        workflow = checkpoint_workflow()
        integrate = copy.deepcopy(fx.load_template('workflow.json')['graphs']['default']['nodes']['integrate'])
        integrate['inputs'] = {'base':{'from':'base.base_commit'}, 'code':{'from':'implement.code.tree'},
                               'review':{'from':'review_impl.summary','context':True}}
        workflow['graphs']['default']['nodes']['integrate'] = integrate
        self.gh = fx.FakeGitHub(self.w)
        self.w.bootstrap(policy=policy, workflow=workflow, settings={'verification.required_ci': []})
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

    def test_implementation_cannot_delete_accepted_child_helper(self):
        self.accepted_tests()
        card = self.writer.start(self.g, 'implement')
        self.child.commit({'Tests/helper.py': None}, 'fix: delete helper')
        self.parent.commit({}, 'fix: update package pointer')
        rc, out = self.writer.submit(self.g, 'implement', card, {'summary': 'Changed'}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertIn('helper.py', json.dumps(out), out)

    def test_implementation_cannot_change_a_newly_accepted_config(self):
        self.accepted_tests()
        self.w.ok('a', 'reopen', str(self.g), 'test_design', '--note', 'include configuration')
        card = self.writer.start(self.g, 'test_design')
        self.child.commit({'Tests/config.json': '{"mode":"safe"}'}, 'test: add configuration')
        self.parent.commit({}, 'test: add package test configuration')
        responses = {f['id']: 'fixed: included' for f in card['corrections']}
        self.writer.submit(self.g, 'test_design', card, {'commands': ['true'], 'responses': responses})
        card = self.reviewer.start(self.g, 'review_tests')
        previous = [{'id': f['id'], 'status': 'resolved'} for f in (card.get('previous') or {}).get('findings', []) if f['status'] == 'open']
        self.reviewer.submit(self.g, 'review_tests', card, {'decision':'approved','summary':'Reviewed','findings':previous}, artifact='Reviewed\n')
        card = self.writer.start(self.g, 'implement')
        self.child.commit({'Tests/config.json': '{"mode":"unsafe"}'}, 'fix: weaken configuration')
        self.parent.commit({}, 'fix: update package pointer')
        rc, out = self.writer.submit(self.g, 'implement', card, {'summary':'Changed'}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertIn('config.json', json.dumps(out), out)


    def test_earlier_child_test_stays_protected_after_noop_test_retry(self):
        self.accepted_tests()
        self.w.ok('a', 'reopen', str(self.g), 'test_design', '--note', 'reconsider tests')
        card = self.writer.start(self.g, 'test_design')
        responses = {f['id']: 'disputed: unchanged tests remain valid' for f in card['corrections']}
        self.writer.submit(self.g, 'test_design', card, {'commands': ['true'], 'responses': responses})
        state = self.w.ok('a', 'show', str(self.g), '--json')['states']['review_tests']
        if state.startswith('ready'):
            card = self.reviewer.start(self.g, 'review_tests')
            prior = [{'id': f['id'], 'status': 'resolved'} for f in (card.get('previous') or {}).get('findings', []) if f['status'] == 'open']
            self.reviewer.submit(self.g, 'review_tests', card, {'decision': 'approved', 'summary':'Reviewed', 'findings':prior}, artifact='Reviewed\n')
        card = self.writer.start(self.g, 'implement')
        self.child.commit({'Tests/helper.py': 'def expected(): return 0\n'}, 'fix: weaken old helper')
        self.parent.commit({}, 'fix: advance package pointer')
        rc, out = self.writer.submit(self.g, 'implement', card, {'summary':'Changed'}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertIn('helper.py', json.dumps(out), out)

    def test_missing_child_object_database_fails_closed_with_provenance_diagnostic(self):
        self.accepted_tests()
        card = self.writer.start(self.g, 'implement')
        self.child.commit({'Runtime/value.py': 'value = 1\n'}, 'feat: implement')
        self.parent.commit({}, 'feat: advance package pointer')
        gitdir = self.child.git('rev-parse', '--absolute-git-dir')
        shutil.move(gitdir, gitdir + '.unavailable')
        rc, out = self.writer.submit(self.g, 'implement', card, {'summary':'Changed'}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertTrue(any(word in json.dumps(out).lower() for word in ('provenance', 'submodule', 'child', 'object')), out)

    def test_blocked_retry_preserves_child_path_even_after_it_is_restored_absent(self):
        self.accepted_tests()
        self.w.ok('a', 'reopen', str(self.g), 'test_design', '--note', 'extend tests')
        card = self.writer.start(self.g, 'test_design')
        self.child.commit({'Tests/transient.py':'assert True\n'}, 'test: temporary child test')
        self.parent.commit({}, 'test: add child test')
        blocked = {'category':'decision','waiting_for':'agent','reason':'retry','instructions':'Complete the test change'}
        self.writer.submit(self.g, 'test_design', card, blocked=blocked)
        card = self.writer.start(self.g, 'test_design')
        self.child.commit({'Tests/transient.py':None}, 'test: remove transient test')
        self.parent.commit({}, 'test: update package tests')
        responses = {f['id']:'fixed: reconsidered' for f in card.get('corrections', [])}
        self.writer.submit(self.g, 'test_design', card, {'commands':['true'], 'responses':responses})
        states = self.w.ok('a', 'show', str(self.g), '--json')['states']
        if states['review_tests'].startswith('ready'):
            card = self.reviewer.start(self.g, 'review_tests')
            prior = [{'id': f['id'], 'status':'resolved'} for f in (card.get('previous') or {}).get('findings', []) if f['status'] == 'open']
            self.reviewer.submit(self.g, 'review_tests', card, {'decision':'approved','summary':'Reviewed','findings':prior}, artifact='Reviewed\n')
        card = self.writer.start(self.g, 'implement')
        self.child.commit({'Tests/transient.py':'assert False\n'}, 'fix: reintroduce transient file')
        self.parent.commit({}, 'fix: advance package pointer')
        rc, out = self.writer.submit(self.g, 'implement', card, {'summary':'Changed'}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertIn('transient.py', json.dumps(out), out)

    def test_child_pointer_rewrite_to_an_ancestor_fails_closed(self):
        self.accepted_tests()
        card = self.writer.start(self.g, 'implement')
        self.child.git('checkout', '-q', 'HEAD~1')
        self.parent.commit({}, 'fix: rewind package pointer')
        rc, out = self.writer.submit(self.g, 'implement', card, {'summary':'Rewound'}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertTrue(any(x in json.dumps(out).lower() for x in ('ancestor','rewrite','descendant','provenance')), out)

    def test_mismatched_child_repository_mapping_fails_closed(self):
        self.accepted_tests()
        card = self.writer.start(self.g, 'implement')
        self.child.commit({'Runtime/value.py':'value = 1\n'}, 'feat: implementation')
        self.parent.git('config', '-f', '.gitmodules', 'submodule.Packages/example.url', '/untrusted/different-repo')
        self.parent.commit({}, 'feat: change package mapping')
        rc, out = self.writer.submit(self.g, 'implement', card, {'summary':'Changed'}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertTrue(any(x in json.dumps(out).lower() for x in ('mapping','identity','repository','provenance')), out)

    def test_base_sync_preserves_child_tests_and_allows_implementation_advance(self):
        self.accepted_tests()
        before = self.w.ok('a', 'show', str(self.g), '--json')['goal']['records']['test_design']
        self.w.push_dev({'unrelated.txt':'upstream change\n'}, 'fix: unrelated upstream change')
        self.w.ok('a', 'reopen', str(self.g), 'base', '--note', 'sync upstream')
        self.w.ok('a', 'start', str(self.g), 'base', '--as', 'codex:aaaa/base-sync')
        after = self.w.ok('a', 'show', str(self.g), '--json')['goal']['records']['test_design']
        self.assertTrue(after['output']['tests']['commit'])
        self.assertTrue(before['output']['tests']['commit'])
        # The new pointer is allowed only if all child test entries still match.
        state = self.w.ok('a', 'show', str(self.g), '--json')['states']['review_tests']
        if state.startswith('ready'):
            card = self.reviewer.start(self.g, 'review_tests')
            prior = [{'id':f['id'],'status':'resolved'} for f in (card.get('previous') or {}).get('findings', []) if f['status']=='open']
            self.reviewer.submit(self.g, 'review_tests', card, {'decision':'approved','summary':'Reviewed','findings':prior}, artifact='Reviewed\n')
        card = self.writer.start(self.g, 'implement')
        self.child.commit({'Runtime/value.py':'value = 1\n'}, 'feat: implement')
        self.parent.commit({}, 'feat: advance child implementation')
        self.writer.submit(self.g, 'implement', card, {'summary':'Implemented'})

    def test_final_integration_tree_contains_verified_child_implementation_pointer(self):
        self.accepted_tests()
        card = self.writer.start(self.g, 'implement')
        child_tip = self.child.commit({'Runtime/value.py':'value = 1\n'}, 'feat: implement')
        self.parent.commit({}, 'feat: advance child implementation')
        self.writer.submit(self.g, 'implement', card, {'summary':'Implemented'})
        review = self.reviewer.start(self.g, 'review_impl')
        self.reviewer.submit(self.g, 'review_impl', review,
                             {'decision':'approved','summary':'Reviewed','findings':[]}, artifact='Reviewed\n')
        result = self.w.ok('a', 'start', str(self.g), 'integrate', '--as', 'codex:aaaa/integrate')
        self.assertTrue(result['ran']['ok'], result)
        pr = result['ran']['output']['pr']
        head = pr['head']
        entry = self.parent.git('ls-tree', head, 'Packages/example')
        self.assertIn(child_tip, entry)
        self.assertIn('160000 commit', entry)
        self.assertEqual('def expected(): return 1', self.child.git('show', child_tip + ':Tests/helper.py'))

    def accept_child_deletion_and_rename(self):
        card = self.writer.start(self.g, 'test_design')
        self.child.git('mv', 'Tests/rename_me.py', 'Tests/renamed.py')
        self.child.commit({'Tests/legacy.py':None}, 'test: delete and rename tests')
        self.parent.commit({}, 'test: update child test suite')
        self.writer.submit(self.g, 'test_design', card, {'commands':['true']})
        card = self.reviewer.start(self.g, 'review_tests')
        self.reviewer.submit(self.g, 'review_tests', card,
                             {'decision':'approved','summary':'Reviewed','findings':[]}, artifact='Reviewed\n')

    def valid_descendant_then_reopen(self):
        card = self.writer.start(self.g, 'implement')
        self.child.commit({'Runtime/value.py':'value = 1\n'}, 'feat: implement')
        self.parent.commit({}, 'feat: advance child')
        self.writer.submit(self.g, 'implement', card, {'summary':'Implemented'})
        self.w.ok('a', 'reopen', str(self.g), 'implement', '--note', 'additional implementation')
        card = self.writer.start(self.g, 'implement')
        responses = {c['id']:'fixed: further work' for c in card.get('corrections', [])}
        return card, responses

    def test_accepted_deletion_stays_absent_after_valid_child_implementation(self):
        self.accept_child_deletion_and_rename()
        card, responses = self.valid_descendant_then_reopen()
        self.child.commit({'Tests/legacy.py':'assert True\n'}, 'fix: reintroduce deleted test')
        self.parent.commit({}, 'fix: advance child')
        rc, out = self.writer.submit(self.g, 'implement', card,
                                     {'summary':'Changed','responses':responses}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertIn('legacy.py', json.dumps(out), out)

    def test_accepted_rename_old_path_stays_absent_after_valid_child_implementation(self):
        self.accept_child_deletion_and_rename()
        card, responses = self.valid_descendant_then_reopen()
        self.child.commit({'Tests/rename_me.py':'assert 1 == 1\n'}, 'fix: restore old name')
        self.parent.commit({}, 'fix: advance child')
        rc, out = self.writer.submit(self.g, 'implement', card,
                                     {'summary':'Changed','responses':responses}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertIn('rename_me.py', json.dumps(out), out)

    def test_accepted_rename_new_path_stays_unchanged_after_valid_child_implementation(self):
        self.accept_child_deletion_and_rename()
        card, responses = self.valid_descendant_then_reopen()
        self.child.commit({'Tests/renamed.py':'assert True\n'}, 'fix: change renamed test')
        self.parent.commit({}, 'fix: advance child')
        rc, out = self.writer.submit(self.g, 'implement', card,
                                     {'summary':'Changed','responses':responses}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertIn('renamed.py', json.dumps(out), out)

    def test_non_descendant_identical_child_tree_is_not_accepted_as_implementation(self):
        self.accepted_tests()
        accepted = self.child.git('rev-parse', 'HEAD')
        accepted_tree = self.child.git('rev-parse', 'HEAD^{tree}')
        card = self.writer.start(self.g, 'implement')
        self.child.git('checkout', '-q', '--orphan', 'unrelated-history')
        self.child.git('commit', '-q', '--allow-empty', '-m', 'feat: unrelated history')
        rewritten = self.child.git('rev-parse', 'HEAD')
        self.assertEqual(accepted_tree, self.child.git('rev-parse', 'HEAD^{tree}'))
        ancestry = subprocess.run(['git','-C',self.child.path,'merge-base','--is-ancestor',accepted,rewritten],
                                  env=self.w.env, capture_output=True)
        self.assertEqual(1, ancestry.returncode)
        self.parent.commit({}, 'feat: rewrite child history')
        rc, out = self.writer.submit(self.g, 'implement', card, {'summary':'Changed'}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertTrue(any(x in json.dumps(out).lower() for x in ('ancestor','rewrite','descendant','provenance')), out)


class PolicyAdoptionJourneys(unittest.TestCase):
    """Preview a copied old graph on the actual Git remote before adopting new defaults."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.gh = fx.FakeGitHub(self.w)
        self.old = json.loads((Path(__file__).parent / 'fixtures/scaffold-route-migration/workflow.json').read_text())
        self.new = fx.load_template('workflow.json')
        policy = fx.load_template('POLICY.json')
        policy['settings']['intent'] = copy.deepcopy(INTENT)
        policy['settings']['engine']['requires'] = [c for c in policy['settings']['engine']['requires']
                                                     if c != 'conditional_review_routes']
        self.w.bootstrap(policy=policy, workflow=self.old)
        self.p = Pilot(self.w, {})
        self.g = self.w.new(title='Previously reviewed goal')['created']['id']
        self.p.run(self.g, 'design')
        self.p.run(self.g, 'review_design')
        self.p.run(self.g, 'adversary_design')
        self.p.run(self.g, 'filter_design')
        self.p.answer(self.g, 'approve_design')

    def preview(self):
        nodes = self.new['graphs']['default']['nodes']
        self.assertIn('scaffold', nodes, 'shipped new graph must contain an optional scaffold node')
        policy = fx.load_template('POLICY.json')
        policy['settings']['intent'] = copy.deepcopy(INTENT)
        files = {'.zzzops/workflow.json': json.dumps(self.new), '.zzzops/POLICY.json': json.dumps(policy)}
        for prompt in (fx.TEMPLATES / 'prompts').iterdir():
            files[f'.zzzops/prompts/{prompt.name}'] = prompt.read_text()
        self.w.seed.commit(files, 'chore: preview new workflow')
        tip = self.w.seed.git('rev-parse', 'HEAD')
        return self.w.ok('a', 'show', str(self.g), '--json', '--policy-ref', tip, cwd=self.w.seed.path)

    def test_preview_does_not_invent_a_route_for_an_old_approved_review(self):
        before = self.p.show(self.g)
        old_review = before['goal']['records']['review_design']
        self.assertNotIn('scaffold_needed', old_review['output'])
        after = self.preview()
        self.assertNotEqual('current', after['states']['approve_design'], after)
        self.assertFalse(after['states']['base'].startswith('ready'), after)
        self.assertEqual(old_review, after['goal']['records']['review_design'])
        actual = self.p.show(self.g)
        self.assertEqual(before['goal_commit'], actual['goal_commit'])
        self.assertEqual(before['goal']['records'], actual['goal']['records'])

    def test_preview_preserves_live_lease_and_never_starts_new_workers(self):
        self.w.ok('a', 'start', str(self.g), 'base', '--as', 'claude:aaaa/base')
        agent, card = self.p.start(self.g, 'test_design')
        before = self.p.show(self.g)
        after = self.preview()
        self.assertEqual(before['goal_commit'], after['goal_commit'])
        self.assertEqual(before['goal']['records'], after['goal']['records'])
        actual = self.p.show(self.g)
        self.assertEqual('running', actual['states']['test_design'])
        self.assertEqual(card['lease']['attempt'], actual['leases'][0]['attempt'])

    def accept_old_tests(self, with_finding=False):
        self.w.ok('a', 'start', str(self.g), 'base', '--as', 'claude:aaaa/base')
        agent, card = self.p.start(self.g, 'test_design')
        wt = agent.worktree(self.g)
        checkpoint = wt.commit({'tests/old_probe.py': 'assert 1 + 1 == 2\n'}, 'test: old accepted test')
        command = 'python3 tests/old_probe.py'
        started = time.monotonic_ns()
        completed = subprocess.run(command, shell=True, cwd=wt.path, env=self.w.env, capture_output=True)
        duration = (time.monotonic_ns() - started) // 1000000
        self.assertEqual(0, completed.returncode)
        cost = {'checkpoint': checkpoint, 'commands': [{'cmd':command,'duration_ms':duration,'exit':0}],
                'total_ms':duration, 'changed_tests':[{'id_or_scope':'tests/old_probe.py', 'duration_ms':duration,
                'observation':'measured fixture test'}], 'summary':'Measured old fixture test'}
        agent.submit(self.g, 'test_design', card, {'commands':[command], 'cost':cost})
        reviewer, card = self.p.start(self.g, 'review_tests')
        findings = [{'text':'Fixture needs correction'}] if with_finding else []
        reviewer.submit(self.g, 'review_tests', card,
                        {'decision':'changes_requested' if findings else 'approved', 'summary':'Reviewed',
                         'findings':findings}, artifact='Reviewed\n')

    def test_preview_preserves_accepted_test_checkpoint_without_auto_approval(self):
        self.accept_old_tests()
        before = self.p.show(self.g)
        after = self.preview()
        self.assertEqual(before['goal']['records']['test_design'], after['goal']['records']['test_design'])
        self.assertNotEqual('current', after['states']['approve_design'], after)
        self.assertNotEqual('current', after['states']['review_tests'], after)
        self.assertEqual(before['goal_commit'], self.p.show(self.g)['goal_commit'])

    def test_preview_preserves_existing_open_finding(self):
        self.accept_old_tests(with_finding=True)
        before = self.p.show(self.g)
        old = before['goal']['records']['review_tests']['findings']
        self.assertTrue(any(f['status'] == 'open' for f in old), old)
        after = self.preview()
        self.assertEqual(old, after['goal']['records']['review_tests']['findings'])
        self.assertFalse(after['states']['implement'].startswith('ready'), after)

    def test_preview_preserves_implementation_lease_and_old_checkpoint(self):
        self.accept_old_tests()
        agent, card = self.p.start(self.g, 'implement')
        before = self.p.show(self.g)
        after = self.preview()
        self.assertEqual(before['goal']['records']['test_design'], after['goal']['records']['test_design'])
        self.assertEqual('running', self.p.show(self.g)['states']['implement'])
        self.assertNotEqual('current', after['states']['approve_design'], after)

    def test_adopting_preview_does_not_auto_approve_old_review(self):
        before = self.p.show(self.g)
        preview = self.preview()
        self.assertNotEqual('current', preview['states']['approve_design'], preview)
        self.w.seed.git('push', '-q', 'origin', 'HEAD:dev')
        after = self.p.show(self.g)
        self.assertNotEqual('current', after['states']['approve_design'], after)
        self.assertEqual(before['goal']['records']['review_design'], after['goal']['records']['review_design'])
        self.assertEqual(before['goal_commit'], after['goal_commit'])


if __name__ == '__main__':
    unittest.main()
