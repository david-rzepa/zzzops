"""`git.line_sync` and `git.line_finish` (G1025 design §5.4, §6, §7; SPEC §5.7, §5.8).

A line goal has no work branch. Its worktree is detached; each back-merge builds its own branch
`zzzops/sync/g<line>/<into>` (into = integration | release) and merges it through a PR with a real merge commit."""

from __future__ import annotations

import os

from engine.canon import iso
from engine.lines import branching, lines_of, merged_ledger, open_members
from engine.ops.integrate import classify, guarded, local_conflict
from engine.ops.run import Blocked, Done
from engine.store import push_atomic
from engine import worktree as wt

VIEW = "number,state,headRefOid,baseRefName,mergeable,mergeStateStatus,statusCheckRollup,mergeCommit"


def run(ctx):
    op = ctx.node_def["op"]
    return guarded(ctx, lambda: (sync if op == "git.line_sync" else finish)(ctx))


# --------------------------------------------------------------------------------------------- shared


def previous_state(ctx) -> dict:
    r = ctx.record
    if r and r["status"] == "blocked":
        return dict((r["blocked"].get("op_state") or {}))
    return {}


def resume_cmd(ctx) -> dict:
    return {"resume": ["start", str(ctx.goal), ctx.node, "--as", "<LABEL>"]}


def wait(ctx, state, reason, delay) -> Blocked:
    return Blocked({"category": "external", "waiting_for": "time", "reason": reason,
                    "retry_after": iso(ctx.now + delay), "op_state": state})


def worktree(ctx) -> str:
    git = ctx.git
    p = wt.worktree_path(git, ctx.goal)
    wt.install_ignore(git)
    known = [os.path.realpath(x) for x in wt.registered_worktrees(git)]
    if os.path.realpath(p) not in known:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        git.run("worktree", "add", "-q", "--detach", p, ctx.snap.integration)
    return p


def merging(git, p) -> bool:
    return git.run("rev-parse", "-q", "--verify", "MERGE_HEAD", cwd=p, check=False).returncode == 0


def parents(git, c) -> list:
    return git.out("rev-list", "--parents", "-n", "1", c).split()[1:]


def tip(ctx, branch):
    return ctx.session.target_tip(branch)


def back_merge(ctx, state, source, into, into_tip, slot, title):
    """Merge `source` into branch `into` through the PR of `zzzops/sync/g<line>/<slot>`. Returns ("merged", commit or
    None) or a Blocked whose op_state is the whole `state` (this back-merge keeps its part under state["bm"][slot])."""
    git, gh, s = ctx.git, ctx.gh, ctx.session
    g = ctx.goal
    sb = f"zzzops/sync/g{g}/{slot}"
    bm = state.setdefault("bm", {}).setdefault(slot, {"resolved": [], "approved": []})
    S = s.fetch_branches([sb]).get(sb)
    open_prs = gh.json("pr", "list", "--head", sb, "--state", "open", "--json", "number,baseRefName") or []
    if not open_prs and not bm.get("pending") and git.is_ancestor(source, into_tip):
        return "merged", None
    p = worktree(ctx)
    pend = bm.pop("pending", None)
    head = None
    if pend:
        if merging(git, p):
            bm["pending"] = pend
            files = " ".join(git.out("diff", "--name-only", "--diff-filter=U", cwd=p).split())
            return Blocked({"category": "conflict", "waiting_for": "agent", "reason": f"merge conflict in {files}",
                            "instructions": f"In {p}: resolve the conflicts in {files}, `git add` them, run "
                                            "`git -c core.editor=true commit --no-edit`, then run the resume command.",
                            "commands": resume_cmd(ctx), "op_state": state})
        H = git.out("rev-parse", "HEAD", cwd=p)
        if parents(git, H) == [pend["ours"], pend["theirs"]] and not git.out(
                "diff", "--name-only", pend["ours"], H, "--", ".zzzops/reviews"):
            bm["resolved"].append(H)
            head = H
    if head is None:
        if merging(git, p):
            git.run("merge", "--abort", cwd=p, check=False)
        base = S or into_tip                               # keep an approved resolution: build on the sync branch
        git.run("checkout", "-q", "--force", "-B", sb, base, cwd=p)
        head = base
    git.run("checkout", "-q", "-B", sb, head, cwd=p)
    for x, name in ((source, title), (into_tip, into)):
        if git.is_ancestor(x, head):
            continue
        msg = f"Merge {name} into {into} (zzzops G{g})" if x != source else f"{title} (zzzops G{g})"
        r = git.run("merge", "--no-ff", "--no-edit", "-m", msg, x, cwd=p, check=False)
        if r.returncode != 0:
            files = " ".join(git.out("diff", "--name-only", "--diff-filter=U", cwd=p).split())
            bm["pending"] = {"ours": head, "theirs": x}
            return Blocked({"category": "conflict", "waiting_for": "agent", "reason": f"merge conflict in {files}",
                            "instructions": f"In {p}: resolve the conflicts in {files}, `git add` them, run "
                                            "`git -c core.editor=true commit --no-edit`, then run the resume command. "
                                            "Keep both sides' intent.",
                            "commands": resume_cmd(ctx), "op_state": state})
        head = git.out("rev-parse", "HEAD", cwd=p)
    if head != S:
        res, _ = push_atomic(git, ctx.snap.R, [(f"refs/heads/{sb}", S, head)])
        if res != "ok":
            return wait(ctx, state, f"could not push {sb}", 60)
        s.snap.targets[sb] = head
    # an agent's resolution reaches the integration branch only with a human's approval (D7)
    asked = bm.pop("asked", None)
    if asked and ctx.answer:
        bm["approved"].append(asked)
    todo = [c for c in bm["resolved"] if c not in bm["approved"] and git.is_ancestor(c, head)]
    if todo:
        bm["asked"] = todo[0]
        return Blocked({"category": "decision", "waiting_for": "human", "reason": "a hand-resolved merge needs approval",
                        "question": f"G{g}: merging into `{into}` needed a hand resolution ({todo[0][:12]}). Approve the "
                                    f"resolution: `git show --remerge-diff {todo[0]}`?",
                        "options": ["approve the resolution", "redo it (reopen this node)"], "op_state": state})
    pr = open_prs[0] if open_prs else None
    if pr is None:
        url = gh.run("pr", "create", "--head", sb, "--base", into, "--title", title, "--body-file", "-",
                     input=f"{title}.\n\nZzzOps line G{g} ({ctx.doc['title']}). The engine merges this PR with a "
                           "merge commit.").strip().splitlines()[-1]
        pr = {"number": int(url.rstrip("/").rsplit("/", 1)[-1]), "baseRefName": into}
    elif pr["baseRefName"] != into:
        gh.run("pr", "edit", str(pr["number"]), "--base", into)
    return merge_pr(ctx, state, pr["number"], head, into)


def merge_pr(ctx, state, n, head, into):
    """Wait for GitHub and the required checks, then merge PR n at `head` with a merge commit (D8)."""
    gh = ctx.gh
    v = gh.json("pr", "view", str(n), "--json", VIEW)
    if v["state"] == "MERGED":
        return "merged", (v.get("mergeCommit") or {}).get("oid")
    if v["state"] == "CLOSED":
        return Blocked({"category": "external", "waiting_for": "human", "reason": f"PR #{n} closed without merging",
                        "question": f"PR #{n} into `{into}` was closed on GitHub. Reopen it, then answer.",
                        "op_state": state})
    if v["headRefOid"] != head:
        return wait(ctx, state, "GitHub has not seen the PR head yet", 60)
    m, ms = v.get("mergeable"), v.get("mergeStateStatus")
    if m in ("UNKNOWN", None) or m == "CONFLICTING" or ms == "DIRTY":
        return wait(ctx, state, f"PR #{n} is not mergeable yet ({m}/{ms})", 60)
    req = list(ctx.settings["verification"]["required_ci"])
    status = {name: "pending" for name in req}
    for item in v.get("statusCheckRollup") or []:
        name = item.get("name") or item.get("context")
        if name in status:
            status[name] = classify(item)
    failed = sorted(k for k, x in status.items() if x == "failed")
    if failed:
        return Blocked({"category": "external", "waiting_for": "human", "reason": f"required checks failed on PR #{n}",
                        "question": f"Required checks {failed} failed on PR #{n} into `{into}`. Fix them on the line "
                                    "through a goal, then answer.", "op_state": state})
    if any(x == "pending" for x in status.values()):
        return wait(ctx, state, f"required checks pending on PR #{n}", 300)
    if ms == "BLOCKED":
        return wait(ctx, state, "GitHub blocks the merge (required reviews, checks or rules); satisfy it on GitHub or "
                                "merge there", 1800)
    gh.run("pr", "merge", str(n), "--merge", "--match-head-commit", head)
    v = gh.json("pr", "view", str(n), "--json", VIEW)
    if v["state"] != "MERGED":
        return wait(ctx, state, "merge not observed yet", 120)
    return "merged", (v.get("mergeCommit") or {}).get("oid")


def line_info(ctx):
    flow = ctx.doc["flow"]
    return flow["line"], flow["name"], flow["branch"]


def gone(ctx, branch, state) -> Blocked:
    return Blocked({"category": "external", "waiting_for": "human", "reason": f"{branch} is gone",
                    "question": f"{branch} is gone from `{ctx.snap.R}`; restore it, or cancel G{ctx.goal}.",
                    "op_state": state})


# --------------------------------------------------------------------------------------------- sync


def sync(ctx):
    kind, name, branch = line_info(ctx)
    state = previous_state(ctx)
    T = tip(ctx, branch)
    if not T:
        return gone(ctx, branch, state)
    if kind == "hotfix":                                  # record-only: bind approve_finish to the hotfix tip (§7)
        return Done({"merged": T, "merge_commit": None}, ok=True, summary=f"{branch} at {T[:7]}")
    I = ctx.snap.I
    out = back_merge(ctx, state, T, I, ctx.snap.integration, "integration", f"Release {name}: merge {branch} into {I}")
    if isinstance(out, Blocked):
        return out
    mc = out[1]
    return Done({"merged": T, "merge_commit": mc}, ok=True,
                summary=f"{branch} ({T[:7]}) merged into {I}" + (f" ({mc[:7]})" if mc else " already"))


# --------------------------------------------------------------------------------------------- finish


def finish(ctx):
    kind, name, branch = line_info(ctx)
    s, git, gh = ctx.session, ctx.git, ctx.gh
    state = previous_state(ctx)
    st = s.state
    lns = lines_of(merged_ledger(st.ledger, st.docs), ctx.settings)
    me = next((x for x in lns if x.goal == ctx.goal), None)
    late = open_members(merged_ledger(st.ledger, st.docs), me) if me else []
    if late:
        return wait(ctx, state, "line_members_open: " + ", ".join(f"G{x}" for x in late), 300)
    T = ctx.inputs["sync"]                                # the approved, recorded tip: never re-read the branch
    cur = tip(ctx, branch)
    if cur and cur != T:
        return Blocked({"category": "decision", "waiting_for": "human", "reason": f"{branch} moved since the approval",
                        "question": f"{branch} moved from {T[:7]} to {cur[:7]} after the finish was approved; "
                                    "re-run sync and approve the finish again.", "op_state": state})
    b = branching(ctx.settings)
    prod = b["production"]
    title = f"Release {name}" if kind == "release" else f"Hotfix {name}"
    if state.get("production_merge") is None:
        prs = gh.json("pr", "list", "--head", branch, "--base", prod, "--state", "all", "--json",
                      "number,state,headRefOid,mergeCommit") or []
        done = next((x for x in prs if x["state"] == "MERGED" and git.is_ancestor(T, x["headRefOid"] or "")), None)
        if done:
            state["production_merge"] = (done.get("mergeCommit") or {}).get("oid")
        else:
            P = tip(ctx, prod)
            if not P:
                return gone(ctx, prod, state)
            files = local_conflict(git, P, T)
            if files is not None:
                return Blocked({"category": "conflict", "waiting_for": "human", "reason": f"{branch} conflicts with {prod}",
                                "question": f"`{prod}` has changes {branch} lacks ({', '.join(files) or 'unknown files'}): "
                                            f"it was changed outside git flow. Merge `{prod}` into {branch} through a "
                                            "stabilisation goal, then answer.", "op_state": state})
            if not cur:
                return gone(ctx, branch, state)
            pr = next((x for x in prs if x["state"] == "OPEN"), None)
            if pr is None:
                url = gh.run("pr", "create", "--head", branch, "--base", prod, "--title", title, "--body-file", "-",
                             input=f"{title}: merge `{branch}` into `{prod}` (ZzzOps G{ctx.goal}). The engine merges it "
                                   "with a merge commit; tags and deployment are the project's own steps."
                             ).strip().splitlines()[-1]
                n = int(url.rstrip("/").rsplit("/", 1)[-1])
            else:
                n = pr["number"]
            out = merge_pr(ctx, state, n, T, prod)
            if isinstance(out, Blocked):
                return out
            state["production_merge"] = out[1]
    back = state.setdefault("back", {})
    intos = [(ctx.snap.I, ctx.snap.integration, "integration")]
    if kind == "hotfix":
        rel = next((x for x in lns if x.kind == "release" and x.open), None)
        if rel and tip(ctx, rel.branch):
            intos.append((rel.branch, tip(ctx, rel.branch), "release"))
    for into, into_tip, slot in intos:
        if into in back:
            continue
        out = back_merge(ctx, state, T, into, into_tip, slot, f"{title}: merge {branch} into {into}")
        if isinstance(out, Blocked):
            return out
        back[into] = out[1]
    return Done({"production_merge": state["production_merge"], "back_merges": dict(back)}, ok=True,
                summary=f"{branch} merged into {prod}" + "".join(f", {k}" for k in back))
