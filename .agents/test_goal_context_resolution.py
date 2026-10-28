"""Public contract for resolving authenticated blockers preserved by migration.

The host, rather than a phase Result, owns this narrow intake.  Discovery binds
the immutable original goal-context and exact blocker content identities.  A
root submission then supplies its judgement, same-goal immutable evidence and,
for human-action blockers, explicit user attribution.  Resolution is an
append-only projection: it never rewrites migration history or satisfies phase,
workspace, dependency, review, CI, merge, or publication gates.
"""
from __future__ import annotations

import copy
import json
import os
import unittest
from unittest import mock

import test_batch_goal_conversion as batch
import test_evidence_dag_journeys as dag
import test_archived_prerequisites as archive_tests


class GoalContextResolutionTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.case = batch.BatchConversionTests(methodName="runTest")
        cls.case.setUp()
        cls.addClassCleanup(cls.case.doCleanups)
        cls.blocker = {
            "status": "open",
            "category": "human-action",
            "question": "User must approve the exact migrated design",
        }
        cls.case.legacy_fields(100, depends_on=[101], blockers=[copy.deepcopy(cls.blocker)])
        result = cls.case.migrate((100,))
        if result["members"]["100"]["status"] != "migrated":
            raise AssertionError(result)
        cls.case.normal_setup(100)
        cls.baseline_issues = copy.deepcopy(cls.case.provider.issues)
        cls.baseline_comments = copy.deepcopy(cls.case.provider.comments)
        cls.baseline_blobs = copy.deepcopy(cls.case.blobs)

    def setUp(self):
        self.case.provider.issues = copy.deepcopy(self.baseline_issues)
        self.case.provider.comments = copy.deepcopy(self.baseline_comments)
        self.case.provider.updates = []
        self.case.blobs = copy.deepcopy(self.baseline_blobs)
        self.case.session.sequence = 0
        self.case.session.calls = []
        self.envelope = dag.z.parse_managed_goal(self.case.provider.issues[100]["body"], 100)
        self.original_payload = copy.deepcopy(self.case.session.read(100, self.envelope["payload"]))
        self.original_context_ref = copy.deepcopy(self.original_payload["goal_context"])
        self.original_context = copy.deepcopy(self.case.session.read(100, self.original_context_ref))
        self.original_comments = copy.deepcopy(self.case.provider.comments[100])

    def fresh_case(self):
        case = batch.BatchConversionTests(methodName="runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        self.case = case
        return case

    def discovery(self, blocker=None):
        blocker_hash = dag.z._workflow.digest(blocker or self.blocker)
        matches = [step for step in self.case.session.checkpoint(100)
                   if (step.get("submission") or {}).get("operation") == "resolve_goal_blocker"
                   and step["submission"].get("blocker_hash") == blocker_hash]
        self.assertEqual(1, len(matches), matches)
        step = matches[0]
        self.assertEqual("root", step.get("assignment"))
        self.assertRegex(json.dumps(step), r"(?i)blocker|resolution|evidence|approval")
        return step

    def current_payload(self):
        envelope = dag.z.parse_managed_goal(self.case.provider.issues[100]["body"], 100)
        return self.case.session.read(100, envelope["payload"])

    def evidence(self, *, goal=100):
        """Use authenticated current host Results/outputs, never invented prose."""
        result, content = self.case.result("understand")
        refs = [result, content["outputs"]["design"], content["outputs"]["allocation"]]
        if goal == 100:
            return refs
        return [{**ref, "uri": ref["uri"].replace("goal:100:", f"goal:{goal}:")}
                for ref in refs]

    def request(self, request_id="resolve-migrated-blocker-1", **changes):
        submission = copy.deepcopy(self.discovery()["submission"])
        submission.update({
            "request_id": request_id,
            "actor": "root-thread",
            "rationale": "The user approved the current design and explicitly superseded the obsolete requirement.",
            "resolution_basis": "Root attests that the cited approval resolves this exact obligation.",
            "evidence": self.evidence(),
            "human_approval": {"approved_by": "requesting-user",
                               "attribution": "Approved the exact current design in this conversation."},
        })
        submission.update(changes)
        return submission

    def call(self, request, *, expected=0):
        with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "root-thread"}):
            return self.case.session.call(100, request, expected=expected)

    def assert_rejected_without_write(self, request, pattern):
        before = copy.deepcopy((self.case.provider.issues, self.case.provider.comments))
        response = self.call(request, expected=2)
        self.assertRegex(json.dumps(response), pattern)
        self.assertEqual(before, (self.case.provider.issues, self.case.provider.comments))

    def resolved_event(self, response):
        step = response["next_steps"][0]
        self.assertEqual("goal_blocker_resolved", step["kind"])
        self.assertEqual(100, step["goal"])
        reference = step.get("resolution") or step.get("event")
        self.assertIsInstance(reference, dict)
        return step, self.case.session.read(100, reference)

    def test_reviewed_dependency_retirement_preserves_blocker_and_history(self):
        before_comments = copy.deepcopy(self.case.provider.comments[100])
        preview = self.call({'operation': 'goal_dependency_prepare',
            'request_id': 'dependency-preview-1', 'old': 101, 'replacement': None,
            'rationale': 'The user approved moving this exact prerequisite into the goal.'})
        step = preview['next_steps'][0]
        self.assertEqual('review_required', step['kind'])
        proposal = step['proposal']
        self.assertEqual([101], proposal['before'])
        self.assertEqual([], proposal['after'])
        review_request = copy.deepcopy(step['submission'])
        review_request.update(actor='independent-thread', decision='approved',
            report='The selected edge is obsolete; unrelated blockers and evidence remain.')
        with mock.patch.dict(os.environ, {'CODEX_THREAD_ID': 'independent-thread'}):
            review_response = self.case.session.call(100, review_request)
        approval = copy.deepcopy(review_response['next_steps'][0]['submission'])
        approval['human_approval'] = {'approved_by': 'requesting-user',
            'attribution': 'Approved the exact #101 relationship retirement.'}
        applied = self.call(approval)
        self.assertEqual('goal_dependency_changed', applied['next_steps'][0]['kind'])
        self.assertEqual([101], applied['next_steps'][0]['before'])
        self.assertEqual([], applied['next_steps'][0]['after'])
        self.assertEqual(before_comments, self.case.provider.comments[100][:len(before_comments)])
        self.assertEqual(self.original_context_ref, self.current_payload()['goal_context'])
        steps = self.case.session.checkpoint(100)
        self.assertTrue(any(s.get('kind') == 'goal_blocker_resolution' for s in steps))
        self.assertFalse(any('Goal #101 requires current' in s.get('reason', '') for s in steps))
        self.assertEqual(applied, self.call(approval), 'exact request replay must be idempotent')

    def test_external_blocker_without_current_results_offers_reviewed_resolution(self):
        case = self.fresh_case()
        blocker = {'status': 'open', 'category': 'external-dependency',
                   'question': 'Goal #101 must finish before this goal can use its work.'}
        case.legacy_fields(100, depends_on=[101], blockers=[blocker])
        self.assertEqual('migrated', case.migrate((100,))['members']['100']['status'])
        envelope = dag.z.parse_managed_goal(case.provider.issues[100]['body'], 100)
        payload = case.session.read(100, envelope['payload'])
        self.assertEqual([], payload['evidence'])
        steps = case.session.checkpoint(100)
        self.assertTrue(any((step.get('submission') or {}).get('operation')
                            == 'goal_external_blocker_prepare' for step in steps), steps)

    def test_archived_prerequisite_requires_independent_review_and_exact_receipts(self):
        case = self.fresh_case()
        blocker = {'status': 'open', 'category': 'external-dependency',
                   'question': 'Goal #101 must finish before this goal can use its work.'}
        other = {'status': 'open', 'category': 'external-dependency',
                 'question': 'Goal #101 must also finish the publication obligation.'}
        case.legacy_fields(100, depends_on=[101], blockers=[blocker, other])
        self.assertEqual('migrated', case.migrate((100,))['members']['100']['status'])
        original_envelope = dag.z.parse_managed_goal(case.provider.issues[100]['body'], 100)
        original_context_ref = copy.deepcopy(case.session.read(100, original_envelope['payload'])['goal_context'])
        prepare = next(step['submission'] for step in case.session.checkpoint(100)
                       if (step.get('submission') or {}).get('operation')
                       == 'goal_external_blocker_prepare')
        prepare.update(request_id='archived-preview-100', pull_number=7)

        def observed(engine, snapshot, request, *, historical_edge=False):
            if (request['context_hash'] != snapshot['goal_context_ref']['hash']
                    or request['blocker_hash'] not in {
                        dag.z._workflow.digest(blocker), dag.z._workflow.digest(other)}
                    or request['prerequisite'] != 101 or request['pull_number'] != 7):
                raise ValueError('Archived candidate identity changed')
            return {'kind': 'archived_prerequisite_proposal',
                'repository': engine.repository, 'goal': 100,
                'context_hash': request['context_hash'], 'blocker_hash': request['blocker_hash'],
                'prerequisite': 101, 'pull_number': 7,
                'candidate': {'identity': 'sha256:' + 'a' * 64},
                'manual_request': 'opaque_requires_reviewed_adoption',
                'migration_transaction': 'sha256:' + 'b' * 64,
                'source_envelope': copy.deepcopy(snapshot['envelope']),
                'policy': engine.node_evidence_policy()}

        before = copy.deepcopy((case.provider.issues, case.provider.comments))
        with mock.patch.object(dag.z._workflow.Workflow,
                               'node_external_blocker_proposal', observed):
            preview = case.session.call(100, prepare)
            self.assertEqual(before, (case.provider.issues, case.provider.comments))
            review = copy.deepcopy(preview['next_steps'][0]['submission'])
            review.update(actor='independent-thread', decision='approved',
                          report='Checked the archived transaction and merged work against the exact obligation.')
            review['adoption'] = {'manual_request': 'opaque',
                'terminal_equivalence': 'The reviewed merge satisfies this prerequisite.',
                'retained_obligations': 'Normal phase and publication gates remain required.'}
            rejected = case.session.call(100, review, expected=2)
            self.assertRegex(json.dumps(rejected), r'(?i)independent|thread')
            current_envelope = dag.z.parse_managed_goal(case.provider.issues[100]['body'], 100)
            case.replace_legacy_payload(current_envelope,
                                        case.session.read(100, current_envelope['payload']))
            with mock.patch.dict(os.environ, {'CODEX_THREAD_ID': 'independent-thread'}):
                rejected = case.session.call(100, review, expected=2)
            self.assertRegex(json.dumps(rejected), r'(?i)proposal|changed|stale')
            case.provider.issues, case.provider.comments = copy.deepcopy(before)
            ordinary_snapshot = dag.z._workflow.Workflow.node_snapshot

            def legacy_context_locator(engine, number, **options):
                snapshot = ordinary_snapshot(engine, number, **options)
                if number == 100 and snapshot.get('goal_context_ref'):
                    identity = snapshot['goal_context_ref']['hash']
                    snapshot['goal_context_ref'] = {'hash': identity, 'uri': 'urn:' + identity}
                return snapshot

            with mock.patch.object(dag.z._workflow.Workflow, 'node_snapshot', legacy_context_locator), \
                 mock.patch.dict(os.environ, {'CODEX_THREAD_ID': 'independent-thread'}):
                reviewed = case.session.call(100, review)
            apply = copy.deepcopy(reviewed['next_steps'][0]['submission'])
            apply['human_approval'] = {'approved_by': 'requesting-user',
                'attribution': 'Approved this exact archived prerequisite equivalence.'}
            with mock.patch.dict(os.environ, {'CODEX_THREAD_ID': 'root-thread'}):
                applied = case.session.call(100, apply)
                self.assertEqual(applied, case.session.call(100, apply))
            self.assertEqual('archived_prerequisite_applied', applied['next_steps'][0]['kind'])
            envelope = dag.z.parse_managed_goal(case.provider.issues[100]['body'], 100)
            payload = case.session.read(100, envelope['payload'])
            self.assertEqual(original_context_ref, payload['goal_context'])
            self.assertEqual(1, len(payload['goal_context_archived_prerequisites']['events']))
            steps = case.session.checkpoint(100)
            second = next(step['submission'] for step in steps
                          if (step.get('submission') or {}).get('operation')
                          == 'goal_external_blocker_prepare')
            second.update(request_id='archived-preview-100-second', pull_number=7)
            second_preview = case.session.call(100, second)
            second_review = copy.deepcopy(second_preview['next_steps'][0]['submission'])
            second_review.update(actor='independent-thread', decision='approved',
                report='The separate publication blocker is satisfied by the same archived merge.')
            second_review['adoption'] = copy.deepcopy(review['adoption'])
            with mock.patch.dict(os.environ, {'CODEX_THREAD_ID': 'independent-thread'}):
                second_reviewed = case.session.call(100, second_review)
            second_apply = copy.deepcopy(second_reviewed['next_steps'][0]['submission'])
            second_apply['human_approval'] = copy.deepcopy(apply['human_approval'])
            with mock.patch.dict(os.environ, {'CODEX_THREAD_ID': 'root-thread'}):
                case.session.call(100, second_apply)
            envelope = dag.z.parse_managed_goal(case.provider.issues[100]['body'], 100)
            payload = case.session.read(100, envelope['payload'])
            self.assertEqual(2, len(payload['goal_context_archived_prerequisites']['events']))
            steps = case.session.checkpoint(100)
            self.assertFalse(any((step.get('submission') or {}).get('operation')
                                 == 'goal_external_blocker_prepare' for step in steps))
            self.assertFalse(any('Goal #101 requires current' in step.get('reason', '')
                                 for step in steps))
            dependency = case.session.call(100, {'operation': 'goal_dependency_prepare',
                'request_id': 'retire-adopted-prerequisite', 'old': 101,
                'replacement': None,
                'rationale': 'The archived prerequisite has been incorporated.'})['next_steps'][0]
            dependency_review = copy.deepcopy(dependency['submission'])
            dependency_review.update(actor='independent-thread', decision='approved',
                report='The reviewed retirement preserves both archived resolutions.')
            with mock.patch.dict(os.environ, {'CODEX_THREAD_ID': 'independent-thread'}):
                dependency_reviewed = case.session.call(100, dependency_review)
            dependency_apply = copy.deepcopy(dependency_reviewed['next_steps'][0]['submission'])
            dependency_apply['human_approval'] = {'approved_by': 'requesting-user',
                'attribution': 'Approved retiring this exact incorporated dependency.'}
            with mock.patch.dict(os.environ, {'CODEX_THREAD_ID': 'root-thread'}):
                case.session.call(100, dependency_apply)
            self.assertTrue(case.session.checkpoint(100))
            envelope = dag.z.parse_managed_goal(case.provider.issues[100]['body'], 100)
            payload = case.session.read(100, envelope['payload'])
            tampered = copy.deepcopy(payload)
            tampered['operational']['receipts'] = [row for row in tampered['operational']['receipts']
                if row['request'] != review['request_id']]
            case.replace_legacy_payload(envelope, tampered)
            rejected = case.session.call(100, expected=2)
            self.assertRegex(json.dumps(rejected), r'(?i)archived|receipt|authentication')

    def test_public_archived_preview_checks_exact_remote_evidence_without_writes(self):
        case = self.fresh_case()
        blocker = {'status': 'open', 'category': 'external-dependency',
                   'question': 'Goal #101 must finish before this goal can use its work.'}
        case.legacy_fields(100, depends_on=[101], blockers=[blocker])
        self.assertEqual('migrated', case.migrate((100,))['members']['100']['status'])
        repository = dag.z._project_repository_identity(case.session.project)
        inputs = archive_tests.ArchivedPrerequisiteTests().candidate_inputs(
            repository=repository, goal=101)
        case.provider.issues[101] = copy.deepcopy(inputs['issue'])
        store = dag.z._workflow.comment_store
        source_envelope = {**inputs['target_intent'], 'revision': 8,
                           'payload': inputs['target_intent']['payload']}
        response_ref = {'hash': store.digest(inputs['migration_response']),
            'uri': f'zzzops:{repository}:goal:101:{store.digest(inputs["migration_response"])}'}
        receipt_ref = {'hash': store.digest(inputs['receipt']),
            'uri': f'zzzops:{repository}:goal:101:{store.digest(inputs["receipt"])}'}
        row = inputs['archived_payload']['operational']['receipts'][0]
        context = {'request_id': row['request'], 'request_hash': row['payload'],
            'response': response_ref, 'migration': {'receipt': receipt_ref},
            'source_envelope': source_envelope,
            'target_envelope': {**inputs['target_intent'],
                                'payload': inputs['envelope']['payload']},
            'entry_payload': inputs['envelope']['payload'],
            'payload': inputs['envelope']['payload'],
            'source_hash': store.digest(json.loads(inputs['source_bytes'])['content']['body']),
            'human_hash': store.digest('Old goal\n\n')}
        records = [{'hash': store.digest(value), 'kind': 'full', 'type': 'json',
                    'text': store.canonical(value)} for value in
                   (inputs['migration_response'], inputs['receipt'],
                    inputs['target_intent'], inputs['target_payload'], inputs['archived_payload'])]
        bodies = store.pack_envelopes({'goal': 101, 'transaction': 'sha256:' + '3' * 64,
                                       'context': context}, records)
        case.provider.comments[101] = [{'id': 9100 + i, 'body': body}
                                       for i, body in enumerate(bodies)]
        case.provider.archived_prerequisite_pull = lambda _number: copy.deepcopy(inputs['pull'])
        case.provider.archived_prerequisite_reachable = lambda _commit, _branch: inputs['merge_reachable']
        values = {dag.z._workflow.digest(value): value for value in
                  (inputs['archived_payload'], inputs['migration_response'],
                   inputs['receipt'], inputs['target_intent'], inputs['target_payload'])}
        original_read = dag.z._workflow.Workflow.read_artifact
        original_published = dag.z._workflow.Workflow.node_published_artifact

        def read(engine, number, reference):
            if number == 101:
                return copy.deepcopy(values[reference['hash']])
            return original_read(engine, number, reference)

        def published(engine, reference):
            if reference == inputs['receipt']['source']:
                return json.loads(inputs['source_bytes']), inputs['source_bytes']
            if reference == inputs['receipt']['policy']:
                return json.loads(inputs['policy_bytes']), inputs['policy_bytes']
            return original_published(engine, reference)

        submission = next(step['submission'] for step in case.session.checkpoint(100)
                          if (step.get('submission') or {}).get('operation')
                          == 'goal_external_blocker_prepare')
        submission.update(request_id='archived-public-preview-100', pull_number=7)
        before = copy.deepcopy((case.provider.issues, case.provider.comments))
        original_snapshot = dag.z._workflow.Workflow.node_snapshot

        def unmapped_history(engine, number, **options):
            snapshot = original_snapshot(engine, number, **options)
            if number == 100:
                snapshot['workflow_migration_blocker'] = (
                    'Unmapped historical phase contracts require policy/data mapping')
            return snapshot

        with mock.patch.object(dag.z._workflow.Workflow, 'read_artifact', read), \
             mock.patch.object(dag.z._workflow.Workflow, 'node_published_artifact', published), \
             mock.patch.object(dag.z._workflow.Workflow, 'node_snapshot', unmapped_history):
            preview = case.session.call(100, submission)
            self.assertEqual('archived_prerequisite_preview', preview['next_steps'][0]['kind'])
            self.assertEqual(before, (case.provider.issues, case.provider.comments))
            for change in ({'prerequisite': 102}, {'blocker_hash': 'sha256:' + 'a' * 64},
                           {'context_hash': 'sha256:' + 'b' * 64}):
                rejected = case.session.call(100, {**submission, **change}, expected=2)
                self.assertRegex(json.dumps(rejected), r'(?i)archived|blocker|context|prerequisite')
                self.assertEqual(before, (case.provider.issues, case.provider.comments))
            inputs['pull']['baseRepository'] = 'foreign/repo'
            rejected = case.session.call(100, submission, expected=2)
            self.assertRegex(json.dumps(rejected), r'(?i)pull|repository|branch')
            inputs['pull']['baseRepository'] = repository
            inputs['merge_reachable'] = False
            rejected = case.session.call(100, submission, expected=2)
            self.assertRegex(json.dumps(rejected), r'(?i)reachable|merge')
            self.assertEqual(before, (case.provider.issues, case.provider.comments))
            inputs['merge_reachable'] = True
            # A hash-consistent archived payload alone is not a historical
            # conversion: its exact provider comment transaction must exist.
            case.provider.comments[101] = []
            rejected = case.session.call(100, submission, expected=2)
            self.assertRegex(json.dumps(rejected), r'(?i)transaction|migration')
            self.assertEqual(before[0], case.provider.issues)
            self.assertEqual(before[1][100], case.provider.comments[100])
            bad_context = {**context, 'request_hash': 'sha256:' + '4' * 64}
            bad_bodies = store.pack_envelopes({'goal': 101,
                'transaction': 'sha256:' + '5' * 64,
                'context': bad_context}, records)
            case.provider.comments[101] = [{'id': 9200 + i, 'body': body}
                                           for i, body in enumerate(bad_bodies)]
            rejected = case.session.call(100, submission, expected=2)
            self.assertRegex(json.dumps(rejected), r'(?i)transaction|source|target|migration')
            case.provider.comments[101] = copy.deepcopy(before[1][101])
            review = copy.deepcopy(preview['next_steps'][0]['submission'])
            review.update(actor='independent-thread', decision='approved',
                report='The original obligation matches the archived conversion and merged PR.')
            review['adoption'] = {'manual_request': 'opaque',
                'terminal_equivalence': 'The reviewed merge satisfies this prerequisite.',
                'retained_obligations': 'Normal phase and publication gates remain required.'}
            with mock.patch.dict(os.environ, {'CODEX_THREAD_ID': 'independent-thread'}):
                reviewed = case.session.call(100, review)
            apply = copy.deepcopy(reviewed['next_steps'][0]['submission'])
            apply['human_approval'] = {'approved_by': 'requesting-user',
                'attribution': 'Approved this exact reviewed archived prerequisite.'}
            inputs['pull']['body'] += ' A later edit retaining the link.'
            with mock.patch.dict(os.environ, {'CODEX_THREAD_ID': 'root-thread'}):
                rejected = case.session.call(100, apply, expected=2)
            self.assertRegex(json.dumps(rejected), r'(?i)candidate|changed|review')
            inputs['pull']['body'] = 'Refs #101.'
            with mock.patch.dict(os.environ, {'CODEX_THREAD_ID': 'root-thread'}):
                applied = case.session.call(100, apply)
                self.assertEqual(applied, case.session.call(100, apply))
            self.assertEqual('archived_prerequisite_applied', applied['next_steps'][0]['kind'])
            steps = case.session.checkpoint(100)
            self.assertFalse(any((step.get('submission') or {}).get('operation')
                                 == 'goal_external_blocker_prepare' for step in steps))
            self.assertFalse(any('Goal #101 requires current' in step.get('reason', '')
                                 for step in steps))
            self.assertTrue(any(step.get('kind') == 'blocker'
                                and 'Unmapped historical phase contracts' in step.get('reason', '')
                                for step in steps))
            rejected = case.session.call(100, {'operation': 'start',
                'request_id': 'unmapped-normal-start'}, expected=2)
            self.assertRegex(json.dumps(rejected), r'Unmapped historical phase contracts')
            case.provider.issues[101]['body'] += '\nA later edit retaining the link.'
            rejected = case.session.call(100, expected=2)
            self.assertRegex(json.dumps(rejected), r'(?i)archived|prerequisite|changed')
            case.provider.issues[101]['body'] = inputs['issue']['body']
            case.provider.issues[101]['state'] = 'open'
            rejected = case.session.call(100, expected=2)
            self.assertRegex(json.dumps(rejected), r'(?i)archived|prerequisite|closed')

    def test_dependency_review_requires_invoking_independent_thread(self):
        step = self.call({'operation': 'goal_dependency_prepare',
            'request_id': 'dependency-preview-auth', 'old': 101, 'replacement': None,
            'rationale': 'Retire the obsolete prerequisite.'})['next_steps'][0]
        request = copy.deepcopy(step['submission'])
        request.update(actor='independent-thread', decision='approved',
                       report='Reviewed the exact edge and retained gates.')
        self.assert_rejected_without_write(request, r'(?i)independent|thread|actor')
        request['actor'] = 'root-thread'
        self.assert_rejected_without_write(request, r'(?i)independent|thread|actor')

    def test_dependency_event_without_review_receipt_is_rejected(self):
        step = self.call({'operation': 'goal_dependency_prepare',
            'request_id': 'dependency-preview-receipt', 'old': 101,
            'replacement': None, 'rationale': 'Retire the obsolete prerequisite.'})['next_steps'][0]
        request = copy.deepcopy(step['submission'])
        request.update(actor='independent-thread', decision='approved',
                       report='Reviewed the exact edge and retained gates.')
        with mock.patch.dict(os.environ, {'CODEX_THREAD_ID': 'independent-thread'}):
            review_response = self.case.session.call(100, request)
        approval = copy.deepcopy(review_response['next_steps'][0]['submission'])
        approval['human_approval'] = {'approved_by': 'requesting-user',
                                     'attribution': 'Approved the exact edge retirement.'}
        self.call(approval)
        envelope = dag.z.parse_managed_goal(self.case.provider.issues[100]['body'], 100)
        payload = copy.deepcopy(self.case.session.read(100, envelope['payload']))
        payload['operational']['receipts'] = [
            receipt for receipt in payload['operational']['receipts']
            if receipt.get('request') != request['request_id']]
        self.case.replace_legacy_payload(envelope, payload)
        rejected = self.case.session.call(100, expected=2)
        self.assertRegex(json.dumps(rejected), r'(?i)dependency|receipt|authentication')

    def test_dependency_review_rejects_changed_goal_revision(self):
        step = self.call({'operation': 'goal_dependency_prepare',
            'request_id': 'dependency-preview-stale', 'old': 101,
            'replacement': None, 'rationale': 'Retire the obsolete prerequisite.'})['next_steps'][0]
        request = copy.deepcopy(step['submission'])
        request.update(actor='independent-thread', decision='approved',
                       report='Reviewed the exact edge and retained gates.')
        envelope = dag.z.parse_managed_goal(self.case.provider.issues[100]['body'], 100)
        self.case.replace_legacy_payload(envelope, self.current_payload())
        before = copy.deepcopy((self.case.provider.issues, self.case.provider.comments))
        with mock.patch.dict(os.environ, {'CODEX_THREAD_ID': 'independent-thread'}):
            rejected = self.case.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(rejected), r'(?i)proposal|changed|stale|evidence')
        self.assertEqual(before, (self.case.provider.issues, self.case.provider.comments))

    def test_dependency_review_exact_retry_rejects_changed_report(self):
        step = self.call({'operation': 'goal_dependency_prepare',
            'request_id': 'dependency-preview-retry', 'old': 101,
            'replacement': None, 'rationale': 'Retire the obsolete prerequisite.'})['next_steps'][0]
        request = copy.deepcopy(step['submission'])
        request.update(actor='independent-thread', decision='approved',
                       report='Reviewed the exact edge and retained gates.')
        with mock.patch.dict(os.environ, {'CODEX_THREAD_ID': 'independent-thread'}):
            first = self.case.session.call(100, request)
            self.assertEqual(first, self.case.session.call(100, request))
            before = copy.deepcopy((self.case.provider.issues, self.case.provider.comments))
            changed = {**request, 'report': 'A different review after the same request ID.'}
            rejected = self.case.session.call(100, changed, expected=2)
        self.assertRegex(json.dumps(rejected), r'(?i)request|replay|conflict|payload')
        self.assertEqual(before, (self.case.provider.issues, self.case.provider.comments))

    def test_dependency_change_preserves_unrelated_dependency(self):
        self.fresh_case()
        self.case.add(102)
        self.case.legacy_fields(100, depends_on=[101, 102],
                                blockers=[copy.deepcopy(self.blocker)])
        self.case.migrate((100, 102))
        self.case.normal_setup(100)
        preview = self.call({'operation': 'goal_dependency_prepare',
            'request_id': 'dependency-preview-unrelated', 'old': 101,
            'replacement': None, 'rationale': 'Retire only goal 101.'})
        proposal = preview['next_steps'][0]['proposal']
        self.assertEqual([101, 102], proposal['before'])
        self.assertEqual([102], proposal['after'])
        envelope = dag.z.parse_managed_goal(self.case.provider.issues[100]['body'], 100)
        payload = self.case.session.read(100, envelope['payload'])
        context = self.case.session.read(100, payload['goal_context'])['content']
        self.assertEqual(self.blocker, context['blockers'][0])

    def test_public_discovery_success_and_exact_authenticated_identity(self):
        step = self.discovery()
        submission = step["submission"]
        self.assertEqual(self.original_context_ref["hash"], submission["context_hash"])
        self.assertEqual(dag.z._workflow.digest(self.blocker), submission["blocker_hash"])

        request = self.request()
        response = self.call(request)
        recorded, event = self.resolved_event(response)
        self.assertEqual("goal_blocker_resolution", event["type"])
        self.assertEqual(self.original_context_ref["hash"], event["content"]["context_hash"])
        self.assertEqual(submission["blocker_hash"], event["content"]["blocker_hash"])
        self.assertEqual("root-thread", event["provenance"]["actor"])
        self.assertEqual("resolve-migrated-blocker-1", event["provenance"]["request_id"])
        self.assertEqual(request["evidence"], event["content"]["evidence"])
        self.assertEqual("requesting-user", event["content"]["human_approval"]["approved_by"])

        steps = self.case.session.checkpoint(100)
        self.assertFalse(any((row.get("submission") or {}).get("blocker_hash")
                             == submission["blocker_hash"] for row in steps), steps)
        dependency = [row for row in steps if row.get("node", {}).get("node") == "test_design"]
        self.assertTrue(dependency, steps)
        self.assertFalse(any(row.get("kind") == "execute" for row in dependency), dependency)
        self.assertRegex(json.dumps(dependency), r"(?i)depend|101|predecessor")
        self.assertFalse(any(row.get("kind") == "result" for row in response["next_steps"]), response)
        self.assertIn(recorded.get("resolution") or recorded.get("event"),
                      self.current_payload()["goal_context_resolutions"]["events"])

    def test_original_context_history_dependency_and_other_blocker_are_immutable(self):
        other = {"status": "open", "category": "technical-unknown",
                 "question": "Confirm an unrelated compatibility constraint"}
        # Rebuild the fixture with two original obligations so projection can
        # prove that only the selected identity is removed.
        self.fresh_case()
        self.case.legacy_fields(100, depends_on=[101], blockers=[copy.deepcopy(self.blocker), other])
        self.case.migrate((100,))
        self.case.normal_setup(100)
        envelope = dag.z.parse_managed_goal(self.case.provider.issues[100]["body"], 100)
        before_payload = copy.deepcopy(self.case.session.read(100, envelope["payload"]))
        before_ref = copy.deepcopy(before_payload["goal_context"])
        before_context = copy.deepcopy(self.case.session.read(100, before_ref))
        before_history = [(row["id"], row["body"])
                          for row in self.case.provider.comments[100]]
        self.call(self.request())
        after_payload = self.current_payload()
        after_history = [(row["id"], row["body"])
                         for row in self.case.provider.comments[100]]
        self.assertEqual(before_history, after_history[:len(before_history)])
        self.assertEqual(before_ref, after_payload["goal_context"])
        self.assertEqual(before_context, self.case.session.read(100, before_ref))
        self.assertEqual([101], before_context["content"]["depends_on"])
        remaining = self.discovery(other)
        self.assertEqual(dag.z._workflow.digest(other), remaining["submission"]["blocker_hash"])

    def test_wrong_stale_foreign_actor_and_required_fields_fail_closed(self):
        base = self.request()
        cases = {
            "wrong blocker": {**base, "blocker_hash": "sha256:" + "1" * 64},
            "stale context": {**base, "context_hash": "sha256:" + "2" * 64},
            "wrong actor": {**base, "actor": "worker-thread"},
            "foreign evidence": {**base, "evidence": self.evidence(goal=101)},
            "empty rationale": {**base, "rationale": ""},
            "empty basis": {**base, "resolution_basis": ""},
            "missing evidence": {**base, "evidence": []},
            "missing approval": {key: value for key, value in base.items()
                                 if key != "human_approval"},
        }
        for label, invalid in cases.items():
            with self.subTest(label=label):
                self.assert_rejected_without_write(invalid,
                    r"(?i)context|blocker|actor|root|evidence|goal|rationale|basis|approval|required")

    def test_previously_current_result_is_rejected_after_its_input_changes(self):
        request = self.request("stale-resolution-evidence")
        self.case.replace_spec("A newer exact specification invalidates prior understanding outputs.")
        self.assert_rejected_without_write(request, r"(?i)stale|current|result|output|evidence")

    def test_idless_blocker_works_but_duplicate_content_is_ambiguous(self):
        # The successful fixture blocker has no id and therefore establishes
        # digest identity support. Duplicate identical content must not be
        # resolved by list position.
        self.call(self.request())
        self.fresh_case()
        self.case.legacy_fields(100, blockers=[copy.deepcopy(self.blocker), copy.deepcopy(self.blocker)])
        self.case.migrate((100,))
        self.case.normal_setup(100)
        steps = self.case.session.checkpoint(100)
        candidates = [s for s in steps if (s.get("submission") or {}).get("operation") == "resolve_goal_blocker"]
        self.assertFalse(candidates, candidates)
        request = {
            "operation": "resolve_goal_blocker", "request_id": "ambiguous-blocker",
            "actor": "root-thread", "context_hash": self.current_payload()["goal_context"]["hash"],
            "blocker_hash": dag.z._workflow.digest(self.blocker), "rationale": "Exact duplicate.",
            "resolution_basis": "Root attestation.", "evidence": self.evidence(),
            "human_approval": {"approved_by": "requesting-user", "attribution": "Approved."},
        }
        self.assert_rejected_without_write(request, r"(?i)ambiguous|duplicate|blocker")

    def test_nonhuman_blocker_requires_no_fabricated_human_approval(self):
        self.fresh_case()
        blocker = {"status": "open", "category": "technical-unknown",
                   "question": "Verify compatibility against the current output"}
        self.case.legacy_fields(100, blockers=[blocker])
        self.case.migrate((100,))
        self.case.normal_setup(100)
        submission = copy.deepcopy(self.discovery(blocker)["submission"])
        self.assertNotIn("human_approval", submission)
        submission.update({
            "request_id": "resolve-technical-blocker", "actor": "root-thread",
            "rationale": "The current authenticated output verifies compatibility.",
            "resolution_basis": "Root inspected the cited current Result and output.",
            "evidence": self.evidence(),
        })
        _, event = self.resolved_event(self.call(submission))
        self.assertNotIn("human_approval", event["content"])

    def test_historical_context_without_stored_context_is_materialised_unchanged(self):
        self.fresh_case()
        self.case.legacy_fields(100, depends_on=[101], blockers=[copy.deepcopy(self.blocker)])
        self.case.publish_historical_v1_migration()
        envelope = dag.z.parse_managed_goal(self.case.provider.issues[100]["body"], 100)
        before = copy.deepcopy(self.case.session.read(100, envelope["payload"]))
        self.assertNotIn("goal_context", before)
        def observed_context():
            with mock.patch.object(dag.z, "GitHubGoalTransitionAdapter",
                                   return_value=self.case.provider):
                engine = dag.z.workflow_engine(self.case.fixture.repo,
                                               self.case.session.project,
                                               self.case.session.runtime)
            engine.adapter = self.case.provider
            return engine.node_snapshot(100)
        initial = observed_context()
        self.assertEqual({"difficulty": "S"}, initial["original_goal_context"]["metadata"])
        self.assertEqual({"difficulty": "S"}, initial["goal_context"]["metadata"])
        self.case.normal_setup(100)
        discovered = self.discovery()
        request = copy.deepcopy(discovered["submission"])
        request.update({
            "request_id": "historical-context-resolution", "actor": "root-thread",
            "rationale": "The exact approved design supersedes the historical requirement.",
            "resolution_basis": "Root attests the cited current approval resolves it.",
            "evidence": self.evidence(),
            "human_approval": {"approved_by": "requesting-user",
                               "attribution": "Approved the exact current design."},
        })
        before_history = [(row["id"], row["body"])
                          for row in self.case.provider.comments[100]]
        self.resolved_event(self.call(request))
        after_history = [(row["id"], row["body"])
                         for row in self.case.provider.comments[100]]
        self.assertEqual(before_history, after_history[:len(before_history)])
        after = self.current_payload()
        context_ref = after["goal_context"]
        context = self.case.session.read(100, context_ref)
        self.assertEqual(discovered["submission"]["context_hash"], context_ref["hash"])
        self.assertEqual({"version": 1, "depends_on": [101],
                          "blockers": [self.blocker], "metadata": {"difficulty": "S"}}, context["content"])
        resolved = observed_context()
        self.assertEqual({"difficulty": "S"}, resolved["original_goal_context"]["metadata"])
        self.assertEqual({"difficulty": "S"}, resolved["goal_context"]["metadata"])

    def test_exact_replay_is_stable_and_changed_payload_conflicts(self):
        request = self.request("stable-resolution-request")
        first = self.call(request)
        after_first = copy.deepcopy((self.case.provider.issues, self.case.provider.comments))
        replay = self.call(request)
        self.assertEqual(first, replay)
        self.assertEqual(after_first, (self.case.provider.issues, self.case.provider.comments))
        changed = copy.deepcopy(request)
        changed["rationale"] += " Changed after commit."
        self.assert_rejected_without_write(changed, r"(?i)request|replay|conflict|payload")

    def test_new_root_consumes_authenticated_historical_resolution(self):
        response = self.call(self.request("historical-root-resolution"))
        self.resolved_event(response)
        runtime = copy.deepcopy(self.case.session.runtime)
        runtime["root_id"] = "new-root-thread"
        resumed = dag.TaskSession(self.case.fixture.repo, self.case.session.project, runtime,
                                  self.case.provider, self.case.session.control)
        before = copy.deepcopy((self.case.provider.issues, self.case.provider.comments))
        steps = resumed.checkpoint(100)
        self.assertEqual(before, (self.case.provider.issues, self.case.provider.comments))
        self.assertFalse(any((step.get("submission") or {}).get("operation")
                             == "resolve_goal_blocker" for step in steps), steps)
        self.assertFalse(any("goal-context blocker" in str(step.get("reason", "")).lower()
                             for step in steps), steps)

    def test_forged_resolution_event_is_rejected_on_read(self):
        response = self.call(self.request("forge-resolution-event"))
        recorded, _event = self.resolved_event(response)
        reference = recorded.get("resolution") or recorded["event"]
        changed = False
        for row in self.case.provider.comments[100]:
            envelope = dag.z._comment_store.decode_envelope(row["body"])
            if not envelope:
                continue
            for artifact in envelope.get("artifacts", []):
                if artifact.get("hash") == reference["hash"]:
                    artifact["hash"] = "sha256:" + "f" * 64
                    row["body"] = dag.z._comment_store.encode_envelope(envelope)
                    changed = True
        self.assertTrue(changed, "resolution artifact must be stored in authenticated history")
        rejected = self.case.session.call(100, expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)resolution|artifact|checksum|receipt|provenance")

    def test_resolution_event_without_committed_receipt_is_rejected(self):
        response = self.call(self.request("missing-resolution-receipt"))
        recorded, _event = self.resolved_event(response)
        reference = recorded.get("resolution") or recorded["event"]
        envelope = dag.z.parse_managed_goal(self.case.provider.issues[100]["body"], 100)
        payload = copy.deepcopy(self.case.session.read(100, envelope["payload"]))
        payload["operational"]["receipts"] = [
            receipt for receipt in payload["operational"]["receipts"]
            if receipt.get("request") != "missing-resolution-receipt"
        ]
        self.assertIn(reference, payload["goal_context_resolutions"]["events"])
        self.case.replace_legacy_payload(envelope, payload)
        rejected = self.case.session.call(100, expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)resolution|receipt|request|authenticate")

    def test_committed_but_unconfirmed_response_recovers_from_exact_receipt(self):
        request = self.request("resolution-response-lost")
        update = self.case.provider.update_issue
        published = False

        def lose_response(number, payload):
            nonlocal published
            result = update(number, payload)
            if not published:
                published = True
                raise OSError("response lost after provider commit")
            return result

        with mock.patch.object(self.case.provider, "update_issue", side_effect=lose_response):
            uncertain = self.call(request, expected=None)
        self.assertTrue(uncertain.get("next_steps"), uncertain)
        recovered = self.call(request)
        _, event = self.resolved_event(recovered)
        self.assertEqual("resolution-response-lost", event["provenance"]["request_id"])
        journal = self.current_payload()["goal_context_resolutions"]["events"]
        self.assertEqual(1, len(journal), journal)

    def test_active_lease_and_closed_goal_reject_without_mutation(self):
        self.fresh_case()
        self.case.legacy_fields(100, blockers=[copy.deepcopy(self.blocker)])
        self.case.migrate((100,))
        understand = self.case.session.acquire("understand")
        tasks = [{"goal": 100, "node": name, "item": None, "generation": 1}
                 for name in ("test_design", "implement")]
        allocation = {"allocations": {task["node"]: {
            "task": task, "owned": [], "consumed": ["product.txt"]} for task in tasks}}
        self.case.session.finish(understand, {
            "design": "Review the unchanged synthetic baseline.", "allocation": allocation})
        request = self.request()
        active = self.case.session.acquire("review_understanding")
        self.assertTrue(active["lease"]["token"])
        self.assert_rejected_without_write(request, r"(?i)lease|owner|active|recover")

        review = {"decision": "approved", "report": "Exact fixture review."}
        permit = {"manifest": self.case.result("understand")[1]["outputs"]["allocation"],
                  "tasks": tasks, "policy": dag.content_hash(self.case.session.project["policy"]),
                  "decision": "approved"}
        self.case.session.finish(active, {"review": review, "authorization": permit})
        self.case.provider.issues[100]["state"] = "closed"
        closed = copy.deepcopy((self.case.provider.issues, self.case.provider.comments))
        response = self.call(request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)closed|archiv|reopen")
        self.assertEqual(closed, (self.case.provider.issues, self.case.provider.comments))

    def test_preview_is_read_only_and_resolution_does_not_bypass_phase_gates(self):
        before = copy.deepcopy((self.case.provider.issues, self.case.provider.comments))
        preview = self.case.session.call(100, intent="preview")
        self.assertEqual(before, (self.case.provider.issues, self.case.provider.comments))
        self.assertTrue(any((s.get("submission") or {}).get("operation") == "resolve_goal_blocker"
                            for s in preview["next_steps"]), preview)

        response = self.call(self.request())
        self.resolved_event(response)
        steps = self.case.session.checkpoint(100)
        self.assertTrue(any(s.get("node", {}).get("node") == "test_design" for s in steps), steps)
        self.assertFalse(any(s.get("node", {}).get("node") == "implement"
                             and s.get("kind") == "execute" for s in steps), steps)
        self.assertFalse(any(s.get("kind") in {"integrate", "publish", "publication"}
                             for s in response["next_steps"]), response)


if __name__ == "__main__":
    unittest.main()
