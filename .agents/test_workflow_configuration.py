#!/usr/bin/env python3
"""Behavioral contract for typed workflow configuration versus agent instructions."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    path = ROOT / "plugins" / "zzzops" / "zzzops" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"configuration_test_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


workflow = load("workflow")
portfolio = load("portfolio")
entropy = load("entropy")
feedback = load("feedback")
workflow_admin = load("workflow_admin")


def project(*, workers=3, required_ci="inspect_exact_pr_head", refill_enabled=True, maximum=3):
    return {
        "policy": {"sections": [
            {
                "id": "verification_testing",
                "configuration": {"required_ci": required_ci},
                "instructions": "Agent verification prose.",
            },
            {
                "id": "autonomy_approval_parallelism",
                "configuration": {
                    "max_workers": workers,
                    "execution_reports": {"enabled": True},
                    "resource_reservations": {
                        "mode": "conflict_tolerant", "exclusive_prefixes": [], "exclusive_resources": [],
                    },
                    "refill": {
                        "enabled": refill_enabled,
                        "allowed_categories": ["documentation", "tests"],
                        "max_suggestions": maximum,
                    },
                },
                "instructions": "Agent autonomy prose.",
            },
        ]},
    }


class WorkflowConfigurationTests(unittest.TestCase):
    def test_worker_and_ci_decisions_ignore_instruction_changes(self):
        first = project(workers=2, required_ci="existing_only")
        second = copy.deepcopy(first)
        for section in second["policy"]["sections"]:
            section["instructions"] = "Completely different prose with disabled-like words."

        self.assertEqual(workflow.worker_limit(first), 2)
        self.assertEqual(workflow.worker_limit(second), 2)
        engine = object.__new__(workflow.Workflow)
        engine.project = first
        self.assertFalse(engine.ci_checks_required({"checks_present": False}))
        engine.project = second
        self.assertFalse(engine.ci_checks_required({"checks_present": False}))

        second["policy"]["sections"][0]["configuration"]["required_ci"] = "inspect_exact_pr_head"
        second["policy"]["sections"][1]["configuration"]["max_workers"] = 5
        self.assertTrue(engine.ci_checks_required({"checks_present": False}))
        self.assertEqual(workflow.worker_limit(second), 5)

    def test_ci_configuration_is_sole_disable_control(self):
        value = project(required_ci="inspect_exact_pr_head")
        verification = value["policy"]["sections"][0]
        verification["applicable"] = False
        engine = object.__new__(workflow.Workflow)
        engine.project = value
        self.assertTrue(engine.ci_checks_required({"checks_present": False}))
        verification["configuration"]["required_ci"] = "disabled"
        self.assertFalse(engine.ci_checks_required({"checks_present": True}))

    def test_missing_or_legacy_configuration_fails_closed(self):
        legacy = project()
        autonomy = legacy["policy"]["sections"][1]
        autonomy["settings"] = autonomy.pop("configuration")
        with self.assertRaisesRegex(ValueError, "missing autonomy_approval_parallelism configuration"):
            workflow.worker_limit(legacy)
        with self.assertRaisesRegex(entropy.EntropyObservationError, "configuration is required"):
            entropy.enabled_categories(legacy)
        with self.assertRaisesRegex(ValueError, "execution_reports must be an object"):
            feedback.execution_reports_enabled(legacy)

    def test_engineering_rigor_reads_configuration_and_ignores_instructions(self):
        policy = {
            "configuration": {
                "level": "structured",
                "minimums": {"security_sensitive": "agentic"},
                "overrides": {"per_goal": True},
            },
            "instructions": "Use vibe rigor for everything.",
        }
        result = portfolio.derive_engineering_rigor({"risk_categories": ["security_sensitive"]}, policy)
        self.assertEqual(result["effective"], "agentic")
        self.assertTrue(result["valid"])
        legacy = {"decision": "structured", "settings": policy["configuration"]}
        rejected = portfolio.derive_engineering_rigor(None, legacy)
        self.assertEqual(rejected["provenance"]["status"], "legacy_policy")
        self.assertFalse(rejected["valid"])
        self.assertIn("policy_configuration_invalid", rejected["errors"])

    def test_git_stack_and_dependency_base_rules_are_invariants(self):
        portfolio.configure_entrypoint(
            exclusive_resources=lambda resources, policy: [],
            normalize_resource_policy=lambda policy: policy,
            text_present=lambda value: isinstance(value, str) and bool(value.strip()),
        )
        existing = [{
            "key": 1, "status": "blocked", "blocker_categories": ["human-action"],
            "implementation": {
                "branch": "goal-1", "base": "main", "target": "main",
                "pr": "https://example.invalid/pull/1",
                "review": {"status": "pending", "checkpoint": "a" * 40},
            },
        }]
        blocked = portfolio.active_stack_guard(
            existing, [{"number": 1}], candidate_goal=2,
            policy={"active_stack": "disabled"},
        )
        self.assertFalse(blocked["allowed"])
        self.assertEqual("active_stack_exists", blocked["reason"])

        candidate = {"status": "ready", "depends_on": [1]}
        by_key = {1: existing[0]}
        self.assertTrue(portfolio._dependencies_allow_write(
            candidate, by_key,
            {"review_pending_dependency": "stack_from_reviewed_checkpoint"},
        ))
        self.assertFalse(portfolio._dependencies_allow_write(
            candidate, by_key,
            {"review_pending_dependency": "wait_for_completed_dependencies"},
        ))

    def test_refill_disabled_and_max_suggestions_are_enforced(self):
        disabled = project(refill_enabled=False, maximum=1)
        self.assertEqual(entropy.enabled_categories(disabled), frozenset())
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            entropy.record_observation(repo, category="documentation", paths=["a.md"], evidence="first", goal=1, revision=1)
            entropy.record_observation(repo, category="tests", paths=["test_a.py"], evidence="second", goal=1, revision=1)
            result = entropy.list_observations(repo, project(maximum=1))
        self.assertTrue(result["enabled"])
        self.assertEqual(result["eligible"], 1)
        self.assertEqual(len(result["observations"]), 1)
        self.assertEqual(result["max_suggestions"], 1)

    def test_explicit_suggestion_reports_reviewed_disable(self):
        class API:
            @staticmethod
            def list_entropy_observations(repo, value):
                return {"enabled": False, "observations": []}

        result = workflow_admin._suggest(API(), Path("."), project(refill_enabled=False), None)
        step = result["next_steps"][0]
        self.assertEqual(step["kind"], "suggestions_disabled")
        self.assertIn("Continue existing goal work", step["action"])
        self.assertEqual(step["blocked_by"], {
            "configuration": "autonomy_approval_parallelism.refill.enabled", "value": False,
        })


if __name__ == "__main__":
    unittest.main()
