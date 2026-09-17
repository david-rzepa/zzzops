import importlib.util
import builtins
import json
import os
import sys
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
            probe_argv=[sys.executable, str(self.probe), mode, phase], interval_seconds=.03,
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
        self.assertEqual([sys.executable, str(self.probe), "active", "implement"], config["leases"][0]["probe_argv"])
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


if __name__ == "__main__":
    unittest.main()
