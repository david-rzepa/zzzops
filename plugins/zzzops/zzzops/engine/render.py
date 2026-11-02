"""Rendering of `next` (SPEC §3.15, §4.11), human items and printed commands (§1.6).

Everything Git-dependent (prompt texts, diffstats, blob views) comes through `Reader`, so rendering is a function of
its arguments."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field

from engine.canon import canonical, iso, parse_iso
from engine.frontier import PRI, GoalResult, Portfolio, order_key
from engine.schemas import lens_label

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

    def has(self, oid: str) -> bool:
        return False

    def human_decisions(self, g: int, graph, nodes) -> list | None:
        """The goal's answered blocked questions on `nodes` (see `human_decisions`); None when history is unreadable."""
        return []


@dataclass
class Ctx:
    prefix: str
    now: int
    settings: dict
    coordinator: dict
    reader: Reader = field(default_factory=Reader)
    goal_commits: dict = field(default_factory=dict)     # id -> goal tip commit (for edit --base)
    goal_dates: dict = field(default_factory=dict)       # id -> goal tip committer date (seconds)
    repo: str | None = None                              # worker-facing commands carry --repo <primary> (G1028)
    targets: dict = field(default_factory=dict)          # G1025: branch -> tip of the production and line branches


def command(ctx: Ctx, argv: list) -> dict:
    """A printed command (SPEC §1.6). With `ctx.repo` (worker-facing output) it ends `--repo <dir>`, so it runs from
    any directory."""
    repo = getattr(ctx, "repo", None)
    argv = list(argv) + (["--repo", repo] if repo else [])
    return {"argv": argv, "command": ctx.prefix + " " + " ".join(shlex.quote(a) if a not in (LABEL, FILE) else a
                                                                 for a in argv)}


def first_line(text: str, limit: int) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:limit]
    return ""


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


# --------------------------------------------------------------------------------------------- human decisions


DECISION_CLIP = 300


def human_decisions(git, tip: str, g: int, graph, nodes) -> list | None:
    """Every answered blocked question of goal g on `nodes`, in commit order (G1026, SPEC §3.9): read from the goal's
    `zzzops: answer G<g> <node>` commits, keeping those whose goal.json has the node's record blocked with an answer
    (which drops approval and dispute answers). Entries: {node, kind, question, text, quote, decided_by, decided_at,
    commit}. None when the history cannot be read."""
    from engine.gitrun import GitError
    prefix = f"zzzops: answer G{g} "
    try:
        log = git.run("log", "--reverse", "--first-parent", "--format=%H%x1f%s", f"--grep=^{prefix}", tip).stdout
    except (GitError, OSError):
        return None
    wanted = set(nodes)
    out = []
    for line in log.splitlines():
        c, _, subject = line.partition("\x1f")
        if not subject.startswith(prefix):
            continue
        node = subject[len(prefix):].strip()
        if node not in wanted or node not in graph.nodes:
            continue
        data = git.cat(f"{c}:goal.json")
        try:
            r = (json.loads(data.decode("utf-8")).get("records") or {}).get(node) if data is not None else None
        except ValueError:
            r = None
        if not isinstance(r, dict) or r.get("status") != "blocked" or not isinstance(r.get("answer"), dict):
            continue
        a = r["answer"]
        out.append({"node": node, "kind": graph.nodes[node].get("kind"),
                    "question": (r.get("blocked") or {}).get("question"), "text": a.get("text"),
                    "quote": a.get("quote"), "decided_by": a.get("decided_by"), "decided_at": a.get("decided_at"),
                    "commit": c})
    return out


def not_descendants(graph, n: str) -> list:
    """Every node of the graph that is not a descendant of n (n included), in topological order."""
    return [m for m in graph.topo if n not in graph.ancestors(m)]


# --------------------------------------------------------------------------------------------- live leases


LIVE_LEASE_NOTE = "Either abandon then restart, or let it finish: its submit lands but the phase re-runs as ready (stale)."


def restart_command(ctx: Ctx, g: int, n: str) -> dict:
    """After abandon the node is reclaimable, so a restart uses --reclaim (shared by abandon and live-lease entries)."""
    return command(ctx, ["start", str(g), n, "--as", LABEL, "--reclaim"])


def lease_commands(ctx: Ctx, g: int, n: str, attempt: int) -> tuple:
    """(abandon, restart) for a running phase."""
    return command(ctx, ["abandon", str(g), n, "--attempt", str(attempt)]), restart_command(ctx, g, n)


def live_lease_entry(ctx: Ctx, g: int, n: str, L, stale_because: list) -> dict:
    abandon, restart = lease_commands(ctx, g, n, L.attempt)
    return {"goal": g, "node": n, "attempt": L.attempt, "holder": L.holder, "expires_at": iso(L.expires_at),
            "stale_because": list(stale_because), "abandon": abandon, "restart": restart, "note": LIVE_LEASE_NOTE}


# --------------------------------------------------------------------------------------------- edit options


def edit_option(ctx: Ctx, g: int, label: str, sets: dict) -> dict:
    return {"label": label, "command": command(ctx, ["edit", str(g), "--file", FILE, "--base", ctx.goal_commits.get(g, "<C>")]),
            "file": {"set": sets}}


def cancel_option(ctx: Ctx, g: int) -> dict:
    return edit_option(ctx, g, "cancel the goal",
                       {"state": "closed", "closed.reason": "cancelled", "closed.note": "<why>"})


# --------------------------------------------------------------------------------------------- actions


def run_capability(state: dict) -> str | None:
    """The one capability rule, shared by `next` actions and task cards: a retry needs `reasoning`; a run whose
    record is stale only on `inputs.base` and that has no live corrections is a rebase (`routine`); otherwise None
    (the caller falls back to the node's own tier). `record_stale` (set at claim time) is the staleness since the
    accepted record; a frontier state carries no `record_stale`, and its `stale_because` is exactly that."""
    if state.get("reason") == "retry":
        return "reasoning"
    record_stale = state["record_stale"] if "record_stale" in state else state.get("stale_because")
    if record_stale == ["inputs.base"] and not state.get("corrections"):
        return "routine"     # only the base moved since the accepted output and no finding asks for a change
    return None


def capability(res: GoalResult, n: str, state: dict) -> str | None:
    nd = res.graph.nodes[n]
    return run_capability(state) or (nd.get("capability", "bounded") if nd["kind"] == "agent" else None)


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
    if res.target is not None:
        a["target"] = res.target["branch"]
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


def checks_summary(result: dict) -> str:
    """Measured checks context, with independently qualified comparison scopes (G1043)."""
    def milliseconds(value, signed=False):
        if type(value) is not int or (not signed and value < 0):
            return None
        return f"{value / 1000:+.3f} s" if signed else f"{value / 1000:.3f} s"

    timing = result.get("timing")
    if not isinstance(timing, dict):
        durations = []
        details = result.get("details")
        for detail in details if isinstance(details, list) else []:
            if not isinstance(detail, dict):
                continue
            duration = milliseconds(detail.get("milliseconds"))
            if duration is None and type(detail.get("seconds")) is int and detail["seconds"] >= 0:
                duration = f"{detail['seconds']} s"
            if duration is not None:
                durations.append(duration)
        recorded = ", ".join(durations[:6]) or "unavailable"
        return f"Legacy local checks: recorded command times {recorded}; total and baseline unavailable (legacy_timing)."

    def provenance(scope):
        source = scope.get("source", scope)
        if not isinstance(source, dict) or source.get("goal") is None:
            return ""
        goal = clip(str(source["goal"]), 20)
        node = clip(str(source.get("node", "?")), 24)
        target = clip(str(source.get("target", "?")), 48)
        merge = clip(str(source.get("merge_commit", "?")), 12)
        return f" vs recorded merged G{goal}/{node} {target}@{merge}"

    def comparison(label, scope):
        if not isinstance(scope, dict):
            scope = {"status": "unavailable", "reason": "legacy_timing"}
        delta = milliseconds(scope.get("delta_ms"), signed=True)
        if scope.get("status") == "available" and delta is not None:
            return f"{label} delta {delta}" + provenance(scope)
        reason = scope.get("reason") or ("invalid_evidence" if scope.get("status") == "available" else "legacy_timing")
        qualifier = clip(str(reason), 64)
        if scope.get("limit"):
            qualifier += f" ({clip(str(scope['limit']), 24)})"
        return f"{label} comparison unavailable: {qualifier}" + provenance(scope)

    total = milliseconds(timing.get("total_ms"))
    verification = milliseconds(timing.get("verification_ms"))
    if total is None:
        reason = clip(str(timing.get("reason") or "invalid_evidence"), 64)
        return f"Local checks timing unavailable: {reason}; repository verification and baseline unavailable."
    baseline = timing.get("baseline")
    parts = [f"Local checks {total}", f"repository verification {verification or 'unavailable'}",
             comparison("Total", baseline),
             comparison("Repository verification", baseline.get("verification") if isinstance(baseline, dict) else None)]
    # Keep the qualifications ahead of verbose command logs and preserve the
    # caveat even if unusual source names need clipping. Full evidence is separate.
    caveat = "; informational: machine load and concurrent goal-command workload may differ."
    return clip("; ".join(parts), 600 - len(caveat)) + caveat


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
        elif (t == "object" and isinstance(v, dict) and not sel.path and sel.kind == "node"
              and (nd.get("inputs") or {}).get(name, {}).get("context") is True
              and res.graph.nodes.get(sel.node, {}).get("kind") == "op"
              and res.graph.nodes.get(sel.node, {}).get("op") == "checks.run"):
            text = json.dumps(v, sort_keys=True, ensure_ascii=False)
            if len(text) > 400:
                entry.update(ctx.reader.blob_view(text))
            else:
                entry["value"] = v
            entry["summary"] = checks_summary(v)
        else:
            entry["summary"] = value_view(v)
        out.append(entry)
    return out


def checkpoint_view(ctx: Ctx, cp: dict) -> dict:
    diff = f"git diff {cp['base']} {cp['commit']} -- ':/' ':(top,exclude).zzzops/reviews'"
    view = {"commit": cp["commit"], "base": cp["base"], "diff": diff}
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
    follows = sorted({(f["id"], f["follows"]) for r in records.values() for f in r.get("findings") or []
                      if f.get("follows")})
    parts.append("waived: " + (", ".join(sorted(waived)) or "none"))
    parts.append("disputed: " + (", ".join(sorted(disputed)) or "none"))
    if follows:
        parts.append("follows: " + ", ".join(f"{a} ← {b}" for a, b in follows))
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
    notes = notes_by_lens(res, n)
    if notes:
        item["notes"] = notes
    lenses = lenses_applied(res, n)
    if lenses:
        item["lenses"] = lenses
    skipped = skips(res)
    if skipped:
        item["skipped"] = skipped
    item.update(pr_and_stack(res))
    item["facts"] = facts(res)
    hd = ctx.reader.human_decisions(g, res.graph, not_descendants(res.graph, n))
    if hd is None:
        item["human_decisions"] = "unavailable"
    elif hd:
        item["human_decisions"] = [dict(e, text=clip(e["text"], DECISION_CLIP)) if isinstance(e.get("text"), str)
                                   else e for e in hd]
    r = (res.doc.get("records") or {}).get(n)
    if r and r["status"] == "done":
        prev = {"decided_at": (r["output"] or {}).get("decided_at"), "quote": (r["output"] or {}).get("quote")}
        if s["ready"].get("stale_because"):
            prev["stale_because"] = s["ready"]["stale_because"]
        diff = interdiff(ctx, res, n, r)
        if diff:
            prev["interdiff"] = diff
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


def notes_by_lens(res: GoalResult, n: str) -> dict:
    """The filter-judged notes of the lenses behind the filters that node n reads, grouped by lens."""
    filters = {p for p in res.graph.producers(n) if res.graph.is_filter(p)}
    lenses = {x for f in filters for x in res.graph.reviewers(f)}
    out = {}
    for t in res.graph.topo:
        for c, f, reason in sorted(res.notes.get(t, []), key=lambda x: x[1]["id"]):
            if c in lenses:
                out.setdefault(lens_label(c, f), []).append({"id": f["id"], "target": t, "text": clip(f["text"], 300),
                                              "impact": clip(f.get("impact") or "", 200), "reason": reason})
    return out


def lenses_applied(res: GoalResult, n: str) -> dict:
    """For each multi-lens reviewer that node n reads: the lenses it applies and those the goal skipped (G1022)."""
    skip = res.doc.get("skip") or {}
    return {p: {"apply": res.graph.applied_lenses(p, skip), "skipped": res.graph.skipped_lenses(p, skip)}
            for p in res.graph.producers(n) if res.graph.lens_defs(p)}


def skips(res: GoalResult) -> list:
    """Every skip with its reason, and the open findings recorded on a skipped node (a late finding is never
    invisible: G1000 approval directive)."""
    records = res.doc.get("records") or {}
    out = []
    for n, reason in sorted((res.doc.get("skip") or {}).items()):
        e = {"node": n, "reason": clip(reason, 300)}
        opened = [{"id": f["id"], "target": f["target"], "text": clip(f["text"], 300)}
                  for f in (records.get(n) or {}).get("findings") or [] if f["status"] == "open"]
        if opened:
            e["open_findings"] = opened
        out.append(e)
    return out


def interdiff(ctx: Ctx, res: GoalResult, n: str, r: dict) -> str | None:
    """§4.11/§4.20: omitted when the subject checkpoint's change is unchanged; else a range-diff of the goal's own
    commits, when the reviewed commit exists locally."""
    subj = res.graph.subject(n)
    sr = (res.doc.get("records") or {}).get(subj) or {}
    for k, old in (r.get("reviewed") or {}).items():
        cur = (sr.get("output") or {}).get(k)
        if isinstance(cur, dict) and cur.get("change") != old.get("change") and ctx.reader.has(old["commit"]):
            return f"git range-diff {old['base']}..{old['commit']} {cur['base']}..{cur['commit']}"
    return None


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
    response = f.get("response") or (((records.get(n) or {}).get("output") or {}).get("responses") or {}).get(f["id"], "")
    q = (f"`{carrier}` and `{n}` disagree on {f['id']}: '{clip(f['text'], 300)}'. `{n}` answered: "
         f"'{clip(response, 300)}'. Uphold the finding (the target must fix it) or waive it?")
    item = {"goal": g, "node": carrier, "stage": res.graph.nodes[carrier]["stage"], "kind": "dispute", "question": q,
            "since": cr["finished_at"]}
    if not full:
        return item
    argv = ["answer", str(g), carrier, "--fp", cr["input_fp"], "--file", FILE]
    if res.graph.nodes[carrier]["kind"] == "op":
        opts = [{"label": "uphold", "command": command(ctx, argv)},
                {"label": "re-observe", "command": command(ctx, ["reopen", str(g), carrier, "--note", "<why>"])}]
        if carrier not in res.graph.terminal and res.graph.skippable(carrier):
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
    if n not in res.graph.terminal and res.graph.skippable(n):
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
        if x not in res.graph.terminal and res.graph.skippable(x):
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
    if any(res.goal in gs for _, gs in p.duplicates):
        return acts, waiting                                  # a duplicate line: no owner until a human picks one
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
                warnings: list | None = None, paused: bool = False, legacy: dict | None = None) -> dict:
    """`blockers`: [{"kind", "message"}]; a message may contain "{n}" (the number of paused actions).
    `paused`: a blocker pauses every action. `legacy`: the pre-reset state item (G1015), shown only when active."""
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
    if p.branching and scope is None:
        items += line_items(ctx, p, full)
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
    if legacy:
        out["legacy"] = legacy
    if p.branching:
        out["releases"] = releases_view(ctx, p)
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


def line_items(ctx: Ctx, p: Portfolio, full: bool) -> list:
    """G1025 portfolio items: release_cut, hotfix_start, duplicate_line and a missing line branch."""
    out = []
    s = ctx.settings
    b = s.get("branching") or {}
    I = s["integration_branch"]
    template = {"decision": "approved", "quote": "<the human's words, verbatim>", "decided_by": "<name>"}
    key = (0, 0, 0, 0, 0)
    if p.cut:
        N = p.cut["release"]
        branch = b["release_prefix"] + str(N)
        tip = ctx.coordinator.get("commit")
        out.append((key, {"kind": "release_cut", "release": N, "branch": branch, "from": I, "tip": tip,
                          "goals": list(p.cut["goals"]),
                          "question": f"Release {N} is complete on {I}. Cut {branch} from {I} at {(tip or '')[:7]}?",
                          "answer_template": dict(template),
                          "command": command(ctx, ["release", "cut", str(N), "--answer", FILE])["command"]}))
    for x in p.hotfix_starts:
        branch = b["hotfix_prefix"] + x
        tip = ctx.targets.get(b.get("production"))
        out.append((key, {"kind": "hotfix_start", "hotfix": x, "branch": branch, "from": b.get("production"), "tip": tip,
                          "question": f"Start hotfix {x}: create {branch} from {b.get('production')}?",
                          "answer_template": dict(template),
                          "command": command(ctx, ["hotfix", "start", x, "--answer", FILE])["command"]}))
    for branch, gs in p.duplicates:
        out.append((key, {"kind": "duplicate_line", "branch": branch, "goals": gs,
                          "question": f"{', '.join(f'G{g}' for g in gs)} all own {branch}; cancel all but one.",
                          "options": [cancel_option(ctx, g) for g in gs]}))
    for x in p.lines:
        if x.open and x.branch in ctx.targets and ctx.targets.get(x.branch) is None:
            out.append((key, {"kind": "line_branch_missing", "goal": x.goal, "branch": x.branch,
                              "question": f"{x.branch} is gone from the remote; restore it or cancel G{x.goal}.",
                              "options": [cancel_option(ctx, x.goal)]}))
    return out


def releases_view(ctx: Ctx, p: Portfolio) -> dict:
    return {"configured": ctx.settings["releases"]["current"], "effective": p.effective,
            "lines": {x.name: {"kind": x.kind, "branch": x.branch, "goal": x.goal, "state": x.state} for x in p.lines},
            "waiting": list(p.release_waiting)}


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
