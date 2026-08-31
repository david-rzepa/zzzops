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

    def test_routed_bootstrap_references_are_counted_as_prompts(self) -> None:
        root = SCRIPT.parents[1]
        paths = {path.relative_to(root).as_posix() for path in prompt_stats.prompt_files(root)}
        self.assertIn(
            "plugins/zzzops/zzzops/references/bootstrap/ANALYZE.md",
            paths,
        )

    def test_report_includes_rows_and_total(self) -> None:
        report = prompt_stats.render_report([("AGENTS.md", 8, 2)])
        self.assertIn("| `AGENTS.md` | 8 | 2 |", report)
        self.assertIn("| **Total** | **8** | **2** |", report)

    def test_only_always_loaded_and_hot_path_contexts_are_enforced(self) -> None:
        root = SCRIPT.parents[1]
        measurements = prompt_stats.enforced_context_profiles(root)
        self.assertEqual(
            {"always-loaded/codex", "capture/codex", "execution/codex"},
            set(measurements),
        )
        self.assertEqual(
            prompt_stats.workflow_profile(root, "capture", "codex")[:2],
            measurements["capture/codex"],
        )

    def test_cold_path_growth_is_advisory_but_hot_path_growth_fails(self) -> None:
        limits = {
            "always-loaded/codex": 700,
            "capture/codex": 3_324,
            "execution/codex": 8_465,
        }
        within_limits = {
            "always-loaded/codex": (2_499, 625),
            "capture/codex": (13_295, 3_324),
            "execution/codex": (33_806, 8_452),
            "bootstrap-greenfield/codex": (4_000_000, 1_000_000),
        }
        self.assertEqual([], prompt_stats.budget_overruns(within_limits, limits))

        for context, limit in limits.items():
            with self.subTest(context=context):
                over_limit = dict(within_limits)
                over_limit[context] = (4 * (limit + 1), limit + 1)
                self.assertEqual(
                    [(context, limit + 1, limit)],
                    prompt_stats.budget_overruns(over_limit, limits),
                )

    def test_enforced_report_distinguishes_advisory_inventory(self) -> None:
        report = prompt_stats.render_enforced_budget_report(
            {"always-loaded/codex": (2_499, 625)},
            {"always-loaded/codex": 700},
            prompt_count=29,
            inventory_bytes=81_165,
            inventory_tokens=20_302,
        )
        self.assertIn("# Enforced prompt budgets", report)
        self.assertIn("| always-loaded/codex | 2499 | 625 | 700 | PASS |", report)
        self.assertIn("Advisory total inventory: 29 prompts", report)

    def test_policy_context_accounting_separates_hot_project_and_cold_content(self) -> None:
        root = SCRIPT.parents[1]
        profiles = prompt_stats.policy_context_profiles(root)
        self.assertEqual(
            {"static-hot-prompts", "current-project-policy", "cold-default-review"},
            set(profiles),
        )
        self.assertGreater(profiles["static-hot-prompts"][0], 0)
        self.assertGreater(profiles["cold-default-review"][0], 0)
        report = prompt_stats.render_enforced_budget_report(
            {"always-loaded/codex": (1, 1)}, {"always-loaded/codex": 2},
            prompt_count=1, inventory_bytes=1, inventory_tokens=1, policy_context=profiles,
        )
        self.assertIn("## Policy context boundary", report)
        self.assertIn("| current-project-policy |", report)

    def test_workflow_profiles_cover_codex(self) -> None:
        root = SCRIPT.parents[1]
        report = prompt_stats.render_workflow_report(root)
        self.assertEqual(
            {"agentic-coaching", "bootstrap-greenfield", "bootstrap-brownfield", "capture", "execution", "policy-review", "migration", "suggestion", "installation-validation", "acceptance", "feedback"},
            set(prompt_stats.WORKFLOW_PROMPTS),
        )
        self.assertEqual(set(prompt_stats.WORKFLOW_PROMPTS), set(prompt_stats.WORKFLOW_SIGNALS))
        self.assertIn("| Workflow | Codex bytes | Codex est. tokens |", report)
        self.assertIn("Advisory routed workflow", report)
        self.assertEqual({"codex"}, set(prompt_stats.HARNESS_PROMPTS))
        for workflow in prompt_stats.WORKFLOW_PROMPTS:
            self.assertIn(f"| {workflow} |", report)

    def test_proactive_delegation_signal_reaches_every_applicable_workflow(self) -> None:
        root = SCRIPT.parents[1]
        for workflow in prompt_stats.PROACTIVE_DELEGATION_WORKFLOWS:
            self.assertIn(prompt_stats.DELEGATION_PROMPT, prompt_stats.WORKFLOW_PROMPTS[workflow])
        delegation = (root / prompt_stats.DELEGATION_PROMPT).read_text(encoding="utf-8")
        for phrase in (
            "authority/safety", "conflict/coupling", "triviality", "overhead",
            "record why", "sequential fallback", "concise evidence-linked summaries",
            "Only the coordinator owns", "claims/reservations", "external writes",
            "Read-only never write", "disjoint worktrees",
        ):
            self.assertIn(phrase, delegation)
        missing = [
            workflow for workflow in sorted(prompt_stats.PROACTIVE_DELEGATION_WORKFLOWS)
            if prompt_stats.PROACTIVE_DELEGATION_SIGNAL
            not in prompt_stats.workflow_profile(root, workflow, "codex")[2]
        ]
        self.assertEqual([], missing)

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
