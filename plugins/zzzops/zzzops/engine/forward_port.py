"""Start a separately reviewed forward-port of a finished maintenance release."""

from __future__ import annotations

import json

from engine import canon, release_id, schemas, store
from engine.cli import scan_request_key
from engine.errors import Refused
from engine.lines import branching


def start(s, source, destination):
    try:
        source = release_id.canonical(source)
    except ValueError as exc:
        raise Refused("validation", str(exc)) from exc
    s.open(all_goals=True)
    settings = s.state.settings
    if "insertable_release_targets" not in schemas.required_caps(settings):
        raise Refused("validation", "forward-port requires capability `insertable_release_targets`")
    b = branching(settings)
    if not b or "forward_port" not in s.state.graphs:
        raise Refused("validation", "forward-port requires release branching and the forward_port workflow graph")
    lines = s.portfolio().lines
    candidates = [line for line in lines if line.kind == "release" and release_id.equal(line.name, source)]
    if len(candidates) != 1:
        raise Refused("not_ready", "source must identify one finished maintenance release")
    line = candidates[0]
    doc = s.state.docs.get(line.goal) or {}
    graph = s.state.graphs.get(doc.get("graph"))
    finish = next((n for n in graph.topo if graph.nodes[n].get("op") == "git.line_finish"), None) if graph else None
    record = (doc.get("records") or {}).get(finish) or {}
    maintenance = (record.get("output") or {}).get("maintenance") or {}
    tip = maintenance.get("approved_tip")
    sync = (doc.get("records") or {}).get("sync") or {}
    approval = (doc.get("records") or {}).get("approve_finish") or {}
    if (doc.get("state") != "closed" or (doc.get("closed") or {}).get("reason") != "done"
            or record.get("status") != "done" or not record.get("ok")
            or approval.get("status") != "done" or not approval.get("ok")
            or (sync.get("output") or {}).get("merged") != tip or not tip):
        raise Refused("not_ready", "source has no approved finished maintenance provenance")
    allowed = {s.snap.I, b["production"]} | {x.branch for x in lines if x.kind == "release" and x.open}
    if (not isinstance(destination, str) or not schemas.ref_ok(destination)
            or destination.startswith("zzzops/") or destination == line.branch or destination not in allowed):
        raise Refused("validation", "destination must be integration, production or an existing open release line")
    tips = s.fetch_branches([destination, line.branch, b["production"]])
    target_tip = tips.get(destination)
    base = maintenance.get("source_commit")
    parents = s.git.out("rev-list", "--parents", "-n", "1", base).split()[1:] if base and s.git.exists(base) else []
    common = next((x for x in [base, *parents] if s.ancestor(x, target_tip) and s.ancestor(x, tip)), None)
    if not target_tip or not s.git.exists(tip) or not common:
        raise Refused("not_ready", "source and destination lack verifiable common released ancestry")
    source_commit = s.snap.goals[line.goal]
    key = "forward:" + canon.H({"source_goal": line.goal, "tip": tip, "destination": destination})
    hits = scan_request_key(s, key) if s.snap.current else []
    if hits:
        return {"ok": True, "goal": hits[0][0], "created": {"id": hits[0][0], "recovered": True}}
    s.require_writable()
    known = set(s.snap.known) | set(s.snap.goals) | set(s.snap.deleted) | set(s.snap.rewritten)
    gid = max(known | {settings["goals"]["first_id"] - 1}) + 1
    carrier = f"zzzops/forward/{gid}"
    details = {"source_release": source, "source_goal": line.goal, "source_goal_commit": source_commit,
               "source_tip": tip, "released_base": common, "destination": destination,
               "destination_tip": target_tip, "carrier": carrier, "request_key": key}
    goal = {"schema": 1, "id": gid, "title": f"Forward-port release {release_id.label(source)} to {destination}",
            "graph": "forward_port", "state": "open", "closed": None, "spec": json.dumps(details, sort_keys=True),
            "priority": "P1", "release": settings["releases"]["current"], "depends_on": [], "skip": {},
            "links": {"issue": None}, "budget": None, "records": {}}
    errors, _ = schemas.validate_goal(goal, None, {**s.state.docs, gid: goal}, s.state.workflow)
    if errors:
        raise Refused("validation", "; ".join(errors))
    msg = store.with_trailers(store.goal_message("new", gid, "created", "open", request_key=key), goal, settings)
    commit = store.goal_commit(s.git, goal, None, msg)
    result, error = store.push_atomic(s.git, s.R, [(f"refs/heads/zzzops/goal/g{gid}", None, commit),
                                                   (f"refs/heads/{carrier}", None, tip)])
    if result != "ok":
        s.refetch(all_goals=True)
        hits = scan_request_key(s, key)
        if hits:
            return {"ok": True, "goal": hits[0][0], "created": {"id": hits[0][0], "recovered": True}}
        raise Refused("conflict", "could not atomically create forward-port", details={"reason": error[:500]})
    return {"ok": True, "goal": gid, "created": {"id": gid, "recovered": False}}
