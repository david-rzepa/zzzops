"""G1049 recovery contract against real Git goal histories and CLI CAS edits."""
from __future__ import annotations

import copy
import json
import os
import shlex
import signal
from datetime import datetime, timezone
import subprocess
import sys
import time
from pathlib import Path
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
        workflow = checkpoint_workflow()
        artifact = copy.deepcopy(fx.load_template("workflow.json")["graphs"]["default"]["nodes"]["design"])
        artifact["inputs"] = {}
        workflow["graphs"]["default"]["nodes"]["artifact_probe"] = artifact
        workflow["graphs"]["default"]["terminal"].append("artifact_probe")
        self.w.bootstrap(workflow=workflow)
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
        later = self.wt.commit({p: f"assert {i} == {i}  # corrected\n" for i, p in enumerate(self.paths[:2])},
                               "test: later partial correction")
        self.wt.git("push", "-q", "origin", f"{later}:refs/heads/zzzops/work/g{self.g}")
        ident = identity.Identity(fx.engine_git(self.wt))
        cp["commit"] = later
        cp["tree"] = ident.code_tree(later)
        cp["change"] = ident.change(cp["base"], later, paths=subset["frozen"])
        self.later_cp = copy.deepcopy(cp)
        self.assertNotEqual(self.accepted["output"]["tests"]["commit"], later)
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
        record = self.show()["goal"]["records"]["test_design"]
        self.assertEqual(self.paths, record["frozen"])
        self.assertEqual(self.later_cp["base"], record["output"]["tests"]["base"])
        self.assertEqual(self.later_cp["commit"], record["output"]["tests"]["commit"])
        self.assertEqual(self.later_cp["tree"], record["output"]["tests"]["tree"])
        ident = identity.Identity(fx.engine_git(self.wt))
        self.assertEqual(ident.change(self.later_cp["base"], self.later_cp["commit"], paths=self.paths),
                         record["output"]["tests"]["change"])
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

    def test_already_published_consumer_cannot_submit_while_producer_blocked(self):
        card = self.a.start(self.g, "implement")
        bad = self.wt.commit({self.paths[0]: "assert False\n"}, "fix: weaken accepted test")
        self.wt.git("push", "-q", "origin", f"{bad}:refs/heads/zzzops/work/g{self.g}")
        blocked = copy.deepcopy(self.accepted)
        blocked.update({"status": "blocked", "ok": False, "output": None,
                        "blocked": {"category": "decision", "waiting_for": "agent", "reason": "retry",
                                    "instructions": "repair tests", "repeats": 1}})
        self.synthesize_legacy_record(self.tip(), blocked)
        before = self.tip()
        rc, out = self.a.submit(self.g, "implement", card, {"summary": "Published early"}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertTrue(any(word in str(out).lower() for word in ("block", "test_design", "producer")), out)
        self.assertEqual(before, self.tip())

    def test_rewritten_checkpoint_history_offers_no_recovery(self):
        self.damaged_history()
        repo = self.w.clones["b"]
        repo.git("checkout", "--orphan", "rewritten-source")
        repo.git("rm", "-rf", ".", check=False)
        unrelated = repo.commit({"tests/unrelated.py": "assert True\n"}, "test: unrelated history")
        repo.git("push", "-q", "origin", f"{unrelated}:refs/heads/fixture-unrelated")
        bad = copy.deepcopy(self.accepted)
        bad["attempt"] += 5
        bad["frozen"] = self.paths[:2]
        bad["output"]["tests"]["commit"] = unrelated
        bad["output"]["tests"]["tree"] = identity.Identity(fx.engine_git(repo)).code_tree(unrelated)
        self.synthesize_legacy_record(self.tip(), bad)
        diag = self.diagnostic()
        self.assertEqual("uncertain", diag["status"])
        self.assertIsNone(diag["proposal"])
        self.assertTrue(diag["issues"])

    def install_goal_push_barrier(self):
        """Pause the first goal-ref push on the real bare fixture remote."""
        ready = Path(self.tmp) / "recovery-goal-push-ready"
        release = Path(self.tmp) / "release-recovery-goal-push"
        lock = Path(self.tmp) / "recovery-goal-push-lock"
        hook = Path(self.w.remote) / "hooks" / "pre-receive"
        payload_path = Path(self.tmp) / "guarded-push-payload"
        contender_ready = Path(self.tmp) / "contender-push-ready"
        contender_payload = Path(self.tmp) / "contender-push-payload"
        script = f"""#!/bin/sh
payload=$(cat)
case "$payload" in
  *refs/heads/zzzops/goal/g{self.g}*)
    if mkdir {shlex.quote(str(lock))} 2>/dev/null; then
      printf '%s\n' "$payload" > {shlex.quote(str(payload_path))}
      touch {shlex.quote(str(ready))}
      i=0
      while [ ! -f {shlex.quote(str(release))} ]; do
        i=$((i + 1))
        [ "$i" -lt 300 ] || exit 1
        sleep 0.1
      done
    else
      printf '%s\n' "$payload" > {shlex.quote(str(contender_payload))}
      touch {shlex.quote(str(contender_ready))}
    fi ;;
  *refs/heads/zzzops/*)
    if [ -d {shlex.quote(str(lock))} ]; then
      printf '%s\n' "$payload" > {shlex.quote(str(contender_payload))}
      touch {shlex.quote(str(contender_ready))}
    fi ;;
esac
exit 0
"""
        hook.write_text(script)
        hook.chmod(0o755)
        return ready, release

    def start_guarded_recovery(self, before_start=None, now=None):
        self.damaged_history()
        diag = self.diagnostic()
        proposal = diag["proposal"]
        self.activate_capability()
        if before_start:
            before_start()
        ready, release = self.install_goal_push_barrier()
        argv = [sys.executable, str(fx.PLUGIN_CODE / "zzzops.py"), "edit", str(self.g),
                "--file", self.w.file(proposal["edit"]), "--base", proposal["base"]]
        proc = subprocess.Popen(argv, cwd=self.w.clones["a"].path, env=self.w.cli_env(now),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        self.addCleanup(lambda: proc.kill() if proc.poll() is None else None)
        self.addCleanup(release.touch)
        deadline = time.monotonic() + 25
        while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(ready.exists(), "recovery did not reach the final guarded goal push")
        return diag, proposal, proc, release

    @staticmethod
    def finish_recovery(proc, release):
        release.touch()
        stdout, stderr = proc.communicate(timeout=30)
        try:
            result = json.loads(stdout)
        except ValueError:
            result = {"stdout": stdout, "stderr": stderr}
        return proc.returncode, result

    def test_already_changed_work_ref_refuses_proposal_before_write(self):
        self.damaged_history()
        proposal = self.diagnostic()["proposal"]
        self.activate_capability()
        changed = self.wt.commit({"src/changed.py": "new = True\n"}, "fix: changed work")
        self.wt.git("push", "-q", "origin", f"{changed}:refs/heads/zzzops/work/g{self.g}")
        before = self.tip()
        rc, out = self.w.run("a", "edit", str(self.g), "--file", self.w.file(proposal["edit"]),
                             "--base", proposal["base"])
        self.assertNotEqual(0, rc, out)
        self.assertEqual(before, self.tip())

    def test_already_claimed_publisher_cannot_race_recovery(self):
        self.damaged_history()
        proposal = self.diagnostic()["proposal"]
        self.activate_capability()
        publisher = self.a.start(self.g, "test_design")
        self.wt.commit({"tests/publisher.py": "assert True\n"}, "test: claimed publisher")
        before = self.tip()
        rc, out = self.w.run("b", "edit", str(self.g), "--file", self.w.file(proposal["edit"]),
                             "--base", proposal["base"])
        self.assertNotEqual(0, rc, out)
        self.assertEqual(before, self.tip())
        self.assertTrue(any(word in str(out).lower() for word in ("lease", "gate", "workspace", "busy")), out)

    def test_workspace_claim_cannot_race_past_recovery_gate(self):
        diag, proposal, proc, release = self.start_guarded_recovery()
        before = self.tip()
        try:
            rc, claim = self.w.run("b", "start", str(self.g), "test_design", "--as", self.b.label)
        finally:
            recovery_rc, recovery = self.finish_recovery(proc, release)
        # While recovery is held inside its guarded push, a competing workspace
        # claim must not also succeed. If reclaim/expiration invalidates recovery,
        # its later push must refuse instead of publishing a stale repair.
        self.assertNotEqual(0, rc, (claim, recovery))
        self.assertEqual("workspace_busy", claim["error"]["code"])
        self.assertEqual("held", claim["error"]["details"]["workspace_gate"]["state"])
        self.assertEqual(0, recovery_rc, (claim, recovery))
        self.assertTrue(recovery.get("applied"), recovery)
        payload = (Path(self.tmp) / "guarded-push-payload").read_text().splitlines()
        refs = [line.split() for line in payload]
        excluded = ("refs/heads/zzzops/goal/", "refs/heads/zzzops/work/")
        changed_gate = [parts for parts in refs if len(parts) == 3 and parts[0] != parts[1]
                        and not parts[2].startswith(excluded)]
        self.assertTrue(changed_gate, "recovery goal update must atomically advance a real gate ref")

    def test_competing_recoveries_cannot_both_apply_the_same_proposal(self):
        diag, proposal, first, release = self.start_guarded_recovery()
        argv = [sys.executable, str(fx.PLUGIN_CODE / "zzzops.py"), "edit", str(self.g),
                "--file", self.w.file(proposal["edit"]), "--base", proposal["base"]]
        second = subprocess.Popen(argv, cwd=self.w.clones["b"].path, env=self.w.cli_env(),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: second.kill() if second.poll() is None else None)
        # Wait for a real second push attempt or an explicit gate refusal
        # while the first writer is still held at its server-side barrier.
        marker = Path(self.tmp) / "contender-push-ready"
        deadline = time.monotonic() + 25
        while not marker.exists() and second.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(marker.exists() or second.poll() is not None,
                        "contender did not reach its gate attempt while recovery was held")
        if marker.exists():
            first_payload = (Path(self.tmp) / "guarded-push-payload").read_text().splitlines()
            second_payload = (Path(self.tmp) / "contender-push-payload").read_text().splitlines()
            def changed_refs(lines):
                return {p[2] for line in lines if len(p := line.split()) == 3 and p[0] != p[1]
                        and not p[2].startswith(("refs/heads/zzzops/goal/", "refs/heads/zzzops/work/"))}
            self.assertTrue(changed_refs(first_payload) & changed_refs(second_payload),
                            "the contender must actually attempt the same changed gate ref")
        first_rc, first_result = self.finish_recovery(first, release)
        second_stdout, second_stderr = second.communicate(timeout=30)
        try:
            second_result = json.loads(second_stdout)
        except ValueError:
            second_result = {"stdout": second_stdout, "stderr": second_stderr}
        self.assertEqual(1, (first_rc == 0) + (second.returncode == 0), (first_result, second_result))
        if not marker.exists():
            self.assertNotEqual(0, second.returncode)
            self.assertTrue(any(word in str(second_result).lower() for word in ("gate", "lease", "busy", "claim")), second_result)
        winner = first_result if first_rc == 0 else second_result
        self.assertTrue(winner.get("applied"), winner)

    def assert_held_gate(self):
        state = self.w.ok("b", "show", str(self.g), "--json")["workspace_gate"]
        self.assertEqual("held", state["state"])
        self.assertTrue(state["holder"])
        self.assertTrue(state["operation"])
        expiry = datetime.fromisoformat(state["expires_at"].replace("Z", "+00:00"))
        ttl = self.w.policy["settings"]["leases"]["ttl_minutes"] * 60
        self.assertEqual(datetime.fromtimestamp(fx.NOW + ttl, timezone.utc), expiry)
        return ttl

    def test_base_sync_start_refuses_held_recovery_gate(self):
        diag, proposal, holder, release = self.start_guarded_recovery()
        try:
            self.w.ok("b", "reopen", str(self.g), "base", "--note", "request sync")
            before_goal = self.tip()
            before_work = self.w.remote_git("rev-parse", f"refs/heads/zzzops/work/g{self.g}")
            rc, result = self.w.run("b", "start", str(self.g), "base", "--as", "codex:bbbb/op")
            self.assertNotEqual(0, rc, result)
            self.assertIn(result["error"]["code"], ("workspace_busy", "validation"))
            self.assertEqual(before_goal, self.tip())
            self.assertEqual(before_work, self.w.remote_git("rev-parse", f"refs/heads/zzzops/work/g{self.g}"))
        finally:
            recovery_rc, recovery = self.finish_recovery(holder, release)
        # Reopening base moved the goal; the held recovery must not publish its
        # previously approved proposal against that stale goal snapshot.
        self.assertNotEqual(0, recovery_rc, recovery)

    def test_non_workspace_artifact_submission_refuses_held_gate_then_succeeds(self):
        saved = {}
        def claim_artifact():
            saved["card"] = self.b.start(self.g, "artifact_probe")
        diag, proposal, holder, release = self.start_guarded_recovery(before_start=claim_artifact)
        try:
            before_goal = self.tip()
            before_work = self.w.remote_git("rev-parse", f"refs/heads/zzzops/work/g{self.g}")
            rc, result = self.b.submit(self.g, "artifact_probe", saved["card"], {"summary": "Review"},
                                       artifact="An independent artifact.\n", ok=False)
            self.assertNotEqual(0, rc, result)
            self.assertEqual("workspace_busy", result["error"]["code"])
            self.assertEqual(before_goal, self.tip())
            self.assertEqual(before_work, self.w.remote_git("rev-parse", f"refs/heads/zzzops/work/g{self.g}"))
        finally:
            recovery_rc, recovery = self.finish_recovery(holder, release)
        self.assertEqual(0, recovery_rc, recovery)
        self.b.submit(self.g, "artifact_probe", saved["card"], {"summary": "Review"},
                      artifact="An independent artifact.\n")

    def test_expired_workspace_submit_routes_refuse_a_newly_held_gate(self):
        saved = {}
        def claim_workspace():
            saved["card"] = self.a.start(self.g, "test_design")
        ttl = self.w.policy["settings"]["leases"]["ttl_minutes"] * 60
        diag, proposal, holder, release = self.start_guarded_recovery(before_start=claim_workspace,
                                                                    now=fx.NOW + ttl + 1)
        card = saved["card"]
        before_goal = self.tip()
        before_work = self.w.remote_git("rev-parse", f"refs/heads/zzzops/work/g{self.g}")
        try:
            for kwargs in ({"output": {"commands": ["true"]}},
                           {"blocked": {"waiting_for": "agent", "instructions": "retry"}}):
                rc, result = self.a.submit(self.g, "test_design", card, ok=False, **kwargs)
                self.assertNotEqual(0, rc, result)
                self.assertIn(result["error"]["code"], ("workspace_busy", "superseded", "claim_lost"))
                self.assertEqual(before_goal, self.tip())
                self.assertEqual(before_work, self.w.remote_git("rev-parse", f"refs/heads/zzzops/work/g{self.g}"))
        finally:
            recovery_rc, recovery = self.finish_recovery(holder, release)
        self.assertEqual(0, recovery_rc, recovery)

    def test_expired_gate_is_automatically_reclaimed_and_stale_holder_cannot_publish(self):
        diag, proposal, holder, release = self.start_guarded_recovery()
        ttl = self.assert_held_gate()
        later = fx.NOW + ttl + 1
        expired = self.w.ok("b", "show", str(self.g), "--json", now=later)["workspace_gate"]
        self.assertEqual("expired", expired["state"])
        try:
            rc, replacement = self.w.run("b", "edit", str(self.g), "--file", self.w.file(proposal["edit"]),
                                         "--base", proposal["base"], now=later)
        finally:
            old_rc, old_result = self.finish_recovery(holder, release)
        self.assertEqual(0, rc, replacement)
        self.assertTrue(replacement["workspace_gate_reclaimed"], replacement)
        self.assertNotEqual(0, old_rc, old_result)
        self.assertIn(old_result["error"]["code"], ("superseded", "claim_lost"))
        self.assertEqual(self.paths, self.show()["goal"]["records"]["test_design"]["frozen"])

    def test_crashed_gate_expires_and_is_reclaimed_without_rewriting_history(self):
        diag, proposal, holder, release = self.start_guarded_recovery()
        ttl = self.assert_held_gate()
        before = self.tip()
        # Kill the complete command process group, including the pending Git
        # push; the acquired gate remains observable on the remote.
        os.killpg(holder.pid, signal.SIGKILL)
        holder.communicate(timeout=10)
        release.touch()
        self.assertEqual(before, self.tip())
        later = fx.NOW + ttl + 1
        expired = self.w.ok("b", "show", str(self.g), "--json", now=later)["workspace_gate"]
        self.assertEqual("expired", expired["state"])
        rc, result = self.w.run("b", "edit", str(self.g), "--file", self.w.file(proposal["edit"]),
                                "--base", proposal["base"], now=later)
        self.assertEqual(0, rc, result)
        self.assertTrue(result["workspace_gate_reclaimed"], result)
        self.assertTrue(result["applied"], result)
        self.assertEqual(self.paths, self.show()["goal"]["records"]["test_design"]["frozen"])

    def test_direct_work_push_is_disclosed_and_not_claimed_as_fenced(self):
        diag, proposal, proc, release = self.start_guarded_recovery()
        self.assertEqual("cooperating_writers", diag["concurrency_guard"])
        self.assertIn("direct", json.dumps(diag).lower())
        old_work = self.w.remote_git("rev-parse", f"refs/heads/zzzops/work/g{self.g}")
        self.assertEqual(old_work, proposal["work_commit"])
        try:
            new_work = self.wt.commit({"src/direct.py": "outside = True\n"}, "fix: direct work push")
            self.wt.git("push", "-q", "origin", f"{new_work}:refs/heads/zzzops/work/g{self.g}")
        finally:
            rc, result = self.finish_recovery(proc, release)
        # This push races after the guarded observation. It is intentionally out
        # of band and cannot be promised as an atomically fenced source ref.
        self.assertEqual(0, rc, result)
        self.assertEqual(new_work, self.w.remote_git("rev-parse", f"refs/heads/zzzops/work/g{self.g}"))
        self.assertEqual("cooperating_writers", result["concurrency_guard"])
        self.assertIn("direct", json.dumps(result).lower())

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
