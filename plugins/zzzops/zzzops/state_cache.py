"""Private derived materialized comment state; never mutation authority."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import platform
import stat
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


def _private_root(*, create: bool) -> Path | None:
    root = _root()
    try:
        if create:
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not root.is_dir() or root.is_symlink(): return None
        os.chmod(root, 0o700)
        if stat.S_IMODE(root.stat().st_mode) != 0o700: return None
        return root
    except OSError:
        return None


def head(comments: list[dict]) -> list[dict] | None:
    result, identities = [], []
    if not isinstance(comments, list): return None
    for row in comments:
        if not isinstance(row, dict): return None
        identity, body = row.get("id"), row.get("body")
        if type(identity) is not int or identity <= 0 or not isinstance(body, str): return None
        identities.append(identity)
        item = {"id": identity,
                "body_hash": "sha256:" + hashlib.sha256(body.encode()).hexdigest()}
        marker = row.get("updated_at") or row.get("created_at")
        if isinstance(marker, str) and marker: item["updated_at"] = marker
        result.append(item)
    return result if identities == sorted(set(identities)) else None


def classify_head(cached: list[dict], observed: list[dict]) -> tuple[str, list[dict]]:
    current = head(observed)
    if current is None or not isinstance(cached, list) or not cached: return "invalid", []
    core = lambda row: (row.get("id"), row.get("body_hash"))
    if [core(row) for row in current] == [core(row) for row in cached]: return "exact", []
    old = {row.get("id"): row for row in cached if isinstance(row, dict)}
    overlap = [row for row in current if row["id"] in old]
    last = cached[-1].get("id", 0)
    suffix = [row for row in observed if row.get("id", 0) > last]
    identities = [row["id"] for row in current]
    overlap_ids = [row["id"] for row in overlap]
    expected_overlap = [row["id"] for row in cached if row.get("id") in set(identities)]
    if (overlap and overlap_ids == expected_overlap
            and all(core(old[row["id"]]) == core(row) for row in overlap)
            and current[-1]["id"] > last and suffix
            and [row["id"] for row in suffix] == sorted({row["id"] for row in suffix})):
        return "append", suffix
    return "changed", []


def load(repository: str, goal: int, issue_body_hash: str, contract: dict) -> dict | None:
    try:
        root = _private_root(create=False)
        path = _path(repository, goal, issue_body_hash)
        if root is None or path.is_symlink(): return None
        document = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION
                or document.get("reducer_version") != REDUCER_VERSION
                or document.get("repository") != repository or document.get("goal") != goal
                or document.get("issue_body_hash") != issue_body_hash
                or document.get("artifact_contract") != contract
                or not isinstance(document.get("last_complete_audit"), (int, float))
                or isinstance(document.get("last_complete_audit"), bool)
                or not math.isfinite(document["last_complete_audit"])
                or document["last_complete_audit"] <= 0
                or head(document.get("materialized_comments")) is None
                or not isinstance(document.get("provider_head"), list)):
            return None
        return document
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError): return None


def requires_full_read(repository: str, goal: int, issue_body_hash: str, contract: dict) -> bool:
    """Whether prior derived storage exists but cannot match this observation."""
    root = _private_root(create=False)
    if root is None: return False
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
                    or document.get("reducer_version") != REDUCER_VERSION
                    or document.get("artifact_contract") != contract
                    or not isinstance(document.get("last_complete_audit"), (int, float))
                    or isinstance(document.get("last_complete_audit"), bool)
                    or not math.isfinite(document["last_complete_audit"])
                    or document["last_complete_audit"] <= 0):
                return True
    return False


def store(repository: str, goal: int, issue_body_hash: str,
          provider_comments: list[dict], materialized_comments: list[dict], contract: dict,
          last_complete_audit: float | None) -> None:
    # Bind the same compact suffix shape used by the provider head endpoint.
    # Older history is periodically re-audited through last_complete_audit.
    observed = head(provider_comments[-100:])
    if (observed is None or head(materialized_comments) is None
            or not isinstance(last_complete_audit, (int, float))
            or isinstance(last_complete_audit, bool) or not math.isfinite(last_complete_audit)
            or last_complete_audit <= 0): return
    document = {"schema_version": SCHEMA_VERSION, "reducer_version": REDUCER_VERSION,
                "repository": repository, "goal": goal, "issue_body_hash": issue_body_hash,
                "artifact_contract": contract,
                "last_complete_audit": last_complete_audit,
                "provider_head": observed, "materialized_comments": materialized_comments}
    path = _path(repository, goal, issue_body_hash)
    try:
        if _private_root(create=True) is None: return
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
