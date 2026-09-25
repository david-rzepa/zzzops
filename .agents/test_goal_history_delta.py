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


def semantic_predecessor(body, number):
    """Independent oracle: retain every persisted field except live coordination."""
    goal = copy.deepcopy(z.parse_managed_goal(body, number))
    if isinstance(goal.get('workflow'), dict):
        for field in ('leases', 'workers', 'receipts'):
            goal['workflow'].pop(field, None)
    human = body.split(z._goals.GOAL_BLOCK_START, 1)[0] + body.split(z._goals.GOAL_BLOCK_END, 1)[1]
    return {'goal': goal, 'human_spec': human}


def legacy_history_body(issue, transition):
    """Exact schema-1 renderer fixture validated against the rejected baseline."""
    number, requested = issue['number'], transition['goal']
    payload = {'schema_version': 1, 'id': z._goals.goal_history_id(number, transition['expected_digest'], requested),
               'issue': number, 'expected_digest': transition['expected_digest'],
               'from_revision': requested['revision'] - 1, 'to_revision': requested['revision'],
               'prior_body': issue['body'], 'requested_goal': requested}
    payload['payload_digest'] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return (
        f"## ZzzOps transition history\n\nArchived canonical state before revision {requested['revision']}.\n\n"
        '### Archived canonical body\n\n' + issue['body'].rstrip() + '\n\n'
        f"### Requested transition\n\n- Status: `{requested['status']}`\n- Next action:\n\n{requested['next_action']}\n\n"
        '<details>\n<summary>' + z._goals.GOAL_HISTORY_DETAILS_SUMMARY + '</summary>\n\n'
        '```json\n' + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n```\n\n</details>\n'
    )


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
        expected = semantic_predecessor(self.issue['body'], 42)
        expected['human_spec'] = '## Outcome / Why\n\nPreserve this human text.\n\n\n\n'
        transition = self.fixture.transition(self.issue)
        transition['goal']['evidence'] = ['Submitted only evidence.']
        transition['goal']['blockers'].append({'id': 'resolved', 'status': 'resolved', 'category': 'human-action', 'resolution': 'Done.'})
        z.apply_goal_transition(self.adapter, 'owner/repo', 42, transition)
        reconstruct = getattr(z._goals, 'reconstruct_goal_history', None)
        self.assertTrue(callable(reconstruct), 'Historical semantic reconstruction API is not implemented')
        historical = reconstruct(self.adapter, 42, 1)
        self.assertEqual(expected, {key: historical[key] for key in ('goal', 'human_spec')})
        self.assertEqual(transition['goal'], historical['submitted_goal'])

    def test_legacy_pending_and_completed_records_are_reused_without_rewrite(self):
        # Explicit schema-1 fixture, independent of the new writer.
        for explicit in (False, True):
            with self.subTest(explicit=explicit):
                adapter = fixtures.FakeGoalTransitionAdapter(self.issue)
                transition = self.fixture.transition(self.issue)
                if explicit:
                    transition['human_spec'] = '## Outcome\n\nPreserve this human text.\n'
                adapter.create_issue_comment(42, legacy_history_body(self.issue, transition))
                before = copy.deepcopy(adapter.comments)
                z.apply_goal_transition(adapter, 'owner/repo', 42, transition)
                z.apply_goal_transition(adapter, 'owner/repo', 42, transition)
                self.assertEqual(before, adapter.comments)
                self.assertEqual(1, len(adapter.updates))


if __name__ == '__main__':
    unittest.main()
