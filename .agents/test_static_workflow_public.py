"""Public regressions for the fixed policy workflow and late phase findings."""
from __future__ import annotations

import copy
import json
import os
import unittest
from unittest import mock

import test_evidence_dag_journeys as dag
import test_workflow_publication_contract as publication


class StaticWorkflowPublicTests(dag.DagFixture):
    def set_current_graph(self, graph):
        dag.z._workflow_section(self.session.project, "workflow_adherence")[
            "configuration"]["phase_dag"] = copy.deepcopy(graph)

    def graph_ref(self):
        return self.payload()[1]["graph"]

    def policy_graph_with_added_phase(self):
        graph = copy.deepcopy(self.graph)
        added = dag.task("policy_added", ["produce"], role="root")
        added["inputs"] = {"subject": dag.subject_input("produce")}
        graph["nodes"].append(added)
        graph["terminals"] = [dag.selector("policy_added")]
        return graph

    def public_steps(self):
        return self.session.checkpoint(100)

    def cutover_mapping(self, step):
        old = {node["id"]: node for node in self.read_blob(self.payload()[1]["graph"])["nodes"]}
        configured = dag.z._workflow_section(
            self.session.project, "workflow_adherence")["configuration"]["phase_dag"]
        new = {node["id"]: node for node in configured["nodes"]}
        current = {}
        for reference in reversed(self.payload()[1]["evidence"]):
            artifact = self.read_blob(reference)
            result = artifact.get("content", {})
            node = result.get("node", {})
            if artifact.get("type") != "result" or node.get("item") is not None:
                continue
            current.setdefault(node.get("node"), (reference, result))
        mapping = []
        for name, (reference, result) in current.items():
            if name not in old or name not in new:
                continue
            for output in result.get("outputs", {}):
                if output not in old[name]["outputs"] or output not in new[name]["outputs"]:
                    continue
                mapping.append({"old": {"node": name, "output": output},
                    "new": {"node": name, "output": output}, "result": reference,
                    "equivalence": {key: True for key in
                        ("inputs", "outputs", "scope", "role", "independence", "approval")}})
        return mapping

    def reviewed_cutover(self, step, request):
        prepared = self.session.call(100, {**step["prepare"], "actor": "root-thread",
            "mapping": self.cutover_mapping(step), "request_id": request + "-prepare"})["next_steps"][0]
        reviewed = self.session.call(100, {**prepared["review"],
            "actor": "independent-cutover-reviewer", "decision": "approved",
            "report": "The exact old/new mapping and current evidence remain equivalent.",
            "request_id": request + "-review"})["next_steps"][0]
        return self.session.call(100, {**reviewed["apply"], "actor": "root-thread",
            "request_id": request + "-apply"})["next_steps"][0]

    def executable_names(self, steps):
        return {step["node"]["node"] for step in steps
                if step.get("kind") == "execute" and step.get("node")}

    def acquire_prefix(self, prefix, *, item=None, actor=None):
        matches = [step for step in self.session.ready()
                   if step["node"]["node"].startswith(prefix)
                   and step["node"].get("item") == item]
        self.assertEqual(1, len(matches), matches)
        return self.session.acquire(matches[0]["node"]["node"], item=item, actor=actor)

    def record_phase_finding(self, result_ref, subject, request_id, finding_id, target=None):
        request = {
            "operation": "phase_finding", "request_id": request_id,
            "actor": "root-thread", "target": target or {"node": "produce", "output": "value"},
            "subject": subject, "source": result_ref,
            "rationale": "A verified diagnostic identified a missing obligation.",
            "id": finding_id,
        }
        with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "root-thread"}):
            return self.session.call(100, request)

    def test_current_policy_graph_is_execution_topology_and_history_remains_audit_only(self):
        historical_ref = copy.deepcopy(self.graph_ref())
        historical_graph = self.read_blob(historical_ref)
        current = self.policy_graph_with_added_phase()
        self.set_current_graph(current)

        steps = self.public_steps()

        self.assertIn("produce", self.executable_names(steps))
        self.assertTrue(any(
            step.get("node", {}).get("node") == "policy_added"
            for step in steps
        ), "the current policy phase must participate in the public frontier")
        self.assertEqual(historical_ref, self.graph_ref(),
                         "policy changes must not replace the historical graph Ref")
        self.assertEqual(historical_graph, self.read_blob(self.graph_ref()),
                         "the payload graph remains immutable audit history")
        self.assertFalse(any(step.get("kind") in {"graph_adopt", "graph_normalize"}
                             for step in steps), steps)

    def test_compatible_result_survives_added_policy_phase_and_only_new_work_is_pending(self):
        self.produce()
        produced = copy.deepcopy(self.produced("produce"))
        historical_ref = copy.deepcopy(self.graph_ref())
        self.set_current_graph(self.policy_graph_with_added_phase())

        steps = self.public_steps()

        self.assertEqual("policy_dag_cutover", steps[0]["kind"])
        applied = self.reviewed_cutover(steps[0], "add-policy-phase")
        self.assertEqual("policy_dag_cutover_applied", applied["kind"])
        steps = self.public_steps()

        self.assertNotIn("produce", self.executable_names(steps),
                         "compatible settled work must not be repeated")
        added = [step for step in steps if step.get("kind") == "execute"
                 and step.get("node", {}).get("node") == "policy_added"]
        self.assertEqual(1, len(added), steps)
        self.assertEqual(produced, added[0]["input_envelope"]["inputs"][0]["source"])
        self.assertEqual(historical_ref, self.graph_ref())

    def test_phase_finding_records_versioned_host_event_without_changing_graph(self):
        self.produce()
        result_ref, result = self.result("produce")
        subject = result["outputs"]["value"]
        historical_ref = copy.deepcopy(self.graph_ref())
        request = {
            "operation": "phase_finding",
            "request_id": "public-phase-finding-1",
            "actor": "root-thread",
            "target": {"node": "produce", "output": "value"},
            "subject": subject,
            "source": result_ref,
            "rationale": "A verified diagnostic identified a missing obligation.",
            "id": "missing-obligation",
        }

        with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "root-thread"}):
            response = self.session.call(100, request)

        recorded = response["next_steps"][0]
        self.assertEqual("phase_data_recorded", recorded["kind"])
        self.assertEqual(100, recorded["goal"])
        self.assertEqual(1, recorded["revision"])
        event = self.read_blob(recorded["event"])
        self.assertEqual("phase_event", event["type"])
        self.assertEqual({
            "id": "missing-obligation",
            "revision": 1,
            "target": {"node": "produce", "output": "value"},
            "source": result_ref,
            "subject": subject,
            "rationale": "A verified diagnostic identified a missing obligation.",
        }, event["content"])
        self.assertEqual("root-thread", event["provenance"]["actor"])
        self.assertEqual("owner/repo", event["provenance"]["repository"])
        self.assertEqual(100, event["provenance"]["goal"])
        self.assertEqual("public-phase-finding-1", event["provenance"]["request_id"])
        payload = self.payload()[1]
        self.assertEqual({"version": 1, "events": [recorded["event"]]}, payload["phase_data"])
        self.assertEqual(historical_ref, payload["graph"])

    def test_phase_finding_rejects_wrong_actor_foreign_or_wrong_hash_source_and_stale_subject(self):
        graph = copy.deepcopy(self.graph)
        next(node for node in graph["nodes"] if node["id"] == "produce")["inputs"] = {
            "request": dag.spec_input(),
        }
        self.install(graph)
        self.produce()
        result_ref, result = self.result("produce")
        subject = result["outputs"]["value"]
        request = {
            "operation": "phase_finding",
            "request_id": "public-phase-finding-invalid",
            "actor": "root-thread",
            "target": {"node": "produce", "output": "value"},
            "subject": subject,
            "source": result_ref,
            "rationale": "A verified diagnostic identified a missing obligation.",
            "id": "invalid-source-must-not-persist",
        }
        foreign_hash = "sha256:" + "1" * 64
        cases = {
            "wrong actor": {**request, "actor": "worker-thread"},
            "foreign goal source": {**request, "source": {
                "hash": foreign_hash,
                "uri": "zzzops:owner/repo:goal:101:" + foreign_hash,
            }},
            "wrong hash source": {**request, "source": {
                "hash": "sha256:" + "f" * 64,
                "uri": result_ref["uri"],
            }},
        }
        for label, invalid in cases.items():
            with self.subTest(label=label):
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "root-thread"}):
                    response = self.session.call(100, invalid, expected=2)
                self.assertRegex(json.dumps(response), r"(?i)actor|root|source|artifact|hash|goal")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))

        self.replace_spec("A newer exact specification invalidates the prior output subject.")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "root-thread"}):
            response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)stale|current|subject|output")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_late_finding_runs_normal_correction_then_a_second_revision_reviews_current_subject(self):
        self.produce()
        original_result, original = self.result("produce")
        original_subject = original["outputs"]["value"]
        first = self.record_phase_finding(
            original_result, original_subject, "late-round-1", "late-two-rounds")
        self.assertEqual(1, first["next_steps"][0]["revision"])
        review_step = next(step for step in first["next_steps"]
                           if step.get("kind") == "execute"
                           and step.get("node", {}).get("node", "").startswith("sw_review_"))
        review_name, item = review_step["node"]["node"], review_step["node"]["item"]
        review = self.session.acquire(review_name, item=item, actor="late-reviewer")
        review_inputs = {row["name"]: row["source"] for row in review["input_envelope"]["inputs"]}
        self.assertEqual(original_subject, review_inputs["subject"])
        self.session.finish(review, {"value": {
            "decision": "changes_requested", "report": "The late defect is reproducible.",
        }})

        interpret = self.acquire_prefix("gc_interpret_", item=item, actor="root-thread")
        review_ref = self.result(review_name, item)[0]
        finding_value = {
            "id": "late-two-rounds", "revision": 1,
            "source": self.produced(review_name, item=item),
            "subjects": [original_subject],
            "target": {"subject": {"kind": "node", "goal": 100, "node": "produce"},
                       "output": "value"},
            "request": "Correct the verified late defect.",
            "rationale": "Independent review requested the scoped correction.",
            "supersedes": None,
        }
        self.session.finish(interpret, {"value": finding_value})
        finding = self.produced(interpret["node"]["node"], item=item)
        admit = self.acquire_prefix("gc_admit_", item=item, actor="root-thread")
        self.session.finish(admit, {"value": {
            "finding": finding, "target_inputs": original["inputs"],
            "authority": self.result(interpret["node"]["node"], item)[0],
            "applicability": "applicable",
            "rationale": "The exact current output requires correction.",
        }, "transfer": None})

        correction = self.session.acquire("produce")
        self.session.finish(correction, {"value": "version two"})
        corrected_result, corrected = self.result("produce")
        corrected_subject = corrected["outputs"]["value"]
        self.assertNotEqual(original_subject, corrected_subject)
        fresh_review = self.session.acquire(review_name, item=item, actor="fresh-reviewer")
        fresh_inputs = {row["name"]: row["source"]
                        for row in fresh_review["input_envelope"]["inputs"]}
        self.assertEqual(corrected_subject, fresh_inputs["subject"])
        self.session.finish(fresh_review, {"value": {
            "decision": "approved", "report": "The corrected current subject resolves the defect.",
        }})

        second = self.record_phase_finding(
            corrected_result, corrected_subject, "late-round-2", "late-two-rounds")
        self.assertEqual(2, second["next_steps"][0]["revision"])
        second_review = next(step for step in second["next_steps"]
                             if step.get("kind") == "execute"
                             and step.get("node", {}).get("node") == review_name
                             and step.get("node", {}).get("item") != item)
        acquired = self.session.acquire(
            review_name, item=second_review["node"]["item"], actor="second-round-reviewer")
        inputs = {row["name"]: row["source"] for row in acquired["input_envelope"]["inputs"]}
        self.assertEqual(corrected_subject, inputs["subject"])
        self.assertNotEqual(original_subject, inputs["subject"])
        self.read_blob(original_result)
        self.read_blob(review_ref)

    def test_member_late_finding_uses_exact_item_generation_and_normal_correction_route(self):
        self.install(dag.selected_graph())
        self.choose({"alpha": "inspect alpha", "beta": "inspect beta"})
        for item in ("alpha", "beta"):
            self.session.finish(
                self.session.acquire("investigate", item=item),
                {"value": "original " + item},
            )
        historical_ref = copy.deepcopy(self.graph_ref())
        alpha_result, alpha = self.result("investigate", "alpha")
        alpha_subject = alpha["outputs"]["value"]
        target = {"node": "investigate", "output": "value", "expansion": "buckets",
                  "item": "alpha", "generation": 1}

        response = self.record_phase_finding(
            alpha_result, alpha_subject, "member-alpha-1", "member-alpha", target)
        recorded = response["next_steps"][0]
        self.assertEqual(("phase_data_recorded", 1),
                         (recorded["kind"], recorded["revision"]))
        review_step = next(step for step in response["next_steps"]
                           if step.get("kind") == "execute"
                           and step.get("node", {}).get("node", "").startswith("sw_review_"))
        event_item = review_step["node"]["item"]
        review_name = review_step["node"]["node"]
        review = self.session.acquire(review_name, item=event_item, actor="member-reviewer")
        inputs = {row["name"]: row["source"] for row in review["input_envelope"]["inputs"]}
        self.assertEqual(alpha_subject, inputs["subject"])
        self.session.finish(review, {"value": {
            "decision": "changes_requested", "report": "Alpha needs its scoped correction.",
        }})
        interpret = self.acquire_prefix("gc_interpret_", item=event_item, actor="root-thread")
        finding_value = {
            "id": "member-alpha", "revision": 1,
            "source": self.produced(review_name, item=event_item),
            "subjects": [alpha_subject],
            "target": {"subject": {"kind": "member", "goal": 100,
                        "expansion": "buckets", "item": "alpha", "generation": 1},
                       "output": "value"},
            "request": "Correct only alpha.",
            "rationale": "Independent member review rejected alpha.",
            "supersedes": None,
        }
        self.session.finish(interpret, {"value": finding_value})
        finding = self.produced(interpret["node"]["node"], item=event_item)
        admit = self.acquire_prefix("gc_admit_", item=event_item, actor="root-thread")
        self.session.finish(admit, {"value": {
            "finding": finding, "target_inputs": alpha["inputs"],
            "authority": self.result(interpret["node"]["node"], event_item)[0],
            "applicability": "applicable", "rationale": "Alpha alone is affected.",
        }, "transfer": None})
        self.session.finish(
            self.session.acquire("investigate", item="alpha"),
            {"value": "corrected alpha"},
        )
        self.assertEqual("corrected alpha", self.read_blob(
            self.produced("investigate", item="alpha"))["content"])
        self.assertEqual("original beta", self.read_blob(
            self.produced("investigate", item="beta"))["content"])
        self.assertEqual(historical_ref, self.graph_ref())
        beta_result, beta = self.result("investigate", "beta")
        beta_response = self.record_phase_finding(
            beta_result, beta["outputs"]["value"], "member-beta-1", "member-beta",
            {**target, "item": "beta"},
        )
        beta_subject = beta["outputs"]["value"]
        beta_review = next(step for step in beta_response["next_steps"]
                           if step.get("kind") == "execute"
                           and step.get("node", {}).get("node", "").startswith("sw_review_")
                           and any(row.get("name") == "subject" and row.get("source") == beta_subject
                                   for row in step["input_envelope"]["inputs"]))
        self.assertEqual(review_name, beta_review["node"]["node"],
                         "member data must not generate a different workflow definition")
        self.assertNotEqual(event_item, beta_review["node"]["item"])
        self.assertEqual(historical_ref, self.graph_ref())

    def test_member_finding_rejects_wrong_item_generation_and_expansion_without_writes(self):
        self.install(dag.selected_graph())
        self.choose({"alpha": "inspect alpha"})
        self.session.finish(
            self.session.acquire("investigate", item="alpha"), {"value": "original alpha"})
        result_ref, result = self.result("investigate", "alpha")
        subject = result["outputs"]["value"]
        target = {"node": "investigate", "output": "value", "expansion": "buckets",
                  "item": "alpha", "generation": 1}
        mutations = {
            "unknown item": {**target, "item": "missing"},
            "stale generation": {**target, "generation": 2},
            "wrong expansion": {**target, "expansion": "other"},
        }
        for label, invalid_target in mutations.items():
            with self.subTest(label=label):
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                request = {
                    "operation": "phase_finding", "request_id": "invalid-member-" + label,
                    "actor": "root-thread", "target": invalid_target,
                    "subject": subject, "source": result_ref,
                    "rationale": "Invalid member identity must fail closed.", "id": "bad-member",
                }
                with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "root-thread"}):
                    response = self.session.call(100, request, expected=2)
                self.assertRegex(json.dumps(response), r"(?i)item|generation|expansion|member|current")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_pending_policy_cutover_blocks_direct_complete_and_integrate_mutations(self):
        self.produce()
        for name in ("review_a", "review_b"):
            self.session.finish(self.session.acquire(name), {"value": "accepted"})
        self.session.finish(self.session.acquire("finish"), {"value": "done"})
        current = {"nodes": [dag.task("policy_only", role="root")], "task_sets": [],
                   "terminals": [dag.selector("policy_only")]}
        self.set_current_graph(current)
        frontier = self.public_steps()
        self.assertEqual(["policy_dag_cutover"], [step["kind"] for step in frontier])
        for operation in ("complete", "integrate"):
            with self.subTest(operation=operation):
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, {
                    "operation": operation, "request_id": "unmapped-history-" + operation,
                }, expected=2)
                self.assertRegex(json.dumps(response), r"(?i)unmapped|historical|policy|phase|graph")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_failed_workspace_verification_proof_is_an_authenticated_phase_finding_source(self):
        case = dag.WorkspaceAuthorityPublicTests(
            "test_workspace_proof_output_result_and_transition_share_one_checkpoint")
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.setup_workspace()
        work = case.acquire_workspace("alpha")
        (case.fixture.repo / "behavior_test.py").write_text(
            "assert False, 'verified missing behavior'\n")
        proof_ref, proof = case.candidate(work, 1)
        self.assertEqual(1, proof["commands"][0]["exit_code"])
        subject = case.produced("alpha")
        request = {
            "operation": "phase_finding", "request_id": "failed-proof-finding",
            "actor": "root-thread", "target": {"node": "alpha", "output": "value"},
            "subject": subject, "source": proof_ref,
            "rationale": "The authenticated workspace command observed missing behavior.",
            "id": "failed-verification-proof",
        }
        with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "root-thread"}):
            response = case.session.call(100, request)
        recorded = response["next_steps"][0]
        self.assertEqual("phase_data_recorded", recorded["kind"])
        event = case.read_blob(recorded["event"])
        self.assertEqual(proof_ref, event["content"]["source"])
        self.assertEqual(subject, event["content"]["subject"])

    def test_generated_member_review_lease_recovers_from_persisted_workflow_after_policy_change(self):
        graph = dag.selected_graph()
        self.install(graph)
        self.choose({"alpha": "inspect alpha"})
        self.session.finish(
            self.session.acquire("investigate", item="alpha"), {"value": "original alpha"})
        result_ref, result = self.result("investigate", "alpha")
        subject = result["outputs"]["value"]
        response = self.record_phase_finding(
            result_ref, subject, "member-pin-1", "member-pin",
            {"node": "investigate", "output": "value", "expansion": "buckets",
             "item": "alpha", "generation": 1},
        )
        review_step = next(step for step in response["next_steps"]
                           if step.get("kind") == "execute"
                           and step.get("node", {}).get("node", "").startswith("sw_review_"))
        review = self.session.acquire(
            review_step["node"]["node"], item=review_step["node"]["item"],
            actor="persistent-member-reviewer")
        _envelope, payload = self.payload()
        workflow_pin = copy.deepcopy(payload["workflow"])
        self.read_blob(workflow_pin["graph"])

        changed_policy = copy.deepcopy(graph)
        next(node for node in changed_policy["nodes"] if node["id"] == "select")[
            "prompt"] += " Policy revision after the member review started."
        self.set_current_graph(changed_policy)
        resumed = self.session.checkpoint(100)
        rendered = json.dumps(resumed)
        self.assertEqual("policy_dag_cutover", resumed[0]["kind"])
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        rejected = self.session.call(100, {**resumed[0]["prepare"], "actor": "root-thread",
            "mapping": self.cutover_mapping(resumed[0]),
            "request_id": "cutover-with-live-member-review"}, expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)lease|worker|resolve|recover")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertNotRegex(rendered, r"(?i)unknown or unsupported phase event target")
        recovery = {
            "operation": "recover", "request_id": "recover-pinned-member-review",
            "node": review["node"], "lease": review["lease"]["token"],
            "actor": review["bound_actor"], "worker_status": "stopped",
            "evidence": "Fixture observed the exact generated member reviewer stopped.",
        }
        self.session.call(100, recovery)
        payload = self.payload()[1]
        self.assertFalse(any(lease["token"] == review["lease"]["token"]
                             for lease in payload["operational"]["leases"]))
        review_results = [self.read_blob(ref) for ref in payload["evidence"]]
        self.assertFalse(any(artifact.get("type") == "result"
                             and artifact.get("content", {}).get("node") == review["node"]
                             for artifact in review_results),
                         "recovery must not fabricate the stopped review result")
        cutover = self.session.checkpoint(100)[0]
        applied = self.reviewed_cutover(cutover, "member-review-policy-change")
        self.assertEqual("policy_dag_cutover_applied", applied["kind"])
        names = self.names()
        self.assertNotIn("select", names, "equivalent settled selection must survive reviewed cutover")
        self.assertIn("synthesize", names)
        self.assertTrue(any(name.startswith("sw_review_") for name in names),
                        "recovering the stopped lease must preserve its unresolved review obligation")
        self.read_blob(workflow_pin["graph"])
        self.assertNotEqual(workflow_pin, self.payload()[1]["workflow"],
                            "the reviewed cutover must record the new authoritative workflow")

    def test_not_applicable_late_finding_preserves_target_and_restores_completion(self):
        self.produce()
        original_result, original = self.result("produce")
        original_subject = original["outputs"]["value"]
        for name in ("review_a", "review_b"):
            self.session.finish(self.session.acquire(name), {"value": "accepted"})
        self.session.finish(self.session.acquire("finish"), {"value": "done"})
        response = self.record_phase_finding(
            original_result, original_subject, "not-applicable-event", "outside-scope")
        review_step = next(step for step in response["next_steps"]
                           if step.get("kind") == "execute"
                           and step.get("node", {}).get("node", "").startswith("sw_review_"))
        review_name, event_item = review_step["node"]["node"], review_step["node"]["item"]
        review = self.session.acquire(review_name, item=event_item, actor="scope-reviewer")
        self.session.finish(review, {"value": {
            "decision": "changes_requested",
            "report": "The report is authentic but outside this target's applicable scope.",
        }})
        interpret = self.acquire_prefix("gc_interpret_", item=event_item, actor="root-thread")
        finding_value = {
            "id": "outside-scope", "revision": 1,
            "source": self.produced(review_name, item=event_item),
            "subjects": [original_subject],
            "target": {"subject": {"kind": "node", "goal": 100, "node": "produce"},
                       "output": "value"},
            "request": "Classify the authenticated report against the exact target.",
            "rationale": "Independent review requested an explicit applicability decision.",
            "supersedes": None,
        }
        self.session.finish(interpret, {"value": finding_value})
        finding = self.produced(interpret["node"]["node"], item=event_item)
        admit = self.acquire_prefix("gc_admit_", item=event_item, actor="root-thread")
        self.session.finish(admit, {"value": {
            "finding": finding, "target_inputs": original["inputs"],
            "authority": self.result(interpret["node"]["node"], event_item)[0],
            "applicability": "not_applicable",
            "rationale": "The verified report does not require changing this exact output.",
        }, "transfer": None})

        self.assertEqual(original_result, self.result("produce")[0])
        steps = self.session.checkpoint(100)
        self.assertTrue(any(step.get("kind") == "complete" for step in steps), steps)
        self.assertFalse(any(step.get("node", {}).get("node") == "produce"
                             and step.get("kind") == "execute" for step in steps))
        review_results = [artifact for artifact in
                          (self.read_blob(ref) for ref in self.payload()[1]["evidence"])
                          if artifact.get("type") == "result"
                          and artifact.get("content", {}).get("node", {}).get("node") == review_name]
        self.assertEqual(1, len(review_results),
                         "not-applicable admission must not fabricate another review Result")
        decision_ref = review_results[0]["content"]["outputs"]["value"]
        self.assertEqual("changes_requested", self.read_blob(decision_ref)["content"]["decision"])

    def test_pre_static_policy_fingerprint_preserves_unchanged_workspace_authorization(self):
        # Exact pre-685 evidence_policy projection: only operational sections
        # were excluded; workflow.phase_dag remained in the evidence identity.
        def predecessor_policy(policy):
            value = copy.deepcopy(policy)
            if isinstance(value.get('sections'), list):
                value['sections'] = [row for row in value['sections']
                    if row.get('id') not in {'model_routing', 'autonomy_approval_parallelism'}]
            return value
        case = dag.WorkspaceAuthorityPublicTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        with mock.patch.object(dag.z._phase_evidence, 'evidence_policy', predecessor_policy):
            case.setup_workspace()
            _alpha, (proof_ref, proof) = case.red_candidate()
            before = {name: case.result(name)[0] for name in
                      ('charter', 'inspect_charter', 'consent', 'alpha', 'observe_alpha', 'accept_alpha')}
        snapshot = dag.z.workflow_engine(case.fixture.repo, case.session.project,
                                         case.session.runtime).node_snapshot(100)
        for name, reference in before.items():
            self.assertEqual(reference, snapshot['projection']['current'].get((100, name, None, 1), (None,))[0], name)
        original_policy = copy.deepcopy(case.session.project['policy'])
        case.session.project['policy']['sections'][0]['instructions'] += ' Require a fresh authority audit before source writes.'
        changed = dag.z.workflow_engine(case.fixture.repo, case.session.project,
                                        case.session.runtime).node_snapshot(100)
        for name in before:
            self.assertNotIn((100, name, None, 1), changed['projection']['current'])
        case.session.project['policy'] = original_policy
        self.assertEqual(proof, case.read_blob(proof_ref))
        consumed = case.fixture.repo / 'read_dependency.txt'
        unchanged = consumed.read_bytes()
        consumed.write_text('Unapproved drift must not be hidden by fingerprint adaptation.\n')
        drifted = dag.z.workflow_engine(case.fixture.repo, case.session.project,
                                        case.session.runtime).node_snapshot(100)
        self.assertNotIn((100, 'alpha', None, 1), drifted['projection']['current'])
        self.assertNotEqual('ready', drifted['projection']['states'][(100, 'beta', None, 1)]['state'])
        consumed.write_bytes(unchanged)
        case.acquire_workspace('beta')

    def test_unrelated_event_preserves_current_approved_event_review(self):
        graph = {'nodes': [dag.task('first'), dag.task('second')], 'task_sets': [],
                 'terminals': [dag.selector('first'), dag.selector('second')]}
        self.install(graph)
        for name in ('first', 'second'):
            self.session.finish(self.session.acquire(name), {'value': name + ' accepted'})
        first_result, first = self.result('first')
        self.record_phase_finding(first_result, first['outputs']['value'], 'event-first', 'first-event',
                                  {'node': 'first', 'output': 'value'})
        ready = next(row for row in self.session.ready()
                     if row['node']['node'].startswith('sw_review_'))
        work = self.session.acquire(ready['node']['node'], item=ready['node']['item'],
                                    actor='independent-event-reviewer')
        self.session.finish(work, {'value': {'decision': 'approved', 'report': 'Exact first subject remains valid.'}})
        identity = work['node']
        accepted = self.result(identity['node'], identity['item'])[0]
        graph_before = dag.z.workflow_engine(self.fixture.repo, self.session.project,
                                             self.session.runtime).node_snapshot(100)['graph']
        second_result, second = self.result('second')
        self.record_phase_finding(second_result, second['outputs']['value'], 'event-second', 'second-event',
                                  {'node': 'second', 'output': 'value'})
        snapshot = dag.z.workflow_engine(self.fixture.repo, self.session.project,
                                         self.session.runtime).node_snapshot(100)
        self.assertEqual(graph_before, snapshot['graph'])
        self.assertEqual(accepted, snapshot['projection']['current'][dag.z._phase_evidence.task_key(identity)][0])
        self.assertEqual(accepted, self.result(identity['node'], identity['item'])[0])

    def test_pending_workspace_authorization_finding_blocks_exact_source_acquisition(self):
        from pathlib import Path
        case = dag.WorkspaceAuthorityPublicTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.setup_workspace()
        ready = next(row for row in case.session.ready() if row['node']['node'] == 'alpha')
        receipt = json.loads(Path(ready['policy']['path']).read_text())['policy_receipt']
        start = {**ready['start'], 'policy_receipt': receipt,
                 'request_id': 'source-start-after-late-authority-event'}
        result, content = case.result('consent')
        subject = content['outputs']['permit']
        with mock.patch.dict(os.environ, {'CODEX_THREAD_ID': 'root-thread'}):
            response = case.session.call(100, {'operation': 'phase_finding',
                'request_id': 'workspace-authority-late-event', 'actor': 'root-thread',
                'target': {'node': 'consent', 'output': 'permit'}, 'subject': subject,
                'source': result, 'rationale': 'The exact workspace authorization needs independent reassessment.',
                'id': 'workspace-authority-late-event'})
        self.assertTrue(any(row.get('node', {}).get('node', '').startswith('sw_review_')
                            for row in response['next_steps']))
        self.assertEqual(result, case.result('consent')[0])
        snapshot = dag.z.workflow_engine(case.fixture.repo, case.session.project, case.session.runtime).node_snapshot(100)
        state = snapshot['projection']['states'][(100, 'alpha', None, 1)]
        self.assertEqual('blocked', state['state'])
        self.assertRegex(state['reason'], r'Pending late finding review')
        before = copy.deepcopy((case.provider.issues, case.provider.comments))
        rejected = case.session.call(100, start, expected=2)
        self.assertRegex(json.dumps(rejected), r'(?i)pending|finding|review|ready|blocked|stale|prerequisite')
        self.assertEqual(before, (case.provider.issues, case.provider.comments))
        self.assertEqual([], case.payload()[1]['operational']['leases'])

    def test_pending_late_review_of_publication_authorization_blocks_direct_integrate(self):
        case = publication.GenericPublicationPublicTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.authorize_context()
        authorization = case.approve_publication()
        case.submit_role("finish", "Exact configured graph complete")
        integrate = case.integration_request(authorization)
        authorization_result = case.result(case.ids["approve"])[0]
        request = {
            "operation": "phase_finding", "request_id": "publication-authorization-event",
            "actor": "root-thread",
            "target": {"node": case.ids["approve"], "output": "value"},
            "subject": authorization, "source": authorization_result,
            "rationale": "Authenticated late evidence questions current publication authority.",
            "id": "publication-authority-late-review",
        }
        with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "root-thread"}):
            response = case.session.call(100, request)
        self.assertTrue(any(step.get("node", {}).get("node", "").startswith("sw_review_")
                            for step in response["next_steps"]))
        before = copy.deepcopy((case.provider.issues, case.provider.comments))
        integrate["request_id"] = "blocked-by-pending-publication-authority-review"
        rejected = case.session.call(100, integrate, expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)pending|phase|review|publication|authoriz")
        self.assertEqual(before, (case.provider.issues, case.provider.comments))
        self.assertEqual([], case.merge_calls)


if __name__ == "__main__":
    unittest.main()
