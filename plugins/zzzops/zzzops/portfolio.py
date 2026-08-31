#!/usr/bin/env python3
"""Portfolio graph, audit, and snapshot mechanics."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable

PORTFOLIO_SCHEMA_VERSION = 2
AVAILABLE_WORK_STATES = {"triage", "prepare", "write"}
ENGINEERING_RIGOR_LEVELS = ("vibe", "structured", "agentic")
_exclusive_resources: Callable[[list[str], Any], list[str]] | None = None
_normalize_resource_policy: Callable[[Any], dict[str, Any]] | None = None
_text_present: Callable[[Any], bool] | None = None

def configure_entrypoint(*, exclusive_resources: Callable[[list[str], Any], list[str]], normalize_resource_policy: Callable[[Any], dict[str, Any]], text_present: Callable[[Any], bool]) -> None:
    global _exclusive_resources, _normalize_resource_policy, _text_present
    _exclusive_resources, _normalize_resource_policy, _text_present = exclusive_resources, normalize_resource_policy, text_present

def _require_configured() -> tuple[Callable[[list[str], Any], list[str]], Callable[[Any], dict[str, Any]], Callable[[Any], bool]]:
    if _exclusive_resources is None or _normalize_resource_policy is None or _text_present is None:
        raise RuntimeError("Portfolio module was not configured by the ZzzOps entry point")
    return _exclusive_resources, _normalize_resource_policy, _text_present

def _cycle_nodes(records: list[dict[str, Any]], relation: str) -> set[Any]:
    graph = {}
    for record in records:
        values = record.get(relation)
        graph[record["key"]] = ([values] if relation == "parent" and values is not None else values or [])
    state: dict[Any, int] = {}
    cycles: set[Any] = set()
    for start in graph:
        if state.get(start):
            continue
        path: list[Any] = [start]
        positions = {start: 0}
        state[start] = 1
        stack = [(start, iter(graph[start]))]
        while stack:
            node, targets = stack[-1]
            try:
                target = next(targets)
            except StopIteration:
                stack.pop()
                state[node] = 2
                positions.pop(node, None)
                path.pop()
                continue
            if target not in graph or state.get(target) == 2:
                continue
            if state.get(target) == 1:
                cycles.update(path[positions[target]:])
                continue
            state[target] = 1
            positions[target] = len(path)
            path.append(target)
            stack.append((target, iter(graph[target])))
    return cycles


def _portfolio_key(value: Any) -> tuple[int, Any]:
    return (0, value) if isinstance(value, int) and not isinstance(value, bool) else (1, str(value))


def derive_engineering_rigor(persisted: Any, policy: Any) -> dict[str, Any]:
    inputs = persisted if isinstance(persisted, dict) else {}
    raw_categories = inputs.get("risk_categories", [])
    categories = list(raw_categories) if isinstance(raw_categories, list) else []
    override = inputs.get("override") if isinstance(inputs.get("override"), dict) else None
    errors: list[str] = []
    if persisted is not None and not isinstance(persisted, dict):
        errors.append("metadata_invalid")
    elif isinstance(persisted, dict):
        if not isinstance(raw_categories, list):
            errors.append("risk_categories_invalid")
        if persisted.get("override") is not None and override is None:
            errors.append("override_invalid")
    projection = {
        "risk_categories": categories, "override": override, "effective": None,
        "valid": not errors, "errors": errors,
    }
    if not isinstance(policy, dict) or policy.get("decision") not in ENGINEERING_RIGOR_LEVELS:
        projection["provenance"] = {"status": "legacy_policy", "project_default": None, "matched_minimums": {}}
        return projection
    settings = policy.get("settings") if isinstance(policy.get("settings"), dict) else {}
    minimums = settings.get("minimums") if isinstance(settings.get("minimums"), dict) else {}
    overrides = settings.get("overrides") if isinstance(settings.get("overrides"), dict) else {}
    rank = {level: index for index, level in enumerate(ENGINEERING_RIGOR_LEVELS)}
    unknown_categories = sorted({category for category in categories if category not in minimums})
    if unknown_categories:
        errors.append("unknown_risk_categories")
    matched = {category: minimums[category] for category in categories if minimums.get(category) in rank}
    default = policy["decision"]
    risk_floor = max(matched.values(), key=rank.get) if matched else None
    floor = max((default, risk_floor), key=rank.get) if risk_floor else default
    effective = floor
    if override is not None and override.get("level") in rank:
        requested = override["level"]
        if overrides.get("per_goal") is not True:
            errors.append("per_goal_override_disabled")
        elif rank[requested] >= rank[floor]:
            if rank[requested] > rank[floor] and overrides.get("raising") != "allowed":
                errors.append("override_raising_disabled")
            else:
                effective = requested
        elif risk_floor is not None and rank[requested] < rank[risk_floor]:
            errors.append("override_below_risk_minimum")
        elif overrides.get("lowering") != "explicit_user_authority":
            errors.append("override_lowering_disabled")
        elif override.get("authority") != "explicit_user":
            errors.append("override_authority_required")
        else:
            effective = requested
    projection.update({
        "effective": effective, "valid": not errors, "errors": errors,
        "provenance": {
            "status": "derived", "project_default": default, "matched_minimums": matched,
            "unknown_risk_categories": unknown_categories,
            "rule": "reviewed_default_risk_minimum_and_authorized_override",
        },
    })
    return projection


def _review_ready_dependency(record: dict[str, Any]) -> bool:
    """Return whether a dependency has a reviewable checkpoint safe to stack on."""
    _, _, text_present = _require_configured()
    if record.get("status") != "blocked":
        return False
    blocker_categories = set(record.get("blocker_categories", []))
    if not blocker_categories or not blocker_categories <= {"human-action", "access-approval"}:
        return False
    implementation = record.get("implementation")
    if not isinstance(implementation, dict):
        return False
    review = implementation.get("review")
    return (
        text_present(implementation.get("branch"))
        and text_present(implementation.get("base"))
        and text_present(implementation.get("target"))
        and text_present(implementation.get("pr"))
        and isinstance(review, dict)
        and review.get("status") in {"pending", "approved"}
        and text_present(review.get("checkpoint"))
    )


def _pending_review_checkpoint(record: dict[str, Any]) -> bool:
    """Recognize a complete pending checkpoint even in a contradictory legacy lifecycle state."""
    _, _, text_present = _require_configured()
    implementation = record.get("implementation")
    if not isinstance(implementation, dict):
        return False
    review = implementation.get("review")
    return (
        all(text_present(implementation.get(field)) for field in ("branch", "base", "target", "pr"))
        and isinstance(review, dict)
        and review.get("status") == "pending"
        and text_present(review.get("checkpoint"))
    )


def _dependencies_allow_write(
    record: dict[str, Any], by_key: dict[Any, dict[str, Any]], git_policy: dict[str, Any],
) -> bool:
    dependencies = record.get("depends_on", [])
    unfinished = [
        by_key.get(dependency)
        for dependency in dependencies
        if by_key.get(dependency, {}).get("status") != "done"
    ]
    if not unfinished:
        return True
    if any(dependency is None or not _review_ready_dependency(dependency) for dependency in unfinished):
        return False
    if git_policy.get("review_pending_dependency") != "stack_from_reviewed_checkpoint":
        return False
    if len(unfinished) == 1:
        return git_policy.get("dependency_base") == "dependency_branch"
    return git_policy.get("multiple_dependency_base") == "reviewed_base_containing_all"


def _work_state(
    record: dict[str, Any], by_key: dict[Any, dict[str, Any]], git_policy: dict[str, Any],
) -> str:
    """Describe the safest useful work currently available for one goal."""
    status = record["status"]
    if status in {"done", "cancelled"}:
        return "terminal"
    if _pending_review_checkpoint(record):
        return "wait_human"
    if status == "blocked":
        return "wait_human" if record.get("needs_human") else "blocked"
    if status == "new":
        return "triage"
    if status == "triaged":
        return "prepare"
    if status in {"ready", "in_progress"}:
        return "write" if _dependencies_allow_write(record, by_key, git_policy) else "wait_dependency"
    return "blocked"


def audit_portfolio(
    records: list[dict[str, Any]], backend: str, as_of: datetime | None = None, resource_policy: Any = None,
) -> list[dict[str, Any]]:
    exclusive_resources, _, text_present = _require_configured()
    as_of = datetime.now(timezone.utc) if as_of is None else as_of
    findings: list[dict[str, Any]] = []
    grouped: dict[Any, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["key"], []).append(record)
    for key, matches in grouped.items():
        if len(matches) > 1:
            findings.append({"code": "duplicate_identity", "goal": key, "detail": f"{len(matches)} records"})
    goals = {key: matches[0] for key, matches in grouped.items()}
    live_resources: dict[str, list[Any]] = {}
    for record in records:
        claim = record.get("claim")
        if isinstance(claim, dict) and claim.get("owner"):
            for resource in exclusive_resources(record.get("resources", []), resource_policy):
                live_resources.setdefault(resource, []).append(record["key"])
    for resource, owners in live_resources.items():
        if len(owners) > 1:
            findings.append({"code": "resource_collision", "goal": owners[0], "detail": f"{resource}: {','.join(map(str, owners))}"})
    for record in records:
        key = record["key"]
        relations = ([record["parent"]] if record.get("parent") is not None else []) + list(record.get("depends_on", []))
        if len(record.get("depends_on", [])) != len(set(record.get("depends_on", []))):
            findings.append({"code": "duplicate_dependency", "goal": key, "detail": "dependency repeated"})
        for target in relations:
            if target == key:
                findings.append({"code": "self_relation", "goal": key, "detail": str(target)})
            elif target not in goals:
                findings.append({"code": "missing_relation", "goal": key, "detail": str(target)})
        if record["status"] == "done":
            unfinished = [str(target) for target in record.get("depends_on", []) if target in goals and goals[target]["status"] != "done"]
            if unfinished:
                findings.append({"code": "done_with_unfinished_dependency", "goal": key, "detail": ",".join(unfinished)})
        cancelled = [str(target) for target in record.get("depends_on", []) if target in goals and goals[target]["status"] == "cancelled"]
        if cancelled:
            findings.append({"code": "cancelled_dependency", "goal": key, "detail": ",".join(cancelled)})
        claim = record.get("claim")
        if isinstance(claim, dict) and claim.get("owner") and claim.get("expires_at"):
            try:
                expires = datetime.fromisoformat(str(claim["expires_at"]).replace("Z", "+00:00"))
                if expires.tzinfo is None:
                    raise ValueError("timezone missing")
                if expires < as_of:
                    findings.append({"code": "stale_claim", "goal": key, "detail": str(claim["expires_at"])})
            except ValueError:
                findings.append({"code": "invalid_claim_expiry", "goal": key, "detail": str(claim["expires_at"])})
        review = (record.get("implementation") or {}).get("review") if isinstance(record.get("implementation"), dict) else None
        if isinstance(review, dict) and review.get("status") == "pending" and not review.get("checkpoint"):
            findings.append({"code": "pending_review_without_checkpoint", "goal": key, "detail": "checkpoint missing"})
        if backend == "github_issues":
            if isinstance(review, dict) and review.get("status") == "approved" and not (record.get("implementation") or {}).get("pr"):
                findings.append({"code": "approved_review_without_pr", "goal": key, "detail": "PR missing"})
            expected = {"zzzops", f"zzzops:status:{record['status']}", f"zzzops:priority:{record['priority']}"}
            actual = set(record.get("labels", []))
            drift = sorted(expected - actual)
            stale = sorted(label for label in actual if (label.startswith("zzzops:status:") or label.startswith("zzzops:priority:")) and label not in expected)
            if drift or stale:
                findings.append({"code": "label_drift", "goal": key, "detail": f"missing={drift}; stale={stale}"})
            terminal = record["status"] in {"done", "cancelled"}
            if terminal != (record.get("state") == "closed"):
                findings.append({"code": "issue_state_drift", "goal": key, "detail": f"goal={record['status']}; issue={record.get('state')}"})
        rigor = record.get("engineering_rigor")
        if isinstance(rigor, dict):
            for error in rigor.get("errors", []):
                detail = error
                if error == "unknown_risk_categories":
                    unknown = rigor.get("provenance", {}).get("unknown_risk_categories", [])
                    detail = "unknown risk categories: " + ", ".join(unknown)
                findings.append({"code": f"engineering_rigor_{error}", "goal": key, "detail": detail})
    for relation in ("depends_on", "parent"):
        for key in sorted(_cycle_nodes(records, relation), key=_portfolio_key):
            findings.append({"code": f"{relation}_cycle", "goal": key, "detail": "cycle member"})
    return sorted(findings, key=lambda finding: (finding["code"], str(finding["goal"]), finding["detail"]))


def build_portfolio_snapshot(
    backend: str, records: list[dict[str, Any]], *, reads: int, raw_bytes: int,
    ignored: int = 0, as_of: datetime | None = None, git_policy: dict[str, Any] | None = None,
    resource_policy: Any = None, rigor_policy: Any = None,
) -> dict[str, Any]:
    _, normalize_resource_policy, _ = _require_configured()
    for record in records:
        record["children"] = []
        record["blocks"] = []
    by_key = {record["key"]: record for record in records}
    for record in records:
        if record.get("parent") in by_key:
            by_key[record["parent"]]["children"].append(record["key"])
        for dependency in record.get("depends_on", []):
            if dependency in by_key:
                by_key[dependency]["blocks"].append(record["key"])
    for record in records:
        record["children"].sort(key=_portfolio_key)
        record["blocks"].sort(key=_portfolio_key)
        record["engineering_rigor"] = derive_engineering_rigor(record.get("engineering_rigor"), rigor_policy)
    resource_policy = normalize_resource_policy(resource_policy) if resource_policy is not None else None
    findings = audit_portfolio(records, backend, as_of, resource_policy)
    terminal = {"done", "cancelled"}
    terminal_keys = {record["key"] for record in records if record["status"] in terminal}
    git_policy = git_policy or {}
    for record in records:
        record["work_state"] = _work_state(record, by_key, git_policy)
    available = [record["key"] for record in records if record["work_state"] in AVAILABLE_WORK_STATES]
    writable = [record["key"] for record in records if record["work_state"] == "write"]
    waiting = [record["key"] for record in records if record["work_state"] == "wait_dependency"]
    blocked = [record["key"] for record in records if record["work_state"] in {"wait_human", "blocked"}]
    portfolio_digest = hashlib.sha256(
        (
            "git_policy:" + json.dumps(git_policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            + "resource_policy:" + json.dumps(resource_policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            + "rigor_policy:" + json.dumps(rigor_policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            + "\n".join(
                f"{record['key']}:{record['revision']}:{record['digest']}"
                for record in sorted(records, key=lambda item: _portfolio_key(item["key"]))
            )
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": PORTFOLIO_SCHEMA_VERSION, "backend": backend, "complete": True,
        "valid": not findings,
        "portfolio_digest": portfolio_digest, "goals": sorted(records, key=lambda record: _portfolio_key(record["key"])),
        "findings": findings, "summary": {
            "total": len(records), "available": len(available), "writable": len(writable),
            "waiting": len(waiting), "blocked": len(blocked),
            "done": len(terminal_keys), "findings": len(findings), "reads": reads,
            "raw_bytes": raw_bytes, "ignored": ignored,
        },
    }


def compact_portfolio_output(snapshot: dict[str, Any]) -> dict[str, Any]:
    terminal_fields = ("key", "title", "status", "schema_version")
    goals = []
    archived = 0
    for goal in snapshot["goals"]:
        if goal["status"] in {"done", "cancelled"}:
            goals.append({"archived": True, **{field: goal.get(field) for field in terminal_fields}})
            archived += 1
        else:
            goals.append(goal)
    return {**snapshot, "goals": goals, "summary": {**snapshot["summary"], "archived": archived}}

