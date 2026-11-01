"""`git.base` (SPEC §5.2): put the goal's own commits on its stack base."""

from __future__ import annotations

from engine.errors import EngineError, Refused
from engine.identity import Identity
from engine.ops.run import Blocked, Done
from engine import worktree as wt


def rebase_in_progress(git, p) -> bool:
    return wt.rebase_in_progress(git, p)


def run(ctx):
    git, snap = ctx.git, ctx.snap
    ident = Identity(git)
    g, p = ctx.goal, ctx.worktree
    I = snap.integration
    W = snap.work.get(g)
    SB = snap.stack.get(g)
    br, sb = f"zzzops/work/g{g}", f"zzzops/stack/g{g}"
    heads = ctx.inputs.get("heads") or {}
    prs = ctx.inputs.get("prs") or {}
    merges = ctx.inputs.get("merges") or {}
    rec = ctx.record
    prev = ((rec.get("blocked") or {}).get("op_state") or {}) if rec and rec["status"] == "blocked" else {}
    if rec and rec["status"] == "done":
        old = rec["output"]["base_commit"]
    else:
        old = prev.get("old") or (git.out("merge-base", W, I) if W else None)
    resume = {"resume": ["start", str(g), ctx.node, "--as", "<LABEL>"]}
    # 0. the worktree
    if rebase_in_progress(git, p):
        return Blocked({"category": "conflict", "waiting_for": "agent", "reason": "rebase in progress",
                        "instructions": f"In {p}: resolve the conflicts, `git add` them, run "
                                        "`git -c core.editor=true rebase --continue` (or `git rebase --abort`), then run "
                                        "the resume command.",
                        "commands": resume, "op_state": prev})
    if not wt.is_clean(git, p):
        return Blocked({"category": "conflict", "waiting_for": "agent", "reason": "uncommitted changes in the goal worktree",
                        "instructions": "Commit or stash them, then run the resume command.", "commands": resume,
                        "op_state": dict(prev, old=old)})
    # 1. what to stack on
    bad = sorted((d for d, m in merges.items() if m and not git.is_ancestor(m, I)), key=int)
    if bad:
        d = bad[0]
        return Blocked({"category": "dependency", "waiting_for": "human", "reason": "dependency merge not in integration",
                        "question": f"G{g}: merge commit {merges[d][:7]} of G{d} is not in {snap.I}: the integration "
                                    "branch was rewritten without it. Drop the dependency or wait?"})
    unmerged = sorted((d for d in heads if heads[d] and not merges.get(d)
                       and ctx.dep_kinds.get(int(d)) in ("open", "held")), key=int)
    for d in unmerged:
        if not git.exists(heads[d]):
            git.run("fetch", "--no-tags", "--no-write-fetch-head", snap.R,
                    f"+refs/heads/zzzops/pr/g{d}:refs/remotes/{snap.R}/zzzops/pr/g{d}", check=False)
    merged = [m for m in merges.values() if m]
    hs = [heads[d] for d in unmerged]
    need_I = not hs or any(not all(git.is_ancestor(m, h) for h in hs) for m in merged)
    S = []
    for x in ([I] if need_I else []) + hs:
        if x not in S:
            S.append(x)
    S = [x for x in S if not any(y != x and git.is_ancestor(x, y) for y in S)]
    stack = [{"goal": int(d), "head": heads[d], "pr": (prs.get(d) or {}).get("number")} for d in unmerged if heads[d] in S]
    ups, post = [], None
    if len(S) == 1:
        onto = S[0]
    elif SB and parents(git, SB) == S:
        onto = SB
    else:
        onto = combine(git, g, S, stack, I in S, snap.I)
        if onto is None:
            return Blocked({"category": "dependency", "waiting_for": "dependency", "reason": "deps_conflict",
                            "op_state": {"old": old, "set": S}})
        ups.append((f"refs/heads/{sb}", SB, onto))
    if len(S) < 2 and SB:
        target = snap.I if S == [I] else f"zzzops/pr/g{stack[0]['goal']}"
        post = lambda: retire_stack(ctx, sb, SB, target)
    out = {"branch": br, "base_commit": onto, "stack": stack, "replay_map": {}, "replay_pos": {}}
    # 2. no artifact yet: the branch is born on the stack base
    if W is None:
        git.run("reset", "-q", "--keep", onto, cwd=p)
        return Done(out, ok=True, ref_updates=ups + [(f"refs/heads/{br}", None, onto)], after_push=post,
                    summary=f"work branch created on {onto[:7]}")
    # 3. a hand-resolved conflict
    Lc = git.rev_parse(f"refs/heads/{br}")
    pw = prev.get("work")
    rv = bool(pw and W != pw and git.is_ancestor(pw, W)
              and all(ident.is_review(c) for c in git.out("rev-list", f"{pw}..{W}").split()))
    accepted = False
    if pw and Lc != pw and (W == pw or rv) and prev.get("onto") and git.is_ancestor(prev["onto"], Lc):
        try:
            ident.check_i1_i2(prev["onto"], Lc)
            accepted = True
        except Refused:
            accepted = False
    if accepted:
        if rv:
            have = {i for _, i in ident.patch_ids(prev["onto"], Lc)}
            todo = [c for c, i in ident.patch_ids(pw, W) if i not in have]
            if todo:
                git.run("cherry-pick", *todo, cwd=p)
            Lc = git.rev_parse(f"refs/heads/{br}")
        frm, start, src = prev["onto"], Lc, W
    else:
        if unpushed_replay(git, ident, Lc, W, old):
            git.run("reset", "-q", "--keep", W, cwd=p)
        wt.sync(git, ident, snap, g, "clean", ctx.node, "?", self_sync=True)
        start = git.rev_parse(f"refs/heads/{br}")
        frm, src = old, start
    if onto == frm and start == W:
        return Done(out, ok=True, ref_updates=ups, after_push=post, summary=f"already on {onto[:7]}")
    # 4. replay only the goal's own commits
    r = git.run("rebase", "-q", "--onto", onto, frm, cwd=p, check=False)
    if r.returncode != 0:
        files = " ".join(git.out("diff", "--name-only", "--diff-filter=U", cwd=p).split())
        return Blocked({"category": "conflict", "waiting_for": "agent", "reason": f"rebase conflict in {files}",
                        "instructions": f"In {p}: resolve the conflicts in {files}, `git add` them, run "
                                        "`git -c core.editor=true rebase --continue`, then run the resume command. "
                                        "Do not change the meaning of the goal's commits.",
                        "commands": resume, "op_state": {"work": W, "onto": onto, "old": old}})
    H = git.out("rev-parse", "HEAD", cwd=p)
    ident.check_i1_i2(onto, H)
    A, B = ident.patch_ids(old, src), ident.patch_ids(onto, H)
    M = {a: b for (a, ai), (b, bi) in zip(A, B) if ai == bi}
    out["replay_map"] = M
    if len(A) == len(B):
        out["replay_pos"] = {a: b for (a, ai), (b, bi) in zip(A, B) if ai != bi}
    return Done(out, ok=True, ref_updates=ups + [(f"refs/heads/{br}", W, H)],
                replayed={"old": old, "onto": onto, "map": M}, after_push=post,
                summary=f"rebased onto {onto[:7]}")


def parents(git, c) -> list:
    return git.out("rev-list", "--parents", "-n", "1", c).split()[1:]


def combine(git, g, S, stack, with_I, I_name):
    acc = S[0]
    tree = None
    for i, h in enumerate(S[1:], 1):
        r = git.run("merge-tree", "--write-tree", "-z", "--no-messages", acc, h, check=False, text=False)
        if r.returncode == 1:
            return None
        if r.returncode != 0:
            raise EngineError(r.stderr.decode("utf-8", "replace"))
        tree = r.stdout.split(b"\0")[0].decode()
        if i < len(S) - 1:
            acc = git.commit_tree(tree, [acc, h], "zzzops: partial stack\n")
    names = ", ".join(f"G{e['goal']}" for e in stack) + (f", {I_name}" if with_I else "")
    return git.commit_tree(tree, list(S), f"zzzops: stack for G{g} (combines {names})\n")


def unpushed_replay(git, ident, Lc, W, old) -> bool:
    if not Lc or Lc == W or git.is_ancestor(Lc, W) or git.is_ancestor(W, Lc):
        return False
    pairs = ident.patch_ids(old, W)
    C = [i for _, i in pairs]
    top_reviews = 0
    for c, _ in reversed(pairs):
        if ident.is_review(c):
            top_reviews += 1
        else:
            break
    low = len(C) - top_reviews
    for m in range(len(C), max(low, 1) - 1, -1):
        firsts = git.out("rev-list", "--first-parent", f"--max-count={m}", Lc).split()[::-1]
        if len(firsts) < m:
            continue
        ids = []
        for c in firsts:
            parent = git.out("rev-parse", f"{c}^")
            got = ident.patch_ids(parent, c)
            ids.append(got[0][1] if got else None)
        if ids == C[:m]:
            return True
    return False


def retire_stack(ctx, sb, SB, target):
    """After base's push: retarget the goal's PR, close the stack PR, then delete the stack branch (H23 order)."""
    from engine.store import push_atomic
    gh = ctx.gh
    warnings = []
    for pr in gh.json("pr", "list", "--base", sb, "--state", "open", "--json", "number") or []:
        gh.run("pr", "edit", str(pr["number"]), "--base", target)
    for pr in gh.json("pr", "list", "--head", sb, "--state", "open", "--json", "number") or []:
        gh.run("pr", "close", str(pr["number"]), "--comment", "Stack no longer needed.")
    r, _ = push_atomic(ctx.git, ctx.snap.R, [(f"refs/heads/{sb}", SB, None)])
    if r != "ok":
        warnings.append({"kind": "stack_branch", "message": f"could not delete {sb}; the next base run or the close will"})
    return warnings
