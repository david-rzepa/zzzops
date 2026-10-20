#!/usr/bin/env python3
"""Repository-scoped release planning, persistence, and boundary operations."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def text_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def _positive(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def new_release_plan(next_release: int = 1) -> dict[str, Any]:
    _positive(next_release, "next_release")
    return {"revision": 0, "next_release": next_release, "assignments": {}, "releases": {}}


def validate_release_plan(plan: Any) -> list[str]:
    errors = []
    if not isinstance(plan, dict): return ["release plan must be an object"]
    try: _positive(plan.get("next_release"), "next_release")
    except ValueError as exc: errors.append(str(exc))
    if not isinstance(plan.get("revision"), int) or isinstance(plan.get("revision"), bool) or plan.get("revision", -1) < 0:
        errors.append("revision must be a non-negative integer")
    assignments = plan.get("assignments")
    if not isinstance(assignments, dict): errors.append("assignments must be an object")
    else:
        for goal, release in assignments.items():
            if not isinstance(goal, str) or not goal.isdigit() or int(goal) < 1: errors.append("assignment goals must be positive integer strings")
            try: _positive(release, "assignment release")
            except ValueError as exc: errors.append(str(exc))
    if not isinstance(plan.get("releases"), dict): errors.append("releases must be an object")
    return errors


def open_release_ids(plan: dict[str, Any]) -> list[int]:
    values = set(plan.get("assignments", {}).values())
    values.update(int(key) for key, value in plan.get("releases", {}).items()
                  if value.get("state") != "branch_confirmed")
    return sorted(values or {plan["next_release"]})


def target_release(plan: dict[str, Any], goal: int) -> int:
    explicit = plan.get("assignments", {}).get(str(goal))
    if explicit is not None: return explicit
    for release_id, release in plan.get("releases", {}).items():
        if str(goal) in release.get("members", {}): return int(release_id)
    current = plan["next_release"]
    release = plan.get("releases", {}).get(str(current), {})
    return current + 1 if release.get("state") in {"frozen_intent", "branch_confirmed"} else current


def assign_release(plan: dict[str, Any], goal: int, release: int, *, expected_revision: int) -> dict[str, Any]:
    _positive(goal, "goal"); _positive(release, "release")
    if plan.get("revision") != expected_revision: raise ValueError("release plan revision changed")
    result = copy.deepcopy(plan); result.setdefault("assignments", {})[str(goal)] = release
    result["revision"] = expected_revision + 1
    return result


def batch_assign(plan, assignments, *, expected_revision):
    if not isinstance(assignments, list) or not assignments: raise ValueError("assignments must be a non-empty list")
    seen = set()
    for item in assignments:
        if not isinstance(item, dict) or set(item) != {"goal", "release"}: raise ValueError("assignment must contain goal and release")
        _positive(item["goal"], "goal"); _positive(item["release"], "release")
        if item["goal"] in seen: raise ValueError("duplicate assignment goal")
        seen.add(item["goal"])
    if plan.get("revision") != expected_revision: raise ValueError("release plan revision changed")
    result = copy.deepcopy(plan)
    for item in assignments: result.setdefault("assignments", {})[str(item["goal"])] = item["release"]
    result["revision"] = expected_revision + 1
    return {"plan": result, "items": [{**item, "status": "applied"} for item in assignments]}


def freeze_membership(plan, release, members):
    _positive(release, "release")
    result = copy.deepcopy(plan); key = str(release); current = result.setdefault("releases", {}).get(key)
    exact = {str(goal): sha for goal, sha in sorted(members.items())}
    if current and current.get("members") != exact: raise ValueError("frozen membership cannot change")
    result["releases"][key] = {**(current or {}), "state": "frozen_intent", "members": exact}
    return result


def _same_plan(record, plan):
    return all(record.get(key) == plan.get(key) for key in ("revision", "next_release", "assignments", "releases"))


def _result(record, status="applied"):
    plan = {key: copy.deepcopy(record[key]) for key in ("revision", "next_release", "assignments", "releases")}
    return {**copy.deepcopy(record), "status": status, "plan": plan}


def persist_plan(adapter, repository, plan, *, expected_revision, request_id):
    errors = validate_release_plan(plan)
    if errors: raise ValueError("invalid release plan: " + "; ".join(errors))
    adapter.acquire_repository_lock(repository, request_id)
    try:
        current = adapter.read(repository)
        if expected_revision is None:
            if current is not None:
                if current.get("request_id") == request_id and _same_plan(current, plan): return _result(current)
                raise ValueError("duplicate release control record conflicts with request")
            record = {"kind": "release-plan", **copy.deepcopy(plan), "request_id": request_id}
            try: adapter.create_only(repository, record)
            except TimeoutError:
                observed = adapter.read(repository)
                return _result(observed) if observed and _same_plan(observed, record) else {**record, "status": "pending", "plan": copy.deepcopy(plan)}
        else:
            if current is None or current.get("revision") != expected_revision: raise ValueError("release plan revision changed")
            record = {"kind": "release-plan", **copy.deepcopy(plan), "request_id": request_id}
            try: adapter.compare_exchange(repository, expected_revision, record)
            except TimeoutError:
                observed = adapter.read(repository)
                return _result(observed) if observed and _same_plan(observed, record) else {**record, "status": "pending", "plan": copy.deepcopy(current)}
        artifact = {"request_id": request_id, "revision": record["revision"], "plan_digest": digest(plan)}
        adapter.append_artifact(repository, artifact)
        return _result(record)
    finally:
        adapter.release_repository_lock(repository, request_id)


def persist_batch_assignments(adapter, repository, assignments, *, expected_revision, request_id):
    # Validate the complete batch before the first effect.
    batch_assign({"revision": expected_revision, "next_release": 1, "assignments": {}, "releases": {}}, assignments,
                 expected_revision=expected_revision)
    current = adapter.read(repository)
    if current is None: raise ValueError("release plan is missing")
    items = []
    revision = expected_revision
    for index, item in enumerate(assignments):
        observed = adapter.read(repository)
        already = observed.get("assignments", {}).get(str(item["goal"])) == item["release"]
        if already:
            items.append({**item, "status": "applied"}); revision = observed["revision"]; continue
        if observed["revision"] != revision: raise ValueError("release plan revision changed")
        desired = assign_release(observed, item["goal"], item["release"], expected_revision=revision)
        outcome = persist_plan(adapter, repository, desired, expected_revision=revision,
                               request_id=f"{request_id}:{index}")
        if outcome["status"] == "pending":
            items.append({**item, "status": "pending"})
            items.extend({**rest, "status": "pending"} for rest in assignments[index + 1:])
            break
        items.append({**item, "status": "applied"}); revision = desired["revision"]
    return {"plan": {k: copy.deepcopy(adapter.read(repository)[k]) for k in ("revision", "next_release", "assignments", "releases")}, "items": items,
            "request_id": request_id}


def capture_assignment_result(*, goal, assignment, target_release, error, request_id):
    return {"status": "created_pending_assignment" if assignment is None else "created_assignment_reconciled",
            "goal": copy.deepcopy(goal), "pending_assignment": {"goal": goal["number"], "release": target_release},
            "error": error, "request_id": request_id}


def select_release_work(records, release_policy, plan, owned):
    priority = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    if not release_policy.get("enabled"):
        return {"ordered": [{"goal": r["key"], "reason": "priority_then_key"} for r in sorted(records, key=lambda x: (priority.get(x["priority"], 9), x["key"]))], "conflicts": []}
    active = plan["next_release"]; targets = {r["key"]: r.get("target_release", target_release(plan, r["key"])) for r in records}
    conflicts = []
    for record in records:
        for dep in record.get("depends_on", []):
            if targets.get(dep, active) > targets[record["key"]]:
                conflicts.append({"code": "future_release_dependency", "goal": record["key"], "dependency": dep})
    blocked_goals = {c["goal"] for c in conflicts}
    active_rows = [r for r in records if targets[r["key"]] == active and r["key"] not in owned and r["key"] not in blocked_goals
                   and r.get("work_state") in {"triage", "prepare", "write"}
                   and not any(next((candidate for candidate in records if candidate["key"] == dep), {}).get("status") not in {"done", "cancelled"}
                               for dep in r.get("depends_on", []))]
    rows, reason = active_rows, "active_release_priority"
    if not rows and release_policy.get("execution_scope") == "later_when_active_blocked":
        rows = [r for r in records if targets[r["key"]] > active and r["key"] not in owned and r.get("work_state") in {"triage", "prepare", "write"}]
        reason = "later_release_active_blocked"
    rows.sort(key=lambda x: (priority.get(x["priority"], 9), x["key"]))
    return {"ordered": [{"goal": r["key"], "reason": reason, "release": targets[r["key"]]} for r in rows], "conflicts": conflicts}


def authorize_integration(goal, plan, *, source_branch, source_ancestors):
    release = goal.get("target_release", target_release(plan, goal["key"]))
    if release > plan["next_release"]:
        return {"status": "blocked", "code": "future_release_integration", "goal": goal["key"], "release": release}
    return {"status": "authorized", "release": release}


def release_readiness(members, *, active_owners, observed_commits, source_ancestors, forbidden_commits=()):
    if not members: return {"status": "empty", "code": "empty_release"}
    if active_owners: return {"status": "blocked", "code": "active_owner"}
    if set(source_ancestors) & set(forbidden_commits): return {"status": "blocked", "code": "future_release_provenance"}
    for key, member in members.items():
        if member.get("status") == "cancelled":
            if not member.get("cancellation_authority"): return {"status": "blocked", "code": "missing_removal_authority", "goal": key}
            continue
        if member.get("status") != "done" or not member.get("integrated_commit"):
            return {"status": "blocked", "code": "member_incomplete", "goal": key}
        sha = member["integrated_commit"]
        if sha not in observed_commits: return {"status": "blocked", "code": "missing_integration_evidence", "goal": key}
        if sha not in source_ancestors: return {"status": "blocked", "code": "source_provenance_mismatch", "goal": key}
    return {"status": "ready"}


def freeze_intent(*, repository, release, members, policy, source_branch, source_sha, destination, authority,
                  source_ancestors=None, forbidden_commits=()):
    if source_ancestors is not None and set(source_ancestors) & set(forbidden_commits): raise ValueError("future release provenance in source")
    content = {"repository": repository, "release": release, "members": {str(k): v for k, v in sorted(members.items())},
               "policy": policy, "source_branch": source_branch, "source_sha": source_sha,
               "destination": destination, "authority": authority}
    return {**content, "digest": digest(content)}


def revalidate_frozen_intent(intent, *, source_sha, members):
    if source_sha != intent["source_sha"]: return {"status": "blocked", "code": "source_drift"}
    if {str(k): v for k, v in members.items()} != intent["members"]: return {"status": "blocked", "code": "membership_drift"}
    return {"status": "ready"}


def bind_publication_approval(frozen, *, target):
    content = {"release_digest": frozen["digest"], "source_sha": frozen["source_sha"], "target": target, "decision": "approved"}
    return {**content, "digest": digest(content)}


def approval_matches(approval, frozen, *, target):
    return isinstance(approval, dict) and approval == bind_publication_approval(frozen, target=target)


def record_publication(frozen, observation):
    if not isinstance(observation, dict) or set(observation) != {"tag", "version", "target_sha"} or observation["target_sha"] != frozen["source_sha"]:
        raise ValueError("publication observation is incomplete or does not match frozen release")
    return {"release": frozen["release"], **copy.deepcopy(observation)}


def observe_publication(provider, frozen, approval_reference, *, target):
    if not isinstance(approval_reference, str): raise ValueError("authenticated approval reference is required")
    approval = provider.observe_approval(approval_reference)
    if not approval_matches(approval, frozen, target=target): raise ValueError("publication approval is stale")
    return record_publication(frozen, provider.observe(frozen["repository"], frozen["release"], target))


def create_branch_reconciled(adapter, branch, sha):
    before = adapter.observe(branch)
    if before is not None:
        if before == sha: return {"status": "confirmed", "branch": branch, "sha": sha}
        raise ValueError("release branch different-SHA conflict")
    try: adapter.create_only(branch, sha)
    except TimeoutError:
        observed = adapter.observe(branch)
        return ({"status": "confirmed", "branch": branch, "sha": sha} if observed == sha
                else {"status": "pending", "branch": branch, "sha": sha})
    return {"status": "created", "branch": branch, "sha": sha}


class GitReleaseBranchAdapter:
    def __init__(self, repo: Path, remote="origin"): self.repo, self.remote = Path(repo), remote
    def _git(self, *args): return subprocess.run(["git", *args], cwd=self.repo, text=True, capture_output=True, check=False)
    def observe(self, branch):
        result = self._git("ls-remote", "--heads", self.remote, f"refs/heads/{branch}")
        if result.returncode: raise ValueError("Git remote branch observation failed")
        return result.stdout.split()[0] if result.stdout.strip() else None
    def create_only(self, branch, sha):
        observed = self.observe(branch)
        if observed:
            if observed == sha: return {"status": "confirmed", "branch": branch, "sha": sha}
            raise ValueError("release branch different-SHA conflict")
        result = self._git("push", self.remote, f"{sha}:refs/heads/{branch}")
        if result.returncode:
            observed = self.observe(branch)
            if observed == sha: return {"status": "confirmed", "branch": branch, "sha": sha}
            raise ValueError("Git did not confirm create-only release branch")
        return {"status": "created", "branch": branch, "sha": sha}


GitHubReleaseBranchAdapter = GitReleaseBranchAdapter


class GitHubReleasePlanAdapter:
    """Release control record over a GitHub issue/comment/label transport."""
    MARKER = "<!-- zzzops-release-plan -->"
    def __init__(self, transport): self.transport = transport
    def _records(self, repository): return self.transport.list_control_issues(repository, self.MARKER)
    def read(self, repository):
        rows = self._records(repository)
        if len(rows) > 1: raise ValueError("duplicate release control records")
        if not rows: return None
        try: return json.loads(rows[0]["body"].split(self.MARKER, 1)[1].strip())
        except (KeyError, json.JSONDecodeError) as exc: raise ValueError("release control record is malformed") from exc
    def acquire_repository_lock(self, repository, request_id): self.transport.acquire_label_lock(repository, "zzzops-release-plan-lock", request_id)
    def release_repository_lock(self, repository, request_id): self.transport.release_label_lock(repository, "zzzops-release-plan-lock", request_id)
    def create_only(self, repository, record):
        if self._records(repository): raise ValueError("duplicate release control record")
        body = self.MARKER + "\n" + canonical(record)
        return self.transport.create_issue(repository, {"title": "ZzzOps release plan", "body": body, "labels": ["zzzops-release-plan-control"]})
    def compare_exchange(self, repository, expected_revision, record):
        rows = self._records(repository)
        if len(rows) != 1: raise ValueError("duplicate or missing release control record")
        current = self.read(repository)
        if current["revision"] != expected_revision: raise ValueError("release plan revision changed")
        body = self.MARKER + "\n" + canonical(record)
        return self.transport.update_issue(repository, rows[0]["number"], {"body": body}, text_hash(rows[0]["body"]))
    def append_artifact(self, repository, artifact):
        rows = self._records(repository)
        if len(rows) != 1: raise ValueError("release control record missing for audit")
        self.transport.append_comment(repository, rows[0]["number"], canonical({"kind": "zzzops-release-audit", **artifact}))
    def observe_release(self, repository, release): return self.transport.observe_release(repository, release)


class ReleaseCoordinator:
    def __init__(self, repository, policy, plan_adapter, branch_provider, evidence_provider=None):
        self.repository, self.policy, self.plans, self.branches = repository, policy, plan_adapter, branch_provider
        self.evidence = evidence_provider or plan_adapter
        self._receipts = {}
    def checkpoint(self, request):
        request_id = request["request_id"]; identity = digest(request)
        if request_id in self._receipts:
            prior_identity, result = self._receipts[request_id]
            if prior_identity != identity: raise ValueError("request id payload changed")
            return copy.deepcopy(result)
        plan = self.plans.read(self.repository)
        operation = request["operation"]
        observed = self.evidence.observe_release(self.repository, plan["next_release"]) if hasattr(self.evidence, "observe_release") else request
        if operation == "propose":
            ready = release_readiness(observed["members"], active_owners=set(observed["active_owners"]),
                observed_commits=set(observed["observed_commits"]), source_ancestors=set(observed["source_ancestors"]),
                forbidden_commits=set(observed.get("forbidden_commits", [])))
            if ready["status"] != "ready": return ready
            members = {int(k): v["integrated_commit"] for k, v in observed["members"].items() if v.get("status") == "done"}
            intent = freeze_intent(repository=self.repository, release=plan["next_release"], members=members,
                policy=digest(self.policy), source_branch=observed["source_branch"], source_sha=observed["source_sha"],
                destination=self.policy["release_branch_prefix"] + str(plan["next_release"]), authority=request["authority"])
            result = {"status": "ready_proposal", "proposal": {"intent": intent, "source_sha": observed["source_sha"], "members": members}}
        elif operation == "freeze":
            proposal = request["proposal"].get("proposal", request["proposal"])
            intent = proposal["intent"]
            updated = copy.deepcopy(plan); updated.setdefault("releases", {})[str(plan["next_release"])] = {"state": "frozen_intent", "intent": intent, "members": intent["members"]}; updated["revision"] += 1
            persist_plan(self.plans, self.repository, updated, expected_revision=plan["revision"], request_id=request_id)
            result = {"status": "frozen_intent", "intent": intent}
        elif operation == "cut":
            intent = request["intent"]
            observed_members = {str(k): (v if isinstance(v, str) else v["integrated_commit"])
                                for k, v in observed["members"].items()
                                if isinstance(v, str) or v.get("status") == "done"}
            check = revalidate_frozen_intent(intent, source_sha=observed["source_sha"], members=observed_members)
            if check["status"] != "ready": return check
            self.plans.acquire_repository_lock(self.repository, request_id)
            try:
                branch = create_branch_reconciled(self.branches, intent["destination"], intent["source_sha"])
                if branch["status"] == "pending": return branch
                current = self.plans.read(self.repository); updated = copy.deepcopy(current)
                updated["releases"][str(intent["release"])]["state"] = "branch_confirmed"
                updated["next_release"] = intent["release"] + 1; updated["revision"] += 1
                self.plans.compare_exchange(self.repository, current["revision"], {"kind": "release-plan", **updated, "request_id": request_id})
                self.plans.append_artifact(self.repository, {"request_id": request_id, "revision": updated["revision"], "plan_digest": digest(updated)})
                result = {"status": "branch_confirmed", "release": intent["release"], "branch": intent["destination"], "sha": intent["source_sha"]}
            finally: self.plans.release_repository_lock(self.repository, request_id)
        else: raise ValueError("unknown release checkpoint operation")
        self._receipts[request_id] = (identity, copy.deepcopy(result)); return result
