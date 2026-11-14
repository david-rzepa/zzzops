from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("prompt_stats.py")
SPEC = importlib.util.spec_from_file_location("prompt_stats", SCRIPT)
assert SPEC and SPEC.loader
prompt_stats = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prompt_stats)
ROOT = Path(__file__).resolve().parents[1]


class PromptStatsTests(unittest.TestCase):
    def test_canonical_size_is_line_ending_invariant(self) -> None:
        lf = b"one\ntwo\n"
        expected = prompt_stats.canonical_size(lf)
        self.assertEqual(prompt_stats.canonical_size(b"one\r\ntwo\r\n"), expected)
        self.assertEqual(prompt_stats.canonical_size(b"one\rtwo\r"), expected)

    def test_skills_references_and_node_prompts_are_counted(self) -> None:
        paths = {path.relative_to(ROOT).as_posix() for path in prompt_stats.prompt_files(ROOT)}
        for path in (prompt_stats.CLI_USAGE_PROMPT, prompt_stats.SETUP_PROMPT, prompt_stats.REPAIR_PROMPT,
                     prompt_stats.COMMUNICATION_PROMPT,
                     "plugins/zzzops/skills/execute-zzzops/SKILL.md",
                     "plugins/zzzops/zzzops/templates/default/prompts/implement.md"):
            self.assertIn(path, paths)

    def test_report_includes_rows_and_total(self) -> None:
        report = prompt_stats.render_report([("AGENTS.md", 8, 2)])
        self.assertIn("| `AGENTS.md` | 8 | 2 |", report)
        self.assertIn("| **Total** | **8** | **2** |", report)

    def test_only_always_loaded_and_hot_path_contexts_are_enforced(self) -> None:
        measurements = prompt_stats.enforced_context_profiles(ROOT)
        self.assertEqual(set(prompt_stats.ENFORCED_PROMPT_BUDGETS), set(measurements))
        self.assertEqual([], prompt_stats.budget_overruns(measurements))
        self.assertEqual(measurements["capture/codex"], prompt_stats.workflow_profile(ROOT, "capture", "codex")[:2])

    def test_cold_path_growth_is_advisory_but_hot_path_growth_fails(self) -> None:
        limits = {"capture/codex": 10}
        self.assertEqual([], prompt_stats.budget_overruns({"capture/codex": (40, 10)}, limits))
        self.assertEqual([("capture/codex", 11, 10)], prompt_stats.budget_overruns({"capture/codex": (44, 11)}, limits))

    def test_enforced_report_distinguishes_advisory_inventory(self) -> None:
        report = prompt_stats.render_enforced_budget_report(
            {"capture/codex": (40, 10)}, {"capture/codex": 20}, prompt_count=3, inventory_bytes=100, inventory_tokens=25)
        self.assertIn("| capture/codex | 40 | 10 | 20 | PASS |", report)
        self.assertIn("Advisory total inventory: 3 prompts", report)

    def test_policy_context_accounting_separates_hot_project_and_cold_content(self) -> None:
        profiles = prompt_stats.policy_context_profiles(ROOT)
        self.assertEqual({"static-hot-prompts", "current-project-policy", "cold-default-review"}, set(profiles))
        self.assertGreater(profiles["cold-default-review"][1], 0)

    def test_workflow_profiles_cover_every_skill(self) -> None:
        report = prompt_stats.render_workflow_report(ROOT)
        for workflow in prompt_stats.WORKFLOW_PROMPTS:
            self.assertIn(f"| {workflow} |", report)
            profiles = prompt_stats.workflow_path_profiles(ROOT, workflow, "codex")
            self.assertLessEqual(profiles["entry"][1], profiles["hot"][1])
        self.assertEqual(set(prompt_stats.WORKFLOW_PROMPTS), set(prompt_stats.WORKFLOW_SIGNALS))

    def test_routed_workflow_signals_are_present(self) -> None:
        failures, _ = prompt_stats.evaluate_workflows(ROOT)
        self.assertEqual([], failures)

    def test_capture_signals_hold_the_intent_check(self) -> None:
        for signal in ("settings.intent", "Amend the intent", "Project intent:"):
            self.assertIn(signal, prompt_stats.WORKFLOW_SIGNALS["capture"])


if __name__ == "__main__":
    unittest.main()
