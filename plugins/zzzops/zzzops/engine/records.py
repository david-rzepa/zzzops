"""Pure construction of records and findings (SPEC §4.14 findings processing, §4.15, §5.1).

Shared by the verbs (which add Git and pushes) and by tests."""

from __future__ import annotations

import re

from engine.canon import iso, parse_iso
from engine.errors import Refused
from engine.fingerprint import out_fp
from engine.frontier import counts
from engine.schemas import Graph, is_material, is_owner_question

SANITIZE = re.compile(r"[^A-Za-z0-9_-]")


def op_finding_id(node: str, key: str) -> str:
    return f"{node}:{SANITIZE.sub('_', key)}"


def make_fence(graph: Graph, doc: dict, x_fp: str | None, lease_input_fp: str | None, claimed_at: int | None):
    """fence(T) -> (target_fp, target_attempt), or (None, None) for a stale or out-of-date submit (SPEC §4.14)."""
    records = doc.get("records") or {}

    def fence(T):
        t = records.get(T)
        if (lease_input_fp is not None and lease_input_fp == x_fp and t and t["status"] == "done"
                and (claimed_at is None or parse_iso(t["finished_at"]) <= claimed_at)):
            return out_fp(graph, T, t), t["attempt"]
        return None, None

    return fence


def response_of(doc: dict, target: str, fid: str) -> str:
    r = (doc.get("records") or {}).get(target)
    return (((r or {}).get("output") or {}).get("responses") or {}).get(fid, "")


RESPOND_INLINE = 600


def check_responses(responses: dict, corrections: list, carriers: dict | None = None, view=None, why=None):
    """Keys equal the live correction ids; 'fixed: '/'disputed: '; no dispute of an upheld finding.

    On a key mismatch the refusal lists the findings to answer (`carriers`: id -> carrying node; `view(text)` gives
    the full-text reference for a clipped text)."""
    ids = {f["id"] for f in corrections}
    given = set(responses or {})
    if given != ids:
        missing, extra = sorted(ids - given), sorted(given - ids)
        reasons = {fid: why(fid) if why else "not_live" for fid in extra}
        msg = []
        if missing:
            msg.append("respond to: " + ", ".join(missing))
        if extra:
            msg.append("no longer live: " + ", ".join(f"{fid} ({reasons[fid]})" for fid in extra))
        respond_to = []
        for f in sorted((f for f in corrections if f["id"] in missing), key=lambda f: f["id"]):
            item = {"id": f["id"], "from": (carriers or {}).get(f["id"], f["id"].split(":")[0]), "target": f["target"],
                    "text": f["text"], "upheld": bool(f.get("upheld"))}
            if len(f["text"].encode("utf-8")) > RESPOND_INLINE:
                item["text"] = f["text"].encode("utf-8")[:RESPOND_INLINE].decode("utf-8", "ignore")
                if view is not None:
                    item["full"] = view(f["text"])
            respond_to.append(item)
        hints = []
        if missing:
            hints.append("Answer each finding under respond_to in `responses` with 'fixed: …' or 'disputed: …'; "
                         "some may have been raised after your card was printed. "
                         "Check no_longer_live and details.why for obsolete response keys and their reasons.")
        if extra:
            hints.append("Drop each response under no_longer_live (details.why says why it is not live), then resubmit.")
        raise Refused("validation", "; ".join(msg),
                      details={"respond_to": respond_to, "no_longer_live": extra, "why": reasons}, hint=" ".join(hints))
    for f in corrections:
        text = responses[f["id"]]
        if not re.match(r"^(fixed|disputed): \S", text or ""):
            raise Refused("validation", f"responses.{f['id']} must start with 'fixed: ' or 'disputed: '")
        if f.get("upheld") and text.startswith("disputed:"):
            raise Refused("validation", f"{f['id']} was upheld by the human: fix it, do not dispute it")


def process_findings(graph: Graph, doc: dict, X: str, r0: dict | None, given: list, attempt: int, fence,
                     decision: str | None = None) -> tuple:
    """Agent submits (review or not). Returns (findings, ok)."""
    result = []
    N = graph.nodes
    latest = {f["id"]: f for f in ((r0 or {}).get("findings") or [])}
    if graph.is_review(X):
        prior = [f for f in latest.values() if f["status"] == "open" and f["target"] != X]
        closed = {f["id"]: f["status"] for f in latest.values() if f["status"] != "open" and f["target"] != X}
        status = {f["id"]: f["status"] for f in given if "id" in f}
        prior_ids = {f["id"] for f in prior}
        unknown = sorted(set(status) - prior_ids - set(closed))
        reopened = sorted(i for i in status if i in closed and status[i] != "resolved")
        missing = sorted(prior_ids - set(status))
        if unknown:
            raise Refused("validation", "unknown finding ids: " + ", ".join(unknown),
                          details={"needs_status": sorted(prior_ids)},
                          hint="Give a status to each finding in previous.findings (needs_status).")
        if reopened:
            words = sorted({"already waived" if closed[i] == "waived" else "already resolved" for i in reopened})
            raise Refused("validation", " / ".join(words) + ": " + ", ".join(reopened),
                          hint="A closed finding cannot be reopened by status. Raise a new finding with "
                               "\"follows\": \"<id>\" for what remains.")
        if missing:
            raise Refused("validation", "give a status (open|resolved) for: " + ", ".join(missing))
        for f in prior:
            if status[f["id"]] == "resolved":
                result.append(dict(f, status="resolved"))
            else:
                r = response_of(doc, f["target"], f["id"]) or None
                disputed = (r or "").startswith("disputed:") and N.get(f["target"], {}).get("kind") == "agent"
                tf, ta = fence(f["target"])
                result.append(dict(f, response=r, rounds=f["rounds"] + (1 if disputed else 0), target_fp=tf,
                                   target_attempt=ta))
    else:
        for f in given:
            if "id" in f:
                raise Refused("validation", "only review nodes give prior findings a status")
            if "follows" in f:
                raise Refused("validation", "only review nodes give a finding `follows`")
    new = [f for f in given if "id" not in f]
    for f in new:
        if "follows" not in f:
            continue
        fid = f["follows"]
        if fid not in latest or latest[fid]["target"] == X:
            raise Refused("validation", f"follows: {fid} is not a finding of {X}'s previous review")
        if latest[fid]["status"] == "open" and status.get(fid) != "resolved":
            raise Refused("validation", f"follows: {fid} is still open; resolve it, and let the new finding carry "
                                        "what remains")
    anc = graph.ancestors(X)
    skip = doc.get("skip") or {}
    for k, f in enumerate(new, 1):
        followed = latest.get(f["follows"]) if "follows" in f else None
        T = f.get("target") or (followed["target"] if followed else None) or graph.subject(X)
        if not T or T == X or T not in anc or T in skip:
            raise Refused("validation", f"finding target {T!r} must be a non-skipped ancestor of {X}")
        tf, ta = fence(T)
        rounds = 1
        if followed and followed["target"] == T:
            # the same defect continued: keep its dispute count (never `upheld`: the human never saw this text)
            r = response_of(doc, T, followed["id"]) or followed.get("response") or ""
            rounds = followed["rounds"] + (1 if r.startswith("disputed:") and N.get(T, {}).get("kind") == "agent"
                                           else 0)
        nf = {"id": f"{X}:{attempt}:{k}", "target": T, "target_fp": tf, "target_attempt": ta,
              "text": f["text"], "status": "open", "response": None, "rounds": rounds, "upheld": False, "note": None}
        if followed:
            nf["follows"] = followed["id"]
        if graph.filter_of(X):
            if f["material"] is False and is_owner_question(f):
                raise Refused("validation", "an owner question is always material: set material: true")
            nf.update(impact=f["impact"], material=f["material"])
        if graph.lens_defs(X):
            nf["lens"] = f["lens"]
        result.append(nf)
    if graph.is_review(X):
        ok = decision == "approved"
        if graph.filter_of(X):             # a filtered lens may approve with notes (`material: false`)
            if ok and any(f["status"] == "open" and is_material(f) for f in result):
                raise Refused("validation", "approved requires no open material finding; "
                              "a lens may approve with notes (material: false)")
        elif ok and any(f["status"] == "open" for f in result):
            raise Refused("validation", "approved requires no open findings")
        if not ok and not any(f["status"] == "open" for f in result):
            raise Refused("validation", "changes_requested requires an open finding")
        if graph.filter_of(X):
            ok = True                      # a filtered lens's findings are candidates: the subject reopens instead
    else:
        ok = True
    return result, ok


def human_findings(graph: Graph, X: str, r0: dict | None, given: list, attempt: int, decision: str, quote: str, fence,
                   skip=()) -> list:
    """A human review answer (SPEC §4.15)."""
    result = [dict(f, status="resolved") for f in ((r0 or {}).get("findings") or []) if f["status"] == "open"]
    new = list(given or [])
    if decision == "changes_requested" and not new:
        new = [{"text": quote}]
    anc = graph.ancestors(X)
    for k, f in enumerate(new, 1):
        T = f.get("target") or graph.subject(X)
        if T not in anc or T == X or T in skip:
            raise Refused("validation", f"finding target {T!r} must be a non-skipped ancestor of {X}")
        tf, ta = fence(T)
        result.append({"id": f"{X}:{attempt}:{k}", "target": T, "target_fp": tf, "target_attempt": ta,
                       "text": f["text"], "status": "open", "response": None, "rounds": 1, "upheld": False, "note": None})
    return result


# Only known temporary namespaces identify random filename components. Ordinary
# command/test basenames, including eight-letter suffixes, remain significant.
TEMP_NAME = re.compile(
    r"(?P<prefix>[/\\](?:tmp|temp|Temp|T)[/\\]tmp|(?<![\w.-])"
    r"(?:zzzops-card-budget-|zzzops-claude-acceptance-|\.zzzops-cleanup-|\.legacy-))"
    r"[a-z0-9_]{8}(?=$|[/\\.\s'\":])")
NORM = re.compile(r"0[xX][0-9a-fA-F]+|[0-9a-fA-F]{7,}|[0-9]+(?:\.[0-9]+)?")


def norm(text: str) -> str:
    text = TEMP_NAME.sub(lambda m: m.group("prefix") + "#", text)
    return NORM.sub("#", text)


def op_findings(graph: Graph, doc: dict, X: str, r0: dict | None, raised: list, producers: dict, input_fp: str,
                fence) -> list:
    """Op findings: `raised` = [{"key", "input", "text"}] -> findings with fixed ids (SPEC §4.14, §5.1)."""
    prev = {f["id"]: f for f in ((r0 or {}).get("findings") or [])}
    out = []
    for item in raised:
        fid = op_finding_id(X, item["key"])
        T = producers.get(item["input"])
        if T is None:
            raise Refused("engine_bug", f"op finding {fid} names input {item['input']!r}, which has no producer")
        p = prev.get(fid)
        r = response_of(doc, T, fid)
        text = item["text"][:4096]
        same = p is not None and norm(p["text"]) == norm(text)
        rounds = 2 if graph.nodes[T]["kind"] == "agent" and r and same else 1
        repeats = (p.get("repeats", 1) + 1) if p and p["status"] == "open" and p.get("carrier_fp") == input_fp else 1
        tf, ta = fence(T)
        out.append({"id": fid, "target": T, "target_fp": tf, "target_attempt": ta, "text": text,
                    "status": "open", "response": r if rounds == 2 else None, "rounds": rounds,
                    "upheld": p["upheld"] if p and same else False, "note": p["note"] if p else None,
                    "repeats": repeats, "carrier_fp": input_fp})
    return out


def auto_responses(graph: Graph, X: str, corrections: list, decided_by: str | None = None) -> dict:
    """Responses for nodes that cannot write prose (SPEC §4.14)."""
    kind = graph.nodes[X]["kind"]
    if kind == "op":
        text = f"fixed: re-run by {graph.nodes[X]['op']}"
    elif kind == "human":
        text = f"fixed: re-answered by {decided_by}"
    else:
        return {}
    return {f["id"]: text for f in corrections}


def blocked_repeats(r0: dict | None, waiting_for: str, reason: str) -> int:
    if r0 and r0["status"] == "blocked":
        b = r0["blocked"]
        if b["waiting_for"] == waiting_for and (waiting_for == "agent" or b["reason"] == reason):
            return b.get("repeats", 1) + 1
    return 1


def record(status: str, ok: bool, attempt: int, holder: str, reason: str, r0: dict | None, input_fp: str,
           fp_parts: dict, output, findings: list, now: int, prompt: str | None = None, **extra) -> dict:
    rec = {"status": status, "ok": ok, "attempt": attempt, "holder": holder, "reason": reason,
           "correction_runs": (r0["correction_runs"] if r0 else 0) + counts(r0, reason, r0 and r0.get("fp_parts"), fp_parts),
           "input_fp": input_fp, "fp_parts": fp_parts, "output": output, "findings": findings, "finished_at": iso(now)}
    if prompt:
        rec["prompt"] = prompt
    rec.update({k: v for k, v in extra.items() if v is not None})
    return rec


def reviewed(graph: Graph, doc: dict, X: str, fresh: bool = True) -> dict | None:
    """A review record's `reviewed`: the subject's checkpoints and artifacts at review time. Nothing for a stale
    submit (`fresh` false): the subject may have moved past the version the reviewer read."""
    subj = graph.subject(X)
    if not subj or not fresh:
        return None
    r = (doc.get("records") or {}).get(subj)
    if not r or r["status"] != "done":
        return None
    out = {}
    for k in graph.checkpoint_outputs(subj):
        v = (r["output"] or {}).get(k)
        if isinstance(v, dict):
            out[k] = {"commit": v["commit"], "base": v["base"], "tree": v["tree"], "change": v["change"]}
    for k in graph.artifact_outputs(subj):
        v = (r["output"] or {}).get(k)
        if isinstance(v, dict) and v.get("blob"):
            out[k] = {"blob": v["blob"], "commit": v.get("commit")}
    return out or None


# --------------------------------------------------------------------------------------------- suggested checkpoint


class GitView:
    """The ancestry questions suggested_checkpoint asks; the verbs answer them with Git, tests with a dict."""

    def is_ancestor(self, a: str, b: str) -> bool:
        raise NotImplementedError

    def committed_since(self, work: str, head: str) -> bool:
        """Whether work..head holds any commit other than docs(review): commits."""
        raise NotImplementedError


def suggested_checkpoint(graph: Graph, doc: dict, X: str, k: str, r0: dict | None, lease_work: str | None,
                         lease_parts: dict, base_value: str | None, head: str, git: GitView) -> str | None:
    """SPEC §4.20 suggested checkpoint, computed at submit (H30), including the no-commit rule (H26).

    Returns the suggestion (the default checkpoint), or None for HEAD; raises checkpoint_required."""
    from engine.fingerprint import stale_keys
    if not r0 or r0["status"] != "done" or not isinstance((r0.get("output") or {}).get(k), dict):
        return None
    c = r0["output"][k]["commit"]
    records = doc.get("records") or {}
    base_sel = graph.selectors[X].get("base")
    bprod = base_sel.producer if base_sel else None
    br = records.get(bprod) if bprod else None
    maps = ((br or {}).get("output") or {}) if br and br["status"] == "done" else {}
    moved = r0["output"][k].get("base") != base_value
    nocommit = bool(lease_work) and not git.committed_since(lease_work, head)
    hint = ("this phase added no commit; name the checkpoint: {\"%s\": {\"commit\": \"<full 40-hex sha>\"}}, your rebased "
            "checkpoint commit, or the base commit when the rebase dropped your commits as already applied" % k)
    if nocommit:
        if moved:
            sug = (maps.get("replay_map") or {}).get(c) or (maps.get("replay_pos") or {}).get(c)
            if not sug:
                raise Refused("checkpoint_required", f"{X}'s previous checkpoint {c[:7]} was rewritten by the restack",
                              hint=hint)
        else:
            sug = c
        if not (sug == head or git.is_ancestor(sug, head)):
            raise Refused("checkpoint_required", f"{X}'s previous checkpoint {sug[:7]} is not in HEAD", hint=hint)
    else:
        if "inputs.base" not in stale_keys(r0.get("fp_parts"), lease_parts):
            return None
        sug = (maps.get("replay_map") or {}).get(c) or (maps.get("replay_pos") or {}).get(c)
        if not sug or not (sug == head or git.is_ancestor(sug, head)):
            return None
    for name, sel in graph.selectors[X].items():
        spec = graph.nodes[X]["inputs"][name]
        if sel is None or sel.kind != "node" or spec.get("context"):
            continue
        p = sel.node
        pr = records.get(p)
        for pk in graph.checkpoint_outputs(p):
            if pr and pr["status"] == "done" and isinstance((pr.get("output") or {}).get(pk), dict):
                pc = pr["output"][pk]["commit"]
                if not (pc == sug or git.is_ancestor(pc, sug)):
                    return None
    return sug
