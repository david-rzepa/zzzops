"""Durable, minimal comment-hydration checkpoint contract for goal #609."""
import base64
import copy
from datetime import datetime, timezone
import json
import unittest
from unittest import mock

import test_zzzops as fixtures
from test_evidence_dag_journeys import DagFixture

store = fixtures.zzzops._comment_store
z = fixtures.zzzops
REPOSITORY = 'owner/repo'


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
            REPOSITORY, 42, store.text_hash('issue body'), comments, [store.digest(required)])
        compact = [{'id': 11 + i, 'body': body} for i, body in enumerate(bodies)]
        view, observed = store.hydration_checkpoint_view(
            compact, [], repository=REPOSITORY, goal=42, issue_body_hash=store.text_hash('issue body'))

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
            REPOSITORY, 42, store.text_hash('issue body'), comments, [store.digest(value)])
        rows = [{'id': 20 + i, 'body': body} for i, body in enumerate(bodies)]

        with self.assertRaisesRegex(ValueError, 'binding'):
            store.hydration_checkpoint_view(
                rows, [], repository='other/repo', goal=42,
                issue_body_hash=store.text_hash('issue body'))
        with self.assertRaisesRegex(ValueError, 'binding'):
            store.hydration_checkpoint_view(rows, [], repository=REPOSITORY, goal=43, issue_body_hash=store.text_hash('issue body'))
        with self.assertRaisesRegex(ValueError, 'binding'):
            store.hydration_checkpoint_view(rows, [], repository=REPOSITORY, goal=42, issue_body_hash=store.text_hash('changed body'))

    def test_incremental_view_accepts_only_strictly_later_ordered_comments(self):
        value = {'current': True}
        comments = [self.envelope(10, [value])]
        bodies, _ = store.hydration_checkpoint_bodies(
            REPOSITORY, 42, store.text_hash('issue body'), comments, [store.digest(value)])
        checkpoint_rows = [{'id': 20 + i, 'body': body} for i, body in enumerate(bodies)]
        later = [self.envelope(30, [{'later': 1}]), self.envelope(31, [{'later': 2}])]

        view, _ = store.hydration_checkpoint_view(
            checkpoint_rows, later, repository=REPOSITORY, goal=42, issue_body_hash=store.text_hash('issue body'))
        self.assertEqual([20, 30, 31], [row['id'] for row in view])
        for invalid in ([later[1], later[0]], [later[0], later[0]], [comments[0]]):
            with self.assertRaisesRegex(ValueError, 'unique, ordered and later'):
                store.hydration_checkpoint_view(
                    checkpoint_rows, invalid, repository=REPOSITORY, goal=42, issue_body_hash=store.text_hash('issue body'))

    def test_incomplete_checkpoint_transaction_never_activates(self):
        children = [{'value': ''.join(store.text_hash(f'{index}-{part}') for part in range(900))}
                    for index in range(3)]
        root = {'children': [{'hash': store.digest(child),
                              'uri': 'zzzops:owner/repo:goal:42:' + store.digest(child)}
                             for child in children]}
        records = [store.ArtifactIndex([]).record(value) for value in [root, *children]]
        source_bodies = store.pack_envelopes(
            {'goal': 42, 'transaction': 'source-large', 'anchor': 'source-large', 'context': {}}, records)
        comments = [{'id': 10 + index, 'body': body} for index, body in enumerate(source_bodies)]
        bodies, _ = store.hydration_checkpoint_bodies(
            REPOSITORY, 42, store.text_hash('issue body'), comments, [store.digest(root)])
        self.assertGreater(len(bodies), 1)
        rows = [{'id': 20 + index, 'body': body} for index, body in enumerate(bodies)]

        with self.assertRaisesRegex(ValueError, 'manifest|transaction'):
            store.hydration_checkpoint_view(
                rows[:-1], [], repository=REPOSITORY, goal=42, issue_body_hash=store.text_hash('issue body'))

    def test_representative_histories_reduce_transferred_and_decoded_work(self):
        for count in (46, 818):
            with self.subTest(comments=count):
                value = {'current': True, 'goal': 42}
                comments = [
                    {'id': index, 'body': f'legacy audit event {index}: ' + ('x' * 256),
                     'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z'}
                    for index in range(1, count)
                ]
                comments.append(self.envelope(count, [value]))
                bodies, _ = store.hydration_checkpoint_bodies(
                    REPOSITORY, 42, store.text_hash('issue body'), comments, [store.digest(value)])
                checkpoint_rows = [
                    {'id': count + index + 1, 'body': body,
                     'created_at': '2026-01-02T00:00:00Z', 'updated_at': '2026-01-02T00:00:00Z'}
                    for index, body in enumerate(bodies)
                ]
                view, _ = store.hydration_checkpoint_view(
                    checkpoint_rows, [], repository=REPOSITORY, goal=42, issue_body_hash=store.text_hash('issue body'))
                full_bytes = sum(len(row['body'].encode()) for row in comments)
                warm_bytes = sum(len(row['body'].encode()) for row in view)

                self.assertLess(len(view), count)
                self.assertLess(warm_bytes, full_bytes)
                self.assertEqual(value, store.ArtifactIndex(view).resolve(store.digest(value))[0])


class WorkflowHydrationCheckpointTests(DagFixture):
    def publish_checkpoint(self):
        start = max(row['id'] for row in self.provider.comments[100]) + 1
        self.provider.comments[100].extend(
            {'id': start + offset, 'body': f'retained historical comment {offset}'}
            for offset in range(40)
        )
        steps = self.session.call(100)['next_steps']
        step = next(item for item in steps if item['kind'] == 'hydration_checkpoint')
        self.session.call(100, step['submission'])
        return step

    def test_expensive_read_prepares_and_idempotently_publishes_checkpoint(self):
        step = self.publish_checkpoint()
        published = self.session.call(100, step['submission'])
        self.assertEqual('checkpoint', published['next_steps'][0]['kind'])
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

    def test_expired_checkpoint_full_audit_detects_precheckpoint_edit(self):
        original = self.publish_checkpoint()
        historical = next(row for row in self.provider.comments[100] if row['body'].startswith('retained historical'))
        historical['body'] += ' edited'
        stamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        self.provider.get_issue_comment_tail = lambda number, limit=100: [
            {**row, 'created_at': stamp, 'updated_at': stamp}
            for row in self.provider.comments[number][-limit:]]

        with mock.patch.object(z._workflow, 'HYDRATION_CHECKPOINT_MAX_AGE_SECONDS', 0), \
             mock.patch.object(self.provider, 'get_issue_comments', wraps=self.provider.get_issue_comments) as full:
            repaired = self.session.call(100)
        self.assertGreater(full.call_count, 0)
        step = next(item for item in repaired['next_steps'] if item['kind'] == 'hydration_checkpoint')
        self.assertNotEqual(original['checkpoint'], step['checkpoint'])

    def test_uncertain_incremental_read_falls_back_to_complete_history(self):
        self.publish_checkpoint()
        self.provider.get_issue_comment_tail = mock.Mock(
            side_effect=z.GoalHistoryReadError('tail unavailable'))

        with mock.patch.object(self.provider, 'get_issue_comments',
                               wraps=self.provider.get_issue_comments) as full:
            resumed = self.session.call(100)
        self.assertGreater(full.call_count, 0)
        self.assertTrue(resumed['next_steps'])

    def test_oversized_checkpoint_does_not_block_the_workflow_frontier(self):
        start = max(row['id'] for row in self.provider.comments[100]) + 1
        self.provider.comments[100].extend(
            {'id': start + offset, 'body': f'retained historical comment {offset}'}
            for offset in range(40)
        )
        with mock.patch.object(store, 'hydration_checkpoint_bodies',
                               side_effect=ValueError('Transaction artifact record limit exceeded')):
            steps = self.session.call(100)['next_steps']
        self.assertTrue(steps)
        self.assertNotIn('hydration_checkpoint', {step['kind'] for step in steps})

    def retained_envelopes(self):
        start = max(row['id'] for row in self.provider.comments[100]) + 1
        for offset in range(40):
            record = store.ArtifactIndex([]).record({'retained': offset, 'text': 'x' * 8192})
            bodies = store.pack_envelopes(
                {'goal': 100, 'transaction': f'retained-{offset}',
                 'anchor': f'retained-{offset}', 'context': {}}, [record])
            self.assertEqual(1, len(bodies))
            self.provider.comments[100].append({'id': start + offset, 'body': bodies[0]})

    def test_valid_history_exceeding_checkpoint_decode_budget_keeps_frontier(self):
        self.retained_envelopes()
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        with mock.patch.object(store, 'MAX_RECONSTRUCTION_WORK_BYTES', 256 * 1024):
            # Each envelope is valid within the unchanged per-operation bound;
            # only the optional eager whole-history checkpoint cannot fit.
            for row in self.provider.comments[100]:
                store.decode_envelope(row['body'])
            with self.assertRaisesRegex(ValueError, 'Decoded content limit'):
                store.ArtifactIndex(self.provider.comments[100])
            steps = self.session.call(100)['next_steps']
        self.assertTrue(any(step['kind'] == 'execute' for step in steps))
        self.assertNotIn('hydration_checkpoint', {step['kind'] for step in steps})
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_checkpoint_materialization_budget_exhaustion_keeps_frontier(self):
        self.retained_envelopes()
        index = store.ArtifactIndex(self.provider.comments[100])
        budget = sum(index.decode_sizes[row['body']] for row in index.comments)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        with mock.patch.object(store, 'MAX_RECONSTRUCTION_WORK_BYTES', budget):
            self.assertEqual(budget, store.ArtifactIndex(self.provider.comments[100]).decode_work)
            steps = self.session.call(100)['next_steps']
        self.assertTrue(any(step['kind'] == 'execute' for step in steps))
        self.assertNotIn('hydration_checkpoint', {step['kind'] for step in steps})
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_overbudget_history_still_rejects_corrupt_envelopes(self):
        self.retained_envelopes()
        row = self.provider.comments[100][-1]
        original = row['body']
        for damage in ('hash', 'trailing'):
            with self.subTest(damage=damage):
                wrapper = json.loads(original[len(store.START):-len(store.END)])
                if damage == 'hash':
                    wrapper['hash'] = 'sha256:' + '0' * 64
                else:
                    encoded = base64.b64decode(wrapper['payload']) + b'trailing'
                    wrapper['payload'] = base64.b64encode(encoded).decode('ascii')
                row['body'] = store.START + json.dumps(wrapper) + store.END
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                with mock.patch.object(store, 'MAX_RECONSTRUCTION_WORK_BYTES', 256 * 1024):
                    response = self.session.call(100)
                self.assertTrue(response['next_steps'])
                self.assertTrue(all(step['kind'] == 'blocker' for step in response['next_steps']))
                self.assertRegex(json.dumps(response), r'hash mismatch|trailing encoding')
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        row['body'] = original


if __name__ == '__main__':
    unittest.main()
