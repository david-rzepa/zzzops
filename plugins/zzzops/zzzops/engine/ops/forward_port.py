"""Prepare and complete an independently approved maintenance forward-port."""

from __future__ import annotations

import json

from engine.gh import GhError
from engine.canon import iso
from engine.ops.lines import merge_pr, parents
from engine.ops.run import Blocked, Done


def blocked(reason, question, state=None):
    result = {"category": "decision", "waiting_for": "human", "reason": reason, "question": question}
    if state is not None:
        result["op_state"] = state
    return Blocked(result)


def observed(ctx, details):
    s = ctx.session
    tips = s.fetch_branches([details["destination"], details["carrier"]])
    return {"source_goal_commit": s.snap.goals.get(details["source_goal"]),
            "destination_tip": tips.get(details["destination"]), "head": tips.get(details["carrier"])}


def prepare(ctx, details):
    o = observed(ctx, details)
    if o["source_goal_commit"] != details["source_goal_commit"]:
        return blocked("source_provenance_changed", "The maintenance source changed; review its recorded provenance.")
    dest, head, source = details["destination"], o["head"], details["source_tip"]
    base = o["destination_tip"]
    if (not base or not head or not ctx.git.is_ancestor(details["released_base"], base)
            or not ctx.git.is_ancestor(source, head)):
        return blocked("destination_or_carrier_invalid", "The destination or carrier is missing or has unrelated history.")
    evidence = {**details, "destination_tip": base, "head": head}
    if ctx.git.is_ancestor(source, base):
        evidence.update(kind="already_in_history", proof=f"git merge-base --is-ancestor {source} {base}",
                        limitation="History does not prove the changes remain effective after a revert.")
        return Done({"evidence": evidence}, ok=True)
    try:
        prs = ctx.gh.json("pr", "list", "--base", dest, "--state", "all", "--json",
                          "number,state,headRefOid,headRefName,baseRefName,mergeCommit,url") or []
    except GhError:
        return blocked("no_diff_unproven", "Provider history is unavailable; integration cannot be proven.")
    for pr in prs:
        merged = (pr.get("mergeCommit") or {}).get("oid")
        if (pr.get("state") == "MERGED" and pr.get("headRefOid") == source and merged
                and ctx.git.exists(merged) and ctx.git.is_ancestor(merged, base)):
            evidence.update(kind="previously_merged", pr=pr.get("number"), url=pr.get("url"), merge_commit=merged,
                            limitation="History does not prove the changes remain effective after a revert.")
            return Done({"evidence": evidence}, ok=True)
    existing = next((p for p in prs if p.get("state") == "OPEN" and p.get("headRefName") == details["carrier"]), None)
    if existing:
        pr = existing
    else:
        try:
            url = ctx.gh.run("pr", "create", "--head", details["carrier"], "--base", dest,
                             "--title", f"Forward-port release {details['source_release']}", "--body-file", "-",
                             input=f"Forward-port maintenance source {source} to {dest}.").strip().splitlines()[-1]
            pr = {"number": int(url.rstrip("/").rsplit("/", 1)[-1]), "url": url}
        except (GhError, IndexError, ValueError):
            # A provider error may mean no diff, or a successful create whose
            # response was lost. Inspect fresh evidence without creating again.
            ctx.session.refetch(all_goals=True)
            latest = observed(ctx, details)
            base = latest["destination_tip"]
            if (latest["source_goal_commit"] != details["source_goal_commit"] or not base
                    or latest["head"] != head):
                return blocked("forward_port_snapshot_changed", "Source, destination or carrier changed during PR creation; review before retrying.")
            evidence["destination_tip"] = base
            if ctx.git.is_ancestor(source, base):
                evidence.update(kind="already_in_history", proof=f"git merge-base --is-ancestor {source} {base}",
                                limitation="History does not prove the changes remain effective after a revert.")
                return Done({"evidence": evidence}, ok=True)
            try:
                after = ctx.gh.json("pr", "list", "--base", dest, "--state", "all", "--json",
                                    "number,state,headRefOid,headRefName,baseRefName,mergeCommit,url") or []
            except GhError:
                after = []
            for item in after:
                merged = (item.get("mergeCommit") or {}).get("oid")
                if (item.get("state") == "MERGED" and item.get("headRefOid") == source and merged
                        and ctx.git.exists(merged) and ctx.git.is_ancestor(merged, base)):
                    evidence.update(kind="previously_merged", pr=item.get("number"), url=item.get("url"),
                                    merge_commit=merged,
                                    limitation="History does not prove the changes remain effective after a revert.")
                    return Done({"evidence": evidence}, ok=True)
            pr = next((item for item in after if item.get("state") == "OPEN"
                       and item.get("headRefName") == details["carrier"] and item.get("headRefOid") == head), None)
            if not pr:
                return blocked("no_diff_unproven", f"No verifiable integration for source {source} and destination {base}; investigate before retrying.")
    evidence.update(kind="pr", pr=pr["number"], url=pr.get("url"))
    return Done({"evidence": evidence}, ok=True)


def finish(ctx, details):
    evidence = ctx.inputs["evidence"]
    o = observed(ctx, details)
    branching = ctx.settings.get("branching") or {}
    allowed = {ctx.snap.I, branching.get("production")} | {
        line.branch for line in ctx.session.portfolio().lines if line.kind == "release" and line.open
    }
    if evidence["kind"] == "pr":
        try:
            existing = ctx.gh.json("pr", "view", str(evidence["pr"]), "--json",
                                   "number,state,headRefOid,baseRefName,mergeCommit") or {}
        except GhError:
            existing = {}
        if existing.get("state") == "MERGED":
            merged = (existing.get("mergeCommit") or {}).get("oid")
            p = parents(ctx.git, merged) if merged and ctx.git.exists(merged) else []
            if (existing.get("headRefOid") != evidence["head"] or existing.get("baseRefName") != details["destination"]
                    or not p or p[0] != evidence["destination_tip"] or not o["destination_tip"]
                    or not ctx.git.is_ancestor(merged, o["destination_tip"])
                    or o["source_goal_commit"] != details["source_goal_commit"]):
                return blocked("post_merge_divergence", f"PR merged as {merged}; source or destination diverged. Review before continuing.",
                               {"evidence": evidence, "merge_commit": merged, "observed": o})
            return Done({"result": {**evidence, "kind": "merged", "merge_commit": merged}}, ok=True)
    if details["destination"] not in allowed:
        return blocked("destination_ineligible", "The destination is no longer an open release line; review before continuing.")
    if (o["source_goal_commit"] != details["source_goal_commit"]
            or o["destination_tip"] != evidence["destination_tip"] or o["head"] != evidence["head"]):
        return blocked("forward_port_snapshot_changed", "The approved source, destination or head changed; obtain fresh review.")
    if evidence["kind"] in ("already_in_history", "previously_merged"):
        return Done({"result": evidence}, ok=True)
    try:
        result = merge_pr(ctx, {}, evidence["pr"], evidence["head"], details["destination"])
    except GhError as exc:
        return Blocked({"category": "external", "waiting_for": "time", "reason": "provider_retry",
                        "retry_after": iso(ctx.now + 300),
                        "instructions": f"Provider could not confirm the merge: {str(exc)}. Retry this operation after resolving the provider issue.",
                        "op_state": {"pr": evidence["pr"], "head": evidence["head"]}})
    if isinstance(result, Blocked):
        return result
    merged = result[1]
    actual = ctx.session.fetch_branches([details["destination"]]).get(details["destination"])
    ctx.session.refetch(all_goals=True)
    p = parents(ctx.git, merged) if merged and ctx.git.exists(merged) else []
    if (not p or p[0] != evidence["destination_tip"] or not actual or not ctx.git.is_ancestor(merged, actual)
            or ctx.session.snap.goals.get(details["source_goal"]) != details["source_goal_commit"]):
        return blocked("post_merge_divergence", f"PR merged as {merged}; source or destination diverged. Review before continuing.",
                       {"evidence": evidence, "merge_commit": merged, "observed_destination": actual,
                        "observed_source_goal": ctx.session.snap.goals.get(details["source_goal"])})
    return Done({"result": {**evidence, "kind": "merged", "merge_commit": merged}}, ok=True)


def run(ctx):
    details = json.loads(ctx.doc["spec"])
    if ctx.node_def["op"] == "git.forward_prepare":
        return prepare(ctx, details)
    return finish(ctx, details)
