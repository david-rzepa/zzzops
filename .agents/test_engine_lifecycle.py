"""Step 5: leases, submit and answer through the CLI (SPEC §4.12, §4.14, §4.15; DESIGN §10 items 6, 11, 16, 19, 26)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import unittest

import engine_fixtures as fx

LONG = 120 * 60 + 1


class Journey(unittest.TestCase):
    """A world with the stub-op graph and two agents (two clones, different holder labels)."""
    renamed = False

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        wf = fx.stub_ops_workflow()
        self.m = {n: n for n in fx.DEFAULT_NODES}
        if self.renamed:
            wf = fx.renamed_workflow(wf)
            self.m = fx.RENAME
        self.w.bootstrap(workflow=wf)
        self.A = fx.Agent(self.w, "a", "claude:aaaa/w-1")
        self.B = fx.Agent(self.w, "b", "codex:bbbb/w-2")

    def n(self, x):
        return self.m[x]

    def goal(self, **kw):
        return self.w.new(title="Cut", **kw)["created"]["id"]

    def item(self, out, node):
        return next(i for i in out["needs_human"] if i["node"] == self.n(node))

    def approve(self, g, node, clone="a", decision="approved", **extra):
        out = self.w.ok(clone, "next", "--goal", str(g))
        it = self.item(out, node)
        ans = dict({"decision": decision, "summary": "s", "quote": "yes", "decided_by": "Dave"}, **extra)
        return self.w.ok(clone, "answer", str(g), self.n(node), "--fp", it["fp"], "--file", self.w.file(ans))

    def review(self, agent, g, node, decision="approved", findings=None):
        c = agent.start(g, self.n(node))
        prior = [{"id": f["id"], "status": "resolved"} for f in (c.get("previous") or {}).get("findings", [])
                 if f["status"] == "open"]
        out = {"decision": decision, "summary": "review", "findings": prior + (findings or [])}
        return agent.submit(g, self.n(node), c, out, artifact="# review\n")

    def through_design(self, g):
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "Design."}, artifact="# Design\n")
        self.review(self.B, g, "review_design")
        self.approve(g, "approve_design")
        c = self.A.start(g, self.n("base"))
        self.A.submit(g, self.n("base"), c, {"base_commit": self.w.remote_git("rev-parse", "dev"), "stack": [],
                                             "branch": f"zzzops/work/g{g}"})

    def through_tests(self, g):
        self.through_design(g)
        c = self.A.start(g, self.n("test_design"))
        self.A.worktree(g).commit({"tests/test_cut.py": "def test_cut():\n    assert cut() == 1\n"}, "test: cut")
        self.A.submit(g, self.n("test_design"), c, {"commands": ["python -m pytest tests"]})
        self.review(self.B, g, "review_tests")

    def through_impl(self, g):
        self.through_tests(g)
        c = self.A.start(g, self.n("implement"))
        self.A.worktree(g).commit({"src/cut.py": "def cut():\n    return 1\n"}, "feat: cut")
        self.A.submit(g, self.n("implement"), c, {"summary": "Built."})
        c = self.A.start(g, self.n("run_tests"))
        self.A.submit(g, self.n("run_tests"), c, {"result": {"passed": True}})

    def show(self, g):
        return self.w.ok("b", "show", str(g), "--json")


class LeaseTests(Journey):
    def test_two_claims_in_the_same_second_have_one_winner(self):
        g = self.goal()
        results = []
        threads = [threading.Thread(target=lambda ag=ag: results.append(ag.start(g, self.n("design"), ok=False)))
                   for ag in (self.A, self.B)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        codes = sorted(rc for rc, _ in results)
        self.assertEqual([0, 3], codes, results)
        lost = [o for rc, o in results if rc == 3][0]
        self.assertEqual("claim_lost", lost["error"]["code"])

    def test_renew_by_attempt_then_submit(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        for i in range(5):
            r = self.w.ok("a", "renew", str(g), self.n("design"), "--attempt", "1", now=fx.NOW + 600 * (i + 1))
            self.assertEqual(30, r["renew_every_minutes"])
        # still live long after the claim, because renewals moved last_active
        out = self.w.ok("b", "next", now=fx.NOW + 3000 + 60)
        self.assertEqual([self.n("design")], [x["node"] for x in out["running"]])
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")

    def test_reclaim_uses_the_lease_own_timeout(self):
        g = self.goal()
        self.A.start(g, self.n("design"))
        # a later policy edit shortens the default; the lease keeps its recorded 120 minutes
        p = json.loads(json.dumps(self.w.policy))
        p["settings"]["leases"]["ttl_minutes"] = 10
        self.w.push_dev({".zzzops/POLICY.json": json.dumps(p, indent=2)})
        out = self.w.ok("b", "next", now=fx.NOW + 30 * 60)
        self.assertEqual(1, len(out["running"]))
        out = self.w.ok("b", "next", now=fx.NOW + LONG)
        self.assertEqual("reclaim", out["actions"][0]["reason"])
        rc, err = self.B.start(g, self.n("design"), ok=False) if False else self.w.run("b", "start", str(g), self.n("design"), "--as", self.B.label, now=fx.NOW + LONG)
        self.assertEqual("not_ready", err["error"]["code"])
        out = self.w.ok("b", "start", str(g), self.n("design"), "--as", self.B.label, "--reclaim", now=fx.NOW + LONG)
        self.assertEqual((2, "reclaim"), (out["lease"]["attempt"], out["reason"]))

    def test_abandon_then_late_submit_is_superseded(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        self.w.ok("a", "abandon", str(g), self.n("design"), "--attempt", "1")
        rc, err = self.A.submit(g, self.n("design"), c, {"summary": "late"}, artifact="# x\n", ok=False)
        self.assertEqual((3, "superseded"), (rc, err["error"]["code"]))
        self.assertIn("abandoned", err["error"]["message"])
        rc, err = self.w.run("a", "renew", str(g), self.n("design"), "--attempt", "1")
        self.assertEqual("superseded", err["error"]["code"])
        out = self.w.ok("b", "next")
        self.assertEqual("reclaim", out["actions"][0]["reason"])
        c2 = self.w.ok("b", "start", str(g), self.n("design"), "--as", self.B.label, "--reclaim")
        self.assertEqual(2, c2["lease"]["attempt"])

    def test_submit_after_reclaim_is_fenced(self):
        g = self.goal()
        self.through_design(g)
        c = self.A.start(g, self.n("test_design"))
        self.A.worktree(g).commit({"tests/t.py": "x = 1\n"}, "test: t")
        goal_tip = self.w.remote_git("rev-parse", f"refs/heads/zzzops/goal/g{g}")
        self.w.ok("b", "start", str(g), self.n("test_design"), "--as", self.B.label, "--reclaim", "--force")
        rc, err = self.A.submit(g, self.n("test_design"), c, {"commands": ["t"]}, ok=False)
        self.assertEqual((3, "superseded"), (rc, err["error"]["code"]))
        self.assertIn("zzzops-salvage", err["error"]["hint"])
        self.assertEqual(goal_tip, self.w.remote_git("rev-parse", f"refs/heads/zzzops/goal/g{g}"))
        self.assertTrue(os.path.exists(os.path.join(self.A.worktree(g).path, "tests", "t.py")))

    def test_lost_response_is_applied_only_for_the_same_holder(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        again = self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        self.assertTrue(again["applied"])
        other = fx.Agent(self.w, "a", "claude:cccc/w-3")
        rc, err = other.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n", ok=False)
        self.assertEqual("superseded", err["error"]["code"])

    def test_server_rule_refusal_is_push_refused(self):
        g = self.goal()
        hook = os.path.join(self.w.remote, "hooks", "pre-receive")
        with open(hook, "w") as fh:
            fh.write("#!/bin/sh\nwhile read old new ref; do case $ref in refs/heads/zzzops/goal/*) "
                     "echo 'rule: goals are protected' >&2; exit 1;; esac; done\nexit 0\n")
        os.chmod(hook, 0o755)
        c = self.A.start(g, self.n("design"))
        rc, err = self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n", ok=False)
        self.assertEqual((2, "push_refused"), (rc, err["error"]["code"]))

    def test_orphan_unparsable_and_future_leases(self):
        g = self.goal()
        s = self.w.seed
        bad = s.git("commit-tree", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", "-m", "garbage")
        s.git("push", "-q", "origin", f"{bad}:refs/heads/zzzops/lease/g{g}/design")
        out = self.w.ok("b", "next")
        self.assertIn("orphan_lease", [x["kind"] for x in out["warnings"]])
        self.assertEqual([self.n("design")], [a["node"] for a in out["actions"]] if not self.renamed else [self.n("design")])
        # a claim replaces the unparsable lease; a future-dated tip warns
        c = self.w.ok("a", "start", str(g), self.n("design"), "--as", self.A.label, now=fx.NOW + 3600)
        out = self.w.ok("b", "next")
        self.assertIn("clock_skew", [x["kind"] for x in out["warnings"]])

    def test_mass_expiry_requires_force(self):
        gs = [self.goal() for _ in range(3)]
        for g in gs:
            self.A.start(g, self.n("design"))
        later = fx.NOW + 10 * 3600
        out = self.w.ok("b", "next", now=later)
        self.assertIn("mass_expiry", [x["kind"] for x in out["warnings"]])
        self.assertTrue(all(a.get("requires_force") for a in out["actions"]))
        rc, err = self.w.run("b", "start", str(gs[0]), self.n("design"), "--as", self.B.label, "--reclaim", now=later)
        self.assertEqual("mass_expiry", err["error"]["code"])
        self.w.ok("b", "start", str(gs[0]), self.n("design"), "--as", self.B.label, "--reclaim", "--force", now=later)

    def test_independence_and_held_goal(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        rc, err = self.A.start(g, self.n("review_design"), ok=False)
        self.assertEqual("independence", err["error"]["code"])
        tip = self.w.ok("b", "show", str(g), "--json")["goal_commit"]
        self.w.ok("b", "edit", str(g), "--set", 'state="held"', "--base", tip)
        rc, err = self.B.start(g, self.n("review_design"), ok=False)
        self.assertEqual("goal_held", err["error"]["code"])


class SubmitTests(Journey):
    def test_new_creates_no_branch_and_first_artifact_does(self):
        g = self.goal()
        refs = self.w.remote_git("for-each-ref", "--format=%(refname)")
        self.assertNotIn(f"zzzops/work/g{g}", refs)
        c = self.A.start(g, self.n("design"))
        self.assertIsNone(c["workspace"])
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        refs = self.w.remote_git("for-each-ref", "--format=%(refname)")
        self.assertIn(f"refs/heads/zzzops/work/g{g}", refs)
        self.assertFalse(os.path.exists(os.path.join(self.w.clones["a"].path, ".zzzops", "worktrees", f"g{g}")))

    def test_changes_requested_reopens_and_responses_are_required(self):
        g = self.goal()
        self.through_impl(g)
        out = self.review(self.B, g, "review_impl", "changes_requested", [{"text": "handle empty input"}])
        self.assertEqual([(self.n("implement"), "reopened")], [(a["node"], a["reason"]) for a in out["next"]["actions"]])
        c = self.A.start(g, self.n("implement"))
        self.A.worktree(g).commit({"src/cut.py": "def cut(x=None):\n    return 1\n"}, "fix: empty")
        rc, err = self.A.submit(g, self.n("implement"), c, {"summary": "Built."}, ok=False)
        self.assertEqual("validation", err["error"]["code"])
        self.assertIn("respond to", err["error"]["message"])
        fid = c["corrections"][0]["id"]
        self.A.submit(g, self.n("implement"), c, {"summary": "Built.", "responses": {fid: "fixed: handled"}})

    def test_dispute_reaches_reviewer_and_escalates(self):
        g = self.goal()
        self.through_impl(g)
        self.review(self.B, g, "review_impl", "changes_requested", [{"text": "rename cut"}])
        c = self.A.start(g, self.n("implement"))
        fid = c["corrections"][0]["id"]
        self.A.submit(g, self.n("implement"), c, {"summary": "Built.", "responses": {fid: "disputed: cut is the domain term"}})
        out = self.w.ok("b", "next", "--goal", str(g))
        self.assertIn((self.n("review_impl"), "not_ok"), [(a["node"], a["reason"]) for a in out["actions"]])
        c = self.B.start(g, self.n("review_impl"))
        self.assertEqual("disputed: cut is the domain term", c["previous"]["findings"][0]["response"])
        out = self.B.submit(g, self.n("review_impl"), c, {"decision": "changes_requested", "summary": "still",
                                                          "findings": [{"id": fid, "status": "open"}]}, artifact="r\n")
        item = [i for i in out["next"]["needs_human"] if i["kind"] == "dispute"][0]
        self.assertEqual(["uphold", "waive", "cancel the goal"], [o["label"] for o in item["options"]])
        ans = self.w.file({"finding": fid, "decision": "waive", "quote": "fine as is", "decided_by": "Dave"})
        self.w.ok("a", "answer", str(g), self.n("review_impl"), "--fp", item["fp"], "--file", ans)

    def test_test_freeze(self):
        g = self.goal()
        self.through_tests(g)
        c = self.A.start(g, self.n("implement"))
        self.A.worktree(g).commit({"src/cut.py": "def cut():\n    return 1\n",
                                   "tests/test_cut.py": "def test_cut():\n    assert True\n"}, "feat: cut (and weaken test)")
        rc, err = self.A.submit(g, self.n("implement"), c, {"summary": "Built."}, ok=False)
        self.assertEqual(("test_freeze", "tests/test_cut.py"), (err["error"]["code"], err["error"]["details"]["paths"][0]["path"]))

    def test_dispute_with_no_commit_keeps_tests_checkpoint(self):
        """H26: a reopened test_design that disputes and commits nothing keeps its tests; implement stays current."""
        g = self.goal()
        self.through_impl(g)
        before = self.show(g)["goal"]["records"][self.n("test_design")]["output"]["tests"]
        self.review(self.B, g, "review_impl", "changes_requested",
                    [{"target": self.n("test_design"), "text": "add an empty-input test"}])
        c = self.A.start(g, self.n("test_design"))
        fid = c["corrections"][0]["id"]
        self.A.submit(g, self.n("test_design"), c, {"commands": ["python -m pytest tests"],
                                                     "responses": {fid: "disputed: covered by test_cut"}})
        doc = self.show(g)
        after = doc["goal"]["records"][self.n("test_design")]["output"]["tests"]
        self.assertEqual(before["commit"], after["commit"])
        self.assertEqual(before["change"], after["change"])
        self.assertEqual("current", doc["states"][self.n("implement")])

    def test_checkpoint_required_after_a_base_move_with_no_commit(self):
        """H26: after a restack without a commit map, a no-commit re-run must name its checkpoint."""
        g = self.goal()
        self.through_impl(g)
        moved = self.w.push_dev({"other.txt": "1\n"})
        out = self.w.ok("a", "reopen", str(g), self.n("base"), "--note", "restack")
        # what git.base would do: rebase the goal's commits and push the rewritten work branch
        wtd = self.A.worktree(g)
        wtd.git("fetch", "-q", "origin")
        wtd.git("rebase", "-q", moved)
        wtd.git("push", "-q", "--force", "origin", f"HEAD:refs/heads/zzzops/work/g{g}")
        c = self.A.start(g, self.n("base"))
        self.A.submit(g, self.n("base"), c, {"base_commit": moved, "stack": [], "branch": f"zzzops/work/g{g}",
                                             "responses": {c["corrections"][0]["id"]: "fixed: restacked"}})
        c = self.A.start(g, self.n("test_design"))
        rc, err = self.A.submit(g, self.n("test_design"), c, {"commands": ["python -m pytest tests"]}, ok=False)
        self.assertEqual("checkpoint_required", err["error"]["code"], err)
        self.assertIn("base commit", err["error"]["hint"])
        tests_commit = wtd.git("log", "--format=%H", "-1", "--grep", "^test: cut")
        self.A.submit(g, self.n("test_design"), c, {"commands": ["python -m pytest tests"],
                                                     "tests": {"commit": tests_commit}})
        rec = self.show(g)["goal"]["records"][self.n("test_design")]["output"]["tests"]
        self.assertEqual((tests_commit, moved), (rec["commit"], rec["base"]))

    def test_card_shape_and_size(self):
        g = self.goal()
        self.through_tests(g)
        c = self.A.start(g, self.n("implement"))
        from engine.card import shrink_candidates
        n = len(json.dumps(c, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode())
        self.assertTrue(n <= 4096 or not shrink_candidates(c), n)
        for k in ("lease", "prompt", "instructions", "inputs", "context", "read_dev", "workspace", "commands",
                  "output_schema"):
            self.assertIn(k, c)
        argv = ["submit", str(g), self.n("implement"), "--attempt", "1", "--as", self.A.label, "--output", "<F>"]
        self.assertEqual("zzzops " + " ".join(argv), c["commands"]["submit"]["command"])
        if "argv" in c["commands"]["submit"]:
            self.assertEqual(argv, c["commands"]["submit"]["argv"])
        self.assertIsInstance(c["inputs"]["tests"], dict)
        self.assertIn("diff", c["inputs"]["tests"])


class AnswerTests(Journey):
    def test_fp_mismatch_and_retried_answer(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        self.review(self.B, g, "review_design")
        out = self.w.ok("a", "next", "--goal", str(g))
        it = self.item(out, "approve_design")
        ans = self.w.file({"decision": "approved", "summary": "s", "quote": "yes", "decided_by": "Dave"})
        rc, err = self.w.run("a", "answer", str(g), self.n("approve_design"), "--fp", "v1:sha256:" + "0" * 64, "--file", ans)
        self.assertEqual("fp_mismatch", err["error"]["code"])
        self.assertEqual(self.n("approve_design"), err["error"]["details"]["current"]["node"])
        self.w.ok("a", "answer", str(g), self.n("approve_design"), "--fp", it["fp"], "--file", ans)
        again = self.w.ok("a", "answer", str(g), self.n("approve_design"), "--fp", it["fp"], "--file", ans)
        self.assertTrue(again["applied"])

    def test_human_rejection_reopens_subject(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        self.review(self.B, g, "review_design")
        out = self.approve(g, "approve_design", decision="changes_requested", quote="simpler please")
        self.assertEqual([(self.n("design"), "reopened")], [(a["node"], a["reason"]) for a in out["next"]["actions"]])

    def test_blocked_for_a_human_then_answered(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        out = self.A.submit(g, self.n("design"), c, blocked={"waiting_for": "human", "question": "Which API?",
                                                              "options": ["REST", "gRPC"], "recommendation": "REST"})
        it = out["next"]["needs_human"][0]
        self.assertEqual(("blocked", "Which API?", "REST"), (it["kind"], it["question"], it["recommendation"]))
        ans = self.w.file({"text": "REST", "quote": "use REST", "decided_by": "Dave"})
        out = self.w.ok("a", "answer", str(g), self.n("design"), "--fp", it["fp"], "--file", ans)
        self.assertEqual([(self.n("design"), "retry")], [(a["node"], a["reason"]) for a in out["next"]["actions"]])
        c = self.A.start(g, self.n("design"))
        self.assertEqual("REST", c["answer"]["text"])


class RenamedSubmitTests(SubmitTests):
    renamed = True


if __name__ == "__main__":
    unittest.main()
