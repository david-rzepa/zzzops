"""`checks.run`: exact-tree verification, optional command lanes and observed cost."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
import signal
import subprocess
import sys
import threading
import time

from engine.canon import H
from engine.identity import Identity
from engine.ops.run import Blocked, Done
from engine.test_cost import available_cpus, cpu_budget, lookup_baseline, unavailable

TAIL = 2048
DETAILS_LIMIT = 4096


def shell(git) -> str:
    if os.name != "nt":
        return "/bin/sh"
    return os.path.normpath(os.path.join(git.out("--exec-path"), "..", "..", "bin", "sh.exe"))


def kill_group(proc):
    """Return false when only the parent fallback could be attempted."""
    try:
        if os.name == "nt":
            outcome = subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                                     capture_output=True, timeout=0.5)
            if outcome.returncode == 0:
                return True
        else:
            os.killpg(proc.pid, signal.SIGKILL)
            return True
    except ProcessLookupError:
        return True  # The process group no longer exists.
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        proc.kill()
    except OSError:
        pass
    # Killing just the parent does not prove that descendants have stopped.
    return False


class _Commands:
    """Both lanes share a deadline, cancellation event and live-process registry."""
    def __init__(self, sh, cwd, deadline):
        self.sh, self.cwd, self.deadline = sh, cwd, deadline
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.live = set()
        self.unconfirmed = set()

    def cancel(self):
        with self.lock:
            self.stopped.set()
            for proc in self.live:
                if kill_group(proc) is False:
                    self.unconfirmed.add(proc.pid)

    def command(self, cmd, env):
        started = time.monotonic()
        proc = None
        timed_out = False
        try:
            group = ({"start_new_session": True} if os.name != "nt"
                     else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP})
            # A sibling's cancellation cannot miss a process still being launched.
            with self.lock:
                if self.stopped.is_set():
                    return None
                proc = subprocess.Popen([self.sh, "-c", cmd], cwd=self.cwd, env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **group)
                self.live.add(proc)
            try:
                output, _ = proc.communicate(timeout=max(0.0, self.deadline - time.monotonic()))
                code = proc.returncode
                if self.stopped.is_set():
                    timed_out, code = True, -1
            except subprocess.TimeoutExpired:
                self.cancel()
                try:
                    output, _ = proc.communicate(timeout=1.0)
                except (subprocess.TimeoutExpired, OSError) as error:
                    with self.lock:
                        self.unconfirmed.add(proc.pid)
                    output = getattr(error, "output", None) or b""
                    output += b"\nProcess/pipe termination could not be confirmed after bounded cleanup."
                timed_out, code = True, -1
        except OSError as error:
            output, code = str(error).encode(), 127
            if proc is not None:
                self.cancel()
                try:
                    proc.communicate(timeout=1.0)
                except (subprocess.TimeoutExpired, OSError):
                    with self.lock:
                        self.unconfirmed.add(proc.pid)
        finally:
            if proc is not None:
                with self.lock:
                    self.live.discard(proc)
        elapsed = max(0.0, time.monotonic() - started)
        milliseconds = round(elapsed * 1000)
        return ({"cmd": cmd, "exit": code, "seconds": int(elapsed),
                 "milliseconds": milliseconds, "tail": (output or b"")[-TAIL:].decode("utf-8", "replace")}, timed_out)

    def lane(self, commands, workers):
        details = []
        env = dict(os.environ, ZZZOPS_TEST_WORKERS=str(workers))
        for cmd in commands:
            if self.stopped.is_set():
                break
            if time.monotonic() >= self.deadline:
                self.cancel()
                break
            observation = self.command(cmd, env)
            if observation is not None:
                detail, _ = observation
                details.append(detail)
        return details


def run_one(sh: str, cmd: str, cwd: str, timeout: float) -> tuple:
    """Retain the legacy four-value helper, including its minimum timeout."""
    runner = _Commands(sh, cwd, time.monotonic() + max(1.0, timeout))
    detail, timed_out = runner.command(cmd, dict(os.environ))
    return detail["exit"], timed_out, detail["seconds"], detail["tail"]


def cap_details(details: list) -> list:
    import json
    while len(json.dumps(details).encode("utf-8")) > DETAILS_LIMIT:
        longest = max(details, key=lambda d: len(d["tail"]), default=None)
        if not longest or not longest["tail"]:
            break
        longest["tail"] = longest["tail"][len(longest["tail"]) // 2:]
    return details


def run(ctx):
    p = ctx.worktree
    ident = Identity(ctx.git)
    tree = ctx.inputs["code"]
    head = ctx.git.out("rev-parse", "HEAD", cwd=p)
    head_tree = ident.code_tree(head)
    if head_tree != tree:
        return Done({"result": {"passed": False, "tree": head_tree, "details": [],
                                "timing": {"status": "unavailable", "reason": "tree_mismatch"}}}, ok=False,
                    findings=[{"key": "tree-mismatch", "input": "code",
                               "text": f"the work branch tip (code tree {head_tree[:7]}) differs from the recorded "
                                       f"checkpoint ({tree[:7]}); submit a checkpoint at the tip"}])
    goal_commands = list(ctx.inputs.get("commands") or [])
    verification = ctx.settings["verification"]
    repo_commands = list(verification["commands"])
    observed_cpus = available_cpus()
    budget = cpu_budget(observed_cpus)
    parallel = bool(verification.get("parallel_commands") and budget > 1 and goal_commands and repo_commands)
    workers = ({"goal": budget // 2, "verification": budget - budget // 2} if parallel
               else {"goal": budget, "verification": budget})
    sh = shell(ctx.git)
    started = time.monotonic()
    commands = _Commands(sh, p, started + verification["timeout_minutes"] * 60)
    try:
        if parallel:
            with ThreadPoolExecutor(max_workers=2) as pool:
                goal_future = pool.submit(commands.lane, goal_commands, workers["goal"])
                repo_future = pool.submit(commands.lane, repo_commands, workers["verification"])
                goal_details, repo_details = goal_future.result(), repo_future.result()
        else:
            goal_details = commands.lane(goal_commands, workers["goal"])
            repo_details = commands.lane(repo_commands, workers["verification"])
        total_ms = max(0, round((time.monotonic() - started) * 1000))
    finally:
        # Futures and process groups have exited before cleanup of the shared tree.
        if not commands.unconfirmed:
            ctx.git.run("reset", "-q", "--hard", "HEAD", cwd=p, check=False)
            ctx.git.run("clean", "-q", "-fd", cwd=p, check=False)
    if commands.unconfirmed:
        pids = sorted(commands.unconfirmed)
        return Blocked({"waiting_for": "human", "category": "external",
                        "reason": "verification process termination could not be confirmed",
                        "question": f"Verification stopped and process groups or pipes for PIDs {pids} "
                                    "could not be confirmed stopped. The worktree was preserved. "
                                    "Stop the remaining processes and inspect the checkout before retrying.",
                        "op_state": {"unconfirmed_pids": pids}})
    details = ([dict(d, source="goal") for d in goal_details]
               + [dict(d, source="verification") for d in repo_details])
    passed = (not commands.stopped.is_set() and all(d["exit"] == 0 for d in details)
              and len(details) == len(goal_commands) + len(repo_commands))
    plan = {"commands": [("goal", c) for c in goal_commands] + [("verification", c) for c in repo_commands],
            "parallel_commands": parallel, "cpu_budget": budget, "workers": workers}
    repo_plan = {"commands": repo_commands, "parallel_commands": parallel,
                 "cpu_budget": budget, "workers": workers["verification"]}
    timing = {"total_ms": total_ms,
              "goal_ms": sum(d["milliseconds"] for d in goal_details),
              "verification_ms": sum(d["milliseconds"] for d in repo_details),
              "parallel_commands": parallel, "workers": workers, "cpu_budget": budget,
              "environment": {"platform": sys.platform, "python": f"{sys.version_info.major}.{sys.version_info.minor}",
                              "cpus": observed_cpus},
              "plan_sha256": H(plan), "verification_plan_sha256": H(repo_plan)}
    try:
        timing["baseline"] = lookup_baseline(ctx, timing)
    except Exception:
        timing["baseline"] = unavailable("invalid_evidence")
    details = cap_details(details)
    findings = []
    if not passed:
        bad = next((d for d in details if d["exit"] != 0), None)
        text = (f"`{bad['cmd']}` {'timed out' if bad['exit'] == -1 else 'exited ' + str(bad['exit'])}:\n{bad['tail'][-1024:]}"
                if bad else "verification timed out before all commands could start")
        findings = [{"key": "failed", "input": "code", "text": text}]
    return Done({"result": {"passed": passed, "tree": tree, "details": details, "timing": timing}},
                ok=passed, findings=findings, summary="passed" if passed else findings[0]["text"].splitlines()[0])
