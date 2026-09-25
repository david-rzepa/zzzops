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
from types import SimpleNamespace
from unittest import mock

import test_workflow_journey as old
from test_workflow_owned_outputs import PublicSession, content_hash
from test_evidence_dag import review_graph, selector, scope, subject_input, task


z = old.z
REAL_PR_STATES = z._github_pull_request_states


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

    def read_blob(self, ref):
        expected = ref["hash"]
        for comment in self.provider.comments[100]:
            if comment["body"].startswith("<!-- zzzops-artifact " + expected + " -->"):
                encoded = re.search(r"```text\n([A-Za-z0-9+/=]+)\n```", comment["body"])[1]
                value = json.loads(zlib.decompress(base64.b64decode(encoded)))
                self.assertEqual(expected, content_hash(value["content"]))
                return value["content"]
        self.fail("Missing referenced immutable artifact: " + expected)

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
        self.session.finish(acquired, outputs, "valid-after-negative")

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
                           subjects=[self.produced("produce")], request="Carry and refine " + slot)
        self.session.finish(self.session.acquire("find"), revised)
        self.session.finish(self.session.acquire("authorize"), {"value": "Both replacements carry all outstanding requirements"})
        admissions = {slot: {"finding": self.produced("find", slot), "target_inputs": self.result("produce")[1]["inputs"],
                             "authority": self.result("authorize")[0], "applicability": "applicable",
                             "rationale": "Refinement carries prior scope"} for slot in revised}
        bundle = {**admissions, **{slot + "_transfer": {
            "prior": old_admissions[slot]["finding"], "replacement": admissions[slot]["finding"],
            "coverage": "carried", "coverage_evidence": self.result("authorize")[0],
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
        retirement = task("retire_member", ["member_admit"], role="root")
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
        self.session.finish(self.session.acquire("member_admit"), {"admission": admission})
        self.assertNotIn("synthesize", self.names())
        if authorized:
            work = self.session.acquire("retire_member")
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


if __name__ == "__main__":
    unittest.main()
