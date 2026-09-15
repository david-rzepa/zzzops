"""Capability provenance comparison for explicit incremental re-bootstrap."""

from __future__ import annotations

from typing import Any


def _capability_map(record: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(record, dict):
        return {}
    capabilities = record.get("capabilities")
    if not isinstance(capabilities, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in capabilities:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        revision = item.get("revision")
        if isinstance(identifier, str) and identifier and isinstance(revision, str) and revision:
            result[identifier] = {
                "id": identifier,
                "revision": revision,
                "status": item.get("status", "verified"),
            }
    return result


def compare_bootstrap_capabilities(
    applied: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a stable, explainable delta without mutating either record.

    Only capability IDs, revisions, and applied status participate. Plugin version
    or unrelated metadata changes therefore remain a cheap no-op.
    """
    applied_map = _capability_map(applied)
    current_map = _capability_map(current)
    if not applied_map:
        return {"status": "legacy_provenance_missing", "added": sorted(current_map), "changed": [], "removed": []}

    added = sorted(set(current_map) - set(applied_map))
    changed = sorted(
        identifier for identifier in set(current_map) & set(applied_map)
        if current_map[identifier]["revision"] != applied_map[identifier]["revision"]
    )
    removed = sorted(set(applied_map) - set(current_map))
    partial = sorted(
        identifier for identifier in set(current_map) & set(applied_map)
        if applied_map[identifier].get("status") not in {"verified", "applied"}
    )
    status = "partially_applied" if partial else ("upgrade_available" if added or changed else "current")
    return {
        "status": status,
        "added": added,
        "changed": changed,
        "removed": removed,
        "partial": partial,
    }
