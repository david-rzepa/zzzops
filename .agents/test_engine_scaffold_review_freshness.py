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
