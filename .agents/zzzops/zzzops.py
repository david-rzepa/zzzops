#!/usr/bin/env python3
"""Small interactive ZzzOps control panel."""

from __future__ import annotations

import argparse
import importlib.util
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

_POLICY_MODULE_PATH = Path(__file__).with_name("policy.py")
_POLICY_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_policy", _POLICY_MODULE_PATH)
assert _POLICY_MODULE_SPEC and _POLICY_MODULE_SPEC.loader
_policy = importlib.util.module_from_spec(_POLICY_MODULE_SPEC)
sys.modules[_POLICY_MODULE_SPEC.name] = _policy
_POLICY_MODULE_SPEC.loader.exec_module(_policy)

PROJECT_SCHEMA_VERSION = _policy.PROJECT_SCHEMA_VERSION
PLAN_SCHEMA_VERSION = 1
POLICY_SCHEMA_VERSION = _policy.POLICY_SCHEMA_VERSION
GOAL_SCHEMA_VERSION = 1
GOAL_TRANSITION_SCHEMA_VERSION = 1
PORTFOLIO_SCHEMA_VERSION = 1
PROJECT_POLICY_RELATIVE = _policy.PROJECT_POLICY_RELATIVE
PROJECT_AUDIT_RELATIVE = _policy.PROJECT_AUDIT_RELATIVE
GOAL_BLOCK_START = "<!-- zzzops-goal"
GOAL_BLOCK_END = "zzzops-goal -->"
BACKENDS = _policy.BACKENDS
POLICY_SECTION_IDS = _policy.POLICY_SECTION_IDS
GOAL_FIELDS = {
    "schema_version", "status", "priority", "value", "difficulty", "confidence",
    "parent", "depends_on", "claim", "blockers",
    "evidence", "next_action", "revision", "implementation", "resources",
}
GOAL_TRANSITION_FIELDS = {"schema_version", "expected_revision", "expected_digest", "goal"}
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
GITHUB_PORTFOLIO_QUERY = """
query($owner:String!,$name:String!,$labels:[String!],$endCursor:String){
  repository(owner:$owner,name:$name){
    nameWithOwner url hasIssuesEnabled viewerPermission
    issues(first:100,after:$endCursor,states:[OPEN,CLOSED],labels:$labels,orderBy:{field:CREATED_AT,direction:ASC}){
      nodes{
        number title body state updatedAt url
        labels(first:100){nodes{name}}
      }
      pageInfo{hasNextPage endCursor}
    }
  }
}
""".strip()
REPOSITORY_SIZE_THRESHOLD_BYTES = 100 * 1024 * 1024
MANAGED_SKILLS = (
    "add-zzzops-goal", "execute-zzzops", "migrate-to-zzzops", "review-zzzops-policy",
    "send-zzzops-feedback", "suggest-zzzops-work",
)
MACHINERY_PATHS = (
    ".agents/zzzops/zzzops.py",
    ".agents/zzzops/policy.py",
    ".agents/zzzops/.gitignore",
    ".agents/zzzops/INSTALL_MANIFEST",
    ".agents/zzzops/templates/project-goals",
    *(f".agents/skills/{name}" for name in MANAGED_SKILLS),
    *(f".claude/skills/{name}" for name in MANAGED_SKILLS),
    ".zzzops/rules",
    ".zzzops/.gitignore",
)
GITHUB_MANAGEMENT_PERMISSIONS = {"TRIAGE", "WRITE", "MAINTAIN", "ADMIN"}
RESERVATION_COLOR = "5319E7"
RESERVATION_ID = re.compile(r"^[A-Za-z0-9._-]+$")
RESERVATION_EXPIRY_GRACE_SECONDS = 60
RESOURCE_LABEL_PREFIX = "zzzops:resource:"
EXECUTION_REPORT_SCHEMA_VERSION = 3
LEGACY_EXECUTION_REPORT_SCHEMA_VERSION = 2
EXECUTION_REPORT_TARGET = "david-rzepa/zzzops"
EXECUTION_REPORT_TITLE = "ZzzOps feedback"
EXECUTION_REPORT_LABELS = ["zzzops", "zzzops-feedback", "zzzops:status:new", "zzzops:priority:P2"]
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


class ReservationProviderError(ValueError):
    """The provider did not produce a safe, confirmed reservation result."""


class GoalTransitionProviderError(ValueError):
    """The provider did not produce a safe, confirmed goal transition result."""


def _reservation_actor(value: str, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value or len(value) > limit or not RESERVATION_ID.fullmatch(value):
        raise ValueError(f"{field} must be 1-{limit} characters using letters, numbers, dot, underscore, or hyphen")
    return value


def reservation_label_name(goal: int) -> str:
    if not isinstance(goal, int) or isinstance(goal, bool) or goal < 1:
        raise ValueError("goal must be a positive issue number")
    return f"zzzops:reserve:{goal}"


def reservation_repository_key(repository: str) -> str:
    return hashlib.sha256(repository.casefold().encode("utf-8")).hexdigest()[:12]


normalize_resources = _policy.normalize_resources
normalize_resource_policy = _policy.normalize_resource_policy
exclusive_resources = _policy.exclusive_resources


def resource_label_name(resource: str) -> str:
    normalized = normalize_resources([resource])[0]
    return RESOURCE_LABEL_PREFIX + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def reservation_description(
    repository: str, goal: int, revision: int, owner: str, run_id: str, expires_at: int,
    acquired_at: int | None = None,
) -> str:
    owner = _reservation_actor(owner, "owner", 20)
    run_id = _reservation_actor(run_id, "run-id", 32)
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValueError("revision must be a positive integer")
    repository_key = reservation_repository_key(repository)
    acquired_at = expires_at if acquired_at is None else acquired_at
    description = f"z1|r={repository_key}|g={goal}|v={revision}|o={owner}|u={run_id}|a={acquired_at}|x={expires_at}"
    if len(description) > 100:
        raise ValueError("reservation metadata exceeds GitHub's label-description limit")
    return description


def parse_reservation_description(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        raise ReservationProviderError("Reservation metadata is missing; no ownership assumed.")
    parts = value.split("|")
    if not parts or parts[0] != "z1":
        raise ReservationProviderError("Reservation metadata is invalid; no ownership assumed.")
    fields = {}
    for part in parts[1:]:
        key, separator, item = part.partition("=")
        if not separator or key in fields:
            raise ReservationProviderError("Reservation metadata is invalid; no ownership assumed.")
        fields[key] = item
    if set(fields) != {"r", "g", "v", "o", "u", "a", "x"}:
        raise ReservationProviderError("Reservation metadata is incomplete; no ownership assumed.")
    try:
        metadata = {
            "repository_key": fields["r"], "goal": int(fields["g"]), "revision": int(fields["v"]),
            "owner": _reservation_actor(fields["o"], "owner", 20),
            "run_id": _reservation_actor(fields["u"], "run-id", 32), "acquired_at": int(fields["a"]),
            "expires_at": int(fields["x"]),
        }
        if metadata["goal"] < 1 or metadata["revision"] < 1 or metadata["acquired_at"] < 0 or metadata["expires_at"] < metadata["acquired_at"]:
            raise ValueError("reservation timestamps or identity are invalid")
        return metadata
    except ValueError as exc:
        raise ReservationProviderError("Reservation metadata is invalid; no ownership assumed.") from exc


class GitHubReservationAdapter:
    def __init__(self, repo: Path, repository: str):
        self.repo = repo
        self.repository = repository
        self.executable = shutil.which("gh")
        if not self.executable:
            raise ReservationProviderError("GitHub CLI is unavailable; no reservation was made.")
        self._identity_checked = False

    def _run(self, arguments: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.executable, *arguments], cwd=self.repo, capture_output=True, text=True,
                encoding="utf-8", timeout=timeout, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ReservationProviderError(f"GitHub did not confirm the reservation request ({type(exc).__name__}); no ownership assumed.") from exc

    def _provider_error(self, result: subprocess.CompletedProcess[str]) -> ReservationProviderError:
        detail = sanitize_output((result.stderr.strip() or result.stdout.strip() or "unknown GitHub error").splitlines()[0][:300])
        return ReservationProviderError(f"GitHub did not confirm the reservation request: {detail}")

    def ensure_identity(self) -> None:
        if self._identity_checked:
            return
        result = self._run(["repo", "view", self.repository, "--json", "nameWithOwner,hasIssuesEnabled,viewerPermission"])
        if result.returncode:
            raise self._provider_error(result)
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ReservationProviderError("GitHub returned invalid repository metadata; no reservation was made.") from exc
        if data.get("nameWithOwner", "").casefold() != self.repository.casefold():
            raise ReservationProviderError("GitHub repository identity changed; no reservation was made.")
        if not data.get("hasIssuesEnabled") or data.get("viewerPermission") not in GITHUB_MANAGEMENT_PERMISSIONS:
            raise ReservationProviderError("GitHub Issues management permission is required; no reservation was made.")
        self._identity_checked = True

    def goal_revision(self, goal: int, require_actionable: bool = False) -> int:
        self.ensure_identity()
        result = self._run(["api", f"repos/{self.repository}/issues/{goal}"])
        if result.returncode:
            raise self._provider_error(result)
        try:
            issue = json.loads(result.stdout)
            parsed = parse_managed_goal(issue.get("body"), goal)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ReservationProviderError("The goal could not be validated; no reservation was made.") from exc
        if parsed is None:
            raise ReservationProviderError("The goal could not be validated; no reservation was made.")
        if require_actionable and parsed["status"] not in {"ready", "in_progress"}:
            raise ReservationProviderError(f"Goal #{goal} is not available for work; no reservation was made.")
        return parsed["revision"]

    def get_label(self, name: str) -> dict[str, Any] | None:
        result = self._run(["api", f"repos/{self.repository}/labels/{quote(name, safe='')}"])
        if result.returncode:
            if "404" in result.stderr or "Not Found" in result.stderr:
                return None
            raise self._provider_error(result)
        try:
            label = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ReservationProviderError("GitHub returned invalid reservation metadata; no ownership assumed.") from exc
        if not isinstance(label, dict) or not label.get("node_id"):
            raise ReservationProviderError("GitHub returned incomplete reservation metadata; no ownership assumed.")
        return label

    def list_resource_labels(self) -> list[dict[str, Any]]:
        result = self._run([
            "api", "--paginate", "--slurp", f"repos/{self.repository}/labels?per_page=100",
        ])
        if result.returncode:
            raise self._provider_error(result)
        try:
            pages = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ReservationProviderError(
                "GitHub returned invalid resource reservation metadata; no release was assumed."
            ) from exc
        if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
            raise ReservationProviderError(
                "GitHub returned incomplete resource reservation metadata; no release was assumed."
            )
        labels = []
        for label in (item for page in pages for item in page):
            if not isinstance(label, dict):
                raise ReservationProviderError(
                    "GitHub returned incomplete resource reservation metadata; no release was assumed."
                )
            if str(label.get("name", "")).startswith(RESOURCE_LABEL_PREFIX):
                if not label.get("node_id"):
                    raise ReservationProviderError(
                        "GitHub returned incomplete resource reservation metadata; no release was assumed."
                    )
                labels.append(label)
        return labels

    def create_label(self, name: str, description: str) -> dict[str, Any] | None:
        result = self._run([
            "api", "--method", "POST", f"repos/{self.repository}/labels",
            "-f", f"name={name}", "-f", f"color={RESERVATION_COLOR}", "-f", f"description={description}",
        ])
        if result.returncode:
            existing = self.get_label(name)
            if existing is not None:
                return None
            raise self._provider_error(result)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            confirmed = self.get_label(name)
            if confirmed and confirmed.get("description") == description:
                return confirmed
            raise ReservationProviderError("GitHub did not confirm the created reservation; no ownership assumed.") from exc

    def delete_label(self, node_id: str) -> None:
        query = "mutation($id:ID!){deleteLabel(input:{id:$id}){clientMutationId}}"
        result = self._run(["api", "graphql", "-F", f"id={node_id}", "-f", f"query={query}"])
        if result.returncode:
            raise self._provider_error(result)

    def update_label(self, node_id: str, description: str) -> None:
        query = "mutation($id:ID!,$description:String!){updateLabel(input:{id:$id,description:$description}){label{id description}}}"
        result = self._run([
            "api", "graphql", "-F", f"id={node_id}", "-F", f"description={description}", "-f", f"query={query}",
        ])
        if result.returncode:
            raise self._provider_error(result)


class GitHubGoalTransitionAdapter:
    def __init__(self, repo: Path, repository: str):
        self.repo = repo
        self.repository = repository
        self.executable = shutil.which("gh")
        if not self.executable:
            raise GoalTransitionProviderError("GitHub CLI is unavailable; no goal update was made.")
        self._identity_checked = False

    def _run(
        self, arguments: list[str], *, input_text: str | None = None, timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.executable, *arguments], cwd=self.repo, capture_output=True, text=True,
                encoding="utf-8", input=input_text, timeout=timeout, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GoalTransitionProviderError(
                f"GitHub did not confirm the goal transition ({type(exc).__name__}); success was not assumed."
            ) from exc

    @staticmethod
    def _provider_error(result: subprocess.CompletedProcess[str]) -> GoalTransitionProviderError:
        detail = sanitize_output((result.stderr.strip() or result.stdout.strip() or "unknown GitHub error").splitlines()[0][:300])
        return GoalTransitionProviderError(f"GitHub did not confirm the goal transition: {detail}")

    def ensure_identity(self) -> None:
        if self._identity_checked:
            return
        result = self._run(["repo", "view", self.repository, "--json", "nameWithOwner,hasIssuesEnabled,viewerPermission"])
        if result.returncode:
            raise self._provider_error(result)
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise GoalTransitionProviderError("GitHub returned invalid repository metadata; no goal update was made.") from exc
        if data.get("nameWithOwner", "").casefold() != self.repository.casefold():
            raise GoalTransitionProviderError("GitHub repository identity changed; no goal update was made.")
        if not data.get("hasIssuesEnabled") or data.get("viewerPermission") not in GITHUB_MANAGEMENT_PERMISSIONS:
            raise GoalTransitionProviderError("GitHub Issues management permission is required; no goal update was made.")
        self._identity_checked = True

    def get_issue(self, number: int) -> dict[str, Any]:
        self.ensure_identity()
        result = self._run(["api", f"repos/{self.repository}/issues/{number}"])
        if result.returncode:
            raise self._provider_error(result)
        try:
            issue = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise GoalTransitionProviderError("GitHub returned invalid goal data; no goal update was made.") from exc
        if not isinstance(issue, dict):
            raise GoalTransitionProviderError("GitHub returned incomplete goal data; no goal update was made.")
        return issue

    def update_issue(self, number: int, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._run(
            ["api", "--method", "PATCH", f"repos/{self.repository}/issues/{number}", "--input", "-"],
            input_text=json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
        if result.returncode:
            raise self._provider_error(result)
        try:
            issue = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise GoalTransitionProviderError(
                "GitHub returned an invalid goal-transition response; success was not assumed."
            ) from exc
        if not isinstance(issue, dict):
            raise GoalTransitionProviderError(
                "GitHub returned an incomplete goal-transition response; success was not assumed."
            )
        return issue


def _validate_reservation_goal(
    adapter: Any, repository: str, goal: int, revision: int, require_actionable: bool = False,
) -> None:
    if adapter.repository.casefold() != repository.casefold():
        raise ReservationProviderError("Repository identity changed; no reservation was made.")
    observed_revision = adapter.goal_revision(goal, require_actionable=require_actionable)
    if observed_revision != revision:
        raise ReservationProviderError(
            f"Goal #{goal} changed from revision {revision} to {observed_revision}; refresh before reserving it."
        )


def _reservation_matches(label: dict[str, Any], description: str) -> bool:
    return label.get("description") == description and bool(label.get("node_id"))


def _validate_reservation_metadata(metadata: dict[str, Any], repository: str, goal: int) -> None:
    if metadata["repository_key"] != reservation_repository_key(repository) or metadata["goal"] != goal:
        raise ReservationProviderError("Reservation identity is invalid; no ownership assumed.")


def _validate_reservation_repository(metadata: dict[str, Any], repository: str) -> None:
    if metadata["repository_key"] != reservation_repository_key(repository):
        raise ReservationProviderError("Reservation repository identity is invalid; no ownership assumed.")


def _live_reservation_holder(metadata: dict[str, Any], now_epoch: int) -> dict[str, Any] | None:
    """Project only bounded, validated metadata for a presently live holder."""
    if metadata["expires_at"] <= now_epoch:
        return None
    return {key: metadata[key] for key in ("goal", "owner", "run_id", "expires_at")}


def acquire_reservation(
    adapter: Any, repository: str, goal: int, revision: int, owner: str, run_id: str,
    ttl_seconds: int = 900, now: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 60 <= ttl_seconds <= 86400:
        raise ValueError("ttl-seconds must be from 60 to 86400")
    now = now or datetime.now(timezone.utc)
    now_epoch = int(now.timestamp())
    expires_at = now_epoch + ttl_seconds
    name = reservation_label_name(goal)
    description = reservation_description(repository, goal, revision, owner, run_id, expires_at, now_epoch)
    _validate_reservation_goal(adapter, repository, goal, revision, require_actionable=True)
    existing = adapter.get_label(name)
    if existing is not None:
        current = parse_reservation_description(existing.get("description"))
        _validate_reservation_metadata(current, repository, goal)
        if current["owner"] == owner and current["run_id"] == run_id and current["revision"] <= revision and current["expires_at"] > now_epoch:
            return {"acquired": True, "outcome": "already_owned", "goal": goal, "expires_at": current["expires_at"]}
        if current["expires_at"] + RESERVATION_EXPIRY_GRACE_SECONDS > now_epoch:
            return {"acquired": False, "outcome": "contended", "goal": goal}
        try:
            adapter.delete_label(existing["node_id"])
        except ReservationProviderError:
            pass
    created = adapter.create_label(name, description)
    if created is None:
        return {"acquired": False, "outcome": "contended", "goal": goal}
    if not _reservation_matches(created, description):
        confirmed = adapter.get_label(name)
        if confirmed is None or not _reservation_matches(confirmed, description):
            raise ReservationProviderError("GitHub did not confirm reservation ownership; no ownership assumed.")
    return {"acquired": True, "outcome": "acquired", "goal": goal, "acquired_at": now_epoch, "expires_at": expires_at}


def renew_reservation(
    adapter: Any, repository: str, goal: int, revision: int, owner: str, run_id: str,
    ttl_seconds: int = 900, now: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 60 <= ttl_seconds <= 86400:
        raise ValueError("ttl-seconds must be from 60 to 86400")
    now = now or datetime.now(timezone.utc)
    now_epoch = int(now.timestamp())
    name = reservation_label_name(goal)
    _validate_reservation_goal(adapter, repository, goal, revision)
    existing = adapter.get_label(name)
    if existing is None:
        return {"acquired": False, "outcome": "missing", "goal": goal}
    current = parse_reservation_description(existing.get("description"))
    _validate_reservation_metadata(current, repository, goal)
    if current["owner"] != owner or current["run_id"] != run_id or current["revision"] > revision or current["expires_at"] <= now_epoch:
        return {"acquired": False, "outcome": "not_owned", "goal": goal}
    expires_at = now_epoch + ttl_seconds
    description = reservation_description(
        repository, goal, revision, owner, run_id, expires_at, current["acquired_at"],
    )
    try:
        adapter.update_label(existing["node_id"], description)
    except ReservationProviderError:
        confirmed = adapter.get_label(name)
        if confirmed is None or confirmed.get("node_id") != existing["node_id"] or not _reservation_matches(confirmed, description):
            raise ReservationProviderError("GitHub did not confirm reservation renewal; no ownership assumed.")
    return {"acquired": True, "outcome": "renewed", "goal": goal, "expires_at": expires_at}


def release_reservation(
    adapter: Any, repository: str, goal: int, revision: int, owner: str, run_id: str, *, _validated: bool = False,
) -> dict[str, Any]:
    name = reservation_label_name(goal)
    if not _validated:
        _validate_reservation_goal(adapter, repository, goal, revision)
    existing = adapter.get_label(name)
    if existing is None:
        return {"released": True, "outcome": "already_released", "goal": goal}
    current = parse_reservation_description(existing.get("description"))
    _validate_reservation_metadata(current, repository, goal)
    if current["owner"] != owner or current["run_id"] != run_id or current["revision"] > revision:
        return {"released": False, "outcome": "not_owned", "goal": goal}
    try:
        adapter.delete_label(existing["node_id"])
    except ReservationProviderError:
        confirmed = adapter.get_label(name)
        if confirmed is not None and confirmed.get("node_id") == existing["node_id"]:
            raise ReservationProviderError("GitHub did not confirm reservation release; it will expire safely.")
    return {"released": True, "outcome": "released", "goal": goal}


def _acquire_resource(
    adapter: Any, repository: str, resource: str, goal: int, revision: int, owner: str, run_id: str,
    ttl_seconds: int, now: datetime,
) -> dict[str, Any]:
    now_epoch = int(now.timestamp())
    expires_at = now_epoch + ttl_seconds
    name = resource_label_name(resource)
    description = reservation_description(repository, goal, revision, owner, run_id, expires_at, now_epoch)
    existing = adapter.get_label(name)
    if existing is not None:
        current = parse_reservation_description(existing.get("description"))
        _validate_reservation_repository(current, repository)
        if (
            current["goal"] == goal and current["owner"] == owner and current["run_id"] == run_id
            and current["revision"] <= revision and current["expires_at"] > now_epoch
        ):
            return {"acquired": True, "outcome": "already_owned", "resource": resource}
        if current["expires_at"] + RESERVATION_EXPIRY_GRACE_SECONDS > now_epoch:
            result = {"acquired": False, "outcome": "resource_contended", "resource": resource}
            holder = _live_reservation_holder(current, now_epoch)
            return {**result, "holder": holder} if holder is not None else result
        try:
            adapter.delete_label(existing["node_id"])
        except ReservationProviderError:
            pass
    created = adapter.create_label(name, description)
    if created is None:
        result = {"acquired": False, "outcome": "resource_contended", "resource": resource}
        confirmed = adapter.get_label(name)
        if confirmed is None:
            return result
        current = parse_reservation_description(confirmed.get("description"))
        _validate_reservation_repository(current, repository)
        holder = _live_reservation_holder(current, now_epoch)
        return {**result, "holder": holder} if holder is not None else result
    if not _reservation_matches(created, description):
        confirmed = adapter.get_label(name)
        if confirmed is None or not _reservation_matches(confirmed, description):
            raise ReservationProviderError("GitHub did not confirm resource ownership; no ownership assumed.")
    return {"acquired": True, "outcome": "acquired", "resource": resource}


def _renew_resource(
    adapter: Any, repository: str, resource: str, goal: int, revision: int, owner: str, run_id: str,
    ttl_seconds: int, now: datetime,
) -> dict[str, Any]:
    name = resource_label_name(resource)
    existing = adapter.get_label(name)
    if existing is None:
        return {"acquired": False, "outcome": "missing", "resource": resource}
    current = parse_reservation_description(existing.get("description"))
    _validate_reservation_repository(current, repository)
    now_epoch = int(now.timestamp())
    if (
        current["goal"] != goal or current["owner"] != owner or current["run_id"] != run_id
        or current["revision"] > revision or current["expires_at"] <= now_epoch
    ):
        return {"acquired": False, "outcome": "not_owned", "resource": resource}
    description = reservation_description(
        repository, goal, revision, owner, run_id, now_epoch + ttl_seconds, current["acquired_at"],
    )
    try:
        adapter.update_label(existing["node_id"], description)
    except ReservationProviderError:
        confirmed = adapter.get_label(name)
        if confirmed is None or confirmed.get("node_id") != existing["node_id"] or not _reservation_matches(confirmed, description):
            raise ReservationProviderError("GitHub did not confirm resource renewal; no ownership assumed.")
    return {"acquired": True, "outcome": "renewed", "resource": resource}


def _release_resource(
    adapter: Any, repository: str, resource: str, goal: int, revision: int, owner: str, run_id: str,
    *, ignore_not_owned: bool = False,
) -> None:
    name = resource_label_name(resource)
    existing = adapter.get_label(name)
    if existing is None:
        return
    current = parse_reservation_description(existing.get("description"))
    _validate_reservation_repository(current, repository)
    if current["goal"] != goal or current["owner"] != owner or current["run_id"] != run_id or current["revision"] > revision:
        if ignore_not_owned:
            return
        raise ReservationProviderError("This run does not own every declared resource; no release was assumed.")
    try:
        adapter.delete_label(existing["node_id"])
    except ReservationProviderError:
        confirmed = adapter.get_label(name)
        if confirmed is not None and confirmed.get("node_id") == existing["node_id"]:
            raise ReservationProviderError("GitHub did not confirm resource release; it will expire safely.")


def _owned_resource_labels(
    adapter: Any, repository: str, goal: int, revision: int, owner: str, run_id: str,
) -> list[dict[str, Any]]:
    owned = []
    for label in adapter.list_resource_labels():
        metadata = parse_reservation_description(label.get("description"))
        if metadata["repository_key"] != reservation_repository_key(repository):
            continue
        if (
            metadata["goal"] == goal and metadata["owner"] == owner and metadata["run_id"] == run_id
            and metadata["revision"] <= revision
        ):
            owned.append(label)
    return owned


def _delete_discovered_resource(adapter: Any, label: dict[str, Any]) -> None:
    try:
        adapter.delete_label(label["node_id"])
    except ReservationProviderError:
        confirmed = adapter.get_label(label["name"])
        if confirmed is not None and confirmed.get("node_id") == label["node_id"]:
            raise ReservationProviderError("GitHub did not confirm resource release; it will expire safely.")


def acquire_reservation_bundle(
    adapter: Any, repository: str, goal: int, revision: int, owner: str, run_id: str,
    resources: list[str], ttl_seconds: int = 900, now: datetime | None = None, resource_policy: Any = None,
) -> dict[str, Any]:
    resources = normalize_resources(resources)
    reserved_resources = exclusive_resources(resources, resource_policy)
    now = now or datetime.now(timezone.utc)
    goal_result = acquire_reservation(adapter, repository, goal, revision, owner, run_id, ttl_seconds, now)
    if not goal_result["acquired"]:
        return goal_result
    acquired = []
    try:
        for resource in reserved_resources:
            result = _acquire_resource(adapter, repository, resource, goal, revision, owner, run_id, ttl_seconds, now)
            if not result["acquired"]:
                for held in reversed(acquired):
                    _release_resource(adapter, repository, held, goal, revision, owner, run_id)
                release_reservation(adapter, repository, goal, revision, owner, run_id, _validated=True)
                contention = {"acquired": False, "outcome": "resource_contended", "goal": goal, "resource": resource}
                return {**contention, "holder": result["holder"]} if "holder" in result else contention
            acquired.append(resource)
    except Exception:
        for held in reversed(acquired):
            _release_resource(adapter, repository, held, goal, revision, owner, run_id)
        release_reservation(adapter, repository, goal, revision, owner, run_id, _validated=True)
        raise
    return {**goal_result, "resources": resources, "reserved_resources": reserved_resources}


def renew_reservation_bundle(
    adapter: Any, repository: str, goal: int, revision: int, owner: str, run_id: str,
    resources: list[str], ttl_seconds: int = 900, now: datetime | None = None, resource_policy: Any = None,
) -> dict[str, Any]:
    resources = normalize_resources(resources)
    reserved_resources = exclusive_resources(resources, resource_policy)
    now = now or datetime.now(timezone.utc)
    result = renew_reservation(adapter, repository, goal, revision, owner, run_id, ttl_seconds, now)
    if not result["acquired"]:
        return result
    for resource in reserved_resources:
        resource_result = _renew_resource(adapter, repository, resource, goal, revision, owner, run_id, ttl_seconds, now)
        if not resource_result["acquired"]:
            return {"acquired": False, "outcome": "resource_lost", "goal": goal, "resource": resource}
    return {**result, "resources": resources, "reserved_resources": reserved_resources}


def release_reservation_bundle(
    adapter: Any, repository: str, goal: int, revision: int, owner: str, run_id: str, resources: list[str],
    resource_policy: Any = None,
) -> dict[str, Any]:
    exclusive_resources(resources, resource_policy)  # Validate retained CLI arguments and reviewed policy.
    try:
        _validate_reservation_goal(adapter, repository, goal, revision)
    except ReservationProviderError as exc:
        return {"released": False, "outcome": "failed", "goal": goal, "detail": str(exc)}
    removed = 0
    try:
        owned = _owned_resource_labels(adapter, repository, goal, revision, owner, run_id)
    except ReservationProviderError as exc:
        return {"released": False, "outcome": "failed", "goal": goal, "detail": str(exc)}
    for label in reversed(owned):
        try:
            _delete_discovered_resource(adapter, label)
            removed += 1
        except ReservationProviderError as exc:
            outcome = "partial" if removed else "failed"
            return {
                "released": False, "outcome": outcome, "goal": goal,
                "released_resources": removed, "detail": str(exc),
            }
    try:
        remaining = _owned_resource_labels(adapter, repository, goal, revision, owner, run_id)
    except ReservationProviderError as exc:
        outcome = "partial" if removed else "failed"
        return {
            "released": False, "outcome": outcome, "goal": goal,
            "released_resources": removed, "detail": str(exc),
        }
    if remaining:
        return {
            "released": False, "outcome": "partial", "goal": goal,
            "released_resources": removed, "detail": "Owned resource reservations remain after release.",
        }
    try:
        goal_result = release_reservation(adapter, repository, goal, revision, owner, run_id, _validated=True)
    except ReservationProviderError as exc:
        outcome = "partial" if removed else "failed"
        return {
            "released": False, "outcome": outcome, "goal": goal,
            "released_resources": removed, "detail": str(exc),
        }
    if goal_result["outcome"] == "already_released" and not removed:
        return goal_result
    return {"released": True, "outcome": "released", "goal": goal}


def reservation_cli_message(result: dict[str, Any], goal: int) -> str:
    outcome = result.get("outcome")
    if result.get("acquired") is True:
        return f"Reserved goal #{goal}."
    if outcome == "released":
        return f"Released goal #{goal} and all owned resources."
    if outcome == "already_released":
        return f"Goal #{goal} and its owned resources were already released."
    if outcome == "partial":
        return f"Partially released goal #{goal}; owned reservations remain. Retry after refreshing."
    if outcome == "failed":
        return f"Could not safely release goal #{goal}; no complete release was assumed."
    if outcome in {"contended", "resource_contended"}:
        holder = result.get("holder")
        if isinstance(holder, dict):
            try:
                holder_goal = holder["goal"]
                holder_owner = _reservation_actor(holder["owner"], "owner", 20)
                holder_run = _reservation_actor(holder["run_id"], "run-id", 32)
                holder_expiry = holder["expires_at"]
                if isinstance(holder_goal, int) and not isinstance(holder_goal, bool) and holder_goal > 0 and isinstance(holder_expiry, int) and not isinstance(holder_expiry, bool) and holder_expiry >= 0:
                    return f"Overlapping work is held by goal #{holder_goal}, owner {holder_owner}, run {holder_run}, until {holder_expiry}. Refresh and choose different work."
            except (KeyError, ValueError):
                pass
        return f"Another agent is handling overlapping work for goal #{goal}. Refresh and choose different work."
    return f"Goal #{goal} is not reserved by this run. Refresh before continuing."


def project_claim_ttl_seconds(project: dict[str, Any]) -> int:
    sections = ((project.get("policy") or {}).get("sections") if isinstance(project.get("policy"), dict) else None)
    section = next((item for item in sections or [] if isinstance(item, dict) and item.get("id") == "autonomy_approval_parallelism"), None)
    hours = ((section.get("settings") or {}).get("claim_ttl_hours") if isinstance(section, dict) else None)
    if not isinstance(hours, int) or isinstance(hours, bool) or not 1 <= hours <= 24:
        raise ValueError("Reviewed project policy must set claim_ttl_hours from 1 to 24")
    return hours * 3600


def project_resource_policy(project: dict[str, Any]) -> dict[str, Any]:
    sections = ((project.get("policy") or {}).get("sections") if isinstance(project.get("policy"), dict) else None)
    section = next((item for item in sections or [] if isinstance(item, dict) and item.get("id") == "autonomy_approval_parallelism"), None)
    settings = section.get("settings") if isinstance(section, dict) else None
    configured = settings.get("resource_reservations") if isinstance(settings, dict) else None
    return normalize_resource_policy(configured)


def execution_reports_enabled(project: dict[str, Any]) -> bool:
    sections = ((project.get("policy") or {}).get("sections") if isinstance(project.get("policy"), dict) else None)
    section = next((item for item in sections or [] if isinstance(item, dict) and item.get("id") == "autonomy_approval_parallelism"), None)
    settings = section.get("settings") if isinstance(section, dict) else None
    configured = settings.get("execution_reports") if isinstance(settings, dict) and "execution_reports" in settings else None
    if configured is not None and not isinstance(configured, dict):
        raise ValueError("Reviewed project policy execution_reports must be an object")
    enabled = configured.get("enabled") if isinstance(configured, dict) and "enabled" in configured else True
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


def _git_blob_digest(data: bytes, width: int) -> str:
    algorithm = hashlib.sha1 if width == 40 else hashlib.sha256
    return algorithm(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def zzzops_provenance(repo: Path) -> dict[str, str]:
    manifest = repo / ".agents" / "zzzops" / "INSTALL_MANIFEST"
    if manifest.is_file():
        try:
            lines = manifest.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"Could not read installed ZzzOps provenance: {type(exc).__name__}") from exc
        if not lines or lines[0] != "zzzops-install-manifest-v1":
            raise ValueError("Installed ZzzOps provenance manifest header is invalid")
        revisions, versions, files = [], [], {}
        for line in lines[1:]:
            fields = line.split("\t", 2)
            if len(fields) == 2 and fields[0] == "revision":
                revisions.append(fields[1])
            elif len(fields) == 2 and fields[0] == "version":
                versions.append(fields[1])
            elif len(fields) == 3 and fields[0] == "file":
                digest, relative = fields[1], fields[2]
                path = Path(relative)
                if not ZZZOPS_REVISION.fullmatch(digest) or path.is_absolute() or ".." in path.parts or relative in files:
                    raise ValueError("Installed ZzzOps provenance manifest file entry is invalid")
                files[relative] = digest
            else:
                raise ValueError("Installed ZzzOps provenance manifest entry is invalid")
        if not versions:
            raise ValueError("Installed ZzzOps manifest predates version provenance; rerun the installer before recording reports")
        if len(revisions) != 1 or len(versions) != 1:
            raise ValueError("Installed ZzzOps provenance fields must occur exactly once")
        try:
            provenance = _validated_zzzops_provenance({"version": versions[0], "revision": revisions[0]})
        except ValueError as exc:
            raise ValueError(f"Installed ZzzOps provenance is invalid: {exc}") from exc
        if not files:
            raise ValueError("Installed ZzzOps provenance manifest contains no managed files")
        for relative, expected in files.items():
            try:
                data = (repo / relative).read_bytes()
            except OSError as exc:
                raise ValueError("Installed ZzzOps mechanics do not match recorded provenance") from exc
            if not hmac.compare_digest(_git_blob_digest(data, len(expected)), expected):
                raise ValueError("Installed ZzzOps mechanics do not match recorded provenance")
        return provenance
    if not (repo / "install.ps1").is_file() or not (repo / "install.sh").is_file():
        raise ValueError("Installed ZzzOps provenance is unavailable; rerun the installer before recording reports")
    values = []
    for command in (("rev-parse", "HEAD"), ("describe", "--tags", "--always", "--long", "--dirty")):
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), *command], text=True, encoding="utf-8",
                capture_output=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f"Could not resolve base-repository ZzzOps provenance: {type(exc).__name__}") from exc
        if result.returncode or not result.stdout.strip():
            raise ValueError("Could not resolve base-repository ZzzOps provenance")
        values.append(result.stdout.strip())
    return _validated_zzzops_provenance({"revision": values[0], "version": values[1]})


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


reviewed_project_state = _policy.reviewed_project_state


def read_cli_text(value: str) -> str:
    if value == "-":
        text = sys.stdin.read()
        return text[1:] if text.startswith("\ufeff") else text
    try:
        return Path(value).resolve().read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Could not read feedback prompt: {type(exc).__name__}") from exc


def configure_cli_stdout() -> None:
    """Use readable, byte-stable UTF-8 whenever stdout owns an encoding layer."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="strict")


project_digest = _policy.project_digest
project_path = _policy.project_path
project_audit_path = _policy.project_audit_path
project_policy_path = _policy.project_policy_path
read_project = _policy.read_project
parse_policy_state = _policy.parse_policy_state
read_policy_text = _policy.read_policy_text
read_project_state = _policy.read_project_state
initialization_base_digest = _policy.initialization_base_digest
policy_review_digest = _policy.policy_review_digest


def validate_project_state(state: Any) -> list[str]:
    if not isinstance(state, dict):
        return ["project state must be an object"]
    allowed = {
        "schema_version", "initialized", "backend", "repository", "revision",
        "charter", "policy", "history", "bindings", "approval",
    }
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
    initialized = state.get("initialized") is True
    policy_errors = validate_policy(state.get("policy"), require_pending=False) if state.get("policy") is not None else []
    errors.extend(f"policy.{error}" for error in policy_errors)
    pending_policy = policy_blockers(state.get("policy")) if not policy_errors else []
    if state.get("initialized") is True:
        if state.get("backend") not in BACKENDS:
            errors.append("initialized backend must be github_issues")
        repository = state.get("repository")
        if not isinstance(repository, dict) or not nonempty(repository.get("identity")):
            errors.append("initialized repository.identity is required")
        if pending_policy:
            errors.append("initialized state cannot have unreviewed required policy: " + ", ".join(pending_policy))
        approval = state.get("approval")
        if not isinstance(approval, dict) or not text_present(approval.get("reviewer")) or not text_present(approval.get("date")):
            errors.append("initialized state requires explicit approval metadata")
        elif approval.get("digest") != policy_review_digest(state):
            errors.append("policy approval digest changed")
    elif state.get("backend") is not None or state.get("repository") is not None or state.get("policy") is not None:
        if state.get("backend") not in BACKENDS or not isinstance(state.get("repository"), dict) or not state.get("policy"):
            errors.append("uninitialized state may select a backend only as a complete pending policy draft")
    bindings = state.get("bindings")
    if not isinstance(bindings, dict):
        errors.append("bindings must be an object")
    else:
        for name, expected_path in (("project", ".zzzops/PROJECT.md"), ("audit", PROJECT_AUDIT_RELATIVE)):
            binding = bindings.get(name)
            if not isinstance(binding, dict) or binding.get("path") != expected_path or not text_present(binding.get("digest")):
                errors.append(f"bindings.{name} must contain the canonical path and digest")
    history = state.get("history")
    if not isinstance(history, list) or not history:
        errors.append("history must be a non-empty list")
    else:
        for index, entry in enumerate(history):
            if not isinstance(entry, dict) or any(not text_present(entry.get(key)) for key in ("date", "actor", "change", "reason")):
                errors.append(f"history[{index}] requires date, actor, change, and reason")
    return errors


def validate_project_artifacts(repo: Path, state: dict[str, Any] | None) -> list[str]:
    if not isinstance(state, dict):
        return []
    bindings = state.get("bindings")
    if not isinstance(bindings, dict):
        return []
    errors = []
    for name, path in (("project", project_path(repo)), ("audit", project_audit_path(repo))):
        binding = bindings.get(name)
        if not isinstance(binding, dict) or not text_present(binding.get("digest")):
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            errors.append(f"{name} policy artifact is unavailable")
            continue
        if project_digest(text) != binding["digest"]:
            errors.append(f"{name} policy artifact digest changed")
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
        elif section_id == "autonomy_approval_parallelism":
            settings = section["settings"]
            if "execution_reports" in settings:
                reporting = settings["execution_reports"]
                if not isinstance(reporting, dict):
                    errors.append(f"{prefix}.settings.execution_reports must be an object")
                elif not isinstance(reporting.get("enabled"), bool):
                    errors.append(f"{prefix}.settings.execution_reports.enabled must be boolean")
            if "resource_reservations" in settings:
                try:
                    normalize_resource_policy(settings["resource_reservations"])
                except ValueError as exc:
                    errors.append(f"{prefix}.settings.{exc}")
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


# Stable entry-point re-exports for existing callers and installed skill prompts.
validate_project_state = _policy.validate_project_state
validate_project_artifacts = _policy.validate_project_artifacts
validate_policy = _policy.validate_policy
policy_blockers = _policy.policy_blockers


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
        "labels": sorted(label["name"] for label in issue.get("labels", []) if isinstance(label, dict) and text_present(label.get("name"))),
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
        transition = json.loads(path.resolve().read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read goal transition: {type(exc).__name__}") from exc
    return transition


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
    if record["revision"] != transition["expected_revision"]:
        raise ValueError(
            f"Goal #{issue_number} changed from revision {transition['expected_revision']} to {record['revision']}; no update was made."
        )
    if not hmac.compare_digest(record["digest"], transition["expected_digest"]):
        raise ValueError(f"Goal #{issue_number} digest changed; no update was made.")

    desired = transition["goal"]
    body = render_managed_goal(desired, issue["body"], issue_number)
    retained_labels = sorted({
        label["name"] for label in issue.get("labels", [])
        if isinstance(label, dict) and text_present(label.get("name"))
        and label["name"] != "zzzops"
        and not label["name"].startswith("zzzops:status:")
        and not label["name"].startswith("zzzops:priority:")
    })
    labels = ["zzzops", *retained_labels, f"zzzops:status:{desired['status']}", f"zzzops:priority:{desired['priority']}"]
    state = "closed" if desired["status"] in {"done", "cancelled"} else "open"
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


def _review_ready_dependency(record: dict[str, Any]) -> bool:
    """Return whether a dependency has a reviewable checkpoint safe to stack on."""
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


def _dependencies_allow_action(
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


def audit_portfolio(
    records: list[dict[str, Any]], backend: str, as_of: datetime | None = None, resource_policy: Any = None,
) -> list[dict[str, Any]]:
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
    for relation in ("depends_on", "parent"):
        for key in sorted(_cycle_nodes(records, relation), key=_portfolio_key):
            findings.append({"code": f"{relation}_cycle", "goal": key, "detail": "cycle member"})
    return sorted(findings, key=lambda finding: (finding["code"], str(finding["goal"]), finding["detail"]))


def build_portfolio_snapshot(
    backend: str, records: list[dict[str, Any]], *, reads: int, raw_bytes: int,
    ignored: int = 0, as_of: datetime | None = None, git_policy: dict[str, Any] | None = None,
    resource_policy: Any = None,
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
    resource_policy = normalize_resource_policy(resource_policy)
    findings = audit_portfolio(records, backend, as_of, resource_policy)
    terminal = {"done", "cancelled"}
    blocked = {record["key"] for record in records if record["status"] == "blocked" or record["needs_human"]}
    terminal_keys = {record["key"] for record in records if record["status"] in terminal}
    git_policy = git_policy or {}
    actionable = [
        record["key"] for record in records
        if record["status"] in {"ready", "in_progress"} and record["key"] not in blocked
        and _dependencies_allow_action(record, by_key, git_policy)
    ]
    actionable_keys = set(actionable)
    for record in records:
        record["actionable"] = record["key"] in actionable_keys
    portfolio_digest = hashlib.sha256(
        (
            "git_policy:" + json.dumps(git_policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            + "resource_policy:" + json.dumps(resource_policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
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
            "total": len(records), "actionable": len(actionable), "blocked": len(blocked),
            "done": len(terminal_keys), "findings": len(findings), "reads": reads,
            "raw_bytes": raw_bytes, "ignored": ignored,
        },
    }


def compact_portfolio_output(snapshot: dict[str, Any]) -> dict[str, Any]:
    terminal_fields = (
        "key", "title", "status", "parent", "depends_on",
        "revision", "digest", "updated_at", "url",
    )
    goals = []
    archived = 0
    for goal in snapshot["goals"]:
        if goal["status"] in {"done", "cancelled"}:
            goals.append({"archived": True, **{field: goal.get(field) for field in terminal_fields}})
            archived += 1
        else:
            goals.append(goal)
    return {**snapshot, "goals": goals, "summary": {**snapshot["summary"], "archived": archived}}


def _project_repository_identity(project: dict[str, Any]) -> str:
    identity = ((project.get("repository") or {}).get("identity") if isinstance(project.get("repository"), dict) else None)
    if project.get("backend") != "github_issues" or not text_present(identity) or identity.count("/") != 1:
        raise ValueError("Canonical policy repository.identity must be owner/repository for GitHub Issues")
    return identity


def _graphql_issue(issue: dict[str, Any]) -> dict[str, Any]:
    labels = issue.get("labels")
    nodes = labels.get("nodes") if isinstance(labels, dict) else None
    if not isinstance(nodes, list):
        raise ValueError("issue labels are incomplete or malformed")
    return {
        "number": issue["number"], "title": issue["title"], "body": issue.get("body") or "",
        "state": str(issue["state"]).lower(), "updated_at": issue["updatedAt"], "html_url": issue["url"],
        "labels": [{"name": node.get("name")} for node in nodes if isinstance(node, dict)],
    }


def _github_repository_capability(data: dict[str, Any]) -> dict[str, Any]:
    permission = data.get("viewerPermission")
    issues_enabled = data.get("hasIssuesEnabled") is True
    usable = issues_enabled and permission in GITHUB_MANAGEMENT_PERMISSIONS
    return {
        "available": True,
        "usable": usable,
        "identity": data.get("nameWithOwner"),
        "url": data.get("url"),
        "issues_enabled": issues_enabled,
        "viewer_permission": permission,
        "detail": "ok" if usable else ("issues disabled" if not issues_enabled else "insufficient permission"),
    }


def github_repository_portfolio_snapshot(
    repo: Path, project: dict[str, Any], include_feedback: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    identity = _project_repository_identity(project)
    owner, name = identity.split("/", 1)
    executable = shutil.which("gh")
    if not executable:
        raise ValueError("GitHub CLI is unavailable")
    command = [
        executable, "api", "graphql", "--paginate", "--slurp",
        "-f", f"query={GITHUB_PORTFOLIO_QUERY}",
        "-F", f"owner={owner}", "-F", f"name={name}", "-F", "labels[]=zzzops",
    ]
    try:
        result = subprocess.run(command, cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"GitHub repository/portfolio read failed: {type(exc).__name__}") from exc
    if result.returncode:
        raise ValueError("GitHub repository/portfolio read failed: " + (result.stderr.strip() or "unknown gh error"))
    try:
        pages = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"GitHub repository/portfolio read returned invalid JSON: {exc}") from exc
    if not isinstance(pages, list) or not pages or any(not isinstance(page, dict) for page in pages):
        raise ValueError("GitHub portfolio pagination result is incomplete or malformed")

    repositories = []
    issue_nodes = []
    for index, page in enumerate(pages):
        data = page.get("data")
        repository = data.get("repository") if isinstance(data, dict) else None
        issue_connection = repository.get("issues") if isinstance(repository, dict) else None
        nodes = issue_connection.get("nodes") if isinstance(issue_connection, dict) else None
        page_info = issue_connection.get("pageInfo") if isinstance(issue_connection, dict) else None
        if not isinstance(repository, dict) or not isinstance(nodes, list) or not isinstance(page_info, dict):
            raise ValueError("GitHub portfolio pagination result is incomplete or malformed")
        if index < len(pages) - 1 and page_info.get("hasNextPage") is not True:
            raise ValueError("GitHub portfolio pagination stopped before the final page")
        if index == len(pages) - 1 and page_info.get("hasNextPage") is not False:
            raise ValueError("GitHub portfolio pagination result is incomplete")
        repositories.append(repository)
        issue_nodes.extend(nodes)

    first = repositories[0]
    metadata = (first.get("nameWithOwner"), first.get("url"), first.get("hasIssuesEnabled"), first.get("viewerPermission"))
    if any((item.get("nameWithOwner"), item.get("url"), item.get("hasIssuesEnabled"), item.get("viewerPermission")) != metadata for item in repositories[1:]):
        raise ValueError("GitHub repository metadata drifted during pagination")
    if first.get("nameWithOwner") != identity:
        raise ValueError(
            f"GitHub repository identity drift: canonical policy records {identity}, "
            f"but GitHub returned {first.get('nameWithOwner') or 'unknown'}"
        )
    repository_probe = _github_repository_capability(first)

    issues = []
    findings = []
    for issue in issue_nodes:
        try:
            if not isinstance(issue, dict):
                raise ValueError("issue must be an object")
            issues.append(_graphql_issue(issue))
        except (KeyError, TypeError, ValueError) as exc:
            goal = issue.get("number", "unknown") if isinstance(issue, dict) else "unknown"
            findings.append({"code": "malformed_record", "goal": goal, "detail": str(exc)})
    def is_feedback(issue: dict[str, Any]) -> bool:
        return any(
            isinstance(label, dict) and label.get("name") == "zzzops-feedback"
            for label in issue.get("labels", [])
        )

    managed = [
        issue for issue in issues
        if GOAL_BLOCK_START in issue["body"] and (include_feedback or not is_feedback(issue))
    ]
    records = []
    for issue in managed:
        try:
            records.append(github_goal_record(issue))
        except (KeyError, TypeError, ValueError) as exc:
            findings.append({"code": "malformed_record", "goal": issue.get("number", "unknown"), "detail": str(exc)})
    snapshot = build_portfolio_snapshot(
        project["backend"], records, reads=len(pages), raw_bytes=len(result.stdout.encode("utf-8")),
        ignored=len(issues) - len(managed),
        git_policy=next(
            (
                section["settings"] for section in ((project.get("policy") or {}).get("sections") or [])
                if isinstance(section, dict) and section.get("id") == "git_review_release"
            ),
            {},
        ),
        resource_policy=project_resource_policy(project),
    )
    snapshot["findings"] = sorted(snapshot["findings"] + findings, key=lambda item: (item["code"], str(item["goal"])))
    snapshot["summary"]["findings"] = len(snapshot["findings"])
    snapshot["complete"] = not findings
    snapshot["valid"] = not snapshot["findings"]
    snapshot["summary"]["processes"] = 1
    return repository_probe, compact_portfolio_output(snapshot)


def portfolio_snapshot(repo: Path, include_feedback: bool = False) -> dict[str, Any]:
    _path, _text, project = read_project_state(repo)
    if project is None:
        raise ValueError("Project policy is missing; run the review-zzzops-policy skill")
    errors = validate_project_state(project)
    errors.extend(validate_project_artifacts(repo, project))
    if errors or not project or not project.get("initialized"):
        raise ValueError("Project policy is not initialized: " + "; ".join(errors or ["review pending"]))
    _repository, snapshot = github_repository_portfolio_snapshot(repo, project, include_feedback)
    return snapshot


def render_portfolio_summary(snapshot: dict[str, Any], include_done: bool = False) -> str:
    summary = snapshot["summary"]
    lines = [
        f"Goals: {summary['actionable']} ready to work, {summary['blocked']} blocked, "
        f"{summary['done']} closed ({summary['total']} total)."
    ]
    if not snapshot["complete"] or not snapshot["valid"]:
        lines.append("This goal list needs attention before work can continue.")
    status_labels = {
        "new": "New", "triaged": "Planned", "ready": "Ready", "in_progress": "In progress",
        "blocked": "Blocked", "done": "Done", "cancelled": "Cancelled",
    }
    for goal in snapshot["goals"]:
        if not include_done and goal["status"] in {"done", "cancelled"}:
            continue
        title = re.sub(r"\s+", " ", str(goal["title"])).strip()[:240]
        label = status_labels.get(goal["status"], goal["status"])
        if goal["status"] in {"ready", "in_progress"} and not goal.get("actionable"):
            label = "Waiting"
        line = f"#{goal['key']} {label}: {title}"
        if goal.get("needs_human"):
            line += " — action needed"
        lines.append(line)
    for finding in snapshot["findings"]:
        lines.append(f"Needs attention on goal #{finding['goal']}: {finding['detail']}")
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


def repository_size_profile(repo: Path) -> dict[str, Any]:
    """Select the default worker mode from existing Git-tracked file bytes."""
    executable = shutil.which("git")
    if not executable:
        return {
            "available": False, "measurement": "existing_git_tracked_worktree_bytes",
            "threshold_bytes": REPOSITORY_SIZE_THRESHOLD_BYTES, "max_workers": 3,
            "mode": "read_only", "detail": "git executable not found",
        }
    try:
        result = subprocess.run(
            [executable, "-C", str(repo), "ls-files", "-z"], cwd=repo,
            capture_output=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "available": False, "measurement": "existing_git_tracked_worktree_bytes",
            "threshold_bytes": REPOSITORY_SIZE_THRESHOLD_BYTES, "max_workers": 3,
            "mode": "read_only", "detail": type(exc).__name__,
        }
    if result.returncode:
        return {
            "available": False, "measurement": "existing_git_tracked_worktree_bytes",
            "threshold_bytes": REPOSITORY_SIZE_THRESHOLD_BYTES, "max_workers": 3,
            "mode": "read_only", "detail": "git ls-files failed",
        }
    total = 0
    files = 0
    for encoded in result.stdout.split(b"\0"):
        if not encoded:
            continue
        relative = Path(os.fsdecode(encoded))
        if relative.is_absolute() or ".." in relative.parts:
            continue
        try:
            stat = os.lstat(repo / relative)
        except OSError:
            continue
        total += stat.st_size
        files += 1
    return {
        "available": True, "measurement": "existing_git_tracked_worktree_bytes",
        "bytes": total, "files": files, "threshold_bytes": REPOSITORY_SIZE_THRESHOLD_BYTES,
        "mode": "worktrees" if total < REPOSITORY_SIZE_THRESHOLD_BYTES else "read_only",
        "max_workers": 3,
    }


def machinery_commit_status(repo: Path) -> dict[str, Any]:
    """Report whether installed ZzzOps mechanics match the repository's HEAD."""
    executable = shutil.which("git")
    if not executable:
        return {
            "available": False, "ok": False, "paths": [], "processes": 0,
            "detail": "Git is unavailable; commit installed ZzzOps machinery before ordinary use.",
        }
    command = [
        executable, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--",
        *MACHINERY_PATHS,
    ]
    try:
        result = subprocess.run(
            command, cwd=repo, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "available": True, "ok": False, "paths": [], "processes": 1,
            "detail": f"Could not verify committed ZzzOps machinery: {type(exc).__name__}.",
        }
    if result.returncode:
        return {
            "available": True, "ok": False, "paths": [], "processes": 1,
            "detail": "Could not verify committed ZzzOps machinery with Git.",
        }

    paths: set[str] = set()
    entries = result.stdout.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        status = entry[:2]
        candidates = [entry[3:] if len(entry) > 3 else ""]
        if any(marker in status for marker in ("R", "C")) and index < len(entries):
            candidates.append(entries[index])
            index += 1
        for candidate in candidates:
            normalized = candidate.replace("\\", "/")
            if not normalized or "/__pycache__/" in f"/{normalized}/" or normalized.endswith((".pyc", ".pyo")):
                continue
            paths.add(normalized)
    changed = sorted(paths)
    return {
        "available": True,
        "ok": not changed,
        "paths": changed,
        "processes": 1,
        "detail": "ok" if not changed else "Commit installed ZzzOps machinery before ordinary use.",
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
    return _github_repository_capability(data)


def inspect_initialization(repo: Path) -> dict[str, Any]:
    path, text = read_project(repo)
    error = None
    try:
        _policy_path, _policy_text, state = read_project_state(repo)
        state_errors = validate_project_state(state) if state is not None else ["canonical policy is missing"]
        state_errors.extend(validate_project_artifacts(repo, state))
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
        "base_digest": initialization_base_digest(repo),
        "state": state,
        "initialized": bool(state and state.get("initialized") is True and not policy_blockers(state.get("policy")) and error is None),
        "valid_state": error is None and state is not None,
        "state_error": error,
        "missing_charter_fields": charter_missing_fields(text),
        "decision_blockers": policy_blockers(state.get("policy")) if state else ["policy:missing"],
        "backend_constraints": {
            "github_issues": "requires a usable GitHub repository probe",
        },
        "capabilities": {
            "git_origin": git_remote,
            "github_auth": github_auth,
            "github_repository": github_repository,
        },
        "repository_size": repository_size_profile(repo),
    }


def decision_checkpoint(repo: Path, include_feedback: bool = False) -> dict[str, Any]:
    path, text = read_project(repo)
    error = None
    try:
        _policy_path, _policy_text, state = read_project_state(repo)
        state_errors = validate_project_state(state) if state is not None else ["canonical policy is missing"]
        state_errors.extend(validate_project_artifacts(repo, state))
        if state_errors:
            error = "; ".join(state_errors)
    except ValueError as exc:
        state = None
        error = str(exc)
    blockers = policy_blockers(state.get("policy")) if state else ["policy:missing"]
    initialized = bool(state and state.get("initialized") is True and not blockers and error is None)
    git_remote = command_probe(["git", "remote", "get-url", "origin"], repo)
    github_available = shutil.which("gh") is not None
    github_processes = 0
    git_machinery = {
        "available": shutil.which("git") is not None,
        "ok": False,
        "paths": [],
        "processes": 0,
        "detail": "initialization required",
    }
    portfolio = {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "complete": False,
        "valid": False,
        "error": "Project policy is not initialized; run the review-zzzops-policy skill",
    }
    github_auth = {
        "available": github_available,
        "ok": False,
        "detail": "initialization required",
    }
    github_repository = {
        "available": github_available,
        "usable": False,
        "detail": "initialization required",
    }
    if initialized and state:
        git_machinery = machinery_commit_status(repo)
    if initialized and state and git_machinery.get("ok") is True:
        github_processes = 1 if github_available else 0
        try:
            github_repository, portfolio = github_repository_portfolio_snapshot(repo, state, include_feedback)
            github_auth = {"available": True, "ok": True, "detail": "github.com"}
        except ValueError as exc:
            detail = sanitize_output(str(exc))
            github_auth = {"available": github_available, "ok": False, "detail": detail}
            github_repository = {"available": github_available, "usable": False, "detail": detail}
            portfolio = {
                "schema_version": PORTFOLIO_SCHEMA_VERSION,
                "complete": False,
                "valid": False,
                "error": detail,
            }
    elif initialized and state:
        detail = str(git_machinery.get("detail") or "Commit installed ZzzOps machinery before ordinary use.")
        github_auth = {"available": github_available, "ok": False, "detail": detail}
        github_repository = {"available": github_available, "usable": False, "detail": detail}
        portfolio = {
            "schema_version": PORTFOLIO_SCHEMA_VERSION,
            "complete": False,
            "valid": False,
            "error": detail,
        }
    ready = bool(
        initialized
        and git_remote.get("ok") is True
        and git_machinery.get("ok") is True
        and github_auth.get("ok") is True
        and github_repository.get("usable") is True
        and portfolio.get("complete") is True
        and portfolio.get("valid") is True
    )
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "project_path": str(path),
        "project_digest": project_digest(text),
        "initialized": initialized,
        "valid_state": error is None and state is not None,
        "state_error": error,
        "decision_blockers": blockers,
        "ready": ready,
        "capabilities": {
            "git_origin": git_remote,
            "git_machinery": git_machinery,
            "github_auth": github_auth,
            "github_repository": github_repository,
        },
        "repository_size": repository_size_profile(repo),
        "portfolio": portfolio,
        "processes": {
            "total": (
                (1 if git_remote.get("available") else 0)
                + int(git_machinery.get("processes", 0))
                + github_processes
            ),
            "github": github_processes,
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
        "charter", "evidence", "confirmations", "github", "policy",
    }
    unknown = sorted(set(plan) - allowed)
    if unknown:
        errors.append("unknown fields: " + ", ".join(unknown))
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        errors.append(f"schema_version must be {PLAN_SCHEMA_VERSION}")
    if plan.get("base_digest") != initialization_base_digest(repo):
        errors.append("base_digest is stale or missing")
    if plan.get("confirmed") is not True:
        errors.append("confirmed must be true")
    backend = plan.get("backend")
    if backend not in BACKENDS:
        errors.append("backend must be github_issues")
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
        if not isinstance(github, dict) or set(github) != {"usable"} or github.get("usable") is not True:
            errors.append("github must contain only usable=true for github_issues")
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
                    errors.append("policy backend settings must record capability evidence, supported-backend tradeoffs, repository identity, and forbidden fallback")
    return errors


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().casefold() != "unknown"


def text_present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(nonempty(item) for item in value)


def render_project(state: dict[str, Any]) -> str:
    charter = state["charter"]
    status = "complete" if state["initialized"] else "incomplete — policy review required"
    reviewed = (state.get("approval") or {}).get("date", "not yet")
    kpis = "\n".join(
        f"| {cell(k['name'])} | {cell(k['why'])} | {cell(k['baseline'])} | "
        f"{cell(k['target'])} | {cell(k['evidence'])} | {cell(k['cadence'])} |"
        for k in charter["kpis"]
    )
    bullets = lambda values: "\n".join(f"- {value}" for value in values)
    checks = "\n".join(f"- [x] {value}" for value in charter["acceptance_criteria"])
    policy = "\n".join(
        f"- `[policy:{section['id']}]` **{section['title']}**: {section['decision']}"
        for section in state["policy"]["sections"]
    )
    return f"""# Project success charter

**Status:** {status}
**Last reviewed:** {reviewed}

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

## Operating policy

{policy}

Detailed rationale and review history: [PROJECT_AUDIT.md](PROJECT_AUDIT.md). Canonical policy state: [POLICY.json](POLICY.json).
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


def render_project_audit(state: dict[str, Any]) -> str:
    status = "complete" if state["initialized"] else "pending explicit review"
    reviewer = (state.get("approval") or {}).get("reviewer", "not yet approved")
    history = "\n".join(
        f"| {cell(entry['date'])} | {cell(entry['actor'])} | {cell(entry['change'])} | {cell(entry['reason'])} |"
        for entry in state["history"]
    )
    return (
        "# ZzzOps project policy audit\n\n"
        f"Status: {status}. Reviewer: {reviewer}. Revision: {state['revision']}.\n\n"
        "## Evidence and decisions\n\n"
        f"{render_policy_sections(state['policy'])}\n\n"
        "## Review record\n\n"
        "| Date | Actor/run | Change | Reason/evidence |\n"
        "| --- | --- | --- | --- |\n"
        f"{history}\n\n"
        "The machine-readable authority is [POLICY.json](POLICY.json); this file is its human audit view.\n"
    )


def cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


# Policy rendering and text predicates are likewise exposed through the historic
# CLI module while their implementation lives in the acyclic policy module.
nonempty = _policy.nonempty
text_present = _policy.text_present
nonempty_list = _policy.nonempty_list
cell = _policy.cell
render_project = _policy.render_project
render_policy_sections = _policy.render_policy_sections
render_project_audit = _policy.render_project_audit


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
    _policy_path, policy_text, old_state = read_project_state(repo)
    revision = int(old_state.get("revision", 0)) + 1 if old_state else 1
    policy = json.loads(json.dumps(plan["policy"]))
    policy["evidence"] = plan["evidence"]
    state = {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "initialized": False,
        "backend": plan["backend"],
        "repository": plan["repository"],
        "revision": revision,
        "charter": plan["charter"],
        "policy": policy,
        "history": [{
            "date": date.today().isoformat(), "actor": "ZzzOps initialization",
            "change": f"Created pending revision {revision}",
            "reason": "Confirmed agent-generated draft; explicit policy review still required.",
        }],
        "bindings": {},
        "approval": None,
    }
    rendered = render_project(state)
    audit = render_project_audit(state)
    state["bindings"] = {
        "project": {"path": ".zzzops/PROJECT.md", "digest": project_digest(rendered)},
        "audit": {"path": PROJECT_AUDIT_RELATIVE, "digest": project_digest(audit)},
    }
    canonical = json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    changed = rendered != current or canonical != policy_text
    if changed:
        atomic_text(path, rendered)
        atomic_text(project_audit_path(repo), audit)
        atomic_text(project_policy_path(repo), canonical)
    return {
        "changed": changed, "path": str(path), "policy_path": str(project_policy_path(repo)), "revision": revision,
        "initialized": False,
        "decision_blockers": policy_blockers(plan["policy"]),
        "policy_digest": policy_review_digest(state),
        "review_required": "Review the summarized policy, then explicitly approve its current policy digest.",
    }


def confirm_project(repo: Path, digest: str, reviewer: str, section_ids: list[str], approve_all: bool) -> dict[str, Any]:
    path, _text, state = read_project_state(repo)
    if state is None:
        raise ValueError("Canonical policy is missing; run policy review first")
    if policy_review_digest(state) != digest:
        raise ValueError("Policy digest changed; review the exact current policy before confirming")
    errors = validate_project_state(state)
    errors.extend(validate_project_artifacts(repo, state))
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
    state["history"].append({
        "date": today,
        "actor": reviewer,
        "change": f"Reviewed policy revision {state['revision']}",
        "reason": f"Approved: {', '.join(selected)}; source digest {digest}.",
    })
    state["approval"] = None
    updated = render_project(state)
    audit_text = render_project_audit(state)
    state["bindings"] = {
        "project": {"path": ".zzzops/PROJECT.md", "digest": project_digest(updated)},
        "audit": {"path": PROJECT_AUDIT_RELATIVE, "digest": project_digest(audit_text)},
    }
    if not blockers:
        state["approval"] = {"reviewer": reviewer, "date": today, "digest": "pending"}
        updated = render_project(state)
        audit_text = render_project_audit(state)
        state["bindings"] = {
            "project": {"path": ".zzzops/PROJECT.md", "digest": project_digest(updated)},
            "audit": {"path": PROJECT_AUDIT_RELATIVE, "digest": project_digest(audit_text)},
        }
        state["approval"]["digest"] = policy_review_digest(state)
    atomic_text(project_path(repo), updated)
    atomic_text(project_audit_path(repo), audit_text)
    atomic_text(path, json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "changed": True,
        "path": str(project_path(repo)),
        "revision": state["revision"],
        "initialized": state["initialized"],
        "decision_blockers": blockers,
        "policy_digest": policy_review_digest(state),
    }


def main() -> int:
    configure_cli_stdout()
    parser = argparse.ArgumentParser(description="ZzzOps project control CLI")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Project root (default: current directory)")
    commands = parser.add_subparsers(dest="command")
    init = commands.add_parser("init", help="Inspect, validate, or apply agent-driven project initialization")
    init_commands = init.add_subparsers(dest="init_command", required=True)
    init_commands.add_parser("inspect", help="Report initialization state and read-only capabilities as JSON")
    validate_command = init_commands.add_parser("validate", help="Validate an agent-generated initialization plan")
    validate_command.add_argument("--plan", type=Path, required=True)
    apply_command = init_commands.add_parser("apply", help="Atomically apply a confirmed initialization plan")
    apply_command.add_argument("--plan", type=Path, required=True)
    confirm_command = init_commands.add_parser("confirm", help="Confirm explicit review of the exact current policy")
    confirm_command.add_argument("--policy-digest", required=True)
    confirm_command.add_argument("--reviewer", required=True)
    confirm_command.add_argument("--section", action="append", default=[])
    confirm_command.add_argument("--all", action="store_true", help="Approve every current policy section")
    checkpoint_parser = commands.add_parser("checkpoint", help="Validate initialized state, GitHub capability, and the goal portfolio once")
    checkpoint_parser.add_argument("--include-feedback", action="store_true", help="Include specially tagged feedback goals for this session")
    portfolio_parser = commands.add_parser("portfolio", help="Read and audit the canonical goal portfolio once")
    portfolio_parser.add_argument("--format", dest="output_format", choices=("summary", "json"), default="summary")
    portfolio_parser.add_argument("--include-done", action="store_true", help="Include terminal goals in summary output")
    portfolio_parser.add_argument("--compare", type=Path, help="Prior JSON snapshot used only to report digest/revision drift")
    portfolio_parser.add_argument("--include-feedback", action="store_true", help="Include specially tagged feedback goals")
    goal_command = commands.add_parser("goal", help="Apply validated GitHub-backed goal transitions")
    goal_commands = goal_command.add_subparsers(dest="goal_command", required=True)
    transition_command = goal_commands.add_parser("transition", help="Apply one file-backed managed-goal transition")
    transition_command.add_argument("--goal", type=int, required=True)
    transition_command.add_argument("--input", type=Path, required=True, help="UTF-8 transition JSON file")
    reserve = commands.add_parser("reserve", help="Atomically reserve a GitHub-backed goal")
    reserve_commands = reserve.add_subparsers(dest="reserve_command", required=True)
    for name in ("acquire", "renew", "release"):
        reserve_command = reserve_commands.add_parser(name)
        reserve_command.add_argument("--goal", type=int, required=True)
        reserve_command.add_argument("--revision", type=int, required=True)
        reserve_command.add_argument("--owner", required=True)
        reserve_command.add_argument("--run-id", required=True)
        reserve_command.add_argument("--resource", action="append", default=[], help="Known resource such as path:src/file")
        reserve_command.add_argument("--format", dest="output_format", choices=("summary", "json"), default="summary")
        if name != "release":
            reserve_command.add_argument("--ttl-seconds", type=int, help="Override reviewed claim_ttl_hours")
    report = commands.add_parser("report", help="Record or inspect privacy-safe machinery execution reports")
    report_commands = report.add_subparsers(dest="report_command", required=True)
    report_record = report_commands.add_parser("record", help="Record one constrained machinery observation")
    report_record.add_argument("--workflow", choices=sorted(EXECUTION_REPORT_WORKFLOWS), required=True)
    report_record.add_argument("--agent", choices=sorted(EXECUTION_REPORT_AGENTS), required=True)
    report_record.add_argument("--issue", choices=sorted(EXECUTION_REPORT_ISSUES), required=True)
    report_record.add_argument("--cause", choices=sorted(EXECUTION_REPORT_CAUSES), required=True)
    report_record.add_argument("--phase", choices=sorted(EXECUTION_REPORT_PHASES), required=True)
    report_record.add_argument("--occurrences", type=int, default=1)
    report_record.add_argument("--wait-seconds", type=int, default=0)
    report_record.add_argument("--extra-tool-calls", type=int, default=0)
    report_record.add_argument("--estimated-tokens", type=int, default=0)
    report_list = report_commands.add_parser("list", help="List valid archived reports")
    report_list.add_argument("--report", action="append", default=[], help="Select a report id; repeat as needed")
    feedback = commands.add_parser("feedback", help="Preview or submit feedback to the public ZzzOps repository")
    feedback_commands = feedback.add_subparsers(dest="feedback_command", required=True)
    for name in ("prepare", "submit"):
        feedback_command = feedback_commands.add_parser(name)
        feedback_command.add_argument(
            "--prompt-file", default="-",
            help="UTF-8 user feedback file, or - for stdin (default)",
        )
        feedback_command.add_argument("--report", action="append", default=[], help="Select a report id; repeat as needed")
        if name == "submit":
            feedback_command.add_argument("--confirm", required=True, help="Exact digest shown by feedback prepare")
    args = parser.parse_args()
    repo = args.repo.resolve()
    if not (repo / ".agents" / "zzzops" / "templates" / "project-goals" / "INIT_PLAN.json").is_file():
        print(f"ZzzOps is not installed at {repo}.")
        return 2
    try:
        if args.command == "checkpoint":
            result = decision_checkpoint(repo, args.include_feedback)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return 0 if result["ready"] else 2
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
                result = confirm_project(repo, args.policy_digest, args.reviewer, args.section, args.all)
                print(json.dumps(result, indent=2))
        elif args.command == "portfolio":
            try:
                result = portfolio_snapshot(repo, args.include_feedback)
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
                    print(f"Could not load goals: {exc}")
                return 2
        elif args.command == "goal":
            project = reviewed_project_state(repo)
            repository = _project_repository_identity(project)
            transition = load_goal_transition(args.input)
            adapter = GitHubGoalTransitionAdapter(repo, repository)
            result = apply_goal_transition(adapter, repository, args.goal, transition)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        elif args.command == "reserve":
            project = reviewed_project_state(repo)
            repository = _project_repository_identity(project)
            resource_policy = project_resource_policy(project)
            adapter = GitHubReservationAdapter(repo, repository)
            ttl_seconds = None
            if args.reserve_command != "release":
                ttl_seconds = args.ttl_seconds if args.ttl_seconds is not None else project_claim_ttl_seconds(project)
            if args.reserve_command == "acquire":
                result = acquire_reservation_bundle(
                    adapter, repository, args.goal, args.revision, args.owner, args.run_id, args.resource, ttl_seconds,
                    resource_policy=resource_policy,
                )
            elif args.reserve_command == "renew":
                result = renew_reservation_bundle(
                    adapter, repository, args.goal, args.revision, args.owner, args.run_id, args.resource, ttl_seconds,
                    resource_policy=resource_policy,
                )
            else:
                result = release_reservation_bundle(
                    adapter, repository, args.goal, args.revision, args.owner, args.run_id, args.resource,
                    resource_policy=resource_policy,
                )
            if args.output_format == "json":
                print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            else:
                print(reservation_cli_message(result, args.goal))
            return 0 if result.get("acquired") is True or result.get("released") is True else 3
        elif args.command == "report":
            if args.report_command == "record":
                project = reviewed_project_state(repo)
                result = record_execution_report(
                    repo, project, workflow=args.workflow, agent=args.agent, issue=args.issue,
                    cause=args.cause, phase=args.phase,
                    occurrences=args.occurrences, wait_seconds=args.wait_seconds,
                    extra_tool_calls=args.extra_tool_calls, estimated_tokens=args.estimated_tokens,
                )
            else:
                result = {"reports": load_execution_reports(repo, args.report or None)}
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        elif args.command == "feedback":
            prompt = read_cli_text(args.prompt_file)
            selected = args.report or None
            if args.feedback_command == "prepare":
                result = prepare_feedback(repo, prompt, selected)
            else:
                result = submit_feedback(repo, prompt, args.confirm, selected)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        else:
            parser.print_help()
    except (EOFError, KeyboardInterrupt):
        print("\nNo further changes made.")
    except ValueError as exc:
        print(f"Could not continue: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
