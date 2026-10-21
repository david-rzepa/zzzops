"""Public construction paths persist recovery-complete graphs on first publication."""
from __future__ import annotations

import copy
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import test_evidence_dag_journeys as dag
import test_graph_compiler as compiler_cases
import test_graph_normalization_public as normalization_cases


class GraphCompilationPublicTests(dag.DagFixture):
    def test_public_release_cli_routes_status_configure_assign_and_checkpoint(self):
        class Provider:
            def __init__(self):
                self.record = None; self.lock = None; self.audit = []; self.observations = []
                self.exchange_calls = 0; self.fail_exchange_at = None
                self.observed = {"members": {"1": {"status": "done", "integrated_commit": "a" * 40}},
                    "active_owners": [], "observed_commits": ["a" * 40],
                    "source_ancestors": ["a" * 40], "forbidden_commits": [],
                    "source_branch": "dev", "source_sha": "a" * 40}
            def acquire_repository_lock(self, repository, request_id):
                if self.lock not in (None, request_id): raise ValueError("locked")
                self.lock = request_id
            def release_repository_lock(self, repository, request_id):
                if self.lock == request_id: self.lock = None
            def read(self, repository): return copy.deepcopy(self.record)
            def create_only(self, repository, record):
                if self.record is not None: raise ValueError("duplicate")
                self.record = copy.deepcopy(record); return copy.deepcopy(record)
            def compare_exchange(self, repository, revision, record):
                if self.record is None or self.record["revision"] != revision: raise ValueError("revision changed")
                self.exchange_calls += 1
                if self.exchange_calls == self.fail_exchange_at: raise TimeoutError("provider outcome unknown before effect")
                self.record = copy.deepcopy(record); return copy.deepcopy(record)
            def append_artifact(self, repository, artifact): self.audit.append(copy.deepcopy(artifact))
            def result_artifact(self, repository, reference):
                matches = [row for row in self.audit if row.get("reference") == reference]
                if len(matches) > 1 and any(row != matches[0] for row in matches[1:]):
                    raise ValueError("conflicting durable release operation results")
                return copy.deepcopy(matches[0]) if matches else None
            def observe_release(self, repository, release):
                self.observations.append((repository, release))
                return copy.deepcopy(self.observed)
        class BranchProvider:
            def __init__(self): self.refs = {}; self.calls = 0; self.uncertain_after = False
            def observe(self, branch): return self.refs.get(branch)
            def create_only(self, branch, sha):
                self.calls += 1
                current = self.refs.get(branch)
                if current is not None and current != sha: raise ValueError("different-SHA conflict")
                self.refs[branch] = sha
                if self.uncertain_after: raise TimeoutError("provider outcome unknown after effect")
                return {"status": "created", "branch": branch, "sha": sha}
        provider = Provider()
        branches = BranchProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); request = root / "request.json"
            project = copy.deepcopy(self.session.project)
            release_policy = {"enabled": True, "next_release": 1, "integration_branch": "dev",
                "publication_branch": "main", "release_branch_prefix": "release/", "execution_scope": "active_only"}
            dag.z._workflow_section(project, "git_review_release")["configuration"]["release_planning"] = release_policy
            with mock.patch.object(dag.z._package, "package_status", return_value={"ok": True, "version": "test", "revision": "test"}), \
                 mock.patch.object(dag.z, "reviewed_project_state", return_value=project), \
                 mock.patch.object(dag.z, "GitHubReleasePlanAdapter", return_value=provider), \
                 mock.patch.object(dag.z, "GitHubReleaseBranchAdapter", return_value=branches):
                def invoke(*argv, payload=None, expected_code=0):
                    if payload is not None: request.write_text(json.dumps(payload), encoding="utf-8")
                    args = ["zzzops", "--repo", str(root), "release", *argv]
                    if payload is not None: args += ["--input", str(request)]
                    with mock.patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()) as output:
                        self.assertEqual(expected_code, dag.z.main())
                    return json.loads(output.getvalue())
                configured = invoke("configure", payload={"request_id": "configure-1", "expected_revision": None,
                    "plan": {"next_release": 1, "assignments": {}, "releases": {}}})
                self.assertEqual("applied", configured["status"])
                before = copy.deepcopy(provider.record); writes = provider.exchange_calls
                invalid = invoke("assign", payload={"request_id": "assign-invalid", "expected_revision": 0,
                    "assignments": [{"goal": 7, "release": 2}, {"goal": 8, "release": 0}]}, expected_code=2)
                self.assertIn("positive", invalid["reason"])
                self.assertEqual(before, provider.record)
                self.assertEqual(writes, provider.exchange_calls)
                provider.fail_exchange_at = provider.exchange_calls + 2
                partial = invoke("assign", payload={"request_id": "assign-partial", "expected_revision": 0,
                    "assignments": [{"goal": 7, "release": 2}, {"goal": 8, "release": 3}]})
                self.assertEqual(["applied", "pending"], [row["status"] for row in partial["items"]])
                self.assertEqual({"7": 2}, provider.record["assignments"])
                after_partial = copy.deepcopy(provider.record); writes = provider.exchange_calls
                conflict = invoke("assign", payload={"request_id": "assign-stale", "expected_revision": 0,
                    "assignments": [{"goal": 9, "release": 4}, {"goal": 10, "release": 4}]}, expected_code=2)
                self.assertIn("revision", conflict["reason"])
                self.assertEqual(after_partial, provider.record)
                self.assertEqual(writes, provider.exchange_calls)
                provider.fail_exchange_at = None
                partial_request = {"request_id": "assign-partial", "expected_revision": 0,
                    "assignments": [{"goal": 7, "release": 2}, {"goal": 8, "release": 3}]}
                recovered = invoke("assign", payload=partial_request)
                self.assertEqual(["applied", "applied"], [row["status"] for row in recovered["items"]])
                self.assertEqual({"7": 2, "8": 3}, provider.record["assignments"])
                self.assertEqual(2, provider.record["revision"], "replay must write only the pending item")
                completed = invoke("assign", payload={"request_id": "assign-complete", "expected_revision": 2,
                    "assignments": [{"goal": 8, "release": 3}, {"goal": 9, "release": 3}]})
                completed_record = copy.deepcopy(provider.record); writes = provider.exchange_calls
                replay = invoke("assign", payload={"request_id": "assign-complete", "expected_revision": 2,
                    "assignments": [{"goal": 8, "release": 3}, {"goal": 9, "release": 3}]})
                self.assertEqual(completed, replay)
                self.assertEqual(completed_record, provider.record)
                self.assertEqual(writes, provider.exchange_calls)
                status = invoke("status")
                self.assertEqual(2, status["assignments"]["7"])
                checkpoint = invoke("checkpoint", payload={"operation": "propose", "request_id": "checkpoint-1",
                    "expected_revision": provider.record["revision"],
                    "members": {"1": {"status": "done", "integrated_commit": "f" * 40}},
                    "active_owners": [], "observed_commits": ["f" * 40], "source_ancestors": ["f" * 40],
                    "source_branch": "forged", "source_sha": "f" * 40,
                    "authority": "sha256:" + "b" * 64})
                self.assertEqual("ready_proposal", checkpoint["status"])
                self.assertEqual("a" * 40, checkpoint["proposal"]["source_sha"])
                self.assertEqual([("owner/repo", 1)], provider.observations)
                frozen = invoke("checkpoint", payload={"operation": "freeze", "request_id": "freeze-public",
                    "expected_revision": provider.record["revision"], "proposal": checkpoint["proposal"]})
                self.assertEqual("frozen_intent", frozen["status"])
                provider.observed["source_sha"] = "e" * 40
                provider.observed["members"] = {"1": {"status": "done", "integrated_commit": "e" * 40}}
                drift = invoke("checkpoint", payload={"operation": "cut", "request_id": "cut-drift",
                    "expected_revision": provider.record["revision"], "intent": frozen["intent"]}, expected_code=2)
                self.assertIn(drift["code"], {"source_drift", "membership_drift"})
                self.assertEqual(0, branches.calls)
                self.assertEqual(1, provider.record["next_release"])
                provider.observed.update(source_sha="a" * 40,
                    members={"1": {"status": "done", "integrated_commit": "a" * 40}})
                branches.uncertain_after = True
                cut_request = {"operation": "cut", "request_id": "cut-public",
                    "expected_revision": provider.record["revision"], "intent": frozen["intent"]}
                confirmed = invoke("checkpoint", payload=cut_request)
                self.assertEqual("branch_confirmed", confirmed["status"])
                self.assertEqual(2, provider.record["next_release"])
                calls = branches.calls; record = copy.deepcopy(provider.record)
                replay_cut = invoke("checkpoint", payload=cut_request)
                self.assertEqual(confirmed, replay_cut)
                self.assertEqual(calls, branches.calls)
                self.assertEqual(record, provider.record)

    def test_release_coordination_does_not_add_goal_dag_nodes(self):
        reviewed = compiler_cases.default_graph()
        dag.z._workflow_section(self.session.project, "workflow_adherence")["configuration"]["phase_dag"] = reviewed
        canonical = dag.z._static_workflow.canonical(reviewed, self.compiler())
        self.assertEqual(canonical, dag.z._static_workflow.canonical(canonical, self.compiler()))
        declarations = [*canonical["nodes"], *(row["template"] for row in canonical["task_sets"])]
        self.assertFalse(any(node["id"].startswith("release_") for node in declarations))

    def test_public_capture_creates_goal_then_returns_recoverable_assignment_state(self):
        class ReleaseProvider:
            def __init__(self):
                self.record = {"kind": "release-plan", "revision": 0, "next_release": 1,
                    "assignments": {}, "releases": {}}; self.lock = None; self.fail_after = True
            def acquire_repository_lock(self, repository, request_id): self.lock = request_id
            def release_repository_lock(self, repository, request_id): self.lock = None
            def read(self, repository): return copy.deepcopy(self.record)
            def compare_exchange(self, repository, revision, record):
                if revision != self.record["revision"]: raise ValueError("revision changed")
                self.record = copy.deepcopy(record)
                if self.fail_after: raise TimeoutError("provider outcome unknown after effect")
                return copy.deepcopy(record)
            def append_artifact(self, repository, artifact): pass
        release_provider = ReleaseProvider()
        project = self.session.project
        dag.z._workflow_section(project, "git_review_release")["configuration"]["release_planning"] = {
            "enabled": True, "next_release": 1, "integration_branch": "dev",
            "publication_branch": "main", "release_branch_prefix": "release/", "execution_scope": "active_only"}
        request = self.capture_request(); request["target_release"] = 2
        def create_issue(payload):
            number = max(self.provider.issues) + 1
            issue = {"number": number, "title": payload["title"], "body": payload["body"], "state": "open",
                "html_url": f"https://github.com/owner/repo/issues/{number}",
                "labels": [{"name": value} for value in payload["labels"]]}
            self.provider.issues[number] = copy.deepcopy(issue); self.provider.comments[number] = []
            return copy.deepcopy(issue)
        self.provider.create_issue = create_issue
        with mock.patch.object(dag.z, "GitHubReleasePlanAdapter", return_value=release_provider):
            proposal = self.session.call(100, {"operation": "capture_propose", "request": request})
            submission = copy.deepcopy(proposal["next_steps"][0]["submission"])
            submission["approved_by"] = "approved-user"
            result = self.session.call(100, submission)
        created = max(set(self.provider.issues) - {100})
        self.assertEqual("created_assignment_reconciled", result["capture"]["status"])
        self.assertEqual(created, result["capture"]["goal"]["number"])
        self.assertEqual(2, release_provider.record["assignments"][str(created)])
        self.assertEqual(1, len(set(self.provider.issues) - {100}), "retry state must not duplicate the goal")

    def compiler(self):
        value = getattr(dag.z, "_graph_compiler", None)
        self.assertIsNotNone(value, "graph compiler service is not registered")
        return value

    def graph_from_goal(self, number=100):
        envelope, payload = self.payload()
        self.assertEqual(number, envelope["issue"])
        return self.read_blob(payload["graph"])

    def assert_complete(self, graph, *, local_goal=100):
        dag.z._phase_evidence.validate_graph(graph)
        canonical = dag.z._static_workflow.canonical(graph, self.compiler())
        self.assertEqual(graph, canonical,
                         "new captures must persist the complete fixed policy workflow")

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
        reviewed = compiler_cases.default_graph()
        dag.z._workflow_section(self.session.project, "workflow_adherence")[
            "configuration"]["phase_dag"] = reviewed
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
        expected = dag.z._static_workflow.canonical(reviewed, self.compiler())
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
        self.assertEqual(self.graph, actual,
                         "policy approval must not rewrite an existing goal's historical graph")
        self.assertEqual(before_evidence, self.payload()[1]["evidence"])
        self.assertNotEqual(reviewed_graph, actual,
                            "the newly approved policy remains current authority without adoption")

    def test_policy_approval_never_replaces_existing_goal_with_settled_results(self):
        self.produce()
        before_issue = copy.deepcopy(self.provider.issues[100])
        before_comments = copy.deepcopy(self.provider.comments[100])
        before_envelope, before_payload = self.payload()
        before_graph = self.read_blob(before_payload["graph"])
        self.assertTrue(before_payload["evidence"], "fixture must contain a real settled Result")

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
        proposed = self.session.call(100, {"operation": "policy_propose", "plan": plan},
                                     intent="inspect")
        step = proposed["next_steps"][0]
        approved = self.session.call(100, {"operation": "policy_approve",
            "proposal_hash": step["hash"], "approved_by": "approved-user"},
            intent="inspect", expected=None)

        after_envelope, after_payload = self.payload()
        self.assertEqual(before_envelope, after_envelope)
        self.assertEqual(before_graph, self.read_blob(after_payload["graph"]))
        self.assertEqual(before_payload["evidence"], after_payload["evidence"])
        self.assertEqual(before_payload["operational"]["receipts"],
                         after_payload["operational"]["receipts"])
        self.assertEqual(before_issue, self.provider.issues[100])
        self.assertEqual(before_comments, self.provider.comments[100])
        if any(step.get("kind") in {"blocker", "repair"}
               for step in approved.get("next_steps", [])):
            self.assertRegex(json.dumps(approved), r"(?i)graph|adopt|settled|result|existing|defer")

    def test_unsupported_first_graph_fails_before_provider_write(self):
        source = compiler_cases.default_graph()
        review = next(n for n in source["nodes"] if n["id"] == "review_decomposition")
        review["inputs"]["unrelated_allocation"] = {
            "producer": {"node": {"kind": "node", "goal": "#this", "node": "understand"}},
            "output": "allocation", "path": [], "mode": "identity",
            "type": copy.deepcopy(next(n for n in source["nodes"] if n["id"] == "understand")
                                  ["outputs"]["allocation"]["schema"]),
        }
        review["independent_of"].append({
            "kind": "node", "goal": "#this", "node": "understand",
        })
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

    def test_new_capture_of_unsupported_member_graph_fails_before_provider_write(self):
        graph = normalization_cases.unsupported_member_retirement_graph()
        dag.z._workflow_section(self.session.project, "workflow_adherence")[
            "configuration"]["phase_dag"] = graph
        request = self.capture_request()
        self.provider.create_issue = lambda _payload: self.fail(
            "unsupported member graph reached provider issue creation")
        proposal = self.session.call(100, {"operation": "capture_propose", "request": request})
        submission = copy.deepcopy(proposal["next_steps"][0]["submission"])
        submission["approved_by"] = "approved-user"
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, submission, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)unsupported|recover|route|contract|target")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))


if __name__ == "__main__":
    unittest.main()
