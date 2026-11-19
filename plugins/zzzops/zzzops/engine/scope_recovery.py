"""Read-only evidence for restoring test scopes from accepted goal history."""

from __future__ import annotations

from engine import store
from engine.identity import Identity

CAPABILITY = "preserved_test_provenance"


def diagnostics(s, g):
    doc = s.state.docs.get(g)
    if not doc:
        return []
    graph = s.state.graphs.get(doc.get("graph"))
    if not graph:
        return []
    producers = sorted({n.get("preserve") for n in graph.nodes.values() if n.get("preserve")})
    return [d for p in producers if (d := inspect(s, g, p, graph, doc)) is not None]


def inspect(s, g, producer, graph, doc):
    current = (doc.get("records") or {}).get(producer)
    if not current:
        return None
    tip = s.snap.goals[g]
    commits = s.git.out("rev-list", "--first-parent", "--reverse", tip).split()
    paths, issues, seen = {}, [], set()
    latest = None
    ident = Identity(s.git)
    work = s.snap.work.get(g)
    if not work:
        issues.append("current work history is unavailable")
    keys = graph.checkpoint_outputs(producer)
    if not keys:
        return None
    for oid in commits:
        parents = s.git.out("rev-list", "--parents", "-n", "1", oid).split()
        if len(parents) > 2:
            issues.append(f"goal history has ambiguous merge {oid}")
            break
        old, error = store.read_goal_json(s.git, oid)
        if error or not isinstance(old, dict) or old.get("id") != g:
            issues.append(f"goal history {oid} is unreadable")
            break
        r = (old.get("records") or {}).get(producer) or {}
        if r.get("status") != "done" or "frozen" not in r:
            continue
        cp = (r.get("output") or {}).get(keys[0]) or {}
        commit, base = cp.get("commit"), cp.get("base")
        token = (r.get("attempt"), commit, base, tuple(r.get("frozen") or []))
        if token in seen:
            continue
        seen.add(token)
        if (not isinstance(r.get("frozen"), list) or not isinstance(r.get("attempt"), int)
                or not isinstance(commit, str) or not isinstance(base, str)
                or not s.git.exists(commit) or not s.git.exists(base)
                or not s.git.is_ancestor(base, commit)
                or (work and not s.git.is_ancestor(commit, work))):
            issues.append(f"accepted checkpoint for {producer} at {oid} has unavailable or rewritten history")
            continue
        try:
            if cp.get("tree") != ident.code_tree(commit) or cp.get("change") != ident.change(base, commit, paths=sorted(r["frozen"])):
                issues.append(f"accepted checkpoint identity at {oid} is inconsistent")
                continue
        except Exception:
            issues.append(f"accepted checkpoint at {oid} cannot be verified")
            continue
        latest = {"goal_commit": oid, "attempt": r["attempt"], "checkpoint": commit, "checkpoint_base": base}
        for path in r["frozen"]:
            source = {"goal_commit": oid, "attempt": r["attempt"], "checkpoint": commit, "checkpoint_base": base}
            paths.setdefault(path, []).append(source)
    if not paths and not issues:
        return None
    known = set(current.get("frozen") or [])
    missing = set(paths) - known
    if not missing and not issues:
        return None
    if known - set(paths):
        issues.append("current scope contains paths without verifiable accepted history")
    if current.get("status") == "done":
        issues.append("done checkpoint identity requires producer resubmission")
    entries = [{"path": path, "sources": sorted(src, key=lambda x: (x["goal_commit"], x["attempt"]))}
               for path, src in sorted(paths.items())]
    proposed = None if issues else {"base": tip, "work_commit": work, "edit": {"set": {f"records.{producer}.frozen": sorted(paths),
                                                                  f"records.{producer}.recovery_work": work}}}
    from engine.workspace_gate import WARNING
    return {"producer": producer, "status": "uncertain" if issues else "proposal", "goal_commit": tip,
            "producer_state": current.get("status"), "latest_accepted_checkpoint": latest,
            "paths": entries, "proposal": proposed, "issues": issues,
            "concurrency_guard": "cooperating_writers", "concurrency_warning": WARNING}
