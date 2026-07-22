#!/usr/bin/env python3
"""Managed-goal parsing, validation, rendering, and record projection."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

GOAL_SCHEMA_VERSION = 1
GOAL_BLOCK_START = "<!-- zzzops-goal"
GOAL_BLOCK_END = "zzzops-goal -->"
GOAL_FIELDS = {
    "schema_version", "status", "priority", "value", "difficulty", "confidence",
    "parent", "depends_on", "claim", "blockers", "evidence", "next_action",
    "revision", "implementation", "resources",
}
GOAL_STATUSES = {"new", "triaged", "ready", "in_progress", "blocked", "done", "cancelled"}
GOAL_PRIORITIES = {"P0", "P1", "P2", "P3"}
GOAL_VALUES = {"critical", "high", "medium", "low"}
GOAL_DIFFICULTIES = {"unknown", "XS", "S", "M", "L", "XL"}
GOAL_CONFIDENCES = {"low", "medium", "high"}
BLOCKER_CATEGORIES = {"specification", "decision", "access-approval", "human-action", "external-dependency", "technical-unknown", "safety-compliance"}
REDUNDANT_GOAL_TITLE_PREFIX = re.compile(r"^\[G-\d{8}-\d{3}-[^\]]+\]\s*")
_normalize_resources: Callable[[Any], list[str]] | None = None
_text_present: Callable[[Any], bool] | None = None

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
    digest_source = "\0".join((issue.get("title") or "", body, issue.get("updated_at") or ""))
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
        "labels": sorted(label["name"] for label in issue.get("labels", []) if isinstance(label, dict) and _text_present(label.get("name"))),
        "state": issue.get("state"), "url": issue.get("html_url"),
    }

