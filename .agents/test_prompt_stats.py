from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("prompt_stats.py")
SPEC = importlib.util.spec_from_file_location("prompt_stats", SCRIPT)
assert SPEC and SPEC.loader
prompt_stats = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prompt_stats)


class PromptStatsTests(unittest.TestCase):
    def test_canonical_size_is_line_ending_invariant(self) -> None:
        lf = "one\ntwo\n".encode()
        expected = prompt_stats.canonical_size(lf)
        self.assertEqual(prompt_stats.canonical_size(b"one\r\ntwo\r\n"), expected)
        self.assertEqual(prompt_stats.canonical_size(b"one\rtwo\r"), expected)

    def test_report_includes_rows_and_total(self) -> None:
        report = prompt_stats.render_report([("AGENTS.md", 8, 2)])
        self.assertIn("| `AGENTS.md` | 8 | 2 |", report)
        self.assertIn("| **Total** | **8** | **2** |", report)

    def test_budget_boundary_is_explicit(self) -> None:
        self.assertTrue(prompt_stats.within_budget([("a", 4, 2)], limit=2))
        self.assertFalse(prompt_stats.within_budget([("a", 4, 3)], limit=2))

    def test_workflow_profiles_cover_both_harnesses(self) -> None:
        root = SCRIPT.parents[1]
        report = prompt_stats.render_workflow_report(root)
        self.assertEqual(
            {"capture", "execution", "policy-review", "migration", "suggestion", "acceptance", "feedback"},
            set(prompt_stats.WORKFLOW_PROMPTS),
        )
        self.assertEqual(set(prompt_stats.WORKFLOW_PROMPTS), set(prompt_stats.WORKFLOW_SIGNALS))
        self.assertIn("| Workflow | Codex bytes | Codex est. tokens | Claude bytes | Claude est. tokens |", report)
        for workflow in prompt_stats.WORKFLOW_PROMPTS:
            self.assertIn(f"| {workflow} |", report)

    def test_workflow_eval_reports_missing_signal(self) -> None:
        root = SCRIPT.parents[1]
        failures, _ = prompt_stats.evaluate_workflows(root)
        self.assertEqual([], failures)
        original = prompt_stats.WORKFLOW_SIGNALS["capture"]
        try:
            prompt_stats.WORKFLOW_SIGNALS["capture"] = ("not-a-real-prompt-signal",)
            failures, _ = prompt_stats.evaluate_workflows(root)
            self.assertTrue(any(item.startswith("capture/codex:") for item in failures))
        finally:
            prompt_stats.WORKFLOW_SIGNALS["capture"] = original


if __name__ == "__main__":
    unittest.main()
