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
        self.addCleanup(self.case.doCleanups)

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

    def admit(self, case_name="conditional_iam"):
        c = self.case
        interpretation = c.session.acquire("interpret_accepted_test_defect")
        c.session.finish(interpretation, {"value": self.finding(case_name)})
        finding = c.produced("interpret_accepted_test_defect")
        c.session.finish(c.session.acquire("admit_accepted_test_correction"), {"value": {
            "finding": finding, "target_inputs": c.result("test_design")[1]["inputs"],
            "authority": c.result("interpret_accepted_test_defect")[0], "applicability": "applicable",
            "rationale": "Exact accepted subject and finite reviewed test allocation"}})
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
        self.assertNotIn("implement", c.names())
        c.session.finish(c.session.acquire("review_test_design", actor="fresh-independent-reviewer"),
                         {"value": {"decision": "approved", "report": "Safe and negative controls verified"}})
        c.session.finish(c.session.acquire("retain_test_design_findings"), {"value": {
            "items": {"accepted_test_conditional_iam": finding}, "rationale": "Retain exact defect"}})
        self.assertNotIn("implement", c.names())
        c.session.finish(c.session.acquire("resolve_test_design_finding", item="accepted_test_conditional_iam",
                                           actor="fresh-independent-resolver"), {"value": {
            "finding": finding, "subjects": [c.produced("test_design")],
            "reviewer_result": c.result("review_test_design")[0], "decision": "resolved",
            "rationale": "Fresh review covers the exact corrected accepted test"}})
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
        self.enable_additive_route_control()
        self.finish_initial_work()
        self.admit()
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
        self.finish_initial_work()
        interpretation = c.session.acquire("interpret_implement_rejection")
        before = copy.deepcopy((c.provider.issues, c.provider.comments))
        response = c.session.call(100, c.session.submission(
            interpretation, {"value": self.finding()}, "existing-route-retarget"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)target|permit|scope")
        self.assertEqual(before, (c.provider.issues, c.provider.comments))

    def run_shipped_case(self, case_name):
        c = self.case
        self.finish_initial_work()
        self.assertIn("interpret_accepted_test_defect", c.names())
        finding = self.admit(case_name)
        correction = c.session.acquire("test_design", actor="correction-" + case_name)
        self.assertIn(c.result("test_design")[0]["hash"], json.dumps(correction["lease"]["acquisition"]))
        self.assertEqual(case_name, self.case.read_blob(finding)["content"]["rationale"].split(":", 1)[0])
        (c.fixture.repo / "behavior_test.py").write_text("assert True  # sanitized workflow fixture\n")
        request = c.session.submission(correction, {"value": json.dumps(ORIGEN_CASES[case_name], sort_keys=True)},
                                       "corrected-" + case_name)
        request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
        c.session.call(100, request)
        c.session.finish(c.session.acquire("review_test_design", actor="reviewer-" + case_name),
                         {"value": {"decision": "approved", "report": "Safe and negative inputs reviewed"}})
        c.session.finish(c.session.acquire("retain_test_design_findings"), {"value": {
            "items": {"accepted_test_" + case_name: finding}, "rationale": "Retain exact defect"}})
        c.session.finish(c.session.acquire("resolve_test_design_finding", item="accepted_test_" + case_name,
                                           actor="resolver-" + case_name), {"value": {
            "finding": finding, "subjects": [c.produced("test_design")],
            "reviewer_result": c.result("review_test_design")[0], "decision": "resolved",
            "rationale": "Fresh independent review covers corrected fixture"}})
        self.assertIn("implement", c.names())

    def test_shipped_route_carries_conditional_iam_fixture(self):
        self.run_shipped_case("conditional_iam")

    def test_shipped_route_carries_null_role_name_fixture(self):
        self.run_shipped_case("null_role_name")

    def test_shipped_route_carries_delete_lifecycle_fixture(self):
        self.run_shipped_case("delete_lifecycle")

    def test_default_graph_declares_acyclic_accepted_test_route(self):
        c = self.case
        template = json.loads((j.old.fixtures.PLUGIN_ROOT / "zzzops/templates/project-goals/INIT_PLAN.json").read_text())
        graph = j.z._workflow_section(template, "workflow_adherence")["configuration"]["phase_dag"]
        ids = [node["id"] for node in graph["nodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("interpret_accepted_test_defect", ids)
        self.assertIn("admit_accepted_test_correction", ids)
        self.assertLess(ids.index("interpret_accepted_test_defect"), ids.index("admit_accepted_test_correction"))
        route = next(node for node in graph["nodes"] if node["id"] == "interpret_accepted_test_defect")
        self.assertEqual("review_test_design", route["inputs"]["accepted_review"]["producer"]["node"]["node"])
        self.assertEqual("identity", route["inputs"]["accepted_review"]["mode"])
        self.assertEqual(["decision"], route["inputs"]["approved"]["path"])
        self.assertEqual("content", route["inputs"]["approved"]["mode"])
        self.assertEqual(["approved"], route["inputs"]["approved"]["type"]["values"])
        self.assertEqual("implement", route["inputs"]["implementation"]["producer"]["node"]["node"])
        self.assertEqual("identity", route["inputs"]["implementation"]["mode"])
        self.assertEqual("review_implement", route["inputs"]["review"]["producer"]["node"]["node"])
        self.assertEqual("identity", route["inputs"]["review"]["mode"])

    def test_reviewed_existing_goal_adoption_preserves_custom_topology_and_history(self):
        c = self.case
        original_install = c.install

        def install_old_with_custom_node(graph):
            graph = copy.deepcopy(graph)
            graph["nodes"] = [node for node in graph["nodes"] if node["id"] not in {
                "interpret_accepted_test_defect", "admit_accepted_test_correction"}]
            graph["nodes"].append(j.task("custom_historical_note", role="root"))
            custom_set = copy.deepcopy(graph["task_sets"][0])
            custom_set["id"] = "custom_historical_findings"
            custom_set["template"]["id"] = "resolve_custom_historical_finding"
            graph["task_sets"].append(custom_set)
            graph["terminals"].append(j.selector("custom_historical_note"))
            original_install(graph)

        c.install = install_old_with_custom_node
        history = self.finish_initial_work()
        c.install = original_install
        old_payload = copy.deepcopy(c.payload()[1])
        old_graph = c.read_blob(old_payload["graph"])
        self.assertFalse({"interpret_accepted_test_defect", "admit_accepted_test_correction"} &
                         {node["id"] for node in old_graph["nodes"]})
        old_node_order = [node["id"] for node in old_graph["nodes"]]
        old_task_sets = copy.deepcopy(old_graph["task_sets"])
        old_terminals = copy.deepcopy(old_graph["terminals"])
        proposed = self.additive_route(c.graph)
        prepared = c.session.call(100, {"operation": "graph_prepare", "graph": proposed,
                                       "rationale": "Add only reviewed accepted-test recovery nodes"})
        for name in ("add_goal", "put_envelope", "envelope_for", "read_at", "result_at", "proposal_review"):
            setattr(c, name, types.MethodType(getattr(j.GraphAdoptionPublicTests, name), c))
        request = c.proposal_review(prepared["next_steps"][0]["proposal"])
        with mock.patch.object(c.provider, "update_issue", side_effect=RuntimeError("interrupted adoption checkpoint")):
            c.session.call(100, request, expected=2)
        accepted = c.session.call(100, request)
        self.assertEqual(accepted, c.session.call(100, request), "Exact adoption retry must be idempotent")
        payload = c.payload()[1]
        self.assertEqual(old_payload["evidence"], payload["evidence"])
        adopted = c.read_blob(payload["graph"])
        adopted_ids = [node["id"] for node in adopted["nodes"]]
        self.assertEqual(old_node_order, adopted_ids[:len(old_node_order)])
        self.assertEqual(old_task_sets, adopted["task_sets"][:len(old_task_sets)])
        self.assertEqual(old_terminals, adopted["terminals"][:len(old_terminals)])
        self.assertIn("custom_historical_note", adopted_ids)
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
        admission = c.session.acquire("admit_accepted_test_correction")
        stale_inputs = copy.deepcopy(c.result("test_design")[1]["inputs"])
        stale_inputs[0]["source"] = c.result("implement")[0]
        before = copy.deepcopy((c.provider.issues, c.provider.comments))
        response = c.session.call(100, c.session.submission(admission, {"value": {
            "finding": finding, "target_inputs": stale_inputs,
            "authority": c.result("interpret_accepted_test_defect")[0],
            "applicability": "applicable", "rationale": "stale subject"}}, "stale-admission"), expected=2)
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
        self.enable_additive_route_control()
        self.finish_initial_work()
        self.admit()
        correction = c.session.acquire("test_design", actor="same-person")
        (c.fixture.repo / "behavior_test.py").write_text("assert True\n")
        request = c.session.submission(correction, {"value": "corrected bounded test"}, "self-review-candidate")
        request["workspace_checks"] = [[sys.executable, "-B", "behavior_test.py"]]
        c.session.call(100, request)
        step = next(row for row in c.session.ready() if row["node"]["node"] == "review_test_design")
        receipt = json.loads(Path(step["policy"]["path"]).read_text())["policy_receipt"]
        started = c.session.call(100, {**step["start"], "policy_receipt": receipt})["next_steps"][0]
        bind = {**started["bind"], "lease": started["lease"]["token"], "actor": "same-person",
                "selection": started["lease"]["selection"], "policy_receipt": receipt,
                "request_id": "self-review-bind"}
        response = c.session.call(100, bind, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)independent|actor|self|review")

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
        c.session.finish(c.session.acquire("admit_implement_correction"), {"value": {
            "finding": implementation_finding, "target_inputs": c.result("implement")[1]["inputs"],
            "authority": c.result("interpret_implement_rejection")[0], "applicability": "applicable",
            "rationale": "Exact implementation correction"}})
        active = c.session.acquire("implement", actor="active-implementation-owner")
        self.assertFalse(any(step["node"]["node"] == "test_design" for step in c.session.ready()),
                         "Shared repository workspace must remain exclusive")
        self.assertFalse(any(step["node"]["node"] == "admit_accepted_test_correction" for step in c.session.ready()),
                         "Evidence admission cannot take over a live workspace owner")
        self.assertTrue(any(lease["token"] == active["lease"]["token"]
                            for lease in c.payload()[1]["operational"]["leases"]))


if __name__ == "__main__":
    unittest.main()
