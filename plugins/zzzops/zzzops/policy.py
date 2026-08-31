"""Canonical project-policy state, validation, and rendering helpers.

This module deliberately has no dependency on the ZzzOps CLI or provider layer so
project-policy behavior can be exercised and reused without importing the control
entry point.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable


PROJECT_SCHEMA_VERSION = 1
POLICY_SCHEMA_VERSION = 1
POLICY_DEFAULT_SCHEMA_VERSION = 1
PROJECT_POLICY_RELATIVE = ".zzzops/POLICY.json"
PROJECT_AUDIT_RELATIVE = ".zzzops/PROJECT_AUDIT.md"
BACKENDS = {"github_issues"}
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
    "engineering_rigor",
    "workflow_adherence",
    "automated_design",
    "autonomy_approval_parallelism",
)
POLICY_SECTION_TITLES = {
    "backend": "Goal storage",
    "git_review_release": "Git, review, and release",
    "execution_continuation": "Work continuation",
    "verification_testing": "Verification and testing",
    "code_quality": "Code quality and refactoring",
    "dependencies_tooling": "Dependencies and tooling",
    "security_privacy_compliance": "Security, privacy, and compliance",
    "documentation_style": "Documentation and communication",
    "deployment_resources": "Deployment and resources",
    "engineering_rigor": "Engineering rigor",
    "workflow_adherence": "ZzzOps workflow use",
    "automated_design": "Automated design",
    "autonomy_approval_parallelism": "Autonomy, approvals, and parallel work",
}

AUTOMATED_DESIGN_SETTINGS = {
    "scope": "bounded_commitment_in_scope_implementation",
    "commitment": {
        "low": "replace_verify_and_clean_within_one_goal_before_fanout",
        "high": "compare_evidence_cost_signal_or_explicit_current_design_review",
        "structural_cost_signals": [
            "affected_goal_units", "started_descendant_branches", "started_descendant_prs",
            "durable_data", "public_or_integration_contracts", "external_state",
            "compatibility_paths", "verification_breadth", "clean_removal_path",
        ],
    },
    "selection_basis": ["project_objectives", "kpi_evidence", "constraints", "precedence"],
    "decision_record": ["alternatives", "rationale", "assumptions", "falsifiable_validation_signal"],
    "privacy_security": "unambiguously_risk_reducing_without_material_behavior_change",
    "hard_stops": [
        "product_scope", "incompatible_public_contract", "destructive_migration", "external_spending",
        "deployment", "external_write", "human_review", "safety_authority", "higher_authority",
    ],
    "insufficient_evidence": "durable_design_blocker",
}

GIT_REVIEW_SETTING_VALUES = {
    "review_pending_dependency": {"wait_for_completed_dependencies", "stack_from_reviewed_checkpoint"},
    "review_gate": {"human_after_checks", "human_at_exhaustion"},
    "conversational_approval": {"allowed_otherwise", "never_for_goal_progress"},
    "pull_request_mode": {"github_stacked_when_verified_else_chained", "chained_prs"},
    "stacked_capability": {"official_gh_stack_extension_with_provider_membership_verification"},
    "stacked_tool_installation": {"explicit_user_approval"},
    "stacked_unavailable_fallback": {"chained_prs"},
}
DEPENDENCY_IMPLEMENTATION_GATES = {"dependencies_done", "stack_from_reviewed_checkpoint"}
WORK_SUGGESTION_CATEGORIES = frozenset({
    "documentation", "tests", "code_quality_non_behavioral", "agent_observability",
})

WORKFLOW_ADHERENCE_SETTINGS = {
    "levels": {
        "optional": "direct_agent_work_allowed",
        "tracked": "durable_goal_required_for_substantial_agent_work",
        "managed": "zzzops_workflow_required_for_repository_changes",
    },
    "exemptions": ["read_only_investigation", "zzzops_administration"],
    "scoped_exception": "explicit_scoped_user_authority",
    "agents_projection": "review_workflow_reconciliation",
}

ENGINEERING_RIGOR_LEVELS = ("vibe", "structured", "agentic")
ENGINEERING_RIGOR_INTERVIEW_DEPTH = {
    "vibe": "light", "structured": "standard", "agentic": "thorough",
}

POLICY_DEFAULT_CONTENT_FIELDS = ("decision", "settings")
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
    }
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
        if not isinstance(provenance, dict) or provenance.get("status") == "unknown":
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


def validate_default_provenance(section: dict[str, Any], prefix: str) -> list[str]:
    provenance = section.get("default_provenance")
    if provenance is None:
        return []  # Legacy reviewed policy: never infer provenance from value equality.
    if not isinstance(provenance, dict):
        return [f"{prefix}.default_provenance must be an object"]
    status = provenance.get("status")
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
    if provenance.get("schema_version") != POLICY_DEFAULT_SCHEMA_VERSION:
        errors.append(f"{prefix}.default_provenance.schema_version must be {POLICY_DEFAULT_SCHEMA_VERSION}")
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
        if not isinstance(snapshot, dict) or set(snapshot) != set(POLICY_DEFAULT_CONTENT_FIELDS):
            errors.append(f"{prefix}.default_provenance.snapshot must contain the complete canonical default")
        elif policy_content_digest(snapshot) != provenance.get("digest"):
            errors.append(f"{prefix}.default_provenance.digest does not match snapshot")
        elif policy_default_content(section) != snapshot:
            errors.append(f"{prefix}.default_provenance snapshot differs from effective policy")
        if "declined_digest" in provenance and not _digest_text(provenance["declined_digest"]):
            errors.append(f"{prefix}.default_provenance.declined_digest is invalid")
    return errors


def default_provenance_label(section: dict[str, Any]) -> str:
    status = (section.get("default_provenance") or {}).get("status")
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


def _missing_setting_paths(current: Any, expected: Any, prefix: str = "settings") -> list[str]:
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
        expected = by_section[section_id].get("content", {}).get("settings", {})
        missing = _missing_setting_paths(section.get("settings"), expected)
        if missing:
            result[section_id] = missing
    return result


def project_digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        if section.get("default_id") is not None and section.get("default_id") != f"zzzops.policy.{section_id}":
            errors.append(f"{prefix}.default_id is inconsistent")
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
        elif section_id == "git_review_release":
            settings = section["settings"]
            for field, allowed in GIT_REVIEW_SETTING_VALUES.items():
                if settings.get(field) not in allowed:
                    errors.append(f"{prefix}.git_review_release.settings.{field} is invalid")
            if settings.get("review_gate") == "human_at_exhaustion" and (
                settings.get("review_pending_dependency") != "stack_from_reviewed_checkpoint"
                or settings.get("conversational_approval") != "never_for_goal_progress"
            ):
                errors.append(
                    f"{prefix}.git_review_release exhaustion review requires checkpoint stacking "
                    "and no conversational goal approval"
                )
        elif section_id == "engineering_rigor":
            settings = section["settings"]
            if section.get("decision") not in ENGINEERING_RIGOR_LEVELS:
                errors.append(f"{prefix}.engineering_rigor.decision must be vibe, structured, or agentic")
            if set(settings) != {"escalation", "minimums", "overrides", "requirements_interview"}:
                errors.append(f"{prefix}.engineering_rigor.settings must contain the bounded rigor contract")
            escalation = settings.get("escalation")
            if not isinstance(escalation, dict) or set(escalation) != {
                "enabled", "allow_automatic_escalation", "allow_automatic_deescalation",
            }:
                errors.append(f"{prefix}.engineering_rigor.escalation is invalid")
            else:
                for field in ("enabled", "allow_automatic_escalation"):
                    if not isinstance(escalation.get(field), bool):
                        errors.append(f"{prefix}.engineering_rigor.escalation.{field} must be boolean")
                if escalation.get("allow_automatic_escalation") is True and escalation.get("enabled") is not True:
                    errors.append(f"{prefix}.engineering_rigor.escalation enabled conflicts with automatic escalation")
                if escalation.get("allow_automatic_deescalation") is not False:
                    errors.append(f"{prefix}.engineering_rigor.allow_automatic_deescalation must remain false")
            minimums = settings.get("minimums")
            if not isinstance(minimums, dict):
                errors.append(f"{prefix}.engineering_rigor.minimums must be an object")
            else:
                for category, level in minimums.items():
                    if (
                        not isinstance(category, str) or not text_present(category)
                        or category.casefold() != category or not category.replace("_", "").isalnum()
                    ):
                        errors.append(f"{prefix}.engineering_rigor.minimums category is invalid")
                    if level not in ENGINEERING_RIGOR_LEVELS:
                        errors.append(f"{prefix}.engineering_rigor.minimums {category!r} level is invalid")
            overrides = settings.get("overrides")
            if not isinstance(overrides, dict) or set(overrides) != {
                "per_goal", "raising", "lowering", "may_undercut_risk_minimum",
            }:
                errors.append(f"{prefix}.engineering_rigor.overrides is invalid")
            else:
                if not isinstance(overrides.get("per_goal"), bool):
                    errors.append(f"{prefix}.engineering_rigor.overrides.per_goal must be boolean")
                if overrides.get("raising") != "allowed":
                    errors.append(f"{prefix}.engineering_rigor.overrides.raising must be allowed")
                if overrides.get("lowering") != "explicit_user_authority":
                    errors.append(f"{prefix}.engineering_rigor.overrides.lowering requires explicit user authority")
                if overrides.get("may_undercut_risk_minimum") is not False:
                    errors.append(f"{prefix}.engineering_rigor.may_undercut_risk_minimum must remain false")
            interview = settings.get("requirements_interview")
            if not isinstance(interview, dict) or set(interview) != {"source", "level_mapping"}:
                errors.append(f"{prefix}.engineering_rigor.requirements_interview is invalid")
            else:
                if interview.get("source") != "effective_engineering_rigor":
                    errors.append(f"{prefix}.engineering_rigor.requirements_interview.source is invalid")
                if interview.get("level_mapping") != ENGINEERING_RIGOR_INTERVIEW_DEPTH:
                    errors.append(f"{prefix}.engineering_rigor.requirements_interview.level_mapping is invalid")
        elif section_id == "workflow_adherence":
            settings = section["settings"]
            if section.get("decision") not in WORKFLOW_ADHERENCE_SETTINGS["levels"]:
                errors.append(f"{prefix}.workflow_adherence.decision must be optional, tracked, or managed")
            if settings != WORKFLOW_ADHERENCE_SETTINGS:
                errors.append(f"{prefix}.workflow_adherence.settings must preserve the bounded routing contract")
        elif section_id == "automated_design":
            settings = section["settings"]
            if section.get("decision") not in {"enabled", "disabled"}:
                errors.append(f"{prefix}.decision must be enabled or disabled")
            for field, expected in AUTOMATED_DESIGN_SETTINGS.items():
                if settings.get(field) != expected:
                    errors.append(f"{prefix}.automated_design.settings.{field} must preserve the bounded contract")
        elif section_id == "autonomy_approval_parallelism":
            settings = section["settings"]
            if settings.get("dependency_implementation_gate") not in DEPENDENCY_IMPLEMENTATION_GATES:
                errors.append(f"{prefix}.settings.dependency_implementation_gate is invalid")
            if "execution_reports" in settings:
                reporting = settings["execution_reports"]
                if not isinstance(reporting, dict):
                    errors.append(f"{prefix}.settings.execution_reports must be an object")
                elif not isinstance(reporting.get("enabled"), bool):
                    errors.append(f"{prefix}.settings.execution_reports.enabled must be boolean")
            if "requirements_interview" in settings:
                interview = settings["requirements_interview"]
                expected = {
                    "capture_depth": {"light", "standard", "thorough"},
                    "mode": {"adaptive"},
                    "stakeholder_model": {"requesting_user_only"},
                    "execution_questions": {"durable_blockers_only"},
                }
                if not isinstance(interview, dict):
                    errors.append(f"{prefix}.settings.requirements_interview must be an object")
                else:
                    for field, allowed in expected.items():
                        if interview.get(field) not in allowed:
                            errors.append(f"{prefix}.settings.requirements_interview.{field} is invalid")
            if "resource_reservations" in settings:
                try:
                    normalize_resource_policy(settings["resource_reservations"])
                except ValueError as exc:
                    errors.append(f"{prefix}.settings.{exc}")
            if "refill" in settings:
                refill = settings["refill"]
                if not isinstance(refill, dict):
                    errors.append(f"{prefix}.settings.refill must be an object")
                else:
                    categories = refill.get("allowed_categories")
                    if (
                        not isinstance(categories, list)
                        or not categories
                        or any(not isinstance(category, str) for category in categories)
                        or len(categories) != len(set(categories))
                        or any(category not in WORK_SUGGESTION_CATEGORIES for category in categories)
                    ):
                        errors.append(f"{prefix}.settings.refill.allowed_categories is invalid")
                    if not isinstance(refill.get("enabled"), bool):
                        errors.append(f"{prefix}.settings.refill.enabled must be boolean")
                    maximum = refill.get("max_per_run")
                    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
                        errors.append(f"{prefix}.settings.refill.max_per_run must be a positive integer")
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
        errors.extend(validate_default_provenance(section, prefix))
    required_sections = set(POLICY_SECTION_IDS)
    missing = sorted(required_sections - seen)
    if missing:
        errors.append("missing sections: " + ", ".join(missing))
    for section_id, paths in missing_policy_settings(policy).items():
        errors.append(f"section {section_id} is missing operational policy settings: {', '.join(paths)}")
    rigor = next((item for item in sections if isinstance(item, dict) and item.get("id") == "engineering_rigor"), None)
    autonomy = next((item for item in sections if isinstance(item, dict) and item.get("id") == "autonomy_approval_parallelism"), None)
    if isinstance(rigor, dict) and isinstance(autonomy, dict):
        rigor_settings = rigor.get("settings") if isinstance(rigor.get("settings"), dict) else {}
        rigor_interview = rigor_settings.get("requirements_interview")
        rigor_interview = rigor_interview if isinstance(rigor_interview, dict) else {}
        mapping = rigor_interview.get("level_mapping", {})
        expected_depth = mapping.get(rigor.get("decision")) if isinstance(mapping, dict) else None
        autonomy_settings = autonomy.get("settings") if isinstance(autonomy.get("settings"), dict) else {}
        autonomy_interview = autonomy_settings.get("requirements_interview")
        autonomy_interview = autonomy_interview if isinstance(autonomy_interview, dict) else {}
        actual_depth = autonomy_interview.get("capture_depth")
        if expected_depth is not None and actual_depth != expected_depth:
            errors.append("engineering_rigor capture_depth conflicts with the reviewed default level")
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
    decision = " ".join(str(section.get("decision") or "Not configured").split())
    if decision and " " not in decision:
        decision = decision.replace("_", " ").capitalize()
        if decision == "Github issues":
            decision = "GitHub Issues"
    if len(decision) <= limit:
        return decision
    boundary = decision.rfind(" ", 0, limit - 20)
    boundary = boundary if boundary >= 50 else limit - 20
    return decision[:boundary].rstrip(" ,;:") + "… (details in audit)"


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
        "| Policy | Current choice | ZzzOps default? | Stale? | Approved | Applies? | Needs attention |\n"
        "| --- | --- | --- | --- | --- | --- | --- |"
    )
    body = "\n".join(
        "| {policy} | {current_choice} | {default_relationship} | {stale} | {approved} | {applies} | {needs_attention} |".format(
            **{key: cell(value) for key, value in row.items()}
        )
        for row in rows
    )
    return header + "\n" + body


def render_project(state: dict[str, Any]) -> str:
    charter = state["charter"]
    status = "complete" if state["initialized"] else "incomplete — policy review required"
    reviewed = (state.get("approval") or {}).get("date", "not yet")
    kpis = "\n".join(f"| {cell(k['name'])} | {cell(k['why'])} | {cell(k['baseline'])} | {cell(k['target'])} | {cell(k['evidence'])} | {cell(k['cadence'])} |" for k in charter["kpis"])
    bullets = lambda values: "\n".join(f"- {value}" for value in values)
    checks = "\n".join(f"- [x] {value}" for value in charter["acceptance_criteria"])
    policy = "\n".join(
        f"- `[policy:{section['id']}]` **{section['title']}**: {section['decision']} ({default_provenance_label(section)})"
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
    evidence = {item["id"]: f"{item['source']} — {item['finding']}" for item in policy.get("evidence", []) if isinstance(item, dict) and text_present(item.get("id"))}
    for section in policy["sections"]:
        approved = section["review"]["approved"] is True
        applicable = "applicable" if section["applicable"] else "not applicable"
        settings = json.dumps(section["settings"], ensure_ascii=False, sort_keys=True)
        sources = "; ".join(
            "{}: {}".format(source_id, evidence.get(source_id, "missing citation"))
            for source_id in section["source_ids"]
        )
        rendered.append(
            f"- [{'x' if approved else ' '}] `[policy:{section['id']}]` **{section['title']}** ({applicable})\n"
            f"  - Decision: {section['decision']}\n"
            f"  - Rationale: {section['rationale']}\n"
            f"  - Sources: {sources}\n"
            f"  - Confidence/default: {section['confidence']}; {section['default_origin']} → {section['default_disposition']}\n"
            f"  - Provenance: {default_provenance_label(section)}\n"
            f"  - Settings: `{settings}`\n"
            f"  - Exceptions: {', '.join(section['exceptions']) or 'none'}\n"
            f"  - Unresolved: {', '.join(section['unresolved']) or 'none'}"
        )
    return "\n".join(rendered)


def render_project_audit(state: dict[str, Any]) -> str:
    status = "complete" if state["initialized"] else "pending explicit review"
    reviewer = (state.get("approval") or {}).get("reviewer", "not yet approved")
    history = "\n".join(f"| {cell(entry['date'])} | {cell(entry['actor'])} | {cell(entry['change'])} | {cell(entry['reason'])} |" for entry in state["history"])
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
