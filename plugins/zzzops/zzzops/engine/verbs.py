"""The lifecycle verbs: start (agent nodes), submit, renew, abandon, answer, reopen and edit (SPEC §4.12–§4.19)."""

from __future__ import annotations

import copy
import dataclasses
import json
import os
import re
import time

from engine import records as rec
from engine import schemas
from engine.canon import EMPTY_TREE, iso, parse_iso
from engine.errors import Refused
from engine.fingerprint import out_fp, stale_keys
from engine.frontier import live_input_changes, recorded_out, resolve
from engine.identity import Identity, conventional
from engine.leases import lease_ref, message as lease_message
from engine.render import clip, command, lease_commands, live_lease_entry, restart_command, state_string
from engine.store import goal_message, parse_commit, push_atomic
from engine import worktree as wt
from engine.ops import LINE_OPS

LABEL_ENV = (("CODEX_THREAD_ID", "codex"), ("CLAUDE_CODE_SESSION_ID", "claude"))


class Applied(Exception):
    """An earlier identical write by the same holder had already landed (a lost response)."""

    def __init__(self, out):
        self.out = out


def default_label(given: str | None) -> str:
    if given:
        label = given
    else:
        label = None
        for var, prefix in LABEL_ENV:
            if os.environ.get(var):
                label = f"{prefix}:{os.environ[var][:8]}"
                break
        if label is None:
            raise Refused("usage", "no holder label: pass --as <harness>:<id>")
    if not schemas.HOLDER.match(label):
        raise Refused("usage", f"holder label {label!r} must match {schemas.HOLDER.pattern}")
    return label


def pushed_summary(updates) -> dict:
    out = {}
    for ref, old, new in updates:
        short = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
        out[short] = "deleted" if not new else ("created" if not old else f"{old[:12]}..{new[:12]}")
    return out


# --------------------------------------------------------------------------------------------- shared lookups


def goal_result(s, g: int, allow_held=True):
    st = s.state
    if g not in s.snap.goals:
        raise Refused("not_found", f"G{g} does not exist")
    if g in st.invalid:
        raise Refused("validation", f"G{g} is invalid: " + "; ".join(st.invalid[g][:3]))
    if g in st.newer:
        raise Refused("engine_too_old", f"G{g} has a newer goal schema than this engine", hint="upgrade the plugin")
    doc = st.docs.get(g)
    if doc is None:
        raise Refused("not_found", f"G{g} could not be read")
    if doc["state"] == "closed":
        raise Refused("goal_closed", f"G{g} is closed ({doc['closed']['reason']})")
    if doc["state"] == "held" and not allow_held:
        raise Refused("goal_held", f"G{g} is held", hint="unhold it with edit (state: open) to continue")
    return s.portfolio().goals[g]


def valid_lease(s, g: int, X: str):
    doc = s.state.docs.get(g)
    L = s.state.leases.get((g, X))
    if not L or not doc or doc["state"] == "closed":
        return None
    graph = s.state.graphs.get(doc["graph"])
    if graph is None or X not in graph.nodes:
        return None
    r = (doc.get("records") or {}).get(X)
    if r and r["attempt"] >= L.attempt:
        return None
    return L


def claimed_at(s, tip: str) -> int | None:
    roots = s.git.out("rev-list", "--max-parents=0", tip).split()
    if not roots:
        return None
    raw = s.git.cat(roots[0])
    return parse_commit(roots[0], raw).committer_date if raw else None


def node_of(res, X):
    if X not in res.graph.nodes:
        raise Refused("not_found", f"G{res.goal} has no node {X!r}")
    return res.graph.nodes[X]


def finish_output(s, g, updates, closed, extra=None) -> dict:
    out = {"ok": True, "coordinator": s.state.coordinator}
    out.update(extra or {})
    out["pushed"] = pushed_summary(updates)
    if g in closed:
        doc = s.state.docs[g]
        out["closed"] = dict(doc["closed"], worktree=wt.remove_if_safe(s.git, s.snap, g))
    out["next"] = s.render_next(scope=[g])
    return out


# --------------------------------------------------------------------------------------------- start (agents)


def start(s, g: int, X: str, label: str, reclaim=False, force=False) -> dict:
    s.open(goals=[g], deps=dependency_ids(s, g))
    st = s.state
    if st.policy_branches:
        b = st.policy_branches[0]
        raise Refused("policy_branch", f"a policy change is in progress on zzzops/policy/{b['topic']}: new work is paused",
                      hint=f"land the branch on {s.snap.I} and delete it, or delete it to abandon the change")
    s.require_writable([g])
    res = goal_result(s, g, allow_held=False)
    nd = node_of(res, X)
    state = res.st[X]
    name = state["name"]
    if nd["kind"] == "human":
        raise Refused("not_ready", f"{X} is a human decision: answer it with `answer`")
    if name == "running":
        if not (reclaim and force):
            L = state["lease"]
            raise Refused("lease_held", f"G{g} {X} is held by {L.holder} until {iso(L.expires_at)}",
                          details={"holder": L.holder, "attempt": L.attempt, "expires_at": iso(L.expires_at)})
    elif name == "reclaimable":
        if not reclaim:
            raise Refused("not_ready", "the lease expired; pass --reclaim")
    elif name == "needs_human" and state["kind"] == "crash_loop":
        if not force or (state["cap"] == "lease" and not reclaim):
            raise Refused("crash_loop", f"G{g} {X} hit the {state['cap']} cap; one more try needs --force"
                          + (" --reclaim" if state["cap"] == "lease" else ""))
    elif name != "ready":
        raise Refused("not_ready", f"G{g} {X} is {state_string(state)}")
    p = s.portfolio()
    if reclaim and p.mass_expiry and not force:
        raise Refused("mass_expiry", "most leases expired at once (a machine that slept?); reclaim needs --force",
                      hint="ask the human before --force")
    if nd["kind"] == "agent" and res.budget.get("over"):
        raise Refused("budget_exceeded", f"G{g} has used {res.budget['used']} correction runs (limit {res.budget['limit']})",
                      hint="answer the budget item first")
    subj = res.graph.subject(X) or res.graph.filter_subject(X)       # a filter's subject comes from its lenses
    if subj and nd["kind"] == "agent":
        sr = (res.doc.get("records") or {}).get(subj)
        if sr and sr.get("holder") == label:
            raise Refused("independence", f"{label} produced {subj}; a different agent must review it")
    if nd.get("workspace"):
        for (lg, node), L in sorted(st.leases.items()):
            if lg == g and node != X and res.graph.nodes.get(node, {}).get("workspace") and valid_lease(s, g, node) and L.live(s.now):
                raise Refused("workspace_busy", f"G{g} {node} holds the goal worktree", details={"node": node, "holder": L.holder})
    if nd.get("workspace") and reclaim and not force:
        wp = wt.worktree_path(s.git, g)
        if os.path.isdir(wp) and not wt.is_clean(s.git, wp):
            raise Refused("dirty_worktree", f"the goal worktree {wp} has uncommitted changes from the previous attempt",
                          hint="inspect it; pass --force to reclaim anyway")
    if nd["kind"] == "agent" and p.live_agents >= s.settings["parallelism"]["max_workers"]:
        raise Refused("capacity", f"{p.live_agents} agent phases are running (max {s.settings['parallelism']['max_workers']})")
    if nd["kind"] == "op":
        from engine.ops.run import start_op
        return start_op(s, res, X, label, state, reclaim, force)
    lease, workspace = claim(s, res, X, label, state, reclaim, force)
    from engine import card
    return card.build(s, res, X, lease["kind_state"], lease)


def dependency_ids(s, g):
    """`start` on a git.base node also fetches its dependencies' PR branches (SPEC §4.2)."""
    s.resolve()
    tip = s.git.rev_parse(f"refs/zzzops/goal/{s.R}/g{g}")
    if not tip:
        return []
    data = s.git.cat(f"{tip}:goal.json")
    try:
        doc = json.loads(data.decode("utf-8")) if data else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []
    return [d for d in doc.get("depends_on") or [] if isinstance(d, int)]


def lease_state(s, res, X, state, force):
    """The state whose fingerprint the lease records; a forced reclaim of a live lease re-evaluates without it."""
    if state["name"] == "running":
        leases = {k: v for k, v in s.state.leases.items() if k != (res.goal, X)}
        p = s.portfolio(leases=leases)
        state = p.goals[res.goal].st[X]
        if state["name"] not in ("ready", "reclaimable", "needs_human"):
            raise Refused("not_ready", f"G{res.goal} {X} is {state_string(state)} without its lease")
    return state


def claim(s, res, X, label, state, reclaim, force, extra_updates=()):
    g = res.goal
    nd = res.graph.nodes[X]
    st0 = state
    state = lease_state(s, res, X, state, force)
    L = s.state.leases.get((g, X))
    r = (res.doc.get("records") or {}).get(X)
    valid = valid_lease(s, g, X)
    attempt = max(r["attempt"] if r else 0, valid.attempt if valid else 0) + 1
    timeout = nd.get("timeout") or (s.settings["leases"]["ttl_minutes"] if nd["kind"] == "agent" else 15)
    if valid and st0["name"] in ("reclaimable", "running") or (valid and state.get("cap") == "lease"):
        reason = valid.reason
    elif state["name"] == "needs_human":
        reason = {"repeat": "retry", "op_finding": "not_ok"}.get(state.get("cap"), "retry")
    else:
        reason = state.get("reason", "retry")
    fp, parts = state.get("fp"), state.get("parts")
    if fp is None or parts is None:
        raise Refused("not_ready", f"G{g} {X} has no resolvable inputs")
    prompt = s.git.rev_parse(f"{s.snap.policy_commit}:.zzzops/prompts/{nd['prompt']}") if nd.get("prompt") else None
    updates = list(extra_updates)
    workspace = None
    if nd.get("workspace"):
        ident = Identity(s.git)
        if reclaim and not force:
            p = wt.ensure_worktree(s.git, s.snap, g)
            if not wt.is_clean(s.git, p):
                raise Refused("dirty_worktree", f"the goal worktree {p} has uncommitted changes from the previous attempt",
                              hint="inspect it; pass --force to reclaim anyway")
        if not s.op_self_sync(nd):
            if wt.sync(s.git, ident, s.snap, g, "dirty_ok", X, attempt) == "ahead":
                tip = wt.local_tip(s.git, g)
                if tip and tip != s.snap.work.get(g):
                    updates.append((f"refs/heads/zzzops/work/g{g}", s.snap.work.get(g), tip))
        elif nd.get("op") not in LINE_OPS:            # a line goal has no work branch: its ops make a detached worktree
            wt.ensure_worktree(s.git, s.snap, g, self_sync=True)
        workspace = wt.worktree_path(s.git, g)
    work = s.snap.work.get(g)
    msg = lease_message("lease", g, X, attempt, label, reason, timeout, work, fp, parts, prompt)
    c = s.git.commit_tree(EMPTY_TREE, [], msg)
    ref = lease_ref(g, X)
    updates.insert(0, (ref, s.snap.leases.get((g, X)), c))     # replaces an orphan or unparsable lease too
    r_, stderr = push_atomic(s.git, s.R, updates)
    if r_ == "remote":
        raise Refused("remote", f"push to `{s.R}` failed")
    if r_ == "rejected":
        s.refetch([g])
        W = s.state.leases.get((g, X))
        raise Refused("claim_lost", f"another agent claimed G{g} {X} first",
                      details={"holder": W.holder if W else None})
    s.snap.advance(updates)
    from engine.leases import parse_message, to_lease
    s.state.leases[(g, X)] = to_lease(parse_message(msg), c, s.now, s.now)
    s._portfolio = None
    lease = {"attempt": attempt, "holder": label, "timeout": timeout, "expires_at": s.now + timeout * 60,
             "reason": reason, "card_reason": "reclaim" if st0["name"] in ("reclaimable", "running") else reason,
             "prompt": prompt, "workspace": workspace, "tip": c, "work": work, "fp": fp, "parts": parts,
             "kind_state": dict(state, **staleness(s, st0, state, r, parts))}
    return lease, workspace


def staleness(s, st0, state, r, parts) -> dict:
    """The card's `stale_because` (since the record and, for a reclaim, since the abandoned attempt started),
    `record_stale` (since the record only; it drives capability) and where the `changed` pointers start."""
    L_old = st0.get("lease")
    rec_sb = set(stale_keys(r.get("fp_parts"), parts)) if r and r.get("input_fp") != state.get("fp") else set()
    sb = rec_sb | (set(stale_keys(L_old.fp_parts, parts)) if L_old is not None else set())
    out = {"stale_because": sorted(sb) or None, "record_stale": sorted(rec_sb) or None, "changed_from": None}
    if sb:
        old = {"inputs": dict((L_old.fp_parts.get("inputs") or {}) if L_old else {})}
        since = []
        if L_old is not None:
            since.append(claimed_at(s, L_old.tip))
        if rec_sb:
            old["inputs"].update({k: v for k, v in ((r.get("fp_parts") or {}).get("inputs") or {}).items()
                                  if f"inputs.{k}" in rec_sb})
            since.append(parse_iso(r["finished_at"]) if r.get("finished_at") else None)
        since = [x for x in since if x is not None]
        out["changed_from"] = {"parts": old, "since": min(since) if since else None}
    return out


# --------------------------------------------------------------------------------------------- submit (§4.14)


def submit(s, g: int, X: str, N: int, label: str, output=None, artifact=None, blocked=None) -> dict:
    if (output is None) == (blocked is None):
        raise Refused("usage", "submit needs exactly one of --output F or --blocked F")
    s.open(goals=[g])
    data = {}
    if output is not None:
        data["out"] = load(output, "output")
    if blocked is not None:
        data["blocked"] = load(blocked, "blocked")
    if artifact is not None:
        try:
            with open(artifact, "rb") as fh:
                data["artifact"] = fh.read()
        except FileNotFoundError:
            raise Refused("not_found", f"artifact file {artifact!r} not found")
    work = {}

    def mutate(sess, docs):
        work.clear()
        cur = docs.get(g)
        r_prev = ((cur or {}).get("records") or {}).get(X)
        L = valid_lease(sess, g, X)
        if L is None and r_prev and r_prev["attempt"] == N and r_prev["holder"] == label:
            raise Applied(r_prev)                              # our earlier submit landed (lost response), even if it closed the goal
        if cur is not None and cur["state"] == "closed":
            raise Refused("superseded", f"Stop this phase: G{g} was closed ({cur['closed']['reason']}).",
                          hint=superseded_hint(sess, g, X, N))
        res = goal_result(sess, g)
        doc = copy.deepcopy(docs[g])
        graph = res.graph
        if X not in graph.nodes:
            raise Refused("superseded", "this phase cannot finish: the node was removed from the workflow",
                          hint=superseded_hint(sess, g, X, N))
        nd = graph.nodes[X]
        r0 = (doc.get("records") or {}).get(X)
        if L is None or L.attempt != N:
            raise Refused("superseded", "Stop this phase. Nothing you sent landed.", hint=superseded_hint(sess, g, X, N))
        if L.timeout == 0:
            raise Refused("superseded", "this phase was abandoned", hint=superseded_hint(sess, g, X, N))
        ident = Identity(sess.git)
        if "blocked" in data:
            record = blocked_record(sess, res, doc, X, L, r0, data["blocked"], ident, work)
        else:
            record = done_record(sess, res, doc, X, L, r0, data["out"], data.get("artifact"), ident, work)
        doc["records"][X] = record
        work["record"] = record
        return {g: doc}

    def extra(sess, new):
        L = valid_lease(sess, g, X)
        ups = [(lease_ref(g, X), L.tip, None)]
        nt = work.get("new_tip")
        if nt and nt != sess.snap.work.get(g):
            ups.append((f"refs/heads/zzzops/work/g{g}", sess.snap.work.get(g), nt))
        return ups

    def message(gg, old, new):
        r = new["records"][X]
        return goal_message("submit", gg, outcome_of(s, gg, X, r, old, new), new["state"], X, N, label)

    try:
        kind, updates, closed = s.write_goals("submit", [g], mutate, extra, message=message)
    except Applied as a:
        r = a.out
        return {"ok": True, "coordinator": s.state.coordinator, "applied": True,
                "recorded": {"goal": g, "node": X, "attempt": r["attempt"], "status": r["status"], "ok": r["ok"],
                             "findings": len(r.get("findings") or [])},
                "pushed": {}, "next": s.render_next(scope=[g])}
    r = work["record"]
    extra_out = {"recorded": {"goal": g, "node": X, "attempt": N, "status": r["status"], "ok": r["ok"],
                              "findings": sum(1 for f in r.get("findings") or [] if f["status"] == "open")}}
    if kind == "applied":
        extra_out["applied"] = True
    return finish_output(s, g, updates, closed, extra_out)


def load(path, what):
    try:
        with open(path, "rb") as fh:
            return json.loads(fh.read().decode("utf-8"))
    except FileNotFoundError:
        raise Refused("not_found", f"{what} file {path!r} not found")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refused("validation", f"{what} file {path!r} is not valid JSON: {exc}")


def superseded_hint(s, g, X, N) -> str:
    lines = ["Stop this phase. Nothing you sent landed. Committed work stays in the goal worktree."]
    if os.path.isdir(wt.worktree_path(s.git, g)):
        lines += wt.salvage_lines(s.git, s.snap, g, X, N)
    return "\n".join(lines)


def corrections_of(res, X):
    return sorted((f for _, f in res.live.get(X, [])), key=lambda f: f["id"])


def x_fp(res, X):
    st = res.st[X]
    return st.get("fp") if st["name"] in ("running", "reclaimable", "ready") else None


def blocked_record(s, res, doc, X, L, r0, b, ident, work):
    errs = schemas.validate_blocked_file(b)
    if errs:
        raise Refused("validation", "; ".join(errs), details={"errors": list(errs)})
    nd = res.graph.nodes[X]
    g = res.goal
    if nd.get("workspace"):
        if wt.sync(s.git, ident, s.snap, g, "dirty_ok", X, L.attempt) == "ahead":
            work["new_tip"] = wt.local_tip(s.git, g)
    wf = b["waiting_for"]
    text = b.get("question") if wf == "human" else b.get("instructions")
    reason = b.get("reason") or (text or "").strip().splitlines()[0][:200]
    blocked = {"category": b.get("category", "decision"), "waiting_for": wf, "reason": reason,
               "repeats": rec.blocked_repeats(r0, wf, reason)}
    for k in ("instructions", "question", "options", "recommendation"):
        if k in b:
            blocked[k] = b[k]
    last = (r0["output"] if r0 and r0["status"] == "done" else (r0 or {}).get("last_output"))
    extra = {"last_output": last} if nd["kind"] == "agent" and "blocked_findings" in schemas.required_caps(s.settings) else {}
    return rec.record("blocked", False, L.attempt, L.holder, L.reason, r0, L.input_fp, L.fp_parts, None, [], s.now,
                      prompt=L.prompt, blocked=blocked, **extra)


def response_why(graph, doc, X, fid):
    """Explain an obsolete response from the latest loaded records (G1040)."""
    records = doc.get("records") or {}
    f = next((f for r in records.values() for f in r.get("findings") or [] if f["id"] == fid), None)
    if f is None:
        return "superseded"
    if f["status"] in ("resolved", "waived"):
        return f["status"]
    if f["target"] != X:
        return "other_target"
    r = records.get(X)
    if r and r["status"] == "blocked":
        if "last_output" not in r:
            return "target_blocked"
        r = dict(r, status="done", output=r["last_output"])
    if not r or f["target_fp"] is None or f["target_fp"] != out_fp(graph, X, r):
        return "target_changed"
    return "not_live"


def done_record(s, res, doc, X, L, r0, out_in, artifact, ident, work):
    graph = res.graph
    nd = graph.nodes[X]
    g = res.goal
    out = copy.deepcopy(out_in)
    errs = schemas.validate_submit_output(graph, X, out)
    if errs:
        code = "too_large" if any("too_large" in e for e in errs) else "validation"
        raise Refused(code, "; ".join(errs[:5]), details={"errors": list(errs)},
                      hint="put long text in the artifact" if code == "too_large" else None)
    if any(isinstance(f, dict) and "follows" in f for f in out.get("findings") or []) \
            and not schemas.follows_required(s.settings):
        raise Refused("validation", "follows needs the policy to keep older engines away from it: "
                                    "settings.engine.requires must include capability `finding_follows`",
                      hint="Resolve the prior finding and raise a plain new finding, or ask the owner to push a policy "
                           "branch adding `finding_follows` to settings.engine.requires.")
    corr = corrections_of(res, X)
    carriers = {f["id"]: c for c, f in res.live.get(X, [])}
    rec.check_responses(out.get("responses", {}), corr, carriers, s.ctx().reader.blob_view,
                        lambda fid: response_why(res.graph, doc, X, fid))
    if not out.get("responses"):
        out.pop("responses", None)
    vals_rec, _ = resolve(graph, doc, X, lambda p: recorded_out(doc, p), s.portfolio().views)
    new_tip = s.snap.work.get(g)
    frozen = None
    cp_key = None
    if nd.get("workspace"):
        if wt.sync(s.git, ident, s.snap, g, "clean", X, L.attempt) == "ahead":
            new_tip = wt.local_tip(s.git, g)
        head = wt.local_tip(s.git, g)
        origin = s.snap.work.get(g) or s.snap.integration
        for c in s.git.out("rev-list", "--reverse", f"{origin}..{head}").split():
            if len(s.git.out("rev-list", "--parents", "-n", "1", c).split()) > 2:
                raise Refused("validation", f"merge commit {c[:12]}: only base makes merge commits in a work branch")
            subject = ident.subject(c)
            parsed = conventional(subject)
            if parsed is None:
                raise Refused("commit_subject", f"commit {c[:12]} has a non-conventional subject: {subject}",
                              details={"commit": c, "subject": subject},
                              hint="Reword your unpushed commits with git commit --amend or git rebase -i, then submit again.")
            if any(n2.get("preserve") == X for n2 in graph.nodes.values()) and parsed[0] != "test":
                raise Refused("test_commit_type", f"{X} commits must use type test; commit {c[:12]} is {parsed[0]}: {subject}",
                              details={"commit": c, "subject": subject, "type": parsed[0]})
            if nd.get("preserve"):
                accepted = (doc.get("records") or {}).get(nd["preserve"]) or {}
                bad = sorted(set(accepted.get("frozen") or []) & set(ident.changed_paths(c)))
                if bad:
                    raise Refused("test_freeze", f"commit {c[:12]} changed accepted test paths: " + ", ".join(bad))
        ident.check_i1_i2(origin, head)
        for k in graph.checkpoint_outputs(X):
            cp_key = k
            given = (out.get(k) or {}).get("commit")
            c = given or head
            full = s.git.rev_parse(c)
            if not full:
                raise Refused("validation", f"checkpoint commit {c!r} does not exist")
            c = full
            if not (c == head or s.git.is_ancestor(c, head)):
                raise Refused("validation", f"checkpoint {c[:12]} is not in the work branch (HEAD {head[:12]})")
            base = vals_rec["base"]
            out[k] = {"commit": c, "base": base, "tree": ident.code_tree(c)}
            if any(n2.get("preserve") == X for n2 in graph.nodes.values()):
                frozen = frozen_paths(s, r0, L, out[k], ident)
            scope = rec.checkpoint_scope(graph, X, {"frozen": frozen} if frozen is not None else (r0 or {}))
            out[k]["change"] = ident.change(base, c, paths=scope)
        if nd.get("preserve") and cp_key:
            preserve_check(s, res, doc, X, out[cp_key], ident)
    arts = graph.artifact_outputs(X)
    if arts:
        if artifact is None:
            raise Refused("validation", f"{X} needs --artifact (the {arts[0]} file)")
        new_tip, out[arts[0]] = ident.artifact_commit(new_tip, s.snap.integration, g, X, artifact)
    elif artifact is not None:
        raise Refused("validation", f"{X} has no artifact output")
    work["new_tip"] = new_tip
    if graph.is_filter(X):
        check_verdicts(out.get("verdicts"), (L.fp_parts or {}).get("candidates") or [])
    given = out.pop("findings", [])
    xfp = x_fp(res, X)
    fence = rec.make_fence(graph, doc, xfp, L.input_fp, claimed_at(s, L.tip))
    findings, ok = rec.process_findings(graph, doc, X, r0, given, L.attempt, fence, out.get("decision"))
    fresh = L.input_fp is not None and L.input_fp == xfp
    extra = {"reviewed": rec.reviewed(graph, doc, X, fresh)} if graph.is_review(X) else {}
    if frozen is not None:
        extra["frozen"] = frozen
    return rec.record("done", ok, L.attempt, L.holder, L.reason, r0, L.input_fp, L.fp_parts, out, findings, s.now,
                      prompt=L.prompt, **extra)


def check_verdicts(verdicts, candidates: list):
    """A filter's verdicts: `keep` or `note`, with a reason, for exactly the non-material candidates on its card (the
    lease's `candidates` part), so nothing is dropped silently."""
    want = sorted(i for i, material in candidates if not material)
    if not isinstance(verdicts, dict):
        raise Refused("validation", "verdicts must be an object")
    missing, extra = sorted(set(want) - set(verdicts)), sorted(set(verdicts) - set(want))
    if missing or extra:
        msg = []
        if missing:
            msg.append("give a verdict for: " + ", ".join(missing))
        if extra:
            msg.append("not a note on your card (material findings reopen the work whatever you decide): "
                       + ", ".join(extra))
        raise Refused("validation", "; ".join(msg),
                      hint="verdicts: {\"<id>\": {\"verdict\": \"keep\" | \"note\", \"reason\": \"…\"}} for every "
                           "non-material candidate")
    for i in want:
        v = verdicts[i]
        if (not isinstance(v, dict) or set(v) != {"verdict", "reason"} or v.get("verdict") not in ("keep", "note")
                or not isinstance(v.get("reason"), str) or not v["reason"].strip()):
            raise Refused("validation", f"verdicts.{i} must be {{\"verdict\": \"keep\" | \"note\", \"reason\": \"<text>\"}}")


def diff_paths(git, a_tree, b_tree) -> set:
    out = git.run("diff-tree", "-r", "--no-renames", "--name-only", "-z", a_tree, b_tree, text=False).stdout
    return {p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p}


def frozen_paths(s, r0, L, cp, ident) -> list:
    prev = set(r0.get("frozen") or []) if r0 and r0["status"] == "done" else set()
    W = L.work
    if W and s.git.is_ancestor(cp["commit"], W):
        return sorted(prev)
    a = W if W and s.git.is_ancestor(W, cp["commit"]) else cp["base"]
    return sorted(prev | diff_paths(s.git, ident.code_tree(a), ident.code_tree(cp["commit"])))


def preserve_check(s, res, doc, X, new_cp, ident):
    graph = res.graph
    P = graph.nodes[X]["preserve"]
    pr = (doc.get("records") or {}).get(P)
    if not pr or pr["status"] != "done":
        return
    k = graph.checkpoint_outputs(P)[0]
    T = pr["output"][k]
    frozen = set(pr.get("frozen") or [])
    touched = diff_paths(s.git, ident.code_tree(T["commit"]), ident.code_tree(new_cp["commit"]))
    bad = sorted(frozen & touched)
    if bad:
        raise Refused("test_freeze", f"{X} changed accepted test paths: " + ", ".join(bad),
                      details={"paths": [{"path": p} for p in bad],
                               "route": f"Restore these paths and resubmit. If a frozen test is wrong, keep it unchanged "
                                        f"and add findings: [{{\"target\": \"{P}\", \"text\": \"…\"}}] to your output."})


def outcome_of(s, g, X, r, old, new) -> str:
    if r["status"] == "blocked":
        b = r["blocked"]
        if b["waiting_for"] == "time":
            return f"waiting until {b['retry_after'][11:16]}: {b['reason']}"
        return f"blocked ({b['waiting_for']}): {b['reason']}"
    opened = [f for f in r.get("findings") or [] if f["status"] == "open"]
    head = "ok"
    if opened:
        targets = sorted({f["target"] for f in opened})
        decision = (r.get("output") or {}).get("decision")
        if decision == "approved":     # a filtered lens approving with notes
            head = f"approved with {len(opened)} note{'s' if len(opened) != 1 else ''} → {', '.join(targets)}"
        else:
            label = "changes_requested" if decision == "changes_requested" else "failed"
            head = f"{label}: {len(opened)} finding{'s' if len(opened) != 1 else ''} → {', '.join(targets)}"
    if new["state"] == "closed" and (old or {}).get("state") != "closed":
        head += f"; closed: {new['closed']['reason']}"
    return head


# --------------------------------------------------------------------------------------------- renew, abandon (§4.12)


def renew(s, g: int, X: str, N: int) -> dict:
    deadline = time.monotonic() + 30
    while True:
        s.open(goals=[g]) if s.snap is None else s.refetch([g])
        if s.state.write_block is not None:
            raise s.state.write_block                          # never a false "superseded" (policy unreadable)
        L = valid_lease(s, g, X)
        if not L or L.attempt != N:
            raise Refused("superseded", f"G{g} {X} attempt {N} is no longer the lease",
                          details={"lease": {"attempt": L.attempt, "holder": L.holder} if L else None})
        if L.timeout == 0:
            raise Refused("superseded", "this phase was abandoned")
        body = s.state.lease_commits[(g, X)].message.split("\n", 1)[1]
        c = s.git.commit_tree(EMPTY_TREE, [L.tip], f"zzzops renew G{g} {X}\n{body}")
        r, _ = push_atomic(s.git, s.R, [(lease_ref(g, X), L.tip, c)])
        if r == "ok":
            out = {"ok": True, "coordinator": s.state.coordinator, "attempt": N,
                   "expires_at": iso(s.now + L.timeout * 60), "renew_every_minutes": max(1, L.timeout // 4)}
            try:
                out.update(renew_inputs_changed(s, g, X, L))
            except Exception:                                  # a renew that pushed is never reported as failed
                pass
            return out
        if r == "remote":
            raise Refused("remote", f"push to `{s.R}` failed")
        if time.monotonic() > deadline:
            raise Refused("contention", "could not renew the lease")


def renew_inputs_changed(s, g: int, X: str, L) -> dict:
    """Fields to add when the phase's inputs changed since start: evaluated with the lease as this renew made it, so
    an expired-then-renewed lease is running too."""
    L2 = dataclasses.replace(L, last_active=s.now)
    p = s.portfolio(leases={**s.state.leases, (g, X): L2})
    res = p.goals.get(g)
    a = res.st.get(X) if res else None
    if not a or a["name"] != "running" or a["fp"] == L.input_fp:
        return {}
    abandon_cmd, restart_cmd = lease_commands(s.ctx(worker=True), g, X, L.attempt)
    return {"inputs_changed": True,
            "stale_because": stale_keys(L.fp_parts, a["parts"]) if a["parts"] else ["unresolved"],
            "abandon": abandon_cmd, "restart": restart_cmd,
            "hint": "Your inputs changed after start: work submitted now lands stale and the phase re-runs. Stop, report, "
                    "and let the root abandon and restart (or finish if nearly done)."}


def abandon(s, g: int, X: str, N: int | None, force=False, note=None) -> dict:
    s.open(goals=[g])
    if s.state.write_block is not None:
        raise s.state.write_block
    if force:
        s.require_writable([g])
    L = valid_lease(s, g, X)
    if not L:
        raise Refused("not_found", f"G{g} {X} has no lease")
    if not force and L.attempt != N:
        raise Refused("superseded", f"G{g} {X} attempt {N} is no longer the lease")
    body = s.state.lease_commits[(g, X)].message.split("\n", 1)[1]
    body = re.sub(r"(?m)^Timeout: \d+$", "Timeout: 0", body)
    c = s.git.commit_tree(EMPTY_TREE, [L.tip], f"zzzops abandon G{g} {X}\n{body}")
    ups = [(lease_ref(g, X), L.tip, c)]
    if force:
        tip = s.snap.goals[g]
        tree = s.git.out("rev-parse", f"{tip}^{{tree}}")
        doc = s.state.docs[g]
        msg = (f"zzzops: abandon G{g} {X} attempt {L.attempt} --force\n\n{note or 'forced'}\n\n"
               f"Outcome: abandoned\nState: {doc['state']}\nEngine: {__import__('engine').build_id()}\n")
        ups.append((f"refs/heads/zzzops/goal/g{g}", tip, s.git.commit_tree(tree, [tip], msg)))
    r, _ = push_atomic(s.git, s.R, ups)
    if r == "remote":
        raise Refused("remote", f"push to `{s.R}` failed")
    if r == "rejected":
        raise Refused("contention", "the lease or goal moved; retry")
    out = {"ok": True, "coordinator": s.state.coordinator, "expired": f"zzzops/lease/g{g}/{X}",
           "restart": restart_command(s.ctx(worker=True), g, X),
           "hint": "The node is now reclaimable: a plain start is refused; run restart."}
    if note:
        out["note"] = note
    return out


# --------------------------------------------------------------------------------------------- answer (§4.15)


def answer(s, g: int, X: str, fp: str, path: str) -> dict:
    a = load(path, "answer")
    s.open(goals=[g])
    info = {}

    def mutate(sess, docs):
        res = goal_result(sess, g)
        doc = copy.deepcopy(docs[g])
        graph = res.graph
        nd = node_of(res, X)
        state = res.st[X]
        records = doc["records"]
        if "finding" in a:
            errs = schemas.validate_answer_file("dispute", a)
            if errs:
                raise Refused("validation", "; ".join(errs))
            r = records.get(X) or {}
            f = next((f for f in r.get("findings") or [] if f["id"] == a["finding"]), None)
            if f is None:
                raise Refused("not_found", f"{X} carries no finding {a['finding']!r}")
            tgt = f["target"]
            esc = res.st.get(tgt, {})
            live = any(c == X and y["id"] == f["id"] for c, y in res.live.get(tgt, []))
            if a["decision"] == "uphold" and f.get("upheld"):
                raise Applied(r)
            if a["decision"] == "waive" and f["status"] == "waived":
                raise Applied(r)
            if not live or not (esc.get("name") == "needs_human" and esc.get("kind") == "dispute"):
                raise Refused("not_ready", f"{a['finding']} is not an escalated dispute")
            if fp != r["input_fp"]:
                raise Refused("fp_mismatch", "the dispute changed; see the current item", details={"current": item_for(sess, g, X)})
            if a["decision"] == "waive" and nd["kind"] == "op":
                raise Refused("validation", "waiving cannot make a check pass: uphold, skip the op, or cancel")
            if a["decision"] == "uphold":
                f["upheld"] = True
            else:
                f["status"], f["note"] = "waived", a["quote"]
            info["outcome"] = f"{a['decision']}: {f['id']}"
            return {g: doc}
        if nd["kind"] == "human":
            if state["name"] == "current" and (records.get(X) or {}).get("input_fp") == fp:
                raise Applied(records[X])
            if not (state["name"] == "needs_human" and state["kind"] == "approve"):
                raise Refused("not_ready", f"G{g} {X} is {state_string(state)}")
            ready = state["ready"]
            if fp != ready["fp"]:
                raise Refused("fp_mismatch", "the question changed: answer the current one",
                              details={"current": item_for(sess, g, X)})
            errs = schemas.validate_answer_file("approve", a)
            if errs:
                raise Refused("validation", "; ".join(errs))
            r0 = records.get(X)
            attempt = (r0["attempt"] if r0 else 0) + 1
            fence = rec.make_fence(graph, doc, ready["fp"], ready["fp"], s.now)
            findings = rec.human_findings(graph, X, r0, a.get("findings") or [], attempt, a["decision"], a["quote"], fence,
                                          skip=doc.get("skip") or {})
            out = {"decision": a["decision"], "summary": a["summary"], "decided_by": a["decided_by"], "quote": a["quote"],
                   "decided_at": a.get("decided_at") or iso(s.now)}
            auto = rec.auto_responses(graph, X, ready.get("corrections") or [], a["decided_by"])
            if auto:
                out["responses"] = auto
            records[X] = rec.record("done", a["decision"] == "approved", attempt, "human", ready["reason"], r0, fp,
                                    ready["parts"], out, findings, s.now, reviewed=rec.reviewed(graph, doc, X))
            info["outcome"] = "ok" if a["decision"] == "approved" else f"changes_requested → {graph.subject(X)}"
            return {g: doc}
        r = records.get(X)
        if r and r["status"] == "blocked" and r.get("answer", {}).get("text") == a.get("text"):
            raise Applied(r)
        if not (state["name"] == "needs_human" and state["kind"] == "blocked"):
            raise Refused("not_ready", f"G{g} {X} is {state_string(state)}")
        if fp != r["input_fp"]:
            raise Refused("fp_mismatch", "the question changed", details={"current": item_for(sess, g, X)})
        errs = schemas.validate_answer_file("blocked", a)
        if errs:
            raise Refused("validation", "; ".join(errs))
        r["answer"] = {"text": a["text"], "quote": a["quote"], "decided_by": a["decided_by"],
                       "decided_at": a.get("decided_at") or iso(s.now)}
        r["blocked"]["waiting_for"] = "agent"
        r["blocked"]["instructions"] = r["blocked"].get("instructions") or f"The human answered: {a['text']}"
        info["outcome"] = "answered: " + a["text"].splitlines()[0][:80]
        return {g: doc}

    def message(gg, old, new):
        return goal_message("answer", gg, info.get("outcome", "ok"), new["state"], X)

    before = s.portfolio()
    try:
        kind, updates, closed = s.write_goals("answer", [g], mutate, message=message)
    except Applied as ap:
        return {"ok": True, "coordinator": s.state.coordinator, "applied": True,
                "recorded": {"goal": g, "node": X}, "next": s.render_next(scope=[g])}
    out = finish_output(s, g, updates, closed, {"recorded": {"goal": g, "node": X, "outcome": info.get("outcome")}})
    out["preview"] = impact(before, s.portfolio(), [g])
    return out


def item_for(s, g, X):
    from engine.render import human_items
    res = s.portfolio().goals.get(g)
    if not res:
        return None
    for _, it in human_items(s.ctx(), res, True):
        if it["node"] == X:
            return it
    return None


# --------------------------------------------------------------------------------------------- reopen, edit (§4.18)


def reopen(s, g: int, X: str, note: str) -> dict:
    if not note or not note.strip():
        raise Refused("usage", "reopen needs --note")
    s.open(goals=[g])
    info = {}

    def mutate(sess, docs):
        res = goal_result(sess, g)
        node_of(res, X)
        doc = copy.deepcopy(docs[g])
        r = doc["records"].get(X)
        if not r or r["status"] != "done":
            raise Refused("not_ready", "nothing to reopen")
        waived = [f for f in r["findings"] if f["status"] == "open" and f["target"] != X]
        for f in waived:
            f["status"], f["note"] = "waived", f"withdrawn: {X} reopened ({note})"
        n = 1 + sum(1 for f in r["findings"] if f["id"].startswith(f"{X}:reopen:"))
        f = {"id": f"{X}:reopen:{n}", "target": X, "target_fp": out_fp(res.graph, X, r), "target_attempt": r["attempt"],
             "text": note, "status": "open", "response": None, "rounds": 1, "upheld": False, "note": None}
        r["findings"].append(f)
        info["finding"], info["waived"] = f, [x["id"] for x in waived]
        return {g: doc}

    before = s.portfolio()
    kind, updates, closed = s.write_goals(
        "reopen", [g], mutate, message=lambda gg, o, n: goal_message("reopen", gg, f"reopened {X}", n["state"], X, note=note))
    return {"ok": True, "coordinator": s.state.coordinator, "finding": info["finding"], "waived": info["waived"],
            "preview": impact(before, s.portfolio(), [g]), "pushed": pushed_summary(updates)}


PATH_SEG = re.compile(r"^([A-Za-z0-9_:]+)(?:\[([^\]]+)\])?$")


def apply_sets(doc: dict, sets: list) -> dict:
    for path, value in sets:
        segs = path.split(".")
        parsed = []
        for seg in segs:
            m = PATH_SEG.match(seg)
            if not m:
                raise Refused("usage", f"bad path segment {seg!r} in {path!r}")
            parsed.append((m.group(1), m.group(2)))
        node = doc
        for i, (name, sel) in enumerate(parsed):
            last = i == len(parsed) - 1
            if sel is None:
                if last:
                    if value is None and i == 1 and parsed[0][0] in ("skip", "records"):
                        node.pop(name, None)                   # null removes a skip or a record
                    else:
                        node[name] = value
                else:
                    if name not in node or not isinstance(node[name], (dict, list)):
                        node[name] = {}
                    node = node[name]
            else:
                arr = node.get(name)
                if not isinstance(arr, list):
                    raise Refused("usage", f"{name} is not an array in {path!r}")
                el = next((x for x in arr if isinstance(x, dict) and x.get("id") == sel), None)
                if el is None and sel.isdigit() and int(sel) < len(arr) and isinstance(arr[int(sel)], dict):
                    el = arr[int(sel)]                         # no element has that id: a position (G1028 waive lines)
                if el is None:
                    raise Refused("not_found", f"no element with id {sel!r} in {name}")
                if last:
                    raise Refused("usage", f"cannot replace an array element in {path!r}; set its fields")
                node = el
    return doc


def edit(s, gids: list, files=(), sets=(), bases=()) -> dict:
    s.open(goals=gids)
    base_of = {}
    for C in bases:
        data = s.git.cat(f"{C}:goal.json")
        if data is None:
            s.git.run("fetch", "-q", s.R, C, check=False)
            data = s.git.cat(f"{C}:goal.json")
        if data is None:
            raise Refused("not_found", f"--base {C} is not a goal commit")
        gid = json.loads(data.decode("utf-8")).get("id")
        if gid not in gids or gid in base_of:
            raise Refused("usage", f"--base {C} names G{gid}, which is not edited (or is given twice)")
        base_of[gid] = s.git.rev_parse(C)
    set_entries = [(k, v) for k, v in sets]
    doc_files = {}
    for f in files:
        content = load(f, "edit")
        if isinstance(content, dict) and set(content) == {"set"} and isinstance(content["set"], dict):
            set_entries += list(content["set"].items())
        elif isinstance(content, dict) and "id" in content:
            doc_files[content["id"]] = content
        else:
            raise Refused("validation", f"{f}: an edit file is a goal document or {{\"set\": {{…}}}}")
    if doc_files and set(doc_files) != set(gids):
        raise Refused("usage", "whole-document edit files must cover exactly the edited goals")
    for g in gids:
        if g not in s.snap.goals:
            raise Refused("not_found", f"G{g} does not exist")
    info = {}

    if base_of:
        s.require_writable(gids)

    def op(sess, docs):
        for g, C in base_of.items():
            if sess.snap.goals.get(g) != C:
                raise Refused("goal_changed", f"G{g} changed since {C[:12]}: run show and redo the edit")
        new = {}
        for g in gids:
            if g in sess.state.newer:
                raise Refused("engine_too_old", f"G{g} has a newer goal schema than this engine", hint="upgrade the plugin")
            old = docs.get(g) or sess.state.invalid_raw.get(g)
            if old is None and not doc_files:
                raise Refused("validation", f"G{g} is unreadable: replace it with a whole-document --file")
            d = copy.deepcopy(doc_files[g]) if doc_files else apply_sets(copy.deepcopy(old), set_entries)
            schemas.normalize_flow(d)                         # G1025 §2: schema 2 only with `flow`
            d = fill_close_fields(sess, old or {}, d)
            d = fill_current_records(sess, d)
            skip_refusal(sess, g, old or {}, d)
            new[g] = d
        return new

    before = s.portfolio()
    docs = copy.deepcopy(s.state.docs)
    new_docs = op(s, docs)
    after_docs = dict(docs)
    after_docs.update(new_docs)
    after = s.portfolio(docs=after_docs)
    prev = impact(before, after, gids)
    ctx = s.ctx()
    live = [live_lease_entry(ctx, g, n, L, sb)
            for g, n, L, sb in live_input_changes(before, after, s.now, impact_scope(before, after, gids))]
    extra = {"live_leases_on_changed_nodes": live, "carried_findings": carried_findings(after, impact_scope(before, after, gids))}
    if live:
        extra["warning"] = f"{len(live)} running phase(s) have inputs this edit changes; see live_leases_on_changed_nodes"
    stale = sum(1 for g, nodes in prev.items() for n, ch in nodes.items()
                if ch["before"] == "current" and ch["after"].startswith("ready (stale")
                and after.goals.get(int(g[1:])) and after.goals[int(g[1:])].graph.nodes[n]["kind"] == "agent")
    follow = follow_up(s, gids, new_docs)
    if set(base_of) != set(gids):
        out = {"ok": True, "coordinator": s.state.coordinator, "applied": False, "preview": prev,
               "stale_agent_phases": stale, **extra, "hint": "add --base <goal commit> for each goal to apply"}
        if follow:
            out["follow_up"] = follow
        return out
    s.require_writable(gids)
    from engine.session import dependent_release_errors
    for g, d in new_docs.items():
        errs, _ = schemas.validate_goal(d, s.state.docs.get(g), after_docs, s.state.workflow,
                                        lambda doc, g=g: s.terminals_current(g, doc, after_docs))
        errs = list(errs) + dependent_release_errors(g, d, after_docs) + s.line_errors(g, d, after_docs)
        if errs:
            raise Refused("too_large" if any("too_large" in e for e in errs) else "validation",
                          f"G{g}: " + "; ".join(errs[:5]), details={"errors": list(errs)})

    def message(gg, old, new):
        paths = changed_paths(old or {}, new)
        return goal_message("edit", gg, ", ".join(paths[:6]) or "no change", new["state"])

    kind, updates, closed = s.write_goals("edit", gids, op, retry=False, message=message)
    if extra["carried_findings"]:
        w = (f"{len(extra['carried_findings'])} open finding(s) stay live on their targets after this edit; "
             "see carried_findings")
        extra["warning"] = (extra["warning"] + "; " + w) if extra.get("warning") else w
    out = {"ok": True, "coordinator": s.state.coordinator, "applied": True,
           "goal_commits": {str(g): s.snap.goals[g] for g in gids}, "preview": prev, "stale_agent_phases": stale,
           **extra, "pushed": pushed_summary(updates)}
    if follow:
        out["follow_up"] = follow
    return out


def carried_findings(after, scope) -> list:
    """SPEC §3.16 (G1028): every finding live after the edit only because it is carried (its carrier is stale), with
    the `--set` lines that waive it."""
    out = []
    for g in sorted(scope):
        res = after.goals.get(g)
        if res is None:
            continue
        for t in res.graph.topo:
            for c, f in res.live.get(t, []):
                if c not in res.stale or c == t:
                    continue
                i = next(k for k, x in enumerate(res.doc["records"][c]["findings"]) if x is f)
                out.append({"goal": g, "id": f["id"], "from": c, "target": t, "text": clip(f["text"], 120),
                            "waive": f"--set 'records.{c}.findings[{i}].status=\"waived\"' "
                                     f"--set 'records.{c}.findings[{i}].note=\"<who waived it, and why>\"'"})
    return sorted(out, key=lambda x: (x["goal"], x["id"]))


def skip_refusal(s, g: int, old: dict, new: dict):
    """A new skip of a node is refused while its latest record has any open finding that is not a note (live, waiting
    for its filter, or waiting for re-review): waive the findings first, visibly (SPEC §4.18 as amended by G1000).
    Non-skippable nodes are refused by goal validation."""
    added = [n for n in (new.get("skip") or {}) if n not in (old.get("skip") or {})]
    res = s.portfolio().goals.get(g)
    if not added or res is None:
        return
    notes = {(c, f["id"]) for lst in res.notes.values() for c, f, _ in lst}
    for n in added:
        if n not in res.graph.nodes:
            continue
        r = (old.get("records") or {}).get(n) or {}
        blocking = [f for f in r.get("findings") or [] if f["status"] == "open" and (n, f["id"]) not in notes]
        if blocking:
            ids = [f["id"] for f in blocking]
            sets = " ".join(f"--set 'records.{n}.findings[{i}].status=\"waived\"' "
                            f"--set 'records.{n}.findings[{i}].note=\"<who waived it, and why>\"'" for i in ids)
            raise Refused("validation", f"G{g}: {n} has open findings that are not notes: " + ", ".join(ids)
                          + "; skipping it would drop them unseen",
                          hint=f"waive them first, visibly: zzzops edit {g} {sets} --base <C>; then add the skip",
                          details={"node": n, "findings": [{"id": f["id"], "text": f["text"][:200]} for f in blocking]})


def changed_paths(old: dict, new: dict, prefix="") -> list:
    out = []
    for k in sorted(set(old) | set(new)):
        a, b = old.get(k), new.get(k)
        if a == b:
            continue
        p = f"{prefix}{k}"
        if isinstance(a, dict) and isinstance(b, dict) and prefix.count(".") < 2:
            out += changed_paths(a, b, p + ".")
        else:
            out.append(p)
    return out


def fill_close_fields(s, old: dict, d: dict) -> dict:
    if d.get("state") == "closed" and old.get("state") != "closed":
        closed = dict(d.get("closed") or {})
        closed.setdefault("reason", "cancelled")
        closed.setdefault("note", "closed by edit")
        closed["by"] = s.git.identity()[0]
        closed["at"] = iso(s.now)
        d["closed"] = closed
    elif d.get("state") in ("open", "held"):
        d["closed"] = None
    return d


def fill_current_records(s, d: dict) -> dict:
    """Migration aid: records with input_fp "current" get the node's current fingerprint; {"commit"} checkpoints are
    completed."""
    records = d.get("records") or {}
    pending = [n for n, r in records.items() if isinstance(r, dict) and r.get("input_fp") == "current"]
    graph = s.state.graphs.get(d.get("graph"))
    if graph is None:
        return d
    ident = Identity(s.git)
    for n in graph.topo:
        r = records.get(n)
        if not isinstance(r, dict):
            continue
        for k in graph.checkpoint_outputs(n):
            cp = (r.get("output") or {}).get(k)
            if isinstance(cp, dict) and set(cp) == {"commit"}:
                vals, _ = resolve(graph, d, n, lambda p: recorded_out(d, p), s.portfolio().views)
                base = vals.get("base")
                if base is None:
                    raise Refused("validation", f"records.{n}.{k}: cannot complete the checkpoint (no base)")
                if not (isinstance(cp["commit"], str) and schemas.SHA.match(cp["commit"])):
                    raise Refused("validation", f"records.{n}.{k}.commit must be a full 40-hex sha")
                c = s.git.rev_parse(cp["commit"])
                if not c:
                    raise Refused("validation", f"records.{n}.{k}.commit {cp['commit']} does not exist")
                r["output"][k] = {"commit": c, "base": base, "tree": ident.code_tree(c), "change": ident.change(base, c)}
        if n in pending:
            from engine.frontier import portfolio as pf
            docs = dict(s.state.docs)
            tmp = copy.deepcopy(d)
            tmp["records"].pop(n, None)
            docs[d["id"]] = tmp
            p = pf(docs, s.state.graphs, {}, s.settings, s.now, s.state.invalid, s.state.newer, **s.pf_kwargs(docs))
            st = p.goals[d["id"]].st[n] if d["id"] in p.goals else None
            if not st or "fp" not in st or st.get("parts") is None and st["name"] != "needs_human":
                raise Refused("validation", f"records.{n}: its inputs do not resolve, so it cannot be marked current")
            parts = st.get("parts") or (st.get("ready") or {}).get("parts")
            r["input_fp"], r["fp_parts"] = st["fp"], parts
    return d


def follow_up(s, gids, new_docs) -> list:
    out = []
    for g in gids:
        d = new_docs[g]
        old = s.state.docs.get(g) or {}
        if d["state"] == "closed" and old.get("state") != "closed" and (d.get("closed") or {}).get("reason") != "done":
            graph = s.state.graphs.get(d["graph"])
            for n, r in sorted((d.get("records") or {}).items()):
                if graph and graph.nodes.get(n, {}).get("op") == "git.integrate" and r.get("status") == "done":
                    pr = (r.get("output") or {}).get("pr") or {}
                    if pr.get("number"):
                        out.append(f"gh pr close {pr['number']}")
            if (d.get("links") or {}).get("issue"):
                out.append(f"gh issue close {d['links']['issue']}")
    return out


def impact_scope(before, after, gids) -> set:
    """The edited goals and their transitive dependents (before or after the edit)."""
    scope = set(gids)
    changed = True
    while changed:
        changed = False
        for g, res in list(after.goals.items()) + list(before.goals.items()):
            if g not in scope and scope & set(res.doc.get("depends_on") or []):
                scope.add(g)
                changed = True
    return scope


def impact(before, after, gids) -> dict:
    """SPEC §3.16 impact preview over the edited goals and their transitive dependents."""
    out = {}
    for g in sorted(impact_scope(before, after, gids)):
        b, a = before.goals.get(g), after.goals.get(g)
        nodes = {}
        topo = (a or b).graph.topo if (a or b) else []
        for n in topo:
            sb = state_string(b.st[n]) if b and n in b.st else ("closed" if b is None else "absent")
            sa = state_string(a.st[n]) if a and n in a.st else ("closed" if a is None else "absent")
            if sb != sa:
                nodes[n] = {"before": sb, "after": sa}
        if nodes:
            out[f"G{g}"] = nodes
    return out
