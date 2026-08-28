#!/usr/bin/env python3
"""Privacy-safe ZzzOps execution-report and feedback mechanics."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

GOAL_SCHEMA_VERSION = 1
_atomic_text: Callable[[Path, str], None] | None = None
_render_managed_goal: Callable[[dict[str, Any], str], str] | None = None
_package_provenance: Callable[[Path | None], dict[str, str]] | None = None

def configure_entrypoint(
    *, atomic_text: Callable[[Path, str], None], render_managed_goal: Callable[[dict[str, Any], str], str],
    package_provenance: Callable[[Path | None], dict[str, str]],
) -> None:
    """Provide the core helpers required by this acyclic module."""
    global _atomic_text, _render_managed_goal, _package_provenance
    _atomic_text = atomic_text
    _render_managed_goal = render_managed_goal
    _package_provenance = package_provenance

def _require_configured() -> tuple[Callable[[Path, str], None], Callable[[dict[str, Any], str], str]]:
    if _atomic_text is None or _render_managed_goal is None:
        raise RuntimeError("Feedback module was not configured by the ZzzOps entry point")
    return _atomic_text, _render_managed_goal

EXECUTION_REPORT_SCHEMA_VERSION = 3
LEGACY_EXECUTION_REPORT_SCHEMA_VERSION = 2
EXECUTION_REPORT_TARGET = "david-rzepa/zzzops"
EXECUTION_REPORT_TITLE = "ZzzOps feedback"
EXECUTION_REPORT_LABELS = ["zzzops", "zzzops-feedback", "zzzops:schema:v1", "zzzops:status:new", "zzzops:priority:P2"]
EXECUTION_REPORT_WORKFLOWS = {
    "add-zzzops-goal", "execute-zzzops", "migrate-to-zzzops", "review-zzzops-policy",
    "run-zzzops-acceptance", "send-zzzops-feedback", "suggest-zzzops-work",
}
EXECUTION_REPORT_AGENTS = {"codex", "claude", "unknown"}
EXECUTION_REPORT_ISSUES = {
    "avoidable_wait", "continuation_stall", "excessive_prompt_load", "excessive_token_use",
    "poor_tool_choice", "redundant_update", "repeated_tool_call", "unnecessary_question",
}
EXECUTION_REPORT_CAUSES = {
    "child_process_auth_unavailable": {
        "title": "Authentication was unavailable to a child process",
        "surface": "Provider authentication across process and sandbox boundaries",
        "observed": "A provider command succeeded in the parent shell but authentication was unavailable when the same provider was invoked by a child process.",
        "recovery": "Run the provider call in the authenticated execution context or use the approved escalation path.",
        "investigation": "Detect credential-boundary mismatches before selecting a subprocess-based workflow.",
    },
    "command_failed_after_external_write": {
        "title": "A command failed after completing an external write",
        "surface": "Provider command output handling",
        "observed": "The external write completed, but later formatting or response handling made the command report failure.",
        "recovery": "Read the provider state before retrying so the write is not duplicated.",
        "investigation": "Separate write success from output formatting and validate provider responses without masking the created resource.",
    },
    "interactive_question_during_execution": {
        "title": "An interactive question paused autonomous execution",
        "surface": "Agent interaction during an authorized execution loop",
        "observed": "The agent asked for input even though the active workflow allowed it to continue safely.",
        "recovery": "Continue after the prompt times out or the user supplies the unnecessary response.",
        "investigation": "Tighten execution-mode prompting so questions are reserved for consequential missing authority or decisions.",
    },
    "powershell_argument_encoding": {
        "title": "PowerShell changed argument or text encoding",
        "surface": "PowerShell argument and text transport",
        "observed": "PowerShell passed command arguments or text bytes differently from the payload the workflow constructed.",
        "recovery": "Use a UTF-8 file or a bounded helper process that preserves exact bytes.",
        "investigation": "Standardize cross-platform byte transport and verify the received payload before external writes.",
    },
    "powershell_stdin_bom": {
        "title": "PowerShell added a byte-order mark to standard input",
        "surface": "PowerShell standard-input encoding",
        "observed": "An unexpected UTF-8 byte-order mark changed the bytes supplied on standard input.",
        "recovery": "Use BOM-tolerant input decoding or a byte-preserving UTF-8 input path.",
        "investigation": "Normalize standard-input decoding and include empty-input and BOM cases in exact-payload tests.",
    },
    "redundant_state_summary": {
        "title": "The agent repeated an unnecessary state summary",
        "surface": "Agent progress communication",
        "observed": "The agent restated workflow state without a new result, decision, risk, or required user action.",
        "recovery": "Resume execution after the redundant update.",
        "investigation": "Make progress updates outcome-driven and suppress summaries that do not help the user decide or act.",
    },
    "repeated_equivalent_tool_call": {
        "title": "The agent repeated an equivalent tool call",
        "surface": "Agent tool selection and state reuse",
        "observed": "The agent repeated a read or probe even though the prior result was still current and sufficient.",
        "recovery": "Reuse the existing observation and continue from the established state.",
        "investigation": "Preserve tool results across workflow steps and make refresh triggers explicit.",
    },
    "shell_quoting_failure": {
        "title": "Shell quoting changed an inline command",
        "surface": "Cross-shell command construction",
        "observed": "Shell parsing changed quoted inline code before the intended process could execute it.",
        "recovery": "Use a securely created temporary file or a simpler native command interface.",
        "investigation": "Avoid nested inline programs across shell boundaries and test exact argument transport on supported platforms.",
    },
    "unavailable_tool_selected": {
        "title": "The workflow selected a tool that was unavailable",
        "surface": "Capability discovery and tool routing",
        "observed": "The workflow attempted a tool path before establishing that the required capability was available.",
        "recovery": "Use the discovered available capability or stop once with an actionable blocker.",
        "investigation": "Move capability discovery ahead of tool selection and reuse the discovered result.",
    },
    "unnecessary_wait_for_timeout": {
        "title": "Waited for an avoidable timeout",
        "surface": "Agent continuation and interactive waits",
        "observed": "Execution waited for a timeout even though the workflow already had enough authority and information to continue.",
        "recovery": "Continue automatically when the wait is not protecting a real decision or external state change.",
        "investigation": "Distinguish required waits from optional interaction and bypass the latter during autonomous execution.",
    },
}
EXECUTION_REPORT_PHASES = {
    "capture", "discovery", "handoff", "implementation", "installation", "migration",
    "policy_review", "triage", "unblocking", "verification",
}
EXECUTION_REPORT_V2_FIELDS = {
    "schema_version", "id", "created_at", "workflow", "agent", "issue", "cause", "phase",
    "occurrences", "impact",
}
EXECUTION_REPORT_FIELDS = EXECUTION_REPORT_V2_FIELDS | {"zzzops"}
EXECUTION_REPORT_ID = re.compile(r"^report-[0-9a-f]{64}$")
ZZZOPS_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
ZZZOPS_REVISION = re.compile(r"^[0-9a-f]{40,64}$")

def execution_reports_enabled(project: dict[str, Any]) -> bool:
    sections = ((project.get("policy") or {}).get("sections") if isinstance(project.get("policy"), dict) else None)
    section = next((item for item in sections or [] if isinstance(item, dict) and item.get("id") == "autonomy_approval_parallelism"), None)
    settings = section.get("settings") if isinstance(section, dict) else None
    configured = settings.get("execution_reports") if isinstance(settings, dict) else None
    if not isinstance(configured, dict):
        raise ValueError("Reviewed project policy execution_reports must be an object")
    enabled = configured.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("Reviewed project policy execution_reports.enabled must be boolean")
    return enabled


def execution_report_directory(repo: Path) -> Path:
    return repo / ".zzzops" / "execution-reports"


def _bounded_count(value: Any, field: str, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= 1_000_000_000:
        raise ValueError(f"{field} must be an integer from {minimum} to 1000000000")
    return value


def execution_report_id(report: dict[str, Any]) -> str:
    payload = {key: value for key, value in report.items() if key != "id"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "report-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validated_zzzops_provenance(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"version", "revision"}:
        raise ValueError("zzzops provenance must contain only version and revision")
    version, revision = value.get("version"), value.get("revision")
    if not isinstance(version, str) or not ZZZOPS_VERSION.fullmatch(version):
        raise ValueError("zzzops version is invalid")
    if not isinstance(revision, str) or not ZZZOPS_REVISION.fullmatch(revision):
        raise ValueError("zzzops revision must be an exact 40-64 character lowercase Git revision")
    return {"version": version, "revision": revision}


def zzzops_provenance(repo: Path) -> dict[str, str]:
    if _package_provenance is None:
        raise RuntimeError("Feedback module was not configured with Agent Plugin provenance")
    return _validated_zzzops_provenance(_package_provenance(repo))


def validate_execution_report(report: Any) -> list[str]:
    if not isinstance(report, dict):
        return ["execution report must be an object"]
    errors: list[str] = []
    schema_version = report.get("schema_version")
    expected_fields = EXECUTION_REPORT_V2_FIELDS if schema_version == LEGACY_EXECUTION_REPORT_SCHEMA_VERSION else EXECUTION_REPORT_FIELDS
    unknown = sorted(set(report) - expected_fields)
    missing = sorted(expected_fields - set(report))
    if unknown:
        errors.append("unknown execution report fields: " + ", ".join(unknown))
    if missing:
        errors.append("missing execution report fields: " + ", ".join(missing))
    if schema_version not in {LEGACY_EXECUTION_REPORT_SCHEMA_VERSION, EXECUTION_REPORT_SCHEMA_VERSION}:
        errors.append(f"schema_version must be {LEGACY_EXECUTION_REPORT_SCHEMA_VERSION} or {EXECUTION_REPORT_SCHEMA_VERSION}")
    if schema_version == EXECUTION_REPORT_SCHEMA_VERSION:
        try:
            _validated_zzzops_provenance(report.get("zzzops"))
        except ValueError as exc:
            errors.append(str(exc))
    report_id = report.get("id")
    if not isinstance(report_id, str) or not EXECUTION_REPORT_ID.fullmatch(report_id):
        errors.append("id must use the constrained report identifier format")
    elif report_id != execution_report_id(report):
        errors.append("id must be content-addressed; execution reports are immutable")
    created_at = report.get("created_at")
    try:
        parsed = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
    except ValueError:
        errors.append("created_at must be an ISO-8601 timestamp with timezone")
    for field, allowed in (
        ("workflow", EXECUTION_REPORT_WORKFLOWS),
        ("agent", EXECUTION_REPORT_AGENTS),
        ("issue", EXECUTION_REPORT_ISSUES),
        ("cause", EXECUTION_REPORT_CAUSES),
        ("phase", EXECUTION_REPORT_PHASES),
    ):
        if report.get(field) not in allowed:
            errors.append(f"{field} is invalid")
    try:
        _bounded_count(report.get("occurrences"), "occurrences", 1)
    except ValueError as exc:
        errors.append(str(exc))
    impact = report.get("impact")
    expected_impact = {"wait_seconds", "extra_tool_calls", "estimated_tokens"}
    if not isinstance(impact, dict) or set(impact) != expected_impact:
        errors.append("impact must contain only wait_seconds, extra_tool_calls, and estimated_tokens")
    else:
        for field in sorted(expected_impact):
            try:
                _bounded_count(impact.get(field), field)
            except ValueError as exc:
                errors.append(str(exc))
    return errors


def record_execution_report(
    repo: Path, project: dict[str, Any], *, workflow: str, agent: str, issue: str, cause: str, phase: str,
    occurrences: int = 1, wait_seconds: int = 0, extra_tool_calls: int = 0,
    estimated_tokens: int = 0, now: datetime | None = None, provenance: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not execution_reports_enabled(project):
        return {"recorded": False, "reason": "disabled"}
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("report timestamp must include a timezone")
    report = {
        "schema_version": EXECUTION_REPORT_SCHEMA_VERSION,
        "created_at": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "workflow": workflow,
        "agent": agent,
        "issue": issue,
        "cause": cause,
        "phase": phase,
        "occurrences": occurrences,
        "zzzops": _validated_zzzops_provenance(provenance) if provenance is not None else zzzops_provenance(repo),
        "impact": {
            "wait_seconds": wait_seconds,
            "extra_tool_calls": extra_tool_calls,
            "estimated_tokens": estimated_tokens,
        },
    }
    report_id = execution_report_id(report)
    report["id"] = report_id
    errors = validate_execution_report(report)
    if errors:
        raise ValueError("Invalid execution report: " + "; ".join(errors))
    path = execution_report_directory(repo) / f"{report_id}.json"
    if path.exists():
        raise ValueError(f"execution report already exists: {report_id}")
    atomic_text, _ = _require_configured()
    atomic_text(path, json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return {"recorded": True, "id": report_id, "path": str(path)}


def load_execution_reports(repo: Path, report_ids: list[str] | None = None) -> list[dict[str, Any]]:
    directory = execution_report_directory(repo)
    requested = None if report_ids is None else set(report_ids)
    if requested is not None:
        for report_id in requested:
            if not isinstance(report_id, str) or not EXECUTION_REPORT_ID.fullmatch(report_id):
                raise ValueError(f"invalid execution report id: {report_id}")
    reports: list[dict[str, Any]] = []
    if directory.is_dir():
        for path in sorted(directory.glob("report-*.json")):
            try:
                report = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"Could not read execution report {path.name}: {type(exc).__name__}") from exc
            errors = validate_execution_report(report)
            if errors or path.name != f"{report.get('id')}.json":
                detail = "; ".join(errors) if errors else "filename does not match id"
                raise ValueError(f"Invalid execution report {path.name}: {detail}")
            if requested is None or report["id"] in requested:
                reports.append(report)
    if requested is not None:
        missing = sorted(requested - {report["id"] for report in reports})
        if missing:
            raise ValueError("unknown execution report ids: " + ", ".join(missing))
    return reports


def prepare_feedback(repo: Path, prompt: str, report_ids: list[str] | None = None) -> dict[str, Any]:
    if not isinstance(prompt, str):
        raise ValueError("feedback prompt must be text")
    reports = load_execution_reports(repo, report_ids)
    if not prompt.strip() and not reports:
        raise ValueError("feedback requires prompt text or at least one execution report")
    report_json = json.dumps(reports, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    feedback_text = prompt if prompt.strip() else "(none)"
    grouped: dict[tuple[str, str], dict[str, int]] = {}
    for report in reports:
        if report["schema_version"] == LEGACY_EXECUTION_REPORT_SCHEMA_VERSION:
            build = "Unknown (schema v2 predates version provenance)"
        else:
            build = f"{report['zzzops']['version']} (revision {report['zzzops']['revision']})"
        totals = grouped.setdefault(
            (report["cause"], build),
            {"occurrences": 0, "wait_seconds": 0, "extra_tool_calls": 0, "estimated_tokens": 0},
        )
        totals["occurrences"] += report["occurrences"]
        for field in ("wait_seconds", "extra_tool_calls", "estimated_tokens"):
            totals[field] += report["impact"][field]
    narratives = []
    for cause, build in sorted(grouped):
        account = EXECUTION_REPORT_CAUSES[cause]
        totals = grouped[(cause, build)]
        impact_parts = []
        for field, singular, plural in (
            ("occurrences", "occurrence", "occurrences"),
            ("wait_seconds", "second waiting", "seconds waiting"),
            ("extra_tool_calls", "extra tool call", "extra tool calls"),
            ("estimated_tokens", "estimated token", "estimated tokens"),
        ):
            value = totals[field]
            impact_parts.append(f"{value} {singular if value == 1 else plural}")
        impact = "; ".join(impact_parts)
        narratives.append(
            f"### {account['title']}\n\n"
            f"**ZzzOps build:** {build}\n\n"
            f"**Machinery surface:** {account['surface']}\n\n"
            f"**Observed:** {account['observed']}\n\n"
            f"**Measured impact:** {impact}.\n\n"
            f"**Typical recovery:** {account['recovery']}\n\n"
            f"**Suggested investigation:** {account['investigation']}"
        )
    narrative_text = "\n\n".join(narratives) if narratives else "No archived execution reports were included."
    body = (
        "## User feedback\n\n"
        f"{feedback_text}\n\n"
        "## Machinery observations\n\n"
        "These natural-language accounts are rendered from constrained machinery-only cause codes. "
        "Observed behavior and measured impact come from the archived records; recovery and investigation text are fixed guidance, not project evidence.\n\n"
        f"{narrative_text}\n\n"
        "<details>\n<summary>Immutable structured reports</summary>\n\n"
        "```json\n"
        f"{report_json}\n"
        "```\n\n</details>\n"
    )
    feedback_goal = {
        "schema_version": GOAL_SCHEMA_VERSION,
        "status": "new", "priority": "P2", "value": "medium",
        "difficulty": "unknown", "confidence": "low",
        "parent": None, "depends_on": [], "claim": None, "blockers": [],
        "evidence": ["User-submitted ZzzOps feedback"],
        "next_action": "Triage this feedback against ZzzOps mechanisms and decide whether it warrants implementation.",
        "revision": 1, "implementation": None, "resources": [],
    }
    _, render_managed_goal = _require_configured()
    body = render_managed_goal(feedback_goal, body)
    selected = [report["id"] for report in reports]
    canonical = json.dumps({
        "target": EXECUTION_REPORT_TARGET, "title": EXECUTION_REPORT_TITLE,
        "body": body, "labels": EXECUTION_REPORT_LABELS, "report_ids": selected,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "target": EXECUTION_REPORT_TARGET,
        "title": EXECUTION_REPORT_TITLE,
        "body": body,
        "labels": list(EXECUTION_REPORT_LABELS),
        "report_ids": selected,
        "digest": "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def submit_feedback(
    repo: Path, prompt: str, confirmation: str, report_ids: list[str] | None = None,
) -> dict[str, Any]:
    prepared = prepare_feedback(repo, prompt, report_ids)
    if not isinstance(confirmation, str) or not hmac.compare_digest(confirmation, prepared["digest"]):
        raise ValueError("feedback confirmation does not match the exact current payload")
    executable = shutil.which("gh")
    if not executable:
        raise ValueError("GitHub CLI is unavailable")
    command = [
        executable, "issue", "create", "--repo", prepared["target"],
        "--title", prepared["title"], "--body-file", "-",
    ]
    for label in prepared["labels"]:
        command.extend(("--label", label))
    try:
        result = subprocess.run(
            command, cwd=repo, input=prepared["body"], text=True, encoding="utf-8",
            capture_output=True, timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Feedback submission failed: {type(exc).__name__}") from exc
    if result.returncode:
        raise ValueError("Feedback submission failed: " + (result.stderr.strip() or "unknown gh error"))
    url = result.stdout.strip()
    expected_prefix = f"https://github.com/{prepared['target']}/issues/"
    if not url.startswith(expected_prefix):
        raise ValueError("Feedback submission returned an unexpected issue URL; reports were retained")
    deleted: list[str] = []
    retained: list[str] = []
    for report_id in prepared["report_ids"]:
        try:
            load_execution_reports(repo, [report_id])
            (execution_report_directory(repo) / f"{report_id}.json").unlink()
            deleted.append(report_id)
        except (OSError, ValueError):
            retained.append(report_id)
    return {
        "submitted": True, "url": url,
        "deleted_report_ids": deleted, "retained_report_ids": retained,
    }
