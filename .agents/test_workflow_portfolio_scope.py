"""Behavioral regressions for dependency-scoped workflow portfolio reads."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_zzzops as fixtures
from test_evidence_dag_journeys import run_generic_regressions


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

    def snapshot(self, repo, issues, *, include_history=False):
        bodies = {
            row["number"]: {"body": row["body"], "updated_at": row["updated_at"]}
            for row in issues if row["state"] == "open"
        }
        with mock.patch.object(z.shutil, "which", return_value="gh"), \
             mock.patch.object(z, "github_repository_goal_index",
                               return_value=({}, issues, [], 0, 1, 0)), \
             mock.patch.object(z, "_github_goal_bodies", return_value=(bodies, 0, 1)), \
             mock.patch.object(z, "_github_goal_relations", return_value=({}, 0, 0)), \
             mock.patch.object(z, "_github_pull_request_states", return_value=({}, 0, 0)) as prs:
            value = z.github_repository_portfolio_snapshot(
                repo, project(), include_history=include_history,
            )[1]
        return value, prs

    def test_targeted_read_hydrates_only_consumed_goal_and_omits_pr_observation(self):
        """A single-goal read must not turn into portfolio comment/PR hydration."""
        goals = [{**z.github_goal_record(self.issue(number)), "schema_version": 2,
                  "envelope": {"payload": {"hash": f"payload-{number}"}}}
                 for number in (1, 2, 3)]
        snapshot = z.build_portfolio_snapshot("github_issues", goals, reads=1, raw_bytes=0)
        api = mock.Mock(wraps=z)
        api._project_repository_identity = z._project_repository_identity
        api.GitHubGoalTransitionAdapter = mock.Mock(return_value=mock.Mock())
        api.empty_phase_evidence = z.empty_phase_evidence
        api.portfolio_snapshot.return_value = snapshot
        engine = z._workflow.Workflow(api, Path("."), project())
        resolved = {1: {"operational": {"leases": []}}}
        engine.artifact_index = mock.Mock(side_effect=lambda number: mock.Mock(
            resolve=lambda _identity: [resolved[number]]))

        _issue, goal = engine.read(1)

        self.assertEqual(1, goal["key"])
        self.assertEqual([mock.call(1)], engine.artifact_index.call_args_list)
        self.assertFalse(any("pull_request" in row for row in engine._portfolio_cache["goals"]))

    def test_ordinary_portfolio_context_skips_unrelated_pull_requests(self):
        implementation = {"branch": "goal/x", "base": "main", "target": "main",
                          "pr": "https://github.com/owner/repo/pull/11",
                          "review": {"status": "not_started", "checkpoint": None}}
        issues = [self.issue(1), self.issue(2, implementation=implementation)]
        bodies = {row["number"]: {"body": row["body"], "updated_at": row["updated_at"]}
                  for row in issues}
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(z.shutil, "which", return_value="gh"), \
             mock.patch.object(z, "github_repository_goal_index",
                               return_value=({}, issues, [], 0, 1, 0)), \
             mock.patch.object(z, "_github_goal_bodies", return_value=(bodies, 0, 1)), \
             mock.patch.object(z, "_github_goal_relations", return_value=({}, 0, 0)), \
             mock.patch.object(z, "_github_pull_request_states", return_value=({}, 0, 0)) as prs:
            z.github_repository_portfolio_snapshot(Path(directory), project())
        prs.assert_not_called()

    def test_scheduling_inventory_is_complete_and_unavailable_inventory_fails_closed(self):
        """Capacity admission sees every live owner and never treats failure as empty."""
        goals = [{**z.github_goal_record(self.issue(number)), "schema_version": 2,
                  "envelope": {"payload": {"hash": f"payload-{number}"}}}
                 for number in (1, 2, 3)]
        snapshot = z.build_portfolio_snapshot("github_issues", goals, reads=1, raw_bytes=0)
        api = mock.Mock(wraps=z)
        api._project_repository_identity = z._project_repository_identity
        api.GitHubGoalTransitionAdapter = mock.Mock(return_value=mock.Mock())
        api.empty_phase_evidence = z.empty_phase_evidence
        api.portfolio_snapshot.return_value = snapshot
        engine = z._workflow.Workflow(api, Path("."), project())
        payloads = {number: {"operational": {"leases": [{"token": f"lease-{number}"}]}}
                    for number in (1, 2, 3)}
        engine.artifact_index = mock.Mock(side_effect=lambda number: mock.Mock(
            resolve=lambda _identity: [payloads[number]]))

        engine.portfolio(allow_invalid=False)
        self.assertEqual({"lease-1", "lease-2", "lease-3"}, {
            lease["token"] for goal in engine._portfolio_cache["goals"]
            for lease in goal.get("operational_leases", [])
        })
        engine.invalidate()
        api.portfolio_snapshot.return_value = copy.deepcopy(snapshot)
        engine.artifact_index = mock.Mock(side_effect=ValueError("inventory unavailable"))
        with self.assertRaisesRegex(ValueError, r"(?i)inventory|lease|portfolio|repair"):
            engine.portfolio(allow_invalid=False)

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
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / ".zzzops").mkdir()
            cache = z._portfolio_cache_path(repo)
            for poisoned in ("not json", json.dumps({
                    "schema_version": 1, "identity": "other/repo",
                    "include_feedback": False, "marker": [], "bodies": {}, "records": {},
            })):
                cache.write_text(poisoned, encoding="utf-8")
                with self.subTest(cache=poisoned[:12]), \
                     mock.patch.object(z.shutil, "which", return_value="gh"), \
                     mock.patch.object(z, "github_repository_goal_index",
                                       return_value=({}, issues, [], 0, 1, 0)), \
                     mock.patch.object(z, "_github_goal_bodies", return_value=({
                         row["number"]: {"body": row["body"], "updated_at": row["updated_at"]}
                         for row in issues}, 100, 1)), \
                     mock.patch.object(z, "_github_goal_relations", return_value=({}, 0, 0)), \
                     mock.patch.object(z, "_github_pull_request_states", return_value=({}, 0, 0)), \
                     mock.patch.object(z, "github_goal_record", wraps=z.github_goal_record) as parse:
                    snapshot = z.github_repository_portfolio_snapshot(repo, project())[1]
                self.assertEqual([1, 2], sorted(row["key"] for row in snapshot["goals"]))
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

    def test_publication_observes_fresh_provider_head_and_base(self):
        run_generic_regressions(
            self,
            "test_workflow_publication_contract.WorkflowPublicationContractTests."
            "test_provider_head_or_base_drift_requires_local_sync",
        )

    def test_provider_drift_still_rejects_stale_inflight_result(self):
        run_generic_regressions(
            self,
            "test_evidence_dag_journeys.EvidenceDagPublicTests."
            "test_semantic_input_drift_rejects_inflight_result_and_bookkeeping_does_not",
        )


if __name__ == "__main__":
    unittest.main()
