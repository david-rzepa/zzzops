#!/usr/bin/env python3
"""Managed-goal parsing, validation, rendering, and record projection."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any, Callable

GOAL_SCHEMA_VERSION = 1
GOAL_BLOCK_START = "<!-- zzzops-goal"
GOAL_BLOCK_END = "zzzops-goal -->"
GOAL_HISTORY_BLOCK_START = "<!-- zzzops-history"
GOAL_HISTORY_BLOCK_END = "zzzops-history -->"
GOAL_HISTORY_SCHEMA_VERSION = 1
GOAL_SCHEMA_LABEL_PREFIX = "zzzops:schema:v"
GOAL_FIELDS = {
    "schema_version", "status", "priority", "value", "difficulty", "confidence",
    "parent", "depends_on", "claim", "blockers", "evidence", "next_action",
    "revision", "implementation", "resources", "engineering_rigor",
}
GOAL_STATUSES = {"new", "triaged", "ready", "in_progress", "blocked", "done", "cancelled"}
GOAL_PRIORITIES = {"P0", "P1", "P2", "P3"}
GOAL_VALUES = {"critical", "high", "medium", "low"}
GOAL_DIFFICULTIES = {"unknown", "XS", "S", "M", "L", "XL"}
GOAL_CONFIDENCES = {"low", "medium", "high"}
ENGINEERING_RIGOR_LEVELS = {"vibe", "structured", "agentic"}
ENGINEERING_RIGOR_OVERRIDE_AUTHORITIES = {"explicit_user", "goal_requirement"}
GOAL_TRANSITION_SCHEMA_VERSION = 1
GOAL_TRANSITION_FIELDS = {"schema_version", "expected_revision", "expected_digest", "goal"}
GOAL_CREATE_SCHEMA_VERSION = 1
GOAL_CREATE_FIELDS = {"schema_version", "title", "body", "labels", "goal"}
BLOCKER_CATEGORIES = {"specification", "decision", "access-approval", "human-action", "external-dependency", "technical-unknown", "safety-compliance"}
REDUNDANT_GOAL_TITLE_PREFIX = re.compile(r"^\[G-\d{8}-\d{3}-[^\]]+\]\s*")
HISTORICAL_HUMAN_SECTIONS = {
    "completed evidence", "evidence", "history", "implementation history",
    "prior checkpoints", "resolved blockers", "superseded requirements",
}
_normalize_resources: Callable[[Any], list[str]] | None = None
_text_present: Callable[[Any], bool] | None = None


class GoalTransitionProviderError(ValueError):
    """The provider did not produce a safe, confirmed goal-operation result."""

def configure_entrypoint(*, normalize_resources: Callable[[Any], list[str]], text_present: Callable[[Any], bool]) -> None:
    global _normalize_resources, _text_present
    _normalize_resources, _text_present = normalize_resources, text_present

def _require_configured() -> tuple[Callable[[Any], list[str]], Callable[[Any], bool]]:
    if _normalize_resources is None or _text_present is None:
        raise RuntimeError("Managed-goal module was not configured by the ZzzOps entry point")
    return _normalize_resources, _text_present

def parse_managed_goal(text: str, issue_number: int | None = None) -> dict[str, Any] | None:
    pattern = re.compile(
        re.escape(GOAL_BLOCK_START) + r"\s*\n(.*?)\n" + re.escape(GOAL_BLOCK_END),
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None
    try:
        goal = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid managed goal JSON: {exc}") from exc
    errors = validate_managed_goal(goal, issue_number)
    if errors:
        raise ValueError("Invalid managed goal: " + "; ".join(errors))
    return goal


def validate_managed_goal(goal: Any, issue_number: int | None = None) -> list[str]:
    if not isinstance(goal, dict):
        return ["managed goal must be an object"]
    errors = []
    unknown = sorted(set(goal) - GOAL_FIELDS)
    if unknown:
        errors.append("unknown fields: " + ", ".join(unknown))
    if goal.get("schema_version") != GOAL_SCHEMA_VERSION:
        errors.append(f"schema_version must be {GOAL_SCHEMA_VERSION}")
    required_text = ("status", "priority", "value", "difficulty", "confidence", "next_action")
    for field in required_text:
        if not _text_present(goal.get(field)):
            errors.append(f"{field} is required")
    for field, allowed in (
        ("status", GOAL_STATUSES), ("priority", GOAL_PRIORITIES), ("value", GOAL_VALUES),
        ("difficulty", GOAL_DIFFICULTIES), ("confidence", GOAL_CONFIDENCES),
    ):
        if _text_present(goal.get(field)) and goal[field] not in allowed:
            errors.append(f"{field} is invalid")
    for field in ("depends_on", "blockers", "evidence"):
        if not isinstance(goal.get(field), list):
            errors.append(f"{field} must be a list")
    parent = goal.get("parent")
    if parent is not None and (not isinstance(parent, int) or isinstance(parent, bool) or parent < 1):
        errors.append("parent must be null or a positive issue number")
    dependencies = goal.get("depends_on")
    if isinstance(dependencies, list):
        if any(not isinstance(item, int) or isinstance(item, bool) or item < 1 for item in dependencies):
            errors.append("depends_on entries must be positive issue numbers")
        if len(set(dependencies)) != len(dependencies):
            errors.append("depends_on entries must be unique")
        if issue_number is not None and issue_number in dependencies:
            errors.append("depends_on cannot contain the current issue")
    if issue_number is not None and parent == issue_number:
        errors.append("parent cannot be the current issue")
    normalize_resources, _ = _require_configured()
    try:
        normalize_resources(goal.get("resources", []))
    except ValueError as exc:
        errors.append(str(exc))
    blockers = goal.get("blockers")
    if isinstance(blockers, list):
        for index, blocker in enumerate(blockers):
            if not isinstance(blocker, dict):
                errors.append(f"blockers[{index}] must be an object")
            elif blocker.get("status") == "open" and blocker.get("category") not in BLOCKER_CATEGORIES:
                errors.append(f"blockers[{index}].category is invalid or missing")
    rigor = goal.get("engineering_rigor")
    if rigor is not None:
        if not isinstance(rigor, dict):
            errors.append("engineering_rigor must be an object or null")
        else:
            unknown_rigor = sorted(set(rigor) - {"risk_categories", "override"})
            if unknown_rigor:
                errors.append("unknown engineering_rigor fields: " + ", ".join(unknown_rigor))
            categories = rigor.get("risk_categories")
            if not isinstance(categories, list):
                errors.append("engineering_rigor.risk_categories must be a list")
            else:
                if any(
                    not isinstance(item, str) or not item or item.casefold() != item
                    or not item.replace("_", "").isalnum()
                    for item in categories
                ):
                    errors.append("engineering_rigor.risk_categories entries must be lowercase identifiers")
                if len(categories) != len(set(categories)):
                    errors.append("engineering_rigor.risk_categories must be unique")
            override = rigor.get("override")
            if override is not None:
                if not isinstance(override, dict) or set(override) != {"level", "authority", "evidence"}:
                    errors.append("engineering_rigor.override must contain level, authority, and evidence")
                else:
                    if override.get("level") not in ENGINEERING_RIGOR_LEVELS:
                        errors.append("engineering_rigor.override.level is invalid")
                    if override.get("authority") not in ENGINEERING_RIGOR_OVERRIDE_AUTHORITIES:
                        errors.append("engineering_rigor.override.authority is invalid")
                    if not _text_present(override.get("evidence")):
                        errors.append("engineering_rigor.override.evidence is required")
    if not isinstance(goal.get("revision"), int) or isinstance(goal.get("revision"), bool) or goal.get("revision", 0) < 1:
        errors.append("revision must be a positive integer")
    implementation = goal.get("implementation")
    if implementation is not None:
        if not isinstance(implementation, dict):
            errors.append("implementation must be an object")
        else:
            for field in ("branch", "base", "target", "pr"):
                if field not in implementation or (implementation[field] is not None and not _text_present(implementation[field])):
                    errors.append(f"implementation.{field} must be null or non-empty text")
            review = implementation.get("review")
            if not isinstance(review, dict) or review.get("status") not in {"not_started", "pending", "approved", "changes_requested"}:
                errors.append("implementation.review.status is invalid")
            elif "checkpoint" not in review or (review["checkpoint"] is not None and not _text_present(review["checkpoint"])):
                errors.append("implementation.review.checkpoint must be null or non-empty text")
    return errors


def render_managed_goal(goal: dict[str, Any], body: str = "", issue_number: int | None = None) -> str:
    errors = validate_managed_goal(goal, issue_number)
    if errors:
        raise ValueError("Invalid managed goal: " + "; ".join(errors))
    block = f"{GOAL_BLOCK_START}\n{json.dumps(goal, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}\n{GOAL_BLOCK_END}"
    pattern = re.compile(
        re.escape(GOAL_BLOCK_START) + r"\s*\n.*?\n" + re.escape(GOAL_BLOCK_END),
        re.DOTALL,
    )
    if pattern.search(body):
        return pattern.sub(lambda _match: block, body, count=1)
    separator = "\n\n" if body and not body.endswith("\n\n") else ""
    return f"{body}{separator}{block}\n"


def compact_human_goal_text(body: str) -> str:
    """Retain current human sections while removing explicitly historical sections."""
    human = body.split(GOAL_BLOCK_START, 1)[0].strip("\ufeff\r\n ")
    sections: list[list[str]] = []
    fence: tuple[str, int] | None = None
    for line in human.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = (token[0], len(token))
            elif token[0] == fence[0] and len(token) >= fence[1]:
                fence = None
        if fence is None and re.match(r"^##\s+", line) and sections and sections[-1]:
            sections.append([])
        if not sections:
            sections.append([])
        sections[-1].append(line)
    kept = []
    for section in sections:
        text = "\n".join(section).strip()
        if not text:
            continue
        heading = section[0]
        normalized = re.sub(r"\s+", " ", heading.removeprefix("##").strip()).casefold()
        if normalized in HISTORICAL_HUMAN_SECTIONS:
            continue
        kept.append(text)
    return "\n\n".join(kept) + "\n"


def compact_managed_goal(goal: dict[str, Any]) -> dict[str, Any]:
    """Project requested transition state into the current-state-only body schema."""
    compact = json.loads(json.dumps(goal))
    compact["evidence"] = []
    compact["blockers"] = [
        blocker for blocker in compact.get("blockers", [])
        if isinstance(blocker, dict) and blocker.get("status") == "open"
    ]
    return compact


def validate_compact_goal_body(body: Any, issue_number: int | None = None) -> list[str]:
    if not isinstance(body, str):
        return ["compact goal body must be text"]
    errors = []
    try:
        goal = parse_managed_goal(body, issue_number)
    except ValueError as exc:
        return [str(exc)]
    if goal is None:
        return ["managed goal block is required"]
    if goal.get("evidence"):
        errors.append("current managed state must not retain transition evidence")
    if any(not isinstance(blocker, dict) or blocker.get("status") != "open" for blocker in goal.get("blockers", [])):
        errors.append("current managed state may contain only open blockers")
    human = body.split(GOAL_BLOCK_START, 1)[0].strip("\ufeff\r\n ") + "\n"
    if compact_human_goal_text(body) != human:
        errors.append("current human text contains an explicitly historical section")
    return errors


def goal_history_id(issue_number: int, expected_digest: str, desired: dict[str, Any]) -> str:
    source = json.dumps(
        {"issue": issue_number, "expected_digest": expected_digest, "desired": compact_managed_goal(desired)},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def render_goal_history(
    issue_number: int, expected_digest: str, prior_body: str, desired: dict[str, Any],
) -> tuple[str, str]:
    """Render one lossless, deterministic append-only transition record."""
    history_id = goal_history_id(issue_number, expected_digest, desired)
    payload = {
        "schema_version": GOAL_HISTORY_SCHEMA_VERSION,
        "id": history_id,
        "issue": issue_number,
        "expected_digest": expected_digest,
        "from_revision": desired["revision"] - 1,
        "to_revision": desired["revision"],
        "prior_body": prior_body,
        "requested_goal": desired,
    }
    payload["payload_digest"] = hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    block = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return history_id, (
        f"## ZzzOps transition history\n\n"
        f"Archived canonical state before revision {desired['revision']}.\n\n"
        f"{GOAL_HISTORY_BLOCK_START}\n{block}\n{GOAL_HISTORY_BLOCK_END}\n"
    )


def parse_goal_history(body: Any) -> dict[str, Any] | None:
    if not isinstance(body, str):
        return None
    pattern = re.compile(
        re.escape(GOAL_HISTORY_BLOCK_START) + r"\s*\n(.*?)\n" + re.escape(GOAL_HISTORY_BLOCK_END),
        re.DOTALL,
    )
    match = pattern.search(body)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid goal history JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Invalid goal history payload")
    digest = payload.get("payload_digest")
    digest_payload = {key: value for key, value in payload.items() if key != "payload_digest"}
    calculated_digest = hashlib.sha256(json.dumps(
        digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    if (
        payload.get("schema_version") != GOAL_HISTORY_SCHEMA_VERSION
        or not isinstance(payload.get("id"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", payload["id"])
        or not isinstance(payload.get("issue"), int)
        or isinstance(payload.get("issue"), bool)
        or payload["issue"] < 1
        or not isinstance(payload.get("expected_digest"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", payload["expected_digest"])
        or not isinstance(payload.get("prior_body"), str)
        or not isinstance(payload.get("requested_goal"), dict)
        or not isinstance(digest, str)
        or not hmac.compare_digest(digest, calculated_digest)
        or not hmac.compare_digest(
            payload["id"], goal_history_id(payload["issue"], payload["expected_digest"], payload["requested_goal"])
        )
    ):
        raise ValueError("Invalid goal history payload")
    return payload


def goal_needs_human(goal: dict[str, Any]) -> bool:
    return any(
        isinstance(blocker, dict)
        and blocker.get("status") == "open"
        and blocker.get("category") in BLOCKER_CATEGORIES
        for blocker in goal.get("blockers", [])
    )


def validate_github_issue_goal(issue_number: Any, title: Any, body: Any) -> list[str]:
    errors = []
    if not isinstance(issue_number, int) or isinstance(issue_number, bool) or issue_number < 1:
        errors.append("issue_number must be a positive integer")
    if not _text_present(title):
        errors.append("title is required")
    elif REDUNDANT_GOAL_TITLE_PREFIX.match(title):
        errors.append("title must not contain a redundant ZzzOps goal ID")
    if not isinstance(body, str):
        return errors + ["body must be text"]
    human = body.split(GOAL_BLOCK_START, 1)[0].lstrip("\ufeff\r\n ")
    if not human:
        errors.append("human-readable content must precede managed state")
    elif human.startswith("---"):
        errors.append("human-readable content must not start with rendered frontmatter")
    elif not human.startswith("## "):
        errors.append("human-readable content must start with a section heading")
    try:
        goal = parse_managed_goal(body, issue_number if isinstance(issue_number, int) else None)
    except ValueError as exc:
        errors.append(str(exc))
    else:
        if goal is None:
            errors.append("managed goal block is required")
    return errors


def github_goal_record(issue: dict[str, Any]) -> dict[str, Any]:
    number = issue.get("number")
    body = issue.get("body") or ""
    goal = parse_managed_goal(body, number)
    if goal is None:
        raise ValueError("managed goal block is required")
    errors = validate_github_issue_goal(number, issue.get("title"), body)
    if errors:
        raise ValueError("; ".join(errors))
    label_names = sorted(
        label["name"] for label in issue.get("labels", [])
        if isinstance(label, dict) and _text_present(label.get("name"))
    )
    schema_versions = [
        int(label.removeprefix(GOAL_SCHEMA_LABEL_PREFIX))
        for label in label_names
        if label.startswith(GOAL_SCHEMA_LABEL_PREFIX) and label.removeprefix(GOAL_SCHEMA_LABEL_PREFIX).isdigit()
    ]
    digest_source = "\0".join((issue.get("title") or "", body))
    return {
        "key": number, "title": issue["title"], "status": goal["status"],
        "priority": goal["priority"], "value": goal["value"], "difficulty": goal["difficulty"],
        "confidence": goal["confidence"], "parent": goal["parent"],
        "depends_on": goal["depends_on"], "claim": goal["claim"], "resources": goal.get("resources", []),
        "needs_human": goal_needs_human(goal),
        "blocker_categories": sorted({blocker["category"] for blocker in goal["blockers"] if blocker.get("status") == "open"}),
        "next_action": goal["next_action"], "revision": goal["revision"],
        "digest": hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
        "updated_at": issue.get("updated_at"), "implementation": goal.get("implementation"),
        "engineering_rigor": goal.get("engineering_rigor"),
        "labels": label_names, "schema_version": schema_versions[0] if len(schema_versions) == 1 else None,
        "state": issue.get("state"), "url": issue.get("html_url"),
    }


def current_goal_schema_label() -> str:
    return f"{GOAL_SCHEMA_LABEL_PREFIX}{GOAL_SCHEMA_VERSION}"


def github_archived_goal_record(issue: dict[str, Any]) -> dict[str, Any]:
    """Project one closed goal from discovery labels without hydrating its body."""
    labels = sorted(
        label["name"] for label in issue.get("labels", [])
        if isinstance(label, dict) and isinstance(label.get("name"), str)
    )
    statuses = [label.removeprefix("zzzops:status:") for label in labels if label.startswith("zzzops:status:")]
    priorities = [label.removeprefix("zzzops:priority:") for label in labels if label.startswith("zzzops:priority:")]
    if len(statuses) != 1 or statuses[0] not in {"done", "cancelled"}:
        raise ValueError("closed goal requires exactly one terminal status label")
    if len(priorities) != 1 or priorities[0] not in GOAL_PRIORITIES:
        raise ValueError("closed goal requires exactly one valid priority label")
    if str(issue.get("state", "")).casefold() != "closed":
        raise ValueError("archived goal projection requires a closed issue")
    digest_source = json.dumps(
        {
            "number": issue.get("number"), "title": issue.get("title"), "state": "closed",
            "labels": labels, "schema_version": issue.get("schema_version"),
        },
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return {
        "key": issue.get("number"), "title": issue.get("title"), "status": statuses[0],
        "priority": priorities[0], "value": None, "difficulty": None, "confidence": None,
        "parent": None, "depends_on": [], "claim": None, "resources": [], "needs_human": False,
        "blocker_categories": [], "next_action": None,
        "revision": None, "digest": hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
        "updated_at": None, "implementation": None, "labels": labels, "state": "closed",
        "url": issue.get("html_url"), "schema_version": issue.get("schema_version"),
        "engineering_rigor": None,
    }


def validate_goal_create(request: Any) -> list[str]:
    if not isinstance(request, dict):
        return ["goal create request must be an object"]
    errors = []
    unknown = sorted(set(request) - GOAL_CREATE_FIELDS)
    missing = sorted(GOAL_CREATE_FIELDS - set(request))
    if unknown:
        errors.append("unknown goal create fields: " + ", ".join(unknown))
    if missing:
        errors.append("missing goal create fields: " + ", ".join(missing))
    if request.get("schema_version") != GOAL_CREATE_SCHEMA_VERSION:
        errors.append(f"goal create schema_version must be {GOAL_CREATE_SCHEMA_VERSION}")
    title = request.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("title is required")
    elif title != title.strip():
        errors.append("title must be trimmed")
    elif len(title) > 256:
        errors.append("title must be at most 256 characters")
    elif REDUNDANT_GOAL_TITLE_PREFIX.match(title):
        errors.append("title must not include a generated goal identifier")
    body = request.get("body")
    if not isinstance(body, str) or not body.strip():
        errors.append("body is required")
    elif GOAL_BLOCK_START in body or GOAL_BLOCK_END in body:
        errors.append("body must not contain a managed goal block")
    labels = request.get("labels")
    if not isinstance(labels, list):
        errors.append("labels must be a list")
    else:
        invalid_labels = [
            label for label in labels
            if not isinstance(label, str) or not label.strip() or label != label.strip() or len(label) > 50
            or label == "zzzops" or label.startswith("zzzops:")
        ]
        if invalid_labels:
            errors.append("labels must be trimmed non-ZzzOps label names")
        if len({label.casefold() for label in labels if isinstance(label, str)}) != len(labels):
            errors.append("labels must be unique")
    goal = request.get("goal")
    errors.extend(validate_managed_goal(goal))
    if isinstance(goal, dict):
        if goal.get("status") != "new":
            errors.append("newly created goals must have status new")
        if goal.get("revision") != 1:
            errors.append("newly created goals must have revision 1")
        if goal.get("claim") is not None:
            errors.append("newly created goals must not have a claim")
        if goal.get("implementation") is not None:
            errors.append("newly created goals must not have implementation state")
    return errors


def load_goal_create(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.resolve().read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read goal create request: {type(exc).__name__}") from exc


def apply_goal_create(adapter: Any, repository: str, request: dict[str, Any]) -> dict[str, Any]:
    errors = validate_goal_create(request)
    if errors:
        raise ValueError("Invalid goal create request: " + "; ".join(errors))
    if adapter.repository.casefold() != repository.casefold():
        raise GoalTransitionProviderError("Repository identity changed; no goal was created.")
    goal = request["goal"]
    body = render_managed_goal(goal, request["body"])
    if len(body) > 65536:
        raise ValueError("Rendered goal body exceeds GitHub's issue limit")
    labels = [
        "zzzops", *request["labels"], current_goal_schema_label(),
        f"zzzops:status:{goal['status']}", f"zzzops:priority:{goal['priority']}",
    ]
    created = adapter.create_issue({"title": request["title"], "body": body, "labels": labels})
    if not isinstance(created, dict):
        raise GoalTransitionProviderError(
            "GitHub returned an unexpected goal-create response; success was not assumed."
        )
    number = created.get("number")
    expected_url = f"https://github.com/{repository}/issues/{number}"
    returned_label_items = created.get("labels")
    returned_labels = None if not isinstance(returned_label_items, list) else {
        label["name"] for label in returned_label_items
        if isinstance(label, dict) and isinstance(label.get("name"), str)
    }
    try:
        returned_goal = parse_managed_goal(created.get("body"), number)
    except (TypeError, ValueError) as exc:
        raise GoalTransitionProviderError(
            "GitHub returned an unexpected goal-create response; success was not assumed."
        ) from exc
    if (
        not isinstance(number, int) or isinstance(number, bool) or number < 1
        or created.get("title") != request["title"]
        or created.get("body") != body
        or str(created.get("state", "")).casefold() != "open"
        or returned_labels != set(labels)
        or created.get("html_url") != expected_url
        or returned_goal != goal
    ):
        raise GoalTransitionProviderError(
            "GitHub returned an unexpected goal-create response; success was not assumed."
        )
    return {
        "number": number, "revision": 1, "state": "open", "status": "new", "url": expected_url,
    }


def validate_goal_transition(transition: Any, issue_number: int) -> list[str]:
    if not isinstance(transition, dict):
        return ["transition must be an object"]
    errors = []
    unknown = sorted(set(transition) - GOAL_TRANSITION_FIELDS)
    missing = sorted(GOAL_TRANSITION_FIELDS - set(transition))
    if unknown:
        errors.append("unknown transition fields: " + ", ".join(unknown))
    if missing:
        errors.append("missing transition fields: " + ", ".join(missing))
    if transition.get("schema_version") != GOAL_TRANSITION_SCHEMA_VERSION:
        errors.append(f"transition schema_version must be {GOAL_TRANSITION_SCHEMA_VERSION}")
    expected_revision = transition.get("expected_revision")
    if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 1:
        errors.append("expected_revision must be a positive integer")
    digest = transition.get("expected_digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        errors.append("expected_digest must be the 64-character checkpoint goal digest")
    goal = transition.get("goal")
    errors.extend(validate_managed_goal(goal, issue_number))
    implementation = goal.get("implementation") if isinstance(goal, dict) else None
    review = implementation.get("review") if isinstance(implementation, dict) else None
    if isinstance(review, dict) and review.get("status") == "pending":
        if goal.get("status") != "blocked":
            errors.append("pending review checkpoint transition must use blocked status")
        if goal.get("claim") is not None:
            errors.append("pending review checkpoint transition must release the claim")
        blockers = goal.get("blockers")
        if not isinstance(blockers, list) or not any(
            isinstance(blocker, dict)
            and blocker.get("status") == "open"
            and blocker.get("category") == "human-action"
            for blocker in blockers
        ):
            errors.append("pending review checkpoint transition must include an open human-action blocker")
        for field in ("branch", "base", "target", "pr"):
            if not _text_present(implementation.get(field)):
                errors.append(f"pending review checkpoint transition requires implementation.{field}")
        if not _text_present(review.get("checkpoint")):
            errors.append("pending review checkpoint transition requires an exact checkpoint")
    if (
        isinstance(goal, dict) and isinstance(expected_revision, int)
        and not isinstance(expected_revision, bool) and goal.get("revision") != expected_revision + 1
    ):
        errors.append("goal revision must increment expected_revision by exactly one")
    return errors


def load_goal_transition(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.resolve().read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read goal transition: {type(exc).__name__}") from exc


def apply_goal_transition(
    adapter: Any, repository: str, issue_number: int, transition: dict[str, Any],
) -> dict[str, Any]:
    errors = validate_goal_transition(transition, issue_number)
    if errors:
        raise ValueError("Invalid goal transition: " + "; ".join(errors))
    if adapter.repository.casefold() != repository.casefold():
        raise GoalTransitionProviderError("Repository identity changed; no goal update was made.")
    issue = adapter.get_issue(issue_number)
    try:
        record = github_goal_record(issue)
    except ValueError as exc:
        raise GoalTransitionProviderError("The current goal could not be validated; no goal update was made.") from exc
    requested = transition["goal"]
    desired = compact_managed_goal(requested)
    history_id = goal_history_id(issue_number, transition["expected_digest"], requested)
    comments = adapter.get_issue_comments(issue_number)
    histories = []
    for comment in comments:
        try:
            history = parse_goal_history(comment.get("body") if isinstance(comment, dict) else None)
        except ValueError as exc:
            raise GoalTransitionProviderError("The selected goal has malformed transition history; no update was made.") from exc
        if history is not None and history.get("id") == history_id:
            histories.append((comment, history))
    if len(histories) > 1:
        raise GoalTransitionProviderError("The selected goal has duplicate transition history; no update was made.")

    state = "closed" if desired["status"] in {"done", "cancelled"} else "open"
    if record["revision"] == desired["revision"]:
        compact_body = render_managed_goal(desired, compact_human_goal_text(issue["body"]), issue_number)
        returned_labels = {
            label["name"] for label in issue.get("labels", [])
            if isinstance(label, dict) and isinstance(label.get("name"), str)
        }
        if (
            issue.get("body") == compact_body
            and str(issue.get("state", "")).casefold() == state
            and current_goal_schema_label() in returned_labels
            and f"zzzops:status:{desired['status']}" in returned_labels
            and f"zzzops:priority:{desired['priority']}" in returned_labels
            and len(histories) == 1
            and histories[0][1].get("issue") == issue_number
            and histories[0][1].get("to_revision") == desired["revision"]
            and histories[0][1].get("requested_goal") == requested
        ):
            return {
                "number": issue_number, "revision": desired["revision"], "state": state,
                "status": desired["status"], "url": f"https://github.com/{repository}/issues/{issue_number}",
            }
        raise ValueError(f"Goal #{issue_number} changed; the requested transition was not confirmed.")

    if record["revision"] != transition["expected_revision"]:
        raise ValueError(
            f"Goal #{issue_number} changed from revision {transition['expected_revision']} to {record['revision']}; no update was made."
        )
    if not hmac.compare_digest(record["digest"], transition["expected_digest"]):
        raise ValueError(f"Goal #{issue_number} digest changed; no update was made.")

    body = render_managed_goal(desired, compact_human_goal_text(issue["body"]), issue_number)
    compact_errors = validate_compact_goal_body(body, issue_number)
    if compact_errors:
        raise ValueError("Invalid compact goal body: " + "; ".join(compact_errors))
    _, history_body = render_goal_history(
        issue_number, transition["expected_digest"], issue["body"], requested,
    )
    if len(history_body) > 65536:
        raise GoalTransitionProviderError("Transition history exceeds GitHub's comment limit; no update was made.")
    if histories:
        if histories[0][0].get("body") != history_body:
            raise GoalTransitionProviderError("Existing transition history does not match the requested update.")
    else:
        created = adapter.create_issue_comment(issue_number, history_body)
        if created.get("body") != history_body or not isinstance(created.get("html_url"), str):
            raise GoalTransitionProviderError(
                "GitHub did not confirm exact transition history; body replacement was not attempted."
            )
    _, text_present = _require_configured()
    retained_labels = sorted({
        label["name"] for label in issue.get("labels", [])
        if isinstance(label, dict) and text_present(label.get("name"))
        and label["name"] != "zzzops"
        and not label["name"].startswith("zzzops:status:")
        and not label["name"].startswith("zzzops:priority:")
        and not label["name"].startswith(GOAL_SCHEMA_LABEL_PREFIX)
    })
    labels = [
        "zzzops", *retained_labels, current_goal_schema_label(),
        f"zzzops:status:{desired['status']}", f"zzzops:priority:{desired['priority']}",
    ]
    updated = adapter.update_issue(issue_number, {"body": body, "labels": labels, "state": state})

    expected_url = f"https://github.com/{repository}/issues/{issue_number}"
    returned_labels = {
        label["name"] for label in updated.get("labels", [])
        if isinstance(label, dict) and text_present(label.get("name"))
    }
    try:
        returned_goal = parse_managed_goal(updated.get("body"), issue_number)
    except ValueError as exc:
        raise GoalTransitionProviderError(
            "GitHub returned an unexpected goal-transition response; success was not assumed."
        ) from exc
    if (
        updated.get("number") != issue_number
        or updated.get("title") != issue.get("title")
        or updated.get("body") != body
        or str(updated.get("state", "")).casefold() != state
        or returned_labels != set(labels)
        or updated.get("html_url") != expected_url
        or returned_goal != desired
    ):
        raise GoalTransitionProviderError(
            "GitHub returned an unexpected goal-transition response; success was not assumed."
        )
    return {
        "number": issue_number, "revision": desired["revision"], "state": state,
        "status": desired["status"], "url": expected_url,
    }


def ensure_current_goal_schema(
    adapter: Any, repository: str, issue_number: int,
) -> dict[str, Any]:
    """Lazily compact one explicitly selected goal and apply the current schema label."""
    issue = adapter.get_issue(issue_number)
    labels = {
        label["name"] for label in issue.get("labels", [])
        if isinstance(label, dict) and isinstance(label.get("name"), str)
    }
    if current_goal_schema_label() in labels and not validate_compact_goal_body(issue.get("body"), issue_number):
        return {"number": issue_number, "migrated": False, "schema_version": GOAL_SCHEMA_VERSION}
    record = github_goal_record(issue)
    desired = parse_managed_goal(issue["body"], issue_number)
    if desired is None:  # pragma: no cover - github_goal_record already rejects this
        raise GoalTransitionProviderError("The selected goal has no managed state; no migration was made.")
    desired = json.loads(json.dumps(desired))
    desired["revision"] += 1
    result = apply_goal_transition(adapter, repository, issue_number, {
        "schema_version": GOAL_TRANSITION_SCHEMA_VERSION,
        "expected_revision": record["revision"],
        "expected_digest": record["digest"],
        "goal": desired,
    })
    return {**result, "migrated": True, "schema_version": GOAL_SCHEMA_VERSION}


def migrate_open_goal_schemas(
    adapter: Any, repository: str, indexes: list[dict[str, Any]], *, limit: int,
) -> dict[str, Any]:
    """Migrate one bounded page of open legacy goals; schema labels are the durable cursor."""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("migration limit must be from 1 to 100")
    candidates = sorted(
        (
            issue for issue in indexes
            if str(issue.get("state", "")).casefold() == "open"
            and issue.get("schema_version") != GOAL_SCHEMA_VERSION
        ),
        key=lambda issue: issue.get("number", 0),
    )
    selected = candidates[:limit]
    migrated = []
    already_current = []
    for issue in selected:
        result = ensure_current_goal_schema(adapter, repository, issue["number"])
        (migrated if result["migrated"] else already_current).append(issue["number"])
    remaining = max(0, len(candidates) - len(selected))
    return {
        "schema_version": GOAL_SCHEMA_VERSION, "selected": [issue["number"] for issue in selected],
        "migrated": migrated, "already_current": already_current,
        "remaining": remaining, "complete": remaining == 0,
    }
