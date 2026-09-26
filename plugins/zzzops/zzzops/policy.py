"""Canonical project-policy state, validation, and rendering helpers.

This module deliberately has no dependency on the ZzzOps CLI or provider layer so
project-policy behavior can be exercised and reused without importing the control
entry point.
"""

from __future__ import annotations

import hashlib
import copy
import json
import re
from pathlib import Path
from typing import Any, Callable


PROJECT_SCHEMA_VERSION = 1
POLICY_SCHEMA_VERSION = 2
POLICY_DEFAULT_SCHEMA_VERSION = 2
PROJECT_POLICY_RELATIVE = ".zzzops/POLICY.json"
PROJECT_AUDIT_RELATIVE = ".zzzops/PROJECT_AUDIT.md"
BACKENDS = {"github_issues"}
POLICY_SECTION_IDS = (
    "backend",
    "git_review_release",
    "verification_testing",
    "code_quality",
    "dependencies_tooling",
    "security_privacy_compliance",
    "documentation_style",
    "deployment_resources",
    "engineering_rigor",
    "model_routing",
    "workflow_adherence",
    "automated_design",
    "autonomy_approval_parallelism",
)
POLICY_SECTION_TITLES = {
    "backend": "Goal storage",
    "git_review_release": "Git, review, and release",
    "verification_testing": "Verification and testing",
    "code_quality": "Code quality and refactoring",
    "dependencies_tooling": "Dependencies and tooling",
    "security_privacy_compliance": "Security, privacy, and compliance",
    "documentation_style": "Documentation and communication",
    "deployment_resources": "Deployment and resources",
    "engineering_rigor": "Engineering rigor",
    "model_routing": "Model routing and delegation",
    "workflow_adherence": "ZzzOps workflow use",
    "automated_design": "Automated design",
    "autonomy_approval_parallelism": "Autonomy, approvals, and parallel work",
}
OPTIONAL_POLICY_SETTING_PREFIXES: dict[str, tuple[str, ...]] = {}

GIT_REVIEW_SETTING_VALUES = {
    "review_pending_dependency": {"wait_for_completed_dependencies", "stack_from_reviewed_checkpoint"},
    "pull_request_mode": {"github_stacked_when_verified_else_chained", "chained_prs"},
}
WORK_SUGGESTION_CATEGORIES = frozenset({
    "documentation", "tests", "code_quality_non_behavioral", "agent_observability",
    "verification_efficiency",
})

REQUIRED_CI_MODES = {"inspect_exact_pr_head", "disabled", "existing_only"}

WORKFLOW_PHASE_IDS = (
    "understand", "decompose", "plan", "test_design", "implement", "publish",
)
WORKFLOW_PHASE_TYPES = frozenset(WORKFLOW_PHASE_IDS)
WORKFLOW_ASSIGNMENT_GROUPS = frozenset({"root", "planning", "implementation", "review", "coordinator"})
WORKFLOW_APPLICABILITY = frozenset({"always", "parent_only", "child_only"})
WORKFLOW_NOT_REQUIRED = frozenset({"never", "atomic_goal"})
WORKFLOW_INPUT_CATEGORIES = frozenset({
    "goal_spec", "policy", "phase_dag", "parents", "dependencies", "repository", "provider",
    "capabilities", "invocation", "upstream_outputs",
})

ROUTING_TIER_IDS = ("routine", "bounded", "reasoning", "architectural")
ROUTING_DIMENSIONS = frozenset({"phase_type", "consequence", "boundedness", "engineering_rigor"})
ROUTING_DIMENSION_VALUES = {
    "phase_type": WORKFLOW_PHASE_TYPES,
    "consequence": frozenset({"routine", "bounded", "consequential", "architectural"}),
    "boundedness": frozenset({"atomic", "bounded", "unbounded"}),
    "engineering_rigor": frozenset({"vibe", "structured", "agentic"}),
}

ENGINEERING_RIGOR_LEVELS = ("vibe", "structured", "agentic")
POLICY_CONFIGURATION_KEYS = {
    "backend": {"authority", "repository_identity", "capability_evidence"},
    "git_review_release": {
        "review_pending_dependency", "pull_request_mode",
    },
    "verification_testing": {"required_ci"},
    "code_quality": set(),
    "dependencies_tooling": set(),
    "security_privacy_compliance": set(),
    "documentation_style": set(),
    "deployment_resources": set(),
    "engineering_rigor": {"level", "minimums", "overrides"},
    "model_routing": {"tiers", "assessment_tree", "model_inventory"},
    "workflow_adherence": {"phase_dag"},
    "automated_design": set(),
    "autonomy_approval_parallelism": {
        "max_workers", "execution_reports", "resource_reservations", "refill", "portfolio_order",
    },
}

POLICY_DEFAULT_CONTENT_FIELDS = ("instructions", "configuration")
DOCUMENTATION_ADAPTER = "documentation-v1-v2-1"
LEGACY_POLICY_SOURCE = {"version": "2.1.0", "revision": "a36cf3a31876385885738cf86d90d8d9f77bbd02"}
LEGACY_DOCUMENTATION_SETTINGS = {
    "documentation": "repository_conventions", "style": "repository_conventions",
    "communication": {"style": "outcome_first", "technical_detail": "decision_risk_failure_or_request",
                      "user_action": "one_clear_action_with_reason_and_next_step"},
}
DOCUMENTATION_SUFFIX = (
    "Follow repository documentation and style conventions. Communicate outcomes first. "
    "Include technical detail for decisions, risks, failures, or when requested. "
    "When user action is needed, give one clear action, its reason, and the next step."
)
# Frozen schema1 requirements from v2.1.0; these validate sources, never map them.
LEGACY_REQUIRED_SETTING_PATHS = {
    "backend": (
        "authority repository_identity fallback capability_evidence tradeoffs tradeoffs.github_issues").split(),
    "git_review_release": (
        "execution_branch branch_base dependency_base review_pending_dependency  "
        "read_only_dependency_investigation multiple_dependency_base parent_pseudo_trunk child_target  "
        "pull_request_unit shared_pull_request commit_unit commit_style review_gate  "
        "review_state_reads_per_checkpoint pr_approval conversational_approval merge_after_approval").split(),
    "execution_continuation": (
        "continue_while_actionable triage_new_first max_easy_wins execute_intent new_goal_checkpoint  "
        "after_additive_capture exhausted_handoff_retains_intent human_unblock_watch  "
        "human_unblock_watch.enabled human_unblock_watch.trigger human_unblock_watch.max_blockers  "
        "human_unblock_watch.notify_once human_unblock_watch.poll_seconds human_unblock_watch.max_seconds  "
        "stop_reasons_clear_intent cross_task").split(),
    "verification_testing": (
        "mode widen test_bug ci_deduplication ci_deduplication.local_probe  "
        "ci_deduplication.skip_broad_local_when ci_deduplication.required_ci ci_deduplication.failure  "
        "ci_deduplication.unavailable artifact_verification artifact_verification.product_runtime  "
        "artifact_verification.documentation artifact_verification.test_cases  "
        "artifact_verification.test_harness").split(),
    "code_quality": (
        "non_behavioral_only_without_feature_goal completion_self_review review_scope dead_code  "
        "dynamic_generated_vendor record_clean_review reverify_after_changes").split(),
    "dependencies_tooling": (
        "tooling generated_files dependency_changes").split(),
    "security_privacy_compliance": (
        "secrets production_mutation project_constraints").split(),
    "documentation_style": (
        "documentation style communication communication.style communication.technical_detail  "
        "communication.user_action").split(),
    "deployment_resources": (
        "deployment resource_mode delegate_wait_after_seconds").split(),
    "engineering_rigor": (
        "escalation escalation.enabled escalation.allow_automatic_escalation  "
        "escalation.allow_automatic_deescalation minimums minimums.authentication minimums.authorization  "
        "minimums.payments minimums.secrets minimums.destructive_data_migrations minimums.security_sensitive  "
        "minimums.throwaway_prototypes overrides overrides.per_goal overrides.raising overrides.lowering  "
        "overrides.may_undercut_risk_minimum requirements_interview requirements_interview.source  "
        "requirements_interview.level_mapping requirements_interview.level_mapping.vibe  "
        "requirements_interview.level_mapping.structured requirements_interview.level_mapping.agentic").split(),
    "workflow_adherence": (
        "levels levels.optional levels.tracked levels.managed exemptions scoped_exception agents_projection").split(),
    "automated_design": (
        "scope commitment commitment.low commitment.high commitment.structural_cost_signals selection_basis  "
        "decision_record privacy_security hard_stops insufficient_evidence").split(),
    "autonomy_approval_parallelism": (
        "blocker_interview blocker_order requirements_interview requirements_interview.capture_depth  "
        "requirements_interview.mode requirements_interview.stakeholder_model  "
        "requirements_interview.execution_questions project_parallel_ceiling max_workers claim_ttl_hours  "
        "parallelization parallelization.measurement parallelization.threshold_bytes  "
        "parallelization.below_threshold_mode parallelization.at_or_above_threshold_mode  "
        "dependency_implementation_gate read_only_dependency_investigation execution_reports  "
        "execution_reports.enabled resource_reservations resource_reservations.mode  "
        "resource_reservations.exclusive_prefixes resource_reservations.exclusive_resources  "
        "worktree_lifecycle worktree_lifecycle.after_task worktree_lifecycle.abandoned_or_dirty  "
        "worktree_lifecycle.reuse_requires refill refill.enabled refill.allowed_categories  "
        "refill.max_per_run capture_defaults capture_defaults.priority capture_defaults.difficulty  "
        "capture_defaults.confidence planning planning.decompose_at planning.max_depth").split(),
}
LEGACY_TYPED_SETTINGS = json.loads(r'''
{
  "engineering_rigor": {
    "escalation": {
      "enabled": true,
      "allow_automatic_escalation": true,
      "allow_automatic_deescalation": false
    },
    "minimums": {
      "authentication": "agentic",
      "authorization": "agentic",
      "payments": "agentic",
      "secrets": "agentic",
      "destructive_data_migrations": "agentic",
      "security_sensitive": "agentic",
      "throwaway_prototypes": "vibe"
    },
    "overrides": {
      "per_goal": true,
      "raising": "allowed",
      "lowering": "explicit_user_authority",
      "may_undercut_risk_minimum": false
    },
    "requirements_interview": {
      "source": "effective_engineering_rigor",
      "level_mapping": {
        "vibe": "light",
        "structured": "standard",
        "agentic": "thorough"
      }
    }
  },
  "workflow_adherence": {
    "levels": {
      "optional": "direct_agent_work_allowed",
      "tracked": "durable_goal_required_for_substantial_agent_work",
      "managed": "zzzops_workflow_required_for_repository_changes"
    },
    "exemptions": [
      "read_only_investigation",
      "zzzops_administration"
    ],
    "scoped_exception": "explicit_scoped_user_authority",
    "agents_projection": "review_workflow_reconciliation"
  },
  "automated_design": {
    "scope": "bounded_commitment_in_scope_implementation",
    "commitment": {
      "low": "replace_verify_and_clean_within_one_goal_before_fanout",
      "high": "compare_evidence_cost_signal_or_explicit_current_design_review",
      "structural_cost_signals": [
        "affected_goal_units",
        "started_descendant_branches",
        "started_descendant_prs",
        "durable_data",
        "public_or_integration_contracts",
        "external_state",
        "compatibility_paths",
        "verification_breadth",
        "clean_removal_path"
      ]
    },
    "selection_basis": [
      "project_objectives",
      "kpi_evidence",
      "constraints",
      "precedence"
    ],
    "decision_record": [
      "alternatives",
      "rationale",
      "assumptions",
      "falsifiable_validation_signal"
    ],
    "privacy_security": "unambiguously_risk_reducing_without_material_behavior_change",
    "hard_stops": [
      "product_scope",
      "incompatible_public_contract",
      "destructive_migration",
      "external_spending",
      "deployment",
      "external_write",
      "human_review",
      "safety_authority",
      "higher_authority"
    ],
    "insufficient_evidence": "durable_design_blocker"
  }
}
''')
_package_provenance: Callable[[Path | None], dict[str, str]] | None = None


def configure_entrypoint(*, package_provenance: Callable[[Path | None], dict[str, str]]) -> None:
    global _package_provenance
    _package_provenance = package_provenance


def policy_default_content(section: dict[str, Any]) -> dict[str, Any]:
    return {
        field: json.loads(json.dumps(section.get(field), ensure_ascii=False))
        for field in POLICY_DEFAULT_CONTENT_FIELDS
    }


def policy_content_digest(content: Any) -> str:
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _exact(left: Any, right: Any) -> bool:
    """JSON equality without Python's True == 1 coercion."""
    return policy_content_digest(left) == policy_content_digest(right)


def _field_differences(left: Any, right: Any, path: str = "") -> list[str]:
    if _exact(left, right):
        return []
    if isinstance(left, dict) and isinstance(right, dict):
        result = []
        for key in sorted(set(left) | set(right)):
            child = f"{path}.{key}" if path else key
            result.extend(_field_differences(left[key], right[key], child)
                          if key in left and key in right else [child])
        return result
    return [path or "$"]


def _section_meaning(section: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return policy_section_review_content(
        {key: value for key, value in section.items() if key != "migration_lineage"}, evidence,
    )


def _legacy_documentation_projection(section: dict[str, Any]) -> dict[str, Any] | None:
    """The sole reviewed cross-schema adapter. It never drops unknown fields."""
    fields = {"id", "title", "required", "applicable", "decision", "rationale", "source_ids",
              "confidence", "default_origin", "default_disposition", "settings", "exceptions",
              "unresolved", "review"}
    if (not isinstance(section, dict) or section.get("id") != "documentation_style"
            or set(section) - fields - {"default_provenance"}
            or fields - set(section) or not text_present(section.get("decision"))
            or not _exact(section.get("settings"), LEGACY_DOCUMENTATION_SETTINGS)):
        return None
    target = copy.deepcopy(section)
    target["instructions"] = target.pop("decision") + "\n\n" + DOCUMENTATION_SUFFIX
    target.pop("settings")
    target["configuration"] = {}
    target.pop("default_provenance", None)
    target.pop("review", None)
    return target


def _legacy_origin_errors(section: dict[str, Any]) -> list[str]:
    """Validate the immutable v2.1.0 documentation catalog, never today's default."""
    origin = section.get("default_provenance")
    if origin is None or origin == {"status": "unknown"}:
        return []
    if not isinstance(origin, dict):
        return ["invalid historical default provenance"]
    status = origin.get("status")
    fields = {"status", "default_id", "schema_version", "source"}
    fields |= {"digest", "snapshot"} if status == "adopted" else {"catalog_digest"}
    if status == "adopted" and "declined_digest" in origin:
        fields.add("declined_digest")
    catalog = {"decision": "Follow evidenced repository documentation, style, and user-communication conventions.",
               "settings": LEGACY_DOCUMENTATION_SETTINGS}
    if (status not in {"adopted", "customized"} or set(origin) != fields
            or origin.get("default_id") != "zzzops.policy.documentation_style"
            or type(origin.get("schema_version")) is not int or origin["schema_version"] != 1
            or not _exact(origin.get("source"), LEGACY_POLICY_SOURCE)
            or origin.get("digest" if status == "adopted" else "catalog_digest") != policy_content_digest(catalog)):
        return ["unrecognized historical documentation default provenance"]
    if status == "adopted" and (not _exact(origin.get("snapshot"), catalog)
            or not _exact({k: section.get(k) for k in ("decision", "settings")}, catalog)):
        return ["historical adopted default differs from its effective content"]
    if "declined_digest" in origin and not _digest_text(origin["declined_digest"]):
        return ["invalid historical declined default digest"]
    return []


def _legacy_schema_errors(source: dict[str, Any]) -> list[str]:
    """Frozen v2.1.0 typed contracts; unsupported sections receive no adapter."""
    errors = []
    sections = {s["id"]: s for s in source["policy"]["sections"]}
    for section_id, section in sections.items():
        settings = section["settings"]
        for path in LEGACY_REQUIRED_SETTING_PATHS[section_id]:
            value = settings
            for component in path.split("."):
                if not isinstance(value, dict) or component not in value:
                    errors.append(f"historical {section_id}.settings.{path} is missing")
                    break
                value = value[component]
        errors.extend(validate_default_provenance(section, f"historical {section_id}", _legacy=True))
    if errors:
        return errors
    git = sections["git_review_release"]["settings"]
    allowed = {
        "review_pending_dependency": {"wait_for_completed_dependencies", "stack_from_reviewed_checkpoint"},
        "review_gate": {"human_after_checks", "human_at_exhaustion"},
        "conversational_approval": {"allowed_otherwise", "never_for_goal_progress"},
    }
    if any(git[key] not in values for key, values in allowed.items()) or (
            git["review_gate"] == "human_at_exhaustion" and (
                git["review_pending_dependency"] != "stack_from_reviewed_checkpoint"
                or git["conversational_approval"] != "never_for_goal_progress")):
        errors.append("invalid historical git review contract")
    rigor = sections["engineering_rigor"]
    settings = rigor["settings"]
    expected = LEGACY_TYPED_SETTINGS["engineering_rigor"]
    if rigor["decision"] not in {"vibe", "structured", "agentic"} or set(settings) != set(expected):
        errors.append("invalid historical engineering rigor contract")
    escalation = settings["escalation"]
    if (set(escalation) != set(expected["escalation"])
            or any(type(escalation[key]) is not bool for key in expected["escalation"])
            or escalation["allow_automatic_deescalation"] is not False
            or (escalation["allow_automatic_escalation"] is True and escalation["enabled"] is not True)):
        errors.append("invalid historical rigor escalation")
    minimums = settings["minimums"]
    if any(not isinstance(key, str) or not text_present(key) or key.casefold() != key
           or not key.replace("_", "").isalnum() or value not in {"vibe", "structured", "agentic"}
           for key, value in minimums.items()):
        errors.append("invalid historical rigor minimums")
    overrides = settings["overrides"]
    if (set(overrides) != set(expected["overrides"]) or type(overrides["per_goal"]) is not bool
            or not _exact({k: v for k, v in overrides.items() if k != "per_goal"},
                          {k: v for k, v in expected["overrides"].items() if k != "per_goal"})):
        errors.append("invalid historical rigor overrides")
    if not _exact(settings["requirements_interview"], expected["requirements_interview"]):
        errors.append("invalid historical rigor interview mapping")
    workflow = sections["workflow_adherence"]
    if (workflow["decision"] not in {"optional", "tracked", "managed"}
            or not _exact(workflow["settings"], LEGACY_TYPED_SETTINGS["workflow_adherence"])):
        errors.append("invalid historical workflow contract")
    design = sections["automated_design"]
    if design["decision"] not in {"enabled", "disabled"} or any(
            not _exact(design["settings"].get(key), value)
            for key, value in LEGACY_TYPED_SETTINGS["automated_design"].items()):
        errors.append("invalid historical automated design contract")
    autonomy = sections["autonomy_approval_parallelism"]["settings"]
    if autonomy["dependency_implementation_gate"] not in {"dependencies_done", "stack_from_reviewed_checkpoint"}:
        errors.append("invalid historical dependency implementation gate")
    if type(autonomy["execution_reports"]["enabled"]) is not bool:
        errors.append("invalid historical execution reporting")
    interview = autonomy["requirements_interview"]
    for key, values in {"capture_depth": {"light", "standard", "thorough"}, "mode": {"adaptive"},
                        "stakeholder_model": {"requesting_user_only"}, "execution_questions": {"durable_blockers_only"}}.items():
        if interview[key] not in values:
            errors.append(f"invalid historical interview {key}")
    if interview["capture_depth"] != expected["requirements_interview"]["level_mapping"].get(rigor["decision"]):
        errors.append("historical rigor and interview depth conflict")
    try:
        normalize_resource_policy(autonomy["resource_reservations"])
    except ValueError as exc:
        errors.append(f"invalid historical resources: {exc}")
    repository = source["repository"]
    backend = sections["backend"]
    if (not nonempty(repository.get("identity")) or backend["decision"] != source["backend"]
            or backend["settings"]["authority"] != source["backend"]
            or backend["settings"]["repository_identity"] != repository["identity"]
            or not text_present(backend["settings"]["capability_evidence"])):
        errors.append("historical backend does not match repository authority")
    charter = source["charter"]
    if any(not nonempty(charter.get(key)) for key in ("outcome", "why_it_matters", "time_horizon", "precedence")):
        errors.append("invalid historical charter text")
    if any(not nonempty_list(charter.get(key)) for key in ("beneficiaries", "acceptance_criteria", "constraints", "non_goals", "unacceptable_tradeoffs")):
        errors.append("invalid historical charter lists")
    kpis = charter.get("kpis")
    if not isinstance(kpis, list) or not kpis or any(
            not isinstance(kpi, dict) or any(not text_present(kpi.get(key))
            for key in ("name", "why", "baseline", "target", "evidence", "cadence")) for kpi in kpis):
        errors.append("invalid historical charter metrics")
    if not source["history"] or any(not isinstance(entry, dict) or any(
            not text_present(entry.get(key)) for key in ("date", "actor", "change", "reason"))
            for entry in source["history"]):
        errors.append("invalid historical review history")
    return errors


def _legacy_authority_errors(source: dict[str, Any], artifacts: dict[str, str], *, review: bool) -> list[str]:
    """Verify persisted schema1 authority and the bounded all-pending review transition.

    Historical reviewed_digest is a *whole pending state* digest. Reconstructing
    that state is valid only when its exact digest matches; no missing snapshot
    is treated as evidence. Other confirmation histories remain unsupported.
    """
    try:
        policy = source["policy"]
        sections = policy["sections"]
        approval = source["approval"]
        expected_ids = (set(POLICY_SECTION_IDS) - {"model_routing"}) | {"execution_continuation"}
        if (type(policy["schema_version"]) is not int or policy["schema_version"] != 1
                or set(policy) != {"schema_version", "sections", "evidence"}
                or source["initialized"] is not True
                or source["backend"] not in BACKENDS
                or type(source["revision"]) is not int or source["revision"] < 2
                or len(sections) != len(expected_ids) or {s["id"] for s in sections} != expected_ids
                or not isinstance(approval, dict) or set(approval) != {"reviewer", "date", "digest"}
                or not text_present(approval["reviewer"]) or not text_present(approval["date"])
                or approval["digest"] != policy_review_digest(source)):
            return ["invalid historical approved state"]
        if set(source) != {"schema_version", "initialized", "backend", "repository", "revision", "charter", "policy", "history", "bindings", "approval"} or type(source["schema_version"]) is not int or source["schema_version"] != 1:
            return ["unsupported historical state fields"]
        evidence = policy["evidence"]
        ids = [item["id"] for item in evidence]
        if not evidence or len(ids) != len(set(ids)) or any(
                not text_present(item.get(k)) for item in evidence for k in ("id", "source", "finding")):
            return ["invalid historical evidence"]
        common = {"id", "title", "required", "applicable", "decision", "rationale", "source_ids",
                  "confidence", "default_origin", "default_disposition", "settings", "exceptions", "unresolved", "review"}
        for section in sections:
            if (set(section) - common - {"default_provenance"} or common - set(section)
                    or any(not text_present(section[k]) for k in ("title", "decision", "rationale", "default_origin"))
                    or any(type(section[k]) is not bool for k in ("required", "applicable"))
                    or section["confidence"] not in {"low", "medium", "high"}
                    or section["default_disposition"] not in {"accepted", "changed", "rejected", "unknown"}
                    or not isinstance(section["settings"], dict)
                    or any(not isinstance(section[k], list) for k in ("source_ids", "exceptions", "unresolved"))
                    or set(section["source_ids"]) - set(ids) or section["unresolved"]
                    or set(section["review"]) != {"approved", "reviewer", "date", "reviewed_digest"}
                    or section["review"]["approved"] is not True
                    or any(not text_present(section["review"][k]) for k in ("reviewer", "date"))
                    or not _digest_text(section["review"]["reviewed_digest"])):
                return ["unsupported historical section or review metadata"]
        schema_errors = _legacy_schema_errors(source)
        if schema_errors:
            return schema_errors
        for name, path in (("project", ".zzzops/PROJECT.md"), ("audit", PROJECT_AUDIT_RELATIVE)):
            if source["bindings"][name] != {"path": path, "digest": project_digest(artifacts[name])}:
                return ["historical rendered artifact binding changed"]
        # Both renderers shipped in v2.1.0 (policy module and CLI entrypoint).
        modes = [mode for mode in (True, False)
                 if render_project(source, _legacy=True, _legacy_provenance=mode) == artifacts["project"]]
        if not modes or render_project_audit(source, _legacy=True) != artifacts["audit"]:
            return ["historical artifacts do not render their bound state"]
        if not review:
            return []
        pending = copy.deepcopy(source)
        pending.update(initialized=False, approval=None, revision=source["revision"] - 1)
        pending["history"] = pending["history"][:-1]
        if not pending["history"]:
            return ["historical pending review history unavailable"]
        for section in pending["policy"]["sections"]:
            section["review"] = {"approved": False}
        for mode in modes:
            pending["bindings"] = {
                "project": {"path": ".zzzops/PROJECT.md", "digest": project_digest(render_project(pending, _legacy=True, _legacy_provenance=mode))},
                "audit": {"path": PROJECT_AUDIT_RELATIVE, "digest": project_digest(render_project_audit(pending, _legacy=True))},
            }
            reviewed_digest = policy_review_digest(pending)
            if all(s["review"] == {"approved": True, "reviewer": approval["reviewer"],
                    "date": approval["date"], "reviewed_digest": reviewed_digest} for s in sections):
                return []
        return ["historical reviewed_digest has no supported exact pending-state reconstruction"]
    except (KeyError, TypeError, ValueError, AttributeError):
        return ["malformed historical authority"]


def classify_policy_upgrade(source: dict[str, Any] | None, target: dict[str, Any],
                           artifacts: dict[str, str] | None = None) -> dict[str, Any]:
    """Compare a source state and a prepared pending policy without mutating either."""
    source_policy = source.get("policy", {}) if isinstance(source, dict) else {}
    def section_list_valid(policy: Any) -> bool:
        return (isinstance(policy, dict) and isinstance(policy.get("sections", []), list)
                and all(isinstance(section, dict) and text_present(section.get("id"))
                        for section in policy.get("sections", [])))
    if not section_list_valid(source_policy) or not section_list_valid(target):
        return {"source_schema": None, "target_schema": None, "classification": "unknown",
                "sections": [], "differences": [], "source_errors": ["malformed policy section structure"],
                "target_errors": []}
    version = source_policy.get("schema_version")
    old = {s["id"]: s for s in source_policy.get("sections", [])}
    new = {s["id"]: s for s in target.get("sections", [])}
    source_errors = (validate_project_state(source) if version == 2 else
                     _legacy_authority_errors(source, artifacts or {}, review=False) if version == 1 else
                     ["unsupported or absent source policy schema"])
    if version == 2 and artifacts is not None:
        for name in ("project", "audit"):
            if project_digest(artifacts.get(name, "")) != (source or {}).get("bindings", {}).get(name, {}).get("digest"):
                source_errors.append(f"{name} policy artifact digest changed")
    target_errors = validate_policy(target, require_pending=True)
    evidence = target.get("evidence")
    evidence_ids = set()
    if not isinstance(evidence, list) or not evidence:
        target_errors.append("evidence must be a non-empty list")
    else:
        for index, item in enumerate(evidence):
            if not isinstance(item, dict) or any(not text_present(item.get(key)) for key in ("id", "source", "finding")):
                target_errors.append(f"evidence[{index}] requires id, source, and finding")
            elif item["id"] in evidence_ids:
                target_errors.append(f"evidence[{index}].id must be unique")
            else:
                evidence_ids.add(item["id"])
    for index, section in enumerate(target.get("sections", [])):
        citations = section.get("source_ids")
        if isinstance(citations, list):
            if any(not isinstance(citation, str) for citation in citations):
                target_errors.append(f"sections[{index}].source_ids must contain evidence identifiers")
            elif set(citations) - evidence_ids:
                target_errors.append(f"sections[{index}].source_ids contain missing citations")
    if set(target) != {"schema_version", "sections", "evidence"} or type(target.get("schema_version")) is not int:
        target_errors.append("unsupported target policy metadata")
    if version == 2 and (set(source_policy) != {"schema_version", "sections", "evidence"}
                         or type(version) is not int):
        source_errors.append("unsupported source policy metadata")
    results = []
    for section_id in sorted(set(old) | set(new)):
        prior, candidate = old.get(section_id), new.get(section_id)
        item = {"section_id": section_id, "classification": "unknown", "differences": [],
                "source_provenance": copy.deepcopy((prior or {}).get("default_provenance")),
                "authority_retained": False, "reasons": []}
        if prior is not None and candidate is not None:
            item["differences"] = _field_differences(
                {k: v for k, v in prior.items() if k not in {"review", "migration_lineage"}},
                {k: v for k, v in candidate.items() if k not in {"review", "migration_lineage"}},
            )
        if prior is None or candidate is None:
            item.update(classification="substantive", differences=["section_added" if prior is None else "section_removed"])
        elif source_errors or target_errors:
            item["reasons"] = source_errors + target_errors
        elif version == 2:
            before = _section_meaning(prior, source_policy["evidence"])
            after = _section_meaning(candidate, target["evidence"])
            item["differences"] = _field_differences(before, after)
            item["classification"] = "substantive" if item["differences"] else "representation_only"
            item["authority_retained"] = not item["differences"] and prior["review"]["approved"] is True
        elif version == 1 and section_id == "documentation_style":
            mapped = _legacy_documentation_projection(prior)
            if mapped is None:
                item["reasons"] = ["documentation settings or metadata have no finite adapter"]
            else:
                before = policy_section_review_content(mapped, source_policy["evidence"])
                after = policy_section_review_content({k: v for k, v in candidate.items()
                    if k not in {"default_provenance", "migration_lineage"}}, target["evidence"])
                item["differences"] = _field_differences(before, after)
                errors = _legacy_origin_errors(prior) + _legacy_authority_errors(source, artifacts or {}, review=True)
                item["reasons"] = errors
                item["classification"] = "substantive" if item["differences"] else "unknown" if errors else "representation_only"
                item["authority_retained"] = item["classification"] == "representation_only"
                item["adapter"] = DOCUMENTATION_ADAPTER
        else:
            item["reasons"] = ["no reviewed section adapter for this schema transition"]
        results.append(item)
    differences = []
    if not _exact(source_policy.get("evidence"), target.get("evidence")):
        differences.append("evidence")
    if version == target.get("schema_version") and not _exact(
            [s["id"] for s in source_policy.get("sections", [])], [s["id"] for s in target.get("sections", [])]):
        differences.append("sections.order")
    kinds = {item["classification"] for item in results}
    if differences:
        kinds.add("substantive")
    if source_errors or target_errors:
        kinds.add("unknown")
    return {"source_schema": version, "target_schema": target.get("schema_version"),
            "classification": "unknown" if "unknown" in kinds else "substantive" if "substantive" in kinds else "representation_only",
            "sections": results, "differences": differences,
            "source_errors": source_errors, "target_errors": target_errors}


def retain_policy_authority(source: dict[str, Any] | None, target: dict[str, Any],
                            artifacts: dict[str, str]) -> dict[str, Any]:
    classification = classify_policy_upgrade(source, target, artifacts)
    old = {s["id"]: s for s in (source or {}).get("policy", {}).get("sections", [])}
    decisions = {item["section_id"]: item for item in classification["sections"]}
    for section in target["sections"]:
        decision = decisions[section["id"]]
        if not decision["authority_retained"]:
            continue
        prior = old[section["id"]]
        if classification["source_schema"] == 2:
            section["review"] = copy.deepcopy(prior["review"])
            if "migration_lineage" in prior:
                section["migration_lineage"] = copy.deepcopy(prior["migration_lineage"])
            continue
        section["default_provenance"] = {
            "status": "derived", "default_id": "zzzops.policy.documentation_style",
            "adapter": DOCUMENTATION_ADAPTER, "source": copy.deepcopy(prior.get("default_provenance")),
        }
        target_digest = policy_content_digest(_section_meaning(section, target["evidence"]))
        section["migration_lineage"] = {
            "adapter": DOCUMENTATION_ADAPTER, "source_identity": copy.deepcopy(LEGACY_POLICY_SOURCE),
            "source_state": copy.deepcopy(source), "source_artifacts": copy.deepcopy(artifacts),
            "target_digest": target_digest,
        }
        section["review"] = {**copy.deepcopy(prior["review"]), "reviewed_digest": target_digest}
    return classification


def _lineage_errors(section: dict[str, Any], evidence: list[dict[str, Any]]) -> list[str]:
    proof = section.get("migration_lineage")
    if proof is None:
        return ["derived provenance lacks migration lineage"] if (section.get("default_provenance") or {}).get("status") == "derived" else []
    try:
        if (set(proof) != {"adapter", "source_identity", "source_state", "source_artifacts", "target_digest"}
                or proof["adapter"] != DOCUMENTATION_ADAPTER
                or not _exact(proof["source_identity"], LEGACY_POLICY_SOURCE)):
            return ["unsupported migration lineage"]
        source = proof["source_state"]
        errors = _legacy_authority_errors(source, proof["source_artifacts"], review=True)
        prior = next(s for s in source["policy"]["sections"] if s["id"] == section["id"])
        errors.extend(_legacy_origin_errors(prior))
        projected = _legacy_documentation_projection(prior)
        if projected is None:
            return errors + ["migration source has no finite adapter"]
        projected["default_provenance"] = {"status": "derived", "default_id": "zzzops.policy.documentation_style",
                                             "adapter": DOCUMENTATION_ADAPTER, "source": copy.deepcopy(prior.get("default_provenance"))}
        expected = _section_meaning(projected, source["policy"]["evidence"])
        actual = _section_meaning(section, evidence)
        if not _exact(expected, actual) or proof["target_digest"] != policy_content_digest(actual):
            errors.append("migration target or source content changed")
        if section["review"] != {**prior["review"], "reviewed_digest": proof["target_digest"]}:
            errors.append("derived review does not retain original approval identity")
        return errors
    except (KeyError, TypeError, ValueError, AttributeError, StopIteration):
        return ["malformed migration lineage"]


def policy_section_review_content(section: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    content = {key: value for key, value in section.items() if key != "review"}
    sources = set(section.get("source_ids", []))
    content["source_evidence"] = sorted(
        (item for item in evidence if item.get("id") in sources), key=lambda item: item["id"],
    )
    return json.loads(json.dumps(content, ensure_ascii=False, sort_keys=True))


def policy_default_catalog() -> dict[str, dict[str, Any]]:
    template = Path(__file__).parent / "templates" / "project-goals" / "INIT_PLAN.json"
    data = json.loads(template.read_text(encoding="utf-8-sig"))
    catalog: dict[str, dict[str, Any]] = {}
    for section in data["policy"]["sections"]:
        default_id = section["default_id"]
        if default_id in catalog:
            raise ValueError(f"duplicate policy default id: {default_id}")
        content = policy_default_content(section)
        catalog[default_id] = {
            "id": default_id,
            "schema_version": POLICY_DEFAULT_SCHEMA_VERSION,
            "section_id": section["id"],
            "content": content,
            "digest": policy_content_digest(content),
        }
    return dict(sorted(catalog.items()))


def machinery_provenance(repo: Path) -> dict[str, str]:
    if _package_provenance is None:
        raise RuntimeError("Policy module was not configured with Agent Plugin provenance")
    return _package_provenance(repo)


def _adopted_provenance(entry: dict[str, Any], source: dict[str, str]) -> dict[str, Any]:
    return {
        "status": "adopted", "default_id": entry["id"],
        "schema_version": entry["schema_version"], "source": source,
        "digest": entry["digest"], "snapshot": json.loads(json.dumps(entry["content"])),
    }


def prepare_policy_defaults(
    repo: Path, policy: dict[str, Any], previous_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prepared = json.loads(json.dumps(policy))
    catalog = policy_default_catalog()
    previous = {
        section["id"]: section for section in (previous_policy or {}).get("sections", [])
        if isinstance(section, dict) and text_present(section.get("id"))
    } if (previous_policy or {}).get("schema_version") == POLICY_SCHEMA_VERSION else {}
    source: dict[str, str] | None = None
    for section in prepared.get("sections", []):
        if not isinstance(section, dict):
            continue
        section_id = section.get("id")
        default_id = section.pop("default_id", None)
        resolution = section.pop("default_resolution", None)
        prior = previous.get(section_id)
        provenance = section.get("default_provenance")
        if prior is not None:
            provenance = json.loads(json.dumps(prior["default_provenance"])) if "default_provenance" in prior else None
            if (provenance or {}).get("status") == "derived" and not _exact(policy_default_content(section), policy_default_content(prior)):
                provenance = {"status": "unknown"}
        if provenance is not None and not isinstance(provenance, dict):
            raise ValueError(f"policy section {section_id} default provenance must be an object")
        if prior is None and default_id is None and not (isinstance(provenance, dict) and provenance.get("default_id")):
            raise ValueError(f"policy section {section_id} lacks a stable default identity")
        entry = catalog.get(default_id or (provenance or {}).get("default_id"))
        if entry is not None and entry["section_id"] != section_id:
            raise ValueError(f"policy section {section_id} uses a default for {entry['section_id']}")
        if resolution is not None:
            if not isinstance(resolution, dict) or resolution.get("action") not in {"accept", "decline"} or entry is None:
                raise ValueError(f"policy section {section_id} has an invalid default resolution")
            if resolution.get("digest") != entry["digest"]:
                raise ValueError(f"policy section {section_id} default resolution is stale")
            if resolution["action"] == "accept":
                for field, value in entry["content"].items():
                    section[field] = json.loads(json.dumps(value))
                source = source or machinery_provenance(repo)
                provenance = _adopted_provenance(entry, source)
                section["default_disposition"] = "accepted"
            else:
                if not isinstance(provenance, dict) or provenance.get("status") != "adopted":
                    raise ValueError(f"policy section {section_id} cannot decline a default without adopted provenance")
                provenance["declined_digest"] = entry["digest"]
        elif provenance is None:
            if prior is not None:
                provenance = None
            elif default_id is None or section.get("default_disposition") == "unknown":
                provenance = {"status": "unknown"}
            elif entry is None:
                raise ValueError(f"policy section {section_id} references an unknown default")
            elif section.get("default_disposition") == "accepted":
                if policy_default_content(section) != entry["content"]:
                    raise ValueError(f"policy section {section_id} accepted default content is inconsistent")
                source = source or machinery_provenance(repo)
                provenance = _adopted_provenance(entry, source)
            else:
                source = source or machinery_provenance(repo)
                provenance = {
                    "status": "customized", "default_id": entry["id"],
                    "schema_version": entry["schema_version"], "source": source,
                    "catalog_digest": entry["digest"],
                }
        elif prior is None and provenance.get("status") in {"adopted", "customized"}:
            if entry is None:
                raise ValueError(f"policy section {section_id} references an unknown default")
            source = source or machinery_provenance(repo)
            expected_digest = provenance.get("digest") if provenance.get("status") == "adopted" else provenance.get("catalog_digest")
            if expected_digest != entry["digest"] or provenance.get("source") != source:
                raise ValueError(f"policy section {section_id} default provenance does not match installed machinery")
        elif provenance.get("status") == "adopted" and policy_default_content(section) != provenance.get("snapshot"):
            provenance = {
                "status": "customized", "default_id": provenance.get("default_id"),
                "schema_version": provenance.get("schema_version"), "source": provenance.get("source"),
                "catalog_digest": provenance.get("digest"),
            }
            section["default_disposition"] = "changed"
        if provenance is None:
            section.pop("default_provenance", None)
        else:
            section["default_provenance"] = provenance
        if (prior is not None and (provenance or {}).get("status") == "derived"
                and not _exact(_section_meaning(section, []), _section_meaning(prior, []))):
            # A new exact human approval may authorize this choice, but the old
            # conversion proof cannot establish its changed meaning or origin.
            section["default_provenance"] = {"status": "unknown"}
    return prepared


def compare_policy_defaults(
    policy: dict[str, Any], catalog: dict[str, dict[str, Any]] | None = None,
    selected_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    catalog = catalog or policy_default_catalog()
    selected_ids = selected_ids or set()
    result = []
    for section in policy.get("sections", []):
        section_id = section.get("id")
        provenance = section.get("default_provenance")
        item: dict[str, Any] = {"section_id": section_id}
        if isinstance(provenance, dict) and provenance.get("status") == "derived":
            original = provenance.get("source") or {}
            item.update({"status": "unknown_origin" if original.get("status", "unknown") == "unknown" else "customized",
                         "default_id": provenance.get("default_id"), "derivation": provenance.get("adapter"),
                         "source_provenance": copy.deepcopy(original)})
        elif not isinstance(provenance, dict) or provenance.get("status") == "unknown":
            item["status"] = "unknown_origin"
        elif provenance.get("status") == "customized" or policy_default_content(section) != provenance.get("snapshot"):
            item.update({"status": "customized", "default_id": provenance.get("default_id")})
        else:
            entry = catalog.get(provenance.get("default_id"))
            if entry is None:
                item.update({"status": "unknown_default", "default_id": provenance.get("default_id")})
            elif provenance.get("digest") == entry["digest"]:
                item.update({"status": "current", "default_id": entry["id"], "digest": entry["digest"]})
            elif provenance.get("declined_digest") == entry["digest"]:
                item.update({"status": "declined", "default_id": entry["id"], "old_digest": provenance.get("digest"), "new_digest": entry["digest"]})
            else:
                item.update({"status": "update_available", "default_id": entry["id"], "old_digest": provenance.get("digest"), "new_digest": entry["digest"]})
                if section_id in selected_ids:
                    item["old_snapshot"] = provenance.get("snapshot")
                    item["new_snapshot"] = entry["content"]
        result.append(item)
    return result


def _digest_text(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(
        character in "0123456789abcdef" for character in value[7:]
    )


def validate_default_provenance(section: dict[str, Any], prefix: str, *, _legacy: bool = False) -> list[str]:
    provenance = section.get("default_provenance")
    if provenance is None:
        return []  # Legacy reviewed policy: never infer provenance from value equality.
    if not isinstance(provenance, dict):
        return [f"{prefix}.default_provenance must be an object"]
    status = provenance.get("status")
    if status == "derived" and not _legacy:
        if (set(provenance) != {"status", "default_id", "adapter", "source"}
                or provenance.get("default_id") != "zzzops.policy.documentation_style"
                or section.get("id") != "documentation_style" or provenance.get("adapter") != DOCUMENTATION_ADAPTER):
            return [f"{prefix}.default_provenance has invalid derivation"]
        return []  # The full derivation is checked with its cited evidence below.
    if status == "unknown":
        return [] if set(provenance) == {"status"} else [f"{prefix}.default_provenance unknown origin must contain only status"]
    if status not in {"adopted", "customized"}:
        return [f"{prefix}.default_provenance.status is invalid"]
    errors = []
    expected_fields = {
        "adopted": {"status", "default_id", "schema_version", "source", "digest", "snapshot"},
        "customized": {"status", "default_id", "schema_version", "source", "catalog_digest"},
    }[status]
    if status == "adopted" and "declined_digest" in provenance:
        expected_fields.add("declined_digest")
    if set(provenance) != expected_fields:
        errors.append(f"{prefix}.default_provenance contains non-canonical fields")
    default_id = provenance.get("default_id")
    if default_id != f"zzzops.policy.{section.get('id')}":
        errors.append(f"{prefix}.default_provenance.default_id is inconsistent")
    schema_version = 1 if _legacy else POLICY_DEFAULT_SCHEMA_VERSION
    if type(provenance.get("schema_version")) is not int or provenance.get("schema_version") != schema_version:
        errors.append(f"{prefix}.default_provenance.schema_version must be {schema_version}")
    source = provenance.get("source")
    revision = source.get("revision") if isinstance(source, dict) else None
    if (
        not isinstance(source, dict) or set(source) != {"revision", "version"}
        or not text_present(source.get("version"))
        or not isinstance(revision, str) or len(revision) not in {40, 64}
        or any(character not in "0123456789abcdef" for character in revision)
    ):
        errors.append(f"{prefix}.default_provenance.source requires revision and version")
    digest_field = "digest" if status == "adopted" else "catalog_digest"
    if not _digest_text(provenance.get(digest_field)):
        errors.append(f"{prefix}.default_provenance.{digest_field} is invalid")
    if status == "adopted":
        snapshot = provenance.get("snapshot")
        fields = ("decision", "settings") if _legacy else POLICY_DEFAULT_CONTENT_FIELDS
        if not isinstance(snapshot, dict) or set(snapshot) != set(fields):
            errors.append(f"{prefix}.default_provenance.snapshot must contain the complete canonical default")
        elif policy_content_digest(snapshot) != provenance.get("digest"):
            errors.append(f"{prefix}.default_provenance.digest does not match snapshot")
        elif not _exact({field: section.get(field) for field in fields}, snapshot):
            errors.append(f"{prefix}.default_provenance snapshot differs from effective policy")
        if "declined_digest" in provenance and not _digest_text(provenance["declined_digest"]):
            errors.append(f"{prefix}.default_provenance.declined_digest is invalid")
    return errors


def default_provenance_label(section: dict[str, Any]) -> str:
    origin = section.get("default_provenance") or {}
    status = origin.get("status")
    if status == "derived":
        return {"adopted": "derived from the recorded historical ZzzOps default",
                "customized": "derived from a historical project customization"}.get(
                    (origin.get("source") or {}).get("status"), "default origin unknown")
    return {
        "adopted": "adopted from the recorded ZzzOps default",
        "customized": "customized from a ZzzOps default",
    }.get(status, "default origin unknown")


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().casefold() != "unknown"


def text_present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(nonempty(item) for item in value)


def normalize_resources(resources: Any) -> list[str]:
    if not isinstance(resources, list):
        raise ValueError("resources must be a list")
    normalized = []
    for resource in resources:
        if not isinstance(resource, str):
            raise ValueError("resource entries must be text")
        value = resource.strip().replace("\\", "/")
        prefix, separator, target = value.partition(":")
        prefix = prefix.casefold()
        if prefix not in {"path", "branch", "integration", "generated", "external"} or not separator or not target:
            raise ValueError("resources must use path, branch, integration, generated, or external prefixes")
        if len(value) > 200 or any(ord(character) < 32 for character in value):
            raise ValueError("resource entries must be at most 200 printable characters")
        normalized.append(value.casefold())
    if len(normalized) != len(set(normalized)):
        raise ValueError("resource entries must be unique")
    return sorted(normalized)


def normalize_resource_policy(policy: Any = None) -> dict[str, Any]:
    if policy is None:
        raise ValueError("reviewed resource_reservations policy is required")
    if not isinstance(policy, dict):
        raise ValueError("resource_reservations must be an object")
    unknown = sorted(set(policy) - {"mode", "exclusive_prefixes", "exclusive_resources"})
    if unknown:
        raise ValueError("resource_reservations has unknown fields: " + ", ".join(unknown))
    mode = policy.get("mode")
    if mode not in {"conflict_tolerant", "strict"}:
        raise ValueError("resource_reservations.mode must be conflict_tolerant or strict")
    prefixes = policy.get("exclusive_prefixes")
    supported = {"path", "integration", "generated", "external"}
    if (
        not isinstance(prefixes, list)
        or any(not isinstance(prefix, str) or prefix not in supported for prefix in prefixes)
        or len(prefixes) != len(set(prefixes))
    ):
        raise ValueError("resource_reservations.exclusive_prefixes must contain unique supported prefixes")
    if "exclusive_resources" not in policy:
        raise ValueError("resource_reservations.exclusive_resources is required")
    resources = normalize_resources(policy["exclusive_resources"])
    return {"mode": mode, "exclusive_prefixes": sorted(prefixes), "exclusive_resources": resources}


def exclusive_resources(resources: Any, policy: Any = None) -> list[str]:
    resources = normalize_resources(resources)
    if not resources:
        return []
    if policy is None and all(resource.startswith("branch:") for resource in resources):
        return resources  # Branch identity is invariant, not a project-policy selection.
    policy = normalize_resource_policy(policy)
    if policy["mode"] == "strict":
        return resources
    exact = set(policy["exclusive_resources"])
    prefixes = set(policy["exclusive_prefixes"])
    return [
        resource for resource in resources
        if resource.startswith("branch:") or resource in exact or resource.partition(":")[0] in prefixes
    ]


def _missing_setting_paths(current: Any, expected: Any, prefix: str = "configuration") -> list[str]:
    if not isinstance(expected, dict):
        return []
    if not isinstance(current, dict):
        return [prefix]
    missing = []
    for key, value in expected.items():
        path = f"{prefix}.{key}"
        if key not in current:
            missing.append(path)
        else:
            missing.extend(_missing_setting_paths(current[key], value, path))
    return missing


def missing_policy_settings(
    policy: dict[str, Any], catalog: dict[str, dict[str, Any]] | None = None,
) -> dict[str, list[str]]:
    """Return absent operational settings without filling them from shipped defaults."""
    catalog = policy_default_catalog() if catalog is None else catalog
    by_section = {
        entry["section_id"]: entry for entry in catalog.values()
        if isinstance(entry, dict) and entry.get("section_id") in POLICY_SECTION_IDS
    }
    result = {}
    for section in policy.get("sections", []):
        if not isinstance(section, dict) or section.get("id") not in by_section:
            continue
        section_id = section["id"]
        expected = by_section[section_id].get("content", {}).get("configuration", {})
        missing = _missing_setting_paths(section.get("configuration"), expected)
        optional_prefixes = OPTIONAL_POLICY_SETTING_PREFIXES.get(section_id, ())
        missing = [path for path in missing if not path.startswith(optional_prefixes)]
        if missing:
            result[section_id] = missing
    return result


def _policy_identifier(value: Any) -> bool:
    return (
        isinstance(value, str) and bool(value) and value.casefold() == value
        and value.replace("_", "").replace("-", "").replace(".", "").isalnum()
    )


def _workflow_phase_dag_errors(value: Any) -> list[str]:
    """Validate the static, declarative workflow graph stored in project policy."""
    if not isinstance(value, dict) or set(value) != {"schema_version", "phases"}:
        return ["phase_dag must contain schema_version and phases"]
    if value.get("schema_version") != 1 or not isinstance(value.get("phases"), list):
        return ["phase_dag schema_version or phases is invalid"]
    nodes: dict[str, dict[str, Any]] = {}
    errors = []
    expected_fields = {"id", "type", "depends_on", "parent_gates", "applicability", "assignment_group", "inputs", "not_required", "review"}
    for index, node in enumerate(value["phases"]):
        prefix = f"phase_dag.phases[{index}]"
        if not isinstance(node, dict) or set(node) != expected_fields:
            errors.append(f"{prefix} has unsupported declarative fields")
            continue
        phase = node.get("id")
        if phase not in WORKFLOW_PHASE_IDS or phase in nodes:
            errors.append(f"{prefix}.id is invalid")
            continue
        if node.get("type") not in WORKFLOW_PHASE_TYPES or node.get("type") != phase:
            errors.append(f"{prefix}.type must match its known phase id")
        if node.get("applicability") not in WORKFLOW_APPLICABILITY:
            errors.append(f"{prefix}.applicability is invalid")
        if node.get("assignment_group") not in WORKFLOW_ASSIGNMENT_GROUPS:
            errors.append(f"{prefix}.assignment_group is invalid")
        if phase == "understand" and node.get("assignment_group") != "root":
            errors.append(f"{prefix}.assignment_group must keep understand on root")
        if node.get("not_required") not in WORKFLOW_NOT_REQUIRED:
            errors.append(f"{prefix}.not_required is invalid")
        if node.get("not_required") == "atomic_goal" and phase != "decompose":
            errors.append(f"{prefix}.not_required is not allowed for this phase")
        review = node.get("review")
        if not isinstance(review, dict) or set(review) != {"independent", "human_approval", "assignment_group"}:
            errors.append(f"{prefix}.review is invalid")
        elif not isinstance(review.get("independent"), bool) or not isinstance(review.get("human_approval"), bool) or review.get("assignment_group") != "review":
            errors.append(f"{prefix}.review is invalid")
        dependencies, parent_gates = node.get("depends_on"), node.get("parent_gates")
        if not isinstance(dependencies, list) or any(item not in WORKFLOW_PHASE_IDS for item in dependencies) or len(set(dependencies)) != len(dependencies):
            errors.append(f"{prefix}.depends_on is invalid")
        if not isinstance(parent_gates, list) or any(item not in WORKFLOW_PHASE_IDS for item in parent_gates) or len(set(parent_gates)) != len(parent_gates):
            errors.append(f"{prefix}.parent_gates is invalid")
        inputs = node.get("inputs")
        if not isinstance(inputs, list) or not inputs or any(item not in WORKFLOW_INPUT_CATEGORIES for item in inputs) or len(set(inputs)) != len(inputs):
            errors.append(f"{prefix}.inputs is invalid")
        nodes[phase] = node
    if set(nodes) != set(WORKFLOW_PHASE_IDS):
        errors.append("phase_dag must define every shipped phase exactly once")
    for phase, node in nodes.items():
        dependencies = node.get("depends_on", [])
        if phase in dependencies or any(dependency not in nodes for dependency in dependencies):
            errors.append(f"phase_dag dependencies for {phase} are invalid")
    visiting, visited = set(), set()
    def visit(phase: str) -> None:
        if phase in visiting:
            errors.append("phase_dag must be acyclic")
            return
        if phase in visited or phase not in nodes:
            return
        visiting.add(phase)
        for dependency in nodes[phase].get("depends_on", []):
            visit(dependency)
        visiting.remove(phase)
        visited.add(phase)
    for phase in nodes:
        visit(phase)
    return errors


def phase_evidence_graph(phase_dag: Any, *, has_parent: bool) -> dict[str, list[dict[str, Any]]]:
    """Project reviewed policy nodes into the exact graph consumed by #432.

    Applicability is resolved before handing the graph to the generic evaluator.
    In particular, a child consumes its parent's decomposition as a parent gate
    instead of receiving an impossible local decomposition dependency. The
    orchestration layer supplies child-completion evidence to parent publication.
    """
    errors = _workflow_phase_dag_errors(phase_dag)
    if errors:
        raise ValueError("Invalid workflow phase DAG: " + "; ".join(errors))
    included = {
        node["id"] for node in phase_dag["phases"]
        if node["applicability"] == "always"
        or (node["applicability"] == "child_only" and has_parent)
        or (node["applicability"] == "parent_only" and not has_parent)
    }
    result = []
    for node in phase_dag["phases"]:
        phase = node["id"]
        if phase not in included:
            continue
        dependencies = [dependency for dependency in node["depends_on"] if dependency in included]
        parent_phases = {item["id"] for item in phase_dag["phases"] if item["applicability"] != "child_only"}
        parent_gates = [gate for gate in node["parent_gates"] if gate in parent_phases] if has_parent else []
        if phase == "publish" and not has_parent:
            dependencies = ["plan"]
        result.append({"id": phase, "depends_on": dependencies, "parent_gates": parent_gates})
    return {"phases": result}


def _routing_settings_errors(settings: Any) -> list[str]:
    if not isinstance(settings, dict) or set(settings) != POLICY_CONFIGURATION_KEYS["model_routing"]:
        return ["configuration must contain the declarative routing contract"]
    errors = []
    inventory = settings.get("model_inventory")
    inventory_fields = {"reviewed_pairs"}
    if not isinstance(inventory, dict) or set(inventory) != inventory_fields:
        errors.append("configuration.model_inventory is invalid")
    else:
        pairs = inventory.get("reviewed_pairs")
        seen_pairs = set()
        if not isinstance(pairs, list):
            errors.append("configuration.model_inventory.reviewed_pairs is invalid")
        else:
            for item in pairs:
                if not isinstance(item, dict) or set(item) != {"model", "effort", "tier", "cost"}:
                    errors.append("configuration.model_inventory.reviewed_pairs is invalid")
                    continue
                pair = (item.get("model"), item.get("effort"))
                if (not all(_policy_identifier(part) for part in pair) or item.get("tier") not in ROUTING_TIER_IDS
                        or not isinstance(item.get("cost"), int) or isinstance(item.get("cost"), bool) or item["cost"] < 0
                        or pair in seen_pairs):
                    errors.append("configuration.model_inventory.reviewed_pairs is invalid")
                seen_pairs.add(pair)
    tiers = settings.get("tiers")
    if not isinstance(tiers, list) or len(tiers) != len(ROUTING_TIER_IDS):
        errors.append("configuration.tiers must define every shipped tier")
    else:
        expected_ranks = set(range(1, len(ROUTING_TIER_IDS) + 1))
        actual_ids = [item.get("id") for item in tiers if isinstance(item, dict)]
        ranks = [item.get("rank") for item in tiers if isinstance(item, dict)]
        if any(not isinstance(item, dict) or set(item) != {"id", "rank"} for item in tiers) or set(actual_ids) != set(ROUTING_TIER_IDS) or set(ranks) != expected_ranks:
            errors.append("configuration.tiers must define every shipped tier")
    tree = settings.get("assessment_tree")
    if not isinstance(tree, list) or not tree:
        errors.append("configuration.assessment_tree is invalid")
    else:
        catch_all = 0
        for index, rule in enumerate(tree):
            if not isinstance(rule, dict) or set(rule) != {"when", "tier"} or rule.get("tier") not in ROUTING_TIER_IDS:
                errors.append("configuration.assessment_tree is invalid")
                continue
            when = rule.get("when")
            if not isinstance(when, dict) or set(when) - ROUTING_DIMENSIONS:
                errors.append("configuration.assessment_tree is invalid")
                continue
            if not when:
                catch_all += 1
                if index != len(tree) - 1:
                    errors.append("configuration.assessment_tree catch-all must be last")
            for dimension, values in when.items():
                allowed = ROUTING_DIMENSION_VALUES[dimension]
                if not isinstance(values, list) or not values or any(value not in allowed for value in values) or len(set(values)) != len(values):
                    errors.append("configuration.assessment_tree is invalid")
        if catch_all != 1:
            errors.append("configuration.assessment_tree requires one final catch-all")
    return errors


def capability_tier(settings: Any, dimensions: Any) -> dict[str, Any]:
    """Evaluate the reviewed declarative tree without selecting a provider model."""
    errors = _routing_settings_errors(settings)
    if errors:
        raise ValueError("Invalid model-routing policy: " + "; ".join(errors))
    if not isinstance(dimensions, dict) or set(dimensions) - ROUTING_DIMENSIONS:
        raise ValueError("Routing dimensions are invalid")
    for key, value in dimensions.items():
        if value not in ROUTING_DIMENSION_VALUES[key]:
            raise ValueError(f"Routing dimension {key} is invalid")
    for index, rule in enumerate(settings["assessment_tree"]):
        if all(dimensions.get(key) in values for key, values in rule["when"].items()):
            return {"tier": rule["tier"], "rule_index": index}
    raise ValueError("Reviewed routing tree has no matching tier")  # pragma: no cover - validated catch-all


def reviewed_model_effort(settings: Any, tier: Any, available_pairs: Any) -> dict[str, Any]:
    """Pick the least-cost reviewed pair in a tier from the current availability set."""
    errors = _routing_settings_errors(settings)
    if errors:
        raise ValueError("Invalid model-routing policy: " + "; ".join(errors))
    if tier not in ROUTING_TIER_IDS:
        raise ValueError("Routing tier is invalid")
    if not isinstance(available_pairs, list):
        raise ValueError("Available model inventory is invalid")
    available = set()
    for item in available_pairs:
        if not isinstance(item, dict) or set(item) != {"model", "effort"} or not _policy_identifier(item.get("model")) or not _policy_identifier(item.get("effort")):
            raise ValueError("Available model inventory is invalid")
        available.add((item["model"], item["effort"]))
    ranks = {item["id"]: item["rank"] for item in settings["tiers"]}
    candidates = [
        item for item in settings["model_inventory"]["reviewed_pairs"]
        if ranks[item["tier"]] >= ranks[tier] and (item["model"], item["effort"]) in available
    ]
    if not candidates:
        return {"available": False, "tier": tier, "selected": None}
    selected = min(candidates, key=lambda item: (item["cost"], item["model"], item["effort"]))
    return {"available": True, "tier": tier, "selected": {"model": selected["model"], "effort": selected["effort"]}}


def reviewed_phase_assignment(
    settings: Any, dimensions: Any, available_pairs: Any, root_pair: Any, *, requires_human: bool = False,
) -> dict[str, Any]:
    """Derive a non-discretionary phase assignment from reviewed routing policy.

    The caller supplies observed runtime facts, never a capability score.  This
    function evaluates the reviewed tree and emits the directive which the
    workflow CLI will place in its actionable next-step response.
    """
    tier_decision = capability_tier(settings, dimensions)
    if not isinstance(requires_human, bool):
        raise ValueError("Human-interaction requirement must be a boolean")
    if not isinstance(root_pair, dict) or set(root_pair) != {"model", "effort"} or not all(
        _policy_identifier(root_pair.get(field)) for field in ("model", "effort")
    ):
        raise ValueError("Root model inventory is invalid")
    # This also validates the complete runtime inventory shape.
    reviewed_model_effort(settings, tier_decision["tier"], available_pairs)
    available = {(item["model"], item["effort"]) for item in available_pairs}
    root = (root_pair["model"], root_pair["effort"])
    reviewed = settings["model_inventory"]["reviewed_pairs"]
    root_entry = next((item for item in reviewed if (item["model"], item["effort"]) == root), None)
    if root_entry is None or root not in available:
        return {
            "status": "blocked", "tier": tier_decision["tier"], "rule_index": tier_decision["rule_index"],
            "reason": "root_model_effort_unreviewed_or_unavailable",
            "next_step": {"action": "resolve_blocker", "instruction": "Record or restore the current root model-plus-effort pair, then retry routing."},
        }
    ranks = {item["id"]: item["rank"] for item in settings["tiers"]}
    requested_rank, root_rank = ranks[tier_decision["tier"]], ranks[root_entry["tier"]]
    if requires_human:
        if requested_rank > root_rank:
            return {
                "status": "blocked", "tier": tier_decision["tier"], "rule_index": tier_decision["rule_index"],
                "reason": "human_interaction_exceeds_root_capability",
                "next_step": {"action": "resolve_blocker", "instruction": "Human interaction must stay on the root agent, whose reviewed capability is insufficient for this phase."},
            }
        return {
            "status": "ready", "tier": tier_decision["tier"], "rule_index": tier_decision["rule_index"],
            "mode": "direct_root", "selected": None,
            "next_step": {"action": "continue_root", "instruction": "Perform this human-interaction phase on the root agent."},
        }
    if requested_rank > root_rank:
        return {
            "status": "blocked", "tier": tier_decision["tier"], "rule_index": tier_decision["rule_index"],
            "reason": "above_root_session_override_required",
            "next_step": {"action": "resolve_blocker", "instruction": "This phase exceeds root capability; obtain the recorded session override, then retry routing."},
        }
    candidates = [
        item for item in reviewed
        if (item["model"], item["effort"]) in available
        and requested_rank <= ranks[item["tier"]] <= root_rank
    ]
    if not candidates:
        return {
            "status": "blocked", "tier": tier_decision["tier"], "rule_index": tier_decision["rule_index"],
            "reason": "reviewed_worker_model_effort_unavailable",
            "next_step": {"action": "resolve_blocker", "instruction": "Make a reviewed model-plus-effort pair at or below root capability available, then retry routing."},
        }
    selected = min(candidates, key=lambda item: (item["cost"], item["model"], item["effort"]))
    assignment = {"model": selected["model"], "effort": selected["effort"]}
    return {
        "status": "ready", "tier": tier_decision["tier"], "rule_index": tier_decision["rule_index"],
        "mode": "delegated", "selected": assignment,
        "next_step": {"action": "delegate", "instruction": f"Delegate this phase using model {assignment['model']} with effort {assignment['effort']}."},
    }


def model_inventory_freshness(reviewed_pairs: Any, observed: Any) -> dict[str, Any]:
    """Only a complete observation of a new model-effort pair stales policy."""
    def pairs(value: Any, *, reviewed: bool) -> set[tuple[str, str]]:
        if not isinstance(value, list):
            raise ValueError("Model inventory pairs must be a list")
        result = set()
        for item in value:
            fields = {"model", "effort", "tier", "cost"} if reviewed else {"model", "effort"}
            if not isinstance(item, dict) or set(item) != fields or not _policy_identifier(item.get("model")) or not _policy_identifier(item.get("effort")):
                raise ValueError("Model inventory pair is invalid")
            if reviewed and (item.get("tier") not in ROUTING_TIER_IDS or not isinstance(item.get("cost"), int) or isinstance(item.get("cost"), bool) or item["cost"] < 0):
                raise ValueError("Reviewed model inventory pair is invalid")
            pair = (item["model"], item["effort"])
            if pair in result:
                raise ValueError("Model inventory pairs must be unique")
            result.add(pair)
        return result
    reviewed = pairs(reviewed_pairs, reviewed=True)
    if not isinstance(observed, dict) or set(observed) != {"status", "pairs"} or observed.get("status") not in {"complete", "unavailable", "partial"}:
        raise ValueError("Observed model inventory is invalid")
    current = pairs(observed.get("pairs"), reviewed=False)
    if observed["status"] != "complete":
        return {"stale": False, "reason": "inventory_not_complete", "added": [], "availability": observed["status"]}
    added = sorted(
        ({"model": model, "effort": effort} for model, effort in current - reviewed),
        key=lambda item: (item["model"], item["effort"]),
    )
    return {"stale": bool(added), "reason": "new_model_effort" if added else "current", "added": added, "availability": "complete"}


def phase_policy_freshness(recorded_policy_digest: Any, effective_policy_digest: Any, *, terminal: bool) -> dict[str, Any]:
    """Derive universal open-goal invalidation without touching closed goal state."""
    if terminal:
        return {"stale": False, "reason": "terminal_goal", "rewrite_required": False}
    if not _digest_text(recorded_policy_digest) or not _digest_text(effective_policy_digest):
        raise ValueError("Policy digests must be SHA-256 digests")
    changed = recorded_policy_digest != effective_policy_digest
    return {"stale": changed, "reason": "policy_digest_changed" if changed else "current", "rewrite_required": False}


def project_digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def classify_release_evidence(
    *, visibility: str | None, github_releases: list[dict[str, Any]] | None,
    owner_declaration: str | None = None,
) -> dict[str, Any]:
    """Classify release evidence without inferring a destructive migration choice."""
    releases = github_releases if isinstance(github_releases, list) else None
    published = [item for item in (releases or []) if isinstance(item, dict)
                 and item.get("draft") is not True
                 and (item.get("published_at") or item.get("publishedAt"))]
    if visibility == "PUBLIC" and published:
        return {
            "status": "released", "released": True, "ambiguous": False,
            "evidence": "github_public_release", "release_count": len(published),
            "first_release_transition": owner_declaration == "never_released",
        }
    if owner_declaration == "never_released" and visibility == "PUBLIC" and releases == []:
        return {
            "status": "never_released", "released": False, "ambiguous": False,
            "evidence": "explicit_owner_declaration", "release_count": 0,
            "first_release_transition": False,
        }
    reason = "release_history_ambiguous"
    if visibility == "PUBLIC" and releases == []:
        reason = "public_repository_without_github_release"
    elif releases is None:
        reason = "release_history_unavailable"
    return {
        "status": "unknown", "released": None, "ambiguous": True,
        "evidence": "none", "reason": reason,
        "release_count": len(published), "first_release_transition": False,
    }


def migration_boundary(policy: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Evaluate captured contract evidence; eligibility never grants reset authority."""
    blocked = {"action": "block", "scope": "none", "reason": "contract_evidence_required"}
    document = context.get("assessment")
    snapshot = context.get("release_snapshot")
    if not isinstance(document, dict) or type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        return blocked
    if (type(context.get("goal")) is not int or type(document.get("goal")) is not int
            or not _digest_text(context.get("goal_spec"))
            or not text_present(context.get("repository"))
            or any(document.get(key) != context.get(key) for key in ("repository", "goal", "goal_spec"))
            or not text_present(document.get("action"))):
        return blocked
    if (not isinstance(snapshot, dict) or snapshot.get("status") != "complete"
            or not isinstance(snapshot.get("releases"), list) or document.get("release_snapshot") != snapshot):
        return blocked
    seen_releases = set()
    for release in snapshot["releases"]:
        if (not isinstance(release, dict) or type(release.get("id")) is not int
                or not text_present(release.get("tag")) or not text_present(release.get("published_at"))
                or not isinstance(release.get("commit"), str)
                or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", release["commit"])
                or release["id"] in seen_releases):
            return blocked
        seen_releases.add(release["id"])
    contracts = document.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        return blocked
    identifiers = [item.get("id") if isinstance(item, dict) else None for item in contracts]
    if any(not text_present(key) for key in identifiers) or len(set(identifiers)) != len(identifiers):
        return blocked
    selected = context.get("contract_id")
    if selected is not None:
        contracts = [item for item in contracts if item["id"] == selected]
        if not contracts:
            return blocked
    for contract in contracts:
        scope = contract.get("scope")
        if (contract.get("status") not in ("shipped", "unreleased")
                or not text_present(contract.get("boundary"))
                or not isinstance(scope, list) or not scope
                or any(not text_present(item) for item in scope)
                or len(set(scope)) != len(scope)):
            return blocked
        evidence = contract.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            return blocked
        presence_facts = {}
        published_commits = {release["commit"] for release in snapshot["releases"]}
        for item in evidence:
            if (not isinstance(item, dict) or type(item.get("goal")) is not int
                    or any(item.get(key) != document.get(key) for key in ("goal", "goal_spec", "release_snapshot"))
                    or item.get("contract") != contract["id"]
                    or item.get("boundary") != contract["boundary"] or item.get("scope") != scope):
                return blocked
            if item.get("kind") == "owner_attestation":
                if not text_present(item.get("author")) or not text_present(item.get("statement")):
                    return blocked
            elif item.get("kind") == "contract_investigation":
                # Captured agent findings are evidence, not owner approval or an
                # automatic proof of arbitrary prose. Review checks the stated
                # distribution boundary and interpretation of inspected facts.
                if (not text_present(item.get("author")) or not text_present(item.get("rationale"))
                        or not text_present(item.get("distribution_boundary"))
                        or item.get("conclusion") != contract["status"]):
                    return blocked
                observations = item.get("observations")
                if not isinstance(observations, list) or not observations:
                    return blocked
                published = {release["id"]: release["commit"] for release in snapshot["releases"]}
                covered, development_present, distribution_inspected, shipped_present = set(), False, False, False
                for observation in observations:
                    if (not isinstance(observation, dict) or not isinstance(observation.get("commit"), str)
                            or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", observation["commit"])
                            or not text_present(observation.get("path"))
                            or observation["path"].startswith(("/", "\\"))
                            or ".." in observation["path"].replace("\\", "/").split("/")):
                        return blocked
                    if "contract_present" not in observation:
                        if not text_present(observation.get("finding")):
                            return blocked
                        distribution_inspected = True
                        continue
                    if type(observation["contract_present"]) is not bool or "release_id" not in observation:
                        return blocked
                    identity = (observation["commit"], observation["path"])
                    present = observation["contract_present"]
                    if identity in presence_facts and presence_facts[identity] != present:
                        return blocked
                    presence_facts[identity] = present
                    # Immutable identity wins over the author's development
                    # label, including facts split across evidence items.
                    if contract["status"] == "unreleased" and present and observation["commit"] in published_commits:
                        return blocked
                    release_id = observation["release_id"]
                    if release_id is None:
                        development_present |= observation["contract_present"]
                    elif type(release_id) is int and published.get(release_id) == observation["commit"]:
                        covered.add(release_id)
                        shipped_present |= observation["contract_present"]
                    else:
                        return blocked
                if not distribution_inspected or covered != set(published):
                    return blocked
                if contract["status"] == "unreleased" and (not development_present or shipped_present):
                    return blocked
                if contract["status"] == "shipped" and not shipped_present:
                    return blocked
            elif item.get("kind") == "release_reference":
                # A captured release identity can support preservation, never
                # prove a contract was absent or grant replacement authority.
                if contract["status"] != "shipped" or item.get("release") not in snapshot["releases"]:
                    return blocked
            else:
                return blocked
    shipped = any(item["status"] == "shipped" for item in contracts)
    return {"action": "preserve" if shipped else "replace_reset", "scope": "affected_project_owned",
            "reason": "shipped_contract" if shipped else "evidenced_unreleased_contract",
            "contracts": [{"id": item["id"], "action": "preserve" if item["status"] == "shipped" else "replace_reset",
                           "scope": "affected_project_owned"} for item in contracts],
            "authority": "Eligibility only; existing operation authority applies. Excludes unrelated user, external and deployment state."}


def stack_tooling_offer(policy: dict[str, Any], capability: dict[str, Any]) -> dict[str, Any]:
    """Describe an interactive tooling decision without granting installation authority."""
    section = next((item for item in policy.get("sections", [])
                    if isinstance(item, dict) and item.get("id") == "git_review_release"), {})
    settings = section.get("configuration") if isinstance(section.get("configuration"), dict) else {}
    preferred = settings.get("pull_request_mode") == "github_stacked_when_verified_else_chained"
    digest = policy_content_digest({key: capability.get(key) for key in
                                    ("reason", "cli_version", "extension_version", "official_source")})
    declined = settings.get("stacked_tooling_decline") == digest
    reason = capability.get("reason")
    if not preferred:
        action = "not_selected"
    elif capability.get("usable") is True:
        action = "use_native_stacks"
    elif declined:
        action = "keep_reviewed_fallback"
    elif reason == "extension_missing":
        action = "offer_installation"
    elif reason in {"gh_missing", "cli_upgrade_required"}:
        action = "review_cli_install_or_upgrade"
    else:
        action = "review_capability_failure"
    return {
        "preferred": preferred, "action": action, "capability_digest": digest,
        "offer_installation": action == "offer_installation",
        "requires_explicit_approval": action in {"offer_installation", "review_cli_install_or_upgrade"},
        "install_command": ["gh", "extension", "install", "github/gh-stack"]
        if action == "offer_installation" else None,
        "decline_is_current": declined,
    }


def project_path(repo: Path) -> Path:
    return repo / ".zzzops" / "PROJECT.md"


def project_audit_path(repo: Path) -> Path:
    return repo / PROJECT_AUDIT_RELATIVE


def project_policy_path(repo: Path) -> Path:
    return repo / PROJECT_POLICY_RELATIVE


def read_project(repo: Path) -> tuple[Path, str]:
    path = project_path(repo)
    try:
        return path, path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return path, ""
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Cannot read project charter from {path}: {exc}") from exc


def parse_policy_state(text: str) -> dict[str, Any]:
    try:
        state = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid canonical policy JSON: {exc}") from exc
    if not isinstance(state, dict):
        raise ValueError("Canonical policy state must be a JSON object")
    return state


def read_policy_text(repo: Path) -> tuple[Path, str]:
    path = project_policy_path(repo)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return path, ""
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Cannot read canonical policy from {path}: {exc}") from exc
    return path, text


def read_project_state(repo: Path) -> tuple[Path, str, dict[str, Any] | None]:
    path, text = read_policy_text(repo)
    if not text:
        return path, text, None
    return path, text, parse_policy_state(text)


def initialization_base_digest(repo: Path) -> str:
    _project_path, project_text = read_project(repo)
    _policy_path, policy_text = read_policy_text(repo)
    return project_digest(project_text + "\0" + policy_text)


def policy_review_digest(state: dict[str, Any]) -> str:
    reviewable = {key: value for key, value in state.items() if key != "approval"}
    payload = json.dumps(reviewable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return project_digest(payload)


def validate_project_state(state: Any) -> list[str]:
    if not isinstance(state, dict):
        return ["project state must be an object"]
    allowed = {"schema_version", "initialized", "backend", "repository", "revision", "charter", "policy", "history", "bindings", "approval"}
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
                if not isinstance(item, dict) or any(not text_present(item.get(field)) for field in ("id", "source", "finding")):
                    errors.append(f"evidence[{index}] requires id, source, and finding")
                elif item["id"] in evidence_ids:
                    errors.append(f"evidence[{index}].id must be unique")
                else:
                    evidence_ids.add(item["id"])
    common_fields = {
        "id", "title", "required", "applicable", "instructions", "rationale", "source_ids",
        "confidence", "default_origin", "default_disposition", "configuration", "exceptions",
        "unresolved", "review",
    }
    optional_fields = {"default_id", "default_resolution", "default_provenance", "migration_lineage"}
    seen = set()
    for index, section in enumerate(sections):
        prefix = f"sections[{index}]"
        if not isinstance(section, dict):
            errors.append(f"{prefix} must be an object")
            continue
        unsupported = sorted(set(section) - common_fields - optional_fields)
        if unsupported:
            errors.append(f"{prefix} has unsupported fields: {', '.join(unsupported)}")
        section_id = section.get("id")
        if section_id not in POLICY_SECTION_IDS or section_id in seen:
            errors.append(f"{prefix}.id must be unique and from the current taxonomy")
        else:
            seen.add(section_id)
        if section.get("default_id") is not None and section.get("default_id") != f"zzzops.policy.{section_id}":
            errors.append(f"{prefix}.default_id is inconsistent")
        for field in ("title", "instructions", "rationale", "confidence", "default_origin", "default_disposition"):
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
        configuration = section.get("configuration")
        if not isinstance(configuration, dict):
            errors.append(f"{prefix}.configuration must be an object")
        elif section_id in POLICY_CONFIGURATION_KEYS:
            allowed = POLICY_CONFIGURATION_KEYS[section_id]
            required = allowed - ({"portfolio_order"} if section_id == "autonomy_approval_parallelism" else set())
            if section_id == "git_review_release":
                allowed = allowed | {"stacked_tooling_decline"}
            missing = sorted(required - set(configuration))
            unknown = sorted(set(configuration) - allowed)
            if missing or unknown:
                errors.append(
                    f"{prefix}.{section_id}.configuration has unsupported configuration fields"
                    + (f"; missing: {', '.join(missing)}" if missing else "")
                    + (f"; unknown: {', '.join(unknown)}" if unknown else "")
                )
            elif section_id == "backend":
                if configuration.get("authority") not in BACKENDS:
                    errors.append(f"{prefix}.backend.configuration.authority is invalid")
                for field in ("repository_identity", "capability_evidence"):
                    if not text_present(configuration.get(field)):
                        errors.append(f"{prefix}.backend.configuration.{field} is required")
            elif section_id == "git_review_release":
                if configuration.get("review_pending_dependency") not in GIT_REVIEW_SETTING_VALUES["review_pending_dependency"]:
                    errors.append(f"{prefix}.git_review_release.configuration.review_pending_dependency is invalid")
                if configuration.get("pull_request_mode") not in GIT_REVIEW_SETTING_VALUES["pull_request_mode"]:
                    errors.append(f"{prefix}.git_review_release.configuration.pull_request_mode is invalid")
                if "stacked_tooling_decline" in configuration and not _digest_text(configuration["stacked_tooling_decline"]):
                    errors.append(f"{prefix}.git_review_release.configuration.stacked_tooling_decline is invalid")
            elif section_id == "verification_testing":
                if configuration.get("required_ci") not in REQUIRED_CI_MODES:
                    errors.append(f"{prefix}.verification_testing.configuration.required_ci is invalid")
            elif section_id == "engineering_rigor":
                if configuration.get("level") not in ENGINEERING_RIGOR_LEVELS:
                    errors.append(f"{prefix}.engineering_rigor.configuration.level is invalid")
                minimums = configuration.get("minimums")
                if not isinstance(minimums, dict):
                    errors.append(f"{prefix}.engineering_rigor.configuration.minimums must be an object")
                else:
                    for category, level in minimums.items():
                        if not _policy_identifier(category) or level not in ENGINEERING_RIGOR_LEVELS:
                            errors.append(f"{prefix}.engineering_rigor.configuration.minimums is invalid")
                overrides = configuration.get("overrides")
                if not isinstance(overrides, dict) or set(overrides) != {"per_goal"}:
                    errors.append(f"{prefix}.engineering_rigor.configuration.overrides is invalid")
                elif not isinstance(overrides.get("per_goal"), bool):
                    errors.append(f"{prefix}.engineering_rigor.configuration.overrides is invalid")
            elif section_id == "model_routing":
                errors.extend(f"{prefix}.model_routing.{error}" for error in _routing_settings_errors(configuration))
            elif section_id == "workflow_adherence":
                errors.extend(f"{prefix}.workflow_adherence.{error}" for error in _workflow_phase_dag_errors(configuration.get("phase_dag")))
            elif section_id == "autonomy_approval_parallelism":
                maximum = configuration.get("max_workers")
                if not isinstance(maximum, int) or isinstance(maximum, bool) or not 1 <= maximum <= 20:
                    errors.append(f"{prefix}.autonomy_approval_parallelism.configuration.max_workers must be an integer from 1 to 20")
                reporting = configuration.get("execution_reports")
                if not isinstance(reporting, dict) or set(reporting) != {"enabled"} or not isinstance(reporting.get("enabled"), bool):
                    errors.append(f"{prefix}.autonomy_approval_parallelism.configuration.execution_reports is invalid")
                try:
                    normalize_resource_policy(configuration.get("resource_reservations"))
                except ValueError as exc:
                    errors.append(f"{prefix}.autonomy_approval_parallelism.configuration.{exc}")
                refill = configuration.get("refill")
                portfolio_order = configuration.get("portfolio_order")
                if portfolio_order is not None:
                    if not isinstance(portfolio_order, dict) or set(portfolio_order) != {"ordered_goal_keys", "rationale"}:
                        errors.append(f"{prefix}.autonomy_approval_parallelism.configuration.portfolio_order is invalid")
                    elif (
                        not isinstance(portfolio_order["ordered_goal_keys"], list)
                        or any(not isinstance(key, int) or isinstance(key, bool) or key < 1 for key in portfolio_order["ordered_goal_keys"])
                        or len(set(portfolio_order["ordered_goal_keys"])) != len(portfolio_order["ordered_goal_keys"])
                        or not text_present(portfolio_order["rationale"])
                    ):
                        errors.append(f"{prefix}.autonomy_approval_parallelism.configuration.portfolio_order is invalid")
                if not isinstance(refill, dict) or set(refill) != {"enabled", "allowed_categories", "max_suggestions"}:
                    errors.append(f"{prefix}.autonomy_approval_parallelism.configuration.refill is invalid")
                else:
                    categories = refill.get("allowed_categories")
                    if (
                        not isinstance(categories, list) or not categories
                        or any(not isinstance(category, str) for category in categories)
                        or len(categories) != len(set(categories))
                        or any(category not in WORK_SUGGESTION_CATEGORIES for category in categories)
                    ):
                        errors.append(f"{prefix}.autonomy_approval_parallelism.configuration.refill.allowed_categories is invalid")
                    if not isinstance(refill.get("enabled"), bool):
                        errors.append(f"{prefix}.autonomy_approval_parallelism.configuration.refill.enabled must be boolean")
                    maximum = refill.get("max_suggestions")
                    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
                        errors.append(f"{prefix}.autonomy_approval_parallelism.configuration.refill.max_suggestions must be a positive integer")
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
        if section_id == "security_privacy_compliance" and (
            section.get("required") is not True or section.get("applicable") is not True
        ):
            errors.append(f"{prefix}.security_privacy_compliance must be required and applicable")
        errors.extend(validate_default_provenance(section, prefix))
        if not require_pending:
            errors.extend(f"{prefix}.{error}" for error in _lineage_errors(section, policy.get("evidence", [])))
        elif "migration_lineage" in section:
            errors.append(f"{prefix}.migration_lineage cannot be supplied by an agent-generated plan")
    missing = sorted(set(POLICY_SECTION_IDS) - seen)
    if missing:
        errors.append("missing sections: " + ", ".join(missing))
    for section_id, paths in missing_policy_settings(policy).items():
        errors.append(f"section {section_id} is missing operational policy configuration: {', '.join(paths)}")
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


def reviewed_project_state(repo: Path) -> dict[str, Any]:
    _path, _policy_text, project = read_project_state(repo)
    errors = validate_project_state(project) if project is not None else ["canonical policy is missing"]
    errors.extend(validate_project_artifacts(repo, project))
    if errors or project.get("initialized") is not True or policy_blockers(project.get("policy")):
        raise ValueError("Project policy is not ready")
    return project


def cell(value: str) -> str:
    return " ".join(str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ").split())


def _plain_policy_choice(section: dict[str, Any], limit: int = 140) -> str:
    decision = " ".join(str(section.get("instructions") or "Not configured").split())
    if decision and " " not in decision:
        decision = decision.replace("_", " ").capitalize()
        if decision == "Github issues":
            decision = "GitHub Issues"
    if len(decision) <= limit:
        return decision
    boundary = decision.rfind(" ", 0, limit - 20)
    boundary = boundary if boundary >= 50 else limit - 20
    return decision[:boundary].rstrip(" ,;:") + "… (details in audit)"


def _plain_policy_configuration(section: dict[str, Any], limit: int = 160) -> str:
    """Render a bounded review summary without hiding typed runtime choices."""
    configuration = section.get("configuration")
    if not isinstance(configuration, dict) or not configuration:
        return "none"
    parts: list[str] = []

    def visit(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key in sorted(value):
                visit(f"{prefix}.{key}" if prefix else key, value[key])
        elif isinstance(value, list):
            if value and all(isinstance(item, str) for item in value) and len(",".join(value)) <= 48:
                parts.append(f"{prefix}={','.join(value)}")
            else:
                parts.append(f"{prefix}={len(value)} items")
        else:
            parts.append(f"{prefix}={json.dumps(value, ensure_ascii=False)}")

    visit("", configuration)
    summary = "; ".join(parts)
    return summary if len(summary) <= limit else summary[: limit - 1].rstrip() + "…"


def policy_review_rows(
    policy: dict[str, Any], catalog: dict[str, dict[str, Any]] | None = None,
    stale_reasons: dict[str, str] | None = None, *, proposal: bool = False,
) -> list[dict[str, str]]:
    """Build the complete plain-language policy-review view without changing audit truth."""
    comparisons = {
        item["section_id"]: item
        for item in compare_policy_defaults(policy, catalog)
        if item.get("section_id") in POLICY_SECTION_IDS
    }
    sections = {
        section.get("id"): section for section in policy.get("sections", [])
        if isinstance(section, dict) and section.get("id") in POLICY_SECTION_IDS
    }
    missing_settings = missing_policy_settings(policy, catalog)
    derived_stale_reasons = {
        section_id: "reviewed policy is missing " + ", ".join(paths)
        for section_id, paths in missing_settings.items()
    }
    derived_stale_reasons.update(stale_reasons or {})
    stale_reasons = derived_stale_reasons
    rows = []
    relationship = {
        "current": "Yes — current ZzzOps default",
        "customized": "No — customized for this project",
        "declined": "No — newer ZzzOps default was declined",
        "unknown_origin": "Unknown — origin was not recorded",
        "unknown_default": "Unknown — recorded default is unavailable",
        "update_available": "Yes — an older ZzzOps default",
    }
    for section_id in POLICY_SECTION_IDS:
        section = sections.get(section_id)
        if section is None:
            rows.append({
                "policy": POLICY_SECTION_TITLES[section_id], "current_choice": "Not configured",
                "configuration": "Not configured",
                "default_relationship": "Unknown — policy is missing",
                "stale": "Yes — this policy is missing", "approved": "Not yet",
                "applies": "Unknown", "needs_attention": "Add and review this policy",
            })
            continue
        comparison = comparisons.get(section_id, {"status": "unknown_origin"})
        status = comparison["status"]
        if proposal and section.get("default_id"):
            default_relationship = {
                "accepted": "Proposed ZzzOps default",
                "changed": "Proposed project customization",
                "rejected": "Proposed rejection of the ZzzOps default",
            }.get(section.get("default_disposition"), "Proposed choice — origin needs review")
            stale = "No — new proposal"
        else:
            default_relationship = relationship.get(status, "Unknown — review needed")
            stale = {
                "current": "No",
                "customized": "No",
                "declined": "No — latest default was reviewed and declined",
                "unknown_origin": "Unknown — earlier policy did not record its origin",
                "unknown_default": "Yes — recorded default is no longer available",
                "update_available": "Yes — ZzzOps changed its recommended choice",
            }.get(status, "Unknown — review needed")
        if section_id in stale_reasons:
            stale = "Yes — " + " ".join(stale_reasons[section_id].split())
        approved = section.get("review", {}).get("approved") is True
        unresolved = section.get("unresolved") or []
        if section_id in stale_reasons:
            attention = "Review the affected choice"
        elif status == "update_available":
            attention = "Review the changed ZzzOps recommendation"
        elif status in {"unknown_origin", "unknown_default"} and not proposal:
            attention = "Confirm whether to keep this choice"
        elif unresolved:
            attention = "Resolve: " + str(unresolved[0])
        elif not approved:
            attention = "Approve this policy"
        else:
            attention = "—"
        rows.append({
            "policy": POLICY_SECTION_TITLES[section_id],
            "current_choice": _plain_policy_choice(section),
            "configuration": _plain_policy_configuration(section),
            "default_relationship": default_relationship, "stale": stale,
            "approved": "✅ Yes" if approved else "Not yet",
            "applies": "Yes" if section.get("applicable") is True else "No",
            "needs_attention": attention,
        })
    return rows


def render_policy_review_table(
    policy: dict[str, Any], catalog: dict[str, dict[str, Any]] | None = None,
    stale_reasons: dict[str, str] | None = None, *, proposal: bool = False,
) -> str:
    rows = policy_review_rows(policy, catalog, stale_reasons, proposal=proposal)
    header = (
        "| Policy | Agent instructions | CLI configuration | ZzzOps default? | Stale? | Approved | Applies? | Needs attention |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    body = "\n".join(
        "| {policy} | {current_choice} | {configuration} | {default_relationship} | {stale} | {approved} | {applies} | {needs_attention} |".format(
            **{key: cell(value) for key, value in row.items()}
        )
        for row in rows
    )
    return header + "\n" + body


def render_project(state: dict[str, Any], *, _legacy: bool = False, _legacy_provenance: bool = True) -> str:
    charter = state["charter"]
    status = "complete" if state["initialized"] else "incomplete — policy review required"
    reviewed = (state.get("approval") or {}).get("date", "not yet")
    kpis = "\n".join(f"| {cell(k['name'])} | {cell(k['why'])} | {cell(k['baseline'])} | {cell(k['target'])} | {cell(k['evidence'])} | {cell(k['cadence'])} |" for k in charter["kpis"])
    bullets = lambda values: "\n".join(f"- {value}" for value in values)
    checks = "\n".join(f"- [x] {value}" for value in charter["acceptance_criteria"])
    policy = "\n".join(
        f"- `[policy:{section['id']}]` **{section['title']}** — Agent instructions: "
        f"{section['instructions']} CLI configuration: {_plain_policy_configuration(section, limit=100)} "
        f"({default_provenance_label(section)})"
        for section in state["policy"]["sections"]
    ) if not _legacy else "\n".join(
        f"- `[policy:{section['id']}]` **{section['title']}**: {section['decision']}"
        + (f" ({default_provenance_label(section)})" if _legacy_provenance else "")
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


def render_policy_sections(policy: dict[str, Any], *, _legacy: bool = False) -> str:
    rendered = []
    evidence = {item["id"]: f"{item['source']} — {item['finding']}" for item in policy.get("evidence", []) if isinstance(item, dict) and text_present(item.get("id"))}
    for section in policy["sections"]:
        approved = section["review"]["approved"] is True
        applicable = "applicable" if section["applicable"] else "not applicable"
        settings = json.dumps(section["settings" if _legacy else "configuration"], ensure_ascii=False, sort_keys=True)
        instruction_label = "Decision" if _legacy else "Instructions"
        configuration_label = "Settings" if _legacy else "Configuration"
        instructions = section["decision" if _legacy else "instructions"]
        sources = "; ".join(
            "{}: {}".format(source_id, evidence.get(source_id, "missing citation"))
            for source_id in section["source_ids"]
        )
        rendered.append(
            f"- [{'x' if approved else ' '}] `[policy:{section['id']}]` **{section['title']}** ({applicable})\n"
            f"  - {instruction_label}: {instructions}\n"
            f"  - Rationale: {section['rationale']}\n"
            f"  - Sources: {sources}\n"
            f"  - Confidence/default: {section['confidence']}; {section['default_origin']} → {section['default_disposition']}\n"
            f"  - Provenance: {default_provenance_label(section)}\n"
            f"  - {configuration_label}: `{settings}`\n"
            f"  - Exceptions: {', '.join(section['exceptions']) or 'none'}\n"
            f"  - Unresolved: {', '.join(section['unresolved']) or 'none'}"
        )
    return "\n".join(rendered)


def render_project_audit(state: dict[str, Any], *, _legacy: bool = False) -> str:
    status = "complete" if state["initialized"] else "pending explicit review"
    reviewer = (state.get("approval") or {}).get("reviewer", "not yet approved")
    history = "\n".join(f"| {cell(entry['date'])} | {cell(entry['actor'])} | {cell(entry['change'])} | {cell(entry['reason'])} |" for entry in state["history"])
    return (
        "# ZzzOps project policy audit\n\n"
        f"Status: {status}. Reviewer: {reviewer}. Revision: {state['revision']}.\n\n"
        "## Evidence and decisions\n\n"
        f"{render_policy_sections(state['policy'], _legacy=_legacy)}\n\n"
        "## Review record\n\n"
        "| Date | Actor/run | Change | Reason/evidence |\n"
        "| --- | --- | --- | --- |\n"
        f"{history}\n\n"
        "The machine-readable authority is [POLICY.json](POLICY.json); this file is its human audit view.\n"
    )
