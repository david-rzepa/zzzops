"""Enforcement of reviewed worker and CI policy at workflow boundaries."""

from __future__ import annotations

import contextlib
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import test_zzzops as fixtures


z = fixtures.zzzops


def project(*, max_workers=2, required_ci="inspect_exact_pr_head", verification_applicable=True):
    return {
        "backend": "github_issues",
        "repository": {"identity": "synthetic/project"},
        "policy": {"sections": [
            {
                "id": "autonomy_approval_parallelism",
                "configuration": {"max_workers": max_workers},
            },
            {
                "id": "verification_testing",
                "applicable": verification_applicable,
                "configuration": {"required_ci": required_ci},
            },
        ]},
    }


def durable(*leases):
    return {
        "leases": {f"phase-{index}": lease for index, lease in enumerate(leases)},
        "receipts": {}, "workers": {}, "assessments": {}, "artifacts": {},
    }


from test_evidence_dag_journeys import DagFixture
import test_evidence_dag_journeys as dag_fixtures


class GenericWorkerCapacityTests(DagFixture):
    add_goal = dag_fixtures.RelationshipPublicTests.add_goal
    put_envelope = dag_fixtures.RelationshipPublicTests.put_envelope

    def test_other_goal_unresolved_owner_consumes_reviewed_capacity_until_observed_stop(self):
        config = z._workflow_section(self.session.project, "autonomy_approval_parallelism")["configuration"]
        config["max_workers"] = 1
        graph = copy.deepcopy(self.graph)
        def symbolic(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "goal" and child == 100:
                        value[key] = "#this"
                    else:
                        symbolic(child)
            elif isinstance(value, list):
                for child in value:
                    symbolic(child)
        symbolic(graph)
        self.install(graph)
        self.add_goal(101, graph)
        target = next(step for step in self.session.checkpoint(101) if step.get("kind") == "execute")
        start = {**target["start"], "policy_receipt": json.loads(Path(target["policy"]["path"]).read_text())["policy_receipt"]}
        first = self.session.acquire("produce", number=100, actor="first-writer")
        for now in (first["lease"]["expires_at"] - 1, first["lease"]["expires_at"] + 1):
            with self.subTest(now=now), mock.patch.object(z._workflow.time, "time", return_value=now):
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                steps = self.session.checkpoint(101)
                self.assertFalse(any(step.get("kind") == "execute" for step in steps))
                self.assertRegex(str(steps), r"(?i)max_workers|capacity|await_worker")
                rejected = self.session.call(101, start, expected=2)
                self.assertRegex(str(rejected), r"(?i)max_workers|capacity|unresolved|active.*lease")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        with mock.patch.object(z._workflow.time, "time", return_value=first["lease"]["expires_at"] + 1):
            steps = self.session.checkpoint(100)
            recovery = next(step for step in steps if "recovery_contract" in step or step.get("kind") == "recover")
            request = copy.deepcopy(recovery.get("submission", recovery.get("recovery_contract")))
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            self.session.call(100, {**request, "worker_status": "unknown", "evidence": "Timeout alone"}, expected=2)
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
            self.session.call(100, {**request, "worker_status": "stopped", "evidence": "Actual first-writer terminal state observed"})
        second = self.session.acquire("produce", number=101, actor="second-writer")
        self.session.finish(second, {"value": "Capacity released only after observed ownership termination"}, number=101)


class WorkerLimitEnforcementTests(unittest.TestCase):
    def test_checkpoint_uses_reviewed_max_workers_instead_of_fixed_three(self):
        goals = [
            {"key": number, "priority": "P1", "status": "ready", "depends_on": []}
            for number in range(1, 6)
        ]
        engine = mock.Mock()
        engine.portfolio.return_value = goals
        engine.step.side_effect = lambda number: [{"kind": "execute", "goal": number,
            "node": {"goal": number, "node": "work", "item": None, "generation": 1}}]

        result = z._workflow.checkpoint(z, Path("."), project(max_workers=2), {}, engine=engine)

        self.assertEqual([1, 2], [step["goal"] for step in result["next_steps"]])
        self.assertEqual([mock.call(1), mock.call(2)], engine.step.call_args_list)

    def test_start_rejects_capacity_consumed_by_another_unresolved_lease(self):
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self, 'test_workflow_policy_enforcement.GenericWorkerCapacityTests.test_other_goal_unresolved_owner_consumes_reviewed_capacity_until_observed_stop')

    def test_checkpoint_replaces_unstartable_phase_with_capacity_step(self):
        # Supported predecessor ownership still consumes capacity until actual
        # stop/conversion; it is not a runnable second phase engine.
        active = {"key": 1, "priority": "P0", "status": "ready", "depends_on": [], "workflow": durable({"expires_at": 0, "worker": "synthetic-worker"})}
        target = {"key": 2, "priority": "P1", "status": "ready", "depends_on": []}
        proposed = {"kind": "execute", "goal": 2,
                    "node": {"goal": 2, "node": "work", "item": None, "generation": 1},
                    "start": {"operation": "start"}}
        engine = mock.Mock()
        engine.portfolio.return_value = [active, target]
        engine.step.side_effect = {1: [{"kind": "await_worker", "goal": 1}], 2: [proposed]}.__getitem__

        portfolio = z._workflow.checkpoint(z, Path("."), project(max_workers=1), {}, engine=engine)
        goal_bound = z._workflow.checkpoint(z, Path("."), project(max_workers=1), {}, number=2, engine=engine)

        for result in (portfolio, goal_bound):
            self.assertEqual("await_worker", result["next_steps"][0]["kind"])
            self.assertEqual(1, result["next_steps"][0]["active_leases"])
            self.assertNotIn(proposed, result["next_steps"])


class PublishCiPolicyTests(unittest.TestCase):
    def engine(self, **settings):
        engine = z._workflow.Workflow.__new__(z._workflow.Workflow)
        engine.project = project(**settings)
        engine.repository = "synthetic/project"
        engine.api = SimpleNamespace(classify_pr_merge=lambda goal, current, repository: {
            "status": "merged_verified" if current.get("checks_verified") else "merged_stale",
        })
        return engine

    def test_exact_head_mode_requires_verified_checks(self):
        engine = self.engine(required_ci="inspect_exact_pr_head")
        self.assertTrue(engine.ci_checks_required({"checks_verified": False}))
        self.assertEqual("merged_stale", engine.classify_merge({}, {"checks_verified": False})["status"])

    def test_only_configuration_can_disable_ci(self):
        engine = self.engine(required_ci="disabled")
        current = {"checks_verified": False}
        self.assertFalse(engine.ci_checks_required(current))
        self.assertEqual("merged_verified", engine.classify_merge({}, current)["status"])
        self.assertFalse(current["checks_verified"])
        engine = self.engine(required_ci="inspect_exact_pr_head", verification_applicable=False)
        self.assertTrue(engine.ci_checks_required(current))
        self.assertEqual("merged_stale", engine.classify_merge({}, current)["status"])

    def test_existing_only_uses_explicit_check_presence_evidence(self):
        engine = self.engine(required_ci="existing_only")
        self.assertFalse(engine.ci_checks_required({"checks_present": False, "checks_verified": False}))
        self.assertTrue(engine.ci_checks_required({"checks_present": True, "checks_verified": False}))
        with self.assertRaisesRegex(ValueError, "does not distinguish absent CI checks"):
            engine.ci_checks_required({"checks_verified": False})

    def test_provider_check_presence_requires_complete_empty_evidence(self):
        def pull(nodes, page_info=None):
            contexts = {"nodes": nodes}
            if page_info is not None:
                contexts["pageInfo"] = page_info
            return {"commits": {"nodes": [{"commit": {"statusCheckRollup": {"contexts": contexts}}}]}}

        self.assertTrue(z._pull_request_checks_present(pull([{"name": "synthetic-check"}])))
        self.assertFalse(z._pull_request_checks_present(pull([], {"hasNextPage": False})))
        self.assertIsNone(z._pull_request_checks_present(pull([])))
        self.assertIsNone(z._pull_request_checks_present({"commits": {"nodes": []}}))
        truncated = pull([{"name": "synthetic-check", "status": "COMPLETED", "conclusion": "SUCCESS"}], {"hasNextPage": True})
        self.assertFalse(z._pull_request_checks_verified(truncated))

    def transition_engine(self, mode):
        engine = z._workflow.Workflow.__new__(z._workflow.Workflow)
        engine.project = project(required_ci=mode)
        engine.repository = "synthetic/project"
        engine.runtime = {"root_id": "root-thread"}
        engine.locked = lambda: contextlib.nullcontext()
        engine.adapter = SimpleNamespace(get_issue_comments=lambda number: [])
        engine.publication_gate = mock.Mock(return_value=None)
        current = {
            "head_oid": "a" * 40, "checks_verified": False,
            "checks_present": False, "merged": True,
        }
        engine.pull_request = mock.Mock(return_value=current)
        engine.context = mock.Mock(return_value=({}, {}, {}, {}))
        engine.save = mock.Mock()
        engine.api = SimpleNamespace(
            parse_managed_goal=lambda body, number: copy.deepcopy(engine.goal),
            derive_phase_steps=lambda *args, **kwargs: {"execute": [], "review": [], "blocked": [], "approve": []},
            classify_pr_merge=lambda goal, observed, repository: {
                "status": "merged_verified" if observed.get("checks_verified") else "merged_stale",
            },
        )
        engine.goal = {
            "key": 7, "revision": 1, "digest": "current", "status": "ready",
            "implementation": {"pr": "synthetic-pr", "review": {"status": "not_started", "checkpoint": None}},
            "workflow": durable(),
        }
        engine.portfolio = mock.Mock(return_value=[engine.goal])
        engine.read = mock.Mock(return_value=({"body": "synthetic"}, engine.goal))
        return engine

    def test_integrate_and_complete_enforce_strict_ci_but_honor_disabled_ci(self):
        # Exact publication safeguards now consume ordinary current generic evidence.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_workflow_publication_contract.GenericPublicationPublicTests.test_strict_ci_blocks_integration_and_only_reviewed_disabled_configuration_permits_it',
            'test_workflow_publication_contract.GenericPublicationPublicTests.test_strict_ci_blocks_complete_and_reviewed_disabled_ci_preserves_current_terminal_requirement',
        )

    def test_publish_review_enforces_strict_ci_but_honors_disabled_ci(self):
        # Exact publication safeguards now consume ordinary current generic evidence.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_workflow_publication_contract.GenericPublicationPublicTests.test_ci_absent_unknown_unverified_and_disabled_authorization_are_distinct',
            'test_workflow_publication_contract.GenericPublicationPublicTests.test_negative_ci_observation_is_recordable_and_review_can_admit_correction_without_approval',
        )


if __name__ == "__main__":
    unittest.main()
