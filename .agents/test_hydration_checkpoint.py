"""Durable, minimal comment-hydration checkpoint contract for goal #609."""
import copy
from datetime import datetime, timezone
import unittest
from unittest import mock

import test_zzzops as fixtures
from test_evidence_dag_journeys import DagFixture

store = fixtures.zzzops._comment_store


class HydrationCheckpointTests(unittest.TestCase):
    def envelope(self, comment_id, values, *, created='2026-01-01T00:00:00Z', updated=None):
        records = [store.ArtifactIndex([]).record(value) for value in values]
        bodies = store.pack_envelopes(
            {'goal': 42, 'transaction': f't-{comment_id}', 'anchor': f'a-{comment_id}', 'context': {}},
            records,
        )
        self.assertEqual(1, len(bodies))
        return {'id': comment_id, 'body': bodies[0], 'created_at': created, 'updated_at': updated or created}

    def test_materializes_only_required_current_closure(self):
        child, unrelated = {'current': [1, 2, 3]}, {'old': 'x' * 1000}
        required = {'child': {'hash': store.digest(child), 'uri': 'zzzops:owner/repo:goal:42:' + store.digest(child)}}
        comments = [self.envelope(10, [required, child, unrelated])]

        bodies, checkpoint = store.hydration_checkpoint_bodies(
            42, store.text_hash('issue body'), comments, [store.digest(required)])
        compact = [{'id': 11 + i, 'body': body} for i, body in enumerate(bodies)]
        view, observed = store.hydration_checkpoint_view(
            compact, [], goal=42, issue_body_hash=store.text_hash('issue body'))

        index = store.ArtifactIndex(view)
        self.assertEqual(required, index.resolve(store.digest(required))[0])
        self.assertEqual(child, index.resolve(store.digest(child))[0])
        self.assertNotIn(store.digest(unrelated), index.records)
        self.assertEqual(checkpoint, observed)
        self.assertEqual({'count': 1, 'last_id': 10}, {
            key: checkpoint['observation'][key] for key in ('count', 'last_id')})

    def test_same_second_edit_and_deletion_change_complete_observation(self):
        comments = [self.envelope(10, [{'value': 1}]), self.envelope(11, [{'value': 2}])]
        original = store.comment_observation(comments)
        edited = copy.deepcopy(comments)
        edited[0]['body'] += ' edited'
        deleted = comments[1:]

        self.assertNotEqual(original['digest'], store.comment_observation(edited)['digest'])
        self.assertNotEqual(original['digest'], store.comment_observation(deleted)['digest'])
        self.assertEqual(original['updated_through'], store.comment_observation(edited)['updated_through'])

    def test_checkpoint_is_bound_to_goal_issue_body_and_complete_manifest(self):
        value = {'current': True}
        comments = [self.envelope(10, [value])]
        bodies, _ = store.hydration_checkpoint_bodies(
            42, store.text_hash('issue body'), comments, [store.digest(value)])
        rows = [{'id': 20 + i, 'body': body} for i, body in enumerate(bodies)]

        with self.assertRaisesRegex(ValueError, 'binding'):
            store.hydration_checkpoint_view(rows, [], goal=43, issue_body_hash=store.text_hash('issue body'))
        with self.assertRaisesRegex(ValueError, 'binding'):
            store.hydration_checkpoint_view(rows, [], goal=42, issue_body_hash=store.text_hash('changed body'))

    def test_incremental_view_accepts_only_strictly_later_ordered_comments(self):
        value = {'current': True}
        comments = [self.envelope(10, [value])]
        bodies, _ = store.hydration_checkpoint_bodies(
            42, store.text_hash('issue body'), comments, [store.digest(value)])
        checkpoint_rows = [{'id': 20 + i, 'body': body} for i, body in enumerate(bodies)]
        later = [self.envelope(30, [{'later': 1}]), self.envelope(31, [{'later': 2}])]

        view, _ = store.hydration_checkpoint_view(
            checkpoint_rows, later, goal=42, issue_body_hash=store.text_hash('issue body'))
        self.assertEqual([20, 30, 31], [row['id'] for row in view])
        for invalid in ([later[1], later[0]], [later[0], later[0]], [comments[0]]):
            with self.assertRaisesRegex(ValueError, 'unique, ordered and later'):
                store.hydration_checkpoint_view(
                    checkpoint_rows, invalid, goal=42, issue_body_hash=store.text_hash('issue body'))


class WorkflowHydrationCheckpointTests(DagFixture):
    def test_expensive_read_prepares_and_idempotently_publishes_checkpoint(self):
        start = max(row['id'] for row in self.provider.comments[100]) + 1
        self.provider.comments[100].extend(
            {'id': start + offset, 'body': f'retained historical comment {offset}'}
            for offset in range(40)
        )

        prepared = self.session.call(100)
        step = prepared['next_steps'][0]
        self.assertEqual('hydration_checkpoint', step['kind'])
        before = len(self.provider.comments[100])
        published = self.session.call(100, step['submission'])
        self.assertEqual('checkpoint', published['next_steps'][0]['kind'])
        self.assertGreater(len(self.provider.comments[100]), before)
        after = copy.deepcopy(self.provider.comments[100])

        self.assertEqual(published, self.session.call(100, step['submission']))
        self.assertEqual(after, self.provider.comments[100])
        stamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        def tail(number, limit=100):
            return [{**row, 'created_at': stamp, 'updated_at': stamp}
                    for row in self.provider.comments[number][-limit:]]
        self.provider.get_issue_comment_tail = tail
        with mock.patch.object(self.provider, 'get_issue_comments', side_effect=AssertionError('full read not expected')):
            resumed = self.session.call(100)
        self.assertNotEqual('hydration_checkpoint', resumed['next_steps'][0]['kind'])


if __name__ == '__main__':
    unittest.main()
