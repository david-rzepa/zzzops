"""Step 9: whole journeys (DESIGN §4.2, §10 items 3 and 25) on the default and on a fully renamed graph, driven by a
generic autopilot that reads only `next`, task cards and human items, never node names."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

import engine_fixtures as fx


class Autopilot:
    """Plays every agent and the human with default answers: reviewers approve, humans approve, ops run."""

    def __init__(self, w, gh):
        self.w, self.gh = w, gh
        self.agents = [fx.Agent(w, "a", "claude:aaaa/w-1"), fx.Agent(w, "b", "codex:bbbb/w-2")]
        self.turn = 0
        self.log = []
        self.preserved = {nd.get("preserve") for graph in w.workflow["graphs"].values()
                          for nd in graph["nodes"].values() if nd.get("preserve")}

    def agent_for(self, g, card_or_action):
        self.turn += 1
        return self.agents[self.turn % 2]

    def run_agent(self, g, node):
        for ag in self.agents:
            rc, card = ag.start(g, node, ok=False)
            if rc == 0:
                break
            if card.get("error", {}).get("code") != "independence":
                raise AssertionError(card)
        schema = card["output_schema"]
        out = {}
        if "decision" in schema:
            prior = [{"id": f["id"], "status": "resolved"} for f in (card.get("previous") or {}).get("findings", [])
                     if f["status"] == "open"]
            out = {"decision": "approved", "summary": f"{node} ok", "findings": prior}
        else:
            for k, t in schema.items():
                if k in ("findings", "responses"):
                    continue
                if t.startswith("checkpoint"):
                    if card["workspace"]:
                        wtd = fx.GitDir(card["workspace"], self.w.env)
                        kind = "test" if node in self.preserved else "feat"
                        wtd.commit({f"work/{node}.txt": f"{node} {self.turn}\n"}, f"{kind}: {node}")
                elif t == "strings":
                    out[k] = ["true"]
                elif t in ("text", "string"):
                    out[k] = f"{node} {k}"
        if card.get("corrections"):
            out["responses"] = {c["id"]: "fixed: done" for c in card["corrections"]}
        art = f"# {node}\n" if card.get("artifact") else None
        ag.submit(g, node, card, out, artifact=art)
        self.log.append(node)

    def answer(self, g, item):
        ans = {"decision": "approved", "summary": "approved", "quote": "yes", "decided_by": "Dave"}
        self.w.ok("a", "answer", str(g), item["node"], "--fp", item["fp"], "--file", self.w.file(ans))
        self.log.append(item["node"])

    def drive(self, goals, limit=120):
        for _ in range(limit):
            nxt = self.w.ok("a", "next")
            open_goals = [g for g in goals if self.w.ok("a", "show", str(g), "--json")["goal"]["state"] != "closed"]
            if not open_goals:
                return
            acted = False
            for item in nxt["needs_human"]:
                if item["goal"] in goals and item["kind"] == "approve":
                    full = self.w.ok("a", "next", "--goal", str(item["goal"]))
                    it = next(x for x in full["needs_human"] if x["node"] == item["node"] and x["kind"] == "approve")
                    self.answer(item["goal"], it)
                    acted = True
                    break
                if item["goal"] in goals:
                    raise AssertionError(f"unexpected human item: {item}")
            if acted:
                continue
            acts = [a for a in nxt["actions"] if a["goal"] in goals]
            if not acts:
                waits = [x for x in nxt["waiting"] if x["goal"] in goals]
                timed = [x for x in waits if x["until"][:2] == "20"]
                if timed and nxt["wake_at"]:
                    from engine.canon import parse_iso
                    self.w.now = max(self.w.now, parse_iso(nxt["wake_at"]))
                    continue
                raise AssertionError(f"no action for {open_goals}: {json.dumps(nxt)[:1500]}")
            a = acts[0]
            if a["kind"] == "op":
                self.w.ok("a", "start", str(a["goal"]), a["node"], "--as", "claude:aaaa/op")
                self.log.append(a["node"])
            else:
                self.run_agent(a["goal"], a["node"])
        raise AssertionError("journey did not finish: " + " ".join(self.log[-30:]))


class JourneyTests(unittest.TestCase):
    renamed = False

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.gh = fx.FakeGitHub(self.w)
        wf = fx.renamed_workflow() if self.renamed else None
        self.w.bootstrap(workflow=wf)
        self.pilot = Autopilot(self.w, self.gh)

    def test_capture_to_merge_with_a_stacked_dependent(self):
        """DESIGN §4.2: G1000, then G1001 depending on it, each from capture to merge."""
        a = self.w.new(title="Base feature")["created"]["id"]
        b = self.w.new(title="Dependent", depends_on=[a])["created"]["id"]
        self.pilot.drive([a, b])
        for g in (a, b):
            doc = self.w.ok("a", "show", str(g), "--json")["goal"]
            self.assertEqual(("closed", "done"), (doc["state"], doc["closed"]["reason"]))
        prs = self.gh.load()["prs"]
        self.assertTrue(all(p["state"] == "MERGED" and p["baseRefName"] == "dev" for p in prs.values()), prs)
        log = self.w.remote_git("log", "--format=%s", "dev")
        self.assertLess(log.index("#2"), log.index("#1"))
        # the work branches stay, so artifacts remain readable
        refs = self.w.remote_git("for-each-ref", "--format=%(refname)")
        self.assertIn(f"refs/heads/zzzops/work/g{a}", refs)

    def test_cost_of_next_and_ops(self):
        a = self.w.new(title="Cost")["created"]["id"]
        self.w.reset_trace()
        self.w.ok("a", "next")
        lines = self.w.trace_lines()
        self.assertEqual(1, len(lines))                       # one fetch, no gh
        self.pilot.drive([a])
        gh_calls = [c for c in self.gh.calls() if c[:1] == ["pr"]]
        self.assertLessEqual(len(gh_calls), 12, gh_calls)
        # item 2: costs cannot grow with archived comments, because nothing reads issues or comments
        for call in self.gh.calls():
            self.assertFalse(call[:2] in (["issue", "view"], ["issue", "list"]) or any("comments" in a for a in call), call)
            self.assertIn(call[0], ("pr", "run", "issue", "api", "auth"), call)
            if call[0] == "issue":
                self.assertEqual("close", call[1])


class RenamedJourneyTests(JourneyTests):
    renamed = True


if __name__ == "__main__":
    unittest.main()
