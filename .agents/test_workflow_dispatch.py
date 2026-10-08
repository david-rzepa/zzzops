"""Scheduling coverage for portfolio-wide public workflow checkpoints."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest
from unittest import mock

import test_zzzops as fixtures


z = fixtures.zzzops


class WorkflowDispatchTests(unittest.TestCase):
    @staticmethod
    def goal(number, priority):
        # Dispatch exercises the current portfolio; predecessor conversion has
        # its own guarded migration tests and is not part of this fixture.
        return {"key": number, "schema_version": 2, "priority": priority,
                "status": "ready", "depends_on": []}

    def checkpoint(self, goals, steps, portfolio_order=None, validation_findings=None):
        engine = mock.Mock(spec=z._workflow.Workflow)
        engine.runtime = {}
        engine.portfolio.return_value = goals
        engine.step.side_effect = lambda number: steps[number]
        engine.reconciliation_step.return_value = None
        engine.validation_blockers.side_effect = lambda goal: (validation_findings or {}).get(goal["key"], [])
        configuration = {"max_workers": 3}
        if portfolio_order is not None:
            configuration["portfolio_order"] = portfolio_order
        project = {"policy": {"sections": [{
            "id": "autonomy_approval_parallelism", "configuration": configuration,
        }]}}
        with mock.patch.object(z._workflow, "Workflow", return_value=engine):
            result = z._workflow.checkpoint(z, Path("."), project, {})
        return result, engine

    def test_waiting_high_priority_goals_do_not_starve_later_runnable_goal(self):
        goals = [
            self.goal(1, "P0"),
            self.goal(2, "P0"),
            self.goal(3, "P1"),
            self.goal(4, "P3"),
        ]
        steps = {
            1: [{"kind": "blocker", "goal": 1, "action": "Await human input."}],
            2: [{"kind": "dependency", "goal": 2, "action": "Await an ancestor."}],
            3: [{"kind": "await_worker", "goal": 3, "action": "Await the leased worker."}],
            4: [{"kind": "execute", "goal": 4, "node": {"goal": 4, "node": "work", "item": None, "generation": 1}, "action": "Execute the declared task."}],
        }

        result, engine = self.checkpoint(goals, steps)

        self.assertEqual([steps[4][0]], result["next_steps"])
        engine.step.assert_has_calls([mock.call(number) for number in (1, 2, 3, 4)], any_order=True)
        self.assertEqual(4, engine.step.call_count)

    def test_all_waiting_portfolio_returns_bounded_informative_steps(self):
        goals = [self.goal(number, "P0") for number in range(1, 5)]
        steps = {
            1: [{"kind": "blocker", "goal": 1, "action": "Await human input."}],
            2: [{"kind": "await_worker", "goal": 2, "action": "Await the leased worker."}],
            3: [{"kind": "dependency", "goal": 3, "action": "Await an ancestor."}],
            4: [{"kind": "blocker", "goal": 4, "action": "Await access."}],
        }

        result, engine = self.checkpoint(goals, steps)

        self.assertEqual([steps[1][0], steps[2][0], steps[3][0]], result["next_steps"])
        self.assertEqual(4, engine.step.call_count)

    def test_completed_or_empty_portfolio_reports_explicit_exhaustion(self):
        result, engine = self.checkpoint([], {})

        self.assertEqual([{
            "kind": "terminal_report", "assignment": "root", "state": "complete",
            "action": "All goals are complete or the portfolio is empty. Report workflow exhaustion; no CLI command is required.",
        }], result["next_steps"])
        engine.step.assert_not_called()

    def test_effective_dag_order_honors_a_reviewed_equal_priority_preference(self):
        goals = [
            {**self.goal(1, "P2"), "depends_on": []},
            {**self.goal(3, "P1"), "depends_on": []},
            {**self.goal(4, "P1"), "depends_on": [1]},
        ]
        steps = {number: [{"kind": "execute", "goal": number, "node": {"goal": number, "node": "work", "item": None, "generation": 1}, "action": "Execute the declared task."}] for number in (1, 3, 4)}
        decision = {"ordered_goal_keys": [4, 3], "rationale": "Remove portfolio friction before unrelated P1 work."}

        result, engine = self.checkpoint(goals, steps, decision)

        # The projection ranks the P2 prerequisite first, then preferred #4
        # ahead of #3. Dispatch keeps #4 waiting until its prerequisite is done.
        self.assertEqual([steps[1][0], steps[3][0]], result["next_steps"])
        engine.step.assert_has_calls([mock.call(1), mock.call(3)], any_order=True)
        self.assertEqual(2, engine.step.call_count)
        self.assertEqual([1, 4, 3], [item["goal"] for item in z.effective_goal_order(goals, decision)])
        self.assertEqual("portfolio_decision", z.effective_goal_order(goals, decision)[1]["reason"])

    def test_reviewed_preference_orders_runnable_equal_priority_goals(self):
        goals = [self.goal(number, "P1") for number in (1, 3, 4)]
        original = copy.deepcopy(goals)
        steps = {goal["key"]: [{"kind": "execute", "goal": goal["key"]}] for goal in goals}
        decision = {"ordered_goal_keys": [4, 3], "rationale": "Clear friction first."}

        result, engine = self.checkpoint(goals, steps, decision)

        self.assertEqual([steps[number][0] for number in (4, 3, 1)], result["next_steps"])
        self.assertEqual(3, engine.step.call_count)
        self.assertEqual(original, goals)

    def test_preference_cannot_bypass_blockers_dependencies_active_workers_or_invalid_goals(self):
        decision = {"ordered_goal_keys": [1, 2], "rationale": "Prefer the first goal when eligible."}
        runnable = {"kind": "execute", "goal": 2}
        for waiting_kind in ("blocker", "dependency", "await_worker", "invalid"):
            with self.subTest(waiting_kind=waiting_kind):
                preferred = self.goal(1, "P1")
                goals = [preferred, self.goal(2, "P1")]
                steps = {2: [runnable]}
                findings = {}
                if waiting_kind == "dependency":
                    preferred["depends_on"] = [3]
                    goals.append(self.goal(3, "P2"))
                    steps[3] = [{"kind": "blocker", "goal": 3}]
                elif waiting_kind == "invalid":
                    findings[1] = [{"code": "missing_relation", "goal": 1, "detail": "99"}]
                else:
                    if waiting_kind == "await_worker":
                        preferred["operational_leases"] = [{"owner": "another-root", "token": "active"}]
                    else:
                        preferred["blockers"] = [{"status": "open", "category": "human-action"}]
                    steps[1] = [{"kind": waiting_kind, "goal": 1}]
                original = copy.deepcopy(goals)

                result, engine = self.checkpoint(goals, steps, decision, findings)

                self.assertEqual([runnable], result["next_steps"])
                engine.step.assert_has_calls([mock.call(number) for number in steps], any_order=True)
                self.assertEqual(len(steps), engine.step.call_count)
                self.assertEqual(original, goals)

    def test_invalid_preferred_goal_retains_findings_when_all_work_is_waiting(self):
        goals = [self.goal(number, "P1") for number in (1, 2)]
        steps = {2: [{"kind": "await_worker", "goal": 2}]}
        findings = {1: [{"code": "missing_relation", "goal": 1, "detail": "99"}]}
        decision = {"ordered_goal_keys": [1], "rationale": "Prefer the first goal when eligible."}

        result, engine = self.checkpoint(goals, steps, decision, findings)

        self.assertEqual("blocker", result["next_steps"][0]["kind"])
        self.assertEqual(1, result["next_steps"][0]["goal"])
        self.assertEqual(findings[1], result["next_steps"][0]["findings"])
        self.assertEqual(steps[2][0], result["next_steps"][1])
        engine.step.assert_called_once_with(2)

    def test_selected_predecessor_still_uses_the_migration_adapter(self):
        goals = [{**self.goal(1, "P1"), "schema_version": 1}, self.goal(2, "P2")]
        migrated_steps = [{"kind": "execute", "goal": 1}]
        migration_result = {"next_steps": [{"members": {"1": {
            "status": "migrated", "next_steps": migrated_steps,
        }}}]}
        with mock.patch.object(z._migration_batch, "run", return_value=migration_result) as migrate:
            result, engine = self.checkpoint(goals, {})

        self.assertEqual(migrated_steps, result["next_steps"])
        migrate.assert_called_once_with(engine, {"action": "migrate", "goals": [1]})
        engine.step.assert_not_called()


if __name__ == "__main__":
    unittest.main()
