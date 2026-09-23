"""Pure, content-addressed phase evidence and DAG eligibility evaluation."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any


PHASE_EVIDENCE_SCHEMA_VERSION = 2
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
PROVIDER_CONTENT_IDENTITY = re.compile(r"^provider:[A-Za-z0-9._-]+:(?:sha256:[0-9a-f]{64}|oid:[0-9a-f]{40,64})$")
IMMUTABLE_REFERENCE = re.compile(r"^(?:git:[0-9a-f]{40,64}(?::[A-Za-z0-9._:/@-]+)?|urn:sha256:[0-9a-f]{64}|provider:[A-Za-z0-9._-]+:(?:sha256:[0-9a-f]{64}|oid:[0-9a-f]{40,64}))$")
PHASE_RECORD_STATUSES = {"completed", "not_required"}


class PhaseEvidenceError(ValueError):
    """Phase evidence is malformed, stale, or cannot support a safe transition."""


def _validate_json(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, list):
        for item in value:
            _validate_json(item)
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise PhaseEvidenceError("canonical JSON object keys must be text")
        for item in value.values():
            _validate_json(item)
        return
    raise PhaseEvidenceError("canonical JSON contains an unsupported value")


def canonical_json_bytes(value: Any) -> bytes:
    """Encode exact UTF-8 JSON without incidental whitespace."""
    _validate_json(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:  # pragma: no cover - narrowed above
        raise PhaseEvidenceError("canonical JSON could not be encoded") from exc


def sha256_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def empty_phase_evidence() -> dict[str, Any]:
    return {
        "schema_version": PHASE_EVIDENCE_SCHEMA_VERSION,
        "records": {},
        "reviews": {},
        "human_approvals": {},
        "withdrawals": [],
    }


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PhaseEvidenceError(f"{field} must be trimmed non-empty text")
    return value


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise PhaseEvidenceError(f"{field} must be a SHA-256 digest")
    return value


def _content_hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or (SHA256.fullmatch(value) is None and PROVIDER_CONTENT_IDENTITY.fullmatch(value) is None):
        raise PhaseEvidenceError(f"{field} must be SHA-256 or a content-addressed provider identity")
    return value


def _artifact(value: Any, field: str, *, required: bool = False) -> dict[str, str] | None:
    if value is None and not required:
        return None
    if not isinstance(value, dict) or set(value) != {"reference", "hash"}:
        raise PhaseEvidenceError(f"{field} must contain immutable reference and hash")
    reference = _text(value.get("reference"), f"{field}.reference")
    if IMMUTABLE_REFERENCE.fullmatch(reference) is None:
        raise PhaseEvidenceError(f"{field}.reference must be a content-addressed immutable identity")
    artifact_hash = value.get("hash")
    if not isinstance(artifact_hash, str) or (SHA256.fullmatch(artifact_hash) is None and PROVIDER_CONTENT_IDENTITY.fullmatch(artifact_hash) is None):
        raise PhaseEvidenceError(f"{field}.hash must be SHA-256 or a content-addressed provider identity")
    return {"reference": reference, "hash": artifact_hash}


def _goal_artifacts(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise PhaseEvidenceError(f"{field} must be a list")
    normalized = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"goal", "artifact"}:
            raise PhaseEvidenceError(f"{field} entries must contain goal and artifact")
        goal = item.get("goal")
        if not isinstance(goal, int) or isinstance(goal, bool) or goal < 1:
            raise PhaseEvidenceError(f"{field}.goal must be a positive integer")
        normalized.append({"goal": goal, "artifact": _artifact(item.get("artifact"), f"{field}.artifact", required=True)})
    return normalized


def _snapshot(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"identity", "snapshot"}:
        raise PhaseEvidenceError(f"{field} must contain identity and snapshot")
    identity = _text(value.get("identity"), f"{field}.identity")
    snapshot = value.get("snapshot")
    if not isinstance(snapshot, dict):
        raise PhaseEvidenceError(f"{field}.snapshot must be an object")
    _validate_json(snapshot)
    return {"identity": identity, "snapshot": copy.deepcopy(snapshot)}


def _input_envelope(value: Any, phase: str) -> dict[str, Any]:
    fields = {
        "schema_version", "phase", "goal_spec", "policy", "phase_dag", "parents", "dependencies",
        "repository", "provider", "capabilities", "invocation", "upstream_outputs", "acceptance_criteria",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise PhaseEvidenceError(f"phase record {phase} input envelope has invalid fields")
    if value.get("schema_version") != PHASE_EVIDENCE_SCHEMA_VERSION or value.get("phase") != phase:
        raise PhaseEvidenceError(f"phase record {phase} input envelope identity is invalid")
    invocation = value.get("invocation")
    if not isinstance(invocation, dict) or set(invocation) != {"intent", "inputs"}:
        raise PhaseEvidenceError(f"phase record {phase} invocation is invalid")
    if not isinstance(invocation.get("inputs"), dict):
        raise PhaseEvidenceError(f"phase record {phase} invocation inputs must be an object")
    _validate_json(invocation["inputs"])
    upstream = value.get("upstream_outputs")
    if not isinstance(upstream, list):
        raise PhaseEvidenceError(f"phase record {phase} upstream outputs must be a list")
    normalized_upstream = []
    for item in upstream:
        if not isinstance(item, dict) or set(item) != {"phase", "hash"}:
            raise PhaseEvidenceError(f"phase record {phase} upstream output is invalid")
        normalized_upstream.append({"phase": _text(item.get("phase"), "upstream phase"), "hash": _content_hash(item.get("hash"), "upstream hash")})
    criteria = value.get("acceptance_criteria")
    if not isinstance(criteria, list):
        raise PhaseEvidenceError(f"phase record {phase} acceptance criteria must be a list")
    normalized_criteria = [_text(item, "acceptance criterion") for item in criteria]
    if len(normalized_criteria) != len(set(normalized_criteria)):
        raise PhaseEvidenceError(f"phase record {phase} acceptance criteria must be unique")
    return {
        "schema_version": PHASE_EVIDENCE_SCHEMA_VERSION, "phase": phase,
        "goal_spec": _sha256(value.get("goal_spec"), "goal_spec"), "policy": _sha256(value.get("policy"), "policy"),
        "phase_dag": _sha256(value.get("phase_dag"), "phase_dag"),
        "parents": _goal_artifacts(value.get("parents"), "parents"),
        "dependencies": _goal_artifacts(value.get("dependencies"), "dependencies"),
        "repository": _snapshot(value.get("repository"), "repository"),
        "provider": _snapshot(value.get("provider"), "provider"),
        "capabilities": _snapshot(value.get("capabilities"), "capabilities"),
        "invocation": {"intent": _text(invocation.get("intent"), "invocation.intent"), "inputs": copy.deepcopy(invocation["inputs"])},
        "upstream_outputs": normalized_upstream,
        "acceptance_criteria": normalized_criteria,
    }


def phase_input_envelope(
    phase: str, goal_spec: str, policy: str, phase_dag: str, *,
    parents: list[dict[str, Any]] | None = None, dependencies: list[dict[str, Any]] | None = None,
    repository: dict[str, Any] | None = None, provider: dict[str, Any] | None = None,
    capabilities: dict[str, Any] | None = None, invocation: dict[str, Any] | None = None,
    upstream_outputs: list[dict[str, Any]] | None = None, acceptance_criteria: list[str] | None = None,
) -> dict[str, Any]:
    """Build one phase's declared input envelope; array order remains declared."""
    envelope = {
        "schema_version": PHASE_EVIDENCE_SCHEMA_VERSION, "phase": _text(phase, "phase"),
        "goal_spec": _sha256(goal_spec, "goal_spec"), "policy": _sha256(policy, "policy"),
        "phase_dag": _sha256(phase_dag, "phase_dag"), "parents": copy.deepcopy(parents or []),
        "dependencies": copy.deepcopy(dependencies or []), "repository": copy.deepcopy(repository),
        "provider": copy.deepcopy(provider), "capabilities": copy.deepcopy(capabilities),
        "invocation": copy.deepcopy(invocation), "upstream_outputs": copy.deepcopy(upstream_outputs or []),
        "acceptance_criteria": copy.deepcopy(acceptance_criteria or []),
    }
    return _input_envelope(envelope, phase)


def goal_spec_digest(goal: dict[str, Any], *, title: str, human_spec: str) -> str:
    """Hash semantic scope, deliberately excluding operational goal revisions."""
    if not isinstance(goal, dict):
        raise PhaseEvidenceError("goal specification must be an object")
    semantic = {
        "title": _text(title, "title"), "human_spec": _text(human_spec.strip(), "human_spec"),
        "priority": goal.get("priority"), "value": goal.get("value"), "difficulty": goal.get("difficulty"),
        "confidence": goal.get("confidence"), "parent": goal.get("parent"),
        "depends_on": goal.get("depends_on"), "resources": goal.get("resources"),
        "engineering_rigor": goal.get("engineering_rigor"),
    }
    return sha256_digest({"schema_version": PHASE_EVIDENCE_SCHEMA_VERSION, "goal_spec": semantic})


def _record(value: Any, phase: str) -> dict[str, Any]:
    fields = {"status", "input_envelope", "input_hash", "output", "verification", "routing", "selection", "actor", "not_required", "test_design"}
    if not isinstance(value, dict) or set(value) != fields:
        raise PhaseEvidenceError(f"phase record {phase} has invalid fields")
    status = value.get("status")
    if status not in PHASE_RECORD_STATUSES:
        raise PhaseEvidenceError(f"phase record {phase} status is invalid")
    envelope = _input_envelope(value.get("input_envelope"), phase)
    calculated = sha256_digest(envelope)
    if value.get("input_hash") != calculated:
        raise PhaseEvidenceError(f"phase record {phase} input hash does not match its envelope")
    result = {
        "status": status, "input_envelope": copy.deepcopy(envelope), "input_hash": calculated,
        "output": _artifact(value.get("output"), f"phase record {phase}.output", required=status == "completed"),
        "verification": _artifact(value.get("verification"), f"phase record {phase}.verification"),
        "routing": _artifact(value.get("routing"), f"phase record {phase}.routing"),
        "selection": copy.deepcopy(value.get("selection")),
        "actor": _text(value.get("actor"), f"phase record {phase}.actor"), "not_required": copy.deepcopy(value.get("not_required")),
        "test_design": _test_design(value.get("test_design"), phase, envelope, status),
    }
    if not isinstance(result["selection"], dict) or set(result["selection"]) != {"model", "effort"}:
        raise PhaseEvidenceError(f"phase record {phase} selection is invalid")
    _text(result["selection"].get("model"), f"phase record {phase}.selection.model")
    _text(result["selection"].get("effort"), f"phase record {phase}.selection.effort")
    if status == "not_required":
        decision = result["not_required"]
        if result["output"] is not None or not isinstance(decision, dict) or set(decision) != {"reason", "policy_rule"}:
            raise PhaseEvidenceError(f"not-required phase record {phase} is invalid")
        _text(decision.get("reason"), f"phase record {phase}.not_required.reason")
        _text(decision.get("policy_rule"), f"phase record {phase}.not_required.policy_rule")
    elif result["not_required"] is not None:
        raise PhaseEvidenceError(f"completed phase record {phase} cannot contain a not-required decision")
    if phase == "implement" and status == "completed" and result["verification"] is None:
        raise PhaseEvidenceError("completed implementation phase requires passing verification evidence")
    return result


def _test_design(value: Any, phase: str, envelope: dict[str, Any], status: str) -> dict[str, Any] | None:
    """Validate the executable behavioural-test contract for a test-design phase."""
    if phase != "test_design":
        if value is not None:
            raise PhaseEvidenceError(f"phase record {phase} cannot contain test design evidence")
        return None
    if status == "not_required":
        if value is not None:
            raise PhaseEvidenceError("not-required test-design phase cannot contain test design evidence")
        return None
    if not isinstance(value, dict) or set(value) != {"baseline_failure", "coverage"}:
        raise PhaseEvidenceError("test-design phase record must contain baseline failure and coverage")
    coverage = value.get("coverage")
    if not isinstance(coverage, list):
        raise PhaseEvidenceError("test-design coverage must be a list")
    expected = envelope["acceptance_criteria"]
    covered: list[str] = []
    normalized = []
    for item in coverage:
        if not isinstance(item, dict) or set(item) != {"criterion", "test", "exclusion"}:
            raise PhaseEvidenceError("test-design coverage entries must contain criterion, test, and exclusion")
        criterion = _text(item.get("criterion"), "test-design coverage criterion")
        test, exclusion = item.get("test"), item.get("exclusion")
        if (test is None) == (exclusion is None):
            raise PhaseEvidenceError("test-design coverage requires exactly one test or exclusion")
        normalized.append({
            "criterion": criterion,
            "test": _artifact(test, "test-design coverage test") if test is not None else None,
            "exclusion": _text(exclusion, "test-design coverage exclusion") if exclusion is not None else None,
        })
        covered.append(criterion)
    if len(covered) != len(set(covered)) or set(covered) != set(expected):
        raise PhaseEvidenceError("test-design coverage must account for every acceptance criterion exactly once")
    return {"baseline_failure": _artifact(value.get("baseline_failure"), "test-design baseline failure", required=True), "coverage": normalized}


def _review_outcomes(value: Any, decision: str) -> dict[str, Any]:
    """Validate durable acceptance and entropy outcomes for a phase review."""
    if not isinstance(value, dict) or set(value) != {"acceptance", "entropy"}:
        raise PhaseEvidenceError("phase review outcomes must contain acceptance and entropy")
    acceptance = value.get("acceptance")
    if acceptance not in {"approved", "changes_requested"} or acceptance != decision:
        raise PhaseEvidenceError("phase review acceptance outcome must match its decision")
    entropy = value.get("entropy")
    if not isinstance(entropy, dict):
        raise PhaseEvidenceError("phase review entropy outcome is invalid")
    outcome = entropy.get("outcome")
    required = {"outcome", "evidence"}
    if outcome not in {"no_findings", "fixed", "follow_up"} or set(entropy) not in (required, required | {"goals"}):
        raise PhaseEvidenceError("phase review entropy outcome is invalid")
    normalized_entropy: dict[str, Any] = {
        "outcome": outcome,
        "evidence": _text(entropy.get("evidence"), "phase review entropy evidence"),
    }
    goals = entropy.get("goals", [])
    if outcome == "follow_up":
        if not isinstance(goals, list) or not goals or any(
            not isinstance(goal, int) or isinstance(goal, bool) or goal < 1 for goal in goals
        ):
            raise PhaseEvidenceError("phase review entropy follow-up goals must be positive integers")
        if len(goals) != len(set(goals)):
            raise PhaseEvidenceError("phase review entropy follow-up goals must be unique")
    elif not isinstance(goals, list) or goals:
        raise PhaseEvidenceError("phase review entropy goals are only allowed for follow-up")
    normalized_entropy["goals"] = list(goals)
    return {"acceptance": acceptance, "entropy": normalized_entropy}


def normalize_phase_evidence(value: Any) -> dict[str, Any]:
    if value is None:
        value = {"schema_version": PHASE_EVIDENCE_SCHEMA_VERSION, "records": {}, "reviews": {}, "withdrawals": []}
    # Legacy schema v1 writers could omit empty review state.  v2 makes that
    # state explicit and adds human approvals, so project both defaults in
    # memory without rewriting provider-owned goal history.
    if isinstance(value, dict) and value.get("schema_version") == 1:
        value = {
            **value,
            "schema_version": PHASE_EVIDENCE_SCHEMA_VERSION,
            "reviews": value.get("reviews", {}),
            "human_approvals": {},
        }
    fields = {"schema_version", "records", "reviews", "withdrawals"}
    if not isinstance(value, dict) or set(value) not in (fields, fields | {"human_approvals"}):
        raise PhaseEvidenceError("phase evidence has invalid fields")
    if value.get("schema_version") != PHASE_EVIDENCE_SCHEMA_VERSION:
        raise PhaseEvidenceError("phase evidence schema version is invalid")
    records, reviews, approvals, withdrawals = value.get("records"), value.get("reviews"), value.get("human_approvals", {}), value.get("withdrawals")
    if not isinstance(records, dict) or not isinstance(reviews, dict) or not isinstance(approvals, dict) or not isinstance(withdrawals, list):
        raise PhaseEvidenceError("phase evidence records, reviews, and withdrawals are required")
    normalized = empty_phase_evidence()
    for phase, record in records.items():
        _text(phase, "phase identifier")
        normalized["records"][phase] = _record(record, phase)
    for phase, review in reviews.items():
        _text(phase, "review phase")
        record = normalized["records"].get(phase)
        binding_field = "output_hash" if record is not None and record["status"] == "completed" else "decision_hash"
        required_review_fields = {"record_hash", "input_hash", binding_field, "artifact", "reviewer", "decision"}
        if record is None or not isinstance(review, dict) or set(review) not in (required_review_fields, required_review_fields | {"outcomes"}):
            raise PhaseEvidenceError("phase review is invalid")
        if review.get("record_hash") != sha256_digest(record):
            raise PhaseEvidenceError("phase review record hash is stale")
        if review.get("input_hash") != record["input_hash"]:
            raise PhaseEvidenceError("phase review input hash is stale")
        if binding_field == "output_hash":
            if review.get(binding_field) != record["output"]["hash"]:
                raise PhaseEvidenceError("phase review output hash is stale")
        elif review.get(binding_field) != sha256_digest(record["not_required"]):
            raise PhaseEvidenceError("phase review not-required decision hash is stale")
        decision = review.get("decision")
        if decision not in {"approved", "changes_requested"}:
            raise PhaseEvidenceError("phase review decision is invalid")
        normalized_review = {
            "record_hash": review["record_hash"],
            "input_hash": review["input_hash"], binding_field: review[binding_field],
            "artifact": _artifact(review.get("artifact"), "phase review artifact", required=True),
            "reviewer": _text(review.get("reviewer"), "phase reviewer"),
            "decision": decision,
        }
        if "outcomes" in review:
            normalized_review["outcomes"] = _review_outcomes(review["outcomes"], decision)
        normalized["reviews"][phase] = normalized_review
    for phase, approval in approvals.items():
        _text(phase, "human approval phase")
        review = normalized["reviews"].get(phase)
        record = normalized["records"].get(phase)
        if record is None or not isinstance(approval, dict) or set(approval) != {"record_hash", "review_hash", "actor", "approval_token"}:
            raise PhaseEvidenceError("phase human approval is invalid")
        expected_review_hash = sha256_digest(review) if review is not None else None
        if approval.get("record_hash") != sha256_digest(record) or approval.get("review_hash") != expected_review_hash:
            raise PhaseEvidenceError("phase human approval is stale")
        actor = _text(approval.get("actor"), "phase human approval actor")
        if actor != "root":
            raise PhaseEvidenceError("phase human approval actor must be root")
        normalized["human_approvals"][phase] = {
            "record_hash": approval["record_hash"], "review_hash": approval["review_hash"],
            "actor": actor, "approval_token": _text(approval.get("approval_token"), "phase human approval token"),
        }
    seen = set()
    for withdrawal in withdrawals:
        if not isinstance(withdrawal, dict) or set(withdrawal) != {"id", "phase", "reason", "actor", "record_hash"}:
            raise PhaseEvidenceError("phase evidence withdrawal has invalid fields")
        identifier = _sha256(withdrawal.get("id"), "phase evidence withdrawal.id")
        phase = _text(withdrawal.get("phase"), "phase evidence withdrawal.phase")
        if identifier in seen or phase not in normalized["records"]:
            raise PhaseEvidenceError("phase evidence withdrawal is invalid")
        seen.add(identifier)
        record_hash = sha256_digest(normalized["records"][phase])
        if withdrawal.get("record_hash") != record_hash:
            raise PhaseEvidenceError("phase evidence withdrawal record hash is stale")
        normalized["withdrawals"].append({"id": identifier, "phase": phase, "reason": _text(withdrawal.get("reason"), "phase evidence withdrawal.reason"), "actor": _text(withdrawal.get("actor"), "phase evidence withdrawal.actor"), "record_hash": record_hash})
    return normalized


def validate_phase_evidence(value: Any) -> list[str]:
    try:
        normalize_phase_evidence(value)
    except PhaseEvidenceError as exc:
        return [str(exc)]
    return []


def _withdrawn(evidence: dict[str, Any], phase: str) -> bool:
    return any(item["phase"] == phase for item in evidence["withdrawals"])


def record_phase_result(
    evidence: Any, phase: str, record: Any, current_input: dict[str, Any],
    *, phase_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return updated evidence only when a submitted result matches current inputs."""
    normalized, phase = normalize_phase_evidence(evidence), _text(phase, "phase")
    normalized_record = _record(record, phase)
    current = _input_envelope(current_input, phase)
    if normalized_record["input_hash"] != sha256_digest(current) or normalized_record["input_envelope"] != current:
        raise PhaseEvidenceError("phase result input evidence is stale")
    if phase == "implement":
        _require_approved_test_design(normalized, normalized_record, phase_policy=phase_policy)
    normalized["records"][phase] = normalized_record
    normalized["reviews"].pop(phase, None)
    normalized["human_approvals"].pop(phase, None)
    normalized["withdrawals"] = [item for item in normalized["withdrawals"] if item["phase"] != phase]
    return normalized


def _require_approved_test_design(
    evidence: dict[str, Any], implementation: dict[str, Any],
    *, phase_policy: dict[str, Any] | None = None,
) -> None:
    """Implementation may only proceed from an approved, explicitly bound test design."""
    independent, human_approval = True, False
    if phase_policy is not None:
        if not isinstance(phase_policy, dict) or not isinstance(phase_policy.get("test_design"), dict):
            raise PhaseEvidenceError("test-design phase policy is invalid")
        configured = phase_policy["test_design"]
        review_policy = configured.get("review")
        if (
            not isinstance(review_policy, dict)
            or not isinstance(review_policy.get("independent"), bool)
            or not isinstance(review_policy.get("human_approval"), bool)
            or configured.get("not_required", "never") != "never"
        ):
            raise PhaseEvidenceError("test-design phase policy is invalid")
        independent = review_policy["independent"]
        human_approval = review_policy["human_approval"]
    design = evidence["records"].get("test_design")
    review = evidence["reviews"].get("test_design")
    if design is None or design["status"] != "completed" or design["test_design"] is None or _withdrawn(evidence, "test_design"):
        raise PhaseEvidenceError("implementation requires completed test-design evidence")
    if review is not None and review["decision"] == "changes_requested":
        raise PhaseEvidenceError("implementation is blocked by requested test-design changes")
    if independent and (review is None or review["decision"] != "approved"):
        raise PhaseEvidenceError("implementation requires approved test-design review")
    if human_approval and "test_design" not in evidence["human_approvals"]:
        raise PhaseEvidenceError("implementation requires test-design human approval")
    output = design["output"]
    if output is None or not any(
        item["phase"] == "test_design" and item["hash"] == output["hash"]
        for item in implementation["input_envelope"]["upstream_outputs"]
    ):
        raise PhaseEvidenceError("implementation must bind the approved test-design output")


def record_phase_review(
    evidence: Any, phase: str, artifact: Any, reviewer: str, *, decision: str = "approved",
    require_independent: bool = True, outcomes: Any = None,
) -> dict[str, Any]:
    """Attach an independent immutable review to the exact current phase record."""
    normalized, phase = normalize_phase_evidence(evidence), _text(phase, "review phase")
    record = normalized["records"].get(phase)
    if record is None:
        raise PhaseEvidenceError("cannot review phase evidence that was never recorded")
    reviewer = _text(reviewer, "phase reviewer")
    if not isinstance(require_independent, bool):
        raise PhaseEvidenceError("phase review independence requirement is invalid")
    if require_independent and reviewer == record["actor"]:
        raise PhaseEvidenceError("phase reviewer must be independent from phase actor")
    if decision not in {"approved", "changes_requested"}:
        raise PhaseEvidenceError("phase review decision is invalid")
    binding = (
        {"output_hash": record["output"]["hash"]}
        if record["output"] is not None
        else {"decision_hash": sha256_digest(record["not_required"])}
    )
    normalized_review = {
        "record_hash": sha256_digest(record),
        "input_hash": record["input_hash"], **binding,
        "artifact": _artifact(artifact, "phase review artifact", required=True),
        "reviewer": reviewer,
        "decision": decision,
    }
    if outcomes is not None:
        normalized_review["outcomes"] = _review_outcomes(outcomes, decision)
    normalized["reviews"][phase] = normalized_review
    normalized["human_approvals"].pop(phase, None)
    return normalized


def record_phase_approval(evidence: Any, phase: str, actor: str, approval_token: str) -> dict[str, Any]:
    """Bind explicit root approval to the exact current record and approved review."""
    normalized, phase = normalize_phase_evidence(evidence), _text(phase, "approval phase")
    record, review = normalized["records"].get(phase), normalized["reviews"].get(phase)
    if record is None or (review is not None and review["decision"] != "approved"):
        raise PhaseEvidenceError("human approval cannot bind a rejected phase review")
    actor = _text(actor, "phase human approval actor")
    if actor != "root":
        raise PhaseEvidenceError("phase human approval actor must be root")
    normalized["human_approvals"][phase] = {
        "record_hash": sha256_digest(record), "review_hash": sha256_digest(review) if review is not None else None,
        "actor": actor, "approval_token": _text(approval_token, "phase human approval token"),
    }
    return normalized


def withdraw_phase_evidence(evidence: Any, phase: str, *, reason: str, actor: str) -> dict[str, Any]:
    """Append a justified withdrawal; evaluation then stales declared descendants."""
    normalized, phase = normalize_phase_evidence(evidence), _text(phase, "phase")
    if phase not in normalized["records"]:
        raise PhaseEvidenceError("cannot withdraw phase evidence that was never recorded")
    item = {"phase": phase, "reason": _text(reason, "reason"), "actor": _text(actor, "actor"), "record_hash": sha256_digest(normalized["records"][phase])}
    item["id"] = sha256_digest(item)
    if not any(existing["id"] == item["id"] for existing in normalized["withdrawals"]):
        normalized["withdrawals"].append(item)
    return normalized


def _graph(graph: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(graph, dict) or set(graph) != {"phases"} or not isinstance(graph["phases"], list):
        raise PhaseEvidenceError("phase graph must contain exactly a phases list")
    result = {}
    for node in graph["phases"]:
        if not isinstance(node, dict) or set(node) - {"id", "depends_on", "parent_gates"}:
            raise PhaseEvidenceError("phase graph node is invalid")
        phase = _text(node.get("id"), "phase graph node id")
        dependencies, parent_gates = node.get("depends_on", []), node.get("parent_gates", [])
        if phase in result or not isinstance(dependencies, list) or not isinstance(parent_gates, list) or any(not isinstance(item, str) or not item for item in dependencies + parent_gates):
            raise PhaseEvidenceError("phase graph edges are invalid")
        result[phase] = {"depends_on": list(dependencies), "parent_gates": list(parent_gates)}
    if any(phase in node["depends_on"] or any(item not in result for item in node["depends_on"]) for phase, node in result.items()):
        raise PhaseEvidenceError("phase graph dependency is invalid")
    visited, visiting = set(), set()
    def visit(phase: str) -> None:
        if phase in visiting:
            raise PhaseEvidenceError("phase graph must be acyclic")
        if phase in visited:
            return
        visiting.add(phase)
        for dependency in result[phase]["depends_on"]:
            visit(dependency)
        visiting.remove(phase)
        visited.add(phase)
    for phase in result:
        visit(phase)
    return result


def derive_phase_eligibility(goal: dict[str, Any], graph: Any, live_inputs: dict[str, dict[str, Any]], related_goals: dict[Any, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Derive the DAG frontier from durable records and freshly declared evidence."""
    nodes = _graph(graph)
    if not isinstance(goal, dict):
        raise PhaseEvidenceError("goal must be an object")
    if goal.get("status") in {"done", "cancelled"} or goal.get("state") == "closed":
        return {"eligible": [], "stale": [], "blocked": [], "invalidated_ancestor_gates": [], "diagnostics": ["terminal_goal"]}
    evidence = normalize_phase_evidence(goal.get("phase_evidence", empty_phase_evidence()))
    if not isinstance(live_inputs, dict) or any(phase not in nodes for phase in live_inputs):
        raise PhaseEvidenceError("live phase inputs are invalid")
    normalized_inputs = {phase: _input_envelope(value, phase) for phase, value in live_inputs.items()}
    current = {
        phase: phase in evidence["records"] and phase in live_inputs and not _withdrawn(evidence, phase)
        and evidence["records"][phase]["input_hash"] == sha256_digest(normalized_inputs[phase])
        for phase in nodes
    }
    stale = [phase for phase in nodes if phase in evidence["records"] and not current[phase]]
    related_goals = related_goals or {}
    parent = related_goals.get(goal.get("parent")) if goal.get("parent") is not None else None
    parent_goal = parent.get("goal") if isinstance(parent, dict) else None
    parent_inputs = parent.get("live_inputs") if isinstance(parent, dict) else None
    parent_evidence = normalize_phase_evidence(parent_goal.get("phase_evidence", empty_phase_evidence())) if isinstance(parent_goal, dict) else None
    eligible, blocked, diagnostics = [], [], []
    for phase, node in nodes.items():
        if current[phase]:
            continue
        unmet = [dependency for dependency in node["depends_on"] if not current[dependency]]
        missing_parent = [
            gate for gate in node["parent_gates"]
            if parent_evidence is None or not isinstance(parent_inputs, dict) or gate not in parent_inputs
            or gate not in parent_evidence["records"] or _withdrawn(parent_evidence, gate)
            or parent_evidence["records"][gate]["status"] != "completed"
            or parent_evidence["records"][gate]["input_hash"] != sha256_digest(_input_envelope(parent_inputs[gate], gate))
        ]
        if unmet or missing_parent:
            blocked.append({"phase": phase, "dependencies": unmet, "parent_gates": missing_parent})
        elif phase not in live_inputs:
            diagnostics.append(f"{phase}:missing_live_input")
        else:
            eligible.append({"phase": phase, "reason": "stale_input" if phase in stale else "missing_evidence"})
    return {
        "eligible": eligible, "stale": stale, "blocked": blocked,
        "invalidated_ancestor_gates": _invalidated_ancestor_gates(nodes, stale, blocked),
        "diagnostics": diagnostics,
    }


def _invalidated_ancestor_gates(
    nodes: dict[str, dict[str, list[str]]], stale: list[str], blocked: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Explain which stale phase gates block descendant phases in the DAG.

    A flat ``stale`` list forces callers to reconstruct reachability before
    they can tell whether a stale phase prevents dispatch.  Keep the original
    frontier fields, but publish the exact stale ancestor-to-blocked-descendant
    relationship in graph order.
    """
    blocked_by_phase = {item["phase"]: item for item in blocked}

    def has_stale_ancestor(phase: str, ancestor: str, seen: set[str] | None = None) -> bool:
        seen = set() if seen is None else seen
        if phase in seen:
            return False
        seen.add(phase)
        dependencies = nodes[phase]["depends_on"]
        return ancestor in dependencies or any(
            has_stale_ancestor(dependency, ancestor, seen) for dependency in dependencies
        )

    result = []
    for ancestor in stale:
        affected = []
        for phase in nodes:
            item = blocked_by_phase.get(phase)
            if item is not None and has_stale_ancestor(phase, ancestor):
                affected.append({
                    "phase": phase,
                    "blocked_phase": phase,
                    "dependencies": list(item["dependencies"]),
                    "parent_gates": list(item["parent_gates"]),
                })
        if affected:
            result.append({"phase": ancestor, "reason": "stale_input", "affected_descendants": affected})
    return result


def derive_phase_steps(
    goal: dict[str, Any], graph: Any, live_inputs: dict[str, dict[str, Any]],
    related_goals: dict[Any, dict[str, Any]] | None = None,
    review_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive executable and review work from immutable evidence, with no cursor.

    Every supplied graph phase requires an approved review before it satisfies a
    dependency. Callers may run independent returned steps in parallel; this
    function deliberately does not reserve or mutate anything.
    """
    nodes = _graph(graph)
    if not isinstance(goal, dict):
        raise PhaseEvidenceError("goal must be an object")
    if goal.get("status") in {"done", "cancelled"} or goal.get("state") == "closed":
        return {"execute": [], "review": [], "stale": [], "blocked": [], "invalidated_ancestor_gates": [], "diagnostics": ["terminal_goal"]}
    evidence = normalize_phase_evidence(goal.get("phase_evidence", empty_phase_evidence()))
    if review_policy is not None and not isinstance(review_policy, dict):
        raise PhaseEvidenceError("phase review policy must be an object")

    def requirements(phase: str) -> dict[str, Any]:
        if review_policy is None:
            return {"independent": True, "human_approval": False, "not_required": None}
        configured = review_policy.get(phase, {})
        if not isinstance(configured, dict):
            raise PhaseEvidenceError(f"phase review policy for {phase} is invalid")
        review = configured.get("review", configured)
        if not isinstance(review, dict):
            raise PhaseEvidenceError(f"phase review policy for {phase} is invalid")
        independent = review.get("independent", True)
        human_approval = review.get("human_approval", False)
        if not isinstance(independent, bool) or not isinstance(human_approval, bool):
            raise PhaseEvidenceError(f"phase review policy for {phase} is invalid")
        not_required = configured.get("not_required", "never")
        if not isinstance(not_required, str):
            raise PhaseEvidenceError(f"phase not-required policy for {phase} is invalid")
        return {"independent": independent, "human_approval": human_approval, "not_required": not_required}

    policies = {phase: requirements(phase) for phase in nodes}
    if not isinstance(live_inputs, dict) or any(phase not in nodes for phase in live_inputs):
        raise PhaseEvidenceError("live phase inputs are invalid")
    normalized_inputs = {phase: _input_envelope(value, phase) for phase, value in live_inputs.items()}
    current = {
        phase: phase in evidence["records"] and phase in normalized_inputs and not _withdrawn(evidence, phase)
        and evidence["records"][phase]["input_hash"] == sha256_digest(normalized_inputs[phase])
        and (
            evidence["records"][phase]["status"] == "completed"
            or policies[phase]["not_required"] is None
            or (
                policies[phase]["not_required"] != "never"
                and evidence["records"][phase]["not_required"]["policy_rule"] == policies[phase]["not_required"]
            )
        )
        for phase in nodes
    }
    review_approved = {
        phase: current[phase]
        and evidence["reviews"].get(phase, {}).get("decision") != "changes_requested"
        and (
            not policies[phase]["independent"]
            or (
                evidence["reviews"].get(phase, {}).get("decision") == "approved"
                and evidence["reviews"][phase]["reviewer"] != evidence["records"][phase]["actor"]
            )
        )
        for phase in nodes
    }
    locally_approved = {
        phase: review_approved[phase]
        and (
            not policies[phase]["human_approval"]
            or phase in evidence["human_approvals"]
        )
        for phase in nodes
    }
    approved: dict[str, bool] = {}

    def dependencies_approved(phase: str) -> bool:
        if phase not in approved:
            approved[phase] = locally_approved[phase] and all(
                dependencies_approved(dependency) for dependency in nodes[phase]["depends_on"]
            )
        return approved[phase]

    for phase in nodes:
        dependencies_approved(phase)
    stale = [phase for phase in nodes if phase in evidence["records"] and not current[phase]]
    related_goals = related_goals or {}
    parent = related_goals.get(goal.get("parent")) if goal.get("parent") is not None else None
    parent_goal = parent.get("goal") if isinstance(parent, dict) else None
    parent_inputs = parent.get("live_inputs") if isinstance(parent, dict) else None
    parent_evidence = normalize_phase_evidence(parent_goal.get("phase_evidence", empty_phase_evidence())) if isinstance(parent_goal, dict) else None

    def parent_gate_missing(gate: str) -> bool:
        if parent_evidence is None or not isinstance(parent_inputs, dict) or gate not in parent_inputs:
            return True
        record = parent_evidence["records"].get(gate)
        review = parent_evidence["reviews"].get(gate)
        policy = requirements(gate)
        if record is None or _withdrawn(parent_evidence, gate):
            return True
        if record["input_hash"] != sha256_digest(_input_envelope(parent_inputs[gate], gate)):
            return True
        if record["status"] == "not_required" and policy["not_required"] is not None and (
            policy["not_required"] == "never" or record["not_required"]["policy_rule"] != policy["not_required"]
        ):
            return True
        if policy["independent"] and (
            review is None or review["decision"] != "approved" or review["reviewer"] == record["actor"]
        ):
            return True
        return policy["human_approval"] and gate not in parent_evidence["human_approvals"]

    execute, review, blocked, diagnostics = [], [], [], []
    for phase, node in nodes.items():
        unmet = [dependency for dependency in node["depends_on"] if not approved[dependency]]
        missing_parent = [gate for gate in node["parent_gates"] if parent_gate_missing(gate)]
        if current[phase] and (unmet or missing_parent):
            blocked.append({"phase": phase, "dependencies": unmet, "parent_gates": missing_parent})
            continue
        if current[phase]:
            if evidence["reviews"].get(phase, {}).get("decision") == "changes_requested":
                execute.append({"phase": phase, "reason": "changes_requested"})
            elif policies[phase]["independent"] and not review_approved[phase]:
                review.append({"phase": phase, "reason": "missing_or_unapproved_review"})
            elif policies[phase]["human_approval"] and phase not in evidence["human_approvals"]:
                review.append({"phase": phase, "reason": "missing_human_approval"})
            continue
        if unmet or missing_parent:
            blocked.append({"phase": phase, "dependencies": unmet, "parent_gates": missing_parent})
        elif phase not in normalized_inputs:
            diagnostics.append(f"{phase}:missing_live_input")
        else:
            execute.append({"phase": phase, "reason": "stale_input" if phase in stale else "missing_evidence"})
    return {
        "execute": execute, "review": review, "stale": stale, "blocked": blocked,
        "invalidated_ancestor_gates": _invalidated_ancestor_gates(nodes, stale, blocked),
        "diagnostics": diagnostics,
    }
