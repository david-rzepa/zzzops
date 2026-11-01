"""`checks.run` (SPEC §5.3): the goal's test commands and the repository's verification commands on the exact tree."""

from __future__ import annotations

import os
import signal
import subprocess
import time

from engine.identity import Identity
from engine.ops.run import Done

TAIL = 2048
DETAILS_LIMIT = 4096


def shell(git) -> str:
    if os.name != "nt":
        return "/bin/sh"
    exec_path = git.out("--exec-path")
    return os.path.normpath(os.path.join(exec_path, "..", "..", "bin", "sh.exe"))


def kill_group(proc):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


def run_one(sh: str, cmd: str, cwd: str, timeout: float) -> tuple:
    kw = {"start_new_session": True} if os.name != "nt" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    start = time.monotonic()
    proc = subprocess.Popen([sh, "-c", cmd], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)
    try:
        out, _ = proc.communicate(timeout=max(1.0, timeout))
        code, timed_out = proc.returncode, False
    except subprocess.TimeoutExpired:
        kill_group(proc)
        out, _ = proc.communicate()
        code, timed_out = -1, True
    return code, timed_out, int(time.monotonic() - start), (out or b"")[-TAIL:].decode("utf-8", "replace")


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
    T = ctx.inputs["code"]
    head = ctx.git.out("rev-parse", "HEAD", cwd=p)
    head_tree = ident.code_tree(head)
    if head_tree != T:
        return Done({"result": {"passed": False, "tree": head_tree, "details": []}}, ok=False,
                    findings=[{"key": "tree-mismatch", "input": "code",
                               "text": f"the work branch tip (code tree {head_tree[:7]}) differs from the recorded "
                                       f"checkpoint ({T[:7]}); submit a checkpoint at the tip"}])
    cmds = list(ctx.inputs.get("commands") or []) + list(ctx.settings["verification"]["commands"])
    end = time.monotonic() + ctx.settings["verification"]["timeout_minutes"] * 60
    sh = shell(ctx.git)
    details, timed_out = [], False
    try:
        for cmd in cmds:
            code, timed_out, seconds, tail = run_one(sh, cmd, p, end - time.monotonic())
            details.append({"cmd": cmd, "exit": code, "seconds": seconds, "tail": tail})
            if timed_out:
                break
    finally:
        ctx.git.run("reset", "-q", "--hard", "HEAD", cwd=p, check=False)
        ctx.git.run("clean", "-q", "-fd", cwd=p, check=False)
    details = cap_details(details)
    passed = all(d["exit"] == 0 for d in details) and not timed_out
    findings = []
    if not passed:
        bad = next(d for d in details if d["exit"] != 0)
        what = "timed out" if bad["exit"] == -1 else f"exited {bad['exit']}"
        findings = [{"key": "failed", "input": "code", "text": f"`{bad['cmd']}` {what}:\n{bad['tail'][-1024:]}"}]
    return Done({"result": {"passed": passed, "tree": T, "details": details}}, ok=passed, findings=findings,
                summary="passed" if passed else findings[0]["text"].splitlines()[0])
