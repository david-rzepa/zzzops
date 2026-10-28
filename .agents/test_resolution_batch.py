"""Resolution batching through the public CLI and immutable provider journal."""
import copy
import hashlib
import json
from pathlib import Path
from unittest import mock
import unittest

import test_evidence_dag_journeys as dag
import test_static_workflow_public as static_public


class ResolutionBatchPublicTests(dag.DagFixture):
    record_phase_finding = static_public.StaticWorkflowPublicTests.record_phase_finding
    acquire_prefix = static_public.StaticWorkflowPublicTests.acquire_prefix
    graph_ref = static_public.StaticWorkflowPublicTests.graph_ref

    def setUp(self):
        super().setUp()
        producer = dag.task('produce')
        producer['inputs'] = {'request': dag.spec_input()}
        reviewer = dag.task('review', ['produce'])
        reviewer['inputs'] = {'subject': dag.subject_input('produce')}
        reviewer['inputs']['subject']['producer']['node']['goal'] = '#this'
        reviewer['independent_of'] = [{**dag.selector('produce'), 'goal': '#this'}]
        reviewer['outputs'] = {'value': {'type': 'review_decision', 'schema': {
            'kind': 'object', 'fields': {
                'decision': {'kind': 'enum', 'values': ['approved', 'changes_requested']},
                'report': {'kind': 'string'}}}}}
        self.install({'nodes': [producer, reviewer], 'task_sets': [],
                      'terminals': [dag.selector('review')]})

    def admit_rejection(self, review_name, item, finding_id, *, revision=1, supersedes=None):
        original = self.result('produce')[1]
        interpret = self.acquire_prefix('gc_interpret_', item=item, actor='root-thread')
        self.session.finish(interpret, {'value': {
            'id': finding_id, 'revision': revision,
            'source': self.produced(review_name, item=item),
            'subjects': [original['outputs']['value']], 'target': dag.scope('produce'),
            'request': 'Repair ' + finding_id, 'rationale': 'Exact independently observed defect.',
            'supersedes': supersedes}})
        finding = self.produced(interpret['node']['node'], item=item)
        admit = self.acquire_prefix('gc_admit_', item=item, actor='root-thread')
        self.session.finish(admit, {'value': {
            'finding': finding, 'target_inputs': original['inputs'],
            'authority': self.result(interpret['node']['node'], item)[0],
            'applicability': 'applicable', 'rationale': 'Correction is in scope.'},
            'transfer': None if supersedes is None else {
                'prior': supersedes, 'replacement': finding, 'coverage': 'carried',
                'authority': self.result(interpret['node']['node'], item)[0],
                'coverage_evidence': self.result(interpret['node']['node'], item)[0]}})
        return finding

    def four_findings_three_overlapping_routes(self):
        self.produce()
        review = self.session.acquire('review', actor='ordinary-reviewer')
        self.session.finish(review, {'value': {
            'decision': 'changes_requested', 'report': 'First exact defect.'}})
        findings = [self.admit_rejection('review', None, 'ordinary')]
        self.session.finish(self.session.acquire('produce'), {'value': 'correction-ordinary'})
        late = []
        for index in range(3):
            result, value = self.result('produce')
            response = self.record_phase_finding(result, value['outputs']['value'],
                'event-' + str(index), 'late-' + str(index))
            event = response['next_steps'][0]
            # Select the exact newly recorded event, not an earlier review that
            # became stale when a subsequent correction changed its subject.
            item = dag.z._static_workflow.event_key({'id': 'late-' + str(index), 'revision': 1})
            name = dag.z._static_workflow.review_name('produce', 'value')
            work = self.session.acquire(name, item=item, actor='late-reviewer-' + str(index))
            self.session.finish(work, {'value': {
                'decision': 'changes_requested', 'report': 'Exact late defect ' + str(index)}})
            findings.append(self.admit_rejection(name, item, 'late-' + str(index)))
            late.append((name, item))
            self.session.finish(self.session.acquire('produce'), {'value': 'correction-' + str(index)})
        for name, item in [('review', None), *late]:
            work = self.session.acquire(name, item=item, actor='final-reviewer-' + str(item))
            self.session.finish(work, {'value': {
                'decision': 'approved', 'report': 'Inspected this exact final corrected subject.'}})
        for step in self.session.ready():
            if step['node']['node'].startswith('gc_retain_'):
                work = self.session.acquire(step['node']['node'], actor='root-thread')
                self.session.finish(work, {'value': {'items': dict(zip(
                    ['ordinary', 'late-0', 'late-1', 'late-2'], findings)),
                    'rationale': 'Retain all four exact admitted finding identities.'}})
        return findings

    def test_four_unique_findings_and_three_overlapping_routes_offer_one_batch(self):
        findings = self.four_findings_three_overlapping_routes()
        self.assertEqual(4, len({ref['hash'] for ref in findings}))
        steps = self.session.ready()
        resolvers = [step for step in steps
                     if step['node']['node'].startswith(('gc_resolve_', 'sw_resolve_'))]
        self.assertEqual(1, len(resolvers),
            'Four unique admitted findings must offer one batch, not ordinary plus late per-finding leases: '
            + repr([step['node'] for step in resolvers]))
        before = (len(self.provider.updates), len(self.provider.comments[100]), len(self.session.calls))
        work, manifest = self.acquire_batch()
        result = self.session.finish(work, self.batch_output(manifest), 'measured-batch-submit')
        calls = self.session.calls[before[2]:]
        self.assertEqual(1, sum(row['operation'] == 'start' for row in calls))
        self.assertEqual(1, sum(row['operation'] == 'submit' for row in calls))
        self.assertEqual(3, len(self.provider.updates) - before[0])
        self.assertEqual(3, len(self.provider.comments[100]) - before[1])
        self.assertTrue(all(len(row['body']) <= dag.z._workflow.comment_store.MAX_COMMENT_CHARACTERS
                            for row in self.provider.comments[100][before[1]:]))
        artifact = self.read_blob(result['submitted']['result'])
        stored = self.read_blob(artifact['content']['outputs']['value'])['content']['entries']
        self.assertEqual({ref['hash'] for ref in findings}, {row['finding']['hash'] for row in stored.values()})
        self.measured_counts = {'unique_findings': len(findings), 'resolver_leases': 1,
            'submit_transactions': 1, 'body_writes': len(self.provider.updates) - before[0],
            'comment_writes': len(self.provider.comments[100]) - before[1],
            'max_comment_characters': max(len(row['body']) for row in self.provider.comments[100][before[1]:])}

    def acquire_batch(self):
        steps = [step for step in self.session.ready()
                 if step['node']['node'].startswith('gc_resolve_batch_')]
        self.assertEqual(1, len(steps), steps)
        step = steps[0]
        work = self.session.acquire(step['node']['node'], item=step['node']['item'],
                                    actor='resolution-assessor')
        binding = next(row for row in work['input_envelope']['inputs'] if row['name'] == 'batch')
        manifest = dag.z._phase_evidence.selected_path(self.read_blob(binding['source'])['content'], binding['path'])
        return work, manifest

    def batch_output(self, manifest, unresolved=()):
        return {'value': {'entries': {key: {
            'finding': entry['finding'], 'subjects': [manifest['subject']],
            'reviewer_result': entry['reviews'][0],
            'decision': 'unresolved' if entry['id'] in unresolved else 'resolved',
            'rationale': 'Independently assessed exact correction for ' + entry['id']}
            for key, entry in manifest['findings'].items()}}}

    def test_mixed_batch_is_atomic_replayable_and_does_not_reoffer_unchanged_debt(self):
        findings = self.four_findings_three_overlapping_routes()
        work, manifest = self.acquire_batch()
        self.assertEqual({ref['hash'] for ref in findings},
                         {entry['finding']['hash'] for entry in manifest['findings'].values()})
        acquisition_revision = work['lease']['acquisition']['expected_goal_revision']
        self.session.call(100, {'operation': 'renew', 'node': work['node'],
            'lease': work['lease']['token'], 'actor': work['bound_actor'], 'request_id': 'renew-before-batch-submit'})
        self.assertGreater(self.payload()[0]['revision'], acquisition_revision)
        output = self.batch_output(manifest, unresolved={'late-2'})
        large_rationale = ''.join(hashlib.sha256(str(index).encode()).hexdigest() for index in range(2500))
        first_key = next(iter(output['value']['entries']))
        output['value']['entries'][first_key]['rationale'] = large_rationale
        before_comments = len(self.provider.comments[100])
        request = self.session.submission(work, output, 'mixed-resolution')
        response = self.session.call(100, request)
        result_ref = response['submitted']['result']
        self.assertEqual('resolution_batch', self.read_blob(
            self.read_blob(result_ref)['content']['outputs']['value'])['type'])
        artifact = self.read_blob(self.read_blob(result_ref)['content']['outputs']['value'])
        self.assertEqual(large_rationale, artifact['content']['entries'][first_key]['rationale'])
        self.assertGreater(len(self.provider.comments[100]) - before_comments, 1)
        self.assertTrue(all(len(row['body']) <= dag.z._workflow.comment_store.MAX_COMMENT_CHARACTERS
                            for row in self.provider.comments[100][before_comments:]))
        replay = self.session.call(100, request)
        self.assertEqual(result_ref, replay['submitted']['result'])
        self.assertFalse(any(step.get('node', {}).get('node', '').startswith('gc_resolve_')
                             for step in response['next_steps']), response)
        self.assertFalse(any(step['node']['node'].startswith('gc_resolve_')
                             for step in self.session.ready()))
        self.assertIn('late-2', repr(self.session.checkpoint(100)))

    def test_raw_duplicate_entry_keys_rejected_directly_and_after_working_input_freeze(self):
        self.four_findings_three_overlapping_routes()
        work, manifest = self.acquire_batch()
        request = self.session.submission(work, self.batch_output(manifest), 'raw-duplicate')
        key = next(iter(request['outputs']['value']['entries']))
        entry = request['outputs']['value']['entries'][key]
        encoded = json.dumps(request)
        needle = json.dumps(key) + ': ' + json.dumps(entry)
        raw = encoded.replace(needle, needle + ', ' + needle, 1).encode()
        self.assertNotEqual(encoded.encode(), raw)
        original = Path.read_text
        def invoke(exact):
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            def read(path, *args, **kwargs):
                if path == self.session.control / 'input.json': return exact.decode()
                return original(path, *args, **kwargs)
            with mock.patch.object(Path, 'read_text', read):
                response = self.session.call(100, request, expected=2)
            self.assertEqual('repair', response['next_steps'][0]['kind'])
            self.assertIn('Duplicate', response['next_steps'][0]['reason'])
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
            return response
        invoke(raw)
        store = dag.z._working_inputs.WorkingInputStore(self.session.repo,
            repository='example/repo', owner='root-thread')
        descriptor = store.open('goal:100', 'execute')
        Path(descriptor['path']).write_bytes(raw)
        frozen = store.freeze('goal:100', 'execute', 'raw-frozen-duplicate', {'operation': 'submit'})
        self.assertEqual(raw, Path(frozen['snapshot']).read_bytes())
        seen = []
        def sender(request_id, exact):
            seen.append(exact)
            invoke(exact)
            return {'receipt': {'request_id': request_id}}
        store.dispatch('raw-frozen-duplicate', sender)
        self.assertEqual([raw], seen)
        self.assertIn('submitted', self.session.finish(work, self.batch_output(manifest), 'valid-raw-control'))

    def test_batch_rejects_each_invalid_entry_before_any_provider_write(self):
        self.four_findings_three_overlapping_routes()
        work, manifest = self.acquire_batch()
        valid = self.batch_output(manifest)
        first, second = list(valid['value']['entries'])[:2]
        cases = {}
        omitted = copy.deepcopy(valid); del omitted['value']['entries'][first]
        cases['omitted'] = omitted
        extra = copy.deepcopy(valid); extra['value']['entries']['duplicate'] = copy.deepcopy(extra['value']['entries'][first])
        cases['extra'] = extra
        swapped = copy.deepcopy(valid); swapped['value']['entries'][first]['finding'] = swapped['value']['entries'][second]['finding']
        cases['swapped'] = swapped
        stale = copy.deepcopy(valid); stale['value']['entries'][first]['subjects'] = [self.read_blob(
            manifest['findings'][first]['finding'])['content']['subjects'][0]]
        cases['stale_subject'] = stale
        forged = copy.deepcopy(valid); forged['value']['entries'][first]['reviewer_result'] = dag.REF
        cases['forged_reviewer'] = forged
        empty = copy.deepcopy(valid); empty['value']['entries'][first]['rationale'] = ' '
        cases['empty_rationale'] = empty
        for label, output in cases.items():
            with self.subTest(label=label):
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                request = self.session.submission(work, output, 'reject-' + label)
                response = self.session.call(100, request, expected=2)
                self.assertEqual('repair', response['next_steps'][0]['kind'])
                self.assertIn('Resolution', response['next_steps'][0]['reason'])
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        response = self.session.finish(work, valid, request_id='valid-after-rejections')
        self.assertIn('submitted', response)
        self.assertFalse(any(step.get('node', {}).get('node', '').startswith('gc_resolve_')
                             for step in self.session.checkpoint(100)))

    def test_changed_subject_closes_old_event_debt_and_batches_only_current_unresolved(self):
        self.four_findings_three_overlapping_routes()
        work, manifest = self.acquire_batch()
        self.session.finish(work, self.batch_output(manifest, unresolved={'late-2'}))
        old_result, old_subject = self.result('produce')
        self.record_phase_finding(old_result, old_subject['outputs']['value'], 'new-event', 'new-defect')
        item = dag.z._static_workflow.event_key({'id': 'new-defect', 'revision': 1})
        name = dag.z._static_workflow.review_name('produce', 'value')
        review = self.session.acquire(name, item=item, actor='new-event-reviewer')
        self.session.finish(review, {'value': {'decision': 'changes_requested', 'report': 'New exact defect.'}})
        self.admit_rejection(name, item, 'new-defect')
        self.session.finish(self.session.acquire('produce'), {'value': 'new independently reviewable correction'})
        offered = self.session.ready()
        old_closed_items = {dag.z._static_workflow.event_key({'id': 'late-' + str(index), 'revision': 1})
                            for index in (0, 1)}
        self.assertFalse(any(step['node'].get('item') in old_closed_items for step in offered))
        for review_name, event_item in [('review', None),
                (name, dag.z._static_workflow.event_key({'id': 'late-2', 'revision': 1})), (name, item)]:
            review = self.session.acquire(review_name, item=event_item, actor='new-subject-reviewer-' + str(event_item))
            self.session.finish(review, {'value': {'decision': 'approved', 'report': 'Verified exact changed subject.'}})
        next_work, next_manifest = self.acquire_batch()
        self.assertEqual({'late-2', 'new-defect'}, {entry['id'] for entry in next_manifest['findings'].values()})
        self.assertNotEqual(work['node']['item'], next_work['node']['item'])

    def load_legacy(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/resolution_batch_legacy.json').read_text())
        self.assertEqual('d5c9943', fixture['generator_commit'])
        self.session.project['policy'] = copy.deepcopy(fixture['policy'])
        self.provider.issues[100] = copy.deepcopy(fixture['issue'])
        self.provider.comments[100] = copy.deepcopy(fixture['comments'])
        return fixture

    def test_pre_batch_public_journal_adopts_without_rewriting_and_keeps_old_resolution_closed(self):
        fixture = self.load_legacy()
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        steps = self.session.checkpoint(100)
        self.assertFalse(any(step['kind'] in ('execute', 'policy_dag_cutover') for step in steps), steps)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertEqual('result', self.read_blob(fixture['result'])['type'])
        original_result, original = self.result('produce')
        self.record_phase_finding(original_result, original['outputs']['value'], 'post-legacy-event', 'post-legacy-defect')
        item = dag.z._static_workflow.event_key({'id': 'post-legacy-defect', 'revision': 1})
        name = dag.z._static_workflow.review_name('produce', 'value')
        review = self.session.acquire(name, item=item, actor='post-legacy-reviewer')
        self.session.finish(review, {'value': {'decision': 'changes_requested', 'report': 'A distinct newly observed defect.'}})
        self.admit_rejection(name, item, 'post-legacy-defect')
        self.session.finish(self.session.acquire('produce'), {'value': 'new subject after historical resolution'})
        for review_name, event_item in [('review', None), (name, item)]:
            review = self.session.acquire(review_name, item=event_item, actor='post-legacy-correction-reviewer-' + str(event_item))
            self.session.finish(review, {'value': {'decision': 'approved', 'report': 'Inspected this new exact subject.'}})
        _, manifest = self.acquire_batch()
        self.assertEqual({'post-legacy-defect'}, {entry['id'] for entry in manifest['findings'].values()})
        self.assertEqual(fixture['comments'], self.provider.comments[100][:len(fixture['comments'])])

    def test_owned_legacy_singular_renewal_preserves_acquisition_revision_and_committed_closure(self):
        fixture = self.load_legacy()
        store = dag.z._workflow.comment_store
        index = store.ArtifactIndex(fixture['comments'])
        transaction = next(envelope for envelope in index.envelopes
            if (envelope.get('context') or {}).get('request_id') == 'legacy-resolution-submit')
        source = transaction['context']['source_envelope']
        payload = index.resolve(source['payload']['hash'])[0]
        lease = payload['operational']['leases'][0]
        result = index.resolve(fixture['result']['hash'])[0]['content']
        outputs = {slot: index.resolve(ref['hash'])[0]['content'] for slot, ref in result['outputs'].items()}
        self.provider.issues[100]['body'] = '<!-- zzzops-goal\n' + json.dumps(source) + '\nzzzops-goal -->'
        self.provider.comments[100] = [row for row in fixture['comments']
            if (store.decode_envelope(row['body']) or {}).get('transaction') != transaction['transaction']]
        self.session.call(100, {'operation': 'renew', 'node': lease['node'], 'lease': lease['token'],
            'actor': lease['worker'], 'request_id': 'legacy-renew-before-submit'})
        self.assertGreater(self.payload()[0]['revision'], lease['acquisition']['expected_goal_revision'])
        # Replay the captured clean external checkout observation; historical
        # journal bytes and host acceptance validation remain unmodified.
        pinned = lease['acquisition']['read_commit']
        def git_observation(command, *args, **kwargs):
            if command in (['git', 'rev-parse', 'HEAD'], ['git', 'rev-parse', '--verify', pinned + '^{tree}']):
                return dag.subprocess.CompletedProcess(command, 0, stdout=pinned + '\n', stderr='')
        self.session.provider_command = git_observation
        with mock.patch.object(dag.z._workflow.managed_worktrees, 'inspect_attempt_worktree',
                               return_value={'status': 'clean', 'head': pinned}):
            response = self.session.call(100, {'operation': 'submit', 'node': lease['node'],
                'lease': lease['token'], 'actor': lease['worker'], 'request_id': 'legacy-renewed-submit',
                'outputs': outputs})
        self.assertIn('submitted', response)
        self.assertFalse(any(step.get('kind') in ('execute', 'blocker', 'repair')
                             for step in self.session.checkpoint(100)))

    def test_distinct_recover_receipts_with_identical_response_preserve_historical_closure(self):
        self.load_legacy()
        reference, original = self.result('produce')
        self.record_phase_finding(reference, original['outputs']['value'], 'recovery-event', 'recovery-event')
        item = dag.z._static_workflow.event_key({'id': 'recovery-event', 'revision': 1})
        name = dag.z._static_workflow.review_name('produce', 'value')
        for attempt in range(2):
            work = self.session.acquire(name, item=item, actor='stopped-reviewer-' + str(attempt))
            self.session.call(100, {'operation': 'recover', 'node': work['node'],
                'lease': work['lease']['token'], 'actor': work['bound_actor'], 'worker_status': 'stopped',
                'evidence': 'Synthetic exact worker terminal observation', 'request_id': 'identical-recover-' + str(attempt)})
        steps = self.session.checkpoint(100)
        self.assertFalse(any(step['kind'] in ('blocker', 'repair') for step in steps), steps)
        self.assertTrue(any(step.get('kind') == 'execute' and step.get('node', {}).get('node') == name for step in steps), steps)
        self.assertFalse(any(step.get('node', {}).get('node', '').startswith('gc_resolve_batch_') for step in steps))
        receipts = [row for row in self.payload()[1]['operational']['receipts']
                    if row['request'].startswith('identical-recover-')]
        self.assertEqual(2, len(receipts))
        self.assertEqual(receipts[0]['result'], receipts[1]['result'])
        pristine = copy.deepcopy((self.provider.issues, self.provider.comments))
        store = dag.z._workflow.comment_store
        index = store.ArtifactIndex(self.provider.comments[100])
        transaction = next(row for row in index.envelopes
            if row.get('context', {}).get('request_id') == 'identical-recover-1')
        selected = [row for row in index.envelopes if row['transaction'] == transaction['transaction']]
        records = [record for row in selected for record in row['artifacts']]
        for mutation in ('request_id', 'request_hash', 'ambiguous_identity'):
            with self.subTest(mutation=mutation):
                self.provider.issues, self.provider.comments = copy.deepcopy(pristine)
                context = copy.deepcopy(transaction['context'])
                identity = transaction['transaction']
                if mutation == 'request_id': context['request_id'] = 'different-request'
                elif mutation == 'request_hash': context['request_hash'] = 'sha256:' + 'f' * 64
                else: identity = 'sha256:' + hashlib.sha256(b'ambiguous transaction').hexdigest()
                bodies = store.pack_envelopes({'goal': 100, 'transaction': identity, 'context': context}, records)
                if mutation == 'ambiguous_identity':
                    for body in bodies: self.provider.create_issue_comment(100, body)
                else:
                    positions = [i for i, row in enumerate(self.provider.comments[100])
                        if (store.decode_envelope(row['body']) or {}).get('transaction') == identity]
                    self.assertEqual(len(positions), len(bodies))
                    for i, body in zip(positions, bodies): self.provider.comments[100][i]['body'] = body
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                blocked = self.session.checkpoint(100)
                self.assertTrue(any(step.get('kind') == 'blocker' and 'committed submit lineage' in step.get('reason', '')
                                    for step in blocked), blocked)
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.provider.issues, self.provider.comments = copy.deepcopy(pristine)
        self.assertFalse(any(step['kind'] in ('blocker', 'repair') for step in self.session.checkpoint(100)))

    def test_batch_lost_body_response_is_observed_and_replayed_once(self):
        self.four_findings_three_overlapping_routes()
        work, manifest = self.acquire_batch()
        request = self.session.submission(work, self.batch_output(manifest), 'batch-lost-body-response')
        before_comments, before_updates = len(self.provider.comments[100]), len(self.provider.updates)
        original = self.provider.update_issue
        failed = []
        def lost(*args, **kwargs):
            result = original(*args, **kwargs)
            if not failed:
                failed.append(True)
                raise dag.z.GoalTransitionProviderError('Synthetic provider body write committed; response lost')
            return result
        with mock.patch.object(self.provider, 'update_issue', side_effect=lost):
            response = self.session.call(100, request)
        self.assertTrue(failed)
        replay = self.session.call(100, request)
        self.assertEqual(response['submitted']['result'], replay['submitted']['result'])
        self.assertEqual(before_updates + 1, len(self.provider.updates))
        self.assertEqual(before_comments + 1, len(self.provider.comments[100]))
        self.assertFalse(self.payload()[1]['operational']['leases'])

    def test_historical_resolution_rejects_orphan_disconnected_and_changed_source_lease(self):
        fixture = self.load_legacy()
        pristine = copy.deepcopy((self.provider.issues, self.provider.comments))
        store = dag.z._workflow.comment_store
        index = store.ArtifactIndex(fixture['comments'])
        transaction = next(envelope for envelope in index.envelopes
                           if (envelope.get('context') or {}).get('request_id') == 'legacy-resolution-submit')
        context = transaction['context']
        # A fully uploaded but uncommitted transaction is custody, not closure.
        self.provider.issues[100]['body'] = '<!-- zzzops-goal\n' + json.dumps(context['source_envelope']) + '\nzzzops-goal -->'
        orphan = self.session.checkpoint(100)
        self.assertTrue(any(step.get('kind') == 'await_worker' for step in orphan), orphan)
        self.assertFalse(any(step.get('kind') == 'complete' for step in orphan))
        self.provider.issues, self.provider.comments = copy.deepcopy(pristine)
        envelope = copy.deepcopy(context['target_envelope']); envelope['revision'] += 1
        self.provider.issues[100]['body'] = '<!-- zzzops-goal\n' + json.dumps(envelope) + '\nzzzops-goal -->'
        disconnected = self.session.call(100)
        self.assertEqual('blocker', disconnected['next_steps'][0]['kind'])
        self.assertIn('committed submit lineage', repr(disconnected))
        self.provider.issues, self.provider.comments = copy.deepcopy(pristine)
        for mutation, reason in [('worker', 'bound worker/acquisition'),
                                 ('evidence', 'append exactly one Result'),
                                 ('prefix', 'prefix extension'),
                                 ('removal', 'remove exactly its own lease')]:
            self.provider.issues, self.provider.comments = copy.deepcopy(pristine)
            source = index.resolve(context['source_envelope']['payload']['hash'])[0]
            if mutation == 'worker': source['operational']['leases'][0]['worker'] = 'forged-worker'
            elif mutation == 'evidence': source['evidence'].pop()
            elif mutation == 'prefix': source['operational']['receipts'].pop()
            else:
                extra = copy.deepcopy(source['operational']['leases'][0])
                extra['node']['node'] = 'produce'
                extra['token'] = 'different-consumed-lease'
                extra['attempt'] = 'different-attempt'
                source['operational']['leases'].append(extra)
            def publish(value):
                reference = self.blob(value)
                return {'hash': reference['hash'], 'uri': 'zzzops:owner/repo:goal:100:' + reference['hash']}
            forged_source = publish(source)
            changed_context = copy.deepcopy(context)
            changed_context['source_envelope']['payload'] = forged_source
            # Keep the forged outer transaction internally consistent so that the
            # source-lease guard, rather than a checksum/continuation mismatch, fires.
            response = index.resolve(context['response']['hash'])[0]
            response['source_envelope'] = changed_context['source_envelope']
            response_ref = publish(response)
            target_payload = index.resolve(context['target_envelope']['payload']['hash'])[0]
            target_payload['operational']['receipts'][-1]['result'] = response_ref
            target_ref = publish(target_payload)
            entry = index.resolve(response['entry_candidate_payload']['hash'])[0]
            entry['operational']['receipts'].append(target_payload['operational']['receipts'][-1])
            changed_context.update(response=response_ref, continuation=response_ref,
                                   payload=target_ref, entry_payload=publish(entry))
            changed_context['target_envelope']['payload'] = target_ref
            self.provider.issues[100]['body'] = '<!-- zzzops-goal\n' + json.dumps(changed_context['target_envelope']) + '\nzzzops-goal -->'
            selected = [envelope for envelope in index.envelopes
                        if envelope['transaction'] == transaction['transaction']]
            records = [record for envelope in selected for record in envelope['artifacts']]
            bodies = store.pack_envelopes({'goal': 100, 'transaction': transaction['transaction'],
                                          'context': changed_context}, records)
            comments = self.provider.comments[100]
            positions = [position for position, comment in enumerate(comments)
                         if (store.decode_envelope(comment['body']) or {}).get('transaction') == transaction['transaction']]
            self.assertEqual(len(positions), len(bodies))
            for position, body in zip(positions, bodies): comments[position]['body'] = body
            changed = self.session.call(100)
            self.assertEqual('blocker', changed['next_steps'][0]['kind'])
            self.assertIn(reason, repr(changed))
        self.provider.issues, self.provider.comments = copy.deepcopy(pristine)
        self.assertFalse(any(step.get('kind') == 'execute' for step in self.session.checkpoint(100)))

    def test_competing_batch_owner_and_stopped_recovery_cannot_duplicate_outcomes(self):
        self.four_findings_three_overlapping_routes()
        offered = next(step for step in self.session.ready() if step['node']['node'].startswith('gc_resolve_batch_'))
        work, manifest = self.acquire_batch()
        receipt = json.loads(Path(offered['policy']['path']).read_text())['policy_receipt']
        competing = {**offered['start'], 'policy_receipt': receipt, 'request_id': 'competing-batch-start'}
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        rejected = self.session.call(100, competing, expected=2)
        self.assertRegex(repr(rejected), r'(?i)lease|owned|ready|owner')
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        with mock.patch.object(dag.z._workflow.time, 'time', return_value=work['lease']['expires_at'] + 1):
            step = next(step for step in self.session.checkpoint(100)
                        if 'recovery_contract' in step or step.get('kind') == 'recover')
            recovery = copy.deepcopy(step.get('submission', step.get('recovery_contract')))
            recovery.update(worker_status='stopped', evidence='Synthetic provider reports this exact worker stopped.',
                            request_id='recover-stopped-batch')
            self.session.call(100, recovery)
        replacement, replacement_manifest = self.acquire_batch()
        self.assertEqual(manifest, replacement_manifest)
        self.assertNotEqual(work['lease']['token'], replacement['lease']['token'])
        stale = self.session.submission(work, self.batch_output(manifest), 'stopped-worker-submit')
        self.session.call(100, stale, expected=2)
        response = self.session.finish(replacement, self.batch_output(replacement_manifest), 'recovered-batch-submit')
        self.assertIn('submitted', response)
        batch_results = [self.read_blob(ref) for ref in self.payload()[1]['evidence']
                         if self.read_blob(ref)['content']['node']['node'].startswith('gc_resolve_batch_')]
        self.assertEqual(1, len(batch_results))

    def test_member_scope_batch_preserves_exact_item_generation_and_unrelated_event(self):
        static_public.StaticWorkflowPublicTests.test_member_late_finding_uses_exact_item_generation_and_normal_correction_route(self)
        name = dag.z._static_workflow.review_name('investigate', 'value')
        for identity in ('member-alpha', 'member-beta'):
            item = dag.z._static_workflow.event_key({'id': identity, 'revision': 1})
            work = self.session.acquire(name, item=item, actor='member-batch-reviewer-' + identity)
            self.session.finish(work, {'value': {'decision': 'approved', 'report': 'Inspected the exact current member subject.'}})
        work, manifest = self.acquire_batch()
        self.assertEqual({'node': 'investigate', 'output': 'value', 'expansion': 'buckets',
                          'item': 'alpha', 'generation': 1}, manifest['target'])
        self.assertEqual({'member-alpha'}, {entry['id'] for entry in manifest['findings'].values()})
        self.session.finish(work, self.batch_output(manifest))
        self.assertFalse(any(step['node']['node'].startswith('gc_resolve_') for step in self.session.ready()))

    def test_new_revision_of_resolved_finding_creates_new_exact_obligation(self):
        fixture = self.load_legacy()
        result, current = self.result('produce')
        self.record_phase_finding(result, current['outputs']['value'], 'revise-legacy', 'legacy-finding')
        item = dag.z._static_workflow.event_key({'id': 'legacy-finding', 'revision': 1})
        name = dag.z._static_workflow.review_name('produce', 'value')
        work = self.session.acquire(name, item=item, actor='revision-reviewer')
        self.session.finish(work, {'value': {'decision': 'changes_requested', 'report': 'New exact finding revision.'}})
        self.admit_rejection(name, item, 'legacy-finding', revision=2, supersedes=fixture['finding'])
        self.session.finish(self.session.acquire('produce'), {'value': 'revision two correction'})
        for review_name, event_item in [('review', None), (name, item)]:
            work = self.session.acquire(review_name, item=event_item, actor='revision-two-reviewer-' + str(event_item))
            self.session.finish(work, {'value': {'decision': 'approved', 'report': 'Reviewed the exact second revision correction.'}})
        work, manifest = self.acquire_batch()
        self.assertEqual([('legacy-finding', 2)], [(entry['id'], entry['revision']) for entry in manifest['findings'].values()])
        self.assertNotEqual(fixture['finding'], next(iter(manifest['findings'].values()))['finding'])
        self.session.finish(work, self.batch_output(manifest))

    def test_changed_input_during_owned_batch_rejects_stale_submit_and_preserves_recovery(self):
        self.four_findings_three_overlapping_routes()
        old_work, old_manifest = self.acquire_batch()
        self.replace_spec('Synthetic external request revision while the exact batch remains owned.')
        steps = self.session.checkpoint(100)
        owned = next(step for step in steps if step.get('node') == old_work['node'])
        self.assertEqual('await_worker', owned['kind'])
        self.assertIn('recovery_contract', owned)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        rejected = self.session.call(100, self.session.submission(
            old_work, self.batch_output(old_manifest), 'stale-covered-set'), expected=2)
        self.assertRegex(repr(rejected), r'(?i)stale|current|input')
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        recovery = {**owned['recovery_contract'], 'request_id': 'recover-stale-covered-set',
                    'worker_status': 'stopped', 'evidence': 'Exact synthetic old worker is stopped.'}
        self.session.call(100, recovery)
        self.assertFalse(self.payload()[1]['operational']['leases'])

    def test_changed_required_context_reoffers_only_unresolved_same_subject_opportunity(self):
        graph = copy.deepcopy(self.graph)
        graph['nodes'].append(dag.task('authority_context'))
        dag.z._graph_compiler._append_static(graph, 'produce', 'value', 'review', 'value')
        resolver = graph['task_sets'][0]['template']
        resolver['inputs']['authority_context'] = dag.subject_input('authority_context')
        resolver['inputs']['authority_context']['producer']['node']['goal'] = '#this'
        self.install(graph)
        self.produce()
        self.session.finish(self.session.acquire('authority_context'), {'value': 'context one'})
        self.session.finish(self.session.acquire('review', actor='initial-reviewer'),
                            {'value': {'decision': 'approved', 'report': 'Inspected exact subject.'}})
        def late_debt(target, identifier):
            source, original = self.result(target)
            self.record_phase_finding(source, original['outputs']['value'], identifier, identifier,
                target={'node': target, 'output': 'value'})
            item = dag.z._static_workflow.event_key({'id': identifier, 'revision': 1})
            name = dag.z._static_workflow.review_name(target, 'value')
            self.session.finish(self.session.acquire(name, item=item, actor='reviewer-' + identifier),
                {'value': {'decision': 'changes_requested', 'report': 'Exact context correction.'}})
            interpret = self.acquire_prefix('gc_interpret_', item=item, actor='root-thread')
            self.session.finish(interpret, {'value': {'id': identifier, 'revision': 1,
                'source': self.produced(name, item=item), 'subjects': [original['outputs']['value']],
                'target': dag.scope(target), 'request': 'Correct exact subject',
                'rationale': 'Observed defect', 'supersedes': None}})
            finding = self.produced(interpret['node']['node'], item=item)
            admit = self.acquire_prefix('gc_admit_', item=item, actor='root-thread')
            self.session.finish(admit, {'value': {'finding': finding,
                'target_inputs': original['inputs'], 'authority': self.result(interpret['node']['node'], item)[0],
                'applicability': 'applicable', 'rationale': 'Exact in-scope correction'}, 'transfer': None})
            return name, item
        name, item = late_debt('produce', 'produce-debt')
        self.session.finish(self.session.acquire('produce'), {'value': 'corrected value'})
        for reviewer, member in [('review', None), (name, item)]:
            self.session.finish(self.session.acquire(reviewer, item=member, actor='correction-' + reviewer),
                {'value': {'decision': 'approved', 'report': 'Inspected exact correction.'}})
        work, first = self.acquire_batch()
        self.session.finish(work, self.batch_output(first, unresolved={'produce-debt'}))
        self.assertFalse(any(step['node']['node'].startswith('gc_resolve_batch_') for step in self.session.ready()))
        late_debt('authority_context', 'context-debt')
        self.session.finish(self.session.acquire('authority_context'), {'value': 'context two'})
        work, second = self.acquire_batch()
        self.assertEqual(first['subject'], second['subject'])
        self.assertEqual(first['findings'], second['findings'])
        self.assertEqual(first['reviews'], second['reviews'])
        self.assertNotEqual(first['opportunities'], second['opportunities'])

    def test_custom_static_resolver_overlap_is_diagnosed_without_bypassing_its_requirements(self):
        graph = copy.deepcopy(self.graph)
        authority = dag.task('custom_authority', role='root')
        custom = dag.task('custom_resolution', ['custom_authority'])
        custom['outputs'] = {'value': {'type': 'resolution', 'schema': dag.RESOLUTION_TYPE}}
        exact_scope = {'subject': {'kind': 'node', 'goal': '#this', 'node': 'produce'}, 'output': 'value'}
        custom['resolves'] = [exact_scope]
        custom['permits'] = [{'type': 'resolution', 'scope': exact_scope}]
        custom['independent_of'] = [exact_scope['subject']]
        graph['nodes'].extend([authority, custom])
        self.install(graph)
        self.produce()
        self.session.finish(self.session.acquire('review', actor='initial-reviewer'),
            {'value': {'decision': 'changes_requested', 'report': 'One exact defect.'}})
        self.admit_rejection('review', None, 'overlap-debt')
        self.session.finish(self.session.acquire('produce'), {'value': 'corrected'})
        self.session.finish(self.session.acquire('review', actor='corrected-reviewer'),
            {'value': {'decision': 'approved', 'report': 'Inspected exact correction.'}})
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        steps = self.session.checkpoint(100)
        self.assertTrue(any('Unsupported resolution overlap' in step.get('reason', '') for step in steps), steps)
        self.assertFalse(any(step.get('node', {}).get('node', '').startswith('gc_resolve_batch_')
                             for step in steps if step['kind'] == 'execute'))
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def registry_capability_fixture(self, capability='bounded', before_work=None):
        graph = copy.deepcopy(self.graph)
        dag.z._graph_compiler._append_static(graph, 'produce', 'value', 'review', 'value')
        graph['task_sets'][0]['template']['executor']['capability'] = capability
        self.install(graph)
        if before_work is not None: before_work()
        self.produce()
        self.session.finish(self.session.acquire('review', actor='first-reviewer'),
            {'value': {'decision': 'changes_requested', 'report': 'One exact registry defect'}})
        original = self.result('produce')[1]
        interpret = next(node['id'] for node in graph['nodes'] if any(
            output['type'] == 'finding' for output in node['outputs'].values()))
        self.session.finish(self.session.acquire(interpret), {'value': {
            'id': 'registry-debt', 'revision': 1, 'source': self.produced('review'),
            'subjects': [original['outputs']['value']], 'target': dag.scope('produce'),
            'request': 'Fix exact registry defect', 'rationale': 'Exact correction', 'supersedes': None}})
        finding = self.produced(interpret)
        admit = next(node['id'] for node in graph['nodes'] if any(
            output['type'] == 'admission' for output in node['outputs'].values()))
        self.session.finish(self.session.acquire(admit), {'value': {'finding': finding,
            'target_inputs': original['inputs'], 'authority': self.result(interpret)[0],
            'applicability': 'applicable', 'rationale': 'In scope'}, 'transfer': None})
        self.session.finish(self.session.acquire('produce'), {'value': 'corrected registry subject'})
        self.session.finish(self.session.acquire('review', actor='approved-reviewer'),
            {'value': {'decision': 'approved', 'report': 'Exact corrected subject inspected'}})
        retain = next(node['id'] for node in graph['nodes'] if any(
            output['type'] == 'finding_registry' for output in node['outputs'].values()))
        self.session.finish(self.session.acquire(retain), {'value': {
            'items': {'registry-debt': finding}, 'rationale': 'Retain exact debt'}})
        return finding

    def historical_policy_resolution(self, corruption=None):
        from test_policy_ci_transition import PolicyCiTransitionTests
        self.git = self.session.git
        self.commit_policy = PolicyCiTransitionTests.commit_policy.__get__(self)
        def reviewed_prefix():
            PolicyCiTransitionTests.reviewed_policy(self, 'disabled', initial=True)
            self.install(self.graph)
            if corruption:
                paths = [self.fixture.repo / '.zzzops' / name for name in
                         ('POLICY.json', 'PROJECT.md', 'PROJECT_AUDIT.md')]
                valid = {path: path.read_bytes() for path in paths}
                path = self.fixture.repo / '.zzzops' / corruption
                if corruption == 'POLICY.json':
                    state = json.loads(path.read_text())
                    state['approval']['digest'] = 'sha256:' + '0' * 64
                    path.write_text(json.dumps(state))
                else: path.write_text(path.read_text() + '\nUnapproved historical alteration.\n')
                self.git('add', '-A', '.zzzops')
                self.git('commit', '--amend', '-qm', 'synthetic invalid historical policy proof')
                for path, data in valid.items(): path.write_bytes(data)
        self.registry_capability_fixture(before_work=reviewed_prefix)
        work, manifest = self.acquire_batch()
        self.session.finish(work, self.batch_output(manifest))
        old_policy = copy.deepcopy(self.session.project['policy'])
        prior = self.result('produce')[0]
        dag.z._workflow_section(self.session.project, 'code_quality')['instructions'] += ' Require an additional substantive source check.'
        PolicyCiTransitionTests.reviewed_policy(self, 'disabled')
        self.assertFalse(dag.z._policy.phase_policy_ci_compatible(old_policy, self.session.project['policy']))
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        steps = self.session.checkpoint(100)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        if corruption:
            self.assertTrue(any(step['kind'] == 'blocker' and 'historical approved policy' in step.get('reason', '') for step in steps), steps)
            return
        self.assertFalse(any(step['kind'] in ('blocker', 'repair') for step in steps), steps)
        ready = {step.get('node', {}).get('node') for step in steps if step['kind'] == 'execute'}
        self.assertIn('produce', ready)
        self.assertNotIn('review', ready)
        self.assertFalse(any(name.startswith('gc_resolve_batch_') for name in ready))
        self.assertEqual(prior, self.result('produce')[0])
        restarted = self.session.acquire('produce')
        self.session.finish(restarted, {'value': 'Current policy requirement satisfied'})
        self.assertIn('review', self.names())
        self.session.finish(self.session.acquire('review', actor='new-policy-reviewer'),
            {'value': {'decision': 'approved', 'report': 'Current policy and changed subject independently checked'}})
        final = self.session.checkpoint(100)
        self.assertFalse(any(step.get('node', {}).get('node', '').startswith('gc_resolve_batch_') for step in final), final)
        self.assertFalse(any('Explicitly unresolved' in step.get('reason', '') for step in final), final)

    def test_authenticated_incompatible_policy_keeps_closure_but_not_old_result_current(self):
        self.historical_policy_resolution()

    def test_historical_closure_rejects_forged_policy_approval(self):
        self.historical_policy_resolution('POLICY.json')

    def test_historical_closure_rejects_changed_project_binding(self):
        self.historical_policy_resolution('PROJECT.md')

    def test_historical_closure_rejects_changed_audit_binding(self):
        self.historical_policy_resolution('PROJECT_AUDIT.md')

    def bounded_runtime(self):
        pair = {'model': 'worker-bounded', 'effort': 'medium'}
        self.session.runtime['root_pair'] = pair
        self.session.runtime['available_pairs'] = [pair]
        return pair

    def test_bounded_registry_batch_preserves_actual_bounded_only_model_selection(self):
        finding = self.registry_capability_fixture()
        pair = self.bounded_runtime()
        work, manifest = self.acquire_batch()
        self.assertEqual(pair, work['lease']['selection'])
        self.assertEqual([finding], [entry['finding'] for entry in manifest['findings'].values()])
        self.session.finish(work, self.batch_output(manifest))
        self.assertFalse(any(step.get('kind') in ('execute', 'blocker', 'repair')
                             for step in self.session.checkpoint(100)))

    def test_reasoning_registry_requirement_cannot_be_lowered_for_bounded_root(self):
        self.registry_capability_fixture('reasoning')
        self.bounded_runtime()
        steps = self.session.checkpoint(100)
        self.assertFalse(any(step['kind'] == 'execute' and step.get('node', {}).get('node', '').startswith('gc_resolve_batch_') for step in steps))
        self.assertTrue(any('Reviewed capability/model inventory unavailable' in step.get('reason', '') for step in steps), steps)

    def test_mixed_capability_batch_shrinking_to_bounded_debt_does_not_reoffer(self):
        self.registry_capability_fixture()
        source, original = self.result('produce')
        self.record_phase_finding(source, original['outputs']['value'], 'mixed-late', 'mixed-late')
        item = dag.z._static_workflow.event_key({'id': 'mixed-late', 'revision': 1})
        name = dag.z._static_workflow.review_name('produce', 'value')
        self.session.finish(self.session.acquire(name, item=item, actor='late-reviewer'),
            {'value': {'decision': 'changes_requested', 'report': 'Exact late defect'}})
        self.admit_rejection(name, item, 'late-reasoning-debt')
        self.session.finish(self.session.acquire('produce'), {'value': 'both defects corrected'})
        for reviewer, member in [('review', None), (name, item)]:
            self.session.finish(self.session.acquire(reviewer, item=member, actor='final-' + reviewer),
                {'value': {'decision': 'approved', 'report': 'Exact corrected subject inspected'}})
        high_runtime = copy.deepcopy(self.session.runtime)
        self.bounded_runtime()
        blocked = self.session.checkpoint(100)
        self.assertTrue(any('Reviewed capability/model inventory unavailable' in step.get('reason', '') for step in blocked), blocked)
        self.assertFalse(any(step['kind'] == 'execute' and step.get('node', {}).get('node', '').startswith('gc_resolve_batch_') for step in blocked))
        self.session.runtime = high_runtime
        work, manifest = self.acquire_batch()
        self.assertEqual({'model': 'worker-reasoning', 'effort': 'high'}, work['lease']['selection'])
        self.assertEqual({'registry-debt', 'late-reasoning-debt'}, {entry['id'] for entry in manifest['findings'].values()})
        self.session.finish(work, self.batch_output(manifest, unresolved={'registry-debt'}))
        for low_root in (False, True):
            if low_root: self.bounded_runtime()
            steps = self.session.checkpoint(100)
            self.assertFalse(any(step.get('kind') == 'execute' and step.get('node', {}).get('node', '').startswith('gc_resolve_batch_') for step in steps), steps)
            self.assertTrue(any('Explicitly unresolved' in step.get('reason', '') for step in steps), steps)

    def test_zero_findings_offer_no_resolution_work(self):
        self.assertFalse(any('resolve' in step['node']['node'] for step in self.session.ready()))

    def test_numeric_and_symbolic_scope_aliases_fail_closed_with_precise_diagnostic(self):
        graph = copy.deepcopy(self.graph)
        reviewer = next(node for node in graph['nodes'] if node['id'] == 'review')
        reviewer['inputs']['subject']['producer']['node']['goal'] = 100
        reviewer['independent_of'][0]['goal'] = 100
        self.install(graph)
        self.produce()
        self.session.finish(self.session.acquire('review', actor='literal-reviewer'),
            {'value': {'decision': 'changes_requested', 'report': 'Exact ordinary defect.'}})
        self.admit_rejection('review', None, 'literal-defect')
        self.session.finish(self.session.acquire('produce'), {'value': 'literal correction'})
        self.session.finish(self.session.acquire('review', actor='literal-correction-reviewer'),
            {'value': {'decision': 'approved', 'report': 'Exact corrected subject reviewed.'}})
        steps = self.session.checkpoint(100)
        self.assertTrue(any('Unsupported resolution scope alias' in step.get('reason', '') for step in steps), steps)
        self.assertFalse(any(step.get('kind') == 'execute' and
                             step.get('node', {}).get('node', '').startswith('gc_resolve_') for step in steps))


class ResolutionBatchContractTests(unittest.TestCase):
    def test_lifecycle_policy_authentication_searches_beyond_current_reuse_horizon(self):
        policy = json.loads((Path(__file__).parents[1] / 'plugins/zzzops/zzzops/templates/project-goals/INIT_PLAN.json').read_text())['policy']
        current = copy.deepcopy(policy)
        next(row for row in current['sections'] if row['id'] == 'code_quality')['instructions'] += ' New substantive requirement.'
        intermediate = copy.deepcopy(policy)
        next(row for row in intermediate['sections'] if row['id'] == 'code_quality')['instructions'] += ' Intermediate requirement.'
        wanted = dag.z._workflow.digest(policy)
        commits = [format(index + 1, '040x') for index in range(82)]
        engine = dag.SimpleNamespace(api=dag.z, repo=Path('/synthetic-policy-history'), project={'policy': current})
        engine.node_policy_at_commit = mock.Mock(side_effect=lambda commit: policy if commit == commits[80] else intermediate)
        result = dag.subprocess.CompletedProcess([], 0, stdout='\n'.join(commits), stderr='')
        with mock.patch.object(dag.z._workflow.subprocess, 'run', return_value=result) as command:
            accepted, _ = dag.z._workflow.Workflow.node_historical_policies(engine, {}, {}, required_hashes={wanted})
            self.assertNotIn(wanted, accepted)
            self.assertIn('--max-count=65', command.call_args.args[0])
            accepted, error = dag.z._workflow.Workflow.node_historical_policies(engine, {}, {},
                compatible_only=False, required_hashes={wanted})
            self.assertIn(wanted, accepted)
            self.assertIsNone(error)
            self.assertNotIn('--max-count=65', command.call_args.args[0])
        self.assertEqual(policy, accepted[wanted])
        self.assertIn(mock.call(commits[80]), engine.node_policy_at_commit.call_args_list)
        self.assertNotIn(mock.call(commits[81]), engine.node_policy_at_commit.call_args_list)

    def test_policy_lookup_requires_exact_approval_when_snapshots_share_projection(self):
        policy = json.loads((Path(__file__).parents[1] / 'plugins/zzzops/zzzops/templates/project-goals/INIT_PLAN.json').read_text())['policy']
        wrong = copy.deepcopy(policy)
        routing = next(row for row in wrong['sections'] if row['id'] == 'model_routing')['configuration']
        routing['allow_above_root_delegation'] = not routing.get('allow_above_root_delegation', False)
        current = copy.deepcopy(policy)
        next(row for row in current['sections'] if row['id'] == 'code_quality')['instructions'] += ' Current incompatible requirement.'
        projection = dag.z._policy.phase_policy_projection
        recorded = dag.z._workflow.digest(projection(policy, 'current'))
        approved = dag.z._workflow.digest(policy)
        self.assertEqual(approved, dag.z._workflow.digest(projection(policy, 'full')))
        self.assertEqual(recorded, dag.z._workflow.digest(projection(wrong, 'current')))
        self.assertNotEqual(approved, dag.z._workflow.digest(wrong))
        commits = ['1' * 40, '2' * 40, '3' * 40]
        engine = dag.SimpleNamespace(api=dag.z, repo=Path('/synthetic-policy-history'), project={'policy': current})
        engine.node_policy_at_commit = mock.Mock(side_effect=lambda commit: wrong if commit == commits[0] else policy)
        result = dag.subprocess.CompletedProcess([], 0, stdout='\n'.join(commits), stderr='')
        with mock.patch.object(dag.z._workflow.subprocess, 'run', return_value=result):
            accepted, error = dag.z._workflow.Workflow.node_historical_policies(engine, {}, {},
                compatible_only=False, required_hashes={recorded, approved})
        self.assertIsNone(error)
        self.assertEqual(wrong, accepted[recorded])
        self.assertEqual(policy, accepted[approved])
        self.assertEqual([mock.call(commits[0]), mock.call(commits[1])], engine.node_policy_at_commit.call_args_list)

    def test_shared_entry_validator_requires_every_review_and_exact_member_scope(self):
        ref = lambda name: {'hash': 'sha256:' + hashlib.sha256(name.encode()).hexdigest(), 'uri': 'urn:' + name}
        subject, finding_ref, producer_ref = ref('subject'), ref('finding'), ref('producer')
        reviewer_refs = [ref('review-one'), ref('review-two')]
        target = {'kind': 'member', 'goal': 100, 'expansion': 'alpha', 'item': 'same', 'generation': 1}
        scope = {'subject': target, 'output': 'value'}
        producer = {'node': {'goal': 100, 'node': 'alpha_worker', 'item': 'same', 'generation': 1},
                    'executor': 'producer', 'outputs': {'value': subject}}
        finding = {'id': 'exact', 'revision': 1, 'target': scope}
        value = {'finding': finding_ref, 'subjects': [subject], 'reviewer_result': reviewer_refs[0],
                 'decision': 'resolved', 'rationale': 'Both independent reviews inspected exact correction.'}
        results = {producer_ref['hash']: (producer_ref, producer)}
        contracts = {}
        for index, review_ref in enumerate(reviewer_refs):
            results[review_ref['hash']] = (review_ref, {'executor': 'reviewer-' + str(index),
                'outputs': {}, 'inputs': [{'source': subject, 'mode': 'identity', 'path': []}],
                'resolutions': [{'selector': target, 'targets': [producer['node']]}]})
            contracts[review_ref['hash']] = {'independent_of': [target]}
        def validate():
            return dag.z._resolution_lifecycle.validate_entry(value,
                expected={'finding': finding_ref, 'id': 'exact', 'revision': 1}, scope=scope, goal=100,
                results=results, contracts=contracts, read=lambda reference, kind: finding,
                ev=dag.z._phase_evidence, required_reviews=reviewer_refs, subject=subject)
        self.assertEqual(value, validate())
        second = results[reviewer_refs[1]['hash']][1]
        saved = copy.deepcopy(second)
        second['inputs'] = []
        with self.assertRaisesRegex(ValueError, 'did not inspect'): validate()
        second.update(copy.deepcopy(saved)); second['executor'] = 'producer'
        with self.assertRaisesRegex(ValueError, 'subject executor'): validate()
        second.update(copy.deepcopy(saved))
        foreign_scope = {**target, 'expansion': 'beta'}
        second['resolutions'][0]['selector'] = foreign_scope
        contracts[reviewer_refs[1]['hash']]['independent_of'] = [foreign_scope]
        with self.assertRaisesRegex(ValueError, 'exact subject independence'): validate()

    def test_compilation_is_idempotent_with_ordinary_and_late_routes(self):
        producer = dag.task('produce')
        reviewer = dag.task('review', ['produce'])
        reviewer['inputs'] = {'subject': dag.subject_input('produce')}
        reviewer['inputs']['subject']['producer']['node']['goal'] = '#this'
        reviewer['independent_of'] = [{**dag.selector('produce'), 'goal': '#this'}]
        reviewer['outputs'] = {'value': {'type': 'review_decision', 'schema': {
            'kind': 'object', 'fields': {
                'decision': {'kind': 'enum', 'values': ['approved', 'changes_requested']},
                'report': {'kind': 'string'}}}}}
        graph = {'nodes': [producer, reviewer], 'task_sets': [], 'terminals': []}
        first = dag.z._static_workflow.canonical(graph, dag.z._graph_compiler)
        second = dag.z._static_workflow.canonical(first, dag.z._graph_compiler)
        self.assertEqual(first, second)
        self.assertEqual(1, sum(row['source']['producer'] == {'slot': 'resolution_batches'}
                               and row['template']['resolves'][0]['subject']['node'] == 'produce'
                               for row in first['task_sets']))

    def test_shipped_policy_has_one_batch_family_per_scope_and_no_active_singular_family(self):
        path = Path(__file__).parents[1] / 'plugins/zzzops/zzzops/templates/project-goals/INIT_PLAN.json'
        policy = json.loads(path.read_text())['policy']
        graph = next(section for section in policy['sections'] if section['id'] == 'workflow_adherence')['configuration']['phase_dag']
        compiled = dag.z._static_workflow.canonical(graph, dag.z._graph_compiler)
        scopes = []
        for row in compiled['task_sets']:
            if row['source']['producer'] == {'slot': 'resolution_batches'}:
                scopes.append(dag.content_hash(row['template']['resolves'][0]))
            elif any(output['type'] == 'resolution' for output in row['template']['outputs'].values()):
                self.assertEqual({'slot': 'retired_resolution_members'}, row['source']['producer'])
        self.assertEqual(len(scopes), len(set(scopes)))
        self.assertEqual(compiled, dag.z._static_workflow.canonical(compiled, dag.z._graph_compiler))
        dag.z._phase_evidence.validate_graph(compiled)

    def test_registry_resolution_schema_binding_and_applicability_are_not_dropped(self):
        original = json.loads((Path(__file__).parent / 'fixtures/legacy_evidence_dag.json').read_text())
        for mutation in ('output_field', 'finding_filter', 'applicability'):
            with self.subTest(mutation=mutation):
                graph = copy.deepcopy(original)
                resolver = next(row['template'] for row in graph['task_sets'] if any(
                    value['type'] == 'resolution' for value in row['template']['outputs'].values()))
                if mutation == 'output_field':
                    resolver['outputs']['value']['schema']['fields']['approval_ticket'] = {'kind': 'string'}
                elif mutation == 'finding_filter':
                    resolver['inputs']['finding']['type']['fields']['uri'] = {'kind': 'enum', 'values': ['zzzops:only-approved-finding']}
                else:
                    resolver['applicability'] = {'input': dag.spec_input(), 'values': ['enabled'],
                        'outputs': {'value': {'finding': dag.REF, 'subjects': [dag.REF], 'reviewer_result': dag.REF,
                            'decision': 'resolved', 'rationale': 'Explicitly inactive'}}, 'rationale': 'Preserve reviewed condition'}
                dag.z._phase_evidence.validate_graph(graph)
                with self.assertRaisesRegex(ValueError, 'Unsupported custom resolution batching contract'):
                    dag.z._static_workflow.canonical(graph, dag.z._graph_compiler)

    def test_registry_executor_capability_cannot_be_silently_downgraded(self):
        graph = json.loads((Path(__file__).parent / 'fixtures/legacy_evidence_dag.json').read_text())
        resolver = next(row['template'] for row in graph['task_sets']
                        if any(value['type'] == 'resolution' for value in row['template']['outputs'].values()))
        resolver['executor']['capability'] = 'architectural'
        with self.assertRaisesRegex(ValueError, 'Unsupported custom resolution batching contract'):
            dag.z._static_workflow.canonical(graph, dag.z._graph_compiler)

    def test_unsupported_registry_finding_alias_has_precise_diagnostic(self):
        path = Path(__file__).parent / 'fixtures/legacy_evidence_dag.json'
        graph = json.loads(path.read_text())
        resolver = next(row['template'] for row in graph['task_sets']
                        if any(value['type'] == 'resolution' for value in row['template']['outputs'].values()))
        resolver['inputs']['renamed_finding'] = resolver['inputs'].pop('finding')
        with self.assertRaisesRegex(ValueError, 'Unsupported resolution registry finding binding'):
            dag.z._static_workflow.canonical(graph, dag.z._graph_compiler)

    def test_custom_resolution_gate_is_not_silently_dropped_by_batching(self):
        path = Path(__file__).parent / 'fixtures/legacy_evidence_dag.json'
        graph = json.loads(path.read_text())
        resolver = next(row['template'] for row in graph['task_sets']
                        if any(value['type'] == 'resolution' for value in row['template']['outputs'].values()))
        resolver['gates'] = copy.deepcopy(resolver['resolves'])
        with self.assertRaisesRegex(ValueError, 'Unsupported custom resolution batching contract'):
            dag.z._static_workflow.canonical(graph, dag.z._graph_compiler)


if __name__ == '__main__':
    unittest.main()
