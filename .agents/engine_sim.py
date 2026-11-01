"""An in-memory driver of the pure engine core, for frontier tests (no Git).

It applies the shared record rules (engine.records) the way submit, answer and op finishes do, with fabricated
commit ids. It is a test aid, not a second engine: it keeps no state the real engine lacks."""

from __future__ import annotations

import copy
import hashlib

import engine_fixtures as fx
from engine import records as rec
from engine.canon import iso
from engine.fingerprint import out_fp
from engine.frontier import Lease, portfolio
from engine.schemas import build_graph


def fake_sha(seed) -> str:
    return hashlib.sha1(str(seed).encode()).hexdigest()


class Sim:
    def __init__(self, workflow=None, policy=None, now=1_800_000_000):
        self.workflow = copy.deepcopy(workflow or fx.load_template("workflow.json"))
        self.policy = copy.deepcopy(policy or fx.load_template("POLICY.json"))
        self.settings = self.policy["settings"]
        self.graphs = {n: build_graph(n, g) for n, g in self.workflow["graphs"].items()}
        self.docs, self.leases = {}, {}
        self.now = now
        self.counter = 0
        self.dev = fake_sha("dev-0")
        self.invalid, self.newer = {}, set()

    # ------------------------------------------------------------------ helpers
    def sha(self):
        self.counter += 1
        return fake_sha(self.counter)

    def tick(self, seconds=60):
        self.now += seconds

    def goal(self, gid, deps=(), skip=None, release=1, priority="P2", state="open", graph="default", budget=None):
        self.docs[gid] = {"schema": 1, "id": gid, "title": f"Goal {gid}", "graph": graph, "state": state,
                          "closed": None, "spec": f"spec {gid}", "priority": priority, "release": release,
                          "depends_on": list(deps), "skip": dict(skip or {}), "links": {"issue": None},
                          "budget": budget, "records": {}}
        return self.docs[gid]

    def eval(self):
        return portfolio(self.docs, self.graphs, self.leases, self.settings, self.now, self.invalid, self.newer)

    def st(self, g, n=None):
        res = self.eval().goals[g]
        return res.st if n is None else res.st[n]

    def names(self, g):
        return {n: s["name"] + (f"({s.get('reason') or s.get('kind') or ''})" if s["name"] in ("ready", "needs_human") else "")
                for n, s in self.st(g).items()}

    def graph(self, g):
        return self.graphs[self.docs[g]["graph"]]

    # ------------------------------------------------------------------ lifecycle
    def start(self, g, n, holder="claude:test/w-1"):
        s = self.st(g, n)
        assert s["name"] in ("ready", "reclaimable") or (s["name"] == "needs_human" and s["kind"] == "crash_loop"), (n, s)
        r = self.docs[g]["records"].get(n)
        old = self.leases.get((g, n))
        attempt = max(r["attempt"] if r else 0, old.attempt if old else 0) + 1
        reason = old.reason if s["name"] == "reclaimable" and old else s.get("reason", "retry")
        L = Lease(g, n, attempt, holder, reason, self.graph(g).nodes[n].get("timeout", 120), self.now, work=None,
                  input_fp=s["fp"], fp_parts=s["parts"], claimed_at=self.now if not old or s["name"] != "reclaimable"
                  else old.claimed_at)
        self.leases[(g, n)] = L
        return L

    def abandon(self, g, n):
        L = self.leases[(g, n)]
        L.timeout = 0
        L.last_active = self.now

    def _fence(self, g, n, L):
        x = self.st(g, n)
        x_fp = x.get("fp") if x["name"] in ("running", "reclaimable", "ready") else None
        return rec.make_fence(self.graph(g), self.docs[g], x_fp, L.input_fp, L.claimed_at)

    def _gen_outputs(self, g, n, same, provided):
        graph = self.graph(g)
        r0 = self.docs[g]["records"].get(n)
        prev = (r0 or {}).get("output") or {}
        out = {}
        from engine.frontier import recorded_out, resolve
        vals, _ = resolve(graph, self.docs[g], n, lambda p: recorded_out(self.docs[g], p),
                          self.eval().views)
        for k, t in (graph.nodes[n].get("outputs") or {}).items():
            if k in provided:
                out[k] = provided[k]
                continue
            if same and k in prev:
                out[k] = copy.deepcopy(prev[k])
                if t == "checkpoint":
                    out[k]["base"] = vals.get("base", out[k]["base"])
                continue
            if t == "checkpoint":
                out[k] = {"commit": self.sha(), "base": vals.get("base"), "tree": self.sha(), "change": self.sha()}
            elif t == "artifact":
                out[k] = {"path": f".zzzops/reviews/{g}/{n}.md", "blob": self.sha(), "commit": self.sha()}
            elif t == "sha":
                out[k] = self.sha()
            elif t == "strings":
                out[k] = ["make test"]
            elif t == "object":
                out[k] = {"v": self.sha()[:8]}
            elif t == "list":
                out[k] = []
            elif t in ("text", "string"):
                out[k] = f"{n} {k} {self.counter}"
            elif t == "int":
                out[k] = 1
            elif t == "bool":
                out[k] = True
        return out

    def submit(self, g, n, findings=(), decision=None, responses=None, same=False, outputs=None, summary=None):
        """An agent submit (review or not) on the live lease."""
        L = self.leases.pop((g, n))
        graph, doc = self.graph(g), self.docs[g]
        r0 = doc["records"].get(n)
        fence = self._fence_from(g, n, L)
        given = list(findings)
        if graph.is_review(n):
            out = {"decision": decision or ("changes_requested" if any("id" not in f for f in given) else "approved"),
                   "summary": summary or f"review {self.counter}"}
            out["report"] = {"path": f".zzzops/reviews/{g}/{n}.md", "blob": self.sha(), "commit": self.sha()}
        else:
            out = self._gen_outputs(g, n, same, outputs or {})
        if responses:
            out["responses"] = dict(responses)
        result, ok = rec.process_findings(graph, doc, n, r0, given, L.attempt, fence, out.get("decision"))
        doc["records"][n] = rec.record("done", ok, L.attempt, L.holder, L.reason, r0, L.input_fp, L.fp_parts, out,
                                       result, self.now, reviewed=rec.reviewed(graph, doc, n))
        self.tick()
        return doc["records"][n]

    def _fence_from(self, g, n, L):
        # the lease is popped; recompute the node's state with it present
        self.leases[(g, n)] = L
        try:
            return self._fence(g, n, L)
        finally:
            self.leases.pop((g, n))

    def blocked(self, g, n, waiting_for="agent", reason="stuck", **fields):
        L = self.leases.pop((g, n))
        doc = self.docs[g]
        r0 = doc["records"].get(n)
        b = {"category": fields.pop("category", "decision"), "waiting_for": waiting_for, "reason": reason,
             "repeats": rec.blocked_repeats(r0, waiting_for, reason)}
        if waiting_for == "agent":
            b["instructions"] = fields.pop("instructions", "try again")
        if waiting_for == "human":
            b["question"] = fields.pop("question", "what now?")
        if waiting_for == "time":
            b["retry_after"] = iso(self.now + fields.pop("delay", 300))
        b.update(fields)
        findings = list((r0 or {}).get("findings") or []) if self.graph(g).nodes[n]["kind"] == "op" else []
        doc["records"][n] = rec.record("blocked", False, L.attempt, L.holder, L.reason, r0, L.input_fp, L.fp_parts,
                                       None, findings, self.now, blocked=b)
        self.tick()
        return doc["records"][n]

    def op(self, g, n, ok=True, outputs=None, raised=(), same=False):
        """An op finish with a Done outcome. `raised`: [{"key", "input", "text"}]."""
        s = self.st(g, n)
        corr = s.get("corrections") or []
        L = self.start(g, n, holder="claude:test/op")
        graph, doc = self.graph(g), self.docs[g]
        r0 = doc["records"].get(n)
        fence = self._fence(g, n, L)
        self.leases.pop((g, n))
        out = self._gen_outputs(g, n, same, outputs or {})
        auto = rec.auto_responses(graph, n, corr)
        if auto:
            out["responses"] = auto
        producers = {k: sel.producer for k, sel in graph.selectors[n].items()}
        findings = rec.op_findings(graph, doc, n, r0, list(raised), producers, L.input_fp, fence)
        doc["records"][n] = rec.record("done", ok and not findings, L.attempt, L.holder, L.reason, r0, L.input_fp,
                                       L.fp_parts, out, findings, self.now)
        self.tick()
        return doc["records"][n]

    def answer(self, g, n, decision="approved", findings=(), quote="ok", decided_by="Dave"):
        s = self.st(g, n)
        assert s["name"] == "needs_human" and s["kind"] == "approve", s
        graph, doc = self.graph(g), self.docs[g]
        r0 = doc["records"].get(n)
        ready = s["ready"]
        attempt = (r0["attempt"] if r0 else 0) + 1
        fence = rec.make_fence(graph, doc, ready["fp"], ready["fp"], self.now)
        result = rec.human_findings(graph, n, r0, list(findings), attempt, decision, quote, fence,
                                    skip=doc.get("skip") or {})
        out = {"decision": decision, "summary": "s", "decided_by": decided_by, "quote": quote, "decided_at": iso(self.now)}
        auto = rec.auto_responses(graph, n, ready.get("corrections") or [], decided_by)
        if auto:
            out["responses"] = auto
        doc["records"][n] = rec.record("done", decision == "approved", attempt, "human", ready["reason"], r0,
                                       ready["fp"], ready["parts"], out, result, self.now,
                                       reviewed=rec.reviewed(graph, doc, n))
        self.tick()
        return doc["records"][n]

    def reopen(self, g, n, note="again"):
        doc = self.docs[g]
        r = doc["records"][n]
        for f in r["findings"]:
            if f["status"] == "open" and f["target"] != n:
                f["status"], f["note"] = "waived", f"withdrawn: {n} reopened ({note})"
        k = 1 + sum(1 for f in r["findings"] if f["id"].startswith(f"{n}:reopen:"))
        r["findings"].append({"id": f"{n}:reopen:{k}", "target": n, "target_fp": out_fp(self.graph(g), n, r),
                              "target_attempt": r["attempt"], "text": note, "status": "open", "response": None,
                              "rounds": 1, "upheld": False, "note": None})

    # ------------------------------------------------------------------ driving
    def step(self, g, n, **kw):
        """Run one ready node the default way: agents submit (reviews approve), humans approve, ops succeed."""
        s = self.st(g, n)
        kind = self.graph(g).nodes[n]["kind"]
        if kind == "human":
            return self.answer(g, n, **kw)
        if kind == "op":
            return self.op(g, n, **kw)
        self.start(g, n)
        corr = s.get("corrections") or []
        responses = kw.pop("responses", None)
        if responses is None and corr:
            responses = {f["id"]: "fixed: done" for f in corr}
        if self.graph(g).is_review(n) and "findings" not in kw:
            prior = [f for f in ((self.docs[g]["records"].get(n) or {}).get("findings") or [])
                     if f["status"] == "open" and f["target"] != n]
            kw["findings"] = [{"id": f["id"], "status": "resolved"} for f in prior]
        return self.submit(g, n, responses=responses, **kw)

    def actionable(self, g):
        st = self.st(g)
        return [n for n in self.graph(g).topo if st[n]["name"] == "ready"
                or (st[n]["name"] == "needs_human" and st[n]["kind"] == "approve")]

    def drive(self, g, until=None, limit=60):
        """Run every actionable node of g in topological order until `until` is current (or nothing is left)."""
        for _ in range(limit):
            if until and self.st(g, until)["name"] == "current":
                return True
            acts = self.actionable(g)
            if not acts:
                return until is None
            self.step(g, acts[0])
        raise AssertionError(f"G{g} did not settle: {self.names(g)}")
