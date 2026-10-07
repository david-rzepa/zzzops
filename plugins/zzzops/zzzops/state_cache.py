"""Private derived materialized comment state; never mutation authority."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile

SCHEMA_VERSION = 1
REDUCER_VERSION = "artifact-index-v1"


def _root() -> Path:
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "zzzops" / "materialized-state"


def _path(repository: str, goal: int, issue_body_hash: str) -> Path:
    identity = json.dumps([repository, goal, issue_body_hash], separators=(",", ":"))
    return _root() / (hashlib.sha256(identity.encode()).hexdigest() + ".json")


def head(comments: list[dict]) -> list[dict] | None:
    result, identities = [], []
    if not isinstance(comments, list): return None
    for row in comments:
        if not isinstance(row, dict): return None
        identity, body = row.get("id"), row.get("body")
        if type(identity) is not int or identity <= 0 or not isinstance(body, str): return None
        identities.append(identity)
        result.append({"id": identity,
                       "body_hash": "sha256:" + hashlib.sha256(body.encode()).hexdigest()})
    return result if identities == sorted(set(identities)) else None


def classify_head(cached: list[dict], observed: list[dict]) -> str:
    current = head(observed)
    if current is None or not isinstance(cached, list) or not cached: return "invalid"
    if current == cached: return "exact"
    old = {row.get("id"): row for row in cached if isinstance(row, dict)}
    overlap = [row for row in current if row["id"] in old]
    last = cached[-1].get("id", 0)
    if (overlap and all(old[row["id"]] == row for row in overlap)
            and current[-1]["id"] > last
            and all(row["id"] > last for row in current[len(overlap):])):
        return "append"
    return "changed"


def load(repository: str, goal: int, issue_body_hash: str) -> dict | None:
    try:
        document = json.loads(_path(repository, goal, issue_body_hash).read_text(encoding="utf-8"))
        if (not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION
                or document.get("reducer_version") != REDUCER_VERSION
                or document.get("repository") != repository or document.get("goal") != goal
                or document.get("issue_body_hash") != issue_body_hash
                or head(document.get("materialized_comments")) is None
                or not isinstance(document.get("provider_head"), list)):
            return None
        return document
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError): return None


def requires_full_read(repository: str, goal: int, issue_body_hash: str) -> bool:
    """Whether prior derived storage exists but cannot match this observation."""
    root = _root()
    try:
        paths = list(root.glob("*.json"))
    except OSError:
        return False
    for path in paths:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return True
        if (isinstance(document, dict) and document.get("repository") == repository
                and document.get("goal") == goal):
            if (document.get("issue_body_hash") != issue_body_hash
                    or document.get("schema_version") != SCHEMA_VERSION
                    or document.get("reducer_version") != REDUCER_VERSION):
                return True
    return False


def store(repository: str, goal: int, issue_body_hash: str,
          provider_comments: list[dict], materialized_comments: list[dict]) -> None:
    observed = head(provider_comments)
    if observed is None or head(materialized_comments) is None: return
    document = {"schema_version": SCHEMA_VERSION, "reducer_version": REDUCER_VERSION,
                "repository": repository, "goal": goal, "issue_body_hash": issue_body_hash,
                "provider_head": observed, "materialized_comments": materialized_comments}
    path = _path(repository, goal, issue_body_hash)
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(document, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                stream.flush(); os.fsync(stream.fileno())
            os.chmod(temporary, 0o600); os.replace(temporary, path)
            entries = sorted(path.parent.glob("*.json"), key=lambda item: item.stat().st_mtime,
                             reverse=True)
            for expired in entries[64:]:
                try: expired.unlink()
                except OSError: pass
        finally:
            try: os.unlink(temporary)
            except FileNotFoundError: pass
    except OSError: return
