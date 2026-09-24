"""Request-scoped workflow reads and self-contained dispatch contracts."""

from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import test_zzzops as fixtures


z = fixtures.zzzops


class MemoryIssueAdapter:
    repository = "synthetic/project"

    def __init__(self, issues):
        self.issues = issues
        self.reads = 0

    def get_issue(self, number):
        self.reads += 1
        return copy.deepcopy(self.issues[number])


class WorkflowInvocationCacheTests(unittest.TestCase):
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
        engine = z._workflow.Workflow(self.api(MemoryIssueAdapter({}), {}), Path('.'), {}, {})
        goal = {'key': 433, 'digest': 'a' * 64, 'status': 'ready',
                'pull_request': {'merged': True, 'head_oid': 'head'}}
        with mock.patch.object(engine, 'classify_merge', return_value={'status': 'merged_stale', 'reasons': ['reviewed_head_mismatch']}):
            step = engine.reconciliation_step(goal)
        self.assertEqual('reconcile', step['submission']['operation'])
        self.assertEqual(goal['digest'], step['submission']['expected_digest'])
        self.assertEqual(z._workflow.digest(goal['pull_request']), step['submission']['expected_merge'])
        goal['status'] = 'done'
        self.assertIsNone(engine.reconciliation_step(goal))

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
        def apply_transition(_adapter, _repository, _number, _transition):
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
        goal = {
            "key": 7, "title": "Synthetic goal", "url": "https://invalid.example/issues/7",
            "status": "ready", "needs_human": False, "claim": None, "workflow": None,
        }
        phase_input = {"goal_spec": "sha256:" + "1" * 64, "policy": "sha256:" + "2" * 64}
        adapter = MemoryIssueAdapter({7: {"record": goal}})
        api = SimpleNamespace(
            _project_repository_identity=lambda project: "synthetic/project",
            GitHubGoalTransitionAdapter=lambda repo, repository: adapter,
            github_goal_record=lambda issue: copy.deepcopy(issue["record"]),
            _workflow_section=lambda project, section: {"configuration": {}},
            workflow_step_plan=lambda *args, **kwargs: {
                "next_steps": [{"kind": "execute", "phase": "understand", "assignment": "root", "selection": {"model": "synthetic", "effort": "low"}}],
                "frontier": {"blocked": []},
            },
            empty_phase_evidence=lambda: {"schema_version": 2, "records": {}, "reviews": {}, "human_approvals": {}, "withdrawals": []},
            portfolio_snapshot=lambda _repo: {"complete": True, "valid": True, "goals": [copy.deepcopy(goal)]},
        )
        engine = z._workflow.Workflow(api, Path("."), {}, {})
        engine.context = mock.Mock(return_value=({}, {"understand": {}}, {"understand": phase_input}, {}))

        step = engine.step(7)[0]

        self.assertEqual("assess", step["kind"])
        self.assertEqual("Synthetic goal", step["title"])
        self.assertEqual(phase_input, step["input_envelope"])
        self.assertEqual(phase_input["goal_spec"], step["goal_specification"]["hash"])
        self.assertEqual({"operation": "read", "phase": "understand"}, step["goal_specification"]["read"])
        self.assertEqual("https://invalid.example/issues/7", step["goal_specification"]["reference"])
        self.assertEqual("7", step["command"][step["command"].index("--goal") + 1])
        self.assertEqual(step["input_hash"], step["submission"]["input_hash"])


if __name__ == "__main__":
    unittest.main()
