"""`release cut N` and `hotfix start X` (G1025 design §3.3, §7): create a line branch and the line goal that owns it,
in one atomic push, race-safe through a request key derived from the line alone."""

from __future__ import annotations

import copy
import time

from engine import canon, schemas
from engine import records as rec
from engine.canon import iso
from engine.errors import Refused
from engine.lines import RELEASE_GRAPH, branching, line_branch


def line_key(kind: str, name: str) -> str:
    """Derived from the line alone, never from the answer file, so racing delegates share one key (§3.3)."""
    return "line:" + canon.H({"line": kind, "name": str(name)})


def check_answer(a) -> dict:
    if not isinstance(a, dict):
        raise Refused("validation", "the answer file must be an object")
    e = schemas.Errors()
    e.unknown("answer", a, {"decision", "summary", "quote", "decided_by", "decided_at"})
    if a.get("decision") != "approved":
        e.add("answer.decision", "must be approved")
    for k in ("quote", "decided_by"):
        if not isinstance(a.get(k), str) or not a[k].strip():
            e.add(f"answer.{k}", "required, non-empty")
    if e:
        raise Refused("validation", "; ".join(e), details={"errors": list(e)})
    return a


def run(s, kind: str, name: str, answer: dict) -> dict:
    from engine import store
    from engine.cli import scan_request_key
    check_answer(answer)
    name = str(name)
    s.open()
    b = branching(s.state.settings)
    if not b:
        raise Refused("usage", "release lines need settings.branching in .zzzops/POLICY.json",
                      hint="add the branching block (and the release graph) through a zzzops/policy/* branch")
    if RELEASE_GRAPH not in s.state.graphs:
        raise Refused("validation", f"the policy has no {RELEASE_GRAPH!r} graph", hint="copy it from the template")
    if kind == "hotfix" and (not schemas.ref_ok(name) or "/" in name):
        raise Refused("validation", f"{name!r} is not a usable hotfix name")
    key = line_key(kind, name)
    branch = line_branch(b, kind, name)
    deadline = time.monotonic() + 30
    while True:
        hits = scan_request_key(s, key) if s.snap.current else []
        if hits:
            gid, root, doc = hits[0]
            cur = s.state.docs.get(gid)
            if cur is None or cur.get("state") == "closed":
                raise Refused("validation" if kind == "hotfix" else "not_ready",
                              f"{kind} {name} is finished (G{gid}); choose a new name" if kind == "hotfix"
                              else f"release {name} was already cut and finished (G{gid})")
            return output(s, kind, name, branch, cur, recovered=True)
        s.require_writable()
        p = s.portfolio()
        start_from = check_ready(s, p, kind, name, b)
        existing = s.fetch_branches([branch]).get(branch)
        warnings = []
        if existing:
            if kind == "release" and s.ancestor(existing, s.snap.integration):
                cut, warnings = existing, [{"kind": "line_branch_adopted",
                                            "message": f"{branch} already existed at {existing[:12]}; adopted as the cut"}]
            else:
                why = f"is not a cut of {s.snap.I}" if kind == "release" else "exists"
                raise Refused("conflict", f"{branch} already exists at {existing[:12]} and {why}",
                              hint=f"delete or rename {branch}, then retry")
        else:
            cut = start_from
        gid, doc, commit = line_goal(s, kind, name, branch, cut, answer, key)
        updates = [(f"refs/heads/zzzops/goal/g{gid}", None, commit)]
        if not existing:
            updates.append((f"refs/heads/{branch}", None, cut))
        r, stderr = store.push_atomic(s.git, s.R, updates)
        if r == "ok":
            s.snap.advance(updates[:1])
            s.snap.targets[branch] = cut
            s.state.docs[gid] = doc
            s.state.ledger[gid] = {"release": doc["release"], "state": "open", "closed": None,
                                   "line": f"{kind}:{name}", "hotfix": None}
            s._portfolio = None
            out = output(s, kind, name, branch, doc, recovered=False)
            if warnings:
                out["warnings"] = warnings
            return out
        if r == "remote":
            raise Refused("remote", f"push to `{s.R}` failed: {stderr.strip().splitlines()[:1]}",
                          hint="rerun the same command: it is safe to retry")
        if time.monotonic() > deadline:
            raise Refused("contention", "could not create the line; retry shortly")
        s.refetch()                                            # a racing cut won, or the id was taken: check again


def check_ready(s, p, kind, name, b) -> str:
    """The item's conditions (§3.2, §7) on this fetch; returns the commit the branch starts from."""
    if kind == "release":
        if not name.isdigit():
            raise Refused("usage", "release cut takes a release number")
        if not p.cut or str(p.cut["release"]) != name:
            why = "; ".join(w["reason"] for w in p.release_waiting) or \
                f"release {name} is not complete on {s.snap.I} (every goal closed, at least one done)"
            raise Refused("not_ready", f"release {name} cannot be cut: {why}")
        return s.snap.integration
    if any(x.kind == "hotfix" and x.name == name for x in p.lines):
        raise Refused("validation", f"hotfix {name} already has a line; choose a new name")
    tip = s.target_tip(b["production"])
    if not tip:
        raise Refused("not_found", f"the production branch `{b['production']}` is not on `{s.R}`")
    return tip


def line_goal(s, kind, name, branch, cut, answer, key) -> tuple:
    from engine import store
    from engine.frontier import portfolio
    st = s.state
    settings = st.settings
    known = set(s.snap.known) | set(s.snap.goals) | set(s.snap.deleted) | set(s.snap.rewritten)
    gid = max(known | {settings["goals"]["first_id"] - 1}) + 1
    p = s.portfolio()
    release = int(name) if kind == "release" else (p.effective or settings["releases"]["current"])
    frm = s.snap.I if kind == "release" else settings["branching"]["production"]
    title = f"Release {name}" if kind == "release" else f"Hotfix {name}"
    doc = {"schema": 2, "id": gid, "title": title, "graph": RELEASE_GRAPH, "state": "open", "closed": None,
           "spec": f"{title}: the line branch `{branch}`, cut from `{frm}` at {cut}. Created by "
                   f"`zzzops {'release cut' if kind == 'release' else 'hotfix start'} {name}`.",
           "priority": "P1", "release": release, "depends_on": [], "skip": {}, "links": {"issue": None},
           "budget": None, "records": {},
           "flow": {"line": kind, "name": name, "branch": branch, "from": frm, "cut": cut}}
    graph = st.graphs[RELEASE_GRAPH]
    first = next(n for n in graph.topo if graph.nodes[n]["kind"] == "human" and not graph.producers(n))
    docs = dict(st.docs)
    docs[gid] = doc
    pf = portfolio(docs, st.graphs, {}, settings, s.now, st.invalid, st.newer, **s.pf_kwargs(docs))
    state = pf.goals[gid].st[first]
    ready = state.get("ready") or state
    out = {"decision": "approved", "summary": answer.get("summary") or f"cut {branch} from {frm} at {cut[:12]}",
           "decided_by": answer["decided_by"], "quote": answer["quote"], "decided_at": answer.get("decided_at") or iso(s.now)}
    doc["records"][first] = rec.record("done", True, 1, "human", "new", None, ready["fp"], ready["parts"], out, [], s.now)
    errs, _ = schemas.validate_goal(doc, None, docs, st.workflow)
    if errs:
        raise Refused("validation", "; ".join(errs[:5]), details={"errors": list(errs)})
    msg = store.with_trailers(store.goal_message("new", gid, "created", "open", request_key=key), doc, settings)
    return gid, doc, store.goal_commit(s.git, doc, None, msg)


def output(s, kind, name, branch, doc, recovered) -> dict:
    out = {"ok": True, "coordinator": s.state.coordinator, kind: int(name) if kind == "release" else name,
           "branch": branch, "cut": doc["flow"]["cut"], "goal": doc["id"],
           "created": {"id": doc["id"], "display": f"G{doc['id']}", "recovered": recovered}}
    out["next"] = s.render_next(scope=[doc["id"]])
    return out
