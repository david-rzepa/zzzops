"""Public verification executes each exact request once across uncertainty."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

import test_evidence_dag_journeys as journeys

z = journeys.z


class AuthoritativeVerificationTests(journeys.DagFixture):
    workspace_graph = journeys.WorkspaceAuthorityPublicTests.workspace_graph
    setup_workspace = journeys.WorkspaceAuthorityPublicTests.setup_workspace
    acquire_workspace = journeys.WorkspaceAuthorityPublicTests.acquire_workspace
    review_candidate = journeys.WorkspaceAuthorityPublicTests.review_candidate

    def setUp(self):
        super().setUp()
        self.setup_workspace()
        self.install_plan()
        self.session.git('add','zzzops-test-plan.json','second_test.py')
        self.session.git('commit','-qm','test plan fixture')
        self.work = self.acquire_workspace('alpha')
        self.counter = Path(self.session.control) / 'verification-count'

    def command(self, code=0):
        return [sys.executable, '-c', "from pathlib import Path; import sys; p=Path(%r); p.write_text(p.read_text()+'run\\n' if p.exists() else 'run\\n'); print('check stdout'); print('check stderr', file=sys.stderr); raise SystemExit(%d)" % (str(self.counter), code)]

    def request(self, identity, code=0, expectation='passed'):
        request = self.session.submission(self.work, {'value': 'exact checked candidate'}, identity)
        request.update(workspace_checks=[self.command(code)], verification_expectation=expectation)
        return request

    def count(self):
        return len(self.counter.read_text().splitlines()) if self.counter.exists() else 0

    def install_plan(self):
        unit={'purpose':'public regression','behavior':'observable','runner':'r','selection':'behavior_test','goals':['557'],'specifications':[],'dependencies':['behavior_test.py'],'completeness':'complete','fallback':'full','order_group':None}
        second={**unit,'selection':'second_test','dependencies':['second_test.py']}
        plan={'schema_version':1,'graph_provider':{'name':'graft','version':'0.17.0','format':'graft-graph-v1','configuration':{}},'runners':{'r':{'adapter':'unittest','start':'.'}},'tests':{'behavior_test':unit,'second_test':second},'latest_success':{}}
        (self.fixture.repo/'zzzops-test-plan.json').write_text(json.dumps(plan))
        (self.fixture.repo/'second_test.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n')

    def test_public_changed_mode_widens_and_persists_partition_fact(self):
        (self.fixture.repo/'behavior_test.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n')
        request=self.session.submission(self.work,{'value':'planned candidate'},'plan-changed')
        request.update(verification_plan={'mode':'changed','changed':['unmapped.py'],'maximum_seconds':10,'durations':{'behavior_test':1}},verification_expectation='passed')
        response=self.session.call(100,request);self.assertIn('verification',response,response);proof=self.read_blob(response['verification']['proof'])
        self.assertTrue(proof['passed']);self.assertEqual(['behavior_test','second_test'],proof['test_plan']['preview']['selected']);self.assertIn('fallback_reason',proof['test_plan']['graph'])
        git_dir=Path(subprocess.check_output(['git','rev-parse','--absolute-git-dir'],cwd=self.fixture.repo,text=True).strip())
        self.assertTrue(list((git_dir/'zzzops/verification/100').glob('partition-facts-*.json')))

    def test_public_expected_red_mode_requires_signature_and_replays_response(self):
        (self.fixture.repo/'behavior_test.py').write_text("import unittest\nclass T(unittest.TestCase):\n def test_red(self): self.fail('missing-557-behavior')\n")
        request=self.session.submission(self.work,{'value':'observed red'},'plan-red')
        request.update(verification_plan={'mode':'expected-red','selected':['behavior_test'],'expected_red':'FAILED'},verification_expectation='observed')
        response=self.session.call(100,request);self.assertTrue(response['verification']['passed'],response);self.assertEqual(response,self.session.call(100,request))

    def test_partition_fact_survives_interruption_and_fresh_lease_reuses_only_success(self):
        (self.fixture.repo/'behavior_test.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n')
        request=self.session.submission(self.work,{'value':'partial planned candidate'},'plan-partial')
        request.update(verification_plan={'mode':'full','maximum_seconds':1,'durations':{'behavior_test':1,'second_test':1}},verification_expectation='passed')
        original=subprocess.run;calls={'behavior_test':0,'second_test':0}
        def interrupted(argv,*args,**kwargs):
            text=json.dumps(argv)
            is_test=argv and argv[0]==sys.executable and '-c' in argv
            for name in calls:
                if is_test and name in text:calls[name]+=1
            if is_test and 'second_test' in text:raise KeyboardInterrupt('after first durable partition fact')
            return original(argv,*args,**kwargs)
        with mock.patch.object(subprocess,'run',side_effect=interrupted),self.assertRaises(KeyboardInterrupt):self.session.call(100,request)
        self.assertEqual({'behavior_test':1,'second_test':1},calls)
        response=self.session.call(100,request);recovery=response['next_steps'][0]['recovery_contract']
        self.session.call(100,{**recovery,'worker_status':'stopped','evidence':'Observed interrupted verifier terminated'})
        self.work=self.acquire_workspace('alpha');fresh=self.session.submission(self.work,{'value':'fresh planned candidate'},'plan-partial-fresh')
        fresh.update(verification_plan=request['verification_plan'],verification_expectation='passed')
        before=dict(calls)
        def counted(argv,*args,**kwargs):
            text=json.dumps(argv)
            for name in calls:
                if argv and argv[0]==sys.executable and '-c' in argv and name in text:calls[name]+=1
            return original(argv,*args,**kwargs)
        with mock.patch.object(subprocess,'run',side_effect=counted):result=self.session.call(100,fresh)
        self.assertIn('verification',result,result)
        self.assertEqual(before['behavior_test'],calls['behavior_test']);self.assertEqual(before['second_test']+1,calls['second_test'])
        proof=self.read_blob(result['verification']['proof']);self.assertEqual(self.work['lease']['token'],proof['lease']);self.assertTrue(proof['passed'])

    def test_plan_facts_survive_response_loss_after_durable_append(self):
        (self.fixture.repo/'behavior_test.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n')
        request=self.session.submission(self.work,{'value':'response lost candidate'},'plan-response-loss')
        request.update(verification_plan={'mode':'full','maximum_seconds':1,'durations':{'behavior_test':1,'second_test':1}},verification_expectation='passed')
        with mock.patch.object(self.provider,'create_issue_comment',side_effect=RuntimeError('lost after durable facts')):self.session.call(100,request,expected=2)
        original=subprocess.run
        def no_repeat(argv,*args,**kwargs):
            if argv and argv[0]==sys.executable and '-c' in argv:self.assertNotIn('behavior_test',json.dumps(argv));self.assertNotIn('second_test',json.dumps(argv))
            return original(argv,*args,**kwargs)
        with mock.patch.object(subprocess,'run',side_effect=no_repeat):response=self.session.call(100,request)
        self.assertTrue(response['verification']['passed'])

    def test_stale_workspace_observed_stop_clears_only_exact_lease_without_accepting_bytes(self):
        (self.fixture.repo/'behavior_test.py').write_text('stale worker bytes\n')
        self.replace_spec('upstream prerequisite changed after worker stopped')
        actor=self.payload()[1]['operational']['leases'][0]['worker']
        request={'operation':'recover','node':self.work['node'],'lease':self.work['lease']['token'],'actor':actor,'request_id':'stale-workspace-recover','worker_status':'stopped','evidence':'Observed exact bound worker and verifier stopped'}
        before=copy.deepcopy((self.provider.issues,self.provider.comments));evidence_before=copy.deepcopy(self.payload()[1]['evidence'])
        self.session.call(100,{**request,'actor':'wrong'},expected=2);self.session.call(100,{**request,'lease':'wrong'},expected=2);self.session.call(100,{**request,'worker_status':'unknown'},expected=2)
        self.assertEqual(before,(self.provider.issues,self.provider.comments))
        response=self.session.call(100,request);checkpoint=response['next_steps'][0]
        self.assertEqual(self.work['lease']['token'],checkpoint['stopped_unaccepted']['lease']);self.assertIn('prerequisite',checkpoint['stopped_unaccepted']['reason'])
        self.assertFalse(self.payload()[1]['operational']['leases']);self.assertNotIn('workspace_draft',checkpoint);self.assertEqual(evidence_before,self.payload()[1]['evidence'])

    def test_native_red_to_green_checks_execute_once_per_phase_request(self):
        (self.fixture.repo / 'behavior_test.py').write_text('from source import value\nassert value() == 2\n')
        command = [sys.executable, '-B', '-c', "from pathlib import Path; import runpy; p=Path(%r); p.write_text(p.read_text()+'run\\n' if p.exists() else 'run\\n'); runpy.run_path('behavior_test.py')" % str(self.counter)]
        red = self.request('native-red', expectation='observed')
        red['workspace_checks'] = [command]
        started = time.monotonic()
        response = self.session.call(100, red)
        self.assertFalse(response['verification']['passed'])
        self.review_candidate('alpha', 1)
        self.work = self.acquire_workspace('beta')
        (self.fixture.repo / 'source.py').write_text('def value():\n    return 2\n')
        green = self.request('native-green')
        green['workspace_checks'] = [command]
        passed = self.session.call(100, green)
        self.assertTrue(passed['verification']['passed'])
        self.assertEqual(2, self.count())
        self.assertEqual(response, self.session.call(100, red))
        self.assertEqual(passed, self.session.call(100, green))
        self.assertEqual(2, self.count())
        elapsed = time.monotonic() - started
        observed = sum(self.read_blob(value['verification']['proof'])['commands'][0]['duration_seconds'] for value in (response, passed))
        self.assertGreaterEqual(elapsed, observed)

    def test_first_append_failure_reuses_command_proof_and_log(self):
        request = self.request('first-append')
        request.pop('verification_expectation')  # Existing submit wire also gets crash-safe execution.
        before = len(self.provider.updates)
        started = time.monotonic()
        with mock.patch.object(self.provider, 'create_issue_comment', side_effect=RuntimeError('unavailable before first append')):
            self.session.call(100, request, expected=2)
        self.assertEqual(1, self.count())
        response = self.session.call(100, request)
        self.assertEqual(1, self.count())
        self.assertEqual(before + 1, len(self.provider.updates))
        self.assertEqual(response, self.session.call(100, request))
        proof = self.read_blob(response['verification']['proof'])
        self.assertEqual(self.work['lease']['token'], proof['lease'])
        self.assertEqual(request['workspace_checks'], [row['command'] for row in proof['commands']])
        self.assertTrue(proof['passed'])
        self.assertIn('check stdout', Path(proof['commands'][0]['log']).read_text())
        self.assertIn('check stderr', Path(proof['commands'][0]['log']).read_text())
        self.assertGreaterEqual(time.monotonic() - started, sum(row['duration_seconds'] for row in proof['commands']))

    def test_failed_green_keeps_lease_and_corrected_request_executes_once(self):
        failed_request = self.request('green-failed', code=1)
        evidence = copy.deepcopy(self.payload()[1]['evidence'])
        failed = self.session.call(100, failed_request)
        self.assertEqual('verification_failed', failed['next_steps'][0]['kind'])
        self.assertEqual(evidence, self.payload()[1]['evidence'])
        self.assertEqual(self.work['lease']['token'], self.payload()[1]['operational']['leases'][0]['token'])
        self.assertEqual(failed, self.session.call(100, failed_request))
        self.assertEqual(1, self.count())
        (self.fixture.repo / 'behavior_test.py').write_text('assert True\n')
        corrected = self.session.call(100, self.request('green-corrected'))
        self.assertTrue(corrected['verification']['passed'])
        self.assertEqual(2, self.count())
        self.assertFalse(self.payload()[1]['operational']['leases'])

    def test_explicit_red_observation_records_failed_proof_without_rerun(self):
        request = self.request('red-baseline', code=1, expectation='observed')
        response = self.session.call(100, request)
        self.assertFalse(response['verification']['passed'])
        self.assertEqual(1, self.read_blob(response['verification']['proof'])['commands'][0]['exit_code'])
        self.assertEqual(self.result('alpha')[0], response['submitted']['result'])
        self.assertEqual(response, self.session.call(100, request))
        self.assertEqual(1, self.count())

    def test_every_required_command_runs_and_launch_failure_is_not_red_success(self):
        request = self.request('required-checks', expectation='observed')
        request['workspace_checks'].append([str(Path(self.session.control) / 'missing-verifier')])
        response = self.session.call(100, request)
        self.assertEqual('verification_failed', response['next_steps'][0]['kind'])
        proof = self.read_blob(response['next_steps'][0]['proof'])
        self.assertEqual(request['workspace_checks'], [record['command'] for record in proof['commands']])
        self.assertIn('execution_error', proof['commands'][1])
        self.assertFalse(proof['passed'])
        self.assertEqual(response, self.session.call(100, request))
        self.assertEqual(1, self.count())

    def test_timeout_is_not_repeated_and_next_request_can_retry_under_live_lease(self):
        request = self.request('timeout')
        original = subprocess.run
        def timeout(argv, *args, **kwargs):
            if argv == request['workspace_checks'][0]:
                original(argv, *args, **kwargs)
                raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
            return original(argv, *args, **kwargs)
        with mock.patch.object(subprocess, 'run', side_effect=timeout):
            response = self.session.call(100, request)
        self.assertEqual('verification_failed', response['next_steps'][0]['kind'])
        proof = self.read_blob(response['next_steps'][0]['proof'])
        self.assertTrue(proof['commands'][0]['timed_out'])
        self.assertFalse(proof['passed'])
        self.assertEqual(response, self.session.call(100, request))
        self.assertEqual(1, self.count())
        self.session.call(100, self.request('after-timeout'))
        self.assertEqual(2, self.count())

    def test_interrupted_running_request_requires_observed_recovery_then_new_owner_works(self):
        request = self.request('interrupted')
        original = subprocess.run
        def interrupted(argv, *args, **kwargs):
            if argv == request['workspace_checks'][0]:
                original(argv, *args, **kwargs)
                raise KeyboardInterrupt('host interrupted before result recorded')
            return original(argv, *args, **kwargs)
        with mock.patch.object(subprocess, 'run', side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            self.session.call(100, request)
        response = self.session.call(100, request)
        self.assertEqual('await_worker', response['next_steps'][0]['kind'])
        self.assertEqual('await_worker', self.session.call(100, self.request('attempted-bypass'))['next_steps'][0]['kind'])
        self.assertEqual(1, self.count())
        recovery = response['next_steps'][0]['recovery_contract']
        self.session.call(100, {**recovery, 'worker_status': 'stopped', 'evidence': 'Observed exact verifier and worker terminated'})
        self.work = self.acquire_workspace('alpha')
        response = self.session.call(100, self.request('new-owner'))
        self.assertTrue(response['verification']['passed'])
        self.assertEqual(2, self.count())

    def test_changed_request_workspace_or_logs_cannot_reuse_unpublished_proof(self):
        request = self.request('immutable-identity')
        with mock.patch.object(self.provider, 'create_issue_comment', side_effect=RuntimeError('unavailable')):
            self.session.call(100, request, expected=2)
        self.assertEqual(1, self.count())
        self.session.call(100, {**request, 'workspace_checks': [self.command(1)]}, expected=2)
        path = self.fixture.repo / 'behavior_test.py'
        original = path.read_bytes() if path.exists() else None
        path.write_text('assert True\n')
        self.session.call(100, request, expected=2)
        if original is None: path.unlink()
        else: path.write_bytes(original)
        logs = list((self.fixture.repo / '.zzzops/diagnostics').glob('node-*.log'))
        self.assertTrue(logs)
        logs[-1].write_text('tampered log')
        self.session.call(100, request, expected=2)
        self.assertEqual(1, self.count())


if __name__ == '__main__':
    unittest.main()
