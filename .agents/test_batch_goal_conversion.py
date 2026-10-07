"""Automatic lossless migration through public dispatch; external boundaries only."""
import copy
import json
import sys
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

    def broad(self):
        main = dag.z.main
        def without_goal():
            args = list(sys.argv); offset = args.index('--goal'); del args[offset:offset + 2]
            with mock.patch.object(sys, 'argv', args): return main()
        with mock.patch.object(dag.z, 'main', side_effect=without_goal):
            return self.session.call(100)

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

    def legacy_checkpoint(self, *, committed=True):
        fingerprint = 'sha256:' + 'a' * 64
        self.legacy_fields(100, workflow={'leases': {}, 'receipts':
            {'legacy-committed': {'hash': fingerprint}} if committed else {},
            'workers': {}, 'assessments': {}, 'artifacts': {}})
        envelope = {'schema_version': 2, 'goal': 100, 'transaction': 'legacy-committed',
                    'context': {'request_id': 'legacy-committed', 'fingerprint': fingerprint,
                                'root_id': 'historical-root'}, 'artifacts': []}
        self.provider.comments[100].append({'id': 900, 'body': dag.z._comment_store.encode_envelope(envelope)})
        self.assertTrue(self.migrate((100,))['complete'])
        return self.payload()

    def prepare_legacy_graph(self, *, expected=0):
        _, payload = self.payload()
        graph = self.session.read(100, payload['graph'])
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        result = self.session.call(100, {'operation': 'graph_prepare', 'graph': graph,
            'rationale': 'Preserve committed legacy history during graph repair'}, expected=expected)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        return result

    def replace_legacy_payload(self, envelope, payload):
        envelope = copy.deepcopy(envelope)
        envelope['payload'] = self.blob(payload)
        envelope['revision'] += 1
        self.provider.issues[100]['body'] = '<!-- zzzops-goal\n' + json.dumps(envelope) + '\nzzzops-goal -->'

    def edit_checkpoint_contexts(self, change, *, legacy=False):
        for row in self.provider.comments[100]:
            envelope = dag.z._comment_store.decode_envelope(row['body'])
            if envelope and bool(envelope.get('context', {}).get('fingerprint')) == legacy:
                change(envelope)
                row['body'] = dag.z._comment_store.encode_envelope(envelope)

    def test_graph_prepare_accepts_committed_legacy_history_without_writes(self):
        self.legacy_checkpoint()
        self.assertEqual(self.prepare_legacy_graph(), self.prepare_legacy_graph())
        self.assert_preserved(100)

    def test_graph_prepare_legacy_proof_survives_specification_and_reviewed_policy_changes(self):
        envelope, payload = self.legacy_checkpoint()
        payload['spec'] = self.blob({'type': 'goal_specification', 'content': 'Later specification',
            'producer': None, 'provenance': {'actor': 'later-author', 'source': None,
                                           'policy': dag.content_hash(self.session.project['policy'])}})
        self.replace_legacy_payload(envelope, payload)
        self.session.project['policy']['sections'][0]['rationale'] = 'Later reviewed policy rationale'
        result = self.prepare_legacy_graph()
        self.assertEqual(dag.content_hash(self.session.project['policy']), result['next_steps'][0]['proposal']['policy'])

    def test_graph_prepare_pending_legacy_history_still_blocks(self):
        self.legacy_checkpoint(committed=False)
        self.assertIn('Uncommitted checkpoint', json.dumps(self.prepare_legacy_graph(expected=2)))

    def test_graph_prepare_legacy_context_requires_goal_and_exact_fingerprint(self):
        self.legacy_checkpoint()
        original = copy.deepcopy(self.provider.comments)
        for field, value in (('fingerprint', 'sha256:' + 'b' * 64), ('fingerprint', None), ('goal', 101)):
            with self.subTest(field=field, value=value):
                self.provider.comments = copy.deepcopy(original)
                def change(row):
                    if field == 'goal': row['goal'] = value
                    else: row['context'][field] = value
                self.edit_checkpoint_contexts(change, legacy=True)
                self.assertIn('Uncommitted checkpoint', json.dumps(self.prepare_legacy_graph(expected=2)))

    def test_graph_prepare_orphan_migration_artifacts_do_not_prove_completion(self):
        envelope, payload = self.legacy_checkpoint()
        payload['operational']['receipts'] = []
        self.replace_legacy_payload(envelope, payload)
        self.assertIn('Uncommitted checkpoint', json.dumps(self.prepare_legacy_graph(expected=2)))

    def test_graph_prepare_migration_transaction_requires_exact_binding(self):
        self.legacy_checkpoint()
        original = copy.deepcopy(self.provider.comments)
        variants = {
            'request_id': None, 'request_hash': 'sha256:' + 'b' * 64, 'source_hash': 'sha256:' + 'b' * 64,
            'response': None, 'migration': None, 'source_envelope': None,
            'target_envelope': None, 'entry_payload': None, 'payload': None,
        }
        for field, value in variants.items():
            with self.subTest(field=field):
                self.provider.comments = copy.deepcopy(original)
                self.edit_checkpoint_contexts(lambda row: row['context'].update({field: value}))
                self.assertRegex(json.dumps(self.prepare_legacy_graph(expected=2)), '(?i)migration|checkpoint')
        for field, value in (('goal', 101), ('transaction', 'wrong-transaction')):
            with self.subTest(field=field):
                self.provider.comments = copy.deepcopy(original)
                self.edit_checkpoint_contexts(lambda row: row.update({field: value}))
                self.assertRegex(json.dumps(self.prepare_legacy_graph(expected=2)), '(?i)migration|checkpoint')

    def test_graph_prepare_conflicting_migration_transaction_blocks(self):
        self.legacy_checkpoint()
        row = next(dag.z._comment_store.decode_envelope(r['body']) for r in self.provider.comments[100]
                   if (dag.z._comment_store.decode_envelope(r['body']) or {}).get('context', {}).get('migration'))
        row['context']['source_hash'] = 'sha256:' + 'b' * 64
        self.provider.comments[100].append({'id': 901, 'body': dag.z._comment_store.encode_envelope(row)})
        self.assertIn('conflicting exact migration transaction', json.dumps(self.prepare_legacy_graph(expected=2)))

    def test_graph_prepare_committed_migration_request_identity_and_hash_must_match(self):
        envelope, payload = self.legacy_checkpoint()
        for field, value in (('request', 'different-request'), ('payload', 'sha256:' + 'b' * 64)):
            with self.subTest(field=field):
                altered = copy.deepcopy(payload)
                altered['operational']['receipts'][0][field] = value
                self.replace_legacy_payload(envelope, altered)
                self.assertIn('request identity or fingerprint mismatch', json.dumps(self.prepare_legacy_graph(expected=2)))

    def test_graph_prepare_migrated_history_preserves_current_results(self):
        config = dag.z._workflow_section(self.session.project, 'workflow_adherence')['configuration']
        config['phase_dag'] = self.graph
        self.legacy_checkpoint()
        self.produce()
        before = self.result('produce')
        self.prepare_legacy_graph()
        self.assertEqual(before, self.result('produce'))
        _, payload = self.payload()
        changed = self.session.read(100, payload['graph'])
        changed['nodes'][0]['prompt'] += ' Change settled semantics.'
        result = self.session.call(100, {'operation': 'graph_prepare', 'graph': changed,
            'rationale': 'Must preserve settled Results'}, expected=2)
        self.assertRegex(json.dumps(result), '(?i)settled|current|preserv')

    def test_graph_prepare_pending_v2_checkpoint_after_migration_still_blocks(self):
        self.legacy_checkpoint()
        ready = next(s for s in self.session.ready() if s['node']['node'] == 'understand')
        receipt = json.loads(Path(ready['policy']['path']).read_text())['policy_receipt']
        request = {**ready['start'], 'policy_receipt': receipt, 'request_id': 'interrupted-v2'}
        with mock.patch.object(self.provider, 'update_issue', side_effect=RuntimeError('provider unavailable')):
            self.session.call(100, request, expected=2)
        self.assertIn('Uncommitted checkpoint', json.dumps(self.prepare_legacy_graph(expected=2)))

    def test_graph_prepare_missing_rooted_source_policy_or_target_blocks(self):
        _, payload = self.legacy_checkpoint()
        response = self.session.read(100, payload['operational']['receipts'][0]['result'])
        receipt_ref = response['next_steps'][0]['receipt']
        receipt = self.session.read(100, receipt_ref)
        refs = [receipt_ref, receipt['source'], receipt['policy'], receipt['target_intent'], receipt['target_payload']]
        original = copy.deepcopy(self.provider.comments)
        for reference in refs:
            with self.subTest(reference=reference):
                self.provider.comments = copy.deepcopy(original)
                for row in self.provider.comments[100]:
                    envelope = dag.z._comment_store.decode_envelope(row['body'])
                    if not envelope: continue
                    envelope['artifacts'] = [a for a in envelope['artifacts'] if a['hash'] != reference['hash']]
                    row['body'] = dag.z._comment_store.encode_envelope(envelope)
                self.assertRegex(json.dumps(self.prepare_legacy_graph(expected=2)), '(?i)artifact|migration|checkpoint')

    def test_graph_prepare_missing_or_corrupt_rooted_response_blocks(self):
        _, payload = self.legacy_checkpoint()
        identity = payload['operational']['receipts'][0]['result']['hash']
        original = copy.deepcopy(self.provider.comments)
        for corrupt in (False, True):
            with self.subTest(corrupt=corrupt):
                self.provider.comments = copy.deepcopy(original)
                for row in self.provider.comments[100]:
                    envelope = dag.z._comment_store.decode_envelope(row['body'])
                    if not envelope: continue
                    if corrupt:
                        for record in envelope['artifacts']:
                            if record['hash'] == identity:
                                record.clear()
                                record.update(kind='legacy', hash=identity, content={'next_steps': []})
                    else:
                        envelope['artifacts'] = [a for a in envelope['artifacts'] if a['hash'] != identity]
                    row['body'] = dag.z._comment_store.encode_envelope(envelope)
                self.assertRegex(json.dumps(self.prepare_legacy_graph(expected=2)), '(?i)artifact|migration|checkpoint')

    def test_graph_prepare_wrong_repository_goal_or_converter_lineage_blocks(self):
        envelope, payload = self.legacy_checkpoint()
        committed = payload['operational']['receipts'][0]
        response = self.session.read(100, committed['result'])
        receipt = self.session.read(100, response['next_steps'][0]['receipt'])
        for field, value in (('repository', 'other/repo'), ('goal', 101), ('converter', 'custom-converter')):
            with self.subTest(field=field):
                altered = copy.deepcopy(response)
                reference = self.blob({**receipt, field: value})
                reference['uri'] = 'zzzops:owner/repo:goal:100:' + reference['hash']
                altered['next_steps'][0]['receipt'] = reference
                replacement = copy.deepcopy(payload)
                reference = self.blob(altered)
                reference['uri'] = 'zzzops:owner/repo:goal:100:' + reference['hash']
                replacement['operational']['receipts'][0]['result'] = reference
                self.replace_legacy_payload(envelope, replacement)
                self.assertRegex(json.dumps(self.prepare_legacy_graph(expected=2)), '(?i)migration|checkpoint')

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
        self.assertTrue(any(s.get('kind') == 'execute' and s.get('node', {}).get('node') == 'requirements' for s in steps))
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

    def test_null_transaction_context_is_ignored_during_migration(self):
        envelope = {
            'schema_version': 2, 'goal': 100, 'transaction': 'historical-null-context',
            'context': None, 'artifacts': [],
        }
        self.provider.comments[100].append({
            'id': 900, 'body': dag.z._comment_store.encode_envelope(envelope),
        })

        result = self.migrate((100,))

        self.assertEqual('migrated', result['members']['100']['status'])
        self.assert_preserved(100)

    def test_malformed_transaction_context_blocks_only_its_batch_member(self):
        envelope = {
            'schema_version': 2, 'goal': 100, 'transaction': 'historical-scalar-context',
            'context': 'invalid', 'artifacts': [],
        }
        self.provider.comments[100].append({
            'id': 900, 'body': dag.z._comment_store.encode_envelope(envelope),
        })

        result = self.migrate()

        self.assertEqual('blocked', result['members']['100']['status'])
        self.assertIn('context must be an object or null', result['members']['100']['reason'])
        self.assertEqual('migrated', result['members']['101']['status'])
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

    def test_broad_execute_migrates_only_the_selected_v1_goal(self):
        self.add(102, state='closed')
        untouched = copy.deepcopy({n: (self.provider.issues[n], self.provider.comments[n]) for n in (101, 102)})
        with mock.patch.object(dag.z._migration_batch, 'run', wraps=dag.z._migration_batch.run) as migration, \
                mock.patch.object(self.provider, 'update_issue', wraps=self.provider.update_issue) as updates:
            response = self.broad()
        self.assertEqual(1, migration.call_count)
        self.assertEqual({'action': 'migrate', 'goals': [100]}, migration.call_args.args[1])
        self.assertEqual(1, updates.call_count)
        self.assert_preserved(100)
        self.assertEqual(untouched, {n: (self.provider.issues[n], self.provider.comments[n]) for n in (101, 102)})
        self.assertFalse(any(step.get('kind') == 'migration_batch' for step in response['next_steps']))

    def test_broad_execute_selected_v2_skips_all_migration_work(self):
        self.legacy_fields(100, priority='P0')
        for label in self.provider.issues[100]['labels']:
            if label['name'].startswith('zzzops:priority:'):
                label['name'] = 'zzzops:priority:P0'
        self.originals[100] = copy.deepcopy(self.provider.issues[100])
        self.migrate((100,))
        self.add(101, state='closed')
        self.legacy_fields(101, status='done')
        for label in self.provider.issues[101]['labels']:
            if label['name'].startswith('zzzops:status:'):
                label['name'] = 'zzzops:status:done'
        self.originals[101] = copy.deepcopy(self.provider.issues[101])
        untouched = copy.deepcopy((self.provider.issues[101], self.provider.comments[101]))
        def current_index(*args, **kwargs):
            capability, rows, findings, raw_bytes, reads, excluded = self.index(*args, **kwargs)
            for row in rows:
                row['schema_version'] = dag.z.parse_managed_goal(
                    self.provider.issues[row['number']]['body'], row['number'])['schema_version']
            return capability, rows, findings, raw_bytes, reads, excluded
        with mock.patch.object(dag.z, 'github_repository_goal_index', side_effect=current_index), \
                mock.patch.object(dag.z._migration_batch, 'run', wraps=dag.z._migration_batch.run) as migration, \
                mock.patch.object(self.provider, 'update_issue', wraps=self.provider.update_issue) as updates:
            response = self.broad()
        self.assertEqual(0, migration.call_count)
        self.assertEqual(0, updates.call_count)
        self.assertEqual(untouched, (self.provider.issues[101], self.provider.comments[101]))
        self.assertTrue(any(step.get('kind') == 'execute' and step.get('node', {}).get('node') == 'requirements'
                            for step in response['next_steps']))

    def test_broad_execute_respects_dependency_before_lazy_migration(self):
        self.add(100, dependencies=(101,))
        untouched = copy.deepcopy((self.provider.issues[100], self.provider.comments[100]))
        with mock.patch.object(dag.z._migration_batch, 'run', wraps=dag.z._migration_batch.run) as migration:
            self.broad()
        self.assertEqual({'action': 'migrate', 'goals': [101]}, migration.call_args.args[1])
        self.assert_preserved(101)
        self.assertEqual(untouched, (self.provider.issues[100], self.provider.comments[100]))

    def test_failed_selected_migration_blocks_and_retries_without_advancing(self):
        valid = copy.deepcopy(self.provider.issues[100])
        self.legacy_fields(100, engineering_rigor={'risk_categories': ['unconfigured_risk']})
        untouched = copy.deepcopy((self.provider.issues[101], self.provider.comments[101]))
        first = self.broad()
        self.assertEqual('blocker', first['next_steps'][0]['kind'])
        self.assertEqual(100, first['next_steps'][0]['goal'])
        self.assertEqual(untouched, (self.provider.issues[101], self.provider.comments[101]))
        self.provider.issues[100] = valid
        self.originals[100] = copy.deepcopy(valid)
        second = self.broad()
        self.assert_preserved(100)
        self.assertEqual(untouched, (self.provider.issues[101], self.provider.comments[101]))
        self.assertFalse(any(step.get('kind') == 'migration_batch' for step in second['next_steps']))

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
