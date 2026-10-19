"""Bounded public regressions for retained checkpoint retirement refreshes."""
import copy
import json
from pathlib import Path
import unittest
from unittest import mock

import test_evidence_dag_journeys as journeys

z = journeys.z


class CheckpointRefreshTests(journeys.DagFixture):
    administrative_review = journeys.GraphAdoptionPublicTests.administrative_review

    def stale_checkpoint(self):
        self.produce()
        ready = next(step for step in self.session.ready() if step['node']['node'] == 'review_a')
        receipt = json.loads(Path(ready['policy']['path']).read_text())['policy_receipt']
        request = {**ready['start'], 'policy_receipt': receipt, 'request_id': 'lost-start'}
        with mock.patch.object(self.provider, 'update_issue', side_effect=RuntimeError('provider unavailable')):
            self.session.call(100, request, expected=2)
        return next(z._comment_store.decode_envelope(row['body'])['transaction']
                    for row in self.provider.comments[100]
                    if (z._comment_store.decode_envelope(row['body']) or {}).get('context', {}).get('request_id') == 'lost-start')

    def prepare(self, transaction):
        return self.session.call(100, {'operation': 'checkpoint_reconcile_prepare',
            'transaction': transaction, 'rationale': 'Retire only this exact abandoned mutation.',
            'request_id': 'prepare-retirement'})['next_steps'][0]

    def review(self, prepared, *, request_id=None):
        request = {**prepared['submission'], 'actor': 'independent-reviewer',
                   'decision': 'approved', 'report': 'The exact abandoned checkpoint has no semantic authority.'}
        if request_id is not None:
            request['request_id'] = request_id
        return self.administrative_review(request)['next_steps'][0]

    def adopt(self, reviewed):
        request = {**reviewed['submission'], 'approved_by': 'user: approved exact retirement'}
        response = self.session.call(100, request)
        self.assertEqual(response, self.session.call(100, request), 'Frozen exact retries remain idempotent')
        return request

    def assert_reconciled(self, transaction, expected=True):
        engine = z.workflow_engine(self.fixture.repo, self.session.project, self.session.runtime)
        snapshot = engine.node_snapshot(100)
        index = engine.artifact_index(100)
        row = next(row for row in index.envelopes if row.get('transaction') == transaction)
        receipts = snapshot['payload']['operational']['receipts']
        self.assertEqual(expected, engine.node_checkpoint_reconciled(snapshot, index, row, receipts))
        self.assertEqual(expected, engine.node_checkpoint_reconciled(snapshot, index, row, list(reversed(receipts))),
                         'Receipt array order does not establish lineage')
        return engine, snapshot, index, row

    def test_refresh_contract_ids_follow_exact_binding(self):
        transaction = self.stale_checkpoint()
        first = self.prepare(transaction)
        reviewed = self.review(first)
        self.adopt(reviewed)
        refreshed = self.prepare(transaction)
        self.assertNotEqual(first['submission']['request_id'], refreshed['submission']['request_id'])
        next_review = self.review(refreshed)
        self.assertNotEqual(reviewed['submission']['request_id'], next_review['submission']['request_id'])
        self.adopt(next_review)
        self.assert_reconciled(transaction)

    def refresh_pair(self, *, stale):
        transaction = self.stale_checkpoint()
        first_review = self.review(self.prepare(transaction), request_id='first-review')
        self.adopt(first_review)
        self.assert_reconciled(transaction)
        old_comments = copy.deepcopy(self.provider.comments[100])
        old_receipts = copy.deepcopy(self.payload()[1]['operational']['receipts'])
        old_evidence = copy.deepcopy(self.payload()[1]['evidence'])
        if stale:
            self.provider.create_issue_comment(100, 'A legitimate human note after the first retirement.')
            self.assert_reconciled(transaction, False)
        second_review = self.review(self.prepare(transaction), request_id='second-review')
        second_review = copy.deepcopy(second_review)
        second_review['submission']['request_id'] = 'second-adoption'
        self.adopt(second_review)
        engine, snapshot, index, row = self.assert_reconciled(transaction)
        pins = []
        descriptor = engine.node_checkpoint_descriptor(snapshot, transaction)
        for receipt in snapshot['payload']['operational']['receipts']:
            response = index.resolve(receipt['result']['hash'])[0]
            if isinstance(response, dict) and response.get('type') == 'checkpoint_reconciliation':
                pins.append(engine.node_checkpoint_reconciliation_pin(snapshot, index, descriptor,
                    snapshot['payload']['operational']['receipts'], receipt, response))
        self.assertEqual(2, len(pins))
        self.assertEqual([False, True] if stale else [True, True], [pin is not None for pin in pins])
        self.assertEqual(old_comments, self.provider.comments[100][:len(old_comments)])
        self.assertEqual(old_receipts, snapshot['payload']['operational']['receipts'][:len(old_receipts)])
        self.assertEqual(old_evidence, snapshot['payload']['evidence'])
        frontier = self.session.checkpoint(100)
        executable = next(step for step in frontier if step.get('kind') == 'execute'
                          and step.get('node', {}).get('node') == 'review_a')
        work = self.session.acquire('review_a')
        self.assertEqual(executable['input_hash'], work['start']['input_hash'])
        release = {'operation': 'release', 'node': work['node'], 'lease': work['lease']['token'],
                   'actor': work['bound_actor'], 'request_id': 'release-after-refresh'}
        self.assertEqual('released', self.session.call(100, release)['next_steps'][0]['kind'])
        return self.assert_reconciled(transaction)

    def test_valid_successor_retires_stale_pin_without_history_loss(self):
        self.refresh_pair(stale=True)

    def test_comparable_valid_pins_select_latest_authenticated_successor(self):
        self.refresh_pair(stale=False)

    def test_fixed_policy_acquisition_contract_follows_current_binding(self):
        self.produce()
        first = self.session.acquire('review_a')
        first_input = first['start']['input_hash']
        release = {'operation': 'release', 'node': first['node'], 'lease': first['lease']['token'],
                   'actor': first['bound_actor'], 'request_id': 'release-first-fixed-policy-binding'}
        self.session.call(100, release)
        second = self.session.acquire('review_a')
        self.assertEqual(first['input_envelope']['contract'], second['input_envelope']['contract'])
        self.assertEqual(first_input, second['start']['input_hash'])
        self.assertNotEqual(first['lease']['token'], second['lease']['token'])

    def test_public_rejection_guards_and_unchanged_payload_retry(self):
        transaction = self.stale_checkpoint()
        prepared = self.prepare(transaction)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        bad = {**prepared['submission'], 'actor': self.session.runtime['root_id'],
               'decision': 'approved', 'report': 'Root cannot independently review itself.'}
        self.administrative_review(bad, expected=2)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        reviewed = self.review(prepared)
        self.session.call(100, {**reviewed['submission'], 'approved_by': ''}, expected=2)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.provider.create_issue_comment(100, 'Review has become stale.')
        self.session.call(100, {**reviewed['submission'], 'approved_by': 'user: approved exact retirement'}, expected=2)
        self.provider.issues, self.provider.comments = copy.deepcopy(before)
        request = self.adopt(reviewed)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, {**request, 'approved_by': 'user: different approved bytes'}, expected=2)
        self.assertRegex(json.dumps(response), r'(?i)payload.*conflict|request.*conflict')
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.acquire('review_a')
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, {'operation': 'checkpoint_reconcile_prepare', 'transaction': transaction,
            'rationale': 'Cannot cross active ownership.', 'request_id': 'active-prepare'}, expected=2)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_failed_provider_confirmation_preserves_history_and_exact_retry(self):
        transaction = self.stale_checkpoint()
        reviewed = self.review(self.prepare(transaction))
        request = {**reviewed['submission'], 'approved_by': 'user: approved exact retirement'}
        old = copy.deepcopy(self.provider.comments[100])
        with mock.patch.object(self.provider, 'update_issue', side_effect=RuntimeError('provider unavailable')):
            self.session.call(100, request, expected=2)
        self.assert_reconciled(transaction, False)
        self.assertEqual(old, self.provider.comments[100][:len(old)])
        response = self.session.call(100, request)
        self.assertEqual(response, self.session.call(100, request))
        self.assert_reconciled(transaction)

    def test_unconfirmed_provider_update_grants_no_retirement(self):
        transaction = self.stale_checkpoint()
        reviewed = self.review(self.prepare(transaction))
        request = {**reviewed['submission'], 'approved_by': 'user: approved exact retirement'}
        old_envelope, old_payload = self.payload()
        with mock.patch.object(self.provider, 'update_issue', side_effect=lambda number, body: copy.deepcopy(self.provider.issues[number])):
            self.session.call(100, request, expected=2)
        envelope, payload = self.payload()
        self.assertEqual(old_envelope, envelope)
        self.assertEqual(old_payload, payload)
        self.assert_reconciled(transaction, False)
        # New bytes under the pending request cannot claim the frozen retry.
        self.session.call(100, {**request, 'approved_by': 'user: changed scope'}, expected=2)
        self.session.call(100, request)
        self.assert_reconciled(transaction)

    def test_conflicting_suffix_gap_and_changed_provider_bytes_fail_closed(self):
        engine, snapshot, index, row = self.refresh_pair(stale=False)
        receipts = snapshot['payload']['operational']['receipts']
        gap = copy.deepcopy(snapshot)
        gap['envelope']['revision'] += 1
        self.assertFalse(engine.node_checkpoint_reconciled(gap, index, row, receipts))
        self.assertFalse(engine.node_checkpoint_reconciled(snapshot, index, row, receipts + [receipts[-1]]))
        comments = copy.deepcopy(self.provider.comments[100])
        descriptor = engine.node_checkpoint_descriptor(snapshot, row['transaction'])
        selected_id = descriptor['provider'][0]['id']
        try:
            comment = next(comment for comment in self.provider.comments[100] if comment['id'] == selected_id)
            decoded = z._comment_store.decode_envelope(comment['body'])
            decoded['context']['source_hash'] = 'sha256:' + 'e' * 64
            comment['body'] = z._comment_store.encode_envelope(decoded)
            engine.invalidate()
            altered_index = engine.artifact_index(100)
            self.assertFalse(engine.node_checkpoint_reconciled(snapshot, altered_index, row, receipts))
        finally:
            self.provider.comments[100] = comments
            engine.invalidate()
        # A second authenticated receipt-shaped child cannot be silently ignored.
        adoption = engine.node_receipt_edge(100, index, receipts[-1])
        context = copy.deepcopy(adoption['context'])
        context.update(request_id='conflicting-fork', request_hash='sha256:' + 'a' * 64,
                       source_envelope=snapshot['envelope'],
                       target_envelope={**snapshot['envelope'], 'revision': snapshot['envelope']['revision'] + 1,
                                        'parent': {'goal': 999}})
        response = {'next_steps': [], 'kind': 'conflicting-child'}
        record = z._comment_store.ArtifactIndex([]).record(response)
        ref = engine.node_ref(record['hash'], 100)
        context['response'] = ref
        body = z._comment_store.pack_envelopes({'goal': 100, 'transaction': 'sha256:' + 'b' * 64,
                                               'context': context}, [record])[0]
        self.provider.create_issue_comment(100, body)
        fork_index = z._comment_store.ArtifactIndex(self.provider.comments[100])
        fork_receipt = {'request': context['request_id'], 'payload': context['request_hash'], 'result': ref}
        self.assertIsNotNone(engine.node_receipt_edge(100, fork_index, fork_receipt))
        self.assertFalse(engine.node_checkpoint_reconciled(snapshot, fork_index, row, receipts + [fork_receipt]))

    def test_public_adoption_rejects_forged_review_owner(self):
        transaction = self.stale_checkpoint()
        reviewed = self.review(self.prepare(transaction))
        engine = z.workflow_engine(self.fixture.repo, self.session.project, self.session.runtime)
        snapshot = engine.node_snapshot(100)
        review_receipt = snapshot['payload']['operational']['receipts'][-1]
        changed = 0
        for comment in self.provider.comments[100]:
            decoded = z._comment_store.decode_envelope(comment['body'])
            if decoded and (decoded.get('context') or {}).get('response') == review_receipt['result']:
                decoded['context']['root'] = 'forged-review-owner'
                comment['body'] = z._comment_store.encode_envelope(decoded)
                changed += 1
        self.assertGreater(changed, 0)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, {**reviewed['submission'],
            'approved_by': 'user: approved exact retirement'}, expected=2)
        self.assertRegex(json.dumps(response), r'(?i)review|root|owner|authenticated')
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_each_pin_rejects_exact_forged_metadata(self):
        transaction = self.stale_checkpoint()
        self.adopt(self.review(self.prepare(transaction)))
        engine, snapshot, index, row = self.assert_reconciled(transaction)
        receipts = snapshot['payload']['operational']['receipts']
        adoption = receipts[-1]
        response = index.resolve(adoption['result']['hash'])[0]
        proposal = index.resolve(response['proposal']['hash'])[0]
        review = index.resolve(response['review']['hash'])[0]
        original_comments = copy.deepcopy(self.provider.comments[100])

        def forge(change):
            forged_proposal, forged_review, forged_response = copy.deepcopy((proposal, review, response))
            change(forged_proposal, forged_review, forged_response)
            bad_uri = forged_response.pop('_bad_uri', False)
            bad_context_root = forged_response.pop('_bad_context_root', False)
            bad_review_root = forged_response.pop('_bad_review_root', False)
            materializer = z._comment_store.ArtifactIndex([])
            proposal_ref = engine.node_ref(journeys.content_hash(forged_proposal), 100)
            if bad_uri:
                proposal_ref['uri'] = proposal_ref['uri'].replace('goal:100:', 'goal:999:')
            forged_review['provenance']['source'] = proposal_ref
            review_ref = engine.node_ref(journeys.content_hash(forged_review), 100)
            forged_response['proposal'], forged_response['review'] = proposal_ref, review_ref
            forged_receipts = copy.deepcopy(receipts)
            comments = copy.deepcopy(original_comments)
            for receipt in forged_receipts[-2:]:
                value = index.resolve(receipt['result']['hash'])[0]
                if receipt['request'] == adoption['request']:
                    replacement = forged_response
                else:
                    replacement = copy.deepcopy(value)
                    replacement['next_steps'][0]['proposal'] = proposal_ref
                    replacement['next_steps'][0]['review'] = review_ref
                result_ref = engine.node_ref(journeys.content_hash(replacement), 100)
                for comment in comments:
                    decoded = z._comment_store.decode_envelope(comment['body'])
                    if decoded and (decoded.get('context') or {}).get('response') == receipt['result']:
                        context = {**decoded['context'], 'response': result_ref}
                        if bad_review_root and receipt['request'] != adoption['request']:
                            context['root'] = 'different-root'
                        if bad_context_root and receipt['request'] == adoption['request']:
                            context['root'] = 'different-root'
                        additions = [materializer.record(v) for v in (forged_proposal, forged_review, replacement)]
                        records = [record for record in decoded['artifacts']
                                   if record['hash'] not in {item['hash'] for item in additions}] + additions
                        bodies = z._comment_store.pack_envelopes(
                            {'goal': 100, 'transaction': decoded['transaction'], 'context': context}, records,
                            decoded['history'])
                        self.assertEqual(1, len(bodies))
                        comment['body'] = bodies[0]
                receipt['result'] = result_ref
            self.provider.comments[100] = comments
            forged_index = z._comment_store.ArtifactIndex(comments)
            # Real immutable records authenticate their content hashes; the
            # altered evidence is not supplied through a mocked resolver.
            self.assertEqual(forged_proposal, forged_index.resolve(proposal_ref['hash'])[0])
            return engine.node_checkpoint_reconciled(snapshot, forged_index, row, forged_receipts)

        controls = {
            'unchanged': (lambda p, r, a: None, True),
            'reference_uri': (lambda p, r, a: a.update(_bad_uri=True), False),
            'adoption_root': (lambda p, r, a: a.update(_bad_context_root=True), False),
            'review_root': (lambda p, r, a: a.update(_bad_review_root=True), False),
            'repository': (lambda p, r, a: p['content'].update(repository='other/repo'), False),
            'goal': (lambda p, r, a: p['content'].update(goal=999), False),
            'proposal_policy': (lambda p, r, a: p['content'].update(policy='sha256:' + 'f' * 64), False),
            'proposal_provenance_policy': (lambda p, r, a: p['provenance'].update(policy='sha256:' + 'f' * 64), False),
            'review_policy': (lambda p, r, a: r['provenance'].update(policy='sha256:' + 'f' * 64), False),
            'root_actor': (lambda p, r, a: p['provenance'].update(actor='different-root'), False),
            'non_independent': (lambda p, r, a: r['provenance'].update(actor=self.session.runtime['root_id']), False),
            'approval': (lambda p, r, a: a.update(approved_by=''), False),
            'descriptor': (lambda p, r, a: a['checkpoint'].update(context_hash='sha256:' + 'f' * 64), False),
        }
        try:
            for name, (change, expected) in controls.items():
                with self.subTest(name=name):
                    self.assertEqual(expected, forge(change))
        finally:
            self.provider.comments[100] = original_comments


if __name__ == '__main__':
    unittest.main()
