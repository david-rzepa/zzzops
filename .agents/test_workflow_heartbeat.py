import importlib.util
import builtins
import json
import os
import sys
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).parent.parent / "plugins" / "zzzops" / "zzzops" / "heartbeat.py"
SPEC = importlib.util.spec_from_file_location("workflow_heartbeat", MODULE_PATH)
heartbeat = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(heartbeat)


class HeartbeatProcessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.repo = self.directory / "repo"
        self.repo.mkdir()
        self.state = self.directory / "state"
        self.runtime = self.directory / "runtime.json"
        self.runtime.write_text(json.dumps({"root_id": "root-a"}), encoding="utf-8")
        self.cli_records = self.directory / "cli-records.jsonl"
        self.probe_records = self.directory / "probe-records.jsonl"
        self.cli = self._script("fake-cli.py", """
import json, sys
from pathlib import Path
args = sys.argv[1:]
payload = json.loads(Path(args[args.index('--input') + 1]).read_text())
with Path(%r).open('a') as handle:
    handle.write(json.dumps(payload, sort_keys=True) + '\\n')
print(json.dumps({'next_steps': [{'kind': 'renewed', 'goal': int(args[args.index('--goal') + 1]), 'phase': payload['phase'], 'actor': payload['actor'], 'lease': payload['lease'], 'expires_at': __import__('time').time() + 900}]}))
raise SystemExit(0)
""" % str(self.cli_records))
        self.probe = self._script("fake-probe.py", """
import json, sys
import time
from pathlib import Path
mode, name = sys.argv[1:3]
with Path(%r).open('a') as handle:
    handle.write(json.dumps({'name': name, 'mode': mode}) + '\\n')
if mode == 'timeout':
    time.sleep(1)
raise SystemExit({'active': 0, 'stopped': 1}.get(mode, 2))
""" % str(self.probe_records))
        self.pids = set()

    def tearDown(self):
        for pid in self.pids:
            process = heartbeat._PROCESSES.get(pid)
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=3)
        self.temporary.cleanup()

    def _script(self, name, body):
        path = self.directory / name
        path.write_text(body, encoding="utf-8")
        return path

    def _start(self, goal, phase, token, mode, actor="worker-a"):
        result = heartbeat.start_heartbeat(
            repo=self.repo, root_id="root-a", runtime_path=self.runtime, cli_path=self.cli,
            goal=goal, phase=phase, token=token, actor=actor,
            probe_argv=[sys.executable, str(self.probe), mode, phase, actor], interval_seconds=.03,
            probe_timeout_seconds=.2, retry_limit=3, state_dir=self.state,
        )
        self.pids.add(result["pid"])
        return result

    def _wait(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.02)
        self.fail("timed out waiting for heartbeat process")

    def test_local_capacity_inventory_is_exact_and_independent_of_renewal(self):
        self.assertEqual(0, heartbeat.active_lease_count(
            repo=self.repo, root_id="root-a", state_dir=self.state))
        heartbeat.track_capacity(repo=self.repo, root_id="root-a", goal=40,
                                 phase="implement", token="capacity-token", state_dir=self.state)
        heartbeat.track_capacity(repo=self.repo, root_id="root-a", goal=40,
                                 phase="implement", token="capacity-token", state_dir=self.state)
        self.assertEqual(1, heartbeat.active_lease_count(
            repo=self.repo, root_id="root-a", state_dir=self.state))
        heartbeat.untrack_capacity(repo=self.repo, root_id="root-a", goal=40,
                                   phase="implement", token="capacity-token", state_dir=self.state)
        self.assertEqual(0, heartbeat.active_lease_count(
            repo=self.repo, root_id="root-a", state_dir=self.state))

    def test_malformed_local_capacity_inventory_fails_closed(self):
        paths = heartbeat._capacity_paths(self.repo, self.state)
        heartbeat._atomic_write(paths["config"], {"schema_version": 1, "repositories": [], "slots": "unknown"})
        with self.assertRaisesRegex(ValueError, "capacity inventory is invalid"):
            heartbeat.active_lease_count(repo=self.repo, root_id="root-a", state_dir=self.state)

    def test_repository_machine_inventory_is_shared_across_roots_but_not_repositories(self):
        other = self.directory / "other-repo"; other.mkdir()
        heartbeat.track_capacity(repo=self.repo, root_id="root-a", goal=41,
                                 phase="implement", token="machine-slot", state_dir=self.state)
        self.assertEqual(1, heartbeat.active_lease_count(
            repo=self.repo, root_id="root-b", state_dir=self.state))
        other_state = self.directory / "other-state"
        self.assertEqual(0, heartbeat.active_lease_count(
            repo=other, root_id="root-b", state_dir=other_state))

    def _lines(self, path):
        try:
            return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        except FileNotFoundError:
            return []

    def test_one_coordinator_renews_multiple_leases_and_stops_tracking_workers(self):
        first = self._start(41, "implement", "token-a", "active")
        second = self._start(42, "review", "token-b", "stopped", actor="worker-b")
        self.assertFalse(second["started"])
        self.assertEqual(first["pid"], second["pid"])

        self._wait(lambda: any(item.get("lease") == "token-a" for item in self._lines(self.cli_records)))
        self._wait(lambda: any(item.get("event") == "worker_stopped" for item in self._lines(Path(first["log"]))))
        renew = next(item for item in self._lines(self.cli_records) if item.get("lease") == "token-a")
        self.assertEqual(
            {"operation": "renew", "phase": "implement", "lease": "token-a", "actor": "worker-a", "worker_status": "active"},
            {key: renew[key] for key in ("operation", "phase", "lease", "actor", "worker_status")},
        )
        self.assertNotIn("probe_argv", renew)

        self._wait(lambda: [lease['token'] for lease in json.loads(Path(first['config']).read_text(encoding='utf-8'))['leases']] == ['token-a'])
        config = json.loads(Path(first["config"]).read_text(encoding="utf-8"))
        if os.name != "nt":
            self.assertEqual(0o700, Path(first["config"]).parent.stat().st_mode & 0o777)
            self.assertEqual(0o600, Path(first["config"]).stat().st_mode & 0o777)
        self.assertEqual(["token-a"], [lease["token"] for lease in config["leases"]])
        self.assertEqual([sys.executable, str(self.probe), "active", "implement", "worker-a"], config["leases"][0]["probe_argv"])
        heartbeat.stop_heartbeat(
            repo=self.repo, root_id="root-a", goal=41, phase="implement", token="token-a",
            state_dir=self.state,
        )
        self._wait(lambda: not heartbeat._pid_alive(first["pid"]))

    def test_module_imports_without_platform_lock_and_reports_actionable_blocker(self):
        original_import = builtins.__import__

        def without_locking(name, *args, **kwargs):
            if name in {"fcntl", "msvcrt"}:
                raise ImportError(name)
            return original_import(name, *args, **kwargs)

        fallback_spec = importlib.util.spec_from_file_location("heartbeat_without_locking", MODULE_PATH)
        fallback = importlib.util.module_from_spec(fallback_spec)
        with mock.patch("builtins.__import__", side_effect=without_locking):
            fallback_spec.loader.exec_module(fallback)
        with self.assertRaisesRegex(ValueError, "locking is unavailable.*explicit recovery"):
            with fallback._locked(self.directory / "unsupported.lock"):
                pass

    def test_probe_must_bind_the_worker_and_cannot_probe_its_own_shell(self):
        arguments = {
            "repo": self.repo, "root_id": "root-a", "runtime_path": self.runtime, "cli_path": self.cli,
            "goal": 90, "phase": "implement", "token": "probe-token", "actor": "worker-a",
            "state_dir": self.state,
        }
        with self.assertRaisesRegex(ValueError, "bound worker identity"):
            heartbeat.start_heartbeat(**arguments, probe_argv=[sys.executable, str(self.probe), "active"])
        with self.assertRaisesRegex(ValueError, "self-referential"):
            heartbeat.start_heartbeat(**arguments, probe_argv=["/bin/sh", "-c", "kill -0 $$", "worker-a"])

    def test_windows_pid_check_uses_read_only_process_api(self):
        class Kernel32:
            def __init__(self, exit_code):
                self.exit_code = exit_code
                self.closed = []

            def OpenProcess(self, access, inherit, pid):
                self.opened = (access, inherit, pid)
                return 123

            def GetExitCodeProcess(self, handle, destination):
                destination._obj.value = self.exit_code
                return True

            def CloseHandle(self, handle):
                self.closed.append(handle)
                return True

        active = Kernel32(259)
        stopped = Kernel32(0)
        self.assertTrue(heartbeat._windows_pid_alive(81, active))
        self.assertFalse(heartbeat._windows_pid_alive(82, stopped))
        self.assertEqual((0x1000, False, 81), active.opened)
        self.assertEqual([123], active.closed)
        with mock.patch.object(heartbeat.os, "name", "nt"), \
                mock.patch.object(heartbeat, "_windows_pid_alive", return_value=True) as windows, \
                mock.patch.object(heartbeat.os, "kill", side_effect=AssertionError("must not signal")):
            self.assertTrue(heartbeat._pid_alive(999999))
        windows.assert_called_once_with(999999)

    def test_unknown_liveness_retries_three_times_then_requires_recovery(self):
        result = self._start(51, "verify", "token-unknown", "unknown")
        log = Path(result["log"])
        self._wait(lambda: any(item.get("event") == "recovery_required" for item in self._lines(log)))
        events = self._lines(log)
        attempts = [item["attempt"] for item in events if item["event"] == "liveness_unknown"]
        self.assertEqual([1, 2, 3], attempts)
        self.assertFalse(any(item.get("lease") == "token-unknown" for item in self._lines(self.cli_records)))
        # The diagnostic precedes the atomic config update; wait for process
        # completion before asserting its durable cleanup.
        self._wait(lambda: not heartbeat._pid_alive(result["pid"]))
        config = json.loads(Path(result["config"]).read_text(encoding="utf-8"))
        self.assertEqual([], config["leases"])

    def test_probe_timeout_is_unknown_and_never_renews(self):
        result = self._start(52, "test_design", "token-timeout", "timeout")
        log = Path(result["log"])
        self._wait(lambda: any(item.get("event") == "recovery_required" for item in self._lines(log)))
        unknown = [item for item in self._lines(log) if item["event"] == "liveness_unknown"]
        self.assertEqual(3, len(unknown))
        self.assertTrue(all(item["detail"] == "TimeoutExpired" for item in unknown))
        self.assertFalse(any(item.get("lease") == "token-timeout" for item in self._lines(self.cli_records)))

    def test_health_classifies_progress_without_releasing_a_quiet_worker(self):
        result = self._start(53, "implement", "health-token", "active")
        self._wait(lambda: any(item.get("event") == "renewal_succeeded" for item in self._lines(Path(result["log"]))))
        active = heartbeat.heartbeat_health(
            repo=self.repo, root_id="root-a", goal=53, phase="implement", token="health-token", state_dir=self.state,
        )
        self.assertEqual("active", active["classification"])
        heartbeat.record_health(
            repo=self.repo, root_id="root-a", goal=53, phase="implement", token="health-token",
            health={"operation_at": 1.0}, state_dir=self.state,
        )
        suspect = heartbeat.heartbeat_health(
            repo=self.repo, root_id="root-a", goal=53, phase="implement", token="health-token", state_dir=self.state, now=time.time() + 1000,
        )
        self.assertEqual("suspect", suspect["classification"])
        self.assertTrue(any(lease["token"] == "health-token" for lease in heartbeat._read(Path(result["config"]))["leases"]))
        heartbeat.record_health(
            repo=self.repo, root_id="root-a", goal=53, phase="implement", token="health-token",
            health={"harness_status": "provider_call"}, state_dir=self.state,
        )
        idle = heartbeat.heartbeat_health(
            repo=self.repo, root_id="root-a", goal=53, phase="implement", token="health-token", state_dir=self.state, now=time.time() + 1000,
        )
        self.assertEqual("idle-but-expected", idle["classification"])
        heartbeat.stop_heartbeat(repo=self.repo, root_id="root-a", goal=53, phase="implement", token="health-token", state_dir=self.state)
        self._wait(lambda: not heartbeat._pid_alive(result["pid"]))

    def test_health_stopped_requires_a_terminal_probe_record(self):
        result = self._start(54, "implement", "stopped-health", "stopped")
        self._wait(lambda: any(item.get("event") == "worker_stopped" for item in self._lines(Path(result["log"]))))
        health = heartbeat.heartbeat_health(
            repo=self.repo, root_id="root-a", goal=54, phase="implement", token="stopped-health", state_dir=self.state,
        )
        self.assertEqual("stopped", health["classification"])

    def test_health_rejects_malformed_signals_without_changing_lease(self):
        result = self._start(55, "implement", "malformed-health", "active")
        with self.assertRaisesRegex(ValueError, "health"):
            heartbeat.record_health(
                repo=self.repo, root_id="root-a", goal=55, phase="implement", token="malformed-health",
                health={"operation_at": "not-a-time"}, state_dir=self.state,
            )
        self.assertTrue(any(lease["token"] == "malformed-health" for lease in heartbeat._read(Path(result["config"]))["leases"]))
        heartbeat.stop_heartbeat(repo=self.repo, root_id="root-a", goal=55, phase="implement", token="malformed-health", state_dir=self.state)
        self._wait(lambda: not heartbeat._pid_alive(result["pid"]))


    def test_active_probe_with_zero_exit_repair_preserves_liveness(self):
        self.cli.write_text("import json\nprint(json.dumps({'next_steps':[{'kind':'repair'}]}))\n")
        result = self._start(71, "plan", "repair-token", "active")
        self._wait(lambda: not heartbeat._pid_alive(result["pid"]))
        events = self._lines(Path(result["log"]))
        failed = [event for event in events if event["event"] == "renewal_failed"]
        self.assertEqual(3, len(failed))
        self.assertTrue(all(event["worker_status"] == "active" for event in failed))
        self.assertFalse(any(event["event"] in {"liveness_unknown", "worker_stopped"} for event in events))
        self.assertEqual("active", events[-1]["worker_status"])

    def test_acknowledgement_requires_exact_identity_and_live_expiry(self):
        lease = dict(goal=1, phase="plan", actor="worker", token="token")
        step = dict(kind="renewed", goal=1, phase="plan", actor="worker", lease="token", expires_at=time.time()+60)
        def result(value):
            return subprocess.CompletedProcess([], 0, json.dumps(value), "")
        self.assertTrue(heartbeat._renewal_acknowledged(result({'next_steps':[step]}), lease))
        for key, value in [('goal',2), ('phase','review'), ('actor','other'), ('lease','other'), ('expires_at',0), ('expires_at',True), ('expires_at',float('inf')), ('kind','repair')]:
            with self.subTest(key=key,value=value):
                self.assertFalse(heartbeat._renewal_acknowledged(result({'next_steps':[{**step,key:value}]}),lease))
        for malformed in ['not json', '{}', 'null', '{"next_steps": [null]}']:
            self.assertFalse(heartbeat._renewal_acknowledged(subprocess.CompletedProcess([],0,malformed,''),lease))

    def test_stop_during_probe_prevents_renewal(self):
        ready, release = self.directory/'ready', self.directory/'release'
        self.probe.write_text("from pathlib import Path\nimport time\nPath(%r).touch()\nwhile not Path(%r).exists(): time.sleep(.005)\n" % (str(ready),str(release)))
        result = self._start(72,"plan","stop-token","active")
        self._wait(ready.exists)
        heartbeat.stop_heartbeat(repo=self.repo,root_id="root-a",goal=72,phase="plan",token="stop-token",state_dir=self.state)
        release.touch()
        self._wait(lambda:not heartbeat._pid_alive(result['pid']))
        self.assertEqual([],self._lines(self.cli_records))

    def test_stop_during_renewal_prevents_retry(self):
        ready, release = self.directory/'renew-ready', self.directory/'renew-release'
        self.cli.write_text("from pathlib import Path\nimport time\nwith Path(%r).open('a') as f: f.write('{}\\n')\nPath(%r).touch()\nwhile not Path(%r).exists(): time.sleep(.005)\nprint('{}')\n" % (str(self.cli_records),str(ready),str(release)))
        result = self._start(73,'plan','inflight-token','active')
        self._wait(ready.exists)
        heartbeat.stop_heartbeat(repo=self.repo,root_id='root-a',goal=73,phase='plan',token='inflight-token',state_dir=self.state)
        release.touch()
        self._wait(lambda:not heartbeat._pid_alive(result['pid']))
        self.assertEqual(1,len(self._lines(self.cli_records)))
        self.assertEqual([],list(self.state.glob('renew-*.json')))
        self.assertEqual([],self._lines(Path(result['log'])))

    @unittest.skipUnless(os.name == "posix", "POSIX process-group cleanup")
    def test_watchdog_terminates_renewal_descendant(self):
        child_pid = self.directory / 'child-pid'
        self.cli.write_text("import subprocess,sys,time\nfrom pathlib import Path\np=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\nPath(%r).write_text(str(p.pid))\ntime.sleep(30)\n" % str(child_pid))
        config = dict(cli_path=str(self.cli),repo=str(self.repo),runtime_path=str(self.runtime),
                      renewal_timeout_seconds=.05,renewal_cleanup_seconds=.05)
        with self.assertRaises(subprocess.TimeoutExpired):
            heartbeat._renew(config,dict(goal=1,phase='plan',token='token',actor='worker'),self.directory)
        pid = int(child_pid.read_text())
        self._wait(lambda: not heartbeat._pid_alive(pid))
        self.assertEqual([], list(self.directory.glob('renew-*.json')))

    def test_renewal_watchdog_is_bounded_and_cleans_payload(self):
        marker = self.directory/'budgets.json'
        self.cli.write_text("import os,json,time\nfrom pathlib import Path\nPath(%r).write_text(json.dumps([os.environ['ZZZOPS_RENEWAL_TIMEOUT_SECONDS'],os.environ['ZZZOPS_RENEWAL_CLEANUP_SECONDS']]))\ntime.sleep(20)\n" % str(marker))
        config=dict(cli_path=str(self.cli),repo=str(self.repo),runtime_path=str(self.runtime),renewal_timeout_seconds=.05,renewal_cleanup_seconds=.05)
        lease=dict(goal=1,phase='plan',token='token',actor='worker')
        started=time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            heartbeat._renew(config,lease,self.directory)
        self.assertLess(time.monotonic()-started,8)
        self.assertEqual(['0.05','0.05'],json.loads(marker.read_text()))
        self.assertEqual([],list(self.directory.glob('renew-*.json')))

    def test_start_atomically_replaces_the_same_phase_lease(self):
        first = self._start(61, "plan", "old-token", "active")
        second = self._start(61, "plan", "new-token", "active", actor="worker-new")
        self.assertEqual(first["pid"], second["pid"])
        config = json.loads(Path(first["config"]).read_text(encoding="utf-8"))
        self.assertEqual([("new-token", "worker-new")], [
            (lease["token"], lease["actor"]) for lease in config["leases"]
        ])
        heartbeat.stop_heartbeat(
            repo=self.repo, root_id="root-a", goal=61, phase="plan", token="new-token",
            state_dir=self.state,
        )
        self._wait(lambda: not heartbeat._pid_alive(first["pid"]))




class AutomaticHeartbeatTests(unittest.TestCase):
    setUp = HeartbeatProcessTests.setUp
    tearDown = HeartbeatProcessTests.tearDown
    _script = HeartbeatProcessTests._script
    _wait = HeartbeatProcessTests._wait
    _lines = HeartbeatProcessTests._lines
    def start_generic(self, *, grace=.15, mode='active'):
        self.cli.write_text('''import json,sys,time
from pathlib import Path
args=sys.argv[1:]; p=json.loads(Path(args[args.index('--input')+1]).read_text())
with Path(%r).open('a') as h:h.write(json.dumps(p)+'\\n')
print(json.dumps({'next_steps':[{'kind':'renewed','goal':int(args[args.index('--goal')+1]),'node':p['node'],'actor':p['actor'],'lease':p['lease'],'expires_at':time.time()+600}]}))
''' % str(self.cli_records))
        node={'goal':61,'node':'review','item':None,'generation':1}
        result=heartbeat.start_heartbeat(repo=self.repo,root_id='root-a',runtime_path=self.runtime,cli_path=self.cli,
            goal=61,phase=json.dumps(node,sort_keys=True),node=node,token='generic-token',actor='worker-a',
            probe_argv=[sys.executable,str(self.probe),mode,'review','worker-a'],interval_seconds=.03,
            grace_seconds=grace,probe_timeout_seconds=.2,state_dir=self.state)
        self.pids.add(result['pid'])
        return node,result

    def test_short_completion_has_no_probe_or_renewal_invocation(self):
        node,result=self.start_generic(grace=2)
        heartbeat.stop_heartbeat(repo=self.repo,root_id='root-a',goal=61,phase=json.dumps(node,sort_keys=True),token='generic-token',state_dir=self.state)
        self._wait(lambda:not heartbeat._pid_alive(result['pid']))
        self.assertEqual([],self._lines(self.cli_records))
        self.assertEqual([],self._lines(self.probe_records))

    def test_generic_long_review_renews_exact_node_and_stops(self):
        node,result=self.start_generic()
        self._wait(lambda:any(r.get('event')=='renewal_succeeded' for r in self._lines(Path(result['log']))))
        payload=self._lines(self.cli_records)[0]
        self.assertEqual(node,payload['node']);self.assertNotIn('phase',payload);self.assertNotIn('worker_status',payload)
        heartbeat.stop_heartbeat(repo=self.repo,root_id='root-a',goal=61,phase=json.dumps(node,sort_keys=True),token='generic-token',state_dir=self.state)
        self._wait(lambda:not heartbeat._pid_alive(result['pid']))

    def test_restart_same_token_does_not_reset_grace_or_duplicate_runner(self):
        _,first=self.start_generic(grace=2)
        deadline=heartbeat._read(Path(first['config']))['leases'][0]['renew_after']
        _,second=self.start_generic(grace=2)
        self.assertEqual(first['pid'],second['pid'])
        self.assertEqual(deadline,heartbeat._read(Path(first['config']))['leases'][0]['renew_after'])

    def test_public_binding_starts_tracking_and_result_stops_exact_token(self):
        import test_evidence_dag_journeys as dag
        case=dag.DagFixture();case.setUp();self.addCleanup(case.doCleanups)
        case.session.runtime['heartbeat']={'probes':{'worker-produce-None':[sys.executable,str(self.probe),'active','produce','worker-produce-None']},'grace_seconds':120}
        with mock.patch.object(dag.z._heartbeat,'start_heartbeat',return_value={'pid':123}) as start, \
             mock.patch.object(dag.z._heartbeat,'stop_heartbeat',return_value={'stopped':True}) as stop:
            work=case.session.acquire('produce')
            self.assertEqual(1,start.call_count)
            self.assertEqual(work['node'],start.call_args.kwargs['node'])
            self.assertEqual(work['lease']['token'],start.call_args.kwargs['token'])
            self.assertEqual(120,start.call_args.kwargs['grace_seconds'])
            case.session.heartbeat_stop = stop
            case.session.finish(work,{'value':'short success'})
            self.assertEqual(work['lease']['token'],stop.call_args.kwargs['token'])

    def test_public_acquire_bind_finish_runs_and_stops_the_exact_coordinator_process(self):
        import test_evidence_dag_journeys as dag
        case=dag.DagFixture();case.setUp();self.addCleanup(case.doCleanups)
        actor='worker-produce-None'
        case.session.runtime['heartbeat']={
            'probes':{actor:[sys.executable,str(self.probe),'active','produce',actor]},
            'grace_seconds':120,
        }
        # The public fixture intercepts the external cleanup hook by default;
        # route that hook to the real implementation for this process test.
        case.session.heartbeat_stop=dag.z._heartbeat.stop_heartbeat
        work=case.session.acquire('produce')
        root_id=case.session.runtime['root_id']
        paths=dag.z._heartbeat._paths(case.session.repo,root_id)
        config=dag.z._heartbeat._read(paths['config'])
        self.assertEqual([(work['lease']['token'],actor)],[
            (lease['token'],lease['actor']) for lease in config['leases']])
        pid=config['pid']
        self.assertTrue(dag.z._heartbeat._pid_alive(pid))
        process=dag.z._heartbeat._PROCESSES[pid]
        self.addCleanup(lambda:process.poll() is None and process.terminate())
        self.addCleanup(lambda:dag.z._heartbeat.stop_heartbeat(
            repo=case.session.repo,root_id=root_id,goal=work['node']['goal'],
            phase=json.dumps(work['node'],sort_keys=True),token=work['lease']['token']))

        case.session.finish(work,{'value':'short success'})

        self.assertEqual([],dag.z._heartbeat._read(paths['config'])['leases'])
        self._wait(lambda:not dag.z._heartbeat._pid_alive(pid))

    def test_missing_probe_does_not_block_public_short_phase(self):
        import test_evidence_dag_journeys as dag
        case=dag.DagFixture();case.setUp();self.addCleanup(case.doCleanups)
        with mock.patch.object(dag.z._heartbeat,'start_heartbeat') as start:
            work=case.session.acquire('produce');case.session.finish(work,{'value':'short success'})
            start.assert_not_called()

    def test_generic_stopped_probe_never_renews_or_releases_durable_ownership(self):
        _,result=self.start_generic(grace=0,mode='stopped')
        self._wait(lambda:not heartbeat._pid_alive(result['pid']))
        self.assertEqual([],self._lines(self.cli_records))
        self.assertTrue(any(r['event']=='worker_stopped' for r in self._lines(Path(result['log']))))

    def test_generic_unknown_probe_stops_monitoring_without_claiming_worker_stopped(self):
        _,result=self.start_generic(grace=0,mode='unknown')
        self._wait(lambda:not heartbeat._pid_alive(result['pid']))
        events=self._lines(Path(result['log']))
        self.assertEqual([],self._lines(self.cli_records))
        self.assertTrue(any(r['event']=='recovery_required' and r['worker_status']=='unknown' for r in events))
        self.assertFalse(any(r['event']=='worker_stopped' for r in events))


    def test_linked_worktree_can_stop_exact_originating_lease(self):
        import shutil
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                        'commit', '--allow-empty', '-qm', 'fixture'], check=True)
        other=self.directory/'other'
        subprocess.run(['git', '-C', str(self.repo), 'worktree', 'add', '--detach', '-q', str(other)], check=True)
        node={'goal':61,'node':'review','item':None,'generation':1};phase=json.dumps(node,sort_keys=True)
        result=heartbeat.start_heartbeat(repo=self.repo,root_id='root-a',runtime_path=self.runtime,cli_path=self.cli,
            goal=61,phase=phase,node=node,token='linked-token',actor='worker-a',
            probe_argv=[sys.executable,str(self.probe),'active','review','worker-a'],grace_seconds=2,interval_seconds=.03)
        self.pids.add(result['pid'])
        self.addCleanup(lambda:shutil.rmtree(Path(result['config']).parent,ignore_errors=True))
        config=heartbeat._read(Path(result['config']))
        self.assertEqual(str(self.repo.resolve()),config['leases'][0]['repo'])
        heartbeat.stop_heartbeat(repo=other,root_id='root-a',goal=61,phase=phase,token='linked-token')
        self.assertEqual([],heartbeat._read(Path(result['config']))['leases'])
        self._wait(lambda:not heartbeat._pid_alive(result['pid']))

    def test_local_registration_lock_is_bounded(self):
        ready=self.directory/'lock-ready'
        paths=heartbeat._paths(self.repo,'root-a',self.state)
        holder=self._script('holder.py', """import importlib.util,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('held_heartbeat',sys.argv[1]);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
with h._locked(Path(sys.argv[2])):
 Path(sys.argv[3]).touch()
 time.sleep(10)
""")
        process=subprocess.Popen([sys.executable,str(holder),str(MODULE_PATH),str(paths['update_lock']),str(ready)])
        try:
            self._wait(ready.exists)
            started=time.monotonic()
            with self.assertRaisesRegex(ValueError,'lock is busy'):
                self.start_generic(grace=2)
            self.assertLess(time.monotonic()-started,2)
            self.assertFalse(self.cli_records.exists())
        finally:
            process.terminate();process.wait(timeout=3)

    def _start_scheduled(self, *, goal, token, expires_at, cli=None, actor='worker-a'):
        node={'goal':goal,'node':'review','item':None,'generation':1}
        result=heartbeat.start_heartbeat(
            repo=self.repo,root_id='root-a',runtime_path=self.runtime,cli_path=cli or self.cli,
            goal=goal,phase=json.dumps(node,sort_keys=True),node=node,token=token,actor=actor,
            probe_argv=[sys.executable,str(self.probe),'active','review',actor],
            expires_at=expires_at,grace_seconds=0,interval_seconds=.02,
            probe_timeout_seconds=.5,state_dir=self.state)
        self.pids.add(result['pid'])
        return node,result

    def test_acknowledged_expiry_replaces_the_due_deadline_and_suppresses_extra_calls(self):
        """The provider acknowledgement, rather than a global interval, owns the next deadline."""
        acknowledged=self.directory/'acknowledged'
        self.cli.write_text('''import json,sys,time
from pathlib import Path
args=sys.argv[1:];p=json.loads(Path(args[args.index('--input')+1]).read_text())
with Path(%r).open('a') as h:h.write(json.dumps({'called_at':time.time(),'lease':p['lease']})+'\\n')
expiry=time.time()+600
Path(%r).write_text(str(expiry))
print(json.dumps({'next_steps':[{'kind':'renewed','goal':int(args[args.index('--goal')+1]),'node':p['node'],'actor':p['actor'],'lease':p['lease'],'expires_at':expiry}]}))
''' % (str(self.cli_records),str(acknowledged)))
        now=time.time()
        node,result=self._start_scheduled(goal=81,token='long-extension',expires_at=now+.4)
        self._wait(acknowledged.exists)
        returned_expiry=float(acknowledged.read_text())
        self._wait(lambda:heartbeat._read(Path(result['config']))['leases'][0].get('expires_at')==returned_expiry)
        lease=heartbeat._read(Path(result['config']))['leases'][0]
        self.assertGreater(lease['renew_after'],now+30)
        self.assertLess(lease['renew_after'],returned_expiry)
        baseline=len(self._lines(self.cli_records))
        time.sleep(.12)
        self.assertEqual(baseline,len(self._lines(self.cli_records)))
        heartbeat.stop_heartbeat(repo=self.repo,root_id='root-a',goal=81,
            phase=json.dumps(node,sort_keys=True),token='long-extension',state_dir=self.state)

    def test_initial_deadlines_are_derived_independently_from_each_lease_expiry(self):
        now=time.time()
        _,first=self._start_scheduled(goal=82,token='short-lease',expires_at=now+180)
        _,second=self._start_scheduled(goal=83,token='long-lease',expires_at=now+600,actor='worker-b')
        self.assertEqual(first['pid'],second['pid'])
        leases={item['token']:item for item in heartbeat._read(Path(first['config']))['leases']}
        self.assertLess(leases['short-lease']['renew_after'],leases['long-lease']['renew_after'])
        for lease in leases.values():
            self.assertLess(lease['renew_after'],lease['expires_at'])

    def test_simultaneously_due_leases_renew_concurrently_within_the_expiry_margin(self):
        self.cli.write_text('''import json,sys,time
from pathlib import Path
args=sys.argv[1:];p=json.loads(Path(args[args.index('--input')+1]).read_text());records=Path(%r)
with records.open('a') as h:h.write(json.dumps({'event':'start','lease':p['lease'],'at':time.time()})+'\\n')
time.sleep(.2)
with records.open('a') as h:h.write(json.dumps({'event':'end','lease':p['lease'],'at':time.time()})+'\\n')
print(json.dumps({'next_steps':[{'kind':'renewed','goal':int(args[args.index('--goal')+1]),'node':p['node'],'actor':p['actor'],'lease':p['lease'],'expires_at':time.time()+600}]}))
''' % str(self.cli_records))
        due=time.time()+.35
        self._start_scheduled(goal=84,token='due-a',expires_at=due)
        self._start_scheduled(goal=85,token='due-b',expires_at=due,actor='worker-b')
        self._wait(lambda:len([r for r in self._lines(self.cli_records) if r['event']=='end'])==2)
        rows=self._lines(self.cli_records)
        starts={r['lease']:r['at'] for r in rows if r['event']=='start'}
        ends={r['lease']:r['at'] for r in rows if r['event']=='end'}
        self.assertLess(max(starts.values()),min(ends.values()),'renewals did not overlap')

    @unittest.skipUnless(os.name == 'posix' and hasattr(__import__('signal'),'SIGUSR1'),
                         'deterministic coordinator wake requires SIGUSR1')
    def test_ninth_simultaneously_due_lease_finishes_before_its_safety_boundary(self):
        """A saturated renewal pool must reserve capacity for every due lease."""
        self.cli.write_text('''import json,sys,time
from pathlib import Path
args=sys.argv[1:];p=json.loads(Path(args[args.index('--input')+1]).read_text());records=Path(%r)
with records.open('a') as h:h.write(json.dumps({'event':'start','lease':p['lease'],'at':time.time()})+'\\n')
time.sleep(1.1)
with records.open('a') as h:h.write(json.dumps({'event':'ack','lease':p['lease'],'at':time.time()})+'\\n')
print(json.dumps({'next_steps':[{'kind':'renewed','goal':int(args[args.index('--goal')+1]),'node':p['node'],'actor':p['actor'],'lease':p['lease'],'expires_at':time.time()+600}]}))
''' % str(self.cli_records))
        registrations=[]
        for offset in range(9):
            node,result=self._start_scheduled(
                goal=100+offset,token='saturated-%d' % offset,
                actor='worker-%d' % offset,expires_at=time.time()+600)
            registrations.append((node,result))
        config_path=Path(registrations[0][1]['config'])
        paths=heartbeat._paths(self.repo,'root-a',self.state)
        boundary=time.time()+2.0
        with heartbeat._locked(paths['update_lock'],timeout_seconds=1):
            config=heartbeat._read(config_path)
            for lease in config['leases']:
                lease['renew_after']=0
                lease['expires_at']=boundary
            heartbeat._atomic_write(config_path,config)
        os.kill(config['pid'],__import__('signal').SIGUSR1)

        self._wait(lambda:len([r for r in self._lines(self.cli_records) if r['event']=='ack'])==9,timeout=5)
        acknowledgements=self._lines(self.cli_records)
        starts=[r for r in acknowledgements if r['event']=='start']
        acks=[r for r in acknowledgements if r['event']=='ack']
        self.assertEqual(8,len([r for r in starts if r['at'] < min(a['at'] for a in acks)]),
                         'fixture did not saturate the eight-worker first wave')
        self.assertTrue(all(row['at'] < boundary for row in acks),
                        'a saturated renewal acknowledgement crossed its lease safety boundary')

        for node,_ in registrations:
            heartbeat.stop_heartbeat(
                repo=self.repo,root_id='root-a',goal=node['goal'],
                phase=json.dumps(node,sort_keys=True),token='saturated-%d' % (node['goal']-100),
                state_dir=self.state)

    @unittest.skipUnless(os.name == 'posix', 'real coordinator termination uses POSIX signals')
    def test_coordinator_death_relaunch_preserves_the_per_lease_deadline(self):
        node,first=self._start_scheduled(goal=86,token='restart-token',expires_at=time.time()+600)
        deadline=heartbeat._read(Path(first['config']))['leases'][0]['renew_after']
        os.kill(first['pid'],15)
        self._wait(lambda:not heartbeat._pid_alive(first['pid']))
        _,second=self._start_scheduled(goal=86,token='restart-token',expires_at=time.time()+600)
        self.assertNotEqual(first['pid'],second['pid'])
        lease=heartbeat._read(Path(second['config']))['leases'][0]
        self.assertEqual(deadline,lease['renew_after'])
        heartbeat.stop_heartbeat(repo=self.repo,root_id='root-a',goal=86,
            phase=json.dumps(node,sort_keys=True),token='restart-token',state_dir=self.state)


if __name__ == "__main__":
    unittest.main()
