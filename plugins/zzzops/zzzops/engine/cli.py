"""The CLI (SPEC §6, §1.6). Every verb prints one JSON object on stdout (`show` prints text unless --json)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from engine import ENGINE_VERSION, schemas
from engine.canon import iso
from engine.errors import EngineError, Refused
from engine.ops import OPS

USAGE = """usage: zzzops <verb> [args]

verbs:
  next [--goal G]... [--all]          what to do next (read-only)
  show G [--node X] [--json]          one goal (read-only)
  new --file F                        create a goal
  start G X [--as L] [--reclaim] [--force]
  submit G X --attempt N [--as L] (--output F [--artifact F] | --blocked F)
  renew G X --attempt N
  abandon G X (--attempt N | --force --note T)
  answer G X --fp P --file F
  reopen G X --note T
  edit G... (--file F... | --set PATH=JSON...) [--base C]...
  validate [G...] | --policy [--dir D]

global flags: --remote R, --integration B
  --policy-ref REF   read-only preview (next, show, validate): read the policy from REF, a zzzops/policy/*
                     branch (or its topic), a branch on the remote, or a local commit, instead of the
                     integration branch
"""

VERBS = {}


def verb(name):
    def deco(fn):
        VERBS[name] = fn
        return fn
    return deco


class Args:
    """A small argv parser: flags may appear anywhere; repeatable flags collect lists."""

    def __init__(self, argv, flags: dict):
        self.pos, self.opts = [], {}
        i = 0
        while i < len(argv):
            a = argv[i]
            if a.startswith("--"):
                name = a[2:]
                value = None
                if "=" in name:
                    name, value = name.split("=", 1)
                kind = flags.get(name)
                if kind is None:
                    raise Refused("usage", f"unknown flag --{name}", hint="run zzzops --help")
                if kind == "bool":
                    self.opts[name] = True
                else:
                    if value is None:
                        i += 1
                        if i >= len(argv):
                            raise Refused("usage", f"--{name} needs a value")
                        value = argv[i]
                    if kind == "list":
                        self.opts.setdefault(name, []).append(value)
                    else:
                        self.opts[name] = value
            else:
                self.pos.append(a)
            i += 1

    def get(self, name, default=None):
        return self.opts.get(name, default)


GLOBAL = {"remote": "value", "integration": "value", "policy-ref": "value"}
PREVIEW_VERBS = "next, show and validate"


def emit(obj: dict):
    sys.stdout.write(json.dumps(obj, indent=2, sort_keys=False, ensure_ascii=False) + "\n")


def goal_id(text: str) -> int:
    t = text[1:] if text[:1] in "Gg" else text
    if not t.isdigit():
        raise Refused("usage", f"not a goal id: {text!r}")
    return int(t)


def session(args, environment=True, preview=False):
    from engine.session import Session
    if args.get("policy-ref") and not preview:
        raise Refused("usage", f"--policy-ref is a read-only preview: it works with {PREVIEW_VERBS}")
    s = Session(remote=args.get("remote"), integration=args.get("integration"), policy_ref=args.get("policy-ref"))
    if environment:
        s.check_environment()
    return s


def load_json_file(path: str, what: str):
    try:
        with open(path, "rb") as fh:
            return json.loads(fh.read().decode("utf-8"))
    except FileNotFoundError:
        raise Refused("not_found", f"{what} file {path!r} not found")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refused("validation", f"{what} file {path!r} is not valid JSON: {exc}")


# --------------------------------------------------------------------------------------------- read-only verbs


@verb("next")
def cmd_next(argv):
    a = Args(argv, dict(GLOBAL, goal="list", all="bool"))
    s = session(a, preview=True)
    s.open(goals=[goal_id(g) for g in a.get("goal", [])], readonly=True)
    scope = [goal_id(g) for g in a.get("goal", [])] or None
    out = s.render_next(scope=scope, all_=bool(a.get("all")))
    s.mirror()
    emit(out)
    return 0


@verb("show")
def cmd_show(argv):
    a = Args(argv, dict(GLOBAL, node="value", json="bool"))
    if len(a.pos) != 1:
        raise Refused("usage", "show G [--node X] [--json]")
    g = goal_id(a.pos[0])
    s = session(a, preview=True)
    st = s.open(goals=[g], readonly=True, all_goals=True)
    if g not in s.snap.goals:
        raise Refused("not_found", f"G{g} does not exist")
    if g not in st.docs:
        errs = st.invalid.get(g) or (["newer goal schema than this engine"] if g in st.newer else ["unreadable"])
        raise Refused("validation", f"G{g} is invalid: " + "; ".join(errs), details={"errors": errs})
    from engine.render import state_string
    p = s.portfolio()
    doc = st.docs[g]
    res = p.goals.get(g)
    states = {n: state_string(res.st[n]) for n in res.graph.topo} if res else {}
    leases = {}
    for (lg, node), L in sorted(st.leases.items()):
        if lg == g:
            leases[node] = {"attempt": L.attempt, "holder": L.holder, "reason": L.reason, "timeout": L.timeout,
                            "last_active": iso(L.last_active), "expires_at": iso(L.expires_at), "tip": L.tip}
    node = a.get("node")
    if node:
        if node not in (res.graph.nodes if res else s.state.graphs.get(doc["graph"]).nodes):
            raise Refused("not_found", f"G{g} has no node {node!r}")
        out = {"ok": True, "coordinator": st.coordinator, "goal": g, "node": node,
               "record": doc["records"].get(node), "state": states.get(node), "lease": leases.get(node),
               "goal_commit": s.snap.goals[g]}
        emit(out)
        return 0
    if a.get("json"):
        out = {"ok": True, "coordinator": st.coordinator, "goal": doc, "goal_commit": s.snap.goals[g], "states": states,
               "leases": leases, "history": f"git log -p refs/zzzops/goal/{s.R}/g{g}"}
        if g in s.snap.rewritten:
            out["rewritten"] = {"accepted": s.snap.goals[g], "remote": s.snap.rewritten[g]}
        emit(out)
        return 0
    lines = [f"G{g} {doc['title']} — {doc['state']}, goal commit {s.snap.goals[g]}"]
    records = doc.get("records") or {}
    for n, sstr in states.items():
        r = records.get(n) or {}
        L = leases.get(n)
        extra = ""
        if r:
            extra += f"  attempt {r.get('attempt')}  {r.get('holder')}  since {r.get('finished_at')}"
        if L:
            extra += f"  lease attempt {L['attempt']} {L['holder']} until {L['expires_at']}"
        lines.append(f"  {n:<16} {sstr}{extra}")
    lines.append(f"history: git log -p refs/zzzops/goal/{s.R}/g{g}")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


@verb("validate")
def cmd_validate(argv):
    a = Args(argv, dict(GLOBAL, policy="bool", dir="value"))
    if a.get("policy"):
        if a.get("policy-ref"):
            raise Refused("usage", "use either --policy (a directory) or --policy-ref (a ref), not both")
        return validate_policy_dir(a)
    s = session(a, environment=False, preview=True)
    from engine.gitrun import check_environment
    env = check_environment(s.git)
    from engine.gh import gh_problems
    st = s.open(readonly=True, all_goals=True)
    env += gh_problems(s)
    package = package_check()
    if package:
        env.append(package)
    wanted = [goal_id(x) for x in a.pos] or sorted(set(st.docs) | set(st.invalid) | st.newer)
    goals = {}
    for g in wanted:
        if g in st.invalid:
            goals[str(g)] = st.invalid[g]
        elif g in st.newer:
            goals[str(g)] = ["newer goal schema than this engine (read-only here)"]
        elif g not in st.docs and g not in s.snap.goals:
            goals[str(g)] = ["does not exist"]
        else:
            goals[str(g)] = []
    policy = []
    for b in st.blockers:
        if b["kind"] in ("policy_invalid", "not_bootstrapped", "engine_too_old", "engine_too_new", "wrong_integration_branch"):
            policy += b.get("errors") or [b["message"]]
    p = s.portfolio()
    warnings = s.warnings(p)
    attrs = os.path.join(s.git.common, "info", "attributes")
    if os.path.exists(attrs):
        warnings.append({"kind": "info_attributes", "message": f"{attrs} exists: it can change diffs, and cannot be disabled"})
    if s.git.config("remote." + (s.R or "origin") + ".partialclonefilter") or s.git.config("extensions.partialClone"):
        warnings.append({"kind": "partial_clone", "message": "partial clone: missing goal documents cost one round trip each"})
    ok = not env and not policy and not any(goals.values())
    out = {"ok": ok, "coordinator": st.coordinator, "goals": goals, "policy": policy, "environment": env,
           "warnings": warnings}
    if a.get("policy-ref") and not policy and st.policy is not None:
        try:
            out.update(policy_impact(dict(a.opts, **{"policy-ref": None}), st.policy, st.workflow))
        except (Refused, Exception):
            pass
    emit(out)
    return 0 if ok else 1


def package_check() -> str | None:
    """The plugin package self-check (DESIGN C4): a damaged or mixed installation is reported, never gated on."""
    import runpy
    try:
        status = runpy.run_path(str(Path(__file__).resolve().parent.parent / "package.py"))["package_status"]()
    except Exception as exc:                                    # pragma: no cover - a broken install
        return f"plugin package check failed: {exc}"
    return None if status.get("ok") else f"plugin package: {status.get('detail')}"


def validate_policy_dir(a) -> int:
    d = Path(a.get("dir") or os.path.join(os.getcwd(), ".zzzops"))
    errors = []

    def load(name):
        p = d / name
        if not p.is_file():
            errors.append(f"{name}: missing in {d}")
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: not valid JSON ({exc})")
            return None

    policy = load("POLICY.json")
    workflow = load("workflow.json")
    if policy is not None:
        errors += list(schemas.validate_policy(policy))
    if workflow is not None:
        errors += list(schemas.validate_workflow(workflow, policy if policy is not None and not errors else None,
                                                 lambda f: (d / "prompts" / f).is_file(), OPS))
    out = {"ok": not errors, "coordinator": {}, "goals": {}, "policy": errors, "environment": [], "warnings": []}
    if not errors:
        try:
            out.update(policy_impact(a, policy, workflow))
        except (Refused, Exception):
            pass
    emit(out)
    return 0 if not errors else 1


def policy_impact(a, policy, workflow) -> dict:
    """SPEC §3.16 policy impact, when goals can be read."""
    from engine.frontier import portfolio
    from engine.render import state_string
    s = session(a, environment=False)
    st = s.open(readonly=True)
    if st.settings is None:
        return {}
    before = s.portfolio()
    graphs = {n: schemas.build_graph(n, g) for n, g in workflow["graphs"].items()}
    after = portfolio(st.docs, graphs, st.leases, policy["settings"], s.now, st.invalid, st.newer)
    nodes, staled, reasked, unknown = {}, {}, 0, []
    for g, res in sorted(before.goals.items()):
        res2 = after.goals.get(g)
        if res2 is None:
            if st.docs[g]["graph"] not in graphs:
                unknown.append(g)
            continue
        for n in res.graph.topo:
            b = state_string(res.st[n])
            x = state_string(res2.st[n]) if n in res2.st else "removed"
            if b != x:
                nodes.setdefault(f"G{g}", {})[n] = {"before": b, "after": x}
                if res.st[n]["name"] == "current" and res2.st.get(n, {}).get("name") == "ready" and res.graph.nodes[n]["kind"] == "agent":
                    staled[n] = staled.get(n, 0) + 1
                if res.st[n]["name"] == "current" and res2.st.get(n, {}).get("name") == "needs_human":
                    reasked += 1
    live_changed = [{"goal": g, "node": n, "holder": L.holder} for (g, n), L in sorted(st.leases.items())
                    if L.live(s.now) and f"G{g}" in nodes and n in nodes[f"G{g}"]]
    new_stuck = sorted(g for g, r in after.goals.items() if r.stuck and not (before.goals.get(g) and before.goals[g].stuck))
    return {"impact": {"agent_phases_staled": staled, "human_gates_reasked": reasked,
                       "live_leases_on_changed_nodes": live_changed, "unknown_graph": unknown, "new_stuck": new_stuck,
                       "nodes": nodes}}


# --------------------------------------------------------------------------------------------- new (§4.17)


@verb("new")
def cmd_new(argv):
    import time
    from engine import store
    a = Args(argv, dict(GLOBAL, file="value"))
    if not a.get("file") or a.pos:
        raise Refused("usage", "new --file F")
    spec = load_json_file(a.get("file"), "new-goal")
    errs = schemas.validate_new_file(spec)
    if errs:
        raise Refused("validation", "; ".join(errs), details={"errors": list(errs)})
    key = request_key_of(spec)
    s = session(a)                                   # refuses --policy-ref before any scan (G1001 §4)
    st = s.open()
    if s.snap.current:
        hits = scan_request_key(s, key)
        if hits:
            return recover_new(s, spec, key, hits)  # recovering writes nothing, so it precedes require_writable
    s.require_writable()
    retry_hint = "rerun the same `new`: it is safe to retry"
    deadline = time.monotonic() + 30
    while True:
        st = s.state
        settings = st.settings
        known = set(s.snap.known) | set(s.snap.goals) | set(s.snap.deleted) | set(s.snap.rewritten)
        gid = max(known | {settings["goals"]["first_id"] - 1}) + 1
        doc = {"schema": 1, "id": gid, "title": spec["title"], "graph": spec.get("graph", "default"),
               "state": spec.get("state", "open"), "closed": None, "spec": spec["spec"],
               "priority": spec.get("priority", "P2"), "release": spec.get("release", settings["releases"]["current"]),
               "depends_on": spec.get("depends_on", []), "skip": spec.get("skip", {}),
               "links": spec.get("links", {"issue": None}), "budget": None, "records": {}}
        all_docs = dict(st.docs)
        all_docs[gid] = doc
        for d in doc["depends_on"] if isinstance(doc["depends_on"], list) else []:
            if isinstance(d, int) and d not in all_docs and d in s.snap.goals:
                dd, _ = store.read_goal_json(s.git, s.snap.goals[d])
                if isinstance(dd, dict):
                    all_docs[d] = dd
        errs, _ = schemas.validate_goal(doc, None, all_docs, st.workflow)
        if errs:
            raise Refused("validation", "; ".join(errs[:5]), details={"errors": list(errs)})
        c = store.goal_commit(s.git, doc, None, store.goal_message("new", gid, "created", doc["state"], request_key=key))
        ref = f"refs/heads/zzzops/goal/g{gid}"
        r, stderr = store.push_atomic(s.git, s.R, [(ref, None, c)], report_up_to_date=True)
        if r == "up_to_date":
            # an identical twin (same document, message and clock) already pushed this exact root commit
            try:
                s.refetch()
            except store.RemoteError as exc:
                raise Refused("remote", str(exc), hint=retry_hint)
            emit(new_output(s, doc, c, key, recovered=True))
            return 0
        if r == "ok":
            s.snap.advance([(ref, None, c)])
            st.docs[gid] = doc
            s._portfolio = None
            emit(new_output(s, doc, c, key, recovered=False))
            return 0
        try:
            s.refetch()
        except store.RemoteError as exc:
            raise Refused("remote", str(exc), hint=retry_hint)
        hits = scan_request_key(s, key)
        if hits:
            return recover_new(s, spec, key, hits)  # the push landed but reported failure, or a racing twin won
        if r == "remote":
            raise Refused("remote", f"push to `{s.R}` failed: {stderr.strip().splitlines()[:1]}", hint=retry_hint)
        if gid not in s.snap.goals:
            raise Refused("push_refused", "the remote refused creating the goal branch (a branch rule or hook)",
                          hint="exclude zzzops/** from branch rules (SETUP.md)")
        if time.monotonic() > deadline:
            raise Refused("contention", "could not allocate a goal id; retry shortly")


NEW_COMPARED = ("graph", "state", "priority", "release", "skip", "links")


def norm_depends_on(v):
    """Sorted, unique ids when depends_on is a list of ints; any other value passes through (validate_goal rejects it)."""
    if isinstance(v, list) and all(isinstance(d, int) and not isinstance(d, bool) for d in v):
        return sorted(set(v))
    return v


def request_key_of(spec: dict) -> str:
    """G1001 §1: the explicit request_key, else sha256 over title, spec and the normalised depends_on."""
    if "request_key" in spec:
        return spec["request_key"]
    from engine import canon
    return "sha256:" + canon.H({"v": 1, "title": spec["title"], "spec": spec["spec"],
                                "depends_on": norm_depends_on(spec.get("depends_on", []))})


def new_differences(spec: dict, root: dict) -> list:
    """The request fields that differ from the goal's root document (fields the request omits are not compared)."""
    out = [k for k in ("title", "spec") if spec[k] != root.get(k)]
    if norm_depends_on(spec.get("depends_on", [])) != norm_depends_on(root.get("depends_on", [])):
        out.append("depends_on")
    return out + [k for k in NEW_COMPARED if k in spec and spec[k] != root.get(k)]


def scan_request_key(s, key: str) -> list:
    """store.find_request_key, plus one refetch and rescan when nothing matched and some goal is only a local ref
    (another `new` in this clone may have written it after this call's fetch listed the remote)."""
    from engine import store
    hits = store.find_request_key(s.git, s.snap, key)
    if not hits and s.snap.deleted:
        try:
            s.refetch()
        except store.RemoteError as exc:
            raise Refused("remote", str(exc), hint="rerun the same `new`: it is safe to retry")
        hits = store.find_request_key(s.git, s.snap, key)
    return hits


def recover_new(s, spec: dict, key: str, hits: list) -> int:
    gid, root, doc = hits[0]
    diff = new_differences(spec, doc)
    if diff:
        raise Refused("validation", f"request_key {key} already created G{gid} with different contents: {', '.join(diff)}",
                      details={"goal": gid, "fields": diff}, hint=f"use a different request_key, or `zzzops edit G{gid}`")
    out = new_output(s, doc, root, key, recovered=True)
    if len(hits) > 1:
        ids = [h[0] for h in hits]
        out["warnings"] = [{"kind": "duplicate_request_key", "goals": ids,
                            "message": f"request_key {key} created several goals ({', '.join(f'G{g}' for g in ids)}); "
                                       f"returning G{gid}"}]
    emit(out)
    return 0


def new_output(s, doc: dict, commit: str, key: str, recovered: bool) -> dict:
    gid = doc["id"]
    return {"ok": True, "coordinator": s.state.coordinator,
            "created": {"id": gid, "display": f"G{gid}", "title": doc["title"], "graph": doc["graph"],
                        "release": doc["release"], "priority": doc["priority"], "depends_on": doc["depends_on"],
                        "goal_commit": commit, "recovered": recovered, "request_key": key},
            "next": s.render_next(scope=[gid])}


# --------------------------------------------------------------------------------------------- lifecycle verbs


def two_ids(a, usage):
    if len(a.pos) != 2:
        raise Refused("usage", usage)
    return goal_id(a.pos[0]), a.pos[1]


def attempt_of(a, required=True):
    v = a.get("attempt")
    if v is None:
        if required:
            raise Refused("usage", "--attempt N is required")
        return None
    if not str(v).isdigit():
        raise Refused("usage", "--attempt takes an integer")
    return int(v)


@verb("start")
def cmd_start(argv):
    from engine import verbs
    a = Args(argv, dict(GLOBAL, **{"as": "value", "reclaim": "bool", "force": "bool"}))
    g, x = two_ids(a, "start G X [--as L] [--reclaim] [--force]")
    s = session(a)
    out = verbs.start(s, g, x, verbs.default_label(a.get("as")), bool(a.get("reclaim")), bool(a.get("force")))
    emit(out)
    return 0


@verb("submit")
def cmd_submit(argv):
    from engine import verbs
    a = Args(argv, dict(GLOBAL, attempt="value", **{"as": "value"}, output="value", artifact="value", blocked="value"))
    g, x = two_ids(a, "submit G X --attempt N [--as L] (--output F [--artifact F] | --blocked F)")
    s = session(a)
    emit(verbs.submit(s, g, x, attempt_of(a), verbs.default_label(a.get("as")), a.get("output"), a.get("artifact"),
                      a.get("blocked")))
    return 0


@verb("renew")
def cmd_renew(argv):
    from engine import verbs
    a = Args(argv, dict(GLOBAL, attempt="value"))
    g, x = two_ids(a, "renew G X --attempt N")
    emit(verbs.renew(session(a), g, x, attempt_of(a)))
    return 0


@verb("abandon")
def cmd_abandon(argv):
    from engine import verbs
    a = Args(argv, dict(GLOBAL, attempt="value", force="bool", note="value"))
    g, x = two_ids(a, "abandon G X (--attempt N | --force --note T)")
    force = bool(a.get("force"))
    if force and not a.get("note"):
        raise Refused("usage", "abandon --force needs --note")
    emit(verbs.abandon(session(a), g, x, attempt_of(a, required=not force), force, a.get("note")))
    return 0


@verb("answer")
def cmd_answer(argv):
    from engine import verbs
    a = Args(argv, dict(GLOBAL, fp="value", file="value"))
    g, x = two_ids(a, "answer G X --fp P --file F")
    if not a.get("fp") or not a.get("file"):
        raise Refused("usage", "answer G X --fp P --file F")
    emit(verbs.answer(session(a), g, x, a.get("fp"), a.get("file")))
    return 0


@verb("reopen")
def cmd_reopen(argv):
    from engine import verbs
    a = Args(argv, dict(GLOBAL, note="value"))
    g, x = two_ids(a, "reopen G X --note T")
    emit(verbs.reopen(session(a), g, x, a.get("note") or ""))
    return 0


@verb("edit")
def cmd_edit(argv):
    from engine import verbs
    a = Args(argv, dict(GLOBAL, file="list", set="list", base="list"))
    if not a.pos:
        raise Refused("usage", "edit G... (--file F... | --set PATH=JSON...) [--base C]...")
    gids = [goal_id(x) for x in a.pos]
    sets = []
    for item in a.get("set", []):
        if "=" not in item:
            raise Refused("usage", f"--set takes PATH=JSON, got {item!r}")
        path, raw = item.split("=", 1)
        try:
            sets.append((path, json.loads(raw)))
        except json.JSONDecodeError as exc:
            raise Refused("usage", f"--set {path}: not JSON ({exc})")
    if not sets and not a.get("file"):
        raise Refused("usage", "edit needs --file or --set")
    emit(verbs.edit(session(a), gids, a.get("file", []), sets, a.get("base", [])))
    return 0


# --------------------------------------------------------------------------------------------- main


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(USAGE)
        return 0
    if argv[0] == "--version":
        sys.stdout.write(ENGINE_VERSION + "\n")
        return 0
    name = argv[0]
    # global flags before the verb
    while name.startswith("--") and len(argv) > 2 and name[2:] in GLOBAL:
        argv = argv[2:] + argv[:2]
        name = argv[0]
    fn = VERBS.get(name)
    if fn is None:
        emit(Refused("usage", f"unknown verb {name!r}", hint="run zzzops --help").envelope())
        return 1
    try:
        return fn(argv[1:])
    except Refused as exc:
        emit(exc.envelope())
        return exc.exit
    except EngineError as exc:
        emit(Refused("engine_bug", str(exc)).envelope())
        return 1
