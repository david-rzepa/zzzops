"""The false route must retain a current independent review of scaffold code."""
import unittest

import test_engine_scaffold_routes as routes


class ScaffoldReviewFreshnessTests(unittest.TestCase):
    def test_changed_design_cannot_reuse_old_scaffold_review(self):
        journey = routes.ScaffoldRouteJourneys('test_review_requires_a_boolean_decision')
        journey.setUp()
        self.addCleanup(journey.doCleanups)
        g, pilot = journey.g, journey.p
        journey.submit_review(True)
        journey.approve_and_base()
        author, card = pilot.start(g, 'scaffold')
        author.submit(g, 'scaffold', card, pilot.output('scaffold', card))
        pilot.run(g, 'review_scaffold', avoid=(author.label,))
        journey.w.ok('a', 'reopen', str(g), 'design', '--note', 'change reviewed design')
        pilot.run(g, 'design')
        journey.submit_review(False)
        pilot.run(g, 'adversary_design')
        pilot.run(g, 'filter_design')
        pilot.answer(g, 'approve_design')
        state = pilot.states(g)['base']
        if state.startswith('ready'):
            journey.w.ok('a', 'start', str(g), 'base', '--as', 'claude:aaaa/base')
        actions = {item['node'] for item in journey.next()['actions']}
        self.assertNotIn('test_design', actions)

    def test_open_downstream_finding_cannot_be_bypassed_by_false_route(self):
        journey = routes.ScaffoldRouteJourneys('test_review_requires_a_boolean_decision')
        journey.setUp()
        self.addCleanup(journey.doCleanups)
        g, pilot = journey.g, journey.p
        journey.submit_review(True)
        journey.approve_and_base()
        author, card = pilot.start(g, 'scaffold')
        author.submit(g, 'scaffold', card, pilot.output('scaffold', card))
        pilot.run(g, 'review_scaffold', avoid=(author.label,))
        writer, card = pilot.start(g, 'test_design')
        output = pilot.output('test_design', card,
                              findings=[{'target': 'scaffold', 'text': 'Contract is missing a seam'}])
        writer.submit(g, 'test_design', card, output)
        journey.flip_to_false()
        state = pilot.states(g)
        self.assertFalse(state['scaffold'].startswith('skipped'), state)
        self.assertNotIn('test_design', {item['node'] for item in journey.next()['actions']})
        snapshot = pilot.show(g)
        findings = snapshot['goal']['records']['test_design']['findings']
        finding = next(f for f in findings if f['target'] == 'scaffold' and f['status'] == 'open')
        journey.w.ok('a', 'edit', str(g),
                     '--set', f'records.test_design.findings[{finding["id"]}].status="waived"',
                     '--set', f'records.test_design.findings[{finding["id"]}].note="waived by owner"',
                     '--base', snapshot['goal_commit'])
        self.assertIn('test_design', {item['node'] for item in journey.next()['actions']})

    def test_blocked_scaffold_commits_cannot_be_bypassed_by_false_route(self):
        journey = routes.ScaffoldRouteJourneys('test_review_requires_a_boolean_decision')
        journey.setUp()
        self.addCleanup(journey.doCleanups)
        g, pilot = journey.g, journey.p
        journey.submit_review(True)
        journey.approve_and_base()
        author, card = pilot.start(g, 'scaffold')
        author.worktree(g).commit({'src/pending_contract.py': 'def call(): raise NotImplementedError()\n'},
                                  'feat: prepare callable contract')
        author.submit(g, 'scaffold', card, blocked={'category': 'decision', 'waiting_for': 'agent',
                                                   'reason': 'more work needed', 'instructions': 'Finish the scaffold'})
        journey.flip_to_false()
        state = pilot.states(g)
        self.assertFalse(state['scaffold'].startswith('skipped'), state)
        self.assertNotIn('test_design', {item['node'] for item in journey.next()['actions']})
        repair, card = pilot.start(g, 'scaffold')
        repair.submit(g, 'scaffold', card, pilot.output('scaffold', card))
        pilot.run(g, 'review_scaffold', avoid=(repair.label,))
        self.assertIn('test_design', {item['node'] for item in journey.next()['actions']})
