"""Short-lived CAS gate for cooperating goal workspace writers."""
from __future__ import annotations

import contextlib
import json
import secrets
import sys

from engine.canon import EMPTY_TREE, iso, read_now
from engine.errors import Refused
from engine import schemas, store

CAPABILITY = "preserved_test_provenance"
WARNING = "Direct Git pushes to work refs are outside the cooperating-writer gate and can race recovery."


def enabled(s):
    return CAPABILITY in schemas.required_caps(s.settings)


def ref(g):
    return f"refs/heads/zzzops/gate/g{g}"


def read(s, g):
    p = s.git.run("ls-remote", s.R, ref(g), check=False, timeout=120)
    if p.returncode:
        raise Refused("remote", "cannot inspect workspace gate")
    lines = p.stdout.splitlines()
    if not lines:
        return None, None
    oid = lines[0].split()[0]
    if not s.git.exists(oid):
        f = s.git.run("fetch", "-q", s.R, ref(g), check=False, timeout=120)
        if f.returncode or not s.git.exists(oid):
            raise Refused("remote", "cannot fetch workspace gate")
    raw = s.git.cat(oid)
    try:
        body = store.parse_commit(oid, raw).message.split("\n", 1)[1]
        doc = json.loads(body)
        if not isinstance(doc, dict) or doc.get("goal") != g or doc.get("state") not in ("held", "free"):
            raise ValueError("invalid gate")
        if not isinstance(doc.get("token"), str) or not doc["token"]:
            raise ValueError("gate has no token")
        if doc["state"] == "held" and (not isinstance(doc.get("holder"), str) or not doc["holder"]
                or not isinstance(doc.get("operation"), str) or not doc["operation"]
                or type(doc.get("acquired_at")) is not int or type(doc.get("expires_at")) is not int
                or doc["expires_at"] <= doc["acquired_at"]):
            raise ValueError("invalid held gate")
    except (ValueError, KeyError, TypeError, IndexError):
        raise Refused("validation", "workspace gate is malformed; inspect it before proceeding")
    return oid, doc


def describe(s, g):
    _, doc = read(s, g)
    if not doc or doc["state"] == "free":
        return None
    state = "expired" if read_now() >= doc["expires_at"] else "held"
    return {"holder": doc["holder"], "operation": doc["operation"],
            "expires_at": iso(doc["expires_at"]), "state": state}


def commit(s, g, parent, doc):
    return s.git.commit_tree(EMPTY_TREE, [parent] if parent else [],
                             "zzzops workspace gate G" + str(g) + "\n" + json.dumps(doc, sort_keys=True))


@contextlib.contextmanager
def hold(s, g, operation):
    if not enabled(s):
        yield None
        return
    held = s.__dict__.setdefault("workspace_gates", {})
    s.git.workspace_gate_holds = held
    if g in held:
        yield held[g]
        return
    old, prev = read(s, g)
    now = read_now()
    reclaimed = bool(prev and prev["state"] == "held" and now >= prev["expires_at"])
    if prev and prev["state"] == "held" and not reclaimed:
        detail = {"holder": prev["holder"], "operation": prev["operation"],
                  "expires_at": iso(prev["expires_at"]), "state": "held"}
        raise Refused("workspace_busy", f"G{g} workspace gate is held by {prev['holder']}", details={"workspace_gate": detail})
    doc = {"goal": g, "state": "held", "holder": "codex:workspace-gate", "operation": operation,
           "token": secrets.token_hex(20), "acquired_at": now,
           "expires_at": now + s.settings["leases"]["ttl_minutes"] * 60}
    oid = commit(s, g, old, doc)
    result, _ = store.push_atomic(s.git, s.R, [(ref(g), old, oid)])
    if result != "ok":
        raise Refused("claim_lost", f"G{g} workspace gate changed while claiming")
    gate = {"oid": oid, "doc": doc, "reclaimed": reclaimed}
    held[g] = gate
    try:
        yield gate
    finally:
        held.pop(g, None)
        free = {"goal": g, "state": "free", "released_at": read_now(), "token": doc["token"]}
        new = commit(s, g, gate["oid"], free)
        status, _ = store.push_atomic(s.git, s.R, [(ref(g), gate["oid"], new)])
        if status != "ok" and sys.exc_info()[0] is None:
            raise Refused("claim_lost", f"G{g} workspace gate could not be released; inspect the goal before retrying")


def decorate(s, updates, force_goal=None):
    """Append a changed gate ref to every guarded atomic work transaction."""
    if not enabled(s):
        return list(updates), {}
    import re
    goals = {int(m.group(1)) for r, _, _ in updates
             if (m := re.fullmatch(r"refs/heads/zzzops/work/g(\d+)", r))}
    if force_goal is not None:
        goals.add(force_goal)
    new = list(updates)
    advanced = {}
    for g in sorted(goals):
        gate = s.__dict__.get("workspace_gates", {}).get(g)
        if not gate:
            raise Refused("validation", f"G{g} work-ref transaction requires its workspace gate")
        if read_now() >= gate["doc"]["expires_at"]:
            raise Refused("superseded", f"G{g} workspace gate expired before the transaction")
        successor = commit(s, g, gate["oid"], gate["doc"] | {"sequence": secrets.token_hex(12)})
        new.append((ref(g), gate["oid"], successor))
        advanced[g] = successor
    return new, advanced


def confirm(s, advanced):
    for g, oid in advanced.items():
        s.workspace_gates[g]["oid"] = oid
