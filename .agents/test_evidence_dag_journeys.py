"""Generic task journeys through z.main, with only external boundaries faked.

Proposed wire adapter: reviewed phase_dag contains CONTRACT.md's Graph; managed
v2 bodies contain its GoalEnvelope; returned steps identify ``node`` by qualified
identity and supply start/bind/submission requests. ``submit`` has outputs as a
name-to-content map. The host constructs output artifacts and Result provenance.
These transport choices are test-design proposals, not a second execution engine.
"""

from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zlib

import test_workflow_journey as old
from test_workflow_owned_outputs import PublicSession, content_hash
from test_evidence_dag import review_graph, selector, scope, subject_input, task


z = old.z


class TaskSession(PublicSession):
    def ready(self, number=100):
        return [step for step in self.checkpoint(number) if step.get("kind") == "execute"]

    def acquire(self, name, *, number=100, actor=None):
        step = next(step for step in self.ready(number) if step["node"]["node"] == name)
        receipt = json.loads(Path(step["policy"]["path"]).read_text())["policy_receipt"]
        request = {**step["start"], "policy_receipt": receipt}
        request.pop("request_id", None)
        acquired = self.call(number, request)["next_steps"][0]
        identity = actor or ("root-thread" if step["assignment"] == "root" else f"worker-{name}")
        lease = acquired["lease"]
        if lease["worker"] is None:
            bind = {**acquired["bind"], "lease": lease["token"], "actor": identity,
                    "selection": lease["selection"], "policy_receipt": receipt}
            bind.pop("request_id", None)
            self.call(number, bind)
        acquired["bound_actor"] = identity
        return acquired

    def submission(self, acquired, outputs, request_id):
        request = copy.deepcopy(acquired["submission"])
        if request["operation"] != "submit":
            raise AssertionError("Every semantic task must use the common submit contract")
        request.update(lease=acquired["lease"]["token"], actor=acquired["bound_actor"],
                       request_id=request_id, outputs=outputs)
        return request

    def finish(self, acquired, outputs, request_id=None, *, number=100):
        return self.call(number, self.submission(acquired, outputs,
                         request_id or f"finish-{acquired['node']['node']}-{self.sequence}"))


class EvidenceDagPublicTests(unittest.TestCase):
    def setUp(self):
        self.fixture = old.FullWorkflowJourneyTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        control = tempfile.TemporaryDirectory()
        self.addCleanup(control.cleanup)
        self.provider = self.fixture.provider
        self.provider.issues.pop(101)
        self.session = TaskSession(self.fixture.repo, self.fixture.project,
                                   self.fixture.runtime, self.provider, control.name)
        self.blobs = {}
        self.graph = review_graph()
        self.install(self.graph)

    def blob(self, content):
        """Seed immutable fixture bytes using the existing comment encoding."""
        digest = content_hash(content)
        raw = json.dumps({"hash": digest, "content": content}, ensure_ascii=False,
                         sort_keys=True, separators=(",", ":"))
        encoded = base64.b64encode(zlib.compress(raw.encode())).decode()
        body = ("<!-- zzzops-artifact " + digest + " -->\n"
                "<details><summary>Immutable phase artifact</summary>\n\n```text\n"
                + encoded + "\n```\n</details>")
        self.provider.create_issue_comment(100, body)
        self.blobs[digest] = copy.deepcopy(content)
        return {"hash": digest, "uri": "urn:" + digest}

    def install(self, graph):
        self.graph = copy.deepcopy(graph)
        z._workflow_section(self.session.project, "workflow_adherence")["configuration"]["phase_dag"] = self.graph
        spec = self.blob({"type": "specification", "content": "Produce and review a value.",
                          "producer": None, "provenance": {"actor": "root-thread", "source": None,
                          "policy": content_hash(self.session.project["policy"])}})
        payload = self.blob({"spec": spec, "graph": self.blob(self.graph), "evidence": [],
                             "operational": {"leases": [], "receipts": []}})
        self.envelope = {"schema_version": 2, "repository": "owner/repo", "issue": 100,
                         "revision": 1, "state": "open", "payload": payload}
        self.provider.issues[100]["body"] = (
            "## Outcome\nProduce and independently review a value.\n\n<!-- zzzops-goal\n"
            + json.dumps(self.envelope) + "\nzzzops-goal -->")

    def names(self):
        return {step["node"]["node"] for step in self.session.ready()}

    def produce(self):
        acquired = self.session.acquire("produce")
        self.session.finish(acquired, {"value": "version one"})
        return acquired

    def assert_rejected(self, acquired, outputs, changes, diagnostic):
        # Positive control is acquired from the real ready frontier, never an
        # unsupported schema. Retain the lease for a successful valid retry.
        payload = self.session.submission(acquired, outputs, "negative-request")
        payload.update(changes)
        before = copy.deepcopy(self.provider.issues)
        response = self.session.call(100, payload, expected=2)
        self.assertRegex(json.dumps(response), diagnostic)
        self.assertEqual(before, self.provider.issues)
        self.session.finish(acquired, outputs, "valid-after-negative")

    def test_parallel_reviews_independent_leases_and_join(self):
        self.assertEqual({"produce"}, self.names())
        self.produce()
        self.assertEqual({"review_a", "review_b"}, self.names())
        first = self.session.acquire("review_a")
        second = self.session.acquire("review_b")
        self.assertNotEqual(first["lease"]["token"], second["lease"]["token"])
        self.assertEqual({"model", "effort"}, set(first["lease"]["selection"]))
        self.session.finish(first, {"value": "accepted"})
        self.assertNotIn("finish", self.names())
        self.session.finish(second, {"value": "accepted"})
        self.assertEqual({"finish"}, self.names())
        final = self.session.acquire("finish")
        self.assertEqual("root-thread", final["bound_actor"])
        self.session.finish(final, {"value": "approved"})
        self.assertEqual(set(), self.names())
        self.assertTrue(any(step["kind"] == "complete" for step in self.session.checkpoint(100)))

    def test_wrong_actor_cannot_submit_and_valid_owner_still_can(self):
        acquired = self.session.acquire("produce")
        self.assert_rejected(acquired, {"value": "valid"}, {"actor": "impostor"}, r"(?i)actor|executor|worker")

    def test_wrong_lease_cannot_submit_and_valid_lease_still_can(self):
        acquired = self.session.acquire("produce")
        self.assert_rejected(acquired, {"value": "valid"}, {"lease": "stale-token"}, r"(?i)lease|ownership")

    def test_output_bundle_is_atomic_and_corrected_retry_succeeds(self):
        acquired = self.session.acquire("produce")
        self.assert_rejected(acquired, {"value": "valid"},
                             {"outputs": {"value": "valid", "undeclared": "must not leak"}},
                             r"(?i)output|undeclared|contract")
        self.assertEqual({"review_a", "review_b"}, self.names())

    def test_wrong_output_type_is_not_generic_schema_rejection(self):
        acquired = self.session.acquire("produce")
        self.assert_rejected(acquired, {"value": "valid"}, {"outputs": {"value": 17}}, r"(?i)type|string|contract")

    def test_exact_retry_is_idempotent_and_changed_payload_rejected(self):
        acquired = self.session.acquire("produce")
        payload = self.session.submission(acquired, {"value": "version one"}, "stable-request")
        first = self.session.call(100, payload)
        durable = copy.deepcopy(self.provider.issues)
        comments = copy.deepcopy(self.provider.comments)
        self.assertEqual(first, self.session.call(100, payload))
        self.assertEqual(durable, self.provider.issues)
        self.assertEqual(comments, self.provider.comments)
        conflict = self.session.call(100, {**payload, "outputs": {"value": "different"}}, expected=2)
        self.assertRegex(json.dumps(conflict), r"(?i)request|receipt|payload|retry")
        self.assertEqual(durable, self.provider.issues)

    def test_same_subject_executor_cannot_review_itself(self):
        producer = self.produce()
        self.assertEqual({"review_a", "review_b"}, self.names())
        with self.assertRaisesRegex(AssertionError, r"(?i)independen|self.review"):
            acquired = self.session.acquire("review_a", actor=producer["bound_actor"])
            self.session.finish(acquired, {"value": "self-approved"})
        self.assertNotIn("finish", self.names())

    def test_bookkeeping_comments_do_not_restart_completed_producer(self):
        self.produce()
        expected = self.names()
        for text in ("Thanks", "Working on this", "Acknowledged", "Thread resolved"):
            self.provider.create_issue_comment(100, text)
            self.assertEqual(expected, self.names())
        self.assertNotIn("produce", self.names())

    def test_unavailable_routing_does_not_downgrade_or_complete(self):
        self.assertEqual({"produce"}, self.names())
        self.session.runtime["available_pairs"] = []
        steps = self.session.checkpoint(100)
        self.assertFalse(any(step["kind"] in {"execute", "complete"} for step in steps))
        self.assertTrue(steps)
        self.assertRegex(json.dumps(steps), r"(?i)capability|model|routing|available")

    def test_existing_lease_resumes_without_duplicate_dispatch(self):
        acquired = self.session.acquire("produce")
        steps = self.session.checkpoint(100)
        self.assertFalse(any(step.get("kind") == "execute" and step.get("node", {}).get("node") == "produce"
                             for step in steps))
        serialized = json.dumps(steps)
        self.assertIn(acquired["bound_actor"], serialized)
        self.assertRegex(serialized, r"(?i)resume|wait|owned|running")
        self.session.finish(acquired, {"value": "resumed"})
        self.assertEqual({"review_a", "review_b"}, self.names())


if __name__ == "__main__":
    unittest.main()
