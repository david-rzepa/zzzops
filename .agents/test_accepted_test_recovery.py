"""Public regressions for correcting an independently rejected accepted test."""
import copy
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

import test_evidence_dag_journeys as j


ORIGEN_CASES = {
    "conditional_iam": {
        "safe": {"principal": "serviceAccount:runner@example.test", "permission": "storage.objects.get",
                 "condition_type": "expression", "condition_name": "bounded-read"},
        "unsafe": [
            {"principal": "allUsers", "permission": "storage.objects.get",
             "condition_type": "expression", "condition_name": "bounded-read"},
            {"principal": "serviceAccount:runner@example.test", "permission": "storage.objects.admin",
             "condition_type": "expression", "condition_name": "bounded-read"},
            {"principal": "serviceAccount:runner@example.test", "permission": "storage.objects.get",
             "condition_type": "title", "condition_name": "bounded-read"},
            {"principal": "serviceAccount:runner@example.test", "permission": "storage.objects.get",
             "condition_type": "expression", "condition_name": "unbounded-read"},
        ],
    },
    "null_role_name": {
        "safe": {"name": None, "project": "fixture-project", "role_id": "fixtureReader",
                 "provenance": "reviewed-import"},
        "unsafe": [
            {"name": "projects/fixture-project/roles/fixtureReader", "project": "fixture-project",
             "role_id": "fixtureReader", "provenance": "reviewed-import"},
            {"name": None, "project": "other-project", "role_id": "fixtureReader",
             "provenance": "reviewed-import"},
            {"name": None, "project": "fixture-project", "role_id": "fixtureOwner",
             "provenance": "reviewed-import"},
            {"name": None, "project": "fixture-project", "role_id": "fixtureReader",
             "provenance": "conflicting-import"},
        ],
    },
    "delete_lifecycle": {
        "safe": {"action": "Delete", "storage_class": "STANDARD"},
        "unsafe": [
            {"action": "SetStorageClass", "storage_class": "STANDARD"},
            {"action": "Delete", "storage_class": "ARCHIVE"},
        ],
    },
}


def sanitized_fixture_is_safe(case_name, value):
    if case_name == "conditional_iam":
        return (value["principal"].startswith("serviceAccount:") and
                value["permission"] == "storage.objects.get" and
                value["condition_type"] == "expression" and value["condition_name"] == "bounded-read")
    if case_name == "null_role_name":
        return (value["name"] is None and value["project"] == "fixture-project" and
                value["role_id"] == "fixtureReader" and value["provenance"] == "reviewed-import")
    return value["action"] == "Delete" and value["storage_class"] == "STANDARD"


class AcceptedTestRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.case = j.DefaultCorrectionPublicTests()
        self.case.setUp()
        self.case.default_decomposition = types.MethodType(self.historical_default_decomposition, self.case)
        self.addCleanup(self.case.doCleanups)

    def historical_default_decomposition(self, case):
        """Build the accepted-test compatibility case on its original DAG."""
        graph = json.loads((Path(__file__).parent / "fixtures" / "legacy_evidence_dag.json").read_text())
        case.install(graph)
        allocation = {"allocations": {name: {
            "task": {"goal": 100, "node": name, "item": None, "generation": 1},
            "owned": ["behavior_test.py" if name == "test_design" else "source.py"],
            "consumed": ["product.txt"],
        } for name in ("test_design", "implement")}}
        case.session.finish(case.session.acquire("understand"), {
            "design": "Atomic bounded fixture", "allocation": allocation})
        permit = {"manifest": case.produced("understand", "allocation"),
                  "tasks": [item["task"] for item in allocation["allocations"].values()],
                  "policy": j.content_hash(case.session.project["policy"]), "decision": "approved"}
        case.session.finish(case.session.acquire("review_understanding"), {
            "review": {"decision": "approved", "report": "Exact historical scope reviewed"},
            "authorization": permit})
        case.session.finish(case.session.acquire("approve_understanding"), {"authorization": permit})
        case.session.finish(case.session.acquire("retain_understand_findings"), {
            "value": {"items": {}, "rationale": "No understanding findings were admitted"}})
        case.session.finish(case.session.acquire("decompose"), {"value": "First atomic disposition"})

    def additive_route(self, graph):
        graph = copy.deepcopy(graph)
        nodes = {node["id"]: node for node in graph["nodes"]}
        if {"interpret_accepted_test_defect", "admit_accepted_test_correction"} <= set(nodes):
            return graph
        interpretation = copy.deepcopy(nodes["interpret_test_design_rejection"])
        interpretation["id"] = "interpret_accepted_test_defect"
        interpretation["executor"]["authority"]["subject"]["node"] = interpretation["id"]
        for name in ("review", "rejected"):
            interpretation["inputs"][name]["producer"]["node"]["node"] = "review_implement"
        interpretation["requires"] = [j.selector(name) for name in ("test_design", "review_implement")]
        admission = copy.deepcopy(nodes["admit_test_design_correction"])
        admission["id"] = "admit_accepted_test_correction"
        admission["executor"]["authority"]["subject"]["node"] = admission["id"]
        admission["inputs"]["finding"]["producer"]["node"]["node"] = interpretation["id"]
        admission["requires"][0]["node"] = interpretation["id"]
        graph["nodes"].extend((interpretation, admission))
        return graph

    def enable_additive_route_control(self):
        """Install the already-approved probe graph only to validate later controls."""
        c = self.case
        original_install = c.install

        def install(graph):
            original_install(self.additive_route(graph))

        c.install = install

    def finish_initial_work(self):
        c = self.case
        original_acquire = c.session.acquire

        def capture_human_approval(name, **kwargs):
            acquired = original_acquire(name, **kwargs)
            if name == "approve_understanding":
                self.initial_human_approval = acquired
            return acquired

        c.session.acquire = capture_human_approval
        try:
            c.default_decomposition()
        finally:
            c.session.acquire = original_acquire
        self.initial_human_authorization = c.read_blob(
            c.produced("approve_understanding", "authorization"))["content"]
        c.session.finish(c.session.acquire("review_decomposition"),
                         {"value": {"decision": "approved", "report": "Atomic plan"}})
        c.session.finish(c.session.acquire("retain_decompose_findings"),
                         {"value": {"items": {}, "rationale": "No decomposition findings"}})
        tests = c.session.acquire("test_design", actor="test-author")
        (c.fixture.repo / "behavior_test.py").write_text("assert True\n")
        request = c.session.submission(tests, {"value": json.dumps(ORIGEN_CASES, sort_keys=True)}, "accepted-tests")
        request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
        c.session.call(100, request)
        self.initial_test_review = c.session.acquire("review_test_design", actor="independent-test-reviewer")
        c.session.finish(self.initial_test_review,
                         {"value": {"decision": "approved", "report": "Accepted bounded tests"}})
        c.session.finish(c.session.acquire("retain_test_design_findings"),
                         {"value": {"items": {}, "rationale": "No earlier findings"}})
        implementation = c.session.acquire("implement", actor="implementer")
        (c.fixture.repo / "source.py").write_text("value = 1\n")
        request = c.session.submission(implementation, {"value": "Stable implementation"}, "implementation")
        request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
        c.session.call(100, request)
        c.session.finish(c.session.acquire("review_implement", actor="implementation-reviewer"), {
            "value": {"decision": "changes_requested",
                      "report": "Accepted tests mishandle each bounded Origen case"}})
        return {
            "test": c.result("test_design")[0], "test_review": c.result("review_test_design")[0],
            "implementation": c.result("implement")[0], "implementation_review": c.result("review_implement")[0],
        }

    def finding(self, case_name="conditional_iam", target=None):
        c = self.case
        return {"id": "accepted_test_" + case_name, "revision": 1,
                "source": c.produced("review_implement"), "subjects": [c.produced("test_design")],
                "target": target or j.scope("test_design"),
                "request": "Correct only the accepted fixture for " + case_name,
                "rationale": case_name + ": " + json.dumps(ORIGEN_CASES[case_name], sort_keys=True),
                "supersedes": None}

    def compiled_admission(self, finding_node="interpret_accepted_test_defect", subject_node="test_design"):
        """Return the one canonical admission for the accepted-test contract."""
        c = self.case
        graph = j.z.workflow_engine(c.fixture.repo, c.session.project, c.session.runtime).node_snapshot(100)["graph"]
        contracts = list(graph["nodes"]) + [row["template"] for row in graph["task_sets"]]
        expected_scope = {"subject": {"kind": "node", "goal": "#this", "node": subject_node},
                          "output": "value"}
        candidates = []
        for node in contracts:
            inputs = node.get("inputs", {})
            permits = node.get("permits", [])
            if (str(node.get("id", "")).startswith("gc_atomic_admit_")
                    and inputs.get("finding", {}).get("producer") == {
                        "node": {"kind": "node", "goal": "#this", "node": finding_node}}
                    and inputs.get("finding", {}).get("output") == "value"
                    and inputs.get("subject", {}).get("producer") == {
                        "node": {"kind": "node", "goal": "#this", "node": subject_node}}
                    and inputs.get("subject", {}).get("output") == "value"
                    and {permit.get("type") for permit in permits} == {"admission", "supersession"}
                    and all(permit.get("scope") == expected_scope for permit in permits)):
                candidates.append(node["id"])
        self.assertEqual(1, len(candidates), candidates)
        replay = {'graph': j.z._static_workflow.canonical(graph, j.z._graph_compiler)}
        replay_ids = {node["id"] for node in replay["graph"]["nodes"]} | {
            row["template"]["id"] for row in replay["graph"]["task_sets"]}
        self.assertIn(candidates[0], replay_ids, "Canonical admission identity must be stable")
        if finding_node == "interpret_accepted_test_defect":
            self.assertNotIn("admit_accepted_test_correction", c.names(),
                             "Historical admission identity must be shadowed after compilation")
        return candidates[0]

    def contract_state(self, node_name, *, target_name):
        """Build the evaluator state for one reviewed contract without replaying its predecessors."""
        c = self.case
        graph = json.loads(
            (Path(__file__).parent / "fixtures" / "legacy_evidence_dag.json").read_text())
        graph = j.z._static_workflow.canonical(graph, j.z._graph_compiler)
        contract = next(node for node in graph["nodes"] if node["id"] == node_name)
        node = {"goal": 100, "node": node_name, "item": None, "generation": 1}
        target = {"goal": 100, "node": target_name, "item": None, "generation": 1}
        selectors = []
        for selector in contract.get("independent_of", []):
            selectors.append({"selector": selector, "targets": [target], "location": "contract"})
        for permit in contract.get("permits", []):
            selector = permit["scope"]["subject"]
            if not any(row["selector"] == selector for row in selectors):
                selectors.append({"selector": selector, "targets": [target], "location": "contract"})
        return graph, {"node": node, "contract": contract, "resolutions": selectors, "inputs": []}

    def admit(self, case_name="conditional_iam"):
        c = self.case
        interpretation = c.session.acquire("interpret_accepted_test_defect")
        c.session.finish(interpretation, {"value": self.finding(case_name)})
        finding = c.produced("interpret_accepted_test_defect")
        c.session.finish(c.session.acquire(self.compiled_admission()), {"value": {
            "finding": finding, "target_inputs": c.result("test_design")[1]["inputs"],
            "authority": c.result("interpret_accepted_test_defect")[0], "applicability": "applicable",
            "rationale": "Exact accepted subject and finite reviewed test allocation"}, "transfer": None})
        return finding

    def test_additive_graph_feasibility_control_reaches_fresh_implementation(self):
        c = self.case
        self.enable_additive_route_control()
        history = self.finish_initial_work()
        self.assertIn("interpret_accepted_test_defect", c.names())
        for case_name, fixture in ORIGEN_CASES.items():
            with self.subTest(case=case_name):
                self.assertTrue(sanitized_fixture_is_safe(case_name, fixture["safe"]))
                for unsafe in fixture["unsafe"]:
                    self.assertFalse(sanitized_fixture_is_safe(case_name, unsafe))
        finding = self.admit()
        self.assertIn("test_design", c.names())
        corrected = c.session.acquire("test_design", actor="correction-author")
        self.assertIn(history["test"]["hash"], json.dumps(corrected["lease"]["acquisition"]))
        (c.fixture.repo / "behavior_test.py").write_text("assert True  # bounded safe inputs accepted\n")
        request = c.session.submission(corrected, {"value": json.dumps(ORIGEN_CASES, sort_keys=True)}, "corrected-tests")
        request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
        c.session.call(100, request)
        persisted_cases = c.read_blob(c.produced("test_design"))["content"]
        self.assertEqual(ORIGEN_CASES, json.loads(persisted_cases))
        self.assertNotIn("implement", c.names())
        c.session.finish(c.session.acquire("review_test_design", actor="fresh-independent-reviewer"),
                         {"value": {"decision": "approved", "report": "Safe and negative controls verified"}})
        c.session.finish(c.session.acquire("retain_test_design_findings"), {"value": {
            "items": {"accepted_test_conditional_iam": finding}, "rationale": "Retain exact defect"}})
        self.assertNotIn("implement", c.names())
        c.resolve_exact_batch({'accepted_test_conditional_iam': finding}, c.produced('test_design'),
                              c.result('review_test_design')[0],
                              'Fresh review covers the exact corrected accepted test',
                              actor='fresh-independent-resolver')
        self.assertIn("implement", c.names())
        for ref in history.values():
            c.read_blob(ref)

    def test_wrong_target_and_active_owner_reject_without_provider_mutation(self):
        c = self.case
        self.enable_additive_route_control()
        self.finish_initial_work()
        interpretation = c.session.acquire("interpret_accepted_test_defect")
        before = copy.deepcopy((c.provider.issues, c.provider.comments))
        bad = self.finding(target=j.scope("implement"))
        response = c.session.call(100, c.session.submission(interpretation, {"value": bad}, "wrong-target"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)target|permit|scope")
        self.assertEqual(before, (c.provider.issues, c.provider.comments))

    def test_expanded_test_path_rejects_without_provider_mutation(self):
        c = self.case
        c.default_decomposition()
        c.session.finish(c.session.acquire("review_decomposition"),
                         {"value": {"decision": "approved", "report": "Atomic plan"}})
        c.session.finish(c.session.acquire("retain_decompose_findings"),
                         {"value": {"items": {}, "rationale": "No decomposition findings"}})
        correction = c.session.acquire("test_design", actor="bounded-test-corrector")
        (c.fixture.repo / "unexpected_test.py").write_text("assert True\n")
        before = copy.deepcopy((c.provider.issues, c.provider.comments))
        request = c.session.submission(correction, {"value": "expanded test path"}, "expanded-test-path")
        request["workspace_checks"] = [[sys.executable, "-B", "unexpected_test.py"]]
        response = c.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)scope|owned|workspace|path|file")
        self.assertEqual(before, (c.provider.issues, c.provider.comments))

    def test_stale_accepted_test_approval_replay_rejects_without_provider_mutation(self):
        c = self.case
        self.enable_additive_route_control()
        self.finish_initial_work()
        self.admit()
        correction = c.session.acquire("test_design", actor="bounded-test-corrector")
        (c.fixture.repo / "behavior_test.py").write_text("assert True  # corrected subject\n")
        request = c.session.submission(correction, {"value": "corrected subject"}, "fresh-corrected-subject")
        request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
        c.session.call(100, request)
        before = copy.deepcopy((c.provider.issues, c.provider.comments))
        stale = c.session.submission(self.initial_test_review,
            {"value": {"decision": "approved", "report": "Approval for old accepted test"}},
            "stale-test-approval-replay")
        response = c.session.call(100, stale, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)stale|input|subject|lease|review")
        self.assertEqual(before, (c.provider.issues, c.provider.comments))

    def test_stale_human_approval_cannot_authorize_changed_allocation_reacquisition(self):
        c = self.case
        self.enable_additive_route_control()
        self.finish_initial_work()
        self.admit()
        c.replace_spec("Changed allocation and authority require fresh human approval")
        changed = copy.deepcopy(c.read_blob(c.produced("understand", "allocation"))["content"])
        changed["allocations"]["test_design"]["owned"].append("expanded_test.py")
        c.session.finish(c.session.acquire("understand"), {
            "design": "Changed accepted-test allocation", "allocation": changed})
        permit = {"manifest": c.produced("understand", "allocation"),
                  "tasks": [row["task"] for row in changed["allocations"].values()],
                  "policy": j.content_hash(c.session.project["policy"]), "decision": "approved"}
        c.session.finish(c.session.acquire("review_understanding", actor="fresh-authority-reviewer"), {
            "review": {"decision": "approved", "report": "Changed exact allocation independently reviewed"},
            "authorization": permit})
        c.session.finish(c.session.acquire("retain_understand_findings"),
                         {"value": {"items": {}, "rationale": "No planning findings"}})
        self.assertIn("approve_understanding", c.names())
        before = copy.deepcopy((c.provider.issues, c.provider.comments))
        stale = c.session.submission(self.initial_human_approval,
                                     {"authorization": self.initial_human_authorization},
                                     "stale-human-approval-replay")
        response = c.session.call(100, stale, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)stale|input|approval|lease|authority")
        self.assertEqual(before, (c.provider.issues, c.provider.comments))
        self.assertNotIn("test_design", c.names())

    def test_existing_implementation_route_cannot_retarget_test_design_negative_control(self):
        c = self.case
        graph, state = self.contract_state(
            "interpret_implement_rejection", target_name="implement")
        engine = j.z.workflow_engine(c.fixture.repo, c.session.project, c.session.runtime)
        source = {"hash": "sha256:" + "2" * 64, "uri": "urn:sha256:" + "2" * 64}
        subject = {"hash": "sha256:" + "3" * 64, "uri": "urn:sha256:" + "3" * 64}
        result_ref = {"hash": "sha256:" + "4" * 64, "uri": "urn:sha256:" + "4" * 64}
        subject_node = {"goal": 100, "node": "test_design", "item": None, "generation": 1}
        subject_result = {"node": subject_node, "executor": "test-author", "inputs": [],
                          "outputs": {"value": subject}}
        snapshot = {"graph": graph, "projection": {
            "current": {j.z._phase_evidence.task_key(subject_node): (result_ref, subject_result)},
            "states": {}, "obligations": {}},
            "artifacts": {source["hash"]: {"type": "review_decision", "content": {}},
                          subject["hash"]: {"type": "test_design", "content": {}}},
            "payload": {"evidence": []}}
        wrong_target = {
            "id": "accepted_test_conditional_iam", "revision": 1,
            "source": source, "subjects": [subject],
            "target": {"subject": {"kind": "node", "goal": 100,
                                    "node": "test_design"}, "output": "value"},
            "request": "Correct only the accepted fixture",
            "rationale": "The implementation route cannot grant test-design scope",
            "supersedes": None,
        }
        with self.assertRaisesRegex(ValueError, r"permit|scope|target"):
            engine.node_validate_bundle(snapshot, state, {"value": wrong_target}, "root-thread")
        allowed_finding = copy.deepcopy(wrong_target)
        allowed_finding["target"]["subject"]["node"] = "implement"
        engine.node_validate_bundle(snapshot, state, {"value": allowed_finding}, "root-thread")
        allowed = next(permit for permit in state["contract"]["permits"]
                       if permit["type"] == "finding")["scope"]
        self.assertEqual("implement", allowed["subject"]["node"])


    def test_default_graph_declares_acyclic_accepted_test_route(self):
        c = self.case
        template = json.loads((j.old.fixtures.PLUGIN_ROOT / "zzzops/templates/project-goals/INIT_PLAN.json").read_text())
        graph = j.z._workflow_section(template, "workflow_adherence")["configuration"]["phase_dag"]
        ids = [node["id"] for node in graph["nodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn("interpret_accepted_test_defect", ids)
        self.assertNotIn("admit_accepted_test_correction", ids)
        self.assertIn("interpret_test_design_rejection", ids)
        self.assertIn("admit_test_design_correction", ids)

    def test_legacy_graph_declares_acyclic_accepted_test_route(self):
        graph = json.loads(
            (Path(__file__).parent / "fixtures" / "legacy_evidence_dag.json").read_text())
        ids = [node["id"] for node in graph["nodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("interpret_accepted_test_defect", ids)
        self.assertIn("admit_accepted_test_correction", ids)
        self.assertLess(ids.index("interpret_accepted_test_defect"),
                        ids.index("admit_accepted_test_correction"))
        route = next(node for node in graph["nodes"]
                     if node["id"] == "interpret_accepted_test_defect")
        self.assertEqual("review_test_design",
                         route["inputs"]["accepted_review"]["producer"]["node"]["node"])
        self.assertEqual("identity", route["inputs"]["accepted_review"]["mode"])
        self.assertEqual(["decision"], route["inputs"]["approved"]["path"])
        self.assertEqual("content", route["inputs"]["approved"]["mode"])
        self.assertEqual(["approved"], route["inputs"]["approved"]["type"]["values"])
        self.assertEqual("implement",
                         route["inputs"]["implementation"]["producer"]["node"]["node"])
        self.assertEqual("identity", route["inputs"]["implementation"]["mode"])
        self.assertEqual("review_implement",
                         route["inputs"]["review"]["producer"]["node"]["node"])
        self.assertEqual("identity", route["inputs"]["review"]["mode"])

    def test_reviewed_policy_repair_preserves_custom_historical_topology_and_results(self):
        c = self.case
        original_install = c.install
        def install_old_with_custom_node(graph):
            graph = copy.deepcopy(graph)
            graph["nodes"].append(j.task("custom_historical_note", role="root"))
            graph["terminals"].append(j.selector("custom_historical_note"))
            original_install(graph)
        c.install = install_old_with_custom_node
        history = self.finish_initial_work()
        c.install = original_install
        old_payload = copy.deepcopy(c.payload()[1])
        old_graph = c.read_blob(old_payload["graph"])
        reviewed = self.additive_route(c.graph)
        j.z._workflow_section(c.session.project, "workflow_adherence")[
            "configuration"]["phase_dag"] = copy.deepcopy(reviewed)
        snapshot = j.z.workflow_engine(c.fixture.repo, c.session.project, c.session.runtime).node_snapshot(100)
        self.assertEqual(j.z._static_workflow.canonical(reviewed, j.z._graph_compiler), snapshot["graph"])
        payload = c.payload()[1]
        self.assertEqual(old_payload["graph"], payload["graph"])
        self.assertEqual(old_payload["evidence"], payload["evidence"])
        self.assertIn("custom_historical_note", {node["id"] for node in old_graph["nodes"]})
        self.assertIn("interpret_accepted_test_defect", c.names())
        for ref in history.values():
            c.read_blob(ref)

    def test_stale_admission_inputs_reject_atomically(self):
        c = self.case
        self.enable_additive_route_control()
        self.finish_initial_work()
        interpretation = c.session.acquire("interpret_accepted_test_defect")
        c.session.finish(interpretation, {"value": self.finding()})
        finding = c.produced("interpret_accepted_test_defect")
        admission = c.session.acquire(self.compiled_admission())
        stale_inputs = copy.deepcopy(c.result("test_design")[1]["inputs"])
        stale_inputs[0]["source"] = c.result("implement")[0]
        before = copy.deepcopy((c.provider.issues, c.provider.comments))
        response = c.session.call(100, c.session.submission(admission, {"value": {
            "finding": finding, "target_inputs": stale_inputs,
            "authority": c.result("interpret_accepted_test_defect")[0],
            "applicability": "applicable", "rationale": "stale subject"}, "transfer": None},
            "stale-admission"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)input|subject|stale|target")
        self.assertEqual(before, (c.provider.issues, c.provider.comments))

    def test_retained_finding_omission_blocks_resolution_and_implementation(self):
        c = self.case
        self.enable_additive_route_control()
        self.finish_initial_work()
        finding = self.admit()
        correction = c.session.acquire("test_design", actor="correction-owner")
        (c.fixture.repo / "behavior_test.py").write_text("assert True\n")
        request = c.session.submission(correction, {"value": "corrected bounded test"}, "corrected")
        request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
        c.session.call(100, request)
        c.session.finish(c.session.acquire("review_test_design", actor="independent-reviewer"),
                         {"value": {"decision": "approved", "report": "Exact correction approved"}})
        registry = c.session.acquire("retain_test_design_findings")
        before = copy.deepcopy((c.provider.issues, c.provider.comments))
        response = c.session.call(100, c.session.submission(registry, {"value": {
            "items": {}, "rationale": "incorrectly omit admitted defect"}}, "omit-retained"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)retain|finding|complete|omit")
        self.assertEqual(before, (c.provider.issues, c.provider.comments))
        self.assertNotIn("implement", c.names())
        c.read_blob(finding)

    def test_correction_author_cannot_bind_fresh_independent_test_review(self):
        c = self.case
        graph, state = self.contract_state("review_test_design", target_name="test_design")
        engine = j.z.workflow_engine(c.fixture.repo, c.session.project, c.session.runtime)
        subject = state["resolutions"][0]["targets"][0]
        key = j.z._phase_evidence.task_key(subject)
        snapshot = {"graph": graph, "projection": {"current": {
            key: ({"hash": "sha256:" + "1" * 64, "uri": "urn:sha256:" + "1" * 64},
                  {"node": subject, "executor": "same-person", "outputs": {}, "inputs": []})}}}
        with self.assertRaisesRegex(ValueError, r"[Ii]ndependent reviewer"):
            engine.node_independence(snapshot, state, "same-person")
        engine.node_independence(snapshot, state, "different-reviewer")

    def test_live_implementation_correction_owner_blocks_test_recovery_takeover(self):
        c = self.case
        self.enable_additive_route_control()
        self.finish_initial_work()
        test_interpretation = c.session.acquire("interpret_accepted_test_defect")
        c.session.finish(test_interpretation, {"value": self.finding()})
        test_finding = c.produced("interpret_accepted_test_defect")
        implement_interpretation = c.session.acquire("interpret_implement_rejection")
        implementation_finding = {"id": "implementation_defect", "revision": 1,
            "source": c.produced("review_implement"), "subjects": [c.produced("implement")],
            "target": j.scope("implement"), "request": "Correct implementation only",
            "rationale": "Independent implementation rejection", "supersedes": None}
        c.session.finish(implement_interpretation, {"value": implementation_finding})
        implementation_finding = c.produced("interpret_implement_rejection")
        implement_admission = self.compiled_admission(
            finding_node="interpret_implement_rejection", subject_node="implement")
        c.session.finish(c.session.acquire(implement_admission), {"value": {
            "finding": implementation_finding, "target_inputs": c.result("implement")[1]["inputs"],
            "authority": c.result("interpret_implement_rejection")[0], "applicability": "applicable",
            "rationale": "Exact implementation correction"}, "transfer": None})
        test_admission = self.compiled_admission()
        active = c.session.acquire("implement", actor="active-implementation-owner")
        self.assertFalse(any(step["node"]["node"] == "test_design" for step in c.session.ready()),
                         "Shared repository workspace must remain exclusive")
        self.assertFalse(any(step["node"]["node"] == test_admission for step in c.session.ready()),
                         "Evidence admission cannot take over a live workspace owner")
        self.assertTrue(any(lease["token"] == active["lease"]["token"]
                            for lease in c.payload()[1]["operational"]["leases"]))


if __name__ == "__main__":
    unittest.main()
