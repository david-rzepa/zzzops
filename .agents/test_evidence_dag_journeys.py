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
import re
import time
import statistics
import hashlib
import importlib
import sys
from types import SimpleNamespace
from unittest import mock

import test_workflow_journey as old
from test_workflow_owned_outputs import PublicSession, content_hash
from test_evidence_dag import review_graph, selector, scope, subject_input, task


z = old.z
REAL_PR_STATES = z._github_pull_request_states


def run_generic_regressions(owner, *test_ids):
    """Run explicitly mapped replacement assertions, never a legacy scheduler.

    Old regression IDs remain executable entrypoints. Each names exact current
    tests preserving its invariant; this helper only manages unittest fixtures.
    It does not translate operations, synthesize results, or choose readiness.
    """
    for test_id in test_ids:
        module, class_name, method = test_id.rsplit(".", 2)
        case = getattr(importlib.import_module(module), class_name)(method)
        with owner.subTest(generic_regression=test_id):
            try:
                case.setUp()
                getattr(case, method)()
                case.tearDown()
            finally:
                case.doCleanups()


def shape(value):
    """Construct closed fixture schemas, never validate data or execute work."""
    if value is None:
        return {"kind": "null"}
    if isinstance(value, bool):
        return {"kind": "boolean"}
    if isinstance(value, int):
        return {"kind": "integer"}
    if isinstance(value, str):
        return {"kind": "string"}
    if isinstance(value, list):
        assert value, "Use an explicit schema for empty fixture arrays"
        return {"kind": "array", "items": shape(value[0])}
    return {"kind": "object", "fields": {key: shape(item) for key, item in value.items()}}


REF = {"hash": "sha256:" + "0" * 64, "uri": "urn:sha256:" + "0" * 64}
REF_TYPE = shape(REF)
NULL_REF = {"kind": "union", "variants": [{"kind": "null"}, REF_TYPE]}
SELECTION_TYPE = {"kind": "object", "fields": {
    "items": {"kind": "map", "values": {"kind": "string"}},
    "rationale": {"kind": "string"}}}


def output(kind, schema):
    return {"type": kind, "schema": schema}


def spec_input():
    return {"producer": {"slot": "spec"}, "output": "content", "path": [],
            "mode": "content", "type": {"kind": "string"}}


def selected_graph():
    select = task("select", role="root")
    select["inputs"] = {"request": spec_input()}
    select["outputs"] = {"chosen": output("selection", SELECTION_TYPE)}
    template = task("investigate", ["select"])
    template["executor"]["authority"] = {"subject": {"kind": "self"}, "output": "value"}
    template["inputs"] = {"item": {
        "producer": {"node": selector("select")}, "output": "chosen",
        "path": ["items", {"item_key": True}], "mode": "content", "type": {"kind": "string"}}}
    join = {"kind": "join", "goal": 100, "expansion": "buckets"}
    synthesize = task("synthesize")
    synthesize["requires"] = [join]
    synthesize["independent_of"] = [join]
    return {"nodes": [select, synthesize], "task_sets": [{"id": "buckets", "source": {
        "producer": {"node": selector("select")}, "output": "chosen", "path": [],
        "mode": "content", "type": SELECTION_TYPE}, "template": template}],
        "terminals": [selector("synthesize")]}


FINDING_TYPE = shape({"id": "f", "revision": 1, "source": REF, "subjects": [REF],
                      "target": scope("produce"), "request": "fix", "rationale": "evidence", "supersedes": None})
FINDING_TYPE["fields"]["supersedes"] = NULL_REF
BINDING_TYPE = shape({"name": "request", "source": REF, "path": ["content"], "mode": "content"})
ADMISSION_TYPE = {"kind": "object", "fields": {
    "finding": REF_TYPE, "target_inputs": {"kind": "array", "items": BINDING_TYPE},
    "authority": REF_TYPE, "applicability": {"kind": "enum", "values": ["applicable", "not_applicable", "unresolved"]},
    "rationale": {"kind": "string"}}}
RESOLUTION_TYPE = shape({"finding": REF, "subjects": [REF], "reviewer_result": REF,
                         "decision": "resolved", "rationale": "verified"})
SOURCE_SAMPLE = {"provider": "github", "id": "comment_1", "revision": 1,
                 "author": "external-reviewer", "body": "Please fix both defects", "subject": REF,
                 "surface": "issue", "commit": "a" * 40, "path": "source.py"}


def correction_graph():
    producer = task("produce")
    producer["inputs"] = {"request": spec_input()}
    source = task("ingest", role="root")
    source["outputs"] = {"comment": output("source", shape(SOURCE_SAMPLE))}
    finder = task("find", ["produce", "ingest"])
    finder["inputs"] = {"subject": subject_input("produce")}
    finder["outputs"] = {slot: output("finding", FINDING_TYPE) for slot in ("first", "second")}
    finder["permits"] = [{"type": "finding", "scope": scope("produce")}]
    authorize = task("authorize", ["produce"], role="root")
    authorize["inputs"] = {"subject": subject_input("produce")}
    admit = task("admit", ["find", "authorize"], role="root")
    admit["inputs"] = {"subject": subject_input("produce")}
    admit["outputs"] = {slot: output("admission", ADMISSION_TYPE) for slot in ("first", "second")}
    admit["permits"] = [{"type": "admission", "scope": scope("produce")}]
    review = task("review", ["produce"])
    review["inputs"] = {"subject": subject_input("produce")}
    review["independent_of"] = [selector("produce")]
    resolve = task("resolve", ["review"])
    resolve["inputs"] = {"subject": subject_input("produce")}
    resolve["independent_of"] = [selector("produce")]
    resolve["resolves"] = [scope("produce")]
    resolve["outputs"] = {slot: output("resolution", RESOLUTION_TYPE) for slot in ("first", "second")}
    resolve["permits"] = [{"type": "resolution", "scope": scope("produce")}]
    finish = task("finish", ["resolve"], role="root")
    finish["gates"] = [scope("produce")]
    return {"nodes": [producer, source, finder, authorize, admit, review, resolve, finish],
            "task_sets": [], "terminals": [selector("finish")]}


class TaskSession(PublicSession):
    def ready(self, number=100):
        return [step for step in self.checkpoint(number) if step.get("kind") == "execute"]

    def acquire(self, name, *, number=100, actor=None, item=None):
        ready = self.ready(number)
        matches = [step for step in ready if step["node"]["node"] == name
                   and step["node"].get("item") == item]
        if len(matches) != 1:
            raise AssertionError(f"Expected one ready task {name}/{item}; observed {ready!r}")
        step = matches[0]
        receipt = json.loads(Path(step["policy"]["path"]).read_text())["policy_receipt"]
        request = {**step["start"], "policy_receipt": receipt}
        request.pop("request_id", None)
        acquired = self.call(number, request)["next_steps"][0]
        identity = actor or ("root-thread" if step["assignment"] == "root" else f"worker-{name}-{item}")
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


class DagFixture(unittest.TestCase):
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
                         "revision": 1, "state": "open", "parent": None, "payload": payload}
        self.provider.issues[100]["body"] = (
            "## Outcome\nProduce and independently review a value.\n\n<!-- zzzops-goal\n"
            + json.dumps(self.envelope) + "\nzzzops-goal -->")

    def names(self):
        return {step["node"]["node"] for step in self.session.ready()}

    def produce(self):
        acquired = self.session.acquire("produce")
        self.session.finish(acquired, {"value": "version one"})
        return acquired

    def read_blob(self, ref):
        expected = ref["hash"]
        # Exercise the public targeted read, including legacy/full/delta codecs.
        # Unrelated retained history must not become this Ref's working set.
        value = self.session.read(100, ref)
        self.assertEqual(expected, content_hash(value))
        return value

    def payload(self):
        body = self.provider.issues[100]["body"]
        envelope = json.loads(re.search(r"<!-- zzzops-goal\s*\n(.*?)\nzzzops-goal -->", body, re.S)[1])
        return envelope, self.read_blob(envelope["payload"])

    def result(self, name, item=None):
        _envelope, payload = self.payload()
        for ref in reversed(payload["evidence"]):
            artifact = self.read_blob(ref)
            if artifact["type"] == "result" and artifact["content"]["node"]["node"] == name \
                    and artifact["content"]["node"].get("item") == item:
                return ref, artifact["content"]
        self.fail("No host-issued result for " + name)

    def produced(self, name, slot="value", item=None):
        return self.result(name, item)[1]["outputs"][slot]

    def replace_spec(self, content):
        """Synthetic external source revision, not a fake execution result."""
        envelope, payload = self.payload()
        spec = self.read_blob(payload["spec"])
        spec["content"] = content
        payload["spec"] = self.blob(spec)
        envelope["payload"] = self.blob(payload)
        envelope["revision"] += 1
        self.provider.issues[100]["body"] = "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"

    def choose(self, items):
        acquired = self.session.acquire("select")
        self.session.finish(acquired, {"chosen": {"items": items, "rationale": "Evidence selects this exact work."}})
        return acquired

    def members(self):
        return {(step["node"]["item"], step["node"]["generation"])
                for step in self.session.ready() if step["node"].get("item") is not None}

    def findings(self, *, applicability="applicable", admit=True, surface="issue", graph=None):
        self.install(graph or correction_graph())
        self.produce()
        subject = self.produced("produce")
        if surface == "pr":
            actual = {"id": 701, "body": "Please add the missing regression test",
                      "commit_id": "a" * 40, "path": "source.py", "user": {"login": "external-reviewer"}}
            self.pr_comments = {701: actual}
            # Model the real PR review-comment endpoint, separately from issue
            # comments. No workflow/evidence decision is replaced by this mock.
            with mock.patch.object(z.subprocess, "run", return_value=SimpleNamespace(
                    returncode=0, stdout=json.dumps([actual]), stderr="")) as transport:
                reader = getattr(z, "read_pull_request_correction_sources", None)
                self.assertTrue(callable(reader), "Missing production PR correction-source reader")
                actual = reader(self.fixture.repo, "owner/repo", 9,
                                marker={"updated_at": "2026-09-24T00:00:00Z", "head_oid": "a" * 40})[0]
                self.assertTrue(transport.called)
                self.assertIn("repos/owner/repo/pulls/9/comments", transport.call_args.args[0])
        else:
            actual = self.provider.create_issue_comment(100, "Please fix both defects")
        self.bound_comment_id = actual["id"]
        comment = {**SOURCE_SAMPLE, "id": f"{surface}_comment_{actual['id']}",
                   "body": actual["body"], "subject": subject, "surface": surface}
        self.session.finish(self.session.acquire("ingest"), {"comment": comment})
        source = self.produced("ingest", "comment")
        findings = {slot: {"id": slot, "revision": 1, "source": source, "subjects": [subject],
                          "target": scope("produce"), "request": "Repair " + slot,
                          "rationale": "Observed failing behavior " + slot, "supersedes": None}
                    for slot in ("first", "second")}
        self.session.finish(self.session.acquire("find"), findings)
        self.session.finish(self.session.acquire("authorize"), {"value": "Authorize in-scope corrections"})
        admissions = {slot: {"finding": self.produced("find", slot),
                            "target_inputs": self.result("produce")[1]["inputs"],
                            "authority": self.result("authorize")[0],
                            "applicability": applicability,
                            "rationale": "Compared exact current subject and required scope"}
                      for slot in ("first", "second")}
        if admit:
            self.session.finish(self.session.acquire("admit"), admissions)
        return findings, admissions

    def resolve_findings(self, admissions):
        self.session.finish(self.session.acquire("review", actor="independent-reviewer"), {"value": "Correction verified"})
        resolutions = {slot: {"finding": admission["finding"], "subjects": [self.produced("produce")],
                              "reviewer_result": self.result("review")[0], "decision": "resolved",
                              "rationale": "Independent verification inspected this revision"}
                       for slot, admission in admissions.items()}
        work = self.session.acquire("resolve", actor="independent-resolution-assessor")
        self.session.finish(work, resolutions)
        return resolutions

    def assert_rejected(self, acquired, outputs, changes, diagnostic):
        # Positive control is acquired from the real ready frontier, never an
        # unsupported schema. Retain the lease for a successful valid retry.
        payload = self.session.submission(acquired, outputs, "negative-request")
        payload.update(changes)
        before = copy.deepcopy(self.provider.issues)
        comments = copy.deepcopy(self.provider.comments)
        response = self.session.call(100, payload, expected=2)
        self.assertRegex(json.dumps(response), diagnostic)
        self.assertEqual(before, self.provider.issues)
        self.assertEqual(comments, self.provider.comments, "Rejected bundle leaked durable artifacts")
        self.session.finish(acquired, outputs, "valid-after-negative-" + acquired["lease"]["attempt"])

class EvidenceDagPublicTests(DagFixture):
    def test_specialist_missing_regression_corrects_tests_then_code_and_rereviews(self):
        self.regression_correction("specialist")

    def test_failed_verification_corrects_missing_regression_without_rerunning_requirements(self):
        self.regression_correction("verification")

    def regression_correction(self, origin):
        requirements = task("requirements", role="root")
        tests = task("tests", ["requirements"])
        code = task("code", ["tests"])
        code["inputs"] = {"tests": subject_input("tests")}
        verify = task("verification", ["code"])
        verify["inputs"] = {"code": subject_input("code")}
        risk = task("specialist", ["verification"])
        risk["inputs"] = {"code": subject_input("code"), "tests": subject_input("tests")}
        risk["independent_of"] = [selector("code"), selector("tests")]
        finding_node = task("interpret_risk", ["specialist"])
        finding_node["outputs"] = {"finding": output("finding", FINDING_TYPE)}
        finding_node["permits"] = [{"type": "finding", "scope": scope("tests")}]
        admit = task("admit_risk", ["interpret_risk"], role="root")
        admit["outputs"] = {"admission": output("admission", ADMISSION_TYPE)}
        admit["permits"] = [{"type": "admission", "scope": scope("tests")}]
        resolve = task("resolve_risk", ["specialist"])
        resolve["outputs"] = {"resolution": output("resolution", RESOLUTION_TYPE)}
        resolve["independent_of"] = [selector("tests"), selector("code")]
        resolve["resolves"] = [scope("tests")]
        resolve["permits"] = [{"type": "resolution", "scope": scope("tests")}]
        finish = task("publish", ["resolve_risk"])
        finish["gates"] = [scope("tests")]
        self.install({"nodes": [requirements, tests, code, verify, risk, finding_node, admit, resolve, finish],
                      "task_sets": [], "terminals": [selector("publish")]})
        for name, text in (("requirements", "Handle empty inputs"), ("tests", "Only ordinary-input regression"),
                           ("code", "Initial implementation"), ("verification", "FAIL: empty input crashes" if origin == "verification" else "Current tests pass"),
                           ("specialist", "Missing empty-input regression and wrong empty-input behavior")):
            self.session.finish(self.session.acquire(name), {"value": text})
        requirements_result = self.result("requirements")[0]
        finding = {"id": "missing_regression", "revision": 1, "source": self.produced(origin),
                   "subjects": [self.produced("tests"), self.produced("code")], "target": scope("tests"),
                   "request": "Add the missing empty-input regression before repairing code",
                   "rationale": "Specialist located the smallest sufficient test correction", "supersedes": None}
        self.session.finish(self.session.acquire("interpret_risk"), {"finding": finding})
        ref = self.produced("interpret_risk", "finding")
        self.session.finish(self.session.acquire("admit_risk"), {"admission": {
            "finding": ref, "target_inputs": self.result("tests")[1]["inputs"],
            "authority": requirements_result, "applicability": "applicable", "rationale": "Existing requirement, same scope"}})
        self.assertIn("tests", self.names())
        self.assertNotIn("code", self.names())
        self.assertNotIn("publish", self.names())
        self.session.finish(self.session.acquire("tests"), {"value": "Meaningful empty-input regression"})
        self.assertIn("code", self.names())
        self.session.finish(self.session.acquire("code"), {"value": "Correct empty-input behavior"})
        self.session.finish(self.session.acquire("verification"), {"value": "Regression and preservation suite pass"})
        self.session.finish(self.session.acquire("specialist"), {"value": "Exact code and regression verified"})
        self.session.finish(self.session.acquire("resolve_risk"), {"resolution": {
            "finding": ref, "subjects": [self.produced("tests"), self.produced("code")],
            "reviewer_result": self.result("specialist")[0], "decision": "resolved",
            "rationale": "Independent specialist inspected both repaired outputs"}})
        self.assertIn("publish", self.names())
        self.assertEqual(requirements_result, self.result("requirements")[0])

    def test_parent_impact_is_root_decision_without_automatic_contract_rewrite(self):
        graph = correction_graph()
        escalation = task("parent_decision", ["find"], role="root")
        escalation["inputs"] = {"finding": {"producer": {"node": selector("find")}, "output": "first",
                                              "path": [], "mode": "identity", "type": FINDING_TYPE}}
        graph["nodes"].append(escalation)
        _findings, admissions = self.findings(graph=graph, applicability="unresolved")
        parent = old.fixtures.PortfolioTests().issue(99)
        original = copy.deepcopy(parent)
        # Parent data is a source artifact, not a malformed active legacy goal
        # injected into this v2 session's portfolio gateway.
        parent_ref = self.blob({"type": "parent_contract", "content": parent, "producer": None,
                                "provenance": {"actor": "root-thread", "source": None, "policy": content_hash(self.session.project["policy"])}})
        work = self.session.acquire("parent_decision")
        self.assertEqual("root-thread", work["bound_actor"])
        self.session.finish(work, {"value": "Parent contract impact requires an explicit parent-goal decision; do not broaden this child"})
        self.assertEqual(original, self.read_blob(parent_ref)["content"])
        self.assertNotIn("finish", self.names())
        self.assertFalse(any(step["kind"] == "complete" for step in self.session.checkpoint(100)))
        self.assertEqual("unresolved", self.read_blob(self.produced("admit", "first"))["content"]["applicability"])

    def test_worker_capacity_and_resource_conflicts_limit_dispatch(self):
        graph = review_graph()
        for node in graph["nodes"][1:3]:
            node["executor"]["resources"] = ["shared_checkout"]
        self.install(graph)
        self.produce()
        first = self.session.acquire("review_a")
        self.assertNotIn("review_b", self.names())
        self.session.finish(first, {"value": "reviewed"})
        self.assertIn("review_b", self.names())
        self.session.finish(self.session.acquire("review_b"), {"value": "reviewed"})
        self.assertIn("finish", self.names())

    def test_root_approval_rejects_worker_then_accepts_root(self):
        self.produce()
        for name in ("review_a", "review_b"):
            self.session.finish(self.session.acquire(name), {"value": "reviewed"})
        approval = self.session.acquire("finish")
        self.assert_rejected(approval, {"value": "Explicit root decision"}, {"actor": "outside-worker"},
                             r"(?i)root|actor|worker|authority")

    def test_light_and_richer_renamed_graphs_execute_without_domain_branches(self):
        for richer in (False, True):
            graph = review_graph()
            if not richer:
                graph["nodes"] = [n for n in graph["nodes"] if n["id"] != "review_b"]
                graph["nodes"][-1]["requires"] = [selector("review_a")]
            names = {"produce": "alpha_71", "review_a": "beta_82", "review_b": "gamma_93", "finish": "delta_04"}
            def renamed(value):
                if isinstance(value, list):
                    return [renamed(v) for v in value]
                if isinstance(value, dict):
                    return {key: names.get(v, v) if key in {"id", "node"} and isinstance(v, str)
                            else renamed(v) for key, v in value.items()}
                return value
            self.install(renamed(graph))
            self.assertEqual({"alpha_71"}, self.names())
            self.session.finish(self.session.acquire("alpha_71"), {"value": "subject"})
            expected = {"beta_82", "gamma_93"} if richer else {"beta_82"}
            self.assertEqual(expected, self.names())
            for name in sorted(expected):
                self.session.finish(self.session.acquire(name), {"value": "reviewed"})
            self.assertEqual({"delta_04"}, self.names())
            self.session.finish(self.session.acquire("delta_04"), {"value": "root decision"})
            self.assertFalse(self.session.ready())

    def test_lighter_policy_proposal_preserves_findings_and_requires_exact_approval(self):
        _findings, admissions = self.findings()
        old_evidence = [self.read_blob(value["finding"]) for value in admissions.values()]
        self.adopt_graph({"nodes": [task("produce")], "task_sets": [], "terminals": [selector("produce")]})
        steps = self.session.checkpoint(100)
        self.assertFalse(any(step["kind"] == "complete" for step in steps), "Lighter policy cannot erase debt")
        self.assertEqual(old_evidence, [self.read_blob(value["finding"]) for value in admissions.values()])
        self.assertRegex(json.dumps(steps), r"(?i)finding|obligation|reconcil|migration|policy|review")

    def test_stronger_policy_requires_added_independent_review_and_preserves_history(self):
        self.produce()
        for name in ("review_a", "review_b"):
            self.session.finish(self.session.acquire(name), {"value": "Inspected original graph"})
        old_result = self.result("produce")[0]
        old_output = self.produced("produce")
        graph = review_graph()
        extra = task("additional_check", ["produce"])
        extra["inputs"] = {"subject": subject_input("produce")}
        extra["independent_of"] = [selector("produce")]
        graph["nodes"].insert(-1, extra)
        graph["nodes"][-1]["requires"].append(selector("additional_check"))
        self.adopt_graph(graph)
        self.assertNotIn("finish", self.names(), "Old approvals cannot satisfy a new prerequisite")
        self.assertEqual(old_output, self.read_blob(old_result)["content"]["outputs"]["value"])
        # Conservative policy rebinding may require fresh unchanged work when
        # equivalence is unproven. Either route must actually perform the new
        # independent review, never manufacture it from previous approval.
        if "produce" in self.names():
            self.produce()
        for name in ("review_a", "review_b", "additional_check"):
            if name in self.names():
                self.session.finish(self.session.acquire(name), {"value": "Reviewed exact current policy and subject"})
        self.assertIsNotNone(self.result("additional_check")[0])
        self.assertIn("finish", self.names())

    def adopt_graph(self, graph):
        """Existing reviewed policy gate, never direct active-graph mutation."""
        initializer = old.fixtures.InitializationTests()
        initializer.repo = self.fixture.repo
        with mock.patch.object(z, "inspect_initialization", return_value={"base_digest": z.initialization_base_digest(self.fixture.repo)}):
            proposal = initializer.plan()
        proposal["repository"]["identity"] = "owner/repo"
        proposal["policy"] = copy.deepcopy(self.session.project["policy"])
        # The fixture substitutes its available model pairs for the shipped
        # inventory. Describe that customization; the public policy gate builds
        # its provenance and still requires approval of the exact proposal.
        routing = next(s for s in proposal["policy"]["sections"] if s["id"] == "model_routing")
        routing["default_disposition"] = "changed"
        backend = next(s for s in proposal["policy"]["sections"] if s["id"] == "backend")
        backend["configuration"].update(repository_identity="owner/repo", authority="github_issues")
        backend["default_disposition"] = "changed"
        workflow = next(s for s in proposal["policy"]["sections"] if s["id"] == "workflow_adherence")
        workflow["configuration"]["phase_dag"] = graph
        workflow["default_disposition"] = "changed"
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        preview = self.session.call(100, {"operation": "policy_propose", "plan": proposal})
        approval = next(step for step in preview["next_steps"] if step["kind"] == "human_approval")
        self.assertIn("hash", approval)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        unauthorized = {**approval["submission"], "approved_by": "<not approved>"}
        response = self.session.call(100, unauthorized, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)explicit|approval")
        self.session.call(100, {**approval["submission"], "approved_by": "fixture-user"})
        self.session.project = z.read_project_state(self.fixture.repo)[2]

    def test_human_answers_drive_affected_reinvestigation_through_generic_admission(self):
        graph = selected_graph()
        question = task("question", ["synthesize"], role="root")
        interpret = task("interpret", ["question", "select"], role="root")
        interpret["outputs"] = {"finding": output("finding", FINDING_TYPE)}
        target = scope("select", "chosen")
        interpret["permits"] = [{"type": "finding", "scope": target}]
        admit = task("admit_answers", ["interpret"], role="root")
        admit["outputs"] = {"admission": output("admission", ADMISSION_TYPE)}
        admit["permits"] = [{"type": "admission", "scope": target}]
        graph["nodes"] += [question, interpret, admit]
        graph["terminals"] = [selector("question")]
        self.install(graph)
        self.choose({"requirements": "original", "security": "unchanged"})
        for item in ("requirements", "security"):
            self.session.finish(self.session.acquire("investigate", item=item), {"value": "conclusion " + item})
        preserved = self.result("investigate", "security")[0]
        self.session.finish(self.session.acquire("synthesize", actor="independent-synthesis"), {"value": "Clarify retention duration"})
        self.session.finish(self.session.acquire("question"), {"value": "Human answer: retention is 30 days"})
        answer = self.produced("question")
        finding = {"id": "answer", "revision": 1, "source": answer,
                   "subjects": [self.produced("select", "chosen")], "target": target,
                   "request": "Update requirements bucket with the human retention answer",
                   "rationale": "Authoritative answer changes one investigation", "supersedes": None}
        self.session.finish(self.session.acquire("interpret"), {"finding": finding})
        admission = {"finding": self.produced("interpret", "finding"),
                     "target_inputs": self.result("select")[1]["inputs"],
                     "authority": self.result("question")[0], "applicability": "applicable",
                     "rationale": "Root answered this exact question"}
        self.session.finish(self.session.acquire("admit_answers"), {"admission": admission})
        self.assertIn("select", self.names())
        self.choose({"requirements": "retention 30 days", "security": "unchanged"})
        self.assertEqual({("requirements", 1)}, self.members())
        self.assertEqual(preserved, self.result("investigate", "security")[0])
        self.assertEqual("Human answer: retention is 30 days", self.read_blob(answer)["content"])

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

    def test_selection_missing_empty_one_and_many_are_distinct(self):
        for items in ({}, {"a": "first"}, {"a": "first", "b": "second"}):
            with self.subTest(items=items):
                self.install(selected_graph())
                self.assertEqual({"select"}, self.names())
                self.assertNotIn("synthesize", self.names())
                self.choose(items)
                self.assertEqual({(key, 1) for key in items}, self.members())
                if items:
                    self.assertNotIn("synthesize", self.names())
                for item in items:
                    acquired = self.session.acquire("investigate", item=item)
                    self.session.finish(acquired, {"value": "conclusion " + item})
                self.assertEqual({"synthesize"}, self.names())
                synthesis = self.session.acquire("synthesize", actor="independent-synthesizer")
                self.session.finish(synthesis, {"value": "synthesized"})
                self.assertFalse(self.session.ready())

    def test_new_bucket_preserves_unchanged_sibling_but_join_waits(self):
        self.install(selected_graph())
        self.choose({"requirements": "inspect requirements"})
        work = self.session.acquire("investigate", item="requirements")
        self.session.finish(work, {"value": "settled"})
        original = self.result("investigate", "requirements")[0]
        self.replace_spec("New evidence adds a migration bucket")
        self.assertNotIn("synthesize", self.names())
        self.choose({"requirements": "inspect requirements", "migration": "inspect conversion"})
        self.assertEqual({("migration", 1)}, self.members())
        self.assertEqual(original, self.result("investigate", "requirements")[0])
        self.assertNotIn("synthesize", self.names())

    def test_changed_bucket_reruns_only_affected_investigation(self):
        self.install(selected_graph())
        self.choose({"a": "original", "b": "unchanged"})
        for item in ("a", "b"):
            self.session.finish(self.session.acquire("investigate", item=item), {"value": item})
        sibling = self.result("investigate", "b")[0]
        self.replace_spec("Human answer changes only investigation a")
        self.choose({"a": "revised", "b": "unchanged"})
        self.assertEqual({("a", 1)}, self.members())
        self.assertEqual(sibling, self.result("investigate", "b")[0])

    def test_reactivation_rejects_retired_generation_worker(self):
        self.install(selected_graph())
        self.choose({"a": "inspect"})
        old_work = self.session.acquire("investigate", item="a")
        self.replace_spec("Retire a with no findings")
        self.choose({})
        self.replace_spec("Reactivate the same item")
        self.choose({"a": "inspect"})
        self.assertEqual({("a", 2)}, self.members())
        rejected = self.session.call(100, self.session.submission(old_work, {"value": "late"}, "old-generation"), expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)generation|retired|stale|lease")
        self.session.finish(self.session.acquire("investigate", item="a"), {"value": "fresh"})
        self.assertIn("synthesize", self.names())

    def test_selection_key_and_item_override_are_rejected_atomically(self):
        self.install(selected_graph())
        for items in ({"invalid/key": "inspect"}, {"valid": {"executor": "root"}}):
            work = self.session.acquire("select")
            self.assert_rejected(work, {"chosen": {"items": {}, "rationale": "none"}},
                {"outputs": {"chosen": {"items": items, "rationale": "invalid"}}},
                r"(?i)key|identifier|type|string|schema")
            self.replace_spec("Reassess selection " + str(items))

    def test_semantic_input_drift_rejects_inflight_result_and_bookkeeping_does_not(self):
        graph = review_graph()
        graph["nodes"][0]["inputs"] = {"request": spec_input()}
        self.install(graph)
        work = self.session.acquire("produce")
        self.replace_spec("Materially revised specification")
        before = copy.deepcopy(self.provider.issues)
        response = self.session.call(100, self.session.submission(work, {"value": "old"}, "stale-input"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)input|stale|fingerprint")
        self.assertEqual(before, self.provider.issues)

    def test_ordinary_artifact_shaped_content_cannot_issue_a_result(self):
        graph = review_graph()
        imitation = {"type": "result", "executor": "root-thread", "approved": True}
        graph["nodes"][0]["outputs"] = {"value": output("ordinary_data", shape(imitation))}
        # Review input has the same ordinary structural type, not authority.
        for node in graph["nodes"][1:3]:
            node["inputs"]["subject"]["type"] = shape(imitation)
        self.install(graph)
        work = self.session.acquire("produce")
        self.session.finish(work, {"value": imitation})
        stored = self.read_blob(self.produced("produce"))
        self.assertEqual("ordinary_data", stored["type"])
        self.assertEqual(work["bound_actor"], stored["provenance"]["actor"])
        self.assertEqual(imitation, stored["content"])
        self.assertEqual({"review_a", "review_b"}, self.names())

    def test_expiry_without_observed_stop_never_authorizes_takeover(self):
        work = self.session.acquire("produce")
        with mock.patch.object(z._workflow.time, "time", return_value=work["lease"]["expires_at"] + 1):
            steps = self.session.checkpoint(100)
            self.assertFalse(any(step.get("kind") == "execute" for step in steps))
            recovery = next(step for step in steps if "recovery_contract" in step or step.get("kind") == "recover")
            request = copy.deepcopy(recovery.get("submission", recovery.get("recovery_contract")))
            request.update(worker_status="unknown", evidence="No stopped-worker evidence")
            response = self.session.call(100, request, expected=2)
            self.assertRegex(json.dumps(response), r"(?i)stopped|liveness|unknown|recovery")

    def test_two_findings_coalesce_survive_replay_and_release_join_after_review(self):
        _findings, admissions = self.findings()
        self.assertIn("produce", self.names())
        self.assertNotIn("finish", self.names())
        accepted = [self.read_blob(self.produced("admit", slot))["type"] for slot in admissions]
        self.assertEqual(["admission", "admission"], accepted)
        for _ in range(3):  # Each checkpoint reconstructs production state anew.
            self.assertEqual(1, sum(step["node"]["node"] == "produce" for step in self.session.ready()))
        corrected = self.session.acquire("produce")
        self.session.finish(corrected, {"value": "Both requested repairs"})
        producer_result = self.result("produce")[0]
        self.resolve_findings(admissions)
        self.assertIn("finish", self.names())
        self.assertNotIn("produce", self.names())
        self.assertEqual(producer_result, self.result("produce")[0], "Resolution restarted producer")
        self.assertEqual("admission", self.read_blob(self.produced("admit", "first"))["type"])

    def test_unauthorized_second_admission_rolls_back_first_and_result(self):
        _findings, admissions = self.findings(admit=False)
        work = self.session.acquire("admit")
        tampered = copy.deepcopy(admissions)
        tampered["second"]["authority"] = self.produced("ingest", "comment")
        self.assert_rejected(work, admissions, {"outputs": tampered}, r"(?i)authority|approval|provenance")
        self.assertIn("produce", self.names())

    def test_stale_subject_admission_does_not_overwrite_newer_work(self):
        self.late_admission("issue")

    def test_late_pr_feedback_against_old_commit_cannot_invalidate_newer_subject(self):
        self.late_admission("pr")

    def late_admission(self, surface):
        _findings, admissions = self.findings(admit=False, surface=surface)
        work = self.session.acquire("admit")
        source = self.produced("ingest", "comment")
        retained = self.read_blob(source)
        self.replace_spec("New specification changes the inspected subject")
        self.produce()
        current = self.result("produce")[0]
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, self.session.submission(work, admissions, "late-admission"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)stale|subject|input|applicab")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertEqual(current, self.result("produce")[0])
        self.assertEqual(retained, self.read_blob(source))
        self.assertNotIn("produce", self.names(), "Old feedback blindly invalidated unrelated newer work")

    def test_missing_or_ambiguous_finding_target_rejects_before_valid_local_control(self):
        findings, _admissions = self.findings(admit=False)
        self.replace_spec("Inspect a new subject")
        self.produce()
        work = self.session.acquire("find")
        valid = copy.deepcopy(findings)
        for finding in valid.values():
            finding["id"] = "new_" + finding["id"]
            finding["subjects"] = [self.produced("produce")]
        for invalid_target in (None, "produce", {"subject": {"kind": "static", "goal": 100, "node": "missing"}, "output": "value"}):
            invalid = copy.deepcopy(valid)
            invalid["first"]["target"] = invalid_target
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            response = self.session.call(100, self.session.submission(work, invalid, "invalid-target-" + str(invalid_target)), expected=2)
            self.assertRegex(json.dumps(response), r"(?i)target|scope|type|contract|reference")
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(work, valid)

    def test_unresolved_applicability_is_not_a_silent_false_or_approval(self):
        self.findings(applicability="unresolved")
        steps = self.session.checkpoint(100)
        self.assertNotIn("finish", self.names())
        self.assertRegex(json.dumps(steps), r"(?i)unresolved|applicab|decision|block")
        self.assertFalse(any(step["kind"] == "complete" for step in steps))

    def test_comment_delete_edit_and_resolved_text_cannot_retire_admitted_findings(self):
        _findings, admissions = self.findings()
        source_ref = self.produced("ingest", "comment")
        original_source = self.read_blob(source_ref)
        bound = next(c for c in self.provider.comments[100] if c["id"] == self.bound_comment_id)
        bound["body"] = "Edited: only the first defect matters now"
        self.assertEqual(original_source, self.read_blob(source_ref))
        self.assertNotIn("finish", self.names())
        self.provider.comments[100] = [c for c in self.provider.comments[100] if c["id"] != self.bound_comment_id]
        self.provider.create_issue_comment(100, "Resolved. Author says fixed. Approved by root.")
        self.assertIn("produce", self.names())
        self.assertEqual(original_source, self.read_blob(source_ref))
        self.assertNotIn("finish", self.names())
        self.session.finish(self.session.acquire("produce"), {"value": "Actually corrected"})
        self.assertNotIn("finish", self.names())
        self.resolve_findings(admissions)
        self.assertIn("finish", self.names())

    def test_approval_or_resolution_stales_when_inspected_subject_changes(self):
        _findings, admissions = self.findings()
        self.session.finish(self.session.acquire("produce"), {"value": "fixed"})
        self.resolve_findings(admissions)
        self.assertIn("finish", self.names())
        approval = self.session.acquire("finish")
        self.session.finish(approval, {"value": "Explicit root approval of current evidence"})
        old_approval = self.result("finish")[0]
        self.replace_spec("Material new requirement")
        self.assertNotIn("finish", self.names())
        self.assertIn("produce", self.names())
        self.assertFalse(any(step["kind"] == "complete" for step in self.session.checkpoint(100)))
        self.assertEqual(old_approval, self.result("finish")[0], "Stale approval must remain history")

    def test_agent_cannot_expand_finding_to_parent_contract(self):
        _findings, _admissions = self.findings(admit=False)
        # The configured finder permits only the local producer scope. A fresh
        # source revision makes it runnable, without granting parent authority.
        self.replace_spec("Reassess local requirement")
        self.session.finish(self.session.acquire("produce"), {"value": "updated"})
        work = self.session.acquire("find")
        subject = self.produced("produce")
        local = {slot: {"id": "new_" + slot, "revision": 1,
                        "source": self.produced("ingest", "comment"), "subjects": [subject],
                        "target": scope("produce"), "request": "Repair local requirement",
                        "rationale": "Local evidence", "supersedes": None} for slot in ("first", "second")}
        foreign = copy.deepcopy(local)
        foreign["second"]["target"]["subject"]["goal"] = 99
        self.assert_rejected(work, local, {"outputs": foreign}, r"(?i)scope|authority|parent|target")

    def test_infrastructure_failure_blocks_only_verification_not_correct_producer(self):
        self.install(correction_graph())
        self.produce()
        producer = self.result("produce")[0]
        work = self.session.acquire("review")
        request = {"operation": "block", "node": work["node"], "lease": work["lease"]["token"],
                   "actor": work["bound_actor"], "category": "external-dependency",
                   "reason": "Verification service unavailable; no product defect observed"}
        self.session.call(100, request)
        self.assertEqual(producer, self.result("produce")[0])
        self.assertNotIn("produce", self.names())
        self.assertNotIn("finish", self.names())
        self.assertRegex(json.dumps(self.session.checkpoint(100)), r"(?i)verification|unavailable|dependency")

    def test_exact_admission_retry_after_it_stales_its_own_task(self):
        _findings, admissions = self.findings(admit=False)
        work = self.session.acquire("admit")
        request = self.session.submission(work, admissions, "durable-admission")
        response = self.session.call(100, request)
        self.assertIn("produce", self.names())
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.assertEqual(response, self.session.call(100, request))
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_conflicting_finding_identity_cannot_replace_prior_provenance(self):
        findings, _admissions = self.findings(admit=False)
        self.replace_spec("Reassess with current subject")
        self.session.finish(self.session.acquire("produce"), {"value": "new subject"})
        work = self.session.acquire("find")
        revised = copy.deepcopy(findings)
        for value in revised.values():
            value["subjects"] = [self.produced("produce")]
        revised["first"]["request"] = "Contradict original under same identity and revision"
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, self.session.submission(work, revised, "conflicting-finding"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)conflict|revision|identity")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        for value in revised.values():
            value["id"] = "new_" + value["id"]
        self.session.finish(work, revised)

    def test_pr_comment_source_correction_rereview_and_retained_history(self):
        _findings, admissions = self.findings(surface="pr")
        source = self.produced("ingest", "comment")
        original = self.read_blob(source)
        self.assertEqual("pr", original["content"]["surface"])
        self.assertEqual("a" * 40, original["content"]["commit"])
        self.pr_comments[701]["body"] = "Edited request after a newer commit"
        del self.pr_comments[701]
        self.assertEqual(original, self.read_blob(source))
        self.assertIn("produce", self.names())
        self.session.finish(self.session.acquire("produce"), {"value": "PR correction with regression coverage"})
        self.resolve_findings(admissions)
        self.assertIn("finish", self.names())

    def test_supersession_carries_obligation_and_only_latest_revision_needs_resolution(self):
        self.supersession("carried")

    def test_authorized_narrowing_retires_omitted_requirements_without_erasing_history(self):
        self.supersession("narrowed")

    def supersession(self, coverage):
        graph = correction_graph()
        supersession_type = shape({"prior": REF, "replacement": REF, "coverage": "carried",
                                   "coverage_evidence": REF, "authority": REF})
        amend = task("amend", ["find", "authorize"], role="root")
        amend["outputs"] = {slot: output("admission", ADMISSION_TYPE) for slot in ("first", "second")}
        amend["outputs"].update({slot + "_transfer": output("supersession", supersession_type)
                                 for slot in ("first", "second")})
        amend["permits"] = [{"type": kind, "scope": scope("produce")} for kind in ("admission", "supersession")]
        findings, old_admissions = self.findings(graph={**graph, "nodes": [*graph["nodes"], amend]})
        self.session.finish(self.session.acquire("produce"), {"value": "First repair still needs refinement"})
        revised = copy.deepcopy(findings)
        for slot, finding in revised.items():
            finding.update(revision=2, supersedes=old_admissions[slot]["finding"],
                           subjects=[self.produced("produce")], request=("Carry and refine " if coverage == "carried"
                           else "Retain only the explicitly root-approved smaller requirement for ") + slot)
        self.session.finish(self.session.acquire("find"), revised)
        self.session.finish(self.session.acquire("authorize"), {"value":
            "Both replacements carry all outstanding requirements" if coverage == "carried" else
            "Root explicitly approves removal of the omitted requirements in both exact replacements"})
        admissions = {slot: {"finding": self.produced("find", slot), "target_inputs": self.result("produce")[1]["inputs"],
                             "authority": self.result("authorize")[0], "applicability": "applicable",
                             "rationale": "Refinement carries prior scope"} for slot in revised}
        bundle = {**admissions, **{slot + "_transfer": {
            "prior": old_admissions[slot]["finding"], "replacement": admissions[slot]["finding"],
            "coverage": coverage, "coverage_evidence": self.result("authorize")[0],
            "authority": self.result("authorize")[0]} for slot in revised}}
        work = self.session.acquire("amend")
        invalid = copy.deepcopy(bundle)
        invalid["second_transfer"]["authority"] = self.produced("ingest", "comment")
        self.assert_rejected(work, bundle, {"outputs": invalid}, r"(?i)authority|coverage|supersession")
        self.assertIn("produce", self.names())
        self.session.finish(self.session.acquire("produce"), {"value": "Refined repairs"})
        self.resolve_findings(admissions)
        self.assertIn("finish", self.names(), "Superseded revisions cannot leave duplicate permanent obligations")
        for slot in revised:
            self.assertEqual(1, self.read_blob(old_admissions[slot]["finding"])["content"]["revision"])

    def test_authorized_finding_withdrawal_requires_exact_authority_and_retains_provenance(self):
        graph = correction_graph()
        # Withdrawal encoding extends the existing retirement fixture: the exact
        # finding Ref is the expected revision, not an arbitrary finding ID.
        retirement_type = shape({"finding": REF, "target": scope("produce"), "authority": REF,
                                 "decision": "withdraw", "rationale": "Approved withdrawal"})
        withdraw = task("withdraw_findings", ["authorize"], role="root")
        withdraw["outputs"] = {slot: output("retirement", retirement_type) for slot in ("first", "second")}
        withdraw["permits"] = [{"type": "retirement", "scope": scope("produce")}]
        graph["nodes"].append(withdraw)
        graph["nodes"][-2]["requires"] = [selector("produce")]
        findings, admissions = self.findings(graph=graph)
        self.assertNotIn("finish", self.names())
        self.session.finish(self.session.acquire("produce"), {"value": "Current subject awaiting disposition"})
        self.session.finish(self.session.acquire("authorize"), {"value": "Root authorizes withdrawal of these exact findings"})
        bundle = {slot: {"finding": admissions[slot]["finding"], "target": scope("produce"),
                        "authority": self.result("authorize")[0], "decision": "withdraw",
                        "rationale": "Root retires this requirement; this is not reviewer resolution"}
                  for slot in findings}
        work = self.session.acquire("withdraw_findings")
        invalid = copy.deepcopy(bundle)
        invalid["second"]["authority"] = self.produced("ingest", "comment")
        self.assert_rejected(work, bundle, {"outputs": invalid}, r"(?i)authority|withdraw|retir")
        if "produce" in self.names():
            self.session.finish(self.session.acquire("produce"), {"value": "Unchanged current subject"})
        self.assertIn("finish", self.names(), "Authorized withdrawal must release the exact retired obligations")
        for slot, original in findings.items():
            self.assertEqual(original, self.read_blob(admissions[slot]["finding"])["content"])
        self.session = TaskSession(self.fixture.repo, self.session.project, self.session.runtime,
                                   self.provider, self.session.control)
        self.assertIn("finish", self.names(), "Replay must retain the authorized retirement disposition")

    def test_generic_task_rejects_policy_drift_without_partial_semantic_publication(self):
        work = self.session.acquire("produce")
        original = copy.deepcopy(self.session.project)
        self.session.project["policy"]["reviewed"] = False
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, self.session.submission(work, {"value": "value"}, "unreviewed-policy"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)policy|review|changed|stale")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.project = original
        self.session.finish(work, {"value": "value"})

    def test_generic_task_read_dependency_and_undeclared_edit_reject_with_valid_control(self):
        work = self.session.acquire("produce")
        # Empty output authority cannot exempt either a consumed file or a new file.
        for name in ("product.txt", "unexpected.py"):
            path = self.fixture.repo / name
            original = path.read_bytes() if path.exists() else None
            try:
                path.write_text("unapproved worktree change\n")
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, self.session.submission(work, {"value": "value"}, "edit-" + name), expected=2)
                self.assertRegex(json.dumps(response), r"(?i)scope|workspace|file|input|changed")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
            finally:
                if original is None:
                    path.unlink()
                else:
                    path.write_bytes(original)
        self.session.finish(work, {"value": "value"})

    def test_generic_completed_result_without_lease_detects_consumed_file_drift(self):
        self.produce()
        before = self.result("produce")[0]
        self.assertFalse(self.payload()[1]["operational"]["leases"])
        self.assertEqual({"review_a", "review_b"}, self.names())
        path = self.fixture.repo / "product.txt"
        original = path.read_bytes()
        try:
            path.write_text("changed read input after completed result\n")
            steps = self.session.checkpoint(100)
            self.assertFalse(any(s.get("kind") == "execute" and s.get("node", {}).get("node") in
                                 {"review_a", "review_b", "finish"} for s in steps))
            self.assertEqual(before, self.result("produce")[0], "Drift must not overwrite historical evidence")
        finally:
            path.write_bytes(original)
        self.assertEqual({"review_a", "review_b"}, self.names())

    def test_host_artifact_overhead_is_preflighted_before_inline_transport_writes(self):
        work = self.session.acquire("produce")
        # The raw value fits exactly, but host type/provenance/result overhead
        # cannot silently exceed the decimal transport ceiling.
        value = "x" * (1000000 - 2)
        self.assertEqual(1000000, len(json.dumps(value).encode()))
        self.assert_rejected(work, {"value": "within budget"}, {"outputs": {"value": value}},
                             r"(?i)1000000|transport|reference|limit")

    def test_semantic_one_mib_limit_rejects_oversized_output_without_partial_bundle(self):
        work = self.session.acquire("produce")
        value = "x" * (1048576 + 1)
        self.assert_rejected(work, {"value": "within both budgets"}, {"outputs": {"value": value}},
                             r"(?i)1048576|semantic|decoded|limit")

    def published_spec(self, raw, *, claimed_hash=None):
        """Fixture publishes exact bytes locally; product receives no Git-write authority."""
        path = self.fixture.repo / "published-spec.json"
        path.write_bytes(raw)
        self.session.git("add", path.name)
        self.session.git("commit", "--allow-empty", "-qm", "fixture immutable specification")
        commit = self.session.git("rev-parse", "HEAD").strip()
        ref = {"hash": claimed_hash or "sha256:" + hashlib.sha256(raw).hexdigest(),
               "uri": f"git:{commit}:{path.name}"}
        envelope, payload = self.payload()
        payload["spec"] = ref
        envelope["payload"] = self.blob(payload)
        envelope["revision"] += 1
        self.provider.issues[100]["body"] = "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"
        return ref

    def typed_spec_bytes(self, size):
        record = {"type": "specification", "content": "", "producer": None,
                  "provenance": {"actor": "root-thread", "source": None,
                                 "policy": content_hash(self.session.project["policy"])}}
        encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        record["content"] = "x" * (size - len(encode(record)))
        raw = encode(record)
        self.assertEqual(size, len(raw))
        return raw

    def test_typed_published_inputs_support_semantic_ceiling_without_raising_transport_limit(self):
        graph = review_graph()
        graph["nodes"][0]["inputs"] = {"request": spec_input()}
        for size in (999999, 1000000, 1000001, 1048576):
            with self.subTest(size=size):
                self.install(graph)
                ref = self.published_spec(self.typed_spec_bytes(size))
                work = self.session.acquire("produce")
                self.session.finish(work, {"value": "Read exact typed published specification"})
                result = self.result("produce")[1]
                self.assertIn(ref, [binding["source"] for binding in result["inputs"]])
                artifact = self.read_blob(self.produced("produce"))
                self.assertEqual(work["bound_actor"], artifact["provenance"]["actor"])
                self.assertEqual({"review_a", "review_b"}, self.names())
        self.assertEqual(1000000, z._comment_store.MAX_ARTIFACT_BYTES)

    def test_published_inputs_require_exact_bytes_typed_decode_and_semantic_bound(self):
        graph = review_graph()
        graph["nodes"][0]["inputs"] = {"request": spec_input()}
        self.install(graph)
        self.published_spec(self.typed_spec_bytes(1000001))
        self.produce()  # valid published-ref control precedes every rejection
        valid = self.typed_spec_bytes(1000001)
        wrong_type = json.loads(valid)
        wrong_type["content"] = 17
        cases = [
            (valid, "sha256:" + "f" * 64, r"(?i)hash|bytes|identity"),
            (json.dumps(wrong_type).encode(), None, r"(?i)type|string|contract"),
            (b'{"type":"specification","type":"forged"}', None, r"(?i)duplicate|key"),
            (self.typed_spec_bytes(1048577), None, r"(?i)1048576|semantic|limit|size"),
        ]
        for raw, claimed, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic):
                self.install(graph)
                self.published_spec(raw, claimed_hash=claimed)
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, expected=None)
                self.assertFalse(any(s.get("kind") == "execute" for s in response["next_steps"]))
                self.assertRegex(json.dumps(response), diagnostic)
                self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_selection_removal_cannot_erase_unresolved_member_finding(self):
        self.member_retirement(False)

    def test_authorized_member_retirement_retains_historical_debt_on_empty_and_reactivation(self):
        self.member_retirement(True)

    def member_retirement(self, authorized):
        graph = selected_graph()
        member = {"kind": "member", "goal": 100, "expansion": "buckets", "item": "a", "generation": "current"}
        target = {"subject": member, "output": "value"}
        finding_type = copy.deepcopy(FINDING_TYPE)
        exact_member = {**member, "generation": 1}
        finding_type["fields"]["target"] = shape({"subject": exact_member, "output": "value"})
        finder = task("member_finding")
        finder["requires"] = [member]
        finder["outputs"] = {"finding": output("finding", finding_type)}
        finder["permits"] = [{"type": "finding", "scope": target}]
        admit = task("member_admit", ["member_finding"], role="root")
        admit["outputs"] = {"admission": output("admission", ADMISSION_TYPE)}
        admit["permits"] = [{"type": "admission", "scope": target}]
        resolver = task("member_resolve")
        resolver["requires"] = [member]
        resolver["resolves"] = [target]
        resolver["independent_of"] = [member]
        resolver["outputs"] = {"resolution": output("resolution", RESOLUTION_TYPE)}
        resolver["permits"] = [{"type": "resolution", "scope": target}]
        graph["nodes"][1]["gates"] = [{"subject": {"kind": "join", "goal": 100, "expansion": "buckets"}, "output": "value"}]
        graph["nodes"] += [finder, admit, resolver]
        # Proposed retirement content encoding: exact finding Ref carries its
        # expected revision; root authority permits member removal, NOT implicit
        # resolution or transfer of that finding to a new generation.
        # Accepted admission persists while its producing task becomes stale.
        # The submitted finding/authority Refs still require live accepted debt.
        retirement = task("retire_member", role="root")
        retirement["outputs"] = {"retirement": output("retirement", shape({
            "finding": REF, "target": {"subject": exact_member, "output": "value"},
            "authority": REF, "decision": "retire_member", "rationale": "Retain outstanding debt"}))}
        retirement["permits"] = [{"type": "retirement", "scope": target}]
        graph["nodes"].append(retirement)
        self.install(graph)
        self.choose({"a": "inspect"})
        self.session.finish(self.session.acquire("investigate", item="a"), {"value": "initial"})
        subject = self.produced("investigate", item="a")
        finding = {"id": "member_flaw", "revision": 1, "source": subject, "subjects": [subject],
                   "target": {"subject": exact_member, "output": "value"}, "request": "Repair missing evidence",
                   "rationale": "Inspection found a gap", "supersedes": None}
        self.session.finish(self.session.acquire("member_finding"), {"finding": finding})
        admission = {"finding": self.produced("member_finding", "finding"),
                     "target_inputs": self.result("investigate", "a")[1]["inputs"],
                     "authority": self.result("select")[0], "applicability": "applicable",
                     "rationale": "Current configured member scope"}
        retirement_work = None
        if authorized:
            retirement_work = self.session.acquire("retire_member")
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            request = self.session.submission(retirement_work, {"retirement": {
                "finding": admission["finding"], "target": finding["target"],
                "authority": self.result("select")[0], "decision": "retire_member",
                "rationale": "A finding alone grants no retirement authority"}}, "unadmitted-retirement")
            response = self.session.call(100, request, expected=2)
            self.assertRegex(json.dumps(response), r"(?i)admi|obligation|authority|finding")
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(self.session.acquire("member_admit"), {"admission": admission})
        self.assertNotIn("synthesize", self.names())
        if authorized:
            # The failed attempt retains its exact owner; no duplicate acquire.
            work = retirement_work
            self.assertEqual("root-thread", work["bound_actor"])
            self.session.finish(work, {"retirement": {"finding": admission["finding"],
                "target": finding["target"], "authority": self.result("select")[0],
                "decision": "retire_member", "rationale": "Root permits removal; historical finding remains unresolved"}})
            self.replace_spec("Root-authorized removal proposal")
            self.choose({})
            self.assertEqual(set(), self.members())
            self.assertNotIn("synthesize", self.names(), "Empty join erased historical debt")
            self.replace_spec("Reintroduce previously retired bucket")
            self.choose({"a": "inspect"})
            self.assertEqual({("a", 2)}, self.members())
            self.assertEqual(finding, self.read_blob(admission["finding"])["content"])
            self.assertNotIn("synthesize", self.names())
            return
        self.replace_spec("Propose removing the bucket")  # injected external proposal only
        work = self.session.acquire("select")
        self.assert_rejected(work, {"chosen": {"items": {"a": "inspect"}, "rationale": "Retain obligation"}},
            {"outputs": {"chosen": {"items": {}, "rationale": "Remove work"}}},
            r"(?i)retir|obligation|finding|authority")
        self.assertEqual("member_flaw", self.read_blob(admission["finding"])["content"]["id"])
        self.assertNotIn("synthesize", self.names())

    def test_pure_frontier_has_no_io_and_fixed_expanded_equal_work_budget(self):
        evaluate = getattr(z._phase_evidence, "derive_task_steps", None)
        self.assertTrue(callable(evaluate), "Missing pure production task-frontier seam")
        z._workflow_section(self.session.project, "autonomy_approval_parallelism")["configuration"]["max_workers"] = 100
        snapshots = []
        for expanded in (False, True):
            if expanded:
                self.install(selected_graph())
                self.choose({f"item_{i}": "Investigate" for i in range(100)})
            else:
                graph = {"nodes": [task(f"item_{i}") for i in range(100)],
                         "task_sets": [], "terminals": [selector(f"item_{i}") for i in range(100)]}
                self.install(graph)
            envelope, payload = self.payload()
            # Proposed pure API: actual accepted payload plus resolved immutable
            # blobs, goal/policy/runtime context; no provider object is supplied.
            refs = [payload["spec"], payload["graph"], *payload["evidence"]]
            artifacts = {ref["hash"]: self.read_blob(ref) for ref in refs}
            for artifact in list(artifacts.values()):
                if artifact.get("type") == "result":
                    for ref in artifact["content"]["outputs"].values():
                        artifacts[ref["hash"]] = self.read_blob(ref)
            context = {"goal": 100, "policy": self.session.project["policy"],
                       "runtime": self.session.runtime, "artifacts": artifacts}
            snapshots.append((copy.deepcopy(self.graph), payload, context))
        medians = []
        with mock.patch.object(z.subprocess, "run", side_effect=AssertionError("Evaluator performed provider/process I/O")):
            for graph, payload, context in snapshots:
                runs = []
                for _ in range(3):
                    started = time.perf_counter()
                    for _ in range(100):
                        result = evaluate(graph, payload, context)
                        self.assertEqual(100, len(result["ready"]))
                    runs.append(time.perf_counter() - started)
                medians.append(statistics.median(runs))
        self.assertLess(max(medians), 1.0, "Approved synthetic 100x100 local evaluator budget exceeded")
        self.assertLessEqual(medians[1] / max(medians[0], .000001), 2.0,
                             "Investigate expanded/fixed equal-work overhead above approved threshold")


class WorkspaceAuthorityPublicTests(DagFixture):
    """U1 public workspace adapter; no phase-name or alternate evaluator seam.

    Proposed host wire for independent review: ordinary submit accepts optional
    workspace_checks argument arrays. The adapter observes these commands and
    attaches its immutable proof through the output Artifact.provenance.source.
    The proof exposes acquisition_hash, input_hash, outputs, consumed and commands.
    Separate ordinary verification/review tasks consume that exact candidate.
    Authorization content below is ordinary typed evidence affirming the exact
    manifest, task identities and policy; caller content never issues a Result.
    The canonical GoalEnvelope.parent identifies the live immediate parent;
    normal cross-goal identity inputs consume its grant and authorization outputs.
    Goal 99 publishes those outputs through the same public submit path as 100.
    """

    def workspace_graph(self):
        identity = {"goal": 100, "node": "alpha", "item": None, "generation": 1}
        entry_type = {"kind": "object", "fields": {"task": shape(identity),
            "owned": {"kind": "array", "items": {"kind": "string"}},
            "consumed": {"kind": "array", "items": {"kind": "string"}}}}
        manifest_type = {"kind": "object", "fields": {
            "allocations": {"kind": "map", "values": entry_type}}}
        authorization_type = {"kind": "object", "fields": {
            "manifest": REF_TYPE, "tasks": {"kind": "array", "items": shape(identity)},
            "policy": {"kind": "string"}, "decision": {"kind": "enum", "values": ["approved"]}}}
        allocate = task("charter", role="root")
        allocate["inputs"] = {"request": spec_input()}
        allocate["outputs"] = {"grant": output("workspace_allocation", manifest_type)}
        def binding(node, slot, schema, path=()):
            return {"producer": {"node": selector(node)}, "output": slot, "path": list(path),
                    "mode": "identity", "type": schema}
        authorize = task("inspect_charter", ["charter"])
        authorize["independent_of"] = [selector("charter")]
        authorize["inputs"] = {"subject": binding("charter", "grant", manifest_type)}
        authorize["outputs"] = {"permit": output("workspace_authorization", authorization_type)}
        approve = task("consent", ["inspect_charter"], role="root")
        approve["inputs"] = {"subject": binding("charter", "grant", manifest_type),
                             "review": binding("inspect_charter", "permit", authorization_type)}
        approve["outputs"] = {"permit": output("workspace_authorization", authorization_type)}
        nodes = [allocate, authorize, approve]
        self.allocations = {"allocations": {}}
        for name, owned, after in (("alpha", ["behavior_test.py"], "consent"),
                                  ("beta", ["source.py"], "accept_alpha"),
                                  ("gamma", [], "accept_beta")):
            work = task(name, [after, "consent"] if after != "consent" else [after])
            work["executor"].update(resources=["repository_workspace"], authority=scope("charter", "grant"))
            work["inputs"] = {
                "allocation": binding("charter", "grant", entry_type, ["allocations", name]),
                "authorization": binding("inspect_charter", "permit", authorization_type),
                "approval": binding("consent", "permit", authorization_type)}
            self.allocations["allocations"][name] = {"task": {**identity, "node": name},
                "owned": owned, "consumed": ["source.py", "behavior_test.py", "read_dependency.txt"]}
            nodes.append(work)
            if name != "gamma":
                observe = task("observe_" + name, [name])
                observe["inputs"] = {"subject": subject_input(name)}
                observe["independent_of"] = [selector(name)]
                accept = task("accept_" + name, ["observe_" + name])
                accept["inputs"] = {"subject": subject_input(name), "checks": subject_input("observe_" + name)}
                accept["independent_of"] = [selector(name), selector("observe_" + name)]
                nodes.extend([observe, accept])
        return {"nodes": nodes, "task_sets": [], "terminals": [selector("gamma")]}

    def setup_workspace(self, mutate=None, *, defer_authorization=False):
        (self.fixture.repo / "source.py").write_text("def value():\n    return 1\n")
        (self.fixture.repo / "read_dependency.txt").write_text("stable dependency\n")
        self.session.git("add", "source.py", "read_dependency.txt")
        self.session.git("commit", "-qm", "workspace fixture baseline")
        graph = self.workspace_graph()
        if mutate:
            mutate(graph, self.allocations)
        self.install(graph)
        self.session.finish(self.session.acquire("charter"), {"grant": self.allocations})
        self.permit = {"manifest": self.produced("charter", "grant"),
                       "tasks": [entry["task"] for entry in self.allocations["allocations"].values()],
                       "policy": content_hash(self.session.project["policy"]), "decision": "approved"}
        if defer_authorization:
            return
        review = self.session.acquire("inspect_charter", actor="allocation-reviewer")
        self.session.finish(review, {"permit": self.permit})
        self.session.finish(self.session.acquire("consent"), {"permit": self.permit})

    def acquire_workspace(self, name):
        step = next((s for s in self.session.ready() if s["node"]["node"] == name), None)
        self.assertIsNotNone(step, "Workspace input/baseline is not ready for " + name)
        work = self.session.acquire(name, actor="writer-" + name)
        self.assertEqual(step["input_hash"], work["input_hash"], "Acquisition changed semantic inputs")
        self.assertEqual(self.allocations["allocations"][name]["task"], work["node"])
        pinned = copy.deepcopy(work["lease"]["acquisition"])
        self.assertIn(self.produced("charter", "grant")["hash"], json.dumps(pinned))
        self.assertIn(self.produced("inspect_charter", "permit")["hash"], json.dumps(pinned))
        self.assertIn(self.produced("consent", "permit")["hash"], json.dumps(pinned))
        self.assertEqual(step["input_hash"], work["input_hash"])
        return work

    def candidate(self, work, expected_exit):
        command = [sys.executable, "-B", "behavior_test.py"]
        request = self.session.submission(work, {"value": "Exact workspace candidate " + work["node"]["node"]},
                                          "candidate-" + work["node"]["node"] + "-" + work["lease"]["token"])
        request["workspace_checks"] = [command]
        self.session.call(100, request)
        artifact = self.read_blob(self.produced(work["node"]["node"]))
        proof_ref = artifact["provenance"]["source"]
        self.assertIsInstance(proof_ref, dict, "Host must publish its authenticated workspace proof")
        proof = self.read_blob(proof_ref)
        self.assertEqual(content_hash(work["lease"]["acquisition"]), proof["acquisition_hash"])
        self.assertEqual(work["input_hash"], proof["input_hash"])
        self.assertEqual(command, proof["commands"][0]["command"])
        self.assertEqual(expected_exit, proof["commands"][0]["exit_code"])
        for name in self.allocations["allocations"][work["node"]["node"]]["owned"]:
            path = self.fixture.repo / name
            expected = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "missing"
            self.assertEqual(expected, proof["outputs"][name])
        self.assertFalse(any(lease["token"] == work["lease"]["token"]
                             for lease in self.payload()[1]["operational"]["leases"]))
        return proof_ref, proof

    def review_candidate(self, name, expected_exit):
        proof_ref = self.read_blob(self.produced(name))["provenance"]["source"]
        self.assertEqual(expected_exit, self.read_blob(proof_ref)["commands"][0]["exit_code"])
        self.session.finish(self.session.acquire("observe_" + name, actor="checker-" + name),
                            {"value": "Observed exact candidate proof exit " + str(expected_exit)})
        self.session.finish(self.session.acquire("accept_" + name, actor="reviewer-" + name),
                            {"value": "Independently reviewed exact candidate and check evidence"})

    def red_candidate(self):
        alpha = self.acquire_workspace("alpha")
        (self.fixture.repo / "behavior_test.py").write_text("from source import value\nassert value() == 2\n")
        proof = self.candidate(alpha, 1)
        self.assertNotIn("beta", self.names(), "Unreviewed candidate must not authorize downstream work")
        self.review_candidate("alpha", 1)
        return alpha, proof

    def test_permitted_red_to_green_edits_keep_fingerprints_and_downstream_proof_reuse(self):
        obsolete = self.fixture.repo / "obsolete.txt"
        obsolete.write_text("Authorized deletion fixture\n")
        self.session.git("add", "obsolete.txt")
        self.session.git("commit", "-qm", "tracked deletion baseline")
        def deletion_allocation(_graph, manifest):
            manifest["allocations"]["beta"]["owned"].append("obsolete.txt")
            manifest["allocations"]["beta"]["consumed"].append("obsolete.txt")
        self.setup_workspace(deletion_allocation)
        alpha, (red_ref, red) = self.red_candidate()
        self.assertEqual("missing", red["consumed"]["behavior_test.py"], "Pin pre-edit absence despite owned test creation")
        beta = self.acquire_workspace("beta")
        pinned = copy.deepcopy(beta["lease"]["acquisition"])
        self.session.call(100, {"operation": "renew", "node": beta["node"],
            "lease": beta["lease"]["token"], "actor": beta["bound_actor"], "worker_status": "active"})
        renewed = next(lease for lease in self.payload()[1]["operational"]["leases"]
                       if lease["token"] == beta["lease"]["token"])
        self.assertEqual(pinned, renewed["acquisition"])
        self.assertEqual(beta["input_hash"], renewed["fingerprint"])
        original = hashlib.sha256((self.fixture.repo / "source.py").read_bytes()).hexdigest()
        deleted_hash = "sha256:" + hashlib.sha256(obsolete.read_bytes()).hexdigest()
        obsolete.unlink()
        (self.fixture.repo / "source.py").write_text("def value():\n    return 2\n")
        green_ref, green = self.candidate(beta, 0)
        self.assertEqual("sha256:" + original, green["consumed"]["source.py"])
        self.assertEqual(deleted_hash, green["consumed"]["obsolete.txt"])
        self.assertEqual("missing", green["outputs"]["obsolete.txt"])
        self.assertNotIn("gamma", self.names())
        self.review_candidate("beta", 0)
        before = self.result("alpha")[0], self.result("beta")[0]
        self.session.git("add", "source.py", "behavior_test.py", "obsolete.txt")
        self.session.git("commit", "-qm", "accepted source change and declared deletion")
        self.assertEqual(green, self.read_blob(green_ref))
        self.assertEqual("missing", green["outputs"]["obsolete.txt"])
        self.session = TaskSession(self.fixture.repo, self.session.project, self.session.runtime,
                                   self.provider, self.session.control)
        gamma = self.acquire_workspace("gamma")
        self.assertFalse(obsolete.exists(), "Accepted deletion must remain reusable downstream")
        self.assertEqual(before, (self.result("alpha")[0], self.result("beta")[0]))
        self.assertEqual(red, self.read_blob(red_ref), "Later green work cannot rewrite red baseline proof")
        self.session.finish(gamma, {"value": "Consumed accepted test and implementation output identities"})

    def test_acquired_owned_path_cannot_be_replaced_by_escaping_symlink(self):
        self.setup_workspace()
        work = self.acquire_workspace("alpha")
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory) / "outside.py"
            outside.write_text("raise SystemExit(0)\n")
            original = outside.read_bytes()
            owned = self.fixture.repo / "behavior_test.py"
            self.assertFalse(owned.exists())
            owned.symlink_to(outside)
            request = self.session.submission(work, {"value": "candidate"}, "escaping-owned-output")
            request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            response = self.session.call(100, request, expected=2)
            self.assertRegex(json.dumps(response), r"(?i)outside|escape|repository|worktree|symlink|scope")
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
            self.assertEqual(original, outside.read_bytes())
            owned.unlink()
            owned.write_text("from source import value\nassert value() == 2\n")
            self.candidate(work, 1)
            self.review_candidate("alpha", 1)
            self.assertIn("beta", self.names())

    def test_pending_workspace_submission_reuses_exact_observed_proof_and_log(self):
        self.setup_workspace()
        work = self.acquire_workspace("alpha")
        (self.fixture.repo / "behavior_test.py").write_text("assert False, 'required missing behavior'\n")
        command = [sys.executable, "-c", "import time; print(time.time_ns()); raise SystemExit(1)"]
        request = self.session.submission(work, {"value": "Observed variable failing baseline"}, "variable-proof-retry")
        request["workspace_checks"] = [command]
        attempted = []
        def unavailable(number, payload):
            attempted.append(copy.deepcopy(payload))
            raise z.GoalTransitionProviderError("lost before workspace body publication")
        with mock.patch.object(self.provider, "update_issue", side_effect=unavailable):
            self.session.call(100, request, expected=None)
        self.assertEqual(1, len(attempted), "Fault must reach the actual candidate publication")
        envelope = json.loads(re.search(r"<!-- zzzops-goal\s*\n(.*?)\nzzzops-goal -->", attempted[0]["body"], re.S)[1])
        pending = self.read_blob(envelope["payload"])
        results = [self.read_blob(ref) for ref in pending["evidence"]]
        result = next(value["content"] for value in reversed(results)
                      if value["type"] == "result" and value["content"]["node"]["node"] == "alpha")
        artifact = self.read_blob(result["outputs"]["value"])
        reference = artifact["provenance"]["source"]
        proof = self.read_blob(reference)
        self.assertEqual(1, proof["commands"][0]["exit_code"])
        log = Path(proof["commands"][0]["log"])
        original_log = log.read_bytes()
        original_comments = copy.deepcopy(self.provider.comments[100])
        observed_file = self.fixture.repo / "behavior_test.py"
        observed_bytes = observed_file.read_bytes()
        observed_file.write_text("assert True, 'changed after observed pending proof'\n")
        before_retry = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)output|proof|workspace|drift|changed")
        self.assertEqual(before_retry, (self.provider.issues, self.provider.comments))
        observed_file.write_bytes(observed_bytes)
        import subprocess
        original_run = subprocess.run
        reruns = []
        def observe(argv, *args, **kwargs):
            if argv == command:
                reruns.append(argv)
            return original_run(argv, *args, **kwargs)
        with mock.patch.object(subprocess, "run", side_effect=observe):
            self.session.call(100, request)
        self.assertEqual([], reruns, "Pending host proof must be recovered before executing commands again")
        self.assertEqual(original_log, log.read_bytes())
        self.assertEqual(original_comments, self.provider.comments[100])
        self.assertEqual(reference, self.read_blob(self.produced("alpha"))["provenance"]["source"])
        self.assertEqual(proof, self.read_blob(reference))
        self.review_candidate("alpha", 1)
        self.assertIn("beta", self.names())

    def test_workspace_proof_output_result_and_transition_share_one_checkpoint(self):
        self.setup_workspace()
        work = self.acquire_workspace("alpha")
        (self.fixture.repo / "behavior_test.py").write_text("assert False, 'required missing behavior'\n")
        initial_comments = len(self.provider.comments[100])
        initial_updates = len(self.provider.updates)
        proof_ref, proof = self.candidate(work, 1)
        self.assertEqual(initial_comments + 1, len(self.provider.comments[100]))
        self.assertEqual(initial_updates + 1, len(self.provider.updates))
        comment = self.provider.comments[100][-1]
        stored = z._comment_store.decode_envelope(comment["body"])
        self.assertIsNotNone(stored)
        hashes = {record["hash"] for record in stored["artifacts"]}
        for ref in (proof_ref, self.produced("alpha"), self.result("alpha")[0], self.payload()[0]["payload"]):
            self.assertIn(ref["hash"], hashes)
        self.assertIn("required missing behavior", Path(proof["commands"][0]["log"]).read_text())
        self.assertFalse(any(lease["token"] == work["lease"]["token"] for lease in self.payload()[1]["operational"]["leases"]))
        self.review_candidate("alpha", 1)

    def test_unrelated_committed_candidate_cannot_replace_acquired_git_baseline(self):
        self.setup_workspace()
        work = self.acquire_workspace("alpha")
        baseline = self.session.git("rev-parse", "HEAD")
        dependency = self.fixture.repo / "read_dependency.txt"
        original = dependency.read_bytes()
        dependency.write_text("Not the acquired Git tree\n")
        self.session.git("add", "read_dependency.txt")
        self.session.git("commit", "-qm", "unreviewed candidate tree")
        self.assertNotEqual(baseline, self.session.git("rev-parse", "HEAD"))
        dependency.write_bytes(original)
        (self.fixture.repo / "behavior_test.py").write_text("from source import value\nassert value() == 2\n")
        request = self.session.submission(work, {"value": "Allowed output cannot authorize unrelated Git baseline"}, "wrong-git-baseline")
        request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)candidate|baseline|snapshot|acquisition|workspace|drift")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.git("reset", "--mixed", baseline)  # Synthetic fixture checkout only.
        self.assertEqual(original, dependency.read_bytes())
        reference, proof = self.candidate(work, 1)
        self.assertEqual(work["input_hash"], proof["input_hash"])
        self.assertEqual(content_hash(work["lease"]["acquisition"]), proof["acquisition_hash"])
        self.review_candidate("alpha", 1)
        self.assertEqual(proof, self.read_blob(reference))

    def test_host_acquisition_raw_pins_reject_provider_corruption_before_matched_submit(self):
        self.setup_workspace()
        self.session.git("config", "core.autocrlf", "true")
        source = self.fixture.repo / "source.py"
        source.write_bytes(source.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.session.git("add", "source.py")
        self.assertEqual("", self.session.git("diff", "--cached", "--name-only"))
        self.assertEqual("", self.session.git("status", "--porcelain", "--", "source.py"))
        work = self.acquire_workspace("alpha")
        acquisition = copy.deepcopy(work["lease"]["acquisition"])
        for field in ("git_commit", "workspace_digest", "input_hash", "checkout_overrides"):
            self.assertIn(field, acquisition, "Retained host-owned workspace pin must be observable")
        self.assertIn("source.py", acquisition["checkout_overrides"])
        mutations = [("null_acquisition", None), ("partial_acquisition", {"git_commit": acquisition["git_commit"]})]
        for field, value in (("checkout_overrides", None),
                             ("checkout_overrides", {"../escape": "sha256:" + "0" * 64}),
                             ("checkout_overrides", {"source.py": "sha256:" + "0" * 64}),
                             ("git_commit", "0" * 40),
                             ("workspace_digest", "sha256:" + "0" * 64),
                             ("input_hash", "sha256:" + "0" * 64)):
            changed = copy.deepcopy(acquisition)
            changed[field] = value
            mutations.append((field + "_" + str(len(mutations)), changed))
        missing_commit = copy.deepcopy(acquisition)
        del missing_commit["git_commit"]
        mutations.append(("missing_git_commit", missing_commit))
        (self.fixture.repo / "behavior_test.py").write_text("from source import value\nassert value() == 2\n")
        request = self.session.submission(work, {"value": "Exact raw pin controls"}, "host-pin-corruption")
        request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
        original = copy.deepcopy(self.provider.issues[100])
        envelope, payload = self.payload()
        for label, value in mutations:
            with self.subTest(host_pin=label):
                changed = copy.deepcopy(payload)
                lease = next(item for item in changed["operational"]["leases"] if item["token"] == work["lease"]["token"])
                lease["acquisition"] = value
                fault = {**envelope, "payload": self.blob(changed), "revision": envelope["revision"] + 1}
                self.provider.issues[100]["body"] = "<!-- zzzops-goal\n" + json.dumps(fault) + "\nzzzops-goal -->"
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, request, expected=2)
                self.assertRegex(json.dumps(response), r"(?i)acquisition|workspace|input|pin|checkout|commit|hash|path|scope")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
                self.provider.issues[100] = copy.deepcopy(original)
        reference, proof = self.candidate(work, 1)
        self.assertEqual(content_hash(acquisition), proof["acquisition_hash"])
        self.assertEqual("sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(), proof["consumed"]["source.py"])
        self.assertEqual(proof, self.session.read(100, reference))
        self.review_candidate("alpha", 1)
        self.assertIn("beta", self.names())

    def test_caller_cannot_replace_authenticated_acquisition_with_supplied_envelope(self):
        self.setup_workspace()
        work = self.acquire_workspace("alpha")
        (self.fixture.repo / "behavior_test.py").write_text("from source import value\nassert value() == 2\n")
        request = self.session.submission(work, {"value": "candidate"}, "forged-acquisition")
        request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        for field in ("input_envelope", "acquisition"):
            rejected = self.session.call(100, {**request, field: {"input_hash": "sha256:" + "0" * 64,
                "consumed": {"source.py": "sha256:" + "0" * 64}}}, expected=2)
            self.assertRegex(json.dumps(rejected), r"(?i)field|envelope|acquisition|input|host")
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.candidate(work, 1)
        self.review_candidate("alpha", 1)
        self.assertIn("beta", self.names())

    def setup_workspace_corrections(self, target="beta", root_gate=False, correction_rounds=1):
        self.correction_target = target
        self.retained_correction_admissions = []
        self.correction_rounds = correction_rounds
        self.correction_consumer = "gamma" if target == "beta" else "beta"
        def graph_changes(graph, _allocations):
            correction = correction_graph()
            def rewrite(value):
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key == "node" and child == "produce":
                            value[key] = target
                        else:
                            rewrite(child)
                elif isinstance(value, list):
                    for child in value:
                        rewrite(child)
            rewrite(correction)
            # A finite registry names only actually admitted pairs. Missing map
            # entries keep future resolver nodes inert; omission never retires
            # the separately retained admission obligations.
            pair_type = shape({"first": REF, "second": REF})
            # Accepted admissions remain effective when their producing task
            # stales. This factual list needs the current subject/review only;
            # it cannot grant, withdraw, or refresh admission authority.
            registry = task("register_findings", ["review"], role="root")
            registry["inputs"] = {"subject": subject_input(target), "review": subject_input("review")}
            registry["outputs"] = {"pairs": output("finding_registry", {"kind": "map", "values": pair_type})}
            correction["nodes"].append(registry)
            original = next(node for node in correction["nodes"] if node["id"] == "resolve")
            template = copy.deepcopy(original)
            for index in range(correction_rounds):
                resolver = original if index == 0 else copy.deepcopy(template)
                resolver["id"] = "resolve" if index == 0 else "resolve_" + str(index + 1)
                resolver["executor"]["authority"] = scope(resolver["id"])
                resolver["requires"].append(selector("register_findings"))
                resolver["inputs"]["findings"] = {"producer": {"node": selector("register_findings")},
                    "output": "pairs", "path": ["round_" + str(index + 1)], "mode": "content", "type": pair_type}
                if index: correction["nodes"].append(resolver)
            graph["nodes"].extend(node for node in correction["nodes"] if node["id"] != "produce")
            ingest = next(node for node in graph["nodes"] if node["id"] == "ingest")
            ingest["inputs"] = {"subject": subject_input(target)}
            consumer = next(node for node in graph["nodes"] if node["id"] == self.correction_consumer)
            consumer["gates"] = [scope(target)]
            if root_gate:
                approval = task("accept_root_" + target, ["accept_" + target], role="root")
                approval["inputs"] = {"subject": subject_input(target), "review": subject_input("accept_" + target)}
                graph["nodes"].append(approval)
                consumer["requires"].append(selector(approval["id"]))
                consumer["inputs"]["root_acceptance"] = subject_input(approval["id"])
        self.setup_workspace(graph_changes)

    def admit_workspace_correction(self, target=None):
        target = target or self.correction_target
        subject = self.produced(target)
        actual = self.provider.create_issue_comment(100, "Repair this exact workspace candidate")
        # This is ordinary root-authenticated factual intake, not a reserved
        # host attestation. Supply real synthetic provider author metadata and
        # the actual fixture commit instead of claiming an invented identity.
        actual["user"] = {"login": "external-reviewer"}
        for stored in self.provider.comments[100]:
            if stored["id"] == actual["id"]:
                stored["user"] = copy.deepcopy(actual["user"])
        comment = {**SOURCE_SAMPLE, "id": "issue_comment_" + str(actual["id"]),
                   "author": actual["user"]["login"], "commit": self.session.git("rev-parse", "HEAD"),
                   "body": actual["body"], "subject": subject, "surface": "issue"}
        self.session.finish(self.session.acquire("ingest"), {"comment": comment})
        findings = {slot: {"id": slot + "_" + str(actual["id"]), "revision": 1,
            "source": self.produced("ingest", "comment"), "subjects": [subject], "target": scope(target),
            "request": "Repair " + slot, "rationale": "Observed exact candidate deficiency", "supersedes": None}
            for slot in ("first", "second")}
        self.session.finish(self.session.acquire("find"), findings)
        self.session.finish(self.session.acquire("authorize"), {"value": "Root authorizes these exact in-scope repairs"})
        admissions = {slot: {"finding": self.produced("find", slot), "target_inputs": self.result(target)[1]["inputs"],
            "authority": self.result("authorize")[0], "applicability": "applicable", "rationale": "Exact current target"}
            for slot in findings}
        self.session.finish(self.session.acquire("admit"), admissions)
        self.retained_correction_admissions.append(copy.deepcopy(admissions))
        return admissions

    def resolve_workspace_pair(self, index, admissions):
        values = {slot: {"finding": admission["finding"], "subjects": [self.produced(self.correction_target)],
            "reviewer_result": self.result("review")[0], "decision": "resolved", "rationale": "Verified exact repair"}
            for slot, admission in admissions.items()}
        name = "resolve" if index == 0 else "resolve_" + str(index + 1)
        self.session.finish(self.session.acquire(name, actor="independent-resolution-reviewer"), values)

    def resolve_workspace_correction(self, admissions, omit_retained=False):
        target = self.correction_target
        self.session.finish(self.session.acquire("review", actor="independent-correction-reviewer"),
                            {"value": "Inspected the exact corrected candidate"})
        steps = self.session.checkpoint(100)
        self.assertTrue(any(step.get("node", {}).get("node") == "admit" and
                            step.get("kind") in ("dependency", "blocked") for step in steps),
                        "The old admitting task is stale even though its accepted findings remain effective")
        self.assertIn("register_findings", self.names(), "Durable admitted facts do not require a current admitting task")
        self.assertEqual(admissions, self.retained_correction_admissions[-1])
        pairs = {"round_" + str(index + 1): {slot: admission["finding"] for slot, admission in pair.items()}
                 for index, pair in enumerate(self.retained_correction_admissions)}
        self.session.finish(self.session.acquire("register_findings"), {"pairs": pairs})
        for index in range(len(pairs), self.correction_rounds):
            self.assertNotIn("resolve_" + str(index + 1), self.names(), "Unadmitted future pair cannot dispatch a resolver")
        for index, pair in enumerate(self.retained_correction_admissions):
            if omit_retained and index < len(pairs) - 1: continue
            self.resolve_workspace_pair(index, pair)

    def red_design_correction(self, crlf=False):
        self.setup_workspace_corrections(target="alpha")
        if crlf:
            self.session.git("config", "core.autocrlf", "true")
            for name in ("source.py", "read_dependency.txt"):
                path = self.fixture.repo / name
                path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            self.session.git("add", "source.py", "read_dependency.txt")
            self.assertEqual("", self.session.git("diff", "--cached", "--name-only"))
            self.assertEqual("", self.session.git("status", "--porcelain", "--", "source.py", "read_dependency.txt"))
        first, (prior_ref, prior_proof) = self.red_candidate()
        prior_candidate = self.produced("alpha")
        prior_test = (self.fixture.repo / "behavior_test.py").read_bytes()
        admissions = self.admit_workspace_correction("alpha")
        self.assertNotIn("beta", self.names())
        correction = self.acquire_workspace("alpha")
        acquired = correction["lease"]["acquisition"]
        self.assertIn(prior_candidate["hash"], json.dumps(acquired))
        self.assertIn(prior_ref["hash"], json.dumps(acquired), "Correction binds exact observed red predecessor")
        self.assertIn("sha256:" + hashlib.sha256(prior_test).hexdigest(), json.dumps(acquired),
                      "Current produced test bytes are the authorized correction baseline")
        if crlf:
            self.assertEqual(first["lease"]["acquisition"]["checkout_overrides"], acquired["checkout_overrides"])
        (self.fixture.repo / "behavior_test.py").write_text(
            "from source import value\nassert value() == 2, 'clarified exact required behavior'\n")
        new_ref, new_proof = self.candidate(correction, 1)
        self.assertNotEqual(prior_ref, new_ref)
        self.assertEqual(1, new_proof["commands"][0]["exit_code"], "Design correction must retain the observed red baseline")
        self.assertEqual(prior_proof, self.read_blob(prior_ref))
        self.review_candidate("alpha", 1)
        self.assertNotIn("beta", self.names(), "Review alone does not resolve admitted findings")
        self.resolve_workspace_correction(admissions)
        self.assertIn("beta", self.names())
        self.assertEqual(prior_proof, self.read_blob(prior_ref))

    def test_design_correction_retains_exact_observed_red_predecessor(self):
        self.red_design_correction()

    def test_crlf_design_correction_retains_frozen_raw_checkout_overrides(self):
        self.red_design_correction(crlf=True)

    def test_host_correction_predecessor_rejects_wrong_identity_disconnected_and_unbounded_chain(self):
        """Finite proposed host wire reusing the owned-output predecessor bound.

        acquisition.predecessor is a host-issued Ref, never a caller argument.
        Its generic snapshot binds node, allocation, authorization, approval,
        result, proof, reviews and prior (Ref|null). The prior chain has the
        existing 32-hop reconstruction bound; it confers no scheduling authority.
        """
        self.setup_workspace_corrections()
        self.red_candidate()
        first = self.acquire_workspace("beta")
        (self.fixture.repo / "source.py").write_text("def value():\n    return 2\n")
        proof_ref, proof = self.candidate(first, 0)
        self.review_candidate("beta", 0)
        result_ref = self.result("beta")[0]
        self.admit_workspace_correction()
        correction = self.acquire_workspace("beta")
        reference = correction["lease"]["acquisition"]["predecessor"]
        predecessor = self.session.read(100, reference)
        self.assertEqual({"node", "allocation", "authorization", "approval", "result", "proof", "reviews", "prior"}, set(predecessor))
        self.assertEqual(first["node"], predecessor["node"])
        self.assertEqual(self.produced("charter", "grant"), predecessor["allocation"])
        self.assertEqual(self.produced("inspect_charter", "permit"), predecessor["authorization"])
        self.assertEqual(self.produced("consent", "permit"), predecessor["approval"])
        self.assertEqual(result_ref, predecessor["result"])
        self.assertEqual(proof_ref, predecessor["proof"])
        self.assertIn(self.result("accept_beta")[0], predecessor["reviews"])
        original_issue = copy.deepcopy(self.provider.issues[100])
        envelope, payload = self.payload()
        mutations = []
        for field, replacement in (("goal", 102), ("node", "alpha")):
            changed = copy.deepcopy(predecessor)
            changed["node"][field] = replacement
            mutations.append(("wrong_" + field, self.blob(changed)))
        for field, replacement in (("allocation", self.produced("alpha")),
                                   ("authorization", self.produced("consent", "permit")),
                                   ("result", self.result("alpha")[0]),
                                   ("proof", self.read_blob(self.produced("alpha"))["provenance"]["source"]),
                                   ("reviews", [self.result("accept_alpha")[0]])):
            changed = copy.deepcopy(predecessor)
            changed[field] = replacement
            mutations.append(("disconnected_" + field, self.blob(changed)))
        changed = copy.deepcopy(predecessor)
        altered = copy.deepcopy(self.read_blob(predecessor["allocation"]))
        altered["content"]["allocations"]["beta"]["owned"].append("read_dependency.txt")
        changed["allocation"] = self.blob(altered)
        mutations.append(("broadened_scope", self.blob(changed)))
        deep = reference
        for _ in range(33):
            snapshot = copy.deepcopy(predecessor)
            snapshot["prior"] = deep
            deep = self.blob(snapshot)
        mutations.extend([("over_limit_chain", deep), ("null", None),
                          ("partial", {"hash": reference["hash"]}),
                          ("unknown", {"hash": "sha256:" + "8" * 64, "uri": "urn:sha256:" + "8" * 64})])
        claimed = content_hash({"unpublished_original_predecessor": predecessor})
        corrupt = json.dumps({"hash": claimed, "content": predecessor}, sort_keys=True, separators=(",", ":"))
        encoded = base64.b64encode(zlib.compress(corrupt.encode())).decode()
        self.provider.create_issue_comment(100, "<!-- zzzops-artifact " + claimed + " -->\n<details><summary>Corrupt predecessor transport</summary>\n\n```text\n" + encoded + "\n```\n</details>")
        mutations.append(("tampered_bytes", {"hash": claimed, "uri": "urn:" + claimed}))
        request = self.session.submission(correction, {"value": "Corrected exact candidate"}, "predecessor-controls")
        request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
        for label, replacement in mutations:
            with self.subTest(predecessor=label):
                current = copy.deepcopy(payload)
                lease = next(item for item in current["operational"]["leases"] if item["token"] == correction["lease"]["token"])
                lease["acquisition"]["predecessor"] = replacement
                changed_envelope = {**envelope, "payload": self.blob(current), "revision": envelope["revision"] + 1}
                self.provider.issues[100]["body"] = "<!-- zzzops-goal\n" + json.dumps(changed_envelope) + "\nzzzops-goal -->"
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, request, expected=2)
                self.assertRegex(json.dumps(response), r"(?i)predecessor|acquisition|allocation|scope|identity|proof|chain|reference|review")
                # This corrupted outer acquisition may reject before decoding;
                # the separate real-correction journey tests traversal capacity.
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
                self.provider.issues[100] = copy.deepcopy(original_issue)
        # Caller cannot replace even a valid host snapshot through submit data.
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, {**request, "predecessor": reference}, expected=2)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        (self.fixture.repo / "source.py").write_text("def value():\n    # Independently requested clarification.\n    return 2\n")
        self.candidate(correction, 0)
        self.assertEqual(proof, self.read_blob(proof_ref))
        self.assertEqual(predecessor, self.session.read(100, reference))

    def test_real_accepted_correction_chain_reaches_bound_before_refusing_next_transition(self):
        self.setup_workspace_corrections(correction_rounds=32)
        self.red_candidate()
        first = self.acquire_workspace("beta")
        (self.fixture.repo / "source.py").write_text("def value():\n    return 2\n")
        initial_ref, initial_proof = self.candidate(first, 0)
        retained_proofs = [(initial_ref, initial_proof)]
        self.review_candidate("beta", 0)
        # Every predecessor is produced through real acquire/submit/review,
        # rather than repeating forged snapshots behind an invalid outer pin.
        for iteration in range(1, 33):
            admissions = self.admit_workspace_correction()
            work = self.acquire_workspace("beta")
            (self.fixture.repo / "source.py").write_text(
                "def value():\n    # Accepted correction %d.\n    return 2\n" % iteration)
            retained_proofs.append(self.candidate(work, 0))
            self.review_candidate("beta", 0)
            self.resolve_workspace_correction(admissions)
        historical_comments = copy.deepcopy(self.provider.comments[100])
        last_accepted_result = self.result("beta")[0]
        last_accepted_output = self.produced("beta")
        self.admit_workspace_correction()
        response = self.session.call(100, expected=None)
        ready = [step for step in response["next_steps"] if step.get("kind") == "execute" and step.get("node", {}).get("node") == "beta"]
        if ready:
            work = self.session.acquire("beta")
            request = self.session.submission(work, {"value": "Beyond reconstruction bound"}, "over-real-chain-bound")
            request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
            response = self.session.call(100, request, expected=2)
        diagnostics = [{"reason": step.get("reason"), "diagnostic": step.get("diagnostic")}
                       for step in response["next_steps"]]
        self.assertRegex(json.dumps(diagnostics), r"(?i)depth|limit")
        self.assertEqual(last_accepted_result, self.result("beta")[0], "Bound refusal cannot publish a new semantic Result")
        self.assertEqual(last_accepted_output, self.produced("beta"), "Bound refusal cannot publish a candidate output")
        for reference, proof in retained_proofs:
            self.assertEqual(proof, self.session.read(100, reference),
                             "Authority traversal bound cannot prohibit targeted historical Ref reads")
        for comment in historical_comments:
            self.assertIn(comment, self.provider.comments[100])
        self.assertNotIn("gamma", self.names())

    def test_corrected_workspace_candidate_preserves_prior_proofs_and_requires_fresh_root_acceptance(self):
        self.setup_workspace_corrections(root_gate=True, correction_rounds=2)
        _alpha, (red_ref, red) = self.red_candidate()
        beta = self.acquire_workspace("beta")
        (self.fixture.repo / "source.py").write_text("def value():\n    return 2\n")
        first_ref, first_proof = self.candidate(beta, 0)
        self.review_candidate("beta", 0)
        self.assertNotIn("gamma", self.names(), "Independent review is not configured root acceptance")
        self.session.finish(self.session.acquire("accept_root_beta"), {"value": "Root accepts exact reviewed first candidate"})
        self.assertIn("gamma", self.names())
        retained = [(red_ref, red), (first_ref, first_proof)]
        for iteration in (1, 2):
            previous_output = self.produced("beta")
            prior_root = self.result("accept_root_beta")[0]
            admissions = self.admit_workspace_correction()
            self.assertNotIn("gamma", self.names())
            correction = self.acquire_workspace("beta")
            self.assertIn(previous_output["hash"], json.dumps(correction["lease"]["acquisition"]),
                          "Correction must bind its exact prior candidate, not arbitrary current bytes")
            for reference, proof in retained:
                self.assertEqual(proof, self.read_blob(reference))
            (self.fixture.repo / "source.py").write_text("def value():\n    # Exact correction %s.\n    return 2\n" % iteration)
            reference, proof = self.candidate(correction, 0)
            retained.append((reference, proof))
            self.assertNotIn("gamma", self.names())
            self.review_candidate("beta", 0)
            self.resolve_workspace_correction(admissions, omit_retained=iteration == 2)
            self.assertNotIn("gamma", self.names(), "Old root acceptance cannot approve the new subject")
            self.assertEqual(prior_root, self.result("accept_root_beta")[0], "Historical acceptance remains immutable")
            self.session.finish(self.session.acquire("accept_root_beta"), {"value": "Root accepts exact reviewed correction " + str(iteration)})
            if iteration == 2:
                self.assertNotIn("gamma", self.names(), "Earlier distinct finding pair still requires current resolution")
                self.resolve_workspace_pair(0, self.retained_correction_admissions[0])
            self.assertIn("gamma", self.names())
            self.assertNotEqual(prior_root, self.result("accept_root_beta")[0])
            self.session.git("add", "source.py", "behavior_test.py")
            self.session.git("commit", "-qm", "exact accepted correction " + str(iteration))
            self.assertIn("gamma", self.names(), "Commit of accepted bytes preserves connected proof reuse")
        for reference, proof in retained:
            self.assertEqual(proof, self.read_blob(reference))
        self.assertEqual({100}, set(self.provider.issues), "In-scope correction cannot create follow-up goals")

    def test_admitted_baseline_correction_rejects_already_acquired_consumer_without_takeover(self):
        self.setup_workspace_corrections(target="alpha")
        _alpha, (reference, proof) = self.red_candidate()
        beta = self.acquire_workspace("beta")
        admissions = self.admit_workspace_correction("alpha")
        self.assertNotIn("beta", self.names())
        (self.fixture.repo / "source.py").write_text("def value():\n    return 2\n")
        request = self.session.submission(beta, {"value": "Stale reviewed baseline cannot authorize this edit"}, "stale-baseline")
        request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        rejected = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)baseline|review|finding|admission|input|stale|prerequisite")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertTrue(any(lease["token"] == beta["lease"]["token"] for lease in self.payload()[1]["operational"]["leases"]))
        self.assertEqual(proof, self.read_blob(reference))
        for admission in admissions.values():
            self.assertEqual("finding", self.read_blob(admission["finding"])["type"])

    def test_current_authorization_must_match_manifest_task_generation_and_policy(self):
        self.setup_workspace(defer_authorization=True)
        work = self.session.acquire("inspect_charter", actor="allocation-reviewer")
        original = copy.deepcopy((self.provider.issues, self.provider.comments))
        for change in ("manifest", "task", "generation", "policy"):
            with self.subTest(change=change):
                self.provider.issues, self.provider.comments = copy.deepcopy(original)
                permit = copy.deepcopy(self.permit)
                if change == "manifest":
                    permit["manifest"] = self.blob({"allocations": {}})
                elif change == "policy":
                    permit["policy"] = "sha256:" + "f" * 64
                else:
                    permit["tasks"][0]["node" if change == "task" else "generation"] = "other" if change == "task" else 2
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, self.session.submission(work, {"permit": permit}, "wrong-" + change), expected=None)
                if self.session.calls[-1]["code"] != 0:
                    self.assertEqual(2, self.session.calls[-1]["code"])
                    self.assertEqual(before, (self.provider.issues, self.provider.comments))
                else:
                    response = self.session.call(100, expected=None)
                if any(s.get("kind") == "execute" and s.get("node", {}).get("node") == "consent"
                       for s in response["next_steps"]):
                    approval = self.session.acquire("consent")
                    before = copy.deepcopy((self.provider.issues, self.provider.comments))
                    response = self.session.call(100, self.session.submission(approval, {"permit": permit}, "approve-" + change), expected=None)
                    if self.session.calls[-1]["code"] != 0:
                        self.assertEqual(2, self.session.calls[-1]["code"])
                        self.assertEqual(before, (self.provider.issues, self.provider.comments))
                    else:
                        response = self.session.call(100, expected=None)
                self.assertEqual(self.permit["manifest"], self.produced("charter", "grant"),
                                 "The producer stays current; only authorization content differs")
                # A malformed authorization may remain factual evidence, but
                # must never grant a writer. If rejected, publishing is atomic.
                self.assertFalse(any(s.get("kind") == "execute" and s.get("node", {}).get("node") == "alpha"
                                     for s in response["next_steps"]))
                self.assert_workspace_blocker(response, r"(?i)manifest|allocation|authorization|policy|generation|authority")
                # Checkpoint must not create a partial alpha lease or rewrite evidence.
                state = copy.deepcopy((self.provider.issues, self.provider.comments))
                self.session.call(100, expected=None)
                self.assertEqual(state, (self.provider.issues, self.provider.comments))
                self.assertFalse(any(l["node"]["node"] == "alpha" for l in self.payload()[1]["operational"]["leases"]))
        self.provider.issues, self.provider.comments = copy.deepcopy(original)
        self.session.finish(work, {"permit": self.permit})
        self.session.finish(self.session.acquire("consent"), {"permit": self.permit})
        self.acquire_workspace("alpha")

    def assert_workspace_blocker(self, response, pattern):
        # Task names and echoed input schemas are not rejection evidence.
        # An unfinished review/approval alone must never satisfy a negative.
        blockers = [step for step in response["next_steps"]
                    if step.get("kind") in ("error", "repair", "blocked")
                    or step.get("directive") == "resolve_blocker"]
        self.assertTrue(blockers, "Expected an explicit authority/path rejection, not an unfinished prerequisite")
        diagnostics = [{key: step[key] for key in ("reason", "diagnostic", "error", "message") if key in step}
                       for step in blockers]
        self.assertRegex(json.dumps(diagnostics), pattern)

    def test_allocation_producer_cannot_self_authorize_and_intruder_cannot_publish(self):
        self.setup_workspace(defer_authorization=True)
        step = next(s for s in self.session.ready() if s["node"]["node"] == "inspect_charter")
        receipt = json.loads(Path(step["policy"]["path"]).read_text())["policy_receipt"]
        start = {**step["start"], "policy_receipt": receipt}
        start.pop("request_id", None)
        work = self.session.call(100, start)["next_steps"][0]
        bind = {**work["bind"], "lease": work["lease"]["token"], "actor": "root-thread",
                "selection": work["lease"]["selection"], "policy_receipt": receipt}
        bind.pop("request_id", None)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, bind, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)independent|actor|authoriz|producer")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.call(100, {**bind, "actor": "allocation-reviewer"})
        work["bound_actor"] = "allocation-reviewer"
        request = self.session.submission(work, {"permit": self.permit}, "intruder-authorization")
        request["actor"] = "unbound-intruder"
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)actor|lease|owner|authoriz")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(work, {"permit": self.permit})
        self.session.finish(self.session.acquire("consent"), {"permit": self.permit})
        self.acquire_workspace("alpha")

    def test_unsafe_allocation_paths_and_undeclared_deletion_never_authorize_edits(self):
        self.setup_workspace()
        valid_graph = copy.deepcopy(self.graph)
        original = copy.deepcopy((self.provider.issues, self.provider.comments))
        with tempfile.TemporaryDirectory() as outside:
            (self.fixture.repo / "escape").symlink_to(outside, target_is_directory=True)
            (self.fixture.repo / "directory").mkdir()
            for path in ("../outside.py", ".git/config", "directory", "*.py", "escape/outside.py"):
                with self.subTest(path=path):
                    self.provider.issues, self.provider.comments = copy.deepcopy(original)
                    self.install(valid_graph)
                    manifest = copy.deepcopy(self.allocations)
                    manifest["allocations"]["alpha"]["owned"] = [path]
                    work = self.session.acquire("charter")
                    before = copy.deepcopy((self.provider.issues, self.provider.comments))
                    response = self.session.call(100, self.session.submission(work, {"grant": manifest}, "unsafe-" + path), expected=None)
                    if self.session.calls[-1]["code"] != 0:
                        self.assertEqual(2, self.session.calls[-1]["code"])
                        self.assertEqual(before, (self.provider.issues, self.provider.comments))
                    else:
                        response = self.session.call(100, expected=None)
                    if any(s.get("kind") == "execute" and s.get("node", {}).get("node") == "inspect_charter"
                           for s in response["next_steps"]):
                        permit = {**self.permit, "manifest": self.produced("charter", "grant")}
                        for name in ("inspect_charter", "consent"):
                            if not any(s.get("kind") == "execute" and s.get("node", {}).get("node") == name
                                       for s in response["next_steps"]):
                                self.assert_workspace_blocker(response, r"(?i)path|scope|allocation|directory|glob|symlink|protected|traversal")
                                break
                            reviewer = self.session.acquire(name, actor="allocation-reviewer" if name == "inspect_charter" else "root-thread")
                            before = copy.deepcopy((self.provider.issues, self.provider.comments))
                            response = self.session.call(100, self.session.submission(reviewer, {"permit": permit}, "unsafe-" + name + path), expected=None)
                            if self.session.calls[-1]["code"] != 0:
                                self.assertEqual(2, self.session.calls[-1]["code"])
                                self.assertEqual(before, (self.provider.issues, self.provider.comments))
                                break
                            response = self.session.call(100, expected=None)
                    self.assertFalse(any(s.get("kind") == "execute" and s.get("node", {}).get("node") == "alpha"
                                         for s in response["next_steps"]))
                    self.assert_workspace_blocker(response, r"(?i)path|scope|allocation|directory|glob|symlink|protected|traversal")
                    before = copy.deepcopy((self.provider.issues, self.provider.comments))
                    self.session.call(100, expected=None)
                    self.assertEqual(before, (self.provider.issues, self.provider.comments))
            (self.fixture.repo / "escape").unlink()
            (self.fixture.repo / "directory").rmdir()
        self.provider.issues, self.provider.comments = copy.deepcopy(original)
        work = self.acquire_workspace("alpha")
        path = self.fixture.repo / "product.txt"
        original_bytes = path.read_bytes()
        path.unlink()
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, self.session.submission(work, {"value": "undeclared deletion"}, "delete-unowned"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)scope|workspace|delet|file|owned")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        path.write_bytes(original_bytes)
        (self.fixture.repo / "behavior_test.py").write_text("from source import value\nassert value() == 2\n")
        self.candidate(work, 1)

    def test_unowned_and_consumed_drift_reject_without_partial_candidate_then_allow_owned_edit(self):
        self.setup_workspace()
        work = self.acquire_workspace("alpha")
        for name in ("unexpected.py", "read_dependency.txt"):
            path = self.fixture.repo / name
            original = path.read_bytes() if path.exists() else None
            try:
                path.write_text("unauthorized change\n")
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, self.session.submission(work, {"value": "candidate"}, "bad-" + name), expected=2)
                self.assertRegex(json.dumps(response), r"(?i)scope|consumed|workspace|file|drift")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
            finally:
                if original is None:
                    path.unlink()
                else:
                    path.write_bytes(original)
        (self.fixture.repo / "behavior_test.py").write_text("from source import value\nassert value() == 2\n")
        self.candidate(work, 1)

    def test_missing_ambiguous_and_wrong_generation_allocations_never_grant_a_lease(self):
        self.setup_workspace()
        valid = next(s for s in self.session.ready() if s["node"]["node"] == "alpha")
        self.assertTrue(valid["start"])
        original_graph = copy.deepcopy(self.graph)
        # Each independent fixture first has a valid graph/allocation control.
        for change in ("missing", "ambiguous", "generation"):
            with self.subTest(change=change):
                graph = copy.deepcopy(original_graph)
                manifest = copy.deepcopy(self.allocations)
                alpha = next(n for n in graph["nodes"] if n["id"] == "alpha")
                if change == "missing":
                    del alpha["inputs"]["allocation"]
                elif change == "ambiguous":
                    alpha["inputs"]["second_allocation"] = copy.deepcopy(alpha["inputs"]["allocation"])
                else:
                    manifest["allocations"]["alpha"]["task"]["generation"] = 2
                # Graph validation or acquisition may reject invalid selection;
                # neither may dispatch a writer or persist a lease for it.
                self.install(graph)
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, expected=None)
                if any(s.get("kind") == "execute" and s.get("node", {}).get("node") == "charter" for s in response["next_steps"]):
                    self.session.finish(self.session.acquire("charter"), {"grant": manifest})
                    permit = {**self.permit, "manifest": self.produced("charter", "grant"),
                              "tasks": [entry["task"] for entry in manifest["allocations"].values()]}
                    self.session.finish(self.session.acquire("inspect_charter", actor="allocation-reviewer"), {"permit": permit})
                    self.session.finish(self.session.acquire("consent"), {"permit": permit})
                    before = copy.deepcopy((self.provider.issues, self.provider.comments))
                    response = self.session.call(100, expected=None)
                self.assertFalse(any(s.get("kind") == "execute" and s.get("node", {}).get("node") == "alpha"
                                     for s in response["next_steps"]))
                self.assertRegex(json.dumps(response), r"(?i)allocation|generation|authority|binding|input")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_parent_authority_revision_rejects_acquired_readonly_work_and_needs_current_review(self):
        def readonly(graph, manifest):
            manifest["allocations"]["alpha"]["owned"] = []
        _graph, parent_output = self.setup_parent_workspace(readonly)
        work = self.acquire_workspace("alpha")
        request = self.session.submission(work, {"value": "Unchanged workspace observation"}, "withdrawn-readonly")
        request["workspace_checks"] = [[sys.executable, "-c", "pass"]]
        original_parent = copy.deepcopy(self.provider.issues[99])
        parent = json.loads(re.search(r"<!-- zzzops-goal\s*\n(.*?)\nzzzops-goal -->", original_parent["body"], re.S)[1])
        index = z._comment_store.ArtifactIndex(self.provider.comments[99])
        payload = index.resolve(parent["payload"]["hash"])[0]
        spec = index.resolve(payload["spec"]["hash"])[0]
        spec["content"] = "Root withdraws prior scope authorization pending current independent review"
        offset = len(self.provider.comments[100])
        payload["spec"] = self.blob(spec)
        parent["payload"] = self.blob(payload)
        for comment in copy.deepcopy(self.provider.comments[100][offset:]):
            self.provider.create_issue_comment(99, comment["body"])
        parent["revision"] += 1
        self.provider.issues[99]["body"] = "<!-- zzzops-goal\n" + json.dumps(parent) + "\nzzzops-goal -->"
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        rejected = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)parent|allocation|authority|review|stale|input")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertTrue(any(item["token"] == work["lease"]["token"] for item in self.payload()[1]["operational"]["leases"]))
        self.session.finish(self.session.acquire("charter", number=99), {"grant": self.allocations}, number=99)
        self.assertNotIn("alpha", self.names())
        self.session.call(100, request, expected=2)
        permit = {**self.permit, "manifest": parent_output("charter", "grant")}
        self.session.finish(self.session.acquire("inspect_charter", number=99, actor="new-parent-reviewer"), {"permit": permit}, number=99)
        self.session.finish(self.session.acquire("consent", number=99), {"permit": permit}, number=99)
        self.session.call(100, request, expected=2)
        # Restoring the exact external predecessor is the matched valid control;
        # new parent review cannot retroactively update an acquired child pin.
        self.provider.issues[99] = original_parent
        self.session.call(100, request)
        proof = self.read_blob(self.read_blob(self.produced("alpha"))["provenance"]["source"])
        self.assertEqual(0, proof["commands"][0]["exit_code"])
        self.assertEqual(content_hash(work["lease"]["acquisition"]), proof["acquisition_hash"])

    def test_new_reviewed_allocation_can_restart_clean_prior_worktree_without_reviving_old_proof(self):
        self.setup_workspace_corrections()
        prior_commit = self.session.git("rev-parse", "HEAD")
        old_grant = self.produced("charter", "grant")
        old_review = self.produced("inspect_charter", "permit")
        old_approval = self.produced("consent", "permit")
        _alpha, (red_ref, red) = self.red_candidate()
        beta = self.acquire_workspace("beta")
        (self.fixture.repo / "source.py").write_text("def value():\n    return 2\n")
        rejected_ref, rejected = self.candidate(beta, 0)
        self.admit_workspace_correction()
        original_repo = self.fixture.repo
        original_source = (original_repo / "source.py").read_bytes()
        original_test = (original_repo / "behavior_test.py").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            clean = Path(directory) / "clean-prior"
            self.session.git("worktree", "add", "--detach", str(clean), prior_commit)
            try:
                self.session.repo = clean
                self.fixture.repo = clean
                self.assertEqual("", self.session.git("status", "--porcelain"))
                self.replace_spec("Root withdraws prior delivery allocation and authorizes fresh investigation from exact clean commit " + prior_commit)
                self.session.finish(self.session.acquire("charter"), {"grant": self.allocations})
                new_grant = self.produced("charter", "grant")
                self.assertEqual(self.read_blob(old_grant)["content"], self.read_blob(new_grant)["content"])
                self.assertNotEqual(old_grant, new_grant)
                self.assertEqual(old_review, self.produced("inspect_charter", "permit"))
                self.assertEqual(old_approval, self.produced("consent", "permit"))
                self.assertNotIn("alpha", self.names(), "Identical manifest bytes need new provenance-bound authorization")
                permit = {**self.permit, "manifest": new_grant}
                self.session.finish(self.session.acquire("inspect_charter", actor="fresh-allocation-reviewer"), {"permit": permit})
                self.assertNotIn("alpha", self.names(), "Fresh independent review still requires configured root consent")
                self.session.finish(self.session.acquire("consent"), {"permit": permit})
                fresh = self.acquire_workspace("alpha")
                self.assertIn(prior_commit, json.dumps(fresh["lease"]["acquisition"]))
                self.assertNotIn(rejected_ref["hash"], json.dumps(fresh["lease"]["acquisition"]),
                                 "Withdrawn source proof cannot normalize the newly authorized clean baseline")
                (clean / "behavior_test.py").write_text("from source import value\nassert value() == 2\n")
                _new_ref, new_proof = self.candidate(fresh, 1)
                self.assertEqual("missing", new_proof["consumed"]["behavior_test.py"])
                self.assertEqual(red, self.session.read(100, red_ref))
                self.assertEqual(rejected, self.session.read(100, rejected_ref))
                self.assertEqual(original_source, (original_repo / "source.py").read_bytes())
                self.assertEqual(original_test, (original_repo / "behavior_test.py").read_bytes())
            finally:
                self.session.repo = original_repo
                self.fixture.repo = original_repo
                self.session.git("worktree", "remove", "--force", str(clean))

    def test_replacing_allocation_cannot_reauthorize_an_inflight_out_of_scope_edit(self):
        self.setup_workspace()
        work = self.acquire_workspace("alpha")
        self.replace_spec("Root proposes a different finite allocation")
        changed = copy.deepcopy(self.allocations)
        changed["allocations"]["alpha"]["owned"].append("unexpected.py")
        self.session.finish(self.session.acquire("charter"), {"grant": changed})
        (self.fixture.repo / "unexpected.py").write_text("not authorized by the acquired manifest\n")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, self.session.submission(work, {"value": "candidate"}, "stale-allocation"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)allocation|review|stale|authority|input|scope")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_tampered_completed_workspace_proof_blocks_downstream_after_lease_removal(self):
        self.setup_workspace()
        _work, (proof_ref, proof) = self.red_candidate()
        self.assertIn("beta", self.names())
        original = copy.deepcopy(self.provider.comments[100])
        mutations = 0
        for comment in self.provider.comments[100]:
            envelope = z._comment_store.decode_envelope(comment["body"])
            if envelope is None:
                continue
            for record in envelope["artifacts"]:
                if record["hash"] == proof_ref["hash"]:
                    record["kind"] = "full"
                    record.pop("base", None)
                    record.pop("patch", None)
                    record["type"] = "json"
                    record["text"] = json.dumps({**proof, "outputs": {"behavior_test.py": "sha256:" + "f" * 64}},
                                                sort_keys=True, separators=(",", ":"))
                    mutations += 1
            comment["body"] = z._comment_store.encode_envelope(envelope)
        self.assertGreater(mutations, 0, "Tamper probe must alter the stored proof, not a nonexistent fixture")
        response = self.session.call(100, expected=None)
        self.assertFalse(any(s.get("kind") == "execute" and s.get("node", {}).get("node") == "beta"
                             for s in response["next_steps"]))
        self.assertRegex(json.dumps(response), r"(?i)hash|proof|artifact|identity|corrupt")
        self.provider.comments[100] = original
        self.assertIn("beta", self.names())

    def test_completed_output_and_consumed_drift_block_reuse_after_lease_removal(self):
        self.setup_workspace()
        _work, _proof = self.red_candidate()
        self.assertIn("beta", self.names())
        for name in ("behavior_test.py", "read_dependency.txt"):
            with self.subTest(path=name):
                path = self.fixture.repo / name
                original = path.read_bytes()
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                try:
                    path.write_text("unreviewed post-result change\n")
                    response = self.session.call(100, expected=None)
                    self.assertFalse(any(s.get("kind") == "execute" and s.get("node", {}).get("node") == "beta"
                                         for s in response["next_steps"]))
                    self.assertRegex(json.dumps(response), r"(?i)workspace|proof|drift|consumed|output")
                    self.assertEqual(before, (self.provider.issues, self.provider.comments))
                finally:
                    path.write_bytes(original)
                self.assertIn("beta", self.names(), "Exact restored proof must remain reusable")

    def setup_parent_workspace(self, mutate=None, parent_mutate=None):
        self.setup_workspace(mutate)
        child_graph = copy.deepcopy(self.graph)
        parent_nodes = copy.deepcopy(child_graph["nodes"][:3])
        # Parent's own qualified prerequisite selectors are local to goal 99;
        # its allocation deliberately grants the exact child task in goal 100.
        def qualify(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "goal" and item == 100:
                        value[key] = 99
                    else:
                        qualify(item)
            elif isinstance(value, list):
                for item in value:
                    qualify(item)
        qualify(parent_nodes)
        parent_graph = {"nodes": parent_nodes, "task_sets": [],
                        "terminals": [{**selector("consent"), "goal": 99}]}
        if parent_mutate:
            parent_mutate(parent_graph)
        for child in (n for n in child_graph["nodes"] if n["id"] in ("alpha", "beta", "gamma")):
            for slot, original in (("parent_allocation", "allocation"), ("parent_authorization", "authorization"),
                                   ("parent_approval", "approval")):
                child["inputs"][slot] = copy.deepcopy(child["inputs"][original])
                child["inputs"][slot]["producer"]["node"]["goal"] = 99
        # Establish final policy before issuing either goal's authorization.
        # Installing it afterwards would correctly stale the parent's evidence.
        self.install(child_graph)
        self.permit["policy"] = content_hash(self.session.project["policy"])
        parent_spec = self.blob({"type": "specification", "content": "Delegate only the exact child allocation",
            "producer": None, "provenance": {"actor": "root-thread", "source": None,
            "policy": content_hash(self.session.project["policy"])}})
        parent_payload = self.blob({"spec": parent_spec, "graph": self.blob(parent_graph), "evidence": [],
                                   "operational": {"leases": [], "receipts": []}})
        parent_envelope = {**self.envelope, "issue": 99, "payload": parent_payload}
        self.provider.issues[99] = {**copy.deepcopy(self.provider.issues[100]), "number": 99,
            "body": "<!-- zzzops-goal\n" + json.dumps(parent_envelope) + "\nzzzops-goal -->"}
        self.provider.comments[99] = copy.deepcopy(self.provider.comments[100])

        def parent_output(name, slot):
            body = self.provider.issues[99]["body"]
            envelope = json.loads(re.search(r"<!-- zzzops-goal\s*\n(.*?)\nzzzops-goal -->", body, re.S)[1])
            index = z._comment_store.ArtifactIndex(self.provider.comments[99])
            payload = index.resolve(envelope["payload"]["hash"])[0]
            for ref in reversed(payload["evidence"]):
                artifact = index.resolve(ref["hash"])[0]
                if artifact["type"] == "result" and artifact["content"]["node"]["node"] == name:
                    return artifact["content"]["outputs"][slot]
            self.fail("Parent must have a host-issued result")

        for name, outputs in (("charter", {"grant": self.allocations}), ("inspect_charter", None), ("consent", None)):
            if outputs is None:
                outputs = {"permit": {**self.permit, "manifest": parent_output("charter", "grant")}}
            work = self.session.acquire(name, number=99,
                                        actor="parent-reviewer" if name == "inspect_charter" else "root-thread")
            self.session.call(99, self.session.submission(work, outputs, "parent-" + name))
        envelope, payload = self.payload()
        envelope["parent"] = 99
        envelope["revision"] += 1
        self.provider.issues[100]["body"] = "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"
        self.session.finish(self.session.acquire("charter"), {"grant": self.allocations})
        permit = {**self.permit, "manifest": self.produced("charter", "grant")}
        self.session.finish(self.session.acquire("inspect_charter", actor="allocation-reviewer"), {"permit": permit})
        self.session.finish(self.session.acquire("consent"), {"permit": permit})
        self.assertIn("alpha", self.names(), "Current exact parent grant is the positive control")
        return child_graph, parent_output

    def test_parent_grant_omission_and_mismatch_cannot_expand_child_authority(self):
        child_graph, parent_output = self.setup_parent_workspace()
        original = copy.deepcopy((self.provider.issues, self.provider.comments, self.session.project))
        for change in ("omitted", "mismatched"):
            with self.subTest(change=change):
                self.provider.issues, self.provider.comments, self.session.project = copy.deepcopy(original)
                changed = copy.deepcopy(child_graph)
                node = next(n for n in changed["nodes"] if n["id"] == "alpha")
                if change == "omitted":
                    for key in ("parent_allocation", "parent_authorization", "parent_approval"):
                        del node["inputs"][key]
                else:
                    node["inputs"]["parent_allocation"]["path"] = ["allocations", "beta"]
                envelope, payload = self.payload()
                payload["graph"] = self.blob(changed)
                envelope["payload"] = self.blob(payload)
                self.provider.issues[100]["body"] = "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"
                z._workflow_section(self.session.project, "workflow_adherence")["configuration"]["phase_dag"] = changed
                # Renew any ordinary producers invalidated by the graph/policy
                # edit, so generic stale authorization is not the negative oracle.
                for number in (99, 100):
                    for name in ("charter", "inspect_charter", "consent"):
                        if not any(s["node"]["node"] == name for s in self.session.ready(number)):
                            continue
                        manifest_ref = (parent_output("charter", "grant") if number == 99
                                        else self.produced("charter", "grant")) if name != "charter" else None
                        outputs = {"grant": self.allocations} if name == "charter" else {"permit": {
                            **self.permit, "manifest": manifest_ref,
                            "policy": content_hash(self.session.project["policy"])}}
                        work = self.session.acquire(name, number=number,
                            actor=("parent-reviewer" if number == 99 else "allocation-reviewer")
                            if name == "inspect_charter" else "root-thread")
                        self.session.call(number, self.session.submission(work, outputs, change + str(number) + name))
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, expected=None)
                self.assertFalse(any(s.get("kind") == "execute" and s.get("node", {}).get("node") == "alpha"
                                     for s in response["next_steps"]))
                self.assertRegex(json.dumps(response), r"(?i)parent|ancestor|allocation|authority")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))



    def test_clean_crlf_checkout_pins_raw_consumed_bytes_and_allows_owned_red_edit(self):
        self.setup_workspace()
        self.session.git("config", "core.autocrlf", "true")
        source = self.fixture.repo / "source.py"
        source.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
        self.session.git("add", "source.py")
        self.assertEqual("", self.session.git("diff", "--cached", "--name-only"))
        self.assertEqual("", self.session.git("status", "--porcelain", "--", "source.py"))
        before = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        work = self.acquire_workspace("alpha")
        (self.fixture.repo / "behavior_test.py").write_bytes(b"from source import value\r\nassert value() == 2\r\n")
        _ref, proof = self.candidate(work, 1)
        self.assertEqual(before, proof["consumed"]["source.py"])
        self.review_candidate("alpha", 1)
        self.assertIn("beta", self.names())

    def test_mixed_clean_checkout_rejects_raw_consumed_drift_and_restores_exact_acquisition(self):
        self.setup_workspace()
        self.session.git("config", "core.autocrlf", "true")
        dependency = self.fixture.repo / "read_dependency.txt"
        original = dependency.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        dependency.write_bytes(original)
        source = self.fixture.repo / "source.py"
        source.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))
        self.session.git("add", "source.py", "read_dependency.txt")
        self.assertEqual("", self.session.git("diff", "--cached", "--name-only"))
        self.assertEqual("", self.session.git("status", "--porcelain", "--", "source.py", "read_dependency.txt"))
        work = self.acquire_workspace("alpha")
        acquisition = copy.deepcopy(work["lease"]["acquisition"])
        self.assertIn("read_dependency.txt", acquisition["checkout_overrides"])
        self.assertNotIn("source.py", acquisition["checkout_overrides"])
        (self.fixture.repo / "behavior_test.py").write_text("from source import value\nassert value() == 2\n")
        request = self.session.submission(work, {"value": "Mixed checkout candidate"}, "mixed-checkout")
        request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
        dependency.write_bytes(original.replace(b"\r\n", b"\n"))
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        rejected = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)drift|changed|consumed|acquisition")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        dependency.write_bytes(original)
        self.session.git("config", "core.autocrlf", "false")
        _reference, proof = self.candidate(work, 1)
        self.assertEqual(content_hash(acquisition), proof["acquisition_hash"])
        self.assertEqual("sha256:" + hashlib.sha256(original).hexdigest(), proof["consumed"]["read_dependency.txt"])
        self.review_candidate("alpha", 1)
        self.assertIn("beta", self.names())

    def test_dirty_unreviewed_source_cannot_be_adopted_as_acquisition_baseline(self):
        self.setup_workspace()
        self.assertIn("alpha", self.names(), "Clean reviewed positive control")
        source = self.fixture.repo / "source.py"
        original = source.read_bytes()
        source.write_text("def value():\n    return 9\n")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        with self.assertRaisesRegex(AssertionError, r"(?i)dirty|drift|workspace|input|baseline"):
            self.acquire_workspace("alpha")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        source.write_bytes(original)
        self.acquire_workspace("alpha")

    def test_workspace_owner_requires_observed_stop_then_fresh_committed_acquisition(self):
        self.setup_workspace()
        orphan = {"type": "workspace_proof", "content": {"outputs": {"source.py": "unaccepted"}},
                  "producer": None, "provenance": {"actor": "untrusted", "source": None,
                  "policy": content_hash(self.session.project["policy"])}}
        orphan_ref = self.blob(orphan)
        ready = next(step for step in self.session.ready() if step["node"]["node"] == "alpha")
        start = {**ready["start"], "policy_receipt": json.loads(Path(ready["policy"]["path"]).read_text())["policy_receipt"]}
        start.pop("request_id", None)
        first = self.acquire_workspace("alpha")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, start, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)lease|owner|active|worker")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        with mock.patch.object(z._workflow.time, "time", return_value=first["lease"]["expires_at"] + 1):
            steps = self.session.checkpoint(100)
            self.assertFalse(any(step.get("kind") == "execute" and step.get("node", {}).get("node") == "alpha" for step in steps))
            recovery = next(step for step in steps if "recovery_contract" in step or step.get("kind") == "recover")
            request = copy.deepcopy(recovery.get("submission", recovery.get("recovery_contract")))
            self.assertEqual(first["lease"]["token"], request["lease"])
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            self.session.call(100, {**request, "worker_status": "unknown", "evidence": "Expiry alone"}, expected=2)
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
            self.session.call(100, {**request, "worker_status": "stopped", "evidence": "Actual original workspace worker observed terminal"})
        (self.fixture.repo / "independent.txt").write_text("Independent committed baseline addition\n")
        self.session.git("add", "independent.txt")
        self.session.git("commit", "-qm", "independent baseline after stopped worker")
        second = self.acquire_workspace("alpha")
        self.assertEqual(orphan, self.session.read(100, orphan_ref), "Unreferenced historical bytes survive independent commit and fresh acquisition")
        self.assertNotEqual(first["lease"]["token"], second["lease"]["token"])
        self.assertIn(self.session.git("rev-parse", "HEAD"), json.dumps(second["lease"]["acquisition"]))
        stale = self.session.submission(first, {"value": "Old stopped owner cannot return"}, "stopped-owner-submit")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, stale, expected=2)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        (self.fixture.repo / "behavior_test.py").write_text("from source import value\nassert value() == 2\n")
        _ref, proof = self.candidate(second, 1)
        self.assertEqual(second["input_hash"], proof["input_hash"])
        self.review_candidate("alpha", 1)
        self.assertIn("beta", self.names())

    def test_unreferenced_proof_artifact_does_not_change_acquisition_inputs(self):
        self.setup_workspace()
        before = next(v["input_hash"] for v in self.session.ready() if v["node"]["node"] == "alpha")
        self.blob({"type": "workspace_proof", "content": {"outputs": {"source.py": "unaccepted"}},
                   "producer": None, "provenance": {"actor": "untrusted", "source": None, "policy": content_hash(self.session.project["policy"])}})
        work = self.acquire_workspace("alpha")
        self.assertEqual(before, work["input_hash"], "Unreferenced bytes cannot become accepted proof authority")

    def test_commit_of_exact_accepted_owned_outputs_preserves_downstream_proof(self):
        self.setup_workspace()
        self.red_candidate()
        beta = self.acquire_workspace("beta")
        (self.fixture.repo / "source.py").write_text("def value():\n    return 2\n")
        reference, proof = self.candidate(beta, 0)
        self.review_candidate("beta", 0)
        self.session.git("add", "source.py", "behavior_test.py")
        self.session.git("commit", "-qm", "verified owned outputs")
        work = self.acquire_workspace("gamma")
        self.assertEqual(proof, self.read_blob(reference))
        self.session.finish(work, {"value": "unchanged accepted bytes after commit"})

    def test_readonly_allocation_accepts_unchanged_workspace_but_rejects_new_file(self):
        def readonly(_graph, allocations):
            allocations["allocations"]["alpha"]["owned"] = []
        self.setup_workspace(readonly)
        work = self.acquire_workspace("alpha")
        extra = self.fixture.repo / "not-granted.py"
        extra.write_text("undeclared = True\n")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        request = self.session.submission(work, {"value": "read only"}, "readonly-extra")
        response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)owned|scope|undeclared|workspace")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        extra.unlink()
        self.session.finish(work, {"value": "read only"})

    def test_unreviewed_candidate_remains_correction_evidence_without_downstream_authority(self):
        self.setup_workspace()
        alpha = self.acquire_workspace("alpha")
        (self.fixture.repo / "behavior_test.py").write_text("from source import value\nassert value() == 2\n")
        ref, proof = self.candidate(alpha, 1)
        self.assertEqual(1, proof["commands"][0]["exit_code"])
        self.assertNotIn("beta", self.names())
        self.assertIn("observe_alpha", self.names())
        self.assertEqual(proof, self.read_blob(ref))
        self.review_candidate("alpha", 1)
        self.assertIn("beta", self.names())

class GatewayTransport:
    """Real cache code sees provider responses; only subprocess is simulated."""
    def __init__(self, issues):
        self.issues = issues
        self.requests = []

    def __call__(self, command, **_kwargs):
        self.requests.append(list(command))
        query = next((arg[6:] for arg in command if arg.startswith("query=")), "")
        if "issues(" in query:
            nodes = [{"number": issue["number"], "title": issue["title"], "state": issue["state"].upper(),
                      "updatedAt": issue["updated_at"], "labels": {"nodes": issue["labels"]}}
                     for issue in self.issues.values()]
            data = [{"data": {"repository": {"nameWithOwner": "owner/repo", "url": "https://github.com/owner/repo",
                    "hasIssuesEnabled": True, "viewerPermission": "ADMIN",
                    "issues": {"nodes": nodes, "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}]
        elif "goal_" in query:
            numbers = [int(n) for n in re.findall(r"goal_(\d+):issue", query)]
            data = {"data": {"repository": {f"goal_{n}": {
                "number": n, "body": self.issues[n]["body"], "updatedAt": self.issues[n]["updated_at"]}
                for n in numbers}}}
        elif command[1:3] == ["api", "repos/owner/repo/releases"]:
            data = [[]]
        else:
            raise AssertionError("Unexpected transport request: " + repr(command))
        return SimpleNamespace(returncode=0, stdout=json.dumps(data), stderr="")

    def body_numbers(self):
        return [int(n) for command in self.requests for arg in command if arg.startswith("query=")
                for n in re.findall(r"goal_(\d+):issue", arg)]


class CacheTransportTests(unittest.TestCase):
    def test_real_gateway_reuses_warm_bodies_and_refetches_only_changed_marker(self):
        fixtures = old.fixtures
        issues = {n: fixtures.PortfolioTests().issue(n) for n in (100, 101)}
        transport = GatewayTransport(issues)
        template = json.loads((fixtures.PLUGIN_ROOT / "zzzops/templates/project-goals/INIT_PLAN.json").read_text())
        project = {"backend": "github_issues", "repository": {"identity": "owner/repo"}, "policy": template["policy"]}
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(z.shutil, "which", return_value="gh"), \
                mock.patch.object(z.subprocess, "run", side_effect=transport):
            repo = Path(directory)
            (repo / ".zzzops").mkdir()
            z.github_repository_portfolio_snapshot(repo, project)
            self.assertEqual([100, 101], sorted(transport.body_numbers()))
            transport.requests.clear()
            z.github_repository_portfolio_snapshot(repo, project)
            self.assertEqual([], transport.body_numbers())
            self.assertEqual(1, len(transport.requests), "Warm gateway requires only its broadphase")
            issues[100]["updated_at"] = "2026-09-25T00:00:00Z"
            transport.requests.clear()
            z.github_repository_portfolio_snapshot(repo, project)
            self.assertEqual([100], transport.body_numbers(), "Unchanged goal must retain cached body")

    def test_actual_release_cache_avoids_fresh_provider_fetch(self):
        transport = GatewayTransport({})
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(z.shutil, "which", return_value="gh"), \
                mock.patch.object(z.subprocess, "run", side_effect=transport):
            repo = Path(directory)
            (repo / ".zzzops").mkdir()
            first = z.github_release_evidence(repo, {"identity": "owner/repo"})
            self.assertEqual("complete", first["status"])
            self.assertEqual(1, len(transport.requests))
            self.assertEqual(first, z.github_release_evidence(repo, {"identity": "owner/repo"}))
            self.assertEqual(1, len(transport.requests))

    def test_actual_pr_cache_batches_and_reuses_details(self):
        # Existing transport-level test asserts cold=2 and warm=1 real requests
        # and batches two PRs. Reuse its assertions instead of a mock counter.
        old.fixtures.PortfolioTests().test_pull_request_broadphase_batches_and_reuses_unchanged_scheduling_evidence()


class PRSourceTransportTests(unittest.TestCase):
    def test_real_source_reader_preserves_pr_commit_author_edits_and_deletion(self):
        reader = getattr(z, "read_pull_request_correction_sources", None)
        self.assertTrue(callable(reader), "Missing production PR correction-source reader")
        original = {"id": 701, "body": "Fix the missing regression", "commit_id": "a" * 40,
                    "original_commit_id": "a" * 40, "path": "source.py", "line": 4,
                    "user": {"login": "external-user"}, "updated_at": "2026-09-24T00:00:00Z"}
        edited = {**original, "body": "Edited correction; approved_by=root is only text",
                  "updated_at": "2026-09-24T01:00:00Z"}
        responses = [[original], [edited], []]
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(z.shutil, "which", return_value="gh"), \
                mock.patch.object(z.subprocess, "run", side_effect=[
                    SimpleNamespace(returncode=0, stdout=json.dumps(records), stderr="") for records in responses]) as transport:
            first_marker = {"updated_at": original["updated_at"], "head_oid": "a" * 40}
            first = reader(Path(directory), "owner/repo", 9, marker=first_marker)
            self.assertEqual(first, reader(Path(directory), "owner/repo", 9, marker=first_marker))
            self.assertEqual(1, transport.call_count, "Unchanged PR source marker must reuse cache")
            second = reader(Path(directory), "owner/repo", 9,
                            marker={"updated_at": edited["updated_at"], "head_oid": "b" * 40})
            last = reader(Path(directory), "owner/repo", 9,
                          marker={"updated_at": "2026-09-24T02:00:00Z", "head_oid": "b" * 40})
        self.assertEqual([original], first)
        self.assertEqual([edited], second)
        self.assertEqual([], last)
        self.assertEqual("a" * 40, second[0]["commit_id"])
        self.assertEqual("external-user", second[0]["user"]["login"])
        self.assertNotIn("approval", second[0])
        self.assertEqual(3, transport.call_count)
        for call in transport.call_args_list:
            self.assertIn("repos/owner/repo/pulls/9/comments", call.args[0])

    def test_source_read_failure_is_not_an_empty_success(self):
        reader = getattr(z, "read_pull_request_correction_sources", None)
        self.assertTrue(callable(reader), "Missing production PR correction-source reader")
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(z.shutil, "which", return_value="gh"), \
                mock.patch.object(z.subprocess, "run", side_effect=[
                    SimpleNamespace(returncode=0, stdout=json.dumps([{ "id": 1, "body": "open finding"}]), stderr=""),
                    SimpleNamespace(returncode=1, stdout="", stderr="Unavailable")]):
            self.assertEqual([{ "id": 1, "body": "open finding"}], reader(Path(directory), "owner/repo", 9,
                marker={"updated_at": "2026-09-24T00:00:00Z", "head_oid": "a" * 40}))
            with self.assertRaisesRegex(ValueError, r"(?i)provider|unavailable|read|failed"):
                reader(Path(directory), "owner/repo", 9,
                       marker={"updated_at": "2026-09-24T01:00:00Z", "head_oid": "a" * 40})


class GatewayIsolationTests(DagFixture):
    def snapshot(self, transport):
        with mock.patch.object(z.shutil, "which", return_value="gh"), \
                mock.patch.object(z, "_github_pull_request_states", REAL_PR_STATES), \
                mock.patch.object(z.subprocess, "run", side_effect=transport):
            return z.github_repository_portfolio_snapshot(self.fixture.repo, self.session.project)[1]

    def test_incompatible_goal_is_local_and_archived_body_is_never_hydrated(self):
        transport = GatewayTransport(self.provider.issues)
        valid = self.snapshot(transport)
        self.assertIn(100, [goal["key"] for goal in valid["goals"]], "Compatible v2 positive control must be accepted")
        unknown = copy.deepcopy(self.provider.issues[100])
        envelope = copy.deepcopy(self.envelope)
        envelope.update(issue=777, schema_version=987)
        unknown.update(number=777, body="<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->")
        archived = copy.deepcopy(self.provider.issues[100])
        archived.update(number=888, state="closed", body="unreadable historical body",
                        labels=[{"name": "zzzops"}, {"name": "zzzops:status:done"}, {"name": "zzzops:priority:P2"}])
        self.provider.issues.update({777: unknown, 888: archived})
        before = copy.deepcopy(self.provider.issues)
        transport.requests.clear()
        result = self.snapshot(transport)
        self.assertIn(100, [goal["key"] for goal in result["goals"]])
        self.assertTrue(any(finding.get("goal") == 777 and "987" in json.dumps(finding)
                            for finding in result["findings"]))
        self.assertFalse(any(finding.get("goal") == 100 for finding in result["findings"]))
        self.assertNotIn(888, transport.body_numbers())
        self.assertEqual(before, self.provider.issues)



class RelationshipPublicTests(DagFixture):
    """Revision16 relationship journeys; raw provider facts, no fake resolver.

    Finite transport proposal: an adapter lists repository issue metadata pages
    with ordinary provider page cursors, then reads exact candidate records. A
    targeted relationship request may inspect historical candidates to establish
    canonical-parent coverage. The fixture supplies raw pages, never a trusted
    relationship_context, fabricated Result, or authority decision. Production
    must establish coverage before issuing its reserved context. Native sub-issue
    metadata alone is insufficient when canonical parent facts can disagree.

    Returned acquired steps expose host-issued Result.resolutions as
    acquisition.resolutions (or lease.acquisition.resolutions). This is a wire
    assertion, not a second evaluator. Each resolution includes the closed
    normative context Ref and exact qualified targets.
    """
    def setUp(self):
        super().setUp()
        self.setup_relationship_transport()

    def setup_relationship_transport(self):
        self.discovery_failure = False
        self.discovery_incomplete = False
        self.relationship_reads = []
        original_get = self.provider.get_issue

        def read(number):
            self.relationship_reads.append(number)
            return original_get(number)

        def metadata_page(cursor=None):
            if self.discovery_failure:
                raise RuntimeError("relationship discovery unavailable")
            numbers = sorted(self.provider.issues)
            start = int(cursor or 0)
            selected = numbers[start:start + 2]
            more = start + 2 < len(numbers) or self.discovery_incomplete
            return {"repository": "owner/repo", "issues": [
                {"number": n, "state": self.provider.issues[n]["state"],
                 "updated_at": self.provider.issues[n]["updated_at"]} for n in selected],
                "page_info": {"has_next_page": more,
                              "end_cursor": str(start + 2) if more and selected else None}}

        self.provider.get_issue = read
        self.provider.list_issue_metadata = metadata_page
        self.provider.get_sub_issues = lambda number: [
            {"number": n} for n in sorted(self.provider.issues)
            if self.envelope_for(n).get("parent") == number]
        self.provider.get_parent_issue = lambda number: self.envelope_for(number).get("parent")
        # Broad execution mirrors the real archived projection. Closed bodies
        # are only fetched by a targeted consumer, never this broadphase fixture.
        def portfolio(*_args, **_kwargs):
            goals = []
            for n, issue in sorted(self.provider.issues.items()):
                if issue["state"] == "closed":
                    metadata = {k: copy.deepcopy(v) for k, v in issue.items() if k != "body"}
                    goals.append(z.github_archived_goal_record(metadata))
                else:
                    goals.append(z.github_goal_record(self.provider.get_issue(n)))
            return {"complete": True, "valid": True, "goals": goals}
        self.session.portfolio_snapshot = portfolio

    def envelope_for(self, number):
        return json.loads(re.search(r"<!-- zzzops-goal\s*\n(.*?)\nzzzops-goal -->",
                                   self.provider.issues[number]["body"], re.S)[1])

    def put_envelope(self, number, envelope):
        self.provider.issues[number]["body"] = "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"
        self.provider.issues[number]["updated_at"] = "2026-09-29T12:%02d:00Z" % envelope["revision"]

    def add_goal(self, number, graph, parent=None):
        payload = self.blob({"spec": self.blob({"type": "specification", "content": "Required output",
            "producer": None, "provenance": {"actor": "root-thread", "source": None,
            "policy": content_hash(self.session.project["policy"])}}), "graph": self.blob(graph),
            "evidence": [], "operational": {"leases": [], "receipts": []}})
        envelope = {"schema_version": 2, "repository": "owner/repo", "issue": number,
                    "revision": 1, "state": "open", "parent": parent, "payload": payload}
        self.provider.issues[number] = {**copy.deepcopy(self.provider.issues[100]), "number": number}
        self.provider.comments[number] = copy.deepcopy(self.provider.comments[100])
        self.put_envelope(number, envelope)

    def read_at(self, number, ref):
        return z._comment_store.ArtifactIndex(self.provider.comments[number]).resolve(ref["hash"])[0]

    def result_at(self, number, name):
        payload = self.read_at(number, self.envelope_for(number)["payload"])
        for ref in reversed(payload["evidence"]):
            artifact = self.read_at(number, ref)
            if artifact["type"] == "result" and artifact["content"]["node"]["node"] == name:
                return ref, artifact["content"]
        self.fail("Missing host Result for %s/%s" % (number, name))

    def symbolic_graph(self, goal="#children", *, kind="node", mode="content"):
        producer = task("produce")
        producer["inputs"] = {"request": spec_input()}
        producer["executor"]["authority"]["subject"]["goal"] = "#this"
        consumer = task("collect")
        target = ({"kind": "node", "goal": goal, "node": "produce"} if kind == "node" else
                  {"kind": "join", "goal": goal, "expansion": "buckets"} if kind == "join" else
                  {"kind": "member", "goal": goal, "expansion": "buckets", "item": "a", "generation": "current"})
        consumer["requires"] = [target]
        selected_type = {"kind": "string"}
        if kind == "join":
            selected_type = {"kind": "map", "values": selected_type}
        if goal == "#children":
            selected_type = {"kind": "map", "values": selected_type}
        consumer["inputs"] = {"values": {"producer": {"node": target}, "output": "value", "path": [],
                                         "mode": mode, "type": selected_type}}
        consumer["executor"]["authority"]["subject"]["goal"] = "#this"
        return {"nodes": [producer, consumer], "task_sets": [],
                "terminals": [{"kind": "node", "goal": "#this", "node": "collect"}]}

    def complete(self, number, name="produce", value="accepted", actor=None):
        work = self.session.acquire(name, number=number, actor=actor)
        self.session.finish(work, {"value": value}, number=number)
        return work

    def child_fixture(self, *, graph=None):
        graph = graph or self.symbolic_graph()
        self.install(graph)
        self.add_goal(101, graph, 100)
        self.add_goal(102, graph, 100)
        self.complete(101, value="child one")
        self.complete(102, value="child two")
        self.assertIn("collect", self.names(), "Positive required-child join must become runnable")
        return graph

    def resolutions(self, acquired):
        acquisition = acquired.get("acquisition", acquired["lease"].get("acquisition", {}))
        self.assertIn("resolutions", acquisition, "Host must pin selector resolutions at acquisition")
        return acquisition["resolutions"]

    def test_same_symbolic_graph_runs_for_multiple_goals_and_keeps_exact_targets(self):
        graph = self.child_fixture()
        self.add_goal(200, graph)
        self.add_goal(201, graph, 200)
        self.complete(201, value="other child")
        before = content_hash(graph)
        for number, expected in ((100, [101, 102]), (200, [201])):
            work = self.session.acquire("collect", number=number)
            resolutions = self.resolutions(work)
            selected = [r for r in resolutions if r["selector"]["goal"] == "#children"]
            self.assertTrue(selected)
            for resolution in selected:
                self.assertEqual(expected, [target["goal"] for target in resolution["targets"]])
                self.assertEqual({"location", "selector", "context", "targets"}, set(resolution))
                context = self.read_at(number, resolution["context"])
                self.assertEqual("relationship_context", context["type"])
                value = context["content"]
                self.assertEqual({"repository", "subject", "subject_envelope", "parent", "children"}, set(value))
                self.assertEqual(number, value["subject"])
                self.assertEqual({"known": True, "value": None}, value["parent"])
                self.assertEqual(expected, sorted(map(int, value["children"]["envelopes"])))
                self.assertTrue(value["children"]["known"])
            self.session.finish(work, {"value": "joined"}, number=number)
            result = self.result_at(number, "collect")[1]
            self.assertEqual(resolutions, result["resolutions"])
            self.assertEqual(sorted(resolutions, key=lambda r: json.dumps(r["location"])), resolutions)
            payload = self.read_at(number, self.envelope_for(number)["payload"])
            self.assertEqual(before, content_hash(self.read_at(number, payload["graph"])))

    def test_every_child_required_including_archived_exact_completion(self):
        self.child_fixture()
        closed = self.envelope_for(102)
        closed["state"] = "archived"
        closed["revision"] += 1
        self.put_envelope(102, closed)
        self.provider.issues[102]["state"] = "closed"
        before = copy.deepcopy(self.provider.issues[102])
        self.relationship_reads.clear()
        work = self.session.acquire("collect")
        targets = {t["goal"] for r in self.resolutions(work) if r["selector"]["goal"] == "#children" for t in r["targets"]}
        self.assertEqual({101, 102}, targets)
        self.assertIn(102, self.relationship_reads, "Exact archived evidence needs targeted historical reading")
        self.session.finish(work, {"value": "all required children"})
        self.assertEqual(before, self.provider.issues[102], "Historical reading cannot reopen or convert")

    def test_new_missing_child_stales_worker_and_does_not_omit_required_work(self):
        graph = self.child_fixture()
        work = self.session.acquire("collect")
        self.add_goal(103, graph, 100)
        response = self.session.call(100, self.session.submission(work, {"value": "stale subset"}, "stale-membership"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)stale|relationship|membership|input")
        self.assertNotIn("collect", self.names())
        self.assertRegex(json.dumps(self.session.checkpoint(100)), r"103")

    def test_unrelated_and_bookkeeping_changes_preserve_relevant_consumer(self):
        graph = self.child_fixture()
        work = self.session.acquire("collect")
        self.add_goal(777, graph)
        self.provider.issues[101]["title"] = "Bookkeeping title"
        self.provider.issues[101]["updated_at"] = "2026-09-29T15:00:00Z"
        self.provider.create_issue_comment(101, "Acknowledged; progress only")
        child_before = self.envelope_for(101)
        other = self.session.acquire("collect", number=101)
        self.assertNotEqual(child_before, self.envelope_for(101), "Real child acquisition must update operational envelope provenance")
        self.session.finish(other, {"value": "unconsumed child result"}, number=101)
        self.session.finish(work, {"value": "unchanged semantic child inputs"})
        self.assertEqual("collect", self.result("collect")[1]["node"]["node"])
        self.assertNotIn("collect", self.names(), "Unchanged selector inputs must reuse the completed result")

    def test_missing_parent_blocks_only_parent_consumer_and_literal_goal_is_preserved(self):
        graph = self.symbolic_graph("#parent")
        self.install(graph)
        self.assertIn("produce", self.names())
        self.assertNotIn("collect", self.names())
        self.assertRegex(json.dumps(self.session.checkpoint(100)), r"(?i)parent|missing")
        literal = self.symbolic_graph(101)
        self.install(literal)
        self.add_goal(101, literal)
        self.complete(101)
        work = self.session.acquire("collect")
        selected = [r for r in self.resolutions(work) if r["selector"]["goal"] == 101]
        self.assertTrue(selected)
        self.assertEqual([101], [t["goal"] for t in selected[0]["targets"]])
        self.session.finish(work, {"value": "literal preserved"})

    def test_known_empty_is_aggregate_not_unknown_and_does_not_manufacture_artifact(self):
        self.install(self.symbolic_graph())
        work = self.session.acquire("collect")
        selected = [r for r in self.resolutions(work) if r["selector"]["goal"] == "#children"]
        self.assertTrue(selected)
        self.assertTrue(all(r["targets"] == [] for r in selected))
        self.session.finish(work, {"value": "known empty aggregate"})
        self.install(self.symbolic_graph("#parent"))
        self.assertNotIn("collect", self.names(), "Null parent cannot create one singular artifact")

    def test_partial_failed_or_conflicting_discovery_blocks_only_affected_consumers(self):
        self.child_fixture()
        self.discovery_incomplete = True
        self.assertNotIn("collect", self.names())
        self.assertIn("produce", self.names())
        self.discovery_incomplete = False
        self.discovery_failure = True
        self.assertNotIn("collect", self.names())
        self.assertRegex(json.dumps(self.session.checkpoint(100)), r"(?i)relationship|unknown|unavailable|incomplete")
        self.discovery_failure = False
        self.assertIn("collect", self.names())
        self.provider.get_parent_issue = lambda _number: 777
        self.assertNotIn("collect", self.names(), "Conflicting provider/canonical relationship cannot issue known context")

    def test_native_subissue_omission_cannot_silently_drop_canonical_child(self):
        self.child_fixture()
        self.provider.get_sub_issues = lambda _number: [{"number": 101}]
        steps = self.session.checkpoint(100)
        runnable = [s for s in steps if s.get("kind") == "execute" and s["node"]["node"] == "collect"]
        if runnable:
            work = self.session.acquire("collect")
            targets = {t["goal"] for r in self.resolutions(work) if r["selector"]["goal"] == "#children" for t in r["targets"]}
            self.assertEqual({101, 102}, targets, "Alternative proven coverage must still include omitted canonical child")
        else:
            self.assertRegex(json.dumps(steps), r"(?i)coverage|complete|relationship|mismatch|unknown")

    def test_projected_cross_goal_cycle_blocks_acquisition_not_unrelated_work(self):
        self.child_fixture()
        graph = self.symbolic_graph("#parent")
        graph["nodes"][0]["requires"] = [{"kind": "node", "goal": "#parent", "node": "collect"}]
        envelope = self.envelope_for(101)
        payload = self.read_at(101, envelope["payload"])
        payload["graph"] = self.blob(graph)
        envelope["payload"] = self.blob(payload)
        self.provider.comments[101] = copy.deepcopy(self.provider.comments[100])
        envelope["revision"] += 1
        self.put_envelope(101, envelope)
        steps = self.session.checkpoint(100)
        self.assertNotIn("collect", self.names())
        self.assertIn("produce", self.names())
        text = json.dumps(steps)
        self.assertRegex(text, r"(?i)cycle|acyclic")
        self.assertIn("101", text)
        self.assertIn("100", text)

    def test_caller_resolutions_cannot_override_host_acquisition(self):
        self.child_fixture()
        work = self.session.acquire("collect")
        self.assert_rejected(work, {"value": "full join"}, {"resolutions": []}, r"(?i)host|field|resolution|binding")

    def test_plural_finding_target_rejected_even_for_one_child_then_literal_succeeds(self):
        self.findings(admit=False)
        self.replace_spec("A source revision permits the next exact producer and finding")
        self.produce()
        work = self.session.acquire("find")
        subject = self.produced("produce")
        source = self.produced("ingest", "comment")
        valid = {slot: {"id": slot + "_new", "revision": 1, "source": source, "subjects": [subject],
                       "target": scope("produce"), "request": "Exact local correction", "rationale": "Observed defect", "supersedes": None}
                 for slot in ("first", "second")}
        self.add_goal(101, self.graph, 100)
        invalid = copy.deepcopy(valid)
        invalid["first"]["target"]["subject"]["goal"] = "#children"
        self.assert_rejected(work, valid, {"outputs": invalid}, r"(?i)plural|literal|target|goal|scope")


    def test_symbolic_member_and_join_project_each_required_child(self):
        for kind in ("member", "join"):
            with self.subTest(kind=kind):
                graph = self.symbolic_graph(kind=kind)
                self.install(graph)
                children = selected_graph()
                def local(value):
                    if isinstance(value, list):
                        return [local(v) for v in value]
                    if isinstance(value, dict):
                        return {k: "#this" if k == "goal" and v == 100 else local(v) for k, v in value.items()}
                    return value
                children = local(children)
                for number in (101, 102):
                    self.add_goal(number, children, 100)
                    selected = self.session.acquire("select", number=number)
                    self.session.finish(selected, {"chosen": {"items": {"a": "Required investigation"}, "rationale": "One current item"}}, number=number)
                    member = self.session.acquire("investigate", number=number, item="a")
                    self.session.finish(member, {"value": "evidence %d" % number}, number=number)
                work = self.session.acquire("collect")
                selected = [r for r in self.resolutions(work) if r["selector"]["goal"] == "#children"]
                self.assertTrue(selected)
                for resolution in selected:
                    self.assertEqual({101, 102}, {t["goal"] for t in resolution["targets"]})
                    self.assertTrue(all(t["item"] == "a" and t["generation"] == 1 for t in resolution["targets"]))
                self.session.finish(work, {"value": "joined members"})

    def test_child_requires_current_parent_review_and_blocks_again_after_parent_drift(self):
        parent_graph = self.symbolic_graph("#this")
        review = parent_graph["nodes"][1]
        review["id"] = "review_parent"
        review["executor"]["authority"]["subject"]["node"] = "review_parent"
        review["inputs"]["values"]["mode"] = "identity"
        review["independent_of"] = [{"kind": "node", "goal": "#this", "node": "produce"}]
        parent_graph["terminals"][0]["node"] = "review_parent"
        child_graph = self.symbolic_graph("#parent")
        child_graph["nodes"][1]["requires"][0]["node"] = "review_parent"
        child_graph["nodes"][1]["inputs"]["values"]["producer"]["node"]["node"] = "review_parent"
        child_graph["nodes"][1]["inputs"]["values"]["mode"] = "identity"
        self.install(child_graph)
        self.add_goal(99, parent_graph)
        envelope = self.envelope_for(100)
        envelope["parent"] = 99
        envelope["revision"] += 1
        self.put_envelope(100, envelope)
        self.complete(99)
        self.assertNotIn("collect", self.names(), "Parent production alone cannot replace independent review")
        self.complete(99, "review_parent", "approved", actor="parent-reviewer")
        self.assertIn("collect", self.names())
        parent = self.envelope_for(99)
        payload = self.read_at(99, parent["payload"])
        spec = self.read_at(99, payload["spec"])
        spec["content"] = "Changed parent contract requires current review"
        first_new = len(self.provider.comments[100])
        payload["spec"] = self.blob(spec)
        parent["payload"] = self.blob(payload)
        for comment in copy.deepcopy(self.provider.comments[100][first_new:]):
            self.provider.create_issue_comment(99, comment["body"])
        parent["revision"] += 1
        self.put_envelope(99, parent)
        self.assertNotIn("collect", self.names())
        self.complete(99, value="updated parent")
        self.assertNotIn("collect", self.names(), "Old parent review cannot authorize the revised parent")
        self.complete(99, "review_parent", "approved", actor="parent-reviewer")
        self.assertIn("collect", self.names())
        self.complete(100, "collect", "current reviewed parent")

    def test_relevant_parent_change_rejects_acquired_child_result(self):
        graph = self.symbolic_graph("#parent")
        self.install(graph)
        self.add_goal(99, graph)
        self.add_goal(98, graph)
        self.complete(99, value="old parent")
        self.complete(98, value="new parent")
        envelope = self.envelope_for(100)
        envelope["parent"] = 99
        envelope["revision"] += 1
        self.put_envelope(100, envelope)
        work = self.session.acquire("collect")
        # External authenticated source transition is data drift, not a forged
        # CLI authority result. Separate tests exercise guarded public mutation.
        envelope = self.envelope_for(100)
        envelope["parent"] = 98
        envelope["revision"] += 1
        self.put_envelope(100, envelope)
        response = self.session.call(100, self.session.submission(work, {"value": "old context"}, "stale-parent"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)stale|parent|relationship|input")

    def test_consumed_child_evidence_drift_rejects_acquired_worker(self):
        self.child_fixture()
        work = self.session.acquire("collect")
        envelope = self.envelope_for(101)
        payload = self.read_at(101, envelope["payload"])
        spec = self.read_at(101, payload["spec"])
        spec["content"] = "Substantively changed child request"
        first_new = len(self.provider.comments[100])
        payload["spec"] = self.blob(spec)
        envelope["payload"] = self.blob(payload)
        for comment in copy.deepcopy(self.provider.comments[100][first_new:]):
            self.provider.create_issue_comment(101, comment["body"])
        envelope["revision"] += 1
        self.put_envelope(101, envelope)
        self.complete(101, value="corrected child")
        response = self.session.call(100, self.session.submission(work, {"value": "old child"}, "stale-child"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)stale|input|evidence|relationship")

    def test_path_is_selected_for_each_child_before_canonical_aggregation(self):
        graph = self.symbolic_graph()
        graph["nodes"][0]["outputs"]["value"] = output("detail", shape({"selected": "yes", "irrelevant": "old"}))
        graph["nodes"][1]["inputs"]["values"]["path"] = ["selected"]
        self.install(graph)
        for number in (102, 101):
            self.add_goal(number, graph, 100)
            self.complete(number, value={"selected": str(number), "irrelevant": "unconsumed"})
        work = self.session.acquire("collect")
        # Public read must expose the actual selected input value. This proposed
        # read projection contains data, not a fixture-computed fingerprint.
        response = self.session.call(100, {"operation": "read", "node": work["node"]})
        content = response["next_steps"][0]["content"]
        self.assertEqual({"101": "101", "102": "102"}, content["inputs"]["values"])
        self.assertEqual(["101", "102"], list(content["inputs"]["values"]))
        self.session.finish(work, {"value": "per-child projection"})

    def test_plural_input_rejects_scalar_contract_after_valid_aggregate_control(self):
        for kind in ("node", "member", "join"):
            with self.subTest(kind=kind):
                graph = self.symbolic_graph(kind=kind)
                expected = {"kind": "map", "values": {"kind": "string"}}
                if kind == "join":
                    expected = {"kind": "map", "values": expected}
                self.assertEqual(expected, graph["nodes"][1]["inputs"]["values"]["type"])
                self.assertEqual([], z._policy._workflow_phase_dag_errors(graph),
                                 "Valid aggregate declaration must precede rejection")
                invalid = copy.deepcopy(graph)
                invalid["nodes"][1]["inputs"]["values"]["type"] = {"kind": "string"}
                self.assertRegex("; ".join(z._policy._workflow_phase_dag_errors(invalid)),
                                 r"(?i)input|aggregate|map|type")

    def test_archived_state_alone_does_not_satisfy_required_child_evidence(self):
        graph = self.child_fixture()
        self.add_goal(103, graph, 100)
        envelope = self.envelope_for(103)
        envelope["state"] = "archived"
        self.put_envelope(103, envelope)
        self.provider.issues[103]["state"] = "closed"
        before = copy.deepcopy(self.provider.issues[103])
        self.assertNotIn("collect", self.names())
        self.assertRegex(json.dumps(self.session.checkpoint(100)), r"103")
        self.assertEqual(before, self.provider.issues[103])

    def parent_change_fixture(self):
        """Finite ordinary output wire proposal, subject to independent review.

        parent_change={repository,subject,expected,parent}; expected is the exact
        subject GoalEnvelope Ref observed after acquisition, checked by the host.
        Root role plus configured permits authorizes only this guarded relation
        change, not scope removal or obligation retirement. No new operation.
        """
        move = task("move", role="root")
        change_type = {"kind": "object", "fields": {
            "repository": {"kind": "string"}, "subject": {"kind": "integer"},
            "expected": REF_TYPE,
            "parent": {"kind": "union", "variants": [{"kind": "integer"}, {"kind": "null"}]}}}
        move["outputs"] = {"change": output("parent_change", change_type)}
        move["executor"]["authority"] = scope("move", "change")
        move["permits"] = [{"type": "parent_change", "scope": scope("move", "change")}]
        graph = {"nodes": [move], "task_sets": [], "terminals": [selector("move")]}
        self.install(graph)
        self.add_goal(99, graph)
        # Creating an immutable fixture Ref is not a parent change. The host
        # must compare the actual canonical record under ownership at submit.
        work = self.session.acquire("move", actor="root-thread")
        expected = self.blob(self.envelope_for(100))
        request = {"repository": "owner/repo", "subject": 100, "expected": expected, "parent": 99}
        return work, request

    def test_guarded_parent_change_positive_retry_and_retained_before_after(self):
        work, change = self.parent_change_fixture()
        payload = self.session.submission(work, {"change": change}, "parent-change-once")
        result = self.session.call(100, payload)
        self.assertEqual(99, self.envelope_for(100)["parent"])
        after = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.assertEqual(result, self.session.call(100, payload))
        self.assertEqual(after, (self.provider.issues, self.provider.comments))
        self.assertEqual(None, self.read_blob(change["expected"])["parent"])
        self.assertEqual(change, self.read_blob(self.produced("move", "change"))["content"])
        self.assertNotIn("schema_activation", json.dumps(result))

    def test_parent_change_rejects_self_unknown_ancestry_crossrepo_and_stale_predecessor(self):
        work, change = self.parent_change_fixture()
        for mutation, diagnostic in (({"parent": 100}, r"(?i)self|cycle|parent"),
                                     ({"parent": 999}, r"(?i)unknown|ancestor|missing|parent"),
                                     ({"repository": "foreign/repo"}, r"(?i)repository|identity|authority"),
                                     ({"expected": REF}, r"(?i)stale|predecessor|source|reference|missing")):
            with self.subTest(mutation=mutation):
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                request = self.session.submission(work, {"change": {**change, **mutation}}, "bad-parent-" + str(len(self.session.calls)))
                response = self.session.call(100, request, expected=2)
                self.assertRegex(json.dumps(response), diagnostic)
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        # Same acquired subject must still accept its exact valid correction.
        self.session.finish(work, {"change": change})
        self.assertEqual(99, self.envelope_for(100)["parent"])

    def test_parent_change_requires_actual_root_not_claimed_content_actor(self):
        work, change = self.parent_change_fixture()
        self.assert_rejected(work, {"change": change}, {"actor": "untrusted-worker"}, r"(?i)root|actor|owner|authority")
        self.assertEqual(99, self.envelope_for(100)["parent"])

    def test_parent_cycle_and_concurrent_predecessor_drift_do_not_overwrite(self):
        work, change = self.parent_change_fixture()
        parent = self.envelope_for(99)
        parent["parent"] = 100
        parent["revision"] += 1
        self.put_envelope(99, parent)
        request = self.session.submission(work, {"change": change}, "parent-cycle")
        response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)cycle|ancestor")
        self.assertIsNone(self.envelope_for(100)["parent"])
        parent["parent"] = None
        parent["revision"] += 1
        self.put_envelope(99, parent)
        current = self.envelope_for(100)
        current["revision"] += 1
        self.put_envelope(100, current)
        before = copy.deepcopy(self.provider.issues)
        response = self.session.call(100, self.session.submission(work, {"change": change}, "concurrent-parent"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)stale|predecessor|revision|input")
        self.assertEqual(before, self.provider.issues)


    def test_reparenting_preserves_admitted_findings_and_does_not_release_join(self):
        self.parent_change_fixture()
        move = copy.deepcopy(self.graph["nodes"][0])
        graph = correction_graph()
        graph["nodes"].append(move)
        _findings, admissions = self.findings(graph=graph)
        self.add_goal(99, graph)
        retained = {slot: self.produced("find", slot) for slot in admissions}
        work = self.session.acquire("move", actor="root-thread")
        change = {"repository": "owner/repo", "subject": 100,
                  "expected": self.blob(self.envelope_for(100)), "parent": 99}
        self.session.finish(work, {"change": change})
        self.assertEqual(99, self.envelope_for(100)["parent"])
        self.assertIn("produce", self.names(), "Admitted correction remains substantive input after reparenting")
        self.assertNotIn("finish", self.names(), "Parent move cannot resolve an outstanding finding")
        self.assertEqual(retained, {slot: self.produced("find", slot) for slot in admissions})

    def test_parent_change_lost_write_response_is_read_back_before_exact_retry(self):
        work, change = self.parent_change_fixture()
        request = self.session.submission(work, {"change": change}, "lost-parent-write")
        original = self.provider.update_issue
        lost = []
        def uncertain(number, payload):
            result = original(number, payload)
            if number == 100 and not lost and self.envelope_for(100)["parent"] == 99:
                lost.append(True)
                raise RuntimeError("provider applied parent body but response was lost")
            return result
        self.provider.update_issue = uncertain
        self.session.call(100, request, expected=None)
        self.assertTrue(lost, "Fault must reach the actual provider write boundary")
        self.provider.update_issue = original
        result = self.session.call(100, request)
        self.assertEqual(99, self.envelope_for(100)["parent"])
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.assertEqual(result, self.session.call(100, request))
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))


    def test_archived_predecessor_read_preserves_source_and_requires_exact_equivalence(self):
        self.child_fixture()
        # Current archived exact evidence already passes the separate positive
        # control. Historical closure and an old approval cannot impersonate a
        # current result; targeted predecessor decoding is still permitted.
        source = old.fixtures.PortfolioTests().issue(103)
        legacy = old.fixtures.PortfolioTests().goal(parent=100, status="done")
        source["body"] = "## Outcome\nHistorical child delivery.\n\n<!-- zzzops-goal\n" + json.dumps(legacy) + "\nzzzops-goal -->"
        source["state"] = "closed"
        self.provider.issues[103] = source
        self.provider.comments[103] = []
        before = copy.deepcopy(source)
        self.relationship_reads.clear()
        self.assertNotIn("collect", self.names())
        diagnostic = json.dumps(self.session.checkpoint(100))
        self.assertRegex(diagnostic, r"(?i)103")
        self.assertRegex(diagnostic, r"(?i)equivalence|evidence|historical|mapping|missing")
        self.assertIn(103, self.relationship_reads)
        self.assertEqual(before, self.provider.issues[103])
        self.assertEqual([], self.provider.comments[103], "Read cannot convert or fabricate archived approval")



class GenericStoragePublicTests(DagFixture):
    """Storage invariants on exact host output Refs from generic submissions."""

    def setUp(self):
        super().setUp()
        graph = review_graph()
        graph["nodes"][0]["inputs"] = {"request": spec_input()}
        self.install(graph)
        self.version = 0

    def versioned_output(self, value):
        if self.version:
            self.replace_spec("Explicit substantive request version %d" % self.version)
        self.version += 1
        acquired = self.session.acquire("produce")
        before = len(self.provider.comments[100])
        self.last_submission = self.session.submission(acquired, {"value": value}, "storage-output-%d" % self.version)
        self.session.call(100, self.last_submission)
        ref = self.produced("produce", "value")
        artifact = self.session.read(100, ref)
        self.assertEqual(value, artifact["content"])
        self.assertEqual(ref["hash"], content_hash(artifact))
        return ref, artifact, before

    def records(self, reference):
        found = []
        for comment in self.provider.comments[100]:
            envelope = z._comment_store.decode_envelope(comment["body"])
            if envelope is not None:
                for record in envelope["artifacts"]:
                    if record["hash"] == reference["hash"]:
                        found.append((comment, envelope, record))
        self.assertTrue(found, "Host submission must store the exact returned output identity")
        return found

    def remove_output_record(self, reference):
        for comment, envelope, record in self.records(reference):
            envelope["artifacts"].remove(record)
            comment["body"] = z._comment_store.encode_envelope(envelope)

    def test_caller_hash_or_extra_operation_cannot_authorize_inline_outputs(self):
        work = self.session.acquire("produce")
        for changes in ({"artifacts": [{"content": "candidate", "hash": "sha256:" + "0" * 64}]},
                        {"artifacts": [{"content": "candidate", "operation": "approve"}]},
                        {"actor": "intruder"}):
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            request = self.session.submission(work, {"value": "candidate"}, "forged-inline-" + str(len(self.session.calls)))
            response = self.session.call(100, {**request, **changes}, expected=2)
            self.assertRegex(json.dumps(response), r"(?i)field|artifact|hash|operation|actor|executor|contract|unsupported")
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(work, {"value": "host derives all authoritative metadata"})

    def test_oversized_single_record_preflight_precedes_every_bundle_write(self):
        graph = copy.deepcopy(self.graph)
        graph["nodes"][0]["outputs"]["large"] = output("text", {"kind": "string"})
        self.install(graph)
        work = self.session.acquire("produce")
        noise = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(2500))
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, self.session.submission(work, {"value": "small valid slot", "large": noise}, "record-too-large"), expected=2)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertRegex(json.dumps(response), r"65536")
        self.assertRegex(json.dumps(response), r"(?i)reference")
        self.session.finish(work, {"value": "small valid slot", "large": "bounded valid control"})

    def test_existing_storage_budget_rejection_preserves_readable_history_and_usable_lease(self):
        work = self.session.acquire("produce")
        store = z._comment_store
        contents = [{"type": "historical_attachment", "content": "existing-%d:" % i + "x" * 900000,
            "producer": None, "provenance": {"actor": "imported-history", "source": None,
            "policy": content_hash(self.session.project["policy"])}} for i in range(20)]
        self.assertGreater(sum(len(store.canonical(content).encode()) for content in contents),
                           store.MAX_RECONSTRUCTION_WORK_BYTES)
        # Each imported envelope is individually bounded; only the unrelated
        # retained total exceeds the active selected reconstruction budget.
        for index, content in enumerate(contents):
            record = store.ArtifactIndex([]).record(content)
            for body in store.pack_envelopes({"goal": 100, "transaction": "existing-budget-" + str(index)}, [record]):
                self.provider.create_issue_comment(100, body)
        historical = copy.deepcopy(self.provider.comments[100])
        reference = {"hash": content_hash(contents[0]), "uri": "urn:" + content_hash(contents[0])}
        self.assertEqual(contents[0], self.session.read(100, reference), "Unreferenced imported attachments are data, never result authority")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, self.session.submission(work,
            {"value": "x" * (store.MAX_ARTIFACT_BYTES + 1)}, "active-output-budget"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)limit|bound|size")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertEqual(contents[0], self.session.read(100, reference))
        # The same lease can still publish a bounded output despite old history.
        value = "new:" + "x" * 900000
        self.session.finish(work, {"value": value})
        self.assertEqual(value, self.read_blob(self.produced("produce"))["content"])
        self.assertEqual(contents[0], self.session.read(100, reference))
        for comment in historical:
            self.assertIn(comment, self.provider.comments[100], "Targeted work cannot prune historical bytes")

    def test_aggregate_output_budget_rejects_all_slots_without_mutation_then_accepts_small_bundle(self):
        graph = copy.deepcopy(self.graph)
        names = ["value", *["extra_%d" % i for i in range(17)]]
        graph["nodes"][0]["outputs"] = {name: output("text", {"kind": "string"}) for name in names}
        self.install(graph)
        work = self.session.acquire("produce")
        large = {name: name + ":" + "x" * 900000 for name in names}
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, self.session.submission(work, large, "aggregate-budget"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)limit|budget|large|size|bytes")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        small = {name: "bounded " + name for name in names}
        self.session.finish(work, small)
        for slot, value in small.items():
            self.assertEqual(value, self.session.read(100, self.produced("produce", slot))["content"])

    def payload_from_body(self, body):
        match = re.search(r"<!-- zzzops-goal\s*\n(.*?)\nzzzops-goal -->", body, re.S)
        self.assertIsNotNone(match)
        envelope = json.loads(match[1])
        self.assertEqual(2, envelope["schema_version"])
        return self.read_blob(envelope["payload"])

    def test_start_and_bind_persist_distinct_unbound_then_actual_worker_checkpoints(self):
        work = self.session.acquire("produce", actor="actual-storage-worker")
        observed = []
        for number, payload in self.provider.updates:
            if number == 100 and "body" in payload:
                state = self.payload_from_body(payload["body"])
                observed.extend(lease for lease in state["operational"]["leases"] if lease["token"] == work["lease"]["token"])
        self.assertGreaterEqual(len(observed), 2)
        self.assertIsNone(observed[-2]["worker"])
        self.assertEqual("actual-storage-worker", observed[-1]["worker"])
        self.assertEqual(observed[-2]["token"], observed[-1]["token"])
        self.session.finish(work, {"value": "Bound exact durable worker"})

    def test_pending_start_retry_retains_generated_identity_and_completed_replay_never_resurrects(self):
        ready = self.session.ready()
        self.assertEqual(1, len(ready))
        step = ready[0]
        receipt = json.loads(Path(step["policy"]["path"]).read_text())["policy_receipt"]
        request = {**step["start"], "policy_receipt": receipt, "request_id": "stable-start-retry"}
        before_comments = len(self.provider.comments[100])
        attempted = []
        def unavailable(number, payload):
            attempted.append(copy.deepcopy(payload))
            raise RuntimeError("Provider unavailable before start body publication")
        with mock.patch.object(self.provider, "update_issue", side_effect=unavailable):
            self.session.call(100, request, expected=None)
        self.assertEqual(1, len(attempted), "Pending append must precede attempted body publication")
        prior = self.payload_from_body(attempted[0]["body"])["operational"]["leases"]
        self.assertEqual(1, len(prior))
        acquired = self.session.call(100, request)["next_steps"][0]
        self.assertEqual(prior[0]["token"], acquired["lease"]["token"])
        self.assertEqual(prior[0]["expires_at"], acquired["lease"]["expires_at"])
        self.assertEqual(before_comments + 1, len(self.provider.comments[100]))
        self.session.call(100, {**acquired["bind"], "actor": "retry-worker", "selection": acquired["lease"]["selection"], "policy_receipt": receipt})
        acquired["bound_actor"] = "retry-worker"
        self.session.finish(acquired, {"value": "Current completed result"})
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, request, expected=None)
        self.assertFalse(self.payload()[1]["operational"]["leases"])
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def logical_selector(self, revision=None):
        selector_value = {"node": {"goal": 100, "node": "produce", "item": None, "generation": 1}, "output": "value"}
        if revision is not None:
            selector_value["revision"] = revision
        return selector_value

    def test_logical_latest_and_exact_historical_revisions_preserve_host_refs(self):
        versions = []
        for value in ("first", "second", "second"):
            reference, artifact, _before = self.versioned_output(value)
            versions.append((self.payload()[0]["revision"], reference, artifact))
        latest = self.session.call(100, {"operation": "read", "artifact": self.logical_selector()})["next_steps"][0]
        self.assertEqual(versions[-1][2], latest["content"])
        self.assertEqual(versions[-1][1]["hash"], latest["resolved"]["hash"])
        self.assertEqual(versions[-1][0], latest["resolved"]["revision"])
        for revision, reference, artifact in versions:
            with self.subTest(revision=revision):
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                read = self.session.call(100, {"operation": "read", "artifact": self.logical_selector(revision)})["next_steps"][0]
                self.assertEqual(artifact, read["content"])
                self.assertEqual(reference["hash"], read["resolved"]["hash"])
                self.assertEqual(revision, read["resolved"]["revision"])
                self.assertEqual(artifact, self.session.read(100, reference))
                self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_immutable_cache_does_not_freeze_logical_latest_output(self):
        first, first_artifact, _before = self.versioned_output("old")
        engine = z.workflow_engine(self.fixture.repo, self.session.project, self.session.runtime)
        self.assertEqual(first_artifact, engine.read_artifact(100, first))
        second, second_artifact, _before = self.versioned_output("new")
        engine.invalidate()
        self.assertEqual(second_artifact, engine.read_artifact(100, self.logical_selector()))
        self.assertEqual(first_artifact, engine.read_artifact(100, first))
        self.assertNotEqual(first, second)

    def test_historical_reads_do_not_resurrect_old_coordination_or_rewrite_current_lease(self):
        old, artifact, _before = self.versioned_output("accepted old output")
        revision = self.payload()[0]["revision"]
        self.replace_spec("New substantive request still being executed")
        work = self.session.acquire("produce")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        read = self.session.call(100, {"operation": "read", "artifact": self.logical_selector(revision)})["next_steps"][0]
        self.assertEqual(artifact, read["content"])
        self.assertEqual(old["hash"], read["resolved"]["hash"])
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        leases = self.payload()[1]["operational"]["leases"]
        self.assertEqual([work["lease"]["token"]], [lease["token"] for lease in leases])
        self.session.finish(work, {"value": "current output"})

    def multipart_request(self, *, reset=True, request_id="multipart-exact"):
        graph = copy.deepcopy(self.graph)
        graph["nodes"][0]["outputs"].update({name: output("text", {"kind": "string"}) for name in ("extra_a", "extra_b")})
        if reset:
            self.install(graph)
        acquired = self.session.acquire("produce")
        values = {name: "".join(hashlib.sha256((name + str(i)).encode()).hexdigest() for i in range(650))
                  for name in ("value", "extra_a", "extra_b")}
        return acquired, values, self.session.submission(acquired, values, request_id)

    def leave_partial_upload(self, request):
        original = self.provider.create_issue_comment
        calls = []
        before = copy.deepcopy(self.provider.issues[100])
        comments = len(self.provider.comments[100])
        def stop_after_one(number, body):
            calls.append(body)
            if len(calls) > 1:
                raise RuntimeError("Injected second multipart write failure")
            return original(number, body)
        with mock.patch.object(self.provider, "create_issue_comment", side_effect=stop_after_one):
            self.session.call(100, request, expected=None)
        self.assertGreater(len(calls), 1, "Fault must reach a genuinely multipart transaction")
        self.assertEqual(comments + 1, len(self.provider.comments[100]))
        self.assertEqual(before, self.provider.issues[100], "Partial upload cannot publish its semantic envelope")
        return copy.deepcopy(self.provider.comments[100][-1]), comments

    def test_multipart_retry_reuses_partial_bytes_and_publishes_one_atomic_output_bundle(self):
        _work, values, request = self.multipart_request()
        updates = len(self.provider.updates)
        partial, before_comments = self.leave_partial_upload(request)
        self.session.call(100, request)
        appended = self.provider.comments[100][before_comments:]
        self.assertGreater(len(appended), 1)
        self.assertEqual(1, sum(comment["body"] == partial["body"] for comment in appended))
        self.assertTrue(all(len(comment["body"]) <= 65536 for comment in appended))
        self.assertEqual(updates + 1, len(self.provider.updates))
        for slot, value in values.items():
            self.assertEqual(value, self.session.read(100, self.produced("produce", slot))["content"])
        self.assertFalse(self.payload()[1]["operational"]["leases"])
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, request)
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))

    def test_partial_upload_still_requires_actual_actor_and_current_input(self):
        _work, values, request = self.multipart_request()
        self.leave_partial_upload(request)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, {**request, "actor": "intruder"}, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)actor|executor|owner|payload|receipt")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        body = self.provider.issues[100]["body"]
        self.replace_spec("Changed substantive specification during partial upload")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)stale|input|source|current")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.provider.issues[100]["body"] = body  # Restore exact external input; pending bytes remain non-authoritative.
        self.session.call(100, request)
        for slot, value in values.items():
            self.assertEqual(value, self.session.read(100, self.produced("produce", slot))["content"])

    def test_pending_multipart_outputs_cannot_replace_latest_historical_or_pinned_reads(self):
        _work, values, request = self.multipart_request(request_id="committed-first-bundle")
        self.session.call(100, request)
        reference = self.produced("produce")
        artifact = self.session.read(100, reference)
        revision = self.payload()[0]["revision"]
        self.replace_spec("Substantively revised request awaiting candidate publication")
        _work, newer, pending = self.multipart_request(reset=False, request_id="pending-new-bundle")
        # Independent changed bytes force a real multipart transaction even
        # when production preserves efficient sparse output deltas.
        newer = {name: "".join(hashlib.sha256(("new-bundle-" + name + str(i)).encode()).hexdigest()
                              for i in range(650)) for name in newer}
        pending["outputs"] = newer
        self.leave_partial_upload(pending)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.assertEqual(artifact, self.session.read(100, reference))
        for selected in (self.logical_selector(), self.logical_selector(revision)):
            read = self.session.call(100, {"operation": "read", "artifact": selected})["next_steps"][0]
            self.assertEqual(artifact, read["content"])
            self.assertEqual(reference["hash"], read["resolved"]["hash"])
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.call(100, pending)
        self.assertEqual(newer["value"], self.session.read(100, self.produced("produce"))["content"])

    def test_inline_output_append_and_body_lost_responses_reuse_one_transaction(self):
        for boundary in ("create_issue_comment", "update_issue"):
            with self.subTest(boundary=boundary):
                graph = review_graph()
                graph["nodes"][0]["outputs"]["extra"] = output("additional_evidence", {"kind": "string"})
                self.install(graph)
                work = self.session.acquire("produce")
                values = {"value": "Exact crash-safe candidate", "extra": "Additional exact evidence"}
                request = self.session.submission(work, values, "inline-lost-" + boundary)
                before_comments, before_updates = len(self.provider.comments[100]), len(self.provider.updates)
                original = getattr(self.provider, boundary)
                failed = []
                def lost(*args, **kwargs):
                    result = original(*args, **kwargs)
                    if not failed:
                        failed.append(True)
                        raise z.GoalTransitionProviderError("Actual provider write committed, response lost")
                    return result
                with mock.patch.object(self.provider, boundary, side_effect=lost):
                    self.session.call(100, request, expected=None)
                self.assertTrue(failed, "Fault must reach the actual provider write")
                self.session.call(100, request)
                self.assertEqual(before_comments + 1, len(self.provider.comments[100]))
                self.assertEqual(before_updates + 1, len(self.provider.updates))
                for slot, value in values.items():
                    self.assertEqual(value, self.session.read(100, self.produced("produce", slot))["content"])
                self.assertFalse(self.payload()[1]["operational"]["leases"])
                stable = copy.deepcopy((self.provider.issues, self.provider.comments))
                self.session.call(100, request)
                self.assertEqual(stable, (self.provider.issues, self.provider.comments))

    def test_archived_checkpoint_and_exact_read_preserve_source_and_have_no_cursor(self):
        envelope, payload = self.payload()
        envelope["state"] = "archived"
        envelope["revision"] += 1
        self.provider.issues[100]["state"] = "closed"
        self.provider.issues[100]["body"] = "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"
        original = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, expected=None)
        self.assertFalse(any(step.get("kind") == "execute" for step in response["next_steps"]))
        self.assertEqual(self.read_blob(payload["spec"]), self.session.read(100, payload["spec"]))
        self.assertEqual(original, (self.provider.issues, self.provider.comments))
        self.assertEqual({"leases", "receipts"}, set(payload["operational"]))

    def test_inline_outputs_result_receipt_and_lease_release_share_one_checkpoint(self):
        graph = copy.deepcopy(self.graph)
        graph["nodes"][0]["outputs"]["other"] = output("text", {"kind": "string"})
        self.install(graph)
        work = self.session.acquire("produce")
        before_comments, before_updates = len(self.provider.comments[100]), len(self.provider.updates)
        request = self.session.submission(work, {"value": "first", "other": "second"}, "single-checkpoint-bundle")
        self.session.call(100, request)
        self.assertEqual(before_comments + 1, len(self.provider.comments[100]))
        self.assertEqual(before_updates + 1, len(self.provider.updates))
        envelope = z._comment_store.decode_envelope(self.provider.comments[100][-1]["body"])
        self.assertIsInstance(envelope, dict)
        hashes = {record["hash"] for record in envelope["artifacts"]}
        for reference in (self.produced("produce"), self.produced("produce", "other"), self.result("produce")[0]):
            self.assertIn(reference["hash"], hashes)
        _goal, payload = self.payload()
        self.assertFalse(payload["operational"]["leases"])
        self.assertTrue(any(receipt["request"] == "single-checkpoint-bundle" for receipt in payload["operational"]["receipts"]))

    def test_alternate_legacy_compression_preserves_typed_output_identity_and_retry(self):
        graph = copy.deepcopy(self.graph)
        graph["nodes"][0]["outputs"]["value"]["schema"] = {"kind": "union", "variants": [
            {"kind": "string"}, {"kind": "object", "fields": {"text": {"kind": "string"}}},
            {"kind": "array", "items": {"kind": "union", "variants": [
                {"kind": "integer"}, {"kind": "boolean"}, {"kind": "null"}]}}]}
        self.install(graph)
        for value in ("Raw Markdown 😀\r\nno final newline", {"text": "long paragraph " * 100}, [1, False, None]):
            with self.subTest(value_type=type(value).__name__):
                reference, artifact, _before = self.versioned_output(value)
                raw = json.dumps({"hash": reference["hash"], "content": artifact}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
                encoded = base64.b64encode(zlib.compress(raw, level=0)).decode()
                body = "<!-- zzzops-artifact " + reference["hash"] + " -->\n<details><summary>Immutable phase artifact</summary>\n\n```text\n" + encoded + "\n```\n</details>"
                self.provider.create_issue_comment(100, body)
                self.assertEqual(artifact, self.session.read(100, reference))
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                self.session.call(100, self.last_submission)
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
                self.assertEqual(reference, self.produced("produce", "value"))

    def test_sparse_output_delta_is_smaller_and_missing_base_fails_closed(self):
        text = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(500))
        first, _artifact, _before = self.versioned_output(text)
        changed, artifact, _before = self.versioned_output(text[:16000] + "!" + text[16001:])
        first_record = self.records(first)[0][2]
        record = self.records(changed)[0][2]
        self.assertEqual("delta", record["kind"])
        self.assertLess(len(json.dumps(record)), len(json.dumps(first_record)))
        self.assertEqual(artifact, self.session.read(100, changed))
        self.remove_output_record(first)
        self.session.call(100, {"operation": "read", "artifact": changed}, expected=2)

    def test_output_delta_cycle_missing_base_duplicate_patch_and_version_reject(self):
        text = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(200))
        self.versioned_output(text)
        reference, artifact, _before = self.versioned_output("!" + text[1:])
        comment, envelope, record = self.records(reference)[0]
        self.assertEqual("delta", record["kind"])
        original = comment["body"]
        for corruption in ("cycle", "missing_base", "duplicate", "patch", "version"):
            with self.subTest(corruption=corruption):
                mutated = copy.deepcopy(envelope)
                selected = next(r for r in mutated["artifacts"] if r["hash"] == reference["hash"])
                if corruption == "cycle":
                    selected["base"] = selected["hash"]
                elif corruption == "missing_base":
                    selected["base"] = "sha256:" + "0" * 64
                elif corruption == "duplicate":
                    mutated["artifacts"].append(copy.deepcopy(selected))
                elif corruption == "patch":
                    selected["patch"]["edits"][0][2] += "tampered"
                else:
                    mutated["schema_version"] = 999
                comment["body"] = z._comment_store.encode_envelope(mutated)
                self.session.call(100, {"operation": "read", "artifact": reference}, expected=2)
                comment["body"] = original
                self.assertEqual(artifact, self.session.read(100, reference))

    def test_unfavorable_output_delta_is_independent_full_record(self):
        first, _artifact, _before = self.versioned_output("a" * 20000)
        changed, artifact, _before = self.versioned_output("z" * 20000)
        self.assertEqual("full", self.records(changed)[0][2]["kind"])
        self.remove_output_record(first)
        self.assertEqual(artifact, self.session.read(100, changed))

    def test_output_chain_rollover_preserves_latest_without_initial_base(self):
        text = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(200))
        first, _artifact, _before = self.versioned_output(text)
        for index in range(9):
            text = text[:100 + index] + "!" + text[101 + index:]
            reference, artifact, _before = self.versioned_output(text)
        self.remove_output_record(first)
        self.assertEqual(artifact, self.session.read(100, reference))
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, self.last_submission)
        self.assertEqual(before, (self.provider.issues, self.provider.comments), "Retry reuses bundled immutable output without another checkpoint")

    def test_decoded_reconstruction_work_bound_applies_to_compressible_output(self):
        reference, artifact, _before = self.versioned_output("compressible " * 40000)
        store = self.session.api._workflow.comment_store
        self.assertTrue(hasattr(store, "MAX_RECONSTRUCTION_WORK_BYTES"))
        with mock.patch.dict(sys.modules):
            spec = importlib.util.spec_from_file_location("generic_budget_pristine_zzzops", self.session.api.__file__)
            pristine = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(pristine)
            self.assertIsNot(store, pristine._workflow.comment_store)
            with mock.patch.object(store, "MAX_RECONSTRUCTION_WORK_BYTES", 100000):
                self.session.call(100, {"operation": "read", "artifact": reference}, expected=2)
        self.assertEqual(artifact, self.session.read(100, reference))


if __name__ == "__main__":
    unittest.main()
