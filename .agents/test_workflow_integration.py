"""Regression journeys through actual goal projection and workflow evidence."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_zzzops as fixtures
z = fixtures.zzzops


from test_evidence_dag_journeys import DagFixture


class GenericIntegrationFreshnessTests(DagFixture):
    def test_generic_goal_routes_declared_task_without_hidden_phase_rigor_assessment(self):
        envelope, _payload = self.payload()
        self.assertNotIn("engineering_rigor", envelope)
        steps = self.session.checkpoint(100)
        self.assertFalse(any(step.get("kind") == "assess" for step in steps))
        executable = [step for step in steps if step.get("kind") == "execute"]
        self.assertEqual(["produce"], [step["node"]["node"] for step in executable])
        self.assertEqual("delegate", executable[0]["assignment"])
        self.assertIn(executable[0]["selection"], self.session.runtime["available_pairs"])
        work = self.session.acquire("produce")
        self.session.finish(work, {"value": "Configured generic task needs no hidden legacy assessment state"})

    def test_worker_role_remains_delegated_with_same_actual_pair_as_root(self):
        pair = {"model": "same-capable-model", "effort": "medium"}
        routing = z._workflow_section(self.session.project, "model_routing")["configuration"]
        routing["model_inventory"]["reviewed_pairs"] = [{**pair, "tier": "bounded", "cost": 1}]
        self.session.runtime.update(root_pair=pair, available_pairs=[pair])
        self.install(self.graph)
        steps = self.session.ready()
        self.assertEqual(1, len(steps))
        self.assertEqual("delegate", steps[0]["assignment"])
        self.assertEqual(pair, steps[0]["selection"])
        work = self.session.acquire("produce", actor="distinct-worker")
        self.assertEqual(pair, work["lease"]["selection"])
        self.session.finish(work, {"value": "Same model pair is a distinct actual executor"})

    def test_missing_delegation_and_expired_unknown_worker_block_until_exact_stopped_recovery(self):
        self.assertEqual({"produce"}, self.names())
        self.session.runtime["delegation"]["available"] = False
        steps = self.session.checkpoint(100)
        self.assertFalse(any(step.get("kind") == "execute" for step in steps))
        self.assertRegex(json.dumps(steps), r"(?i)delegat|capability|discovery")
        self.session.runtime["delegation"]["available"] = True
        work = self.session.acquire("produce")
        with mock.patch.object(z._workflow.time, "time", return_value=work["lease"]["expires_at"] + 1):
            steps = self.session.checkpoint(100)
            self.assertFalse(any(step.get("kind") == "execute" for step in steps))
            recovery_steps = [step for step in steps if "recovery_contract" in step or step.get("kind") == "recover"]
            self.assertTrue(recovery_steps)
            recovery = recovery_steps[0]
            request = copy.deepcopy(recovery.get("submission", recovery.get("recovery_contract")))
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            response = self.session.call(100, {**request, "worker_status": "unknown", "evidence": "Timeout alone"}, expected=2)
            self.assertRegex(json.dumps(response), r"(?i)stopped|liveness|unknown|recovery")
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
            response = self.session.call(100, {**request, "lease": "different-token", "worker_status": "stopped", "evidence": "Observed terminal worker"}, expected=2)
            self.assertRegex(json.dumps(response), r"(?i)lease|token|owner|exact")
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
            self.session.call(100, {**request, "worker_status": "stopped", "evidence": "Fixture worker terminal state observed"})
        replacement = self.session.acquire("produce")
        self.assertNotEqual(work["lease"]["token"], replacement["lease"]["token"])
        self.session.finish(replacement, {"value": "fresh exact owner"})

    def test_start_bind_receipt_and_actual_pair_are_guarded_before_writes(self):
        steps = self.session.ready()
        self.assertEqual(1, len(steps))
        step = steps[0]
        receipt = json.loads(Path(step["policy"]["path"]).read_text())["policy_receipt"]
        self.assertNotIn(receipt, json.dumps(step))
        self.assertNotEqual(receipt, step["policy"]["sha256"])
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        for value in (None, "stale-receipt", step["policy"]["sha256"]):
            request = {**step["start"], "policy_receipt": value}
            response = self.session.call(100, request, expected=2)
            self.assertRegex(json.dumps(response), r"(?i)policy.receipt|policy.*read")
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
        acquired = self.session.call(100, {**step["start"], "policy_receipt": receipt})["next_steps"][0]
        self.assertIsNone(acquired["lease"]["worker"])
        bind = {**acquired["bind"], "actor": "receipt-worker", "selection": acquired["lease"]["selection"]}
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        for changes, diagnostic in (({"policy_receipt": None}, r"(?i)policy.receipt|policy.*read"),
                                    ({"policy_receipt": receipt, "selection": {"model": "unselected", "effort": "low"}}, r"(?i)model|effort|selection|pair")):
            response = self.session.call(100, {**bind, **changes}, expected=2)
            self.assertRegex(json.dumps(response), diagnostic)
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.call(100, {**bind, "policy_receipt": receipt})
        acquired["bound_actor"] = "receipt-worker"
        self.assertNotIn(receipt, self.provider.issues[100]["body"])
        self.assertNotIn(receipt, json.dumps(acquired))
        self.session.finish(acquired, {"value": "bound actual executor"})

    def test_preview_and_operational_revision_preserve_exact_generic_inputs(self):
        execute = self.session.call(100)["next_steps"]
        ready_steps = [step for step in execute if step.get("node", {}).get("node") == "produce" and step.get("start")]
        self.assertTrue(ready_steps, "Generic producer must expose public acquisition")
        ready = ready_steps[0]
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        preview = self.session.call(100, intent="preview")["next_steps"]
        preview_steps = [step for step in preview if step.get("node", {}).get("node") == "produce"]
        self.assertTrue(preview_steps, "Preview must expose the same generic producer")
        preview_ready = preview_steps[0]
        self.assertEqual(ready["input_hash"], preview_ready["input_hash"])
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.provider.create_issue_comment(100, "Bookkeeping acknowledgement")
        work = self.session.acquire("produce")
        self.assertEqual(ready["input_hash"], work["input_hash"], "Own lease/body revision cannot stale semantic inputs")
        self.session.finish(work, {"value": "same approved input"})
        self.assertNotIn("produce", self.names())

    def test_configuration_and_instruction_drift_each_reject_current_assignment(self):
        work = self.session.acquire("produce")
        original = copy.deepcopy(self.session.project)
        for field in ("configuration", "instructions"):
            with self.subTest(field=field):
                self.session.project = copy.deepcopy(original)
                section = z._workflow_section(self.session.project, "verification_testing")
                if field == "configuration":
                    configuration = section["configuration"]
                    configuration["required_ci"] = ("disabled" if configuration.get("required_ci") != "disabled" else "inspect_exact_pr_head")
                else:
                    section["instructions"] = section.get("instructions", "") + " Preserve failing evidence."
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, self.session.submission(work, {"value": "stale policy"}, "changed-" + field), expected=2)
                self.assertRegex(json.dumps(response), r"(?i)policy|input|stale|changed")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.project = original
        self.session.finish(work, {"value": "unchanged approved policy"})


class WorkflowIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.GoalTransitionTests()
        self.adapter = fixtures.FakeGoalTransitionAdapter(self.fixture.issue())
        self.graph = {'phases': [{'id': 'plan'}]}
        self.nodes = {'plan': {'review': {'independent': True}}}
        self.project = {'backend': 'github_issues', 'repository': {'identity': 'owner/repo'},
                        'policy': {'sections': [{'id': 'workflow_adherence', 'configuration': {'phase_dag': self.graph}}]}}

    def test_rendered_goal_produces_live_inputs_without_phase_evidence(self):
        # The regression now observes persisted public generic task evidence.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.EvidenceDagPublicTests.test_parallel_reviews_independent_leases_and_join',
        )

    def test_operational_revision_and_preview_do_not_change_inputs(self):
        # The regression now observes persisted public generic task evidence.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_workflow_integration.GenericIntegrationFreshnessTests.test_preview_and_operational_revision_preserve_exact_generic_inputs',
        )

    def test_configuration_and_instruction_changes_each_invalidate_open_evidence(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            "test_workflow_integration.GenericIntegrationFreshnessTests.test_configuration_and_instruction_drift_each_reject_current_assignment",
        )

    def test_submission_then_backend_reread_requires_review_not_reexecution(self):
        # The regression now observes persisted public generic task evidence.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.EvidenceDagPublicTests.test_parallel_reviews_independent_leases_and_join',
        )

    def test_every_acceptance_bullet_is_required(self):
        body = '## Acceptance\n- [ ] Must work\n- Preserve data\n- [x] Already done\n\n## Constraints\n- Out of scope\n'
        self.assertEqual(['Must work', 'Preserve data', 'Already done'], z._goals.goal_acceptance_criteria(body))

    def test_execute_semantic_intent_reaches_workflow(self):
        self.assertEqual(['zzzops.py', 'workflow', '--intent', 'execute', '--source-skill', '$execute-zzzops'],
                         z.normalize_workflow_entrypoint(['zzzops.py', '--intent', 'execute']))

    def test_rejected_review_returns_phase_for_correction(self):
        # The regression now observes persisted public generic task evidence.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.EvidenceDagPublicTests.test_specialist_missing_regression_corrects_tests_then_code_and_rereviews',
        )

class PublicWorkflowJourneyTests(unittest.TestCase):
    def setUp(self):
        if self._testMethodName in ('test_new_goal_with_null_rigor_reaches_assessment_and_assignment', 'test_blocker_step_supplies_exact_resolution_request', 'test_expiry_requires_recovery_and_missing_delegation_blocks', 'test_start_and_worker_bind_require_current_policy_read_without_writes_on_rejection', 'test_persisted_execute_review_human_approval_journey', 'test_actor_selection_and_duplicate_submission_are_guarded'):
            return  # Replacement owns an isolated public generic fixture; no legacy configuration patch.
        import json
        import contextlib
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.adapter = fixtures.FakeGoalTransitionAdapter(fixtures.GoalTransitionTests().issue())
        template = json.loads((fixtures.PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        self.project = {'backend': 'github_issues', 'repository': {'identity': 'owner/repo'}, 'policy': template['policy']}
        routing = next(s for s in self.project['policy']['sections'] if s['id'] == 'model_routing')['configuration']
        routing['model_inventory']['reviewed_pairs'] = [
            {'model': 'root', 'effort': 'high', 'tier': 'architectural', 'cost': 10},
            {'model': 'worker', 'effort': 'medium', 'tier': 'bounded', 'cost': 2}]
        self.runtime = {'root_pair': {'model': 'root', 'effort': 'high'}, 'available_pairs': [{'model': 'root', 'effort': 'high'}, {'model': 'worker', 'effort': 'medium'}], 'root_id': 'root-thread', 'delegation': {'available': True, 'tool': 'spawn_agent', 'discovery_complete': True}}
        # Restrict the graph for this transition-focused fixture; projection,
        # live inputs, routing, records, and persisted transitions remain real.
        self.graph = {'phases': [{'id': 'plan'}]}
        self.nodes = {'plan': {'assignment_group': 'planning', 'review': {'independent': True, 'human_approval': True, 'assignment_group': 'review'}}}
        self.patches = [mock.patch.object(z, 'GitHubGoalTransitionAdapter', return_value=self.adapter), mock.patch.object(z, '_workflow_phase_configuration', return_value=(self.graph, self.nodes)), mock.patch.object(z, 'portfolio_snapshot', side_effect=lambda repo: {'valid': True, 'complete': True, 'goals': [z.github_goal_record(self.adapter.issue)]})]
        for patch in self.patches:
            patch.start(); self.addCleanup(patch.stop)
        self.engine = z.workflow_engine(self.repo, self.project, self.runtime)
        self.engine.locked = contextlib.nullcontext
        self.seq = 0

    def mutate(self, **payload):
        self.seq += 1
        if payload.get('operation') in {'start', 'bind'}:
            import json
            kind = payload.get('kind')
            if kind is None:
                goal = z.github_goal_record(self.adapter.issue)
                kind = next(v['kind'] for v in goal['workflow']['leases'].values() if v['token'] == payload['lease'])
            step = {'phase': payload['phase'], 'kind': kind}
            z._policy_context.attach({'next_steps': [step]}, self.repo, self.project, source='$execute-zzzops')
            payload.setdefault('policy_receipt', json.loads(Path(step['policy']['path']).read_text())['policy_receipt'])
        return self.engine.mutate(42, {'request_id': str(self.seq), **payload})

    def start(self, kind):
        step = self.engine.step(42)[0]
        self.assertEqual(kind, step['kind'])
        return self.mutate(operation='start', phase='plan', kind=kind, input_hash=step['input_hash'])['next_steps'][0]

    def prepare(self):
        step = self.engine.step(42)[0]
        self.assertEqual('assess', step['kind'])
        self.mutate(operation='assess', phase='plan', input_hash=step['input_hash'], files=[], dimensions={'consequence': 'bounded', 'boundedness': 'atomic', 'engineering_rigor': 'structured'})
        step = self.start('execute')
        lease = step['lease']
        self.mutate(operation='bind', phase='plan', lease=lease['token'], actor='builder', selection=lease['selection'])
        record = fixtures.PhaseEvidenceTests().record('plan', step['input_envelope'])
        record.update(actor='builder', selection=lease['selection'], routing=step['result_contract']['record']['routing'], output=self.engine.artifact(42, {'output': 'output'}))
        return lease, record

    def test_new_goal_with_null_rigor_reaches_assessment_and_assignment(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_workflow_integration.GenericIntegrationFreshnessTests.test_generic_goal_routes_declared_task_without_hidden_phase_rigor_assessment')

    def test_start_and_worker_bind_require_current_policy_read_without_writes_on_rejection(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_workflow_integration.GenericIntegrationFreshnessTests.test_start_bind_receipt_and_actual_pair_are_guarded_before_writes',
        )

    def test_persisted_execute_review_human_approval_journey(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_phase_review_contract.GenericReviewGateTests.test_review_is_not_human_approval_and_root_binds_current_subject_and_review',
        )

    def test_actor_selection_and_duplicate_submission_are_guarded(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_workflow_integration.GenericIntegrationFreshnessTests.test_start_bind_receipt_and_actual_pair_are_guarded_before_writes',
            'test_evidence_dag_journeys.EvidenceDagPublicTests.test_wrong_actor_cannot_submit_and_valid_owner_still_can',
            'test_evidence_dag_journeys.EvidenceDagPublicTests.test_exact_retry_is_idempotent_and_changed_payload_rejected',
            'test_evidence_dag_journeys.EvidenceDagPublicTests.test_ordinary_artifact_shaped_content_cannot_issue_a_result',
        )

    def test_expiry_requires_recovery_and_missing_delegation_blocks(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_workflow_integration.GenericIntegrationFreshnessTests.test_missing_delegation_and_expired_unknown_worker_block_until_exact_stopped_recovery')

    def test_blocker_step_supplies_exact_resolution_request(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_evidence_dag_journeys.EvidenceDagPublicTests.test_human_answers_drive_affected_reinvestigation_through_generic_admission')


class MigrationEvidenceFreshnessTests(unittest.TestCase):
    """Actual input/review projection with synthetic provider observations."""
    def setUp(self):
        pass  # Each retained ID invokes its concrete isolated generic public fixture.

    def live(self, goal=None):
        self.engine.invalidate()
        return self.engine.inputs(self.goal if goal is None else goal, self.fixture.graph)

    def approved(self, live):
        record = fixtures.PhaseEvidenceTests().record('plan', live['plan'])
        evidence = z.record_phase_result(z.empty_phase_evidence(), 'plan', record, live['plan'])
        artifact = {'reference': 'urn:sha256:' + 'a' * 64, 'hash': 'sha256:' + 'a' * 64}
        evidence = z.record_phase_review(evidence, 'plan', artifact, 'independent-reviewer', decision='approved')
        return evidence

    def test_external_release_change_stales_review_without_file_or_policy_change(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_migration_acceptance.GenericMigrationInputTests.test_release_commit_drift_blocks_exact_consumers_with_unchanged_document_and_policy')

    def test_unavailable_provider_is_not_cached_as_fresh_and_restores(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_migration_acceptance.GenericMigrationInputTests.test_unavailable_provider_is_unknown_and_restoration_reuses_exact_input')

    def test_attestation_revocation_and_deletion_stale_only_affected_goal(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_migration_acceptance.GenericMigrationInputTests.test_revoked_or_deleted_attestation_blocks_only_its_consumers_then_exact_restore')

    def test_two_goal_assessments_cannot_substitute_on_resume(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_migration_acceptance.GenericMigrationInputTests.test_foreign_goal_assessment_never_substitutes_for_exact_goal_spec')

    def test_current_reassessment_reuses_substantive_output_with_new_review(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_migration_acceptance.GenericMigrationInputTests.test_current_reassessment_requires_new_review_even_for_identical_conclusion')

    def test_public_dispatch_exposes_changed_release_input_identity(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_migration_acceptance.GenericMigrationInputTests.test_public_dispatch_exposes_new_current_release_binding_after_reassessment')


    def test_affected_phases_share_one_observation_and_next_projection_refreshes(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_migration_acceptance.GenericMigrationInputTests.test_two_declared_consumers_share_one_observation_per_projection_then_refresh')

    def test_public_migration_blocker_contract_persists_and_replays_receipt(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_migration_acceptance.GenericMigrationDiscoveryTests.test_factual_root_report_replays_exactly_without_granting_missing_evidence_authority')


class MigrationDiscoveryJourneyTests(unittest.TestCase):
    """Use only public output contracts to discover and prepare local evidence."""
    def setUp(self):
        pass  # Each retained ID invokes its concrete isolated generic public fixture.

    def step(self):
        code, result, error = self.harness.run_main('--intent', 'execute', '--goal', '42', '--runtime', str(self.runtime))
        self.assertEqual(0, code, result); self.assertEqual('', error)
        return next(s for s in result['next_steps'] if s.get('phase') == 'plan')

    def submit(self, step, payload):
        self.sequence += 1
        payload = dict(payload, request_id=f'discovery-{self.sequence}')
        self.payload.write_text(json.dumps(payload))
        args = [str(self.runtime) if a == '<runtime.json>' else str(self.payload) if a == '<submission.json>' else a
                for a in step['command']]
        code, result, error = self.harness.run_main(*args)
        self.assertEqual(0, code, result); self.assertEqual('', error)
        return result

    def missing(self):
        step = self.step()
        self.assertEqual('assess', step['kind'])
        self.assertIn('migration_evidence', step, 'Ordinary assess must disclose the conditional evidence dependency')
        guidance = step['migration_evidence']
        self.assertTrue(guidance.get('when'), 'Applicability remains reasoned root judgment')
        relative = guidance['path']
        self.assertEqual('.zzzops/migration/42.json', relative)
        request = copy.deepcopy(step['submission'])
        self.assertEqual('assess', request['operation'])
        request['files'].append(relative)
        self.submit(step, request)
        blocker = self.step()
        self.assertEqual('blocker', blocker['kind'])
        self.assertEqual(relative, blocker['path'])
        return self.repo / relative, blocker, self.resource(blocker)

    def resource(self, blocker):
        import hashlib
        self.assertIn('preparation', blocker, 'Missing evidence must link complete preparation guidance')
        link = blocker['preparation']
        raw = Path(link['path']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), link['sha256'].removeprefix('sha256:'))
        data = json.loads(raw)
        self.assertTrue(data.get('instructions'))
        template = data['template']
        for field in ('schema_version', 'repository', 'goal', 'goal_spec', 'action', 'release_snapshot', 'contracts'):
            self.assertIn(field, template)
        self.assertEqual('owner/repo', template['repository'])
        self.assertEqual(42, template['goal'])
        self.assertEqual(blocker['input_envelope']['goal_spec'], template['goal_spec'])
        self.assertEqual(blocker['evidence']['release_snapshot'], template['release_snapshot'])
        self.assertEqual('unknown', template['contracts'][0]['status'])
        self.assertFalse(template['contracts'][0]['evidence'])
        examples = data['evidence_templates']
        self.assertIn('contract_investigation', examples); self.assertIn('owner_attestation', examples)
        for example in examples.values():
            self.assertFalse(example.get('author'), 'Never manufacture an agent or owner statement')
        self.assertFalse(examples['owner_attestation'].get('statement'))
        self.assertFalse(examples['contract_investigation'].get('rationale'))
        self.observation_shapes(data)
        return data

    def observation_shapes(self, resource):
        observations = resource['evidence_templates']['contract_investigation'].get('observations')
        self.assertIsInstance(observations, list)
        presence = [o for o in observations if isinstance(o, dict) and
                    {'commit', 'path', 'release_id', 'contract_present'} <= set(o)]
        distribution = [o for o in observations if isinstance(o, dict) and
                        {'commit', 'path', 'finding'} <= set(o)]
        self.assertTrue(presence, 'Resource must expose fillable contract-presence observation fields')
        self.assertTrue(distribution, 'Resource must expose fillable distribution-inspection fields')
        for observation in observations:
            self.assertFalse(observation.get('commit'), 'Do not fabricate an inspected commit')
            self.assertFalse(observation.get('path'), 'Do not fabricate an inspected file')
            self.assertIsNone(observation.get('contract_present'), 'Do not fabricate presence or absence')
            self.assertFalse(observation.get('finding'), 'Do not fabricate a distribution finding')
        guidance = resource.get('observation_guidance', {})
        for kind in ('development', 'published', 'distribution', 'path'):
            self.assertTrue(guidance.get(kind), f'Resource must explain {kind} observation semantics')
        self.assertIn('release_id', guidance['development'])
        self.assertIn('null', guidance['development'].lower())
        for term in ('release_id', 'commit', 'release_snapshot', 'contract_present'):
            self.assertIn(term, guidance['published'])
        self.assertIn('finding', guidance['distribution'])
        self.assertIn('relative', guidance['path'].lower())
        return presence[0], distribution[0]

    def filled(self, resource, kind='contract_investigation'):
        # Fill only shapes disclosed by the public resource. Facts below are
        # explicit synthetic investigation, never private fixture wire format.
        document = copy.deepcopy(resource['template'])
        document['action'] = 'Replace only synthetic project cache-v2 records'
        contract = copy.deepcopy(document['contracts'][0])
        contract.update(id='cache-v2', boundary='Only experimental project cache records',
                        status='unreleased', scope=['project-cache/v2'])
        evidence = copy.deepcopy(resource['evidence_templates'][kind])
        evidence.update(kind=kind, author='synthetic-investigator' if kind == 'contract_investigation' else 'synthetic-owner',
                        goal=document['goal'], goal_spec=document['goal_spec'], release_snapshot=document['release_snapshot'],
                        contract=contract['id'], boundary=contract['boundary'], scope=contract['scope'])
        if kind == 'contract_investigation':
            for key in ('conclusion', 'rationale', 'distribution_boundary', 'observations'):
                self.assertIn(key, evidence)
            presence, distribution = self.observation_shapes(resource)
            development = copy.deepcopy(presence)
            development.update(commit='c' * 40, path='cache/schema-v2.json', release_id=None, contract_present=True)
            inspected_distribution = copy.deepcopy(distribution)
            inspected_distribution.update(commit='c' * 40, path='distribution.json',
                                          finding='Only published packages distribute this synthetic contract.')
            observations = [development, inspected_distribution]
            for release in document['release_snapshot']['releases']:
                published = copy.deepcopy(presence)
                published.update(commit=release['commit'], path='cache/schema-v2.json',
                                 release_id=release['id'], contract_present=False)
                observations.append(published)
            evidence.update(conclusion='unreleased',
                            rationale='Inspected the development schema and each published tree: this synthetic contract exists only in development.',
                            distribution_boundary='Synthetic cache formats are distributed only in published packages; no separate deployment.',
                            observations=observations)
        else:
            self.assertIn('statement', evidence)
            evidence['statement'] = 'I maintain this synthetic cache and confirm it has never been distributed.'
        contract['evidence'] = [evidence]; document['contracts'] = [contract]
        return document

    def test_public_discovery_preparation_and_both_evidence_alternatives_resume(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_migration_acceptance.GenericMigrationDiscoveryTests.test_disclosed_preparation_keeps_unknown_facts_and_both_evidence_alternatives_resume')

    def test_preparation_resource_is_stable_and_refreshes_with_facts_and_spec(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_migration_acceptance.GenericMigrationDiscoveryTests.test_preparation_identity_stable_then_changes_with_provider_and_exact_spec')

    def test_discovered_route_blocks_foreign_stale_ambiguous_and_unavailable_evidence(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_migration_acceptance.GenericMigrationDiscoveryTests.test_foreign_stale_ambiguous_and_unknown_provider_block_after_valid_prepared_control')
