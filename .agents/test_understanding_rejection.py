"""Understanding rejection and revision through the public workflow dispatcher."""
import copy
import json
import unittest
from unittest import mock

import test_evidence_dag_journeys as j


class UnderstandingRejectionTests(j.DagFixture):
    LEGACY_GRAPH_DIGEST = '1fe19e2953d33a0a46183f42518f0c9620709b5c95a35226e66ffa18ce896f8d'

    def legacy_graph(self):
        path = j.Path(__file__).parent / 'fixtures' / 'legacy_evidence_dag.json'
        graph = json.loads(path.read_text(encoding='utf-8'))
        canonical = json.dumps(graph, sort_keys=True, separators=(',', ':')).encode()
        self.assertEqual(self.LEGACY_GRAPH_DIGEST, j.hashlib.sha256(canonical).hexdigest())
        return graph

    def test_historical_evidence_dag_matches_shipped_55b05ec_checkpoint(self):
        graph = self.legacy_graph()
        self.assertEqual(36, len(graph['nodes']))
        self.assertIn('review_understanding', {node['id'] for node in graph['nodes']})

    def setup_design(self, graph=None):
        if graph is None:
            graph = self.legacy_graph()
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

    def compiled_understanding_admission(self):
        graph = j.z.workflow_engine(self.fixture.repo, self.session.project, self.session.runtime).node_snapshot(100)['graph']
        contracts = list(graph['nodes']) + [row['template'] for row in graph['task_sets']]
        expected_scope = {'subject': {'kind': 'node', 'goal': '#this', 'node': 'understand'},
                          'output': 'design'}
        candidates = []
        for node in contracts:
            inputs = node.get('inputs', {})
            permits = node.get('permits', [])
            if (str(node.get('id', '')).startswith('gc_atomic_admit_')
                    and inputs.get('finding', {}).get('producer') == {
                        'node': {'kind': 'node', 'goal': '#this', 'node': 'interpret_understand_rejection'}}
                    and inputs.get('finding', {}).get('output') == 'value'
                    and inputs.get('subject', {}).get('producer') == {
                        'node': {'kind': 'node', 'goal': '#this', 'node': 'understand'}}
                    and inputs.get('subject', {}).get('output') == 'design'
                    and {permit.get('type') for permit in permits} == {'admission', 'supersession'}
                    and all(permit.get('scope') == expected_scope for permit in permits)):
                candidates.append(node['id'])
        self.assertEqual(1, len(candidates), candidates)
        replay = {'graph': j.z._static_workflow.canonical(graph, j.z._graph_compiler)}
        replay_ids = {node['id'] for node in replay['graph']['nodes']} | {
            row['template']['id'] for row in replay['graph']['task_sets']}
        self.assertIn(candidates[0], replay_ids, 'Canonical admission identity must be stable')
        self.assertNotIn('admit_understand_correction', self.names())
        return candidates[0]

    def admit(self):
        subject = self.produced('understand', 'design')
        self.session.finish(self.session.acquire('interpret_understand_rejection'), {'value': {
            'id': 'private_access', 'revision': 1, 'source': self.produced('review_understanding', 'review'),
            'subjects': [subject, self.produced('understand', 'allocation')],
            'target': j.scope('understand', 'design'), 'request': 'Revise design and finite allocation',
            'rationale': 'Exact independent review rejected both artifacts', 'supersedes': None}})
        self.finding = self.produced('interpret_understand_rejection')
        self.session.finish(self.session.acquire(self.compiled_understanding_admission()), {'value': {
            'finding': self.finding, 'target_inputs': self.result('understand')[1]['inputs'],
            'authority': self.result('interpret_understand_rejection')[0],
            'applicability': 'applicable', 'rationale': 'Planning only; no workspace authority'},
            'transfer': None})

    def resolve(self):
        self.session.finish(self.session.acquire('retain_understand_findings'), {'value': {
            'items': {'private_access': self.finding}, 'rationale': 'Retain the rejected design finding'}})
        self.resolve_exact_batch({'private_access': self.finding}, self.produced('understand', 'design'),
                                 self.result('review_understanding')[0],
                                 'Fresh exact-design independent review covers the correction')

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
        graph = self.legacy_graph()
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

        approval_case = UnderstandingRejectionTests()
        approval_case.setUp()
        self.addCleanup(approval_case.doCleanups)
        approval_graph = approval_case.legacy_graph()
        approval_contract = next(node for node in approval_graph['nodes']
                                 if node['id'] == 'review_understanding')
        approval_contract['outputs']['authorization']['schema'] = \
            approval_contract['outputs']['authorization']['schema']['variants'][0]
        approval_case.setup_design(approval_graph)
        review = approval_case.session.acquire('review_understanding')
        request = approval_case.session.submission(review, {
            'review': {'decision': 'approved', 'report': 'Approval still needs exact authority'},
            'authorization': None}, 'legacy-approved-without-authority')
        response = approval_case.session.call(100, request, expected=2)
        approval_case.assertRegex(json.dumps(response), r'(?i)authorization')

    def test_design_revision_invalidates_prior_human_approval_and_downstream_results(self):
        graph = self.legacy_graph()
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
        self.resolve_exact_batch({'later_audit': finding}, self.produced('understand', 'design'),
                                 self.result('review_understanding')[0], 'Verified')
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
    administrative_review = j.GraphAdoptionPublicTests.administrative_review
    proposal_review = j.GraphAdoptionPublicTests.proposal_review

    def test_reviewed_policy_repair_preserves_historical_design_and_graph(self):
        original = self.legacy_graph()
        self.setup_design(original)
        design_result = self.result('understand')[0]
        historical_graph = copy.deepcopy(self.payload()[1]['graph'])
        history = copy.deepcopy(self.payload()[1]['evidence'])
        repaired = j.z._static_workflow.canonical(original, j.z._graph_compiler)
        j.z._workflow_section(self.session.project, 'workflow_adherence')[
            'configuration']['phase_dag'] = copy.deepcopy(repaired)
        snapshot = j.z.workflow_engine(
            self.fixture.repo, self.session.project, self.session.runtime).node_snapshot(100)
        self.assertEqual(repaired, snapshot['graph'])
        self.assertEqual(historical_graph, self.payload()[1]['graph'])
        self.assertEqual(history, self.payload()[1]['evidence'])
        self.assertEqual(design_result, self.result('understand')[0])
        self.assertFalse(any(self.read_blob(row['result']).get('type') == 'graph_normalization'
                             for row in self.payload()[1]['operational']['receipts']))


class RepeatedDefaultCorrectionTests(j.DagFixture):
    """A shipped correction route can revise one admitted finding repeatedly."""

    default_decomposition = j.DefaultCorrectionPublicTests.default_decomposition
    review = j.DefaultCorrectionPublicTests.review

    def shipped_graph(self):
        template = json.loads((j.old.fixtures.PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        return j.z._workflow_section(template, 'workflow_adherence')['configuration']['phase_dag']

    def test_every_shipped_correction_admission_has_one_nullable_atomic_transfer(self):
        graph = self.shipped_graph()
        admissions = [node for node in graph['nodes']
                      if node['id'].startswith('admit_') and node['id'].endswith('_correction')]
        admissions.extend(item['template'] for item in graph['task_sets']
                          if item['template']['id'].startswith('admit_')
                          and item['template']['id'].endswith('_correction'))
        self.assertTrue(admissions)
        for node in admissions:
            with self.subTest(node=node['id']):
                self.assertEqual({'value', 'transfer'}, set(node['outputs']))
                self.assertEqual('admission', node['outputs']['value']['type'])
                self.assertEqual('supersession', node['outputs']['transfer']['type'])
                transfer = node['outputs']['transfer']['schema']
                self.assertEqual('union', transfer['kind'])
                self.assertEqual({'null', 'object'}, {variant['kind'] for variant in transfer['variants']})
                supersession = next(variant for variant in transfer['variants'] if variant['kind'] == 'object')
                self.assertEqual({'prior', 'replacement', 'coverage', 'coverage_evidence', 'authority'},
                                 set(supersession['fields']))
                self.assertEqual({'admission', 'supersession'},
                                 {permit['type'] for permit in node['permits']})

    def test_second_rejection_atomically_supersedes_first_admitted_finding(self):
        self.default_decomposition()
        finding_id = 'decomposition_defect'

        self.session.finish(self.session.acquire('decomposition_review'), {
            'value': self.review('changes_requested', 'First correction required'),
            'authorization': None})
        self.session.finish(self.session.acquire('interpret_decomposition_rejection'), {'value': {
            'id': finding_id, 'revision': 1, 'source': self.produced('decomposition_review'),
            'subjects': [self.produced('decompose')], 'target': j.scope('decompose'),
            'request': 'Correct the first observed defect',
            'rationale': 'Independent review rejected the exact decomposition', 'supersedes': None}})
        revision_one = self.produced('interpret_decomposition_rejection')
        first_admission = {
            'finding': revision_one, 'target_inputs': self.result('decompose')[1]['inputs'],
            'authority': self.result('interpret_decomposition_rejection')[0],
            'applicability': 'applicable', 'rationale': 'Within the exact approved planning scope'}
        first_work = self.session.acquire('admit_decomposition_correction')
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        rejected = self.session.call(100, self.session.submission(
            first_work, {'value': first_admission}, 'missing-first-transfer'), expected=2)
        self.assertRegex(json.dumps(rejected), r'(?i)transfer|output|missing')
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(first_work, {'value': first_admission, 'transfer': None})

        empty_members = {'items': {}, 'rationale': 'No additional review members.'}
        self.session.finish(self.session.acquire('decompose'), {'value': {
            'delivery_class': 'atomic', 'rationale': 'First corrected decomposition',
            'children': {'items': {}, 'rationale': 'Atomic work has no child goals.'},
            'implementation_review_members': empty_members,
            'integration_review_members': empty_members}})
        self.session.finish(self.session.acquire('decomposition_review'), {
            'value': self.review('changes_requested', 'The same defect needs refinement'),
            'authorization': None})
        self.session.finish(self.session.acquire('interpret_decomposition_rejection'), {'value': {
            'id': finding_id, 'revision': 2, 'source': self.produced('decomposition_review'),
            'subjects': [self.produced('decompose')], 'target': j.scope('decompose'),
            'request': 'Refine the same correction without duplicating its obligation',
            'rationale': 'Fresh review rejected the corrected exact decomposition',
            'supersedes': revision_one}})
        revision_two = self.produced('interpret_decomposition_rejection')
        authority = self.result('interpret_decomposition_rejection')[0]
        second_admission = {
            'finding': revision_two, 'target_inputs': self.result('decompose')[1]['inputs'],
            'authority': authority, 'applicability': 'applicable',
            'rationale': 'The revised finding remains within the exact planning scope'}
        second_work = self.session.acquire('admit_decomposition_correction')
        for nonce, transfer in (
                ('null-second-transfer', None),
                ('malformed-second-transfer', {
                    'prior': revision_one, 'replacement': revision_one, 'coverage': 'carried',
                    'coverage_evidence': authority, 'authority': authority})):
            with self.subTest(nonce=nonce):
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                rejected = self.session.call(100, self.session.submission(
                    second_work, {'value': second_admission, 'transfer': transfer}, nonce), expected=2)
                self.assertRegex(json.dumps(rejected), r'(?i)transfer|supersession|replacement|coverage')
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(second_work, {'value': second_admission, 'transfer': {
            'prior': revision_one, 'replacement': revision_two, 'coverage': 'carried',
            'coverage_evidence': authority, 'authority': authority}})

        snapshot = j.z.workflow_engine(
            self.fixture.repo, self.session.project, self.session.runtime).node_snapshot(100)
        obligation = snapshot['projection']['obligations'][(100, finding_id)]
        self.assertEqual(revision_two, obligation['finding'])
        self.assertEqual(2, self.read_blob(revision_two)['content']['revision'])
        self.assertEqual(1, self.read_blob(revision_one)['content']['revision'])


class RepeatedConfiguredMemberCorrectionTests(j.DagFixture):
    """Configured review members use the same atomic supersession contract."""

    requirements = j.ShippedGoal499PublicJourneyTests.requirements
    specification = j.ShippedGoal499PublicJourneyTests.specification
    approved_review = staticmethod(j.ShippedGoal499PublicJourneyTests.approved_review)
    administrative_review = j.GraphAdoptionPublicTests.administrative_review
    proposal_review = j.GraphAdoptionPublicTests.proposal_review

    def setUp(self):
        super().setUp()
        template = json.loads(
            (j.old.fixtures.PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        self.shipped = j.z._workflow_section(
            template, 'workflow_adherence')['configuration']['phase_dag']
        self.install(self.shipped)

    def reject_and_interpret(self, revision, supersedes):
        member = 'data_residency'
        self.session.finish(self.session.acquire('spec_review', item=member), {'value': {
            'decision': 'changes_requested', 'report': f'Residency correction {revision} is incomplete',
            'outcomes': ['blocked'], 'findings': ['spec:data-residency-region']}})
        self.session.finish(self.session.acquire('interpret_spec_review_rejection', item=member), {'value': {
            'id': 'data-residency-region', 'revision': revision,
            'source': self.produced('spec_review', item=member),
            'subjects': [self.produced('spec')], 'target': j.scope('spec'),
            'request': 'Refine the reviewed residency constraint',
            'rationale': 'The configured independent reviewer rejected the exact specification',
            'supersedes': supersedes}})
        return self.produced('interpret_spec_review_rejection', item=member)

    def admission(self, finding):
        return {
            'finding': finding, 'target_inputs': self.result('spec')[1]['inputs'],
            'authority': self.result('interpret_spec_review_rejection', item='data_residency')[0],
            'applicability': 'applicable',
            'rationale': 'Root admits the exact configured-domain correction'}

    def corrected_specification(self, allocation, revision):
        self.session.finish(self.session.acquire('spec'), {'value': {
            'specification': f'Residency-constrained behavior revision {revision}',
            'criteria': ['observable', f'residency revision {revision} is explicit'],
            'risks': ['correctness', 'data_residency'],
            'review_members': {'items': {'data_residency': 'configured repository-specific risk'},
                               'rationale': 'Re-review the configured domain correction'}},
            'allocation': allocation})

    def cutover_mapping(self):
        old_graph = self.read_blob(self.payload()[1]['graph'])
        new_graph = j.z._workflow_section(
            self.session.project, 'workflow_adherence')['configuration']['phase_dag']
        old = {node['id']: node for node in old_graph['nodes']}
        new = {node['id']: node for node in new_graph['nodes']}
        current = {}
        for reference in reversed(self.payload()[1]['evidence']):
            artifact = self.read_blob(reference); result = artifact.get('content', {})
            node = result.get('node', {})
            if artifact.get('type') != 'result' or node.get('item') is not None:
                continue
            current.setdefault(node.get('node'), (reference, result))
        mapping = []
        for name, (reference, result) in current.items():
            if name not in old or name not in new:
                continue
            for output in result.get('outputs', {}):
                if output in old[name]['outputs'] and output in new[name]['outputs']:
                    mapping.append({'old': {'node': name, 'output': output},
                        'new': {'node': name, 'output': output}, 'result': reference,
                        'equivalence': {key: True for key in
                            ('inputs', 'outputs', 'scope', 'role', 'independence', 'approval')}})
        return mapping

    def reviewed_cutover(self, step):
        prepared = self.session.call(100, {**step['prepare'], 'actor': 'root-thread',
            'mapping': self.cutover_mapping(),
            'request_id': 'prepare-legacy-admission-cutover'})['next_steps'][0]
        reviewed = self.session.call(100, {**prepared['review'],
            'actor': 'independent-cutover-reviewer', 'decision': 'approved',
            'report': 'The legacy admission is replaced without inheriting its authority.',
            'request_id': 'review-legacy-admission-cutover'})['next_steps'][0]
        return self.session.call(100, {**reviewed['apply'], 'actor': 'root-thread',
            'request_id': 'apply-legacy-admission-cutover'})['next_steps'][0]

    def test_repeated_configured_member_correction_requires_exact_atomic_transfer(self):
        self.requirements()
        _specification, allocation = self.specification(
            {'data_residency': 'configured repository-specific risk'})

        revision_one = self.reject_and_interpret(1, None)
        first = self.admission(revision_one)
        work = self.session.acquire('admit_spec_review_correction', item='data_residency')
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        rejected = self.session.call(100, self.session.submission(
            work, {'value': first}, 'member-missing-first-transfer'), expected=2)
        self.assertRegex(json.dumps(rejected), r'(?i)transfer|output|missing')
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(work, {'value': first, 'transfer': None})

        self.corrected_specification(allocation, 1)
        revision_two = self.reject_and_interpret(2, revision_one)
        second = self.admission(revision_two)
        authority = self.result('interpret_spec_review_rejection', item='data_residency')[0]
        work = self.session.acquire('admit_spec_review_correction', item='data_residency')
        candidates = (
            ('member-null-second-transfer', None),
            ('member-wrong-replacement', {
                'prior': revision_one, 'replacement': revision_one, 'coverage': 'carried',
                'coverage_evidence': authority, 'authority': authority}),
        )
        for nonce, transfer in candidates:
            with self.subTest(nonce=nonce):
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                rejected = self.session.call(100, self.session.submission(
                    work, {'value': second, 'transfer': transfer}, nonce), expected=2)
                self.assertRegex(json.dumps(rejected), r'(?i)transfer|supersession|replacement|coverage')
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(work, {'value': second, 'transfer': {
            'prior': revision_one, 'replacement': revision_two, 'coverage': 'carried',
            'coverage_evidence': authority, 'authority': authority}})

        snapshot = j.z.workflow_engine(
            self.fixture.repo, self.session.project, self.session.runtime).node_snapshot(100)
        obligation = snapshot['projection']['obligations'][(100, 'data-residency-region')]
        self.assertEqual(revision_two, obligation['finding'])
        self.assertEqual(1, self.read_blob(revision_one)['content']['revision'])
        self.assertEqual(2, self.read_blob(revision_two)['content']['revision'])

    def test_owned_shadowed_legacy_admission_can_recover_after_policy_migration(self):
        legacy = copy.deepcopy(self.shipped)
        admission = next(item['template'] for item in legacy['task_sets']
                         if item['template']['id'] == 'admit_spec_review_correction')
        admission['outputs'].pop('transfer', None)
        admission['permits'] = [permit for permit in admission['permits']
                                if permit['type'] != 'supersession']
        self.install(legacy)
        with mock.patch.object(j.z._static_workflow, 'canonical', side_effect=lambda graph, _compiler: graph):
            self.requirements()
            self.specification({'data_residency': 'configured repository-specific risk'})
            self.reject_and_interpret(1, None)
            owned = self.session.acquire('admit_spec_review_correction',
                                         item='data_residency', actor='legacy-owner')
        frontier = self.session.checkpoint(100)
        self.assertEqual(['policy_dag_cutover'], [step['kind'] for step in frontier])
        self.assertFalse(any(step.get('kind') == 'execute'
                             and step.get('node', {}).get('node', '').startswith('gc_atomic_admit_')
                             for step in frontier), 'replacement must not race the owned legacy admission')
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        direct = {**frontier[0]['prepare'], 'actor': 'root-thread',
                  'mapping': self.cutover_mapping(),
                  'request_id': 'cutover-with-owned-legacy-admission'}
        rejected = self.session.call(100, direct, expected=2)
        self.assertRegex(json.dumps(rejected), r'(?i)owner|legacy|admission|lease|recover')
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        recovery = {'operation': 'recover', 'request_id': 'recover-shadowed-legacy-admission',
                    'node': owned['node'], 'lease': owned['lease']['token'],
                    'actor': owned['lease']['owner'], 'worker_status': 'stopped',
                    'evidence': 'Observed the pre-migration admission worker terminated'}
        self.session.call(100, recovery)
        self.assertFalse(any(row['token'] == owned['lease']['token']
                             for row in self.payload()[1]['operational']['leases']))
        applied = self.reviewed_cutover(self.session.checkpoint(100)[0])
        self.assertEqual('policy_dag_cutover_applied', applied['kind'])
        self.assertNotIn('admit_spec_review_correction', self.names())
        self.assertTrue(any(name.startswith('gc_atomic_admit_') for name in self.names()))

    def test_persisted_legacy_member_route_is_shadowed_before_repeated_correction(self):
        legacy = copy.deepcopy(self.shipped)
        legacy_admissions = [item['template'] for item in legacy['task_sets']
                             if item['template']['id'] == 'admit_spec_review_correction']
        self.assertEqual(1, len(legacy_admissions))
        legacy_admissions[0]['outputs'].pop('transfer', None)
        legacy_admissions[0]['permits'] = [permit for permit in legacy_admissions[0]['permits']
                                          if permit['type'] != 'supersession']
        old_nodes = copy.deepcopy(legacy['nodes'])
        old_task_sets = copy.deepcopy(legacy['task_sets'])
        old_terminals = copy.deepcopy(legacy['terminals'])
        self.install(legacy)
        self.requirements()
        _specification, allocation = self.specification(
            {'data_residency': 'configured repository-specific risk'})
        rejection = self.session.finish(self.session.acquire('spec_review', item='data_residency'), {'value': {
            'decision': 'changes_requested', 'report': 'Legacy member route needs one correction',
            'outcomes': ['blocked'], 'findings': ['spec:data-residency-region']}})
        frontier = self.session.checkpoint(100)
        _envelope, payload = self.payload()
        persisted = self.read_blob(payload['graph'])
        self.assertEqual(old_nodes, persisted['nodes'][:len(old_nodes)])
        self.assertEqual(old_task_sets, persisted['task_sets'][:len(old_task_sets)])
        self.assertEqual(old_terminals, persisted['terminals'])
        receipts = [self.read_blob(row['result']) for row in payload['operational']['receipts']]
        normalizations = [row for row in receipts if row.get('type') == 'graph_normalization']
        self.assertEqual(0, len(normalizations))
        self.assertNotRegex(json.dumps([rejection, frontier]), r'(?i)graph_prepare|graph_adopt')
        executable = j.z.workflow_engine(
            self.fixture.repo, self.session.project, self.session.runtime).node_snapshot(100)['graph']
        legacy_source = next(item['source'] for item in persisted['task_sets']
                             if item['template']['id'] == 'admit_spec_review_correction')
        admission_templates = [item['template'] for item in executable['task_sets']
                               if item['source'] == legacy_source
                               and (item['template']['id'] == 'admit_spec_review_correction'
                                    or ('transfer' in item['template']['outputs']
                                        and any(permit['type'] == 'supersession'
                                                for permit in item['template']['permits'])))]
        self.assertEqual(2, len(admission_templates),
                         'Repair retains the legacy contract solely for historical Result interpretation')
        legacy_template = next(template for template in admission_templates
                               if template['id'] == 'admit_spec_review_correction')
        upgraded_template = next(template for template in admission_templates
                                 if template['id'] != 'admit_spec_review_correction')
        upgraded_id = upgraded_template['id']
        self.assertEqual({'value'}, set(legacy_template['outputs']))
        self.assertEqual({'value', 'transfer'}, set(upgraded_template['outputs']))
        self.assertEqual({'admission', 'supersession'},
                         {permit['type'] for permit in upgraded_template['permits']})

        self.session.finish(self.session.acquire(
            'interpret_spec_review_rejection', item='data_residency'), {'value': {
                'id': 'data-residency-region', 'revision': 1,
                'source': self.produced('spec_review', item='data_residency'),
                'subjects': [self.produced('spec')], 'target': j.scope('spec'),
                'request': 'Add the reviewed residency constraint',
                'rationale': 'The configured independent reviewer rejected the exact specification',
                'supersedes': None}})
        revision_one = self.produced('interpret_spec_review_rejection', item='data_residency')
        frontier = self.session.checkpoint(100)
        active = [step for step in frontier if step.get('kind') == 'execute'
                  and step.get('node', {}).get('node') == upgraded_id]
        self.assertEqual([upgraded_id],
                         [step['node']['node'] for step in active])
        self.assertEqual('data_residency', active[0]['node']['item'])
        self.assertNotIn('admit_spec_review_correction', self.names())
        legacy_start = copy.deepcopy(active[0]['start'])
        legacy_start['node']['node'] = 'admit_spec_review_correction'
        legacy_start['policy_receipt'] = json.loads(
            j.Path(active[0]['policy']['path']).read_text())['policy_receipt']
        legacy_start['request_id'] = 'shadowed-legacy-member-start'
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        rejected = self.session.call(100, legacy_start, expected=2)
        self.assertRegex(json.dumps(rejected), r'(?i)legacy|superseded|atomic transfer|shadow')
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

        first = self.admission(revision_one)
        self.session.finish(self.session.acquire(
            upgraded_id, item='data_residency'),
            {'value': first, 'transfer': None})

        self.corrected_specification(allocation, 1)
        revision_two = self.reject_and_interpret(2, revision_one)
        second = self.admission(revision_two)
        work = self.session.acquire(upgraded_id, item='data_residency')
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        rejected = self.session.call(100, self.session.submission(
            work, {'value': second, 'transfer': None}, 'legacy-member-null-second-transfer'), expected=2)
        self.assertRegex(json.dumps(rejected), r'(?i)transfer|supersession|coverage')
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        authority = self.result('interpret_spec_review_rejection', item='data_residency')[0]
        self.session.finish(work, {'value': second, 'transfer': {
            'prior': revision_one, 'replacement': revision_two, 'coverage': 'carried',
            'coverage_evidence': authority, 'authority': authority}})
        obligation = j.z.workflow_engine(
            self.fixture.repo, self.session.project, self.session.runtime
        ).node_snapshot(100)['projection']['obligations'][(100, 'data-residency-region')]
        self.assertEqual(revision_two, obligation['finding'])
        self.assertEqual(1, self.read_blob(revision_one)['content']['revision'])



if __name__ == '__main__':
    unittest.main()
