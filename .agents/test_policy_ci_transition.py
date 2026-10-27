"""Public workflow regression for reviewed terminal CI policy changes."""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import test_evidence_dag_journeys as dag
import test_workflow_policy_approval as approval
import test_workflow_publication_contract as publication


z = dag.z


class PolicyCiTransitionTests(dag.DagFixture):
    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.fixture.repo), *args], text=True).strip()

    def commit_policy(self, message):
        self.git("add", ".zzzops/POLICY.json", ".zzzops/PROJECT.md", ".zzzops/PROJECT_AUDIT.md")
        self.git("commit", "-qm", message)

    def reviewed_policy(self, mode, *, initial=False):
        reviewer = approval.WorkflowPolicyApprovalTests()
        reviewer.repo = self.fixture.repo
        plan = reviewer.plan()
        plan["repository"] = {"identity": "owner/repo", "remote": "local"}
        pending_reviews = {section["id"]: section["review"] for section in plan["policy"]["sections"]}
        plan["policy"] = copy.deepcopy(self.session.project["policy"])
        for section in plan["policy"]["sections"]:
            section["review"] = copy.deepcopy(pending_reviews[section["id"]])
            if section["id"] in {"backend", "workflow_adherence", "model_routing", "verification_testing", "git_review_release", "code_quality"}:
                section["default_disposition"] = "changed"
            if section["id"] == "backend":
                section["configuration"]["repository_identity"] = "owner/repo"
            if section["id"] == "verification_testing":
                section["configuration"]["required_ci"] = mode
        proposal = reviewer.public({"operation": "policy_propose", "plan": plan})
        self.assertEqual("human_approval", proposal["next_steps"][0]["kind"])
        reviewer.approve(proposal, reviewer="policy-owner")
        state = z.read_project_state(self.fixture.repo)[2]
        self.assertEqual([], z.validate_project_state(state))
        self.assertEqual([], z.validate_project_artifacts(self.fixture.repo, state))
        self.session.project["policy"] = copy.deepcopy(state["policy"])
        self.commit_policy("reviewed initial policy" if initial else "reviewed CI transition")
        return state

    def initial_result(self):
        self.reviewed_policy("disabled", initial=True)
        self.install(self.graph)
        self.produce()
        return copy.deepcopy(self.payload()[1]["evidence"])

    def executable(self):
        return {step["node"]["node"] for step in self.session.checkpoint(100)
                if step.get("kind") == "execute"}

    def assert_policy_diagnostic(self, steps):
        reasons = " ".join(str(step.get("reason", step.get("action", "")))
                           for step in steps if step.get("kind") in {"blocker", "dependency", "repair"})
        self.assertRegex(reasons, r"(?i)policy|ancestor|approval|binding|historical")

    def replace_payload(self, envelope, payload):
        envelope["payload"] = self.blob(payload)
        envelope["revision"] += 1
        self.provider.issues[100]["body"] = re.sub(
            r"<!-- zzzops-goal\s*\n.*?\nzzzops-goal -->",
            "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->",
            self.provider.issues[100]["body"], flags=re.S)

    def test_reviewed_ci_only_change_keeps_prior_result_and_immutable_history(self):
        before = self.initial_result()
        self.assertEqual(1, len(self.provider.issues))
        self.assertEqual(1, len(before))
        self.assertIn("review_a", self.names())

        self.reviewed_policy("existing_only")
        steps = self.session.checkpoint(100)

        active = {step["node"]["node"] for step in steps if step.get("kind") == "execute"}
        self.assertIn("review_a", active)
        self.assertNotIn("produce", active)
        self.assertEqual(before, self.payload()[1]["evidence"])
        self.assertEqual(1, len(self.provider.issues))

    def test_reviewed_ci_loosening_keeps_prior_result(self):
        self.reviewed_policy("inspect_exact_pr_head", initial=True)
        self.install(self.graph)
        self.produce()
        before = copy.deepcopy(self.payload()[1]["evidence"])
        self.reviewed_policy("disabled")
        self.assertIn("review_a", self.executable())
        self.assertEqual(before, self.payload()[1]["evidence"])

    def test_verification_instruction_change_stales_prior_result(self):
        before = self.initial_result()
        verification = z._workflow_section(self.session.project, "verification_testing")
        verification["instructions"] += " Require a new independent observation."
        self.reviewed_policy("disabled")
        self.assertIn("produce", self.executable())
        self.assertEqual(before, self.payload()[1]["evidence"])

    def test_other_policy_configuration_change_stales_prior_result(self):
        before = self.initial_result()
        release = z._workflow_section(self.session.project, "git_review_release")
        release["configuration"]["release_planning"]["next_release"] += 1
        self.reviewed_policy("existing_only")
        self.assertIn("produce", self.executable())
        self.assertEqual(before, self.payload()[1]["evidence"])

    def test_node_contract_and_goal_input_changes_stale_prior_result(self):
        before = self.initial_result()
        changed = copy.deepcopy(self.graph)
        changed["nodes"][0]["prompt"] += " Additional output detail is required."
        z._workflow_section(self.session.project, "workflow_adherence")["configuration"]["phase_dag"] = changed
        self.reviewed_policy("disabled")
        steps = self.session.checkpoint(100)
        producer = next(step for step in steps if step.get("node", {}).get("node") == "produce")
        self.assertEqual("execute", producer["kind"])
        self.assertNotEqual(self.result("produce")[1]["contract"],
                            producer["input_envelope"]["contract"])
        downstream = next(step for step in steps if step.get("node", {}).get("node") == "review_a")
        self.assertEqual("dependency", downstream["kind"])
        self.assertRegex(downstream["reason"], r"produce.*required evidence is stale or missing")
        self.assertNotIn("review_a", {step.get("node", {}).get("node") for step in steps
                                      if step.get("kind") == "execute"})
        self.assertEqual(before, self.payload()[1]["evidence"])

        self.replace_spec("A revised request changes the declared source input.")
        self.assertNotIn("review_a", self.executable())
        self.assertEqual(before, self.payload()[1]["evidence"])

    def corrupt_old_snapshot(self, filename, corrupt):
        self.reviewed_policy("disabled", initial=True)
        paths = [self.fixture.repo / ".zzzops" / name for name in
                 ("POLICY.json", "PROJECT.md", "PROJECT_AUDIT.md")]
        valid = {path: path.read_bytes() for path in paths}
        target = self.fixture.repo / ".zzzops" / filename
        corrupt(target)
        self.git("add", "-A", ".zzzops")
        self.git("commit", "--amend", "-qm", "tampered old policy approval")
        self.install(self.graph)
        self.produce()
        before = copy.deepcopy(self.payload()[1]["evidence"])
        for path, data in valid.items():
            path.write_bytes(data)
        self.reviewed_policy("existing_only")
        steps = self.session.checkpoint(100)
        self.assertNotIn("review_a", {step["node"]["node"] for step in steps
                                      if step.get("kind") == "execute"})
        self.assertEqual(before, self.payload()[1]["evidence"])
        self.assert_policy_diagnostic(steps)

    def test_invalid_old_project_binding_does_not_grant_policy_equivalence(self):
        self.corrupt_old_snapshot("PROJECT.md", lambda path: path.write_text(
            path.read_text() + "\nUnreviewed historical edit\n"))

    def test_invalid_old_audit_binding_does_not_grant_policy_equivalence(self):
        self.corrupt_old_snapshot("PROJECT_AUDIT.md", lambda path: path.write_text(
            path.read_text() + "\nUnreviewed historical audit edit\n"))

    def test_wrong_repository_old_policy_does_not_grant_policy_equivalence(self):
        def wrong_repository(path):
            state = json.loads(path.read_text())
            state["repository"]["identity"] = "other/repository"
            path.write_text(json.dumps(state))
        self.corrupt_old_snapshot("POLICY.json", wrong_repository)

    def test_old_policy_approval_digest_mismatch_is_distinct_from_file_bindings(self):
        def wrong_approval_digest(path):
            state = json.loads(path.read_text())
            state["approval"]["digest"] = "sha256:" + "0" * 64
            path.write_text(json.dumps(state))
            self.assertEqual([], z.validate_project_artifacts(self.fixture.repo, state))
            self.assertTrue(any("policy approval digest changed" in error
                                for error in z.validate_project_state(state)))
        self.corrupt_old_snapshot("POLICY.json", wrong_approval_digest)

    def test_missing_old_policy_does_not_grant_policy_equivalence(self):
        self.corrupt_old_snapshot("POLICY.json", lambda path: path.unlink())

    def test_malformed_old_policy_does_not_grant_policy_equivalence(self):
        self.corrupt_old_snapshot("POLICY.json", lambda path: path.write_text("{invalid json"))

    def test_old_matching_policy_beyond_sixty_four_policy_changes_fails_closed(self):
        before = self.initial_result()
        section = z._workflow_section(self.session.project, "code_quality")
        original = section["instructions"]
        # Each commit contains a separately approved substantive policy change;
        # no workflow or goal replay occurs while the bounded ancestor history grows.
        for index in range(65):
            z._workflow_section(self.session.project, "code_quality")["instructions"] = (
                original + f" Require historical check {index}.")
            self.reviewed_policy("disabled")
        self.assertEqual(65, len(self.git("rev-list", "--first-parent", "HEAD", "--", ".zzzops/POLICY.json").splitlines()) - 1)
        z._workflow_section(self.session.project, "code_quality")["instructions"] = original
        self.reviewed_policy("existing_only")
        steps = self.session.checkpoint(100)
        self.assertNotIn("review_a", {step["node"]["node"] for step in steps
                                      if step.get("kind") == "execute"})
        reasons = " ".join(str(step.get("reason", step.get("action", ""))) for step in steps)
        self.assertRegex(reasons, r"(?i)64|bound|ancestor|history")
        self.assertEqual(before, self.payload()[1]["evidence"])

    def test_two_matching_approved_ancestors_are_not_arbitrarily_selected(self):
        before = self.initial_result()
        verification = z._workflow_section(self.session.project, "verification_testing")
        verification["rationale"] += " Confirmed by a second independent review."
        self.reviewed_policy("disabled")
        self.reviewed_policy("existing_only")
        steps = self.session.checkpoint(100)
        self.assertNotIn("review_a", {step["node"]["node"] for step in steps
                                      if step.get("kind") == "execute"})
        self.assert_policy_diagnostic(steps)
        self.assertEqual(before, self.payload()[1]["evidence"])

    def test_forged_legacy_policy_digest_cannot_revalidate_result(self):
        self.initial_result()
        envelope, payload = self.payload()
        old_ref, _ = self.result("produce")
        artifact = self.read_blob(old_ref)
        artifact["provenance"]["policy"] = "sha256:" + "0" * 64
        forged = self.blob(artifact)
        payload["evidence"] = [forged if ref == old_ref else ref for ref in payload["evidence"]]
        self.replace_payload(envelope, payload)
        self.reviewed_policy("existing_only")
        steps = self.session.checkpoint(100)
        self.assertNotIn("review_a", {step["node"]["node"] for step in steps
                                      if step.get("kind") == "execute"})
        self.assert_policy_diagnostic(steps)
        self.assertEqual([forged], self.payload()[1]["evidence"])

    def test_identical_retry_after_provider_response_loss_keeps_one_result(self):
        before = self.initial_result()
        self.reviewed_policy("existing_only")
        work = self.session.acquire("review_a")
        request = self.session.submission(work, {"value": "Reviewed preserved producer result"},
                                          "ci-transition-lost-response")
        update = self.provider.update_issue
        lost = []
        def uncertain(number, payload):
            result = update(number, payload)
            if number == 100 and not lost:
                lost.append(True)
                raise z.GoalTransitionProviderError("Committed body; provider response lost")
            return result
        with mock.patch.object(self.provider, "update_issue", side_effect=uncertain):
            self.session.call(100, request, expected=None)
        self.assertTrue(lost)
        self.session.call(100, request)
        evidence = copy.deepcopy(self.payload()[1]["evidence"])
        self.assertEqual(before, evidence[:len(before)])
        self.assertEqual(2, len(evidence))
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, request)
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))
        self.assertEqual(1, len(self.provider.issues))


class PolicyCiPreStaticTests(dag.DagFixture):
    """Produce real legacy artifacts under one pre-static policy evaluator."""

    git = PolicyCiTransitionTests.git
    commit_policy = PolicyCiTransitionTests.commit_policy
    reviewed_policy = PolicyCiTransitionTests.reviewed_policy
    workspace_graph = dag.WorkspaceAuthorityPublicTests.workspace_graph

    def test_pre_static_policy_context_and_workspace_provenance_compose_with_ci_change(self):
        (self.fixture.repo / "source.py").write_text("def value():\n    return 1\n")
        (self.fixture.repo / "read_dependency.txt").write_text("stable dependency\n")
        self.session.git("add", "source.py", "read_dependency.txt")
        self.session.git("commit", "-qm", "workspace fixture baseline")
        graph = self.workspace_graph()
        self.install(graph)
        self.reviewed_policy("disabled", initial=True)
        self.install(graph)

        def pre_static(policy):
            value = copy.deepcopy(policy)
            value["sections"] = [row for row in value["sections"] if row["id"] not in
                                 {"model_routing", "autonomy_approval_parallelism"}]
            return value
        historical = z._workflow.digest(pre_static(self.session.project["policy"]))
        original_digest = z._workflow.digest
        def legacy_digest(value):
            if value == self.session.project["policy"]:
                return historical
            return original_digest(value)
        with (mock.patch.object(z._phase_evidence, "evidence_policy", side_effect=pre_static),
              mock.patch.object(z._workflow, "digest", side_effect=legacy_digest)):
            self.session.finish(self.session.acquire("charter"), {"grant": self.allocations})
            permit = {"manifest": self.produced("charter", "grant"),
                      "tasks": [entry["task"] for entry in self.allocations["allocations"].values()],
                      "policy": historical,
                      "decision": "approved"}
            self.session.finish(self.session.acquire("inspect_charter", actor="allocation-reviewer"),
                                {"permit": permit})
            self.session.finish(self.session.acquire("consent"), {"permit": permit})
            self.session.finish(self.session.acquire("alpha"), {"value": "legacy workspace"})

        authorization_ref, authorization = self.result("inspect_charter")
        authorization_artifact = self.read_blob(authorization_ref)
        self.assertEqual(historical, authorization_artifact["provenance"]["policy"])
        policy_bindings = [binding for binding in authorization["inputs"]
                           if binding["name"] == "__policy"]
        self.assertEqual(1, len(policy_bindings))
        policy_context = self.read_blob(policy_bindings[0]["source"])
        self.assertEqual(historical, policy_context["content"]["policy"])
        self.assertEqual(historical, policy_context["provenance"]["policy"])
        self.assertEqual(z._workflow.digest({"node": next(node for node in graph["nodes"]
                         if node["id"] == "inspect_charter"), "policy": historical}),
                         authorization["contract"])

        workspace_ref, workspace_result = self.result("alpha")
        workspace_artifact = self.read_blob(workspace_ref)
        self.assertEqual(historical, workspace_artifact["provenance"]["policy"])
        self.assertEqual(z._workflow.digest({"node": next(node for node in graph["nodes"]
                         if node["id"] == "alpha"), "policy": historical}),
                         workspace_result["contract"])
        workspace_bindings = [binding for binding in workspace_result["inputs"]
                              if binding["name"] == "__workspace"]
        self.assertEqual(1, len(workspace_bindings))
        workspace = self.read_blob(workspace_bindings[0]["source"])
        self.assertEqual(historical, workspace["provenance"]["policy"])
        evidence = copy.deepcopy(self.payload()[1]["evidence"])
        self.reviewed_policy("existing_only")
        names = self.names()
        self.assertIn("observe_alpha", names)
        self.assertNotIn("alpha", names)
        self.assertEqual(evidence, self.payload()[1]["evidence"])


class PolicyCiTerminalTests(dag.DagFixture):
    git = PolicyCiTransitionTests.git
    commit_policy = PolicyCiTransitionTests.commit_policy
    reviewed_policy = PolicyCiTransitionTests.reviewed_policy
    setup_publication = publication.GenericPublicationPublicTests.setup_publication
    provider_command = publication.GenericPublicationPublicTests.provider_command
    mark_merged = publication.GenericPublicationPublicTests.mark_merged
    configure = publication.GenericPublicationPublicTests.configure
    submit_role = publication.GenericPublicationPublicTests.submit_role
    authorize_context = publication.GenericPublicationPublicTests.authorize_context
    observed_value = publication.GenericPublicationPublicTests.observed_value
    approve_publication = publication.GenericPublicationPublicTests.approve_publication
    integration_request = publication.GenericPublicationPublicTests.integration_request

    def setUp(self):
        super().setUp()
        self.setup_publication()

    def prior_authorization(self, mode):
        self.reviewed_policy(mode, initial=True)
        self.git("branch", "-f", "goal-child", "dev")
        self.fixture.base_oid = self.git("rev-parse", "dev")
        self.fixture.head_oid = self.fixture.base_oid
        self.observation.update(base_oid=self.fixture.base_oid, head_oid=self.fixture.head_oid)
        self.configure()
        self.authorize_context()
        authority = self.approve_publication()
        self.submit_role("finish", "Complete exact evidence")
        return authority, self.integration_request(authority), copy.deepcopy(self.payload()[1]["evidence"])

    def sync_current_head(self):
        self.git("branch", "-f", "goal-child", "dev")
        current = self.git("rev-parse", "dev")
        self.fixture.base_oid = current
        self.fixture.head_oid = current
        self.observation.update(base_oid=current, head_oid=current, review_verified=True)

    def test_tightened_exact_head_ci_rejects_prior_authorization_and_failed_checks(self):
        _authority, request, original = self.prior_authorization("disabled")

        self.reviewed_policy("inspect_exact_pr_head")
        self.observation["checks_verified"] = False
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)CI|checks|stale|current|authorization|evidence")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertEqual([], self.merge_calls)
        self.assertEqual(original, self.payload()[1]["evidence"])

        self.observation["checks_verified"] = True
        self.observation["checks_present"] = False
        response = self.session.call(100, {**request, "request_id": "absent-checks"}, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)CI|checks|stale|current|authorization|evidence")
        self.assertEqual([], self.merge_calls)
        self.observation["checks_present"] = True
        self.observation["head_oid"] = "e" * 40
        response = self.session.call(100, {**request, "request_id": "moved-head"}, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)head|stale|current|authorization|evidence")
        self.assertEqual([], self.merge_calls)

    def test_existing_only_tightening_requires_new_current_head_authorization(self):
        old_authority, old_request, original = self.prior_authorization("existing_only")
        self.reviewed_policy("inspect_exact_pr_head")
        self.observation["checks_verified"] = False
        rejected = self.session.call(100, old_request, expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)CI|checks|stale|current|authorization|evidence")
        self.assertEqual([], self.merge_calls)
        self.assertEqual(original, self.payload()[1]["evidence"])

        self.sync_current_head()
        self.observation.update(checks_present=True, checks_verified=True)
        self.assertIn("observe", self.names())
        self.submit_role("observe", self.observed_value())
        self.submit_role("review", "Fresh exact head and passing CI reviewed", actor="new-head-reviewer")
        self.submit_role("approve", {"subject": self.produced("observe"),
            "review": self.produced("review"), "policy": dag.content_hash(self.session.project["policy"]),
            "decision": "approved"})
        current_authority = self.produced("approve")
        self.assertNotEqual(old_authority, current_authority)
        self.submit_role("finish", "Current head terminal proof")
        self.session.call(100, self.integration_request(current_authority))
        self.assertEqual(1, len(self.merge_calls))

    def test_ci_loosening_preserves_scope_approval_but_refreshes_head_and_review(self):
        old_authority, _old_request, _original = self.prior_authorization("inspect_exact_pr_head")
        consent = self.result("consent")[0]
        self.reviewed_policy("disabled")
        self.sync_current_head()
        self.observation.update(checks_present=True, checks_verified=False)
        self.assertEqual(consent, self.result("consent")[0])
        self.assertIn("observe", self.names())
        self.submit_role("observe", self.observed_value())
        self.submit_role("review", "Fresh provider head and review observed", actor="new-head-reviewer")
        self.submit_role("approve", {"subject": self.produced("observe"),
            "review": self.produced("review"), "policy": dag.content_hash(self.session.project["policy"]),
            "decision": "approved"})
        authority = self.produced("approve")
        self.assertNotEqual(old_authority, authority)
        self.submit_role("finish", "Current disabled-CI terminal proof")
        self.session.call(100, self.integration_request(authority))
        self.assertEqual(1, len(self.merge_calls))


class PolicyCiDefaultDagTests(dag.DagFixture):
    """A fresh goal follows the shipped phase graph through reviewed code work."""

    git = PolicyCiTransitionTests.git
    commit_policy = PolicyCiTransitionTests.commit_policy
    reviewed_policy = PolicyCiTransitionTests.reviewed_policy
    default_decomposition = dag.DefaultCorrectionPublicTests.default_decomposition
    review = dag.DefaultCorrectionPublicTests.review
    decomposition_authorization = dag.DefaultCorrectionPublicTests.decomposition_authorization

    def setUp(self):
        super().setUp()
        template = json.loads((dag.old.fixtures.PLUGIN_ROOT /
            "zzzops/templates/project-goals/INIT_PLAN.json").read_text())
        self.shipped = z._workflow_section(template, "workflow_adherence")["configuration"]["phase_dag"]
        self.install(self.shipped)

    def test_shipped_requirements_spec_test_and_implementation_survive_ci_transition(self):
        self.reviewed_policy("disabled", initial=True)
        remote_dir = tempfile.TemporaryDirectory()
        self.addCleanup(remote_dir.cleanup)
        remote = Path(remote_dir.name) / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        self.session.git("remote", "add", "origin", str(remote))
        self.default_decomposition()
        self.session.finish(self.session.acquire("decomposition_review"), {
            "value": self.review("approved", "Atomic disposition accepted"),
            "authorization": self.decomposition_authorization()})
        self.session.finish(self.session.acquire("retain_decomposition_findings"), {
            "value": {"items": {}, "rationale": "No admitted decomposition findings"}})

        test_work = self.session.acquire("test_design")
        test_tree = Path(test_work.get("managed_worktree", {"path": self.fixture.repo})["path"])
        (test_tree / "behavior_test.py").write_text(
            "from source import value\nassert value() == 2\n")
        subprocess.run(["git", "add", "behavior_test.py"], cwd=test_tree, check=True)
        subprocess.run(["git", "commit", "-qm", "test(goal-100): probe expected value"],
                       cwd=test_tree, check=True)
        request = self.session.submission(test_work, {"value": "Test returns two"}, "ci-test-design")
        request.update(workspace_checks=[[sys.executable, "-B", "behavior_test.py"]],
                       verification_expectation="observed")
        self.session.call(100, request)
        self.session.finish(self.session.acquire("test_verification"), {
            "value": "Observed the exact red behavior test"})
        self.session.finish(self.session.acquire("test_design_review"), {
            "value": self.review("approved", "Red test exercises the required behavior")})
        self.session.finish(self.session.acquire("retain_test_design_findings"), {
            "value": {"items": {}, "rationale": "No admitted test findings"}})

        implement = self.session.acquire("implement")
        implement_tree = Path(implement.get("managed_worktree", {"path": self.fixture.repo})["path"])
        (implement_tree / "source.py").write_text("def value():\n    return 2\n")
        subprocess.run(["git", "add", "source.py"], cwd=implement_tree, check=True)
        subprocess.run(["git", "commit", "-qm", "feat(goal-100): return expected value"],
                       cwd=implement_tree, check=True)
        request = self.session.submission(implement, {"value": "Implementation returns two"},
                                          "ci-implementation")
        request.update(workspace_checks=[[sys.executable, "-B", "behavior_test.py"]],
                       verification_expectation="passed")
        self.session.call(100, request)
        prior = {name: self.result(name)[0] for name in
                 ("requirements", "spec", "test_design", "implement")}
        evidence = copy.deepcopy(self.payload()[1]["evidence"])
        self.reviewed_policy("existing_only")
        steps = self.session.checkpoint(100)
        active = {step.get("node", {}).get("node") for step in steps
                  if step.get("kind") == "execute"}
        self.assertFalse(active & prior.keys(), sorted(active))
        self.assertEqual(prior, {name: self.result(name)[0] for name in prior})
        self.assertEqual(evidence, self.payload()[1]["evidence"])
        self.assertEqual(1, len(self.provider.issues))

        consumed = self.fixture.repo / "product.txt"
        original = consumed.read_bytes()
        try:
            consumed.write_text("changed consumed workspace input\n")
            drifted = self.session.checkpoint(100)
            self.assertTrue(any(step.get("node", {}).get("node") in {"test_design", "implement"}
                                and step.get("kind") in {"execute", "dependency", "repair"}
                                for step in drifted), drifted)
            self.assertEqual(evidence, self.payload()[1]["evidence"])
        finally:
            consumed.write_bytes(original)
        restored = self.session.checkpoint(100)
        self.assertFalse({step.get("node", {}).get("node") for step in restored
                          if step.get("kind") == "execute"} & prior.keys())
