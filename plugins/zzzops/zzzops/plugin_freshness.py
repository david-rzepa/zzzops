"""Read-only inventories and freshness evidence for installed agent plugins."""

from __future__ import annotations

import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CHECK_INTERVAL_SECONDS = 24 * 60 * 60


def _cache_path() -> Path:
    """Return the per-user derived cache path without creating or modifying it."""
    system = platform.system()
    if system == "Windows":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif system == "Darwin":
        root = Path.home() / "Library" / "Caches"
    else:
        root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "zzzops" / "plugin-freshness.json"


def _run_json(command: list[str], timeout: int = 8) -> tuple[Any | None, str | None]:
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        return None, type(exc).__name__
    if completed.returncode != 0:
        return None, f"exit:{completed.returncode}"
    try:
        return json.loads(completed.stdout), None
    except (UnicodeError, json.JSONDecodeError):
        return None, "invalid_json"


def _inventory(agent: str, command: list[str]) -> dict[str, Any]:
    payload, error = _run_json(command)
    result: dict[str, Any] = {
        "agent": agent, "available": True, "ok": error is None,
        "error": error, "plugins": [], "source": "native_inventory",
    }
    if error is not None:
        return result
    entries = payload.get("installed") if agent == "codex" and isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        result["ok"] = False
        result["error"] = "installed_inventory_missing"
        return result
    for entry in entries:
        if not isinstance(entry, dict):
            result["ok"] = False
            result["error"] = "malformed_plugin_entry"
            result["plugins"] = []
            return result
        identity = entry.get("pluginId") or entry.get("name")
        if not isinstance(identity, str) or not identity:
            result["ok"] = False
            result["error"] = "plugin_identity_missing"
            result["plugins"] = []
            return result
        result["plugins"].append({
            "id": identity,
            "version": entry.get("version"),
            "source": entry.get("source") or entry.get("marketplace") or entry.get("marketplaceName"),
            "enabled": entry.get("enabled"),
            "scope": entry.get("scope") or entry.get("installScope"),
        })
    return result


def native_plugin_inventory() -> dict[str, Any]:
    """Read supported native installed-plugin inventories; never install or refresh."""
    checked_at = datetime.now(timezone.utc).isoformat()
    return {
        "checked_at": checked_at,
        "cache_path": str(_cache_path()),
        "agents": {
            "codex": _inventory("codex", ["codex", "plugin", "list", "--json"]),
            "claude": _inventory("claude", ["claude", "plugin", "list", "--json"]),
        },
    }


def freshness_due(cache: dict[str, Any] | None, now: datetime | None = None) -> bool:
    """Whether the last successful check is absent or at least one day old."""
    if not isinstance(cache, dict) or cache.get("status") != "ok":
        return True
    checked = cache.get("checked_at")
    if not isinstance(checked, str):
        return True
    try:
        timestamp = datetime.fromisoformat(checked.replace("Z", "+00:00"))
    except ValueError:
        return True
    current = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return (current - timestamp).total_seconds() >= CHECK_INTERVAL_SECONDS
