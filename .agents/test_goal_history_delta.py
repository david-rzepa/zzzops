"""#539 durable transition behavior; provider writes are in-memory only.

Proposed additive reconstruction API: goals.reconstruct_goal_history(adapter,
number, revision) returns {goal, human_spec, submitted_goal}. The historical goal
is a semantic projection, never a source of live workflow ownership.
"""
import copy
import hashlib
import json
import unittest

import test_zzzops as fixtures

z = fixtures.zzzops


class ReverseHistoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.GoalTransitionTests()
        self.issue = self.fixture.issue()
        self.adapter = fixtures.FakeGoalTransitionAdapter(self.issue)

    def test_large_unchanged_state_small_transition_fits_without_snapshot_copy(self):
        # Synthetic regression only: the real #498 measurement remains an integration gate.
        text = ''.join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(700))
        self.issue['body'] = z.render_managed_goal(self.fixture.goal(), '## Outcome\n\n' + text + '\n', 42)
        self.adapter = fixtures.FakeGoalTransitionAdapter(self.issue)
        result = z.apply_goal_transition(self.adapter, 'owner/repo', 42, self.fixture.transition(self.issue))
        self.assertEqual(2, result['revision'])
        self.assertTrue(all(len(c['body']) <= 65536 for c in self.adapter.comments))
        self.assertLess(sum(len(c['body']) for c in self.adapter.comments), 12000)
        self.assertIn(text, self.adapter.issue['body'])

    def test_pending_retry_binds_explicit_human_text(self):
        transition = self.fixture.transition(self.issue)
        transition['human_spec'] = '## Outcome\n\nApproved human text A.\n'
        self.adapter.failure = 'injected body failure'
        with self.assertRaises(z.GoalTransitionProviderError):
            z.apply_goal_transition(self.adapter, 'owner/repo', 42, transition)
        self.adapter.failure = None
        before = copy.deepcopy(self.adapter.comments)
        changed = copy.deepcopy(transition)
        changed['human_spec'] = '## Outcome\n\nDifferent human text B.\n'
        with self.assertRaises((ValueError, z.GoalTransitionProviderError)):
            z.apply_goal_transition(self.adapter, 'owner/repo', 42, changed)
        self.assertEqual(before, self.adapter.comments)
        self.assertEqual(self.issue['body'], self.adapter.issue['body'])
        z.apply_goal_transition(self.adapter, 'owner/repo', 42, transition)
        self.assertEqual(before, self.adapter.comments)
        self.assertIn('Approved human text A.', self.adapter.issue['body'])

    def test_lost_append_and_body_responses_recover_without_duplicate_writes(self):
        for boundary in ('append', 'body'):
            with self.subTest(boundary=boundary):
                adapter = fixtures.FakeGoalTransitionAdapter(self.issue)
                method = 'create_issue_comment' if boundary == 'append' else 'update_issue'
                original = getattr(adapter, method)
                def lost(*args):
                    original(*args)
                    raise z.GoalTransitionProviderError('lost response')
                setattr(adapter, method, lost)
                transition = self.fixture.transition(self.issue)
                try:
                    z.apply_goal_transition(adapter, 'owner/repo', 42, transition)
                except z.GoalTransitionProviderError:
                    pass
                setattr(adapter, method, original)
                result = z.apply_goal_transition(adapter, 'owner/repo', 42, transition)
                self.assertEqual(2, result['revision'])
                self.assertEqual(1, len(adapter.comments))
                self.assertEqual(1, len(adapter.updates))

    def test_publication_rechecks_state_after_append(self):
        original = self.adapter.create_issue_comment
        def racing(number, body):
            result = original(number, body)
            self.adapter.issue['body'] = self.adapter.issue['body'].replace('Preserve this human text.', 'Concurrent human edit.')
            return result
        self.adapter.create_issue_comment = racing
        with self.assertRaises((ValueError, z.GoalTransitionProviderError)):
            z.apply_goal_transition(self.adapter, 'owner/repo', 42, self.fixture.transition(self.issue))
        self.assertEqual([], self.adapter.updates)
        self.assertIn('Concurrent human edit.', self.adapter.issue['body'])

    def test_reconstructs_exact_human_text_and_submitted_only_semantics(self):
        transition = self.fixture.transition(self.issue)
        transition['goal']['evidence'] = ['Submitted only evidence.']
        transition['goal']['blockers'].append({'id': 'resolved', 'status': 'resolved', 'category': 'human-action', 'resolution': 'Done.'})
        z.apply_goal_transition(self.adapter, 'owner/repo', 42, transition)
        reconstruct = getattr(z._goals, 'reconstruct_goal_history', None)
        self.assertTrue(callable(reconstruct), 'Historical semantic reconstruction API is not implemented')
        historical = reconstruct(self.adapter, 42, 1)
        self.assertEqual(self.fixture.goal()['next_action'], historical['goal']['next_action'])
        self.assertIn('Preserve this human text.', historical['human_spec'])
        self.assertEqual(['Submitted only evidence.'], historical['submitted_goal']['evidence'])
        self.assertIn('resolved', [b['id'] for b in historical['submitted_goal']['blockers']])
        workflow = historical['goal'].get('workflow', {})
        for key in ('leases', 'workers', 'receipts'):
            self.assertFalse(workflow.get(key))

    def test_legacy_pending_and_completed_records_are_reused_without_rewrite(self):
        # Explicit schema-1 fixture, independent of the new writer.
        for explicit in (False, True):
            with self.subTest(explicit=explicit):
                adapter = fixtures.FakeGoalTransitionAdapter(self.issue)
                transition = self.fixture.transition(self.issue)
                if explicit:
                    transition['human_spec'] = '## Outcome\n\nPreserve this human text.\n'
                requested = transition['goal']
                payload = {'schema_version': 1, 'id': z._goals.goal_history_id(42, transition['expected_digest'], requested),
                           'issue': 42, 'expected_digest': transition['expected_digest'], 'from_revision': 1,
                           'to_revision': 2, 'prior_body': self.issue['body'], 'requested_goal': requested}
                payload['payload_digest'] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                body = (
                    '## ZzzOps transition history\n\nArchived canonical state before revision 2.\n\n'
                    '### Archived canonical body\n\n' + self.issue['body'].rstrip() + '\n\n'
                    '### Requested transition\n\n- Status: `blocked`\n- Next action:\n\nWait for review.\n\n'
                    '<details>\n<summary>' + z._goals.GOAL_HISTORY_DETAILS_SUMMARY + '</summary>\n\n'
                    '```json\n' + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n```\n\n</details>\n'
                )
                adapter.create_issue_comment(42, body)
                before = copy.deepcopy(adapter.comments)
                z.apply_goal_transition(adapter, 'owner/repo', 42, transition)
                z.apply_goal_transition(adapter, 'owner/repo', 42, transition)
                self.assertEqual(before, adapter.comments)
                self.assertEqual(1, len(adapter.updates))


if __name__ == '__main__':
    unittest.main()
