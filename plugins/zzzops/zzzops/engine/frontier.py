"""The frontier (SPEC §4.9), the portfolio (§4.10) and ordering (§4.11).

Pure: everything is passed in; no I/O, no clock, no environment. Iteration is in topological or sorted order, so
identical arguments give identical results."""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.canon import parse_iso
from engine.fingerprint import fp_parts as _fp_parts, input_fp, out_fp, stale_keys
from engine.schemas import Graph, is_material

ABSENT = object()


class Skipped:
    pass


SKIPPED = Skipped()


@dataclass(frozen=True)
class Missing:
    reason: str


@dataclass
class Lease:
    """A parsed, valid lease (SPEC §3.8). Times are integer seconds."""
    goal: int
    node: str
    attempt: int
    holder: str
    reason: str
    timeout: int                 # minutes; 0 = abandoned
    last_active: int
    work: str | None = None
    input_fp: str | None = None
    fp_parts: dict | None = None
    prompt: str | None = None
    tip: str | None = None
    claimed_at: int | None = None

    def live(self, now: int) -> bool:
        return self.timeout > 0 and now - self.last_active < self.timeout * 60

    @property
    def expires_at(self) -> int:
        return self.last_active + self.timeout * 60


def miss(node, reason, **extra) -> dict:
    m = {"node": node, "reason": reason}
    m.update(extra)
    return m


def get_path(obj, path):
    for key in path:
        if not isinstance(obj, dict) or key not in obj:
            return ABSENT
        obj = obj[key]
    return obj


# --------------------------------------------------------------------------------------------- resolve


def resolve(graph: Graph, doc: dict, n: str, out_of, dep_view: dict):
    vals, missing = {}, []
    nd = graph.nodes[n]
    for name in sorted((nd.get("inputs") or {})):
        s = nd["inputs"][name]
        sel = graph.selectors[n][name]
        if sel.kind == "goal":
            v = get_path(doc, list(sel.path))
            if v is ABSENT:
                missing.append(miss("goal." + ".".join(sel.path), "output_absent"))
            else:
                vals[name] = v
        elif sel.kind == "node":
            o = out_of(sel.node)
            if o is SKIPPED:
                if s.get("optional"):
                    vals[name] = None
                else:
                    missing.append(miss(sel.node, "skipped"))
            elif isinstance(o, Missing):
                missing.append(miss(sel.node, o.reason))
            else:
                v = get_path(o, [sel.output, *sel.path])
                if v is ABSENT:
                    missing.append(miss(sel.node, "output_absent"))
                else:
                    vals[name] = v
        else:
            m, bad = {}, []
            for d in sorted(doc.get("depends_on") or []):
                dv = dep_view.get(d) or INVALID_VIEW

                def dmiss(wait, d=d, dv=dv):
                    return {"node": sel.node, "reason": "dependency", "dep": d, "state": dv["state"], "wait": wait}

                if sel.node in dv["cur"]:
                    v = get_path(dv["cur"][sel.node], [sel.output, *sel.path])
                    if v is ABSENT:
                        bad.append(dmiss(False))
                    else:
                        m[str(d)] = v
                elif dv["kind"] == "done" or (dv["kind"] in ("open", "held") and sel.node in dv["skip"]):
                    if s.get("optional"):
                        m[str(d)] = None
                    else:
                        bad.append(dmiss(False))
                elif dv["kind"] in ("open", "held") and sel.node in dv["nodes"]:
                    if s.get("pending"):
                        m[str(d)] = None
                    else:
                        bad.append(dmiss(not dv["stuck"]))
                elif dv["kind"] == "newer":
                    bad.append(dmiss(True))
                else:
                    bad.append(dmiss(False))
            if bad:
                missing += bad
            else:
                vals[name] = m
    return vals, missing


def recorded_out(doc: dict, p: str):
    if p in (doc.get("skip") or {}):
        return SKIPPED
    r = (doc.get("records") or {}).get(p)
    if r and r["status"] == "done":
        return r["output"]
    return Missing("no_record")


# --------------------------------------------------------------------------------------------- frontier


def frontier(graph: Graph, doc: dict, dep_view: dict, leases: dict, settings: dict, now: int, lctx: dict | None = None):
    """States of one goal's nodes. `leases`: node -> Lease (valid leases only). Returns (st, cur, live, notes, stale):
    `notes` maps a target to the (lens, finding, reason) of its open lens findings that a fresh filter judged `note`;
    `stale` is the set of carriers whose done record is not fresh (their findings may be carried, G1028).
    `lctx` (G1025, branching only): {"target", "integration", "effective", "hotfix_waiting", "upstream",
    "members_open", "line_behind"}; None keeps every rule as it was."""
    N, topo = graph.nodes, graph.topo
    lx = lctx or {}
    tpart = lx.get("target") if lx.get("target") and lx.get("target") != lx.get("integration") else None
    effective = lx.get("effective", settings["releases"]["current"])
    hotfix_member = bool((doc.get("flow") or {}).get("hotfix"))

    def fp_parts(graph, n, vals, subj_rec, settings, records=None, skip=None):
        p = _fp_parts(graph, n, vals, subj_rec, settings, records, skip)
        if tpart and N[n].get("op") == "git.base":
            p["target"] = tpart
        return p

    def line_wait(n, node):
        """A frontier-computed wait (G1025 design §6, §7, §8): never recorded, so it ends on its own."""
        if not lctx:
            return None
        if node.get("op") == "git.base":
            if lx.get("hotfix_waiting"):
                x = lx["hotfix_waiting"]
                return {"name": "waiting", "until": f"hotfix {x} started", "reason": "hotfix_start"}
            mi = (lx.get("upstream") or {}).get("merged_in_target") or {}
            late = sorted(int(d) for d, ok in mi.items() if ok is False)
            if late:
                return {"name": "waiting", "until": f"G{late[0]}'s release sync", "reason": "release_sync"}
        if node.get("line_complete") and lx.get("members_open"):
            ids = ", ".join(f"G{x}" for x in lx["members_open"])
            return {"name": "waiting", "until": f"{ids} of the line close", "reason": "line_members_open"}
        return None

    comp = {}
    skip = doc.get("skip") or {}
    records = doc.get("records") or {}
    R = {n: records[n] for n in topo if n in records and n not in skip}

    def recorded(p):
        return recorded_out(doc, p)

    # ---- pass 1: liveness, from recorded values only
    fresh = {}
    for c in topo:
        if c not in R or R[c]["status"] != "done":
            continue
        vals, missing = resolve(graph, doc, c, recorded, dep_view)
        subj = graph.subject(c)
        fresh[c] = (not missing and not (subj and (subj not in R or R[subj]["status"] != "done"))
                    and input_fp(fp_parts(graph, c, vals, R.get(subj), settings, R, skip)) == R[c]["input_fp"])
    live = {n: [] for n in topo}
    notes = {}
    stale = {c for c in fresh if not fresh[c]}
    for c in topo:
        if c not in fresh:
            continue
        carry = not fresh[c]
        verdicts = carried_verdicts(graph, R, c) if carry else filter_verdicts(graph, R, fresh, c)
        for f in R[c].get("findings") or []:
            t = f["target"]
            if carry and verdicts is not None and t != c:
                # a stale lens: a material finding is carried; a non-material one only with the verdict `keep`
                if f["status"] != "open":
                    continue
                if not is_material(f):
                    v = verdicts.get(f["id"])
                    if is_note(f, verdicts) and t in N:
                        notes.setdefault(t, []).append((c, f, v.get("reason")))
                    if not (isinstance(v, dict) and v.get("verdict") == "keep"):
                        continue
            elif verdicts is not None and t != c:
                # a filtered lens's finding waits for its fresh filter (the join); a non-material one judged `note` is
                # a note and never live; without a verdict it is kept
                if verdicts is False:
                    continue
                if is_note(f, verdicts):
                    if t in N:
                        notes.setdefault(t, []).append((c, f, verdicts[f["id"]].get("reason")))
                    continue
            if carry and t != c and N[c]["kind"] == "op":
                continue    # an op re-observes: its findings are rebuilt when it re-runs, never carried (SPEC §4.9, G1028)
            if (f["status"] == "open" and f["target_fp"] is not None and t in N and t in R
                    and R[t]["status"] == "done" and f["target_fp"] == out_fp(graph, t, R[t])
                    and not (N[t]["kind"] == "op" and t != c and R[t]["attempt"] > (f.get("target_attempt") or 0))):
                live[t].append((c, f))

    # ---- pass 2: states
    cur, st = {}, {}

    def current_out(p):
        if p in skip:
            return SKIPPED
        return cur[p] if p in cur else Missing("not_current")

    for n in topo:
        node = N[n]
        if n in skip:
            st[n] = {"name": "skipped", "reason": skip[n]}
            continue
        r = R.get(n)
        L = leases.get(n)
        if L and r and r["attempt"] >= L.attempt:
            L = None
        vals, missing = resolve(graph, doc, n, current_out, dep_view)
        subj = graph.subject(n)
        if subj and subj not in cur:
            missing.append(miss(subj, "subject_not_current"))
        if L and L.live(now):
            rv, rmiss = resolve(graph, doc, n, recorded, dep_view)
            rsub = bool(subj) and (subj not in R or R[subj]["status"] != "done")
            rparts = None if rmiss or rsub else fp_parts(graph, n, rv, R.get(subj), settings, R, skip)
            f = input_fp(rparts) if rparts else None
            st[n] = {"name": "running", "lease": L, "fp": f, "parts": rparts}
            continue
        if (missing or lx.get("hotfix_waiting")) and lctx and node.get("op") == "git.base":
            # a merged dependency not in the target yet, or no hotfix line: a hotfix member with no line waits even
            # when its base record is current, so nothing below it runs against the integration branch (§4, §7)
            w = line_wait(n, node)
            if w:
                st[n] = w
                continue
        if missing:
            st[n] = {"name": "blocked", "missing": missing}
            continue
        if node.get("release_gate") and not hotfix_member and doc["release"] > effective:
            st[n] = {"name": "waiting", "until": f"release {doc['release']}", "reason": "release"}
            continue
        parts = fp_parts(graph, n, vals, R.get(subj), settings, R, skip)
        f = input_fp(parts)
        comp[n] = (f, parts)
        corr = sorted((x for _, x in live[n]), key=lambda x: x["id"])
        if L:
            if L.attempt >= (r["attempt"] if r else 0) + 3:
                st[n] = {"name": "needs_human", "kind": "crash_loop", "cap": "lease", "lease": L, "fp": f, "parts": parts,
                         "corrections": corr}
                continue
            st[n] = {"name": "reclaimable", "lease": L, "fp": f, "parts": parts, "corrections": corr}
            continue
        if r is None:
            s = {"name": "ready", "reason": "new"}
        elif r["input_fp"] != f:
            s = {"name": "ready", "reason": "stale", "stale_because": stale_keys(r.get("fp_parts"), parts)}
        elif r["status"] == "blocked":
            b = r["blocked"]
            wf = b["waiting_for"]
            if wf == "time" and now < parse_iso(b["retry_after"]):
                st[n] = {"name": "waiting", "until": b["retry_after"], "reason": b["reason"], "retry_after": b["retry_after"]}
                continue
            if wf == "dependency":
                st[n] = {"name": "waiting", "until": "the dependencies combine cleanly", "reason": b["reason"]}
                continue
            if wf == "human":
                st[n] = {"name": "needs_human", "kind": "blocked", "blocked": b, "fp": r["input_fp"], "record": r}
                continue
            if wf == "agent" and b.get("repeats", 1) >= 3:
                st[n] = {"name": "needs_human", "kind": "crash_loop", "cap": "repeat", "blocked": b, "fp": f, "parts": parts,
                         "corrections": corr}
                continue
            s = {"name": "ready", "reason": "retry", "instructions": b.get("instructions"), "answer": r.get("answer")}
        elif corr:
            s = {"name": "ready", "reason": "reopened"}
        elif not r["ok"]:
            if node["kind"] == "op" and any(x["status"] == "open" and x.get("repeats", 1) >= 3 for x in r.get("findings") or []):
                st[n] = {"name": "needs_human", "kind": "crash_loop", "cap": "op_finding", "record": r, "fp": f, "parts": parts,
                         "corrections": corr}
                continue
            own = sorted({x["target"] for x in r.get("findings") or [] if any(cc == n and y is x for cc, y in live.get(x["target"], []))})
            if own:
                st[n] = {"name": "blocked", "missing": [miss(t, "findings_open") for t in own]}
                continue
            s = {"name": "ready", "reason": "not_ok"}
        elif node.get("schedule") == "upstream" and lx.get("line_behind"):
            s = {"name": "ready", "reason": "upstream", "stale_because": ["upstream"]}
        else:
            st[n] = {"name": "current"}
            cur[n] = r["output"]
            continue
        s["corrections"], s["fp"], s["parts"] = corr, f, parts
        w = line_wait(n, node)
        if w:
            st[n] = w
            continue
        esc = [(c, x) for c, x in live[n] if escalates(N, n, c, x)]
        if esc:
            st[n] = {"name": "needs_human", "kind": "dispute", "escalated": esc, "ready": s}
            continue
        if node["kind"] == "human":
            st[n] = {"name": "needs_human", "kind": "approve", "ready": s, "fp": f, "parts": parts}
            continue
        st[n] = s
    if lctx:
        restack(graph, doc, st, comp, lx)
    return st, cur, live, notes, stale


def carried_verdicts(graph: Graph, R: dict, lens: str):
    """For a stale lens: None when unfiltered, else the verdicts of its filter's latest done record, fresh or not
    ({} when it has none)."""
    F = graph.filter_of(lens)
    if not F:
        return None
    fr = R.get(F)
    v = ((fr or {}).get("output") or {}).get("verdicts") if fr and fr["status"] == "done" else None
    return v if isinstance(v, dict) else {}


def restack(graph: Graph, doc: dict, st: dict, comp: dict, lx: dict):
    """Pass 3 (G1025 design §5.3): a scheduled restack before an agent works on the goal's code. It rewrites only
    states pass 2 computed: `base` becomes ready (upstream) and every ready workspace node below it is blocked."""
    N = graph.nodes
    up = lx.get("upstream") or {}
    base = next((n for n in graph.topo if N[n].get("op") == "git.base"), None)
    if not base or not up.get("behind") or st.get(base, {}).get("name") != "current" or base not in comp:
        return
    rb = (doc.get("records") or {}).get(base) or {}
    out = rb.get("output") or {}
    if out.get("stack"):
        return                                                    # stacked: the base moves with its dependencies
    below = [n for n in graph.topo if n != base and N[n].get("workspace") and base in graph.ancestors(n)]
    if any(st[n]["name"] == "running" for n in below):
        return
    done = out.get("scheduled_for")
    records = doc.get("records") or {}
    cands = [{"node": n, "after_attempt": (records.get(n) or {}).get("attempt", 0)} for n in below
             if N[n]["kind"] == "agent" and st[n]["name"] == "ready"]
    due = [c for c in cands if c != done]
    if not due:
        return
    f, parts = comp[base]
    st[base] = {"name": "ready", "reason": "upstream", "stale_because": ["upstream"], "corrections": [], "fp": f,
                "parts": parts, "scheduled_for": due[0]}
    for n in below:
        if st[n]["name"] in ("ready", "reclaimable"):
            st[n] = {"name": "blocked", "missing": [miss(base, "restack")]}


def filter_verdicts(graph: Graph, R: dict, fresh: dict, lens: str):
    """None for an unfiltered node; False while the lens's filter has no fresh done record; else its verdicts."""
    F = graph.filter_of(lens)
    if not F:
        return None
    fr = R.get(F)
    if not fr or not fresh.get(F):
        return False
    v = (fr.get("output") or {}).get("verdicts")
    return v if isinstance(v, dict) else {}


def is_note(f: dict, verdicts) -> bool:
    """An open, non-material lens finding with the verdict `note` (SPEC §4.9 as amended by G1000)."""
    v = verdicts.get(f["id"]) if isinstance(verdicts, dict) else None
    return (f["status"] == "open" and not is_material(f) and isinstance(v, dict)
            and v.get("verdict") == "note")


def escalates(N: dict, target: str, carrier: str, f: dict) -> bool:
    return (f["rounds"] >= 2 and not f["upheld"] and N[target]["kind"] == "agent" and N[carrier]["kind"] != "human")


# --------------------------------------------------------------------------------------------- portfolio

INVALID_VIEW = {"kind": "invalid", "state": "invalid", "cur": {}, "skip": {}, "nodes": {}, "stuck": False}
NEWER_VIEW = {"kind": "newer", "state": "newer", "cur": {}, "skip": {}, "nodes": {}, "stuck": False}


@dataclass
class GoalResult:
    goal: int
    doc: dict
    graph: Graph
    st: dict
    cur: dict
    live: dict
    notes: dict = field(default_factory=dict)        # target -> [(lens, finding, reason)] (filter-judged notes)
    stale: set = field(default_factory=set)          # carriers with a done record that is not fresh (G1028)
    stuck: dict | None = None
    budget: dict = field(default_factory=dict)       # {"used", "limit", "over", "per_node"}
    close: bool = False                              # every terminal current but the goal is open
    busy: str | None = None                          # workspace node with a live lease
    target: dict | None = None                       # G1025: {"branch", "kind"} with branching on


@dataclass
class Portfolio:
    goals: dict                                      # id -> GoalResult (open and held goals)
    views: dict                                      # id -> dep view
    invalid: dict                                    # id -> [errors]
    newer: set
    mass_expiry: bool = False
    expired: int = 0
    live_agents: int = 0
    branching: bool = False                          # G1025: everything below is empty without settings.branching
    ledger: dict = field(default_factory=dict)       # id -> trailer entry, overridden by the documents read
    lines: list = field(default_factory=list)        # [lines.Line]
    effective: int | None = None
    cut: dict | None = None                          # {"release", "goals"} when a release_cut item is due
    release_waiting: list = field(default_factory=list)
    hotfix_starts: list = field(default_factory=list)
    duplicates: list = field(default_factory=list)   # [(branch, [goal ids])]


def closed_view(doc: dict, graph: Graph | None) -> dict:
    nodes = graph.nodes if graph else {}
    if doc["closed"]["reason"] == "done":
        cur = {n: r["output"] for n, r in sorted((doc.get("records") or {}).items()) if r["status"] == "done" and r["ok"]}
        return {"kind": "done", "state": "merged", "cur": cur, "skip": doc.get("skip") or {}, "nodes": nodes, "stuck": False}
    return {"kind": "closed", "state": "cancelled", "cur": {}, "skip": doc.get("skip") or {}, "nodes": nodes, "stuck": False}


def goal_order(docs: dict) -> tuple:
    """(order, cyclic): topological order over depends_on, ties by id; every member of a dependency cycle (a
    strongly connected component of two or more goals, or a self-dependency) is excluded."""
    index, low, stack, on, comps = {}, {}, [], set(), []
    counter = [0]

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in sorted(d for d in docs[v].get("depends_on") or [] if d in docs):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            comps.append(comp)

    for g in sorted(docs):
        if g not in index:
            strong(g)
    cyclic = set()
    for comp in comps:
        if len(comp) > 1 or comp[0] in (docs[comp[0]].get("depends_on") or []):
            cyclic.update(comp)
    order, done = [], set()

    def visit(g):
        if g in done or g in cyclic:
            return
        done.add(g)
        for d in sorted(docs[g].get("depends_on") or []):
            if d in docs:
                visit(d)
        order.append(g)

    for g in sorted(docs):
        visit(g)
    return order, cyclic


def portfolio(docs: dict, graphs: dict, leases: dict, settings: dict, now: int, invalid: dict | None = None,
              newer: set | None = None, ledger: dict | None = None, upstream: dict | None = None) -> Portfolio:
    """docs: id -> valid document (any state); graphs: name -> Graph; leases: (goal, node) -> Lease (parsed);
    invalid: id -> errors; newer: ids whose schema is newer than this engine. G1025, with settings.branching only:
    `ledger` (id -> trailer entry, §3.1) and `upstream` (id -> {"target", "tip", "behind", "merged_in_target"})."""
    from engine import lines as ln
    b = ln.branching(settings)
    L = ln.merged_ledger(ledger, docs) if b else {}
    lns = ln.lines_of(L, settings) if b else []
    effective = ln.effective_release(settings, lns) if b else None
    upstream = upstream or {}
    invalid = dict(invalid or {})
    newer = set(newer or ())
    order, cyclic = goal_order(docs)
    for g in sorted(cyclic):
        invalid[g] = ["dependency cycle: " + ", ".join(f"G{c}" for c in sorted(cyclic))]
    views = {g: INVALID_VIEW for g in invalid}
    views.update({g: NEWER_VIEW for g in newer})
    results = {}
    for g in order:
        d = docs[g]
        graph = graphs.get(d["graph"])
        if graph is None:
            invalid[g] = [f"unknown graph {d['graph']!r}"]
            views[g] = INVALID_VIEW
            continue
        if d["state"] == "closed":
            views[g] = closed_view(d, graph)
            continue
        goal_leases = valid_leases(g, d, graph, leases)
        dep_view = {x: views.get(x, INVALID_VIEW) for x in d.get("depends_on") or []}
        lctx, target = None, None
        if b:
            target = ln.target_of(d, settings, lns)
            lctx = {"target": target["branch"], "integration": settings["integration_branch"], "effective": effective,
                    "hotfix_waiting": target.get("name") if target["kind"] == "hotfix" and not target["branch"] else None,
                    "upstream": upstream.get(g) or {}}
            flow = d.get("flow") or {}
            if flow.get("line"):
                me = next((x for x in lns if x.goal == g), None)
                lctx["members_open"] = ln.open_members(L, me) if me else []
                lctx["line_behind"] = bool((upstream.get(g) or {}).get("behind"))
        st, cur, live, notes, stale = frontier(graph, d, dep_view, goal_leases, settings, now, lctx)
        res = GoalResult(g, d, graph, st, cur, live, notes, stale=stale, target=target)
        finish_goal(res, goal_leases, now)
        results[g] = res
        stuck = res.stuck is not None
        views[g] = {"kind": d["state"], "state": "stuck" if stuck else d["state"], "cur": cur,
                    "skip": d.get("skip") or {}, "nodes": graph.nodes, "stuck": stuck}
    p = Portfolio(results, views, invalid, newer)
    if b:
        p.branching, p.ledger, p.lines, p.effective = True, L, lns, effective
        if RELEASE_GRAPH_NAME in graphs:
            p.cut, p.release_waiting = ln.cut_state(L, lns, settings, effective)
            p.hotfix_starts = ln.hotfix_starts(L, lns)
        p.duplicates = ln.duplicates(lns)
    lease_guards(p, docs, leases, now)
    return p


RELEASE_GRAPH_NAME = "release"


def valid_leases(g: int, doc: dict, graph: Graph, leases: dict) -> dict:
    """node -> Lease for the goal's valid leases (SPEC §1.1): node in the graph, attempt above the record's."""
    out = {}
    if doc["state"] == "closed":
        return out
    for (lg, node), L in sorted(leases.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        if lg != g or node not in graph.nodes:
            continue
        r = (doc.get("records") or {}).get(node)
        if r and r["attempt"] >= L.attempt:
            continue
        out[node] = L
    return out


def orphan_leases(docs: dict, graphs: dict, leases: dict) -> list:
    """(goal, node) keys of parsed leases that are not valid (SPEC §4.12)."""
    out = []
    for (g, node), L in sorted(leases.items()):
        d = docs.get(g)
        graph = graphs.get(d["graph"]) if d else None
        if d is None or graph is None or d["state"] == "closed" or node not in graph.nodes:
            out.append((g, node))
            continue
        r = (d.get("records") or {}).get(node)
        if r and r["attempt"] >= L.attempt:
            out.append((g, node))
    return out


def lease_guards(p: Portfolio, docs: dict, leases: dict, now: int):
    valid = []
    for res in p.goals.values():
        for node, L in valid_leases(res.goal, res.doc, res.graph, leases).items():
            valid.append((res, node, L))
    nonabandoned = [(res, n, L) for res, n, L in valid if L.timeout > 0]
    expired = [x for x in nonabandoned if not x[2].live(now)]
    p.expired = len(expired)
    p.mass_expiry = len(expired) >= 3 and 2 * len(expired) > len(nonabandoned)
    p.live_agents = sum(1 for res, n, L in valid if L.live(now) and res.graph.nodes[n]["kind"] == "agent")


def finish_goal(res: GoalResult, goal_leases: dict, now: int):
    st, graph, doc = res.st, res.graph, res.doc
    topo = graph.topo
    progress = any(st[n]["name"] in ("ready", "running", "reclaimable", "waiting", "needs_human") for n in topo)
    done = all(st[t]["name"] == "current" for t in graph.terminal)
    named_wait = any(m["reason"] == "dependency" and m.get("wait")
                     for n in topo if st[n]["name"] == "blocked" for m in st[n]["missing"])
    if doc["state"] == "open" and not progress and not done and not named_wait:
        x = next((n for n in topo if st[n]["name"] == "blocked"), None)
        if x is not None:
            res.stuck = {"node": x, "missing": st[x]["missing"]}
    res.close = doc["state"] == "open" and done
    agent = [n for n in topo if graph.nodes[n]["kind"] == "agent"]
    records = doc.get("records") or {}
    per_node = {n: records[n]["correction_runs"] for n in agent if n in records and records[n]["correction_runs"]}
    used = sum(records[n]["correction_runs"] for n in agent if n in records)
    limit = doc["budget"] if doc.get("budget") is not None else 3 * len(agent)
    res.budget = {"used": used, "limit": limit, "over": used > limit, "per_node": per_node, "agents": len(agent)}
    for n in topo:
        L = goal_leases.get(n)
        if L and L.live(now) and graph.nodes[n].get("workspace") and st[n]["name"] == "running":
            res.busy = n
            break


def live_input_changes(before: Portfolio, after: Portfolio, now: int, scope=None) -> list:
    """(goal, node, lease, stale_because) for each live lease whose input fingerprint differs between before and
    after. Goals absent from `after` (closed) are skipped; `scope` limits the goals considered."""
    out = []
    for g in sorted(after.goals):
        if scope is not None and g not in scope:
            continue
        b_res = before.goals.get(g)
        if b_res is None:
            continue
        a_res = after.goals[g]
        for n in a_res.graph.topo:
            a = a_res.st.get(n)
            if not a or a["name"] != "running" or not a["lease"].live(now):
                continue
            b = b_res.st.get(n)
            if not b or b["name"] != "running" or b["fp"] == a["fp"]:
                continue
            sb = ["unresolved"] if a["fp"] is None else stale_keys(b.get("parts"), a["parts"])
            out.append((g, n, a["lease"], sb))
    return out


def counts(r0: dict | None, reason: str, old_parts: dict | None, parts: dict) -> int:
    """1 when a new record counts toward the correction budget (SPEC §4.10)."""
    if r0 is None:
        return 0
    keys = stale_keys(old_parts, parts)
    # an input the definition added or removed (present on one side only, with `def` stale) is a policy change, not
    # a correction: like `def` itself it is exempt (G1022: adopting a new graph re-runs in-flight phases for free)
    old_in, new_in = (old_parts or {}).get("inputs") or {}, (parts or {}).get("inputs") or {}
    redefined = {f"inputs.{k}" for k in set(old_in) ^ set(new_in)} if "def" in keys else set()
    if reason == "stale" and all(k in ("def", "candidates", "lenses") or k.startswith("policy.") or k in redefined
                                 for k in keys):
        return 0
    return 1


def all_terminal_current(doc: dict, graph: Graph, dep_view: dict, settings: dict, now: int) -> bool:
    """For §3.3 rule 8 and the generic close (§4.19); leases do not matter for currency."""
    st, _, _, _, _ = frontier(graph, doc, dep_view, {}, settings, now)
    return all(st[t]["name"] == "current" for t in graph.terminal)


# --------------------------------------------------------------------------------------------- ordering (§4.11)

PRI = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def order_key(settings: dict, doc: dict, graph: Graph, node: str) -> tuple:
    stage = graph.nodes[node]["stage"] if node in graph.nodes else "delivery"
    s = (0 if stage == "discovery" else 1) if settings["scheduling"]["order"] == "stage_first" else 0
    return (s, doc["release"], PRI[doc["priority"]], doc["id"], graph.topo.index(node) if node in graph.topo else 0)
