"""Behavioral regressions for dependency-scoped workflow portfolio reads."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_zzzops as fixtures
from test_evidence_dag_journeys import DagFixture, run_generic_regressions


z = fixtures.zzzops


def project():
    return {
        "backend": "github_issues",
        "repository": {"identity": "owner/repo"},
        "policy": {"sections": [
            {"id": "autonomy_approval_parallelism",
             "configuration": fixtures.TEST_AUTONOMY_CONFIGURATION},
            fixtures.TEST_RIGOR_POLICY,
        ]},
    }


class PortfolioScopeTests(unittest.TestCase):
    def setUp(self):
        self.portfolio = fixtures.PortfolioTests()

    def issue(self, number, **changes):
        return self.portfolio.issue(number, **changes)

    def test_targeted_workflow_context_skips_unrelated_bodies_and_prs_before_fresh_publication(self):
        implementation = {"branch": "goal/x", "base": "main", "target": "main",
                          "pr": "https://github.com/owner/repo/pull/11",
                          "review": {"status": "not_started", "checkpoint": None}}
        issues = [self.issue(1), self.issue(2, implementation=implementation), self.issue(3)]
        bodies = {row["number"]: {"body": row["body"], "updated_at": row["updated_at"]}
                  for row in issues}
        hydrated = []
        def read_bodies(_repo, _gh, _owner, _name, selected):
            hydrated.extend(selected)
            return ({number: bodies[number] for number in hydrated}, 10, 1)
        def gateway(repo, **scope):
            return z.github_repository_portfolio_snapshot(repo, project(), **scope)[1]
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(z.shutil, "which", return_value="gh"), \
             mock.patch.object(z, "github_repository_goal_index",
                               return_value=({}, issues, [], 0, 1, 0)), \
             mock.patch.object(z, "_github_goal_bodies", side_effect=read_bodies), \
             mock.patch.object(z, "_github_goal_relations", return_value=({}, 0, 0)), \
             mock.patch.object(z, "_github_pull_request_states", return_value=({}, 0, 0)) as prs, \
             mock.patch.object(z, "portfolio_snapshot", side_effect=gateway), \
             mock.patch.object(z, "GitHubGoalTransitionAdapter", return_value=mock.Mock()):
            _issue, goal = z._workflow.Workflow(z, Path(directory), project()).read(1)
        self.assertEqual(1, goal["key"])
        self.assertEqual([1], hydrated)
        prs.assert_not_called()
        run_generic_regressions(
            self,
            "test_workflow_publication_contract.WorkflowPublicationContractTests."
            "test_provider_head_or_base_drift_requires_local_sync",
        )

    def test_scheduling_inventory_is_complete_and_unavailable_inventory_fails_closed(self):
        """Capacity admission sees every live owner and never treats failure as empty."""
        run_generic_regressions(
            self,
            "test_workflow_policy_enforcement.GenericWorkerCapacityTests."
            "test_other_goal_unresolved_owner_consumes_reviewed_capacity_until_observed_stop",
        )
        case = DagFixture()
        case.setUp()
        self.addCleanup(case.doCleanups)
        target = next(step for step in case.session.checkpoint(100) if step.get("kind") == "execute")
        request = {**target["start"], "policy_receipt": json.loads(
            Path(target["policy"]["path"]).read_text())["policy_receipt"]}
        case.session.portfolio_snapshot = mock.Mock(side_effect=ValueError("ownership inventory unavailable"))
        rejected = case.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(rejected), r"(?i)inventory|portfolio|unavailable|repair")

    def test_one_changed_marker_reparses_only_that_record(self):
        first, second = self.issue(1), self.issue(2)
        selected = [first, second]
        bodies = {row["number"]: {"body": row["body"], "updated_at": row["updated_at"]}
                  for row in selected}
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / ".zzzops").mkdir()
            with mock.patch.object(z.shutil, "which", return_value="gh"), \
                 mock.patch.object(z, "github_repository_goal_index",
                                   return_value=({}, selected, [], 0, 1, 0)), \
                 mock.patch.object(z, "_github_goal_bodies", return_value=(bodies, 0, 1)), \
                 mock.patch.object(z, "_github_goal_relations", return_value=({}, 0, 0)), \
                 mock.patch.object(z, "_github_pull_request_states", return_value=({}, 0, 0)):
                z.github_repository_portfolio_snapshot(repo, project())
            changed = self.issue(1, status="in_progress")
            changed["updated_at"] = "2026-10-03T00:00:00Z"
            selected = [changed, second]
            bodies = {1: {"body": changed["body"], "updated_at": changed["updated_at"]}}
            with mock.patch.object(z.shutil, "which", return_value="gh"), \
                 mock.patch.object(z, "github_repository_goal_index",
                                   return_value=({}, selected, [], 0, 1, 0)), \
                 mock.patch.object(z, "_github_goal_bodies", return_value=(bodies, 0, 1)), \
                 mock.patch.object(z, "_github_goal_relations", return_value=({}, 0, 0)), \
                 mock.patch.object(z, "_github_pull_request_states", return_value=({}, 0, 0)), \
                 mock.patch.object(z, "github_goal_record", wraps=z.github_goal_record) as parse:
                z.github_repository_portfolio_snapshot(repo, project())
        self.assertEqual({1}, {call.args[0]["number"] for call in parse.call_args_list})

    def test_malformed_or_repository_mismatched_cache_refreshes_exact_records(self):
        issues = [self.issue(1), self.issue(2)]
        issues[0]["body"] = issues[0]["body"].replace("Useful work.", "Exact first body.")
        issues[1]["body"] = issues[1]["body"].replace("Useful work.", "Exact second body.")
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / ".zzzops").mkdir()
            cache = z._portfolio_cache_path(repo)
            plausible_mismatch = {
                "schema_version": 1, "identity": "owner/repo", "include_feedback": False,
                "marker": [{"number": row["number"], "updated_at": row["updated_at"]} for row in issues],
                "bodies": {str(row["number"]): row["body"] for row in issues},
                "records": {"1": {**z.github_goal_record(issues[1]), "key": 1},
                            "2": z.github_goal_record(issues[1])},
            }
            for poisoned in ("not json", json.dumps({
                    "schema_version": 1, "identity": "other/repo",
                    "include_feedback": False, "marker": [], "bodies": {}, "records": {},
            }), json.dumps(plausible_mismatch)):
                cache.write_text(poisoned, encoding="utf-8")
                hydration_processes = 0 if poisoned == json.dumps(plausible_mismatch) else 1
                with self.subTest(cache=poisoned[:12]), \
                     mock.patch.object(z.shutil, "which", return_value="gh"), \
                     mock.patch.object(z, "github_repository_goal_index",
                                       return_value=({}, issues, [], 0, 1, 0)), \
                     mock.patch.object(z, "_github_goal_bodies", return_value=({
                         row["number"]: {"body": row["body"], "updated_at": row["updated_at"]}
                         for row in issues}, 100, hydration_processes)), \
                     mock.patch.object(z, "_github_goal_relations", return_value=({}, 0, 0)), \
                     mock.patch.object(z, "_github_pull_request_states", return_value=({}, 0, 0)), \
                     mock.patch.object(z, "github_goal_record", wraps=z.github_goal_record) as parse:
                    snapshot = z.github_repository_portfolio_snapshot(repo, project())[1]
                self.assertEqual([1, 2], [row["key"] for row in snapshot["goals"]])
                self.assertIn("Exact first body.", snapshot["goals"][0]["human_spec"])
                self.assertEqual({1, 2}, {call.args[0]["number"] for call in parse.call_args_list})

    def test_targeted_closed_dependency_is_present_without_unrelated_closed_history(self):
        open_goal = self.issue(1, depends_on=[2])
        needed = self.issue(2, status="done")
        unrelated = self.issue(3, status="done")
        bodies = {1: {"body": open_goal["body"], "updated_at": open_goal["updated_at"]}}
        with mock.patch.object(z.shutil, "which", return_value="gh"), \
             mock.patch.object(z, "github_repository_goal_index",
                               return_value=({}, [open_goal], [], 0, 1, 0)), \
             mock.patch.object(z, "_github_goal_bodies", return_value=(bodies, 0, 1)), \
             mock.patch.object(z, "_github_goal_relations", return_value=({2: needed}, 20, 1)) as relations, \
             mock.patch.object(z, "_github_pull_request_states", return_value=({}, 0, 0)):
            snapshot = z.github_repository_portfolio_snapshot(Path("."), project())[1]
        self.assertEqual([1, 2], [row["key"] for row in snapshot["goals"]])
        relations.assert_called_once_with(Path("."), "gh", "owner", "repo", [2])

    def test_provider_drift_still_rejects_stale_inflight_result(self):
        run_generic_regressions(
            self,
            "test_evidence_dag_journeys.EvidenceDagPublicTests."
            "test_semantic_input_drift_rejects_inflight_result_and_bookkeeping_does_not",
        )


if __name__ == "__main__":
    unittest.main()
