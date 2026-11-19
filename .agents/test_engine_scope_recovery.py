"""G1049 recovery contract against real Git goal histories and CLI CAS edits."""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest

import engine_fixtures as fx
from engine import identity, store
from test_engine_conventional import checkpoint_workflow


CAP = "preserved_test_provenance"


class RecoveryJourney(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.w.bootstrap(workflow=checkpoint_workflow())
        self.a = fx.Agent(self.w, "a", "codex:aaaa/tester")
        self.b = fx.Agent(self.w, "b", "codex:bbbb/reviewer")
        self.g = self.w.new(title="Historical lost scope")["created"]["id"]
        self.w.ok("a", "start", str(self.g), "base", "--as", "codex:aaaa/op")
        self.wt = self.a.worktree(self.g)
        self.paths = [f"tests/case_{i:02}.py" for i in range(13)]
        card = self.a.start(self.g, "test_design")
        self.wt.commit({p: f"assert {i} == {i}\n" for i, p in enumerate(self.paths)}, "test: accepted scope")
        self.a.submit(self.g, "test_design", card, {"commands": ["true"]})
        c = self.b.start(self.g, "review_tests")
        self.b.submit(self.g, "review_tests", c,
                      {"decision": "approved", "summary": "Reviewed", "findings": []}, artifact="Reviewed.\n")
        self.accepted = self.show()["goal"]["records"]["test_design"]
        self.accepted_tip = self.tip()

    def show(self):
        return self.w.ok("a", "show", str(self.g), "--json")

    def tip(self):
        return self.w.remote_git("rev-parse", f"refs/heads/zzzops/goal/g{self.g}")

    def synthesize_legacy_record(self, parent, record):
        """Append legacy state to the throwaway remote, preserving immutable parents.

        This simulates a historical older writer even after the tested engine has
        been fixed; all production reads and edits use the CLI against real refs.
        """
        clone = self.w.clones["a"]
        clone.git("fetch", "-q", "origin", f"refs/heads/zzzops/goal/g{self.g}")
        doc = json.loads(clone.git("show", f"{parent}:goal.json"))
        doc["records"]["test_design"] = record
        git = fx.engine_git(clone)
        message = store.with_trailers(store.goal_message("submit", self.g, "legacy fixture", "open", "test_design"),
                                      doc, self.w.policy["settings"])
        commit = store.goal_commit(git, doc, parent, message)
        clone.git("push", "-q", "origin", f"{commit}:refs/heads/zzzops/goal/g{self.g}")
        return commit

    def damaged_history(self, final_status="blocked"):
        self.w.ok("a", "reopen", str(self.g), "test_design", "--note", "prior review finding")
        card = self.a.start(self.g, "test_design")
        self.a.submit(self.g, "test_design", card,
                      blocked={"waiting_for": "agent", "instructions": "retry"})
        current = self.show()["goal"]["records"]["test_design"]
        current.pop("frozen", None)
        first_block = self.synthesize_legacy_record(self.tip(), current)
        subset = copy.deepcopy(self.accepted)
        subset["attempt"] = current["attempt"] + 1
        subset["frozen"] = self.paths[:2]
        cp = subset["output"]["tests"]
        cp["change"] = identity.Identity(fx.engine_git(self.wt)).change(cp["base"], cp["commit"], paths=subset["frozen"])
        partial_done = self.synthesize_legacy_record(first_block, subset)
        if final_status == "done":
            return partial_done
        current["attempt"] += 2
        return self.synthesize_legacy_record(partial_done, current)

    def diagnostic(self):
        result = self.w.ok("a", "validate", str(self.g))
        self.assertIn("scope_recovery", result, "validate must expose the additive recovery contract")
        diagnostics = result["scope_recovery"][str(self.g)]
        self.assertEqual(1, len(diagnostics), result)
        return diagnostics[0]

    def test_unaffected_goal_offers_no_recovery(self):
        result = self.w.ok("a", "validate", str(self.g))
        self.assertEqual([], result.get("scope_recovery", {}).get(str(self.g)), result)

    def test_thirteen_to_two_history_has_read_only_path_provenance_and_cas_proposal(self):
        damaged_tip = self.damaged_history()
        old = self.w.remote_git("show", f"{self.accepted_tip}:goal.json")
        diag = self.diagnostic()
        self.assertEqual(damaged_tip, self.tip(), "validate must not mutate the goal")
        self.assertEqual(("test_design", "proposal", damaged_tip, "blocked"),
                         (diag["producer"], diag["status"], diag["goal_commit"], diag["producer_state"]))
        self.assertEqual(self.paths, [p["path"] for p in diag["paths"]])
        for path in diag["paths"]:
            self.assertTrue(path["sources"])
            for source in path["sources"]:
                self.assertEqual(40, len(source["goal_commit"]))
                self.assertIsInstance(source["attempt"], int)
                self.assertEqual(40, len(source["checkpoint"]))
                self.assertEqual(40, len(source["checkpoint_base"]))
        proposal = diag["proposal"]
        self.assertEqual(damaged_tip, proposal["base"])
        self.assertEqual(self.paths, proposal["edit"]["set"]["records.test_design.frozen"])
        preview = self.w.ok("a", "edit", str(self.g), "--file", self.w.file(proposal["edit"]))
        self.assertFalse(preview["applied"])
        self.assertEqual(damaged_tip, self.tip())
        self.assertEqual(old, self.w.remote_git("show", f"{self.accepted_tip}:goal.json"))

    def test_done_checkpoint_is_not_silently_widened_without_identity_correction(self):
        tip = self.damaged_history(final_status="done")
        diag = self.diagnostic()
        self.assertEqual(tip, diag["goal_commit"])
        if diag["status"] == "uncertain":
            self.assertIsNone(diag["proposal"])
            self.assertTrue(diag["issues"])
        else:
            sets = diag["proposal"]["edit"]["set"]
            self.assertEqual(self.paths, sets["records.test_design.frozen"])
            self.assertTrue(any("change" in key or "output" in key for key in sets), sets)

    def activate_capability(self):
        policy = copy.deepcopy(self.w.policy)
        policy["settings"]["engine"]["requires"].append(CAP)
        self.w.push_dev({".zzzops/POLICY.json": json.dumps(policy, indent=2) + "\n"})

    def test_apply_proposal_requires_capability_and_retains_test_history(self):
        self.damaged_history()
        diag = self.diagnostic()
        proposal = diag["proposal"]
        old_tip = self.tip()
        payload = self.w.file(proposal["edit"])
        rc, out = self.w.run("a", "edit", str(self.g), "--file", payload, "--base", proposal["base"])
        self.assertNotEqual(0, rc, out)
        self.assertEqual(old_tip, self.tip())
        self.activate_capability()
        applied = self.w.ok("a", "edit", str(self.g), "--file", payload, "--base", proposal["base"])
        self.assertTrue(applied["applied"])
        self.assertEqual(self.paths, self.show()["goal"]["records"]["test_design"]["frozen"])
        self.assertEqual([], self.w.ok("a", "validate", str(self.g))["scope_recovery"][str(self.g)])
        card = self.a.start(self.g, "test_design")
        responses = {f["id"]: "disputed: preserved accepted tests" for f in card.get("corrections", [])}
        self.a.submit(self.g, "test_design", card, {"commands": ["true"], "responses": responses})
        self.assertEqual(self.paths, self.show()["goal"]["records"]["test_design"]["frozen"])
        states = self.show()["states"]
        self.assertTrue(states["review_tests"].startswith("ready"), states)
        review = self.b.start(self.g, "review_tests")
        previous = [{"id": f["id"], "status": "resolved"} for f in
                    (review.get("previous") or {}).get("findings", []) if f["status"] == "open"]
        self.b.submit(self.g, "review_tests", review,
                      {"decision": "approved", "summary": "Reviewed restored scope", "findings": previous},
                      artifact="Reviewed all protected paths.\n")
        implement = self.a.start(self.g, "implement")
        for path in self.paths:
            self.wt.commit({path: "assert False\n"}, "fix: weaken protected test")
            rc, out = self.a.submit(self.g, "implement", implement, {"summary": "Try"}, ok=False)
            self.assertNotEqual(0, rc, out)
            self.assertEqual("test_freeze", out["error"]["code"])
            self.wt.git("reset", "--hard", "HEAD^")

    def test_stale_goal_base_refuses_recovery_without_writes(self):
        self.damaged_history()
        proposal = self.diagnostic()["proposal"]
        self.activate_capability()
        self.w.ok("a", "edit", str(self.g), "--set", 'priority="P1"', "--base", proposal["base"])
        changed = self.tip()
        rc, out = self.w.run("a", "edit", str(self.g), "--file", self.w.file(proposal["edit"]),
                             "--base", proposal["base"])
        self.assertNotEqual(0, rc, out)
        self.assertEqual(changed, self.tip())

    def test_live_producer_lease_refuses_a_previously_valid_proposal(self):
        self.damaged_history()
        proposal = self.diagnostic()["proposal"]
        self.activate_capability()
        self.a.start(self.g, "test_design")
        before = self.tip()
        rc, out = self.w.run("a", "edit", str(self.g), "--file", self.w.file(proposal["edit"]),
                             "--base", proposal["base"])
        self.assertNotEqual(0, rc, out)
        self.assertEqual(before, self.tip())

    def test_unavailable_checkpoint_in_history_is_uncertain(self):
        self.damaged_history()
        bad = copy.deepcopy(self.accepted)
        bad["attempt"] += 5
        bad["frozen"] = self.paths[:2]
        bad["output"]["tests"]["commit"] = "f" * 40
        self.synthesize_legacy_record(self.tip(), bad)
        diag = self.diagnostic()
        self.assertEqual("uncertain", diag["status"])
        self.assertIsNone(diag["proposal"])
        self.assertTrue(diag["issues"])

    def test_unrelated_paths_in_modified_proposal_are_refused(self):
        self.damaged_history()
        diag = self.diagnostic()
        self.assertEqual("proposal", diag["status"])
        proposal = copy.deepcopy(diag["proposal"])
        self.activate_capability()
        proposal["edit"]["set"]["records.test_design.frozen"].append("src/unrelated.py")
        before = self.tip()
        rc, result = self.w.run("a", "edit", str(self.g), "--file", self.w.file(proposal["edit"]),
                                "--base", proposal["base"])
        self.assertNotEqual(0, rc, result)
        self.assertEqual(before, self.tip())


if __name__ == "__main__":
    unittest.main()
