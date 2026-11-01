"""Canonical JSON, hashing and time (SPEC §1.3, §1.4, §2.4)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone

MAX_INT = 2 ** 53 - 1
ZERO = "0" * 40
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def H(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def goal_bytes(doc: dict) -> bytes:
    return (json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def find_floats(value, path="$"):
    """Paths of floats (and out-of-range integers) anywhere in a JSON value."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return []
    if isinstance(value, float):
        return [path]
    if isinstance(value, int):
        return [] if abs(value) <= MAX_INT else [path]
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in find_floats(v, f"{path}.{k}")]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in find_floats(v, f"{path}[{i}]")]
    return [path]


def read_now() -> int:
    raw = os.environ.get("ZZZOPS_NOW")
    return int(raw) if raw not in (None, "") else int(time.time())


def iso(seconds: int) -> str:
    return datetime.fromtimestamp(int(seconds), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: str) -> int:
    return int(datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())


def git_date(seconds: int) -> str:
    return f"@{int(seconds)} +0000"


def version_tuple(text: str) -> tuple:
    parts = text.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"not a MAJOR.MINOR.PATCH version: {text!r}")
    return tuple(int(p) for p in parts)
