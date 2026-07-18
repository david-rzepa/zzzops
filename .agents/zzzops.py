#!/usr/bin/env python3
"""Small interactive ZzzOps control panel."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zzzops_health as health

PROJECT_SCHEMA_VERSION = 1
PLAN_SCHEMA_VERSION = 1
POLICY_SCHEMA_VERSION = 1
GOAL_SCHEMA_VERSION = 1
PORTFOLIO_SCHEMA_VERSION = 1
PROJECT_BLOCK_START = "<!-- zzzops-project-state"
PROJECT_BLOCK_END = "zzzops-project-state -->"
GOAL_BLOCK_START = "<!-- zzzops-goal"
GOAL_BLOCK_END = "zzzops-goal -->"
BACKENDS = {"github_issues", "local_files"}
POLICY_SECTION_IDS = (
    "backend",
    "git_review_release",
    "execution_continuation",
    "verification_testing",
    "code_quality",
    "dependencies_tooling",
    "security_privacy_compliance",
    "documentation_style",
    "deployment_resources",
    "autonomy_approval_parallelism",
)
GOAL_FIELDS = {
    "schema_version", "status", "priority", "value", "difficulty", "confidence",
    "parent", "depends_on", "claim", "blockers",
    "evidence", "next_action", "revision", "implementation",
}
BLOCKER_CATEGORIES = {
    "specification", "decision", "access-approval", "human-action",
    "external-dependency", "technical-unknown", "safety-compliance",
}
GOAL_STATUSES = {"new", "triaged", "ready", "in_progress", "blocked", "done", "cancelled"}
GOAL_PRIORITIES = {"P0", "P1", "P2", "P3"}
GOAL_VALUES = {"critical", "high", "medium", "low"}
GOAL_DIFFICULTIES = {"unknown", "XS", "S", "M", "L", "XL"}
GOAL_CONFIDENCES = {"low", "medium", "high"}
REDUNDANT_GOAL_TITLE_PREFIX = re.compile(r"^\[G-\d{8}-\d{3}-[^\]]+\]\s*")

PREFERENCE_LABELS = (
    ("documentation", "Fill backlog with documentation work"),
    ("tests", "Fill backlog with test work"),
    ("code_quality_non_behavioral", "Fill backlog with non-behavioral code-quality work"),
)
PARALLEL_MODES = (
    ("sequential", "Sequential only"),
    ("read_only", "Read-only parallel work"),
    ("worktrees", "Writable parallel work in Git worktrees"),
)
HEALTH_FIELDS = (
    (("enabled",), "Enable health nudges", "bool", None),
    (("timezone",), "IANA timezone", "text", None),
    (("signals", "allow_exact_message"), "Use exact harness message times", "bool", None),
    (("signals", "allow_observed_receipt"), "Use approximate workflow receipt times", "bool", None),
    (("schedule", "work_days"), "Work days (0=Mon..6=Sun)", "days", None),
    (("schedule", "work_start"), "Work start", "text", None),
    (("schedule", "work_end"), "Work end", "text", None),
    (("schedule", "wind_down"), "Wind-down time", "text", None),
    (("schedule", "bedtime"), "Bedtime", "text", None),
    (("schedule", "wake"), "Wake time", "text", None),
    (("schedule", "quiet_start"), "Quiet start", "text", None),
    (("schedule", "quiet_end"), "Quiet end", "text", None),
    (("reminders", "late_night", "enabled"), "Late-night reminder", "bool", None),
    (("reminders", "weekend", "enabled"), "Weekend reminder", "bool", None),
    (("reminders", "wind_down", "enabled"), "Wind-down reminder", "bool", None),
    (("reminders", "outside_work_hours", "enabled"), "Outside-work-window reminder", "bool", None),
    (("reminders", "long_session", "after_minutes"), "Long-session minutes", "int", (1, 1440)),
    (("reminders", "break", "after_minutes"), "Break minutes", "int", (1, 1440)),
    (("reminders", "hydration", "after_minutes"), "Water-break minutes", "int", (1, 1440)),
    (("delivery", "cooldown_minutes"), "Nudge cooldown minutes", "int", (1, 1440)),
    (("delivery", "snooze_minutes"), "Default snooze minutes", "int", (1, 1440)),
    (("delivery", "inactivity_reset_minutes"), "Session reset minutes", "int", (1, 1440)),
    (("delivery", "tone"), "Tone", "choice", ("gentle", "direct", "humorous")),
    (("privacy", "retention_hours"), "Derived timestamp retention hours", "int", (1, 720)),
)


def load_preferences(repo: Path) -> tuple[Path, dict[str, Any]]:
    path = repo / ".zzzops" / "PREFERENCES.json"
    template = repo / ".agents" / "templates" / "project-goals" / "PREFERENCES.json"
    source = path if path.exists() else template
    try:
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read preferences from {source}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Preferences root must be a JSON object")
    fill = data.setdefault("fill_backlog", {})
    if not isinstance(fill, dict):
        raise ValueError("fill_backlog must be a JSON object")
    for key, _label in PREFERENCE_LABELS:
        if not isinstance(fill.setdefault(key, False), bool):
            raise ValueError(f"fill_backlog.{key} must be true or false")
    cap = fill.setdefault("max_goals_per_refill", 3)
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1 or cap > 25:
        raise ValueError("max_goals_per_refill must be an integer from 1 to 25")
    parallel = data.setdefault("parallelization", {})
    if not isinstance(parallel, dict):
        raise ValueError("parallelization must be a JSON object")
    mode = parallel.setdefault("mode", "read_only")
    if mode not in {value for value, _label in PARALLEL_MODES}:
        raise ValueError("parallelization.mode must be sequential, read_only, or worktrees")
    workers = parallel.setdefault("max_workers", 2)
    if not isinstance(workers, int) or isinstance(workers, bool) or workers < 1 or workers > 8:
        raise ValueError("parallelization.max_workers must be an integer from 1 to 8")
    return path, data


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def user_health_preferences_path(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if env.get("ZZZOPS_USER_CONFIG_DIR"):
        return Path(env["ZZZOPS_USER_CONFIG_DIR"]) / "health_preferences.json"
    if sys.platform == "win32":
        root = env.get("APPDATA")
        return Path(root) / "ZzzOps" / "health_preferences.json" if root else Path.home() / ".config" / "zzzops" / "health_preferences.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ZzzOps" / "health_preferences.json"
    return Path(env.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "zzzops" / "health_preferences.json"


def machine_health_state_path(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if env.get("ZZZOPS_MACHINE_STATE_DIR"):
        return Path(env["ZZZOPS_MACHINE_STATE_DIR"]) / "health_state.json"
    if sys.platform == "win32":
        root = env.get("LOCALAPPDATA")
        return Path(root) / "ZzzOps" / "health_state.json" if root else Path.home() / ".local" / "state" / "zzzops" / "health_state.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ZzzOps" / "health_state.json"
    return Path(env.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "zzzops" / "health_state.json"


def load_json_object(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return deepcopy_json(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def deepcopy_json(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value))


def load_user_health_preferences() -> tuple[Path, dict[str, Any]]:
    path = user_health_preferences_path()
    data = health.merged_preferences(load_json_object(path, health.default_preferences()))
    errors = health.validate_preferences(data)
    if errors:
        raise ValueError("Invalid user health preferences: " + "; ".join(errors))
    return path, data


def load_machine_health_state() -> tuple[Path, dict[str, Any]]:
    path = machine_health_state_path()
    data = health.merged_state(load_json_object(path, health.default_state()))
    errors = health.validate_state(data)
    if errors:
        raise ValueError("Invalid machine health state: " + "; ".join(errors))
    return path, data


def private_atomic_json(path: Path, data: dict[str, Any]) -> None:
    atomic_json(path, data)
    if os.name != "nt":
        path.chmod(0o600)


def storage_error(exc: OSError, path: Path) -> dict[str, Any]:
    return {
        "ok": False,
        "reason_code": "storage_unavailable",
        "path": str(path),
        "detail": type(exc).__name__,
        "fallback": "none; grant access or set the documented ZzzOps path override",
    }


def project_digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def project_path(repo: Path) -> Path:
    return repo / ".zzzops" / "PROJECT.md"


def read_project(repo: Path) -> tuple[Path, str]:
    path = project_path(repo)
    try:
        return path, path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return path, ""
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Cannot read project charter from {path}: {exc}") from exc


def parse_project_state(text: str) -> dict[str, Any] | None:
    pattern = re.compile(
        re.escape(PROJECT_BLOCK_START) + r"\s*\n(.*?)\n" + re.escape(PROJECT_BLOCK_END),
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None
    try:
        state = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid project state JSON: {exc}") from exc
    if not isinstance(state, dict):
        raise ValueError("Project state must be a JSON object")
    return state


def validate_project_state(state: Any) -> list[str]:
    if not isinstance(state, dict):
        return ["project state must be an object"]
    allowed = {"schema_version", "initialized", "backend", "repository", "revision", "migration_pending", "policy"}
    errors = []
    unknown = sorted(set(state) - allowed)
    if unknown:
        errors.append("unknown fields: " + ", ".join(unknown))
    if state.get("schema_version") != PROJECT_SCHEMA_VERSION:
        errors.append(f"schema_version must be {PROJECT_SCHEMA_VERSION}")
    if not isinstance(state.get("initialized"), bool):
        errors.append("initialized must be boolean")
    if not isinstance(state.get("revision"), int) or isinstance(state.get("revision"), bool) or state.get("revision", -1) < 0:
        errors.append("revision must be a non-negative integer")
    if not isinstance(state.get("migration_pending"), bool):
        errors.append("migration_pending must be boolean")
    policy_errors = validate_policy(state.get("policy"), require_pending=False) if state.get("policy") is not None else []
    errors.extend(f"policy.{error}" for error in policy_errors)
    pending_policy = policy_blockers(state.get("policy")) if not policy_errors else []
    if state.get("initialized") is True:
        if state.get("backend") not in BACKENDS:
            errors.append("initialized backend must be github_issues or local_files")
        repository = state.get("repository")
        if not isinstance(repository, dict) or not nonempty(repository.get("identity")):
            errors.append("initialized repository.identity is required")
        if pending_policy:
            errors.append("initialized state cannot have unreviewed required policy: " + ", ".join(pending_policy))
    elif state.get("backend") is not None or state.get("repository") is not None or state.get("migration_pending") is not False:
        if state.get("backend") not in BACKENDS or not isinstance(state.get("repository"), dict) or not state.get("policy"):
            errors.append("uninitialized state may select a backend only as a complete pending policy draft")
    return errors


def validate_policy(policy: Any, require_pending: bool) -> list[str]:
    if not isinstance(policy, dict):
        return ["must be an object"]
    errors = []
    if policy.get("schema_version") != POLICY_SCHEMA_VERSION:
        errors.append(f"schema_version must be {POLICY_SCHEMA_VERSION}")
    sections = policy.get("sections")
    if not isinstance(sections, list):
        return errors + ["sections must be a list"]
    evidence_ids = set()
    if not require_pending:
        evidence = policy.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append("evidence must be a non-empty list")
        else:
            for index, item in enumerate(evidence):
                if not isinstance(item, dict) or not text_present(item.get("id")) or not text_present(item.get("source")) or not text_present(item.get("finding")):
                    errors.append(f"evidence[{index}] requires id, source, and finding")
                elif item["id"] in evidence_ids:
                    errors.append(f"evidence[{index}].id must be unique")
                else:
                    evidence_ids.add(item["id"])
    seen = set()
    for index, section in enumerate(sections):
        prefix = f"sections[{index}]"
        if not isinstance(section, dict):
            errors.append(f"{prefix} must be an object")
            continue
        section_id = section.get("id")
        if section_id not in POLICY_SECTION_IDS or section_id in seen:
            errors.append(f"{prefix}.id must be unique and from the current taxonomy")
        else:
            seen.add(section_id)
        for field in ("title", "decision", "rationale", "confidence", "default_origin", "default_disposition"):
            if not text_present(section.get(field)):
                errors.append(f"{prefix}.{field} is required")
        if section.get("confidence") not in {"low", "medium", "high"}:
            errors.append(f"{prefix}.confidence must be low, medium, or high")
        if section.get("default_disposition") not in {"accepted", "changed", "rejected", "unknown"}:
            errors.append(f"{prefix}.default_disposition must be accepted, changed, rejected, or unknown")
        if not isinstance(section.get("required"), bool) or not isinstance(section.get("applicable"), bool):
            errors.append(f"{prefix}.required and applicable must be booleans")
        for field in ("source_ids", "exceptions", "unresolved"):
            if not isinstance(section.get(field), list):
                errors.append(f"{prefix}.{field} must be a list")
        if not require_pending and isinstance(section.get("source_ids"), list):
            missing_sources = sorted(set(section["source_ids"]) - evidence_ids)
            if missing_sources:
                errors.append(f"{prefix}.source_ids missing citations: {', '.join(missing_sources)}")
        if not isinstance(section.get("settings"), dict):
            errors.append(f"{prefix}.settings must be an object")
        review = section.get("review")
        if not isinstance(review, dict) or not isinstance(review.get("approved"), bool):
            errors.append(f"{prefix}.review.approved must be boolean")
        elif require_pending and review.get("approved") is not False:
            errors.append(f"{prefix}.review must be pending in an agent-generated plan")
        elif review.get("approved") is True and any(not text_present(review.get(field)) for field in ("reviewer", "date", "reviewed_digest")):
            errors.append(f"{prefix}.review approval requires reviewer, date, and reviewed_digest")
        elif review.get("approved") is True and section.get("unresolved"):
            errors.append(f"{prefix}.review cannot approve unresolved choices")
        if section.get("applicable") is False and not text_present(section.get("rationale")):
            errors.append(f"{prefix}.rationale is required for not applicable")
    missing = sorted(set(POLICY_SECTION_IDS) - seen)
    if missing:
        errors.append("missing sections: " + ", ".join(missing))
    return errors


def policy_blockers(policy: Any) -> list[str]:
    if not isinstance(policy, dict) or not isinstance(policy.get("sections"), list):
        return ["policy:missing"]
    return [
        f"policy:{section.get('id')}"
        for section in policy["sections"]
        if isinstance(section, dict)
        and section.get("required") is True
        and not (isinstance(section.get("review"), dict) and section["review"].get("approved") is True)
    ]


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
        if not text_present(goal.get(field)):
            errors.append(f"{field} is required")
    for field, allowed in (
        ("status", GOAL_STATUSES), ("priority", GOAL_PRIORITIES), ("value", GOAL_VALUES),
        ("difficulty", GOAL_DIFFICULTIES), ("confidence", GOAL_CONFIDENCES),
    ):
        if text_present(goal.get(field)) and goal[field] not in allowed:
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
                if field not in implementation or (implementation[field] is not None and not text_present(implementation[field])):
                    errors.append(f"implementation.{field} must be null or non-empty text")
            review = implementation.get("review")
            if not isinstance(review, dict) or review.get("status") not in {"not_started", "pending", "approved", "changes_requested"}:
                errors.append("implementation.review.status is invalid")
            elif "checkpoint" not in review or (review["checkpoint"] is not None and not text_present(review["checkpoint"])):
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
    if not text_present(title):
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


def _inline_yaml_value(value: str) -> Any:
    value = value.strip()
    if value in {"", "null", "~"}:
        return None
    if value.casefold() in {"true", "false"}:
        return value.casefold() == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [item.strip().strip('"\'') for item in inner.split(",")]
    if value.startswith("{") and value.endswith("}"):
        result = {}
        for item in value[1:-1].split(","):
            key, separator, nested = item.partition(":")
            if not separator:
                raise ValueError(f"invalid inline mapping: {value}")
            result[key.strip()] = _inline_yaml_value(nested)
        return result
    return value.strip('"\'')


def parse_local_goal(path: Path, repo: Path | None = None) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    match = re.match(r"---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        raise ValueError("missing YAML frontmatter")
    frontmatter = match.group(1)
    fields: dict[str, Any] = {}
    implementation: dict[str, Any] = {}
    in_implementation = False
    for line in frontmatter.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        key, separator, value = line.strip().partition(":")
        if not separator:
            raise ValueError(f"invalid frontmatter line: {line}")
        if indent == 0:
            in_implementation = key == "implementation"
            if not in_implementation:
                fields[key] = _inline_yaml_value(value)
        elif in_implementation and indent == 2:
            implementation[key] = _inline_yaml_value(value)
    if implementation:
        fields["implementation"] = implementation
    for required in ("id", "title", "status", "priority", "value", "difficulty", "confidence"):
        if not text_present(fields.get(required)):
            raise ValueError(f"{required} is required")
    for field, allowed in (
        ("status", GOAL_STATUSES), ("priority", GOAL_PRIORITIES), ("value", GOAL_VALUES),
        ("difficulty", GOAL_DIFFICULTIES), ("confidence", GOAL_CONFIDENCES),
    ):
        if fields[field] not in allowed:
            raise ValueError(f"{field} is invalid")
    for relation in ("depends_on", "blocks"):
        if not isinstance(fields.get(relation, []), list):
            raise ValueError(f"{relation} must be an inline list")
    blocker_categories = re.findall(
        r"Status/category/raised/owner:\s*open\s*/\s*`?([a-z-]+)`?", text[match.end():], re.IGNORECASE,
    )
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "key": fields["id"], "title": fields["title"], "status": fields["status"],
        "priority": fields["priority"], "value": fields["value"], "difficulty": fields["difficulty"],
        "confidence": fields["confidence"], "parent": fields.get("parent"),
        "depends_on": fields.get("depends_on", []), "claim": fields.get("claim"),
        "needs_human": bool(fields.get("needs_human")) or bool(blocker_categories),
        "blocker_categories": blocker_categories, "next_action": _extract_next_action(text),
        "revision": None, "digest": digest, "updated_at": fields.get("updated"),
        "implementation": fields.get("implementation"), "labels": [],
        "path": path.relative_to(repo).as_posix() if repo is not None else path.name,
        "declared_blocks": fields.get("blocks", []), "filename": path.stem,
    }


def _extract_next_action(text: str) -> str:
    match = re.search(r"\*\*Next action:\*\*\s*(.+)", text)
    return match.group(1).strip() if match else ""


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
        "depends_on": goal["depends_on"], "claim": goal["claim"],
        "needs_human": goal_needs_human(goal),
        "blocker_categories": sorted({blocker["category"] for blocker in goal["blockers"] if blocker.get("status") == "open"}),
        "next_action": goal["next_action"], "revision": goal["revision"],
        "digest": hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
        "updated_at": issue.get("updated_at"), "implementation": goal.get("implementation"),
        "labels": sorted(label["name"] for label in issue.get("labels", []) if isinstance(label, dict) and text_present(label.get("name"))),
        "state": issue.get("state"), "url": issue.get("html_url"),
    }


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


def audit_portfolio(records: list[dict[str, Any]], backend: str, as_of: datetime | None = None) -> list[dict[str, Any]]:
    as_of = datetime.now(timezone.utc) if as_of is None else as_of
    findings: list[dict[str, Any]] = []
    grouped: dict[Any, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["key"], []).append(record)
    for key, matches in grouped.items():
        if len(matches) > 1:
            findings.append({"code": "duplicate_identity", "goal": key, "detail": f"{len(matches)} records"})
    goals = {key: matches[0] for key, matches in grouped.items()}
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
        elif backend == "local_files":
            if record.get("filename") != key:
                findings.append({"code": "filename_identity_mismatch", "goal": key, "detail": str(record.get("filename"))})
            if set(record.get("declared_blocks", [])) != set(record.get("blocks", [])):
                findings.append({"code": "local_backlink_drift", "goal": key, "detail": f"declared={record.get('declared_blocks', [])}; derived={record.get('blocks', [])}"})
    for relation in ("depends_on", "parent"):
        for key in sorted(_cycle_nodes(records, relation), key=_portfolio_key):
            findings.append({"code": f"{relation}_cycle", "goal": key, "detail": "cycle member"})
    return sorted(findings, key=lambda finding: (finding["code"], str(finding["goal"]), finding["detail"]))


def build_portfolio_snapshot(
    backend: str, records: list[dict[str, Any]], *, reads: int, raw_bytes: int,
    ignored: int = 0, as_of: datetime | None = None,
) -> dict[str, Any]:
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
    findings = audit_portfolio(records, backend, as_of)
    terminal = {"done", "cancelled"}
    blocked = {record["key"] for record in records if record["status"] == "blocked" or record["needs_human"]}
    terminal_keys = {record["key"] for record in records if record["status"] in terminal}
    done = {record["key"] for record in records if record["status"] == "done"}
    actionable = [
        record["key"] for record in records
        if record["status"] in {"ready", "in_progress"} and record["key"] not in blocked
        and all(dependency in done for dependency in record.get("depends_on", []))
    ]
    portfolio_digest = hashlib.sha256(
        "\n".join(f"{record['key']}:{record['revision']}:{record['digest']}" for record in sorted(records, key=lambda item: _portfolio_key(item["key"]))).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": PORTFOLIO_SCHEMA_VERSION, "backend": backend, "complete": True,
        "valid": not findings,
        "portfolio_digest": portfolio_digest, "goals": sorted(records, key=lambda record: _portfolio_key(record["key"])),
        "findings": findings, "summary": {
            "total": len(records), "actionable": len(actionable), "blocked": len(blocked),
            "done": len(terminal_keys), "findings": len(findings), "reads": reads,
            "raw_bytes": raw_bytes, "ignored": ignored,
        },
    }


def portfolio_snapshot(repo: Path, as_of: datetime | None = None) -> dict[str, Any]:
    project_path = repo / ".zzzops" / "PROJECT.md"
    if not project_path.is_file():
        raise ValueError("PROJECT.md is missing; run agent-driven initialization")
    project = parse_project_state(project_path.read_text(encoding="utf-8-sig"))
    errors = validate_project_state(project)
    if errors or not project or not project.get("initialized"):
        raise ValueError("PROJECT.md is not initialized: " + "; ".join(errors or ["initialization pending"]))
    backend = project["backend"]
    if backend == "local_files":
        item_root = repo / "goals" / "items"
        paths = sorted(item_root.glob("*.md")) if item_root.is_dir() else []
        records = []
        findings = []
        raw_bytes = 0
        for path in paths:
            try:
                if path.is_symlink():
                    raise ValueError("symbolic-link goal files are not supported")
                raw_bytes += path.stat().st_size
                records.append(parse_local_goal(path, repo))
            except (OSError, UnicodeError, ValueError) as exc:
                findings.append({"code": "malformed_record", "goal": path.name, "detail": str(exc)})
        index_path = repo / "goals" / "INDEX.md"
        expected_links = {path.name for path in paths}
        if expected_links and not index_path.is_file():
            findings.append({"code": "local_index_drift", "goal": "goals/INDEX.md", "detail": "derived index missing"})
        elif index_path.is_file():
            try:
                index_text = index_path.read_text(encoding="utf-8-sig")
                actual_links = set(re.findall(r"items/([^\s)>]+\.md)", index_text))
                if actual_links != expected_links:
                    findings.append({"code": "local_index_drift", "goal": "goals/INDEX.md", "detail": f"missing={sorted(expected_links - actual_links)}; stale={sorted(actual_links - expected_links)}"})
            except (OSError, UnicodeError) as exc:
                findings.append({"code": "local_index_drift", "goal": "goals/INDEX.md", "detail": str(exc)})
        snapshot = build_portfolio_snapshot(backend, records, reads=1, raw_bytes=raw_bytes, as_of=as_of)
        snapshot["findings"] = sorted(snapshot["findings"] + findings, key=lambda item: (item["code"], str(item["goal"])))
        snapshot["summary"]["findings"] = len(snapshot["findings"])
        snapshot["complete"] = not findings
        snapshot["valid"] = not snapshot["findings"]
        snapshot["summary"]["processes"] = 0
        return snapshot
    identity = ((project.get("repository") or {}).get("identity") if isinstance(project.get("repository"), dict) else None)
    if not text_present(identity):
        raise ValueError("PROJECT.md repository.identity is required for GitHub Issues")
    executable = shutil.which("gh")
    if not executable:
        raise ValueError("GitHub CLI is unavailable")
    command = [executable, "api", "--paginate", "--slurp", f"repos/{identity}/issues?state=all&labels=zzzops&per_page=100"]
    try:
        result = subprocess.run(command, cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"GitHub portfolio read failed: {type(exc).__name__}") from exc
    if result.returncode:
        raise ValueError("GitHub portfolio read failed: " + (result.stderr.strip() or "unknown gh error"))
    try:
        pages = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"GitHub portfolio read returned invalid JSON: {exc}") from exc
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise ValueError("GitHub portfolio pagination result is incomplete or malformed")
    issues = [issue for page in pages for issue in page if isinstance(issue, dict) and "pull_request" not in issue]
    managed = [issue for issue in issues if GOAL_BLOCK_START in (issue.get("body") or "")]
    records = []
    findings = []
    for issue in managed:
        try:
            records.append(github_goal_record(issue))
        except (KeyError, TypeError, ValueError) as exc:
            findings.append({"code": "malformed_record", "goal": issue.get("number", "unknown"), "detail": str(exc)})
    snapshot = build_portfolio_snapshot(
        backend, records, reads=len(pages), raw_bytes=len(result.stdout.encode("utf-8")),
        ignored=len(issues) - len(managed), as_of=as_of,
    )
    snapshot["findings"] = sorted(snapshot["findings"] + findings, key=lambda item: (item["code"], str(item["goal"])))
    snapshot["summary"]["findings"] = len(snapshot["findings"])
    snapshot["complete"] = not findings
    snapshot["valid"] = not snapshot["findings"]
    snapshot["summary"]["processes"] = 1
    return snapshot


def render_portfolio_summary(snapshot: dict[str, Any], include_done: bool = False) -> str:
    summary = snapshot["summary"]
    lines = [
        f"ZzzOps portfolio: {snapshot['backend']} | goals={summary['total']} actionable={summary['actionable']} "
        f"blocked={summary['blocked']} done={summary['done']} findings={summary['findings']} reads={summary['reads']} "
        f"complete={str(snapshot['complete']).lower()} valid={str(snapshot['valid']).lower()}",
        f"digest={snapshot['portfolio_digest']}",
    ]
    for goal in snapshot["goals"]:
        if not include_done and goal["status"] in {"done", "cancelled"}:
            continue
        human = " human" if goal["needs_human"] else ""
        title = re.sub(r"\s+", " ", str(goal["title"])).strip()[:240]
        next_action = re.sub(r"\s+", " ", str(goal["next_action"])).strip()[:240]
        lines.append(f"{goal['key']} [{goal['status']} {goal['priority']}/{goal['value']}/{goal['difficulty']}{human}] {title} — {next_action}")
    for finding in snapshot["findings"]:
        lines.append(f"! {finding['code']} {finding['goal']}: {finding['detail']}")
    return "\n".join(lines)


def compare_portfolios(snapshot: dict[str, Any], prior: dict[str, Any]) -> list[dict[str, Any]]:
    if prior.get("schema_version") != PORTFOLIO_SCHEMA_VERSION or not isinstance(prior.get("goals"), list):
        raise ValueError("comparison snapshot has an unsupported schema")
    if any(not isinstance(goal, dict) or "key" not in goal or "digest" not in goal or "revision" not in goal for goal in prior["goals"]):
        raise ValueError("comparison snapshot contains a malformed goal")
    current = {goal["key"]: goal for goal in snapshot["goals"]}
    previous = {goal["key"]: goal for goal in prior["goals"]}
    findings = []
    for key in sorted(current.keys() | previous.keys(), key=_portfolio_key):
        if key not in previous:
            findings.append({"code": "goal_added", "goal": key, "detail": "absent from comparison snapshot"})
        elif key not in current:
            findings.append({"code": "goal_removed", "goal": key, "detail": "absent from current snapshot"})
        elif current[key].get("digest") != previous[key].get("digest") or current[key].get("revision") != previous[key].get("revision"):
            findings.append({"code": "goal_changed", "goal": key, "detail": "digest or revision changed"})
    return findings


def command_probe(command: list[str], repo: Path) -> dict[str, Any]:
    executable = shutil.which(command[0])
    if not executable:
        return {"available": False, "ok": False, "detail": "executable not found"}
    try:
        result = subprocess.run(
            [executable, *command[1:]], cwd=repo, capture_output=True, text=True,
            timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": True, "ok": False, "detail": type(exc).__name__}
    detail = (result.stdout.strip() or result.stderr.strip()).splitlines()
    return {
        "available": True,
        "ok": result.returncode == 0,
        "detail": sanitize_output(detail[0][:300]) if detail else "",
    }


def sanitize_output(value: str) -> str:
    return re.sub(r"(https?://)[^/@\s]+@", r"\1***@", value)


def github_repository_probe(repo: Path) -> dict[str, Any]:
    executable = shutil.which("gh")
    if not executable:
        return {"available": False, "usable": False, "detail": "executable not found"}
    try:
        result = subprocess.run(
            [executable, "repo", "view", "--json", "nameWithOwner,url,hasIssuesEnabled,viewerPermission"],
            cwd=repo, capture_output=True, text=True, timeout=8, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": True, "usable": False, "detail": type(exc).__name__}
    if result.returncode:
        detail = (result.stderr.strip() or "repository probe failed").splitlines()[0]
        return {"available": True, "usable": False, "detail": sanitize_output(detail[:300])}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"available": True, "usable": False, "detail": "invalid gh JSON"}
    permission = data.get("viewerPermission")
    issues = data.get("hasIssuesEnabled") is True
    return {
        "available": True,
        "usable": issues and permission in {"TRIAGE", "WRITE", "MAINTAIN", "ADMIN"},
        "identity": data.get("nameWithOwner"),
        "url": data.get("url"),
        "issues_enabled": issues,
        "viewer_permission": permission,
        "detail": "ok" if issues else "issues disabled",
    }


def inspect_initialization(repo: Path) -> dict[str, Any]:
    path, text = read_project(repo)
    error = None
    try:
        state = parse_project_state(text)
        state_errors = validate_project_state(state) if state is not None else ["project state block is missing"]
        if state_errors:
            error = "; ".join(state_errors)
    except ValueError as exc:
        state = None
        error = str(exc)
    git_remote = command_probe(["git", "remote", "get-url", "origin"], repo)
    github_auth = command_probe(["gh", "auth", "status"], repo)
    github_repository = github_repository_probe(repo)
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "project_path": str(path),
        "base_digest": project_digest(text),
        "state": state,
        "initialized": bool(state and state.get("initialized") is True and not policy_blockers(state.get("policy"))),
        "valid_state": error is None and state is not None,
        "state_error": error,
        "missing_charter_fields": charter_missing_fields(text),
        "decision_blockers": policy_blockers(state.get("policy")) if state else ["policy:missing"],
        "backend_constraints": {
            "github_issues": "requires a usable GitHub repository probe",
            "local_files": "explicit supported alternative; never automatic failover",
        },
        "capabilities": {
            "git_origin": git_remote,
            "github_auth": github_auth,
            "github_repository": github_repository,
        },
    }


def charter_missing_fields(text: str) -> list[str]:
    fields = []
    labels = {
        "outcome": "Outcome",
        "beneficiaries": "Primary beneficiaries",
        "why_it_matters": "Why it matters",
    }
    for field, label in labels.items():
        match = re.search(rf"^- {re.escape(label)}:\s*(.*)$", text, re.MULTILINE | re.IGNORECASE)
        if not match or not nonempty(match.group(1)):
            fields.append(field)
    if not re.search(r"^- \[x\]\s+.+", text, re.MULTILINE | re.IGNORECASE):
        fields.append("acceptance_criteria")
    if "| Unknown |" in text or "## Success metrics" not in text:
        fields.append("kpis")
    return fields


def load_plan(path: Path) -> dict[str, Any]:
    try:
        plan = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read initialization plan from {path}: {exc}") from exc
    if not isinstance(plan, dict):
        raise ValueError("Initialization plan must be a JSON object")
    return plan


def validate_plan(repo: Path, plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allowed = {
        "schema_version", "base_digest", "confirmed", "backend", "repository",
        "charter", "evidence", "confirmations", "github", "migration_pending", "policy",
    }
    unknown = sorted(set(plan) - allowed)
    if unknown:
        errors.append("unknown fields: " + ", ".join(unknown))
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        errors.append(f"schema_version must be {PLAN_SCHEMA_VERSION}")
    _path, current = read_project(repo)
    if plan.get("base_digest") != project_digest(current):
        errors.append("base_digest is stale or missing")
    if plan.get("confirmed") is not True:
        errors.append("confirmed must be true")
    backend = plan.get("backend")
    if backend not in BACKENDS:
        errors.append("backend must be github_issues or local_files")
    if not isinstance(plan.get("migration_pending"), bool):
        errors.append("migration_pending must be boolean")
    local_goals = list((repo / "goals" / "items").glob("*.md"))
    expected_migration = backend == "github_issues" and bool(local_goals)
    if plan.get("migration_pending") is not expected_migration:
        errors.append(f"migration_pending must be {str(expected_migration).lower()} for current local goal state")
    repository = plan.get("repository")
    if not isinstance(repository, dict) or not nonempty(repository.get("identity")):
        errors.append("repository.identity is required")
    charter = plan.get("charter")
    if not isinstance(charter, dict):
        errors.append("charter must be an object")
    else:
        required_text = ("outcome", "why_it_matters", "time_horizon", "precedence")
        for field in required_text:
            if not nonempty(charter.get(field)):
                errors.append(f"charter.{field} is required")
        required_lists = (
            "beneficiaries", "acceptance_criteria", "constraints",
            "non_goals", "unacceptable_tradeoffs",
        )
        for field in required_lists:
            if not nonempty_list(charter.get(field)):
                errors.append(f"charter.{field} must be a non-empty list")
        kpis = charter.get("kpis")
        if not isinstance(kpis, list) or not kpis:
            errors.append("charter.kpis must be a non-empty list")
        for index, kpi in enumerate(kpis if isinstance(kpis, list) else []):
            required = ("name", "why", "baseline", "target", "evidence", "cadence")
            if not isinstance(kpi, dict) or any(not text_present(kpi.get(key)) for key in required):
                errors.append(f"charter.kpis[{index}] must define {', '.join(required)}")
    evidence = plan.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("evidence must be a non-empty list")
        evidence = []
    evidence_ids = set()
    proposal_ids = set()
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            errors.append(f"evidence[{index}] must be an object")
            continue
        evidence_id = item.get("id")
        if not text_present(evidence_id) or evidence_id in evidence_ids:
            errors.append(f"evidence[{index}].id must be unique and non-empty")
        else:
            evidence_ids.add(evidence_id)
        if item.get("kind") not in {"observed", "proposed"}:
            errors.append(f"evidence[{index}].kind must be observed or proposed")
        if not text_present(item.get("source")) or not text_present(item.get("finding")):
            errors.append(f"evidence[{index}] requires source and finding")
        if item.get("kind") == "proposed" and text_present(evidence_id):
            proposal_ids.add(evidence_id)
    confirmations = plan.get("confirmations")
    if not isinstance(confirmations, list) or not confirmations:
        errors.append("confirmations must be a non-empty list")
        confirmations = []
    confirmed_ids = set()
    for index, item in enumerate(confirmations):
        if not isinstance(item, dict):
            errors.append(f"confirmations[{index}] must be an object")
            continue
        evidence_id = item.get("evidence_id")
        if evidence_id not in evidence_ids:
            errors.append(f"confirmations[{index}].evidence_id must reference evidence")
        else:
            confirmed_ids.add(evidence_id)
        if not text_present(item.get("confirmed_by")) or not text_present(item.get("date")):
            errors.append(f"confirmations[{index}] requires confirmed_by and date")
    unconfirmed = sorted(proposal_ids - confirmed_ids)
    if unconfirmed:
        errors.append("unconfirmed proposals: " + ", ".join(unconfirmed))
    if backend == "github_issues":
        github = plan.get("github")
        if not isinstance(github, dict) or github.get("usable") is not True:
            errors.append("github.usable must be true for github_issues")
    policy_errors = validate_policy(plan.get("policy"), require_pending=True)
    errors.extend(f"policy.{error}" for error in policy_errors)
    policy = plan.get("policy")
    if isinstance(policy, dict) and isinstance(policy.get("sections"), list):
        for index, section in enumerate(policy["sections"]):
            if not isinstance(section, dict):
                continue
            unknown_sources = sorted(set(section.get("source_ids", [])) - evidence_ids) if isinstance(section.get("source_ids"), list) else []
            if unknown_sources:
                errors.append(f"policy.sections[{index}].source_ids reference unknown evidence: {', '.join(unknown_sources)}")
            if section.get("id") == "backend":
                if section.get("decision") != backend:
                    errors.append("policy backend decision must equal backend")
                settings = section.get("settings")
                tradeoffs = settings.get("tradeoffs") if isinstance(settings, dict) else None
                if (
                    not isinstance(settings, dict)
                    or settings.get("fallback") != "forbidden"
                    or settings.get("repository_identity") != (repository or {}).get("identity")
                    or not text_present(settings.get("capability_evidence"))
                    or not isinstance(tradeoffs, dict)
                    or not all(text_present(tradeoffs.get(name)) for name in BACKENDS)
                ):
                    errors.append("policy backend settings must record capability evidence, both tradeoffs, repository identity, and forbidden fallback")
    return errors


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().casefold() != "unknown"


def text_present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(nonempty(item) for item in value)


def render_project(plan: dict[str, Any], revision: int) -> str:
    charter = plan["charter"]
    policy_state = json.loads(json.dumps(plan["policy"]))
    policy_state["evidence"] = plan["evidence"]
    state = {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "initialized": False,
        "backend": plan["backend"],
        "repository": plan["repository"],
        "revision": revision,
        "migration_pending": plan["migration_pending"],
        "policy": policy_state,
    }
    block = json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True)
    kpis = "\n".join(
        f"| {cell(k['name'])} | {cell(k['why'])} | {cell(k['baseline'])} | "
        f"{cell(k['target'])} | {cell(k['evidence'])} | {cell(k['cadence'])} |"
        for k in charter["kpis"]
    )
    bullets = lambda values: "\n".join(f"- {value}" for value in values)
    checks = "\n".join(f"- [x] {value}" for value in charter["acceptance_criteria"])
    policy = render_policy_sections(policy_state)
    return f"""# Project success charter

{PROJECT_BLOCK_START}
{block}
{PROJECT_BLOCK_END}

**Status:** incomplete — policy review required
**Last reviewed:** not yet

## Overall goal
- Outcome: {charter['outcome']}
- Primary beneficiaries: {', '.join(charter['beneficiaries'])}
- Why it matters: {charter['why_it_matters']}
- Time horizon: {charter['time_horizon']}

## Success metrics
| KPI | Why it matters | Baseline | Target / threshold | Evidence source | Review cadence |
| --- | --- | --- | --- | --- | --- |
{kpis}

## Project acceptance criteria
{checks}

## Value rubric
- `critical`: required for project acceptance, safety, or a binding deadline.
- `high`: materially moves a priority KPI or unlocks critical/high-value work.
- `medium`: useful measurable contribution with limited leverage.
- `low`: weak, speculative, cosmetic, or currently unmeasured contribution.

When KPIs conflict, prefer: {charter['precedence']}

## Constraints and non-goals
### Constraints
{bullets(charter['constraints'])}

### Non-goals
{bullets(charter['non_goals'])}

### Unacceptable tradeoffs
{bullets(charter['unacceptable_tradeoffs'])}

## Assumptions and open questions
- None recorded at initialization; add evidence-backed changes with history.

## Operating policy review
Read every section in this exact file. Each unchecked stable policy ID is a `decision` blocker. Only explicit user approval may check it; repository evidence or agent inference is not approval.

{policy}

## History
| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| {date.today().isoformat()} | ZzzOps initialization | Created pending revision {revision} | Confirmed agent-generated draft; exact-file policy review still required. |
"""


def render_policy_sections(policy: dict[str, Any]) -> str:
    rendered = []
    evidence = {
        item["id"]: f"{item['source']} — {item['finding']}"
        for item in policy.get("evidence", [])
        if isinstance(item, dict) and text_present(item.get("id"))
    }
    for section in policy["sections"]:
        approved = section["review"]["approved"] is True
        applicable = "applicable" if section["applicable"] else "not applicable"
        settings = json.dumps(section["settings"], ensure_ascii=False, sort_keys=True)
        rendered.append(
            f"- [{'x' if approved else ' '}] `[policy:{section['id']}]` **{section['title']}** ({applicable})\n"
            f"  - Decision: {section['decision']}\n"
            f"  - Rationale: {section['rationale']}\n"
            f"  - Sources: {'; '.join(f'{source_id}: {evidence.get(source_id, "missing citation")}' for source_id in section['source_ids'])}\n"
            f"  - Confidence/default: {section['confidence']}; {section['default_origin']} → {section['default_disposition']}\n"
            f"  - Settings: `{settings}`\n"
            f"  - Exceptions: {', '.join(section['exceptions']) or 'none'}\n"
            f"  - Unresolved: {', '.join(section['unresolved']) or 'none'}"
        )
    return "\n".join(rendered)


def cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def apply_plan(repo: Path, plan: dict[str, Any]) -> dict[str, Any]:
    errors = validate_plan(repo, plan)
    if errors:
        raise ValueError("Invalid initialization plan: " + "; ".join(errors))
    path, current = read_project(repo)
    old_state = parse_project_state(current)
    revision = int(old_state.get("revision", 0)) + 1 if old_state else 1
    rendered = render_project(plan, revision)
    if rendered == current:
        return {
            "changed": False, "path": str(path), "revision": revision,
            "preferences_command": "python .agents/zzzops.py",
        }
    atomic_text(path, rendered)
    return {
        "changed": True, "path": str(path), "revision": revision,
        "initialized": False,
        "decision_blockers": policy_blockers(plan["policy"]),
        "project_digest": project_digest(rendered),
        "review_required": "Read the exact PROJECT.md file, then explicitly approve its current digest.",
        "preferences_command": "python .agents/zzzops.py",
    }


def confirm_project(repo: Path, digest: str, reviewer: str, section_ids: list[str], approve_all: bool) -> dict[str, Any]:
    path, text = read_project(repo)
    if project_digest(text) != digest:
        raise ValueError("PROJECT.md digest changed; read the exact current file before confirming")
    state = parse_project_state(text)
    errors = validate_project_state(state)
    if errors:
        raise ValueError("Invalid project state: " + "; ".join(errors))
    if not text_present(reviewer):
        raise ValueError("reviewer is required")
    policy = state["policy"]
    available = {section["id"]: section for section in policy["sections"]}
    selected = list(available) if approve_all else section_ids
    if not selected:
        raise ValueError("select --all or at least one --section after explicit user approval")
    unknown = sorted(set(selected) - set(available))
    if unknown:
        raise ValueError("unknown policy sections: " + ", ".join(unknown))
    unresolved = [section_id for section_id in selected if available[section_id].get("unresolved")]
    if unresolved:
        raise ValueError("resolve policy choices before approval: " + ", ".join(unresolved))
    today = date.today().isoformat()
    for section_id in selected:
        section = available[section_id]
        section["review"] = {
            "approved": True,
            "reviewer": reviewer,
            "date": today,
            "reviewed_digest": digest,
        }
    blockers = policy_blockers(policy)
    state["initialized"] = not blockers
    state["revision"] += 1
    block = f"{PROJECT_BLOCK_START}\n{json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True)}\n{PROJECT_BLOCK_END}"
    updated = re.sub(
        re.escape(PROJECT_BLOCK_START) + r"\s*\n.*?\n" + re.escape(PROJECT_BLOCK_END),
        lambda _match: block,
        text,
        count=1,
        flags=re.DOTALL,
    )
    for section_id in selected:
        updated = re.sub(rf"^- \[ \](\s+`\[policy:{re.escape(section_id)}\]`)", r"- [x]\1", updated, flags=re.MULTILINE)
    if not blockers:
        updated = re.sub(r"^\*\*Status:\*\*.*$", "**Status:** complete", updated, flags=re.MULTILINE)
        updated = re.sub(r"^\*\*Last reviewed:\*\*.*$", f"**Last reviewed:** {today}", updated, flags=re.MULTILINE)
    history = f"| {today} | {reviewer} | Reviewed policy revision {state['revision']} | Approved: {', '.join(selected)}; source digest `{digest}`. |"
    updated = updated.rstrip() + "\n" + history + "\n"
    atomic_text(path, updated)
    return {
        "changed": True,
        "path": str(path),
        "revision": state["revision"],
        "initialized": state["initialized"],
        "decision_blockers": blockers,
        "project_digest": project_digest(updated),
    }


def edit_preferences(repo: Path) -> None:
    path, preferences = load_preferences(repo)
    fill = preferences["fill_backlog"]
    while True:
        print("\nBacklog refill preferences")
        for number, (key, label) in enumerate(PREFERENCE_LABELS, 1):
            print(f"  {number}. [{'x' if fill[key] else ' '}] {label}")
        print(f"  4. Maximum goals per refill: {fill['max_goals_per_refill']}")
        print("  s. Save and return")
        print("  q. Discard and return")
        choice = input("> ").strip().casefold()
        if choice in {"1", "2", "3"}:
            key = PREFERENCE_LABELS[int(choice) - 1][0]
            fill[key] = not fill[key]
        elif choice == "4":
            value = input("Maximum goals per refill (1-25): ").strip()
            if value.isdigit() and 1 <= int(value) <= 25:
                fill["max_goals_per_refill"] = int(value)
            else:
                print("Enter an integer from 1 to 25.")
        elif choice == "s":
            atomic_json(path, preferences)
            print(f"Saved local preferences to {path}")
            return
        elif choice == "q":
            print("No changes saved.")
            return
        else:
            print("Choose 1-4, s, or q.")


def edit_parallelization(repo: Path) -> None:
    path, preferences = load_preferences(repo)
    parallel = preferences["parallelization"]
    while True:
        print("\nParallelization preferences")
        for number, (value, label) in enumerate(PARALLEL_MODES, 1):
            print(f"  {number}. {'*' if parallel['mode'] == value else ' '} {label}")
        print(f"  4. Maximum workers: {parallel['max_workers']}")
        print("  s. Save and return")
        print("  q. Discard and return")
        choice = input("> ").strip().casefold()
        if choice in {"1", "2", "3"}:
            parallel["mode"] = PARALLEL_MODES[int(choice) - 1][0]
        elif choice == "4":
            value = input("Maximum workers (1-8): ").strip()
            if value.isdigit() and 1 <= int(value) <= 8:
                parallel["max_workers"] = int(value)
            else:
                print("Enter an integer from 1 to 8.")
        elif choice == "s":
            atomic_json(path, preferences)
            print(f"Saved local preferences to {path}")
            return
        elif choice == "q":
            print("No changes saved.")
            return
        else:
            print("Choose 1-4, s, or q.")


def nested_get(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = data
    for key in path:
        current = current[key]
    return current


def nested_set(data: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = data
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value


def edit_health_preferences() -> None:
    path, preferences = load_user_health_preferences()
    while True:
        print(f"\nUser health preferences ({path})")
        print("Disabled by default; timestamps/state are machine-local and no sandbox is bypassed.")
        for number, (field, label, _kind, _options) in enumerate(HEALTH_FIELDS, 1):
            print(f"  {number}. {label}: {nested_get(preferences, field)}")
        print("  s. Save and return")
        print("  r. Reset to opt-in defaults")
        print("  q. Discard and return")
        choice = input("> ").strip().casefold()
        if choice == "q":
            print("No changes saved.")
            return
        if choice == "r":
            preferences = health.default_preferences()
            continue
        if choice == "s":
            errors = health.validate_preferences(preferences)
            if errors:
                print("Cannot save: " + "; ".join(errors))
                continue
            try:
                private_atomic_json(path, preferences)
            except OSError as exc:
                print(json.dumps(storage_error(exc, path), indent=2))
                return
            print(f"Saved user health preferences to {path}")
            return
        if not choice.isdigit() or not 1 <= int(choice) <= len(HEALTH_FIELDS):
            print(f"Choose 1-{len(HEALTH_FIELDS)}, s, r, or q.")
            continue
        field, label, kind, options = HEALTH_FIELDS[int(choice) - 1]
        current = nested_get(preferences, field)
        if kind == "bool":
            nested_set(preferences, field, not current)
            continue
        raw = input(f"{label} [{current}]: ").strip()
        if not raw:
            continue
        if kind == "int":
            low, high = options
            if not raw.isdigit() or not low <= int(raw) <= high:
                print(f"Enter an integer from {low} to {high}.")
                continue
            value: Any = int(raw)
        elif kind == "days":
            try:
                value = [int(item.strip()) for item in raw.split(",")]
            except ValueError:
                print("Enter comma-separated integers from 0 to 6.")
                continue
        elif kind == "choice":
            if raw not in options:
                print("Choose " + ", ".join(options) + ".")
                continue
            value = raw
        else:
            value = raw
        nested_set(preferences, field, value)


def health_status() -> dict[str, Any]:
    preferences_path, preferences = load_user_health_preferences()
    state_path, state = load_machine_health_state()
    return {
        "ok": True,
        "enabled": preferences["enabled"],
        "preferences_path": str(preferences_path),
        "preferences_exists": preferences_path.exists(),
        "state_path": str(state_path),
        "state_exists": state_path.exists(),
        "activity_precision": state.get("activity_precision"),
        "last_activity_at": state.get("last_activity_at"),
        "snoozed_until": state.get("snoozed_until"),
    }


def health_check(now_value: str | None, activity_timestamp: str | None, precision: str) -> dict[str, Any]:
    preferences_path, preferences = load_user_health_preferences()
    state_path, state = load_machine_health_state()
    now = datetime.now(timezone.utc) if now_value is None else health._parse_instant(now_value)
    if now is None:
        raise ValueError("--now must be an ISO-8601 instant with an offset")
    activity = None
    if activity_timestamp is not None:
        activity = {"timestamp": activity_timestamp, "precision": precision}
    decision, updated = health.evaluate(now, activity, preferences, state)
    if updated != state:
        try:
            private_atomic_json(state_path, updated)
        except OSError as exc:
            return storage_error(exc, state_path)
    return {
        "ok": True,
        "decision": decision,
        "preferences_path": str(preferences_path),
        "state_path": str(state_path),
    }


def health_reset(include_preferences: bool) -> dict[str, Any]:
    paths = [machine_health_state_path()]
    if include_preferences:
        paths.append(user_health_preferences_path())
    removed = []
    for path in paths:
        try:
            if path.exists():
                path.unlink()
                removed.append(str(path))
        except OSError as exc:
            return storage_error(exc, path)
    return {"ok": True, "removed": removed}


def health_snooze(minutes: int | None, now_value: str | None) -> dict[str, Any]:
    _preferences_path, preferences = load_user_health_preferences()
    state_path, state = load_machine_health_state()
    duration = preferences["delivery"]["snooze_minutes"] if minutes is None else minutes
    if not 1 <= duration <= 1440:
        raise ValueError("--minutes must be from 1 to 1440")
    now = datetime.now(timezone.utc) if now_value is None else health._parse_instant(now_value)
    if now is None:
        raise ValueError("--now must be an ISO-8601 instant with an offset")
    until = now + timedelta(minutes=duration)
    state["snoozed_until"] = health._iso(until)
    try:
        private_atomic_json(state_path, state)
    except OSError as exc:
        return storage_error(exc, state_path)
    return {"ok": True, "snoozed_until": health._iso(until), "state_path": str(state_path)}


def health_resume() -> dict[str, Any]:
    state_path, state = load_machine_health_state()
    if not state_path.exists():
        return {"ok": True, "changed": False, "state_path": str(state_path)}
    changed = state.get("snoozed_until") is not None
    state["snoozed_until"] = None
    if changed:
        try:
            private_atomic_json(state_path, state)
        except OSError as exc:
            return storage_error(exc, state_path)
    return {"ok": True, "changed": changed, "state_path": str(state_path)}


def interactive(repo: Path) -> None:
    while True:
        print("\nZzzOps control panel")
        print("  1. Edit preferences")
        print("  2. Edit parallelization")
        print("  3. Edit user health preferences")
        print("  q. Exit")
        choice = input("> ").strip().casefold()
        if choice == "1":
            edit_preferences(repo)
        elif choice == "2":
            edit_parallelization(repo)
        elif choice == "3":
            edit_health_preferences()
        elif choice == "q":
            return
        else:
            print("Choose 1, 2, 3, or q.")


def main() -> int:
    parser = argparse.ArgumentParser(description="ZzzOps control panel")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Project root (default: current directory)")
    commands = parser.add_subparsers(dest="command")
    init = commands.add_parser("init", help="Inspect, validate, or apply agent-driven project initialization")
    init_commands = init.add_subparsers(dest="init_command", required=True)
    inspect_command = init_commands.add_parser("inspect", help="Report initialization state and read-only capabilities")
    inspect_command.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    validate_command = init_commands.add_parser("validate", help="Validate an agent-generated initialization plan")
    validate_command.add_argument("--plan", type=Path, required=True)
    apply_command = init_commands.add_parser("apply", help="Atomically apply a confirmed initialization plan")
    apply_command.add_argument("--plan", type=Path, required=True)
    confirm_command = init_commands.add_parser("confirm", help="Confirm explicit review of the exact current PROJECT.md")
    confirm_command.add_argument("--project-digest", required=True)
    confirm_command.add_argument("--reviewer", required=True)
    confirm_command.add_argument("--section", action="append", default=[])
    confirm_command.add_argument("--all", action="store_true", help="Approve every current policy section")
    portfolio_parser = commands.add_parser("portfolio", help="Read and audit the canonical goal portfolio once")
    portfolio_parser.add_argument("--format", dest="output_format", choices=("summary", "json"), default="summary")
    portfolio_parser.add_argument("--include-done", action="store_true", help="Include terminal goals in summary output")
    portfolio_parser.add_argument("--as-of", help="Injected ISO-8601 audit instant for deterministic claim checks")
    portfolio_parser.add_argument("--compare", type=Path, help="Prior JSON snapshot used only to report digest/revision drift")
    health_parser = commands.add_parser("health", help="Inspect or operate opt-in user health support")
    health_commands = health_parser.add_subparsers(dest="health_command", required=True)
    health_commands.add_parser("status", help="Show user preference and machine-state capability without writes")
    check_command = health_commands.add_parser("check", help="Evaluate one health hook")
    check_command.add_argument("--now", help="Injected ISO-8601 current instant (default: system UTC)")
    check_command.add_argument("--activity-timestamp", help="Optional ISO-8601 activity instant")
    check_command.add_argument("--precision", choices=sorted(health.PRECISIONS), default="current_only")
    record_command = health_commands.add_parser("record", help="Record qualified activity and evaluate one hook")
    record_command.add_argument("--now", help="Injected ISO-8601 current instant (default: system UTC)")
    record_command.add_argument("--activity-timestamp", required=True, help="ISO-8601 activity instant")
    record_command.add_argument("--precision", choices=("exact_message", "observed_receipt"), required=True)
    reset_command = health_commands.add_parser("reset", help="Delete machine health state")
    reset_command.add_argument("--preferences", action="store_true", help="Also delete user health preferences")
    snooze_command = health_commands.add_parser("snooze", help="Suppress health nudges temporarily")
    snooze_command.add_argument("--minutes", type=int, help="Override the configured snooze duration")
    snooze_command.add_argument("--now", help="Injected ISO-8601 current instant (tests/harnesses)")
    health_commands.add_parser("resume", help="Clear the current snooze")
    args = parser.parse_args()
    repo = args.repo.resolve()
    if not (repo / ".agents" / "templates" / "project-goals" / "PREFERENCES.json").is_file():
        print(f"ERROR: ZzzOps is not installed at {repo}")
        return 2
    try:
        if args.command == "init":
            if args.init_command == "inspect":
                result = inspect_initialization(repo)
                print(json.dumps(result, indent=2, ensure_ascii=False))
            elif args.init_command in {"validate", "apply"}:
                plan = load_plan(args.plan.resolve())
                if args.init_command == "validate":
                    errors = validate_plan(repo, plan)
                    print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
                    return 0 if not errors else 2
                result = apply_plan(repo, plan)
                print(json.dumps(result, indent=2))
            else:
                result = confirm_project(repo, args.project_digest, args.reviewer, args.section, args.all)
                print(json.dumps(result, indent=2))
        elif args.command == "portfolio":
            try:
                as_of = None
                if args.as_of:
                    as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
                    if as_of.tzinfo is None:
                        raise ValueError("--as-of must include a timezone")
                result = portfolio_snapshot(repo, as_of)
                if args.compare:
                    prior = json.loads(args.compare.resolve().read_text(encoding="utf-8-sig"))
                    result["changes"] = compare_portfolios(result, prior)
                if args.output_format == "json":
                    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
                else:
                    print(render_portfolio_summary(result, args.include_done))
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                if args.output_format == "json":
                    print(json.dumps({"schema_version": PORTFOLIO_SCHEMA_VERSION, "complete": False, "valid": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
                else:
                    print(f"ERROR: {exc}")
                return 2
        elif args.command == "health":
            if args.health_command == "status":
                result = health_status()
            elif args.health_command in {"check", "record"}:
                result = health_check(args.now, args.activity_timestamp, args.precision)
            elif args.health_command == "reset":
                result = health_reset(args.preferences)
            elif args.health_command == "snooze":
                result = health_snooze(args.minutes, args.now)
            else:
                result = health_resume()
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result.get("ok") else 2
        else:
            interactive(repo)
    except (EOFError, KeyboardInterrupt):
        print("\nNo further changes made.")
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
