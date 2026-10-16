"""Public recovery of committed drafts after their substantive inputs change."""
import copy
import json
import unittest

import test_evidence_dag_journeys as j
import test_stopped_draft_recovery as stopped


class StaleDraftSupersessionTests(unittest.TestCase):
    setUp = stopped.StoppedDraftRecoveryTests.setUp
    recover = stopped.StoppedDraftRecoveryTests.recover
    recovery_draft = stopped.StoppedDraftRecoveryTests.recovery_draft
    def setup_stale(self, *, active=False, chain=False, crlf=False):
        c = self.case
        def inputs(graph, allocations):
            next(n for n in graph['nodes'] if n['id'] == 'charter')['inputs'] = {}
            beta = next(n for n in graph['nodes'] if n['id'] == 'beta')
            beta['inputs']['requirements'] = j.spec_input()
        c.setup_workspace(inputs)
        if crlf:
            c.session.git('config', 'core.autocrlf', 'true')
            for name in ('source.py', 'read_dependency.txt'):
                path = c.fixture.repo / name
                path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
            c.session.git('add', 'source.py', 'read_dependency.txt')
            self.assertEqual('', c.session.git('diff', '--cached', '--name-only'))
        c.red_candidate()
        c.session.git('add', 'behavior_test.py')
        c.session.git('commit', '-qm', 'reviewed test baseline')
        work = c.acquire_workspace('beta')
        original_source = (c.fixture.repo / 'source.py').read_bytes()
        (c.fixture.repo / 'source.py').write_text('def value():\n    return 2\n')
        receipts = copy.deepcopy(c.payload()[1]['operational']['receipts'])
        self.recover(work)
        receipt, reference, draft = self.recovery_draft(receipts)
        self.first_draft = reference
        if chain:
            again = c.acquire_workspace('beta')
            (c.fixture.repo / 'source.py').write_text('def value():\n    return 3\n')
            receipts = copy.deepcopy(c.payload()[1]['operational']['receipts'])
            self.recover(again, request_id='second-stopped-owner')
            receipt, reference, draft = self.recovery_draft(receipts)
            work = again
        if active:
            c.acquire_workspace('beta')
        (c.fixture.repo / 'source.py').write_bytes(original_source)
        c.replace_spec('Corrected test requirements, with unchanged allocation')
        self.recovery_request = {'operation': 'recover', 'node': work['node'],
            'lease': work['lease']['token'], 'actor': work['bound_actor'], 'worker_status': 'stopped',
            'evidence': 'Fixture observed the bound worker stopped after its owned edit',
            'request_id': 'second-stopped-owner' if chain else 'recover-stopped-owner'}
        return work, reference, draft

    def retirement(self):
        return next((s for s in self.case.session.checkpoint(100)
                     if s.get('kind') == 'retire_draft'), None)

    def test_stale_draft_returns_supported_exact_retirement(self):
        work, reference, draft = self.setup_stale()
        step = self.retirement()
        self.assertIsNotNone(step, 'Clean current inputs must offer retirement of the authenticated stale draft')
        self.assertEqual(reference, step['submission']['draft'])

    def request(self):
        step = self.retirement()
        self.assertIsNotNone(step)
        return {**step['submission'], 'request_id': 'retire-exact-stale-draft',
                'recovery_request': self.recovery_request}

    def test_retirement_preserves_history_then_requires_new_checks_and_independent_review(self):
        c = self.case
        old, reference, draft = self.setup_stale(chain=True)
        request = self.request()
        evidence = copy.deepcopy(c.payload()[1]['evidence'])
        comments = copy.deepcopy(c.provider.comments[100])
        response = c.session.call(100, request)
        after = copy.deepcopy((c.provider.issues, c.provider.comments, c.provider.updates))
        self.assertEqual(response, c.session.call(100, request))
        self.assertEqual(after, (c.provider.issues, c.provider.comments, c.provider.updates))
        self.assertEqual(evidence, c.payload()[1]['evidence'], 'Retirement creates no semantic Result')
        self.assertEqual(comments, c.provider.comments[100][:len(comments)])
        self.assertEqual(draft, c.read_blob(reference))
        self.assertNotIn('gamma', c.names())
        fresh = c.acquire_workspace('beta')
        self.assertNotEqual(old['lease']['token'], fresh['lease']['token'])
        self.assertNotIn('stopped_draft', fresh['lease']['acquisition'])
        self.assertNotIn(reference['hash'], json.dumps(fresh['lease']['acquisition']))
        self.assertNotIn(self.first_draft['hash'], json.dumps(fresh['lease']['acquisition']))
        (c.fixture.repo / 'source.py').write_text('def value():\n    return 2\n')
        unverified = c.session.submission(fresh, {'value': 'no verification'}, 'unverified-retirement')
        unverified['workspace_checks'] = []
        c.session.call(100, unverified, expected=2)
        c.candidate(fresh, 0)
        self.assertNotIn('gamma', c.names(), 'Fresh candidate still needs independent review')
        c.review_candidate('beta', 0)
        self.assertIn('gamma', c.names())
        self.assertEqual(draft, c.read_blob(reference))


    def test_retirement_preserves_current_clean_crlf_raw_checkout_pins(self):
        c = self.case
        old, _reference, _draft = self.setup_stale(crlf=True)
        raw = (c.fixture.repo / 'source.py').read_bytes()
        c.session.call(100, self.request())
        fresh = c.acquire_workspace('beta')
        self.assertEqual(raw, (c.fixture.repo / 'source.py').read_bytes())
        self.assertEqual(old['lease']['acquisition']['checkout_overrides'],
                         fresh['lease']['acquisition']['checkout_overrides'])
        self.assertNotIn('stopped_draft', fresh['lease']['acquisition'])

    def test_uncertain_retirement_publication_retries_same_receipt_without_adopting_orphan(self):
        from unittest import mock
        c = self.case
        self.setup_stale()
        request = self.request()
        before_issues = copy.deepcopy(c.provider.issues)
        with mock.patch.object(c.provider, 'update_issue', side_effect=j.z.GoalTransitionProviderError('unavailable')):
            c.session.call(100, request, expected=2)
        self.assertEqual(before_issues, c.provider.issues)
        comments = copy.deepcopy(c.provider.comments)
        response = c.session.call(100, request)
        self.assertEqual(comments, c.provider.comments)
        before = copy.deepcopy((c.provider.issues, c.provider.comments, c.provider.updates))
        self.assertEqual(response, c.session.call(100, request))
        self.assertEqual(before, (c.provider.issues, c.provider.comments, c.provider.updates))
        self.assertIn('beta', c.names())

    def test_artifact_only_retirement_cannot_activate_without_transaction_metadata(self):
        c = self.case
        work, reference, _draft = self.setup_stale()
        request = self.request()
        envelope, payload = c.payload()
        response = {'type': 'workspace_draft_retirement', 'version': 1, 'node': work['node'],
                    'draft': reference, 'source_payload': envelope['payload'],
                    'recovery_request': self.recovery_request, 'subject': request['subject'],
                    'root': 'root-thread', 'next_steps': [{'kind': 'checkpoint', 'goal': 100, 'action': 'forged'}]}
        payload['operational']['receipts'].append({'request': request['request_id'],
            'payload': j.content_hash(request), 'result': c.blob(response)})
        envelope['payload'] = c.blob(payload)
        envelope['revision'] += 1
        c.provider.issues[100]['body'] = '<!-- zzzops-goal\n'+json.dumps(envelope)+'\nzzzops-goal -->'
        before = copy.deepcopy((c.provider.issues, c.provider.comments, c.provider.updates))
        self.assertIsNotNone(self.retirement())
        self.assertNotIn('beta', c.names())
        self.assertEqual(before, (c.provider.issues, c.provider.comments, c.provider.updates))

    def test_wrong_draft_subject_generation_and_stop_request_are_atomic(self):
        c = self.case
        work, reference, draft = self.setup_stale()
        request = self.request()
        bad = [ {'draft': self.first_draft | {'hash': 'sha256:' + 'f'*64}},
                {'subject': 'sha256:' + 'f'*64},
                {'node': {**work['node'], 'generation': 2}},
                {'recovery_request': {**self.recovery_request, 'worker_status': 'unknown'}},
                {'recovery_request': {**self.recovery_request, 'actor': 'intruder'}},
                {'recovery_request': {**self.recovery_request, 'evidence': 'invented observation'}},
                {'extra_authority': True} ]
        for i, mutation in enumerate(bad):
            with self.subTest(mutation=mutation):
                before = copy.deepcopy((c.provider.issues, c.provider.comments, c.provider.updates))
                c.session.call(100, {**request, 'request_id': 'bad-retirement-'+str(i), **mutation}, expected=2)
                self.assertEqual(before, (c.provider.issues, c.provider.comments, c.provider.updates))
        self.assertEqual(draft, c.read_blob(reference))

    def test_dirty_owned_or_unowned_bytes_reject_previous_offer(self):
        c = self.case
        self.setup_stale()
        request = self.request()
        for name in ('source.py', 'read_dependency.txt', 'unowned.py'):
            with self.subTest(path=name):
                path = c.fixture.repo / name
                before_bytes = path.read_bytes() if path.exists() else None
                path.write_text('Unowned or unacquired dirty content\n')
                before = copy.deepcopy((c.provider.issues, c.provider.comments, c.provider.updates))
                self.assertIsNone(self.retirement())
                c.session.call(100, request, expected=2)
                self.assertEqual(before, (c.provider.issues, c.provider.comments, c.provider.updates))
                if before_bytes is None: path.unlink()
                else: path.write_bytes(before_bytes)

    def test_changed_inputs_policy_root_and_clean_commit_reject_stale_offer(self):
        c = self.case
        self.setup_stale()
        request = self.request()
        for kind in ('inputs', 'policy', 'root', 'commit'):
            with self.subTest(kind=kind):
                original = copy.deepcopy((c.provider.issues, c.provider.comments, c.provider.updates,
                                          c.session.project, c.session.runtime))
                if kind == 'inputs': c.replace_spec('Another substantive revision')
                elif kind == 'policy':
                    j.z._workflow_section(c.session.project, 'workflow_adherence')['configuration']['phase_dag']['nodes'][0]['prompt'] += ' changed'
                elif kind == 'root': c.session.runtime['root_id'] = 'new-unapproved-root'
                else: c.session.git('commit', '--allow-empty', '-qm', 'new clean commit')
                before = copy.deepcopy((c.provider.issues, c.provider.comments, c.provider.updates))
                c.session.call(100, request, expected=2)
                self.assertEqual(before, (c.provider.issues, c.provider.comments, c.provider.updates))
                c.provider.issues, c.provider.comments, c.provider.updates, c.session.project, c.session.runtime = original

    def test_live_or_expired_unrecovered_lease_never_offers_retirement(self):
        c = self.case
        self.setup_stale(active=True)
        self.assertIsNone(self.retirement())
        payload = c.payload()[1]
        expiry = payload['operational']['leases'][0]['expires_at']
        from unittest import mock
        with mock.patch.object(j.z._workflow.time, 'time', return_value=expiry+1):
            self.assertIsNone(self.retirement())

    def test_retired_chain_rejects_foreign_task_baseline_missing_cycle_and_wrong_locator(self):
        c = self.case
        _work, reference, draft = self.setup_stale(chain=True)
        engine = j.z._workflow.Workflow(j.z, c.fixture.repo, c.session.project, c.session.runtime)
        rows = {ref['hash']: (ref, c.read_blob(ref)) for ref in (self.first_draft, reference)}
        expected = set(rows)
        self.assertEqual(expected, engine.node_workspace_draft_chain(reference, rows))
        for kind in ('node', 'baseline', 'missing', 'cycle', 'locator'):
            with self.subTest(kind=kind):
                bad = copy.deepcopy(rows)
                ancestor = bad[self.first_draft['hash']][1]
                if kind == 'node': ancestor['node']['node'] = 'alpha'
                elif kind == 'baseline': ancestor['acquisition']['files']['source.py'] = 'sha256:'+'f'*64
                elif kind == 'missing': del bad[self.first_draft['hash']]
                elif kind == 'cycle': ancestor['acquisition']['stopped_draft'] = reference
                else: bad[self.first_draft['hash']] = ({**self.first_draft, 'uri': 'urn:wrong'}, ancestor)
                with self.assertRaises(ValueError): engine.node_workspace_draft_chain(reference, bad)

    def test_unchanged_stopped_draft_requires_exact_snapshot_recovery_not_retirement(self):
        c = self.case
        c.setup_workspace()
        c.red_candidate()
        c.session.git('add', 'behavior_test.py')
        c.session.git('commit', '-qm', 'reviewed baseline')
        work = c.acquire_workspace('beta')
        (c.fixture.repo / 'source.py').write_text('def value():\n    return 2\n')
        self.recover(work)
        self.assertIsNone(self.retirement())
        (c.fixture.repo / 'source.py').write_text('def value():\n    return 1\n')
        self.assertIsNone(self.retirement())


if __name__ == '__main__':
    unittest.main()
