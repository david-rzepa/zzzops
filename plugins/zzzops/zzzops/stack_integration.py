"""Deterministic, resumable planning for provider-backed pull-request stacks."""
from __future__ import annotations

import copy
import hashlib
import json

MAX_PROVIDER_RESPONSE = 1024 * 1024
MAX_DIAGNOSTIC = 64 * 1024
STATUS_PAGE_SIZE = 50


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value):
    return "sha256:" + hashlib.sha256(_canonical(value).encode()).hexdigest()


def _ordered(observed, target):
    by_branch = {}
    for row in observed:
        branch = row.get("branch")
        if not branch or branch in by_branch:
            raise ValueError("duplicate provider stack member")
        by_branch[branch] = row
    children = {}
    for row in observed:
        children.setdefault(row.get("base"), []).append(row)
    ordered, seen, base = [], set(), target
    while children.get(base):
        candidates = children[base]
        if len(candidates) != 1:
            raise ValueError("provider topology is not a linear stack")
        row = candidates[0]
        branch = row["branch"]
        if branch in seen:
            raise ValueError("cycle in provider stack topology")
        seen.add(branch); ordered.append(row); base = branch
    if len(ordered) != len(observed):
        raise ValueError("provider topology is incomplete or cyclic")
    return ordered


def _validate_member(row, repository=None):
    if repository is not None and row.get("repository", repository) != repository:
        raise ValueError("stack member belongs to another repository")
    if row.get("implementation_review") != "current":
        raise ValueError("stack member implementation review is stale")
    if row.get("ci") != "verified":
        raise ValueError("stack member CI checks are not verified")
    if row.get("release") != "eligible":
        raise ValueError("stack member release is blocked")
    if row.get("owner"):
        raise ValueError("stack member has a live owner lease")


def prepare_plan(request, *, observed, revision, existing=None, page=None):
    """Freeze a complete provider-derived stack, or return a paging checkpoint."""
    proposal = copy.deepcopy(request)
    if existing is not None:
        if revision < existing.get("revision", 0):
            raise ValueError("stale stack plan revision")
        if existing.get("request_id") == proposal.get("request_id"):
            if existing.get("request_hash") != _hash(proposal):
                raise ValueError("request payload conflict")
            return copy.deepcopy(existing)
    submitted = proposal.get("members") or []
    for row in submitted:
        if row.get("repository", proposal.get("repository")) != proposal.get("repository"):
            raise ValueError("submitted stack member belongs to another repository")
    submitted_keys = [(row.get("goal"), row.get("branch")) for row in submitted]
    if len(set(submitted_keys)) != len(submitted_keys):
        raise ValueError("duplicate submitted stack member")
    if page and not page.get("complete", True):
        result = {"version": 1, "state": "collecting_membership",
                  "request_id": proposal.get("request_id"), "request_hash": _hash(proposal),
                  "repository": proposal.get("repository"), "target": proposal.get("target"),
                  "method": proposal.get("method"), "revision": revision,
                  "members": copy.deepcopy(observed), "continuation": page.get("cursor")}
        result["plan_id"] = _hash({k: v for k, v in result.items() if k != "plan_id"})
        return result
    ordered = _ordered(observed, proposal.get("target"))
    observed_keys = {(row.get("goal"), row.get("branch")) for row in ordered}
    if set(submitted_keys) != observed_keys or len(submitted) != len(ordered):
        raise ValueError("submitted members do not match complete provider membership")
    repository = proposal.get("repository")
    members = []
    for row in ordered:
        _validate_member(row, repository)
        item = copy.deepcopy(row); item["status"] = "pending"; members.append(item)
    result = {"version": 1, "state": "prepared", "request_id": proposal.get("request_id"),
              "request_hash": _hash(proposal), "repository": repository,
              "target": proposal.get("target"), "method": proposal.get("method"),
              "revision": revision, "member_count": len(members), "members": members}
    result["plan_id"] = _hash({k: v for k, v in result.items() if k != "plan_id"})
    return result


def _current_member(plan):
    return next((row for row in plan.get("members", [])
                 if row.get("status") not in ("observed", "reconciled")), None)


def _validate_facts(plan, facts):
    if facts.get("reservation") != "owned":
        raise ValueError("repository publication reservation is not owned")
    if facts.get("prior_process") != "stopped":
        raise ValueError("prior publication process is still live")
    if facts.get("root") != "current":
        raise ValueError("root authorization is not current")
    current = facts.get("members") or []
    frozen = plan.get("members") or []
    if len(current) != len(frozen):
        raise ValueError("stack membership changed")
    for expected, actual in zip(frozen, current):
        if expected.get("goal") != actual.get("goal") or expected.get("head") != actual.get("head"):
            raise ValueError("stack member head changed")
        if expected.get("base") != actual.get("base") or expected.get("base_head") != actual.get("base_head"):
            raise ValueError("stack member base changed")
        _validate_member(actual, plan.get("repository"))


def advance_plan(plan, *, facts, capability):
    """Choose at most one authorized transport action from fresh facts."""
    result = copy.deepcopy(plan)
    if facts.get("response_bytes", 0) > MAX_PROVIDER_RESPONSE:
        raise ValueError("provider response exceeds 1 MiB limit")
    if facts.get("control_body_bytes", 0) >= MAX_PROVIDER_RESPONSE:
        raise ValueError("control body exceeds storage capacity budget")
    _validate_facts(result, facts)
    if facts.get("storage_capacity", True) is False:
        result["next_action"] = "storage_blocked"; result.pop("dispatch", None); return result
    member = _current_member(result)
    if member is None:
        result["next_action"] = "complete"; return result
    native = (capability.get("installed") and capability.get("membership_verified") and
              capability.get("atomic_prefix") and capability.get("expected_head_guard") and
              capability.get("method") == result.get("method") and
              not capability.get("admin_required") and facts.get("all_effect_ready"))
    if native:
        pending = [r for r in result["members"] if r.get("status") == "pending"]
        dispatch = {"goals": [r["goal"] for r in pending],
                    "expected_heads": [r["head"] for r in pending], "method": result["method"]}
        transport = "native"
    else:
        dispatch = {"goal": member["goal"], "pr": member.get("pr"),
                    "expected_head": member["head"], "method": result["method"]}
        command = ["gh", "pr", "merge", str(member.get("pr")),
                   "--" + result["method"], "--match-head-commit", member["head"]]
        if facts.get("repository_requires_admin"):
            authority = facts.get("admin_authorization") or {}
            if (authority.get("repository") != result.get("repository") or
                    authority.get("pr") != member.get("pr") or
                    authority.get("expected_head") != member.get("head")):
                raise ValueError("admin authorization scope does not match effect")
            command.append("--admin")
        dispatch["command"] = command; transport = "sequential"
    result["transport"] = transport; result["dispatch"] = dispatch
    diagnostic = str(facts.get("provider_output", ""))
    truncated = len(diagnostic) > MAX_DIAGNOSTIC
    attempt = {"goal": member["goal"], "head": member["head"], "status": "intent",
               "diagnostic": diagnostic[:MAX_DIAGNOSTIC], "diagnostic_truncated": truncated}
    outcome = facts.get("provider_outcome")
    if outcome in ("timeout", "unknown", "queued"):
        attempt["status"] = "unresolved"; result["next_action"] = "observe"
    elif outcome == "merged" and facts.get("receipt_write") == "failed":
        attempt["status"] = "unresolved"; result["next_action"] = "observe"
    else:
        result["next_action"] = "dispatch"
    result["attempt"] = attempt
    return result


def observe_attempt(plan, *, provider):
    result = copy.deepcopy(plan); result.pop("dispatch", None)
    for row in result.get("members", []):
        state = provider.get(str(row.get("goal")), provider.get(row.get("goal")))
        if state == "merged":
            row["status"] = "observed"
    attempted = result.get("attempt")
    if attempted and provider.get(str(attempted.get("goal"))) == "merged":
        attempted["status"] = "observed"
    result["next_action"] = "reconcile" if any(r.get("status") == "observed" for r in result.get("members", [])) else "observe"
    return result


def reconcile_plan(plan, *, goal, semantic_complete=False, error=None):
    result = copy.deepcopy(plan); result.pop("dispatch", None)
    if error:
        result["next_action"] = "retry_reconciliation"; return result
    for row in result.get("members", []):
        if row.get("goal") == goal and semantic_complete:
            row["status"] = "reconciled"
    result["next_action"] = "advance" if semantic_complete else "await_phase_evidence"
    return result


def status_page(plan, *, limit=STATUS_PAGE_SIZE, cursor=0):
    limit = min(max(int(limit), 1), STATUS_PAGE_SIZE); start = max(int(cursor or 0), 0)
    members = copy.deepcopy(plan.get("members", [])[start:start + limit])
    result = {k: copy.deepcopy(v) for k, v in plan.items() if k not in ("members", "dispatch")}
    result["members"] = members
    result["continuation"] = start + limit if start + limit < len(plan.get("members", [])) else None
    return result
