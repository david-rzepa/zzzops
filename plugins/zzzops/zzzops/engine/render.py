"""Rendering of `next` (SPEC §3.15, §4.11), human items and printed commands (§1.6).

Everything Git-dependent (prompt texts, diffstats, blob views) comes through `Reader`, so rendering is a function of
its arguments."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field

from engine.canon import canonical, iso, parse_iso
from engine.frontier import PRI, GoalResult, Portfolio, order_key

NEXT_LIMIT = 8192
LABEL = "<LABEL>"
FILE = "<F>"


class Reader:
    """Read access the renderers need; the CLI implements it over Git, tests with dicts."""

    def prompt(self, name: str) -> str | None:
        return None

    def diffstat(self, base: str, commit: str) -> str | None:
        return None

    def blob_view(self, text: str) -> dict:
        return {"summary": first_line(text, 200)}

    def artifact_url(self, commit: str, path: str) -> str | None:
        return None


@dataclass
class Ctx:
    prefix: str
    now: int
    settings: dict
    coordinator: dict
    reader: Reader = field(default_factory=Reader)
    goal_commits: dict = field(default_factory=dict)     # id -> goal tip commit (for edit --base)
    goal_dates: dict = field(default_factory=dict)       # id -> goal tip committer date (seconds)


def command(ctx: Ctx, argv: list) -> dict:
    return {"argv": list(argv), "command": ctx.prefix + " " + " ".join(shlex.quote(a) if a not in (LABEL, FILE) else a
                                                                      for a in argv)}


def first_line(text: str, limit: int) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:limit]
    return ""


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


# --------------------------------------------------------------------------------------------- edit options


def edit_option(ctx: Ctx, g: int, label: str, sets: dict) -> dict:
    return {"label": label, "command": command(ctx, ["edit", str(g), "--file", FILE, "--base", ctx.goal_commits.get(g, "<C>")]),
            "file": {"set": sets}}


def cancel_option(ctx: Ctx, g: int) -> dict:
    return edit_option(ctx, g, "cancel the goal",
                       {"state": "closed", "closed.reason": "cancelled", "closed.note": "<why>"})


# --------------------------------------------------------------------------------------------- actions


def capability(res: GoalResult, n: str, state: dict) -> str | None:
    nd = res.graph.nodes[n]
    if state.get("reason") == "retry":
        return "reasoning"
    if state.get("stale_because") == ["inputs.base"]:
        return "routine"
    return nd.get("capability", "bounded") if nd["kind"] == "agent" else None


def action(ctx: Ctx, p: Portfolio, res: GoalResult, n: str) -> dict:
    s = res.st[n]
    nd = res.graph.nodes[n]
    g = res.goal
    reclaim = s["name"] == "reclaimable"
    a = {"goal": g, "node": n, "title": f"G{g} {res.doc['title']}", "kind": nd["kind"], "stage": nd["stage"],
         "root": bool(nd.get("root", False)), "capability": capability(res, n, s),
         "reason": "reclaim" if reclaim else s["reason"]}
    if s.get("stale_because"):
        a["stale_because"] = s["stale_because"]
    if s.get("corrections"):
        a["corrections"] = len(s["corrections"])
    if s.get("reason") == "retry" and s.get("instructions"):
        a["instructions"] = s["instructions"]
    argv = ["start", str(g), n, "--as", LABEL] + (["--reclaim"] if reclaim else [])
    if reclaim and p.mass_expiry:
        a["requires_force"] = True
        a["note"] = "possible clock problem; ask the human before --force"
    a["command"] = command(ctx, argv)
    return a


# --------------------------------------------------------------------------------------------- human items


def value_view(v, limit=400) -> str:
    text = v if isinstance(v, str) else json.dumps(v, sort_keys=True, ensure_ascii=False)
    return clip(text, limit)


def substitute(question: str, res: GoalResult, vals: dict) -> str:
    out = question.replace("{id}", str(res.goal)).replace("{title}", res.doc["title"])
    for k, v in vals.items():
        if isinstance(v, (str, int)) and not isinstance(v, bool):
            out = out.replace("{" + k + "}", str(v))
    return out


def prompt_question(ctx: Ctx, res: GoalResult, n: str) -> str:
    text = ctx.reader.prompt(res.graph.nodes[n].get("prompt", "")) or ""
    line = first_line(text, 1000).lstrip("#").strip()
    return line or f"G{res.goal} {n}?"


def approve_context(ctx: Ctx, res: GoalResult, n: str, vals: dict) -> list:
    out = []
    nd = res.graph.nodes[n]
    for name in sorted(nd.get("inputs") or {}):
        sel = res.graph.selectors[n][name]
        if name not in vals:
            continue
        v = vals[name]
        t = res.graph.output_types.get(sel.node, {}).get(sel.output) if sel.kind == "node" else None
        entry = {"label": sel.text}
        if t == "checkpoint" and isinstance(v, dict) and not sel.path:
            entry.update(checkpoint_view(ctx, v))
        elif t == "checkpoint" and sel.path and sel.path[0] in ("change", "tree"):
            cp = res.cur.get(sel.node, {}).get(sel.output)
            entry.update(checkpoint_view(ctx, cp) if cp else {"summary": value_view(v)})
        elif t == "artifact" and isinstance(v, dict) and not sel.path:
            entry.update({"path": v.get("path"), "blob": v.get("blob"), "read": f"git cat-file -p {v.get('blob')}"})
            url = ctx.reader.artifact_url(v.get("commit"), v.get("path")) if v.get("commit") else None
            if url:
                entry["url"] = url
        else:
            entry["summary"] = value_view(v)
        out.append(entry)
    return out


def checkpoint_view(ctx: Ctx, cp: dict) -> dict:
    diff = f"git diff {cp['base']} {cp['commit']} -- ':/' ':(top,exclude).zzzops/reviews'"
    view = {"diff": diff}
    stat = ctx.reader.diffstat(cp["base"], cp["commit"])
    if stat:
        view["diffstat"] = stat
    return view


def facts(res: GoalResult) -> str:
    parts = []
    records = res.doc.get("records") or {}
    for n in res.graph.topo:
        nd = res.graph.nodes[n]
        if nd["kind"] == "agent" and res.graph.is_review(n) and n in records:
            k = records[n]["attempt"]
            parts.append(f"{n}: {k} review{'s' if k != 1 else ''}")
    waived = [f["id"] for r in records.values() for f in r.get("findings") or [] if f["status"] == "waived"]
    disputed = [f["id"] for r in records.values() for f in r.get("findings") or []
                if f["status"] == "open" and (f.get("response") or "").startswith("disputed: ")]
    parts.append("waived: " + (", ".join(sorted(waived)) or "none"))
    parts.append("disputed: " + (", ".join(sorted(disputed)) or "none"))
    ci = "not run yet"
    for n in res.graph.topo:
        if res.graph.nodes[n].get("op") == "git.integrate" and n in records and records[n]["status"] == "done":
            c = (records[n]["output"] or {}).get("ci") or {}
            if c.get("stacked"):
                ci = "stacked"
            elif c.get("failed"):
                ci = "failed: " + ", ".join(c["failed"])
            elif records[n]["ok"]:
                ci = "passed"
    parts.append("CI: " + ci)
    return "; ".join(parts)


def pr_and_stack(res: GoalResult) -> dict:
    out = {}
    records = res.doc.get("records") or {}
    for n in res.graph.topo:
        nd = res.graph.nodes[n]
        r = records.get(n)
        if nd.get("op") == "git.integrate" and r and r["status"] == "done" and (r["output"] or {}).get("pr"):
            pr = r["output"]["pr"]
            out["pr"] = {"number": pr.get("number"), "url": pr.get("url")}
        if nd.get("op") == "git.base" and r and r["status"] == "done" and (r["output"] or {}).get("stack"):
            stack = r["output"]["stack"]
            out["stack"] = "stacked on " + ", ".join(f"G{x['goal']} (PR #{x.get('pr')}, not merged yet)" for x in stack)
    return out


def since_approve(res: GoalResult, n: str) -> int | None:
    records = res.doc.get("records") or {}
    times = []
    for p in res.graph.producers(n):
        r = records.get(p)
        if r:
            times.append(parse_iso(r["finished_at"]))
    return max(times) if times else None


def approve_item(ctx: Ctx, res: GoalResult, n: str, full: bool) -> dict:
    from engine.frontier import resolve
    s = res.st[n]
    g = res.goal
    vals, _ = resolve(res.graph, res.doc, n, lambda p: res.cur[p] if p in res.cur else None, {})
    vals = {k: v for k, v in vals.items()}
    q = substitute(prompt_question(ctx, res, n), res, vals)
    since = since_approve(res, n)
    item = {"goal": g, "node": n, "stage": res.graph.nodes[n]["stage"], "kind": "approve", "question": q,
            "since": iso(since) if since is not None else None}
    if not full:
        return item
    item["context"] = approve_context(ctx, res, n, vals)
    item.update(pr_and_stack(res))
    item["facts"] = facts(res)
    r = (res.doc.get("records") or {}).get(n)
    if r and r["status"] == "done":
        prev = {"decided_at": (r["output"] or {}).get("decided_at"), "quote": (r["output"] or {}).get("quote")}
        if s["ready"].get("stale_because"):
            prev["stale_because"] = s["ready"]["stale_because"]
        item["previous"] = prev
    fp = s["fp"]
    argv = ["answer", str(g), n, "--fp", fp, "--file", FILE]
    item["options"] = [{"label": "approve", "command": command(ctx, argv)},
                       {"label": "request changes", "command": command(ctx, argv)},
                       cancel_option(ctx, g)]
    item["fp"] = fp
    item["answer_template"] = {"decision": "approved", "summary": "<what was approved, in your words>",
                               "quote": "<the human's words, verbatim>", "decided_by": "<name>"}
    return item


def blocked_item(ctx: Ctx, res: GoalResult, n: str, full: bool) -> dict:
    s = res.st[n]
    b = s["blocked"]
    g = res.goal
    item = {"goal": g, "node": n, "stage": res.graph.nodes[n]["stage"], "kind": "blocked", "question": b["question"],
            "since": s["record"]["finished_at"]}
    if not full:
        return item
    opts = [{"label": o} for o in b.get("options", [])]
    for label, argv in (b.get("commands") or {}).items():
        opts.append({"label": label, "command": command(ctx, argv)})
    opts.append({"label": "answer", "command": command(ctx, ["answer", str(g), n, "--fp", s["fp"], "--file", FILE])})
    item["options"] = opts
    if b.get("recommendation"):
        item["recommendation"] = b["recommendation"]
    item["fp"] = s["fp"]
    item["answer_template"] = {"text": "<the answer>", "quote": "<the human's words, verbatim>", "decided_by": "<name>"}
    return item


def dispute_item(ctx: Ctx, res: GoalResult, n: str, full: bool) -> dict:
    s = res.st[n]
    g = res.goal
    carrier, f = s["escalated"][0]
    records = res.doc.get("records") or {}
    cr = records[carrier]
    q = (f"`{carrier}` and `{n}` disagree on {f['id']}: '{clip(f['text'], 300)}'. `{n}` answered: "
         f"'{clip(f.get('response') or '', 300)}'. Uphold the finding (the target must fix it) or waive it?")
    item = {"goal": g, "node": carrier, "stage": res.graph.nodes[carrier]["stage"], "kind": "dispute", "question": q,
            "since": cr["finished_at"]}
    if not full:
        return item
    argv = ["answer", str(g), carrier, "--fp", cr["input_fp"], "--file", FILE]
    if res.graph.nodes[carrier]["kind"] == "op":
        opts = [{"label": "uphold", "command": command(ctx, argv)},
                {"label": "re-observe", "command": command(ctx, ["reopen", str(g), carrier, "--note", "<why>"])}]
        if carrier not in res.graph.terminal:
            opts.append(edit_option(ctx, g, f"skip {carrier}", {f"skip.{carrier}": "<reason>"}))
        opts.append(cancel_option(ctx, g))
    else:
        opts = [{"label": "uphold", "command": command(ctx, argv)}, {"label": "waive", "command": command(ctx, argv)},
                cancel_option(ctx, g)]
    item["options"] = opts
    item["fp"] = cr["input_fp"]
    item["answer_template"] = {"finding": f["id"], "decision": "uphold", "quote": "<the human's words, verbatim>",
                               "decided_by": "<name>"}
    return item


def crash_item(ctx: Ctx, res: GoalResult, n: str, full: bool) -> dict:
    s = res.st[n]
    g = res.goal
    cap = s["cap"]
    if cap == "lease":
        L = s["lease"]
        q = f"G{g} {n} has started {L.attempt} times without finishing. Try once more, skip it, or cancel?"
        since = iso(L.last_active)
        retry = ["start", str(g), n, "--as", LABEL, "--reclaim", "--force"]
    elif cap == "repeat":
        q = f"G{g} {n} was blocked three times in a row waiting for an agent: {s['blocked']['reason']}. Try once more, skip it, or cancel?"
        since = None
        retry = ["start", str(g), n, "--as", LABEL, "--force"]
    else:
        ids = sorted(x["id"] for x in s["record"].get("findings") or [] if x["status"] == "open" and x.get("repeats", 1) >= 3)
        q = f"G{g} {n} raised {', '.join(ids)} three times with unchanged inputs. Try once more, skip it, or cancel?"
        since = None
        retry = ["start", str(g), n, "--as", LABEL, "--force"]
    record = (res.doc.get("records") or {}).get(n)
    if since is None and record:
        since = record["finished_at"]
    item = {"goal": g, "node": n, "stage": res.graph.nodes[n]["stage"], "kind": "crash_loop", "question": q, "since": since}
    if not full:
        return item
    one_more = {"label": "one more try", "command": command(ctx, retry)}
    if res.graph.nodes[n]["kind"] == "agent" and res.budget.get("over"):
        raise_opt = budget_raise(ctx, res)
        one_more = {"label": "one more try (raise the budget first)", "command": raise_opt["command"],
                    "file": raise_opt["file"], "then": command(ctx, retry)}
    opts = [one_more]
    if n not in res.graph.terminal:
        opts.append(edit_option(ctx, g, f"skip {n}", {f"skip.{n}": "<reason>"}))
    opts.append(cancel_option(ctx, g))
    item["options"] = opts
    return item


def budget_raise(ctx: Ctx, res: GoalResult) -> dict:
    b = res.budget
    return edit_option(ctx, res.goal, "raise the budget", {"budget": b["used"] + 3 * b["agents"]})


def budget_item(ctx: Ctx, res: GoalResult, node: str, full: bool) -> dict:
    b = res.budget
    g = res.goal
    per = ", ".join(f"{k} {v}" for k, v in b["per_node"].items()) or "none"
    q = f"G{g} has used {b['used']} correction runs (limit {b['limit']}): {per}. Continue, hold, or cancel?"
    item = {"goal": g, "node": node, "stage": res.graph.nodes[node]["stage"], "kind": "budget", "question": q,
            "since": iso(ctx.goal_dates[g]) if g in ctx.goal_dates else None}
    if full:
        item["options"] = [budget_raise(ctx, res), edit_option(ctx, g, "hold the goal", {"state": "held"}),
                           cancel_option(ctx, g)]
    return item


def stuck_item(ctx: Ctx, res: GoalResult, full: bool) -> dict:
    g = res.goal
    x = res.stuck["node"]
    first = res.stuck["missing"][0]
    reasons = "; ".join(describe_miss(m) for m in res.stuck["missing"])
    q = f"G{g} is stuck at {x}: {reasons}."
    item = {"goal": g, "node": x, "stage": res.graph.nodes[x]["stage"], "kind": "stuck", "question": q,
            "since": iso(ctx.goal_dates[g]) if g in ctx.goal_dates else None}
    if not full:
        return item
    opts = []
    reason = first["reason"]
    if reason == "skipped":
        p = first["node"]
        opts.append(edit_option(ctx, g, f"unskip {p}", {f"skip.{p}": None}))
        if x not in res.graph.terminal:
            opts.append(edit_option(ctx, g, f"skip {x} too", {f"skip.{x}": "<reason>"}))
    elif reason in ("output_absent", "no_record"):
        opts.append({"label": f"reopen {first['node']}",
                     "command": command(ctx, ["reopen", str(g), first["node"], "--note", "<why>"])})
    elif reason == "dependency":
        d = first["dep"]
        deps = [i for i in res.doc.get("depends_on") or [] if i != d]
        opts.append(edit_option(ctx, g, f"drop G{d}", {"depends_on": deps}))
        opts.append(edit_option(ctx, g, f"retarget G{d}", {"depends_on": deps + ["<replacement id>"]}))
        if first.get("state") == "stuck":
            opts.append({"label": f"answer G{d}'s stuck item first"})
    else:
        p = first["node"] if first["node"] in res.graph.nodes else x
        opts.append({"label": f"reopen {p}", "command": command(ctx, ["reopen", str(g), p, "--note", "<why>"])})
    opts.append(cancel_option(ctx, g))
    item["options"] = opts
    return item


def close_item(ctx: Ctx, res: GoalResult, full: bool) -> dict:
    g = res.goal
    node = res.graph.terminal[0]
    item = {"goal": g, "node": node, "stage": res.graph.nodes[node]["stage"], "kind": "close",
            "question": f"Every terminal node of G{g} is current. Close it as done?",
            "since": iso(ctx.goal_dates[g]) if g in ctx.goal_dates else None}
    if full:
        item["options"] = [edit_option(ctx, g, "close as done", {"state": "closed", "closed.reason": "done",
                                                                "closed.note": "every terminal node is current"})]
    return item


def describe_miss(m: dict) -> str:
    if m["reason"] == "dependency":
        return f"G{m['dep']} {m['node']} ({m['state']})"
    return f"{m['node']} {m['reason'].replace('_', ' ')}"


def human_items(ctx: Ctx, res: GoalResult, full: bool) -> list:
    """(sort key, item) pairs for one open goal."""
    out = []
    settings = ctx.settings
    for n in res.graph.topo:
        s = res.st[n]
        if s["name"] != "needs_human":
            continue
        kind = s["kind"]
        if kind == "approve":
            item = approve_item(ctx, res, n, full)
        elif kind == "blocked":
            item = blocked_item(ctx, res, n, full)
        elif kind == "dispute":
            item = dispute_item(ctx, res, n, full)
        else:
            item = crash_item(ctx, res, n, full)
        if not full:
            item = compact(ctx, item)
        out.append((order_key(settings, res.doc, res.graph, item["node"]), item))
    if res.stuck:
        it = stuck_item(ctx, res, full)
        out.append((order_key(settings, res.doc, res.graph, it["node"]), it if full else compact(ctx, it)))
    if res.budget.get("over"):
        node = next((n for n in res.graph.topo if res.graph.nodes[n]["kind"] == "agent"
                     and res.st[n]["name"] in ("ready", "reclaimable")),
                    next(n for n in res.graph.topo if res.graph.nodes[n]["kind"] == "agent"))
        it = budget_item(ctx, res, node, full)
        out.append((order_key(settings, res.doc, res.graph, node), it if full else compact(ctx, it)))
    if res.close:
        it = close_item(ctx, res, full)
        out.append((order_key(settings, res.doc, res.graph, it["node"]), it if full else compact(ctx, it)))
    return out


def compact(ctx: Ctx, item: dict) -> dict:
    return {"goal": item["goal"], "node": item["node"], "kind": item["kind"], "question": item["question"],
            "since": item.get("since"), "expand": command(ctx, ["next", "--goal", str(item["goal"])])}


# --------------------------------------------------------------------------------------------- next


def goal_actions(ctx: Ctx, p: Portfolio, res: GoalResult) -> tuple:
    """(actions as (key, action), waiting entries) for one goal."""
    acts, waiting = [], []
    for n in res.graph.topo:
        s = res.st[n]
        nd = res.graph.nodes[n]
        if s["name"] not in ("ready", "reclaimable") or nd["kind"] == "human":
            continue
        if nd["kind"] == "agent" and res.budget.get("over"):
            continue
        if res.busy and nd.get("workspace") and n != res.busy:
            waiting.append({"goal": res.goal, "node": n, "until": f"{res.busy} finishes", "reason": f"workspace busy: {res.busy}"})
            continue
        acts.append((order_key(ctx.settings, res.doc, res.graph, n), action(ctx, p, res, n)))
    return acts, waiting


def goal_waiting(res: GoalResult) -> list:
    out = []
    for n in res.graph.topo:
        s = res.st[n]
        if s["name"] == "waiting":
            out.append({"goal": res.goal, "node": n, "until": s["until"], "reason": s["reason"]})
    for n in res.graph.topo:
        s = res.st[n]
        if s["name"] != "blocked":
            continue
        named = [m for m in s["missing"] if m["reason"] == "dependency" and m.get("wait")]
        if named:
            m = named[0]
            if m["state"] == "newer":
                until = "engine upgrade"
            elif m["state"] == "held":
                until = f"G{m['dep']} held"
            else:
                until = f"G{m['dep']} {m['node']}"
            out.append({"goal": res.goal, "node": n, "until": until, "reason": f"dependency {m['state']}"})
            break
    return out


def goal_running(res: GoalResult) -> list:
    out = []
    for n in res.graph.topo:
        s = res.st[n]
        if s["name"] == "running":
            L = s["lease"]
            out.append({"goal": res.goal, "node": n, "holder": L.holder, "attempt": L.attempt,
                        "expires_at": iso(L.expires_at)})
    return out


def render_next(ctx: Ctx, p: Portfolio, scope: list | None = None, all_: bool = False, blockers: list | None = None,
                warnings: list | None = None, paused: bool = False) -> dict:
    """`blockers`: [{"kind", "message"}]; a message may contain "{n}" (the number of paused actions).
    `paused`: a blocker pauses every action."""
    blockers = [dict(b) for b in (blockers or [])]
    warnings = list(warnings or [])
    full = bool(scope)
    in_scope = [g for g in sorted(p.goals) if (scope is None or g in scope)]
    acts, items, waiting, running = [], [], [], []
    out_acts = out_items = 0
    wake = []
    for g in sorted(p.goals):
        res = p.goals[g]
        a, w = goal_actions(ctx, p, res) if res.doc["state"] == "open" else ([], [])
        h = human_items(ctx, res, full) if res.doc["state"] == "open" else []
        if g not in in_scope:
            out_acts += len(a)
            out_items += len(h)
            continue
        acts += a
        items += h
        waiting += goal_waiting(res) + w
        running += goal_running(res)
        for n in res.graph.topo:
            s = res.st[n]
            if s["name"] == "waiting" and s.get("retry_after"):
                wake.append(parse_iso(s["retry_after"]))
            if s["name"] == "running":
                wake.append(s["lease"].expires_at)
    acts.sort(key=lambda x: x[0])
    items.sort(key=lambda x: x[0])
    actions = [a for _, a in acts]
    needs = [i for _, i in items]
    if paused:
        n = len(actions)
        actions = []
        for b in blockers:
            b["message"] = b["message"].replace("{n}", str(n))
    out = {"ok": True, "coordinator": ctx.coordinator, "now": iso(ctx.now),
           "wake_at": iso(min(wake)) if wake else None,
           "scope": {"goals": list(scope)} if scope else {"goals": "all"},
           "blockers": blockers, "actions": actions, "needs_human": needs, "waiting": waiting, "running": running,
           "capacity": {"live": p.live_agents, "max": ctx.settings["parallelism"]["max_workers"]},
           "warnings": warnings}
    if scope:
        out["also_pending"] = {"human": out_items, "actions": 0 if paused else out_acts}
    if all_:
        out["goals"] = [goal_summary(res, ctx) for g, res in sorted(p.goals.items())]
        return out
    dropped = {"actions": 0, "needs_human": 0}
    while len(canonical(out)) > NEXT_LIMIT and (out["actions"] or out["needs_human"]):
        key = "actions" if len(out["actions"]) >= len(out["needs_human"]) else "needs_human"
        out[key] = out[key][:-1]
        dropped[key] += 1
        out["truncated"] = dict(dropped, hint="next --all")
    return out


def goal_summary(res: GoalResult, ctx: Ctx) -> dict:
    first = next((n for n in res.graph.topo if res.st[n]["name"] not in ("current", "skipped")), None)
    stage = res.graph.nodes[first]["stage"] if first else "done"
    return {"id": res.goal, "title": res.doc["title"], "state": res.doc["state"], "stage": stage,
            "first_unfinished": first,
            "last_change": iso(ctx.goal_dates[res.goal]) if res.goal in ctx.goal_dates else None}


def state_string(s: dict) -> str:
    """The impact-preview form of a state (SPEC §3.16): name plus its reason."""
    name = s["name"]
    if name == "ready":
        sb = s.get("stale_because")
        return f"ready ({s['reason']}: {', '.join(sb)})" if sb else f"ready ({s['reason']})"
    if name == "blocked":
        return "blocked (" + ", ".join(describe_miss(m) for m in s["missing"]) + ")"
    if name == "needs_human":
        return f"needs_human ({s['kind']})"
    if name == "waiting":
        return f"waiting ({s['reason']})"
    if name == "skipped":
        return "skipped"
    return name
