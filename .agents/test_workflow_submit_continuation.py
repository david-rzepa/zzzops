"""Atomic submit continuations through the real public CLI and fake provider."""
import copy
import json
import threading
import time
import unittest
import sys
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import test_evidence_dag_journeys as journeys
from test_evidence_dag_journeys import DagFixture, z
import test_workflow_publication_contract as publication
from test_workflow_owned_outputs import content_hash


class SubmitContinuationTests(DagFixture):
    def test_test_plan_response_loss_and_partial_fact_continuation_contract(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_workflow_authoritative_verification.AuthoritativeVerificationTests.test_public_changed_mode_widens_and_persists_partition_fact',
            'test_workflow_authoritative_verification.AuthoritativeVerificationTests.test_first_append_failure_reuses_command_proof_and_log')
    def ready_names(self, response):
        return {step['node']['node'] for step in response['next_steps'] if step['kind'] == 'execute'}

    def acquire_returned(self, response, name, actor):
        step = next(step for step in response['next_steps'] if step.get('kind') == 'execute' and step['node']['node'] == name)
        receipt = json.loads(Path(step['policy']['path']).read_text())['policy_receipt']
        work = self.session.call(100, {**step['start'], 'policy_receipt': receipt})['next_steps'][0]
        self.session.call(100, {**work['bind'], 'actor': actor, 'selection': work['lease']['selection'], 'policy_receipt': receipt})
        work['bound_actor'] = actor
        return work

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
        reviewed = response
        for name in ('review_a', 'review_b'):
            with mock.patch.object(z._workflow.Workflow, 'node_checkpoint', side_effect=AssertionError('continuation needs no checkpoint')):
                review = self.acquire_returned(reviewed, name, 'independent-' + name)
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
        with mock.patch.object(self.provider, 'update_issue', side_effect=z.GoalTransitionProviderError('unavailable')):
            failed = self.session.call(100, request, expected=2)
        self.assertFalse(self.ready_names(failed))
        self.assertEqual(before, self.provider.issues)
        response = self.session.call(100, request)
        self.assertEqual({'review_a', 'review_b'}, self.ready_names(response))
        self.assertEqual(response, self.session.call(100, request))

    def test_exact_parent_grants_and_human_root_boundary_are_preserved(self):
        fixture = journeys.WorkspaceAuthorityPublicTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.setup_parent_workspace()
        submissions = [call['response'] for call in fixture.session.calls if call['operation'] == 'submit' and call['goal'] == 100]
        consent = next(value for value in reversed(submissions) if value['submitted']['node']['node'] == 'consent')
        review = next(value for value in reversed(submissions) if value['submitted']['node']['node'] == 'inspect_charter')
        self.assertIn('consent', self.ready_names(review))
        self.assertNotIn('alpha', self.ready_names(review))
        self.assertIn('alpha', self.ready_names(consent))
        step = next(step for step in consent['next_steps'] if step.get('node', {}).get('node') == 'alpha')
        pinned = {item['name'] for item in step['input_envelope']['inputs']}
        self.assertTrue({'parent_allocation', 'parent_authorization', 'parent_approval'} <= pinned)
        self.assertFalse(fixture.payload()[1]['operational']['leases'])

    def test_released_lease_frees_capacity_in_same_continuation(self):
        z._workflow_section(self.session.project, 'autonomy_approval_parallelism')['configuration']['max_workers'] = 1
        work = self.session.acquire('produce')
        response = self.session.finish(work, {'value': 'candidate'})
        self.assertEqual({'review_a', 'review_b'}, self.ready_names(response))
        self.assertFalse(any(step.get('max_workers') == 1 for step in response['next_steps']))

    def test_lost_successful_body_response_returns_confirmed_continuation(self):
        work = self.session.acquire('produce')
        request = self.session.submission(work, {'value': 'candidate'}, 'lost-body-continuation')
        original = self.provider.update_issue
        updates = len(self.provider.updates)
        def lost(*args, **kwargs):
            original(*args, **kwargs)
            raise z.GoalTransitionProviderError('committed response lost')
        with mock.patch.object(self.provider, 'update_issue', side_effect=lost):
            response = self.session.call(100, request)
        self.assertEqual({'review_a', 'review_b'}, self.ready_names(response))
        self.assertEqual(response, self.session.call(100, request))
        self.assertEqual(updates + 1, len(self.provider.updates))

    def test_changes_requested_review_returns_correction_without_approval(self):
        fixture = journeys.DefaultCorrectionPublicTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.default_decomposition()
        work = fixture.session.acquire('decomposition_review')
        response = fixture.session.finish(work, {
            'value': {'decision': 'changes_requested', 'report': 'Required correction',
                      'outcomes': ['blocked'], 'findings': ['Required correction']},
            'authorization': None,
        })
        ready = self.ready_names(response)
        self.assertIn('interpret_decomposition_rejection', ready)
        self.assertNotIn('test_design', ready)
        self.assertNotIn('approve_spec', ready)
        self.assertFalse(any(step['kind'] in {'integrate', 'complete'} for step in response['next_steps']))

    def test_expired_or_stale_submission_cannot_publish_continuation(self):
        graph = copy.deepcopy(self.graph)
        graph['nodes'][0]['inputs'] = {'request': journeys.spec_input()}
        self.install(graph)
        work = self.session.acquire('produce')
        request = self.session.submission(work, {'value': 'candidate'}, 'stale-continuation')
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        with mock.patch.object(z._workflow.time, 'time', return_value=work['lease']['expires_at'] + 1):
            self.session.call(100, request, expected=2)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.replace_spec('substantively changed input')
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, request, expected=2)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_workspace_proof_logs_and_continuation_survive_retry(self):
        fixture = journeys.WorkspaceAuthorityPublicTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.setup_workspace()
        work = fixture.acquire_workspace('alpha')
        (fixture.fixture.repo / 'behavior_test.py').write_text("assert False, 'required missing behavior'\n")
        request = fixture.session.submission(work, {'value': 'verified failing baseline'}, 'proof-continuation')
        command = [sys.executable, '-c', "print('single proof'); raise SystemExit(1)"]
        request['workspace_checks'] = [command]
        with mock.patch.object(fixture.provider, 'update_issue', side_effect=z.GoalTransitionProviderError('unavailable')):
            fixture.session.call(100, request, expected=2)
        comments = copy.deepcopy(fixture.provider.comments)
        logs = {path: path.read_bytes() for path in (fixture.fixture.repo / '.zzzops/diagnostics').glob('node-*.log')}
        self.assertTrue(logs)
        import subprocess
        original = subprocess.run
        def no_repeat(argv, *args, **kwargs):
            self.assertNotEqual(command, argv, 'Retry must reuse the original proof and log')
            return original(argv, *args, **kwargs)
        with mock.patch.object(subprocess, 'run', side_effect=no_repeat):
            response = fixture.session.call(100, request)
        self.assertEqual({'observe_alpha'}, self.ready_names(response))
        self.assertNotIn('beta', self.ready_names(response))
        self.assertEqual(comments, fixture.provider.comments)
        self.assertEqual(logs, {path: path.read_bytes() for path in logs})
        ref = fixture.read_blob(fixture.produced('alpha'))['provenance']['source']
        self.assertFalse(fixture.read_blob(ref)['passed'])
        self.assertEqual(response, fixture.session.call(100, request))

    def test_legacy_literal_response_receipts_replay_unchanged(self):
        request = {'operation': 'submit', 'request_id': 'legacy-literal'}
        literal = {'next_steps': [{'kind': 'checkpoint', 'goal': 100}]}
        envelope, payload = self.payload()
        payload['operational']['receipts'].append({'request': request['request_id'],
            'payload': content_hash(request), 'result': self.blob(literal)})
        envelope['payload'] = self.blob(payload)
        self.provider.issues[100]['body'] = '<!-- zzzops-goal\n' + json.dumps(envelope) + '\nzzzops-goal -->'
        self.assertEqual(literal, self.session.call(100, request))


class SchedulingInventoryContinuationTests(DagFixture):
    ready_names = SubmitContinuationTests.ready_names
    add_goal = journeys.RelationshipPublicTests.add_goal
    put_envelope = journeys.RelationshipPublicTests.put_envelope

    def setUp(self):
        super().setUp()
        z._workflow_section(self.session.project, 'autonomy_approval_parallelism')['configuration']['max_workers'] = 1
        graph = json.loads(json.dumps(self.graph).replace('"goal": 100', '"goal": "#this"'))
        self.install(graph)
        raw = self.session.portfolio_snapshot
        def unhydrated(*args, **kwargs):
            value = raw(*args, **kwargs)
            for goal in value['goals']:
                goal.pop('operational_leases', None)
            return value
        self.session.portfolio_snapshot = unhydrated

    def add_unrelated_owner(self, work):
        self.add_goal(101, self.graph)
        envelope = z.parse_managed_goal(self.provider.issues[101]['body'], 101)
        payload = self.session.read(101, envelope['payload'])
        lease = copy.deepcopy(work['lease'])
        lease['node']['goal'] = 101
        lease['token'] = 'unrelated-owner'
        payload['operational']['leases'] = [lease]
        offset = len(self.provider.comments[100])
        envelope['payload'] = self.blob(payload)
        for row in self.provider.comments[100][offset:]:
            self.provider.create_issue_comment(101, row['body'])
        self.put_envelope(101, envelope)

    def test_targeted_checkpoint_counts_local_machine_slot_before_offering_start(self):
        self.session.acquire('produce')
        self.add_goal(101, self.graph)
        with mock.patch.object(self.provider, 'get_issue_comments', wraps=self.provider.get_issue_comments) as reads:
            response = self.session.call(101)
        self.assertEqual(set(), self.ready_names(response))
        self.assertEqual(1, next(step['active_leases'] for step in response['next_steps'] if 'active_leases' in step))
        self.assertLessEqual({call.args[0] for call in reads.call_args_list}, {100, 101})

    def test_continuation_ignores_other_machine_owner_after_releasing_local_slot(self):
        work = self.session.acquire('produce')
        self.add_unrelated_owner(work)
        response = self.session.finish(work, {'value': 'candidate'})
        self.assertEqual({'review_a', 'review_b'}, self.ready_names(response))
        self.assertFalse(self.payload()[1]['operational']['leases'])

    def test_unavailable_unrelated_history_does_not_define_local_capacity(self):
        work = self.session.acquire('produce')
        self.add_goal(101, self.graph)
        self.add_goal(102, self.graph)
        self.provider.comments[101] = []
        blocked = self.session.call(102)
        self.assertFalse(self.ready_names(blocked))
        request = self.session.submission(work, {'value': 'candidate'}, 'unavailable-inventory')
        response = self.session.call(100, request)
        self.assertEqual({'review_a', 'review_b'}, self.ready_names(response))

    def test_broad_checkpoint_hydrates_only_selected_frontier_not_all_owners(self):
        z._workflow_section(self.session.project, 'autonomy_approval_parallelism')['configuration']['max_workers'] = 10
        for number in range(101, 121):
            self.add_goal(number, self.graph)
        z._heartbeat.initialize_capacity(repo=self.fixture.repo, slots=[])
        issue_reads = []
        comment_reads = []
        issue_snapshot = lambda _repo, _repository, number: (
            issue_reads.append(number) or copy.deepcopy(self.provider.issues[number]))
        comments = self.provider.get_issue_comments
        def observed_comments(number):
            comment_reads.append(number)
            return comments(number)
        with mock.patch.object(self.provider, 'get_issue_comments', side_effect=observed_comments), \
                mock.patch.object(z, 'GitHubGoalTransitionAdapter', return_value=self.provider), \
                mock.patch.object(z, 'portfolio_snapshot', side_effect=self.session.portfolio_snapshot), \
                mock.patch.object(z, 'provider_issue_snapshot', side_effect=issue_snapshot):
            engine = z._workflow.Workflow(z, self.fixture.repo, self.session.project, self.fixture.runtime)
            engine.read_only()
            original_step = engine.step
            lock = threading.Lock(); active = 0; peak = 0
            def observed_step(number):
                nonlocal active, peak
                with lock: active += 1; peak = max(peak, active)
                try:
                    time.sleep(.02)
                    return original_step(number)
                finally:
                    with lock: active -= 1
            with mock.patch.object(engine, 'artifact_index', wraps=engine.artifact_index) as indexes, \
                    mock.patch.object(engine, 'step', side_effect=observed_step):
                response = z._workflow.checkpoint(
                    z, self.fixture.repo, self.session.project, self.fixture.runtime, engine=engine)
        self.assertTrue(self.ready_names(response))
        hydrated = {call.args[0] for call in indexes.call_args_list}
        self.assertLessEqual(len(hydrated), 10)
        self.assertLess(len(hydrated), 21)
        self.assertGreater(peak, 1)
        self.assertEqual(list(range(100, 110)), sorted(issue_reads))
        self.assertEqual(list(range(100, 110)), sorted(comment_reads))

    def test_concurrent_repository_identity_probe_is_single_flight(self):
        adapter_type = self.fixture.patches[0].temp_original
        adapter = adapter_type(self.fixture.repo, 'owner/repo')
        barrier = threading.Barrier(10)
        reads = 0
        lock = threading.Lock()
        def provider(arguments, **_kwargs):
            nonlocal reads
            self.assertEqual(['repo', 'view', 'owner/repo', '--json',
                              'nameWithOwner,hasIssuesEnabled,viewerPermission'], arguments)
            with lock:
                reads += 1
            time.sleep(.05)
            return subprocess.CompletedProcess(arguments, 0, json.dumps({
                'nameWithOwner': 'owner/repo', 'hasIssuesEnabled': True,
                'viewerPermission': 'ADMIN'}), '')
        def probe(_number):
            barrier.wait()
            adapter.ensure_identity()
            return adapter._identity_checked
        with mock.patch.object(adapter, '_run', side_effect=provider):
            with ThreadPoolExecutor(max_workers=10) as pool:
                observed = list(pool.map(probe, range(10)))
        self.assertEqual([True] * 10, observed)
        self.assertEqual(1, reads)

    def test_concurrent_identical_issue_snapshots_are_single_flight(self):
        engine = z._workflow.Workflow(z, self.fixture.repo, self.session.project, self.fixture.runtime)
        engine.read_only()
        barrier = threading.Barrier(10)
        reads = 0
        lock = threading.Lock()
        def issue_snapshot(_repo, _repository, number):
            nonlocal reads
            with lock:
                reads += 1
            time.sleep(.05)
            return copy.deepcopy(self.provider.issues[number])
        def read_issue(_number):
            barrier.wait()
            return engine.adapter.get_issue(100)
        with mock.patch.object(z, 'provider_issue_snapshot', side_effect=issue_snapshot):
            with ThreadPoolExecutor(max_workers=10) as pool:
                observed = list(pool.map(read_issue, range(10)))
        self.assertTrue(all(issue == observed[0] for issue in observed))
        self.assertEqual(1, reads)

    def test_concurrent_identical_freshness_reads_are_single_flight(self):
        engine = z._workflow.Workflow(z, self.fixture.repo, self.session.project, self.fixture.runtime)
        barrier = threading.Barrier(10)
        reads = 0
        full_reads = 0
        lock = threading.Lock()
        comments = self.provider.get_issue_comments(100)
        def tail(number):
            nonlocal reads
            with lock:
                reads += 1
            time.sleep(.05)
            return copy.deepcopy(comments)
        def full(number):
            nonlocal full_reads
            with lock:
                full_reads += 1
            return copy.deepcopy(comments)
        self.provider.get_issue_comment_tail = tail
        with mock.patch.object(self.provider, 'get_issue_comments', side_effect=full):
            engine.read_only()
            engine._issue_observations = {100: copy.deepcopy(self.provider.issues[100])}
            def read_freshness(_number):
                barrier.wait()
                return engine.artifact_index(100)
            with mock.patch.object(z._workflow.state_cache, 'load', return_value=None), \
                mock.patch.object(z._workflow.state_cache, 'requires_full_read', return_value=False), \
                mock.patch.object(z._workflow.state_cache, 'store'):
                with ThreadPoolExecutor(max_workers=10) as pool:
                    observed = list(pool.map(read_freshness, range(10)))
        self.assertTrue(all(index.comments == observed[0].comments for index in observed))
        self.assertEqual(1, reads)
        self.assertEqual(1, full_reads)

    def test_broad_provider_call_matrix_keeps_history_reads_frontier_bounded(self):
        z._workflow_section(self.session.project, 'autonomy_approval_parallelism')['configuration']['max_workers'] = 10
        for number in range(101, 121):
            self.add_goal(number, self.graph)
        legacy = self.fixture.issue(120, parent=None, title='Legacy goal outside selected frontier')
        self.provider.issues[120]['body'] = legacy['body']
        z._heartbeat.initialize_capacity(repo=self.fixture.repo, slots=[])
        raw_comments = self.provider.get_issue_comments
        full_reads = {}
        tail_reads = {}
        issue_reads = {}
        def comments(number):
            full_reads[scenario].append(number)
            return raw_comments(number)
        def tail(number):
            tail_reads[scenario].append(number)
            observed = raw_comments(number)
            if scenario == 'partially_changed' and number == 105:
                observed[0]['body'] += '\nexternally edited'
            return observed
        def issue_snapshot(_repo, _repository, number):
            issue_reads[scenario].append(number)
            return copy.deepcopy(self.provider.issues[number])
        self.provider.get_issue_comment_tail = tail
        cached = {}
        def load(_repository, number, _issue_hash, contract):
            if scenario == 'cold':
                return None
            return copy.deepcopy(cached[number])
        with mock.patch.object(self.provider, 'get_issue_comments', side_effect=comments), \
                mock.patch.object(z, 'GitHubGoalTransitionAdapter', return_value=self.provider), \
                mock.patch.object(z, 'portfolio_snapshot', side_effect=self.session.portfolio_snapshot), \
                mock.patch.object(z, 'provider_issue_snapshot', side_effect=issue_snapshot), \
                mock.patch.object(z._workflow.state_cache, 'load', side_effect=load), \
                mock.patch.object(z._workflow.state_cache, 'requires_full_read', return_value=False), \
                mock.patch.object(z._workflow.state_cache, 'store'):
            for scenario in ('cold', 'warm', 'partially_changed', 'retry'):
                full_reads[scenario] = []
                tail_reads[scenario] = []
                issue_reads[scenario] = []
                engine = z._workflow.Workflow(z, self.fixture.repo, self.session.project, self.fixture.runtime)
                engine.read_only()
                response = z._workflow.checkpoint(
                    z, self.fixture.repo, self.session.project, self.fixture.runtime, engine=engine)
                self.assertTrue(self.ready_names(response))
                if scenario == 'cold':
                    now = time.time()
                    cached = {number: {
                        'provider_head': z._workflow.state_cache.head(raw_comments(number)),
                        'materialized_comments': raw_comments(number),
                        'last_complete_audit': now,
                    } for number in range(100, 110)}
        selected = list(range(100, 110))
        self.assertEqual({'cold': selected, 'warm': [], 'partially_changed': [105], 'retry': []},
                         {name: sorted(reads) for name, reads in full_reads.items()})
        self.assertEqual({name: selected for name in ('cold', 'warm', 'partially_changed', 'retry')},
                         {name: sorted(reads) for name, reads in tail_reads.items()})
        self.assertEqual({name: selected for name in ('cold', 'warm', 'partially_changed', 'retry')},
                         {name: sorted(reads) for name, reads in issue_reads.items()})
        for reads in tail_reads.values():
            self.assertNotIn(120, reads, 'mixed v1/v2 inventory must not hydrate an unselected legacy goal')

    def test_first_capacity_read_bootstraps_preupgrade_durable_owner(self):
        work = self.session.acquire('produce')
        z._heartbeat._capacity_paths(self.fixture.repo)['config'].unlink(missing_ok=True)
        self.add_goal(101, self.graph)
        raw_comments = self.provider.get_issue_comments
        reads = []
        def comments(number):
            reads.append(number)
            return raw_comments(number)
        with mock.patch.object(self.provider, 'get_issue_comments', side_effect=comments):
            response = self.session.call(101)
        self.assertFalse(self.ready_names(response))
        self.assertEqual([100, 101], sorted(set(reads)))
        self.assertEqual(len(set(reads)), len(reads), reads)
        self.assertEqual(1, next(step['active_leases'] for step in response['next_steps']
                                 if 'active_leases' in step))
        inventory = z._heartbeat.capacity_inventory(repo=self.fixture.repo)
        self.assertTrue(inventory['initialized'])
        self.assertEqual([work['lease']['token']], [slot['token'] for slot in inventory['slots']])
        self.session.finish(work, {'value': 'cleanup'})

    def test_stale_local_slot_is_removed_after_exact_durable_reconciliation(self):
        z._heartbeat.initialize_capacity(repo=self.fixture.repo, slots=[])
        node = {'goal': 100, 'node': 'produce', 'item': None, 'generation': 1}
        z._heartbeat.track_capacity(repo=self.fixture.repo, root_id=self.fixture.runtime['root_id'],
                                    goal=100, phase=json.dumps(node, sort_keys=True), token='stale-local')
        response = self.session.call(100)
        self.assertIn('produce', self.ready_names(response))
        self.assertEqual([], z._heartbeat.capacity_inventory(repo=self.fixture.repo)['slots'])

    def test_malformed_slot_goal_retains_capacity_and_fails_closed(self):
        z._heartbeat.initialize_capacity(repo=self.fixture.repo, slots=[])
        node = {'goal': 100, 'node': 'produce', 'item': None, 'generation': 1}
        z._heartbeat.track_capacity(repo=self.fixture.repo, root_id=self.fixture.runtime['root_id'],
                                    goal=100, phase=json.dumps(node, sort_keys=True), token='uncertain-local')
        self.add_goal(101, self.graph)
        raw = self.session.portfolio_snapshot
        def malformed(*args, **kwargs):
            value = raw(*args, **kwargs)
            value['goals'] = [goal for goal in value['goals'] if goal['key'] != 100]
            value['findings'] = value.get('findings', []) + [
                {'code': 'malformed_record', 'goal': 100, 'detail': 'synthetic corruption'}]
            value['complete'] = True
            return value
        self.session.portfolio_snapshot = malformed
        raw_comments = self.provider.get_issue_comments
        reads = []
        def comments(number):
            reads.append(number)
            return raw_comments(number)
        with mock.patch.object(self.provider, 'get_issue_comments', side_effect=comments):
            failed = self.session.call(101, expected=2)
        self.assertRegex(json.dumps(failed), r'(?i)local worker slot.*malformed|unavailable')
        self.assertEqual([101], reads)
        self.assertEqual(['uncertain-local'], [slot['token'] for slot in
                         z._heartbeat.capacity_inventory(repo=self.fixture.repo)['slots']])
        z._heartbeat.untrack_capacity(repo=self.fixture.repo, root_id=self.fixture.runtime['root_id'],
                                      goal=100, phase=json.dumps(node, sort_keys=True), token='uncertain-local')

    def test_nonscheduling_continuation_and_owned_checkpoint_skip_unrelated_inventory(self):
        graph = copy.deepcopy(self.graph)
        graph['nodes'] = graph['nodes'][:1]
        graph['terminals'] = [{'kind': 'node', 'goal': '#this', 'node': 'produce'}]
        self.install(graph)
        work = self.session.acquire('produce')
        self.add_goal(101, graph)
        self.provider.comments[101] = []
        with mock.patch.object(self.provider, 'get_issue_comments', wraps=self.provider.get_issue_comments) as reads:
            owned = self.session.call(100)
            response = self.session.finish(work, {'value': 'done'})
        self.assertFalse(self.ready_names(owned))
        self.assertEqual(['complete'], [step['kind'] for step in response['next_steps']])
        self.assertNotIn(101, [call.args[0] for call in reads.call_args_list])


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

    def test_pending_publication_reuses_operational_request_id(self):
        request = self.approval_request()
        with mock.patch.object(self.provider, 'update_issue', side_effect=z.GoalTransitionProviderError('unavailable')):
            self.session.call(100, request, expected=2)
        comments = copy.deepcopy(self.provider.comments)
        response = self.session.call(100, request)
        self.assertTrue(any(step['kind'] == 'integrate' for step in response['next_steps']))
        self.assertEqual(comments, self.provider.comments)
        self.assertEqual(response, self.session.call(100, request))
        self.assertEqual([], self.merge_calls)

    def test_deferred_binding_rejects_forged_transaction_target(self):
        request = self.approval_request()
        self.mark_merged()
        response = self.session.call(100, request)
        changed = 0
        for row in self.provider.comments[100]:
            envelope = z._comment_store.decode_envelope(row['body'])
            if envelope and envelope.get('context', {}).get('request_id') == request['request_id']:
                envelope['context']['target_envelope']['revision'] += 10
                row['body'] = z._comment_store.encode_envelope(envelope)
                changed += 1
        self.assertGreater(changed, 0)
        failed = self.session.call(100, request, expected=2)
        self.assertNotEqual(response, failed)
        self.assertFalse(any(step['kind'] == 'reconcile' for step in failed['next_steps']))

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
