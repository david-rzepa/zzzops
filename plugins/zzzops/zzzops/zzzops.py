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
from urllib.parse import quote, urlparse

_PACKAGE_MODULE_PATH = Path(__file__).with_name("package.py")
_PACKAGE_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_package", _PACKAGE_MODULE_PATH)
assert _PACKAGE_MODULE_SPEC and _PACKAGE_MODULE_SPEC.loader
_package = importlib.util.module_from_spec(_PACKAGE_MODULE_SPEC)
sys.modules[_PACKAGE_MODULE_SPEC.name] = _package
_PACKAGE_MODULE_SPEC.loader.exec_module(_package)

_INSTALLATION_MODULE_PATH = Path(__file__).with_name("installation.py")
_INSTALLATION_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_installation", _INSTALLATION_MODULE_PATH)
assert _INSTALLATION_MODULE_SPEC and _INSTALLATION_MODULE_SPEC.loader
_installation = importlib.util.module_from_spec(_INSTALLATION_MODULE_SPEC)
sys.modules[_INSTALLATION_MODULE_SPEC.name] = _installation
_INSTALLATION_MODULE_SPEC.loader.exec_module(_installation)

_ENTROPY_MODULE_PATH = Path(__file__).with_name("entropy.py")
_ENTROPY_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_entropy", _ENTROPY_MODULE_PATH)
assert _ENTROPY_MODULE_SPEC and _ENTROPY_MODULE_SPEC.loader
_entropy = importlib.util.module_from_spec(_ENTROPY_MODULE_SPEC)
sys.modules[_ENTROPY_MODULE_SPEC.name] = _entropy
_ENTROPY_MODULE_SPEC.loader.exec_module(_entropy)

_ENTROPY_REVIEW_MODULE_PATH = Path(__file__).with_name("entropy_review.py")
_ENTROPY_REVIEW_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_entropy_review", _ENTROPY_REVIEW_MODULE_PATH)
assert _ENTROPY_REVIEW_MODULE_SPEC and _ENTROPY_REVIEW_MODULE_SPEC.loader
_entropy_review = importlib.util.module_from_spec(_ENTROPY_REVIEW_MODULE_SPEC)
sys.modules[_ENTROPY_REVIEW_MODULE_SPEC.name] = _entropy_review
_ENTROPY_REVIEW_MODULE_SPEC.loader.exec_module(_entropy_review)

_DIAGNOSTICS_MODULE_PATH = Path(__file__).with_name("diagnostics.py")
_DIAGNOSTICS_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_diagnostics", _DIAGNOSTICS_MODULE_PATH)
assert _DIAGNOSTICS_MODULE_SPEC and _DIAGNOSTICS_MODULE_SPEC.loader
_diagnostics = importlib.util.module_from_spec(_DIAGNOSTICS_MODULE_SPEC)
sys.modules[_DIAGNOSTICS_MODULE_SPEC.name] = _diagnostics
_DIAGNOSTICS_MODULE_SPEC.loader.exec_module(_diagnostics)

_PLUGIN_FRESHNESS_MODULE_PATH = Path(__file__).with_name("plugin_freshness.py")
_PLUGIN_FRESHNESS_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_plugin_freshness", _PLUGIN_FRESHNESS_MODULE_PATH)
assert _PLUGIN_FRESHNESS_MODULE_SPEC and _PLUGIN_FRESHNESS_MODULE_SPEC.loader
_plugin_freshness = importlib.util.module_from_spec(_PLUGIN_FRESHNESS_MODULE_SPEC)
sys.modules[_PLUGIN_FRESHNESS_MODULE_SPEC.name] = _plugin_freshness
_PLUGIN_FRESHNESS_MODULE_SPEC.loader.exec_module(_plugin_freshness)

_POLICY_MODULE_PATH = Path(__file__).with_name("policy.py")
_POLICY_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_policy", _POLICY_MODULE_PATH)
assert _POLICY_MODULE_SPEC and _POLICY_MODULE_SPEC.loader
_policy = importlib.util.module_from_spec(_POLICY_MODULE_SPEC)
sys.modules[_POLICY_MODULE_SPEC.name] = _policy
_POLICY_MODULE_SPEC.loader.exec_module(_policy)
_policy.configure_entrypoint(package_provenance=_package.package_provenance)

_ROUTING_MODULE_PATH = Path(__file__).with_name("routing.py")
_ROUTING_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_routing", _ROUTING_MODULE_PATH)
assert _ROUTING_MODULE_SPEC and _ROUTING_MODULE_SPEC.loader
_routing = importlib.util.module_from_spec(_ROUTING_MODULE_SPEC)
sys.modules[_ROUTING_MODULE_SPEC.name] = _routing
_ROUTING_MODULE_SPEC.loader.exec_module(_routing)

_BOOTSTRAP_MODULE_PATH = Path(__file__).with_name("bootstrap.py")
_BOOTSTRAP_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_bootstrap", _BOOTSTRAP_MODULE_PATH)
assert _BOOTSTRAP_MODULE_SPEC and _BOOTSTRAP_MODULE_SPEC.loader
_bootstrap = importlib.util.module_from_spec(_BOOTSTRAP_MODULE_SPEC)
sys.modules[_BOOTSTRAP_MODULE_SPEC.name] = _bootstrap
_BOOTSTRAP_MODULE_SPEC.loader.exec_module(_bootstrap)
_RESERVATION_MODULE_PATH = Path(__file__).with_name("reservation.py")
_RESERVATION_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_reservation", _RESERVATION_MODULE_PATH)
assert _RESERVATION_MODULE_SPEC and _RESERVATION_MODULE_SPEC.loader
_reservation = importlib.util.module_from_spec(_RESERVATION_MODULE_SPEC)
sys.modules[_RESERVATION_MODULE_SPEC.name] = _reservation
_RESERVATION_MODULE_SPEC.loader.exec_module(_reservation)

_FEEDBACK_MODULE_PATH = Path(__file__).with_name("feedback.py")
_FEEDBACK_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_feedback", _FEEDBACK_MODULE_PATH)
assert _FEEDBACK_MODULE_SPEC and _FEEDBACK_MODULE_SPEC.loader
_feedback = importlib.util.module_from_spec(_FEEDBACK_MODULE_SPEC)
sys.modules[_FEEDBACK_MODULE_SPEC.name] = _feedback
_FEEDBACK_MODULE_SPEC.loader.exec_module(_feedback)

_COACHING_MODULE_PATH = Path(__file__).with_name("coaching.py")
_COACHING_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_coaching", _COACHING_MODULE_PATH)
assert _COACHING_MODULE_SPEC and _COACHING_MODULE_SPEC.loader
_coaching = importlib.util.module_from_spec(_COACHING_MODULE_SPEC)
sys.modules[_COACHING_MODULE_SPEC.name] = _coaching
_COACHING_MODULE_SPEC.loader.exec_module(_coaching)

_PHASE_EVIDENCE_MODULE_PATH = Path(__file__).with_name("phase_evidence.py")
_PHASE_EVIDENCE_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_phase_evidence", _PHASE_EVIDENCE_MODULE_PATH)
assert _PHASE_EVIDENCE_MODULE_SPEC and _PHASE_EVIDENCE_MODULE_SPEC.loader
_phase_evidence = importlib.util.module_from_spec(_PHASE_EVIDENCE_MODULE_SPEC)
sys.modules[_PHASE_EVIDENCE_MODULE_SPEC.name] = _phase_evidence
_PHASE_EVIDENCE_MODULE_SPEC.loader.exec_module(_phase_evidence)

_GOALS_MODULE_PATH = Path(__file__).with_name("goals.py")
_GOALS_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_goals", _GOALS_MODULE_PATH)
assert _GOALS_MODULE_SPEC and _GOALS_MODULE_SPEC.loader
_goals = importlib.util.module_from_spec(_GOALS_MODULE_SPEC)
sys.modules[_GOALS_MODULE_SPEC.name] = _goals
_GOALS_MODULE_SPEC.loader.exec_module(_goals)

_PORTFOLIO_MODULE_PATH = Path(__file__).with_name("portfolio.py")
_PORTFOLIO_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_portfolio", _PORTFOLIO_MODULE_PATH)
assert _PORTFOLIO_MODULE_SPEC and _PORTFOLIO_MODULE_SPEC.loader
_portfolio = importlib.util.module_from_spec(_PORTFOLIO_MODULE_SPEC)
sys.modules[_PORTFOLIO_MODULE_SPEC.name] = _portfolio
_PORTFOLIO_MODULE_SPEC.loader.exec_module(_portfolio)

_MERGE_RECONCILIATION_MODULE_PATH = Path(__file__).with_name("merge_reconciliation.py")
_MERGE_RECONCILIATION_MODULE_SPEC = importlib.util.spec_from_file_location("zzzops_merge_reconciliation", _MERGE_RECONCILIATION_MODULE_PATH)
assert _MERGE_RECONCILIATION_MODULE_SPEC and _MERGE_RECONCILIATION_MODULE_SPEC.loader
_merge_reconciliation = importlib.util.module_from_spec(_MERGE_RECONCILIATION_MODULE_SPEC)
sys.modules[_MERGE_RECONCILIATION_MODULE_SPEC.name] = _merge_reconciliation
_MERGE_RECONCILIATION_MODULE_SPEC.loader.exec_module(_merge_reconciliation)

PROJECT_SCHEMA_VERSION = _policy.PROJECT_SCHEMA_VERSION
PLAN_SCHEMA_VERSION = 1
POLICY_SCHEMA_VERSION = _policy.POLICY_SCHEMA_VERSION
GOAL_SCHEMA_VERSION = 1
GOAL_TRANSITION_SCHEMA_VERSION = 1
PORTFOLIO_SCHEMA_VERSION = _portfolio.PORTFOLIO_SCHEMA_VERSION
PROJECT_POLICY_RELATIVE = _policy.PROJECT_POLICY_RELATIVE
PROJECT_AUDIT_RELATIVE = _policy.PROJECT_AUDIT_RELATIVE
GOAL_BLOCK_START = "<!-- zzzops-goal"
GOAL_BLOCK_END = "zzzops-goal -->"
BACKENDS = _policy.BACKENDS
POLICY_SECTION_IDS = _policy.POLICY_SECTION_IDS
policy_default_catalog = _policy.policy_default_catalog
policy_content_digest = _policy.policy_content_digest
compare_bootstrap_capabilities = _bootstrap.compare_bootstrap_capabilities
prepare_policy_defaults = _policy.prepare_policy_defaults
compare_policy_defaults = _policy.compare_policy_defaults
missing_policy_settings = _policy.missing_policy_settings
policy_review_rows = _policy.policy_review_rows
render_policy_review_table = _policy.render_policy_review_table
capability_tier = _policy.capability_tier
phase_evidence_graph = _policy.phase_evidence_graph
reviewed_model_effort = _policy.reviewed_model_effort
reviewed_phase_assignment = _policy.reviewed_phase_assignment
model_inventory_freshness = _policy.model_inventory_freshness
phase_policy_freshness = _policy.phase_policy_freshness
route_phase = _routing.route_phase
prepare_phase_assignment = _routing.prepare_phase_assignment
prepare_reviewed_phase_assignment = _routing.prepare_reviewed_phase_assignment
validate_launch_plan = _routing.validate_launch_plan
routing_event = _routing.routing_event
discover_delegation_capability = _routing.discover_delegation_capability
GOAL_FIELDS = _goals.GOAL_FIELDS
workflow_adoption_assessment = _goals.workflow_adoption_assessment
GOAL_TRANSITION_FIELDS = {"schema_version", "expected_revision", "expected_digest", "goal"}
PHASE_EVIDENCE_SCHEMA_VERSION = _phase_evidence.PHASE_EVIDENCE_SCHEMA_VERSION
PhaseEvidenceError = _phase_evidence.PhaseEvidenceError
canonical_json_bytes = _phase_evidence.canonical_json_bytes
sha256_phase_evidence_digest = _phase_evidence.sha256_digest
empty_phase_evidence = _phase_evidence.empty_phase_evidence
phase_input_envelope = _phase_evidence.phase_input_envelope
goal_spec_digest = _phase_evidence.goal_spec_digest
validate_phase_evidence = _phase_evidence.validate_phase_evidence
normalize_phase_evidence = _phase_evidence.normalize_phase_evidence
record_phase_result = _phase_evidence.record_phase_result
record_phase_review = _phase_evidence.record_phase_review
withdraw_phase_evidence = _phase_evidence.withdraw_phase_evidence
derive_phase_eligibility = _phase_evidence.derive_phase_eligibility
derive_phase_steps = _phase_evidence.derive_phase_steps
BLOCKER_CATEGORIES = {
    "specification", "decision", "access-approval", "human-action",
    "external-dependency", "technical-unknown", "safety-compliance",
}
WORKFLOW_INTENTS = {"capture", "execute", "approve", "resume", "inspect"}
WORKFLOW_DEFAULT_SKILLS = {
    "capture": "$add-zzzops-goal", "execute": "$execute-zzzops", "approve": "$execute-zzzops",
    "resume": "$execute-zzzops", "inspect": "$review-zzzops-policy",
}
WORKFLOW_SKILL_INTENTS = {
    "$add-zzzops-goal": {"capture"}, "$execute-zzzops": {"execute", "approve", "resume"},
    "$bootstrap-zzzops-repository": {"inspect"}, "$migrate-to-zzzops": {"inspect"},
    "$review-agentic-engineering": {"inspect"}, "$review-zzzops-entropy": {"execute"},
    "$review-zzzops-policy": {"inspect"}, "$send-zzzops-feedback": {"execute"},
    "$suggest-zzzops-work": {"inspect"}, "$validate-zzzops-installation": {"inspect"},
}
WORKFLOW_SOURCE_ACTIONS = {
    "$add-zzzops-goal": "Capture the requested outcome and durable goal evidence.",
    "$bootstrap-zzzops-repository": "Inspect repository and product evidence for the bootstrap workflow.",
    "$migrate-to-zzzops": "Inspect candidate legacy work and its adoption evidence.",
    "$review-agentic-engineering": "Inspect completed-work evidence for the requested agentic-engineering review.",
    "$review-zzzops-entropy": "Inspect the requested entropy-review evidence and coverage state.",
    "$review-zzzops-policy": "Inspect policy state and prepare the required review input.",
    "$send-zzzops-feedback": "Inspect the requested feedback evidence and exact submission preconditions.",
    "$suggest-zzzops-work": "Inspect bounded repository evidence for possible work suggestions.",
    "$validate-zzzops-installation": "Inspect installed-package validation evidence for this repository.",
}


def workflow_envelope(intent: str, steps: Any) -> dict[str, Any]:
    """Validate the action-only public workflow response."""
    if intent not in WORKFLOW_INTENTS or not isinstance(steps, list):
        raise ValueError("workflow response is invalid")
    seen, normalized = set(), []
    for step in steps:
        fields = {"id", "skill", "intent", "audience", "phase", "action", "reason"}
        optional_fields = {"directive", "model", "effort"}
        if not isinstance(step, dict) or not fields <= set(step) or set(step) - fields - optional_fields or step.get("id") in seen:
            raise ValueError("workflow next step is invalid")
        if step.get("intent") not in WORKFLOW_INTENTS or step["intent"] not in WORKFLOW_SKILL_INTENTS.get(step.get("skill"), set()) or step.get("audience") not in {"root", "worker"}:
            raise ValueError("workflow next step is invalid")
        if any(not isinstance(step.get(field), str) or not step[field] for field in fields):
            raise ValueError("workflow next step is invalid")
        if step.get("directive") not in {None, "delegate", "continue_root", "resolve_blocker"}:
            raise ValueError("workflow next step is invalid")
        if ("model" in step) != ("effort" in step) or any(
            not isinstance(step.get(field), str) or not step[field]
            for field in {"model", "effort"} if field in step
        ):
            raise ValueError("workflow next step is invalid")
        if step.get("directive") == "delegate" and ("model" not in step or "effort" not in step):
            raise ValueError("workflow next step is invalid")
        if step.get("directive") != "delegate" and ("model" in step or "effort" in step):
            raise ValueError("workflow next step is invalid")
        seen.add(step["id"])
        normalized.append(dict(step))
    return {"schema_version": 1, "next_steps": normalized}


def workflow_repair_step(intent: str, reason: str, action: str, *, source_skill: str | None = None) -> dict[str, Any]:
    """Return the one actionable repair step for a failed public invocation."""
    skill = source_skill if source_skill in WORKFLOW_SKILL_INTENTS and intent in WORKFLOW_SKILL_INTENTS[source_skill] else WORKFLOW_DEFAULT_SKILLS[intent]
    return {
        "id": "workflow-repair", "skill": skill, "intent": intent,
        "audience": "root", "phase": "context", "directive": "resolve_blocker",
        "action": action, "reason": reason,
    }


def workflow_context_step(
    repo: Path, package: dict[str, Any], *, source_skill: str | None = None,
) -> dict[str, Any] | None:
    """Derive the mandatory shared context gate without retaining workflow state."""
    provenance = {field: package.get(field) for field in ("version", "revision")}
    if all(isinstance(value, str) and value for value in provenance.values()):
        status = _installation.validation_status(repo, provenance)
        if status.get("required") is True and source_skill != "$validate-zzzops-installation":
            return {
                "id": "installation-validation", "skill": "$validate-zzzops-installation", "intent": "inspect",
                "audience": "root", "phase": "context",
                "action": "Validate the installed ZzzOps package for this repository, then invoke workflow again.",
                "reason": f"Repository installation validation is required ({status.get('reason')}).",
            }
    inspection = inspect_initialization(repo)
    if inspection.get("initialized") is True:
        return None
    if inspection.get("state") is None:
        return {
            "id": "bootstrap", "skill": "$bootstrap-zzzops-repository", "intent": "inspect",
            "audience": "root", "phase": "context",
            "action": "Bootstrap repository policy and canonical context, then invoke workflow again.",
            "reason": str(inspection.get("state_error") or "Canonical project policy is missing."),
        }
    return {
        "id": "policy-review", "skill": "$review-zzzops-policy", "intent": "inspect",
        "audience": "root", "phase": "context",
        "action": "Inspect policy state and prepare the required review input.",
        "reason": "; ".join(inspection.get("decision_blockers") or ["Project policy is not ready."]),
    }


def workflow_routing_step(intent: str, settings: Any, request: Any) -> dict[str, Any]:
    """Turn reviewed routing facts into an imperative workflow instruction.

    The caller supplies observed harness facts, while policy selects the route.
    This deliberately leaves no agent-side delegation heuristic: a ready worker
    route emits ``delegate`` with its exact model-plus-effort pair; an
    unavailable harness emits a blocker instead.
    """
    fields = {"phase", "dimensions", "available_pairs", "root_pair", "tool_catalog"}
    if not isinstance(request, dict) or set(request) != fields:
        raise ValueError("workflow routing request is invalid")
    assignment = prepare_reviewed_phase_assignment(
        reviewed_phase_assignment(
            settings, request["dimensions"], request["available_pairs"], request["root_pair"],
        ),
        request["tool_catalog"],
    )
    phase = request["phase"]
    if not isinstance(phase, str) or not phase:
        raise ValueError("workflow routing request is invalid")
    directive = assignment["next_step"]
    if directive["action"] == "delegate":
        selected = assignment["selected"]
        return {
            "id": f"delegate-{phase}", "skill": "$execute-zzzops", "intent": "execute",
            "audience": "root", "phase": phase,
            "directive": "delegate",
            "action": directive["instruction"],
            "reason": "Reviewed routing requires a worker for this phase.",
            "model": selected["model"], "effort": selected["effort"],
        }
    if directive["action"] == "continue_root":
        return {
            "id": f"root-{phase}", "skill": "$execute-zzzops", "intent": "execute",
            "audience": "root", "phase": phase,
            "directive": "continue_root",
            "action": directive["instruction"],
            "reason": "Reviewed routing requires root execution for this phase.",
        }
    return {
        "id": f"routing-blocker-{phase}", "skill": "$execute-zzzops", "intent": "execute",
        "audience": "root", "phase": phase,
        "directive": "resolve_blocker",
        "action": directive["instruction"],
        "reason": str(assignment.get("reason") or "Routing is not executable."),
    }


def workflow_phase_frontier(
    goal: dict[str, Any], phase_dag: Any, live_inputs: dict[str, dict[str, Any]],
    related_goals: dict[Any, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project the evidence-derived phase DAG into an ordered action frontier.

    The projection deliberately does not let a skill select delegation.  Root
    phases are explicit root work. Every other eligible phase is an explicit
    routing-evidence prerequisite, after which ``workflow_routing_step`` emits
    the sole permitted launch directive.
    """
    if not isinstance(phase_dag, dict) or not isinstance(phase_dag.get("phases"), list):
        raise ValueError("workflow phase DAG is invalid")
    graph = phase_evidence_graph(phase_dag, has_parent=goal.get("parent") is not None)
    eligibility = derive_phase_eligibility(goal, graph, live_inputs, related_goals)
    nodes = {
        node.get("id"): node for node in phase_dag["phases"]
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    steps = []
    for item in eligibility["eligible"]:
        phase = item["phase"]
        node = nodes.get(phase)
        if not isinstance(node, dict):
            raise ValueError("workflow phase DAG is invalid")
        if node.get("assignment_group") == "root":
            steps.append({
                "id": f"root-{phase}", "skill": "$execute-zzzops", "intent": "execute",
                "audience": "root", "phase": phase, "directive": "continue_root",
                "action": f"Perform the {phase} phase on the root agent.",
                "reason": f"The reviewed phase DAG assigns {phase} to the root agent ({item['reason']}).",
            })
        else:
            steps.append({
                "id": f"routing-evidence-{phase}", "skill": "$execute-zzzops", "intent": "execute",
                "audience": "root", "phase": phase,
                "action": f"Record complete routing evidence for the {phase} phase, then invoke workflow routing.",
                "reason": f"The {phase} phase is eligible ({item['reason']}) but its reviewed model-and-effort assignment has not yet been evaluated.",
            })
    return {"eligibility": eligibility, "next_steps": steps}
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
        number title state
        labels(first:100){nodes{name}}
      }
      pageInfo{hasNextPage endCursor}
    }
  }
}
""".strip()
GITHUB_GOAL_HISTORY_QUERY = """
query($owner:String!,$name:String!,$number:Int!,$endCursor:String){
  repository(owner:$owner,name:$name){
    issue(number:$number){
      comments(first:100,after:$endCursor){
        nodes{body createdAt url author{login}}
        pageInfo{hasNextPage endCursor}
      }
    }
  }
}
""".strip()
GOAL_SCHEMA_LABEL = re.compile(r"^zzzops:schema:v(?P<version>[1-9][0-9]*)$")
GOAL_HYDRATION_BATCH_SIZE = 100
MANAGED_SKILLS = (
    "add-zzzops-goal", "bootstrap-zzzops-repository", "execute-zzzops", "migrate-to-zzzops",
    "review-agentic-engineering", "review-zzzops-entropy", "review-zzzops-policy", "send-zzzops-feedback", "suggest-zzzops-work",
    "validate-zzzops-installation",
)
GITHUB_MANAGEMENT_PERMISSIONS = {"TRIAGE", "WRITE", "MAINTAIN", "ADMIN"}
RESERVATION_COLOR = "5319E7"
RESERVATION_ID = re.compile(r"^[A-Za-z0-9._-]+$")
RESERVATION_EXPIRY_GRACE_SECONDS = 60
RESOURCE_LABEL_PREFIX = "zzzops:resource:"


class ReservationProviderError(ValueError):
    """The provider did not produce a safe, confirmed reservation result."""


ReservationProviderError = _reservation.ReservationProviderError
GoalTransitionProviderError = _goals.GoalTransitionProviderError
_reservation_actor = _reservation._reservation_actor
reservation_label_name = _reservation.reservation_label_name
reservation_repository_key = _reservation.reservation_repository_key
resource_label_name = _reservation.resource_label_name
reservation_description = _reservation.reservation_description
parse_reservation_description = _reservation.parse_reservation_description
phase_lease_label_name = _reservation.phase_lease_label_name
storage_lock_label_name = _reservation.storage_lock_label_name
storage_lock_description = _reservation.storage_lock_description
acquire_storage_lock = _reservation.acquire_storage_lock
renew_storage_lock = _reservation.renew_storage_lock
release_storage_lock = _reservation.release_storage_lock
parse_storage_lock_description = _reservation.parse_storage_lock_description
phase_lease_description = _reservation.phase_lease_description
parse_phase_lease_description = _reservation.parse_phase_lease_description
normalize_resources = _policy.normalize_resources
normalize_resource_policy = _policy.normalize_resource_policy
exclusive_resources = _policy.exclusive_resources

_cycle_nodes = _portfolio._cycle_nodes
_portfolio_key = _portfolio._portfolio_key
audit_portfolio = _portfolio.audit_portfolio
build_portfolio_snapshot = _portfolio.build_portfolio_snapshot
compact_portfolio_output = _portfolio.compact_portfolio_output
classify_pr_merge = _merge_reconciliation.classify_pr_merge
build_reconciliation_transition = _merge_reconciliation.build_reconciliation_transition
derive_engineering_rigor = _portfolio.derive_engineering_rigor

parse_managed_goal = _goals.parse_managed_goal
validate_managed_goal = _goals.validate_managed_goal
render_managed_goal = _goals.render_managed_goal
compact_human_goal_text = _goals.compact_human_goal_text
compact_managed_goal = _goals.compact_managed_goal
validate_compact_goal_body = _goals.validate_compact_goal_body
goal_history_id = _goals.goal_history_id
render_goal_history = _goals.render_goal_history
parse_goal_history = _goals.parse_goal_history
goal_needs_human = _goals.goal_needs_human
validate_github_issue_goal = _goals.validate_github_issue_goal
github_goal_record = _goals.github_goal_record
github_archived_goal_record = _goals.github_archived_goal_record
current_goal_schema_label = _goals.current_goal_schema_label
validate_goal_transition = _goals.validate_goal_transition
load_goal_transition = _goals.load_goal_transition
apply_goal_transition = _goals.apply_goal_transition
apply_independent_goal_transitions = _goals.apply_independent_goal_transitions
validate_goal_create = _goals.validate_goal_create
load_goal_create = _goals.load_goal_create
apply_goal_create = _goals.apply_goal_create
ensure_current_goal_schema = _goals.ensure_current_goal_schema
migrate_open_goal_schemas = _goals.migrate_open_goal_schemas

entropy_observation_directory = _entropy.observation_directory
enabled_entropy_categories = _entropy.enabled_categories
list_entropy_observations = _entropy.list_observations
record_entropy_observation = _entropy.record_observation
record_entropy_observation_checkpoint = _entropy.record_observation_checkpoint
resolve_entropy_observations = _entropy.resolve_observations
EntropyObservationError = _entropy.EntropyObservationError

entropy_review_directory = _entropy_review.review_directory
normalize_entropy_review_event = _entropy_review.normalize_review_event
record_entropy_review_event = _entropy_review.record_review_event
entropy_review_status = _entropy_review.entropy_review_status
plan_entropy_review = _entropy_review.plan_entropy_review
complete_entropy_review = _entropy_review.complete_entropy_review
load_entropy_review_json = _entropy_review.load_review_json
EntropyReviewError = _entropy_review.EntropyReviewError

TimingSession = _diagnostics.TimingSession
diagnostic_directory = _diagnostics.diagnostic_directory
validate_diagnostic = _diagnostics.validate_diagnostic
record_diagnostic = _diagnostics.record_diagnostic
list_diagnostics = _diagnostics.list_diagnostics
purge_diagnostics = _diagnostics.purge_diagnostics
timing_suggestion = _diagnostics.timing_suggestion
load_diagnostic = _diagnostics.load_diagnostic
delete_diagnostic = _diagnostics.delete_diagnostic
DiagnosticError = _diagnostics.DiagnosticError


def _timed_call(timing: Any, phase: str, operation: Any) -> Any:
    if timing is None:
        return operation()
    with timing.span(phase):
        return operation()

execution_reports_enabled = _feedback.execution_reports_enabled
execution_report_directory = _feedback.execution_report_directory
execution_report_id = _feedback.execution_report_id
_validated_zzzops_provenance = _feedback._validated_zzzops_provenance
zzzops_provenance = _feedback.zzzops_provenance
validate_execution_report = _feedback.validate_execution_report
validate_timing_feedback = _feedback.validate_timing_feedback
record_execution_report = _feedback.record_execution_report
load_execution_reports = _feedback.load_execution_reports
prepare_feedback = _feedback.prepare_feedback
submit_feedback = _feedback.submit_feedback
EXECUTION_REPORT_SCHEMA_VERSION = _feedback.EXECUTION_REPORT_SCHEMA_VERSION
LEGACY_EXECUTION_REPORT_SCHEMA_VERSION = _feedback.LEGACY_EXECUTION_REPORT_SCHEMA_VERSION
EXECUTION_REPORT_TARGET = _feedback.EXECUTION_REPORT_TARGET
EXECUTION_REPORT_TITLE = _feedback.EXECUTION_REPORT_TITLE
EXECUTION_REPORT_LABELS = _feedback.EXECUTION_REPORT_LABELS
EXECUTION_REPORT_WORKFLOWS = _feedback.EXECUTION_REPORT_WORKFLOWS
EXECUTION_REPORT_AGENTS = _feedback.EXECUTION_REPORT_AGENTS
EXECUTION_REPORT_ISSUES = _feedback.EXECUTION_REPORT_ISSUES
EXECUTION_REPORT_CAUSES = _feedback.EXECUTION_REPORT_CAUSES
EXECUTION_REPORT_PHASES = _feedback.EXECUTION_REPORT_PHASES
EXECUTION_REPORT_V2_FIELDS = _feedback.EXECUTION_REPORT_V2_FIELDS
EXECUTION_REPORT_FIELDS = _feedback.EXECUTION_REPORT_FIELDS
EXECUTION_REPORT_ID = _feedback.EXECUTION_REPORT_ID
ZZZOPS_VERSION = _feedback.ZZZOPS_VERSION
ZZZOPS_REVISION = _feedback.ZZZOPS_REVISION
attribute_agent_work = _coaching.attribute_agent_work
COACHING_SCHEMA_VERSION = _coaching.COACHING_SCHEMA_VERSION
COACHING_SIGNAL_CATEGORIES = _coaching.COACHING_SIGNAL_CATEGORIES


GitHubReservationAdapter = _reservation.GitHubReservationAdapter


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
                f"GitHub did not confirm the goal operation ({type(exc).__name__}); success was not assumed."
            ) from exc

    @staticmethod
    def _provider_error(result: subprocess.CompletedProcess[str]) -> GoalTransitionProviderError:
        detail = sanitize_output((result.stderr.strip() or result.stdout.strip() or "unknown GitHub error").splitlines()[0][:300])
        return GoalTransitionProviderError(f"GitHub did not confirm the goal operation: {detail}")

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

    def create_issue(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_identity()
        result = self._run(
            ["api", "--method", "POST", f"repos/{self.repository}/issues", "--input", "-"],
            input_text=json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
        if result.returncode:
            raise self._provider_error(result)
        try:
            issue = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise GoalTransitionProviderError(
                "GitHub returned an invalid goal-create response; success was not assumed."
            ) from exc
        if not isinstance(issue, dict):
            raise GoalTransitionProviderError(
                "GitHub returned an incomplete goal-create response; success was not assumed."
            )
        return issue

    def get_issue_comments(self, number: int) -> list[dict[str, Any]]:
        self.ensure_identity()
        result = self._run([
            "api", "--paginate", "--slurp",
            f"repos/{self.repository}/issues/{number}/comments?per_page=100",
        ])
        if result.returncode:
            raise self._provider_error(result)
        try:
            pages = json.loads(result.stdout)
            if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
                raise TypeError("comment pages must be lists")
            comments = [comment for page in pages for comment in page]
            if any(not isinstance(comment, dict) for comment in comments):
                raise TypeError("comments must be objects")
            return comments
        except (json.JSONDecodeError, TypeError) as exc:
            raise GoalTransitionProviderError(
                "GitHub returned invalid goal history; no body update was made."
            ) from exc

    def create_issue_comment(self, number: int, body: str) -> dict[str, Any]:
        result = self._run(
            ["api", "--method", "POST", f"repos/{self.repository}/issues/{number}/comments", "--input", "-"],
            input_text=json.dumps({"body": body}, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
        if result.returncode:
            raise self._provider_error(result)
        try:
            comment = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise GoalTransitionProviderError(
                "GitHub returned an invalid history response; body replacement was not attempted."
            ) from exc
        if not isinstance(comment, dict):
            raise GoalTransitionProviderError(
                "GitHub returned an incomplete history response; body replacement was not attempted."
            )
        return comment


_validate_reservation_goal = _reservation._validate_reservation_goal
acquire_reservation = _reservation.acquire_reservation
renew_reservation = _reservation.renew_reservation
release_reservation = _reservation.release_reservation
acquire_reservation_bundle = _reservation.acquire_reservation_bundle
renew_reservation_bundle = _reservation.renew_reservation_bundle
release_reservation_bundle = _reservation.release_reservation_bundle
reservation_cli_message = _reservation.reservation_cli_message
acquire_phase_lease = _reservation.acquire_phase_lease
renew_phase_lease = _reservation.renew_phase_lease
release_phase_lease = _reservation.release_phase_lease
PhaseLeaseHeartbeat = _reservation.PhaseLeaseHeartbeat
apply_independent_batch = _reservation.apply_independent_batch


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


# Stable entry-point re-exports for existing callers and installed skill prompts.
validate_project_state = _policy.validate_project_state
validate_project_artifacts = _policy.validate_project_artifacts
validate_policy = _policy.validate_policy
policy_blockers = _policy.policy_blockers
migration_boundary = _policy.migration_boundary


def _project_repository_identity(project: dict[str, Any]) -> str:
    identity = ((project.get("repository") or {}).get("identity") if isinstance(project.get("repository"), dict) else None)
    if project.get("backend") != "github_issues" or not text_present(identity) or identity.count("/") != 1:
        raise ValueError("Canonical policy repository.identity must be owner/repository for GitHub Issues")
    return identity


def _graphql_labels(issue: dict[str, Any]) -> list[dict[str, Any]]:
    labels = issue.get("labels")
    nodes = labels.get("nodes") if isinstance(labels, dict) else None
    if not isinstance(nodes, list):
        raise ValueError("issue labels are incomplete or malformed")
    return [{"name": node.get("name")} for node in nodes if isinstance(node, dict)]


def _graphql_issue_index(issue: dict[str, Any], repository_url: str) -> dict[str, Any]:
    labels = _graphql_labels(issue)
    schema_versions = [
        int(match.group("version"))
        for label in labels
        if isinstance(label.get("name"), str) and (match := GOAL_SCHEMA_LABEL.fullmatch(label["name"]))
    ]
    if len(schema_versions) > 1:
        raise ValueError("issue has multiple goal schema labels")
    return {
        "number": issue["number"], "title": issue["title"],
        "state": str(issue["state"]).lower(), "labels": labels,
        "schema_version": schema_versions[0] if schema_versions else None,
        "html_url": f"{repository_url.rstrip('/')}/issues/{issue['number']}",
    }


def _goal_body_query(numbers: list[int]) -> str:
    fields = "\n".join(
        f"    goal_{number}:issue(number:{number}){{number body updatedAt}}"
        for number in numbers
    )
    return (
        "query($owner:String!,$name:String!){\n"
        "  repository(owner:$owner,name:$name){\n"
        f"{fields}\n"
        "  }\n"
        "}"
    )


def _github_goal_bodies(
    repo: Path, executable: str, owner: str, name: str, numbers: list[int],
) -> tuple[dict[int, dict[str, Any]], int, int]:
    if not numbers:
        return {}, 0, 0
    hydrated = {}
    raw_bytes = 0
    processes = 0
    for offset in range(0, len(numbers), GOAL_HYDRATION_BATCH_SIZE):
        batch = numbers[offset:offset + GOAL_HYDRATION_BATCH_SIZE]
        command = [
            executable, "api", "graphql", "-f", f"query={_goal_body_query(batch)}",
            "-F", f"owner={owner}", "-F", f"name={name}",
        ]
        try:
            result = subprocess.run(
                command, cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f"GitHub targeted goal-body read failed: {type(exc).__name__}") from exc
        processes += 1
        if result.returncode:
            raise ValueError("GitHub targeted goal-body read failed: " + (result.stderr.strip() or "unknown gh error"))
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"GitHub targeted goal-body read returned invalid JSON: {exc}") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        repository = data.get("repository") if isinstance(data, dict) else None
        if not isinstance(repository, dict):
            raise ValueError("GitHub targeted goal-body read is incomplete or malformed")
        for number in batch:
            issue = repository.get(f"goal_{number}")
            if not isinstance(issue, dict) or issue.get("number") != number or not isinstance(issue.get("body"), str):
                raise ValueError(f"GitHub targeted goal-body read omitted issue #{number}")
            hydrated[number] = {"body": issue["body"], "updated_at": issue.get("updatedAt")}
        raw_bytes += len(result.stdout.encode("utf-8"))
    return hydrated, raw_bytes, processes


def _github_pull_request_states(
    repo: Path, executable: str, selected: list[dict[str, Any]], bodies: dict[int, dict[str, Any]],
) -> tuple[dict[int, dict[str, Any]], int, int]:
    """Read PR merge state for implementation URLs in one query per PR repository."""
    targets: dict[tuple[str, str, int], list[int]] = {}
    for issue in selected:
        body = bodies.get(issue["number"], {}).get("body")
        if not isinstance(body, str):
            continue
        goal = _goals.parse_managed_goal(body, issue["number"])
        implementation = goal.get("implementation") if isinstance(goal, dict) else None
        pr_url = implementation.get("pr") if isinstance(implementation, dict) else None
        if not isinstance(pr_url, str) or not pr_url.startswith("https://github.com/"):
            continue
        parsed = urlparse(pr_url)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 4 or parts[2].casefold() != "pull" or not parts[3].isdigit():
            continue
        targets.setdefault((parts[0], parts[1], int(parts[3])), []).append(issue["number"])
    states: dict[int, dict[str, Any]] = {}
    raw_bytes = 0
    processes = 0
    for owner, name, number in sorted(targets):
        query = """query($owner:String!,$name:String!,$number:Int!){
  repository(owner:$owner,name:$name){
    nameWithOwner
    pullRequest(number:$number){
      merged mergedAt headRefOid baseRefName baseRefOid
      mergeCommit{oid}
      repository{nameWithOwner}
      reviewDecision
      commits(last:1){nodes{commit{statusCheckRollup{contexts(first:100){nodes{
        __typename
        ... on CheckRun{name status conclusion}
        ... on StatusContext{context state}
      }}}}}}
    }
  }
}"""
        command = [
            executable, "api", "graphql", "-f", f"query={query}",
            "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"number={number}",
        ]
        try:
            result = subprocess.run(command, cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f"GitHub pull-request state read failed: {type(exc).__name__}") from exc
        processes += 1
        if result.returncode:
            raise ValueError("GitHub pull-request state read failed: " + (result.stderr.strip() or "unknown gh error"))
        try:
            payload = json.loads(result.stdout)
            data = payload["data"]["repository"]
            pull_request = data.get("pullRequest")
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError("GitHub pull-request state read returned invalid JSON") from exc
        if not isinstance(pull_request, dict):
            normalized = None
        else:
            merge_commit = pull_request.get("mergeCommit")
            pr_repository = pull_request.get("repository")
            normalized = {
                "merged": pull_request.get("merged") is True,
                "merged_at": pull_request.get("mergedAt"),
                "head_oid": pull_request.get("headRefOid"),
                "base_oid": pull_request.get("baseRefOid"),
                "base_ref": pull_request.get("baseRefName"),
                "merge_commit": merge_commit.get("oid") if isinstance(merge_commit, dict) else None,
                "repository": pr_repository.get("nameWithOwner") if isinstance(pr_repository, dict) else None,
                "checks_verified": _pull_request_checks_verified(pull_request),
                "review_verified": pull_request.get("reviewDecision") == "APPROVED",
            }
        for issue_number in targets[(owner, name, number)]:
            if normalized is not None:
                states[issue_number] = normalized
        raw_bytes += len(result.stdout.encode("utf-8"))
    return states, raw_bytes, processes


def _pull_request_checks_verified(pull_request: Any) -> bool:
    """Accept only a non-empty, completed-success check rollup on the PR head."""
    if not isinstance(pull_request, dict):
        return False
    commits = pull_request.get("commits")
    nodes = commits.get("nodes") if isinstance(commits, dict) else None
    if not isinstance(nodes, list) or len(nodes) != 1 or not isinstance(nodes[0], dict):
        return False
    commit = nodes[0].get("commit")
    rollup = commit.get("statusCheckRollup") if isinstance(commit, dict) else None
    contexts = rollup.get("contexts") if isinstance(rollup, dict) else None
    checks = contexts.get("nodes") if isinstance(contexts, dict) else None
    if not isinstance(checks, list) or not checks:
        return False
    for check in checks:
        if not isinstance(check, dict):
            return False
        if check.get("__typename") == "CheckRun":
            if not isinstance(check.get("name"), str) or not check["name"] or check.get("status") != "COMPLETED" or check.get("conclusion") != "SUCCESS":
                return False
        elif check.get("__typename") == "StatusContext":
            if not isinstance(check.get("context"), str) or not check["context"] or check.get("state") != "SUCCESS":
                return False
        else:
            return False
    return True


def github_issue_history(repo: Path, project: dict[str, Any], issue_number: int) -> list[dict[str, Any]]:
    """Hydrate append-only history for one explicitly selected goal."""
    identity = _project_repository_identity(project)
    owner, name = identity.split("/", 1)
    executable = shutil.which("gh")
    if not executable:
        raise ValueError("GitHub CLI is unavailable")
    command = [
        executable, "api", "graphql", "--paginate", "--slurp",
        "-f", f"query={GITHUB_GOAL_HISTORY_QUERY}", "-F", f"owner={owner}",
        "-F", f"name={name}", "-F", f"number={issue_number}",
    ]
    try:
        result = subprocess.run(
            command, cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"GitHub goal-history read failed: {type(exc).__name__}") from exc
    if result.returncode:
        raise ValueError("GitHub goal-history read failed: " + (result.stderr.strip() or "unknown gh error"))
    try:
        pages = json.loads(result.stdout)
        if not isinstance(pages, list) or not pages:
            raise TypeError("pagination result must contain at least one page")
        comments = []
        for index, page in enumerate(pages):
            connection = page["data"]["repository"]["issue"]["comments"]
            page_info = connection["pageInfo"]
            if index < len(pages) - 1 and page_info.get("hasNextPage") is not True:
                raise TypeError("history pagination stopped before final page")
            if index == len(pages) - 1 and page_info.get("hasNextPage") is not False:
                raise TypeError("history pagination is incomplete")
            comments.extend(connection["nodes"])
        return comments
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("GitHub goal-history read is incomplete or malformed") from exc


def _github_repository_capability(data: dict[str, Any]) -> dict[str, Any]:
    permission = data.get("viewerPermission")
    issues_enabled = data.get("hasIssuesEnabled") is True
    usable = issues_enabled and permission in GITHUB_MANAGEMENT_PERMISSIONS
    return {
        "available": True,
        "usable": usable,
        "identity": data.get("nameWithOwner"),
        "url": data.get("url"),
        "visibility": data.get("visibility"),
        "issues_enabled": issues_enabled,
        "viewer_permission": permission,
        "detail": "ok" if usable else ("issues disabled" if not issues_enabled else "insufficient permission"),
    }


def github_repository_goal_index(
    repo: Path, project: dict[str, Any], include_feedback: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], int, int, int]:
    """Read only provider-owned identity, state, and derived goal labels."""
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
    indexed_issues = []
    findings = []
    for issue in issue_nodes:
        try:
            if not isinstance(issue, dict):
                raise ValueError("issue must be an object")
            indexed_issues.append(_graphql_issue_index(issue, first["url"]))
        except (KeyError, TypeError, ValueError) as exc:
            goal = issue.get("number", "unknown") if isinstance(issue, dict) else "unknown"
            findings.append({"code": "malformed_record", "goal": goal, "detail": str(exc)})
    def is_feedback(issue: dict[str, Any]) -> bool:
        return any(
            isinstance(label, dict) and label.get("name") == "zzzops-feedback"
            for label in issue.get("labels", [])
        )

    selected = [issue for issue in indexed_issues if include_feedback or not is_feedback(issue)]
    return (
        _github_repository_capability(first), selected, findings,
        len(result.stdout.encode("utf-8")), len(pages), len(indexed_issues) - len(selected),
    )


def _portfolio_from_hydrated_goals(
    project: dict[str, Any], selected: list[dict[str, Any]], bodies: dict[int, dict[str, Any]],
    findings: list[dict[str, Any]], discovery_bytes: int, discovery_reads: int,
    hydration_bytes: int, hydration_processes: int, excluded: int,
    pull_request_states: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    open_selected = [issue for issue in selected if issue["state"] == "open"]
    managed = []
    for issue in open_selected:
        hydrated = bodies[issue["number"]]
        candidate = {**issue, **hydrated}
        if pull_request_states and issue["number"] in pull_request_states:
            candidate["pull_request"] = pull_request_states[issue["number"]]
            candidate["repository"] = project["repository"]["identity"]
        if GOAL_BLOCK_START in candidate["body"]:
            managed.append(candidate)
    records = []
    for issue in managed:
        try:
            records.append(github_goal_record(issue))
        except (KeyError, TypeError, ValueError) as exc:
            findings.append({"code": "malformed_record", "goal": issue.get("number", "unknown"), "detail": str(exc)})
    for issue in selected:
        if issue["state"] != "closed":
            continue
        try:
            records.append(github_archived_goal_record(issue))
        except (KeyError, TypeError, ValueError) as exc:
            findings.append({"code": "malformed_record", "goal": issue.get("number", "unknown"), "detail": str(exc)})
    snapshot = build_portfolio_snapshot(
        project["backend"], records, reads=discovery_reads + hydration_processes,
        raw_bytes=discovery_bytes + hydration_bytes,
        ignored=excluded + len(selected) - len(records),
        git_policy=next(
            (
                section["settings"] for section in ((project.get("policy") or {}).get("sections") or [])
                if isinstance(section, dict) and section.get("id") == "git_review_release"
            ),
            {},
        ),
        resource_policy=project_resource_policy(project),
        rigor_policy=next(
            (
                section for section in ((project.get("policy") or {}).get("sections") or [])
                if isinstance(section, dict) and section.get("id") == "engineering_rigor"
                and isinstance(section.get("review"), dict) and section["review"].get("approved") is True
            ),
            None,
        ),
    )
    snapshot["findings"] = sorted(snapshot["findings"] + findings, key=lambda item: (item["code"], str(item["goal"])))
    snapshot["summary"]["findings"] = len(snapshot["findings"])
    snapshot["complete"] = not findings
    snapshot["valid"] = not snapshot["findings"]
    snapshot["summary"]["discovery_raw_bytes"] = discovery_bytes
    snapshot["summary"]["hydration_raw_bytes"] = hydration_bytes
    snapshot["summary"]["processes"] = 1 + hydration_processes
    return compact_portfolio_output(snapshot)


def github_repository_portfolio_snapshot(
    repo: Path, project: dict[str, Any], include_feedback: bool = False, *, timing: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    identity = _project_repository_identity(project)
    owner, name = identity.split("/", 1)
    executable = shutil.which("gh")
    if not executable:
        raise ValueError("GitHub CLI is unavailable")
    repository_probe, selected, findings, discovery_bytes, discovery_reads, excluded = _timed_call(
        timing, "github_discovery", lambda: github_repository_goal_index(repo, project, include_feedback),
    )
    open_selected = [issue for issue in selected if issue["state"] == "open"]
    bodies, hydration_bytes, hydration_processes = _timed_call(
        timing, "goal_hydration", lambda: _github_goal_bodies(
            repo, executable, owner, name, [issue["number"] for issue in open_selected],
        ),
    )
    pull_request_states, pull_request_bytes, pull_request_processes = _github_pull_request_states(
        repo, executable, open_selected, bodies,
    )
    snapshot = _timed_call(
        timing, "graph_validation", lambda: _portfolio_from_hydrated_goals(
            project, selected, bodies, findings, discovery_bytes, discovery_reads,
            hydration_bytes + pull_request_bytes, hydration_processes + pull_request_processes, excluded,
            pull_request_states,
        ),
    )
    return repository_probe, snapshot


def _validated_portfolio_project(repo: Path) -> dict[str, Any]:
    _path, _text, project = read_project_state(repo)
    if project is None:
        raise ValueError("Project policy is missing; run the review-zzzops-policy skill")
    errors = validate_project_state(project)
    errors.extend(validate_project_artifacts(repo, project))
    if errors or not project or not project.get("initialized"):
        raise ValueError("Project policy is not initialized: " + "; ".join(errors or ["review pending"]))
    return project


def portfolio_snapshot(repo: Path, include_feedback: bool = False, *, timing: Any = None) -> dict[str, Any]:
    project = _timed_call(timing, "policy_validation", lambda: _validated_portfolio_project(repo))
    _repository, snapshot = github_repository_portfolio_snapshot(
        repo, project, include_feedback, timing=timing,
    )
    return snapshot


WORKFLOW_STEP_SCHEMA_VERSION = 1
WORKFLOW_PHASE_PROMPTS = {
    (phase, kind): f"execute-zzzops/references/phases/{phase}-{kind}.md"
    for phase in ("understand", "decompose", "plan", "test_design", "implement", "publish")
    for kind in ("execute", "review")
}


def _workflow_section(project: dict[str, Any], identifier: str) -> dict[str, Any]:
    for section in project.get("policy", {}).get("sections", []):
        if isinstance(section, dict) and section.get("id") == identifier and isinstance(section.get("settings"), dict):
            return section
    raise ValueError(f"Reviewed {identifier} policy is unavailable")


def _workflow_runtime(runtime: Any) -> dict[str, Any]:
    if not isinstance(runtime, dict) or set(runtime) != {"root_pair", "available_pairs"}:
        raise ValueError("workflow runtime must contain root_pair and available_pairs")
    root, available = runtime["root_pair"], runtime["available_pairs"]
    if not isinstance(root, dict) or set(root) != {"model", "effort"} or not isinstance(available, list):
        raise ValueError("workflow runtime is invalid")
    # reviewed_model_effort performs the detailed identifier validation.
    return {"root_pair": dict(root), "available_pairs": [dict(item) if isinstance(item, dict) else item for item in available]}


def workflow_step_plan(
    goal: dict[str, Any], graph: dict[str, Any], live_inputs: dict[str, dict[str, Any]],
    phase_nodes: dict[str, dict[str, Any]], routing_settings: dict[str, Any], runtime: Any,
    *, related_goals: dict[Any, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Turn a pure evidence frontier into exact phase prompts and routing pairs."""
    frontier = derive_phase_steps(goal, graph, live_inputs, related_goals)
    try:
        runtime = _workflow_runtime(runtime)
    except ValueError as exc:
        return {"schema_version": WORKFLOW_STEP_SCHEMA_VERSION, "next_steps": [{
            "kind": "capability_discovery", "assignment": "root", "reason": str(exc),
        }], "frontier": frontier}
    tiers = {item["id"]: item["rank"] for item in routing_settings["tiers"]}
    root_choice = next(
        (item for item in routing_settings["model_inventory"]["reviewed_pairs"] if {
            "model": item["model"], "effort": item["effort"],
        } == runtime["root_pair"]),
        None,
    )
    if root_choice is None:
        return {"schema_version": WORKFLOW_STEP_SCHEMA_VERSION, "next_steps": [{
            "kind": "capability_discovery", "assignment": "root", "reason": "root model-plus-effort pair is not reviewed",
        }], "frontier": frontier}
    dimensions_base = {
        "consequence": "architectural" if "architecture" in goal.get("engineering_rigor", {}).get("risk_categories", []) else "bounded",
        "boundedness": "atomic" if goal.get("difficulty") in {"XS", "S"} else "bounded",
        "engineering_rigor": goal.get("engineering_rigor", {}).get("effective") or "structured",
    }
    steps = []
    for kind, entries in (("execute", frontier["execute"]), ("review", frontier["review"])):
        for entry in entries:
            phase = entry["phase"]
            node = phase_nodes[phase]
            human_approval = kind == "review" and node.get("review", {}).get("human_approval") is True
            tier = capability_tier(routing_settings, {**dimensions_base, "phase_type": phase})["tier"]
            chosen = reviewed_model_effort(routing_settings, tier, runtime["available_pairs"])
            if not chosen["available"]:
                steps.append({"kind": "capability_discovery", "phase": phase, "assignment": "root", "reason": f"no reviewed available model-plus-effort pair for {tier}"})
                continue
            selection = runtime["root_pair"] if (human_approval or (kind == "execute" and node["assignment_group"] == "root")) else chosen["selected"]
            if tiers[tier] > tiers[root_choice["tier"]] and selection != runtime["root_pair"]:
                steps.append({"kind": "session_override", "phase": phase, "assignment": "root", "reason": "required model tier exceeds root capability"})
                continue
            steps.append({
                "kind": "human_approval" if human_approval else kind, "phase": phase, "reason": entry["reason"],
                "skill": WORKFLOW_PHASE_PROMPTS[(phase, kind)],
                "assignment": "root" if selection == runtime["root_pair"] else "delegate",
                "selection": selection,
            })
    return {"schema_version": WORKFLOW_STEP_SCHEMA_VERSION, "next_steps": steps, "frontier": frontier}


def _workflow_phase_configuration(project: dict[str, Any], goal: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    adherence = _workflow_section(project, "workflow_adherence")
    dag = adherence["settings"].get("phase_dag")
    graph = phase_evidence_graph(dag, has_parent=goal.get("parent") is not None)
    phase_nodes = {node["id"]: node for node in dag["phases"] if node["id"] in {item["id"] for item in graph["phases"]}}
    return graph, phase_nodes


def _workflow_repository_snapshot(repo: Path, identity: str) -> dict[str, Any]:
    head = "unavailable"
    executable = shutil.which("git")
    if executable:
        try:
            result = subprocess.run([executable, "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, timeout=5, check=False)
            if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", result.stdout.strip()):
                head = result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {"identity": identity, "snapshot": {"head": head}}


def workflow_live_inputs(repo: Path, project: dict[str, Any], goal: dict[str, Any], intent: str, graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build reproducible phase inputs from the current repository and goal record."""
    if intent not in {"execute", "preview"}:
        raise ValueError("workflow intent is invalid")
    identity = _project_repository_identity(project)
    policy = project["policy"]
    dag = _workflow_section(project, "workflow_adherence")["settings"]["phase_dag"]
    goal_digest = goal_spec_digest(goal, title=goal["title"], human_spec=goal["human_spec"])
    evidence = normalize_phase_evidence(goal.get("phase_evidence", empty_phase_evidence()))
    live = {}
    for node in graph["phases"]:
        phase = node["id"]
        upstream = []
        for dependency in node.get("depends_on", []):
            output = evidence["records"].get(dependency, {}).get("output")
            if isinstance(output, dict):
                upstream.append({"phase": dependency, "hash": output["hash"]})
        live[phase] = phase_input_envelope(
            phase, goal_digest, sha256_phase_evidence_digest(policy), sha256_phase_evidence_digest(dag),
            repository=_workflow_repository_snapshot(repo, identity),
            provider={"identity": "github", "snapshot": {"repository": identity}},
            capabilities={"identity": "workflow-runtime", "snapshot": {"status": "declared_at_checkpoint"}},
            invocation={"intent": intent, "inputs": {"goal": goal["key"], "revision": goal["revision"]}},
            upstream_outputs=upstream, acceptance_criteria=goal.get("acceptance_criteria", []),
        )
    return live


def workflow_checkpoint(repo: Path, goal_number: int, intent: str, runtime: Any) -> dict[str, Any]:
    """Public, functional checkpoint: re-read state and return only required work."""
    project = reviewed_project_state(repo)
    portfolio = portfolio_snapshot(repo)
    if portfolio.get("complete") is not True or portfolio.get("valid") is not True:
        raise ValueError("Goal portfolio is not valid")
    if goal_number not in {item.get("key") for item in portfolio.get("goals", [])}:
        raise ValueError(f"Goal #{goal_number} is not present in the current portfolio")
    repository = _project_repository_identity(project)
    adapter = GitHubGoalTransitionAdapter(repo, repository)
    issue = adapter.get_issue(goal_number)
    goal = github_goal_record(issue)
    graph, phase_nodes = _workflow_phase_configuration(project, goal)
    live_inputs = workflow_live_inputs(repo, project, goal, intent, graph)
    related: dict[Any, dict[str, Any]] = {}
    if goal.get("parent") is not None:
        parent_issue = adapter.get_issue(goal["parent"])
        parent = github_goal_record(parent_issue)
        parent_graph, _parent_nodes = _workflow_phase_configuration(project, parent)
        related[goal["parent"]] = {"goal": parent, "live_inputs": workflow_live_inputs(repo, project, parent, intent, parent_graph)}
    routing = _workflow_section(project, "model_routing")["settings"]
    result = workflow_step_plan(goal, graph, live_inputs, phase_nodes, routing, runtime, related_goals=related)
    return {"next_steps": result["next_steps"]}


def migrate_open_repository_goals(
    repo: Path, project: dict[str, Any], *, limit: int, include_feedback: bool = False,
) -> dict[str, Any]:
    repository = _project_repository_identity(project)
    capability, indexes, findings, discovery_bytes, discovery_reads, excluded = github_repository_goal_index(
        repo, project, include_feedback,
    )
    if not capability["usable"]:
        raise GoalTransitionProviderError("GitHub Issues management permission is required; no migration was made.")
    if findings:
        raise GoalTransitionProviderError("Minimal goal discovery is malformed; no migration was made.")
    adapter = GitHubGoalTransitionAdapter(repo, repository)
    result = migrate_open_goal_schemas(adapter, repository, indexes, limit=limit)
    return {
        **result, "discovery_raw_bytes": discovery_bytes, "discovery_reads": discovery_reads,
        "excluded": excluded,
    }


def inspect_repository_goal(repo: Path, project: dict[str, Any], issue_number: int) -> dict[str, Any]:
    """Explicitly inspect one goal, lazily repairing legacy schema before projection."""
    repository = _project_repository_identity(project)
    adapter = GitHubGoalTransitionAdapter(repo, repository)
    migration = ensure_current_goal_schema(adapter, repository, issue_number)
    issue = adapter.get_issue(issue_number)
    return {"migration": migration, "goal": github_goal_record(issue)}


def reconcile_merged_goal(repo: Path, project: dict[str, Any], issue_number: int, *, apply: bool = False) -> dict[str, Any]:
    """Preview or apply one exact-evidence merged-PR goal reconciliation."""
    repository = _project_repository_identity(project)
    adapter = GitHubGoalTransitionAdapter(repo, repository)
    issue = adapter.get_issue(issue_number)
    record = github_goal_record(issue)
    states, _raw_bytes, _processes = _github_pull_request_states(
        repo, adapter.executable, [{"number": issue_number}], {issue_number: {"body": issue.get("body", "")}},
    )
    merge = classify_pr_merge(record, states.get(issue_number), repository)
    result: dict[str, Any] = {"goal": issue_number, "merge": merge, "applied": False}
    if merge.get("status") != "merged_verified":
        return result
    transition = build_reconciliation_transition(record, merge, github_goal_record(issue)["digest"])
    result["transition"] = transition
    if apply:
        result["result"] = apply_goal_transition(adapter, repository, issue_number, transition)
        updated_issue = adapter.get_issue(issue_number)
        updated = github_goal_record(updated_issue)
        implementation = updated.get("implementation") or {}
        pr_url = implementation.get("pr")
        tail = pr_url.rstrip("/").rsplit("/", 1)[-1] if isinstance(pr_url, str) else ""
        event = {
            "schema_version": 1,
            "repository": repository,
            "goal": issue_number,
            "revision": updated["revision"],
            "goal_digest": github_goal_record(updated_issue)["digest"],
            "status": updated["status"],
            "kind": "integrated_change",
            "pr": int(tail) if tail.isdigit() else None,
            "base_oid": merge.get("base_oid"),
            "head_oid": merge.get("head_oid"),
            "merge_oid": merge.get("merge_commit"),
        }
        result["entropy_event"] = record_entropy_review_event(repo, event)
        result["applied"] = True
    return result


def render_portfolio_summary(snapshot: dict[str, Any], include_done: bool = False) -> str:
    summary = snapshot["summary"]
    lines = [
        f"Goals: {summary['available']} available ({summary['writable']} writable), "
        f"{summary['waiting']} waiting on dependencies, {summary['blocked']} blocked, "
        f"{summary['done']} closed ({summary['total']} total)."
    ]
    if not snapshot["complete"] or not snapshot["valid"]:
        lines.append("This goal list needs attention before work can continue.")
    status_labels = {
        "new": "New", "triaged": "Planned", "ready": "Ready", "in_progress": "In progress",
        "blocked": "Blocked", "done": "Done", "cancelled": "Cancelled",
    }
    work_labels = {
        "triage": "Triage available", "prepare": "Preparation available",
        "wait_dependency": "Waiting on dependency", "wait_human": "Waiting on human",
    }
    for goal in snapshot["goals"]:
        if not include_done and goal["status"] in {"done", "cancelled"}:
            continue
        title = re.sub(r"\s+", " ", str(goal["title"])).strip()[:240]
        label = status_labels.get(goal["status"], goal["status"])
        label = work_labels.get(goal.get("work_state"), label)
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
    if any(
        not isinstance(goal, dict) or "key" not in goal
        or (not goal.get("archived") and ("digest" not in goal or "revision" not in goal))
        for goal in prior["goals"]
    ):
        raise ValueError("comparison snapshot contains a malformed goal")
    current = {goal["key"]: goal for goal in snapshot["goals"]}
    previous = {goal["key"]: goal for goal in prior["goals"]}
    findings = []
    for key in sorted(current.keys() | previous.keys(), key=_portfolio_key):
        if key not in previous:
            findings.append({"code": "goal_added", "goal": key, "detail": "absent from comparison snapshot"})
        elif key not in current:
            findings.append({"code": "goal_removed", "goal": key, "detail": "absent from current snapshot"})
        elif (
            current[key].get("digest"), current[key].get("revision"), current[key].get("title"),
            current[key].get("status"), current[key].get("schema_version"),
        ) != (
            previous[key].get("digest"), previous[key].get("revision"), previous[key].get("title"),
            previous[key].get("status"), previous[key].get("schema_version"),
        ):
            findings.append({"code": "goal_changed", "goal": key, "detail": "current projection changed"})
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
    """Measure existing Git-tracked file bytes without selecting a policy value."""
    executable = shutil.which("git")
    if not executable:
        return {
            "available": False, "measurement": "existing_git_tracked_worktree_bytes",
            "detail": "git executable not found",
        }
    try:
        result = subprocess.run(
            [executable, "-C", str(repo), "ls-files", "-z"], cwd=repo,
            capture_output=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "available": False, "measurement": "existing_git_tracked_worktree_bytes",
            "detail": type(exc).__name__,
        }
    if result.returncode:
        return {
            "available": False, "measurement": "existing_git_tracked_worktree_bytes",
            "detail": "git ls-files failed",
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
        "bytes": total, "files": files,
    }


def machinery_commit_status(repo: Path) -> dict[str, Any]:
    """Compatibility alias for the loaded Agent Plugin package status."""
    return _package.package_status()


def sanitize_output(value: str) -> str:
    return re.sub(r"(https?://)[^/@\s]+@", r"\1***@", value)


_reservation.configure_entrypoint(parse_managed_goal, sanitize_output)


def github_repository_probe(repo: Path) -> dict[str, Any]:
    executable = shutil.which("gh")
    if not executable:
        return {"available": False, "usable": False, "detail": "executable not found"}
    try:
        result = subprocess.run(
            [executable, "repo", "view", "--json", "nameWithOwner,url,visibility,hasIssuesEnabled,viewerPermission"],
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


def github_release_evidence(repo: Path, repository: dict[str, Any]) -> dict[str, Any]:
    """Read public GitHub Releases; absence or failure remains ambiguous."""
    identity = repository.get("identity") if isinstance(repository, dict) else None
    executable = shutil.which("gh")
    if not executable or not isinstance(identity, str) or identity.count("/") != 1:
        return {"available": False, "releases": None, "reason": "repository_identity_unavailable"}
    try:
        result = subprocess.run(
            [executable, "api", f"repos/{identity}/releases", "--paginate", "--slurp"],
            cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=8, check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        return {"available": True, "releases": None, "reason": type(exc).__name__}
    if result.returncode != 0:
        return {"available": True, "releases": None, "reason": "release_api_failed"}
    try:
        releases = json.loads(result.stdout)
    except (UnicodeError, json.JSONDecodeError):
        return {"available": True, "releases": None, "reason": "release_api_invalid_json"}
    if isinstance(releases, list) and all(isinstance(page, list) for page in releases):
        releases = [item for page in releases for item in page]
    if not isinstance(releases, list):
        return {"available": True, "releases": None, "reason": "release_api_malformed"}
    return {"available": True, "releases": releases, "reason": "ok"}


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
    github_releases = github_release_evidence(repo, github_repository)
    release_status = _policy.classify_release_evidence(
        visibility=github_repository.get("visibility") if isinstance(github_repository, dict) else None,
        github_releases=github_releases.get("releases"),
    )
    if state and isinstance(state.get("policy"), dict):
        review_policy = state["policy"]
        review_is_proposal = False
    elif (repo / _policy.PROJECT_POLICY_RELATIVE).exists():
        review_policy = {"sections": []}
        review_is_proposal = False
    else:
        template = json.loads(
            (Path(__file__).parent / "templates" / "project-goals" / "INIT_PLAN.json").read_text(encoding="utf-8-sig")
        )
        review_policy = template["policy"]
        review_is_proposal = True
    migration_policy_review = _policy.legacy_migration_review(review_policy, release_status)
    migration_action = _policy.migration_boundary(review_policy, release_status)
    migration_policy_invalidated = migration_policy_review.get("reason") in {
        "migration_policy_missing",
        "first_release_invalidated_pre_release_policy",
    }
    decision_blockers = policy_blockers(state.get("policy")) if state else ["policy:missing"]
    if migration_policy_invalidated:
        decision_blockers = [*decision_blockers, "legacy_migration:first_release_requires_policy_rereview"]
    github_stack = github_stack_probe(repo)
    plugin_inventory = _plugin_freshness.native_plugin_inventory()
    cache_path = Path(plugin_inventory["cache_path"])
    cache = None
    try:
        if cache_path.is_file():
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        cache = None
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "project_path": str(path),
        "base_digest": initialization_base_digest(repo),
        "state": state,
        "initialized": bool(state and state.get("initialized") is True and not decision_blockers and error is None),
        "valid_state": error is None and state is not None,
        "state_error": error,
        "missing_charter_fields": charter_missing_fields(text),
        "decision_blockers": decision_blockers,
        "policy_defaults": compare_policy_defaults(state["policy"]) if state and isinstance(state.get("policy"), dict) else [],
        "policy_review_table": render_policy_review_table(review_policy, proposal=review_is_proposal),
        "stack_tooling_offer": _policy.stack_tooling_offer(review_policy, github_stack),
        "plugin_freshness": {
            "due": _plugin_freshness.freshness_due(cache),
            "inventory": plugin_inventory,
            "cache_status": cache.get("status") if isinstance(cache, dict) else "missing",
        },
        "backend_constraints": {
            "github_issues": "requires a usable GitHub repository probe",
        },
        "capabilities": {
            "git_origin": git_remote,
            "plugin_package": _package.package_status(),
            "github_auth": github_auth,
            "github_repository": github_repository,
            "github_release_evidence": github_releases,
            "release_status": release_status,
            "legacy_migration_review": migration_policy_review,
            "migration_boundary": migration_action,
            "github_stack": github_stack,
        },
        "repository_size": repository_size_profile(repo),
    }


def github_stack_probe(repo: Path) -> dict[str, Any]:
    """Read local CLI/official extension capability; never install or infer a remote stack."""
    result = {
        "available": shutil.which("gh") is not None, "usable": False,
        "reason": "gh_missing", "cli_version": None, "extension_version": None,
        "official_source": "github/gh-stack", "minimum_cli_version": "2.0.0",
        "provider_membership_verified": False,
    }
    if not result["available"]:
        return result

    def output(*arguments: str) -> str | None:
        try:
            probe = subprocess.run(["gh", *arguments], cwd=repo, capture_output=True,
                                   text=True, timeout=5, check=False)
        except (OSError, UnicodeError, subprocess.TimeoutExpired):
            return None
        return probe.stdout if probe.returncode == 0 else None

    cli = output("--version")
    version = re.search(r"^gh version (\d+)\.(\d+)\.(\d+)\b", cli or "")
    result["reason"] = "cli_unverified"
    if version is None:
        return result
    result["cli_version"] = ".".join(version.groups())
    if tuple(map(int, version.groups())) < (2, 0, 0):
        result["reason"] = "cli_upgrade_required"
        return result
    extensions = output("extension", "list")
    if extensions is None:
        result["reason"] = "extension_list_failed"
        return result
    if any(not re.match(r"^\s*gh\s+\S+\s+\S+/\S+\s+\S+", line)
           for line in extensions.splitlines() if line.strip()):
        result["reason"] = "extension_list_unverified"
        return result
    stack = re.search(r"^\s*gh\s+stack\s+(\S+)\s+(\S+)", extensions, re.MULTILINE)
    if stack is None:
        result["reason"] = "extension_missing"
        return result
    if stack.group(1) != result["official_source"]:
        result["reason"] = "wrong_extension_source"
        return result
    installed = output("stack", "--version")
    version = re.search(r"^gh stack version (\d+\.\d+\.\d+(?:[-+][\w.-]+)?)\b", installed or "")
    result["reason"] = "extension_unverified"
    if version is not None:
        result.update(usable=True, reason="usable", extension_version=version.group(1))
    return result


def _checkpoint_policy_state(repo: Path) -> tuple[Path, str, dict[str, Any] | None, str | None, list[str], bool]:
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
    return path, text, state, error, blockers, initialized


def decision_checkpoint(repo: Path, include_feedback: bool = False, *, timing: Any = None) -> dict[str, Any]:
    path, text, state, error, blockers, initialized = _timed_call(
        timing, "policy_validation", lambda: _checkpoint_policy_state(repo),
    )
    git_remote = _timed_call(
        timing, "git_origin", lambda: command_probe(["git", "remote", "get-url", "origin"], repo),
    )
    github_available = shutil.which("gh") is not None
    github_processes = 0
    plugin_package = {
        "available": True,
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
        plugin_package = _timed_call(timing, "package", _package.package_status)
    if initialized and state and plugin_package.get("ok") is True:
        github_processes = 1 if github_available else 0
        try:
            github_repository, portfolio = github_repository_portfolio_snapshot(
                repo, state, include_feedback, timing=timing,
            )
            github_processes = int(portfolio.get("summary", {}).get("processes", github_processes))
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
        detail = str(plugin_package.get("detail") or "Reinstall ZzzOps from its Codex marketplace.")
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
        and plugin_package.get("ok") is True
        and github_auth.get("ok") is True
        and github_repository.get("usable") is True
        and portfolio.get("complete") is True
        and portfolio.get("valid") is True
    )
    repository_size = _timed_call(timing, "repository_size", lambda: repository_size_profile(repo))
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
            "plugin_package": plugin_package,
            "github_auth": github_auth,
            "github_repository": github_repository,
        },
        "repository_size": repository_size,
        "portfolio": portfolio,
        "processes": {
            "total": (
                (1 if git_remote.get("available") else 0)
                + int(plugin_package.get("processes", 0))
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
    if isinstance(policy, dict):
        try:
            previous = read_project_state(repo)[2]
            prepared = prepare_policy_defaults(repo, policy, (previous or {}).get("policy"))
            errors.extend(f"policy.{error}" for error in validate_policy(prepared, require_pending=True))
        except ValueError as exc:
            errors.append(f"policy.default provenance: {exc}")
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


# Policy rendering and text predicates are likewise exposed through the historic
# CLI module while their implementation lives in the acyclic policy module.
nonempty = _policy.nonempty
text_present = _policy.text_present
nonempty_list = _policy.nonempty_list
cell = _policy.cell
render_project = _policy.render_project
render_policy_sections = _policy.render_policy_sections
render_project_audit = _policy.render_project_audit

_goals.configure_entrypoint(
    normalize_resources=normalize_resources, text_present=text_present,
    validate_phase_evidence=_phase_evidence.validate_phase_evidence,
)
_portfolio.configure_entrypoint(exclusive_resources=exclusive_resources, normalize_resource_policy=normalize_resource_policy, text_present=text_present, merge_classifier=classify_pr_merge)
active_stack_guard = _portfolio.active_stack_guard
linear_publication_next_step = _portfolio.linear_publication_next_step


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
    previous_policy = old_state.get("policy") if old_state else None
    policy = prepare_policy_defaults(repo, plan["policy"], previous_policy)
    policy["evidence"] = plan["evidence"]
    if previous_policy:
        old_sections = {section["id"]: section for section in previous_policy["sections"]}
        old_evidence = previous_policy.get("evidence", [])
        for section in policy["sections"]:
            prior = old_sections.get(section["id"])
            if (
                prior is not None
                and _policy.policy_section_review_content(section, policy["evidence"])
                == _policy.policy_section_review_content(prior, old_evidence)
            ):
                section["review"] = json.loads(json.dumps(prior["review"]))
    history = json.loads(json.dumps(old_state["history"])) if old_state else []
    history.append({
        "date": date.today().isoformat(), "actor": "ZzzOps initialization",
        "change": f"Created pending revision {revision}",
        "reason": "Confirmed agent-generated draft; explicit policy review still required.",
    })
    state = {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "initialized": False,
        "backend": plan["backend"],
        "repository": plan["repository"],
        "revision": revision,
        "charter": plan["charter"],
        "policy": policy,
        "history": history,
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
        "decision_blockers": policy_blockers(policy),
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


def _run_profiled(repo: Path, operation: Any) -> tuple[int, str]:
    timing = TimingSession()
    failed = False
    try:
        with timing.command():
            return operation(timing)
    except BaseException:
        failed = True
        raise
    finally:
        try:
            record_diagnostic(repo, timing.snapshot())
        except DiagnosticError:
            if not failed:
                raise


def _profiled_checkpoint_cli(repo: Path, args: argparse.Namespace) -> tuple[int, str]:
    def operation(timing: Any) -> tuple[int, str]:
        timing.mark("startup", provenance="unavailable")
        package = _timed_call(timing, "package", _package.package_status)
        if package.get("ok") is not True:
            return 2, str(package.get("detail") or "The ZzzOps Agent Plugin package is invalid.")
        result = decision_checkpoint(repo, args.include_feedback, timing=timing)
        rendered = _timed_call(
            timing, "rendering",
            lambda: json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
        return (0 if result["ready"] else 2), rendered

    try:
        return _run_profiled(repo, operation)
    except ValueError as exc:
        return 2, f"Could not continue: {exc}"


def _profiled_portfolio_cli(repo: Path, args: argparse.Namespace) -> tuple[int, str]:
    def operation(timing: Any) -> tuple[int, str]:
        timing.mark("startup", provenance="unavailable")
        package = _timed_call(timing, "package", _package.package_status)
        if package.get("ok") is not True:
            return 2, str(package.get("detail") or "The ZzzOps Agent Plugin package is invalid.")
        result = portfolio_snapshot(repo, args.include_feedback, timing=timing)
        if args.compare:
            prior = json.loads(args.compare.resolve().read_text(encoding="utf-8-sig"))
            result["changes"] = compare_portfolios(result, prior)
        rendered = _timed_call(
            timing, "rendering",
            lambda: (
                json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                if args.output_format == "json"
                else render_portfolio_summary(result, args.include_done)
            ),
        )
        return 0, rendered

    try:
        return _run_profiled(repo, operation)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        if args.output_format == "json":
            return 2, json.dumps(
                {"schema_version": PORTFOLIO_SCHEMA_VERSION, "complete": False, "valid": False, "error": str(exc)},
                ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            )
        return 2, f"Could not load goals: {exc}"


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
    checkpoint_parser.add_argument("--profile", action="store_true", help="Record one local privacy-safe timing aggregate")
    workflow_parser = commands.add_parser("workflow", help="Return the next actionable ZzzOps workflow step")
    workflow_parser.add_argument("--goal", type=int, help="Managed goal whose evidence-derived phase frontier to evaluate")
    workflow_parser.add_argument("--intent", choices=sorted(WORKFLOW_INTENTS), required=True)
    workflow_parser.add_argument("--source-skill", choices=sorted(WORKFLOW_SKILL_INTENTS), help="Named skill that initiated this public workflow call")
    workflow_parser.add_argument("--runtime", type=Path, help="Current root and available model-effort pairs as JSON")
    installation = commands.add_parser("installation", help="Check or record per-repository plugin validation")
    installation_commands = installation.add_subparsers(dest="installation_command", required=True)
    installation_commands.add_parser("status", help="Report whether this installed package needs repository validation")
    installation_commands.add_parser("audit", help="Audit fingerprint-owned legacy repository machinery")
    installation_record = installation_commands.add_parser("record", help="Record a confirmed current-package validation outcome")
    installation_record.add_argument("--outcome", choices=sorted(_installation.OUTCOMES), required=True)
    installation_record.add_argument("--audit-signature", required=True)
    entropy = commands.add_parser("entropy", help="Track compact repository entropy observations")
    entropy_commands = entropy.add_subparsers(dest="entropy_command", required=True)
    entropy_commands.add_parser("list", help="List observations enabled by existing suggestion policy")
    entropy_observe = entropy_commands.add_parser("observe", help="Record one bounded entropy observation")
    entropy_observe.add_argument("--none", action="store_true", help="Record an explicit no-observation checkpoint")
    entropy_observe.add_argument("--category", choices=sorted(_entropy.ENTROPY_CATEGORIES))
    entropy_observe.add_argument("--path", action="append", dest="paths", default=[])
    entropy_observe.add_argument("--evidence")
    entropy_observe.add_argument("--goal", type=int, required=True)
    entropy_observe.add_argument("--revision", type=int, required=True)
    entropy_resolve = entropy_commands.add_parser("resolve", help="Remove observations after validation")
    entropy_resolve.add_argument("--fingerprint", action="append", dest="fingerprints", required=True)
    entropy_resolve.add_argument("--outcome", choices=("captured", "dismissed"), required=True)
    entropy_review = entropy_commands.add_parser("review", help="Track exact entropy-review batches and coverage")
    entropy_review_commands = entropy_review.add_subparsers(dest="entropy_review_command", required=True)
    entropy_review_status_parser = entropy_review_commands.add_parser("status", help="Report uncovered exact review work")
    entropy_review_status_parser.add_argument("--current-event", action="append", default=None)
    entropy_review_mark = entropy_review_commands.add_parser("mark", help="Record one exact goal-change event")
    entropy_review_mark.add_argument("--input", type=Path, required=True)
    entropy_review_plan = entropy_review_commands.add_parser("plan", help="Freeze one recent or full review batch")
    entropy_review_plan.add_argument("--mode", choices=("recent", "full"), required=True)
    entropy_review_plan.add_argument("--current-event", action="append", default=None)
    entropy_review_complete = entropy_review_commands.add_parser("complete", help="Record successful exact review coverage")
    entropy_review_complete.add_argument("--input", type=Path, required=True)
    diagnostics = commands.add_parser("diagnostics", help="Inspect privacy-safe local timing diagnostics")
    diagnostics_commands = diagnostics.add_subparsers(dest="diagnostics_command", required=True)
    diagnostics_commands.add_parser("list", help="List validated local timing aggregates")
    diagnostics_commands.add_parser("suggest", help="Read one current bounded bottleneck candidate")
    portfolio_parser = commands.add_parser("portfolio", help="Read and audit the canonical goal portfolio once")
    portfolio_parser.add_argument("--format", dest="output_format", choices=("summary", "json"), default="summary")
    portfolio_parser.add_argument("--include-done", action="store_true", help="Include terminal goals in summary output")
    portfolio_parser.add_argument("--compare", type=Path, help="Prior JSON snapshot used only to report digest/revision drift")
    portfolio_parser.add_argument("--include-feedback", action="store_true", help="Include specially tagged feedback goals")
    portfolio_parser.add_argument("--profile", action="store_true", help="Record one local privacy-safe timing aggregate")
    goal_command = commands.add_parser("goal", help="Create, transition, or inspect validated GitHub-backed goals")
    goal_commands = goal_command.add_subparsers(dest="goal_command", required=True)
    create_goal_command = goal_commands.add_parser("create", help="Create one goal from a validated UTF-8 request file")
    create_goal_command.add_argument("--input", type=Path, required=True, help="UTF-8 goal create JSON file")
    transition_command = goal_commands.add_parser("transition", help="Apply one file-backed managed-goal transition")
    transition_command.add_argument("--goal", type=int, required=True)
    transition_command.add_argument("--input", type=Path, required=True, help="UTF-8 transition JSON file")
    migrate_open_command = goal_commands.add_parser("migrate-open", help="Compact one bounded page of open legacy goals")
    migrate_open_command.add_argument("--limit", type=int, default=25)
    migrate_open_command.add_argument("--include-feedback", action="store_true")
    inspect_goal_command = goal_commands.add_parser("inspect", help="Inspect one goal and lazily compact legacy state")
    inspect_goal_command.add_argument("--goal", type=int, required=True)
    reconcile_command = goal_commands.add_parser("reconcile-merged", help="Preview or apply one exact-evidence merged-PR reconciliation")
    reconcile_command.add_argument("--goal", type=int, required=True)
    reconcile_command.add_argument("--apply", action="store_true", help="Apply the guarded transition after previewing its exact evidence")
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
    coaching = commands.add_parser("coaching", help="Attribute bounded software-agent work evidence without writes")
    coaching_commands = coaching.add_subparsers(dest="coaching_command", required=True)
    coaching_attribute = coaching_commands.add_parser("attribute", help="Classify a bounded attribution request")
    coaching_attribute.add_argument("--input", type=Path, required=True, help="UTF-8 bounded attribution JSON file")
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
        feedback_command.add_argument("--diagnostic", help="Select one local timing diagnostic id")
        feedback_command.add_argument("--diagnostic-agent", choices=sorted(_feedback.TIMING_AGENTS), default="unknown")
        feedback_command.add_argument("--diagnostic-platform", choices=sorted(_feedback.TIMING_PLATFORMS), default="unknown")
        feedback_command.add_argument("--diagnostic-python", choices=sorted(_feedback.TIMING_PYTHONS), default="unknown")
        if name == "submit":
            feedback_command.add_argument("--confirm", required=True, help="Exact digest shown by feedback prepare")
    args = parser.parse_args()
    repo = args.repo.resolve()
    if args.command == "checkpoint" and args.profile:
        try:
            code, output = _profiled_checkpoint_cli(repo, args)
            print(output)
            return code
        except (EOFError, KeyboardInterrupt):
            print("\nNo further changes made.")
            return 0
    if args.command == "portfolio" and args.profile:
        try:
            code, output = _profiled_portfolio_cli(repo, args)
            print(output)
            return code
        except (EOFError, KeyboardInterrupt):
            print("\nNo further changes made.")
            return 0
    package = _package.package_status()
    if package.get("ok") is not True:
        if args.command == "workflow":
            repair = workflow_repair_step(
                args.intent, "The ZzzOps Agent Plugin package is invalid.",
                "Repair or reinstall the ZzzOps Agent Plugin package, then invoke workflow again.",
                source_skill=args.source_skill,
            )
            print(json.dumps(workflow_envelope(args.intent, [repair]), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return 2
        print(str(package.get("detail") or "The ZzzOps Agent Plugin package is invalid."))
        return 2
    try:
        if args.command == "installation":
            provenance = {"version": package["version"], "revision": package["revision"]}
            if args.installation_command == "status":
                result = _installation.validation_status(repo, provenance)
            elif args.installation_command == "audit":
                result = _installation.installation_audit(repo)
            else:
                result = _installation.record_validation(
                    repo, provenance, outcome=args.outcome, audit_signature=args.audit_signature,
                )
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return 0
        elif args.command == "entropy":
            if args.entropy_command == "list":
                project = reviewed_project_state(repo)
                result = list_entropy_observations(repo, project)
            elif args.entropy_command == "observe":
                if args.none:
                    if args.category or args.paths or args.evidence:
                        raise ValueError("--none cannot be combined with an entropy observation")
                    result = record_entropy_observation_checkpoint(repo, goal=args.goal, revision=args.revision)
                else:
                    if not args.category or not args.paths or not args.evidence:
                        raise ValueError("an entropy observation requires --category, --path, and --evidence")
                    result = record_entropy_observation(
                        repo, category=args.category, paths=args.paths, evidence=args.evidence,
                        goal=args.goal, revision=args.revision,
                    )
            elif args.entropy_command == "resolve":
                result = resolve_entropy_observations(
                    repo, fingerprints=args.fingerprints, outcome=args.outcome,
                )
            else:
                project = reviewed_project_state(repo)
                repository_identity = _project_repository_identity(project)
                eligible = list_entropy_observations(repo, project)["observations"]
                observation_fingerprints = [_entropy._fingerprint(item) for item in eligible]
                if args.entropy_review_command == "status":
                    result = entropy_review_status(
                        repo,
                        current_event_fingerprints=args.current_event,
                        observation_fingerprints=observation_fingerprints,
                        expected_repository=repository_identity,
                    )
                elif args.entropy_review_command == "mark":
                    event = load_entropy_review_json(args.input.resolve())
                    if not isinstance(event.get("repository"), str) or event["repository"].casefold() != repository_identity.casefold():
                        raise EntropyReviewError("entropy-review event repository does not match project policy")
                    result = record_entropy_review_event(repo, event)
                elif args.entropy_review_command == "plan":
                    result = plan_entropy_review(
                        repo,
                        mode=args.mode,
                        current_event_fingerprints=args.current_event,
                        observation_fingerprints=observation_fingerprints,
                        expected_repository=repository_identity,
                    )
                else:
                    result = complete_entropy_review(
                        repo, load_entropy_review_json(args.input.resolve()),
                        expected_repository=repository_identity,
                    )
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return 0
        elif args.command == "diagnostics":
            result = list_diagnostics(repo) if args.diagnostics_command == "list" else timing_suggestion(repo)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return 0
        elif args.command == "checkpoint":
            result = decision_checkpoint(repo, args.include_feedback)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return 0 if result["ready"] else 2
        elif args.command == "workflow":
            try:
                if args.source_skill and args.intent not in WORKFLOW_SKILL_INTENTS[args.source_skill]:
                    raise ValueError("The source skill cannot initiate the requested workflow intent")
                if args.goal is None:
                    source_skill = args.source_skill or WORKFLOW_DEFAULT_SKILLS[args.intent]
                    result = {"next_steps": [{
                        "kind": "dispatch", "assignment": "root", "skill": source_skill,
                        "intent": args.intent, "action": WORKFLOW_SOURCE_ACTIONS[source_skill],
                    }]}
                elif args.intent not in {"execute", "preview"}:
                    raise ValueError("Goal phase checkpoints require execute or preview intent")
                else:
                    if args.runtime is None:
                        raise ValueError("Goal phase checkpoints require current runtime evidence")
                    runtime = json.loads(args.runtime.resolve().read_text(encoding="utf-8-sig"))
                    result = workflow_checkpoint(repo, args.goal, args.intent, runtime)
                print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
                return 0
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                print(json.dumps({"next_steps": [{"kind": "blocker", "assignment": "root", "reason": str(exc)}]}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
                return 2
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
            if args.goal_command == "create":
                request = load_goal_create(args.input)
                errors = validate_goal_create(request)
                if errors:
                    raise ValueError("Invalid goal create request: " + "; ".join(errors))
                adapter = GitHubGoalTransitionAdapter(repo, repository)
                result = apply_goal_create(adapter, repository, request)
            elif args.goal_command == "transition":
                transition = load_goal_transition(args.input)
                adapter = GitHubGoalTransitionAdapter(repo, repository)
                result = apply_goal_transition(adapter, repository, args.goal, transition)
                requested_goal = transition.get("goal") if isinstance(transition, dict) else None
                if isinstance(requested_goal, dict) and requested_goal.get("status") == "done" and not ((requested_goal.get("implementation") or {}).get("pr")):
                    updated_issue = adapter.get_issue(args.goal)
                    updated_goal = github_goal_record(updated_issue)
                    result["entropy_event"] = record_entropy_review_event(repo, {
                        "schema_version": 1,
                        "repository": repository,
                        "goal": args.goal,
                        "revision": updated_goal["revision"],
                        "goal_digest": updated_goal["digest"],
                        "status": updated_goal["status"],
                        "kind": "completed_goal",
                        "pr": None,
                        "base_oid": None,
                        "head_oid": None,
                        "merge_oid": None,
                    })
                elif (
                    isinstance(requested_goal, dict)
                    and requested_goal.get("status") == "blocked"
                    and isinstance(requested_goal.get("implementation"), dict)
                    and isinstance(requested_goal["implementation"].get("review"), dict)
                    and requested_goal["implementation"]["review"].get("status") == "pending"
                ):
                    updated_issue = adapter.get_issue(args.goal)
                    states, _raw, _processes = _github_pull_request_states(
                        repo, adapter.executable, [{"number": args.goal}], {args.goal: {"body": updated_issue.get("body", "")}},
                    )
                    pr_state = states.get(args.goal)
                    implementation = requested_goal["implementation"]
                    pr_url = implementation.get("pr")
                    tail = pr_url.rstrip("/").rsplit("/", 1)[-1] if isinstance(pr_url, str) else ""
                    if not isinstance(pr_state, dict) or not pr_state.get("base_oid") or not pr_state.get("head_oid"):
                        raise ValueError("qualifying review checkpoint lacks exact PR base/head evidence")
                    updated_goal = github_goal_record(updated_issue)
                    result["entropy_event"] = record_entropy_review_event(repo, {
                        "schema_version": 1,
                        "repository": repository,
                        "goal": args.goal,
                        "revision": updated_goal["revision"],
                        "goal_digest": updated_goal["digest"],
                        "status": updated_goal["status"],
                        "kind": "verified_checkpoint",
                        "pr": int(tail) if tail.isdigit() else None,
                        "base_oid": pr_state["base_oid"],
                        "head_oid": pr_state["head_oid"],
                        "merge_oid": None,
                    })
            elif args.goal_command == "migrate-open":
                result = migrate_open_repository_goals(
                    repo, project, limit=args.limit, include_feedback=args.include_feedback,
                )
            elif args.goal_command == "reconcile-merged":
                result = reconcile_merged_goal(repo, project, args.goal, apply=args.apply)
            else:
                result = inspect_repository_goal(repo, project, args.goal)
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
        elif args.command == "coaching":
            request = json.loads(args.input.resolve().read_text(encoding="utf-8-sig"))
            result = attribute_agent_work(request)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        elif args.command == "feedback":
            prompt = read_cli_text(args.prompt_file)
            selected = args.report or None
            runtime = None if args.diagnostic is None else {
                "agent": args.diagnostic_agent,
                "platform": args.diagnostic_platform,
                "python": args.diagnostic_python,
            }
            if args.feedback_command == "prepare":
                result = prepare_feedback(
                    repo, prompt, selected,
                    diagnostic_id=args.diagnostic, diagnostic_runtime=runtime,
                )
            else:
                result = submit_feedback(
                    repo, prompt, args.confirm, selected,
                    diagnostic_id=args.diagnostic, diagnostic_runtime=runtime,
                )
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        else:
            parser.print_help()
    except (EOFError, KeyboardInterrupt):
        print("\nNo further changes made.")
    except ValueError as exc:
        if args.command == "workflow":
            repair = workflow_repair_step(
                args.intent, str(exc), "Repair the reported workflow input or current repository state, then invoke workflow again.",
                source_skill=args.source_skill,
            )
            print(json.dumps(workflow_envelope(args.intent, [repair]), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return 2
        print(f"Could not continue: {exc}")
        return 2
    return 0


_feedback.configure_entrypoint(
    atomic_text=atomic_text,
    render_managed_goal=render_managed_goal,
    package_provenance=_package.package_provenance,
    load_diagnostic=_diagnostics.load_diagnostic,
    delete_diagnostic=_diagnostics.delete_diagnostic,
    validate_diagnostic=_diagnostics.validate_diagnostic,
)


if __name__ == "__main__":
    raise SystemExit(main())
