"""Public CLI inventory discovery is a generic new-task acquisition boundary."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import test_evidence_dag_journeys as journeys
from test_evidence_dag_journeys import DagFixture, TaskSession, z


class ModelInventoryPhaseBoundaryTests(DagFixture):
    add_goal = journeys.RelationshipPublicTests.add_goal
    put_envelope = journeys.RelationshipPublicTests.put_envelope
    def discover(self):
        self.session.runtime['available_pairs'].append({'model': 'new-model', 'effort': 'low'})

    def start_request(self, name='produce', number=100):
        step = next(step for step in self.session.checkpoint(number)
                    if step.get('node', {}).get('node') == name and 'start' in step)
        receipt = json.loads(Path(step['policy']['path']).read_text())['policy_receipt']
        return {**step['start'], 'policy_receipt': receipt, 'request_id': 'start-' + str(number) + name}

    def test_existing_phase_finishes_after_discovery_and_restart_but_next_task_waits(self):
        request = self.start_request()
        work = self.session.call(100, request)['next_steps'][0]
        self.discover()
        # A new CLI session must resume the exact acquisition, never reroute it.
        self.session = TaskSession(self.session.repo, self.session.project, self.session.runtime,
                                   self.provider, self.session.control)
        replay = self.session.call(100, request)['next_steps'][0]
        self.assertEqual(work['lease'], replay['lease'])
        receipt = json.loads(Path(work['policy']['path']).read_text())['policy_receipt']
        self.session.call(100, {**work['bind'], 'actor': 'worker-produce',
                               'selection': work['lease']['selection'], 'policy_receipt': receipt})
        work['bound_actor'] = 'worker-produce'
        read = self.session.call(100, {'operation': 'read', 'node': work['node']})
        self.assertEqual('read', read['next_steps'][0]['kind'])
        self.assertEqual('deferred_until_execution_phase_start', read['model_inventory_review']['status'])
        submit = self.session.submission(work, {'value': 'candidate'}, 'finish-after-discovery')
        response = self.session.call(100, submit)
        self.assertEqual(response, self.session.call(100, submit))
        self.assertFalse(self.payload()[1]['operational']['leases'])
        # Reviewer and root tasks use the same new lease boundary as producers.
        pending = [step for step in response['next_steps'] if step.get('kind') == 'policy_review']
        self.assertEqual({'review_a', 'review_b'}, {step['node']['node'] for step in pending})
        self.assertTrue(all(step['boundary'] == 'execution_phase_start' for step in pending))

    def test_frozen_start_and_parallel_goal_are_blocked_before_any_write(self):
        request = self.start_request()
        self.add_goal(101, self.graph)
        parallel = self.start_request(number=101)
        work = self.session.acquire('produce')
        self.discover()
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(101, parallel)
        self.assertEqual('policy_review', response['next_steps'][0]['kind'])
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertTrue(self.payload()[1]['operational']['leases'])
        response = self.session.call(100, {'operation': 'recover', 'node': work['node'],
            'lease': work['lease']['token'], 'actor': work['bound_actor'],
            'worker_status': 'stopped', 'evidence': 'Test worker has stopped.'})
        self.assertEqual('checkpoint', response['next_steps'][0]['kind'])
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.assertEqual('policy_review', self.session.call(100, request)['next_steps'][0]['kind'])
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_discovery_after_preflight_is_checked_again_under_lock(self):
        request = self.start_request()
        self.discover()
        # The frozen public start must be rejected even without another checkpoint.
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        result = self.session.call(100, request)
        self.assertEqual('policy_review', result['next_steps'][0]['kind'])
        self.assertEqual('required_before_execution_phase_start', result['model_inventory_review']['status'])
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertFalse(z._heartbeat.capacity_inventory(repo=self.fixture.repo)['slots'])

    def test_lost_selected_pair_rejects_submit_but_allows_custody_release(self):
        work = self.session.acquire('produce')
        self.discover()
        self.session.runtime['available_pairs'] = [pair for pair in self.session.runtime['available_pairs']
                                                   if pair != work['lease']['selection']]
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        rejected = self.session.call(100, self.session.submission(work, {'value': 'candidate'}, 'lost-pair'), expected=2)
        self.assertIn('Bound model/effort pair', str(rejected))
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        released = self.session.call(100, {'operation': 'release', 'node': work['node'],
            'lease': work['lease']['token'], 'actor': work['bound_actor']})
        self.assertEqual('released', released['next_steps'][0]['kind'])

    def test_live_owner_renewal_and_monitoring_continue_with_pending_review(self):
        worker = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.read()'],
                                  stdin=subprocess.PIPE)
        self.addCleanup(worker.wait)
        self.addCleanup(worker.stdin.close)
        actor = 'inventory-worker-' + str(worker.pid)
        work = self.session.acquire('produce', actor=actor)
        self.discover()
        identity = {'node': work['node'], 'lease': work['lease']['token'], 'actor': actor}
        monitored = self.session.call(100, {'operation': 'heartbeat', **identity})
        self.assertEqual('await_worker', monitored['next_steps'][0]['kind'])
        renewed = self.session.call(100, {'operation': 'renew', **identity})
        self.assertEqual('renewed', renewed['next_steps'][0]['kind'])
        self.assertEqual(work['lease']['token'], renewed['next_steps'][0]['lease'])
        self.assertIsNone(worker.poll())
        self.session.finish(work, {'value': 'completed with original selection'})

    def test_readonly_preview_and_capture_remain_available(self):
        self.discover()
        preview = self.session.call(100, intent='preview')
        self.assertIn('model_inventory_review', preview)
        capture = self.session.call(100, intent='capture')
        self.assertEqual('capture', capture['next_steps'][0]['kind'])

    def test_loss_of_selected_pair_prevents_binding_without_rerouting(self):
        request = self.start_request()
        work = self.session.call(100, request)['next_steps'][0]
        self.discover()
        self.session.runtime['available_pairs'] = [pair for pair in self.session.runtime['available_pairs']
                                                   if pair != work['lease']['selection']]
        receipt = json.loads(Path(work['policy']['path']).read_text())['policy_receipt']
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        rejected = self.session.call(100, {**work['bind'], 'actor': 'worker-produce',
            'selection': work['lease']['selection'], 'policy_receipt': receipt}, expected=2)
        self.assertIn('Bound model/effort pair', str(rejected))
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_existing_root_owner_finishes_but_new_root_task_requires_review(self):
        graph = copy.deepcopy(self.graph)
        graph['nodes'][0]['executor']['role'] = 'root'
        self.install(graph)
        work = self.session.acquire('produce')
        self.discover()
        self.session.finish(work, {'value': 'root result'})
        self.assertFalse(self.payload()[1]['operational']['leases'])
        # A root role is no exception to a fresh generic task's review boundary.
        self.add_goal(101, graph)
        steps = self.session.checkpoint(101)
        self.assertTrue(any(step.get('kind') == 'policy_review' for step in steps))
        self.assertFalse(any('start' in step for step in steps))
