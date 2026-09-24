"""Local phase-lease heartbeat coordinator.

Probe commands are deliberately confined to this local file-backed runtime. The
durable goal stores worker identity and lease state, never executable commands.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl as _fcntl
except ImportError:  # Windows
    _fcntl = None

try:
    import msvcrt as _msvcrt
except ImportError:  # POSIX
    _msvcrt = None


_PROCESSES: dict[int, subprocess.Popen[Any]] = {}
_WAKE = threading.Event()
_HEALTH_SIGNAL_FIELDS = frozenset({"activity_at", "output_at", "cpu_progress_at", "io_progress_at", "operation_at"})
_EXPECTED_IDLE_STATUSES = frozenset({"waiting", "awaiting_input", "provider_call", "sleeping"})


def _ignore_wake_signal() -> None:
    if hasattr(signal, "SIGUSR1"):
        signal.signal(signal.SIGUSR1, signal.SIG_IGN)


def _identity(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"{field} must be non-empty text")
    return value


def _command(value: list[str], field: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item or "\x00" in item for item in value):
        raise ValueError(f"{field} must be a non-empty argument list")
    return list(value)


def _worker_liveness_probe(value: list[str], actor: str) -> list[str]:
    """Validate a probe is bound to the leased worker, not its probe shell."""
    command = _command(value, "probe_argv")
    if actor not in command[1:]:
        raise ValueError("probe_argv must include the bound worker identity as an exact argument")
    if any("$$" in argument or "$PPID" in argument or "$BASHPID" in argument for argument in command):
        raise ValueError("probe_argv must not use a self-referential shell process identity")
    return command


def _default_state_dir(repo: Path) -> Path:
    key = hashlib.sha256(str(repo.resolve()).encode()).hexdigest()[:24]
    uid = getattr(os, "getuid", lambda: 0)()
    return Path(tempfile.gettempdir()) / f"zzzops-heartbeats-{uid}" / key


def _paths(repo: Path, root_id: str, state_dir: Path | None = None) -> dict[str, Path]:
    root_key = hashlib.sha256(_identity(root_id, "root_id").encode()).hexdigest()[:24]
    directory = (state_dir or _default_state_dir(repo)).resolve()
    return {
        "directory": directory,
        "config": directory / f"{root_key}.json",
        "update_lock": directory / f"{root_key}.update.lock",
        "coordinator_lock": directory / f"{root_key}.coordinator.lock",
        "log": directory / f"{root_key}.log",
    }


def _ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError as exc:
        raise ValueError(f"Heartbeat runtime directory cannot be made private: {path}") from exc


@contextlib.contextmanager
def _locked(path: Path, blocking: bool = True) -> Iterator[Any]:
    if _fcntl is None and _msvcrt is None:
        raise ValueError("Local heartbeat locking is unavailable on this platform; keep the lease and request explicit recovery coordination.")
    _ensure_private_directory(path.parent)
    handle = path.open("a+b")
    try:
        if _fcntl is not None:
            flags = _fcntl.LOCK_EX | (0 if blocking else _fcntl.LOCK_NB)
            _fcntl.flock(handle.fileno(), flags)
        else:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            mode = _msvcrt.LK_LOCK if blocking else _msvcrt.LK_NBLCK
            try:
                _msvcrt.locking(handle.fileno(), mode, 1)
            except OSError as exc:
                if not blocking:
                    raise BlockingIOError(str(exc)) from exc
                raise
    except (OSError, BlockingIOError):
        handle.close()
        raise
    try:
        yield handle
    finally:
        if _fcntl is not None:
            _fcntl.flock(handle.fileno(), _fcntl.LOCK_UN)
        else:
            handle.seek(0)
            _msvcrt.locking(handle.fileno(), _msvcrt.LK_UNLCK, 1)
        handle.close()


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"leases": []}
    if not isinstance(value, dict) or not isinstance(value.get("leases"), list):
        raise ValueError("heartbeat config is invalid")
    return value


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    _ensure_private_directory(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _pid_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid < 1:
        return False
    local = _PROCESSES.get(pid)
    if local is not None:
        return local.poll() is None
    if os.name == "nt":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
        stat_path = Path(f"/proc/{pid}/stat")
        if stat_path.exists() and stat_path.read_text(encoding="utf-8").split()[2] == "Z":
            return False
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _windows_pid_alive(pid: int, kernel32: Any = None) -> bool:
    """Query Windows process state without delivering a signal."""
    import ctypes
    from ctypes import wintypes

    if kernel32 is None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
    process_query_limited_information = 0x1000
    still_active = 259
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _log(path: Path, event: str, lease: dict[str, Any], **detail: Any) -> None:
    record = {
        "time": time.time(), "event": event, "goal": lease.get("goal"),
        "phase": lease.get("phase"), "token": lease.get("token"), "actor": lease.get("actor"), **detail,
    }
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def _recent_events(path: Path, maximum_bytes: int = 65536) -> list[dict[str, Any]]:
    """Return a bounded, structured tail of coordinator-owned log records."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - maximum_bytes))
            data = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    if len(data) >= maximum_bytes:
        data = data.split("\n", 1)[-1]
    events = []
    for line in data.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _health_signal_snapshot(value: Any) -> tuple[dict[str, float], str | None]:
    if value is None:
        return {}, None
    if not isinstance(value, dict):
        return {}, "malformed_health_signals"
    signals: dict[str, float] = {}
    for field in _HEALTH_SIGNAL_FIELDS:
        signal_at = value.get(field)
        if signal_at is None:
            continue
        if not isinstance(signal_at, (int, float)) or isinstance(signal_at, bool) or not math.isfinite(signal_at):
            return {}, "malformed_health_signals"
        signals[field] = float(signal_at)
    return signals, None


def heartbeat_health(
    *, repo: Path, root_id: str, goal: int, phase: str, token: str,
    state_dir: Path | None = None, now: float | None = None,
) -> dict[str, Any]:
    """Classify local worker health without changing durable or local lease state.

    Health is diagnostic only.  In particular, quiet output, low resource use,
    a stale provider operation, and an unknown probe never become a stopped
    result and never remove a lease.
    """
    current = time.time() if now is None else now
    paths = _paths(repo.resolve(), root_id, state_dir)
    try:
        config = _read(paths["config"])
    except (OSError, ValueError, json.JSONDecodeError):
        return {"classification": "unknown", "evidence_at": current,
                "explanation": ["The local heartbeat state is malformed or unreadable."],
                "next_action": "Inspect the local heartbeat state, harness worker status, latest result file, and backend lease before recovery."}
    lease = next((item for item in config["leases"] if
                  (item.get("goal"), item.get("phase"), item.get("token")) == (goal, phase, token)), None)
    events = [event for event in _recent_events(paths["log"])
              if (event.get("goal"), event.get("phase"), event.get("token")) == (goal, phase, token)]
    latest = events[-1] if events else None
    evidence_at = latest.get("time") if isinstance(latest, dict) else None
    terminal = next((event for event in reversed(events) if event.get("event") == "worker_stopped"), None)
    if terminal is not None:
        return {"classification": "stopped", "evidence_at": terminal.get("time"),
                "explanation": ["The bound liveness probe recorded a terminal worker status."],
                "next_action": "Inspect the latest result file and backend lease, then recover only if the durable phase remains incomplete."}
    if lease is None:
        return {"classification": "unknown", "evidence_at": evidence_at,
                "explanation": ["No matching local heartbeat lease is currently tracked; no terminal worker status was observed."],
                "next_action": "Inspect the real process, harness worker status, latest result file, and backend lease before recovery."}
    signals, malformed = _health_signal_snapshot(lease.get("health"))
    if malformed:
        return {"classification": "unknown", "evidence_at": evidence_at,
                "explanation": ["The worker health signal data is malformed."],
                "next_action": "Inspect the real process, harness worker status, latest result file, and backend lease before recovery."}
    if latest and latest.get("event") == "liveness_unknown":
        return {"classification": "unknown", "evidence_at": evidence_at,
                "explanation": ["The liveness probe did not establish a terminal worker status."],
                "next_action": "Inspect the real process, harness worker status, latest result file, and backend lease before recovery."}
    harness_status = lease.get("health", {}).get("harness_status") if isinstance(lease.get("health"), dict) else None
    newest_signal = max(signals.values(), default=evidence_at if isinstance(evidence_at, (int, float)) else None)
    threshold = 900.0 if phase in {"understanding", "test_design", "test_execution"} else 300.0
    if harness_status in _EXPECTED_IDLE_STATUSES:
        classification = "idle-but-expected"
        explanation = [f"Harness reports expected idle state: {harness_status}."]
    elif newest_signal is None:
        classification = "unknown"
        explanation = ["No privacy-safe activity signal has been recorded yet."]
    elif current - newest_signal <= threshold:
        classification = "active"
        explanation = ["Recent heartbeat renewal or worker progress signal was observed."]
    else:
        classification = "suspect"
        explanation = [f"No progress signal has been observed for {current - newest_signal:.0f}s (threshold {threshold:.0f}s)."]
    return {"classification": classification, "evidence_at": newest_signal,
            "signals": sorted(signals), "harness_status": harness_status,
            "explanation": explanation,
            "next_action": "Wait and recheck." if classification in {"active", "idle-but-expected"} else
                           "Inspect the real process, harness worker status, latest result file, and backend lease before recovery."}


def record_health(
    *, repo: Path, root_id: str, goal: int, phase: str, token: str,
    health: dict[str, Any], state_dir: Path | None = None,
) -> None:
    """Persist timestamp-only health evidence for one already-tracked lease."""
    signals, malformed = _health_signal_snapshot(health)
    status = health.get("harness_status") if isinstance(health, dict) else None
    if malformed or (status is not None and not isinstance(status, str)):
        raise ValueError("health must contain only finite timestamp signals and an optional text harness_status")
    paths = _paths(repo.resolve(), root_id, state_dir)
    with _locked(paths["update_lock"]):
        config = _read(paths["config"])
        for lease in config["leases"]:
            if (lease.get("goal"), lease.get("phase"), lease.get("token")) == (goal, phase, token):
                lease["health"] = {**signals, **({"harness_status": status} if status else {})}
                _atomic_write(paths["config"], config)
                return
    raise ValueError("heartbeat lease is not tracked")


def _remove_lease(config_path: Path, update_lock: Path, goal: int, phase: str, token: str) -> None:
    with _locked(update_lock):
        config = _read(config_path)
        config["leases"] = [
            lease for lease in config["leases"]
            if (lease.get("goal"), lease.get("phase"), lease.get("token")) != (goal, phase, token)
        ]
        _atomic_write(config_path, config)


def start_heartbeat(
    *, repo: Path, root_id: str, runtime_path: Path, cli_path: Path,
    goal: int, phase: str, token: str, actor: str, probe_argv: list[str],
    interval_seconds: float = 300, probe_timeout_seconds: float = 10,
    retry_limit: int = 3, state_dir: Path | None = None,
) -> dict[str, Any]:
    """Upsert a local lease and ensure one detached coordinator for repo/root."""
    repo = repo.resolve()
    runtime_path, cli_path = runtime_path.resolve(), cli_path.resolve()
    if not isinstance(goal, int) or isinstance(goal, bool) or goal < 1:
        raise ValueError("goal must be a positive integer")
    phase, token, actor = (_identity(phase, "phase"), _identity(token, "token"), _identity(actor, "actor"))
    probe_argv = _worker_liveness_probe(probe_argv, actor)
    if interval_seconds <= 0 or probe_timeout_seconds <= 0:
        raise ValueError("heartbeat intervals and timeouts must be positive")
    if not isinstance(retry_limit, int) or isinstance(retry_limit, bool) or retry_limit < 1:
        raise ValueError("retry_limit must be a positive integer")
    paths = _paths(repo, root_id, state_dir)
    _ensure_private_directory(paths["directory"])
    lease = {
        "goal": goal, "phase": phase, "token": token, "actor": actor,
        "probe_argv": probe_argv,
    }
    with _locked(paths["update_lock"]):
        config = _read(paths["config"])
        config.update({
            "repo": str(repo), "root_id": root_id, "runtime_path": str(runtime_path),
            "cli_path": str(cli_path), "interval_seconds": float(interval_seconds),
            "probe_timeout_seconds": float(probe_timeout_seconds), "retry_limit": retry_limit,
            "log_path": str(paths["log"]), "coordinator_lock": str(paths["coordinator_lock"]),
            "update_lock": str(paths["update_lock"]),
        })
        config["leases"] = [
            current for current in config.get("leases", [])
            if (current.get("goal"), current.get("phase")) != (goal, phase)
        ] + [lease]
        running = _pid_alive(config.get("pid"))
        started = False
        if not running:
            # The child must never observe a missing or half-written config.
            _atomic_write(paths["config"], config)
            options: dict[str, Any] = {
                "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL, "close_fds": True, "start_new_session": True,
            }
            if os.name != "nt" and hasattr(signal, "SIGUSR1"):
                options["preexec_fn"] = _ignore_wake_signal
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "run", "--config", str(paths["config"])],
                **options,
            )
            config["pid"] = process.pid
            _PROCESSES[process.pid] = process
            started = True
        _atomic_write(paths["config"], config)
        if running and hasattr(signal, "SIGUSR1"):
            with contextlib.suppress(OSError):
                os.kill(config["pid"], signal.SIGUSR1)
    return {"started": started, "pid": config["pid"], "config": str(paths["config"]), "log": str(paths["log"])}


def stop_heartbeat(
    *, repo: Path, root_id: str, goal: int, phase: str, token: str,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """Stop locally tracking one exact lease without releasing durable ownership."""
    paths = _paths(repo.resolve(), root_id, state_dir)
    _remove_lease(paths["config"], paths["update_lock"], goal, phase, token)
    config = _read(paths["config"])
    if _pid_alive(config.get("pid")) and hasattr(signal, "SIGUSR1"):
        with contextlib.suppress(OSError):
            os.kill(config["pid"], signal.SIGUSR1)
    return {"stopped": True, "config": str(paths["config"])}


def _renew(config: dict[str, Any], lease: dict[str, Any], directory: Path) -> subprocess.CompletedProcess[str]:
    payload = {
        "operation": "renew", "phase": lease["phase"], "lease": lease["token"],
        "actor": lease["actor"], "worker_status": "active", "request_id": uuid.uuid4().hex,
    }
    payload_path = directory / f"renew-{os.getpid()}-{uuid.uuid4().hex}.json"
    _atomic_write(payload_path, payload)
    try:
        cli_path = Path(config["cli_path"])
        cli = [sys.executable, str(cli_path)] if cli_path.suffix == ".py" or not os.access(cli_path, os.X_OK) else [str(cli_path)]
        work_timeout = float(config.get("renewal_timeout_seconds", 30))
        cleanup_timeout = float(config.get("renewal_cleanup_seconds", 10))
        if not all(math.isfinite(value) and value > 0 for value in (work_timeout, cleanup_timeout)):
            raise ValueError("renewal budgets must be finite positive seconds")
        environment = dict(os.environ, ZZZOPS_RENEWAL_TIMEOUT_SECONDS=str(work_timeout),
                           ZZZOPS_RENEWAL_CLEANUP_SECONDS=str(cleanup_timeout))
        command = [*cli, "--repo", config["repo"], "--intent", "execute",
                   "--goal", str(lease["goal"]), "--runtime", config["runtime_path"],
                   "--input", str(payload_path)]
        process = subprocess.Popen(command, cwd=config["repo"], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, env=environment,
                                   start_new_session=True)
        try:
            # Reserve four seconds of the watchdog margin for tree cleanup/reap.
            stdout, stderr = process.communicate(timeout=work_timeout + cleanup_timeout + 1)
        except subprocess.TimeoutExpired:
            # Only terminate the process tree created for this renewal attempt.
            if os.name == "posix":
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            elif os.name == "nt":
                # Windows tree termination is best effort; always reap our child.
                with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=2, check=False)
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            # Do not wait indefinitely for pipes held by an escaped descendant.
            process.stdout.close()
            process.stderr.close()
            process.wait(timeout=2)
            raise
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        payload_path.unlink(missing_ok=True)


def _renewal_acknowledged(result: subprocess.CompletedProcess[str], lease: dict[str, Any]) -> bool:
    if result.returncode != 0:
        return False
    try:
        response = json.loads(result.stdout)
        steps = response["next_steps"]
        if not isinstance(steps, list) or len(steps) != 1:
            return False
        step = steps[0]
        expiry = step.get("expires_at")
        return (step.get("kind") == "renewed"
                and all(step.get(key) == lease[key] for key in ("goal", "phase", "actor"))
                and step.get("lease") == lease["token"]
                and isinstance(expiry, (int, float)) and not isinstance(expiry, bool)
                and math.isfinite(expiry) and expiry > time.time())
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def _tracked(config_path: Path, lease: dict[str, Any]) -> bool:
    return any(all(current.get(key) == lease.get(key) for key in ("goal", "phase", "token", "actor"))
               for current in _read(config_path)["leases"])


def _wait_for_config_change(config_path: Path, interval: float, observed: int) -> None:
    """Sleep until the next cycle, polling config changes where wake signals lack support."""
    deadline = time.monotonic() + interval
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        if _WAKE.wait(min(remaining, 1.0)):
            _WAKE.clear()
            return
        try:
            if config_path.stat().st_mtime_ns != observed:
                return
        except FileNotFoundError:
            return


def run(config_path: Path) -> int:
    """Run until no leases remain or another coordinator owns this config."""
    config_path = config_path.resolve()
    initial = _read(config_path)
    coordinator_lock = Path(initial["coordinator_lock"])
    update_lock = Path(initial["update_lock"])
    try:
        lifetime = _locked(coordinator_lock, blocking=False)
        lifetime.__enter__()
    except BlockingIOError:
        return 0
    failures: dict[str, int] = {}
    try:
        if hasattr(signal, "SIGUSR1"):
            signal.signal(signal.SIGUSR1, lambda _signum, _frame: _WAKE.set())
        while True:
            try:
                observed_config = config_path.stat().st_mtime_ns
            except FileNotFoundError:
                return 0
            config = _read(config_path)
            leases = list(config["leases"])
            if not leases:
                return 0
            interval = float(config["interval_seconds"])
            timeout = float(config["probe_timeout_seconds"])
            limit = int(config["retry_limit"])
            log_path = Path(config["log_path"])
            for lease in leases:
                token = lease["token"]
                if not _tracked(config_path, lease):
                    continue
                try:
                    probe = subprocess.run(
                        _command(lease["probe_argv"], "probe_argv"), cwd=config["repo"],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=timeout, check=False, shell=False,
                    )
                    status = "active" if probe.returncode == 0 else "stopped" if probe.returncode == 1 else "unknown"
                except (OSError, subprocess.TimeoutExpired) as exc:
                    status = "unknown"
                    probe = exc
                if not _tracked(config_path, lease):
                    failures.pop(token, None)
                    continue
                if status == "stopped":
                    _log(log_path, "worker_stopped", lease)
                    _remove_lease(config_path, update_lock, lease["goal"], lease["phase"], token)
                    failures.pop(token, None)
                    continue
                if status == "active":
                    try:
                        renewed = _renew(config, lease, config_path.parent)
                    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
                        probe = exc
                    else:
                        if _renewal_acknowledged(renewed, lease):
                            _log(log_path, "renewal_succeeded", lease, worker_status="active")
                            failures.pop(token, None)
                            continue
                        probe = renewed
                if not _tracked(config_path, lease):
                    failures.pop(token, None)
                    continue
                failures[token] = failures.get(token, 0) + 1
                detail = type(probe).__name__ if not isinstance(probe, subprocess.CompletedProcess) else f"exit_{probe.returncode}"
                if status == "active" and isinstance(probe, subprocess.CompletedProcess) and probe.returncode == 0:
                    detail = "invalid_renewal_acknowledgement"
                _log(log_path, "renewal_failed" if status == "active" else "liveness_unknown", lease,
                     worker_status=status, attempt=failures[token], detail=detail)
                if failures[token] >= limit:
                    _log(log_path, "recovery_required", lease, worker_status=status,
                         reason="renewal_failed" if status == "active" else "liveness_unknown", attempts=failures[token])
                    _remove_lease(config_path, update_lock, lease["goal"], lease["phase"], token)
                    failures.pop(token, None)
            _wait_for_config_change(config_path, interval, observed_config)
    finally:
        lifetime.__exit__(None, None, None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ZzzOps local lease heartbeat")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    return run(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
