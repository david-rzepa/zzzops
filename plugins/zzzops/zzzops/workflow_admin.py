"""Public administrative intent handlers for the ZzzOps workflow entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any


FEEDBACK_SOURCE = "$send-zzzops-feedback"
SUGGEST_SOURCE = "$suggest-zzzops-work"
CAPTURE_SOURCE = "$add-zzzops-goal"


def _root_id(runtime: Any) -> str | None:
    if not isinstance(runtime, dict):
        return None
    value = runtime.get("root_id")
    return value if isinstance(value, str) and value.strip() else None


def _goal_create_contract(api: Any) -> tuple[int, list[str]]:
    goals = getattr(api, "_goals", None)
    version = getattr(api, "GOAL_CREATE_SCHEMA_VERSION", None)
    fields = getattr(api, "GOAL_CREATE_FIELDS", None)
    if version is None and goals is not None:
        version = getattr(goals, "GOAL_CREATE_SCHEMA_VERSION", None)
    if fields is None and goals is not None:
        fields = getattr(goals, "GOAL_CREATE_FIELDS", None)
    if not isinstance(version, int) or not isinstance(fields, (set, frozenset)):
        raise ValueError("The public goal-create schema is unavailable")
    return version, sorted(fields)


def _feedback_selection(payload: dict[str, Any]) -> tuple[str, list[str] | None, str | None, dict[str, str] | None]:
    prompt = payload.get("prompt")
    report_ids = payload.get("report_ids")
    diagnostic_id = payload.get("diagnostic_id")
    diagnostic_runtime = payload.get("diagnostic_runtime")
    if not isinstance(prompt, str):
        raise ValueError("feedback prompt must be text")
    if report_ids is not None and (
        not isinstance(report_ids, list) or any(not isinstance(item, str) for item in report_ids)
    ):
        raise ValueError("feedback report_ids must be a list of identifiers or null")
    if diagnostic_id is not None and not isinstance(diagnostic_id, str):
        raise ValueError("feedback diagnostic_id must be text or null")
    if diagnostic_runtime is not None and not isinstance(diagnostic_runtime, dict):
        raise ValueError("feedback diagnostic_runtime must be an object or null")
    return prompt, report_ids, diagnostic_id, diagnostic_runtime


def _feedback(api: Any, repo: Path, runtime: Any, payload: dict[str, Any] | None) -> dict[str, Any]:
    instruction = api.workflow_instruction(FEEDBACK_SOURCE)
    if payload is None:
        reports = api.load_execution_reports(repo)
        diagnostics = api.list_diagnostics(repo)
        return {"next_steps": [{
            "kind": "feedback_prepare", "assignment": "root", "instruction": instruction,
            "action": "Select privacy-safe archived evidence and prepare the exact public payload.",
            "evidence": {"reports": reports, "timing_diagnostics": diagnostics},
            "submission": {
                "operation": "feedback_prepare", "prompt": "<exact user feedback text>",
                "report_ids": None, "diagnostic_id": None, "diagnostic_runtime": None,
            },
        }]}

    operation = payload.get("operation")
    allowed = {
        "feedback_prepare": {"operation", "prompt", "report_ids", "diagnostic_id", "diagnostic_runtime"},
        "feedback_submit": {
            "operation", "prompt", "report_ids", "diagnostic_id", "diagnostic_runtime",
            "confirmation", "approved_by",
        },
    }
    if operation not in allowed or set(payload) != allowed[operation]:
        raise ValueError("feedback submission does not match the returned contract")
    prompt, report_ids, diagnostic_id, diagnostic_runtime = _feedback_selection(payload)

    if operation == "feedback_prepare":
        preview = api.prepare_feedback(
            repo, prompt, report_ids,
            diagnostic_id=diagnostic_id, diagnostic_runtime=diagnostic_runtime,
        )
        followup = {
            "operation": "feedback_submit", "prompt": prompt, "report_ids": report_ids,
            "diagnostic_id": diagnostic_id, "diagnostic_runtime": diagnostic_runtime,
            "confirmation": preview["digest"], "approved_by": "<explicit human approver>",
        }
        return {"next_steps": [{
            "kind": "human_approval", "assignment": "root", "instruction": instruction,
            "action": "Show the exact public target, title, labels, body, and digest; submit only after explicit approval.",
            "preview": preview, "submission": followup,
        }]}

    approved_by = payload.get("approved_by")
    if _root_id(runtime) is None:
        raise ValueError("Feedback submission requires the root agent")
    if not isinstance(approved_by, str) or not approved_by.strip() or approved_by.strip().startswith("<"):
        raise ValueError("Feedback submission requires explicit human approval of the exact payload")
    confirmation = payload.get("confirmation")
    if not isinstance(confirmation, str):
        raise ValueError("Feedback submission requires the confirmed exact digest")
    result = api.submit_feedback(
        repo, prompt, confirmation, report_ids,
        diagnostic_id=diagnostic_id, diagnostic_runtime=diagnostic_runtime,
    )
    return {"next_steps": [{
        "kind": "feedback_submitted", "assignment": "root",
        "action": "Return the created public issue and artifact-retention result.",
        "result": result,
    }]}


def _suggest(api: Any, repo: Path, project: dict[str, Any], payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is not None:
        raise ValueError("Work suggestion is read-only; capture an approved recommendation through the goal workflow")
    observations = api.list_entropy_observations(repo, project)
    if observations.get("enabled") is not True:
        return {"next_steps": [{
            "kind": "suggestions_disabled", "assignment": "root",
            "action": "Automatic work suggestions are disabled by the reviewed project configuration. Continue existing goal work; propose enabling suggestions only if the user requests it.",
            "blocked_by": {"configuration": "autonomy_approval_parallelism.refill.enabled", "value": False},
        }]}
    timing = api.timing_suggestion(repo)
    evidence: dict[str, Any] = {"entropy": observations, "timing_status": timing.get("reason")}
    if timing.get("available") is True:
        evidence["diagnostic"] = timing
    return {"next_steps": [{
        "kind": "suggest", "assignment": "root", "instruction": api.workflow_instruction(SUGGEST_SOURCE),
        "action": "Validate the returned read-only evidence and recommend only supported work.",
        "evidence": evidence,
    }]}


def _capture(api: Any, payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is not None:
        return None
    version, fields = _goal_create_contract(api)
    return {"next_steps": [{
        "kind": "capture", "assignment": "root", "instruction": api.workflow_instruction(CAPTURE_SOURCE),
        "action": "Interview the user and submit one approved goal using the public create schema.",
        "schema": {"schema_version": version, "fields": fields},
        "request_schema_version": version, "request_fields": fields,
        "submission": {"operation": "capture_propose", "request": "<validated goal-create request>"},
    }]}


def handle(
    api: Any, repo: Path, project: dict[str, Any], source: str,
    runtime: Any, payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Handle one administrative public intent, or return ``None`` when unowned."""
    if payload is not None and not isinstance(payload, dict):
        raise ValueError("workflow administrative input must be an object")
    if source == FEEDBACK_SOURCE:
        return _feedback(api, repo, runtime, payload)
    if source == SUGGEST_SOURCE:
        return _suggest(api, repo, project, payload)
    if source == CAPTURE_SOURCE:
        return _capture(api, payload)
    return None
