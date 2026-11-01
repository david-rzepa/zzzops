"""`git.integrate` (SPEC §5.4): the review-free PR branch, the PR, and its required checks."""

from __future__ import annotations

import os
import re
import sys

from engine.canon import iso
from engine.errors import EngineError, Refused
from engine.gh import GhError
from engine.identity import Identity, REVIEW_PATH
from engine.ops.run import Blocked, Done
from engine.store import push_atomic
from engine import worktree as wt

RUN_ID = re.compile(r"/actions/runs/(\d+)")


def guarded(ctx, body):
    """§5.6 error mapping: transient gh failures wait; any other gh failure asks the human."""
    try:
        return body()
    except GhError as exc:
        line = str(exc).splitlines()[0][:300]
        if exc.transient:
            return ctx.wait(line, 300)
        return Blocked({"category": "external", "waiting_for": "human", "reason": "gh failed",
                        "question": f"gh failed: {line}. Fix access, then answer to retry."})


def run(ctx):
    return guarded(ctx, lambda: _run(ctx))


def fail(key, text):
    return Done({"pr": None, "ci": None}, ok=False, findings=[{"key": key, "input": "code", "text": text}])


def classify(item) -> str:
    if item.get("__typename") == "StatusContext" or "context" in item and "status" not in item:
        s = item.get("state")
        return "passed" if s == "SUCCESS" else ("failed" if s in ("FAILURE", "ERROR") else "pending")
    if item.get("status") == "COMPLETED":
        return "passed" if item.get("conclusion") in ("SUCCESS", "NEUTRAL", "SKIPPED") else "failed"
    return "pending"


def committer(git):
    v = git.config("zzzops.committer") or "ZzzOps <zzzops@localhost>"
    m = re.match(r"^\s*(.*?)\s*<([^>]*)>\s*$", v)
    return (m.group(1), m.group(2)) if m else ("ZzzOps", "zzzops@localhost")


def _run(ctx):
    git, snap, gh = ctx.git, ctx.snap, ctx.gh
    ident = Identity(git)
    g, p = ctx.goal, ctx.worktree
    I = snap.I
    W, B, T = snap.work.get(g), ctx.inputs["base"], ctx.inputs["code"]
    stack = ctx.inputs.get("stack") or []
    if not stack:
        target = I
    elif len(stack) == 1 and B == stack[0]["head"]:
        target = f"zzzops/pr/g{stack[0]['goal']}"
    else:
        target = f"zzzops/stack/g{g}"
    tmp, br = f"zzzops-tmp/g{g}", f"zzzops/work/g{g}"
    # 0. clean up after a crash, then reconcile
    if wt.rebase_in_progress(git, p):
        git.run("rebase", "--abort", cwd=p, check=False)
    cur = git.run("symbolic-ref", "-q", "--short", "HEAD", cwd=p, check=False).stdout.strip()
    if cur == tmp:
        git.run("switch", "-q", br, cwd=p)
    if git.rev_parse(f"refs/heads/{tmp}"):
        git.run("branch", "-q", "-D", tmp)
    wt.sync(git, ident, snap, g, "clean", ctx.node, "?", self_sync=True)
    W = snap.work.get(g)
    # 1. check the work branch
    if ident.code_tree(W) != T:
        return fail("work-beyond-checkpoint", f"{br} has code beyond the recorded checkpoint; submit a checkpoint at the tip")
    try:
        ident.check_i1_i2(B, W)
    except Refused as exc:
        return fail("history", exc.message)
    pol = git.out("diff", "--name-only", B, W, "--", ".zzzops/POLICY.json", ".zzzops/workflow.json", ".zzzops/prompts")
    if pol:
        return fail("policy-paths", "goal diffs must not touch policy files; change policy through a zzzops/policy/* branch")
    commits = git.out("rev-list", "--reverse", "--topo-order", f"{B}..{W}").split()
    if all(ident.is_review(c) for c in commits):
        return Blocked({"category": "decision", "waiting_for": "human", "reason": "no code commits",
                        "question": f"G{g} has no code commits to integrate. Close it as superseded (nothing to deliver)?",
                        "options": ["close as superseded", f"reopen {ctx.producers['code']}"],
                        "commands": {"close as superseded": ["edit", str(g), "--file", "<F>", "--base", "<C>"],
                                     f"reopen {ctx.producers['code']}": ["reopen", str(g), ctx.producers["code"], "--note", "<why>"]}})
    # 2. deterministic rebuild: drop review commits
    todo = "".join(f"{'drop' if ident.is_review(c) else 'pick'} {c} {ident.subject(c)}\n" for c in commits)
    gitdir = git.out("rev-parse", "--absolute-git-dir", cwd=p)
    todo_path = os.path.join(gitdir, "zzzops-todo")
    with open(todo_path, "w", encoding="utf-8") as fh:
        fh.write(todo)
    git.run("switch", "-q", "-c", tmp, W, cwd=p)
    name, email = committer(git)
    editor = f'"{sys.executable}" -c "import shutil,sys; shutil.copyfile(sys.argv[1], sys.argv[2])" "{todo_path}"'
    r = git.run("-c", "commit.gpgSign=false", "rebase", "-q", "-i", "--no-autosquash", "--no-update-refs",
                "--committer-date-is-author-date", B, cwd=p, check=False,
                env={"GIT_SEQUENCE_EDITOR": editor, "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email})
    if r.returncode != 0:
        git.run("rebase", "--abort", cwd=p, check=False)
        git.run("switch", "-q", br, cwd=p, check=False)
        git.run("branch", "-q", "-D", tmp, check=False)
        raise EngineError(f"the review-free rebuild failed: {r.stderr.strip()[:300]}")
    H = git.out("rev-parse", "HEAD", cwd=p)
    git.run("switch", "-q", br, cwd=p)
    git.run("branch", "-q", "-D", tmp)
    if ident.code_tree(H) != T:
        raise EngineError("the rebuilt PR head has a different code tree")
    if git.out("diff", "--name-only", B, H, "--", REVIEW_PATH):
        raise EngineError("the rebuilt PR head contains review files")
    # 3. push the PR head; expected value = this invocation's fetched tip
    res, _ = push_atomic(git, snap.R, [(f"refs/heads/zzzops/pr/g{g}", snap.pr.get(g), H)])
    if res != "ok":
        raise Refused("contention", "the PR branch moved; run integrate again")
    snap.pr[g] = H
    # 4. the PR
    prs = gh.json("pr", "list", "--head", f"zzzops/pr/g{g}", "--state", "all", "--json",
                  "number,state,url,headRefOid,baseRefName,body") or []
    pr = prs[0] if prs else None

    def pr_out(base):
        return {"number": pr["number"], "url": pr["url"], "head": H, "tree": T, "base": base}

    if pr and pr["state"] == "CLOSED":
        return Blocked({"category": "external", "waiting_for": "human", "reason": f"PR #{pr['number']} closed without merging",
                        "question": f"PR #{pr['number']} for G{g} was closed on GitHub without merging. Reopen it, or cancel G{g}?",
                        "options": ["reopen the PR on GitHub, then answer 'reopened'", "cancel the goal"]})
    if pr and pr["state"] == "MERGED":
        if pr["baseRefName"] != I:
            return Blocked({"category": "external", "waiting_for": "human", "reason": "PR merged into another base",
                            "question": f"PR #{pr['number']} was merged into `{pr['baseRefName']}`, not `{I}`, so G{g}'s "
                                        f"code is not on `{I}`. Open a follow-up goal for it, then cancel G{g}."})
        if pr["headRefOid"] != H and ident.code_tree(pull_head(ctx, pr["number"])) != T:
            return Blocked({"category": "external", "waiting_for": "human", "reason": "PR merged other code",
                            "question": f"PR #{pr['number']} for G{g} was merged with code other than the reviewed checkpoint "
                                        f"({T[:7]}). Open a follow-up goal for the difference, then cancel G{g}."})
        return Done({"pr": pr_out(I), "ci": {"stacked": False, "required": [], "passed": [], "failed": []}}, ok=True)
    body = pr_body(ctx, g, stack, target, I)
    title = f"{ctx.doc['title']} (G{g})"
    if pr is None:
        url = gh.run("pr", "create", "--head", f"zzzops/pr/g{g}", "--base", target, "--title", title, "--body-file", "-",
                     input=body).strip().splitlines()[-1]
        n = int(url.rstrip("/").rsplit("/", 1)[-1])
        pr = {"number": n, "url": url, "state": "OPEN", "baseRefName": target}
    else:
        if pr["baseRefName"] != target:
            gh.run("pr", "edit", str(pr["number"]), "--base", target)
        if pr.get("body") != body:
            gh.run("pr", "edit", str(pr["number"]), "--body-file", "-", input=body)
    if target == f"zzzops/stack/g{g}":
        stack_pr(ctx, g, pr["number"], stack, B, I)
    out_pr = pr_out(target)
    v = gh.json("pr", "view", str(pr["number"]), "--json", "headRefOid,statusCheckRollup,mergeable,mergeStateStatus")
    # 5a. stacked PRs: required checks are not enforced
    if target != I:
        if v["headRefOid"] != H:
            return ctx.wait("GitHub has not seen the PR head yet", 120)
        checks = {}
        for item in v.get("statusCheckRollup") or []:
            checks[item.get("name") or item.get("context")] = classify(item)
        return Done({"pr": out_pr, "ci": {"stacked": True, "checks": checks}}, ok=True, summary=f"PR #{pr['number']} stacked")
    # 5b. PRs into I: a conflict first, then required checks
    if v["headRefOid"] == H and (v.get("mergeable") == "CONFLICTING" or v.get("mergeStateStatus") == "DIRTY"):
        return Done({"pr": out_pr, "ci": None}, ok=False,
                    findings=[{"key": "conflict", "input": "base",
                               "text": f"PR #{pr['number']} conflicts with {I} ({v.get('mergeStateStatus')}); rebase the work branch"}])
    req = list(ctx.settings["verification"]["required_ci"])
    if not req:
        return Done({"pr": out_pr, "ci": {"stacked": False, "required": [], "passed": [], "failed": []}}, ok=True,
                    summary=f"PR #{pr['number']}")
    status = {name: "pending" for name in req}
    urls = {}
    if v["headRefOid"] == H:
        for item in v.get("statusCheckRollup") or []:
            name = item.get("name") or item.get("context")
            if name in req:
                status[name] = classify(item)
                urls[name] = item.get("detailsUrl") or item.get("targetUrl") or ""
    rec = ctx.record
    st = {}
    if rec and rec["status"] == "blocked" and ((rec["blocked"].get("op_state") or {}).get("head") == H):
        st = rec["blocked"]["op_state"]
    if ctx.answer:
        st = {}
    failed = sorted(n for n, s in status.items() if s == "failed")
    pending = sorted(n for n, s in status.items() if s == "pending")
    now = ctx.now
    if failed:
        runs = sorted({m.group(1) for n in failed for m in [RUN_ID.search(urls.get(n, ""))] if m})
        if runs and st.get("rerun_head") != H:
            for rid in runs:
                gh.run("run", "rerun", rid, "--failed")
            return Blocked({"category": "external", "waiting_for": "time",
                            "reason": f"required checks failed ({', '.join(failed)}); re-ran once",
                            "retry_after": iso(now + 300),
                            "op_state": {"head": H, "pending_since": now, "polls": 0, "rerun_head": H}})
        return Done({"pr": out_pr, "ci": {"stacked": False, "required": req,
                                          "passed": sorted(set(req) - set(failed) - set(pending)), "failed": failed}},
                    ok=False, findings=[{"key": f"check-{n}", "input": "code",
                                         "text": f"required check `{n}` failed on {H[:7]}: {urls.get(n, '')}"} for n in failed])
    if pending:
        since, polls = st.get("pending_since", now), st.get("polls", 0)
        if now - since >= ctx.settings["verification"]["ci_timeout_minutes"] * 60:
            return Blocked({"category": "external", "waiting_for": "human", "reason": "required checks pending too long",
                            "question": f"Required checks {pending} have not finished on PR #{pr['number']} (head {H[:7]}) "
                                        f"after {(now - since) // 60} minutes. They may be path-filtered, renamed or stuck. "
                                        "Wait longer, or fix verification.required_ci through a policy branch?",
                            "options": ["wait: answer with text 'wait'", "fix verification.required_ci"],
                            "recommendation": "check the PR's checks on GitHub first",
                            "op_state": {"head": H, "pending_since": since, "polls": polls, "rerun_head": st.get("rerun_head")}})
        wait = min(5 * 2 ** polls, 30)
        return Blocked({"category": "external", "waiting_for": "time", "reason": f"required checks pending: {', '.join(pending)}",
                        "retry_after": iso(now + wait * 60),
                        "op_state": {"head": H, "pending_since": since, "polls": polls + 1, "rerun_head": st.get("rerun_head")}})
    return Done({"pr": out_pr, "ci": {"stacked": False, "required": req, "passed": req, "failed": []}}, ok=True,
                summary=f"PR #{pr['number']}: checks passed")


def pr_body(ctx, g, stack, target, I) -> str:
    summary = ctx.inputs.get("summary") or ""
    review = ctx.inputs.get("review") or ""
    body = f"{summary}\n\n## Review\n{review}\n\nZzzOps goal G{g}. Built from zzzops/work/g{g} without docs(review) commits."
    if target != I:
        body += "\n\n" + " ".join(f"Stacked on #{e['pr']} (G{e['goal']}), not merged yet." for e in stack)
    return body


def stack_pr(ctx, g, n, stack, B, I):
    git, gh = ctx.git, ctx.gh
    first_parent = git.out("rev-list", "--parents", "-n", "1", B).split()[1:2]
    with_I = bool(first_parent) and first_parent[0] not in {e["head"] for e in stack}
    title = f"Stack for #{n}: combines " + ", ".join(f"#{e['pr']}" for e in stack) + (f" and {I}" if with_I else "") \
        + " (do not merge)"
    body = (f"ZzzOps stack base for G{g} (PR #{n}). Combines:\n" + "".join(f"- #{e['pr']} (G{e['goal']})\n" for e in stack)
            + "\nZzzOps never merges this PR; it is closed when the stack set has fewer than two members.")
    sp = gh.json("pr", "list", "--head", f"zzzops/stack/g{g}", "--state", "open", "--json", "number,title,body") or []
    if not sp:
        gh.run("pr", "create", "--draft", "--head", f"zzzops/stack/g{g}", "--base", I, "--title", title, "--body-file", "-",
               input=body)
    elif sp[0].get("title") != title or sp[0].get("body") != body:
        gh.run("pr", "edit", str(sp[0]["number"]), "--title", title, "--body-file", "-", input=body)


def pull_head(ctx, n):
    R = ctx.snap.R
    ctx.git.run("fetch", "--no-tags", "--no-write-fetch-head", R, f"+refs/pull/{n}/head:refs/remotes/{R}/pull/{n}")
    return ctx.git.out("rev-parse", f"refs/remotes/{R}/pull/{n}")
