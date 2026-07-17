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
PROJECT_BLOCK_START = "<!-- zzzops-project-state"
PROJECT_BLOCK_END = "zzzops-project-state -->"
GOAL_BLOCK_START = "<!-- zzzops-goal"
GOAL_BLOCK_END = "zzzops-goal -->"
BACKENDS = {"github_issues", "local_files"}
GOAL_FIELDS = {
    "id", "title", "status", "priority", "value", "difficulty", "confidence",
    "parent", "depends_on", "blocks", "needs_human", "claim", "blockers",
    "evidence", "next_action", "revision",
}

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


def read_project(repo: Path) -> tuple[Path, str]:
    path = repo / "goals" / "PROJECT.md"
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
    allowed = {"schema_version", "initialized", "backend", "repository", "revision", "migration_pending"}
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
    if state.get("initialized") is True:
        if state.get("backend") not in BACKENDS:
            errors.append("initialized backend must be github_issues or local_files")
        repository = state.get("repository")
        if not isinstance(repository, dict) or not nonempty(repository.get("identity")):
            errors.append("initialized repository.identity is required")
    elif state.get("backend") is not None or state.get("repository") is not None or state.get("migration_pending") is not False:
        errors.append("uninitialized state cannot select a backend, repository, or migration")
    return errors


def parse_managed_goal(text: str) -> dict[str, Any] | None:
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
    errors = validate_managed_goal(goal)
    if errors:
        raise ValueError("Invalid managed goal: " + "; ".join(errors))
    return goal


def validate_managed_goal(goal: Any) -> list[str]:
    if not isinstance(goal, dict):
        return ["managed goal must be an object"]
    errors = []
    unknown = sorted(set(goal) - GOAL_FIELDS)
    if unknown:
        errors.append("unknown fields: " + ", ".join(unknown))
    required_text = ("id", "title", "status", "priority", "value", "difficulty", "confidence", "next_action")
    for field in required_text:
        if not text_present(goal.get(field)):
            errors.append(f"{field} is required")
    for field in ("depends_on", "blocks", "blockers", "evidence"):
        if not isinstance(goal.get(field), list):
            errors.append(f"{field} must be a list")
    if not isinstance(goal.get("needs_human"), bool):
        errors.append("needs_human must be boolean")
    if not isinstance(goal.get("revision"), int) or isinstance(goal.get("revision"), bool) or goal.get("revision", 0) < 1:
        errors.append("revision must be a positive integer")
    return errors


def render_managed_goal(goal: dict[str, Any], body: str = "") -> str:
    errors = validate_managed_goal(goal)
    if errors:
        raise ValueError("Invalid managed goal: " + "; ".join(errors))
    block = f"{GOAL_BLOCK_START}\n{json.dumps(goal, indent=2, ensure_ascii=False, sort_keys=True)}\n{GOAL_BLOCK_END}"
    pattern = re.compile(
        re.escape(GOAL_BLOCK_START) + r"\s*\n.*?\n" + re.escape(GOAL_BLOCK_END),
        re.DOTALL,
    )
    if pattern.search(body):
        return pattern.sub(lambda _match: block, body, count=1)
    separator = "\n\n" if body and not body.endswith("\n\n") else ""
    return f"{body}{separator}{block}\n"


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
        "initialized": bool(state and state.get("initialized") is True),
        "valid_state": error is None and state is not None,
        "state_error": error,
        "missing_charter_fields": charter_missing_fields(text),
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
        "charter", "evidence", "confirmations", "github", "migration_pending",
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
    return errors


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().casefold() != "unknown"


def text_present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(nonempty(item) for item in value)


def render_project(plan: dict[str, Any], revision: int) -> str:
    charter = plan["charter"]
    state = {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "initialized": True,
        "backend": plan["backend"],
        "repository": plan["repository"],
        "revision": revision,
        "migration_pending": plan["migration_pending"],
    }
    block = json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True)
    kpis = "\n".join(
        f"| {cell(k['name'])} | {cell(k['why'])} | {cell(k['baseline'])} | "
        f"{cell(k['target'])} | {cell(k['evidence'])} | {cell(k['cadence'])} |"
        for k in charter["kpis"]
    )
    bullets = lambda values: "\n".join(f"- {value}" for value in values)
    checks = "\n".join(f"- [x] {value}" for value in charter["acceptance_criteria"])
    return f"""# Project success charter

{PROJECT_BLOCK_START}
{block}
{PROJECT_BLOCK_END}

**Status:** complete
**Last reviewed:** {date.today().isoformat()}

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

## History
| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| {date.today().isoformat()} | ZzzOps initialization | Initialized revision {revision} | Confirmed agent-generated plan; backend `{plan['backend']}`. |
"""


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
        "preferences_command": "python .agents/zzzops.py",
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
            else:
                plan = load_plan(args.plan.resolve())
                if args.init_command == "validate":
                    errors = validate_plan(repo, plan)
                    print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
                    return 0 if not errors else 2
                result = apply_plan(repo, plan)
                print(json.dumps(result, indent=2))
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
