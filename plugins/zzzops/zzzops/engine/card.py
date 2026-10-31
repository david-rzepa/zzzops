"""Task card construction (SPEC §3.14, §4.20): at most 4,096 bytes."""

from __future__ import annotations

import json

from engine.canon import canonical, iso
from engine.frontier import recorded_out, resolve
from engine.render import command, first_line

CARD_LIMIT = 4096
INLINE = 600


def view(reader, v):
    if len(canonical(v)) <= INLINE:
        return v
    text = v if isinstance(v, str) else json.dumps(v, indent=2, sort_keys=True, ensure_ascii=False)
    return reader.blob_view(text)


def checkpoint_view(cp):
    return {"commit": cp["commit"], "tree": cp["tree"], "change": cp["change"],
            "diff": f"git diff {cp['base']} {cp['commit']} -- ':/' ':(top,exclude).zzzops/reviews'"}


def value_of(session, res, n, name, v):
    """The card view of one resolved input value."""
    sel = res.graph.selectors[n][name]
    if v is None:
        return None
    t = res.graph.output_types.get(sel.node, {}).get(sel.output) if sel.kind in ("node", "deps") and not sel.path else None
    reader = session.ctx().reader

    def one(x, producer_out=None, goal=res.goal):
        if x is None:
            return None
        if t == "checkpoint" and isinstance(x, dict):
            return checkpoint_view(x)
        if t == "artifact" and isinstance(x, dict):
            out = {"path": x["path"], "blob": x["blob"], "read": f"git cat-file -p {x['blob']}"}
            summary = (producer_out or {}).get("summary")
            if isinstance(summary, str):
                out["summary"] = summary[:400]
            if not session.git.exists(x["blob"]):
                session.fetch_work_of(goal)
                if not session.git.exists(x["blob"]):
                    out["read"] = "(full text no longer available)"
            return out
        return view(reader, x)

    if sel.kind == "deps":
        cur = {}
        for d, x in sorted((v or {}).items()):
            dv = session.portfolio().views.get(int(d), {})
            cur[d] = one(x, (dv.get("cur") or {}).get(sel.node), int(d))
        return cur
    producer_out = res.cur.get(sel.node) if sel.kind == "node" else None
    return one(v, producer_out)


def build(session, res, n: str, s: dict, lease: dict, suggested: dict | None = None) -> dict:
    g, graph, doc = res.goal, res.graph, res.doc
    nd = graph.nodes[n]
    ctx = session.ctx()
    reader = ctx.reader
    settings = session.settings
    vals, _ = resolve(graph, doc, n, lambda p: res.cur[p] if p in res.cur else recorded_out(doc, p),
                      session.portfolio().views)
    inputs, context = {}, {}
    for name in sorted(nd.get("inputs") or {}):
        if name not in vals:
            continue
        target = context if nd["inputs"][name].get("context") else inputs
        target[name] = value_of(session, res, n, name, vals[name])
    cap = nd.get("capability", "bounded")
    if s.get("reason") == "retry":
        cap = "reasoning"
    elif s.get("stale_because") == ["inputs.base"]:
        cap = "routine"
    timeout = lease["timeout"]
    every = max(1, timeout // 4)
    card = {"ok": True, "coordinator": session.state.coordinator, "goal": g, "title": doc["title"], "node": n,
            "stage": nd["stage"],
            "run": {"root": bool(nd.get("root", False)), "capability": cap,
                    "models": list(settings["routing"]["tiers"].get(cap, []))},
            "lease": {"branch": f"zzzops/lease/g{g}/{n}", "attempt": lease["attempt"], "holder": lease["holder"],
                      "timeout_minutes": timeout, "renew_every_minutes": every, "expires_at": iso(lease["expires_at"])},
            "renew": f"Renew every {every} minutes (timeout {timeout}). After any pause, renew first.",
            "reason": lease["card_reason"]}
    if s.get("stale_because"):
        card["stale_because"] = s["stale_because"]
    prompt_text = reader.prompt(nd["prompt"]) or ""
    card["prompt"] = {"text": prompt_text} if len(prompt_text.encode("utf-8")) <= INLINE else \
        dict(reader.blob_view(prompt_text), blob=lease.get("prompt") or reader.blob_view(prompt_text).get("blob"))
    if lease.get("prompt") and "blob" not in card["prompt"]:
        card["prompt"]["blob"] = lease["prompt"]
    ins = (session.state.policy or {}).get("instructions") or {}
    card["instructions"] = {k: ({"text": ins[k]} if len(ins[k].encode("utf-8")) <= INLINE else reader.blob_view(ins[k]))
                            for k in nd.get("instructions", []) if k in ins}
    card["inputs"], card["context"] = inputs, context
    if nd.get("workspace"):
        cmds = []
        for name in sorted(nd.get("inputs") or {}):
            sel = graph.selectors[n][name]
            t = graph.output_types.get(sel.node, {}).get(sel.output) if sel.kind == "node" and not sel.path else None
            if t == "strings" and isinstance(vals.get(name), list):
                cmds += vals[name]
        if cmds:
            card["commands_to_run"] = {"from": "commands", "list": cmds, "note": "Run these in the workspace before you submit."}
    card["corrections"] = [{"id": f["id"], "from": _carrier(res, f), "text": f["text"], "rounds": f["rounds"],
                            "upheld": f["upheld"]} for f in s.get("corrections") or []]
    prev = previous(session, res, n, s)
    if prev:
        card["previous"] = prev
    if suggested:
        card["suggested_checkpoint"] = suggested
    r = (doc.get("records") or {}).get(n)
    if s.get("reason") == "retry" and r:
        if r.get("answer"):
            card["answer"] = {k: r["answer"][k] for k in ("text", "quote", "decided_by") if k in r["answer"]}
        if (r.get("blocked") or {}).get("instructions"):
            card["blocked_instructions"] = r["blocked"]["instructions"]
    I = session.snap.integration
    card["read_dev"] = {"commit": I, "show": f"git show {I}:<path>", "grep": f"git grep <pattern> {I}",
                        "mirror": session.mirror_path()}
    card["workspace"] = lease.get("workspace")
    card["output_schema"] = output_schema(graph, n, s)
    arts = graph.artifact_outputs(n)
    if arts:
        card["artifact"] = {"output": arts[0], "path": f".zzzops/reviews/{g}/{n}.md"}
    holder, N = lease["holder"], str(lease["attempt"])
    card["commands"] = {
        "submit": command(ctx, ["submit", str(g), n, "--attempt", N, "--as", holder, "--output", "<F>"]
                          + (["--artifact", "<A>"] if arts else [])),
        "blocked": command(ctx, ["submit", str(g), n, "--attempt", N, "--as", holder, "--blocked", "<F>"]),
        "renew": command(ctx, ["renew", str(g), n, "--attempt", N]),
        "abandon": command(ctx, ["abandon", str(g), n, "--attempt", N])}
    return shrink(card, reader)


def _carrier(res, f):
    for c, x in sum((res.live.get(t, []) for t in res.live), []):
        if x is f:
            return c
    return f["id"].split(":")[0]


def output_schema(graph, n, s) -> dict:
    out = {}
    if graph.is_review(n):
        out["decision"] = "approved | changes_requested (approved only with no finding open)"
        out["summary"] = "text: your verdict"
        out["findings"] = ("[{\"id\": <prior id>, \"status\": \"open\"|\"resolved\"} for every prior open finding, "
                           "{\"target\"?: <node>, \"text\": …} for new ones]")
    else:
        for k, t in graph.output_types[n].items():
            if t == "checkpoint":
                out[k] = ("checkpoint: the suggested checkpoint if any, else HEAD (a phase that adds no commit keeps its "
                          "previous checkpoint); or {\"commit\": sha}")
            elif t == "artifact":
                out[k] = "artifact: write the file and pass it with --artifact"
            else:
                out[k] = t
        out["findings"] = "optional: [{\"target\": <ancestor node>, \"text\": …}]"
    if s.get("corrections"):
        out["responses"] = "required for: " + ", ".join(f["id"] for f in s["corrections"])
    return out


def previous(session, res, n, s) -> dict | None:
    r = (res.doc.get("records") or {}).get(n)
    if not r or r["status"] != "done":
        return None
    prev = {}
    if res.graph.is_review(n):
        subj = res.graph.subject(n)
        sr = (res.doc.get("records") or {}).get(subj) or {}
        responses = ((sr.get("output") or {}).get("responses")) or {}
        prev["findings"] = [{"id": f["id"], "target": f["target"], "text": f["text"], "status": f["status"],
                             "response": responses.get(f["id"], f.get("response"))}
                            for f in r.get("findings") or [] if f["target"] != n]
        for k, old in (r.get("reviewed") or {}).items():
            cur = (sr.get("output") or {}).get(k)
            if not isinstance(cur, dict) or cur.get("change") == old.get("change"):
                continue
            if session.git.exists(old["commit"]):
                prev["interdiff"] = (f"git range-diff {old['base']}..{old['commit']} {cur['base']}..{cur['commit']}")
            else:
                prev["note"] = "previous version not available; review in full"
    if s.get("stale_because") == ["def"]:
        prev["output"] = r["output"]
        prev["hint"] = "If it still holds, resubmit it."
    return prev or None


def shrink(card: dict, reader) -> dict:
    """While the card is over 4,096 bytes, replace the largest inline text with a view reference."""
    for _ in range(60):
        if len(canonical(card)) <= CARD_LIMIT:
            return card
        cands = []
        if "text" in card.get("prompt", {}):
            cands.append((len(card["prompt"]["text"]), ("prompt",)))
        for k, v in card.get("instructions", {}).items():
            if "text" in v:
                cands.append((len(v["text"]), ("instructions", k)))
        for sect in ("inputs", "context"):
            for k, v in card.get(sect, {}).items():
                if isinstance(v, str):
                    cands.append((len(v), (sect, k)))
                elif isinstance(v, (dict, list)) and "blob" not in (v if isinstance(v, dict) else {}):
                    cands.append((len(canonical(v)), (sect, k)))
        for i, c in enumerate(card.get("corrections", [])):
            if len(c["text"]) > 200:
                cands.append((len(c["text"]), ("corrections", i)))
        cands = [c for c in cands if c[0] > 100]
        if not cands:
            break
        _, path = max(cands, key=lambda c: c[0])
        if path[0] == "prompt":
            card["prompt"] = reader.blob_view(card["prompt"]["text"])
        elif path[0] == "instructions":
            card["instructions"][path[1]] = reader.blob_view(card["instructions"][path[1]]["text"])
        elif path[0] == "corrections":
            c = card["corrections"][path[1]]
            c["full"] = reader.blob_view(c["text"])
            c["text"] = c["text"][:200]
        else:
            v = card[path[0]][path[1]]
            card[path[0]][path[1]] = reader.blob_view(v if isinstance(v, str) else json.dumps(v, indent=2, sort_keys=True))
    return card
