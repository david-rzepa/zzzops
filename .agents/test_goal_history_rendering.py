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
    def test_large_workflow_history_is_lossless_and_fits_provider_limit(self):
        prior = '## Outcome\n\nPreserve this.\n<!-- zzzops-goal\n' + ('{"evidence":"repeated"}\n' * 4000) + 'zzzops-goal -->\n'
        desired = {"status": "ready", "revision": 99, "next_action": "Continue", "evidence": ['phase proof'] * 4000}
        _, rendered = MODULE.render_goal_history(42, 'a' * 64, prior, desired)
        self.assertLess(len(rendered), 65536)
        self.assertIn('zlib-base64', rendered)
        parsed = MODULE.parse_goal_history(rendered)
        self.assertEqual(prior, parsed['prior_body'])
        self.assertEqual(desired, parsed['requested_goal'])

    def test_human_sections_are_readable_and_payload_round_trips(self):
        prior = '## Outcome\n\nLine one.\n\nQuoted “text” and Unicode: café 🚀.\n'
        desired = {
            "schema_version": 1, "status": "blocked", "revision": 2,
            "next_action": "First line.\nSecond line with \"quotes\".",
        }
        _, rendered = MODULE.render_goal_history(42, "a" * 64, prior, desired)
        self.assertIn("### Archived canonical body\n\n## Outcome\n\nLine one.", rendered)
        self.assertIn("Second line with \"quotes\".", rendered)
        self.assertIn("<details>", rendered)
        self.assertIn("```json", rendered)
        self.assertNotIn("<!-- zzzops-history", rendered)
        parsed = MODULE.parse_goal_history(rendered)
        self.assertEqual(parsed["prior_body"], prior)
        self.assertEqual(parsed["requested_goal"], desired)


if __name__ == "__main__":
    unittest.main()
