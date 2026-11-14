"""Release and hotfix lines (G1025; SPEC §3.2, §4.9): pure helpers over the settings, the goal documents and the
trailer ledger. No I/O."""

from __future__ import annotations

from dataclasses import dataclass

RELEASE_GRAPH = "release"


def branching(settings: dict | None) -> dict | None:
    b = (settings or {}).get("branching")
    return b if isinstance(b, dict) else None


def entry_of(doc: dict) -> dict:
    """The ledger entry of a document: what the goal-commit trailers cache (§3.1)."""
    flow = doc.get("flow") or {}
    return {"release": doc.get("release"), "state": doc.get("state"), "closed": (doc.get("closed") or {}).get("reason"),
            "line": f"{flow['line']}:{flow['name']}" if flow.get("line") else None, "hotfix": flow.get("hotfix")}


def merged_ledger(ledger: dict | None, docs: dict) -> dict:
    """The trailer ledger, overridden by every document that was read (documents are the truth)."""
    out = {g: dict(v) for g, v in (ledger or {}).items()}
    for g, d in docs.items():
        out[g] = entry_of(d)
    return out


def line_branch(b: dict, kind: str, name: str) -> str:
    return (b["release_prefix"] if kind == "release" else b["hotfix_prefix"]) + str(name)


@dataclass(frozen=True)
class Line:
    goal: int
    kind: str                 # release | hotfix
    name: str
    branch: str
    state: str                # open | held | closed
    closed: str | None

    @property
    def open(self) -> bool:
        return self.state != "closed"


def lines_of(ledger: dict, settings: dict) -> list:
    b = branching(settings)
    if not b:
        return []
    out = []
    for g, e in sorted(ledger.items()):
        v = e.get("line")
        if not isinstance(v, str) or ":" not in v:
            continue
        kind, name = v.split(":", 1)
        if kind not in ("release", "hotfix"):
            continue
        out.append(Line(g, kind, name, line_branch(b, kind, name), e.get("state") or "open", e.get("closed")))
    return out


def effective_release(settings: dict, lines: list) -> int:
    """max(releases.current, 1 + the highest cut release): a finished line keeps counting (§3.1)."""
    cur = settings["releases"]["current"]
    cut = [int(x.name) for x in lines if x.kind == "release" and x.name.isdigit()]
    return max([cur] + [n + 1 for n in cut])


def open_line(lines: list, kind: str, name) -> Line | None:
    hits = [x for x in lines if x.kind == kind and x.name == str(name) and x.open]
    return hits[0] if hits else None


def is_member(e: dict) -> bool:
    """A goal that belongs to its release (not a line goal, not a hotfix member)."""
    return not e.get("line") and not e.get("hotfix")


def members(ledger: dict, line: Line) -> list:
    out = []
    for g, e in sorted(ledger.items()):
        if g == line.goal or e.get("line"):
            continue
        if line.kind == "hotfix" and e.get("hotfix") == line.name:
            out.append(g)
        elif line.kind == "release" and is_member(e) and str(e.get("release")) == line.name:
            out.append(g)
    return out


def open_members(ledger: dict, line: Line) -> list:
    return [g for g in members(ledger, line) if ledger[g].get("state") in ("open", "held")]


def target_of(doc: dict, settings: dict, lines: list) -> dict:
    """{"branch", "kind"} of a goal: its open line's branch, else the integration branch. A hotfix member with no
    open line has branch None (its `base` waits for `hotfix start`)."""
    I = settings["integration_branch"]
    b = branching(settings)
    if not b:
        return {"branch": I, "kind": "integration"}
    flow = doc.get("flow") or {}
    if flow.get("line"):
        return {"branch": line_branch(b, flow["line"], flow["name"]), "kind": flow["line"]}
    if flow.get("hotfix"):
        x = open_line(lines, "hotfix", flow["hotfix"])
        return {"branch": x.branch if x else None, "kind": "hotfix", "name": flow["hotfix"]}
    x = open_line(lines, "release", doc.get("release"))
    if x:
        return {"branch": x.branch, "kind": "release"}
    return {"branch": I, "kind": "integration"}


def cut_state(ledger: dict, lines: list, settings: dict, effective: int) -> tuple:
    """(cut, waiting): the release_cut offer {"release", "goals"} or None, and the waiting entries (§3.2)."""
    N = effective
    mem = [g for g, e in sorted(ledger.items()) if is_member(e) and e.get("release") == N]
    complete = bool(mem) and all(ledger[g].get("state") == "closed" for g in mem) \
        and any(ledger[g].get("closed") == "done" for g in mem)
    if not complete or any(x.kind == "release" and x.name == str(N) for x in lines):
        return None, []
    busy = [x for x in lines if x.kind == "release" and x.open]
    if busy:
        return None, [{"release": N, "until": f"release {busy[0].name} finished",
                       "reason": f"release {N} complete; waiting: release {busy[0].name} not finished"}]
    return {"release": N, "goals": mem}, []


def hotfix_starts(ledger: dict, lines: list) -> list:
    """Hotfix names with an open member and no line yet."""
    names = sorted({e["hotfix"] for e in ledger.values() if e.get("hotfix") and e.get("state") in ("open", "held")})
    return [x for x in names if not any(l.kind == "hotfix" and l.name == x for l in lines)]


def duplicates(lines: list) -> list:
    """[(branch, [goals])] of open line goals that claim the same branch."""
    by = {}
    for x in lines:
        if x.open:
            by.setdefault(x.branch, []).append(x.goal)
    return [(b, gs) for b, gs in sorted(by.items()) if len(gs) > 1]
