"""Provider merge-state classification for exact, authority-safe goal reconciliation."""

from __future__ import annotations

from typing import Any


def classify_pr_merge(record: dict[str, Any], pull_request: dict[str, Any] | None, repository: str) -> dict[str, Any]:
    """Classify a goal's implementation PR without mutating goal state."""
    implementation = record.get("implementation") if isinstance(record, dict) else None
    review = implementation.get("review") if isinstance(implementation, dict) else None
    if not isinstance(implementation, dict) or not isinstance(review, dict) or not implementation.get("pr"):
        return {"status": "unavailable", "reasons": ["implementation_pr_missing"]}
    if not isinstance(pull_request, dict):
        return {"status": "unavailable", "reasons": ["provider_pr_state_missing"]}
    if pull_request.get("merged") is not True:
        return {"status": "open", "reasons": ["pr_not_merged"]}

    reasons: list[str] = []
    if pull_request.get("repository") != repository:
        reasons.append("repository_mismatch")
    if pull_request.get("base_ref") != implementation.get("target"):
        reasons.append("target_branch_mismatch")
    if pull_request.get("head_oid") != review.get("checkpoint"):
        reasons.append("reviewed_head_mismatch")
    if not pull_request.get("merge_commit") or not pull_request.get("merged_at"):
        reasons.append("merge_evidence_incomplete")
    if pull_request.get("checks_verified") is not True:
        reasons.append("required_checks_unverified")
    if pull_request.get("review_verified") is not True:
        reasons.append("review_evidence_unverified")
    if reasons:
        return {"status": "merged_stale", "reasons": reasons}
    return {
        "status": "merged_verified",
        "reasons": [],
        "merge_commit": pull_request["merge_commit"],
        "head_oid": pull_request["head_oid"],
    }
