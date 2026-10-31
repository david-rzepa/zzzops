"""The one Git runner (SPEC §4.1), startup checks (§1.5) and identities (§1.7)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

from engine.canon import git_date
from engine.errors import EngineError, Refused

MIN_GIT = (2, 41)
NETWORK = {"fetch", "push", "ls-remote"}
ID_ENV = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_ATTR_NOSYSTEM": "1"}


class GitError(Exception):
    def __init__(self, args, rc, stderr):
        super().__init__(f"git {' '.join(args)} failed ({rc}): {stderr.strip().splitlines()[0] if stderr.strip() else ''}")
        self.args_, self.rc, self.stderr = args, rc, stderr


def trace(entry: dict):
    path = os.environ.get("ZZZOPS_TRACE")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")


def base_env() -> dict:
    env = dict(os.environ)
    env.update({"LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_ASK_YESNO": "false"})
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"):
        env.pop(k, None)
    return env


class Git:
    """Runs `git -C <primary> -c maintenance.auto=false -c gc.auto=0 -c core.hooksPath=<empty> …`."""

    def __init__(self, primary: str | Path, common_dir: str | Path, now: int):
        self.primary = str(primary)
        self.common = str(common_dir)
        self.now = now
        self.hooks = os.path.join(self.common, "zzzops", "empty-hooks")
        self._identity = None
        self._batch = None

    # ------------------------------------------------------------------ discovery
    @classmethod
    def discover(cls, cwd: str | Path, now: int) -> "Git":
        env = base_env()
        p = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--git-common-dir"], capture_output=True, text=True, env=env)
        if p.returncode != 0:
            raise Refused("environment", "not inside a Git repository", details={"cwd": str(cwd)})
        common = Path(p.stdout.strip())
        if not common.is_absolute():
            common = (Path(cwd) / common).resolve()
        w = subprocess.run(["git", "-C", str(cwd), "worktree", "list", "--porcelain"], capture_output=True, text=True, env=env)
        primary = None
        for line in w.stdout.splitlines():
            if line.startswith("worktree "):
                primary = line[len("worktree "):]
                break
        if primary is None:
            raise Refused("environment", "cannot find the primary worktree")
        return cls(primary, common, now)

    # ------------------------------------------------------------------ running
    def run(self, *args, input=None, check=True, identity=False, hooks=False, commit=False, cwd=None, env=None,
            text=True, timeout=None):
        """Run one Git command. identity: the isolated configuration of SPEC §4.1; hooks: keep the repository's
        hooks (pushes with work or PR refs); commit: engine identity and dates."""
        cmd = ["git", "-C", cwd or self.primary, "-c", "maintenance.auto=false", "-c", "gc.auto=0"]
        if not hooks:
            try:
                os.makedirs(self.hooks, exist_ok=True)
            except OSError:
                pass                                       # a missing hooks directory disables hooks just as well
            cmd += ["-c", f"core.hooksPath={self.hooks}"]
        cmd += list(args)
        e = base_env()
        if identity:
            e.update(ID_ENV)
        if commit:
            name, email = self.identity()
            e.update({"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": name,
                      "GIT_COMMITTER_EMAIL": email, "GIT_AUTHOR_DATE": git_date(self.now),
                      "GIT_COMMITTER_DATE": git_date(self.now)})
        if env:
            e.update(env)
        if isinstance(input, str) and not text:
            input = input.encode("utf-8")
        start = time.monotonic()
        try:
            p = subprocess.run(cmd, input=input, capture_output=True, text=text, env=e, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise GitError(list(args), -1, f"timed out after {timeout} s") from exc
        verb = next((a for a in args if not a.startswith("-")), "")
        if verb in NETWORK:
            trace({"cmd": ["git", *args], "rc": p.returncode, "ms": int((time.monotonic() - start) * 1000)})
        if check and p.returncode != 0:
            err = p.stderr if text else p.stderr.decode("utf-8", "replace")
            raise GitError(list(args), p.returncode, err)
        return p

    def out(self, *args, **kw) -> str:
        return self.run(*args, **kw).stdout.strip()

    def identity(self) -> tuple:
        if self._identity is None:
            name = self.run("config", "user.name", check=False).stdout.strip() or "zzzops"
            email = self.run("config", "user.email", check=False).stdout.strip() or "zzzops@localhost"
            self._identity = (name, email)
        return self._identity

    def config(self, key: str) -> str | None:
        p = self.run("config", key, check=False)
        return p.stdout.strip() or None if p.returncode == 0 else None

    # ------------------------------------------------------------------ plumbing
    def rev_parse(self, rev: str) -> str | None:
        p = self.run("rev-parse", "--verify", "--quiet", rev + "^{object}", check=False)
        return p.stdout.strip() or None if p.returncode == 0 else None

    def is_ancestor(self, a: str, b: str) -> bool:
        if a == b:
            return True
        return self.run("merge-base", "--is-ancestor", a, b, check=False).returncode == 0

    def exists(self, oid: str) -> bool:
        return self.run("cat-file", "-e", oid, check=False).returncode == 0

    def hash_object(self, data: bytes) -> str:
        return self.run("hash-object", "-w", "--stdin", input=data, text=False).stdout.decode().strip()

    def commit_tree(self, tree: str, parents=(), message: str = "") -> str:
        args = ["commit-tree", tree]
        for p in parents:
            args += ["-p", p]
        return self.out(*args, "-F", "-", input=message, commit=True)

    def cat(self, spec: str) -> bytes | None:
        """One object through a persistent `cat-file --batch` (SPEC §4.1)."""
        if self._batch is None or self._batch.poll() is not None:
            self._batch = subprocess.Popen(["git", "-C", self.primary, "cat-file", "--batch"], stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE, env=base_env())
        b = self._batch
        b.stdin.write(spec.encode("utf-8") + b"\n")
        b.stdin.flush()
        header = b.stdout.readline().decode("utf-8", "replace").rstrip("\n")
        if header.endswith(" missing") or header.endswith(" ambiguous"):
            return None
        size = int(header.split()[2])
        data = b.stdout.read(size)
        b.stdout.read(1)
        return data

    def close(self):
        if self._batch is not None and self._batch.poll() is None:
            self._batch.stdin.close()
            self._batch.wait()
        self._batch = None


# --------------------------------------------------------------------------------------------- startup checks


def parse_version(text: str) -> tuple:
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not m:
        return (0, 0, 0)
    return tuple(int(x or 0) for x in m.groups())


def check_environment(git: Git, probe: bool = True) -> list:
    """The startup checks in order; returns a list of problems (empty when the environment is usable)."""
    problems = []
    v = subprocess.run(["git", "version"], capture_output=True, text=True, env=base_env())
    found = parse_version(v.stdout)
    if found[:2] < MIN_GIT:
        problems.append(f"Git {'.'.join(map(str, found))} is too old: ZzzOps needs Git >= 2.41 (see SETUP.md)")
        return problems
    fmt = git.run("rev-parse", "--show-object-format", check=False).stdout.strip()
    if fmt and fmt != "sha1":
        problems.append(f"object format {fmt}: ZzzOps supports SHA-1 repositories only")
    if git.run("rev-parse", "--is-shallow-repository", check=False).stdout.strip() == "true":
        problems.append("shallow clone: ancestry checks would give false answers; use a full clone")
    if os.environ.get("CODEX_SANDBOX_NETWORK_DISABLED") == "1":
        problems.append("Codex sandbox: network/Git-dir writes are blocked; see SETUP.md")
    elif probe:
        d = os.path.join(git.common, "zzzops")
        path = os.path.join(d, f"probe-{os.getpid()}")
        try:
            os.makedirs(d, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("probe")
            os.remove(path)
        except OSError as exc:
            problems.append(f"cannot write the Git directory ({exc.strerror}): network/Git-dir writes are blocked; see SETUP.md")
    return problems


def require_environment(git: Git):
    problems = check_environment(git)
    if problems:
        raise Refused("environment", problems[0], details={"problems": problems},
                      hint="fix the environment (see SETUP.md), then retry")


def engine_error(message: str):
    raise EngineError(message)
