"""Carry-forward across a clean replay (SPEC §4.21): decided per node from the replay's own commit map."""

from __future__ import annotations

import copy

from engine.fingerprint import fp_selected, input_fp
from engine.frontier import get_path
from engine.identity import Identity
from engine.records import checkpoint_scope


def carry_forward(session, graph, doc, X: str, base_record: dict, replayed: dict, live: dict) -> list:
    """Rewrite, inside X's finishing write, the checkpoint records whose commits map exactly. Returns carried nodes."""
    synced = base_record["output"].get("synced")
    if not replayed and not synced:
        return []
    git = session.git
    ident = Identity(git)
    old, M = (synced["old"], {}) if synced else (replayed["old"], replayed["map"])
    new_output = base_record["output"]
    records = doc.get("records") or {}
    open_ids = {f["id"] for r in records.values() for f in r.get("findings") or [] if f["status"] == "open"}
    carried = []
    for n in graph.topo:
        nd = graph.nodes[n]
        if nd["kind"] != "agent" or not nd.get("workspace"):
            continue
        via = [k for k, s in (nd.get("inputs") or {}).items()
               if not s.get("context") and graph.selectors[n][k].kind == "node" and graph.selectors[n][k].node == X]
        cps = graph.checkpoint_outputs(n)
        r = records.get(n)
        if not via or not cps or not r or r["status"] != "done":
            continue
        if any(not isinstance(r["output"].get(k), dict) or r["output"][k]["base"] != old for k in cps):
            continue
        scope = checkpoint_scope(graph, n, r)
        relocated = {}
        for k in cps:
            cp = r["output"][k]
            if synced:
                c2 = relocate(cp, synced, git)
                if c2 is None:
                    break
                new_cp = {"commit": c2, "base": synced["onto"], "tree": ident.code_tree(c2), "change": cp["change"]}
                if not unchanged(ident, n, k, cp, new_cp, scope):
                    break
                relocated[k] = new_cp
            elif all(c in M for c in git.out("rev-list", f"{old}..{cp['commit']}").split()) and cp["commit"] in M:
                c2 = M[cp["commit"]]
                relocated[k] = {"commit": c2, "base": new_output["base_commit"], "tree": ident.code_tree(c2),
                                "change": ident.change(new_output["base_commit"], c2, paths=scope)}
        if len(relocated) != len(cps):
            continue
        o = copy.deepcopy(r["output"])
        parts = copy.deepcopy(r["fp_parts"])
        for k in via:
            sel = graph.selectors[n][k]
            parts["inputs"][k] = fp_selected(graph, n, k, get_path(new_output, [sel.output, *sel.path]))
        o.update(relocated)
        if not live.get(n) and o.get("responses"):
            kept = {i: v for i, v in o["responses"].items() if i in open_ids}
            if kept:
                o["responses"] = kept
            else:
                del o["responses"]
        records[n] = dict(r, output=o, fp_parts=parts, input_fp=input_fp(parts), carried_by=X)
        carried.append(n)
    return carried


def relocate(cp: dict, synced: dict | None, git=None) -> str | None:
    if synced and (cp["commit"] == synced["work"] or (git is not None and git.is_ancestor(cp["commit"], synced["work"]))):
        return synced["tip"]
    return None


def unchanged(ident, node, key, old_cp, new_cp, scope):
    return ident.change(new_cp["base"], new_cp["commit"], paths=scope) == old_cp["change"]
