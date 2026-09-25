"""Safe version entry and goal isolation at existing production boundaries.

Conversion evidence must not obtain authority from arbitrary submitted JSON.
No conversion engine or provider transaction protocol is implemented here.
"""

from __future__ import annotations

import json
import unittest
import copy
import base64
import re
import zlib
from types import SimpleNamespace
from unittest import mock

import test_zzzops as fixtures
import test_evidence_dag_journeys as dag
from test_evidence_dag import task, selector, scope


z = fixtures.zzzops


class ConversionTransport:
    """Provider effects and injected lost responses, never conversion logic."""
    def __init__(self, issue, *, fault=None, timing="before", concurrent=False):
        self.issue = copy.deepcopy(issue)
        self.comments = []
        self.events = []
        self.fault, self.timing, self.concurrent = fault, timing, concurrent
        self.fired = False

    def get_issue(self, number):
        assert number == self.issue["number"]
        return copy.deepcopy(self.issue)

    def get_issue_comments(self, number):
        assert number == self.issue["number"]
        return copy.deepcopy(self.comments)

    def effect(self, boundary, mutate):
        fail = boundary == self.fault and not self.fired
        if fail:
            self.fired = True
        if fail and self.timing == "before":
            if self.concurrent:
                self.issue["body"] += "\nNewer user content: never overwrite."
                self.issue["updated_at"] = "2026-09-25T00:00:00Z"
            raise TimeoutError("Injected uncertain provider response before " + boundary)
        result = mutate()
        self.events.append(boundary)
        if fail and self.timing == "after":
            if self.concurrent:
                self.issue["body"] += "\nNewer user content: never overwrite."
                self.issue["updated_at"] = "2026-09-25T00:00:00Z"
            raise TimeoutError("Injected lost provider response after " + boundary)
        return result

    def create_issue_comment(self, number, body):
        assert number == self.issue["number"]
        # Observable protocol sequence is backup, intent, body, labels, receipt.
        # Encoding is opaque; the production helper determines its contents.
        stage = ("backup", "intent", "receipt")[min(len(self.comments), 2)]
        def mutate():
            comment = {"id": len(self.comments) + 1, "body": body,
                       "html_url": f"https://example.test/issues/{number}#c{len(self.comments)+1}"}
            self.comments.append(comment)
            return copy.deepcopy(comment)
        return self.effect(stage, mutate)

    def update_issue(self, number, payload):
        assert number == self.issue["number"]
        stage = "body" if "body" in payload else "labels"
        def mutate():
            self.issue.update(copy.deepcopy(payload))
            self.issue["updated_at"] = f"2026-09-24T12:00:{len(self.events):02d}Z"
            return copy.deepcopy(self.issue)
        return self.effect(stage, mutate)


class GoalEnvelopeTests(unittest.TestCase):
    def envelope(self):
        digest = "sha256:" + "1" * 64
        return {"schema_version": 2, "repository": "owner/repo", "issue": 100,
                "revision": 1, "state": "open",
                "payload": {"hash": digest, "uri": "urn:" + digest}}

    def body(self, value):
        return "Human specification must survive.\n<!-- zzzops-goal\n" + json.dumps(value) + "\nzzzops-goal -->"

    def parse(self, body):
        return z._goals.parse_managed_goal(body, 100)

    def valid_control(self):
        envelope = self.envelope()
        self.assertEqual(envelope, self.parse(self.body(envelope)))
        return envelope

    def test_v2_identity_envelope_is_readable_without_decoding_payload(self):
        self.valid_control()

    def test_boolean_schema_version_is_not_an_integer_version(self):
        envelope = self.valid_control()
        envelope["schema_version"] = True
        with self.assertRaisesRegex(ValueError, r"(?i)version|integer|schema"):
            self.parse(self.body(envelope))


class ConversionDurabilityTests(unittest.TestCase):
    """Proposed private seam in existing goals.py, not a replacement engine.

    activate_goal_conversion(adapter, repository, number, prepared, request_id)
    consumes an already independently reviewed conversion, retaining exact source,
    target and authority references. Public task admission must authenticate those
    references; these tests isolate provider retry/recovery after that admission.
    """
    def fixture(self, **fault):
        issue = fixtures.PortfolioTests().issue(100)
        source = copy.deepcopy(issue)
        digest = "sha256:" + "3" * 64
        envelope = {"schema_version": 2, "repository": "owner/repo", "issue": 100,
                    "revision": 1, "state": "open", "payload": {"hash": digest, "uri": "urn:" + digest}}
        target = "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"
        prepared = {"repository": "owner/repo", "issue": 100, "source": source,
                    "target_body": target, "target_labels": ["zzzops", "zzzops:schema:v2"],
                    "converter": "fixture_converter_v2", "policy": "sha256:" + "4" * 64,
                    "review": {"hash": "sha256:" + "5" * 64, "uri": "urn:sha256:" + "5" * 64},
                    "approval": {"hash": "sha256:" + "6" * 64, "uri": "urn:sha256:" + "6" * 64},
                    "missing_obligations": ["Current generic verification and independent review"],
                    "mapped_evidence": []}
        return ConversionTransport(issue, **fault), prepared

    def activate(self, provider, prepared, request="conversion-100"):
        helper = getattr(z._goals, "activate_goal_conversion", None)
        self.assertTrue(callable(helper), "Missing production conversion-activation seam")
        return helper(provider, "owner/repo", 100, copy.deepcopy(prepared), request)

    def valid_control(self):
        provider, prepared = self.fixture()
        self.activate(provider, prepared)
        self.assertEqual(prepared["target_body"], provider.issue["body"])
        self.assertEqual(["backup", "intent", "body", "labels", "receipt"], provider.events)
        self.assertEqual(prepared["target_labels"], provider.issue["labels"])
        self.assert_bindings(provider, prepared)
        return provider, prepared

    def assert_bindings(self, provider, prepared):
        def decode(comment):
            body = comment["body"]
            encoded = re.search(r"```text\n([A-Za-z0-9+/=]+)\n```", body)
            if encoded:
                return json.loads(zlib.decompress(base64.b64decode(encoded[1])))
            return json.loads(body)
        def descendants(value):
            yield value
            if isinstance(value, dict):
                for child in value.values():
                    yield from descendants(child)
            elif isinstance(value, list):
                for child in value:
                    yield from descendants(child)
        backup = list(descendants(decode(provider.comments[0])))
        self.assertIn(prepared["source"], backup, "Backup must preserve exact source body and provider metadata")
        intent = list(descendants(decode(provider.comments[1])))
        for expected in ("owner/repo", 100, prepared["policy"], prepared["review"],
                         prepared["approval"], prepared["converter"],
                         z._phase_evidence.sha256_digest(prepared["source"]),
                         z._phase_evidence.sha256_digest({"body": prepared["target_body"], "labels": prepared["target_labels"]})):
            self.assertIn(expected, intent, "Intent omitted exact conversion/authority binding")

    def test_all_durable_boundaries_recover_before_and_after_lost_responses(self):
        self.valid_control()
        for stage in ("backup", "intent", "body", "labels", "receipt"):
            for timing in ("before", "after"):
                with self.subTest(boundary=stage, timing=timing):
                    provider, prepared = self.fixture(fault=stage, timing=timing)
                    try:
                        self.activate(provider, prepared)
                    except (TimeoutError, ValueError):
                        pass  # Recovery can be immediate readback or explicit retry.
                    retained = copy.deepcopy(provider.comments[:2])
                    self.activate(provider, prepared)
                    self.assertEqual(prepared["target_body"], provider.issue["body"])
                    self.assertEqual(prepared["target_labels"], provider.issue["labels"])
                    self.assert_bindings(provider, prepared)
                    self.assertEqual(retained, provider.comments[:len(retained)],
                                     "Retry rewrote immutable backup/intent")
                    before = copy.deepcopy((provider.issue, provider.comments, provider.events))
                    self.activate(provider, prepared)
                    self.assertEqual(before, (provider.issue, provider.comments, provider.events))

    def test_concurrent_user_edit_is_never_overwritten_by_retry_or_rollback(self):
        self.valid_control()
        for stage in ("backup", "intent", "body", "labels", "receipt"):
            with self.subTest(boundary=stage):
                provider, prepared = self.fixture(fault=stage, timing="after", concurrent=True)
                try:
                    self.activate(provider, prepared)
                except (TimeoutError, ValueError):
                    pass
                self.assertIn("Newer user content", provider.issue["body"])
                observed = copy.deepcopy(provider.issue)
                try:
                    result = self.activate(provider, prepared)
                except ValueError:
                    result = {"status": "blocked"}
                self.assertEqual(observed, provider.issue)
                self.assertNotEqual("activated", result.get("status"))

    def test_exact_receipt_rejects_changed_target_under_same_request(self):
        provider, prepared = self.valid_control()
        before = copy.deepcopy((provider.issue, provider.comments))
        changed = copy.deepcopy(prepared)
        changed["target_body"] += "\nDifferent content"
        with self.assertRaisesRegex(ValueError, r"(?i)receipt|request|payload|conflict"):
            self.activate(provider, changed)
        self.assertEqual(before, (provider.issue, provider.comments))

    def test_closed_goal_is_archived_without_activation(self):
        self.valid_control()
        provider, prepared = self.fixture()
        provider.issue["state"] = "closed"
        before = copy.deepcopy(provider.issue)
        try:
            self.activate(provider, prepared)
        except ValueError:
            pass
        self.assertEqual(before, provider.issue)
        self.assertEqual([], provider.events)

    def test_wrong_source_or_repository_has_no_durable_effect(self):
        self.valid_control()
        for field, value in (("repository", "foreign/repo"), ("issue", 101)):
            provider, prepared = self.fixture()
            prepared[field] = value
            with self.assertRaisesRegex(ValueError, r"(?i)identity|repository|issue|source"):
                self.activate(provider, prepared)
            self.assertEqual([], provider.events)

class GoalEnvelopeNegativeTests(GoalEnvelopeTests):
    test_v2_identity_envelope_is_readable_without_decoding_payload = None
    test_boolean_schema_version_is_not_an_integer_version = None
    def test_provider_issue_identity_cannot_be_overridden_by_body(self):
        envelope = self.valid_control()
        envelope["issue"] = 101
        with self.assertRaisesRegex(ValueError, r"(?i)identity|issue|mismatch"):
            self.parse(self.body(envelope))

    def test_duplicate_managed_blocks_are_not_first_match_wins(self):
        envelope = self.valid_control()
        with self.assertRaisesRegex(ValueError, r"(?i)duplicate|multiple|block"):
            self.parse(self.body(envelope) + "\n" + self.body(envelope))

    def test_duplicate_json_keys_are_not_last_writer_wins(self):
        envelope = self.valid_control()
        body = self.body(envelope).replace('"schema_version": 2', '"schema_version": 1, "schema_version": 2')
        with self.assertRaisesRegex(ValueError, r"(?i)duplicate|key"):
            self.parse(body)

    def test_future_version_reports_its_own_version(self):
        envelope = self.valid_control()
        envelope["schema_version"] = 987
        with self.assertRaisesRegex(ValueError, r"987"):
            self.parse(self.body(envelope))

    def test_unknown_envelope_fields_do_not_become_execution_authority(self):
        envelope = self.valid_control()
        envelope["migration_graph"] = {"nodes": [{"id": "approve_myself"}]}
        with self.assertRaisesRegex(ValueError, r"(?i)unknown|field|unsupported"):
            self.parse(self.body(envelope))

    def test_oversized_record_is_rejected_not_truncated(self):
        envelope = self.valid_control()
        envelope["payload"]["uri"] = "x" * (1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, r"(?i)size|large|limit|bounded"):
            self.parse(self.body(envelope))


class MigrationEntryPublicTests(dag.DagFixture):
    """Proposed policy mapping: migration_entries[{from,to,graph}].

    All actions use returned generic start/bind/submit contracts. The installed
    entry graph supplies authority; incompatible issue content supplies only data.
    First acquisition backs up exact legacy bytes, then stores an ordinary v2
    envelope with spec=legacy-source artifact and graph=trusted entry graph.
    That body owns normal evidence/leases/receipts during migration preparation;
    it is not activation of the normal graph. Final activation binds original
    source AND current preparation revision and requires exact review/approval.
    """
    def entry(self):
        self.target_envelope, self.target_payload = self.payload()
        self.target = self.blob(self.target_envelope)
        source = fixtures.PortfolioTests().issue(100)
        self.provider.issues[100] = copy.deepcopy(source)
        analyze = task("analyze")
        analyze["outputs"] = {"source": dag.output("migration_source", dag.shape(source))}
        convert = task("convert", ["analyze"])
        converted_type = {"kind": "object", "fields": {
            "source": dag.REF_TYPE, "target": dag.REF_TYPE,
            "mapped_evidence": {"kind": "array", "items": dag.REF_TYPE},
            "missing_obligations": {"kind": "array", "items": {"kind": "string"}}}}
        convert["outputs"] = {"conversion": dag.output("conversion", converted_type)}
        review = task("conversion_review", ["convert"])
        review["independent_of"] = [selector("convert")]
        approval = task("conversion_approval", ["conversion_review"], role="root")
        activate = task("activate", ["conversion_approval"], role="root")
        activate["outputs"] = {"activation": dag.output("schema_activation", dag.shape({"conversion": dag.REF, "approval": dag.REF}))}
        activate["permits"] = [{"type": "schema_activation", "scope": scope("activate", "activation")}]
        for node in (review, approval, activate):
            node["inputs"] = {"conversion": {"producer": {"node": selector("convert")},
                "output": "conversion", "path": [], "mode": "identity", "type": converted_type}}
        graph = {"nodes": [analyze, convert, review, approval, activate], "task_sets": [],
                 "terminals": [selector("activate")]}
        config = z._workflow_section(self.session.project, "workflow_adherence")["configuration"]
        config["migration_entries"] = [{"from": 1, "to": 2, "graph": graph}]
        # Migration bootstrap evidence is readable through the same artifact
        # read contract, before the incompatible body becomes an active payload.
        return source, graph

    def migration_result(self, name):
        response = self.session.call(100, {"operation": "read", "node": {"goal": 100, "node": name,
                                                                      "item": None, "generation": 1}})
        evidence = response["next_steps"][0]["content"]
        return evidence["result"], evidence["outputs"]

    def prepared(self):
        source, graph = self.entry()
        self.assertEqual({"analyze"}, self.names())
        work = self.session.acquire("analyze")
        envelope, payload = self.payload()
        self.assertEqual(2, envelope["schema_version"])
        self.assertEqual(graph, self.read_blob(payload["graph"]))
        self.assertEqual(source, self.read_blob(payload["spec"])["content"], "Entry preparation lost exact legacy source")
        self.session.finish(work, {"source": source})
        source_ref = self.migration_result("analyze")[1]["source"]
        conversion = {"source": source_ref, "target": self.target, "mapped_evidence": [],
                      "missing_obligations": ["Current verification", "Current independent review"]}
        self.session.finish(self.session.acquire("convert"), {"conversion": conversion})
        return source, conversion

    def test_trusted_entry_review_root_approval_then_activation_without_fabricated_evidence(self):
        source, conversion = self.prepared()
        converted_revision = self.payload()[0]["revision"]
        self.session = dag.TaskSession(self.fixture.repo, self.session.project, self.session.runtime,
                                       self.provider, self.session.control)
        self.assertEqual(source, self.read_blob(conversion["source"])["content"])
        self.assertEqual({"conversion_review"}, self.names())
        self.session.finish(self.session.acquire("conversion_review", actor="independent-conversion-reviewer"),
                            {"value": "Exact source preserved; evidence gaps remain missing"})
        self.assertEqual({"conversion_approval"}, self.names())
        approval = self.session.acquire("conversion_approval")
        self.assertEqual("root-thread", approval["bound_actor"])
        self.session.finish(approval, {"value": "Fixture user approves exact conversion"})
        self.assertGreater(self.payload()[0]["revision"], converted_revision,
                           "Review and approval must advance canonical entry state")
        approval_ref = self.migration_result("conversion_approval")[0]
        conversion_ref = self.migration_result("convert")[1]["conversion"]
        work = self.session.acquire("activate")
        self.session.finish(work, {"activation": {"conversion": conversion_ref, "approval": approval_ref}})
        envelope, payload = self.payload()
        self.assertEqual(2, envelope["schema_version"])
        self.assertNotIn("phase_evidence", envelope)
        self.assertEqual([], self.read_blob(conversion_ref)["content"]["mapped_evidence"])
        self.assertEqual(["Current verification", "Current independent review"],
                         self.read_blob(conversion_ref)["content"]["missing_obligations"])
        self.assertIn("produce", self.names(), "Legacy history cannot manufacture current delivery results")
        self.assertEqual("open", self.provider.get_issue(100)["state"].lower(),
                         "Entry completion cannot close unfinished normal work")

    def test_unreviewed_activation_payload_cannot_bypass_entry_graph(self):
        source, _conversion = self.prepared()
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        request = {"operation": "submit", "node": {"goal": 100, "node": "activate", "item": None, "generation": 1},
                   "actor": "root-thread", "lease": "invented", "request_id": "bypass",
                   "outputs": {"activation": {"conversion": self.target, "approval": self.target}}}
        response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)lease|approval|prerequisite|ownership")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertEqual(source, self.read_blob(_conversion["source"])["content"])

    def test_missing_conversion_target_ref_rejected_before_any_activation(self):
        source, _graph = self.entry()
        self.session.finish(self.session.acquire("analyze"), {"source": source})
        work = self.session.acquire("convert")
        source_ref = self.migration_result("analyze")[1]["source"]
        valid = {"source": source_ref, "target": self.target, "mapped_evidence": [], "missing_obligations": ["verification"]}
        invalid = {**valid, "target": {"hash": "sha256:" + "f" * 64, "uri": "urn:sha256:" + "f" * 64}}
        self.assert_rejected(work, {"conversion": valid}, {"outputs": {"conversion": invalid}},
                             r"(?i)missing|artifact|reference|target")

    def test_closed_record_is_not_reopened_or_migrated_by_active_entry(self):
        source, _graph = self.entry()
        self.provider.issues[100]["state"] = "closed"
        self.provider.issues[100]["labels"] = [{"name": "zzzops"}, {"name": "zzzops:status:done"}, {"name": "zzzops:priority:P2"}]
        self.provider.issues[100]["body"] = "<!-- zzzops-goal\nmalformed archived bytes\nzzzops-goal -->"
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        # Use the actual archived projection at the provider gateway boundary;
        # full no-hydration discovery is separately tested on real transport.
        self.session.portfolio_snapshot = lambda *_a, **_k: {
            "complete": True, "valid": True,
            "goals": [z.github_archived_goal_record(self.provider.get_issue(100))]}
        steps = self.session.checkpoint(100)
        self.assertFalse(any(step.get("kind") == "execute" for step in steps))
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_incompatible_body_cannot_supply_its_own_migration_graph(self):
        source, _graph = self.entry()
        self.assertEqual({"analyze"}, self.names())
        body = self.provider.issues[100]["body"]
        match = re.search(r"<!-- zzzops-goal\s*\n(.*?)\nzzzops-goal -->", body, re.S)
        legacy = json.loads(match[1])
        legacy["migration"] = {"approved": True, "graph": {"nodes": [task("grant_approval")]}}
        legacy["graph"] = legacy["migration"]["graph"]
        self.provider.issues[100]["body"] = body[:match.start(1)] + json.dumps(legacy) + body[match.end(1):]
        steps = self.session.call(100, expected=None)["next_steps"]
        self.assertFalse(any(s.get("kind") == "execute" and s.get("node", {}).get("node") != "analyze" for s in steps))
        self.assertNotIn("grant_approval", [s.get("node", {}).get("node") for s in steps])

    def test_forged_prepared_entry_graph_is_not_authority_on_restart(self):
        self.prepared()  # authenticated valid control before injected corruption
        envelope, payload = self.payload()
        payload["graph"] = self.blob({"nodes": [task("grant_approval", role="root")],
                                     "task_sets": [], "terminals": [selector("grant_approval")]})
        envelope["payload"] = self.blob(payload)
        self.provider.issues[100]["body"] = GoalEnvelopeTests().body(envelope)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session = dag.TaskSession(self.fixture.repo, self.session.project, self.session.runtime,
                                       self.provider, self.session.control)
        steps = self.session.call(100, expected=None)["next_steps"]
        self.assertFalse(any(s.get("kind") == "execute" for s in steps))
        self.assertRegex(json.dumps(steps), r"(?i)trusted|migration|authority|graph|preparation")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_activation_rejects_changed_entry_revision_without_partial_effects(self):
        self.prepared()
        self.session.finish(self.session.acquire("conversion_review", actor="independent-conversion-reviewer"),
                            {"value": "Reviewed exact conversion"})
        self.session.finish(self.session.acquire("conversion_approval"), {"value": "Approve reviewed conversion"})
        activation = {"conversion": self.migration_result("convert")[1]["conversion"],
                      "approval": self.migration_result("conversion_approval")[0]}
        work = self.session.acquire("activate")
        # External drift, not an alternative semantic write operation: a stale
        # acquired activation cannot overwrite a newer canonical entry record.
        envelope, _payload = self.payload()
        original = copy.deepcopy(self.provider.issues[100])
        envelope["revision"] += 1
        self.provider.issues[100]["body"] = GoalEnvelopeTests().body(envelope)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        rejected = self.session.call(100, self.session.submission(work, {"activation": activation}, "stale-activation"), expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)revision|stale|changed|conflict")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.provider.issues[100] = original  # restore injected drift for valid control
        self.session.finish(work, {"activation": activation})
        self.assertIn("produce", self.names())
        self.assertEqual("open", self.provider.get_issue(100)["state"].lower())

    def test_entry_task_restart_uses_same_canonical_evidence_and_original_source(self):
        source, graph = self.entry()
        original_update = self.provider.update_issue
        original_body = source["body"]
        def source_preserving_write(number, payload):
            if "body" in payload and payload["body"] != original_body:
                proposed = json.loads(re.search(r"<!-- zzzops-goal\s*\n(.*?)\nzzzops-goal -->", payload["body"], re.S)[1])
                proposed_payload = self.read_blob(proposed["payload"])
                self.assertEqual(source, self.read_blob(proposed_payload["spec"])["content"],
                                 "Exact backup must already exist before entry-body replacement")
            return original_update(number, payload)
        self.provider.update_issue = source_preserving_write
        first = self.session.acquire("analyze")
        token, actor = first["lease"]["token"], first["bound_actor"]
        self.session = dag.TaskSession(self.fixture.repo, self.session.project, self.session.runtime,
                                       self.provider, self.session.control)
        steps = self.session.checkpoint(100)
        self.assertIn(actor, json.dumps(steps))
        self.assertFalse(any(step.get("kind") == "execute" and step.get("node", {}).get("node") == "analyze" for step in steps))
        self.session.finish(first, {"source": source})
        retained = self.result("analyze")[0]
        self.session = dag.TaskSession(self.fixture.repo, self.session.project, self.session.runtime,
                                       self.provider, self.session.control)
        self.assertEqual({"convert"}, self.names())
        self.assertEqual(retained, self.result("analyze")[0])
        self.assertEqual(graph, self.read_blob(self.payload()[1]["graph"]))
        self.assertNotIn("produce", self.names(), "Preparation is not normal-goal activation")


if __name__ == "__main__":
    unittest.main()
