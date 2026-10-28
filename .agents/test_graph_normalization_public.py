"""Public guarded lazy normalization and applicability behavior."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from unittest import mock

import test_evidence_dag_journeys as dag
import test_understanding_rejection as member


def unsupported_member_retirement_graph():
    """Historical member-debt graph whose missing unresolved route is unsupported."""
    graph = dag.selected_graph()
    member_selector = {"kind": "member", "goal": 100, "expansion": "buckets",
                       "item": "a", "generation": "current"}
    target = {"subject": member_selector, "output": "value"}
    finding_type = copy.deepcopy(dag.FINDING_TYPE)
    exact_member = {**member_selector, "generation": 1}
    finding_type["fields"]["target"] = dag.shape({"subject": exact_member, "output": "value"})
    finder = dag.task("member_finding")
    finder["requires"] = [member_selector]
    finder["outputs"] = {"finding": dag.output("finding", finding_type)}
    finder["permits"] = [{"type": "finding", "scope": target}]
    admit = dag.task("member_admit", ["member_finding"], role="root")
    admit["outputs"] = {"admission": dag.output("admission", dag.ADMISSION_TYPE)}
    admit["permits"] = [{"type": "admission", "scope": target}]
    resolver = dag.task("member_resolve")
    resolver["requires"] = [member_selector]
    resolver["resolves"] = [target]
    resolver["independent_of"] = [member_selector]
    resolver["outputs"] = {"resolution": dag.output("resolution", dag.RESOLUTION_TYPE)}
    resolver["permits"] = [{"type": "resolution", "scope": target}]
    graph["nodes"][1]["gates"] = [{"subject": {"kind": "join", "goal": 100,
                                                    "expansion": "buckets"}, "output": "value"}]
    retirement = dag.task("retire_member", role="root")
    retirement["outputs"] = {"retirement": dag.output("retirement", dag.shape({
        "finding": dag.REF, "target": {"subject": exact_member, "output": "value"},
        "authority": dag.REF, "decision": "retire_member",
        "rationale": "Retain outstanding debt"}))}
    retirement["permits"] = [{"type": "retirement", "scope": target}]
    graph["nodes"] += [finder, admit, resolver, retirement]
    return graph


def compiled_family(case, target):
    graph = case.read_blob(case.payload()[1]["graph"])
    families = [row for row in graph["task_sets"]
        if row["source"].get("producer") == {"slot": "obligation_selections"}
        and row["source"]["path"] == [target, "value"]]
    case.assertEqual(3, len(families))
    assessment = next(row for row in families if any(
        value["type"] == "applicability_assessment" for value in row["template"]["outputs"].values()))
    observation = next(row for row in families if row["template"]["executor"]["role"] == "worker")
    context = next(row for row in families if row not in (assessment, observation))
    return observation, context, assessment


def prepare_compiled_assessment(case, target, finding_id, admission, finding, classification,
                                expected_subject=None):
    observation, context, assessment = compiled_family(case, target)
    for row, actor, text in ((observation, "independent-applicability", "Inspected exact obligation"),
                             (context, "root-thread", "Root bounded classification context")):
        work = case.session.acquire(row["template"]["id"], item=finding_id, actor=actor)
        case.session.finish(work, {next(iter(row["template"]["outputs"])): text})
    work = case.session.acquire(assessment["template"]["id"], item=finding_id, actor="root-thread")
    subject = next(binding["source"] for binding in work["input_envelope"]["inputs"]
                   if binding["name"] == "subject" and binding["mode"] == "identity"
                   and binding["path"] == [])
    if expected_subject is not None:
        case.assertEqual(expected_subject, subject,
                         "the host must bind the exact subject admitted with this finding revision")
    case.assertEqual(subject, next(binding["source"] for binding in work["lease"]["acquisition"]["inputs"]
                                   if binding["name"] == "subject"))
    value = {"admission": admission, "finding": finding, "subjects": [subject],
        "reviewer_result": case.result(observation["template"]["id"], item=finding_id)[0],
        "authority": case.result(context["template"]["id"], item=finding_id)[0],
        "applicability": classification, "rationale": "Exact revision independently inspected"}
    case.assertEqual([subject], value["subjects"])
    return work, next(iter(assessment["template"]["outputs"])), value


def two_target_graph():
    graph = dag.correction_graph()
    names = {node["id"]: node["id"] + "_b" for node in graph["nodes"]}
    def rename(value):
        if isinstance(value, dict):
            return {key: (names.get(item, item) if key == "node" and isinstance(item, str) else rename(item))
                    for key, item in value.items()}
        if isinstance(value, list):
            return [rename(item) for item in value]
        return value
    cloned = rename(copy.deepcopy(graph))
    for node in cloned["nodes"]:
        node["id"] = names.get(node["id"].removesuffix("_b"), node["id"])
    graph["nodes"].extend(cloned["nodes"])
    graph["terminals"].extend(cloned["terminals"])
    return graph


class GraphNormalizationPublicTests(dag.DagFixture):
    """Fixed-policy execution and retired graph-transaction compatibility."""

    def payload_state(self):
        envelope, payload = self.payload()
        return envelope, payload, self.read_blob(payload["graph"])

    def normalization_receipts(self):
        return [self.read_blob(row["result"])
                for row in self.payload()[1]["operational"]["receipts"]
                if self.read_blob(row["result"]).get("type") == "graph_normalization"]

    def rewrite_payload(self, change):
        envelope, payload = self.payload()
        payload = copy.deepcopy(payload); change(payload)
        envelope = copy.deepcopy(envelope); envelope["payload"] = self.blob(payload); envelope["revision"] += 1
        self.provider.issues[100]["body"] = "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"

    def seed_committed_normalization(self):
        request = {"operation": "graph_normalize", "repository": "owner/repo", "goal": 100,
                   "root": "root-thread", "request_id": "historic-normalization-committed",
                   "source": self.payload()[0]["payload"], "compiler_version": "historic-v1",
                   "target_hash": "sha256:" + "a" * 64, "delta_hash": "sha256:" + "b" * 64}
        result = {"type": "graph_normalization", "content": {"request": copy.deepcopy(request),
                  "target_hash": request["target_hash"], "routes": []},
                  "next_steps": [{"kind": "checkpoint", "goal": 100}]}
        result_ref = self.blob(result)
        def add(payload):
            payload["operational"]["receipts"].append({
                "request": request["request_id"], "payload": dag.content_hash(request), "result": result_ref})
        self.rewrite_payload(add)
        return request, result

    def test_current_policy_graph_is_the_only_execution_topology(self):
        historical_ref = copy.deepcopy(self.payload()[1]["graph"])
        historical = self.read_blob(historical_ref)
        policy_graph = copy.deepcopy(self.graph)
        extra = dag.task("policy_only", ["produce"], role="root")
        extra["inputs"] = {"subject": dag.subject_input("produce")}
        policy_graph["nodes"].append(extra); policy_graph["terminals"] = [dag.selector("policy_only")]
        dag.z._workflow_section(self.session.project, "workflow_adherence")["configuration"]["phase_dag"] = policy_graph
        snapshot = dag.z.workflow_engine(self.fixture.repo, self.session.project, self.session.runtime).node_snapshot(100)
        self.assertIn("policy_only", {node["id"] for node in snapshot["graph"]["nodes"]})
        self.assertEqual(historical_ref, self.payload()[1]["graph"])
        self.assertEqual(historical, self.read_blob(self.payload()[1]["graph"]))
        self.assertEqual([], self.normalization_receipts())

    def test_checkpoint_never_normalizes_or_adopts_historical_graph(self):
        before = copy.deepcopy((self.provider.issues, self.provider.comments, self.payload()[1]["graph"]))
        steps = self.session.checkpoint(100)
        self.assertFalse(any(step.get("kind") in {"graph_normalize", "graph_adopt"} for step in steps))
        self.assertEqual(before, (self.provider.issues, self.provider.comments, self.payload()[1]["graph"]))

    def test_new_retired_graph_operations_reject_without_provider_writes(self):
        for operation in ("graph_prepare", "graph_review", "graph_adopt", "graph_review_bootstrap", "graph_normalize"):
            with self.subTest(operation=operation):
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, {"operation": operation,
                    "request_id": "new-retired-" + operation}, expected=2)
                self.assertRegex(json.dumps(response), r"(?i)policy|retired|reconcil|history")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_exact_committed_normalization_receipt_replays_without_writes(self):
        request, expected = self.seed_committed_normalization()
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, request)
        self.assertEqual(expected, {key: response[key] for key in expected})
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertEqual(1, len(self.normalization_receipts()))

    def test_committed_receipt_payload_conflict_rejects_without_writes(self):
        request, _expected = self.seed_committed_normalization()
        request["target_hash"] = "sha256:" + "f" * 64
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)conflict|payload|receipt")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_uncommitted_historical_request_becomes_explicit_reconciliation_debt(self):
        request = {"operation": "graph_normalize", "request_id": "historic-interrupted",
                   "goal": 100, "repository": "owner/repo", "target_hash": "sha256:" + "a" * 64}
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)interrupted|checkpoint reconciliation|frozen|history")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_unsupported_policy_graph_fails_without_falling_back_to_history(self):
        graph = unsupported_member_retirement_graph()
        self.install(graph)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.checkpoint(100)
        self.assertRegex(json.dumps(response), r"(?i)unsupported|member|policy")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertEqual(graph, self.payload_state()[2])

    def test_snapshot_canonicalization_is_idempotent_and_preserves_payload_graph(self):
        historical = copy.deepcopy(self.payload_state()[2])
        snapshot = dag.z.workflow_engine(self.fixture.repo, self.session.project, self.session.runtime).node_snapshot(100)
        canonical = dag.z._static_workflow.canonical(snapshot["graph"], dag.z._graph_compiler)
        self.assertEqual(snapshot["graph"], canonical)
        self.assertEqual(historical, self.payload_state()[2])

    def test_foreign_and_malformed_host_selection_bindings_reject_without_writes(self):
        compiled = dag.z._graph_compiler.compile_graph(dag.correction_graph(), local_goal=100)["graph"]
        families = [row for row in compiled["task_sets"]
                    if row["source"].get("producer") == {"slot": "obligation_selections"}]
        self.assertTrue(families)
        for path in ([999, "value"], [{"foreign_goal": 999}, "value"]):
            graph = copy.deepcopy(compiled)
            next(row for row in graph["task_sets"] if row["id"] == families[0]["id"])["source"]["path"] = path
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            self.install(graph)
            response = self.session.checkpoint(100)
            self.assertRegex(json.dumps(response), r"(?i)foreign|selection|target|path|contract|malform|unsupported")
            self.assertEqual([], self.normalization_receipts())
            # Installation is fixture setup; public checkpoint itself performs no write.
            after_install = copy.deepcopy((self.provider.issues, self.provider.comments))
            self.session.checkpoint(100)
            self.assertEqual(after_install, (self.provider.issues, self.provider.comments))


class CompiledConfiguredMemberApplicabilityTests(member.RepeatedConfiguredMemberCorrectionTests):
    def setUp(self):
        super().setUp()
        compiler = getattr(dag.z, "_graph_compiler", None)
        self.assertIsNotNone(compiler, "graph compiler service is not registered")
        self.install(compiler.compile_graph(self.shipped, local_goal=100)["graph"])

    def test_persisted_legacy_member_route_is_shadowed_before_repeated_correction(self):
        historical = copy.deepcopy(self.payload()[1]["graph"])
        snapshot = dag.z.workflow_engine(self.fixture.repo, self.session.project,
            self.session.runtime).node_snapshot(100)
        self.assertEqual(snapshot["graph"], dag.z._static_workflow.canonical(
            snapshot["graph"], dag.z._graph_compiler))
        self.assertEqual(historical, self.payload()[1]["graph"])

    def test_member_origin_reclassification_after_atomic_same_id_revision(self):
        self.requirements()
        _specification, allocation = self.specification({"data_residency": "configured risk"})
        subject_a = self.produced("spec")
        first = self.reject_and_interpret(1, None)
        admission = self.admission(first); admission["applicability"] = "unresolved"
        self.session.finish(self.session.acquire("admit_spec_review_correction", item="data_residency"),
                            {"value": admission, "transfer": None})
        identity = "data-residency-region"
        family_ids = [row["id"] for row in compiled_family(self, "spec")]
        work, slot, old = prepare_compiled_assessment(self, "spec", identity,
            self.produced("admit_spec_review_correction", item="data_residency"), first, "applicable",
            subject_a)
        self.session.finish(work, {slot: old})
        old_result = self.result(compiled_family(self, "spec")[2]["template"]["id"], item=identity)[0]
        self.assertFalse(any(step["node"]["node"] == compiled_family(self, "spec")[2]["template"]["id"]
                             and step["node"].get("item") == identity for step in self.session.ready()))
        self.corrected_specification(allocation, 2)
        subject_b = self.produced("spec")
        self.assertNotEqual(subject_a, subject_b)
        second = self.reject_and_interpret(2, first)
        revised = self.admission(second); revised["applicability"] = "unresolved"
        authority = revised["authority"]
        self.session.finish(self.session.acquire("admit_spec_review_correction", item="data_residency"),
            {"value": revised, "transfer": {"prior": first, "replacement": second,
             "coverage": "carried", "coverage_evidence": authority, "authority": authority}})
        self.assertEqual(family_ids, [row["id"] for row in compiled_family(self, "spec")])
        self.assertEqual([subject_b], self.read_blob(second)["content"]["subjects"])
        projection = dag.z.workflow_engine(self.fixture.repo, self.session.project,
            self.session.runtime).node_snapshot(100)["projection"]
        current_outputs = [ref for _key, (_result_ref, result) in projection["current"].items()
                           for ref in result["outputs"].values()]
        self.assertNotIn(subject_a, current_outputs)
        self.assertNotIn(subject_b, current_outputs)
        work2, slot2, fresh = prepare_compiled_assessment(self, "spec", identity,
            self.produced("admit_spec_review_correction", item="data_residency"), second, "not_applicable",
            subject_b)
        wrong_subject = copy.deepcopy(fresh); wrong_subject["subjects"] = [subject_a]
        same_executor = copy.deepcopy(fresh); same_executor["reviewer_result"] = fresh["authority"]
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, self.session.submission(work2, {slot2: wrong_subject},
            "reject-wrong-historical-subject"), expected=2)
        self.session.call(100, self.session.submission(work2, {slot2: same_executor},
            "reject-root-as-independent-reviewer"), expected=2)
        self.session.call(100, self.session.submission(work2, {slot2: old}, "reject-old-revision"), expected=2)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(work2, {slot2: fresh})
        projection = dag.z.workflow_engine(self.fixture.repo, self.session.project,
            self.session.runtime).node_snapshot(100)["projection"]
        obligation = projection["obligations"][(100, identity)]
        self.assertEqual(second, obligation["finding"])
        self.assertEqual("not_applicable", obligation["applicability"])
        self.assertIn(old_result, self.payload()[1]["evidence"])
        self.assertEqual(1, self.read_blob(first)["content"]["revision"])
        self.assertEqual(2, self.read_blob(second)["content"]["revision"])
        self.corrected_specification(allocation, 3)
        subject_c = self.produced("spec")
        self.assertNotIn(subject_c, (subject_a, subject_b))
        projection = dag.z.workflow_engine(self.fixture.repo, self.session.project,
            self.session.runtime).node_snapshot(100)["projection"]
        current_outputs = [ref for _key, (_result_ref, result) in projection["current"].items()
                           for ref in result["outputs"].values()]
        self.assertIn(subject_c, current_outputs)
        self.assertNotIn(subject_a, current_outputs)
        self.assertNotIn(subject_b, current_outputs)

_REAL_TRANSPORT_ADAPTER = dag.z.GitHubGoalTransitionAdapter


class GraphNormalizationTransportTests(dag.DagFixture):
    """Provider boundary remains read-only for retired graph operations."""
    rewrite_payload = GraphNormalizationPublicTests.rewrite_payload
    seed_committed_normalization = GraphNormalizationPublicTests.seed_committed_normalization

    def setUp(self):
        super().setUp()
        self.writes = []
        append, update = self.provider.create_issue_comment, self.provider.update_issue
        def observe_append(*args, **kwargs):
            self.writes.append("comment")
            return append(*args, **kwargs)
        def observe_update(*args, **kwargs):
            self.writes.append("body")
            return update(*args, **kwargs)
        self.provider.create_issue_comment = observe_append
        self.provider.update_issue = observe_update

    def test_committed_replay_does_not_touch_provider_transport(self):
        request, expected = self.seed_committed_normalization()
        self.writes.clear()
        response = self.session.call(100, request)
        self.assertEqual(expected, {key: response[key] for key in expected})
        self.assertEqual([], self.writes)

    def test_conflicting_committed_replay_does_not_touch_provider_transport(self):
        request, _expected = self.seed_committed_normalization()
        self.writes.clear(); request["delta_hash"] = "sha256:" + "e" * 64
        self.session.call(100, request, expected=2)
        self.assertEqual([], self.writes)

    def test_interrupted_retired_request_does_not_touch_provider_transport(self):
        self.writes.clear()
        response = self.session.call(100, {"operation": "graph_normalize",
            "request_id": "historic-interrupted", "goal": 100}, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)checkpoint reconciliation|interrupted")
        self.assertEqual([], self.writes)


if __name__ == "__main__":
    unittest.main()
