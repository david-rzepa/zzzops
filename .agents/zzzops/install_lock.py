#!/usr/bin/env python3
"""Validate the committed lock for disposable ZzzOps machinery."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

LOCK_RELATIVE = ".zzzops/ZZZOPS_LOCK.json"
LOCK_SCHEMA_VERSION = 1
_REVISION = re.compile(r"^[0-9a-f]{40,64}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_PATH_PART = re.compile(r"^[A-Za-z0-9._-]+$")
_SKILLS = {
    "add-zzzops-goal", "execute-zzzops", "migrate-to-zzzops",
    "review-zzzops-policy", "send-zzzops-feedback", "suggest-zzzops-work",
}
_ROOTS = (
    ".agents/zzzops",
    *(f".agents/skills/{name}" for name in sorted(_SKILLS)),
    *(f".claude/skills/{name}" for name in sorted(_SKILLS)),
    ".zzzops/rules",
)


class InstallLockError(ValueError):
    """The committed installation lock cannot safely identify machinery."""


def _safe_relative(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise InstallLockError("managed paths must be non-empty normalized POSIX paths")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(part in {"", ".", ".."} for part in path.parts):
        raise InstallLockError(f"unsafe managed path: {value}")
    if any(not _PATH_PART.fullmatch(part) for part in path.parts):
        raise InstallLockError(f"managed path is not portable: {value}")
    if value == LOCK_RELATIVE or not any(value.startswith(root + "/") for root in _ROOTS):
        raise InstallLockError(f"path is outside disposable machinery roots: {value}")
    return value


def validate_install_lock(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or set(data) != {"schema_version", "revision", "version", "files"}:
        raise InstallLockError("installation lock must contain only schema_version, revision, version, and files")
    if data.get("schema_version") != LOCK_SCHEMA_VERSION:
        raise InstallLockError(f"installation lock schema_version must be {LOCK_SCHEMA_VERSION}")
    if not isinstance(data.get("revision"), str) or not _REVISION.fullmatch(data["revision"]):
        raise InstallLockError("installation lock revision is invalid")
    if not isinstance(data.get("version"), str) or not _VERSION.fullmatch(data["version"]):
        raise InstallLockError("installation lock version is invalid")
    files = data.get("files")
    if not isinstance(files, dict) or not files:
        raise InstallLockError("installation lock files must be a non-empty object")
    normalized: dict[str, str] = {}
    portable_paths: set[str] = set()
    for raw_path, digest in files.items():
        path = _safe_relative(raw_path)
        portable = path.casefold()
        if portable in portable_paths:
            raise InstallLockError(f"duplicate cross-platform managed path: {path}")
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            raise InstallLockError(f"invalid SHA-256 digest for {path}")
        portable_paths.add(portable)
        normalized[path] = digest
    return {
        "schema_version": LOCK_SCHEMA_VERSION,
        "revision": data["revision"],
        "version": data["version"],
        "files": dict(sorted(normalized.items())),
    }


def parse_install_lock_bytes(data: bytes) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise InstallLockError(f"duplicate installation lock key: {key}")
            result[key] = value
        return result
    try:
        parsed = json.loads(data.decode("utf-8-sig"), object_pairs_hook=reject_duplicates)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InstallLockError(f"could not read committed installation lock: {type(exc).__name__}") from exc
    return validate_install_lock(parsed)


def read_install_lock_snapshot(repo: Path) -> tuple[dict[str, Any], bytes]:
    path = repo / LOCK_RELATIVE
    try:
        if path.is_symlink():
            raise InstallLockError(f"committed installation lock must not be a symlink: {LOCK_RELATIVE}")
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise InstallLockError(f"missing committed installation lock: {LOCK_RELATIVE}") from exc
    except OSError as exc:
        raise InstallLockError(f"could not read committed installation lock: {type(exc).__name__}") from exc
    return parse_install_lock_bytes(data), data


def read_install_lock(repo: Path) -> dict[str, Any]:
    return read_install_lock_snapshot(repo)[0]


def file_digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.lower() in {".json", ".md", ".py", ".yaml", ".yml"} or path.name == "ZZZOPS_GITIGNORE":
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def build_install_lock(repo: Path, revision: str, version: str) -> dict[str, Any]:
    """Build deterministic lock data from the machinery materialized in repo."""
    files = {relative: file_digest(repo / relative) for relative in sorted(_installed_files(repo))}
    return validate_install_lock({
        "schema_version": LOCK_SCHEMA_VERSION,
        "revision": revision,
        "version": version,
        "files": files,
    })


def _unsafe_or_missing(repo: Path, relative: str) -> bool:
    current = repo
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            return True
    return not current.is_file()


def _installed_files(repo: Path) -> set[str]:
    installed: set[str] = set()
    for root in _ROOTS:
        directory = repo / root
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            installed.add(root)
            continue
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            relative = path.relative_to(repo).as_posix()
            if path.is_symlink():
                installed.add(relative)
                continue
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            installed.add(relative)
    return installed


def installation_lock_status(repo: Path) -> dict[str, Any]:
    """Report whether local disposable machinery exactly matches its lock."""
    try:
        lock = read_install_lock(repo)
    except InstallLockError as exc:
        return {
            "available": True, "ok": False, "paths": [LOCK_RELATIVE], "processes": 0,
            "detail": f"{exc}; rerun the regular ZzzOps installer.",
        }
    expected = set(lock["files"])
    changed = set(_installed_files(repo) - expected)
    for relative, digest in lock["files"].items():
        path = repo / relative
        try:
            mismatch = _unsafe_or_missing(repo, relative) or file_digest(path) != digest
        except OSError:
            mismatch = True
        if mismatch:
            changed.add(relative)
    paths = sorted(changed)
    return {
        "available": True,
        "ok": not paths,
        "paths": paths,
        "processes": 0,
        "detail": "ok" if not paths else "Disposable ZzzOps machinery does not match the committed lock; rerun the regular installer.",
    }
