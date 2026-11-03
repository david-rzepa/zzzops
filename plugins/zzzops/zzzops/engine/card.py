"""Task card construction (SPEC §3.14, §4.20): aimed at 4,096 bytes; see `shrink`."""

from __future__ import annotations

import copy
import hashlib
import json

from engine.identity import Identity
from engine.records import checkpoint_scope

from engine.canon import canonical, iso
from engine import schemas
from engine.schemas import SHA, get_dotted, is_material, lens_label
from engine.frontier import recorded_out, resolve
from engine.render import clip, command, first_line, run_capability, scoped_git_command
from engine.schemas import SHA

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


def checkpoint_view(cp, sub=None, scope=None, exclude=None, reader=None):
    """The card view of a checkpoint; `tree` only for a whole checkpoint or a `.tree` selector."""
    out = {"commit": cp["commit"], "base": cp["base"], "change": cp["change"],
           "diff": scoped_git_command(["diff", cp["base"], cp["base"] if scope == [] else cp["commit"]],
                                      scope, exclude, quoted_root=True)}
    if sub in (None, "tree"):
        out["tree"] = cp["tree"]
    if len(scope or []) + len(exclude or []) > 12:
        out["diff"] = _blob(reader, out["diff"])
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

    producer_record = (res.doc.get("records") or {}).get(sel.node) or {}
    scope = checkpoint_scope(res.graph, sel.node, producer_record) if sel.kind == "node" else None
    preserved = res.graph.nodes.get(sel.node, {}).get("preserve") if sel.kind == "node" else None
    excluded = ((res.doc.get("records") or {}).get(preserved) or {}).get("frozen") if preserved else None

    def one(x, producer_out=None, goal=res.goal):
        if x is None:
            return None
        if sub:
            full = producer_out.get(sel.output) if isinstance(producer_out, dict) else None
            if isinstance(full, dict) and full.get(sub) == x and all(k in full for k in ("commit", "base", "change")):
                return checkpoint_view(full, sub, scope, excluded, reader)
            return view(reader, x)
        if t == "checkpoint" and isinstance(x, dict):
            return checkpoint_view(x, scope=scope, exclude=excluded, reader=reader)
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


def build(session, res, n: str, s: dict, lease: dict) -> dict:
    g, graph, doc = res.goal, res.graph, res.doc
    nd = graph.nodes[n]
    ctx = session.ctx(worker=True)
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
    cap = run_capability(s) or nd.get("capability", "bounded")
    timeout = lease["timeout"]
    every = max(1, timeout // 4)
    card = {"ok": True, "coordinator": session.state.coordinator, "goal": g, "title": doc["title"], "node": n,
            "stage": nd["stage"],
            "run": {"root": bool(nd.get("root", False)), "capability": cap,
                    "models": list(settings["routing"]["tiers"].get(cap, []))},
            "lease": {"branch": f"zzzops/lease/g{g}/{n}", "attempt": lease["attempt"], "holder": lease["holder"],
                      "timeout_minutes": timeout, "renew_every_minutes": every, "expires_at": iso(lease["expires_at"])},
            "reason": lease["card_reason"]}
    if s.get("stale_because"):
        card["stale_because"] = s["stale_because"]
        ch = changed(session, res, n, (s.get("changed_from") or {}).get("parts"), s.get("parts") or lease["parts"],
                     (s.get("changed_from") or {}).get("since"), s["stale_because"])
        if ch:
            card["changed"] = ch
    prompt_text = reader.prompt(nd["prompt"]) or ""
    card["prompt"] = {"text": prompt_text} if len(prompt_text.encode("utf-8")) <= INLINE else \
        dict(reader.blob_view(prompt_text), blob=lease.get("prompt") or reader.blob_view(prompt_text).get("blob"))
    if lease.get("prompt") and "blob" not in card["prompt"]:
        card["prompt"]["blob"] = lease["prompt"]
    ins = (session.state.policy or {}).get("instructions") or {}
    card["instructions"] = {k: ({"text": ins[k]} if len(ins[k].encode("utf-8")) <= INLINE else reader.blob_view(ins[k]))
                            for k in nd.get("instructions", []) if k in ins}
    if graph.lens_defs(n):
        card["lenses"] = lens_section(reader, graph, n, doc.get("skip") or {})
    card["inputs"], card["context"] = inputs, context
    if nd["kind"] == "agent" and nd.get("policy"):
        card["policy"] = {k: view(reader, get_dotted(settings, k)) for k in nd["policy"]}
    if nd.get("workspace"):
        cmds = []
        for name in sorted(nd.get("inputs") or {}):
            sel = graph.selectors[n][name]
            t = graph.output_types.get(sel.node, {}).get(sel.output) if sel.kind == "node" and not sel.path else None
            if t == "strings" and isinstance(vals.get(name), list):
                cmds += vals[name]
        if cmds:
            card["commands_to_run"] = {"from": "commands", "list": cmds, "note": "Run these in the workspace before you submit."}
    card["corrections"] = [correction(res, f) for f in s.get("corrections") or []]
    notes = notes_for(res, n)
    if notes:
        card["notes"] = notes
    if graph.is_filter(n):
        card["candidates"] = candidates(res, n)
    prev = previous(session, res, n, dict(s, stale_because=s.get("record_stale")))   # previous.output: record staleness
    if prev:
        card["previous"] = prev
    r = (doc.get("records") or {}).get(n)
    if r and r.get("status") == "blocked" and r.get("answer"):     # also on a stale card (G1026)
        card["answer"] = {k: r["answer"][k] for k in ("text", "quote", "decided_by") if k in r["answer"]}
    if s.get("reason") == "retry" and r and (r.get("blocked") or {}).get("instructions"):
        card["blocked_instructions"] = r["blocked"]["instructions"]
    hd = reader.human_decisions(g, graph, decision_nodes(graph, n))
    if hd is None:
        card["human_decisions"] = "unavailable"
    elif hd:
        card["human_decisions"] = hd
    I = session.snap.integration
    if res.target is not None and res.target.get("branch"):          # G1025: the goal's target tip, not dev
        I = session.target_tip(res.target["branch"]) or I
        card["target"] = {"branch": res.target["branch"], "kind": res.target["kind"], "commit": I}
    card["read_dev"] = {"commit": I, "show": f"git show {I}:<path>", "grep": f"git grep <pattern> {I}",
                        "mirror": session.mirror_path()}
    card["workspace"] = lease.get("workspace")
    card["output_schema"] = output_schema(graph, n, dict(s, corrections=card["corrections"]),
                                          follows=schemas.follows_required(settings))
    arts = graph.artifact_outputs(n)
    if arts:
        card["artifact"] = {"output": arts[0], "path": f".zzzops/reviews/{g}/{n}.md"}
    holder, N = lease["holder"], str(lease["attempt"])
    card["commands"] = {
        "submit": command(ctx, ["submit", str(g), n, "--attempt", N, "--as", holder, "--output", "<F>"]
                          + (["--artifact", "<A>"] if arts else [])),
        "blocked": command(ctx, ["submit", str(g), n, "--attempt", N, "--as", holder, "--blocked", "<F>"]),
        "renew": dict(command(ctx, ["renew", str(g), n, "--attempt", N]),
                      when=f"every {every} minutes (timeout {timeout}); renew first after a pause"),
        "abandon": command(ctx, ["abandon", str(g), n, "--attempt", N])}
    return shrink(card, reader)


def decision_nodes(graph, n) -> list:
    """The nodes whose human decisions a card shows: its own, or, on a review or filter card, its subject's and the
    subject's ancestors' (G1026)."""
    subj = graph.subject(n) or graph.filter_subject(n)
    return [n] if not subj else [subj] + sorted(graph.ancestors(subj))


def correction(res, f) -> dict:
    """One card correction: `stale_review` when its carrier is stale (a carried finding), `follows`/`follows_text`
    when it narrows an earlier finding (G1028)."""
    c = _carrier(res, f)
    out = {"id": f["id"], "from": c, "text": f["text"], "rounds": f["rounds"], "upheld": f["upheld"]}
    if c in res.stale:
        out["stale_review"] = True
    if f.get("follows"):
        out["follows"] = f["follows"]
        old = finding_by_id(res.doc, f["follows"])
        if old is not None:
            out["follows_text"] = clip(old["text"], 120)
    return out


def finding_by_id(doc, fid):
    for r in (doc.get("records") or {}).values():
        for x in r.get("findings") or []:
            if x["id"] == fid:
                return x
    return None


def lens_section(reader, graph, n, skip) -> dict:
    """A multi-lens reviewer's checklist (G1022): the lenses it applies, in order; those the goal skipped, with
    reasons; and the applied lenses' prompt texts, concatenated (a blob view when long)."""
    apply = graph.applied_lenses(n, skip)
    defs = graph.lens_defs(n)
    text = "\n\n".join((reader.prompt(defs[x]["prompt"]) or "").strip() for x in apply) + "\n"
    return {"apply": apply, "skipped": graph.skipped_lenses(n, skip),
            "text": {"text": text} if len(text.encode("utf-8")) <= INLINE else reader.blob_view(text)}


def notes_for(res, n) -> list:
    """The filter-judged notes on target n: optional to act on, never corrections."""
    return [{"id": f["id"], "lens": lens_label(c, f), "text": f["text"], "impact": f.get("impact"), "reason": reason}
            for c, f, reason in sorted(res.notes.get(n, []), key=lambda x: x[1]["id"])]


def candidates(res, flt) -> list:
    """A filter's card: every open finding on its lenses' latest (non-skipped) records."""
    from engine.records import response_of
    out = []
    skip = res.doc.get("skip") or {}
    records = res.doc.get("records") or {}
    for lens in res.graph.reviewers(flt):
        if lens in skip:
            continue
        for f in (records.get(lens) or {}).get("findings") or []:
            if f["status"] == "open":
                out.append({"id": f["id"], "lens": lens_label(lens, f), "target": f["target"], "text": f["text"],
                            "impact": f.get("impact"), "material": is_material(f),
                            "response": response_of(res.doc, f["target"], f["id"]) or f.get("response")})
    return sorted(out, key=lambda c: c["id"])


def _carrier(res, f):
    for c, x in sum((res.live.get(t, []) for t in res.live), []):
        if x is f:
            return c
    return f["id"].split(":")[0]


def changed(session, res, n, old_parts, new_parts, since, keys) -> dict:
    """One cheap, local pointer per stale key that has one: a goal-field input gets a goal.json diff since `since`,
    an artifact input a blob diff. Never fetches."""
    out = {}
    graph = res.graph
    old_in = (old_parts or {}).get("inputs") or {}
    new_in = (new_parts or {}).get("inputs") or {}
    tip = session.snap.goals.get(res.goal)
    for key in keys:
        if not key.startswith("inputs."):
            continue
        name = key[len("inputs."):]
        sel = graph.selectors[n].get(name)
        if sel is None:
            continue
        if sel.kind == "goal":
            if not tip or since is None:
                continue
            old = session.git.out("rev-list", "-1", "--first-parent", f"--before={since}", tip).strip()
            if old and old != tip:
                out[key] = {"diff": f"git diff {old} {tip} -- goal.json"}
        elif graph.selector_type(sel) == "artifact":
            a, b = _blob_of(old_in.get(name)), _blob_of(new_in.get(name))
            if not (a and b):
                continue
            out[key] = {"diff": f"git diff {a} {b}"} if session.git.exists(a) else {"note": "previous version not available"}
    return out


def _blob_of(part):
    if not isinstance(part, str) or ":blob:" not in part:
        return None
    sha = part.rsplit(":blob:", 1)[1]
    return sha if SHA.match(sha) else None


def finding_effect(graph, n) -> str:
    """What a finding from this phase does (one place for G1000's filtered-review branch)."""
    if graph.is_review(n):
        return "Each open finding reopens its target: it re-runs and must answer it in responses."
    return "it reopens that ancestor; this phase re-runs if that ancestor's output changes."


def new_finding_hint(graph, n, follows: bool = False) -> str:
    """The shape of a new review finding; a multi-lens reviewer's names every declared lens (G1022); `follows`
    is offered only when the policy requires it (G1028)."""
    lenses = " | ".join(f'"{x}"' for x in graph.lens_defs(n))
    tail = ", \"follows\"?: <id>" if follows else ""
    return (f'{{"target"?: <node>, "lens": {lenses}, "text": …{tail}}}' if lenses
            else f'{{"target"?: <node>, "text": …{tail}}}')


def output_schema(graph, n, s, follows: bool = False) -> dict:
    """`follows`: the policy requires the finding key `follows` (only then is it offered, G1028)."""
    out = {}
    if graph.is_review(n):
        out["decision"] = ("approved | changes_requested (changes_requested only with a material finding open; "
                           "approve with notes)" if graph.filter_of(n)
                           else "approved | changes_requested (approved only with no finding open)")
        out["summary"] = "text: your verdict"
        if follows:
            out["findings"] = ("[{\"id\": <id>, \"status\": \"open\"|\"resolved\"} for every finding in previous.findings, "
                               f"{new_finding_hint(graph, n, True)} for new ones]. Ids in "
                               "previous.resolved need no status. When a prior finding is partly fixed, resolve it and "
                               "raise what remains with \"follows\": <its id>. " + finding_effect(graph, n))
        else:
            out["findings"] = ("[{\"id\": <id>, \"status\": \"open\"|\"resolved\"} for every finding in previous.findings, "
                               f"{new_finding_hint(graph, n)} for new ones]. Ids in previous.resolved need no "
                               "status. " + finding_effect(graph, n))
    else:
        for k, t in graph.output_types[n].items():
            if t == "checkpoint":
                out[k] = ("checkpoint (optional): omit the key to default to the work branch's HEAD. "
                          "Override with {\"commit\": \"<full 40-hex sha>\"}; no refs or short shas.")
            elif t == "artifact":
                out[k] = "artifact: write it to a local file and pass that file with --artifact; artifact.path is where submit stores it."
            else:
                out[k] = t
        out["findings"] = "optional: [{\"target\": <ancestor node>, \"text\": …}]; " + finding_effect(graph, n)
    if s.get("corrections"):
        out["responses"] = "required for: " + ", ".join(f["id"] for f in s["corrections"])
        if any(f.get("stale_review") for f in s["corrections"]):
            out["responses"] += (". A stale_review finding came from a review whose inputs have since changed: answer "
                                 "it fixed: if your output handles it, or disputed: with the reason if the change made "
                                 "it moot.")
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
        mine = [f for f in r.get("findings") or [] if f["target"] != n]
        prev["findings"] = [dict({"id": f["id"], "target": f["target"], "text": f["text"], "status": f["status"],
                                  "response": response_of(res.doc, f["target"], f["id"]) or f.get("response")},
                                 **({"follows": f["follows"]} if f.get("follows") else {}))
                            for f in mine if f["status"] == "open"]
        closed = [{"id": f["id"], "status": f["status"], "text": clip(f["text"], 120)}
                  for f in mine if f["status"] != "open"]
        if closed:
            prev["resolved"] = closed
        for k, old in (r.get("reviewed") or {}).items():
            cur = (sr.get("output") or {}).get(k)
            if "blob" in old:                                   # an artifact: what changed since the last review
                if not isinstance(cur, dict) or cur.get("blob") == old["blob"]:
                    continue
                a, b = old["blob"], cur.get("blob")
                if not (isinstance(a, str) and SHA.match(a) and isinstance(b, str) and SHA.match(b)):
                    prev["note"] = "previous version not available; review in full"
                    continue
                if not session.git.exists(a):
                    session.fetch_work_of(res.goal)
                if session.git.exists(a):
                    prev["changed"] = f"git diff {a} {b}"
                else:
                    prev["note"] = "previous version not available; review in full"
                continue
            if not isinstance(cur, dict) or (cur.get("change") == old.get("change") and cur.get("base") == old.get("base")):
                continue
            if session.git.exists(old["commit"]):
                scope = checkpoint_scope(res.graph, subj, sr)
                producer = res.graph.nodes[subj].get("preserve")
                excluded = (((res.doc.get("records") or {}).get(producer) or {}).get("frozen") or []) if producer else []
                if old["base"] == cur["base"]:
                    prev["interdiff"] = scoped_git_command(["diff", old["commit"], cur["commit"]], scope, excluded)
                else:
                    syncs = Identity(session.git).sync_merges(old["commit"], cur["commit"])
                    if syncs:
                        prev["interdiff"] = scoped_git_command(
                            ["log", "-p", "--first-parent", "--no-merges", f"{old['commit']}..{cur['commit']}"], scope, excluded)
                        prev["syncs"] = [f"git show --remerge-diff {c}" for c in syncs]
                    else:
                        prev["interdiff"] = scoped_git_command(
                            ["range-diff", f"{old['base']}..{old['commit']}", f"{cur['base']}..{cur['commit']}"], scope, excluded)
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
    for sect in ("inputs", "context", "policy"):
        for k, v in (card.get(sect) or {}).items():
            if v is None or _is_view(v) or (isinstance(v, dict) and "blob" in v):
                continue
            if isinstance(v, (str, dict, list)):
                blobs.append((len(v) if isinstance(v, str) else len(canonical(v)), (sect, k)))
    for i, c in enumerate(card.get("corrections") or []):
        if isinstance(c.get("text"), str) and len(c["text"]) > 200 and "full" not in c:
            blobs.append((len(c["text"]), ("corrections", i)))
    if isinstance(card.get("human_decisions"), list):
        blobs.append((len(canonical(card["human_decisions"])), ("human_decisions",)))
    for sect in ("candidates", "notes"):
        for i, c in enumerate(card.get(sect) or []):
            size = len(c.get("text") or "") + len(c.get("impact") or "")
            if size > 200 and "full" not in c:
                blobs.append((size, (sect, i)))
    blobs.sort(key=lambda b: -b[0])
    steps += [("blob",) + path for _, path in blobs]
    if any(len(v["summary"]) > 80 for v in _summaries(card)):
        steps.append(("clip", "summaries", 80))
    return steps


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
            v["summary"] = clip(v["summary"], step[2] if len(step) > 2 else SUMMARY)
    elif step[1] == "prompt":
        card["prompt"] = _blob(reader, card["prompt"]["text"], SUMMARY)
    elif step[1] == "human_decisions":
        card["human_decisions"] = _blob(reader, card["human_decisions"], SUMMARY)
    elif step[1] == "instructions":
        card["instructions"][step[2]] = _blob(reader, card["instructions"][step[2]]["text"], SUMMARY)
    elif step[1] == "corrections":
        c = card["corrections"][step[2]]
        c["full"] = {k: v for k, v in _blob(reader, c["text"], SUMMARY).items() if k != "summary"}
        c["text"] = c["text"][:200]
    elif step[1] in ("candidates", "notes"):
        c = card[step[1]][step[2]]
        full = json.dumps({"text": c.get("text"), "impact": c.get("impact")}, indent=2)
        c["full"] = {k: v for k, v in _blob(reader, full, SUMMARY).items() if k != "summary"}
        c["text"] = (c.get("text") or "")[:120]
        if c.get("impact"):
            c["impact"] = c["impact"][:80]
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
    inline text, then clip remaining blob previews to 80 characters. Checkpoint views are never blobbed,
    and a card never leaves larger than it entered."""
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
