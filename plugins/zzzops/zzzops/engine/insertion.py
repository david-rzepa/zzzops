"""Preview an isolated inserted release from an approved immutable source."""

from __future__ import annotations

import copy

from engine import canon, release_id, schemas
from engine.errors import Refused
from engine.lines import branching, line_branch

CAPABILITY = "insertable_release_targets"


def preview(s, target, source):
    try:
        target, source = release_id.canonical(target), release_id.canonical(source)
    except ValueError as exc:
        raise Refused("validation", str(exc)) from exc
    s.open(all_goals=True, readonly=True)
    settings = s.state.settings
    collision = next((b for b in s.state.blockers if b.get("kind") in
                      ("release_alias_collision", "release_alias_check_unavailable")), None)
    if collision:
        raise Refused("conflict", collision["message"])
    if CAPABILITY not in schemas.required_caps(settings):
        raise Refused("validation", f"release insertion requires capability `{CAPABILITY}`")
    b = branching(settings)
    if not b:
        raise Refused("usage", "release insertion requires settings.branching")
    source_lines = [line for line in s.portfolio().lines
                    if line.kind == "release" and release_id.equal(line.name, source)]
    if len(source_lines) != 1:
        raise Refused("not_ready", f"release {source} requires one unambiguous finished source line")
    line = source_lines[0]
    doc = s.state.docs.get(line.goal)
    if not doc or doc.get("state") != "closed" or (doc.get("closed") or {}).get("reason") != "done":
        raise Refused("not_ready", f"release {source} is not successfully finished")
    graph = s.state.graphs.get(doc.get("graph"))
    finish = next((n for n in graph.topo if graph.nodes[n].get("op") == "git.line_finish"), None) if graph else None
    record = (doc.get("records") or {}).get(finish) or {}
    output = record.get("output") or {}
    # Fetch only to make immutable recorded objects available locally; the
    # movable source ref is never used as the release provenance.
    s.fetch_branches([b["production"], line.branch])
    maintenance = output.get("maintenance")
    source_commit = output.get("production_merge")
    provenance_kind = "production_merge"
    if not source_commit and isinstance(maintenance, dict):
        source_commit = maintenance.get("approved_tip")
        provenance_kind = "maintenance"
        approved = (doc.get("records") or {}).get("approve_finish") or {}
        sync = (doc.get("records") or {}).get("sync") or {}
        if (approved.get("status") != "done" or not approved.get("ok")
                or (sync.get("output") or {}).get("merged") != source_commit
                or not s.ancestor(maintenance.get("source_commit"), source_commit)):
            raise Refused("not_ready", f"release {source} lacks approved maintenance provenance")
    production = s.target_tip(b["production"])
    if not production:
        raise Refused("not_found", f"production branch `{b['production']}` was not found")
    if record.get("status") != "done" or not record.get("ok") or not source_commit or not s.git.exists(source_commit):
        raise Refused("not_ready", f"release {source} has no verifiable finished source commit")
    released_base = maintenance.get("source_commit") if provenance_kind == "maintenance" else source_commit
    if not s.ancestor(released_base, production):
        raise Refused("not_ready", "source release and production have no verified released ancestry")
    if release_id.components(target) <= release_id.components(source):
        raise Refused("validation", "inserted target must follow its source release")
    branch = line_branch(b, "release", target)
    ledger = s.portfolio().ledger
    completed = sorted(g for g, entry in ledger.items()
                       if not entry.get("line") and not entry.get("hotfix")
                       and release_id.equal(entry.get("release"), target)
                       and entry.get("state") == "closed" and entry.get("closed") == "done")
    details = {"target": target, "source_release": source, "source_goal": line.goal,
               "source_commit": source_commit, "source_provenance_kind": provenance_kind,
               "source_provenance_goal_commit": s.snap.goals[line.goal],
               "production_ref": b["production"], "production_commit": production,
               "mode": "production_patch" if source_commit == production else "maintenance",
               "branch": branch,
               "later_lines": [x.name for x in s.portfolio().lines
                               if x.kind == "release" and release_id.components(x.name) > release_id.components(target)],
               "already_completed_members": completed}
    details["fingerprint"] = "v1:sha256:" + canon.H(details)
    return {"ok": True, "coordinator": s.state.coordinator, "insert_preview": details,
            "answer_template": {"decision": "approved", "quote": "<owner words>",
                                "decided_by": "<name>", "fingerprint": details["fingerprint"]}}


def insert(s, target, source, answer):
    from engine import lineverbs, store
    from engine.cli import scan_request_key

    if not isinstance(answer, dict) or answer.get("decision") != "approved":
        raise Refused("validation", "release insert requires an approved answer")
    if any(not isinstance(answer.get(k), str) or not answer[k].strip()
           for k in ("quote", "decided_by", "fingerprint")):
        raise Refused("validation", "answer requires quote, decided_by and fingerprint")
    details = preview(s, target, source)["insert_preview"]
    if answer["fingerprint"] != details["fingerprint"]:
        raise Refused("preview_stale", "release insertion preview changed; obtain fresh approval")
    if details["already_completed_members"]:
        raise Refused("not_ready", "completed integration members require reviewed backport before insertion",
                      details={"goals": details["already_completed_members"]})
    s.require_writable()
    name, branch = release_id.label(details["target"]), details["branch"]
    key = lineverbs.line_key("release", name)
    metadata = {"mode": details["mode"], "source_release": details["source_release"],
                "source_goal": details["source_goal"], "source_commit": details["source_commit"],
                "source_goal_commit": details["source_provenance_goal_commit"],
                "production_commit": details["production_commit"],
                "fingerprint": details["fingerprint"], "verified": False,
                "approval": {k: v for k, v in answer.items() if k != "fingerprint"}}
    hits = scan_request_key(s, key) if s.snap.current else []
    if hits:
        gid, _, old = hits[0]
        meta = (old.get("flow") or {}).get("inserted") or {}
        if (old.get("state") == "closed" or meta.get("source_commit") != details["source_commit"]
                or not release_id.equal(meta.get("source_release"), details["source_release"])):
            raise Refused("conflict", "release line exists with different or finished provenance")
        if meta.get("verified"):
            if meta.get("fingerprint") != details["fingerprint"]:
                raise Refused("conflict", "verified release line has different provenance")
            return {"ok": True, "goal": gid, "branch": branch, "created": {"id": gid, "recovered": True}}
        observed = s.fetch_branches([branch, details["production_ref"]])
        if (observed.get(branch) != details["source_commit"]
                or observed.get(details["production_ref"]) != details["production_commit"]
                or s.snap.goals.get(details["source_goal"]) != details["source_provenance_goal_commit"]):
            raise Refused("preview_stale", "pending release observations changed; obtain fresh approval")
        verified = copy.deepcopy(old)
        metadata["verified"] = True
        verified["flow"]["inserted"] = metadata
        old_tip = s.snap.goals[gid]
        message = store.with_trailers(store.goal_message("edit", gid, "verified inserted release", "open"),
                                      verified, s.state.settings)
        new = store.goal_commit(s.git, verified, old_tip, message)
        result, stderr = store.push_atomic(s.git, s.R, [(f"refs/heads/zzzops/goal/g{gid}", old_tip, new)])
        if result != "ok":
            raise Refused("conflict", "release remains pending after verification race", details={"reason": stderr[:500]})
        return {"ok": True, "goal": gid, "branch": branch, "pending_verification": False,
                "created": {"id": gid, "recovered": True}}
    if s.fetch_branches([branch]).get(branch):
        raise Refused("conflict", f"release branch `{branch}` already exists")
    line_answer = {k: v for k, v in answer.items() if k != "fingerprint"}
    gid, doc, commit = lineverbs.line_goal(s, "release", name, branch, details["source_commit"],
                                          line_answer, key, inserted=metadata)
    ref = f"refs/heads/zzzops/goal/g{gid}"
    result, stderr = store.push_atomic(s.git, s.R, [(ref, None, commit),
                                                     (f"refs/heads/{branch}", None, details["source_commit"])])
    if result != "ok":
        raise Refused("conflict", "could not atomically create release line and goal", details={"reason": stderr[:500]})
    s.refetch(all_goals=True)
    created = s.state.docs.get(gid)
    if not created:
        raise Refused("remote", "release created but goal could not be re-read; it remains pending")
    branch_tip = s.fetch_branches([branch]).get(branch)
    production = s.fetch_branches([details["production_ref"]]).get(details["production_ref"])
    if (branch_tip != details["source_commit"] or production != details["production_commit"]
            or s.snap.goals.get(details["source_goal"]) != details["source_provenance_goal_commit"]):
        return {"ok": True, "goal": gid, "branch": branch, "pending_verification": True,
                "created": {"id": gid, "recovered": False}}
    verified = copy.deepcopy(created)
    verified["flow"]["inserted"]["verified"] = True
    old = s.snap.goals[gid]
    message = store.with_trailers(store.goal_message("edit", gid, "verified inserted release", "open"),
                                  verified, s.state.settings)
    new = store.goal_commit(s.git, verified, old, message)
    result, stderr = store.push_atomic(s.git, s.R, [(ref, old, new)])
    if result != "ok":
        raise Refused("conflict", "release remains pending after verification race", details={"reason": stderr[:500]})
    return {"ok": True, "goal": gid, "branch": branch, "pending_verification": False,
            "created": {"id": gid, "recovered": False}}
