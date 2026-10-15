"""Public construction paths persist recovery-complete graphs on first publication."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest import mock

import test_evidence_dag_journeys as dag
import test_graph_compiler as compiler_cases


class GraphCompilationPublicTests(dag.DagFixture):
    def compiler(self):
        value = getattr(dag.z, "_graph_compiler", None)
        self.assertIsNotNone(value, "graph compiler service is not registered")
        return value

    def graph_from_goal(self, number=100):
        envelope, payload = self.payload()
        self.assertEqual(number, envelope["issue"])
        return self.read_blob(payload["graph"])

    def assert_complete(self, graph, *, local_goal=100):
        self.compiler().validate_recovery(graph, local_goal=local_goal)
        self.assertIn("obligation_selections", json.dumps(graph, sort_keys=True))

    def capture_request(self):
        return {
            "schema_version": 1, "title": "Compile first captured graph",
            "body": "## Outcome\nPersist a complete graph.\n\n## Acceptance\n- [ ] Rejection exposes ordinary correction work.\n",
            "labels": [], "goal": {"schema_version": 1, "status": "new", "priority": "P0",
                "value": "high", "difficulty": "S", "confidence": "high", "parent": None,
                "depends_on": [], "claim": None, "blockers": [], "evidence": ["Approved test fixture."],
                "next_action": "Understand the approved goal.", "revision": 1,
                "implementation": None, "resources": []},
        }

    def test_public_capture_persists_complete_deterministic_first_graph(self):
        request = self.capture_request()
        def create_issue(payload):
            number = max(self.provider.issues) + 1
            issue = {"number": number, "title": payload["title"], "body": payload["body"],
                     "state": "open", "html_url": f"https://github.com/owner/repo/issues/{number}",
                     "labels": [{"name": value} for value in payload["labels"]]}
            self.provider.issues[number] = copy.deepcopy(issue)
            self.provider.comments[number] = []
            return copy.deepcopy(issue)
        self.provider.create_issue = create_issue
        proposal = self.session.call(100, {"operation": "capture_propose", "request": request})
        submission = copy.deepcopy(proposal["next_steps"][0]["submission"])
        submission["approved_by"] = "approved-user"
        writes = []
        unrelated = copy.deepcopy((self.provider.issues[100], self.provider.comments[100]))
        update = self.provider.update_issue
        with mock.patch.object(self.provider, "update_issue",
                               side_effect=lambda number, payload: (writes.append((number, copy.deepcopy(payload))),
                                                                    update(number, payload))[1]):
            self.session.call(100, submission)
        created = max(set(self.provider.issues) - {100})
        envelope = dag.z.parse_managed_goal(self.provider.issues[created]["body"], created)
        payload = self.session.read(created, envelope["payload"])
        actual = self.session.read(created, payload["graph"])
        self.assert_complete(actual, local_goal=created)
        graph_writes = [body for number, body in writes if number == created and "zzzops-goal" in body.get("body", "")]
        self.assertTrue(graph_writes, "capture never persisted a managed compiled graph")
        first_v2 = next((dag.z.parse_managed_goal(row["body"], created) for row in graph_writes
                         if dag.z.parse_managed_goal(row["body"], created).get("schema_version") == 2), None)
        self.assertIsNotNone(first_v2, "capture never published a v2 graph")
        first_payload = self.session.read(created, first_v2["payload"])
        first_graph = self.session.read(created, first_payload["graph"])
        self.assert_complete(first_graph, local_goal=created)
        reviewed = dag.z._workflow_section(self.session.project, "workflow_adherence")["configuration"]["phase_dag"]
        expected = self.compiler().compile_graph(reviewed, local_goal=created)["graph"]
        self.assertEqual(expected, first_graph)
        self.assertEqual(expected, actual)
        self.assertEqual(unrelated, (self.provider.issues[100], self.provider.comments[100]))

    def test_public_bootstrap_attachment_preserves_reviewed_contract(self):
        plan = json.loads((Path(__file__).parents[1] /
            "plugins/zzzops/zzzops/templates/project-goals/INIT_PLAN.json").read_text())
        plan["base_digest"] = dag.z.initialization_base_digest(self.fixture.repo)
        plan["repository"] = {"identity": "owner/repo", "remote": "local"}
        plan["github"] = {"usable": True}
        backend = dag.z._workflow_section(plan, "backend")
        backend["instructions"] = "Store canonical goals in GitHub Issues."
        backend["configuration"]["authority"] = "github_issues"
        backend["configuration"]["repository_identity"] = "owner/repo"
        backend["default_disposition"] = "changed"
        reviewed_graph = copy.deepcopy(
            dag.z._workflow_section(plan, "workflow_adherence")["configuration"]["phase_dag"])
        proposed = self.session.call(100, {"operation": "policy_propose", "plan": plan}, intent="inspect")
        step = proposed["next_steps"][0]
        before_evidence = copy.deepcopy(self.payload()[1]["evidence"])
        self.session.call(100, {"operation": "policy_approve", "proposal_hash": step["hash"],
                                "approved_by": "approved-user"}, intent="inspect")
        actual = self.graph_from_goal()
        self.assert_complete(actual)
        self.assertEqual(reviewed_graph["terminals"], actual["terminals"])
        self.assertEqual(before_evidence, self.payload()[1]["evidence"])
        self.assertEqual(actual, self.compiler().compile_graph(reviewed_graph, local_goal=100)["graph"])

    def test_unsupported_first_graph_fails_before_provider_write(self):
        source = compiler_cases.default_graph()
        review = next(n for n in source["nodes"] if n["id"] == "review_decomposition")
        review["inputs"]["unrelated_allocation"] = {
            "producer": {"node": {"kind": "node", "goal": "#this", "node": "understand"}},
            "output": "allocation", "path": [], "mode": "identity",
            "type": copy.deepcopy(next(n for n in source["nodes"] if n["id"] == "understand")
                                  ["outputs"]["allocation"]["schema"]),
        }
        dag.z._workflow_section(self.session.project, "workflow_adherence")["configuration"]["phase_dag"] = source
        request = self.capture_request()
        def forbidden_create(_payload):
            self.fail("unsupported graph reached provider issue creation")
        self.provider.create_issue = forbidden_create
        proposal = self.session.call(100, {"operation": "capture_propose", "request": request})
        submission = copy.deepcopy(proposal["next_steps"][0]["submission"])
        submission["approved_by"] = "approved-user"
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, submission, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)ambig|route|recover|contract|target")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))


if __name__ == "__main__":
    unittest.main()
