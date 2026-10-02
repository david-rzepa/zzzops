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
from pathlib import Path
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
                "revision": 1, "state": "open", "parent": None,
                "payload": {"hash": digest, "uri": "urn:" + digest}}

    def body(self, value):
        return "Human specification must survive.\n<!-- zzzops-goal\n" + json.dumps(value) + "\nzzzops-goal -->"

    def parse(self, body):
        return z._goals.parse_managed_goal(body, 100)

    def valid_control(self):
        envelope = self.envelope()
        try:
            parsed = self.parse(self.body(envelope))
        except ValueError as exc:
            self.fail("Production rejected the valid revision16 envelope: " + str(exc))
        self.assertEqual(envelope, parsed)
        return envelope

    def test_v2_identity_envelope_is_readable_without_decoding_payload(self):
        self.valid_control()

    def test_boolean_schema_version_is_not_an_integer_version(self):
        envelope = self.valid_control()
        envelope["schema_version"] = True
        with self.assertRaisesRegex(ValueError, r"(?i)version|integer|schema"):
            self.parse(self.body(envelope))

    def test_parent_is_required_nullable_positive_integer_not_historical_guess(self):
        envelope = self.valid_control()
        envelope["parent"] = 99
        self.assertEqual(envelope, self.parse(self.body(envelope)))
        for parent in (True, 0, -1, 1.5, "99", "#parent"):
            with self.subTest(parent=parent):
                invalid = {**envelope, "parent": parent}
                with self.assertRaisesRegex(ValueError, r"(?i)parent|integer|identity"):
                    self.parse(self.body(invalid))
        del envelope["parent"]
        with self.assertRaisesRegex(ValueError, r"(?i)parent|missing|field"):
            self.parse(self.body(envelope))


class GenericPortfolioMetadataTests(unittest.TestCase):
    def issue(self, priority="P1", status="new"):
        fixture = GoalEnvelopeTests()
        return {"number": 100, "title": "Preserve reviewed priority",
                "body": fixture.body(fixture.envelope()), "state": "open",
                "labels": [{"name": label} for label in
                           ("zzzops", f"zzzops:priority:{priority}", f"zzzops:status:{status}")]}

    def test_conversion_preserves_all_supported_priorities_without_legacy_status_drift(self):
        for priority in ("P0", "P1", "P2", "P3"):
            with self.subTest(priority=priority):
                record = z.github_goal_record(self.issue(priority))
                self.assertEqual(priority, record["priority"])
                self.assertEqual([], z.audit_portfolio([record], "github_issues"))

    def test_ambiguous_or_unknown_priority_is_rejected_without_mutation(self):
        for labels in (("P1", "P2"), ("P9",)):
            with self.subTest(priorities=labels):
                issue = self.issue()
                issue["labels"] = [f"zzzops:priority:{value}" for value in labels]
                before = copy.deepcopy(issue)
                with self.assertRaisesRegex(ValueError, "priority"):
                    z.github_goal_record(issue)
                self.assertEqual(before, issue)

    def test_missing_priority_keeps_default_and_required_label_diagnostic(self):
        issue = self.issue()
        issue["labels"] = ["zzzops", "zzzops:status:new"]
        record = z.github_goal_record(issue)
        self.assertEqual("P2", record["priority"])
        findings = z.audit_portfolio([record], "github_issues")
        self.assertEqual(["label_drift"], [finding["code"] for finding in findings])
        self.assertIn("zzzops:priority:P2", findings[0]["detail"])

    def test_status_labels_cannot_manufacture_completion_or_reopen_closed_goals(self):
        self.assertEqual("ready", z.github_goal_record(self.issue(status="done"))["status"])
        closed = self.issue()
        closed["state"] = "closed"
        self.assertEqual("done", z.github_goal_record(closed)["status"])

    def test_legacy_status_label_audit_remains_active(self):
        issue = fixtures.PortfolioTests().issue(100)
        issue["labels"] = [label for label in issue["labels"]
                           if not label["name"].startswith("zzzops:status:")]
        findings = z.audit_portfolio([z.github_goal_record(issue)], "github_issues")
        self.assertIn("label_drift", [finding["code"] for finding in findings])


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
                    "revision": 1, "state": "open", "parent": None, "payload": {"hash": digest, "uri": "urn:" + digest}}
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

    def test_p1_entry_remains_executable_after_analyze_with_real_label_audit(self):
        self.entry()
        source = fixtures.PortfolioTests().issue(100, priority="P1", status="new")
        self.provider.issues[100] = copy.deepcopy(source)
        snapshot = self.session.portfolio_snapshot

        def audited_snapshot(*args, **kwargs):
            value = snapshot(*args, **kwargs)
            value["findings"] = z.audit_portfolio(value["goals"], "github_issues")
            value["valid"] = not value["findings"]
            return value

        self.session.portfolio_snapshot = audited_snapshot
        self.session.finish(self.session.acquire("analyze"), {"source": source})
        self.assertEqual("P1", self.session.goal(100)["priority"])
        self.assertEqual({"convert"}, self.names())
        self.assertEqual(source["labels"], self.provider.issues[100]["labels"])

    def test_selected_open_entry_is_bounded_and_retry_preserves_other_sources(self):
        source, _graph = self.entry()
        self.provider.issues[101] = fixtures.PortfolioTests().issue(101)
        self.provider.issues[102] = fixtures.PortfolioTests().issue(102)
        self.provider.issues[102]["state"] = "closed"
        for number in (101, 102):
            self.provider.comments[number] = []
        others = copy.deepcopy({number: (self.provider.issues[number], self.provider.comments[number])
                                for number in (101, 102)})
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.assertEqual({"analyze"}, self.names())
        self.assertEqual(before, (self.provider.issues, self.provider.comments),
                         "Discovery cannot automatically migrate any source")
        step = next(step for step in self.session.ready() if step["node"]["node"] == "analyze")
        receipt = json.loads(Path(step["policy"]["path"]).read_text())["policy_receipt"]
        request = {**step["start"], "policy_receipt": receipt, "request_id": "bounded-entry-start"}
        first = self.session.call(100, request)["next_steps"][0]
        prepared = copy.deepcopy((self.provider.issues, self.provider.comments))
        again = self.session.call(100, request)["next_steps"][0]
        self.assertEqual(first["lease"]["token"], again["lease"]["token"])
        self.assertEqual(prepared, (self.provider.issues, self.provider.comments))
        self.assertEqual(source, self.read_blob(self.payload()[1]["spec"])["content"])
        self.assertEqual(others, {number: (self.provider.issues[number], self.provider.comments[number])
                                  for number in (101, 102)})
        self.assertFalse(any(step.get("node", {}).get("node") == "produce"
                             for step in self.session.checkpoint(100)))

    def test_schema_label_cannot_authorize_noncompact_source_or_erase_history(self):
        source, _graph = self.entry()
        legacy = z.parse_managed_goal(source["body"], 100)
        legacy["evidence"] = ["Historical evidence must survive exactly."]
        human = ("## Outcome\nKeep this.\n\n```md\n## Evidence\nKeep fenced example.\n```\n\n"
                 "## Evidence\nArchive this without erasure.\n\n## Scope\nKeep scope.\n")
        source["body"] = z.render_managed_goal(legacy, human, 100)
        source["labels"].append({"name": "zzzops:schema:v1"})
        self.provider.issues[100] = copy.deepcopy(source)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.assertEqual({"analyze"}, self.names())
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        work = self.session.acquire("analyze")
        self.assertEqual(source, self.read_blob(self.payload()[1]["spec"])["content"])
        self.session.finish(work, {"source": source})
        self.assertEqual(source, self.read_blob(self.migration_result("analyze")[1]["source"])["content"])
        self.assertEqual({"convert"}, self.names(), "A label/source backup cannot activate normal delivery")

    def test_entry_backup_confirmation_precedes_body_replacement_and_retries_exactly(self):
        source, _graph = self.entry()
        self.assertEqual({"analyze"}, self.names())
        step = next(step for step in self.session.ready() if step["node"]["node"] == "analyze")
        receipt = json.loads(Path(step["policy"]["path"]).read_text())["policy_receipt"]
        request = {**step["start"], "policy_receipt": receipt, "request_id": "source-confirmation"}
        create, read = self.provider.create_issue_comment, self.provider.get_issue_comments
        initial_comments = copy.deepcopy(self.provider.comments[100])
        def unconfirmed_create(number, body):
            result = create(number, body)
            return {**result, "body": "Unconfirmed provider response"}
        def unconfirmed_read(number):
            known = {row["id"] for row in initial_comments}
            return [row if row["id"] in known else {**row, "body": "Unconfirmed provider readback"}
                    for row in read(number)]
        self.provider.create_issue_comment = unconfirmed_create
        self.provider.get_issue_comments = unconfirmed_read
        response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)confirm|backup|source|artifact|content|readback")
        self.assertEqual(source, self.provider.issues[100],
                         "No source replacement before exact immutable backup is confirmed")
        self.assertGreater(len(self.provider.comments[100]), len(initial_comments))
        retained = copy.deepcopy(self.provider.comments[100])
        self.provider.create_issue_comment, self.provider.get_issue_comments = create, read
        acquired = self.session.call(100, request)["next_steps"][0]
        self.assertEqual(source, self.read_blob(self.payload()[1]["spec"])["content"])
        for comment in retained:
            self.assertEqual(1, sum(row["body"] == comment["body"] for row in self.provider.comments[100]))
        after = copy.deepcopy((self.provider.issues, self.provider.comments))
        retry = self.session.call(100, request)["next_steps"][0]
        self.assertEqual(acquired["lease"]["token"], retry["lease"]["token"])
        self.assertEqual(after, (self.provider.issues, self.provider.comments))

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

    def mapped_preparation(self):
        """Proposed equivalence evidence inside existing mapped_evidence refs.

        V9 requires exact source/contract/subject equivalence but leaves this
        record's encoding to implementation. It is data reviewed by the trusted
        entry graph, never a caller-issued Result or independent authority.
        """
        source, _graph = self.entry()
        historical_output = self.blob("Previously delivered value")
        digest = dag.content_hash
        old_inputs = {"schema_version": 2, "phase": "understand", "goal_spec": digest("old-spec"),
            "policy": digest("old-policy"), "phase_dag": digest("old-graph"), "parents": [], "dependencies": [],
            "repository": {"identity": "owner/repo", "snapshot": {}},
            "provider": {"identity": "github", "snapshot": {}},
            "capabilities": {"identity": "fixture", "snapshot": {}},
            "invocation": {"intent": "execute", "inputs": {"goal": 100}},
            "upstream_outputs": [], "acceptance_criteria": ["Produce the requested value"]}
        record = {"status": "completed", "input_envelope": old_inputs, "input_hash": digest(old_inputs),
            "output": {"reference": historical_output["uri"], "hash": historical_output["hash"]},
            "verification": None, "routing": None, "selection": {"model": "worker-bounded", "effort": "medium"},
            "actor": "historical-producer", "not_required": None, "test_design": None}
        evidence = {"schema_version": 2, "records": {"understand": record}, "reviews": {},
                    "human_approvals": {}, "withdrawals": []}
        # Literal supported v1 source fixture, not execution through a legacy engine.
        legacy = fixtures.PortfolioTests().goal(phase_evidence=evidence)
        source["body"] = "## Outcome\nExact historical human text.\n<!-- zzzops-goal\n" + json.dumps(legacy) + "\nzzzops-goal -->"
        self.provider.issues[100] = copy.deepcopy(source)
        self.session.finish(self.session.acquire("analyze"), {"source": source})
        source_ref = self.migration_result("analyze")[1]["source"]
        mapping = {"source": source_ref, "source_phase": "understand",
                   "source_record_hash": digest(record), "target": {"goal": 100, "node": "produce", "item": None, "generation": 1},
                   "contract": {"node": self.graph["nodes"][0], "policy": digest(self.session.project["policy"])}, "inputs": [],
                   "outputs": {"value": historical_output},
                   "rationale": "Exact historical output satisfies this unchanged task; no review or approval is mapped"}
        mapping_ref = self.blob(mapping)
        conversion = {"source": source_ref, "target": self.target, "mapped_evidence": [mapping_ref],
                      "missing_obligations": ["review_a", "review_b", "finish"]}
        return source, record, mapping, conversion

    def test_reviewed_nonempty_historical_mapping_preserves_source_and_missing_reviews(self):
        source, record, mapping, conversion = self.mapped_preparation()
        self.session.finish(self.session.acquire("convert"), {"conversion": conversion})
        self.assertNotIn("produce", self.names(), "Preparation must not execute the normal graph")
        self.session.finish(self.session.acquire("conversion_review", actor="independent-mapping-reviewer"),
                            {"value": "Verified exact old record, current contract, input and output equivalence"})
        self.session.finish(self.session.acquire("conversion_approval"), {"value": "Root approves this exact mapping"})
        refs = {"conversion": self.migration_result("convert")[1]["conversion"],
                "approval": self.migration_result("conversion_approval")[0]}
        self.session.finish(self.session.acquire("activate"), {"activation": refs})
        self.assertEqual(source, self.read_blob(conversion["source"])["content"])
        self.assertEqual(mapping, self.read_blob(conversion["mapped_evidence"][0]))
        self.assertEqual({"review_a", "review_b"}, self.names(),
                         "Only equivalently mapped producer may be current; missing reviews remain work")
        result_ref, result = self.result("produce")
        self.assertRegex(result["contract"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(record["actor"], result["executor"], "Conversion must preserve historical producer identity")
        self.assertNotIn(result_ref, conversion["mapped_evidence"], "Host must issue mapped Result after approved activation")
        self.assertEqual("Previously delivered value", self.read_blob(result["outputs"]["value"])["content"])
        self.session = dag.TaskSession(self.fixture.repo, self.session.project, self.session.runtime,
                                       self.provider, self.session.control)
        self.assertEqual({"review_a", "review_b"}, self.names())
        self.assertEqual("open", self.provider.get_issue(100)["state"].lower())

    def test_nonempty_mapping_cannot_change_historical_output_or_contract(self):
        _source, _record, mapping, conversion = self.mapped_preparation()
        work = self.session.acquire("convert")
        for change in ({"source_record_hash": "sha256:" + "f" * 64},
                       {"contract": {"node": task("different_task"), "policy": "sha256:" + "e" * 64}},
                       {"outputs": {"value": self.blob("Fabricated replacement")}}):
            with self.subTest(change=change):
                altered = self.blob({**mapping, **change})
                invalid = {**conversion, "mapped_evidence": [altered]}
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, self.session.submission(work, {"conversion": invalid},
                                              "invalid-mapping-" + next(iter(change))), expected=2)
                self.assertRegex(json.dumps(response), r"(?i)mapping|equivalen|source|contract|output|hash")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(work, {"conversion": conversion})
        self.assertEqual({"conversion_review"}, self.names())

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



    def test_trusted_entry_uses_symbolic_self_and_preserves_predecessor_parent(self):
        source, graph = self.entry()
        def symbolic(value):
            if isinstance(value, list):
                return [symbolic(item) for item in value]
            if isinstance(value, dict):
                return {key: "#this" if key == "goal" and item == 100 else symbolic(item)
                        for key, item in value.items()}
            return value
        graph = symbolic(graph)
        config = z._workflow_section(self.session.project, "workflow_adherence")["configuration"]
        config["migration_entries"] = [{"from": 1, "to": 2, "graph": graph}]
        legacy = fixtures.PortfolioTests().goal(parent=99)
        source["body"] = "## Outcome\nMigrate the exact historical goal and preserve its parent.\n\n<!-- zzzops-goal\n" + json.dumps(legacy) + "\nzzzops-goal -->"
        self.provider.issues[100] = copy.deepcopy(source)
        self.provider.issues[99] = fixtures.PortfolioTests().issue(99)
        self.provider.comments[99] = []
        target = {**self.target_envelope, "parent": 99}
        self.target = self.blob(target)
        self.session.finish(self.session.acquire("analyze"), {"source": source})
        self.assertEqual(99, self.payload()[0]["parent"], "Trusted predecessor decoding must preserve canonical parent")
        self.assertEqual(graph, self.read_blob(self.payload()[1]["graph"]))
        conversion = {"source": self.migration_result("analyze")[1]["source"], "target": self.target,
                      "mapped_evidence": [], "missing_obligations": ["Current independent review"]}
        self.session.finish(self.session.acquire("convert"), {"conversion": conversion})
        self.session.finish(self.session.acquire("conversion_review", actor="independent-reviewer"), {"value": "Exact parent and source verified"})
        self.session.finish(self.session.acquire("conversion_approval"), {"value": "Root approves exact conversion"})
        work = self.session.acquire("activate")
        self.session.finish(work, {"activation": {"conversion": self.migration_result("convert")[1]["conversion"],
                                                  "approval": self.migration_result("conversion_approval")[0]}})
        self.assertEqual(99, self.payload()[0]["parent"])
        self.assertEqual(source, self.read_blob(conversion["source"])["content"])
        self.assertIn("produce", self.names(), "Preserving relationship metadata never fabricates delivery")


    def test_mixed_history_exact_refs_preserve_predecessor_snapshots_and_live_coordination(self):
        self.mixed_history()

    def test_approval_bearing_historical_snapshots_remain_data_after_conversion(self):
        self.mixed_history(approved=True)

    def mixed_history(self, approved=False):
        from test_goal_history_delta import legacy_history_body, semantic_predecessor
        initial, graph = self.entry()
        if approved:
            # Pure supported predecessor codecs build historical fixture data;
            # no legacy scheduler, lease acquisition or active result routing.
            from test_phase_review_contract import PhaseReviewContractTests
            historical = PhaseReviewContractTests()
            old_input = historical.envelope("plan")
            old_record = historical.record("plan", old_input)
            evidence = z._phase_evidence.record_phase_result(None, "plan", old_record, old_input)
            raw = z.parse_managed_goal(initial["body"], 100)
            raw["phase_evidence"] = evidence
            initial["body"] = z.render_managed_goal(raw, "## Outcome\nPreserve exact historical approvals as evidence.\n", 100)
        initial["html_url"] = "https://github.com/owner/repo/issues/100"
        self.provider.issues[100] = copy.deepcopy(initial)
        first_snapshot = semantic_predecessor(initial["body"], 100)
        predecessor = z.parse_managed_goal(initial["body"], 100)
        predecessor.update(revision=predecessor["revision"] + 1, next_action="Continue after historical transition")
        if approved:
            evidence = z._phase_evidence.record_phase_review(evidence, "plan", historical.artifact("exact old review"),
                "historical-independent-reviewer", outcomes={"acceptance": "approved",
                "entropy": {"outcome": "no_findings", "evidence": "No additional historical findings", "goals": []}})
            evidence = z._phase_evidence.record_phase_approval(evidence, "plan", "root", "user: exact historical approval")
            predecessor["phase_evidence"] = evidence
        transition = {"schema_version": 1, "expected_revision": predecessor["revision"] - 1,
                      "expected_digest": z.github_goal_record(initial)["digest"], "goal": predecessor}
        legacy = legacy_history_body(initial, transition)
        legacy_comment = self.provider.create_issue_comment(100, legacy)
        # Historical transport fixture, not dispatch through a retired engine.
        z.apply_goal_transition(self.provider, "owner/repo", 100, transition)
        source = copy.deepcopy(self.provider.issues[100])
        second_snapshot = semantic_predecessor(source["body"], 100)
        if approved:
            self.assertEqual(old_record, first_snapshot["goal"]["phase_evidence"]["records"]["plan"])
            self.assertEqual(evidence, second_snapshot["goal"]["phase_evidence"])
            self.assertTrue(evidence["reviews"]["plan"])
            self.assertTrue(evidence["human_approvals"]["plan"])
        reconstructed = z._goals.reconstruct_goal_history(self.provider, 100, first_snapshot["goal"]["revision"])
        self.assertEqual(first_snapshot, {key: reconstructed[key] for key in ("goal", "human_spec")})
        comments = copy.deepcopy(self.provider.comments[100])
        # Exact JSON strings preserve arbitrary historical structures, including
        # empty collections, without introducing a second active schema grammar.
        history = {"first_snapshot": json.dumps(first_snapshot, sort_keys=True),
                   "second_snapshot": json.dumps(second_snapshot, sort_keys=True),
                   "comments": json.dumps(comments, sort_keys=True)}
        self.assertEqual(first_snapshot, json.loads(history["first_snapshot"]))
        self.assertEqual(second_snapshot, json.loads(history["second_snapshot"]))
        self.assertEqual(comments, json.loads(history["comments"]))
        schema = dag.shape(history)
        graph["nodes"][0]["outputs"]["history"] = dag.output("historical_sources", schema)
        graph["nodes"][1]["inputs"] = {"history": {"producer": {"node": selector("analyze")},
            "output": "history", "path": [], "mode": "identity", "type": schema}}
        z._workflow_section(self.session.project, "workflow_adherence")["configuration"]["migration_entries"][0]["graph"] = graph
        analyze = self.session.acquire("analyze")
        self.session.finish(analyze, {"source": source, "history": history})
        source_ref = self.migration_result("analyze")[1]["source"]
        history_ref = self.migration_result("analyze")[1]["history"]
        conversion = {"source": source_ref, "target": self.target, "mapped_evidence": [],
                      "missing_obligations": ["Current normal delivery and independent reviews"]}
        self.session.finish(self.session.acquire("convert"), {"conversion": conversion})
        self.session.finish(self.session.acquire("conversion_review", actor="history-conversion-reviewer"),
                            {"value": "Exact source and mixed historical evidence independently inspected"})
        self.session.finish(self.session.acquire("conversion_approval"), {"value": "Root approves exact reviewed conversion"})
        entry_result = self.migration_result("conversion_approval")[0]
        self.session.finish(self.session.acquire("activate"), {"activation": {
            "conversion": self.migration_result("convert")[1]["conversion"], "approval": entry_result}})
        producer = self.session.acquire("produce")
        self.session.finish(producer, {"value": "New generic normal evidence"})
        normal_ref = self.produced("produce")
        reviewer = self.session.acquire("review_a", actor="current-normal-reviewer")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        expected = [(source_ref, source), (history_ref, history), (normal_ref, "New generic normal evidence")]
        for reference, content in expected:
            artifact = self.session.read(100, reference)
            self.assertEqual(content, artifact["content"])
        self.assertEqual(self.read_blob(entry_result), self.session.read(100, entry_result))
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        current = self.payload()[1]["operational"]
        self.assertTrue(any(item["token"] == reviewer["lease"]["token"] for item in current["leases"]))
        for comment in comments:
            self.assertIn(comment, self.provider.comments[100], "Mixed predecessor transaction bytes are immutable history")
        self.assertEqual(legacy, next(comment["body"] for comment in self.provider.comments[100]
                                     if comment["id"] == legacy_comment["id"]))
        self.session.finish(reviewer, {"value": "Current reviewer remains owner after all historical reads"})
        # Cross-version revision numbers are not a global history identity. This
        # control uses exact host Refs and makes no renumbering/API assumption.

    def test_predecessor_owner_must_be_observed_stopped_before_fresh_generic_entry_lease(self):
        from test_workflow_state import WorkflowStateValidationTests
        source, _graph = self.entry()
        self.assertEqual({"analyze"}, self.names(), "Owner-free predecessor is the valid entry control")
        predecessor = z.parse_managed_goal(source["body"], 100)
        predecessor["workflow"] = WorkflowStateValidationTests().valid()
        lease = predecessor["workflow"]["leases"]["plan:review"]
        source["body"] = z.render_managed_goal(predecessor, "## Outcome\nPreserve unresolved predecessor ownership.\n", 100)
        self.provider.issues[100] = copy.deepcopy(source)
        for timestamp in (lease["expires_at"] - 1, lease["expires_at"] + 1):
            with self.subTest(timestamp=timestamp), mock.patch.object(z._workflow.time, "time", return_value=timestamp):
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, expected=None)
                self.assertFalse(any(step.get("kind") == "execute" for step in response["next_steps"]))
                self.assertRegex(json.dumps(response), r"(?i)owner|worker|lease|recover|migration")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        with mock.patch.object(z._workflow.time, "time", return_value=lease["expires_at"] + 1):
            response = self.session.call(100, expected=None)
            recovery = next(step for step in response["next_steps"]
                            if "recovery_contract" in step or step.get("kind") == "recover")
            request = copy.deepcopy(recovery.get("submission", recovery.get("recovery_contract")))
            self.assertEqual(lease["token"], request["lease"])
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            self.session.call(100, {**request, "worker_status": "unknown", "evidence": "Expiry is not termination"}, expected=2)
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
            self.session.call(100, {**request, "lease": "another-owner", "worker_status": "stopped",
                                   "evidence": "Different worker stopped"}, expected=2)
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
            self.session.call(100, {**request, "worker_status": "stopped",
                                   "evidence": "Exact predecessor reviewer terminal state observed"})
        recovered_source = copy.deepcopy(self.provider.issues[100])
        analyze = self.session.acquire("analyze")
        self.assertNotEqual(lease["token"], analyze["lease"]["token"])
        self.assertEqual("submit", analyze["submission"]["operation"])
        self.assertEqual(recovered_source, self.read_blob(self.payload()[1]["spec"])["content"])
        self.session.finish(analyze, {"source": recovered_source})
        self.assertNotIn("produce", self.names(), "Source analysis does not invent conversion review or activation")

    def test_v1_cutover_rejects_phase_operations_and_uses_only_generic_submission(self):
        source, graph = self.entry()
        steps = self.session.checkpoint(100)
        self.assertEqual({"analyze"}, {step["node"]["node"] for step in steps if step.get("kind") == "execute"})
        self.assertFalse(any(step.get("phase") in {"understand", "decompose", "plan", "test_design", "implement"} for step in steps))
        for operation in ("record_result", "record_review", "approve"):
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            response = self.session.call(100, {"operation": operation, "phase": "understand", "actor": "root-thread"}, expected=2)
            self.assertRegex(json.dumps(response), r"(?i)legacy|operation|generic|unsupported|migration")
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
        analyze = self.session.acquire("analyze")
        self.assertEqual("submit", analyze["submission"]["operation"])
        self.session.finish(analyze, {"source": source})
        conversion = {"source": self.migration_result("analyze")[1]["source"], "target": self.target,
                      "mapped_evidence": [], "missing_obligations": ["Current delivery and reviews"]}
        self.session.finish(self.session.acquire("convert"), {"conversion": conversion})
        self.session.finish(self.session.acquire("conversion_review", actor="independent-reviewer"), {"value": "Exact conversion inspected"})
        self.session.finish(self.session.acquire("conversion_approval"), {"value": "Root approves exact conversion"})
        self.session.finish(self.session.acquire("activate"), {"activation": {
            "conversion": self.migration_result("convert")[1]["conversion"],
            "approval": self.migration_result("conversion_approval")[0]}})
        self.assertEqual(2, self.payload()[0]["schema_version"])
        produce = self.session.acquire("produce")
        self.assertEqual("submit", produce["submission"]["operation"])
        self.session.finish(produce, {"value": "Generic normal execution"})
        self.assertEqual({"review_a", "review_b"}, self.names())
        self.assertEqual(source, self.read_blob(conversion["source"])["content"])

if __name__ == "__main__":
    unittest.main()
