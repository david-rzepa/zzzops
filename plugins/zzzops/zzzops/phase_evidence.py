"""Pure, content-addressed phase evidence and DAG eligibility evaluation."""

from __future__ import annotations

import copy
import hashlib
import json
import marshal
import re
from typing import Any
from collections import OrderedDict
from threading import RLock


PHASE_EVIDENCE_SCHEMA_VERSION = 2
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
PROVIDER_CONTENT_IDENTITY = re.compile(r"^provider:[A-Za-z0-9._-]+:(?:sha256:[0-9a-f]{64}|oid:[0-9a-f]{40,64})$")
IMMUTABLE_REFERENCE = re.compile(r"^(?:git:[0-9a-f]{40,64}(?::[A-Za-z0-9._:/@-]+)?|urn:sha256:[0-9a-f]{64}|provider:[A-Za-z0-9._-]+:(?:sha256:[0-9a-f]{64}|oid:[0-9a-f]{40,64}))$")
PHASE_RECORD_STATUSES = {"completed", "not_required"}
OPERATIONAL_POLICY_SECTIONS = {"model_routing", "autonomy_approval_parallelism"}


def evidence_policy(policy: dict[str, Any]) -> dict[str, Any]:
    """Return policy meaning that can change the validity of completed work.

    Routing, inventory, concurrency and refill settings affect scheduling and
    future acquisition.  They are deliberately excluded from Result identity;
    the graph and declared inputs continue to carry substantive requirements.
    """
    value = copy.deepcopy(policy)
    sections = value.get("sections")
    if isinstance(sections, list):
        value["sections"] = [section for section in sections
                             if section.get("id") not in OPERATIONAL_POLICY_SECTIONS]
    return value


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
    if outcome not in {"no_findings", "fixed", "follow_up", "correction_required"} or set(entropy) not in (required, required | {"goals"}):
        raise PhaseEvidenceError("phase review entropy outcome is invalid")
    if outcome == "correction_required" and acceptance != "changes_requested":
        raise PhaseEvidenceError("pending in-goal entropy correction requires changes_requested acceptance")
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


# Version two execution contracts. The phase codecs above decode historical
# evidence only; active graph validation and execution use these task contracts.
TASK_ID = re.compile(r'^[A-Za-z0-9_-]+$')
RESERVED_OUTPUT_TYPES = {'result', 'relationship_context'}


def task_identifier(value):
    return isinstance(value, str) and TASK_ID.fullmatch(value) is not None


def contract_fields(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f'{label} has missing or unknown fields; expected {sorted(fields)}')


def positive_integer(value):
    return type(value) is int and value > 0


def validate_ref(value):
    contract_fields(value, {'hash', 'uri'}, 'Ref')
    if not isinstance(value['hash'], str) or not SHA256.fullmatch(value['hash']) or not isinstance(value['uri'], str) or not value['uri']:
        raise ValueError('Ref requires a content hash and nonempty URI')


def value_matches(schema, value):
    kind = schema['kind']
    if kind == 'string': return isinstance(value, str)
    if kind == 'boolean': return type(value) is bool
    if kind == 'integer': return type(value) is int
    if kind == 'null': return value is None
    if kind == 'enum': return any(type(value) is type(v) and value == v for v in schema['values'])
    if kind == 'union': return sum(value_matches(s, value) for s in schema['variants']) == 1
    if kind == 'array': return isinstance(value, list) and all(value_matches(schema['items'], v) for v in value)
    if kind == 'map': return isinstance(value, dict) and all(isinstance(k, str) and value_matches(schema['values'], v) for k, v in value.items())
    if kind == 'object': return isinstance(value, dict) and set(value) == set(schema['fields']) and all(value_matches(s, value[k]) for k, s in schema['fields'].items())
    return False


def types_overlap(a, b):
    if a['kind'] == 'union': return any(types_overlap(v, b) for v in a['variants'])
    if b['kind'] == 'union': return types_overlap(b, a)
    if a['kind'] == 'enum': return any(value_matches(b, v) for v in a['values'])
    if b['kind'] == 'enum': return types_overlap(b, a)
    ak, bk = a['kind'], b['kind']
    if ak == bk:
        if ak == 'object': return set(a['fields']) == set(b['fields']) and all(types_overlap(v, b['fields'][k]) for k, v in a['fields'].items())
        # Every array/map pair overlaps at the empty collection.
        return True
    if ak == 'map' and bk == 'object': return all(types_overlap(a['values'], v) for v in b['fields'].values())
    if bk == 'map' and ak == 'object': return types_overlap(b, a)
    return False


def validate_type(schema, depth=0):
    if depth > 16: raise ValueError('Type contract nesting limit is 16')
    if not isinstance(schema, dict): raise ValueError('Type contract must be an object')
    kind = schema.get('kind')
    extra = {'array': 'items', 'object': 'fields', 'map': 'values', 'enum': 'values', 'union': 'variants'}
    if kind not in {'string', 'boolean', 'integer', 'null', *extra}: raise ValueError('Unsupported type contract kind')
    contract_fields(schema, {'kind', extra[kind]} if kind in extra else {'kind'}, 'Type schema')
    if kind in {'array', 'map'}: validate_type(schema[extra[kind]], depth + 1)
    elif kind == 'object':
        if not isinstance(schema['fields'], dict): raise ValueError('Object fields must be a map')
        for name, child in schema['fields'].items():
            if not task_identifier(name): raise ValueError('Object field identity is invalid')
            validate_type(child, depth + 1)
    elif kind == 'enum':
        values = schema['values']
        if not isinstance(values, list) or not values or any(type(v) not in (str, bool, int, type(None)) for v in values): raise ValueError('Enum requires scalar alternatives')
        if len({canonical_json_bytes(v) for v in values}) != len(values): raise ValueError('Enum alternatives must be distinct')
    elif kind == 'union':
        values = schema['variants']
        if not isinstance(values, list) or len(values) < 2: raise ValueError('Union requires disjoint alternatives')
        for v in values: validate_type(v, depth + 1)
        if any(types_overlap(a, b) for i, a in enumerate(values) for b in values[i + 1:]): raise ValueError('Union alternatives overlap; disjoint values required')


def validate_selector(value, template=False):
    if not isinstance(value, dict): raise ValueError('Node selector must be an object')
    kind = value.get('kind')
    fields = {'node': {'kind', 'goal', 'node'}, 'member': {'kind', 'goal', 'expansion', 'item', 'generation'}, 'join': {'kind', 'goal', 'expansion'}, 'self': {'kind'}}
    if kind not in fields or kind == 'self' and not template: raise ValueError('Unsupported node selector kind')
    contract_fields(value, fields[kind], 'Node selector')
    if kind == 'self': return
    goal = value['goal']
    if not positive_integer(goal) and goal not in ('#this', '#parent', '#children'): raise ValueError('Selector goal identity must be positive integer or #this/#parent/#children')
    for field in ('node', 'expansion', 'item'):
        if field in value and not task_identifier(value[field]): raise ValueError(f'Selector {field} identity is invalid')
    if kind == 'member' and value['generation'] != 'current' and not positive_integer(value['generation']): raise ValueError('Member generation must be positive or current')


def validate_scope(value, template=False):
    contract_fields(value, {'subject', 'output'}, 'Scope')
    validate_selector(value['subject'], template)
    if not task_identifier(value['output']): raise ValueError('Scope output identity is invalid')


def validate_input(value, template=False):
    contract_fields(value, {'producer', 'output', 'path', 'mode', 'type'}, 'Input')
    producer = value['producer']
    if not isinstance(producer, dict) or set(producer) not in ({'node'}, {'slot'}): raise ValueError('Input producer must name one node selector or external slot')
    if 'node' in producer: validate_selector(producer['node'], template)
    elif not task_identifier(producer['slot']): raise ValueError('Input slot identity is invalid')
    if not task_identifier(value['output']) or value['mode'] not in ('content', 'identity'): raise ValueError('Input output/mode is invalid')
    if not isinstance(value['path'], list): raise ValueError('Input path must be an array')
    for token in value['path']:
        if isinstance(token, str) or type(token) is int and token >= 0: continue
        if template and token == {'item_key': True}: continue
        raise ValueError('Input path supports only typed keys/indexes and template item_key')
    validate_type(value['type'])
    if 'node' in producer:
        selector = producer['node']; aggregate = value['type']
        levels = int(selector.get('goal') == '#children') + int(selector.get('kind') == 'join')
        for _ in range(levels):
            if aggregate.get('kind') != 'map': raise ValueError('Plural input aggregate type must be a canonical map')
            aggregate = aggregate['values']


def validate_graph(graph):
    """Closed declarative grammar; relationship closure is checked by the host."""
    contract_fields(graph, {'nodes', 'task_sets', 'terminals'}, 'Graph')
    if any(not isinstance(graph[k], list) for k in graph): raise ValueError('Graph nodes/task_sets/terminals must be arrays')
    names, sets, definitions = {}, {}, []
    for node in graph['nodes']: definitions.append((node, False))
    for expansion in graph['task_sets']:
        contract_fields(expansion, {'id', 'source', 'template'}, 'TaskSet')
        if not task_identifier(expansion['id']) or expansion['id'] in sets: raise ValueError('Duplicate or invalid task-set identity')
        sets[expansion['id']] = expansion
        validate_input(expansion['source'])
        definitions.append((expansion['template'], True))
    for node, template in definitions:
        contract_fields(node, {'id', 'prompt', 'inputs', 'outputs', 'requires', 'executor', 'independent_of', 'gates', 'resolves', 'permits'}, 'Node')
        name = node['id']
        if not task_identifier(name) or name in names or name in sets: raise ValueError('Duplicate or invalid node/template identity')
        names[name] = node
        if not isinstance(node['prompt'], str) or not node['prompt'].strip(): raise ValueError('Node prompt is required')
        for key in ('inputs', 'outputs'):
            if not isinstance(node[key], dict) or any(not task_identifier(k) for k in node[key]): raise ValueError(f'Node {key} must have unique slot identities')
        for value in node['inputs'].values(): validate_input(value, template)
        for value in node['outputs'].values():
            contract_fields(value, {'type', 'schema'}, 'Output contract')
            if not task_identifier(value['type']) or value['type'] in RESERVED_OUTPUT_TYPES: raise ValueError('Reserved host or invalid output type')
            validate_type(value['schema'])
        executor = node['executor']
        contract_fields(executor, {'role', 'capability', 'resources', 'authority'}, 'Executor')
        if executor['role'] not in ('root', 'worker') or not task_identifier(executor['capability']): raise ValueError('Executor role/capability is invalid')
        if not isinstance(executor['resources'], list) or any(not task_identifier(r) for r in executor['resources']) or len(set(executor['resources'])) != len(executor['resources']): raise ValueError('Executor resources must be unique identities')
        validate_scope(executor['authority'], template)
        for field in ('requires', 'independent_of', 'gates', 'resolves', 'permits'):
            if not isinstance(node[field], list): raise ValueError(f'Node {field} must be an array')
            for value in node[field]:
                if field in ('requires', 'independent_of'): validate_selector(value, template)
                elif field == 'permits':
                    contract_fields(value, {'type', 'scope'}, 'Permit')
                    if not task_identifier(value['type']): raise ValueError('Permit type is invalid')
                    validate_scope(value['scope'], template)
                else: validate_scope(value, template)
    local_goals = {n['executor']['authority']['subject'].get('goal') for n, _ in definitions if n['executor']['authority']['subject'].get('node') == n['id']}
    def local_target(selector):
        if selector['kind'] == 'self': return None
        if selector['goal'] != '#this' and selector['goal'] not in local_goals: return None
        if selector['kind'] == 'node':
            if selector['node'] not in names: raise ValueError('Unknown node reference: ' + selector['node'])
            return selector['node']
        if selector['expansion'] not in sets: raise ValueError('Unknown expansion reference: ' + selector['expansion'])
        return sets[selector['expansion']]['template']['id']
    edges = {name: set() for name in names}
    for node, template in definitions:
        for ref in node['requires'] + [i['producer']['node'] for i in node['inputs'].values() if 'node' in i['producer']]:
            target = local_target(ref)
            if target: edges[node['id']].add(target)
        for ref in node['independent_of']:
            if local_target(ref) == node['id']: raise ValueError('Self independence is unsatisfiable')
        for scoped in [node['executor']['authority'], *node['gates'], *node['resolves'], *(p['scope'] for p in node['permits'])]: local_target(scoped['subject'])
    for expansion in sets.values():
        if 'node' in expansion['source']['producer']:
            target = local_target(expansion['source']['producer']['node'])
            if target: edges[expansion['template']['id']].add(target)
    for ref in graph['terminals']:
        validate_selector(ref); local_target(ref)
    for gated, _ in definitions:
        for resolver, _ in definitions:
            if any(gate == scope for gate in gated['gates'] for scope in resolver['resolves']): edges[gated['id']].add(resolver['id'])
    visiting, visited = set(), set()
    def visit(name):
        if name in visiting: raise ValueError('Graph cycle or unsatisfiable resolver/gate dependency at ' + name)
        if name in visited: return
        visiting.add(name)
        for parent in sorted(edges[name]): visit(parent)
        visiting.remove(name); visited.add(name)
    for name in sorted(names): visit(name)
    return graph


def graph_errors(graph):
    try:
        validate_graph(graph)
    except (ValueError, TypeError, KeyError) as exc:
        return [str(exc)]
    return []


def task_key(node):
    return (node['goal'], node['node'], node.get('item'), node['generation'])


def selected_path(value, path):
    for token in path:
        if isinstance(value, dict) and isinstance(token, str) and token in value:
            value = value[token]
        elif isinstance(value, list) and type(token) is int and 0 <= token < len(value):
            value = value[token]
        else:
            raise ValueError('Selected typed input path is missing')
    return value


# This process-local projection cache is disposable, never authority. Marshal
# preserves mapping order/key types and returns fresh output containers; only
# bytes generated here are decoded. No cache data is read from external storage.
_PROJECTION_CACHE = OrderedDict()
_PROJECTION_CACHE_LOCK = RLock()
_PROJECTION_CACHE_BYTES = 8 * 1024 * 1024


def derive_task_steps(graph, payload, context):
    """Project the exact current snapshot; reuse expanded projections only."""
    if not graph.get('task_sets'):
        return _derive_task_steps(graph, payload, context)
    try:
        key = marshal.dumps((graph, payload, context))
    except (TypeError, ValueError):
        return _derive_task_steps(graph, payload, context)
    if len(key) > _PROJECTION_CACHE_BYTES:
        return _derive_task_steps(graph, payload, context)
    with _PROJECTION_CACHE_LOCK:
        encoded = _PROJECTION_CACHE.get(key)
        if encoded is not None:
            _PROJECTION_CACHE.move_to_end(key)
    if encoded is not None:
        return marshal.loads(encoded)
    value = _derive_task_steps(graph, payload, context)
    try:
        # Do not publish a projection under an input that changed mid-call.
        if marshal.dumps((graph, payload, context)) != key:
            return value
        encoded = marshal.dumps(value)
    except (TypeError, ValueError):
        return value
    if len(key) + len(encoded) <= _PROJECTION_CACHE_BYTES:
        with _PROJECTION_CACHE_LOCK:
            _PROJECTION_CACHE[key] = encoded
            while (len(_PROJECTION_CACHE) > 4 or
                   sum(len(k) + len(v) for k, v in _PROJECTION_CACHE.items()) > _PROJECTION_CACHE_BYTES):
                _PROJECTION_CACHE.popitem(last=False)
    return value


def _derive_task_steps(graph, payload, context):
    """Evaluate an authenticated closed snapshot without provider or clock I/O.

    The host supplies content-addressed artifacts and relationship coverage.
    Results are projections of that snapshot, not a mutable execution cursor.
    """
    # The host has validated the closed JSON snapshot. Avoid recursively
    # revalidating its immutable containers for every node fingerprint.
    def semantic_hash(value):
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        return 'sha256:' + hashlib.sha256(raw).hexdigest()
    goal = context['goal']
    artifacts = dict(context['artifacts'])
    policy = semantic_hash(evidence_policy(context['policy']))
    snapshots = dict(context.get('goals', {}))
    snapshots.setdefault(goal, {'graph': graph, 'payload': payload})
    instances, records, outputs, expansions, memberships = {}, {}, [], {}, {}
    statuses, current, evaluating, expanding = {}, {}, set(), set()
    member_lookup, records_by_node, selector_paths = {}, {}, {}
    verified_artifacts = set()
    def artifact(ref):
        identity = ref['hash']; value = artifacts[identity]
        if identity not in verified_artifacts:
            raw = context.get('published_bytes', {}).get(identity)
            if raw is not None:
                if len(raw) > 1048576 or 'sha256:' + hashlib.sha256(raw).hexdigest() != identity or json.loads(raw) != value: raise ValueError('Published artifact bytes hash mismatch')
            elif semantic_hash(value) != identity: raise ValueError('Artifact content checksum mismatch')
            verified_artifacts.add(identity)
        return value
    def remember(value):
        identity = semantic_hash(value); artifacts[identity] = value
        return {'hash': identity, 'uri': 'urn:' + identity}
    for number, snapshot in snapshots.items():
        records[number] = []
        for ref in snapshot['payload']['evidence']:
            value = artifact(ref)
            if value.get('type') != 'result': raise ValueError('Payload evidence must contain host Result artifacts')
            result = value['content']
            if result['node']['goal'] != number: raise ValueError('Result goal identity mismatch')
            records[number].append((ref, result))
            records_by_node.setdefault(task_key(result['node']), []).append((ref, result))
            for output_ref in result['outputs'].values():
                output = artifact(output_ref)
                if output.get('producer') != result['attempt'] or output.get('provenance', {}).get('actor') != result['executor']:
                    raise ValueError('Result/output producer provenance mismatch')
                outputs.append((output_ref, output, result))
        for index, node in enumerate(snapshot['graph']['nodes']):
            identity = {'goal': number, 'node': node['id'], 'item': None, 'generation': 1}
            instances[task_key(identity)] = {'node': identity, 'contract': node, 'location': ['nodes', index]}
        for index, expansion in enumerate(snapshot['graph']['task_sets']):
            expansions[(number, expansion['id'])] = (expansion, index)
    latest_outputs = {key: {ref['hash'] for ref in rows[-1][1]['outputs'].values()} for key, rows in records_by_node.items()}
    output_owners = {ref['hash']: task_key(result['node']) for rows in records.values() for _, result in rows for ref in result['outputs'].values()}
    obligations = {}
    for ref, output, _ in outputs:
        value = output['content']
        if output['type'] == 'admission':
            finding = artifact(value['finding'])['content']
            obligations[(finding['target']['subject'].get('goal'), finding['id'])] = {'finding': value['finding'], 'content': finding, 'admission': ref, 'applicability': value['applicability']}
        elif output['type'] == 'applicability_assessment':
            finding = artifact(value['finding'])['content']
            key = (finding['target']['subject'].get('goal'), finding['id'])
            prior = obligations.get(key)
            if prior and prior['finding'] == value['finding'] and prior['admission'] == value['admission']:
                obligations[key] = {**prior, 'assessment': ref, 'applicability': value['applicability']}
        elif output['type'] in ('withdrawal', 'retirement') and isinstance(value, dict) and 'finding' in value and value.get('decision') != 'retire_member':
            finding = artifact(value['finding'])['content']
            obligations.pop((finding['target']['subject'].get('goal'), finding['id']), None)
    def relationship(number):
        return snapshots[number].get('relationship', {'parent': {'known': False, 'value': None}, 'children': {'known': False, 'envelopes': {}}})
    def selected_goals(selector, number):
        target = selector['goal']
        if target == '#this': return [number]
        if type(target) is int: return [target]
        relation = relationship(number)
        if target == '#parent':
            if not relation['parent']['known'] or relation['parent']['value'] is None: raise ValueError('Required parent relationship is missing or unknown')
            return [relation['parent']['value']]
        if not relation['children']['known']: raise ValueError('Required children membership completeness is unknown: ' + snapshots[number].get('relationship_error', 'missing provider coverage'))
        return sorted(int(key) for key in relation['children']['envelopes'])
    def targets(selector, number):
        result = []
        for selected in selected_goals(selector, number):
            if selected not in snapshots: raise ValueError(f'Required goal {selected} evidence is unknown')
            if selector['kind'] == 'node': result.append((selected, selector['node'], None, 1)); continue
            expansion_key = (selected, selector['expansion'])
            expand(expansion_key)
            members = memberships.get(expansion_key)
            if members is None: raise ValueError('Selection membership is unresolved')
            if selector['kind'] == 'join': result.extend(members); continue
            generation = selector['generation']
            if generation == 'current':
                match = member_lookup.get((expansion_key, selector['item']))
                matches = [match] if match is not None else []
                if not matches: raise ValueError('Member current generation is missing or retired')
                result.extend(matches)
            else:
                expansion, _ = expansions[expansion_key]
                result.append((selected, expansion['template']['id'], selector['item'], generation))
        return sorted(set(result), key=lambda k: (k[0], k[1], k[2] or '', k[3]))
    def get_input(binding, number):
        producer = binding['producer']; selected = []
        if 'slot' in producer:
            slot = producer['slot']
            if slot == 'relationship_context':
                ref = snapshots[number].get('context_ref')
                if ref is None: raise ValueError('Authenticated relationship context unavailable')
                value = artifact(ref)['content']
            elif slot == 'obligations':
                value = {identifier: {'admission': obligation['admission'],
                                      'finding': obligation['finding'],
                                      'target': obligation['content']['target'],
                                      'applicability': obligation['applicability']}
                         for (target_goal, identifier), obligation in obligations.items()
                         if target_goal == number}
                ref = remember({'type': 'obligation_context', 'content': value, 'producer': None,
                                'provenance': {'actor': 'host', 'source': None, 'policy': policy}})
            else:
                ref = snapshots[number]['payload'][slot]
                value = artifact(ref)['content']
            value = selected_path(value, binding['path']); path = binding['path']
        else:
            selector = producer['node']; selected = targets(selector, number)
            plural = selector['goal'] == '#children'; joining = selector['kind'] == 'join'
            values, sources = {}, {}
            for key in selected:
                evaluate(key)
                if key not in current: raise ValueError('Input producer is not current: ' + str(key))
                output_ref = current[key][1]['outputs'][binding['output']]
                item = selected_path(artifact(output_ref)['content'], binding['path'])
                if plural:
                    child = str(key[0])
                    if joining:
                        values.setdefault(child, {})[key[2]] = item; sources.setdefault(child, {})[key[2]] = output_ref
                    else: values[child] = item; sources[child] = output_ref
                elif joining: values[key[2]] = item; sources[key[2]] = output_ref
                else: value, ref = item, output_ref
            if plural or joining:
                if plural and joining:
                    for child in selected_goals(selector, number): values.setdefault(str(child), {}); sources.setdefault(str(child), {})
                value = values
                ref = remember({'type': 'binding', 'content': {'values': values, 'sources': sources}, 'producer': None,
                                'provenance': {'actor': 'host', 'source': None, 'policy': policy}})
                path = ['values']
            else:
                if len(selected) != 1: raise ValueError('Required singular artifact is missing')
                path = binding['path']
        if not value_matches(binding['type'], value): raise ValueError('Selected input violates its aggregate type contract')
        return ref, value, path, selected
    def expand(key):
        if key in memberships: return
        if key in expanding: raise ValueError('Projected selection dependency cycle')
        if key not in expansions: raise ValueError('Unknown expansion reference')
        expanding.add(key)
        expansion, index = expansions[key]; number = key[0]
        try:
            _, selection, _, _ = get_input(expansion['source'], number)
            if not isinstance(selection, dict) or set(selection) != {'items', 'rationale'} or not isinstance(selection['items'], dict): raise ValueError('Selection contract is unresolved')
            history, active = {}, set()
            producer = expansion['source']['producer'].get('node', {})
            for _, previous in records[number]:
                if previous['node']['node'] != producer.get('node'): continue
                ref = previous['outputs'].get(expansion['source']['output'])
                if ref is None: continue
                prior = selected_path(artifact(ref)['content'], expansion['source']['path'])
                keys = set(prior['items'])
                for item in keys - active: history[item] = history.get(item, 0) + 1
                active = keys
            selected = []
            def compile_template(value):
                if value == {'kind': 'self'}: return lambda item, subject: subject
                if value == {'item_key': True}: return lambda item, subject: item
                if isinstance(value, dict):
                    changed = {name: fn for name, child in value.items() if (fn := compile_template(child)) is not None}
                    if changed: return lambda item, subject: {**value, **{name: fn(item, subject) for name, fn in changed.items()}}
                elif isinstance(value, list):
                    changed = {i: fn for i, child in enumerate(value) if (fn := compile_template(child)) is not None}
                    if changed: return lambda item, subject: [changed[i](item, subject) if i in changed else child for i, child in enumerate(value)]
                return None
            materialize = compile_template(expansion['template'])
            for item in sorted(selection['items']):
                if not task_identifier(item): raise ValueError('Selection item identity is invalid')
                generation = history.get(item, 1)
                identity = {'goal': number, 'node': expansion['template']['id'], 'item': item, 'generation': generation}
                self_selector = {'kind': 'member', 'goal': number, 'expansion': key[1], 'item': item, 'generation': generation}
                node_contract = materialize(item, self_selector) if materialize else expansion['template']
                identity_key = task_key(identity)
                instances[identity_key] = {'node': identity, 'contract': node_contract, 'expansion': key[1], 'location': ['task_sets', index, 'template']}
                selected.append(identity_key)
                member_lookup[(key, item)] = identity_key
            memberships[key] = selected
        except (KeyError, ValueError, TypeError):
            memberships[key] = None
        finally: expanding.remove(key)
    def covers(scope, target, number):
        if scope['output'] != target['output']: return False
        a, b = scope['subject'], target['subject']
        if b.get('goal') not in selected_goals(a, number): return False
        if a['kind'] == 'node': return b['kind'] == 'node' and a['node'] == b['node']
        return b.get('expansion') == a.get('expansion') and (a['kind'] == 'join' or a.get('item') == b.get('item') and (a.get('generation') == 'current' or a.get('generation') == b.get('generation')))
    def obligation_resolved(obligation):
        for _, result in list(current.values()):
            for ref in result['outputs'].values():
                output = artifact(ref)
                if output['type'] != 'resolution': continue
                value = output['content']
                if value['finding'] != obligation['finding'] or value['decision'] != 'resolved': continue
                if value['reviewer_result'] not in [r for r, _ in current.values()]: continue
                accepted = {ref['hash'] for _, item in current.values() for ref in item['outputs'].values()}
                if all(ref['hash'] in accepted for ref in value['subjects']): return True
        return False
    def evaluate(key):
        if key in statuses: return
        if key in evaluating: raise ValueError('Projected qualified-node dependency cycle: ' + str(key))
        if key not in instances: raise ValueError('Unknown or retired qualified node: ' + str(key))
        evaluating.add(key); instance = instances[key]; node = instance['contract']; number = key[0]
        state = {**instance, 'inputs': [], 'values': {}, 'resolutions': [], 'state': 'blocked'}
        contract = semantic_hash({'node': node, 'policy': policy})
        state['contract_hash'] = contract
        try:
            # Accepted finding/admission effects were folded from history above.
            # Their producing Result still obeys ordinary input freshness.
            prerequisites = []
            for selector in node['requires']:
                for parent in targets(selector, number):
                    evaluate(parent)
                    if parent not in current: raise ValueError('Blocked: prerequisite is not current: ' + str(parent) + ': ' + statuses.get(parent, {}).get('reason', 'required evidence is stale or missing'))
                    prerequisites.append(parent)
            for gate in node['gates']:
                for resolver_key, resolver in list(instances.items()):
                    if resolver_key == key: continue
                    if any(covers(gate, scope, number) for scope in resolver['contract']['resolves']): evaluate(resolver_key)
                if any(covers(gate, o['content']['target'], number) and not obligation_resolved(o) for o in obligations.values()): raise ValueError('Unresolved finding/applicability blocks this gate')
            hashes, bound = {}, set()
            for name, binding in sorted(node['inputs'].items()):
                ref, value, path, selected = get_input(binding, number)
                state['inputs'].append({'name': name, 'source': ref, 'path': path, 'mode': binding['mode']})
                state['values'][name] = value; bound.update(selected)
                hashes[name] = ref['hash'] if binding['mode'] == 'identity' else semantic_hash(value)
            # Authorization decisions are explicitly policy-bound content. Bind
            # their producer Result to the same current policy so a policy
            # change reopens ordinary independent/root authorization work while
            # retaining every previous Result as immutable history.
            if any(output.get('type') == 'workspace_authorization' for output in node['outputs'].values()):
                ref = remember({'type': 'policy_context', 'content': {'policy': policy}, 'producer': None,
                                'provenance': {'actor': 'host', 'source': None, 'policy': policy}})
                state['inputs'].append({'name': '__policy', 'source': ref, 'path': [], 'mode': 'identity'})
                hashes['__policy'] = ref['hash']
            if ('workspaces' in context or 'repository_workspace' in node['executor']['resources']) and not context.get('workspace_probe'):
                workspace = context.get('workspaces', {}).get(key)
                if not workspace or 'error' in workspace: raise ValueError((workspace or {}).get('error', 'Workspace allocation/authority is unavailable'))
                ref = workspace['binding']
                # Root's read-only checkout pin guards its live acquisition,
                # not semantic reuse of decisions consuming only declared Refs.
                if not workspace.get('readonly'):
                    state['inputs'].append({'name': '__workspace', 'source': ref, 'path': [], 'mode': 'identity'})
                    hashes['__workspace'] = ref['hash']
                state['workspace'] = workspace
            if 'publications' in context and 'repository_publication' in node['executor']['resources']:
                publication = context['publications'].get(key)
                if not publication or 'error' in publication: raise ValueError((publication or {}).get('error', 'Publication provider context is unavailable'))
                ref = publication['binding']
                state['inputs'].append({'name': '__publication', 'source': ref, 'path': [], 'mode': 'identity'})
                hashes['__publication'] = ref['hash']
                state['publication'] = publication
            # Requires is a currentness gate. Identity dependencies must be
            # declared inputs; unrelated prerequisite Result revisions must not
            # override content-mode reuse once all gates are current again.
            implicit = []
            correction_scope = {'subject': {'kind': 'member', 'goal': number, 'expansion': instance['expansion'], 'item': key[2], 'generation': key[3]} if 'expansion' in instance else {'kind': 'node', 'goal': number, 'node': key[1]}, 'output': None}
            applicable, unresolved = [], False
            for obligation in obligations.values():
                target = obligation['content']['target']
                correction_scope['output'] = target['output']
                if covers(correction_scope, target, number):
                    if obligation['applicability'] == 'unresolved': unresolved = True
                    if obligation['applicability'] == 'applicable': applicable.append(obligation['finding'])
            implicit += [('__correction_' + str(i), ref) for i, ref in enumerate(sorted(applicable, key=lambda r: r['hash']))]
            for name, ref in implicit:
                state['inputs'].append({'name': name, 'source': ref, 'path': [], 'mode': 'identity'}); hashes[name] = ref['hash']
            def locations(value, path=()):
                if isinstance(value, dict):
                    if value.get('kind') in ('node', 'member', 'join') and 'goal' in value:
                        yield path
                    else:
                        for name in sorted(value): yield from locations(value[name], path + (name,))
                elif isinstance(value, list):
                    for i, child in enumerate(value): yield from locations(child, path + (i,))
            path_key = (number, instance.get('expansion'), node['id'])
            if path_key not in selector_paths: selector_paths[path_key] = list(locations(node))
            for path in selector_paths[path_key]:
                selector = selected_path(node, path)
                selected = targets(selector, number)
                state['resolutions'].append({'location': instance['location'] + list(path), 'selector': selector,
                    'context': snapshots[number].get('context_ref'), 'targets': [instances[k]['node'] for k in selected]})
            resolution_semantics = [{'location': r['location'], 'selector': r['selector'], 'targets': r['targets']} for r in state['resolutions']]
            state.update(input_hash=semantic_hash({'node': instance['node'], 'contract': contract, 'inputs': hashes, 'resolutions': resolution_semantics}), state='ready', prerequisites=prerequisites)
            for ref, result in reversed(records_by_node.get(key, [])):
                recorded_policy = artifact(ref).get('provenance', {}).get('policy')
                legacy_contract = semantic_hash({'node': node, 'policy': recorded_policy}) if isinstance(recorded_policy, str) else None
                if task_key(result['node']) != key or result['contract'] not in {contract, legacy_contract}: continue
                legacy = result['contract'] == legacy_contract and result['contract'] != contract
                old_hashes = {}
                for binding in result['inputs']:
                    if binding['name'] == '__workspace' and (context.get('workspace_probe') or 'workspaces' not in context or '__workspace' not in hashes): continue
                    if 'publications' not in context and binding['name'] == '__publication': continue
                    old_hashes[binding['name']] = binding['source']['hash'] if binding['mode'] == 'identity' else semantic_hash(selected_path(artifact(binding['source'])['content'], binding['path']))
                comparable_hashes = dict(hashes)
                # Results created before policy_context existed already carry
                # immutable policy provenance and a legacy contract.  Do not
                # invalidate them merely because the host later introduced
                # this redundant binding; all declared semantic inputs still
                # require exact equality.
                if legacy and '__policy' not in old_hashes:
                    comparable_hashes.pop('__policy', None)
                old_resolutions = [{k: r[k] for k in ('location', 'selector', 'targets')} for r in result.get('resolutions', [])]
                if old_hashes.get('__workspace') != hashes.get('__workspace'): state['reason'] = 'Workspace consumed/acquisition snapshot changed'
                if old_hashes == comparable_hashes and old_resolutions == resolution_semantics:
                    current[key] = (ref, result); state['state'] = 'complete'; state.pop('reason', None); break
            if unresolved and key not in current:
                state['state'] = 'blocked'; raise ValueError('Finding applicability unresolved')
        except (ValueError, KeyError, TypeError) as exc:
            state['reason'] = str(exc)
        finally:
            statuses[key] = state; evaluating.remove(key)
    for key in list(instances): evaluate(key)
    for key in expansions: expand(key)
    for key in list(instances): evaluate(key)
    leases = {task_key(item['node']): item for item in payload['operational']['leases']}
    complete = True
    for selector in graph['terminals']:
        try: complete = complete and all(key in current for key in targets(selector, goal))
        except (ValueError, KeyError): complete = False
    if any(not obligation_resolved(o) for o in obligations.values()): complete = False
    return {'ready': [s for k, s in statuses.items() if k[0] == goal and s['state'] == 'ready' and k not in leases], 'states': statuses, 'current': current, 'leases': leases, 'complete': complete, 'obligations': obligations, 'artifacts': artifacts}
