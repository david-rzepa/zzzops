"""Atomic submit continuations through the real public CLI and fake provider."""
import copy
import json
import unittest
from unittest import mock

import test_evidence_dag_journeys as journeys
from test_evidence_dag_journeys import DagFixture, z
import test_workflow_publication_contract as publication
from test_workflow_owned_outputs import content_hash


class SubmitContinuationTests(DagFixture):
    def ready_names(self, response):
        return {step['node']['node'] for step in response['next_steps'] if step['kind'] == 'execute'}

    def test_execution_and_independent_reviews_continue_without_checkpoint(self):
        work = self.session.acquire('produce')
        request = self.session.submission(work, {'value': 'candidate'}, 'direct-continuation')
        before = len(self.provider.updates)
        with mock.patch.object(z._workflow.Workflow, 'node_checkpoint', side_effect=AssertionError('submit cannot checkpoint')):
            response = self.session.call(100, request)
        self.assertEqual({'review_a', 'review_b'}, self.ready_names(response))
        self.assertEqual({'goal': 100, 'node': work['node'], 'result': self.result('produce')[0]}, response['submitted'])
        self.assertEqual(before + 1, len(self.provider.updates))
        self.assertFalse(self.payload()[1]['operational']['leases'])
        for name in ('review_a', 'review_b'):
            review = self.session.acquire(name, actor='independent-' + name)
            reviewed = self.session.finish(review, {'value': 'reviewed exact candidate'})
        self.assertEqual({'finish'}, self.ready_names(reviewed))
        root = next(step for step in reviewed['next_steps'] if step['kind'] == 'execute')
        self.assertEqual('root', root['assignment'])
        self.assertEqual(response, self.session.call(100, request))
        self.assertEqual(3, len(self.payload()[1]['evidence']))
        self.assertEqual('open', self.provider.issues[100]['state'])

    def test_replay_conflict_and_invalid_actor_or_output_preserve_state(self):
        work = self.session.acquire('produce')
        request = self.session.submission(work, {'value': 'candidate'}, 'exact-continuation')
        for mutation in ({'actor': 'intruder'}, {'outputs': {'wrong': 12}}):
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            self.session.call(100, {**request, **mutation}, expected=2)
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
        response = self.session.call(100, request)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, {**request, 'outputs': {'value': 'changed'}}, expected=2)
        self.assertEqual(response, self.session.call(100, request))
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_uncertain_publication_has_no_success_then_exact_retry(self):
        work = self.session.acquire('produce')
        request = self.session.submission(work, {'value': 'candidate'}, 'uncertain-continuation')
        before = copy.deepcopy(self.provider.issues)
        with mock.patch.object(self.provider, 'update_issue', side_effect=RuntimeError('unavailable')):
            failed = self.session.call(100, request, expected=2)
        self.assertFalse(self.ready_names(failed))
        self.assertEqual(before, self.provider.issues)
        response = self.session.call(100, request)
        self.assertEqual({'review_a', 'review_b'}, self.ready_names(response))
        self.assertEqual(response, self.session.call(100, request))

    def test_legacy_literal_response_receipts_replay_unchanged(self):
        request = {'operation': 'submit', 'request_id': 'legacy-literal'}
        literal = {'next_steps': [{'kind': 'checkpoint', 'goal': 100}]}
        envelope, payload = self.payload()
        payload['operational']['receipts'].append({'request': request['request_id'],
            'payload': content_hash(request), 'result': self.blob(literal)})
        envelope['payload'] = self.blob(payload)
        self.provider.issues[100]['body'] = '<!-- zzzops-goal\n' + json.dumps(envelope) + '\nzzzops-goal -->'
        self.assertEqual(literal, self.session.call(100, request))


class MultipartContinuationTests(DagFixture):
    def setUp(self):
        super().setUp()
    multipart_request = journeys.GenericStoragePublicTests.multipart_request
    leave_partial_upload = journeys.GenericStoragePublicTests.leave_partial_upload

    def test_partial_append_reuses_exact_continuation_and_result(self):
        _work, _values, request = self.multipart_request()
        updates = len(self.provider.updates)
        partial, offset = self.leave_partial_upload(request)
        response = self.session.call(100, request)
        self.assertEqual({'review_a', 'review_b'}, SubmitContinuationTests.ready_names(self, response))
        self.assertEqual(response, self.session.call(100, request))
        self.assertEqual(1, sum(row['body'] == partial['body'] for row in self.provider.comments[100][offset:]))
        self.assertEqual(updates + 1, len(self.provider.updates))
        self.assertEqual(1, len(self.payload()[1]['evidence']))


class PublicationContinuationTests(DagFixture):
    def setUp(self):
        super().setUp()
        self.setup_publication()
    setup_publication = publication.GenericPublicationPublicTests.setup_publication
    provider_command = publication.GenericPublicationPublicTests.provider_command
    configure = publication.GenericPublicationPublicTests.configure
    submit_role = publication.GenericPublicationPublicTests.submit_role
    authorize_context = publication.GenericPublicationPublicTests.authorize_context
    observed_value = publication.GenericPublicationPublicTests.observed_value
    mark_merged = publication.GenericPublicationPublicTests.mark_merged

    def approval_request(self):
        self.authorize_context()
        self.submit_role('observe', self.observed_value())
        self.submit_role('review', 'exact independent review', actor='publication-reviewer')
        work = self.session.acquire(self.ids['approve'])
        return self.session.submission(work, {'value': {'subject': self.produced(self.ids['observe']),
            'review': self.produced(self.ids['review']), 'policy': content_hash(self.session.project['policy']),
            'decision': 'approved'}}, 'publication-continuation')

    def test_publication_approval_returns_integrate_without_effect(self):
        request = self.approval_request()
        response = self.session.call(100, request)
        integration = next(step for step in response['next_steps'] if step['kind'] == 'integrate')
        self.assertEqual(self.observation['head_oid'], integration['submission']['expected_head'])
        self.assertEqual(self.produced(self.ids['approve']), integration['submission']['authorization'])
        self.assertEqual([], self.merge_calls)
        self.assertEqual(response, self.session.call(100, request))

    def test_reconciliation_binds_original_confirmed_envelope_on_replay(self):
        request = self.approval_request()
        self.mark_merged()
        response = self.session.call(100, request)
        reconciliation = next(step for step in response['next_steps'] if step['kind'] == 'reconcile')
        original, _ = self.payload()
        self.assertEqual(content_hash(original), reconciliation['submission']['expected_digest'])
        self.assertIsInstance(reconciliation['submission']['expected_digest'], str)
        self.replace_spec('later unrelated envelope state')
        self.assertEqual(response, self.session.call(100, request))
        self.assertNotEqual(content_hash(self.payload()[0]), reconciliation['submission']['expected_digest'])
        self.assertEqual([], self.merge_calls)


if __name__ == '__main__':
    unittest.main()
