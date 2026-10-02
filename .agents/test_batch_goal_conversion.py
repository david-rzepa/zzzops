"""Automatic lossless migration through public dispatch; external boundaries only."""
import copy
import json
from pathlib import Path
from unittest import mock

import test_evidence_dag_journeys as dag


class BatchConversionTests(dag.DagFixture):
    def setUp(self):
        super().setUp()
        template = json.loads((dag.old.fixtures.PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        config = dag.z._workflow_section(self.session.project, 'workflow_adherence')['configuration']
        config['phase_dag'] = next(s for s in template['policy']['sections'] if s['id'] == 'workflow_adherence')['configuration']['phase_dag']
        config.pop('migration_entries', None)
        self.policy = copy.deepcopy(self.session.project)
        configuration_dir = self.fixture.repo / '.zzzops'
        configuration_dir.mkdir(exist_ok=True)
        self.configuration_bytes = {'POLICY.json': json.dumps(self.policy, indent=2).encode(), 'PROJECT.md': b'Reviewed instructions remain exact.\n', 'model-inventory.json': json.dumps(dag.z._workflow_section(self.policy, 'model_routing')['configuration']['model_inventory']).encode()}
        for name, raw in self.configuration_bytes.items(): (configuration_dir / name).write_bytes(raw)
        self.provider.comments = {}
        self.provider.issues = {}
        self.originals = {}
        for number in (100, 101):
            self.add(number)
        self.index_patch = mock.patch.object(dag.z, 'github_repository_goal_index', side_effect=self.index)
        self.index_patch.start()
        self.addCleanup(self.index_patch.stop)

    def add(self, number, *, state='open', parent=None, dependencies=(), blockers=()):
        issue = dag.old.fixtures.PortfolioTests().issue(number, priority='P1', status='new')
        value = dag.z.parse_managed_goal(issue['body'], number)
        value.update(parent=parent, depends_on=list(dependencies), blockers=[{'status': 'open', 'category': 'human-action', 'question': text} for text in blockers])
        prefix = issue['body'].split('<!-- zzzops-goal', 1)[0]
        issue['body'] = prefix + '<!-- zzzops-goal\n' + json.dumps(value) + '\nzzzops-goal -->'
        issue['state'] = state
        self.provider.issues[number] = issue
        self.provider.comments[number] = []
        self.originals[number] = copy.deepcopy(issue)

    def index(self, *_args, **_kwargs):
        rows = [{'number': n, 'state': i['state'], 'schema_version': 1,
                 'labels': copy.deepcopy(i['labels'])} for n, i in self.provider.issues.items()]
        return {'usable': True}, rows, [], 0, 1, []

    def batch(self, action, *, expected=0, **fields):
        response = self.session.call(100, {'operation': 'migration_batch', 'action': action, **fields}, expected=expected)
        return response['next_steps'][0]

    def migrate(self, numbers=(100, 101)):
        return self.batch('migrate', goals=list(numbers))

    def assert_preserved(self, number):
        issue = self.provider.issues[number]
        original = self.originals[number]
        start, end = '<!-- zzzops-goal', 'zzzops-goal -->'
        self.assertEqual(original['body'].split(start)[0], issue['body'].split(start)[0])
        self.assertEqual(original['body'].split(end)[1], issue['body'].split(end)[1])
        envelope = dag.z.parse_managed_goal(issue['body'], number)
        self.assertEqual(2, envelope['schema_version'])
        self.assertEqual(original['state'], issue['state'])
        self.assertEqual(original['labels'], issue['labels'])
        self.assertEqual(self.policy, self.session.project)
        for name, raw in self.configuration_bytes.items():
            self.assertEqual(raw, (self.fixture.repo / '.zzzops' / name).read_bytes())
        payload = self.session.read(number, envelope['payload'])
        self.assertEqual([], payload['evidence'], 'Migration creates no product Results')
        self.assertEqual([], payload['operational']['leases'])
        spec = self.session.read(number, payload['spec'])
        self.assertEqual(original, self.session.read(number, spec['provenance']['source'])['content'])
        return payload

    def legacy_fields(self, number, **fields):
        issue = self.provider.issues[number]
        value = dag.z.parse_managed_goal(issue['body'], number)
        value.update(fields)
        issue['body'] = issue['body'].split('<!-- zzzops-goal')[0] + '<!-- zzzops-goal\n' + json.dumps(value) + '\nzzzops-goal -->'
        self.originals[number] = copy.deepcopy(issue)

    def test_empty_rigor_and_risk_annotations_migrate_without_losing_requirements(self):
        self.legacy_fields(100, engineering_rigor={'risk_categories': []})
        self.legacy_fields(101, engineering_rigor={'risk_categories': ['authorization'], 'override': None})
        routing = dag.z._workflow_section(self.session.project, 'model_routing')['configuration']
        routing['assessment_tree'].insert(0, {'when': {'engineering_rigor': ['agentic']}, 'tier': 'architectural'})
        self.policy = copy.deepcopy(self.session.project)
        result = self.migrate()
        self.assertTrue(result['complete'], result)
        for number in (100, 101):
            payload = self.assert_preserved(number)
            spec = self.session.read(number, payload['spec'])['content']
            graph = self.session.read(number, payload['graph'])
            if number == 100:
                self.assertEqual(dag.z._workflow_section(self.policy, 'workflow_adherence')['configuration']['phase_dag'], graph)
            if number == 101:
                self.assertIn('authorization', spec)
                self.assertIn('agentic', spec)
                self.assertTrue(all(n['executor']['capability'] == 'architectural' for n in graph['nodes']))

    def test_rigor_mapping_keeps_stricter_floor_and_covers_custom_tasks_and_templates(self):
        self.legacy_fields(100, engineering_rigor={'risk_categories': ['authorization']})
        config = dag.z._workflow_section(self.session.project, 'workflow_adherence')['configuration']
        graph = dag.selected_graph()
        graph['nodes'][0]['executor']['capability'] = 'architectural'
        graph['task_sets'][0]['template']['executor']['capability'] = 'bounded'
        config['phase_dag'] = graph
        routing = dag.z._workflow_section(self.session.project, 'model_routing')['configuration']
        routing['assessment_tree'].insert(0, {'when': {'engineering_rigor': ['agentic'], 'phase_type': ['implement']}, 'tier': 'reasoning'})
        self.assertTrue(self.migrate((100,))['complete'])
        envelope = dag.z.parse_managed_goal(self.provider.issues[100]['body'], 100)
        payload = self.session.read(100, envelope['payload'])
        migrated = self.session.read(100, payload['graph'])
        self.assertEqual('architectural', migrated['nodes'][0]['executor']['capability'])
        self.assertEqual('reasoning', migrated['task_sets'][0]['template']['executor']['capability'])
        self.assertIn('agentic', migrated['task_sets'][0]['template']['prompt'])

    def test_nonexclusive_resources_preserve_hints_without_granting_edits(self):
        self.legacy_fields(100, resources=[' PATH:src/a.py ', 'integration:dev'])
        result = self.migrate((100,))
        self.assertTrue(result['complete'], result)
        payload = self.assert_preserved(100)
        spec = self.session.read(100, payload['spec'])['content']
        self.assertIn('path:src/a.py', spec)
        self.assertIn('not edit authority', spec)
        graph = self.session.read(100, payload['graph'])
        self.assertEqual(dag.z._workflow_section(self.policy, 'workflow_adherence')['configuration']['phase_dag'], graph)
        acquired = self.session.acquire('understand')
        self.assertNotIn('owned', acquired['lease']['acquisition'])
        self.assertNotIn('path:src/a.py', json.dumps(acquired['lease']['acquisition']))
        self.assertFalse(any(s['node']['node'] == 'implement' for s in self.session.ready()))

    def test_exclusive_resources_block_with_repair_guidance_and_no_mutation(self):
        self.legacy_fields(100, resources=['external:shared-api'])
        self.legacy_fields(101, resources=['branch:Topic'])
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        result = self.migrate()
        for number in (100, 101):
            member = result['members'][str(number)]
            self.assertEqual('blocked', member['status'])
            self.assertIn('exclusive resources', member['reason'])
            self.assertEqual(['resources'], member['remediation']['fields'])
            self.assertIn('shared reservation protocol', ' '.join(member['remediation']['steps']))
            self.assertEqual({'operation': 'migration_batch', 'action': 'migrate', 'goals': [number]}, member['remediation']['retry'])
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_unsupported_metadata_has_specific_guidance_and_no_mutation(self):
        self.legacy_fields(100, engineering_rigor={'risk_categories': ['unconfigured_risk']})
        self.legacy_fields(101, engineering_rigor={'risk_categories': [], 'override': {
            'level': 'agentic', 'authority': 'explicit_user', 'evidence': 'Historical approval'}})
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        result = self.migrate()
        for number, member in result['members'].items():
            self.assertEqual('blocked', member['status'])
            self.assertIn('engineering_rigor', member['remediation']['fields'])
            self.assertTrue(member['remediation']['steps'])
            self.assertEqual({'operation': 'migration_batch', 'action': 'migrate', 'goals': [int(number)]}, member['remediation']['retry'])
            self.assertIn('Preserve the requirement', ' '.join(member['remediation']['steps']))
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        response = self.session.call(101)
        self.assertIn('remediation', response['next_steps'][0])
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_execute_encounter_automatically_migrates_without_review_or_approval(self):
        response = self.session.call(100)
        self.assert_preserved(100)
        steps = response['next_steps']
        self.assertTrue(any(s.get('kind') == 'execute' and s.get('node', {}).get('node') == 'understand' for s in steps))
        self.assertFalse(any('conversion_approval' in str(s.get('node')) for s in steps))
        self.assertEqual(self.originals[101], self.provider.issues[101])

    def test_batch_two_members_and_exact_retry_do_not_need_approval(self):
        result = self.migrate()
        self.assertTrue(result['complete'])
        for n in (100, 101):
            self.assertEqual('migrated', result['members'][str(n)]['status'])
            self.assertTrue(result['members'][str(n)]['next_steps'])
            self.assert_preserved(n)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        result = self.migrate()
        self.assertTrue(result['complete'])
        self.assertTrue(all(m['status'] == 'already_current' for m in result['members'].values()))
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_read_preview_and_discovery_are_readonly_and_pages_are_bounded(self):
        for n in (102, 103, 104): self.add(n)
        self.add(105, state='closed')
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, {'operation': 'read'})
        self.session.call(100, intent='preview', expected=None)
        self.session.call(100, {'operation': 'migration_batch', 'action': 'migrate', 'goals': [100]}, intent='preview', expected=2)
        self.batch('status', goals=[100, 101])
        reads = []
        original = self.provider.get_issue
        with mock.patch.object(self.provider, 'get_issue', side_effect=lambda n: (reads.append(n), original(n))[1]):
            first = self.batch('discover', limit=2)
        self.assertLessEqual(len(set(reads)), 2)
        self.assertNotIn(105, reads)
        second = self.batch('discover', limit=2, after=first['cursor'])
        third = self.batch('discover', limit=2, after=second['cursor'])
        self.assertEqual([100, 101, 102, 103, 104], first['goals'] + second['goals'] + third['goals'])
        self.assertEqual(0, third['remaining'])
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_malformed_unsupported_closed_members_do_not_stop_supported_member(self):
        self.provider.issues[101]['body'] = 'Invalid <!-- zzzops-goal\n{}\nzzzops-goal -->'
        self.add(102)
        self.provider.issues[102]['body'] = self.provider.issues[102]['body'].replace('"schema_version": 1', '"schema_version": 99')
        self.add(103, state='closed')
        before = copy.deepcopy({n: self.provider.issues[n] for n in (101, 102, 103)})
        result = self.migrate((100, 101, 102, 103))
        self.assertEqual('migrated', result['members']['100']['status'])
        self.assertFalse(result['complete'])
        for n in (101, 102): self.assertEqual('blocked', result['members'][str(n)]['status'])
        self.assertEqual('closed', result['members']['103']['status'])
        self.assertEqual(before, {n: self.provider.issues[n] for n in before})

    def test_stale_labels_cannot_reconvert_v2_or_invalid_ids_mutate(self):
        self.migrate()
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.assertEqual([], self.batch('discover')['goals'])
        self.assertTrue(self.batch('status', goals=[100, 101])['complete'])
        self.assertTrue(all(m['status'] == 'already_current' for m in self.migrate()['members'].values()))
        for ids in ([0], [-1], [100, 100], [True], []):
            self.batch('migrate', goals=ids, expected=2)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_history_suffix_and_old_approval_are_preserved_as_data(self):
        from test_phase_review_contract import PhaseReviewContractTests
        value = dag.z.parse_managed_goal(self.provider.issues[100]['body'], 100)
        f = PhaseReviewContractTests(); original_input = f.envelope('plan')
        evidence = dag.z._phase_evidence.record_phase_result(None, 'plan', f.record('plan', original_input), original_input)
        evidence = dag.z._phase_evidence.record_phase_review(evidence, 'plan', f.artifact('old review'), 'old reviewer', outcomes={'acceptance': 'approved', 'entropy': {'outcome': 'no_findings', 'evidence': 'Old finding', 'goals': []}})
        value['phase_evidence'] = dag.z._phase_evidence.record_phase_approval(evidence, 'plan', 'root', 'old user approval')
        self.provider.issues[100]['body'] = self.provider.issues[100]['body'].split('<!-- zzzops-goal')[0] + '<!-- zzzops-goal\n' + json.dumps(value) + '\nzzzops-goal -->\nHuman postscript.\n'
        self.provider.create_issue_comment(100, 'Historical transaction: preserve byte for byte.')
        self.originals[100] = copy.deepcopy(self.provider.issues[100])
        comments = copy.deepcopy(self.provider.comments[100])
        self.migrate()
        self.assert_preserved(100)
        for row in comments: self.assertIn(row, self.provider.comments[100])
        # Subsequent ordinary checkpoints must keep the preserved postscript too.
        self.normal_setup(100)
        self.assertTrue(self.provider.issues[100]['body'].endswith('\nHuman postscript.\n'))

    def test_parent_dependency_and_blockers_are_active_semantics(self):
        self.add(101, parent=100, dependencies=[100], blockers=['User must supply deployment window'])
        result = self.migrate()
        self.assertTrue(result['complete'])
        payload = self.assert_preserved(101)
        envelope = dag.z.parse_managed_goal(self.provider.issues[101]['body'], 101)
        self.assertEqual(100, envelope['parent'])
        graph = self.session.read(101, payload['graph'])
        self.assertIn('deployment window', json.dumps(graph))
        self.assertIn('"goal": 100', json.dumps(graph))
        steps = self.session.checkpoint(101)
        self.assertTrue(any('deployment window' in s.get('instruction', '') for s in steps))
        self.assertFalse(any(s.get('kind') == 'execute' and s.get('node', {}).get('node') in ('test_design', 'implement') for s in steps))

    def test_dependency_releases_only_after_real_current_implementation_review(self):
        self.add(101, dependencies=[100]); self.migrate()
        review = self.normal_setup(101)
        step = next(s for s in self.session.checkpoint(101) if s.get('node', {}).get('node') == 'test_design')
        self.assertNotEqual('execute', step['kind']); self.assertIn('100', step['reason']); self.assertIn('review_implement', step['reason'])
        self.normal_setup(100)
        for name, outputs in (('test_design', {'value': 'Observed baseline tests'}), ('review_test_design', {'value': review}), ('implement', {'value': 'Observed baseline implementation'}), ('review_implement', {'value': review})):
            self.session.finish(self.session.acquire(name, number=100), outputs, number=100)
            if name == 'review_test_design':
                self.session.finish(self.session.acquire('retain_test_design_findings', number=100), {
                    'value': {'items': {}, 'rationale': 'No test-design findings were admitted in this fixture.'}}, number=100)
        self.assertTrue(any(s.get('kind') == 'execute' and s.get('node', {}).get('node') == 'test_design' for s in self.session.checkpoint(101)))

    def test_child_workspace_still_requires_actual_parent_grant(self):
        self.add(101, parent=100); self.migrate(); self.normal_setup(101)
        step = next(s for s in self.session.checkpoint(101) if s.get('node', {}).get('node') == 'test_design')
        self.assertNotEqual('execute', step['kind']); self.assertRegex(step['reason'], r'(?i)parent.*(allocation|grant|authoriz)')

    def test_unknown_dependency_blocks_affected_member_without_writing(self):
        self.add(101, dependencies=[999]); before = copy.deepcopy(self.provider.issues[101])
        result = self.migrate()
        self.assertEqual('migrated', result['members']['100']['status'])
        self.assertEqual('blocked', result['members']['101']['status'])
        self.assertIn('999', result['members']['101']['reason'])
        self.assertEqual(before, self.provider.issues[101])

    def test_expired_ownership_requires_observed_stopped_recovery(self):
        from test_workflow_state import WorkflowStateValidationTests
        value = dag.z.parse_managed_goal(self.provider.issues[101]['body'], 101)
        value['workflow'] = WorkflowStateValidationTests().valid()
        value['workflow']['leases']['plan:review']['expires_at'] = 1
        self.provider.issues[101]['body'] = dag.z.render_managed_goal(value, '## Outcome\nPreserve owner.\n', 101)
        before = copy.deepcopy(self.provider.issues[101]); result = self.migrate()
        self.assertEqual('blocked', result['members']['101']['status']); self.assertEqual(before, self.provider.issues[101])
        contract = next(s['recovery_contract'] for s in self.session.checkpoint(101) if 'recovery_contract' in s)
        self.session.call(101, {**contract, 'worker_status': 'unknown', 'evidence': 'Expired only'}, expected=2)
        self.assertEqual(before, self.provider.issues[101])
        self.session.call(101, {**contract, 'worker_status': 'stopped', 'evidence': 'Observed synthetic terminal event'})
        self.assertEqual('migrated', self.migrate((101,))['members']['101']['status'])

    def test_lost_append_and_body_responses_reconcile_without_duplicates(self):
        append = self.provider.create_issue_comment; update = self.provider.update_issue
        hits = set()
        def lost_append(n, body):
            result = append(n, body)
            if 'append' not in hits: hits.add('append'); raise OSError('Lost append reply')
            return result
        def lost_body(n, payload):
            result = update(n, payload)
            if 'body' not in hits: hits.add('body'); raise OSError('Lost body reply')
            return result
        with mock.patch.object(self.provider, 'create_issue_comment', side_effect=lost_append), mock.patch.object(self.provider, 'update_issue', side_effect=lost_body):
            self.assertTrue(self.migrate()['complete'])
        self.assertEqual({'append', 'body'}, hits)
        before = copy.deepcopy((self.provider.issues, self.provider.comments)); self.migrate()
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        for rows in self.provider.comments.values(): self.assertEqual(len(rows), len({r['body'] for r in rows}))

    def test_interruption_resumes_exact_source_and_policy_and_keeps_unrelated_success(self):
        update = self.provider.update_issue
        def fail(n, payload):
            if n == 101: raise OSError('Before body publication')
            return update(n, payload)
        with mock.patch.object(self.provider, 'update_issue', side_effect=fail): result = self.migrate()
        self.assertEqual('migrated', result['members']['100']['status']); self.assertEqual('blocked', result['members']['101']['status'])
        comments = copy.deepcopy(self.provider.comments[101]); self.assertTrue(comments)
        self.provider.issues[100]['state'] = 'closed'; closed = copy.deepcopy((self.provider.issues[100], self.provider.comments[100]))
        self.assertEqual('migrated', self.migrate()['members']['101']['status'])
        self.assertEqual(comments, self.provider.comments[101], 'Resume must reuse exact prepared transaction')
        self.assertEqual(closed, (self.provider.issues[100], self.provider.comments[100]))
        self.assert_preserved(101)

    def test_concurrent_human_edit_during_publication_cannot_be_overwritten(self):
        append = self.provider.create_issue_comment; fired = set()
        def concurrent(n, body):
            result = append(n, body)
            if n == 101 and n not in fired:
                fired.add(n); self.provider.issues[n]['body'] = 'User edit\n' + self.provider.issues[n]['body']
            return result
        with mock.patch.object(self.provider, 'create_issue_comment', side_effect=concurrent): result = self.migrate()
        self.assertEqual('migrated', result['members']['100']['status']); self.assertEqual('blocked', result['members']['101']['status'])
        self.assertTrue(self.provider.issues[101]['body'].startswith('User edit\n'))
        # A new invocation may migrate the newly observed source, never old bytes.
        self.originals[101] = copy.deepcopy(self.provider.issues[101]); self.migrate((101,)); self.assert_preserved(101)

    def test_stale_task_request_returns_new_checkpoint_without_executing(self):
        response = self.session.call(100, {'operation': 'start', 'node': {'goal': 100, 'node': 'understand', 'item': None, 'generation': 1}, 'input_hash': 'stale', 'policy_receipt': 'stale'})
        self.assert_preserved(100)
        self.assertTrue(any(s.get('kind') == 'execute' for s in response['next_steps']))

    def test_custom_in_progress_conversion_is_not_replaced(self):
        import test_goal_schema_conversion as fixtures
        fixture = fixtures.MigrationEntryPublicTests(); fixture.setUp()
        try:
            fixture.entry(); work = fixture.session.acquire('analyze')
            before = copy.deepcopy((fixture.provider.issues, fixture.provider.comments))
            response = fixture.session.call(100, {'operation': 'migration_batch', 'action': 'migrate', 'goals': [100]})
            member = response['next_steps'][0]['members']['100']
            self.assertEqual('custom_migration', member['status'])
            self.assertEqual(before, (fixture.provider.issues, fixture.provider.comments))
        finally: fixture.doCleanups()

    def prepared_receipt(self, number):
        contexts = [dag.z._comment_store.decode_envelope(c['body']) for c in self.provider.comments[number]]
        refs = [c['context']['migration']['receipt'] for c in contexts if c and c.get('context', {}).get('migration')]
        self.assertTrue(refs)
        ref = refs[0]; value = self.session.read(number, ref)
        self.assertEqual(ref['hash'], dag.content_hash(value))
        self.assertEqual('schema_migration', value['type'])
        self.assertEqual('owner/repo', value['repository']); self.assertEqual(number, value['goal'])
        for field in ('source', 'target_intent', 'policy'):
            self.assertEqual(value[field]['hash'], dag.content_hash(self.session.read(number, value[field])))
        self.assertEqual(self.originals[number], self.session.read(number, value['source'])['content'])
        self.assertEqual(self.policy['policy'], self.session.read(number, value['policy']))
        return value

    def test_receipt_distinguishes_intent_from_exact_committed_target(self):
        result = self.migrate((100,))['members']['100']
        receipt = self.prepared_receipt(100)
        intent = self.session.read(100, receipt['target_intent'])
        committed = dag.z.parse_managed_goal(self.provider.issues[100]['body'], 100)
        self.assertEqual(committed, result['published_target'])
        self.assertNotEqual(intent['payload'], committed['payload'])
        intended_payload = self.session.read(100, intent['payload'])
        actual_payload = self.session.read(100, committed['payload'])
        self.assertEqual([], intended_payload['operational']['receipts'])
        self.assertEqual(1, len(actual_payload['operational']['receipts']))
        for field in ('graph', 'spec', 'evidence'):
            self.assertEqual(intended_payload[field], actual_payload[field])
        contexts = [dag.z._comment_store.decode_envelope(row['body']) for row in self.provider.comments[100]]
        contexts = [c['context'] for c in contexts if c and c.get('context', {}).get('migration', {}).get('receipt') == result['receipt']]
        self.assertTrue(contexts)
        self.assertTrue(all(c['target_envelope'] == committed for c in contexts))

    def test_policy_graph_drift_and_unreadable_pending_artifacts_cannot_publish(self):
        update = self.provider.update_issue
        with mock.patch.object(self.provider, 'update_issue', side_effect=OSError('interrupt before body')):
            self.migrate((101,))
        receipt = self.prepared_receipt(101)
        original = copy.deepcopy((self.provider.issues, self.provider.comments))
        config = dag.z._workflow_section(self.session.project, 'workflow_adherence')['configuration']
        config['phase_dag']['nodes'][0]['prompt'] += ' Changed current graph contract.'
        result = self.migrate((101,))
        self.assertEqual('blocked', result['members']['101']['status'])
        self.assertRegex(result['members']['101']['reason'], r'(?i)policy|graph|drift')
        self.assertEqual(original, (self.provider.issues, self.provider.comments))
        self.session.project = copy.deepcopy(self.policy)
        reference = receipt['target_intent']
        removed = [c for c in self.provider.comments[101] if reference['hash'] in json.dumps(dag.z._comment_store.decode_envelope(c['body']) or {})]
        self.assertTrue(removed)
        self.provider.comments[101] = [c for c in self.provider.comments[101] if c not in removed]
        # Keep one context/receipt witness if a single packed comment held everything.
        if not self.provider.comments[101]:
            envelope = dag.z._comment_store.decode_envelope(removed[0]['body'])
            records = [r for r in envelope['artifacts'] if r['hash'] != reference['hash']]
            for body in dag.z._comment_store.pack_envelopes({k: envelope[k] for k in ('goal', 'transaction', 'context')}, records):
                self.provider.create_issue_comment(101, body)
        before = copy.deepcopy(self.provider.issues[101]); result = self.migrate((101,))
        self.assertEqual('blocked', result['members']['101']['status']); self.assertEqual(before, self.provider.issues[101])

    def test_policy_drift_before_publication_is_rechecked(self):
        append = self.provider.create_issue_comment; fired = []
        def changed(n, body):
            result = append(n, body)
            if not fired:
                fired.append(True); self.session.project['policy']['sections'][0]['instructions'] += ' Changed reviewed policy.'
            return result
        before = copy.deepcopy(self.provider.issues[100])
        with mock.patch.object(self.provider, 'create_issue_comment', side_effect=changed): result = self.migrate((100,))
        self.assertEqual('blocked', result['members']['100']['status']); self.assertEqual(before, self.provider.issues[100])

    def test_concurrent_closure_and_label_changes_survive(self):
        append = self.provider.create_issue_comment; fired = set()
        def changed(n, body):
            result = append(n, body)
            if n not in fired:
                fired.add(n)
                if n == 101: self.provider.issues[n]['state'] = 'closed'
                else: self.provider.issues[n]['labels'].append({'name': 'human-label'})
            return result
        with mock.patch.object(self.provider, 'create_issue_comment', side_effect=changed): result = self.migrate()
        self.assertEqual('migrated', result['members']['100']['status'])
        self.assertIn({'name': 'human-label'}, self.provider.issues[100]['labels'])
        self.assertEqual('closed', self.provider.issues[101]['state'])
        self.assertEqual(self.originals[101]['body'], self.provider.issues[101]['body'])
        self.assertEqual('blocked', result['members']['101']['status'])

    def test_bounded_discovery_page_migration(self):
        self.add(102); self.add(103, state='closed')
        reads = []; original = self.provider.get_issue
        with mock.patch.object(self.provider, 'get_issue', side_effect=lambda n: (reads.append(n), original(n))[1]):
            result = self.batch('migrate', limit=1)
        self.assertEqual({'100'}, set(result['members'])); self.assertEqual(2, result['remaining'])
        self.assertNotIn(101, reads); self.assertNotIn(102, reads); self.assertNotIn(103, reads)
        self.assertEqual(self.originals[101], self.provider.issues[101])

    def test_broad_execute_encounters_open_v1_without_hydrating_closed(self):
        import sys
        self.add(102, state='closed')
        main = dag.z.main
        def without_goal():
            args = list(sys.argv); offset = args.index('--goal'); del args[offset:offset + 2]
            with mock.patch.object(sys, 'argv', args): return main()
        read = self.provider.get_issue
        def open_only(n):
            self.assertNotEqual(102, n, 'Broad execute must not hydrate a closed goal')
            return read(n)
        with mock.patch.object(dag.z, 'main', side_effect=without_goal), mock.patch.object(self.provider, 'get_issue', side_effect=open_only):
            self.session.call(100)
        for n in (100, 101): self.assert_preserved(n)
        self.assertEqual(self.originals[102], self.provider.issues[102])

    def test_ambiguous_native_priority_cannot_silently_change_effective_priority(self):
        self.provider.issues[101]['labels'] = [x for x in self.provider.issues[101]['labels'] if not x['name'].startswith('zzzops:priority:')]
        before = copy.deepcopy((self.provider.issues[101], self.provider.comments[101]))
        result = self.migrate()
        self.assertEqual('migrated', result['members']['100']['status'])
        self.assertEqual('blocked', result['members']['101']['status'])
        self.assertIn('priority', result['members']['101']['reason'])
        self.assertEqual(before, (self.provider.issues[101], self.provider.comments[101]))

    def test_current_only_page_returns_actionable_next_page(self):
        self.migrate((100,)); self.add(102)
        first = self.batch('migrate', limit=1)
        self.assertEqual('already_current', first['members']['100']['status'])
        request = first['submission']
        self.assertEqual(100, request['after'])
        second = self.session.call(100, request)['next_steps'][0]
        self.assertEqual('migrated', second['members']['101']['status'])
        third = self.session.call(100, second['submission'])['next_steps'][0]
        self.assertEqual('migrated', third['members']['102']['status'])
        self.assertEqual(0, third['remaining'])

    def test_unresolved_human_blocker_prevents_otherwise_eligible_workspace(self):
        self.add(100, blockers=['User must supply deployment window']); self.migrate((100,))
        # Read-only understanding can advance; workspace tasks must still wait.
        self.normal_setup(100)
        step = next(s for s in self.session.checkpoint(100) if s.get('node', {}).get('node') == 'test_design')
        self.assertNotEqual('execute', step['kind'])
        self.assertRegex(step['reason'], r'(?i)legacy_blockers|deployment window|unresolved')

    def test_live_owner_cannot_be_automatically_recovered(self):
        from test_workflow_state import WorkflowStateValidationTests
        import time
        value = dag.z.parse_managed_goal(self.provider.issues[101]['body'], 101)
        value['workflow'] = WorkflowStateValidationTests().valid()
        value['workflow']['leases']['plan:review']['expires_at'] = time.time() + 600
        self.provider.issues[101]['body'] = dag.z.render_managed_goal(value, '## Outcome\nKeep live owner.\n', 101)
        before = copy.deepcopy((self.provider.issues[101], self.provider.comments[101]))
        self.assertEqual('blocked', self.migrate((101,))['members']['101']['status'])
        self.assertEqual(before, (self.provider.issues[101], self.provider.comments[101]))

    def test_built_package_fresh_process_resume(self):
        import subprocess, sys
        from zipfile import ZipFile
        from test_marketplace_bundle import load_builder, ROOT
        update = self.provider.update_issue
        def fail(n, payload):
            if n == 101: raise OSError('Before second body publication')
            return update(n, payload)
        with mock.patch.object(self.provider, 'update_issue', side_effect=fail): self.migrate()
        self.provider.issues[100]['state'] = 'closed'
        closed = copy.deepcopy((self.provider.issues[100], self.provider.comments[100]))
        directory = Path(self.session.control)
        archive = load_builder().build_bundle(ROOT, directory / 'bundle', '2.0.0')['plugin']
        installed = directory / 'installed'
        with ZipFile(archive) as z: z.extractall(installed)
        self.assertTrue((installed / 'zzzops/migration_batch.py').is_file())
        state = directory / 'external-provider.json'
        state.write_text(json.dumps({'issues': self.provider.issues, 'comments': self.provider.comments, 'project': self.session.project, 'runtime': self.session.runtime, 'repo': str(self.fixture.repo)}))
        request = directory / 'resume-request.json'; request.write_text(json.dumps({'operation': 'migration_batch', 'action': 'migrate', 'goals': [101]}))
        command = [sys.executable, '-B', str(Path(__file__).resolve()), '--transport', str(installed), str(state), str(request)]
        for attempt in range(2):
            result = subprocess.run(command, text=True, capture_output=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertTrue(json.loads(result.stdout)['next_steps'][0]['complete'])
            saved = json.loads(state.read_text()); self.assertEqual(closed, (saved['issues']['100'], saved['comments']['100']))
            if attempt == 0: first = copy.deepcopy(saved)
            else: self.assertEqual(first, saved)

    def normal_setup(self, number):
        tasks = [{'goal': number, 'node': name, 'item': None, 'generation': 1} for name in ('test_design', 'implement')]
        allocation = {'allocations': {t['node']: {'task': t, 'owned': [], 'consumed': ['product.txt']} for t in tasks}}
        self.session.finish(self.session.acquire('understand', number=number), {'design': 'Review the unchanged synthetic baseline.', 'allocation': allocation}, number=number)
        outputs = self.session.call(number, {'operation': 'read', 'node': {'goal': number, 'node': 'understand', 'item': None, 'generation': 1}})['next_steps'][0]['content']['outputs']
        permit = {'manifest': outputs['allocation'], 'tasks': tasks, 'policy': dag.content_hash(self.session.project['policy']), 'decision': 'approved'}
        review = {'decision': 'approved', 'report': 'Independent fixture review of exact baseline.'}
        self.session.finish(self.session.acquire('review_understanding', number=number), {'review': review, 'authorization': permit}, number=number)
        self.session.finish(self.session.acquire('approve_understanding', number=number), {'authorization': permit}, number=number)
        self.session.finish(self.session.acquire('retain_understand_findings', number=number), {
            'value': {'items': {}, 'rationale': 'No understanding findings were admitted in this fixture.'}}, number=number)
        self.session.finish(self.session.acquire('decompose', number=number), {'value': 'One atomic fixture outcome.'}, number=number)
        self.session.finish(self.session.acquire('review_decomposition', number=number), {'value': review}, number=number)
        self.session.finish(self.session.acquire('retain_decompose_findings', number=number), {
            'value': {'items': {}, 'rationale': 'No decomposition findings were admitted in this fixture.'}}, number=number)
        return review


def transport_main(installed, state_path, request_path):
    """Fresh interpreter + built distribution; JSON file is the external service."""
    import importlib.util
    import tempfile
    from types import SimpleNamespace
    state_path = Path(state_path)
    state = json.loads(state_path.read_text())
    path = Path(installed) / 'zzzops/zzzops.py'
    spec = importlib.util.spec_from_file_location('installed_batch_cli', path)
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    assert Path(api._workflow.__file__).is_relative_to(Path(installed))
    assert api._package.package_status()['ok']
    provider = object.__new__(dag.old.MemoryGoalProvider)
    provider.issues = {int(k): v for k, v in state['issues'].items()}
    provider.comments = {int(k): v for k, v in state['comments'].items()}
    provider.updates = []
    with tempfile.TemporaryDirectory() as control:
        session = dag.TaskSession(state['repo'], state['project'], state['runtime'], provider, control, api=api)
        response = session.call(100, json.loads(Path(request_path).read_text()))
    state.update(issues=provider.issues, comments=provider.comments)
    state_path.write_text(json.dumps(state))
    print(json.dumps(response))


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--transport': transport_main(*sys.argv[2:])
    else:
        import unittest
        unittest.main()
