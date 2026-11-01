"""Fingerprints (SPEC §4.8). Pure functions of values; provenance is never identity."""

from __future__ import annotations

from engine import FP_VERSION
from engine.canon import H
from engine.ops import OPS
from engine.schemas import Graph, get_dotted, is_material

V = FP_VERSION + ":"


def fp(value, type_: str) -> str:
    if value is not None and type_ == "checkpoint":
        return V + "change:" + value["change"]
    if value is not None and type_ == "artifact":
        return V + "blob:" + value["blob"]
    return V + "sha256:" + H(value)


def fp_selected(graph: Graph, node: str, name: str, value) -> str:
    sel = graph.selectors[node][name]
    t = graph.selector_type(sel)
    if t == "map":
        et = graph.element_type(sel)
        return V + "sha256:" + H({k: fp(v, et) for k, v in sorted((value or {}).items())})
    return fp(value, t)


def out_fp(graph: Graph, node: str, record: dict, drop=()) -> str:
    """The recorded output, normalized: checkpoints by change, artifacts by blob."""
    types = graph.output_types.get(node, {})
    out = {k: v for k, v in (record.get("output") or {}).items() if k not in drop}
    return V + "sha256:" + H({k: (fp(v, types.get(k, "plain")) if types.get(k) in ("checkpoint", "artifact") else v)
                              for k, v in out.items()})


def node_def_fp(nd: dict) -> str:
    """ALLOWLIST of the semantic fields of a node definition."""
    d = {"kind": nd["kind"], "op": nd.get("op"),
         "op_version": OPS[nd["op"]].version if nd["kind"] == "op" and nd.get("op") in OPS else None,
         "inputs": {k: {"from": s["from"], "optional": s.get("optional", False), "pending": s.get("pending", False)}
                    for k, s in (nd.get("inputs") or {}).items() if not s.get("context")},
         "outputs": nd.get("outputs", {}), "review": nd.get("review"), "preserve": nd.get("preserve"),
         "workspace": nd.get("workspace", False), "rev": nd.get("rev", 0)}
    if isinstance(nd.get("lenses"), dict):        # only on multi-lens reviewers, so no other node's fp changes
        d["lenses"] = {k: (s or {}).get("skippable", True) is not False for k, s in nd["lenses"].items()}
    return V + "sha256:" + H(d)


def candidates(graph: Graph, f: str, records: dict) -> list:
    """A filter's `candidates` part: the sorted [id, material] pairs of the open findings on its lenses' latest records
    (`records`: the goal's non-skipped records). A finding without `material` counts as material."""
    out = []
    for lens in graph.reviewers(f):
        for x in (records.get(lens) or {}).get("findings") or []:
            if x["status"] == "open":
                out.append([x["id"], is_material(x)])
    return sorted(out)


def fp_parts(graph: Graph, node: str, vals: dict, subject_record: dict | None, settings: dict,
             records: dict | None = None, skip: dict | None = None) -> dict:
    nd = graph.nodes[node]
    p = {"def": node_def_fp(nd),
         "inputs": {k: fp_selected(graph, node, k, vals.get(k)) for k, s in sorted((nd.get("inputs") or {}).items())
                    if not s.get("context")},
         "policy": {k: get_dotted(settings, k) for k in nd.get("policy", [])}}
    subject = graph.subject(node)
    if subject:
        p["subject"] = out_fp(graph, subject, subject_record or {}, drop={"responses"})
    if graph.is_filter(node):
        p["candidates"] = candidates(graph, node, records or {})
    if graph.lens_defs(node):
        p["lenses"] = graph.applied_lenses(node, skip)
    return p


def input_fp(parts: dict) -> str:
    return V + "sha256:" + H(parts)


def stale_keys(old: dict | None, new: dict) -> list:
    old = old or {}
    keys = []
    if old.get("def") != new.get("def"):
        keys.append("def")
    for k in sorted(set(old.get("inputs") or {}) | set(new.get("inputs") or {})):
        if (old.get("inputs") or {}).get(k) != (new.get("inputs") or {}).get(k):
            keys.append(f"inputs.{k}")
    for k in sorted(set(old.get("policy") or {}) | set(new.get("policy") or {})):
        if (old.get("policy") or {}).get(k, _ABSENT) != (new.get("policy") or {}).get(k, _ABSENT):
            keys.append(f"policy.{k}")
    if old.get("subject") != new.get("subject"):
        keys.append("subject")
    if old.get("candidates") != new.get("candidates"):
        keys.append("candidates")
    if old.get("lenses") != new.get("lenses"):
        keys.append("lenses")
    return sorted(keys)


_ABSENT = object()
