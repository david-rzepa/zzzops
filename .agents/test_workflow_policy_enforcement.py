"""Enforcement of reviewed worker and CI policy at workflow boundaries."""

from __future__ import annotations

import contextlib
import copy
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


class WorkerLimitEnforcementTests(unittest.TestCase):
    def test_checkpoint_uses_reviewed_max_workers_instead_of_fixed_three(self):
        goals = [
            {"key": number, "priority": "P1", "status": "ready", "depends_on": []}
            for number in range(1, 6)
        ]
        engine = mock.Mock()
        engine.portfolio.return_value = goals
        engine.step.side_effect = lambda number: [{"kind": "assess", "goal": number}]

        result = z._workflow.checkpoint(z, Path("."), project(max_workers=2), {}, engine=engine)

        self.assertEqual([1, 2], [step["goal"] for step in result["next_steps"]])
        self.assertEqual([mock.call(1), mock.call(2)], engine.step.call_args_list)

    def test_start_rejects_capacity_consumed_by_another_unresolved_lease(self):
        engine = z._workflow.Workflow.__new__(z._workflow.Workflow)
        engine.project = project(max_workers=1)
        engine.runtime = {"root_id": "root-thread"}
        engine.locked = lambda: contextlib.nullcontext()
        active = {
            "key": 1, "status": "ready",
            "workflow": durable({"expires_at": 0, "worker": "synthetic-worker"}),
        }
        goal = {
            "key": 2, "revision": 1, "digest": "current", "status": "ready",
            "workflow": durable(),
        }
        issue = {"body": "synthetic"}
        engine.portfolio = mock.Mock(return_value=[active, goal])
        engine.read = mock.Mock(return_value=(issue, goal))
        engine.step = mock.Mock(return_value=[{
            "kind": "execute", "phase": "understand", "input_hash": "sha256:input",
        }])
        engine.save = mock.Mock()
        engine.api = SimpleNamespace(parse_managed_goal=lambda body, number: copy.deepcopy(goal))

        with self.assertRaisesRegex(ValueError, "max_workers"):
            engine.mutate(2, {
                "operation": "start", "phase": "understand", "kind": "execute",
                "input_hash": "sha256:input", "request_id": "start-2",
            })
        engine.save.assert_not_called()

    def test_checkpoint_replaces_unstartable_phase_with_capacity_step(self):
        active = {"key": 1, "priority": "P0", "status": "ready", "depends_on": [], "workflow": durable({"expires_at": 0, "worker": "synthetic-worker"})}
        target = {"key": 2, "priority": "P1", "status": "ready", "depends_on": []}
        proposed = {"kind": "execute", "goal": 2, "start": {"operation": "start"}}
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
        operations = (
            {"operation": "integrate", "approved_by": "approved-user", "expected_head": "a" * 40},
            {"operation": "complete"},
        )
        for payload in operations:
            payload = {**payload, "request_id": "request-" + payload["operation"]}
            with self.subTest(operation=payload["operation"], mode="strict"):
                strict = self.transition_engine("inspect_exact_pr_head")
                with self.assertRaisesRegex(ValueError, "CI checks|required_checks|merged PR evidence"):
                    strict.mutate(7, payload)
                strict.save.assert_not_called()
            with self.subTest(operation=payload["operation"], mode="disabled"):
                disabled = self.transition_engine("disabled")
                disabled.mutate(7, payload)
                disabled.save.assert_called_once()

    def test_publish_review_enforces_strict_ci_but_honors_disabled_ci(self):
        record = {"status": "completed"}
        evidence = z.empty_phase_evidence()
        evidence["records"]["publish"] = record
        goal = {"key": 7, "implementation": {"pr": "synthetic-pr"}, "phase_evidence": evidence}
        live = {"publish": {"goal_spec": "sha256:" + "1" * 64}}
        lease = {
            "kind": "review", "worker": "review-worker", "input_hash": z._workflow.digest(live["publish"]),
            "record_hash": z._workflow.digest(record), "review_hash": None,
        }
        payload = {
            "operation": "record_review", "phase": "publish", "actor": "review-worker",
            "artifact": {"reference": "urn:sha256:" + "2" * 64, "hash": "sha256:" + "2" * 64},
            "outcomes": {"acceptance": "approved", "entropy": {"outcome": "no_findings", "evidence": "Synthetic review", "goals": []}},
        }
        for mode, denied in (("inspect_exact_pr_head", True), ("disabled", False)):
            with self.subTest(mode=mode):
                engine = self.engine(required_ci=mode)
                engine.runtime = {"root_id": "root-thread"}
                engine.pull_request = mock.Mock(return_value={"checks_verified": False, "checks_present": False})
                engine.context = mock.Mock(return_value=({}, {"publish": {"review": {"independent": True}}}, live, {}))
                engine.read_artifact = mock.Mock(return_value={})
                engine.api.derive_phase_steps = lambda *args, **kwargs: {"execute": [], "review": [{"phase": "publish"}]}
                engine.api.empty_phase_evidence = z.empty_phase_evidence
                engine.api.record_phase_review = lambda *args, **kwargs: {"reviewed": True}
                if denied:
                    with self.assertRaisesRegex(ValueError, "CI checks"):
                        engine.submit_evidence(goal, copy.deepcopy(goal), {**durable(), "leases": {"publish:review": lease}}, "publish:review", lease, payload)
                else:
                    engine.submit_evidence(goal, copy.deepcopy(goal), {**durable(), "leases": {"publish:review": lease}}, "publish:review", lease, payload)
                    engine.read_artifact.assert_called_once()


if __name__ == "__main__":
    unittest.main()
