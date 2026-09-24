"""Canonical project-policy state, validation, and rendering helpers.

This module deliberately has no dependency on the ZzzOps CLI or provider layer so
project-policy behavior can be exercised and reused without importing the control
entry point.
"""

from __future__ import annotations

import hashlib
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
    "understand", "decompose", "test_design", "implement", "publish",
)
# Existing reviewed policies remain readable until explicit default adoption.
WORKFLOW_PHASE_TYPES = frozenset((*WORKFLOW_PHASE_IDS, "plan"))
WORKFLOW_ASSIGNMENT_GROUPS = frozenset({"root", "planning", "implementation", "review", "coordinator"})
WORKFLOW_APPLICABILITY = frozenset({"always", "parent_only", "child_only", "leaf_only"})
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
        if phase not in WORKFLOW_PHASE_TYPES or phase in nodes:
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
        review_fields = {"independent", "human_approval", "assignment_group"}
        if not isinstance(review, dict) or not review_fields <= set(review) or set(review) - review_fields - {"types", "by_consequence"}:
            errors.append(f"{prefix}.review is invalid")
        elif not isinstance(review.get("independent"), bool) or not isinstance(review.get("human_approval"), bool) or review.get("assignment_group") != "review":
            errors.append(f"{prefix}.review is invalid")
        if isinstance(review, dict):
            variants = review.get('by_consequence', {})
            if (not isinstance(variants, dict)
                    or any(key not in ROUTING_DIMENSION_VALUES['consequence'] for key in variants)):
                errors.append(f'{prefix}.review.by_consequence is invalid')
                variants = {}
            for variant in [review, *variants.values()]:
                if not isinstance(variant, dict):
                    errors.append(f'{prefix}.review override must be an object')
                    continue
                if variant is not review and (not variant or set(variant) - review_fields - {'types'}):
                    errors.append(f'{prefix}.review override has unsupported fields')
                for flag in ('independent', 'human_approval'):
                    if flag in variant and not isinstance(variant[flag], bool):
                        errors.append(f'{prefix}.review.{flag} must be boolean')
                if 'assignment_group' in variant and variant['assignment_group'] != 'review':
                    errors.append(f'{prefix}.review must use the review assignment group')
                if 'types' in variant and (not isinstance(variant['types'], list) or not variant['types']
                        or any(not _policy_identifier(t) for t in variant['types'])
                        or len(set(variant['types'])) != len(variant['types'])):
                    errors.append(f'{prefix}.review.types must be distinct review identifiers')
        dependencies, parent_gates = node.get("depends_on"), node.get("parent_gates")
        if not isinstance(dependencies, list) or any(item not in WORKFLOW_PHASE_TYPES for item in dependencies) or len(set(dependencies)) != len(dependencies):
            errors.append(f"{prefix}.depends_on is invalid")
        if not isinstance(parent_gates, list) or any(item not in WORKFLOW_PHASE_TYPES for item in parent_gates) or len(set(parent_gates)) != len(parent_gates):
            errors.append(f"{prefix}.parent_gates is invalid")
        inputs = node.get("inputs")
        if not isinstance(inputs, list) or not inputs or any(item not in WORKFLOW_INPUT_CATEGORIES for item in inputs) or len(set(inputs)) != len(inputs):
            errors.append(f"{prefix}.inputs is invalid")
        nodes[phase] = node
    if set(nodes) not in (set(WORKFLOW_PHASE_IDS), set(WORKFLOW_PHASE_TYPES)):
        errors.append("phase_dag must define every shipped phase exactly once")
    for phase, node in nodes.items():
        dependencies = node.get("depends_on", [])
        if phase in dependencies or any(dependency not in nodes for dependency in dependencies) or any(gate not in nodes for gate in node.get('parent_gates', [])):
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


def phase_evidence_graph(phase_dag: Any, *, has_parent: bool, has_children: bool = False) -> dict[str, list[dict[str, Any]]]:
    """Project reviewed policy nodes into the exact graph consumed by #432.

    Applicability is resolved before handing the graph to the generic evaluator.
    In particular, a child consumes its parent's decomposition as a parent gate
    instead of receiving an impossible local decomposition dependency. The
    orchestration layer supplies child-completion evidence to parent publication.
    Leaf-owned phases depend on child relationships, not structural parenthood.
    Legacy child_only policies retain their meaning until reviewed adoption.
    """
    errors = _workflow_phase_dag_errors(phase_dag)
    if errors:
        raise ValueError("Invalid workflow phase DAG: " + "; ".join(errors))
    included = {
        node["id"] for node in phase_dag["phases"]
        if node["applicability"] == "always"
        or (node["applicability"] == "child_only" and has_parent)
        or (node["applicability"] == "leaf_only" and not has_children)
        or (node["applicability"] == "parent_only" and not has_parent)
    }
    result = []
    for node in phase_dag["phases"]:
        phase = node["id"]
        if phase not in included:
            continue
        dependencies = [dependency for dependency in node["depends_on"] if dependency in included]
        parent_phases = {item["id"] for item in phase_dag["phases"] if item["applicability"] not in {"child_only", "leaf_only"}}
        parent_gates = [gate for gate in node["parent_gates"] if gate in parent_phases] if has_parent else []
        if phase == "publish" and "implement" not in included:
            dependencies = ["plan" if "plan" in included else "decompose"]
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
    optional_fields = {"default_id", "default_resolution", "default_provenance"}
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


def render_project(state: dict[str, Any]) -> str:
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
        settings = json.dumps(section["configuration"], ensure_ascii=False, sort_keys=True)
        sources = "; ".join(
            "{}: {}".format(source_id, evidence.get(source_id, "missing citation"))
            for source_id in section["source_ids"]
        )
        rendered.append(
            f"- [{'x' if approved else ' '}] `[policy:{section['id']}]` **{section['title']}** ({applicable})\n"
            f"  - Instructions: {section['instructions']}\n"
            f"  - Rationale: {section['rationale']}\n"
            f"  - Sources: {sources}\n"
            f"  - Confidence/default: {section['confidence']}; {section['default_origin']} → {section['default_disposition']}\n"
            f"  - Provenance: {default_provenance_label(section)}\n"
            f"  - Configuration: `{settings}`\n"
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
