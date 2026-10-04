"""Public regressions for authenticated continuity of stopped owned drafts."""
import copy
import hashlib
import json
import re
import unittest

import test_evidence_dag_journeys as j


class StoppedDraftRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.case = j.WorkspaceAuthorityPublicTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def acquire_dirty_beta(self, *, crlf=False):
        c = self.case
        c.setup_workspace()
        if crlf:
            c.session.git("config", "core.autocrlf", "true")
            for name in ("source.py", "read_dependency.txt"):
                path = c.fixture.repo / name
                path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            c.session.git("add", "source.py", "read_dependency.txt")
            self.assertEqual("", c.session.git("diff", "--cached", "--name-only"))
        c.red_candidate()
        work = c.acquire_workspace("beta")
        data = b"def value():\r\n    return 2\r\n" if crlf else b"def value():\n    return 2\n"
        (c.fixture.repo / "source.py").write_bytes(data)
        return work, data

    def recover(self, work, request_id="recover-stopped-owner", **overrides):
        expected = overrides.pop("expected", 0)
        request = {"operation": "recover", "node": work["node"], "lease": work["lease"]["token"],
                   "actor": work["bound_actor"], "worker_status": "stopped",
                   "evidence": "Fixture observed the bound worker stopped after its owned edit",
                   "request_id": request_id}
        request.update(overrides)
        return self.case.session.call(100, request, expected=expected)

    def recovery_draft(self, receipts_before):
        c = self.case
        receipts = c.payload()[1]["operational"]["receipts"]
        added = receipts[len(receipts_before):]
        self.assertEqual(1, len(added), "Recovery must commit exactly one reachable response receipt")
        response = c.read_blob(added[0]["result"])
        self.assertTrue(response.get("next_steps"), "Committed recovery response must remain readable")
        self.assertIn("workspace_draft", response["next_steps"][0],
                      "Recovery with owned continuity must publish its authenticated workspace_draft Ref")
        draft_ref = response["next_steps"][0]["workspace_draft"]
        return added[0], draft_ref, c.read_blob(draft_ref)

    def assert_draft_bindings(self, work, draft, stopped_bytes):
        c = self.case
        acquisition = work["lease"]["acquisition"]
        self.assertEqual("workspace_draft", draft["type"])
        self.assertEqual(work["node"], draft["node"])
        self.assertEqual(work["lease"]["token"], draft["lease"]["token"])
        self.assertEqual(work["lease"]["attempt"], draft["lease"]["attempt"])
        self.assertEqual(work["lease"]["owner"], draft["lease"]["owner"])
        self.assertEqual(work["bound_actor"], draft["lease"]["worker"])
        source_payload = c.read_blob(draft["source_payload"])
        source_lease = next(row for row in source_payload["operational"]["leases"]
                            if row["token"] == work["lease"]["token"])
        self.assertEqual(work["bound_actor"], source_lease["worker"])
        acquisition_receipt = c.read_blob(draft["acquisition_receipt"])
        self.assertIn(work["lease"]["token"], json.dumps(acquisition_receipt))
        self.assertEqual(acquisition, draft["acquisition"])
        self.assertEqual(j.content_hash(acquisition), draft["acquisition_hash"])
        self.assertEqual(work["input_hash"], draft["input_hash"])
        self.assertEqual(acquisition["contract"], draft["contract"])
        self.assertEqual(j.content_hash(c.session.project["policy"]), draft["policy"])
        authority_names = {"allocation", "authorization", "approval",
                           "parent_allocation", "parent_authorization", "parent_approval"}
        authority_inputs = [row for row in acquisition["inputs"] if row["name"] in authority_names]
        direct = {row["name"]: row["source"] for row in authority_inputs}
        expected_authority = {name: direct[name] for name in ("allocation", "authorization", "approval")}
        expected_authority["inputs"] = authority_inputs
        self.assertEqual(expected_authority, draft["authority"])
        expected_files = {path.name: "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted(c.fixture.repo.iterdir()) if path.is_file()}
        self.assertEqual(expected_files, draft["files"])
        self.assertEqual(j.content_hash(expected_files), draft["workspace"])
        self.assertEqual({"source.py": "sha256:" + hashlib.sha256(stopped_bytes).hexdigest()}, draft["outputs"])
        self.assertIn("observed", draft["evidence"].lower())

    def test_owned_draft_survives_stop_as_operational_evidence_and_reacquires_exact_task(self):
        c = self.case
        work, stopped_bytes = self.acquire_dirty_beta()
        payload_before = c.payload()[1]
        evidence_before = copy.deepcopy(payload_before["evidence"])
        receipts_before = copy.deepcopy(payload_before["operational"]["receipts"])
        understanding = c.result("inspect_charter")[0]
        approval = c.result("consent")[0]
        self.recover(work)
        payload = c.payload()[1]
        self.assertEqual(evidence_before, payload["evidence"], "A draft must never be published as a Result")
        self.assertGreater(len(payload["operational"]["receipts"]), len(receipts_before),
                           "Recovery must commit host-authenticated operational continuity before lease removal")
        receipt, draft_ref, draft = self.recovery_draft(receipts_before)
        self.assertEqual("recover-stopped-owner", receipt["request"])
        self.assert_draft_bindings(work, draft, stopped_bytes)
        self.assertEqual(understanding, c.result("inspect_charter")[0])
        self.assertEqual(approval, c.result("consent")[0])
        self.assertNotIn("gamma", c.names(), "A stopped draft cannot satisfy review or dependency gates")
        fresh = c.acquire_workspace("beta")
        self.assertNotEqual(work["lease"]["token"], fresh["lease"]["token"])
        self.assertEqual(stopped_bytes, (c.fixture.repo / "source.py").read_bytes())
        original_source = work["lease"]["acquisition"]["files"]["source.py"]
        self.assertEqual(original_source, fresh["lease"]["acquisition"]["files"]["source.py"],
                         "Fresh acquisition must retain the original authenticated baseline")
        self.assertEqual(draft_ref, fresh["lease"]["acquisition"]["stopped_draft"])
        self.assertNotIn(draft_ref["hash"], json.dumps(fresh["lease"]["acquisition"]["baseline_proofs"]),
                         "Draft continuity must never enter accepted review/proof edges")
        no_checks = c.session.submission(fresh, {"value": "unverified stopped draft"}, "no-checks")
        self.assertRegex(json.dumps(c.session.call(100, no_checks, expected=2)), r"(?i)check|verif|workspace")
        _proof_ref, proof = c.candidate(fresh, 0)
        self.assertEqual(original_source, proof["acquisition"]["files"]["source.py"])
        c.review_candidate("beta", 0)
        self.assertIn("gamma", c.names())
        stale = c.session.submission(work, {"value": "stale owner"}, "stale-after-recovery")
        self.assertRegex(json.dumps(c.session.call(100, stale, expected=2)), r"(?i)lease|owner|stale")

    def test_exact_recovery_retry_is_idempotent_and_repeated_chain_keeps_each_baseline(self):
        c = self.case
        first, first_bytes = self.acquire_dirty_beta()
        receipts0 = copy.deepcopy(c.payload()[1]["operational"]["receipts"])
        response = self.recover(first, request_id="same-recovery")
        _receipt1, draft1_ref, draft1 = self.recovery_draft(receipts0)
        self.assert_draft_bindings(first, draft1, first_bytes)
        snapshot = copy.deepcopy(c.payload()[1]["operational"])
        retry = self.recover(first, request_id="same-recovery")
        self.assertEqual(response, retry)
        self.assertEqual(snapshot, c.payload()[1]["operational"])
        second = c.acquire_workspace("beta")
        self.assertEqual(draft1_ref, second["lease"]["acquisition"]["stopped_draft"])
        second_bytes = b"def value():\n    return 3\n"
        (c.fixture.repo / "source.py").write_bytes(second_bytes)
        receipts1 = copy.deepcopy(c.payload()[1]["operational"]["receipts"])
        self.recover(second, request_id="second-recovery")
        receipt2, draft2_ref, draft2 = self.recovery_draft(receipts1)
        self.assertNotEqual(draft1_ref, draft2_ref)
        self.assertEqual(draft1_ref, draft2["acquisition"]["stopped_draft"])
        self.assert_draft_bindings(second, draft2, second_bytes)
        self.assertEqual("second-recovery", receipt2["request"])
        third = c.acquire_workspace("beta")
        self.assertEqual(second_bytes, (c.fixture.repo / "source.py").read_bytes())
        self.assertEqual(draft2_ref, third["lease"]["acquisition"]["stopped_draft"])
        self.assertEqual(first["lease"]["acquisition"]["files"]["source.py"],
                         third["lease"]["acquisition"]["files"]["source.py"])

    def test_repeated_recovery_records_successor_when_draft_reverts_to_original_baseline(self):
        c = self.case
        first, first_bytes = self.acquire_dirty_beta()
        receipts0 = copy.deepcopy(c.payload()[1]["operational"]["receipts"])
        self.recover(first, request_id="first-dirty-recovery")
        _receipt1, draft1_ref, draft1 = self.recovery_draft(receipts0)
        self.assert_draft_bindings(first, draft1, first_bytes)
        second = c.acquire_workspace("beta")
        self.assertEqual(draft1_ref, second["lease"]["acquisition"]["stopped_draft"])
        original_bytes = b"def value():\n    return 1\n"
        (c.fixture.repo / "source.py").write_bytes(original_bytes)
        receipts1 = copy.deepcopy(c.payload()[1]["operational"]["receipts"])
        self.recover(second, request_id="reverted-successor-recovery")
        receipt2, draft2_ref, draft2 = self.recovery_draft(receipts1)
        self.assertNotEqual(draft1_ref, draft2_ref)
        self.assertEqual(draft1_ref, draft2["acquisition"]["stopped_draft"])
        self.assertEqual({}, draft2["outputs"], "Exact baseline reversion has an empty owned delta")
        self.assertEqual("sha256:" + hashlib.sha256(original_bytes).hexdigest(), draft2["files"]["source.py"])
        self.assertEqual("reverted-successor-recovery", receipt2["request"])
        third = c.acquire_workspace("beta")
        self.assertNotEqual(second["lease"]["token"], third["lease"]["token"])
        self.assertEqual(draft2_ref, third["lease"]["acquisition"]["stopped_draft"])
        self.assertEqual(original_bytes, (c.fixture.repo / "source.py").read_bytes())

    def test_crlf_and_zero_delta_controls_preserve_exact_checkout_semantics(self):
        c = self.case
        work, raw = self.acquire_dirty_beta(crlf=True)
        self.recover(work)
        fresh = c.acquire_workspace("beta")
        self.assertEqual(raw, (c.fixture.repo / "source.py").read_bytes())
        self.assertEqual(work["lease"]["acquisition"]["checkout_overrides"],
                         fresh["lease"]["acquisition"]["checkout_overrides"])
    def test_zero_delta_clean_git_recovery_remains_a_passing_control(self):
        c = self.case
        c.setup_workspace()
        c.red_candidate()
        clean = c.acquire_workspace("beta")
        self.recover(clean, request_id="zero-delta")
        self.assertIn("beta", c.names(), "Clean stopped work retains ordinary reacquisition behavior")

    def test_live_owner_blocks_takeover_before_observed_stop(self):
        c = self.case
        work, _ = self.acquire_dirty_beta()
        before = copy.deepcopy((c.provider.issues, c.provider.comments))
        response = c.session.call(100, {"operation": "start", "node": work["node"],
                                       "input_hash": work["input_hash"], "actor": "replacement"}, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)owned|owner|lease|active")
        self.assertEqual(before, (c.provider.issues, c.provider.comments))

    def assert_bad_recovery(self, label, override):
        c = self.case
        work, _ = self.acquire_dirty_beta()
        before = copy.deepcopy((c.provider.issues, c.provider.comments))
        request = {"operation": "recover", "node": work["node"], "lease": work["lease"]["token"],
                   "actor": work["bound_actor"], "worker_status": "stopped", "evidence": "observed stop",
                   "request_id": "bad-" + label, **override}
        response = c.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)lease|actor|node|generation|owner")
        self.assertEqual(before, (c.provider.issues, c.provider.comments))

    def test_wrong_actor_recovery_fails_closed(self):
        self.assert_bad_recovery("actor", {"actor": "intruder"})

    def test_wrong_token_recovery_fails_closed(self):
        self.assert_bad_recovery("token", {"lease": "wrong-token"})

    def test_wrong_task_recovery_fails_closed(self):
        self.assert_bad_recovery("task", {"node": {"goal": 100, "node": "gamma", "item": None, "generation": 1}})

    def test_wrong_generation_recovery_fails_closed(self):
        self.assert_bad_recovery("generation", {"node": {"goal": 100, "node": "beta", "item": None,
                                                         "generation": 99}})

    def test_post_stop_edit_without_fresh_lease_blocks_reacquisition(self):
        c = self.case
        work, _ = self.acquire_dirty_beta()
        self.recover(work)
        (c.fixture.repo / "source.py").write_text("def value():\n    return 999\n")
        steps = c.session.checkpoint(100)
        self.assertFalse(any(s.get("kind") == "execute" and s.get("node", {}).get("node") == "beta" for s in steps),
                         "Post-stop edits without a fresh lease must not authorize continuity")

    def test_unowned_change_at_stop_is_rejected_without_receipt(self):
        c = self.case
        work, _ = self.acquire_dirty_beta()
        (c.fixture.repo / "unexpected.py").write_text("unowned\n")
        before = copy.deepcopy(c.payload()[1]["operational"])
        response = self.recover(work, request_id="unowned-at-stop", expected=2)
        self.assertRegex(json.dumps(response), r"(?i)scope|owned|workspace|file")
        self.assertEqual(before, c.payload()[1]["operational"])

    def test_consumed_change_at_stop_is_rejected_without_receipt(self):
        c = self.case
        work, _ = self.acquire_dirty_beta()
        (c.fixture.repo / "read_dependency.txt").write_text("drifted dependency\n")
        before = copy.deepcopy(c.payload()[1]["operational"])
        response = self.recover(work, request_id="consumed-at-stop", expected=2)
        self.assertRegex(json.dumps(response), r"(?i)consumed|workspace|drift|file")
        self.assertEqual(before, c.payload()[1]["operational"])

    def test_spec_drift_cannot_turn_stopped_bytes_into_authority(self):
        c = self.case
        work, _ = self.acquire_dirty_beta()
        c.replace_spec("A changed policy/allocation requires fresh independent authority")
        before = copy.deepcopy(c.payload()[1]["operational"])
        response = self.recover(work, request_id="authority-drift", expected=2)
        self.assertRegex(json.dumps(response), r"(?i)policy|allocation|authority|input|stale")
        self.assertEqual(before, c.payload()[1]["operational"])

    def test_policy_drift_at_stop_is_rejected_without_receipt(self):
        c = self.case
        work, _ = self.acquire_dirty_beta()
        c.session.project["policy"]["reviewed"] = False
        before = copy.deepcopy(c.payload()[1]["operational"])
        response = self.recover(work, request_id="policy-drift", expected=2)
        self.assertRegex(json.dumps(response), r"(?i)policy|review|changed|stale")
        self.assertEqual(before, c.payload()[1]["operational"])

    def test_allocation_drift_at_stop_is_rejected_without_receipt(self):
        c = self.case
        work, _ = self.acquire_dirty_beta()
        c.replace_spec("A changed finite allocation requires fresh review")
        changed = copy.deepcopy(c.allocations)
        changed["allocations"]["beta"]["owned"] = ["replacement.py"]
        c.session.finish(c.session.acquire("charter"), {"grant": changed})
        before = copy.deepcopy(c.payload()[1]["operational"])
        response = self.recover(work, request_id="allocation-drift", expected=2)
        self.assertRegex(json.dumps(response), r"(?i)allocation|authority|input|stale")
        self.assertEqual(before, c.payload()[1]["operational"])

    def test_parent_authority_drift_at_stop_is_rejected_without_receipt(self):
        c = self.case
        c.setup_parent_workspace()
        c.red_candidate()
        work = c.acquire_workspace("beta")
        (c.fixture.repo / "source.py").write_text("def value():\n    return 2\n")
        body = c.provider.issues[99]["body"]
        parent = json.loads(re.search(r"<!-- zzzops-goal\s*\n(.*?)\nzzzops-goal -->", body, re.S)[1])
        index = j.z._comment_store.ArtifactIndex(c.provider.comments[99])
        payload = index.resolve(parent["payload"]["hash"])[0]
        spec = index.resolve(payload["spec"]["hash"])[0]
        spec["content"] = "Parent withdraws the previous child grant pending review"
        offset = len(c.provider.comments[100])
        payload["spec"] = c.blob(spec)
        parent["payload"] = c.blob(payload)
        for comment in copy.deepcopy(c.provider.comments[100][offset:]):
            c.provider.create_issue_comment(99, comment["body"])
        parent["revision"] += 1
        c.provider.issues[99]["body"] = "<!-- zzzops-goal\n" + json.dumps(parent) + "\nzzzops-goal -->"
        before = copy.deepcopy(c.payload()[1]["operational"])
        response = self.recover(work, request_id="parent-drift", expected=2)
        self.assertRegex(json.dumps(response), r"(?i)parent|authority|grant|input|stale")
        self.assertEqual(before, c.payload()[1]["operational"])

    def test_parent_authority_refs_are_pinned_in_authenticated_draft(self):
        c = self.case
        c.setup_parent_workspace()
        c.red_candidate()
        work = c.acquire_workspace("beta")
        stopped = b"def value():\n    return 2\n"
        (c.fixture.repo / "source.py").write_bytes(stopped)
        receipts = copy.deepcopy(c.payload()[1]["operational"]["receipts"])
        self.recover(work, request_id="parent-bound-draft")
        _receipt, _draft_ref, draft = self.recovery_draft(receipts)
        self.assert_draft_bindings(work, draft, stopped)
        self.assertEqual({"parent_allocation", "parent_authorization", "parent_approval"},
                         {row["name"] for row in draft["authority"]["inputs"]
                          if row["name"].startswith("parent_")})

    def test_authority_drift_after_recovery_revokes_draft_reacquisition(self):
        c = self.case
        work, _ = self.acquire_dirty_beta()
        self.recover(work, request_id="draft-before-policy-drift")
        self.assertIn("beta", c.names(), "Authenticated draft is the positive control before authority drift")
        c.session.project["policy"]["reviewed"] = False
        self.assertNotIn("beta", c.names(), "Current authority must still govern draft reacquisition")

    def test_tampered_committed_recovery_receipt_cannot_authorize_reacquisition(self):
        c = self.case
        work, _ = self.acquire_dirty_beta()
        before = len(c.payload()[1]["operational"]["receipts"])
        self.recover(work, request_id="receipt-to-tamper")
        receipts = c.payload()[1]["operational"]["receipts"]
        self.assertGreater(len(receipts), before)
        target = receipts[-1]["result"]["hash"]
        changed = 0
        for comment in c.provider.comments[100]:
            envelope = j.z._comment_store.decode_envelope(comment["body"])
            if envelope is None:
                continue
            for record in envelope["artifacts"]:
                if record["hash"] == target:
                    record["text"] = record.get("text", "") + "tampered"
                    changed += 1
            comment["body"] = j.z._comment_store.encode_envelope(envelope)
        self.assertEqual(1, changed, "Probe must corrupt the committed receipt artifact")
        response = c.session.call(100, expected=None)
        self.assertFalse(any(step.get("kind") == "execute" and step.get("node", {}).get("node") == "beta"
                             for step in response["next_steps"]))
        self.assertRegex(json.dumps(response), r"(?i)hash|receipt|artifact|corrupt|provenance")

    def test_orphaned_recovery_artifact_and_disconnected_bytes_do_not_authorize_continuity(self):
        c = self.case
        work, _ = self.acquire_dirty_beta()
        self.recover(work, request_id="receipt-to-orphan")
        body = c.provider.issues[100]["body"]
        envelope = json.loads(re.search(r"<!-- zzzops-goal\s*\n(.*?)\nzzzops-goal -->", body, re.S)[1])
        payload = c.read_blob(envelope["payload"])
        orphan = payload["operational"]["receipts"].pop()
        envelope["payload"] = c.blob(payload)
        envelope["revision"] += 1
        c.provider.issues[100]["body"] = "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"
        self.assertEqual(b"def value():\n    return 2\n", (c.fixture.repo / "source.py").read_bytes())
        response = c.session.call(100, expected=None)
        self.assertFalse(any(step.get("kind") == "execute" and step.get("node", {}).get("node") == "beta"
                             for step in response["next_steps"]))
        self.assertRegex(json.dumps(response), r"(?i)receipt|provenance|workspace|snapshot|drift")
        c.read_blob(orphan["result"])


if __name__ == "__main__":
    unittest.main()
