"""Request-scoped workflow reads and self-contained dispatch contracts."""

from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import test_zzzops as fixtures
import test_evidence_dag_journeys as dag_fixtures
import test_workflow_publication_contract as publication_fixtures


z = fixtures.zzzops


class MemoryIssueAdapter:
    repository = "synthetic/project"

    def __init__(self, issues):
        self.issues = issues
        self.reads = 0

    def get_issue(self, number):
        self.reads += 1
        return copy.deepcopy(self.issues[number])

    def get_issue_comments(self, number):
        return []


class WorkflowInvocationCacheTests(unittest.TestCase):
    def test_real_public_v2_checkpoint_uses_gateway_without_direct_issue_or_pr_capability(self):
        case = dag_fixtures.DagFixture()
        case.setUp()
        self.addCleanup(case.doCleanups)
        snapshot = case.session.portfolio_snapshot()
        case.session.portfolio_snapshot = lambda *_args, **_kwargs: copy.deepcopy(snapshot)
        direct_issue = case.provider.get_issue
        direct_pr = getattr(case.provider, "get_pull_request", None)
        case.provider.get_issue = mock.Mock(side_effect=AssertionError(
            "read-only checkpoint bypassed the hydrated gateway"))
        if direct_pr is not None:
            case.provider.get_pull_request = mock.Mock(side_effect=AssertionError(
                "read-only checkpoint fetched a PR directly"))

        steps = case.session.checkpoint(100)

        self.assertTrue(any(step.get("kind") == "execute" for step in steps))
        case.provider.get_issue.assert_not_called()
        if direct_pr is not None:
            case.provider.get_pull_request.assert_not_called()
        case.provider.get_issue = direct_issue
        if direct_pr is not None:
            case.provider.get_pull_request = direct_pr

    def test_public_checkpoint_uses_real_gateway_and_reuses_exact_provider_bytes(self):
        case = dag_fixtures.DagFixture(); case.setUp()
        self.addCleanup(case.doCleanups)
        snapshot = case.session.portfolio_snapshot()
        case.session.portfolio_snapshot = lambda *_a, **_k: copy.deepcopy(snapshot)
        issue = copy.deepcopy(case.provider.issues[100])
        case.session.provider_issue_snapshot = z.provider_issue_snapshot
        with mock.patch.object(z, '_github_goal_relations', return_value=({100: issue}, 10, 1)) as metadata, \
             mock.patch.object(z, '_github_goal_bodies', return_value=({100: {'body': issue['body']}}, 10, 1)) as bodies, \
             mock.patch.object(case.provider, 'get_issue', side_effect=AssertionError('Direct issue read')):
            steps = case.session.checkpoint(100)
        self.assertTrue(any(step.get('kind') == 'execute' for step in steps))
        metadata.assert_called_once()
        bodies.assert_called_once()
        self.assertEqual([100], metadata.call_args.args[-1])
        self.assertEqual([100], bodies.call_args.args[-1])

    def test_pr_gateway_shares_invocation_snapshot_and_invalidates_on_refresh(self):
        repo = Path('.')
        rows = [{'number': 100}]
        bodies = {100: {'repository_context': {'pr': 'https://github.com/owner/repo/pull/7'}}}
        observed = {100: {'head_oid': 'a' * 40}}
        with mock.patch.object(z, '_observe_pull_request_states', side_effect=lambda *_a: (copy.deepcopy(observed), 10, 1)) as provider:
            with z.provider_read_invocation():
                first, _, _ = z._github_pull_request_states(repo, 'gh', rows, bodies)
                first[100]['head_oid'] = 'tampered'
                second, size, count = z._github_pull_request_states(repo, 'gh', rows, bodies)
                self.assertEqual('a' * 40, second[100]['head_oid'])
                self.assertEqual((0, 0), (size, count))
                self.assertEqual(1, provider.call_count)
                observed[100]['head_oid'] = 'b' * 40
                z.invalidate_provider_reads(repo, 'owner/repo')
                self.assertEqual('b' * 40, z._github_pull_request_states(repo, 'gh', rows, bodies)[0][100]['head_oid'])
                self.assertEqual(2, provider.call_count)
            with z.provider_read_invocation():
                z._github_pull_request_states(repo, 'gh', rows, bodies)
                self.assertEqual(3, provider.call_count)

    def test_real_locked_v2_mutation_retains_fresh_exact_issue_read(self):
        case = dag_fixtures.DagFixture()
        case.setUp()
        self.addCleanup(case.doCleanups)
        original = case.provider.get_issue
        reads = []
        def observed(number):
            reads.append(number)
            return original(number)
        case.provider.get_issue = observed

        work = case.session.acquire("produce")
        reads.clear()
        case.session.finish(work, {"value": "fresh locked mutation"})

        self.assertIn(100, reads)

    def test_attributed_merge_findings_do_not_block_independent_reads(self):
        goals = [{'key': 433, 'status': 'ready'}, {'key': 435, 'status': 'ready'}]
        portfolio = {'complete': False, 'goals': goals, 'findings': [
            {'goal': 433, 'code': 'merged_pr_stale_checkpoint', 'detail': 'reviewed_head_mismatch'}]}
        api = self.api(MemoryIssueAdapter({}), portfolio)
        engine = z._workflow.Workflow(api, Path('.'), {}, {})
        self.assertEqual(goals, engine.portfolio(), 'Internal context reads must preserve goal-local isolation too')
        self.assertEqual(435, engine.read(435)[1]['key'])
        self.assertEqual([], engine.validation_blockers(goals[1]))
        self.assertEqual(433, engine.validation_blockers(goals[0])[0]['goal'])
        goals[1]['depends_on'] = [433]
        self.assertEqual(433, engine.validation_blockers(goals[1])[0]['goal'])
        portfolio['error'] = 'provider inventory truncated'
        with self.assertRaises(ValueError):
            engine.portfolio(allow_invalid=True)

    def test_merged_goal_emits_exact_public_reconciliation_contract(self):
        # Observed merge is data: operational integration cannot manufacture
        # the required post-effect Result or semantic completion.
        case = publication_fixtures.GenericPublicationPublicTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.install(case.with_merge_observation(copy.deepcopy(case.graph)))
        case.authorize_context()
        authority = case.approve_publication()
        request = case.integration_request(authority)
        case.session.call(100, request)
        self.assertEqual(1, len(case.merge_calls))
        self.assertTrue(case.observation["merged"])
        self.assertEqual("open", case.provider.issues[100]["state"])
        self.assertNotIn("finish", case.names())
        steps = case.session.checkpoint(100)
        reconcile = next(step for step in steps if step.get("kind") == "reconcile")
        self.assertEqual("root", reconcile["assignment"])
        envelope, payload = case.payload()
        self.assertEqual(dag_fixtures.content_hash(envelope), reconcile["submission"]["expected_digest"])
        self.assertEqual(dag_fixtures.content_hash(case.observation), reconcile["submission"]["expected_merge"])
        before = copy.deepcopy((case.provider.issues, case.provider.comments))
        stale = {**reconcile["submission"], "expected_merge": "sha256:" + "0" * 64}
        case.session.call(100, stale, expected=2)
        self.assertEqual(before, (case.provider.issues, case.provider.comments))
        case.session.call(100, reconcile["submission"])
        self.assertEqual(payload["evidence"], case.payload()[1]["evidence"],
                         "Operational reconciliation cannot mint semantic Results")
        self.assertEqual("open", case.provider.issues[100]["state"])
        self.assertNotIn("finish", case.names())
        acquired = case.session.acquire("observed_merge")
        before = copy.deepcopy((case.provider.issues, case.provider.comments))
        value = case.merge_value()
        case.session.call(100, case.session.submission(acquired,
            {"value": {**value, "head_oid": "a" * 40}}, "wrong-observed-head"), expected=2)
        self.assertEqual(before, (case.provider.issues, case.provider.comments))
        case.session.finish(acquired, {"value": value})
        self.assertIn("finish", case.names())
        case.submit_role("finish", "Current observed merge accepted")
        self.assertFalse(case.session.ready())
        final = next(step for step in case.session.checkpoint(100) if step.get("kind") == "reconcile")
        case.session.call(100, final["submission"])
        self.assertEqual("closed", case.provider.issues[100]["state"])
        before = copy.deepcopy((case.provider.issues, case.provider.comments))
        terminal = case.session.checkpoint(100)
        self.assertEqual(1, len(terminal))
        self.assertEqual("terminal_report", terminal[0]["kind"])
        self.assertEqual("complete", terminal[0]["state"])
        self.assertNotIn("submission", terminal[0])
        self.assertEqual(before, (case.provider.issues, case.provider.comments))

    def api(self, adapter, portfolio):
        return SimpleNamespace(
            _project_repository_identity=lambda project: "synthetic/project",
            GitHubGoalTransitionAdapter=lambda repo, repository: adapter,
            github_goal_record=lambda issue: copy.deepcopy(issue["record"]),
            empty_phase_evidence=lambda: {"schema_version": 2, "records": {}, "reviews": {}, "human_approvals": {}, "withdrawals": []},
            portfolio_snapshot=mock.Mock(return_value=portfolio),
        )

    def test_reads_and_portfolio_are_cached_only_for_one_workflow_instance(self):
        issues = {1: {"record": {"key": 1, "title": "Initial", "status": "ready"}}}
        adapter = MemoryIssueAdapter(issues)
        portfolio = {"complete": True, "valid": True, "goals": [issues[1]["record"]]}
        api = self.api(adapter, portfolio)
        engine = z._workflow.Workflow(api, Path("."), {}, {})

        first_issue, first = engine.read(1)
        first["title"] = "Caller mutation"
        first_issue["number"] = 99
        self.assertEqual("Initial", engine.read(1)[1]["title"])
        engine.portfolio()[0]["status"] = "done"
        self.assertEqual("ready", engine.portfolio()[0]["status"])
        self.assertEqual(0, adapter.reads)
        api.portfolio_snapshot.assert_called_once()

        issues[1]["record"]["title"] = "Provider update"
        another = z._workflow.Workflow(api, Path("."), {}, {})
        self.assertEqual("Provider update", another.read(1)[1]["title"])
        self.assertEqual(0, adapter.reads)

    def test_storage_lock_and_successful_save_each_invalidate_cached_authority(self):
        issues = {1: {"record": {"key": 1, "title": "Initial"}}}
        adapter = MemoryIssueAdapter(issues)
        api = self.api(adapter, {"complete": True, "valid": True, "goals": [issues[1]["record"]]})
        api.GitHubReservationAdapter = lambda repo, repository: object()
        api.acquire_storage_lock = lambda *args: {"acquired": True, "expires_at": 10**12}
        api.release_storage_lock = lambda *args: {"released": True}
        api.renew_storage_lock = lambda *args: {"acquired": True, "expires_at": 10**12}
        api.GOAL_TRANSITION_SCHEMA_VERSION = 1
        def apply_transition(_adapter, _repository, _number, _transition, **_observed):
            issues[1]["record"]["title"] = "Saved provider state"
            return {"number": 1}
        api.apply_goal_transition = apply_transition
        engine = z._workflow.Workflow(api, Path("."), {}, {})

        engine.read(1)
        issues[1]["record"]["title"] = "Changed before lock"
        with engine.locked():
            issue, current = engine.read(1)
            self.assertEqual("Changed before lock", current["title"])
            engine.save(issue, {"key": 1, "revision": 1, "digest": "digest"}, {"status": "ready"})
            self.assertEqual("Saved provider state", engine.read(1)[1]["title"])
        self.assertEqual(0, adapter.reads)

    def test_public_checkpoint_reuses_the_validated_workflow_engine(self):
        engine = mock.Mock()
        engine.portfolio.return_value = [{"key": 1, "status": "done", "priority": "P1"}]
        engine.api.github_repository_goal_index.return_value = (
            {"usable": True}, [], [], 0, 0, [],
        )
        project = {
            "backend": "github_issues", "repository": {"identity": "synthetic/project"},
            "policy": {"sections": [{
                "id": "autonomy_approval_parallelism", "configuration": {"max_workers": 3},
            }]},
        }
        with (
            mock.patch.object(z._package, "package_status", return_value={"ok": True, "version": "1", "revision": "abc"}),
            mock.patch.object(z._installation, "validation_status", return_value={"required": False}),
            mock.patch.object(z, "workflow_context_step", return_value=None),
            mock.patch.object(z, "reviewed_project_state", return_value=project),
            mock.patch.object(z._workflow, "Workflow", return_value=engine) as constructor,
            mock.patch.object(z._workflow_admin, "handle", return_value=None),
        ):
            result = z._workflow.public_run(z, Path("."), "execute", "$execute-zzzops", {}, None, None)

        self.assertEqual({"next_steps": [{
            "kind": "terminal_report", "assignment": "root", "state": "complete",
            "action": "All goals are complete or the portfolio is empty. Report workflow exhaustion; no CLI command is required.",
        }]}, result)
        constructor.assert_called_once()
        self.assertEqual(2, engine.portfolio.call_count)


class AssessContractTests(unittest.TestCase):
    def test_assess_step_carries_exact_goal_read_contract_and_phase_inputs(self):
        # Generic execution exposes the exact contract, consumed specification,
        # policy receipt and input hash without a privileged assess phase.
        case = dag_fixtures.DagFixture()
        case.setUp()
        self.addCleanup(case.doCleanups)
        graph = copy.deepcopy(case.graph)
        graph["nodes"][0]["inputs"] = {"request": dag_fixtures.spec_input()}
        case.install(graph)
        step = next(item for item in case.session.ready() if item["node"]["node"] == "produce")
        self.assertEqual("execute", step["kind"])
        self.assertEqual(100, step["goal"])
        self.assertEqual(step["node"], step["input_envelope"]["node"])
        contract = next(node for node in case.graph["nodes"] if node["id"] == "produce")
        self.assertEqual(dag_fixtures.content_hash({"node": contract, "policy": dag_fixtures.content_hash(case.session.project["policy"])}),
                         step["input_envelope"]["contract"])
        self.assertEqual(contract["prompt"], step["instruction"])
        _, payload = case.payload()
        binding = next(item for item in step["input_envelope"]["inputs"] if item["name"] == "request")
        self.assertEqual(payload["spec"], binding["source"])
        specification = case.session.read(100, binding["source"])
        self.assertEqual("specification", specification["type"])
        self.assertEqual(dag_fixtures.content_hash(specification), binding["source"]["hash"])
        self.assertEqual(step["input_hash"], step["start"]["input_hash"])
        self.assertEqual(step["node"], step["start"]["node"])
        acquired = case.session.acquire("produce")
        self.assertEqual(step["input_hash"], acquired["lease"]["fingerprint"])
        self.assertEqual("submit", acquired["submission"]["operation"])
        self.assertEqual(step["node"], acquired["submission"]["node"])
        before = copy.deepcopy((case.provider.issues, case.provider.comments))
        request = case.session.submission(acquired, {"value": "unauthorized"}, "wrong-worker")
        request["actor"] = "different-worker"
        case.session.call(100, request, expected=2)
        self.assertEqual(before, (case.provider.issues, case.provider.comments))
        case.session.finish(acquired, {"value": "exact assigned work"})


if __name__ == "__main__":
    unittest.main()
