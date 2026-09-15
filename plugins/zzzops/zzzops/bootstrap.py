"""Capability provenance comparison for explicit incremental re-bootstrap."""

from __future__ import annotations

import hashlib
import json
from typing import Any


BOOTSTRAP_STATE_RELATIVE = ".zzzops/BOOTSTRAP.json"


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


def create_review_checkpoint(
    root_goal_id: int,
    harness_goal_ids: list[int],
    tooling: dict[str, Any] | None,
    product_milestone: dict[str, Any],
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or reuse the post-harness product-review checkpoint.

    The checkpoint is deliberately derived from stable goal/tooling inputs, so
    repeated bootstrap invocations reuse it and cannot duplicate product goals.
    No product goal is created by this function.
    """
    if isinstance(existing, dict) and existing.get("checkpoint_id"):
        return dict(existing)
    payload = {
        "root_goal_id": root_goal_id,
        "harness_goal_ids": sorted(set(harness_goal_ids)),
        "tooling": tooling if isinstance(tooling, dict) else {"selected": False, "candidates": []},
        "product_milestone": product_milestone,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    checkpoint_id = hashlib.sha256(encoded).hexdigest()[:16]
    return {
        "schema_version": 1,
        "checkpoint_id": checkpoint_id,
        "status": "awaiting_product_review",
        "product_goals_created": False,
        **payload,
    }


def record_review_decision(
    checkpoint: dict[str, Any], decision: str, checkpoint_id: str,
) -> dict[str, Any]:
    """Record an approval or deferral exactly once against a checkpoint."""
    if not isinstance(checkpoint, dict) or checkpoint.get("checkpoint_id") != checkpoint_id:
        raise ValueError("checkpoint id does not match")
    if decision not in {"approved", "deferred"}:
        raise ValueError("decision must be approved or deferred")
    result = dict(checkpoint)
    current = result.get("status")
    if current in {"approved", "deferred"}:
        if current != decision:
            raise ValueError("checkpoint already has a different decision")
        return result
    if current != "awaiting_product_review":
        raise ValueError("checkpoint is not awaiting product review")
    result["status"] = decision
    result["decision_checkpoint_id"] = checkpoint_id
    return result
