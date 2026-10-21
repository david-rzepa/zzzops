"""Public contract for resolving authenticated blockers preserved by migration.

The host, rather than a phase Result, owns this narrow intake.  Discovery binds
the immutable original goal-context and exact blocker content identities.  A
root submission then supplies its judgement, same-goal immutable evidence and,
for human-action blockers, explicit user attribution.  Resolution is an
append-only projection: it never rewrites migration history or satisfies phase,
workspace, dependency, review, CI, merge, or publication gates.
"""
from __future__ import annotations

import copy
import json
import os
import unittest
from unittest import mock

import test_batch_goal_conversion as batch
import test_evidence_dag_journeys as dag


class GoalContextResolutionTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.case = batch.BatchConversionTests(methodName="runTest")
        cls.case.setUp()
        cls.addClassCleanup(cls.case.doCleanups)
        cls.blocker = {
            "status": "open",
            "category": "human-action",
            "question": "User must approve the exact migrated design",
        }
        cls.case.legacy_fields(100, depends_on=[101], blockers=[copy.deepcopy(cls.blocker)])
        result = cls.case.migrate((100,))
        if result["members"]["100"]["status"] != "migrated":
            raise AssertionError(result)
        cls.case.normal_setup(100)
        cls.baseline_issues = copy.deepcopy(cls.case.provider.issues)
        cls.baseline_comments = copy.deepcopy(cls.case.provider.comments)
        cls.baseline_blobs = copy.deepcopy(cls.case.blobs)

    def setUp(self):
        self.case.provider.issues = copy.deepcopy(self.baseline_issues)
        self.case.provider.comments = copy.deepcopy(self.baseline_comments)
        self.case.provider.updates = []
        self.case.blobs = copy.deepcopy(self.baseline_blobs)
        self.case.session.sequence = 0
        self.case.session.calls = []
        self.envelope = dag.z.parse_managed_goal(self.case.provider.issues[100]["body"], 100)
        self.original_payload = copy.deepcopy(self.case.session.read(100, self.envelope["payload"]))
        self.original_context_ref = copy.deepcopy(self.original_payload["goal_context"])
        self.original_context = copy.deepcopy(self.case.session.read(100, self.original_context_ref))
        self.original_comments = copy.deepcopy(self.case.provider.comments[100])

    def fresh_case(self):
        case = batch.BatchConversionTests(methodName="runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        self.case = case
        return case

    def discovery(self, blocker=None):
        blocker_hash = dag.z._workflow.digest(blocker or self.blocker)
        matches = [step for step in self.case.session.checkpoint(100)
                   if (step.get("submission") or {}).get("operation") == "resolve_goal_blocker"
                   and step["submission"].get("blocker_hash") == blocker_hash]
        self.assertEqual(1, len(matches), matches)
        step = matches[0]
        self.assertEqual("root", step.get("assignment"))
        self.assertRegex(json.dumps(step), r"(?i)blocker|resolution|evidence|approval")
        return step

    def current_payload(self):
        envelope = dag.z.parse_managed_goal(self.case.provider.issues[100]["body"], 100)
        return self.case.session.read(100, envelope["payload"])

    def evidence(self, *, goal=100):
        """Use authenticated current host Results/outputs, never invented prose."""
        result, content = self.case.result("understand")
        refs = [result, content["outputs"]["design"], content["outputs"]["allocation"]]
        if goal == 100:
            return refs
        return [{**ref, "uri": ref["uri"].replace("goal:100:", f"goal:{goal}:")}
                for ref in refs]

    def request(self, request_id="resolve-migrated-blocker-1", **changes):
        submission = copy.deepcopy(self.discovery()["submission"])
        submission.update({
            "request_id": request_id,
            "actor": "root-thread",
            "rationale": "The user approved the current design and explicitly superseded the obsolete requirement.",
            "resolution_basis": "Root attests that the cited approval resolves this exact obligation.",
            "evidence": self.evidence(),
            "human_approval": {"approved_by": "requesting-user",
                               "attribution": "Approved the exact current design in this conversation."},
        })
        submission.update(changes)
        return submission

    def call(self, request, *, expected=0):
        with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "root-thread"}):
            return self.case.session.call(100, request, expected=expected)

    def assert_rejected_without_write(self, request, pattern):
        before = copy.deepcopy((self.case.provider.issues, self.case.provider.comments))
        response = self.call(request, expected=2)
        self.assertRegex(json.dumps(response), pattern)
        self.assertEqual(before, (self.case.provider.issues, self.case.provider.comments))

    def resolved_event(self, response):
        step = response["next_steps"][0]
        self.assertEqual("goal_blocker_resolved", step["kind"])
        self.assertEqual(100, step["goal"])
        reference = step.get("resolution") or step.get("event")
        self.assertIsInstance(reference, dict)
        return step, self.case.session.read(100, reference)

    def test_public_discovery_success_and_exact_authenticated_identity(self):
        step = self.discovery()
        submission = step["submission"]
        self.assertEqual(self.original_context_ref["hash"], submission["context_hash"])
        self.assertEqual(dag.z._workflow.digest(self.blocker), submission["blocker_hash"])

        request = self.request()
        response = self.call(request)
        recorded, event = self.resolved_event(response)
        self.assertEqual("goal_blocker_resolution", event["type"])
        self.assertEqual(self.original_context_ref["hash"], event["content"]["context_hash"])
        self.assertEqual(submission["blocker_hash"], event["content"]["blocker_hash"])
        self.assertEqual("root-thread", event["provenance"]["actor"])
        self.assertEqual("resolve-migrated-blocker-1", event["provenance"]["request_id"])
        self.assertEqual(request["evidence"], event["content"]["evidence"])
        self.assertEqual("requesting-user", event["content"]["human_approval"]["approved_by"])

        steps = self.case.session.checkpoint(100)
        self.assertFalse(any((row.get("submission") or {}).get("blocker_hash")
                             == submission["blocker_hash"] for row in steps), steps)
        dependency = [row for row in steps if row.get("node", {}).get("node") == "test_design"]
        self.assertTrue(dependency, steps)
        self.assertFalse(any(row.get("kind") == "execute" for row in dependency), dependency)
        self.assertRegex(json.dumps(dependency), r"(?i)depend|101|predecessor")
        self.assertFalse(any(row.get("kind") == "result" for row in response["next_steps"]), response)
        self.assertIn(recorded.get("resolution") or recorded.get("event"),
                      self.current_payload()["goal_context_resolutions"]["events"])

    def test_original_context_history_dependency_and_other_blocker_are_immutable(self):
        other = {"status": "open", "category": "technical-unknown",
                 "question": "Confirm an unrelated compatibility constraint"}
        # Rebuild the fixture with two original obligations so projection can
        # prove that only the selected identity is removed.
        self.fresh_case()
        self.case.legacy_fields(100, depends_on=[101], blockers=[copy.deepcopy(self.blocker), other])
        self.case.migrate((100,))
        self.case.normal_setup(100)
        envelope = dag.z.parse_managed_goal(self.case.provider.issues[100]["body"], 100)
        before_payload = copy.deepcopy(self.case.session.read(100, envelope["payload"]))
        before_ref = copy.deepcopy(before_payload["goal_context"])
        before_context = copy.deepcopy(self.case.session.read(100, before_ref))
        before_history = [(row["id"], row["body"])
                          for row in self.case.provider.comments[100]]
        self.call(self.request())
        after_payload = self.current_payload()
        after_history = [(row["id"], row["body"])
                         for row in self.case.provider.comments[100]]
        self.assertEqual(before_history, after_history[:len(before_history)])
        self.assertEqual(before_ref, after_payload["goal_context"])
        self.assertEqual(before_context, self.case.session.read(100, before_ref))
        self.assertEqual([101], before_context["content"]["depends_on"])
        remaining = self.discovery(other)
        self.assertEqual(dag.z._workflow.digest(other), remaining["submission"]["blocker_hash"])

    def test_wrong_stale_foreign_actor_and_required_fields_fail_closed(self):
        base = self.request()
        cases = {
            "wrong blocker": {**base, "blocker_hash": "sha256:" + "1" * 64},
            "stale context": {**base, "context_hash": "sha256:" + "2" * 64},
            "wrong actor": {**base, "actor": "worker-thread"},
            "foreign evidence": {**base, "evidence": self.evidence(goal=101)},
            "empty rationale": {**base, "rationale": ""},
            "empty basis": {**base, "resolution_basis": ""},
            "missing evidence": {**base, "evidence": []},
            "missing approval": {key: value for key, value in base.items()
                                 if key != "human_approval"},
        }
        for label, invalid in cases.items():
            with self.subTest(label=label):
                self.assert_rejected_without_write(invalid,
                    r"(?i)context|blocker|actor|root|evidence|goal|rationale|basis|approval|required")

    def test_previously_current_result_is_rejected_after_its_input_changes(self):
        request = self.request("stale-resolution-evidence")
        self.case.replace_spec("A newer exact specification invalidates prior understanding outputs.")
        self.assert_rejected_without_write(request, r"(?i)stale|current|result|output|evidence")

    def test_idless_blocker_works_but_duplicate_content_is_ambiguous(self):
        # The successful fixture blocker has no id and therefore establishes
        # digest identity support. Duplicate identical content must not be
        # resolved by list position.
        self.call(self.request())
        self.fresh_case()
        self.case.legacy_fields(100, blockers=[copy.deepcopy(self.blocker), copy.deepcopy(self.blocker)])
        self.case.migrate((100,))
        self.case.normal_setup(100)
        steps = self.case.session.checkpoint(100)
        candidates = [s for s in steps if (s.get("submission") or {}).get("operation") == "resolve_goal_blocker"]
        self.assertFalse(candidates, candidates)
        request = {
            "operation": "resolve_goal_blocker", "request_id": "ambiguous-blocker",
            "actor": "root-thread", "context_hash": self.current_payload()["goal_context"]["hash"],
            "blocker_hash": dag.z._workflow.digest(self.blocker), "rationale": "Exact duplicate.",
            "resolution_basis": "Root attestation.", "evidence": self.evidence(),
            "human_approval": {"approved_by": "requesting-user", "attribution": "Approved."},
        }
        self.assert_rejected_without_write(request, r"(?i)ambiguous|duplicate|blocker")

    def test_nonhuman_blocker_requires_no_fabricated_human_approval(self):
        self.fresh_case()
        blocker = {"status": "open", "category": "technical-unknown",
                   "question": "Verify compatibility against the current output"}
        self.case.legacy_fields(100, blockers=[blocker])
        self.case.migrate((100,))
        self.case.normal_setup(100)
        submission = copy.deepcopy(self.discovery(blocker)["submission"])
        self.assertNotIn("human_approval", submission)
        submission.update({
            "request_id": "resolve-technical-blocker", "actor": "root-thread",
            "rationale": "The current authenticated output verifies compatibility.",
            "resolution_basis": "Root inspected the cited current Result and output.",
            "evidence": self.evidence(),
        })
        _, event = self.resolved_event(self.call(submission))
        self.assertNotIn("human_approval", event["content"])

    def test_historical_context_without_stored_context_is_materialised_unchanged(self):
        self.fresh_case()
        self.case.legacy_fields(100, depends_on=[101], blockers=[copy.deepcopy(self.blocker)])
        self.case.publish_historical_v1_migration()
        envelope = dag.z.parse_managed_goal(self.case.provider.issues[100]["body"], 100)
        before = copy.deepcopy(self.case.session.read(100, envelope["payload"]))
        self.assertNotIn("goal_context", before)
        self.case.normal_setup(100)
        discovered = self.discovery()
        request = copy.deepcopy(discovered["submission"])
        request.update({
            "request_id": "historical-context-resolution", "actor": "root-thread",
            "rationale": "The exact approved design supersedes the historical requirement.",
            "resolution_basis": "Root attests the cited current approval resolves it.",
            "evidence": self.evidence(),
            "human_approval": {"approved_by": "requesting-user",
                               "attribution": "Approved the exact current design."},
        })
        before_history = [(row["id"], row["body"])
                          for row in self.case.provider.comments[100]]
        self.resolved_event(self.call(request))
        after_history = [(row["id"], row["body"])
                         for row in self.case.provider.comments[100]]
        self.assertEqual(before_history, after_history[:len(before_history)])
        after = self.current_payload()
        context_ref = after["goal_context"]
        context = self.case.session.read(100, context_ref)
        self.assertEqual(discovered["submission"]["context_hash"], context_ref["hash"])
        self.assertEqual({"version": 1, "depends_on": [101],
                          "blockers": [self.blocker], "metadata": {}}, context["content"])

    def test_exact_replay_is_stable_and_changed_payload_conflicts(self):
        request = self.request("stable-resolution-request")
        first = self.call(request)
        after_first = copy.deepcopy((self.case.provider.issues, self.case.provider.comments))
        replay = self.call(request)
        self.assertEqual(first, replay)
        self.assertEqual(after_first, (self.case.provider.issues, self.case.provider.comments))
        changed = copy.deepcopy(request)
        changed["rationale"] += " Changed after commit."
        self.assert_rejected_without_write(changed, r"(?i)request|replay|conflict|payload")

    def test_new_root_consumes_authenticated_historical_resolution(self):
        response = self.call(self.request("historical-root-resolution"))
        self.resolved_event(response)
        runtime = copy.deepcopy(self.case.session.runtime)
        runtime["root_id"] = "new-root-thread"
        resumed = dag.TaskSession(self.case.fixture.repo, self.case.session.project, runtime,
                                  self.case.provider, self.case.session.control)
        before = copy.deepcopy((self.case.provider.issues, self.case.provider.comments))
        steps = resumed.checkpoint(100)
        self.assertEqual(before, (self.case.provider.issues, self.case.provider.comments))
        self.assertFalse(any((step.get("submission") or {}).get("operation")
                             == "resolve_goal_blocker" for step in steps), steps)
        self.assertFalse(any("goal-context blocker" in str(step.get("reason", "")).lower()
                             for step in steps), steps)

    def test_forged_resolution_event_is_rejected_on_read(self):
        response = self.call(self.request("forge-resolution-event"))
        recorded, _event = self.resolved_event(response)
        reference = recorded.get("resolution") or recorded["event"]
        changed = False
        for row in self.case.provider.comments[100]:
            envelope = dag.z._comment_store.decode_envelope(row["body"])
            if not envelope:
                continue
            for artifact in envelope.get("artifacts", []):
                if artifact.get("hash") == reference["hash"]:
                    artifact["hash"] = "sha256:" + "f" * 64
                    row["body"] = dag.z._comment_store.encode_envelope(envelope)
                    changed = True
        self.assertTrue(changed, "resolution artifact must be stored in authenticated history")
        rejected = self.case.session.call(100, expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)resolution|artifact|checksum|receipt|provenance")

    def test_resolution_event_without_committed_receipt_is_rejected(self):
        response = self.call(self.request("missing-resolution-receipt"))
        recorded, _event = self.resolved_event(response)
        reference = recorded.get("resolution") or recorded["event"]
        envelope = dag.z.parse_managed_goal(self.case.provider.issues[100]["body"], 100)
        payload = copy.deepcopy(self.case.session.read(100, envelope["payload"]))
        payload["operational"]["receipts"] = [
            receipt for receipt in payload["operational"]["receipts"]
            if receipt.get("request") != "missing-resolution-receipt"
        ]
        self.assertIn(reference, payload["goal_context_resolutions"]["events"])
        self.case.replace_legacy_payload(envelope, payload)
        rejected = self.case.session.call(100, expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)resolution|receipt|request|authenticate")

    def test_committed_but_unconfirmed_response_recovers_from_exact_receipt(self):
        request = self.request("resolution-response-lost")
        update = self.case.provider.update_issue
        published = False

        def lose_response(number, payload):
            nonlocal published
            result = update(number, payload)
            if not published:
                published = True
                raise OSError("response lost after provider commit")
            return result

        with mock.patch.object(self.case.provider, "update_issue", side_effect=lose_response):
            uncertain = self.call(request, expected=None)
        self.assertTrue(uncertain.get("next_steps"), uncertain)
        recovered = self.call(request)
        _, event = self.resolved_event(recovered)
        self.assertEqual("resolution-response-lost", event["provenance"]["request_id"])
        journal = self.current_payload()["goal_context_resolutions"]["events"]
        self.assertEqual(1, len(journal), journal)

    def test_active_lease_and_closed_goal_reject_without_mutation(self):
        self.fresh_case()
        self.case.legacy_fields(100, blockers=[copy.deepcopy(self.blocker)])
        self.case.migrate((100,))
        understand = self.case.session.acquire("understand")
        tasks = [{"goal": 100, "node": name, "item": None, "generation": 1}
                 for name in ("test_design", "implement")]
        allocation = {"allocations": {task["node"]: {
            "task": task, "owned": [], "consumed": ["product.txt"]} for task in tasks}}
        self.case.session.finish(understand, {
            "design": "Review the unchanged synthetic baseline.", "allocation": allocation})
        request = self.request()
        active = self.case.session.acquire("review_understanding")
        self.assertTrue(active["lease"]["token"])
        self.assert_rejected_without_write(request, r"(?i)lease|owner|active|recover")

        review = {"decision": "approved", "report": "Exact fixture review."}
        permit = {"manifest": self.case.result("understand")[1]["outputs"]["allocation"],
                  "tasks": tasks, "policy": dag.content_hash(self.case.session.project["policy"]),
                  "decision": "approved"}
        self.case.session.finish(active, {"review": review, "authorization": permit})
        self.case.provider.issues[100]["state"] = "closed"
        closed = copy.deepcopy((self.case.provider.issues, self.case.provider.comments))
        response = self.call(request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)closed|archiv|reopen")
        self.assertEqual(closed, (self.case.provider.issues, self.case.provider.comments))

    def test_preview_is_read_only_and_resolution_does_not_bypass_phase_gates(self):
        before = copy.deepcopy((self.case.provider.issues, self.case.provider.comments))
        preview = self.case.session.call(100, intent="preview")
        self.assertEqual(before, (self.case.provider.issues, self.case.provider.comments))
        self.assertTrue(any((s.get("submission") or {}).get("operation") == "resolve_goal_blocker"
                            for s in preview["next_steps"]), preview)

        response = self.call(self.request())
        self.resolved_event(response)
        steps = self.case.session.checkpoint(100)
        self.assertTrue(any(s.get("node", {}).get("node") == "test_design" for s in steps), steps)
        self.assertFalse(any(s.get("node", {}).get("node") == "implement"
                             and s.get("kind") == "execute" for s in steps), steps)
        self.assertFalse(any(s.get("kind") in {"integrate", "publish", "publication"}
                             for s in response["next_steps"]), response)


if __name__ == "__main__":
    unittest.main()
