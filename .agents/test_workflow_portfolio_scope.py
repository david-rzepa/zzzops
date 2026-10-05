"""Behavioral regressions for dependency-scoped workflow portfolio reads."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import time
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

    def test_warm_targeted_workflow_context_skips_unrelated_comments_and_prs(self):
        implementation = {"branch": "goal/x", "base": "main", "target": "main",
                          "pr": "https://github.com/owner/repo/pull/11",
                          "review": {"status": "not_started", "checkpoint": None}}
        issues = [self.issue(1), self.issue(2, implementation=implementation), self.issue(3)]
        bodies = {row["number"]: {"body": row["body"], "updated_at": row["updated_at"]}
                  for row in issues}
        def gateway(repo, **scope):
            return z.github_repository_portfolio_snapshot(repo, project(), **scope)[1]
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(z.shutil, "which", return_value="gh"), \
             mock.patch.object(z, "github_repository_goal_index",
                               return_value=({}, issues, [], 0, 1, 0)), \
             mock.patch.object(z, "_github_goal_bodies", return_value=(bodies, 10, 1)) as body_reads, \
             mock.patch.object(z, "_github_goal_relations", return_value=({}, 0, 0)), \
             mock.patch.object(z, "_github_pull_request_states", return_value=({}, 0, 0)) as prs, \
             mock.patch.object(z, "portfolio_snapshot", side_effect=gateway), \
             mock.patch.object(z, "GitHubGoalTransitionAdapter", return_value=mock.Mock()):
            z.github_repository_portfolio_snapshot(Path(directory), project())
            body_reads.reset_mock()
            prs.reset_mock()
            engine = z._workflow.Workflow(z, Path(directory), project())
            with mock.patch.object(engine, "artifact_index", wraps=engine.artifact_index) as comments:
                _issue, goal = engine.read(1)
        self.assertEqual(1, goal["key"])
        body_reads.assert_not_called()
        self.assertFalse(any(call.args[0] in {2, 3} for call in comments.call_args_list))
        prs.assert_not_called()

    def test_targeted_v2_context_hydrates_only_requested_payload_with_unrelated_live_owner(self):
        from test_workflow_policy_enforcement import GenericWorkerCapacityTests
        case = GenericWorkerCapacityTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        owner = case.session.acquire("produce", number=100, actor="unrelated-owner")
        case.add_goal(101, case.graph)
        unrelated_envelope, unrelated_payload = case.payload()
        self.assertEqual(owner["lease"]["token"],
                         unrelated_payload["operational"]["leases"][0]["token"])
        with mock.patch.object(z, "portfolio_snapshot", side_effect=case.session.portfolio_snapshot), \
             mock.patch.object(z, "GitHubGoalTransitionAdapter", return_value=case.provider), \
             mock.patch.object(case.provider, "get_issue_comments", wraps=case.provider.get_issue_comments) as comments:
            engine = z._workflow.Workflow(z, case.fixture.repo, case.session.project)
            _, goal = engine.read(101)
            self.assertEqual(2, goal["schema_version"])
            requested = engine.artifact_index(101).resolve(goal["envelope"]["payload"]["hash"])[0]
            self.assertEqual([], requested["operational"]["leases"])
        self.assertEqual([101], [call.args[0] for call in comments.call_args_list])

    def test_same_session_context_then_publication_observes_fresh_provider_drift(self):
        from test_workflow_publication_contract import GenericPublicationPublicTests
        case = GenericPublicationPublicTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        provider_facts = z._github_pull_request_states
        provider_facts.reset_mock()
        case.session.checkpoint(100)
        provider_facts.assert_not_called()
        case.authorize_context()
        work = case.session.acquire(case.ids["observe"])
        declared = case.observed_value()
        case.observation["head_oid"] = "a" * 40
        rejected = case.session.call(
            100, case.session.submission(work, {"value": declared}, "fresh-context-drift"),
            expected=2,
        )
        self.assertRegex(json.dumps(rejected), r"(?i)head|stale|provider|input")
        self.assertGreater(provider_facts.call_count, 0)

    def test_legacy_publication_consumer_observes_only_its_exact_pr(self):
        goal = z.github_goal_record(self.issue(1, implementation={
            "branch": "goal/x", "base": "main", "target": "main",
            "pr": "https://github.com/owner/repo/pull/11",
            "review": {"status": "not_started", "checkpoint": None}}))
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(z, "_github_pull_request_states", return_value=({1: {"head_oid": "fresh"}}, 0, 1)) as provider:
            engine = z._workflow.Workflow(z, Path(directory), project())
            self.assertEqual({"head_oid": "fresh"}, engine.pull_request(goal))
            provider.assert_called_once_with(
                Path(directory), "gh", [{"number": 1}],
                {1: {"repository_context": goal["implementation"]}})

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

    def test_missing_unrelated_v2_payload_blocks_capacity_but_not_target_context(self):
        from test_workflow_policy_enforcement import GenericWorkerCapacityTests
        case = GenericWorkerCapacityTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.add_goal(101, case.graph)
        case.provider.comments[101] = []
        with mock.patch.object(z, "portfolio_snapshot", side_effect=case.session.portfolio_snapshot), \
             mock.patch.object(z, "GitHubGoalTransitionAdapter", return_value=case.provider):
            engine = z._workflow.Workflow(z, case.fixture.repo, case.session.project)
            self.assertEqual(100, engine.read(100)[1]["key"])
            with self.assertRaisesRegex(ValueError, "Ownership inventory unavailable.*101"):
                engine.portfolio(include_ownership=True)

    def test_ownership_inventory_hydrates_independent_goals_concurrently(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = z._workflow.Workflow(z, Path(directory), project())
            engine._portfolio_cache = {"complete": True, "findings": [], "goals": [
                {"key": number, "schema_version": 2, "status": "ready",
                 "envelope": {"payload": {"hash": f"sha256:{number:064x}"}}}
                for number in range(1, 4)
            ]}
            lock = threading.Lock()
            active = peak = 0
            class Index:
                def resolve(self, _identity):
                    nonlocal active, peak
                    with lock:
                        active += 1
                        peak = max(peak, active)
                    time.sleep(0.05)
                    with lock:
                        active -= 1
                    return ({"operational": {"leases": []}}, None)
            engine.artifact_index = mock.Mock(side_effect=lambda _number: Index())
            goals = engine.portfolio(include_ownership=True)
            self.assertGreater(peak, 1)
            self.assertTrue(all(goal["operational_leases"] == [] for goal in goals))

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
                self.assertEqual([1, 2], [row["key"] for row in snapshot["goals"]])
                self.assertIn("Exact first body.", snapshot["goals"][0]["human_spec"])
                self.assertEqual({1, 2}, {call.args[0]["number"] for call in parse.call_args_list})

            bodies = {row["number"]: {"body": row["body"], "updated_at": row["updated_at"]}
                      for row in issues}
            with mock.patch.object(z.shutil, "which", return_value="gh"), \
                 mock.patch.object(z, "github_repository_goal_index", return_value=({}, issues, [], 0, 1, 0)), \
                 mock.patch.object(z, "_github_goal_bodies", return_value=(bodies, 100, 1)), \
                 mock.patch.object(z, "_github_goal_relations", return_value=({}, 0, 0)), \
                 mock.patch.object(z, "_github_pull_request_states", return_value=({}, 0, 0)):
                z.github_repository_portfolio_snapshot(repo, project())
            valid_cache = json.loads(cache.read_text(encoding="utf-8"))
            valid_cache["records"]["1"] = {**valid_cache["records"]["2"], "key": 1}
            cache.write_text(json.dumps(valid_cache), encoding="utf-8")
            with mock.patch.object(z.shutil, "which", return_value="gh"), \
                 mock.patch.object(z, "github_repository_goal_index", return_value=({}, issues, [], 0, 1, 0)), \
                 mock.patch.object(z, "_github_goal_bodies") as body_read, \
                 mock.patch.object(z, "_github_goal_relations", return_value=({}, 0, 0)), \
                 mock.patch.object(z, "_github_pull_request_states", return_value=({}, 0, 0)):
                snapshot = z.github_repository_portfolio_snapshot(repo, project())[1]
            body_read.assert_not_called()
            self.assertIn("Exact first body.", snapshot["goals"][0]["human_spec"])

    def test_body_cache_corruption_and_discovery_hydration_drift_are_not_reused(self):
        selected = [{"number": 1, "state": "open", "updated_at": "revision-one"}]
        bodies = {1: {"body": "original body", "updated_at": "revision-one"}}
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            z._store_open_bodies(repo, "owner/repo", False, selected, bodies)
            cache = z._portfolio_cache_path(repo)
            stored = json.loads(cache.read_text())
            stored["bodies"]["1"] = "corrupted body"
            cache.write_text(json.dumps(stored))
            self.assertEqual({}, z._cached_open_bodies(repo, "owner/repo", False, selected, partial=True))
            cache.unlink()
            bodies[1]["updated_at"] = "revision-two"
            z._store_open_bodies(repo, "owner/repo", False, selected, bodies)
            self.assertFalse(cache.exists())

    def test_unencodable_cached_body_hydrates_only_corrupt_entry(self):
        issues = [self.issue(1), self.issue(2)]
        bodies = {row["number"]: {"body": row["body"], "updated_at": row["updated_at"]}
                  for row in issues}
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            z._store_open_bodies(repo, "owner/repo", False, issues, bodies)
            cache = z._portfolio_cache_path(repo)
            corrupted = json.loads(cache.read_text())
            corrupted["bodies"]["1"] = chr(0xD800)
            cache.write_text(json.dumps(corrupted))
            self.assertIsNone(z._cached_open_bodies(repo, "owner/repo", False, issues))
            self.assertEqual({2: bodies[2]}, z._cached_open_bodies(
                repo, "owner/repo", False, issues, partial=True))
            with mock.patch.object(z.shutil, "which", return_value="gh"), \
                 mock.patch.object(z, "github_repository_goal_index", return_value=({}, issues, [], 0, 1, 0)), \
                 mock.patch.object(z, "_github_goal_bodies", return_value=({1: bodies[1]}, 100, 1)) as hydration, \
                 mock.patch.object(z, "_github_goal_relations", return_value=({}, 0, 0)), \
                 mock.patch.object(z, "_github_pull_request_states", return_value=({}, 0, 0)):
                snapshot = z.github_repository_portfolio_snapshot(repo, project())[1]
            hydration.assert_called_once_with(repo, "gh", "owner", "repo", [1])
            self.assertEqual([1, 2], [row["key"] for row in snapshot["goals"]])
            self.assertEqual(bodies, z._cached_open_bodies(repo, "owner/repo", False, issues))

    def test_targeted_closed_dependency_is_present_without_unrelated_closed_history(self):
        open_goal = self.issue(1, depends_on=[2])
        needed = self.issue(2, status="done")
        bodies = {1: {"body": open_goal["body"], "updated_at": open_goal["updated_at"]}}
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(z.shutil, "which", return_value="gh"), \
             mock.patch.object(z, "github_repository_goal_index",
                               return_value=({}, [open_goal], [], 0, 1, 0)), \
             mock.patch.object(z, "_github_goal_bodies", return_value=(bodies, 0, 1)), \
             mock.patch.object(z, "_github_goal_relations", return_value=({2: needed}, 20, 1)) as relations, \
             mock.patch.object(z, "_github_pull_request_states", return_value=({}, 0, 0)):
            snapshot = z.github_repository_portfolio_snapshot(Path(directory), project())[1]
        self.assertEqual([1, 2], [row["key"] for row in snapshot["goals"]])
        relations.assert_called_once_with(Path(directory), "gh", "owner", "repo", [2])

    def test_provider_drift_still_rejects_stale_inflight_result(self):
        run_generic_regressions(
            self,
            "test_evidence_dag_journeys.EvidenceDagPublicTests."
            "test_semantic_input_drift_rejects_inflight_result_and_bookkeeping_does_not",
        )


if __name__ == "__main__":
    unittest.main()
