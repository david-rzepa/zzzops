"""`github.merge` (SPEC §5.5): observe, then merge at the expected head; retarget dependents once merged."""

from __future__ import annotations

from datetime import datetime, timezone

from engine.identity import Identity
from engine.ops.integrate import guarded, pull_head
from engine.ops.run import Blocked, Done

VIEW = "state,mergeCommit,mergedAt,headRefOid,baseRefName,mergeable,mergeStateStatus,autoMergeRequest"


def run(ctx):
    return guarded(ctx, lambda: _run(ctx))


def to_iso(text):
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return text


def dependent_target(ctx, head, default):
    """A dependent PR goes to its own goal's target, not the merged goal's (G1025 §8)."""
    import re
    m = re.match(r"^zzzops/pr/g(\d+)$", head or "")
    if not m or ctx.session is None:
        return default
    res = ctx.session.portfolio().goals.get(int(m.group(1)))
    b = (res.target or {}).get("branch") if res else None
    return b or default


def _run(ctx):
    gh, snap = ctx.gh, ctx.snap
    g = ctx.goal
    I = (ctx.target or {}).get("branch") or snap.I          # the goal's target (G1025), the integration branch by default
    pr = ctx.inputs["pr"]
    n, H = pr["number"], pr["head"]

    def wrong_base(b):
        prod = ctx.producers["pr"]
        return Blocked({"category": "dependency", "waiting_for": "human", "reason": "PR base is not the integration branch",
                        "question": f"PR #{n} for G{g} targets `{b}`, not `{I}`, although every dependency has merged. "
                                    f"Rebuild it on `{I}` (reopen {prod}), or cancel G{g}?",
                        "options": ["reopen the PR's producer", "cancel the goal"],
                        "commands": {"reopen the PR's producer": ["reopen", str(g), prod, "--note", "<why>"]}})

    def merged(v):
        if v["baseRefName"] != I:
            return Blocked({"category": "external", "waiting_for": "human", "reason": "PR merged into another base",
                            "question": f"PR #{n} was merged into `{v['baseRefName']}`, not `{I}`, so G{g}'s code is not on "
                                        f"`{I}`. Open a follow-up goal for it, then cancel G{g}."})
        if v["headRefOid"] != H and Identity(ctx.git).code_tree(pull_head(ctx, n)) != pr["tree"]:
            return Blocked({"category": "external", "waiting_for": "human", "reason": "PR merged other code",
                            "question": f"PR #{n} for G{g} was merged with code other than the reviewed checkpoint. Open a "
                                        f"follow-up goal for the difference, then cancel G{g}."})
        for m in gh.json("pr", "list", "--base", f"zzzops/pr/g{g}", "--state", "open", "--json",
                         "number,headRefName") or []:
            gh.run("pr", "edit", str(m["number"]), "--base", dependent_target(ctx, m.get("headRefName"), I))
        if ctx.inputs.get("issue"):
            try:
                gh.run("issue", "close", str(ctx.inputs["issue"]), "--comment", f"Done in #{n}.")
            except Exception:
                pass
        note = "" if v["headRefOid"] == H else f" (merged head {v['headRefOid'][:7]} differs from {H[:7]} with the same code)"
        return Done({"merge_commit": (v.get("mergeCommit") or {}).get("oid"), "merged_at": to_iso(v.get("mergedAt"))},
                    ok=True, summary="merged" + note)

    if pr["base"] != I:
        return wrong_base(pr["base"])
    v = gh.json("pr", "view", str(n), "--json", VIEW)
    if v["state"] == "MERGED":
        return merged(v)
    if v["state"] == "CLOSED":
        return Blocked({"category": "external", "waiting_for": "human", "reason": f"PR #{n} closed without merging",
                        "question": f"PR #{n} was closed without merging. Reopen it on GitHub, or cancel G{g}?"})
    if v["state"] == "OPEN" and v["baseRefName"] != I:
        return wrong_base(v["baseRefName"])
    if v["headRefOid"] != H:
        return Blocked({"category": "external", "waiting_for": "human", "reason": "PR head moved",
                        "question": f"PR #{n}'s head moved from {H[:7]} to {v['headRefOid'][:7]}: someone pushed to it. "
                                    "Merge it as it is now (merge it on GitHub, then answer this item), or rebuild it from "
                                    "the work branch (reopen integrate, then answer this item; the pushed commits are discarded)?"})
    if v.get("mergeable") == "CONFLICTING" or v.get("mergeStateStatus") in ("DIRTY", "BEHIND"):
        if "base" not in ctx.inputs:
            return Blocked({"category": "conflict", "waiting_for": "human", "reason": "PR cannot merge",
                            "question": f"PR #{n} cannot merge ({v.get('mergeStateStatus')}). Rebase it?"})
        return Done({"merge_commit": None, "merged_at": None}, ok=False,
                    findings=[{"key": "conflict", "input": "base",
                               "text": f"PR #{n} cannot merge into {I} ({v.get('mergeStateStatus')}); rebase the work branch"}])
    if v.get("autoMergeRequest"):
        return ctx.wait("queued on GitHub (auto-merge)", 300)
    if v.get("mergeStateStatus") == "BLOCKED":
        return ctx.wait("GitHub blocks the merge (required reviews, checks, signatures or queue); satisfy it on GitHub "
                        "or merge there", 1800)
    if v.get("mergeable") == "UNKNOWN":
        return ctx.wait("GitHub is computing mergeability", 120)
    from engine.gh import GhError
    try:
        gh.run("pr", "merge", str(n), f"--{ctx.settings['merge']['method']}", "--match-head-commit", H)
    except GhError as exc:
        if "queue" in str(exc).lower() or "already" in str(exc).lower():
            return ctx.wait("queued on GitHub", 300)
        raise
    v = gh.json("pr", "view", str(n), "--json", VIEW)
    return merged(v) if v["state"] == "MERGED" else ctx.wait("merge not observed yet", 120)
