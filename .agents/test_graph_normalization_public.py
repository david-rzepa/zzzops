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


def prepare_compiled_assessment(case, target, finding_id, admission, finding, classification):
    observation, context, assessment = compiled_family(case, target)
    for row, actor, text in ((observation, "independent-applicability", "Inspected exact obligation"),
                             (context, "root-thread", "Root bounded classification context")):
        work = case.session.acquire(row["template"]["id"], item=finding_id, actor=actor)
        case.session.finish(work, {next(iter(row["template"]["outputs"])): text})
    work = case.session.acquire(assessment["template"]["id"], item=finding_id, actor="root-thread")
    subject = next(binding["source"] for binding in work["input_envelope"]["inputs"]
                   if binding["name"] == "subject" and binding["mode"] == "identity"
                   and binding["path"] == [])
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
    def setUp(self):
        super().setUp()
        graph = copy.deepcopy(self.graph)
        review = next(node for node in graph["nodes"] if node["id"] == "review_a")
        review["outputs"] = {"value": dag.output("review_decision", {"kind": "object", "fields": {
            "decision": {"kind": "enum", "values": ["approved", "changes_requested"]},
            "report": {"kind": "string"}}})}
        self.install(graph)

    def arrange_historical_incomplete(self, *, settle_result=False, acquire=False):
        compiler = getattr(dag.z, "_graph_compiler", None)
        self.assertIsNotNone(compiler, "graph compiler service is not registered")
        incomplete = copy.deepcopy(self.graph)
        complete = compiler.compile_graph(incomplete, local_goal=100)["graph"]
        self.install(complete)
        if settle_result:
            self.produce()
        lease = self.session.acquire("produce") if acquire else None
        envelope, payload = self.payload()[:2]
        payload = copy.deepcopy(payload)
        payload["graph"] = self.blob(incomplete)
        envelope = copy.deepcopy(envelope)
        envelope["payload"] = self.blob(payload)
        envelope["revision"] += 1
        self.provider.issues[100]["body"] = "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"
        return lease

    def rewrite_payload(self, change):
        envelope, payload = self.payload()
        payload = copy.deepcopy(payload)
        change(payload)
        envelope = copy.deepcopy(envelope)
        envelope["payload"] = self.blob(payload)
        envelope["revision"] += 1
        self.provider.issues[100]["body"] = "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"

    def replace_with_incomplete_graph(self):
        incomplete = copy.deepcopy(self.graph)
        self.rewrite_payload(lambda payload: payload.update(graph=self.blob(incomplete)))

    def payload_state(self):
        envelope, payload = self.payload()
        return envelope, payload, self.read_blob(payload["graph"])

    def normalization_receipts(self):
        _envelope, payload, _graph = self.payload_state()
        receipts = []
        for row in payload["operational"]["receipts"]:
            self.assertEqual({"request", "payload", "result"}, set(row))
            item = self.read_blob(row["result"])
            if item.get("type") == "graph_normalization":
                receipts.append(item)
        return receipts

    def normalize_once(self):
        response = self.session.checkpoint(100)
        receipts = self.normalization_receipts()
        self.assertEqual(1, len(receipts), "eligible checkpoint must apply one guarded normalization")
        return response, receipts[0]

    def broad_checkpoint(self):
        main = dag.z.main
        def without_goal():
            args = list(sys.argv); offset = args.index("--goal"); del args[offset:offset + 2]
            with mock.patch.object(sys, "argv", args):
                return main()
        with mock.patch.object(dag.z, "main", side_effect=without_goal):
            return self.session.call(100)

    def assert_unconfirmed_did_not_advance(self, response, before_evidence, before_leases):
        encoded = json.dumps(response)
        self.assertNotRegex(encoded, r'"kind"\s*:\s*"execute"')
        self.assertNotRegex(encoded, r'"kind"\s*:\s*"complete"')
        self.assertNotRegex(encoded, r'(?i)ci.waiv|authorize.merge|workspace.authoriz')
        self.assertEqual(before_evidence, self.payload()[1]["evidence"])
        self.assertEqual(before_leases, self.payload()[1]["operational"]["leases"])

    def assert_confirmed_readback_did_not_manufacture_work(self, response,
                                                            before_evidence, before_leases):
        encoded = json.dumps(response)
        self.assertNotRegex(encoded, r'"kind"\s*:\s*"complete"')
        self.assertNotRegex(encoded, r'(?i)ci.waiv|authorize.merge|workspace.authoriz')
        self.assertEqual(before_evidence, self.payload()[1]["evidence"])
        self.assertEqual(before_leases, self.payload()[1]["operational"]["leases"])

    def replay_request(self, receipt):
        request = copy.deepcopy(receipt["content"]["request"])
        self.assertEqual("graph_normalize", request["operation"])
        return request

    def pending_normalization_requests(self, comments):
        values = []
        for comment in comments:
            envelope = dag.z._comment_store.decode_envelope(comment["body"])
            for record in (envelope or {}).get("artifacts", []):
                if record.get("type") == "json" and isinstance(record.get("text"), str):
                    values.append(json.loads(record["text"]))
                elif "content" in record:
                    values.append(record["content"])
        requests = []
        def visit(value):
            if isinstance(value, dict):
                if value.get("operation") == "graph_normalize" and value.get("request_id"):
                    requests.append(copy.deepcopy(value))
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        for value in values:
            visit(value)
        return requests

    def test_selected_incomplete_goal_normalizes_once_and_preserves_exact_history(self):
        self.arrange_historical_incomplete(settle_result=True)
        before_envelope, before_payload, before_graph = self.payload_state()
        before_evidence = copy.deepcopy(before_payload["evidence"])
        before_receipts = copy.deepcopy(before_payload["operational"]["receipts"])
        before_current = copy.deepcopy(
            dag.z.workflow_engine(self.fixture.repo, self.session.project,
                                  self.session.runtime).node_snapshot(100)["projection"]["current"])
        self.assertTrue(before_current, "historical fixture must contain real settled host Results")
        response, _receipt = self.normalize_once()
        after_envelope, after_payload, after_graph = self.payload_state()
        self.assertEqual(before_graph["nodes"], after_graph["nodes"][:len(before_graph["nodes"])])
        self.assertEqual(before_graph["task_sets"], after_graph["task_sets"][:len(before_graph["task_sets"])])
        self.assertEqual(before_graph["terminals"], after_graph["terminals"])
        self.assertEqual(before_evidence, after_payload["evidence"][:len(before_evidence)])
        self.assertEqual(before_receipts,
                         after_payload["operational"]["receipts"][:len(before_receipts)])
        after_current = dag.z.workflow_engine(self.fixture.repo, self.session.project,
            self.session.runtime).node_snapshot(100)["projection"]["current"]
        self.assertEqual(before_current, after_current)
        self.assertGreater(after_envelope["revision"], before_envelope["revision"])
        self.assertNotRegex(json.dumps(response), r"(?i)review_graph|graph_adopt")
        second = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.checkpoint(100)
        self.assertEqual(second, (self.provider.issues, self.provider.comments))

    def test_preview_historical_closed_and_snapshot_reads_never_normalize(self):
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        engine = dag.z.workflow_engine(self.fixture.repo, self.session.project, self.session.runtime)
        engine.node_snapshot(100)
        self.session.read(100, self.envelope["payload"])
        self.session.call(100, intent="preview")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.provider.issues[100]["state"] = "closed"
        closed = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.checkpoint(100)
        self.assertEqual(closed, (self.provider.issues, self.provider.comments))
        self.provider.issues[100]["state"] = "open"
        envelope, _payload = self.payload()
        envelope["state"] = "closed"
        self.provider.issues[100]["body"] = "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"
        envelope_closed = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.checkpoint(100)
        self.assertEqual(envelope_closed, (self.provider.issues, self.provider.comments))

    def test_tampered_normalization_request_rejects_without_writes(self):
        _response, receipt = self.normalize_once()
        request = self.replay_request(receipt)
        mutations = (
            {"target_hash": "sha256:" + "f" * 64},
            {"delta_hash": "sha256:" + "e" * 64},
            {"compiler_version": "caller-selected"},
            {"request_id": "changed-request"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                bad = {**request, **mutation}
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, bad, expected=2)
                self.assertRegex(json.dumps(response), r"(?i)target|delta|compiler|request|exact|current")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_rejection_order_and_output_slot_do_not_change_routes_or_target(self):
        def journey(order):
            case = dag.DagFixture(); case.setUp()
            self.addCleanup(case.doCleanups)
            graph = copy.deepcopy(case.graph)
            producer = next(node for node in graph["nodes"] if node["id"] == "produce")
            producer["outputs"]["alternate"] = dag.output("text", {"kind": "string"})
            for name in ("review_a", "review_b"):
                review = next(node for node in graph["nodes"] if node["id"] == name)
                review["outputs"] = {"value": dag.output("review_decision", {"kind": "object", "fields": {
                    "decision": {"kind": "enum", "values": ["approved", "changes_requested"]},
                    "report": {"kind": "string"}}})}
            next(node for node in graph["nodes"] if node["id"] == "review_b")["inputs"]["subject"]["output"] = "alternate"
            compiler = dag.z._graph_compiler
            complete = compiler.compile_graph(graph, local_goal=100)["graph"]
            case.install(complete)
            case.session.finish(case.session.acquire("produce"), {"value": "primary", "alternate": "secondary"})
            for name in order:
                case.session.finish(case.session.acquire(name, actor="independent-" + name), {"value": {
                    "decision": "changes_requested", "report": "Exact slot rejected"}})
            envelope, payload = case.payload(); payload = copy.deepcopy(payload); payload["graph"] = case.blob(graph)
            envelope = copy.deepcopy(envelope); envelope["payload"] = case.blob(payload); envelope["revision"] += 1
            case.provider.issues[100]["body"] = "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"
            case.session.checkpoint(100)
            final_graph = case.read_blob(case.payload()[1]["graph"])
            receipt = [case.read_blob(row["result"]) for row in case.payload()[1]["operational"]["receipts"]
                       if case.read_blob(row["result"]).get("type") == "graph_normalization"][-1]
            return final_graph, receipt["content"]["routes"], receipt["content"]["target_hash"]
        first = journey(("review_a", "review_b")); second = journey(("review_b", "review_a"))
        self.assertEqual(first, second)

    def test_broad_checkpoint_normalizes_only_selected_incomplete_goal(self):
        self.provider.issues[101] = copy.deepcopy(self.provider.issues[100])
        self.provider.issues[101]["number"] = 101
        self.provider.comments[101] = copy.deepcopy(self.provider.comments[100])
        envelope = dag.z.parse_managed_goal(self.provider.issues[101]["body"], 100)
        envelope["issue"] = 101
        prefix = self.provider.issues[101]["body"].split("<!-- zzzops-goal", 1)[0]
        self.provider.issues[101]["body"] = prefix + "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"
        untouched = copy.deepcopy((self.provider.issues[101], self.provider.comments[101]))
        selected_before = copy.deepcopy((self.provider.issues[100], self.provider.comments[100]))
        self.broad_checkpoint()
        self.assertNotEqual(selected_before, (self.provider.issues[100], self.provider.comments[100]),
                            "broad checkpoint did not normalize the selected candidate")
        self.assertEqual(untouched, (self.provider.issues[101], self.provider.comments[101]))

    def test_arbitrary_graph_adoption_still_requires_review_and_approval(self):
        dag.run_generic_regressions(self,
            "test_evidence_dag_journeys.GraphAdoptionPublicTests.test_direct_review_is_durable_independent_authority_free_and_replayable",
            "test_evidence_dag_journeys.GraphAdoptionPublicTests.test_reviewed_goal_only_adoption_preserves_results_history_and_receipt",
            "test_evidence_dag_journeys.GraphAdoptionPublicTests.test_graph_review_bootstrap_requires_explicit_approval")
        _response, receipt = self.normalize_once()
        request = self.replay_request(receipt)
        self.assertNotIn("graph_adopt", request)
        self.assertNotIn("approved_by", request)

    def test_live_owner_defers_normalization(self):
        acquired = self.arrange_historical_incomplete(acquire=True)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.checkpoint(100)
        self.assertRegex(json.dumps(response), r"(?i)lease|owner|resume|pending")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertTrue(acquired["lease"]["token"])

    def test_expired_but_unrecovered_owner_still_defers_normalization(self):
        self.arrange_historical_incomplete(acquire=True)
        def expire(payload):
            self.assertEqual(1, len(payload["operational"]["leases"]))
            payload["operational"]["leases"][0]["expires_at"] = 1
        self.rewrite_payload(expire)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.checkpoint(100)
        self.assertRegex(json.dumps(response), r"(?i)expired|recover|owner|lease")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_unresolved_pending_checkpoint_defers_normalization(self):
        compiler = getattr(dag.z, "_graph_compiler", None)
        self.assertIsNotNone(compiler, "graph compiler service is not registered")
        incomplete = copy.deepcopy(self.graph)
        compiled = compiler.compile_graph(incomplete, local_goal=100)["graph"]
        self.assertNotEqual(dag.content_hash(incomplete), dag.content_hash(compiled))
        with self.assertRaisesRegex(Exception, r"(?i)recover|incomplete|addition"):
            compiler.validate_recovery(incomplete, local_goal=100)
        self.install(compiled)
        step = next(item for item in self.session.ready() if item["node"]["node"] == "produce")
        receipt = json.loads(dag.Path(step["policy"]["path"]).read_text())["policy_receipt"]
        request = {**step["start"], "policy_receipt": receipt, "request_id": "pending-before-body"}
        with mock.patch.object(self.provider, "update_issue", side_effect=RuntimeError("provider unavailable")):
            self.session.call(100, request, expected=2)
        self.rewrite_payload(lambda payload: payload.update(graph=self.blob(incomplete)))
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.checkpoint(100)
        self.assertRegex(json.dumps(response), r"(?i)pending|reconcil|checkpoint|uncertain")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_stale_source_policy_or_current_projection_cannot_commit(self):
        self.arrange_historical_incomplete(settle_result=True)
        _response, receipt = self.normalize_once()
        request = self.replay_request(receipt)
        self.assertTrue(request["current"],
                        "authenticated request must contain a real settled current Result map")
        variants = []
        stale_source = copy.deepcopy(request); stale_source["source"] = {"hash": "sha256:" + "a" * 64, "uri": "urn:sha256:" + "a" * 64}; variants.append(stale_source)
        stale_policy = copy.deepcopy(request); stale_policy["policy"] = "sha256:" + "b" * 64; variants.append(stale_policy)
        stale_current = copy.deepcopy(request)
        stale_current["current"] = ([] if isinstance(request["current"], dict) else {})
        self.assertNotEqual(request["current"], stale_current["current"])
        variants.append(stale_current)
        for request in variants:
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            response = self.session.call(100, request, expected=2)
            self.assertRegex(json.dumps(response), r"(?i)stale|source|policy|current|exact")
            self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_nonzero_current_result_invalidation_is_never_normalized(self):
        self.arrange_historical_incomplete(settle_result=True)
        compiler = dag.z._graph_compiler
        source = self.payload_state()[2]
        prospective = compiler.compile_graph(source, local_goal=100)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        workflow = dag.z._workflow.Workflow
        original_snapshot = workflow.node_snapshot
        def drop_projected_current(engine, number, *args, **kwargs):
            snapshot = original_snapshot(engine, number, *args, **kwargs)
            if kwargs.get("graph_override") is not None:
                snapshot["projection"]["current"] = {}
            return snapshot
        with mock.patch.object(compiler, "compile_graph", return_value=prospective), \
                mock.patch.object(workflow, "node_snapshot", drop_projected_current):
            response = self.session.checkpoint(100)
        self.assertRegex(json.dumps(response), r"(?i)invalidat|current|settled|preserv")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_lost_response_exact_retry_commits_one_receipt_and_one_extension(self):
        baseline = len(self.normalization_receipts())
        before_evidence = copy.deepcopy(self.payload()[1]["evidence"])
        before_leases = copy.deepcopy(self.payload()[1]["operational"]["leases"])
        original = self.provider.update_issue
        calls = {"count": 0}
        def lost_once(*args, **kwargs):
            value = original(*args, **kwargs)
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("lost response after commit")
            return value
        with mock.patch.object(self.provider, "update_issue", side_effect=lost_once):
            confirmed = self.session.checkpoint(100)
        self.assert_confirmed_readback_did_not_manufacture_work(
            {"next_steps": confirmed}, before_evidence, before_leases)
        self.assertEqual(baseline + 1, len(self.normalization_receipts()),
                         "exact committed readback records one normalization receipt")
        self.session.checkpoint(100)
        _envelope, payload, graph = self.payload_state()
        receipts = [self.read_blob(row["result"]) for row in payload["operational"]["receipts"]]
        normalizations = [item for item in receipts if item.get("type") == "graph_normalization"]
        self.assertEqual(baseline + 1, len(normalizations))
        self.assertEqual(normalizations[-1]["content"]["target_hash"], dag.content_hash(graph))
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.checkpoint(100)
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))

    def test_direct_pending_retry_requires_fresh_durable_provider_confirmation(self):
        baseline = len(self.normalization_receipts())
        before_payload = copy.deepcopy(self.payload()[1])
        before_comments = len(self.provider.comments[100])
        append = self.provider.create_issue_comment
        calls = {"count": 0}
        def interrupt(*args, **kwargs):
            value = append(*args, **kwargs)
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("pending normalization artifact response lost")
            return value
        with mock.patch.object(self.provider, "create_issue_comment", side_effect=interrupt):
            self.session.checkpoint(100)
        requests = self.pending_normalization_requests(
            self.provider.comments[100][before_comments:])
        self.assertEqual(1, len(requests), "host must publish one exact pending normalization request")
        request = requests[0]
        pending_state = copy.deepcopy((self.provider.issues, self.provider.comments))
        durable_issue = copy.deepcopy(self.provider.issues[100])
        def acknowledge_without_durability(number, payload):
            acknowledged = copy.deepcopy(self.provider.issues[number])
            acknowledged.update(copy.deepcopy(payload))
            return acknowledged
        with mock.patch.object(self.provider, "update_issue", side_effect=acknowledge_without_durability):
            unconfirmed = self.session.call(100, request, expected=2)
        self.assertNotRegex(json.dumps(unconfirmed), r'(?i)"kind"\s*:\s*"execute"|"kind"\s*:\s*"complete"|normalization.applied')
        self.assertEqual(durable_issue, self.provider.issues[100])
        self.assertEqual(pending_state, (self.provider.issues, self.provider.comments))
        pending_payload = self.payload()[1]
        self.assertEqual(before_payload["evidence"], pending_payload["evidence"])
        self.assertEqual(before_payload["operational"]["leases"],
                         pending_payload["operational"]["leases"])
        self.assertEqual(baseline, len(self.normalization_receipts()))

        self.session.call(100, request)
        receipts = self.normalization_receipts()
        self.assertEqual(baseline + 1, len(receipts))
        self.assertEqual(request["target_hash"], receipts[-1]["content"]["target_hash"])
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, request)
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))

    def test_interruption_after_artifact_publication_retries_exactly_once(self):
        baseline = len(self.normalization_receipts())
        before_evidence = copy.deepcopy(self.payload()[1]["evidence"])
        before_leases = copy.deepcopy(self.payload()[1]["operational"]["leases"])
        append = self.provider.create_issue_comment
        comments = self.provider.get_issue_comments
        calls = {"count": 0}
        confirmation_unavailable = {"value": False}
        def lost_artifact(*args, **kwargs):
            value = append(*args, **kwargs)
            calls["count"] += 1
            if calls["count"] == 1:
                confirmation_unavailable["value"] = True
                raise OSError("lost artifact publication response")
            return value
        def unavailable_comments(*args, **kwargs):
            if confirmation_unavailable["value"]:
                raise OSError("normalization confirmation unavailable")
            return comments(*args, **kwargs)
        with mock.patch.object(self.provider, "create_issue_comment", side_effect=lost_artifact), \
                mock.patch.object(self.provider, "get_issue_comments", side_effect=unavailable_comments):
            uncertain = self.session.checkpoint(100)
        self.assert_unconfirmed_did_not_advance(
            {"next_steps": uncertain}, before_evidence, before_leases)
        self.session.checkpoint(100)
        self.assertEqual(baseline + 1, len(self.normalization_receipts()))
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.checkpoint(100)
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))

    def test_pending_normalization_never_switches_compiler_version(self):
        compiler = dag.z._graph_compiler
        append = self.provider.create_issue_comment
        calls = {"count": 0}
        historic = "historic-normalizer-version"
        historic_calls = []
        compile_graph = compiler.compile_graph
        before_comments = len(self.provider.comments[100])
        def versioned_compile(graph, local_goal=None, compiler_version=None):
            historic_calls.append(compiler_version)
            return compile_graph(graph, local_goal=local_goal,
                                 compiler_version=compiler_version)
        def interrupt(*args, **kwargs):
            value = append(*args, **kwargs)
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("interrupt versioned normalization")
            return value
        with mock.patch.object(compiler, "SUPPORTED_VERSION", historic), \
                mock.patch.object(compiler, "compile_graph", side_effect=versioned_compile), \
                mock.patch.object(self.provider, "create_issue_comment", side_effect=interrupt):
            self.session.checkpoint(100)
        self.assertIn(historic, historic_calls,
                      "dispatcher must pass the installed compiler version explicitly")
        published = self.provider.comments[100][before_comments:]
        self.assertTrue(published, "interruption must leave a readable pending artifact")
        envelopes = [dag.z._comment_store.decode_envelope(comment["body"])
                     for comment in published]
        artifacts = []
        for envelope in envelopes:
            for record in (envelope or {}).get("artifacts", []):
                if not isinstance(record, dict):
                    continue
                if "content" in record:
                    artifacts.append(record["content"])
                elif record.get("type") == "json" and isinstance(record.get("text"), str):
                    artifacts.append(json.loads(record["text"]))
        def mappings(value):
            if isinstance(value, dict):
                yield value
                for child in value.values():
                    yield from mappings(child)
            elif isinstance(value, list):
                for child in value:
                    yield from mappings(child)
        pending = [row for artifact in artifacts for row in mappings(artifact)
                   if row.get("compiler_version") == historic
                   and row.get("request_id") and row.get("target_hash")]
        self.assertEqual(1, len(pending),
                         "published pending artifact must bind version, request, and target")
        historic_request = pending[0]["request_id"]
        historic_target = pending[0]["target_hash"]
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.checkpoint(100)
        self.assertRegex(json.dumps(response), r"(?i)compiler|version|pending|exact|defer")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertEqual(historic_request, pending[0]["request_id"])
        self.assertEqual(historic_target, pending[0]["target_hash"])

    def test_compiled_applicability_family_exposes_exact_ordinary_work(self):
        findings, admissions = self.findings(applicability="unresolved")
        steps = self.session.checkpoint(100)
        self.assertNotRegex(json.dumps(steps), r"(?i)review_graph|graph_adopt")
        _envelope, _payload, graph = self.payload_state()
        families = [item for item in graph["task_sets"]
                    if item["source"].get("producer", {}).get("slot") == "obligation_selections"]
        self.assertEqual(3, len(families))
        assessment = next(item for item in families if any(
            output.get("type") == "applicability_assessment"
            for output in item["template"]["outputs"].values()))
        observation = next(item for item in families
                           if item["template"]["executor"]["role"] == "worker")
        context = next(item for item in families if item not in (assessment, observation))
        finding_id = "first"
        observation_work = self.session.acquire(observation["template"]["id"], item=finding_id,
                                                actor="independent-applicability-reviewer")
        observation_slot = next(iter(observation["template"]["outputs"]))
        self.session.finish(observation_work, {observation_slot: "Observed exact current subject and obligation."})
        context_work = self.session.acquire(context["template"]["id"], item=finding_id)
        context_slot = next(iter(context["template"]["outputs"]))
        self.session.finish(context_work, {context_slot: "Root supplied bounded classification context."})
        assessment_work = self.session.acquire(assessment["template"]["id"], item=finding_id,
                                               actor="root-thread")
        assessment_slot = next(iter(assessment["template"]["outputs"]))
        value = {"admission": self.produced("admit", finding_id),
                 "finding": admissions[finding_id]["finding"],
                 "subjects": [self.produced("produce")],
                 "reviewer_result": self.result(observation["template"]["id"], item=finding_id)[0],
                 "authority": self.result(context["template"]["id"], item=finding_id)[0],
                 "applicability": getattr(self, "classification", "not_applicable"),
                 "rationale": "Exact finding received an explicit bounded classification."}
        wrong_values = []
        wrong = copy.deepcopy(value); wrong["reviewer_result"] = wrong["authority"]; wrong_values.append(wrong)
        wrong = copy.deepcopy(value); wrong["authority"] = wrong["reviewer_result"]; wrong_values.append(wrong)
        wrong = copy.deepcopy(value); wrong["finding"] = admissions["second"]["finding"]; wrong_values.append(wrong)
        wrong = copy.deepcopy(value); wrong["admission"] = self.produced("admit", "second"); wrong_values.append(wrong)
        wrong = copy.deepcopy(value); wrong["subjects"] = [self.produced("ingest", "comment")]; wrong_values.append(wrong)
        for index, wrong in enumerate(wrong_values):
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            rejected = self.session.call(100, self.session.submission(
                assessment_work, {assessment_slot: wrong}, f"wrong-applicability-{index}"), expected=2)
            self.assertRegex(json.dumps(rejected), r"(?i)review|authority|finding|admission|subject|input")
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(assessment_work, {assessment_slot: value})
        snapshot = dag.z.workflow_engine(self.fixture.repo, self.session.project,
                                         self.session.runtime).node_snapshot(100)
        self.assertEqual(value["applicability"], snapshot["projection"]["obligations"][(100, "first")]["applicability"])
        self.assertEqual("unresolved", snapshot["projection"]["obligations"][(100, "second")]["applicability"])
        self.assertNotIn("finish", self.names())
        self.assertEqual({"first", "second"}, set(findings))
        self.assertEqual({"first", "second"}, set(admissions))


    def test_applicable_classification_uses_the_same_exact_family_and_preserves_sibling(self):
        self.classification = "applicable"
        self.test_compiled_applicability_family_exposes_exact_ordinary_work()

    def test_applicability_history_revision_and_configured_member_controls_remain_exact(self):
        dag.run_generic_regressions(
            self,
            "test_evidence_dag_journeys.EvidenceDagPublicTests.test_reviewed_applicability_assessment_classifies_exact_historical_obligation",
            "test_evidence_dag_journeys.EvidenceDagPublicTests.test_supersession_carries_obligation_and_only_latest_revision_needs_resolution",
            "test_evidence_dag_journeys.EvidenceDagPublicTests.test_authorized_member_retirement_retains_historical_debt_on_empty_and_reactivation",
        )

    def test_runtime_two_targets_filter_items_and_keep_empty_selection_empty(self):
        graph = two_target_graph()
        first_findings, _first_admissions = self.findings(graph=graph, applicability="unresolved")
        families_a = compiled_family(self, "produce")
        families_b = compiled_family(self, "produce_b")
        observation_a, observation_b = families_a[0], families_b[0]
        ready = self.session.ready()
        self.assertEqual({"first", "second"}, {step["node"]["item"] for step in ready
            if step["node"]["node"] == observation_a["template"]["id"]})
        self.assertEqual(set(), {step["node"]["item"] for step in ready
            if step["node"]["node"] == observation_b["template"]["id"]})
        self.session.finish(self.session.acquire("produce_b"), {"value": "second target"})
        subject = self.produced("produce_b")
        comment = self.provider.create_issue_comment(100, "Second target defects")
        source_value = {**dag.SOURCE_SAMPLE, "id": f"issue_comment_{comment['id']}",
                        "body": comment["body"], "subject": subject}
        self.session.finish(self.session.acquire("ingest_b"), {"comment": source_value})
        source = self.produced("ingest_b", "comment")
        found = {slot: {"id": finding_id, "revision": 1, "source": source, "subjects": [subject],
            "target": dag.scope("produce_b"), "request": "Repair " + finding_id,
            "rationale": "Observed exact second target", "supersedes": None}
            for slot, finding_id in (("first", "third"), ("second", "fourth"))}
        self.session.finish(self.session.acquire("find_b"), found)
        self.session.finish(self.session.acquire("authorize_b"), {"value": "Authorize second target"})
        admissions = {slot: {"finding": self.produced("find_b", slot),
            "target_inputs": self.result("produce_b")[1]["inputs"],
            "authority": self.result("authorize_b")[0], "applicability": "unresolved",
            "rationale": "Exact second target"} for slot in ("first", "second")}
        self.session.finish(self.session.acquire("admit_b"), admissions)
        ready = self.session.ready()
        self.assertEqual({"first", "second"}, {step["node"]["item"] for step in ready
            if step["node"]["node"] == observation_a["template"]["id"]})
        self.assertEqual({"third", "fourth"}, {step["node"]["item"] for step in ready
            if step["node"]["node"] == observation_b["template"]["id"]})
        self.assertEqual({"first", "second"}, set(first_findings))

    def test_foreign_and_malformed_host_selection_bindings_reject_without_writes(self):
        compiler = dag.z._graph_compiler
        compiled = compiler.compile_graph(dag.correction_graph(), local_goal=100)["graph"]
        families = [row for row in compiled["task_sets"]
                    if row["source"].get("producer") == {"slot": "obligation_selections"}]
        self.assertTrue(families)
        for label, path in (("foreign", [999, "value"]),
                            ("malformed", [{"foreign_goal": 999}, "value"])):
            with self.subTest(label=label):
                graph = copy.deepcopy(compiled)
                target = next(row for row in graph["task_sets"]
                              if row["id"] == families[0]["id"])
                target["source"]["path"] = path
                self.install(graph)
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.checkpoint(100)
                self.assertRegex(json.dumps(response), r"(?i)foreign|selection|target|path|contract|malform")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_unsupported_historical_member_graph_retains_frontier_without_normalizing(self):
        graph = unsupported_member_retirement_graph()
        self.install(graph)
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.checkpoint(100)
        encoded = json.dumps(response)
        self.assertRegex(encoded, r'(?i)unsupported|recover|route|graph.prepare|repair')
        self.assertRegex(encoded, r'(?i)select')
        self.assertEqual(graph, self.payload_state()[2])
        self.assertEqual([], self.normalization_receipts())
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.choose({"a": "inspect"})
        self.session.finish(self.session.acquire("investigate", item="a"), {"value": "initial"})
        subject = self.produced("investigate", item="a")
        exact_member = {"kind": "member", "goal": 100, "expansion": "buckets",
                        "item": "a", "generation": 1}
        finding = {"id": "member_flaw", "revision": 1, "source": subject,
            "subjects": [subject], "target": {"subject": exact_member, "output": "value"},
            "request": "Repair missing evidence", "rationale": "Inspection found a gap",
            "supersedes": None}
        self.session.finish(self.session.acquire("member_finding"), {"finding": finding})
        admission = {"finding": self.produced("member_finding", "finding"),
            "target_inputs": self.result("investigate", "a")[1]["inputs"],
            "authority": self.result("select")[0], "applicability": "unresolved",
            "rationale": "Current configured member scope requires classification"}
        work = self.session.acquire("member_admit")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        blocked = self.session.call(100, self.session.submission(
            work, {"admission": admission}, "unresolved-unsupported-member"), expected=2)
        self.assertRegex(json.dumps(blocked), r'(?i)unresolved|represent|recover|route|graph.prepare|repair')
        self.assertEqual([], self.normalization_receipts())
        self.assertEqual(before, (self.provider.issues, self.provider.comments))


class CompiledConfiguredMemberApplicabilityTests(member.RepeatedConfiguredMemberCorrectionTests):
    def setUp(self):
        super().setUp()
        compiler = getattr(dag.z, "_graph_compiler", None)
        self.assertIsNotNone(compiler, "graph compiler service is not registered")
        self.install(compiler.compile_graph(self.shipped, local_goal=100)["graph"])

    def test_member_origin_reclassification_after_atomic_same_id_revision(self):
        self.requirements()
        _specification, allocation = self.specification({"data_residency": "configured risk"})
        first = self.reject_and_interpret(1, None)
        admission = self.admission(first); admission["applicability"] = "unresolved"
        self.session.finish(self.session.acquire("admit_spec_review_correction", item="data_residency"),
                            {"value": admission, "transfer": None})
        identity = "data-residency-region"
        family_ids = [row["id"] for row in compiled_family(self, "spec")]
        work, slot, old = prepare_compiled_assessment(self, "spec", identity,
            self.produced("admit_spec_review_correction", item="data_residency"), first, "applicable")
        self.session.finish(work, {slot: old})
        old_result = self.result(compiled_family(self, "spec")[2]["template"]["id"], item=identity)[0]
        self.assertFalse(any(step["node"]["node"] == compiled_family(self, "spec")[2]["template"]["id"]
                             and step["node"].get("item") == identity for step in self.session.ready()))
        self.corrected_specification(allocation, 2)
        second = self.reject_and_interpret(2, first)
        revised = self.admission(second); revised["applicability"] = "unresolved"
        authority = revised["authority"]
        self.session.finish(self.session.acquire("admit_spec_review_correction", item="data_residency"),
            {"value": revised, "transfer": {"prior": first, "replacement": second,
             "coverage": "carried", "coverage_evidence": authority, "authority": authority}})
        self.assertEqual(family_ids, [row["id"] for row in compiled_family(self, "spec")])
        historical_subject = self.produced("spec")
        work2, slot2, fresh = prepare_compiled_assessment(self, "spec", identity,
            self.produced("admit_spec_review_correction", item="data_residency"), second, "not_applicable")
        self.assertNotEqual([historical_subject], fresh["subjects"],
                            "same-ID revision must not reuse historical enumeration")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
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


if __name__ == "__main__":
    unittest.main()
