"""Scheduling coverage for portfolio-wide public workflow checkpoints."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

import test_zzzops as fixtures


z = fixtures.zzzops


class WorkflowDispatchTests(unittest.TestCase):
    @staticmethod
    def goal(number, priority):
        return {"key": number, "priority": priority, "status": "ready", "depends_on": []}

    def checkpoint(self, goals, steps):
        engine = mock.Mock()
        engine.portfolio.return_value = goals
        engine.step.side_effect = lambda number: steps[number]
        with mock.patch.object(z._workflow, "Workflow", return_value=engine):
            result = z._workflow.checkpoint(z, Path("."), {}, {})
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
            4: [{"kind": "assess", "goal": 4, "action": "Assess this runnable phase."}],
        }

        result, engine = self.checkpoint(goals, steps)

        self.assertEqual([steps[4][0]], result["next_steps"])
        self.assertEqual([mock.call(1), mock.call(2), mock.call(3), mock.call(4)], engine.step.call_args_list)

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


if __name__ == "__main__":
    unittest.main()
