"""Step 2: the no-dead-end property (DESIGN §10 item 8) over random portfolios built by random verb sequences.

ZZZOPS_LONG_TESTS=1 runs ten times as many sequences."""

from __future__ import annotations

import os
import random
import unittest

import engine_fixtures as fx
from engine_sim import Sim
from engine import render
from engine.canon import canonical, iso
from engine.errors import Refused
from engine.schemas import find_cycle

LONG = os.environ.get("ZZZOPS_LONG_TESTS") == "1"


def ctx(s):
    return render.Ctx(prefix="zzzops", now=s.now, settings=s.settings, coordinator={"commit": "c" * 40, "current": True},
                      goal_commits={g: "a" * 40 for g in s.docs})


def random_step(s: Sim, rng: random.Random):
    goals = [g for g, d in s.docs.items() if d["state"] in ("open", "held")]
    if not goals:
        return
    g = rng.choice(goals)
    doc = s.docs[g]
    roll = rng.random()
    if roll < 0.04 and doc["state"] == "open":
        doc["state"] = "held"
        return
    if roll < 0.07 and doc["state"] == "held":
        doc["state"] = "open"
        return
    if roll < 0.09:
        doc.update(state="closed", closed={"reason": "cancelled", "note": "n", "by": "t", "at": iso(s.now)})
        return
    if roll < 0.12:
        others = [x for x in s.docs if x != g and x not in doc["depends_on"]
                  and s.docs[x]["release"] <= doc["release"]]
        if others:
            old = doc["depends_on"]
            doc["depends_on"] = sorted(old + [rng.choice(others)])
            if find_cycle(s.docs, g):                                  # edit validation refuses cycles (§3.3 rule 4)
                doc["depends_on"] = old
        return
    if roll < 0.14 and doc["depends_on"]:
        doc["depends_on"] = doc["depends_on"][1:]
        return
    if roll < 0.16:
        graph = s.graph(g)
        cand = [n for n in graph.topo if n not in graph.terminal and n not in doc["skip"]]
        doc["skip"][rng.choice(cand)] = "random skip"
        return
    if roll < 0.18 and doc["skip"]:
        doc["skip"].pop(sorted(doc["skip"])[0])
        return
    if roll < 0.22:
        s.tick(rng.choice([60, 600, 7200, 9000]))
        return
    if roll < 0.24:
        s.dev = s.sha()                                             # dev moves: nothing in the sim reads it yet
        return
    if doc["state"] != "open":
        return
    st = s.st(g)
    graph = s.graph(g)
    cands = [n for n in graph.topo if st[n]["name"] in ("ready", "reclaimable", "needs_human")]
    if not cands:
        return
    n = rng.choice(cands)
    x = st[n]
    kind = graph.nodes[n]["kind"]
    try:
        if x["name"] == "needs_human" and x["kind"] == "approve":
            if rng.random() < 0.3:
                s.answer(g, n, decision="changes_requested", quote="change it")
            else:
                s.answer(g, n)
        elif x["name"] == "needs_human" and x["kind"] == "crash_loop":
            if x["cap"] == "lease":
                s.leases.pop((g, n), None)
            elif x["cap"] in ("repeat",):
                s.docs[g]["records"][n]["blocked"]["repeats"] = 1
            else:
                for f in s.docs[g]["records"][n]["findings"]:
                    f["repeats"] = 1
        elif x["name"] == "needs_human" and x["kind"] == "dispute":
            carrier, f = x["escalated"][0]
            f["upheld"] = True
        elif x["name"] == "needs_human" and x["kind"] == "blocked":
            r = s.docs[g]["records"][n]
            r["answer"] = {"text": "go", "quote": "go", "decided_by": "t", "decided_at": iso(s.now)}
            r["blocked"]["waiting_for"] = "agent"
            r["blocked"].setdefault("instructions", "The human answered: go")
        elif kind == "op":
            r = rng.random()
            if r < 0.15:
                ins = [k for k, sel in graph.selectors[n].items() if sel and sel.producer and graph.nodes[sel.producer]["kind"] != "human"]
                if ins:
                    s.op(g, n, ok=False, raised=[{"key": "k", "input": rng.choice(ins), "text": "failed"}])
            elif r < 0.25:
                s.start(g, n)
                s.blocked(g, n, "time", "pending", delay=rng.choice([60, 300]), category="external")
            elif r < 0.30:
                s.start(g, n)
                s.blocked(g, n, "human", "decide", category="external")
            else:
                s.op(g, n, same=rng.random() < 0.3)
        else:
            r = rng.random()
            s.start(g, n)
            if r < 0.06:
                s.abandon(g, n)
                return
            if r < 0.10:
                s.tick(130 * 60)                                       # the lease expires (crash path)
                return
            if r < 0.16:
                s.blocked(g, n, "agent", rng.choice(["a", "b"]))
                return
            if r < 0.20:
                s.blocked(g, n, "human", "q?")
                return
            corr = x.get("corrections") or []
            responses = {f["id"]: rng.choice(["fixed: ok", "disputed: no"]) for f in corr} if corr else None
            if graph.is_review(n):
                prior = [f for f in ((s.docs[g]["records"].get(n) or {}).get("findings") or [])
                         if f["status"] == "open" and f["target"] != n]
                given = [{"id": f["id"], "status": rng.choice(["open", "resolved"])} for f in prior]
                if rng.random() < 0.3:
                    anc = sorted(a for a in graph.ancestors(n) if a not in s.docs[g]["skip"] and a != n)
                    if anc:
                        given.append({"target": rng.choice(anc), "text": "fix this"})
                opened = any(f.get("status") == "open" or "text" in f for f in given)
                s.submit(g, n, findings=given, decision="changes_requested" if opened else "approved", responses=responses)
            else:
                s.submit(g, n, responses=responses, same=rng.random() < 0.3)
    except Refused:
        s.leases.pop((g, n), None)


def check_invariant(tc, s: Sim):
    p = s.eval()
    out = render.render_next(ctx(s), p, all_=True)
    tc.assertEqual(canonical(out), canonical(render.render_next(ctx(s), s.eval(), all_=True)))
    small = render.render_next(ctx(s), p)
    tc.assertLessEqual(len(canonical(small)), render.NEXT_LIMIT)
    shown = set()
    for key in ("actions", "needs_human", "waiting", "running"):
        shown |= {x["goal"] for x in out[key]}
    for g, res in p.goals.items():
        if res.doc["state"] != "open":
            continue
        tc.assertIn(g, shown, f"G{g} has no action, item, wait or running phase: {s.names(g)}")


class NoDeadEndPropertyTests(unittest.TestCase):
    def run_seeds(self, seeds, steps, renamed=False):
        for seed in seeds:
            rng = random.Random(seed)
            s = Sim(workflow=fx.renamed_workflow() if renamed else None)
            for g in range(1, rng.randint(2, 5) + 1):
                rel = rng.choice([1, 1, 1, 2])
                deps = [d for d in range(1, g) if rng.random() < 0.35 and s.docs[d]["release"] <= rel]
                s.goal(g, deps=deps, release=rel, priority=rng.choice(["P1", "P2"]),
                       budget=rng.choice([None, None, 2]))
            for _ in range(steps):
                random_step(s, rng)
                check_invariant(self, s)

    def test_random_portfolios(self):
        self.run_seeds(range(200 if LONG else 25), 80)

    def test_random_portfolios_renamed(self):
        self.run_seeds(range(1000, 1000 + (100 if LONG else 10)), 80, renamed=True)


if __name__ == "__main__":
    unittest.main()
