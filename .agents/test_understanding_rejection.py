"""Understanding rejection and revision through the public workflow dispatcher."""
import copy
import json
import unittest

import test_evidence_dag_journeys as j


class UnderstandingRejectionTests(j.DagFixture):
    def setup_design(self, graph=None):
        if graph is None:
            template = json.loads((j.old.fixtures.PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
            graph = j.z._workflow_section(template, 'workflow_adherence')['configuration']['phase_dag']
        self.install(graph)
        self.allocation = {'allocations': {name: {
            'task': {'goal': 100, 'node': name, 'item': None, 'generation': 1},
            'owned': ['behavior_test.py' if name == 'test_design' else 'source.py'],
            'consumed': ['product.txt'],
        } for name in ('test_design', 'implement')}}
        self.session.finish(self.session.acquire('understand'),
                            {'design': 'Original design', 'allocation': self.allocation})

    def permit(self):
        return {'manifest': self.produced('understand', 'allocation'),
                'tasks': [row['task'] for row in self.allocation['allocations'].values()],
                'policy': j.content_hash(self.session.project['policy']), 'decision': 'approved'}

    def reject(self):
        self.session.finish(self.session.acquire('review_understanding'), {
            'review': {'decision': 'changes_requested', 'report': 'Revise private-access design and allocation'},
            'authorization': None})

    def admit(self):
        subject = self.produced('understand', 'design')
        self.session.finish(self.session.acquire('interpret_understand_rejection'), {'value': {
            'id': 'private_access', 'revision': 1, 'source': self.produced('review_understanding', 'review'),
            'subjects': [subject, self.produced('understand', 'allocation')],
            'target': j.scope('understand', 'design'), 'request': 'Revise design and finite allocation',
            'rationale': 'Exact independent review rejected both artifacts', 'supersedes': None}})
        self.finding = self.produced('interpret_understand_rejection')
        self.session.finish(self.session.acquire('admit_understand_correction'), {'value': {
            'finding': self.finding, 'target_inputs': self.result('understand')[1]['inputs'],
            'authority': self.result('interpret_understand_rejection')[0],
            'applicability': 'applicable', 'rationale': 'Planning only; no workspace authority'}})

    def resolve(self):
        self.session.finish(self.session.acquire('retain_understand_findings'), {'value': {
            'items': {'private_access': self.finding}, 'rationale': 'Retain the rejected design finding'}})
        self.session.finish(self.session.acquire('resolve_understand_finding', item='private_access'), {'value': {
            'finding': self.finding, 'subjects': [self.produced('understand', 'design')],
            'reviewer_result': self.result('review_understanding')[0], 'decision': 'resolved',
            'rationale': 'Fresh exact-design independent review covers the correction'}})

    def test_rejection_revision_independent_review_then_fresh_human_approval(self):
        self.setup_design()
        original = self.result('understand')[0]
        old_design = self.produced('understand', 'design')
        old_allocation = self.produced('understand', 'allocation')
        self.reject()
        rejected = self.result('review_understanding')[0]
        self.assertIsNone(self.read_blob(self.produced('review_understanding', 'authorization'))['content'])
        self.assertNotIn('approve_understanding', self.names())
        self.assertNotIn('test_design', self.names())
        self.admit()
        self.assertIn('understand', self.names())
        self.allocation['allocations']['implement']['owned'] = ['revised_source.py']
        self.session.finish(self.session.acquire('understand'), {
            'design': 'Revised private-access design', 'allocation': self.allocation})
        self.assertNotEqual(old_design, self.produced('understand', 'design'))
        self.assertNotEqual(old_allocation, self.produced('understand', 'allocation'))
        review = self.session.acquire('review_understanding')
        inputs = {row['name']: row['source'] for row in review['input_envelope']['inputs']}
        self.assertEqual(self.produced('understand', 'design'), inputs['design'])
        self.assertEqual(self.produced('understand', 'allocation'), inputs['allocation'])
        self.session.finish(review, {'review': {'decision': 'approved', 'report': 'Revised exact pair accepted'},
                                     'authorization': self.permit()})
        self.resolve()
        self.assertNotIn('decompose', self.names())
        self.assertNotIn('test_design', self.names())
        self.session.finish(self.session.acquire('approve_understanding'), {'authorization': self.permit()})
        self.assertIn('decompose', self.names())
        for ref in (original, old_design, old_allocation, rejected, self.finding):
            self.read_blob(ref)


    def test_contradictory_authorization_is_rejected_without_provider_mutation(self):
        self.setup_design()
        review = self.session.acquire('review_understanding')
        for decision, authorization in [('changes_requested', self.permit()), ('approved', None)]:
            with self.subTest(decision=decision):
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                request = self.session.submission(review, {
                    'review': {'decision': decision, 'report': 'Contradictory candidate'},
                    'authorization': authorization}, 'contradiction-' + decision)
                response = self.session.call(100, request, expected=2)
                self.assertRegex(json.dumps(response), r'(?i)rejected review|authorization')
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(review, {'review': {'decision': 'changes_requested', 'report': 'Honest rejection'},
                                     'authorization': None})
        self.assertNotIn('approve_understanding', self.names())

    def test_legacy_review_contract_accepts_rejection_without_granting_authority(self):
        template = json.loads((j.old.fixtures.PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        graph = j.z._workflow_section(template, 'workflow_adherence')['configuration']['phase_dag']
        review_contract = next(node for node in graph['nodes'] if node['id'] == 'review_understanding')
        review_contract['outputs']['authorization']['schema'] = \
            review_contract['outputs']['authorization']['schema']['variants'][0]
        self.setup_design(graph)
        review = self.session.acquire('review_understanding')
        self.session.finish(review, {
            'review': {'decision': 'changes_requested', 'report': 'Legacy graph still permits honest rejection'},
            'authorization': None})
        self.assertIsNone(self.read_blob(self.produced('review_understanding', 'authorization'))['content'])
        self.assertNotIn('approve_understanding', self.names())
        self.assertNotIn('test_design', self.names())

        self.setup_design(graph)
        review = self.session.acquire('review_understanding')
        request = self.session.submission(review, {
            'review': {'decision': 'approved', 'report': 'Approval still needs exact authority'},
            'authorization': None}, 'legacy-approved-without-authority')
        response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r'(?i)authorization')

    def test_design_revision_invalidates_prior_human_approval_and_downstream_results(self):
        template = json.loads((j.old.fixtures.PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        graph = j.z._workflow_section(template, 'workflow_adherence')['configuration']['phase_dag']
        # A later scoped audit demonstrates invalidation after an earlier human approval.
        audit = copy.deepcopy(next(n for n in graph['nodes'] if n['id'] == 'interpret_understand_rejection'))
        audit['id'] = 'audit_understanding'
        audit['executor']['authority']['subject']['node'] = audit['id']
        audit['inputs'].pop('rejected')
        admission = copy.deepcopy(next(n for n in graph['nodes'] if n['id'] == 'admit_understand_correction'))
        admission['id'] = 'admit_audit'
        admission['executor']['authority']['subject']['node'] = admission['id']
        admission['inputs']['finding']['producer']['node']['node'] = audit['id']
        admission['requires'][0]['node'] = audit['id']
        graph['nodes'].extend([audit, admission])
        self.setup_design(graph)
        self.session.finish(self.session.acquire('review_understanding'), {
            'review': {'decision': 'approved', 'report': 'Initial exact design accepted'}, 'authorization': self.permit()})
        self.session.finish(self.session.acquire('retain_understand_findings'), {
            'value': {'items': {}, 'rationale': 'No findings yet'}})
        approval = self.session.acquire('approve_understanding')
        old_start = copy.deepcopy(approval['start'])
        old_start['policy_receipt'] = json.loads(j.Path(approval['policy']['path']).read_text())['policy_receipt']
        old_submission = self.session.submission(approval, {'authorization': self.permit()}, 'original-human-consent')
        self.session.call(100, old_submission)
        old_approval = self.result('approve_understanding')[0]
        self.session.finish(self.session.acquire('decompose'), {'value': 'Original settled decomposition'})
        old_downstream = self.result('decompose')[0]
        original_evidence = copy.deepcopy(self.payload()[1]['evidence'])
        self.session.finish(self.session.acquire(audit['id']), {'value': {
            'id': 'later_audit', 'revision': 1, 'source': self.produced('review_understanding', 'review'),
            'subjects': [self.produced('understand', 'design'), self.produced('understand', 'allocation')],
            'target': j.scope('understand', 'design'), 'request': 'Revise after later scoped audit',
            'rationale': 'New reviewed planning constraint', 'supersedes': None}})
        finding = self.produced(audit['id'])
        self.session.finish(self.session.acquire(admission['id']), {'value': {
            'finding': finding, 'target_inputs': self.result('understand')[1]['inputs'],
            'authority': self.result(audit['id'])[0], 'applicability': 'applicable', 'rationale': 'Planning only'}})
        self.assertIn('understand', self.names())
        self.assertNotIn('review_decomposition', self.names())
        self.assertNotIn('test_design', self.names())
        self.session.finish(self.session.acquire('understand'), {
            'design': 'Revised design; same logical allocation still needs new exact consent', 'allocation': self.allocation})
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        old_start['request_id'] = 'stale-human-start'
        self.session.call(100, old_start, expected=2)
        old_submission['request_id'] = 'stale-human-submit'
        self.session.call(100, old_submission, expected=2)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(self.session.acquire('review_understanding'), {
            'review': {'decision': 'approved', 'report': 'Revised exact artifacts approved'}, 'authorization': self.permit()})
        self.session.finish(self.session.acquire('retain_understand_findings'), {'value': {
            'items': {'later_audit': finding}, 'rationale': 'Retain the later audit'}})
        self.session.finish(self.session.acquire('resolve_understand_finding', item='later_audit'), {'value': {
            'finding': finding, 'subjects': [self.produced('understand', 'design')],
            'reviewer_result': self.result('review_understanding')[0], 'decision': 'resolved', 'rationale': 'Verified'}})
        self.assertIn('approve_understanding', self.names())
        self.assertNotIn('decompose', self.names())
        self.assertNotIn('test_design', self.names())
        fresh = self.session.acquire('approve_understanding')
        self.assertNotEqual(approval['input_hash'], fresh['input_hash'])
        self.session.finish(fresh, {'authorization': self.permit()})
        self.assertIn('decompose', self.names())
        self.assertNotIn('review_decomposition', self.names(), 'Old downstream Result is historical, not current')
        self.assertNotIn('implement', self.names())
        self.assertTrue(all(ref in self.payload()[1]['evidence'] for ref in original_evidence))
        for ref in (old_approval, old_downstream): self.read_blob(ref)

    add_goal = j.GraphAdoptionPublicTests.add_goal
    put_envelope = j.GraphAdoptionPublicTests.put_envelope
    envelope_for = j.GraphAdoptionPublicTests.envelope_for
    read_at = j.GraphAdoptionPublicTests.read_at
    result_at = j.GraphAdoptionPublicTests.result_at
    proposal_review = j.GraphAdoptionPublicTests.proposal_review

    def test_existing_goal_adopts_repaired_graph_without_rewriting_design_or_policy(self):
        template = json.loads((j.old.fixtures.PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        repaired = j.z._workflow_section(template, 'workflow_adherence')['configuration']['phase_dag']
        # Origen's persisted graph predates the other default correction paths:
        # preserve its original sixteen nodes and append only this repair.
        repair_ids = {'interpret_understand_rejection', 'admit_understand_correction',
                      'retain_understand_findings'}
        repaired['nodes'] = repaired['nodes'][:16] + [
            n for n in repaired['nodes'] if n['id'] in repair_ids]
        repaired['task_sets'] = [t for t in repaired['task_sets'] if t['id'] == 'understand_findings']
        for node in repaired['nodes'][:16]:
            if node['id'] != 'decompose':
                node['requires'] = [r for r in node['requires'] if r.get('kind') != 'join']
                node['gates'] = []
        original = copy.deepcopy(repaired)
        original['nodes'] = [n for n in original['nodes'] if n['id'] not in {
            'interpret_understand_rejection', 'admit_understand_correction', 'retain_understand_findings'}]
        original['task_sets'] = [t for t in original['task_sets'] if t['id'] != 'understand_findings']
        review = next(n for n in original['nodes'] if n['id'] == 'review_understanding')
        review['outputs']['authorization']['schema'] = review['outputs']['authorization']['schema']['variants'][0]
        decompose = next(n for n in original['nodes'] if n['id'] == 'decompose')
        decompose['requires'] = [r for r in decompose['requires'] if r.get('expansion') != 'understand_findings']
        decompose['gates'] = []
        self.setup_design(original)
        design_result = self.result('understand')[0]
        history = copy.deepcopy(self.payload()[1]['evidence'])
        policy = copy.deepcopy(self.session.project['policy'])
        proposal = self.session.call(100, {'operation': 'graph_prepare', 'graph': repaired,
                                         'rationale': 'Repair rejected understanding without losing current design'})
        request = self.proposal_review(proposal['next_steps'][0]['proposal'])
        self.session.call(100, request)
        self.assertEqual(policy, self.session.project['policy'])
        self.assertEqual(history, self.payload()[1]['evidence'])
        self.assertEqual(design_result, self.result('understand')[0])
        self.reject()
        self.admit()
        self.assertIn('understand', self.names())


if __name__ == '__main__':
    unittest.main()
