"""The `gh` wrapper (SPEC §5.6)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time

from engine.errors import Refused
from engine.gitrun import parse_version, trace

MIN_GH = (2, 40, 0)
TIMEOUT = 60


class GhError(Exception):
    def __init__(self, args, rc, stderr, transient):
        super().__init__(f"gh {' '.join(args)}: {stderr.strip().splitlines()[0] if stderr.strip() else rc}")
        self.args_, self.rc, self.stderr, self.transient = args, rc, stderr, transient


TRANSIENT = re.compile(r"(timed? ?out|timeout|connection|network|rate limit|HTTP 5\d\d|502|503|504|EOF|"
                       r"temporarily|could not resolve|TLS)", re.I)


def gh_repo(session) -> str | None:
    """SPEC §5.6: parsed from the remote's URL; an inherited GH_REPO is only a fallback."""
    url = session.git.config(f"remote.{session.R}.url") or ""
    m = re.match(r"^(?:https://|ssh://)?(?:git@)?[^/:]+[/:]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return os.environ.get("GH_REPO") or None


class Gh:
    def __init__(self, session):
        self.s = session
        self.repo = gh_repo(session)

    def env(self):
        e = dict(os.environ)
        e.update({"GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1", "NO_COLOR": "1"})
        if self.repo:
            e["GH_REPO"] = self.repo
        return e

    def run(self, *args, input=None, check=True) -> str:
        start = time.monotonic()
        try:
            p = subprocess.run(["gh", *args], input=input.encode("utf-8") if isinstance(input, str) else input,
                               capture_output=True, env=self.env(), timeout=TIMEOUT, cwd=self.s.git.primary)
            p.stdout = p.stdout.decode("utf-8", "replace")      # bytes on the pipes: no "\r\n" on Windows
            p.stderr = p.stderr.decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            trace({"cmd": ["gh", *args], "rc": -1, "ms": int((time.monotonic() - start) * 1000)})
            raise GhError(list(args), -1, "timed out", True)
        except FileNotFoundError:
            raise GhError(list(args), -1, "gh is not installed", False)
        trace({"cmd": ["gh", *args], "rc": p.returncode, "ms": int((time.monotonic() - start) * 1000)})
        if check and p.returncode != 0:
            raise GhError(list(args), p.returncode, p.stderr, bool(TRANSIENT.search(p.stderr or "")))
        return p.stdout

    def json(self, *args):
        out = self.run(*args)
        return json.loads(out) if out.strip() else None


def gh_problems(session) -> list:
    if shutil.which("gh") is None:
        return ["gh is not installed (needed by git.integrate and github.merge)"]
    v = subprocess.run(["gh", "--version"], capture_output=True, text=True)
    if parse_version(v.stdout) < MIN_GH:
        return [f"gh {'.'.join(map(str, parse_version(v.stdout)))} is too old: needs gh >= 2.40.0"]
    a = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, env=Gh(session).env())
    if a.returncode != 0:
        return ["gh is not authenticated: run `gh auth login`, or set GH_TOKEN"]
    return []


def require_gh(session):
    problems = gh_problems(session)
    if problems:
        raise Refused("environment", problems[0], hint="see SETUP.md")
