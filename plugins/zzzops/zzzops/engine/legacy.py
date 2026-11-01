"""Detection of pre-reset ZzzOps state and its disclosure as the `legacy` item (G1015).

Local signals are free and read on every `next` and `validate`. A check (one `ls-remote` plus at most one
`gh api graphql` search) runs only when the cache key changes or `retry_after` passes; its result is cached in
`<git-common>/zzzops/legacy.json`. The check never makes a verb fail."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from engine import ENGINE_VERSION
from engine.canon import canonical, iso, parse_iso

SKILL = "migrate-zzzops-repository"
SCHEMA = 1
HOUR = 3600
RETRY = 24 * HOUR                    # after a transient failure, and while the item is active
UNAVAILABLE_RETRY = 7 * 24 * HOUR    # after gh is missing or not authenticated
FILES_SHOWN = 10
NODES = 100

# The two GitHub searches; `{repo}` is `O/R`. The migrate skill runs exactly these strings (from `validate`).
QUERIES = {
    "labelled": "repo:{repo} is:issue is:open label:zzzops,zzzops:schema:v1,zzzops:schema:v2",
    "marked": 'repo:{repo} is:issue is:open "zzzops-goal" in:body -label:zzzops',
}
DOCUMENT = ("query($labelled:String!,$marked:String!){"
            "labelled: search(type:ISSUE, query:$labelled, first:100){issueCount nodes{... on Issue{number}}} "
            "marked: search(type:ISSUE, query:$marked, first:100){issueCount nodes{... on Issue{number}}}}")

OLD_FILES = (".zzzops/PROJECT_AUDIT.md", ".zzzops/BOOTSTRAP.json", ".zzzops/ZZZOPS_LOCK.json", ".zzzops/rules")
NEW_REF = re.compile(r"^refs/heads/zzzops/(?:(?:goal|work|pr|stack)/g\d+|lease/g\d+/.+|policy/.+)$")
AUTH = re.compile(r"gh auth login|HTTP 401|authentication", re.I)
REPO = re.compile(r"^(?:https://|ssh://)?(?:git@)?[^/:]+[/:]([^/]+)/([^/]+?)(?:\.git)?/?$")


def _cleanup_constants() -> tuple:
    """LEGACY_ROOTS and the two ignore-block markers of scripts/cleanup_legacy.py (one source of truth)."""
    path = Path(__file__).resolve().parents[2] / "scripts" / "cleanup_legacy.py"
    try:
        spec = importlib.util.spec_from_file_location("zzzops_cleanup_legacy", path)
        mod = sys.modules.get(spec.name)
        if mod is None:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod                       # dataclasses need the module registered
            spec.loader.exec_module(mod)
        return tuple(mod.LEGACY_ROOTS), mod.ROOT_IGNORE_START, mod.STATE_IGNORE_START
    except Exception:                                          # pragma: no cover - a damaged install
        return (), "# BEGIN ZZZOPS DISPOSABLE MACHINERY", "# BEGIN ZZZOPS LOCAL STATE"


# ------------------------------------------------------------------------------------------------ cache


def cache_key(engine_version: str, remote_url, signals) -> str:
    """sha256 of the canonical JSON of the engine version, the configured remote URL and the sorted local signals."""
    return hashlib.sha256(canonical({"engine": engine_version, "remote": remote_url or "",
                                     "signals": sorted(signals)})).hexdigest()


def cache_path(common: str) -> str:
    return os.path.join(common, "zzzops", "legacy.json")


def read_cache(common: str) -> dict | None:
    try:
        with open(cache_path(common), encoding="utf-8") as fh:
            c = json.load(fh)
    except (OSError, ValueError):
        return None
    return c if isinstance(c, dict) and c.get("schema") == SCHEMA else None


def write_cache(common: str, record: dict):
    """Atomic write of `<common>/zzzops/legacy.json`; best effort."""
    d = os.path.join(common, "zzzops")
    try:
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".legacy-", suffix=".json", dir=d)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, cache_path(common))
    except OSError:
        pass


# ------------------------------------------------------------------------------------------------ signals


def old_policy(raw) -> bool:
    """The pre-reset `.zzzops/POLICY.json`: schema_version 1, or no `settings` and an old top-level key."""
    if not isinstance(raw, dict):
        return False
    sv = raw.get("schema_version")
    if isinstance(sv, int) and not isinstance(sv, bool) and sv == 1:
        return True
    return "settings" not in raw and any(k in raw for k in ("approval", "backend", "bindings", "charter"))


def local_signals(session) -> tuple:
    """(policy, files): the old-format policy flag and the sorted names of old files, ignore blocks and install
    roots. Reads blobs at the policy commit through the persistent cat-file and the primary worktree only."""
    git, st = session.git, session.state
    roots, root_marker, state_marker = _cleanup_constants()
    files = set()
    P = session.snap.policy_commit if session.snap is not None else None
    if P:
        for path in OLD_FILES:
            if git.cat(f"{P}:{path}") is not None:
                files.add(path)
        for path, marker in ((".gitignore", root_marker), (".zzzops/.gitignore", state_marker)):
            data = git.cat(f"{P}:{path}")
            if data is not None and marker.encode("utf-8") in data:
                files.add(path)
    for r in roots:
        if os.path.exists(os.path.join(git.primary, r)):
            files.add(r)
    return old_policy(st.policy_raw if st is not None else None), sorted(files)


def repo_of(url) -> str | None:
    m = REPO.match(url or "")
    return f"{m.group(1)}/{m.group(2)}" if m else None


def ignored(session) -> bool:
    settings = session.state.settings if session.state is not None else None
    leg = (settings or {}).get("legacy")
    return isinstance(leg, dict) and leg.get("ignore") is True


# ------------------------------------------------------------------------------------------------ the check


def count_refs(session):
    """Legacy refs on the remote, by name only; (count, error)."""
    try:
        p = session.git.run("ls-remote", session.R, "refs/heads/zzzops/*", "refs/zzzops/*", check=False)
    except Exception as exc:                                   # a timeout
        return None, str(exc)
    if p.returncode != 0:
        return None, _first(p.stderr) or f"ls-remote exited {p.returncode}"
    n = 0
    for line in p.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and not NEW_REF.match(parts[1].strip()):
            n += 1
    return n, None


def search(session, repo: str, gh_ok: bool):
    """The GitHub signal: (github, result or None, error). result = (hits per alias, truncated)."""
    from engine.gh import Gh, GhError
    if not gh_ok or shutil.which("gh") is None:
        return "unavailable", None, "gh is not installed or not authenticated"
    q = {k: v.format(repo=repo) for k, v in QUERIES.items()}
    try:
        out = Gh(session).run("api", "graphql", "-f", f"query={DOCUMENT}",
                              "-f", f"labelled={q['labelled']}", "-f", f"marked={q['marked']}")
    except GhError as exc:
        err = _first(exc.stderr) or str(exc)
        if not exc.transient and AUTH.search(exc.stderr or ""):
            return "unavailable", None, err
        if exc.rc == -1 and "not installed" in (exc.stderr or ""):
            return "unavailable", None, err
        return "retry", None, err
    try:
        data = json.loads(out)["data"]
        hits = {}
        for alias in QUERIES:
            conn = data[alias]
            hits[alias] = (int(conn["issueCount"]),
                           [int(n["number"]) for n in conn["nodes"] if isinstance(n, dict) and "number" in n])
    except (ValueError, KeyError, TypeError) as exc:
        return "retry", None, f"unexpected graphql response: {exc}"
    return "ok", hits, None


def linked_issues(session) -> set:
    out = set()
    for doc in (session.state.docs or {}).values():
        n = ((doc or {}).get("links") or {}).get("issue")
        if isinstance(n, int) and not isinstance(n, bool):
            out.add(n)
    return out


def run_check(session, key: str, url, policy: bool, files: list, previous: dict | None, gh_ok: bool) -> dict:
    now = session.now
    rec = {"schema": SCHEMA, "key": key, "engine": ENGINE_VERSION, "checked_at": iso(now), "github": "none",
           "retry_after": None, "error": None, "issues": None, "issue_count": None, "linked": None, "refs": None}
    same = previous if previous and previous.get("key") == key else None
    refs, ref_err = count_refs(session)
    rec["refs"] = refs if refs is not None else (same or {}).get("refs")
    repo = repo_of(url)
    retry = None
    if repo is not None:
        github, hits, err = search(session, repo, gh_ok)
        rec["github"], rec["error"] = github, err
        if github == "ok":
            linked = linked_issues(session)
            found = set()
            total = 0
            for count, numbers in hits.values():
                found |= set(numbers)
                total += count
            truncated = any(count > len(numbers) for count, numbers in hits.values())
            sub = sorted(found & linked)
            issues = sorted(found - linked)
            rec["issues"], rec["linked"] = issues, sub
            rec["issue_count"] = max(total - len(sub), len(issues)) if truncated else len(issues)
        else:
            if same and same.get("issues") is not None:
                rec["issues"], rec["issue_count"], rec["linked"] = same["issues"], same["issue_count"], same.get("linked")
            retry = UNAVAILABLE_RETRY if github == "unavailable" else RETRY
    if ref_err:
        rec["error"] = rec["error"] or ref_err
        retry = min(retry or RETRY, RETRY)
    if retry is None and active(policy, files, rec["issue_count"]):
        retry = RETRY
    rec["retry_after"] = iso(now + retry) if retry else None
    return rec


def active(policy: bool, files: list, issue_count) -> bool:
    return bool(policy or files or (issue_count or 0) > 0)


# ------------------------------------------------------------------------------------------------ status


def status(session, mode: str = "cache", gh_ok: bool = True, full: bool = False) -> dict | None:
    """The `legacy` item or None. mode: "cache" (never checks), "check" (`next`: checks on a key change or after
    retry_after) or "force" (`validate`: always checks). `full` adds the counted set (validate)."""
    try:
        return _status(session, mode, gh_ok, full)
    except Exception:                                          # the legacy check never makes a verb fail
        return None


def _status(session, mode, gh_ok, full):
    if session.state is None or ignored(session):
        return None
    git = session.git
    policy, files = local_signals(session)
    url = git.config(f"remote.{session.R}.url") if session.R else None
    signals = list(files) + (["policy:old"] if policy else [])
    key = cache_key(ENGINE_VERSION, url, signals)
    cache = read_cache(git.common)
    can_check = (mode in ("check", "force") and session.snap is not None and session.snap.current
                 and not session.policy_ref)
    due = mode == "force" or cache is None or cache.get("key") != key or _passed(cache.get("retry_after"), session.now)
    if can_check and due:
        cache = run_check(session, key, url, policy, files, cache, gh_ok)
        write_cache(git.common, cache)
    rec = cache if cache is not None and cache.get("key") == key else None
    issue_count = rec.get("issue_count") if rec else None
    if not active(policy, files, issue_count):
        return None
    return item(session, rec, policy, files, issue_count, url, full)


def _passed(when, now) -> bool:
    if not when:
        return False
    try:
        return now >= parse_iso(when)
    except (TypeError, ValueError):
        return True


def item(session, rec, policy, files, issue_count, url, full) -> dict:
    from engine.session import cli_prefix
    refs = rec.get("refs") if rec else None
    parts = []
    if policy:
        parts.append("a pre-reset .zzzops/POLICY.json")
    if issue_count:
        parts.append(f"{issue_count} open goal issue{'s' if issue_count != 1 else ''}")
    if files:
        parts.append(f"{len(files)} old file{'s' if len(files) != 1 else ''}")
    if refs:
        parts.append(f"{refs} old ref{'s' if refs != 1 else ''} on {session.R}")
    if issue_count is None:
        parts.append("open goal issues not yet counted")
    out = {
        "message": "This repository still has pre-reset ZzzOps state: " + ", ".join(parts) + f". Migrate it with the "
                   f"{SKILL} skill; other work is not blocked.",
        "counts": {"issues": issue_count, "files": len(files), "refs": refs},
        "files": files[:FILES_SHOWN],
        "skill": SKILL,
        "recheck": f"{cli_prefix()} validate",
        "checked": ({"engine": rec.get("engine"), "at": rec.get("checked_at"), "github": rec.get("github")}
                    if rec else None),
        "dismiss": "set settings.legacy.ignore to true through a zzzops/policy/* branch",
    }
    if full:
        repo = repo_of(url)
        issues = rec.get("issues") if rec else None
        out["issues"] = issues
        out["linked"] = rec.get("linked") if rec else None
        out["queries"] = {k: v.format(repo=repo) for k, v in QUERIES.items()} if repo else {}
        out["truncated"] = bool(issues is not None and issue_count is not None and issue_count > len(issues))
    return out


def _first(text) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""
