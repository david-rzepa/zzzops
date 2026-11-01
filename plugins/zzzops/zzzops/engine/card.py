"""Task card construction (SPEC §3.14, §4.20): aimed at 4,096 bytes; see `shrink`."""

from __future__ import annotations

import copy
import hashlib
import json

from engine.canon import canonical, iso
from engine.frontier import recorded_out, resolve
from engine.render import clip, command, first_line

CARD_LIMIT = 4096
INLINE = 600
SUMMARY = 120


def key_summary(v) -> str:
    """One line for a blobbed dict or list: scalars as k=v, lists as `k: N items`, dicts as `k: {…}`."""
    if isinstance(v, list):
        return f"{len(v)} items"
    parts = []
    for k in sorted(v):
        x = v[k]
        if isinstance(x, list):
            parts.append(f"{k}: {len(x)} items")
        elif isinstance(x, dict):
            parts.append(f"{k}: {{…}}")
        else:
            parts.append(f"{k}={x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)}")
    return clip("; ".join(parts), SUMMARY)


def _blob(reader, v, summary_limit=200) -> dict:
    """A blob view of a text, dict or list; with no reader, a same-size stand-in (used only to measure)."""
    text = v if isinstance(v, str) else json.dumps(v, indent=2, sort_keys=True, ensure_ascii=False)
    if reader is not None:
        out = dict(reader.blob_view(text))
    else:
        data = text.encode("utf-8")
        b = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        out = {"summary": "", "blob": b, "read": f"git cat-file -p {b}"}
    out["summary"] = first_line(text, summary_limit) if isinstance(v, str) else key_summary(v)
    return out


def view(reader, v):
    if len(canonical(v)) <= INLINE:
        return v
    return _blob(reader, v)


def checkpoint_view(cp, sub=None):
    """The card view of a checkpoint; `tree` only for a whole checkpoint or a `.tree` selector."""
    out = {"commit": cp["commit"], "base": cp["base"], "change": cp["change"],
           "diff": f"git diff {cp['base']} {cp['commit']} -- ':/' ':(top,exclude).zzzops/reviews'"}
    if sub in (None, "tree"):
        out["tree"] = cp["tree"]
    return out


def value_of(session, res, n, name, v):
    """The card view of one resolved input value."""
    sel = res.graph.selectors[n][name]
    if v is None:
        return None
    ot = res.graph.output_types.get(sel.node, {}).get(sel.output) if sel.kind in ("node", "deps") else None
    t = ot if not sel.path else None
    sub = sel.path[0] if ot == "checkpoint" and tuple(sel.path) in (("change",), ("tree",)) else None
    reader = session.ctx().reader

    def one(x, producer_out=None, goal=res.goal):
        if x is None:
            return None
        if sub:
            full = producer_out.get(sel.output) if isinstance(producer_out, dict) else None
            if isinstance(full, dict) and full.get(sub) == x and all(k in full for k in ("commit", "base", "change")):
                return checkpoint_view(full, sub)
            return view(reader, x)
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
    producer_out = None
    if sel.kind == "node":
        producer_out = res.cur[sel.node] if sel.node in res.cur else recorded_out(res.doc, sel.node)
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
        from engine.records import response_of
        prev["findings"] = [{"id": f["id"], "target": f["target"], "text": f["text"], "status": f["status"],
                             "response": response_of(res.doc, f["target"], f["id"]) or f.get("response")}
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


def _is_view(v) -> bool:
    """A checkpoint view, or a container holding one (never blobbed)."""
    if isinstance(v, dict):
        return ("commit" in v and "diff" in v) or any(_is_view(x) for x in v.values())
    if isinstance(v, list):
        return any(_is_view(x) for x in v)
    return False


def _summaries(obj):
    """Every blob view (or artifact view) with a summary, outside `previous`."""
    if isinstance(obj, dict):
        if "blob" in obj and "read" in obj and isinstance(obj.get("summary"), str):
            yield obj
        for k, v in obj.items():
            if k != "previous":
                yield from _summaries(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _summaries(v)


def _steps(card: dict) -> list:
    """Every shrink step in order: lossless, clip, then blob the largest inline text first."""
    steps = []
    if any(isinstance(v, dict) and "argv" in v for v in (card.get("commands") or {}).values()):
        steps.append(("drop", "commands.argv"))
    ctx_cmds = (card.get("context") or {}).get("commands")
    if ctx_cmds is not None and ctx_cmds == (card.get("commands_to_run") or {}).get("list"):
        steps.append(("point", "context.commands"))
    if any(len(v["summary"]) > SUMMARY for v in _summaries(card)):
        steps.append(("clip", "summaries"))
    blobs = []
    if isinstance(card.get("prompt"), dict) and "text" in card["prompt"]:
        blobs.append((len(card["prompt"]["text"]), ("prompt",)))
    for k, v in (card.get("instructions") or {}).items():
        if isinstance(v, dict) and "text" in v:
            blobs.append((len(v["text"]), ("instructions", k)))
    for sect in ("inputs", "context"):
        for k, v in (card.get(sect) or {}).items():
            if v is None or _is_view(v) or (isinstance(v, dict) and "blob" in v):
                continue
            if isinstance(v, (str, dict, list)):
                blobs.append((len(v) if isinstance(v, str) else len(canonical(v)), (sect, k)))
    for i, c in enumerate(card.get("corrections") or []):
        if isinstance(c.get("text"), str) and len(c["text"]) > 200 and "full" not in c:
            blobs.append((len(c["text"]), ("corrections", i)))
    blobs.sort(key=lambda b: -b[0])
    return steps + [("blob",) + path for _, path in blobs]


def _apply(card: dict, step: tuple, reader) -> dict:
    card = copy.deepcopy(card)
    kind = step[0]
    if kind == "drop":
        for v in card["commands"].values():
            if isinstance(v, dict):
                v.pop("argv", None)
    elif kind == "point":
        card["context"]["commands"] = "see commands_to_run"
    elif kind == "clip":
        for v in _summaries(card):
            v["summary"] = clip(v["summary"], SUMMARY)
    elif step[1] == "prompt":
        card["prompt"] = _blob(reader, card["prompt"]["text"], SUMMARY)
    elif step[1] == "instructions":
        card["instructions"][step[2]] = _blob(reader, card["instructions"][step[2]]["text"], SUMMARY)
    elif step[1] == "corrections":
        c = card["corrections"][step[2]]
        c["full"] = {k: v for k, v in _blob(reader, c["text"], SUMMARY).items() if k != "summary"}
        c["text"] = c["text"][:200]
    else:
        card[step[1]][step[2]] = _blob(reader, card[step[1]][step[2]], SUMMARY)
    return card


def shrink_candidates(card: dict, reader=None) -> list:
    """The shrink steps that would make this card smaller, in the order `shrink` tries them."""
    n = len(canonical(card))
    return [st for st in _steps(card) if len(canonical(_apply(card, st, None))) < n]


def shrink(card: dict, reader) -> dict:
    """While the card is over 4,096 bytes, apply the first step that makes it smaller: drop `argv`, point
    `context.commands` at `commands_to_run`, clip blob summaries to 120 characters, then blob the largest
    inline text. Checkpoint views are never blobbed, and a card never leaves larger than it entered."""
    for _ in range(100):
        n = len(canonical(card))
        if n <= CARD_LIMIT:
            return card
        for st in shrink_candidates(card):
            out = _apply(card, st, reader)
            if len(canonical(out)) < n:
                card = out
                break
        else:
            return card
    return card
