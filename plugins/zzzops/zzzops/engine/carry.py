"""Carry-forward across a clean replay (SPEC §4.21): decided per node from the replay's own commit map."""

from __future__ import annotations

import copy

from engine.fingerprint import fp_selected, input_fp
from engine.frontier import get_path
from engine.identity import Identity


def carry_forward(session, graph, doc, X: str, base_record: dict, replayed: dict, live: dict) -> list:
    """Rewrite, inside X's finishing write, the checkpoint records whose commits map exactly. Returns carried nodes."""
    if not replayed:
        return []
    git = session.git
    ident = Identity(git)
    old, M = replayed["old"], replayed["map"]
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
        ok = True
        for k in cps:
            for c in git.out("rev-list", f"{old}..{r['output'][k]['commit']}").split():
                if c not in M:
                    ok = False
                    break
        if not ok:
            continue
        o = copy.deepcopy(r["output"])
        parts = copy.deepcopy(r["fp_parts"])
        for k in via:
            sel = graph.selectors[n][k]
            parts["inputs"][k] = fp_selected(graph, n, k, get_path(new_output, [sel.output, *sel.path]))
        base_sel = graph.selectors[n]["base"]
        b2 = get_path(new_output, [base_sel.output, *base_sel.path])
        for k in cps:
            c2 = M[r["output"][k]["commit"]]
            o[k] = {"commit": c2, "base": b2, "tree": ident.code_tree(c2), "change": ident.change(b2, c2)}
        if not live.get(n) and o.get("responses"):
            kept = {i: v for i, v in o["responses"].items() if i in open_ids}
            if kept:
                o["responses"] = kept
            else:
                del o["responses"]
        records[n] = dict(r, output=o, fp_parts=parts, input_fp=input_fp(parts), carried_by=X)
        carried.append(n)
    return carried
