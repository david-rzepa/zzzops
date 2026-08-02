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
GOAL_TRANSITION_SCHEMA_VERSION = 1
GOAL_TRANSITION_FIELDS = {"schema_version", "expected_revision", "expected_digest", "goal"}
BLOCKER_CATEGORIES = {"specification", "decision", "access-approval", "human-action", "external-dependency", "technical-unknown", "safety-compliance"}
REDUNDANT_GOAL_TITLE_PREFIX = re.compile(r"^\[G-\d{8}-\d{3}-[^\]]+\]\s*")
HISTORICAL_HUMAN_SECTIONS = {
    "completed evidence", "evidence", "history", "implementation history",
    "prior checkpoints", "resolved blockers", "superseded requirements",
}
_normalize_resources: Callable[[Any], list[str]] | None = None
_text_present: Callable[[Any], bool] | None = None


class GoalTransitionProviderError(ValueError):
    """The provider did not produce a safe, confirmed goal transition result."""

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
        "labels": sorted(label["name"] for label in issue.get("labels", []) if isinstance(label, dict) and _text_present(label.get("name"))),
        "state": issue.get("state"), "url": issue.get("html_url"),
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
    })
    labels = ["zzzops", *retained_labels, f"zzzops:status:{desired['status']}", f"zzzops:priority:{desired['priority']}"]
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

