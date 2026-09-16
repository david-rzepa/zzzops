import importlib.util
import json
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "plugins/zzzops/zzzops/goals.py"
SPEC = importlib.util.spec_from_file_location("zzzops_goals_history", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class GoalHistoryRenderingTests(unittest.TestCase):
    def test_human_sections_are_readable_and_payload_round_trips(self):
        prior = '## Outcome\n\nLine one.\n\nQuoted “text” and Unicode: café 🚀.\n'
        desired = {
            "schema_version": 1, "status": "blocked", "revision": 2,
            "next_action": "First line.\nSecond line with \"quotes\".",
        }
        _, rendered = MODULE.render_goal_history(42, "a" * 64, prior, desired)
        self.assertIn("### Archived canonical body\n\n## Outcome\n\nLine one.", rendered)
        self.assertIn("Second line with \"quotes\".", rendered)
        self.assertNotIn(r"\\n", rendered.split(MODULE.GOAL_HISTORY_BLOCK_START, 1)[0])
        parsed = MODULE.parse_goal_history(rendered)
        self.assertEqual(parsed["prior_body"], prior)
        self.assertEqual(parsed["requested_goal"], desired)


if __name__ == "__main__":
    unittest.main()
