"""The op interface and `start` on an op node: claim, run, finish like submit (SPEC §5.1)."""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from typing import Callable

from engine import records as rec
from engine.canon import iso
from engine.errors import Refused
from engine.frontier import recorded_out, resolve
from engine.identity import Identity
from engine.leases import lease_ref
from engine.ops import OPS
from engine.store import goal_message
from engine import worktree as wt


@dataclass
class Done:
    output: dict
    ok: bool
    findings: list = field(default_factory=list)       # [{"key", "input", "text"}]
    ref_updates: list = field(default_factory=list)    # [(ref, expected, new)]
    replayed: dict | None = None                       # {"old", "onto", "map", ...} (§4.21)
    after_push: Callable | None = None
    summary: str = ""


@dataclass
class Blocked:
    blocked: dict


@dataclass
class OpContext:
    goal: int
    doc: dict
    node: str
    node_def: dict
    inputs: dict
    producers: dict
    dep_kinds: dict
    record: dict | None
    corrections: list
    answer: dict | None
    settings: dict
    snap: object
    git: object
    gh: object
    worktree: str | None
    now: int
    renew: Callable
    session: object = None
    graph: object = None

    def wait(self, reason: str, delay: int, question: str | None = None) -> Blocked:
        r = self.record
        st = ((r.get("blocked") or {}).get("op_state") or {}) if r and r["status"] == "blocked" \
            and r["blocked"]["waiting_for"] == "time" else {}
        if self.answer:
            st = {}
        since = st.get("pending_since", self.now)
        polls = st.get("polls", 0)
        minutes = (self.now - since) // 60
        if self.now - since >= self.settings["verification"]["ci_timeout_minutes"] * 60:
            return Blocked({"category": "external", "waiting_for": "human", "reason": f"{reason} for {minutes} minutes",
                            "question": question or (f"G{self.goal} {self.node}: {reason}, for {minutes} minutes. "
                                                     "Fix it, or answer 'wait' to keep waiting."),
                            "op_state": {"pending_since": since, "polls": polls}})
        return Blocked({"category": "external", "waiting_for": "time", "reason": reason,
                        "retry_after": iso(self.now + min(delay * 2 ** polls, 1800)),
                        "op_state": {"pending_since": since, "polls": polls + 1}})


def cap(text: str, limit: int = 1024) -> str:
    b = (text or "").encode("utf-8")
    return text if len(b) <= limit else b[:limit - 3].decode("utf-8", "ignore") + "…"


class Renewer:
    def __init__(self, s, g, X, attempt, timeout):
        self.s, self.g, self.X, self.attempt = s, g, X, attempt
        self.interval = max(60.0, timeout * 60 / 4)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True)

    def loop(self):
        while not self.stop_event.wait(self.interval):
            try:
                self.renew_once()
            except Exception:
                pass

    def renew_once(self):
        from engine.session import Session
        from engine import verbs
        sub = Session(cwd=self.s.git.primary, remote=self.s.R, integration=self.s.I)
        verbs.renew(sub, self.g, self.X, self.attempt)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop_event.set()
        self.thread.join(timeout=5)


def make_context(s, res, X, lease) -> OpContext:
    graph, doc = res.graph, res.doc
    vals, _ = resolve(graph, doc, X, lambda p: res.cur[p] if p in res.cur else recorded_out(doc, p),
                      s.portfolio().views)
    producers = {k: sel.producer for k, sel in graph.selectors[X].items()}
    views = s.portfolio().views
    dep_kinds = {d: (views.get(d) or {}).get("kind", "invalid") for d in doc.get("depends_on") or []}
    r = (doc.get("records") or {}).get(X)
    corr = sorted((f for _, f in res.live.get(X, [])), key=lambda f: f["id"])
    gh = None
    spec = OPS[graph.nodes[X]["op"]]
    if spec.gh or graph.nodes[X]["op"] == "git.base":
        from engine.gh import Gh
        gh = Gh(s)
    return OpContext(goal=res.goal, doc=doc, node=X, node_def=graph.nodes[X], inputs=vals, producers=producers,
                     dep_kinds=dep_kinds, record=r, corrections=corr,
                     answer=(r or {}).get("answer") if r and r["status"] == "blocked" else None,
                     settings=s.settings, snap=s.snap, git=s.git, gh=gh, worktree=lease.get("workspace"), now=s.now,
                     renew=lambda: None, session=s, graph=graph)


def start_op(s, res, X, label, state, reclaim, force) -> dict:
    from engine import verbs
    g = res.goal
    nd = res.graph.nodes[X]
    spec = OPS[nd["op"]]
    if spec.gh:
        from engine.gh import require_gh
        require_gh(s)
    if nd.get("workspace") and not spec.self_sync:
        p = wt.worktree_path(s.git, g)
        import os
        if os.path.isdir(p) and not wt.is_clean(s.git, p) and not force:
            raise Refused("dirty_worktree", f"the goal worktree {p} has uncommitted changes",
                          hint="commit or stash them, then retry")
    lease, workspace = verbs.claim(s, res, X, label, state, reclaim, force)
    if nd.get("workspace") and not spec.self_sync:
        wt.sync(s.git, Identity(s.git), s.snap, g, "clean", X, lease["attempt"])
    res = s.portfolio().goals[g]
    ctx = make_context(s, res, X, lease)
    import time
    deadline = None
    while True:
        with Renewer(s, g, X, lease["attempt"], lease["timeout"]) as renewer:
            ctx.renew = renewer.renew_once
            try:
                result = spec.run(ctx)
            except Refused:
                raise
            except Exception as exc:
                raise Refused("op_error", f"{nd['op']} failed: {exc}", hint="the lease expires; start --reclaim retries it")
        # the renewer is stopped: a renewal can no longer race the finish
        if nd["op"] != "git.base" or not isinstance(result, Done):
            return finish(s, g, X, label, lease, result, spec, ctx)
        W0 = ctx.snap.work.get(g)
        try:
            return finish(s, g, X, label, lease, result, spec, ctx, retry=False)
        except Refused as exc:
            if exc.code != "goal_changed":
                raise
        # §5.1: the finish was rejected; re-run in-process while the lease is ours and W moved only by reviews
        deadline = deadline or time.monotonic() + 30
        if time.monotonic() > deadline:
            raise Refused("contention", "the goal kept changing during the restack; run base again")
        L = verbs.valid_lease(s, g, X)
        W1 = s.snap.work.get(g)
        ident = Identity(s.git)
        if L is None or L.attempt != lease["attempt"] or L.timeout == 0:
            raise Refused("superseded", f"G{g} {X} attempt {lease['attempt']} lost its lease during the restack")
        if W1 != W0 and not (W0 and W1 and s.git.is_ancestor(W0, W1)
                             and all(ident.is_review(c) for c in s.git.out("rev-list", f"{W0}..{W1}").split())):
            raise Refused("contention", "the work branch moved during the restack; run base again")
        res = s.portfolio().goals[g]
        ctx = make_context(s, res, X, lease)


def finish(s, g, X, label, lease, result, spec, ctx, retry=True) -> dict:
    from engine import verbs
    from engine.carry import carry_forward
    N = lease["attempt"]
    info = {}
    retries = {"n": 0}

    def mutate(sess, docs):
        res = sess.portfolio().goals.get(g)
        if res is None:
            raise Refused("goal_closed", f"G{g} closed meanwhile")
        L = verbs.valid_lease(sess, g, X)
        if L is None or L.attempt != N:
            raise Refused("superseded", f"G{g} {X} attempt {N} lost its lease before finishing")
        doc = copy.deepcopy(docs[g])
        graph = res.graph
        r0 = (doc.get("records") or {}).get(X)
        if isinstance(result, Blocked):
            b = dict(result.blocked)
            b["repeats"] = rec.blocked_repeats(r0, b["waiting_for"], b["reason"])
            for k in ("reason", "question", "instructions"):
                if isinstance(b.get(k), str):
                    b[k] = cap(b[k])
            findings = copy.deepcopy((r0 or {}).get("findings") or []) if r0 else []
            record = rec.record("blocked", False, N, label, L.reason, r0, L.input_fp, L.fp_parts, None, findings,
                                sess.now, blocked=b)
            info["outcome"] = "blocked"
        else:
            out = dict(result.output)
            for k in graph.output_types[X]:
                out.setdefault(k, None)
            corr = sorted((f for _, f in res.live.get(X, [])), key=lambda f: f["id"])
            auto = rec.auto_responses(graph, X, corr)
            if auto:
                out["responses"] = auto
            fence = rec.make_fence(graph, doc, verbs.x_fp(res, X), L.input_fp, verbs.claimed_at(sess, L.tip))
            producers = {k: sel.producer for k, sel in graph.selectors[X].items()}
            findings = rec.op_findings(graph, doc, X, r0, list(result.findings), producers, L.input_fp, fence)
            ok = bool(result.ok) and not findings
            if not ok and not findings:
                raise Refused("engine_bug", f"{X} failed without a finding")
            record = rec.record("done", ok, N, label, L.reason, r0, L.input_fp, L.fp_parts, out, findings, sess.now)
            info["outcome"] = "done"
        doc["records"][X] = record
        info["record"] = record
        if isinstance(result, Done) and result.replayed:
            info["carried"] = carry_forward(sess, graph, doc, X, record, result.replayed, res.live)
        return {g: doc}

    def extra(sess, new):
        ups = [(lease_ref(g, X), sess.snap.leases.get((g, X)), None)]
        if isinstance(result, Done):
            ups += list(result.ref_updates)
        return ups

    def message(gg, old, new):
        r = new["records"][X]
        text = verbs.outcome_of(s, gg, X, r, old, new)
        if info.get("carried"):
            text += "; carried: " + ", ".join(info["carried"])
        return goal_message("start", gg, text, new["state"], X, N, label)

    kind, updates, closed = s.write_goals("start", [g], mutate, extra, message=message, retry=retry)
    warnings = []
    if isinstance(result, Done) and result.after_push:
        try:
            for w in result.after_push() or []:
                warnings.append(w)
        except Exception as exc:
            warnings.append({"kind": "after_push", "message": f"{exc}"})
    r = info["record"]
    ran = {"goal": g, "node": X, "op": ctx.node_def["op"], "attempt": N, "outcome": info["outcome"],
           "findings": r.get("findings") if info["outcome"] == "done" else [],
           "summary": result.summary if isinstance(result, Done) else r["blocked"]["reason"]}
    if info["outcome"] == "done":
        ran["ok"], ran["output"] = r["ok"], r["output"]
    else:
        ran["blocked"] = r["blocked"]
    extra_out = {"ran": ran}
    if info.get("carried"):
        extra_out["carried"] = info["carried"]
    if warnings:
        extra_out["warnings"] = warnings
    return verbs.finish_output(s, g, updates, closed, extra_out)
