"""Pure, content-addressed phase evidence and DAG eligibility evaluation."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any


PHASE_EVIDENCE_SCHEMA_VERSION = 1
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
    return {"schema_version": PHASE_EVIDENCE_SCHEMA_VERSION, "records": {}, "withdrawals": []}


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
        "repository", "provider", "capabilities", "invocation", "upstream_outputs",
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
    }


def phase_input_envelope(
    phase: str, goal_spec: str, policy: str, phase_dag: str, *,
    parents: list[dict[str, Any]] | None = None, dependencies: list[dict[str, Any]] | None = None,
    repository: dict[str, Any] | None = None, provider: dict[str, Any] | None = None,
    capabilities: dict[str, Any] | None = None, invocation: dict[str, Any] | None = None,
    upstream_outputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one phase's declared input envelope; array order remains declared."""
    envelope = {
        "schema_version": PHASE_EVIDENCE_SCHEMA_VERSION, "phase": _text(phase, "phase"),
        "goal_spec": _sha256(goal_spec, "goal_spec"), "policy": _sha256(policy, "policy"),
        "phase_dag": _sha256(phase_dag, "phase_dag"), "parents": copy.deepcopy(parents or []),
        "dependencies": copy.deepcopy(dependencies or []), "repository": copy.deepcopy(repository),
        "provider": copy.deepcopy(provider), "capabilities": copy.deepcopy(capabilities),
        "invocation": copy.deepcopy(invocation), "upstream_outputs": copy.deepcopy(upstream_outputs or []),
    }
    return _input_envelope(envelope, phase)


def goal_spec_digest(goal: dict[str, Any], *, title: str, human_spec: str) -> str:
    """Hash semantic scope, deliberately excluding operational goal revisions."""
    if not isinstance(goal, dict):
        raise PhaseEvidenceError("goal specification must be an object")
    semantic = {
        "title": _text(title, "title"), "human_spec": _text(human_spec, "human_spec"),
        "priority": goal.get("priority"), "value": goal.get("value"), "difficulty": goal.get("difficulty"),
        "confidence": goal.get("confidence"), "parent": goal.get("parent"),
        "depends_on": goal.get("depends_on"), "resources": goal.get("resources"),
        "engineering_rigor": goal.get("engineering_rigor"),
    }
    return sha256_digest({"schema_version": PHASE_EVIDENCE_SCHEMA_VERSION, "goal_spec": semantic})


def _record(value: Any, phase: str) -> dict[str, Any]:
    fields = {"status", "input_envelope", "input_hash", "output", "verification", "routing", "review", "selection", "actor", "not_required"}
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
        "review": _artifact(value.get("review"), f"phase record {phase}.review"),
        "selection": copy.deepcopy(value.get("selection")),
        "actor": _text(value.get("actor"), f"phase record {phase}.actor"), "not_required": copy.deepcopy(value.get("not_required")),
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
    return result


def normalize_phase_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schema_version", "records", "withdrawals"}:
        raise PhaseEvidenceError("phase evidence has invalid fields")
    if value.get("schema_version") != PHASE_EVIDENCE_SCHEMA_VERSION:
        raise PhaseEvidenceError("phase evidence schema version is invalid")
    records, withdrawals = value.get("records"), value.get("withdrawals")
    if not isinstance(records, dict) or not isinstance(withdrawals, list):
        raise PhaseEvidenceError("phase evidence records and withdrawals are required")
    normalized = empty_phase_evidence()
    for phase, record in records.items():
        _text(phase, "phase identifier")
        normalized["records"][phase] = _record(record, phase)
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


def record_phase_result(evidence: Any, phase: str, record: Any, current_input: dict[str, Any]) -> dict[str, Any]:
    """Return updated evidence only when a submitted result matches current inputs."""
    normalized, phase = normalize_phase_evidence(evidence), _text(phase, "phase")
    normalized_record = _record(record, phase)
    current = _input_envelope(current_input, phase)
    if normalized_record["input_hash"] != sha256_digest(current) or normalized_record["input_envelope"] != current:
        raise PhaseEvidenceError("phase result input evidence is stale")
    normalized["records"][phase] = normalized_record
    normalized["withdrawals"] = [item for item in normalized["withdrawals"] if item["phase"] != phase]
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
        return {"eligible": [], "stale": [], "blocked": [], "diagnostics": ["terminal_goal"]}
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
    return {"eligible": eligible, "stale": stale, "blocked": blocked, "diagnostics": diagnostics}
