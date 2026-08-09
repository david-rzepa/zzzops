import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PLUGIN_ROOT = Path(__file__).parent.parent / "plugins" / "zzzops"
MODULE_PATH = PLUGIN_ROOT / "zzzops" / "zzzops.py"
SPEC = importlib.util.spec_from_file_location("zzzops", MODULE_PATH)
zzzops = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(zzzops)


class PolicyModuleTests(unittest.TestCase):
    def test_entry_point_reexports_policy_state_contract(self):
        policy = zzzops._policy
        for name in (
            "project_digest", "read_project_state", "validate_project_state",
            "validate_policy", "render_project", "render_project_audit",
            "normalize_resource_policy", "policy_default_catalog", "policy_content_digest",
            "prepare_policy_defaults", "compare_policy_defaults",
        ):
            self.assertIs(getattr(zzzops, name), getattr(policy, name))


class ReservationModuleTests(unittest.TestCase):
    def test_entry_point_reexports_reservation_contract(self):
        reservation = zzzops._reservation
        for name in (
            "GitHubReservationAdapter", "acquire_reservation_bundle",
            "renew_reservation_bundle", "release_reservation_bundle",
            "reservation_cli_message",
        ):
            self.assertIs(getattr(zzzops, name), getattr(reservation, name))


class FeedbackModuleTests(unittest.TestCase):
    def test_entry_point_reexports_feedback_contract(self):
        feedback = zzzops._feedback
        for name in (
            "record_execution_report", "load_execution_reports", "prepare_feedback",
            "submit_feedback", "zzzops_provenance", "validate_execution_report",
        ):
            self.assertIs(getattr(zzzops, name), getattr(feedback, name))


class GoalsModuleTests(unittest.TestCase):
    def test_entry_point_reexports_managed_goal_contract(self):
        goals = zzzops._goals
        for name in (
            "parse_managed_goal", "validate_managed_goal", "render_managed_goal",
            "github_goal_record", "github_archived_goal_record", "current_goal_schema_label",
            "validate_github_issue_goal", "validate_goal_transition", "load_goal_transition",
            "apply_goal_transition", "ensure_current_goal_schema", "migrate_open_goal_schemas",
            "GoalTransitionProviderError",
        ):
            self.assertIs(getattr(zzzops, name), getattr(goals, name))


class PortfolioModuleTests(unittest.TestCase):
    def test_entry_point_reexports_portfolio_contract(self):
        portfolio = zzzops._portfolio
        for name in ("audit_portfolio", "build_portfolio_snapshot", "compact_portfolio_output"):
            self.assertIs(getattr(zzzops, name), getattr(portfolio, name))


class InitializationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        (self.repo / ".zzzops").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def plan(self):
        inspection = zzzops.inspect_initialization(self.repo)
        init_template = MODULE_PATH.parent / "templates" / "project-goals" / "INIT_PLAN.json"
        policy = json.loads(init_template.read_text(encoding="utf-8"))["policy"]
        policy["sections"][0]["settings"]["repository_identity"] = "example/repo"
        policy["sections"][0]["decision"] = "github_issues"
        policy["sections"][0]["settings"]["authority"] = "github_issues"
        policy["sections"][0]["default_disposition"] = "changed"
        return {
            "schema_version": 1,
            "base_digest": inspection["base_digest"],
            "confirmed": True,
            "backend": "github_issues",
            "repository": {"identity": "example/repo", "remote": "local"},
            "charter": {
                "outcome": "Agents complete durable project work autonomously.",
                "beneficiaries": ["maintainers"],
                "why_it_matters": "Less babysitting and no lost work.",
                "time_horizon": "ongoing",
                "kpis": [{
                    "name": "Autonomous transitions", "why": "Measures autonomy",
                    "baseline": "unknown", "target": ">=80%", "evidence": "goal history",
                    "cadence": "monthly",
                }],
                "acceptance_criteria": ["A fresh repository can initialize and capture work."],
                "precedence": "safety, correctness, privacy, then autonomy",
                "constraints": ["standard library only"],
                "non_goals": ["replace project management suites"],
                "unacceptable_tradeoffs": ["inventing user decisions"],
            },
            "evidence": [
                {"id": "E-001", "kind": "observed", "source": "README.md", "finding": "durable goals"},
                {"id": "E-002", "kind": "proposed", "source": "agent synthesis", "finding": "charter"},
            ],
            "confirmations": [{"evidence_id": "E-002", "confirmed_by": "user", "date": "2026-07-16"}],
            "github": {"usable": True},
            "policy": policy,
        }

    @mock.patch.object(zzzops, "command_probe", return_value={"available": False, "ok": False, "detail": "test"})
    @mock.patch.object(zzzops, "github_repository_probe", return_value={"available": False, "usable": False})
    def test_inspect_is_read_only_and_reports_incomplete(self, _github, _probe):
        project = self.repo / ".zzzops" / "PROJECT.md"
        self.assertFalse(project.exists())
        result = zzzops.inspect_initialization(self.repo)
        self.assertFalse(result["initialized"])
        self.assertFalse(result["valid_state"])
        self.assertIn("outcome", result["missing_charter_fields"])
        self.assertFalse(project.exists())

    @mock.patch.object(zzzops, "command_probe", return_value={"available": False, "ok": False, "detail": "test"})
    @mock.patch.object(zzzops, "github_repository_probe", return_value={"available": False, "usable": False})
    def test_validate_apply_and_reinspect(self, _github, _probe):
        plan = self.plan()
        documentation = next(section for section in plan["policy"]["sections"] if section["id"] == "documentation_style")
        self.assertEqual("outcome_first", documentation["settings"]["communication"]["style"])
        self.assertEqual([], zzzops.validate_plan(self.repo, plan))
        applied = zzzops.apply_plan(self.repo, plan)
        self.assertTrue(applied["changed"])
        result = zzzops.inspect_initialization(self.repo)
        self.assertFalse(result["initialized"])
        self.assertEqual("github_issues", result["state"]["backend"])
        self.assertEqual([], result["missing_charter_fields"])
        self.assertEqual(len(zzzops.POLICY_SECTION_IDS), len(result["decision_blockers"]))
        project_text = (self.repo / ".zzzops" / "PROJECT.md").read_text(encoding="utf-8")
        self.assertIn("Agents complete durable", project_text)
        self.assertNotIn("E-002: agent synthesis — charter", project_text)
        self.assertIn("E-002: agent synthesis — charter", (self.repo / ".zzzops" / "PROJECT_AUDIT.md").read_text(encoding="utf-8"))
        reviewed = zzzops.confirm_project(
            self.repo, applied["policy_digest"], "test-user", [], True,
        )
        self.assertTrue(reviewed["initialized"])
        self.assertEqual([], reviewed["decision_blockers"])
        compact = (self.repo / ".zzzops" / "PROJECT.md").read_text(encoding="utf-8")
        audit = (self.repo / ".zzzops" / "PROJECT_AUDIT.md").read_text(encoding="utf-8")
        self.assertIn("PROJECT_AUDIT.md", compact)
        self.assertNotIn("E-002: agent synthesis", compact)
        self.assertIn("E-002: agent synthesis", audit)
        self.assertLess(len(compact), len(audit))
        self.assertNotIn("zzzops-project-state", compact)
        self.assertTrue((self.repo / ".zzzops" / "POLICY.json").is_file())
        self.assertTrue(zzzops.inspect_initialization(self.repo)["initialized"])

        altered_audit = audit.replace("Decision: github_issues", "Decision: changed", 1)
        (self.repo / ".zzzops" / "PROJECT_AUDIT.md").write_text(altered_audit, encoding="utf-8")
        compact_state = zzzops.read_project_state(self.repo)[2]
        self.assertIn("audit policy artifact digest changed", zzzops.validate_project_artifacts(self.repo, compact_state))

        (self.repo / ".zzzops" / "PROJECT_AUDIT.md").write_text(audit + "tampered\n", encoding="utf-8")
        changed = zzzops.inspect_initialization(self.repo)
        self.assertFalse(changed["initialized"])
        self.assertIn("audit policy artifact digest changed", changed["state_error"])

    def test_review_is_exact_digest_explicit_and_incremental(self):
        applied = zzzops.apply_plan(self.repo, self.plan())
        with self.assertRaisesRegex(ValueError, "digest changed"):
            zzzops.confirm_project(self.repo, "sha256:stale", "test-user", [], True)
        first = zzzops.confirm_project(
            self.repo, applied["policy_digest"], "test-user", ["backend"], False,
        )
        self.assertFalse(first["initialized"])
        self.assertNotIn("policy:backend", first["decision_blockers"])
        self.assertIn("policy:verification_testing", first["decision_blockers"])
        final = zzzops.confirm_project(self.repo, first["policy_digest"], "test-user", [], True)
        self.assertTrue(final["initialized"])

    def test_policy_rereview_preserves_history_and_appends_once(self):
        first = zzzops.apply_plan(self.repo, self.plan())
        zzzops.confirm_project(self.repo, first["policy_digest"], "first-reviewer", [], True)
        prior = json.loads(json.dumps(zzzops.read_project_state(self.repo)[2]["history"]))

        second = zzzops.apply_plan(self.repo, self.plan())
        pending = zzzops.read_project_state(self.repo)[2]
        self.assertEqual(prior, pending["history"][:-1])
        self.assertEqual(len(prior) + 1, len(pending["history"]))
        self.assertEqual("ZzzOps initialization", pending["history"][-1]["actor"])

        with self.assertRaisesRegex(ValueError, "base_digest is stale"):
            zzzops.apply_plan(self.repo, second)
        self.assertEqual(pending["history"], zzzops.read_project_state(self.repo)[2]["history"])

        with self.assertRaisesRegex(ValueError, "digest changed"):
            zzzops.confirm_project(self.repo, "sha256:stale", "second-reviewer", [], True)
        self.assertEqual(pending["history"], zzzops.read_project_state(self.repo)[2]["history"])

        zzzops.confirm_project(self.repo, second["policy_digest"], "second-reviewer", [], True)
        reviewed = zzzops.read_project_state(self.repo)[2]
        self.assertEqual(prior, reviewed["history"][:len(prior)])
        self.assertEqual(len(prior) + 2, len(reviewed["history"]))
        self.assertEqual("second-reviewer", reviewed["history"][-1]["actor"])
        audit = (self.repo / ".zzzops" / "PROJECT_AUDIT.md").read_text(encoding="utf-8")
        for entry in reviewed["history"]:
            self.assertIn(entry["change"], audit)

    def test_clean_initialization_starts_with_one_pending_history_entry(self):
        zzzops.apply_plan(self.repo, self.plan())
        history = zzzops.read_project_state(self.repo)[2]["history"]
        self.assertEqual(1, len(history))
        self.assertEqual("ZzzOps initialization", history[0]["actor"])

    def test_bound_charter_and_canonical_policy_changes_invalidate_review(self):
        applied = zzzops.apply_plan(self.repo, self.plan())
        zzzops.confirm_project(self.repo, applied["policy_digest"], "test-user", [], True)
        project = self.repo / ".zzzops" / "PROJECT.md"
        original = project.read_text(encoding="utf-8")
        project.write_text(original + "changed\n", encoding="utf-8")
        self.assertIn("project policy artifact digest changed", zzzops.inspect_initialization(self.repo)["state_error"])
        project.write_text(original, encoding="utf-8")
        policy = self.repo / ".zzzops" / "POLICY.json"
        state = json.loads(policy.read_text(encoding="utf-8"))
        state["policy"]["sections"][0]["decision"] = "changed"
        policy.write_text(json.dumps(state), encoding="utf-8")
        self.assertIn("policy approval digest changed", zzzops.inspect_initialization(self.repo)["state_error"])

    def test_initialization_plan_digest_binds_existing_policy_state(self):
        plan = self.plan()
        zzzops.apply_plan(self.repo, plan)
        plan = self.plan()
        state_path = self.repo / ".zzzops" / "POLICY.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["revision"] += 1
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.assertIn("base_digest is stale or missing", zzzops.validate_plan(self.repo, plan))

    def test_policy_preserves_unknown_settings_and_agents_cannot_preapprove(self):
        plan = self.plan()
        section = plan["policy"]["sections"][4]
        section["settings"]["project_extension"] = {"custom": True}
        section["default_disposition"] = "changed"
        section["review"]["approved"] = True
        self.assertTrue(any("review must be pending" in error for error in zzzops.validate_plan(self.repo, plan)))
        section["review"]["approved"] = False
        applied = zzzops.apply_plan(self.repo, plan)
        zzzops.confirm_project(self.repo, applied["policy_digest"], "test-user", [], True)
        state = zzzops.read_project_state(self.repo)[2]
        self.assertEqual({"custom": True}, state["policy"]["sections"][4]["settings"]["project_extension"])

    def test_default_catalog_and_adopted_provenance_are_canonical(self):
        catalog = zzzops.policy_default_catalog()
        self.assertEqual(len(zzzops.POLICY_SECTION_IDS), len(catalog))
        self.assertEqual(catalog, zzzops.policy_default_catalog())
        for default_id, entry in catalog.items():
            self.assertEqual(default_id, entry["id"])
            self.assertEqual(1, entry["schema_version"])
            self.assertEqual(entry["digest"], zzzops.policy_content_digest(entry["content"]))

        missing_id = self.plan()
        next(item for item in missing_id["policy"]["sections"] if item["id"] == "documentation_style").pop("default_id")
        self.assertTrue(any("lacks a stable default identity" in error for error in zzzops.validate_plan(self.repo, missing_id)))
        malformed = self.plan()
        next(item for item in malformed["policy"]["sections"] if item["id"] == "documentation_style").pop("settings")
        self.assertTrue(any("settings must be an object" in error for error in zzzops.validate_plan(self.repo, malformed)))
        forged = self.plan()
        next(item for item in forged["policy"]["sections"] if item["id"] == "documentation_style")["default_provenance"] = "forged"
        self.assertTrue(any("default provenance must be an object" in error for error in zzzops.validate_plan(self.repo, forged)))

        applied = zzzops.apply_plan(self.repo, self.plan())
        state = zzzops.read_project_state(self.repo)[2]
        backend = next(item for item in state["policy"]["sections"] if item["id"] == "backend")
        documentation = next(item for item in state["policy"]["sections"] if item["id"] == "documentation_style")
        self.assertEqual("customized", backend["default_provenance"]["status"])
        adopted = documentation["default_provenance"]
        self.assertEqual("adopted", adopted["status"])
        self.assertEqual(1, adopted["schema_version"])
        self.assertEqual(adopted["digest"], zzzops.policy_content_digest(adopted["snapshot"]))
        self.assertTrue(adopted["source"]["revision"])
        self.assertTrue(adopted["source"]["version"])
        self.assertEqual([], zzzops.validate_project_state(state))
        self.assertTrue(applied["policy_digest"])
        summary = zzzops.inspect_initialization(self.repo)["policy_defaults"]
        self.assertEqual(len(zzzops.POLICY_SECTION_IDS), len(summary))
        self.assertTrue(all("old_snapshot" not in item and "new_snapshot" not in item for item in summary))

        adopted["digest"] = "sha256:" + "0" * 64
        self.assertTrue(any("default_provenance.digest" in error for error in zzzops.validate_project_state(state)))

    def test_default_comparison_is_progressive_and_never_attributes_legacy_values(self):
        zzzops.apply_plan(self.repo, self.plan())
        policy = zzzops.read_project_state(self.repo)[2]["policy"]
        catalog = zzzops.policy_default_catalog()
        default_id = "zzzops.policy.documentation_style"
        changed = json.loads(json.dumps(catalog))
        changed[default_id]["content"]["decision"] = "A newer documented default."
        changed[default_id]["digest"] = zzzops.policy_content_digest(changed[default_id]["content"])
        quality_id = "zzzops.policy.code_quality"
        changed[quality_id]["content"]["decision"] = "A newer quality default."
        changed[quality_id]["digest"] = zzzops.policy_content_digest(changed[quality_id]["content"])

        compact = {item["section_id"]: item for item in zzzops.compare_policy_defaults(policy, changed)}
        self.assertEqual("update_available", compact["documentation_style"]["status"])
        self.assertEqual("update_available", compact["code_quality"]["status"])
        self.assertNotIn("old_snapshot", compact["documentation_style"])
        selected = zzzops.compare_policy_defaults(policy, changed, {"documentation_style"})
        documentation = next(item for item in selected if item["section_id"] == "documentation_style")
        self.assertIn("old_snapshot", documentation)
        self.assertIn("new_snapshot", documentation)
        self.assertEqual("customized", compact["backend"]["status"])

        legacy = json.loads(json.dumps(policy))
        next(item for item in legacy["sections"] if item["id"] == "documentation_style").pop("default_provenance")
        legacy_result = {item["section_id"]: item for item in zzzops.compare_policy_defaults(legacy, changed)}
        self.assertEqual("unknown_origin", legacy_result["documentation_style"]["status"])
        self.assertEqual([], zzzops.validate_policy(legacy, False))
        prepared_legacy = zzzops.prepare_policy_defaults(self.repo, legacy, legacy)
        self.assertNotIn(
            "default_provenance",
            next(item for item in prepared_legacy["sections"] if item["id"] == "documentation_style"),
        )

        provenance = next(item for item in policy["sections"] if item["id"] == "documentation_style")["default_provenance"]
        provenance["declined_digest"] = changed[default_id]["digest"]
        declined = {item["section_id"]: item for item in zzzops.compare_policy_defaults(policy, changed)}
        self.assertEqual("declined", declined["documentation_style"]["status"])

    def test_changed_default_acceptance_uses_normal_policy_review(self):
        first = zzzops.apply_plan(self.repo, self.plan())
        zzzops.confirm_project(self.repo, first["policy_digest"], "first-reviewer", [], True)
        catalog = zzzops.policy_default_catalog()
        default_id = "zzzops.policy.documentation_style"
        catalog[default_id]["content"]["decision"] = "A newer documented default."
        catalog[default_id]["digest"] = zzzops.policy_content_digest(catalog[default_id]["content"])
        plan = self.plan()
        section = next(item for item in plan["policy"]["sections"] if item["id"] == "documentation_style")
        section["default_resolution"] = {"action": "accept", "digest": catalog[default_id]["digest"]}
        with mock.patch.object(zzzops._policy, "policy_default_catalog", return_value=catalog):
            stale = json.loads(json.dumps(plan))
            next(item for item in stale["policy"]["sections"] if item["id"] == "documentation_style")["default_resolution"]["digest"] = "sha256:" + "0" * 64
            self.assertTrue(any("default resolution is stale" in error for error in zzzops.validate_plan(self.repo, stale)))
            self.assertEqual([], zzzops.validate_plan(self.repo, plan))
            applied = zzzops.apply_plan(self.repo, plan)
        pending = zzzops.read_project_state(self.repo)[2]
        updated = next(item for item in pending["policy"]["sections"] if item["id"] == "documentation_style")
        self.assertEqual("A newer documented default.", updated["decision"])
        self.assertEqual(catalog[default_id]["digest"], updated["default_provenance"]["digest"])
        self.assertFalse(pending["initialized"])
        self.assertEqual(["policy:documentation_style"], applied["decision_blockers"])
        self.assertTrue(next(item for item in pending["policy"]["sections"] if item["id"] == "code_quality")["review"]["approved"])
        zzzops.confirm_project(self.repo, applied["policy_digest"], "second-reviewer", [], True)

    def test_changed_default_decline_is_stable_and_does_not_reprompt(self):
        first = zzzops.apply_plan(self.repo, self.plan())
        zzzops.confirm_project(self.repo, first["policy_digest"], "first-reviewer", [], True)
        catalog = zzzops.policy_default_catalog()
        default_id = "zzzops.policy.documentation_style"
        catalog[default_id]["content"]["decision"] = "A newer documented default."
        catalog[default_id]["digest"] = zzzops.policy_content_digest(catalog[default_id]["content"])
        plan = self.plan()
        section = next(item for item in plan["policy"]["sections"] if item["id"] == "documentation_style")
        section["default_resolution"] = {"action": "decline", "digest": catalog[default_id]["digest"]}
        with mock.patch.object(zzzops._policy, "policy_default_catalog", return_value=catalog):
            applied = zzzops.apply_plan(self.repo, plan)
            zzzops.confirm_project(self.repo, applied["policy_digest"], "second-reviewer", [], True)
            confirmed = zzzops.read_project_state(self.repo)[2]
            first_comparison = zzzops.compare_policy_defaults(confirmed["policy"], catalog)
            second_comparison = zzzops.compare_policy_defaults(confirmed["policy"], catalog)
        result = {item["section_id"]: item for item in first_comparison}
        self.assertEqual("declined", result["documentation_style"]["status"])
        self.assertEqual(first_comparison, second_comparison)

    def test_default_provenance_renders_plain_language(self):
        zzzops.apply_plan(self.repo, self.plan())
        state = zzzops.read_project_state(self.repo)[2]
        audit = zzzops.render_project_audit(state)
        self.assertIn("adopted from the recorded ZzzOps default", audit)
        self.assertIn("customized from a ZzzOps default", audit)

    def test_policy_review_guidance_loads_changed_default_snapshots_progressively(self):
        review = (MODULE_PATH.parents[1] / "skills" / "review-zzzops-policy" / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "Compare default IDs/digests first",
            "load full old/new snapshots only for changed or selected sections",
            "Missing legacy provenance stays unknown",
            "report customized values without replacement",
        ):
            self.assertIn(phrase, review)

    def test_project_policy_requires_resolvable_source_citations(self):
        applied = zzzops.apply_plan(self.repo, self.plan())
        state = zzzops.read_project_state(self.repo)[2]
        state["policy"]["evidence"] = []
        self.assertIn("policy.evidence must be a non-empty list", zzzops.validate_project_state(state))

    def test_approval_digest_rejects_machine_policy_tampering(self):
        applied = zzzops.apply_plan(self.repo, self.plan())
        zzzops.confirm_project(self.repo, applied["policy_digest"], "test-user", [], True)
        state = zzzops.read_project_state(self.repo)[2]
        state["policy"]["sections"][0]["decision"] = "changed"
        self.assertIn("policy approval digest changed", zzzops.validate_project_state(state))

    def test_not_applicable_policy_requires_explicit_review(self):
        plan = self.plan()
        section = plan["policy"]["sections"][7]
        section["applicable"] = False
        section["decision"] = "not applicable"
        section["default_disposition"] = "changed"
        section["rationale"] = "No user or developer documentation exists in this repository."
        applied = zzzops.apply_plan(self.repo, plan)
        self.assertIn("policy:documentation_style", applied["decision_blockers"])
        reviewed = zzzops.confirm_project(
            self.repo, applied["policy_digest"], "test-user", ["documentation_style"], False,
        )
        self.assertNotIn("policy:documentation_style", reviewed["decision_blockers"])

    def test_policy_conflict_remains_a_decision_blocker(self):
        plan = self.plan()
        plan["policy"]["sections"][1]["unresolved"] = [
            "AGENTS.md requires PRs but repository settings allow direct pushes."
        ]
        applied = zzzops.apply_plan(self.repo, plan)
        with self.assertRaisesRegex(ValueError, "resolve policy choices"):
            zzzops.confirm_project(
                self.repo, applied["policy_digest"], "test-user", ["git_review_release"], False,
            )
        self.assertIn("policy:git_review_release", zzzops.inspect_initialization(self.repo)["decision_blockers"])

    def test_cli_confirm_requires_and_uses_current_digest(self):
        applied = zzzops.apply_plan(self.repo, self.plan())
        result = subprocess.run(
            [
                sys.executable, str(MODULE_PATH), "--repo", str(self.repo),
                "init", "confirm", "--policy-digest", applied["policy_digest"],
                "--reviewer", "test-user", "--all",
            ],
            text=True, encoding="utf-8", capture_output=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        self.assertTrue(json.loads(result.stdout)["initialized"])

    def test_cli_without_command_shows_help_without_writing_local_state(self):
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--repo", str(self.repo)],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        self.assertIn("ZzzOps project control CLI", result.stdout)

    def test_rejects_unconfirmed_unknown_and_stale_plans(self):
        plan = self.plan()
        plan["confirmed"] = False
        plan["surprise"] = True
        plan["base_digest"] = "sha256:stale"
        errors = zzzops.validate_plan(self.repo, plan)
        self.assertTrue(any("unknown fields" in error for error in errors))
        self.assertIn("confirmed must be true", errors)
        self.assertIn("base_digest is stale or missing", errors)

    def test_github_backend_requires_observed_capability(self):
        plan = self.plan()
        plan["github"]["usable"] = False
        self.assertIn("github must contain only usable=true for github_issues", zzzops.validate_plan(self.repo, plan))

    def test_invalid_project_state_is_reported(self):
        project = self.repo / ".zzzops" / "POLICY.json"
        project.write_text("{bad}\n", encoding="utf-8")
        with mock.patch.object(zzzops, "command_probe", return_value={}), mock.patch.object(zzzops, "github_repository_probe", return_value={}):
            result = zzzops.inspect_initialization(self.repo)
        self.assertFalse(result["valid_state"])
        self.assertIn("Invalid canonical policy JSON", result["state_error"])

    def test_atomic_text_cleans_temporary_file_on_replace_failure(self):
        path = self.repo / ".zzzops" / "failure.md"
        with mock.patch.object(zzzops.os, "replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                zzzops.atomic_text(path, "new\n")
        self.assertFalse(path.exists())
        self.assertEqual([], list(path.parent.iterdir()))

    @mock.patch.object(zzzops.shutil, "which", return_value="git")
    @mock.patch.object(zzzops.subprocess, "run")
    def test_repository_size_uses_only_existing_git_tracked_bytes(self, run, _which):
        tracked = self.repo / "tracked.bin"
        ignored = self.repo / "ignored.bin"
        tracked.write_bytes(b"123456789")
        ignored.write_bytes(b"x" * 100)
        run.return_value = subprocess.CompletedProcess([], 0, stdout=b"tracked.bin\0missing.bin\0", stderr=b"")
        with mock.patch.object(zzzops, "REPOSITORY_SIZE_THRESHOLD_BYTES", 10):
            small = zzzops.repository_size_profile(self.repo)
            self.assertEqual("worktrees", small["mode"])
            self.assertEqual(9, small["bytes"])
            tracked.write_bytes(b"1234567890")
            boundary = zzzops.repository_size_profile(self.repo)
            self.assertEqual("read_only", boundary["mode"])
            self.assertEqual(10, boundary["bytes"])
        self.assertEqual(3, boundary["max_workers"])
        self.assertEqual("existing_git_tracked_worktree_bytes", boundary["measurement"])

    @mock.patch.object(zzzops.shutil, "which", return_value=None)
    def test_repository_size_falls_back_to_read_only_when_git_is_unavailable(self, _which):
        profile = zzzops.repository_size_profile(self.repo)
        self.assertFalse(profile["available"])
        self.assertEqual("read_only", profile["mode"])
        self.assertEqual(3, profile["max_workers"])

    def test_plugin_package_status_and_provenance_are_valid(self):
        status = zzzops.machinery_commit_status(self.repo)
        self.assertTrue(status["ok"])
        self.assertEqual("2.0.0", status["version"])
        self.assertRegex(status["revision"], r"^[0-9a-f]{64}$")
        self.assertEqual(0, status["processes"])

        provenance = zzzops.zzzops_provenance(self.repo)
        self.assertEqual(status["version"], provenance["version"])
        self.assertEqual(status["revision"], provenance["revision"])

    def test_rejects_unconfirmed_proposal(self):
        plan = self.plan()
        plan["confirmations"] = []
        errors = zzzops.validate_plan(self.repo, plan)
        self.assertIn("confirmations must be a non-empty list", errors)
        self.assertIn("unconfirmed proposals: E-002", errors)

    def test_rejects_unsupported_project_state_schema(self):
        project = self.repo / ".zzzops" / "POLICY.json"
        project.write_text(
            '{"schema_version": 99, "initialized": false, "backend": null, "repository": null, "revision": 0}\n',
            encoding="utf-8",
        )
        with mock.patch.object(zzzops, "command_probe", return_value={}), mock.patch.object(zzzops, "github_repository_probe", return_value={}):
            result = zzzops.inspect_initialization(self.repo)
        self.assertFalse(result["valid_state"])
        self.assertIn("schema_version must be 1", result["state_error"])

    def test_probe_output_redacts_url_userinfo(self):
        self.assertEqual("https://***@example.test/repo.git", zzzops.sanitize_output("https://secret@example.test/repo.git"))

    def test_project_state_path_is_stable(self):
        self.assertEqual(self.repo / ".zzzops" / "PROJECT.md", zzzops.project_path(self.repo))
        self.assertEqual(self.repo / ".zzzops" / "POLICY.json", zzzops.project_policy_path(self.repo))

    @mock.patch.object(zzzops.shutil, "which", return_value="gh")
    @mock.patch.object(zzzops.subprocess, "run")
    def test_github_probe_requires_issues_and_management_permission(self, run, _which):
        run.return_value = mock.Mock(
            returncode=0, stderr="",
            stdout=json.dumps({
                "nameWithOwner": "owner/repo", "url": "https://github.com/owner/repo",
                "hasIssuesEnabled": True, "viewerPermission": "TRIAGE",
            }),
        )
        result = zzzops.github_repository_probe(self.repo)
        self.assertTrue(result["usable"])
        self.assertEqual("owner/repo", result["identity"])
        run.return_value.stdout = json.dumps({
            "nameWithOwner": "owner/repo", "url": "https://github.com/owner/repo",
            "hasIssuesEnabled": False, "viewerPermission": "ADMIN",
        })
        disabled = zzzops.github_repository_probe(self.repo)
        self.assertFalse(disabled["usable"])
        self.assertEqual("issues disabled", disabled["detail"])
        run.return_value.stdout = json.dumps({
            "nameWithOwner": "owner/repo", "url": "https://github.com/owner/repo",
            "hasIssuesEnabled": True, "viewerPermission": "READ",
        })
        insufficient = zzzops.github_repository_probe(self.repo)
        self.assertFalse(insufficient["usable"])
        self.assertEqual("insufficient permission", insufficient["detail"])


class ExecutionReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        (self.repo / ".zzzops").mkdir()
        self.project = {
            "policy": {"sections": [{
                "id": "autonomy_approval_parallelism",
                "settings": {"execution_reports": {"enabled": True}},
            }]},
        }
        self.now = datetime(2026, 7, 21, 18, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def record(self, **overrides):
        values = {
            "workflow": "execute-zzzops",
            "agent": "codex",
            "issue": "avoidable_wait",
            "cause": "unnecessary_wait_for_timeout",
            "phase": "unblocking",
            "occurrences": 2,
            "wait_seconds": 30,
            "extra_tool_calls": 1,
            "estimated_tokens": 250,
            "now": self.now,
            "provenance": {"version": "v1.2.3-4-gabcdef0", "revision": "a" * 40},
        }
        values.update(overrides)
        return zzzops.record_execution_report(self.repo, self.project, **values)

    def test_feedback_cli_text_normalizes_utf8_bom_for_file_and_stdin(self):
        prompt = self.repo / "prompt.txt"
        for text in ("", "Feedback"):
            prompt.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
            from_file = zzzops.read_cli_text(str(prompt))
            with mock.patch.object(sys, "stdin", io.StringIO("\ufeff" + text)):
                from_stdin = zzzops.read_cli_text("-")
            self.assertEqual(text, from_file)
            self.assertEqual(from_file, from_stdin)

    def test_feedback_prepare_emits_utf8_bytes_under_non_utf8_inherited_encoding(self):
        prompt = self.repo / "prompt.txt"
        feedback = "Please preserve this em dash — exactly."
        prompt.write_bytes(b"\xef\xbb\xbf" + feedback.encode("utf-8"))
        environment = dict(os.environ)
        environment["PYTHONIOENCODING"] = "cp1252"
        command = [
            sys.executable, str(MODULE_PATH), "--repo", str(MODULE_PATH.parents[2]),
            "feedback", "prepare", "--prompt-file", str(prompt),
        ]

        first = subprocess.run(command, capture_output=True, check=False, env=environment)
        self.assertEqual(0, first.returncode, first.stderr.decode("utf-8", errors="replace"))
        decoded = first.stdout.decode("utf-8")
        prepared = json.loads(decoded)
        self.assertIn(feedback, prepared["body"])

        second = subprocess.run(command, capture_output=True, check=False, env=environment)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(prepared["digest"], json.loads(second.stdout.decode("utf-8"))["digest"])

    def test_record_is_constrained_local_and_policy_can_disable_it(self):
        result = self.record()
        self.assertTrue(result["recorded"])
        self.assertRegex(result["id"], r"^report-[0-9a-f]{64}$")
        report = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(3, report["schema_version"])
        self.assertEqual({"version": "v1.2.3-4-gabcdef0", "revision": "a" * 40}, report["zzzops"])
        self.assertEqual("avoidable_wait", report["issue"])
        self.assertEqual("unnecessary_wait_for_timeout", report["cause"])
        self.assertEqual(
            {"estimated_tokens": 250, "extra_tool_calls": 1, "wait_seconds": 30},
            report["impact"],
        )
        self.assertNotIn("project", json.dumps(report).lower())

        disabled = json.loads(json.dumps(self.project))
        disabled["policy"]["sections"][0]["settings"]["execution_reports"]["enabled"] = False
        skipped = zzzops.record_execution_report(
            self.repo, disabled, workflow="execute-zzzops", agent="codex",
            issue="redundant_update", cause="redundant_state_summary", phase="handoff",
        )
        self.assertEqual({"recorded": False, "reason": "disabled"}, skipped)
        self.assertEqual(1, len(zzzops.load_execution_reports(self.repo)))

        invalid = json.loads(json.dumps(self.project))
        invalid["policy"]["sections"][0]["settings"]["execution_reports"] = False
        with self.assertRaisesRegex(ValueError, "must be an object"):
            zzzops.record_execution_report(
                self.repo, invalid, workflow="execute-zzzops", agent="codex",
                issue="redundant_update", cause="redundant_state_summary", phase="handoff",
            )

    def test_record_rejects_unconstrained_or_invalid_content(self):
        with self.assertRaisesRegex(ValueError, "issue"):
            self.record(issue="C:/private/project-name")
        with self.assertRaisesRegex(ValueError, "cause"):
            self.record(cause="C:/private/project-name")
        with self.assertRaisesRegex(ValueError, "occurrences"):
            self.record(occurrences=0)
        with self.assertRaisesRegex(ValueError, "wait_seconds"):
            self.record(wait_seconds=-1)
        with self.assertRaisesRegex(ValueError, "version"):
            self.record(provenance={"version": "private project/version", "revision": "a" * 40})
        with self.assertRaisesRegex(ValueError, "revision"):
            self.record(provenance={"version": "v1.2.3", "revision": "short"})

    @mock.patch.object(zzzops.shutil, "which", return_value="gh")
    @mock.patch.object(zzzops.subprocess, "run")
    def test_feedback_preview_confirmation_and_successful_cleanup(self, run, _which):
        created = self.record()
        preview = zzzops.prepare_feedback(self.repo, "Please reduce unnecessary waits.")
        self.assertEqual("david-rzepa/zzzops", preview["target"])
        self.assertEqual("ZzzOps feedback", preview["title"])
        self.assertEqual(
            ["zzzops", "zzzops-feedback", "zzzops:schema:v1", "zzzops:status:new", "zzzops:priority:P2"],
            preview["labels"],
        )
        self.assertIn("Please reduce unnecessary waits.", preview["body"])
        self.assertIn("## Machinery observations", preview["body"])
        self.assertIn("### Waited for an avoidable timeout", preview["body"])
        self.assertIn("**ZzzOps build:** v1.2.3-4-gabcdef0 (revision " + "a" * 40 + ")", preview["body"])
        self.assertIn("**Observed:**", preview["body"])
        self.assertIn("**Measured impact:**", preview["body"])
        self.assertIn("**Typical recovery:**", preview["body"])
        self.assertIn("**Suggested investigation:**", preview["body"])
        self.assertIn("<summary>Immutable structured reports</summary>", preview["body"])
        self.assertNotIn("1 extra tool calls", preview["body"])
        self.assertIn('"issue":"avoidable_wait"', preview["body"])
        self.assertEqual([created["id"]], preview["report_ids"])
        self.assertRegex(preview["digest"], r"^sha256:[0-9a-f]{64}$")
        feedback_goal = zzzops.parse_managed_goal(preview["body"])
        self.assertEqual("new", feedback_goal["status"])
        self.assertEqual("P2", feedback_goal["priority"])

        with self.assertRaisesRegex(ValueError, "confirmation"):
            zzzops.submit_feedback(self.repo, "Please reduce unnecessary waits.", "sha256:wrong")
        self.assertEqual(1, len(zzzops.load_execution_reports(self.repo)))

        run.return_value = SimpleNamespace(returncode=0, stdout="https://github.com/david-rzepa/zzzops/issues/130\n", stderr="")
        submitted = zzzops.submit_feedback(
            self.repo, "Please reduce unnecessary waits.", preview["digest"],
        )
        self.assertEqual("https://github.com/david-rzepa/zzzops/issues/130", submitted["url"])
        self.assertEqual([], zzzops.load_execution_reports(self.repo))
        command = run.call_args.args[0]
        self.assertEqual([
            "gh", "issue", "create", "--repo", "david-rzepa/zzzops",
            "--title", "ZzzOps feedback", "--body-file", "-",
            "--label", "zzzops", "--label", "zzzops-feedback",
            "--label", "zzzops:schema:v1", "--label", "zzzops:status:new", "--label", "zzzops:priority:P2",
        ], command)
        self.assertEqual(preview["body"], run.call_args.kwargs["input"])

    def test_legacy_v2_report_remains_immutable_and_renders_unknown_provenance(self):
        created = self.record()
        path = Path(created["path"])
        report = json.loads(path.read_text(encoding="utf-8"))
        report["schema_version"] = 2
        report.pop("zzzops")
        report["id"] = zzzops.execution_report_id(report)
        legacy_path = path.with_name(report["id"] + ".json")
        path.unlink()
        legacy_path.write_text(json.dumps(report), encoding="utf-8")

        loaded = zzzops.load_execution_reports(self.repo)
        self.assertEqual(2, loaded[0]["schema_version"])
        body = zzzops.prepare_feedback(self.repo, "")["body"]
        self.assertIn("**ZzzOps build:** Unknown (schema v2 predates version provenance)", body)
        self.assertNotIn('"zzzops"', body)

    def test_feedback_provenance_uses_validated_plugin_package(self):
        provenance = zzzops.zzzops_provenance(self.repo)
        self.assertEqual("2.0.0", provenance["version"])
        self.assertRegex(provenance["revision"], r"^[0-9a-f]{64}$")

    def test_feedback_keeps_distinct_causes_separate_and_aggregates_matching_causes(self):
        self.record(
            issue="poor_tool_choice",
            cause="powershell_stdin_bom",
            occurrences=1,
            wait_seconds=5,
            extra_tool_calls=1,
            estimated_tokens=50,
        )
        self.record(
            issue="poor_tool_choice",
            cause="child_process_auth_unavailable",
            occurrences=2,
            wait_seconds=30,
            extra_tool_calls=2,
            estimated_tokens=300,
            now=self.now + timedelta(seconds=1),
        )
        self.record(
            issue="poor_tool_choice",
            cause="powershell_stdin_bom",
            occurrences=2,
            wait_seconds=10,
            extra_tool_calls=2,
            estimated_tokens=350,
            now=self.now + timedelta(seconds=2),
        )

        body = zzzops.prepare_feedback(self.repo, "")["body"]
        self.assertEqual(1, body.count("### PowerShell added a byte-order mark to standard input"))
        self.assertEqual(1, body.count("### Authentication was unavailable to a child process"))
        self.assertIn("3 occurrences; 15 seconds waiting; 3 extra tool calls; 400 estimated tokens", body)

    def test_feedback_separates_the_same_cause_by_zzzops_build(self):
        self.record(provenance={"version": "v1.0.0", "revision": "a" * 40})
        self.record(
            provenance={"version": "v1.1.0", "revision": "b" * 40},
            now=self.now + timedelta(seconds=1),
        )
        body = zzzops.prepare_feedback(self.repo, "")["body"]
        self.assertEqual(2, body.count("### Waited for an avoidable timeout"))
        self.assertIn("**ZzzOps build:** v1.0.0 (revision " + "a" * 40 + ")", body)
        self.assertIn("**ZzzOps build:** v1.1.0 (revision " + "b" * 40 + ")", body)

    @mock.patch.object(zzzops.shutil, "which", return_value="gh")
    @mock.patch.object(zzzops.subprocess, "run")
    def test_failed_submission_retains_reports(self, run, _which):
        self.record()
        preview = zzzops.prepare_feedback(self.repo, "Feedback")
        run.return_value = SimpleNamespace(returncode=1, stdout="", stderr="provider failed")
        with self.assertRaisesRegex(ValueError, "provider failed"):
            zzzops.submit_feedback(self.repo, "Feedback", preview["digest"])
        self.assertEqual(1, len(zzzops.load_execution_reports(self.repo)))

    @mock.patch.object(zzzops.shutil, "which", return_value="gh")
    @mock.patch.object(zzzops.subprocess, "run")
    def test_post_submit_drift_retains_changed_report(self, run, _which):
        created = self.record()
        preview = zzzops.prepare_feedback(self.repo, "Feedback")

        def provider(*_args, **_kwargs):
            path = zzzops.execution_report_directory(self.repo) / f"{created['id']}.json"
            changed = json.loads(path.read_text(encoding="utf-8"))
            changed["occurrences"] = 3
            path.write_text(json.dumps(changed), encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="https://github.com/david-rzepa/zzzops/issues/130\n", stderr="")

        run.side_effect = provider
        submitted = zzzops.submit_feedback(self.repo, "Feedback", preview["digest"])
        self.assertEqual([], submitted["deleted_report_ids"])
        self.assertEqual([created["id"]], submitted["retained_report_ids"])
        with self.assertRaisesRegex(ValueError, "content-addressed"):
            zzzops.load_execution_reports(self.repo)


class ManagedGoalTests(unittest.TestCase):
    def goal(self):
        return {
            "schema_version": 1, "status": "ready",
            "priority": "P1", "value": "high", "difficulty": "S", "confidence": "high",
            "parent": None, "depends_on": [],
            "claim": {"owner": None}, "blockers": [], "evidence": [],
            "next_action": "Run the focused probe.", "revision": 1,
        }

    def test_managed_goal_round_trip_preserves_unmanaged_text(self):
        original = "## Outcome / Why\n\nHuman context before.\n\n## Next action\n\nHuman context after.\n"
        body = zzzops.render_managed_goal(self.goal(), original, 42)
        self.assertEqual(self.goal(), zzzops.parse_managed_goal(body, 42))
        changed = self.goal()
        changed["status"] = "done"
        updated = zzzops.render_managed_goal(changed, body, 42)
        self.assertTrue(updated.startswith(original.rstrip("\n")))
        self.assertEqual("done", zzzops.parse_managed_goal(updated, 42)["status"])
        self.assertEqual(1, updated.count(zzzops.GOAL_BLOCK_START))
        managed_line = updated.split(zzzops.GOAL_BLOCK_START + "\n", 1)[1].split("\n", 1)[0]
        self.assertNotIn("\n", managed_line)

    def test_github_issue_envelope_is_human_first_and_issue_native(self):
        body = zzzops.render_managed_goal(self.goal(), "## Outcome / Why\n\nObservable value.\n", 42)
        self.assertEqual([], zzzops.validate_github_issue_goal(42, "Plain human title", body))
        self.assertTrue(any("redundant ZzzOps goal ID" in error for error in zzzops.validate_github_issue_goal(42, "[G-20260716-001-example] Plain human title", body)))
        self.assertTrue(any("rendered frontmatter" in error for error in zzzops.validate_github_issue_goal(42, "Plain", "---\nid: old\n---\n" + body)))

    def test_github_relationships_use_issue_numbers(self):
        goal = self.goal()
        goal["parent"] = 7
        goal["depends_on"] = [8, 9]
        self.assertEqual([], zzzops.validate_managed_goal(goal, 42))
        goal["depends_on"] = [8, 8, 42]
        errors = zzzops.validate_managed_goal(goal, 42)
        self.assertIn("depends_on entries must be unique", errors)
        self.assertIn("depends_on cannot contain the current issue", errors)

    def test_human_queue_is_derived_from_open_blockers(self):
        goal = self.goal()
        goal["blockers"] = [{"id": "B-001", "status": "open", "category": "human-action"}]
        self.assertTrue(zzzops.goal_needs_human(goal))
        goal["blockers"][0]["status"] = "resolved"
        self.assertFalse(zzzops.goal_needs_human(goal))
        goal["blockers"] = [{"id": "B-002", "status": "open", "category": "technical-unknown"}]
        self.assertTrue(zzzops.goal_needs_human(goal))

    def test_open_blocker_requires_known_category(self):
        goal = self.goal()
        goal["blockers"] = [{"id": "B-001", "status": "open"}]
        self.assertIn("blockers[0].category is invalid or missing", zzzops.validate_managed_goal(goal, 42))

    def test_managed_goal_rejects_unknown_or_partial_schema(self):
        goal = self.goal()
        goal["surprise"] = True
        goal["id"] = "G-redundant"
        goal["title"] = "Duplicated"
        goal["blocks"] = []
        goal["needs_human"] = False
        del goal["next_action"]
        errors = zzzops.validate_managed_goal(goal)
        self.assertTrue(any("unknown fields" in error for error in errors))
        self.assertIn("next_action is required", errors)

    def test_managed_goal_validates_branch_review_identity(self):
        goal = self.goal()
        goal["implementation"] = {
            "branch": "goal/example", "base": "dev", "target": "dev", "pr": None,
            "review": {"status": "pending", "checkpoint": "abc123"},
        }
        self.assertEqual([], zzzops.validate_managed_goal(goal))
        goal["implementation"]["review"]["status"] = "self_approved"
        self.assertIn("implementation.review.status is invalid", zzzops.validate_managed_goal(goal))

    def test_managed_goal_rejects_invented_lifecycle_enums(self):
        goal = self.goal()
        for field, value in (("status", "almost-done"), ("priority", "urgent"), ("value", "priceless"), ("difficulty", "heroic"), ("confidence", "vibes")):
            candidate = dict(goal)
            candidate[field] = value
            self.assertIn(f"{field} is invalid", zzzops.validate_managed_goal(candidate))


class FakeGoalTransitionAdapter:
    def __init__(self, issue):
        self.repository = "owner/repo"
        self.issue = json.loads(json.dumps(issue))
        self.updates = []
        self.comments = []
        self.failure = None
        self.response_mutation = None
        self.comment_response_mutation = None

    def get_issue(self, number):
        self.assert_number(number)
        return json.loads(json.dumps(self.issue))

    def update_issue(self, number, payload):
        self.assert_number(number)
        self.updates.append(json.loads(json.dumps(payload)))
        if self.failure:
            raise zzzops.GoalTransitionProviderError(self.failure)
        updated = json.loads(json.dumps(self.issue))
        updated.update({"body": payload["body"], "state": payload["state"], "updated_at": "2026-07-21T21:00:00Z"})
        updated["labels"] = [{"name": label} for label in payload["labels"]]
        self.issue = updated
        response = json.loads(json.dumps(updated))
        if self.response_mutation:
            self.response_mutation(response)
        return response

    def get_issue_comments(self, number):
        self.assert_number(number)
        return json.loads(json.dumps(self.comments))

    def create_issue_comment(self, number, body):
        self.assert_number(number)
        comment = {
            "id": len(self.comments) + 1, "body": body,
            "html_url": f"https://github.com/owner/repo/issues/42#issuecomment-{len(self.comments) + 1}",
        }
        self.comments.append(json.loads(json.dumps(comment)))
        self.issue["updated_at"] = "2026-07-21T20:30:00Z"
        response = json.loads(json.dumps(comment))
        if self.comment_response_mutation:
            self.comment_response_mutation(response)
        return response

    @staticmethod
    def assert_number(number):
        if number != 42:
            raise AssertionError(number)


class GoalTransitionTests(unittest.TestCase):
    def goal(self):
        return {
            "schema_version": 1, "status": "ready", "priority": "P2", "value": "high",
            "difficulty": "S", "confidence": "high", "parent": None, "depends_on": [],
            "claim": None, "blockers": [], "evidence": ["Baseline."],
            "next_action": "Run the probe.", "revision": 1,
            "implementation": {"branch": None, "base": None, "target": None, "pr": None,
                               "review": {"status": "not_started", "checkpoint": None}},
            "resources": [],
        }

    def issue(self):
        body = zzzops.render_managed_goal(self.goal(), "## Outcome / Why\n\nPreserve this human text.\n", 42)
        return {
            "number": 42, "title": "Transition safely", "body": body, "state": "open",
            "updated_at": "2026-07-21T20:00:00Z", "html_url": "https://github.com/owner/repo/issues/42",
            "labels": [{"name": "zzzops"}, {"name": "zzzops-feedback"},
                       {"name": "zzzops:status:ready"}, {"name": "zzzops:priority:P2"}],
        }

    def transition(self, issue=None):
        issue = issue or self.issue()
        desired = json.loads(json.dumps(self.goal()))
        desired.update({"status": "blocked", "priority": "P1", "revision": 2,
                        "next_action": "Wait for review."})
        desired["blockers"] = [{"id": "B-001", "status": "open", "category": "human-action"}]
        return {
            "schema_version": 1,
            "expected_revision": 1,
            "expected_digest": zzzops.github_goal_record(issue)["digest"],
            "goal": desired,
        }

    def test_transition_preserves_human_text_and_derives_provider_state(self):
        issue = self.issue()
        adapter = FakeGoalTransitionAdapter(issue)
        result = zzzops.apply_goal_transition(adapter, "owner/repo", 42, self.transition(issue))
        self.assertEqual(1, len(adapter.updates))
        self.assertEqual(1, len(adapter.comments))
        payload = adapter.updates[0]
        self.assertTrue(payload["body"].startswith("## Outcome / Why\n\nPreserve this human text."))
        self.assertEqual("open", payload["state"])
        self.assertEqual(
            {"zzzops", "zzzops-feedback", "zzzops:schema:v1", "zzzops:status:blocked", "zzzops:priority:P1"},
            set(payload["labels"]),
        )
        self.assertEqual({"number": 42, "revision": 2, "state": "open", "status": "blocked",
                          "url": "https://github.com/owner/repo/issues/42"}, result)
        history = zzzops.parse_goal_history(adapter.comments[0]["body"])
        self.assertEqual(issue["body"], history["prior_body"])
        self.assertEqual(["Baseline."], history["requested_goal"]["evidence"])
        self.assertEqual([], zzzops.parse_managed_goal(payload["body"], 42)["evidence"])

        adapter = FakeGoalTransitionAdapter(issue)
        transition = self.transition(issue)
        transition["goal"].update({"status": "done", "blockers": [], "next_action": "No further action."})
        result = zzzops.apply_goal_transition(adapter, "owner/repo", 42, transition)
        self.assertEqual("closed", result["state"])
        self.assertIn("zzzops:status:done", adapter.updates[0]["labels"])

    def test_transition_replaces_stale_schema_labels_with_current_schema(self):
        issue = self.issue()
        issue["labels"].append({"name": "zzzops:schema:v9"})
        adapter = FakeGoalTransitionAdapter(issue)

        zzzops.apply_goal_transition(adapter, "owner/repo", 42, self.transition(issue))

        self.assertIn("zzzops:schema:v1", adapter.updates[0]["labels"])
        self.assertNotIn("zzzops:schema:v9", adapter.updates[0]["labels"])

    def test_transition_rejects_stale_or_malformed_input_before_write(self):
        issue = self.issue()
        for change in ("revision", "digest", "schema", "revision_jump"):
            adapter = FakeGoalTransitionAdapter(issue)
            transition = self.transition(issue)
            if change == "revision":
                transition["expected_revision"] = 9
            elif change == "digest":
                transition["expected_digest"] = "0" * 64
            elif change == "schema":
                transition["surprise"] = True
            else:
                transition["goal"]["revision"] = 3
            with self.assertRaises(ValueError, msg=change):
                zzzops.apply_goal_transition(adapter, "owner/repo", 42, transition)
            self.assertEqual([], adapter.updates)

    def test_transition_never_implies_success_on_provider_failure_or_bad_response(self):
        issue = self.issue()
        adapter = FakeGoalTransitionAdapter(issue)
        adapter.failure = "provider failed"
        with self.assertRaisesRegex(zzzops.GoalTransitionProviderError, "provider failed"):
            zzzops.apply_goal_transition(adapter, "owner/repo", 42, self.transition(issue))
        self.assertEqual(issue["body"], adapter.issue["body"])
        self.assertEqual("2026-07-21T20:30:00Z", adapter.issue["updated_at"])
        self.assertEqual(1, len(adapter.comments))

        adapter.failure = None
        result = zzzops.apply_goal_transition(adapter, "owner/repo", 42, self.transition(issue))
        self.assertEqual(1, len(adapter.comments))
        self.assertEqual(2, result["revision"])

        adapter = FakeGoalTransitionAdapter(issue)
        adapter.response_mutation = lambda updated: updated.update({"body": "unexpected"})
        with self.assertRaisesRegex(zzzops.GoalTransitionProviderError, "unexpected"):
            zzzops.apply_goal_transition(adapter, "owner/repo", 42, self.transition(issue))
        self.assertEqual(1, len(adapter.updates))
        result = zzzops.apply_goal_transition(adapter, "owner/repo", 42, self.transition(issue))
        self.assertEqual(1, len(adapter.updates))
        self.assertEqual(1, len(adapter.comments))
        self.assertEqual(2, result["revision"])

    def test_transition_compacts_history_sections_and_recovers_comment_confirmation(self):
        issue = self.issue()
        issue["body"] = zzzops.render_managed_goal(
            self.goal(),
            "## Outcome / Why\n\nKeep this.\n\n```md\n## Evidence\nKeep fenced example.\n```\n\n"
            "## Evidence\n\nArchive this.\n\n## Scope\n\nKeep scope.\n",
            42,
        )
        transition = self.transition(issue)
        transition["goal"]["blockers"].append({
            "id": "B-old", "status": "resolved", "category": "human-action", "resolution": "Done",
        })
        adapter = FakeGoalTransitionAdapter(issue)
        adapter.comment_response_mutation = lambda comment: comment.update({"body": "unconfirmed"})
        self.assertIn("transition evidence", zzzops.validate_compact_goal_body(issue["body"], 42)[0])

        with self.assertRaisesRegex(zzzops.GoalTransitionProviderError, "exact transition history"):
            zzzops.apply_goal_transition(adapter, "owner/repo", 42, transition)
        self.assertEqual([], adapter.updates)
        self.assertEqual(1, len(adapter.comments))

        adapter.comment_response_mutation = None
        zzzops.apply_goal_transition(adapter, "owner/repo", 42, transition)
        self.assertEqual(1, len(adapter.comments))
        self.assertNotIn("Archive this.", adapter.issue["body"])
        self.assertIn("Keep fenced example.", adapter.issue["body"])
        self.assertIn("## Outcome / Why", adapter.issue["body"])
        self.assertIn("## Scope", adapter.issue["body"])
        compact = zzzops.parse_managed_goal(adapter.issue["body"], 42)
        self.assertEqual([], compact["evidence"])
        self.assertEqual(["B-001"], [blocker["id"] for blocker in compact["blockers"]])
        self.assertEqual([], zzzops.validate_compact_goal_body(adapter.issue["body"], 42))

        history = zzzops.parse_goal_history(adapter.comments[0]["body"])
        tampered = json.loads(json.dumps(history))
        tampered["prior_body"] += "tampered"
        tampered_body = (
            f"{zzzops._goals.GOAL_HISTORY_BLOCK_START}\n"
            f"{json.dumps(tampered, sort_keys=True, separators=(',', ':'))}\n"
            f"{zzzops._goals.GOAL_HISTORY_BLOCK_END}\n"
        )
        with self.assertRaisesRegex(ValueError, "Invalid goal history payload"):
            zzzops.parse_goal_history(tampered_body)

    def test_transition_file_is_bom_tolerant(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transition.json"
            transition = self.transition()
            path.write_bytes(b"\xef\xbb\xbf" + json.dumps(transition).encode("utf-8"))
            self.assertEqual(transition, zzzops.load_goal_transition(path))

    @mock.patch.object(zzzops.shutil, "which", return_value="gh")
    @mock.patch.object(zzzops.subprocess, "run")
    def test_github_transition_adapter_uses_one_json_stdin_patch(self, run, _which):
        issue = self.issue()
        run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps(issue), stderr="")
        adapter = zzzops.GitHubGoalTransitionAdapter(Path.cwd(), "owner/repo")
        payload = {"body": issue["body"], "labels": ["zzzops"], "state": "open"}
        self.assertEqual(issue, adapter.update_issue(42, payload))
        self.assertEqual(
            ["gh", "api", "--method", "PATCH", "repos/owner/repo/issues/42", "--input", "-"],
            run.call_args.args[0],
        )
        self.assertEqual(payload, json.loads(run.call_args.kwargs["input"]))

    @mock.patch.object(zzzops.shutil, "which", return_value="gh")
    @mock.patch.object(zzzops.subprocess, "run")
    def test_github_transition_adapter_reads_and_appends_selected_history(self, run, _which):
        comment = {"id": 9, "body": "history", "html_url": "https://example.test/comment/9"}
        run.side_effect = [
            SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
                "nameWithOwner": "owner/repo", "hasIssuesEnabled": True, "viewerPermission": "ADMIN",
            })),
            SimpleNamespace(returncode=0, stderr="", stdout=json.dumps([[comment]])),
            SimpleNamespace(returncode=0, stderr="", stdout=json.dumps(comment)),
        ]
        adapter = zzzops.GitHubGoalTransitionAdapter(Path.cwd(), "owner/repo")

        self.assertEqual([comment], adapter.get_issue_comments(42))
        self.assertEqual(comment, adapter.create_issue_comment(42, "history"))

        read_command = run.call_args_list[1].args[0]
        self.assertEqual(["gh", "api", "--paginate", "--slurp", "repos/owner/repo/issues/42/comments?per_page=100"], read_command)
        write_command = run.call_args_list[2].args[0]
        self.assertEqual(["gh", "api", "--method", "POST", "repos/owner/repo/issues/42/comments", "--input", "-"], write_command)
        self.assertEqual({"body": "history"}, json.loads(run.call_args_list[2].kwargs["input"]))


class FakeGoalSchemaAdapter:
    def __init__(self, issues):
        self.repository = "owner/repo"
        self.issues = {issue["number"]: json.loads(json.dumps(issue)) for issue in issues}
        self.comments = {number: [] for number in self.issues}
        self.updates = []

    def get_issue(self, number):
        return json.loads(json.dumps(self.issues[number]))

    def get_issue_comments(self, number):
        return json.loads(json.dumps(self.comments[number]))

    def create_issue_comment(self, number, body):
        comment = {
            "id": len(self.comments[number]) + 1,
            "body": body,
            "html_url": f"https://github.com/owner/repo/issues/{number}#history",
        }
        self.comments[number].append(json.loads(json.dumps(comment)))
        return comment

    def update_issue(self, number, payload):
        self.updates.append(number)
        issue = self.issues[number]
        issue.update({"body": payload["body"], "state": payload["state"]})
        issue["labels"] = [{"name": label} for label in payload["labels"]]
        return json.loads(json.dumps(issue))


class GoalSchemaMigrationTests(unittest.TestCase):
    def issue(self, number, *, status="ready", schema=None):
        goal = {
            "schema_version": 1, "status": status, "priority": "P2", "value": "medium",
            "difficulty": "S", "confidence": "high", "parent": None, "depends_on": [],
            "claim": None, "blockers": [], "evidence": ["Historical evidence."],
            "next_action": "Continue." if status not in {"done", "cancelled"} else "No further action.",
            "revision": 1, "implementation": {
                "branch": None, "base": None, "target": None, "pr": None,
                "review": {"status": "not_started", "checkpoint": None},
            }, "resources": [],
        }
        labels = [
            {"name": "zzzops"}, {"name": f"zzzops:status:{status}"},
            {"name": "zzzops:priority:P2"},
        ]
        if schema is not None:
            labels.append({"name": f"zzzops:schema:v{schema}"})
        return {
            "number": number, "title": f"Goal {number}",
            "body": zzzops.render_managed_goal(goal, "## Outcome\n\nKeep this.\n", number),
            "state": "closed" if status in {"done", "cancelled"} else "open",
            "updated_at": "2026-08-01T00:00:00Z",
            "html_url": f"https://github.com/owner/repo/issues/{number}", "labels": labels,
        }

    def index(self, issue):
        labels = issue["labels"]
        schema = next((int(label["name"].rsplit("v", 1)[1]) for label in labels if label["name"].startswith("zzzops:schema:v")), None)
        return {key: issue[key] for key in ("number", "title", "state", "labels", "html_url")} | {"schema_version": schema}

    def test_open_migration_is_bounded_open_only_and_idempotent(self):
        legacy_open = self.issue(1)
        current_open = self.issue(2, schema=1)
        legacy_closed = self.issue(3, status="done")
        second_legacy_open = self.issue(4)
        adapter = FakeGoalSchemaAdapter([legacy_open, current_open, legacy_closed, second_legacy_open])
        indexes = [self.index(issue) for issue in (legacy_open, current_open, legacy_closed, second_legacy_open)]

        first = zzzops.migrate_open_goal_schemas(adapter, "owner/repo", indexes, limit=1)
        refreshed = [self.index(adapter.issues[number]) for number in sorted(adapter.issues)]
        second = zzzops.migrate_open_goal_schemas(adapter, "owner/repo", refreshed, limit=1)
        final = zzzops.migrate_open_goal_schemas(
            adapter, "owner/repo", [self.index(adapter.issues[number]) for number in sorted(adapter.issues)], limit=1,
        )

        self.assertEqual([1], first["migrated"])
        self.assertEqual(1, first["remaining"])
        self.assertEqual([4], second["migrated"])
        self.assertTrue(second["complete"])
        self.assertEqual([], final["migrated"])
        self.assertEqual([1, 4], adapter.updates)
        self.assertEqual([], adapter.comments[3])
        self.assertNotIn(3, adapter.updates)

    def test_selected_current_label_repairs_noncompact_body(self):
        issue = self.issue(6, schema=1)
        adapter = FakeGoalSchemaAdapter([issue])

        result = zzzops.ensure_current_goal_schema(adapter, "owner/repo", 6)

        self.assertTrue(result["migrated"])
        self.assertEqual([], zzzops.parse_managed_goal(adapter.issues[6]["body"], 6)["evidence"])

    def test_selected_closed_legacy_goal_is_compacted_lazily(self):
        issue = self.issue(7, status="done")
        adapter = FakeGoalSchemaAdapter([issue])

        result = zzzops.ensure_current_goal_schema(adapter, "owner/repo", 7)

        self.assertTrue(result["migrated"])
        self.assertEqual("closed", adapter.issues[7]["state"])
        self.assertIn({"name": "zzzops:schema:v1"}, adapter.issues[7]["labels"])
        self.assertEqual([], zzzops.parse_managed_goal(adapter.issues[7]["body"], 7)["evidence"])
        self.assertEqual(1, len(adapter.comments[7]))


class PortfolioTests(unittest.TestCase):
    def goal(self, **overrides):
        goal = {
            "schema_version": 1, "status": "ready", "priority": "P2", "value": "medium",
            "difficulty": "S", "confidence": "high", "parent": None, "depends_on": [],
            "claim": {"owner": None}, "blockers": [], "evidence": [],
            "next_action": "Run the next observable probe.", "revision": 1,
            "implementation": {"branch": None, "base": None, "target": None, "pr": None,
                               "review": {"status": "not_started", "checkpoint": None}},
        }
        goal.update(overrides)
        return goal

    def issue(self, number, **goal_overrides):
        goal = self.goal(**goal_overrides)
        title = f"Goal {number}"
        body = zzzops.render_managed_goal(goal, "## Outcome / Why\n\nUseful work.\n", number)
        return {
            "number": number, "title": title, "body": body, "state": "closed" if goal["status"] == "done" else "open",
            "updated_at": f"2026-07-{number:02d}T00:00:00Z", "html_url": f"https://example.test/issues/{number}",
            "labels": [{"name": "zzzops"}, {"name": f"zzzops:status:{goal['status']}"}, {"name": f"zzzops:priority:{goal['priority']}"}],
        }

    def test_empty_snapshot_is_complete_and_deterministic(self):
        first = zzzops.build_portfolio_snapshot("github_issues", [], reads=1, raw_bytes=0)
        second = zzzops.build_portfolio_snapshot("github_issues", [], reads=1, raw_bytes=0)
        self.assertTrue(first["complete"])
        self.assertEqual(first["portfolio_digest"], second["portfolio_digest"])
        self.assertEqual(0, first["summary"]["total"])
        self.assertEqual([], first["findings"])

    def test_snapshot_projects_explicit_work_states(self):
        records = [
            zzzops.github_goal_record(self.issue(1, status="new")),
            zzzops.github_goal_record(self.issue(2, status="triaged")),
            zzzops.github_goal_record(self.issue(3, status="ready")),
            zzzops.github_goal_record(self.issue(4, status="in_progress", depends_on=[3])),
            zzzops.github_goal_record(self.issue(
                5, status="blocked",
                blockers=[{"id": "B-1", "status": "open", "category": "human-action"}],
            )),
            zzzops.github_goal_record(self.issue(6, status="blocked")),
            zzzops.github_goal_record(self.issue(7, status="done")),
            zzzops.github_goal_record(self.issue(
                8, status="ready",
                blockers=[{"id": "B-2", "status": "open", "category": "human-action"}],
            )),
        ]

        snapshot = zzzops.build_portfolio_snapshot("github_issues", records, reads=1, raw_bytes=100)
        by_key = {goal["key"]: goal for goal in snapshot["goals"]}

        self.assertEqual(2, snapshot["schema_version"])
        self.assertEqual(
            {
                1: "triage", 2: "prepare", 3: "write", 4: "wait_dependency",
                5: "wait_human", 6: "blocked", 7: "terminal", 8: "write",
            },
            {key: goal["work_state"] for key, goal in by_key.items()},
        )
        self.assertFalse(any("actionable" in goal for goal in snapshot["goals"]))
        self.assertEqual(4, snapshot["summary"]["available"])
        self.assertEqual(2, snapshot["summary"]["writable"])
        self.assertEqual(1, snapshot["summary"]["waiting"])

    def test_snapshot_derives_graph_work_state_and_compact_summary(self):
        records = [
            zzzops.github_goal_record(self.issue(1, status="done")),
            zzzops.github_goal_record(self.issue(2, depends_on=[1])),
            zzzops.github_goal_record(self.issue(3, parent=2, status="blocked", blockers=[{"id": "B-1", "status": "open", "category": "decision"}])),
        ]
        snapshot = zzzops.build_portfolio_snapshot(
            "github_issues", records, reads=1, raw_bytes=20000,
            as_of=zzzops.datetime(2026, 7, 17, tzinfo=zzzops.timezone.utc),
        )
        by_key = {goal["key"]: goal for goal in snapshot["goals"]}
        self.assertEqual([2], by_key[1]["blocks"])
        self.assertEqual([3], by_key[2]["children"])
        self.assertEqual({
            "total": 3, "available": 1, "writable": 1, "waiting": 0,
            "blocked": 1, "done": 1, "findings": 0, "reads": 1,
            "raw_bytes": 20000, "ignored": 0,
        }, snapshot["summary"])
        self.assertTrue(snapshot["valid"])
        summary = zzzops.render_portfolio_summary(snapshot)
        self.assertIn("Goals: 1 available (1 writable), 0 waiting on dependencies, 1 blocked, 1 closed (3 total).", summary)
        self.assertIn("#2 Ready: Goal 2", summary)
        self.assertNotIn("Goal 1", summary)
        self.assertNotIn("digest", summary)
        self.assertNotIn("reads", summary)
        self.assertNotIn("P1", summary)
        self.assertLess(len(summary.encode("utf-8")), snapshot["summary"]["raw_bytes"] // 10)

    def test_review_ready_dependency_is_writable_only_when_project_policy_allows_stacking(self):
        review_ready = {
            "branch": "goal/parent", "base": "dev", "target": "dev", "pr": "https://example.test/pull/1",
            "review": {"status": "pending", "checkpoint": "abc123"},
        }
        records = [
            zzzops.github_goal_record(self.issue(
                1, status="blocked", implementation=review_ready,
                blockers=[{"id": "B-1", "status": "open", "category": "human-action"}],
            )),
            zzzops.github_goal_record(self.issue(2, depends_on=[1], status="in_progress")),
        ]
        stacked = zzzops.build_portfolio_snapshot(
            "github_issues", records, reads=1, raw_bytes=100,
            git_policy={
                "dependency_base": "dependency_branch",
                "review_pending_dependency": "stack_from_reviewed_checkpoint",
            },
        )
        by_key = {goal["key"]: goal for goal in stacked["goals"]}
        self.assertEqual(1, stacked["summary"]["writable"])
        self.assertEqual("write", by_key[2]["work_state"])
        self.assertIn("#2 In progress: Goal 2", zzzops.render_portfolio_summary(stacked))

        completed_only = zzzops.build_portfolio_snapshot(
            "github_issues", records, reads=1, raw_bytes=100,
            git_policy={"dependency_base": "completed_goal"},
        )
        self.assertEqual(0, completed_only["summary"]["available"])
        self.assertEqual(1, completed_only["summary"]["waiting"])
        self.assertNotEqual(stacked["portfolio_digest"], completed_only["portfolio_digest"])
        self.assertEqual(
            "wait_dependency",
            next(goal for goal in completed_only["goals"] if goal["key"] == 2)["work_state"],
        )

        records[0]["blocker_categories"] = ["technical-unknown"]
        unsafe = zzzops.build_portfolio_snapshot(
            "github_issues", records, reads=1, raw_bytes=100,
            git_policy={
                "dependency_base": "dependency_branch",
                "review_pending_dependency": "stack_from_reviewed_checkpoint",
            },
        )
        self.assertEqual(0, unsafe["summary"]["available"])
        self.assertEqual(1, unsafe["summary"]["waiting"])

    def test_audit_reports_graph_state_claim_review_and_label_drift(self):
        stale = {"owner": "Codex", "expires_at": "2026-07-16T00:00:00Z"}
        pending = {"branch": "goal/x", "base": "dev", "target": "dev", "pr": "url", "review": {"status": "pending", "checkpoint": "abc"}}
        records = [
            zzzops.github_goal_record(self.issue(1, depends_on=[2], claim=stale, implementation=pending)),
            zzzops.github_goal_record(self.issue(2, depends_on=[1], status="done")),
        ]
        records[0]["depends_on"].append(2)
        records[0]["implementation"]["review"]["checkpoint"] = None
        records[1]["claim"] = {"owner": "Codex", "expires_at": "2026-07-16T00:00:00"}
        records[0]["labels"] = ["zzzops", "zzzops:status:new"]
        findings = zzzops.audit_portfolio(records, "github_issues", zzzops.datetime(2026, 7, 17, tzinfo=zzzops.timezone.utc))
        codes = {finding["code"] for finding in findings}
        self.assertTrue({"duplicate_dependency", "depends_on_cycle", "done_with_unfinished_dependency", "stale_claim", "invalid_claim_expiry", "pending_review_without_checkpoint", "label_drift"}.issubset(codes))

    @mock.patch.object(zzzops.shutil, "which", return_value="gh")
    @mock.patch.object(zzzops.subprocess, "run")
    @mock.patch.object(zzzops, "validate_project_artifacts", return_value=[])
    @mock.patch.object(zzzops, "validate_project_state", return_value=[])
    @mock.patch.object(zzzops, "read_project_state", return_value=(Path("POLICY.json"), "state", {"initialized": True, "backend": "github_issues", "repository": {"identity": "owner/repo"}}))
    def test_github_adapter_stages_minimal_discovery_and_targeted_bodies(self, _read_state, _validate, _artifacts, run, _which):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / ".zzzops").mkdir()
            (repo / ".zzzops" / "PROJECT.md").write_text("state", encoding="utf-8")
            def graphql_issue(issue):
                return {
                    "number": issue["number"], "title": issue["title"],
                    "state": issue["state"].upper(),
                    "labels": {"nodes": issue["labels"]},
                }

            def body_payload(*issues):
                return {"data": {"repository": {
                    f"goal_{issue['number']}": {
                        "number": issue["number"], "body": issue["body"], "updatedAt": issue["updated_at"],
                    }
                    for issue in issues
                }}}

            feedback = self.issue(2, status="new")
            feedback["labels"].append({"name": "zzzops-feedback"})
            payload = [
                {"data": {"repository": {
                    "nameWithOwner": "owner/repo", "url": "https://example.test/owner/repo",
                    "hasIssuesEnabled": True, "viewerPermission": "ADMIN",
                    "issues": {"nodes": [graphql_issue(self.issue(1)), graphql_issue(feedback)],
                               "pageInfo": {"hasNextPage": True, "endCursor": "page-1"}},
                }}},
                {"data": {"repository": {
                    "nameWithOwner": "owner/repo", "url": "https://example.test/owner/repo",
                    "hasIssuesEnabled": True, "viewerPermission": "ADMIN",
                    "issues": {"nodes": [graphql_issue(self.issue(3))],
                               "pageInfo": {"hasNextPage": False, "endCursor": "page-2"}},
                }}},
            ]
            issue_one, issue_three = self.issue(1), self.issue(3, status="done")
            payload[1]["data"]["repository"]["issues"]["nodes"][0] = graphql_issue(issue_three)
            run.side_effect = [
                SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""),
                SimpleNamespace(returncode=0, stdout=json.dumps(body_payload(issue_one)), stderr=""),
                SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""),
                SimpleNamespace(returncode=0, stdout=json.dumps(body_payload(issue_one, feedback)), stderr=""),
            ]
            snapshot = zzzops.portfolio_snapshot(repo)
            _, included = zzzops.github_repository_portfolio_snapshot(
                repo, {"backend": "github_issues", "repository": {"identity": "owner/repo"}},
                include_feedback=True,
            )
        self.assertEqual([1, 3], [goal["key"] for goal in snapshot["goals"]])
        self.assertEqual([1, 2, 3], [goal["key"] for goal in included["goals"]])
        self.assertEqual(3, snapshot["summary"]["reads"])
        self.assertEqual(2, snapshot["summary"]["processes"])
        self.assertEqual(1, snapshot["summary"]["ignored"])
        self.assertEqual(0, included["summary"]["ignored"])
        discovery = run.call_args_list[0].args[0]
        hydration = run.call_args_list[1].args[0]
        discovery_query = next(value[6:] for value in discovery if value.startswith("query="))
        hydration_query = next(value[6:] for value in hydration if value.startswith("query="))
        self.assertIn("--paginate", discovery)
        self.assertIn("--slurp", discovery)
        self.assertIn("number title state", discovery_query)
        issue_fields = discovery_query.split("nodes{", 1)[1].split("}", 1)[0]
        for excluded in ("body", "updatedAt", "url", "comments"):
            self.assertNotIn(excluded, issue_fields)
        self.assertIn("goal_1:issue(number:1){number body updatedAt}", hydration_query)
        self.assertNotIn("goal_3:", hydration_query)
        self.assertNotIn("goal_2:", hydration_query)
        archived = next(goal for goal in snapshot["goals"] if goal["key"] == 3)
        self.assertTrue(archived["archived"])
        self.assertEqual("done", archived["status"])
        self.assertEqual("https://example.test/owner/repo/issues/1", snapshot["goals"][0]["url"])
        self.assertLess(snapshot["summary"]["discovery_raw_bytes"], snapshot["summary"]["raw_bytes"])
        self.assertEqual(4, run.call_count)

    @mock.patch.object(zzzops.shutil, "which", side_effect=lambda command: command)
    @mock.patch.object(zzzops.subprocess, "run")
    @mock.patch.object(zzzops, "charter_missing_fields", return_value=[])
    @mock.patch.object(zzzops, "policy_blockers", return_value=[])
    @mock.patch.object(zzzops, "validate_project_artifacts", return_value=[])
    @mock.patch.object(zzzops, "validate_project_state", return_value=[])
    @mock.patch.object(zzzops, "read_project_state")
    @mock.patch.object(zzzops, "read_project", return_value=(Path("PROJECT.md"), "project"))
    @mock.patch.object(zzzops, "repository_size_profile", return_value={"mode": "worktrees", "max_workers": 3})
    @mock.patch.object(zzzops._package, "package_status", return_value={"available": True, "ok": True, "paths": [], "processes": 0, "detail": "ok"})
    def test_decision_checkpoint_embeds_portfolio_after_valid_plugin_package(
        self, _package, _size, _read, read_state, _validate, _artifacts, _blockers, _missing, run, _which,
    ):
        state = {
            "initialized": True, "backend": "github_issues", "repository": {"identity": "owner/repo"},
            "policy": {"sections": []},
        }
        read_state.return_value = (Path("POLICY.json"), "state", state)
        issue = self.issue(1)
        graphql_issue = {
            "number": issue["number"], "title": issue["title"],
            "state": issue["state"].upper(),
            "labels": {"nodes": issue["labels"]},
        }
        run.side_effect = [
            SimpleNamespace(returncode=0, stdout="https://github.com/owner/repo.git\n", stderr=""),
            SimpleNamespace(returncode=0, stdout=json.dumps([{"data": {"repository": {
                "nameWithOwner": "owner/repo", "url": "https://example.test/owner/repo",
                "hasIssuesEnabled": True, "viewerPermission": "ADMIN",
                "issues": {"nodes": [graphql_issue],
                           "pageInfo": {"hasNextPage": False, "endCursor": "page-1"}},
            }}}]), stderr=""),
            SimpleNamespace(returncode=0, stdout=json.dumps({"data": {"repository": {
                "goal_1": {"number": 1, "body": issue["body"], "updatedAt": issue["updated_at"]},
            }}}), stderr=""),
        ]

        result = zzzops.decision_checkpoint(Path("."))

        self.assertTrue(result["ready"])
        self.assertTrue(result["initialized"])
        self.assertTrue(result["capabilities"]["github_auth"]["ok"])
        self.assertTrue(result["capabilities"]["github_repository"]["usable"])
        self.assertTrue(result["portfolio"]["complete"])
        self.assertEqual([1], [goal["key"] for goal in result["portfolio"]["goals"]])
        self.assertEqual({"total": 3, "github": 2}, result["processes"])
        self.assertEqual(3, run.call_count)
        self.assertEqual("git", run.call_args_list[0].args[0][0])
        self.assertIn("graphql", run.call_args_list[1].args[0])

    @mock.patch.object(zzzops.shutil, "which", return_value="gh")
    @mock.patch.object(zzzops.subprocess, "run")
    def test_goal_history_is_an_explicit_separate_hydration(self, run, _which):
        run.return_value = SimpleNamespace(returncode=0, stderr="", stdout=json.dumps([
            {"data": {"repository": {"issue": {"comments": {
                "nodes": [{"body": "prior state", "createdAt": "2026-01-01T00:00:00Z", "url": "history", "author": {"login": "user"}}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }}}}},
        ]))

        comments = zzzops.github_issue_history(
            Path("."), {"backend": "github_issues", "repository": {"identity": "owner/repo"}}, 7,
        )

        self.assertEqual("prior state", comments[0]["body"])
        command = run.call_args.args[0]
        query = next(value[6:] for value in command if value.startswith("query="))
        self.assertIn("comments(first:100", query)
        self.assertNotIn(" title", query)
        self.assertNotIn(" labels", query)

    @mock.patch.object(zzzops.shutil, "which", return_value="gh")
    @mock.patch.object(zzzops, "repository_size_profile", return_value={"mode": "worktrees", "max_workers": 3})
    @mock.patch.object(zzzops, "github_repository_portfolio_snapshot")
    @mock.patch.object(zzzops, "command_probe", return_value={"available": True, "ok": True, "detail": "origin"})
    @mock.patch.object(zzzops, "policy_blockers", return_value=[])
    @mock.patch.object(zzzops, "validate_project_artifacts", return_value=[])
    @mock.patch.object(zzzops, "validate_project_state", return_value=[])
    @mock.patch.object(zzzops, "read_project_state")
    @mock.patch.object(zzzops, "read_project", return_value=(Path("PROJECT.md"), "project"))
    @mock.patch.object(zzzops._package, "package_status", return_value={
        "available": True, "ok": False, "paths": ["plugins/zzzops/zzzops/zzzops.py"], "processes": 0,
        "detail": "The installed ZzzOps plugin package is invalid; reinstall or update it through Codex.",
    })
    def test_decision_checkpoint_stops_before_portfolio_for_invalid_plugin_package(
        self, _machinery, _read, read_state, _validate, _artifacts, _blockers,
        _probe, portfolio, _size, _which,
    ):
        read_state.return_value = (Path("POLICY.json"), "state", {
            "initialized": True, "backend": "github_issues",
            "repository": {"identity": "owner/repo"}, "policy": {"sections": []},
        })

        result = zzzops.decision_checkpoint(Path("."))

        self.assertFalse(result["ready"])
        self.assertEqual(["plugins/zzzops/zzzops/zzzops.py"], result["capabilities"]["plugin_package"]["paths"])
        self.assertIn("reinstall or update", result["portfolio"]["error"])
        self.assertEqual({"total": 1, "github": 0}, result["processes"])
        portfolio.assert_not_called()

    @mock.patch.object(zzzops.shutil, "which", return_value="gh")
    @mock.patch.object(zzzops.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout="", stderr="API rate limit exceeded; partial page rejected"))
    @mock.patch.object(zzzops, "validate_project_artifacts", return_value=[])
    @mock.patch.object(zzzops, "validate_project_state", return_value=[])
    @mock.patch.object(zzzops, "read_project_state", return_value=(Path("POLICY.json"), "state", {"initialized": True, "backend": "github_issues", "repository": {"identity": "owner/repo"}}))
    def test_github_adapter_reports_partial_or_rate_limit_failure(self, _read_state, _validate, _artifacts, _run, _which):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / ".zzzops").mkdir()
            (repo / ".zzzops" / "PROJECT.md").write_text("state", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "rate limit.*partial page"):
                zzzops.portfolio_snapshot(repo)

    @mock.patch.object(zzzops.shutil, "which", return_value="gh")
    @mock.patch.object(zzzops.subprocess, "run")
    def test_github_adapter_rejects_repository_identity_drift(self, run, _which):
        run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps([{"data": {"repository": {
            "nameWithOwner": "owner/renamed", "url": "https://example.test/owner/renamed",
            "hasIssuesEnabled": True, "viewerPermission": "ADMIN",
            "issues": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}},
        }}}]), stderr="")

        with self.assertRaisesRegex(ValueError, "identity drift.*owner/repo.*owner/renamed"):
            zzzops.github_repository_portfolio_snapshot(
                Path("."), {"backend": "github_issues", "repository": {"identity": "owner/repo"}},
            )

    def test_large_graph_is_iterative_and_invalid_snapshots_still_expose_work_states(self):
        chain = [{"key": index, "parent": None, "depends_on": [] if index == 0 else [index - 1]} for index in range(1500)]
        self.assertEqual(set(), zzzops._cycle_nodes(chain, "depends_on"))
        chain[0]["depends_on"] = [1499]
        self.assertEqual(1500, len(zzzops._cycle_nodes(chain, "depends_on")))
        records = [
            zzzops.github_goal_record(self.issue(1, status="new")),
            zzzops.github_goal_record(self.issue(2, status="triaged")),
            zzzops.github_goal_record(self.issue(3, status="cancelled")),
            zzzops.github_goal_record(self.issue(4, depends_on=[3])),
        ]
        snapshot = zzzops.build_portfolio_snapshot("github_issues", records, reads=1, raw_bytes=100)
        self.assertEqual(2, snapshot["summary"]["available"])
        self.assertEqual(
            {1: "triage", 2: "prepare", 3: "terminal", 4: "wait_dependency"},
            {goal["key"]: goal["work_state"] for goal in snapshot["goals"]},
        )
        self.assertFalse(snapshot["valid"])
        self.assertIn("cancelled_dependency", {finding["code"] for finding in snapshot["findings"]})

    def test_projection_benchmark_fixture_is_repeatable(self):
        context = ("Observable outcome, acceptance evidence, scope, decisions, and resumable history. " * 18).strip()
        issues = []
        for number in range(1, 121):
            issue = self.issue(number)
            goal = zzzops.parse_managed_goal(issue["body"], number)
            issue["body"] = zzzops.render_managed_goal(goal, f"## Outcome / Why\n\n{context}\n", number)
            issues.append(issue)
        raw_bytes = sum(len((issue["title"] + issue["body"]).encode("utf-8")) for issue in issues)
        full_discovery = json.dumps([{
            "number": issue["number"], "title": issue["title"], "body": issue["body"],
            "state": issue["state"], "updatedAt": issue["updated_at"], "url": issue["html_url"],
            "labels": issue["labels"],
        } for issue in issues], separators=(",", ":")).encode("utf-8")
        minimal_discovery = json.dumps([{
            "number": issue["number"], "title": issue["title"], "state": issue["state"],
            "labels": issue["labels"],
        } for issue in issues], separators=(",", ":")).encode("utf-8")
        snapshot = zzzops.build_portfolio_snapshot(
            "github_issues", [zzzops.github_goal_record(issue) for issue in issues], reads=2, raw_bytes=raw_bytes,
        )
        json_bytes = len(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        summary_bytes = len(zzzops.render_portfolio_summary(snapshot).encode("utf-8"))
        self.assertEqual(2, snapshot["summary"]["reads"])
        self.assertLess(json_bytes, raw_bytes)
        self.assertLess(summary_bytes, json_bytes)
        self.assertLess(len(minimal_discovery), len(full_discovery) // 10)

    def test_minimal_index_identifies_schema_from_labels_and_reconstructs_url(self):
        issue = {
            "number": 7, "title": "Selected goal", "state": "OPEN",
            "labels": {"nodes": [{"name": "zzzops"}, {"name": "zzzops:schema:v2"}]},
        }

        indexed = zzzops._graphql_issue_index(issue, "https://github.com/owner/repo")

        self.assertEqual(2, indexed["schema_version"])
        self.assertEqual("https://github.com/owner/repo/issues/7", indexed["html_url"])
        duplicate = json.loads(json.dumps(issue))
        duplicate["labels"]["nodes"].append({"name": "zzzops:schema:v1"})
        with self.assertRaisesRegex(ValueError, "multiple goal schema labels"):
            zzzops._graphql_issue_index(duplicate, "https://github.com/owner/repo")

    def test_terminal_output_is_archived_after_full_validation(self):
        records = [zzzops.github_goal_record(self.issue(number, status="done")) for number in range(1, 121)]
        records.append(zzzops.github_goal_record(self.issue(121, status="ready")))
        full = zzzops.build_portfolio_snapshot("github_issues", records, reads=2, raw_bytes=200000)
        compact = zzzops.compact_portfolio_output(full)
        full_bytes = len(json.dumps(full, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        compact_bytes = len(json.dumps(compact, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))

        archived = next(goal for goal in compact["goals"] if goal["key"] == 1)
        active = next(goal for goal in compact["goals"] if goal["key"] == 121)
        self.assertEqual(120, compact["summary"]["archived"])
        self.assertEqual(
            {"archived", "key", "schema_version", "status", "title"},
            set(archived),
        )
        self.assertNotIn("archived", active)
        self.assertLess(compact_bytes, full_bytes // 2)
        self.assertIn("#1 Done: Goal 1", zzzops.render_portfolio_summary(compact, include_done=True))

    def test_compare_reports_added_removed_and_changed_goals(self):
        current = zzzops.build_portfolio_snapshot("github_issues", [
            {"key": "A", "title": "A", "status": "ready", "priority": "P1", "value": "high", "difficulty": "S", "confidence": "high", "parent": None, "depends_on": [], "claim": None, "needs_human": False, "blocker_categories": [], "next_action": "A", "revision": 2, "digest": "new", "updated_at": None, "implementation": None, "labels": []},
            {"key": "C", "title": "C", "status": "ready", "priority": "P2", "value": "medium", "difficulty": "S", "confidence": "high", "parent": None, "depends_on": [], "claim": None, "needs_human": False, "blocker_categories": [], "next_action": "C", "revision": 1, "digest": "c", "updated_at": None, "implementation": None, "labels": []},
        ], reads=1, raw_bytes=10)
        prior = {"schema_version": 2, "goals": [{"key": "A", "revision": 1, "digest": "old"}, {"key": "B", "revision": 1, "digest": "b"}]}
        self.assertEqual(["goal_changed", "goal_removed", "goal_added"], [finding["code"] for finding in zzzops.compare_portfolios(current, prior)])
        with self.assertRaisesRegex(ValueError, "unsupported schema"):
            zzzops.compare_portfolios(current, {"schema_version": 1, "goals": []})
        with self.assertRaisesRegex(ValueError, "malformed goal"):
            zzzops.compare_portfolios(current, {"schema_version": 2, "goals": [None]})

    def test_portfolio_allows_advisory_overlap_and_rejects_exclusive_overlap(self):
        common = {
            "status": "in_progress", "priority": "P1", "value": "high", "difficulty": "S",
            "confidence": "high", "parent": None, "depends_on": [], "needs_human": False,
            "blocker_categories": [], "next_action": "Work.", "revision": 1, "updated_at": None,
            "implementation": None, "labels": [], "resources": ["path:shared.txt", "branch:shared"],
        }
        records = [
            {**common, "key": 1, "title": "One", "claim": {"owner": "a"}, "digest": "a"},
            {**common, "key": 2, "title": "Two", "claim": {"owner": "b"}, "digest": "b"},
        ]
        snapshot = zzzops.build_portfolio_snapshot("github_issues", records, reads=1, raw_bytes=10)
        collisions = [finding["detail"] for finding in snapshot["findings"] if finding["code"] == "resource_collision"]
        self.assertEqual(["branch:shared: 1,2"], collisions)

        strict = zzzops.build_portfolio_snapshot(
            "github_issues", records, reads=1, raw_bytes=10,
            resource_policy={"mode": "strict", "exclusive_prefixes": [], "exclusive_resources": []},
        )
        strict_collisions = [finding["detail"] for finding in strict["findings"] if finding["code"] == "resource_collision"]
        self.assertEqual(["branch:shared: 1,2", "path:shared.txt: 1,2"], strict_collisions)


class FakeReservationAdapter:
    def __init__(self, revision=4, repository="owner/repo", barrier=None, barrier_prefix=None):
        self.revision = revision
        self.repository = repository
        self.barrier = barrier
        self.barrier_prefix = barrier_prefix
        self.labels = {}
        self.next_id = 1
        self.lock = threading.Lock()
        self.delete_error = None
        self.delete_error_node_ids = set()
        self.update_error = None
        self.create_error = None
        self.list_error = None

    @property
    def label(self):
        return self.labels.get(zzzops.reservation_label_name(12))

    @label.setter
    def label(self, value):
        name = zzzops.reservation_label_name(12)
        if value is None:
            self.labels.pop(name, None)
        else:
            self.labels[name] = value

    def goal_revision(self, _goal, require_writable=False):
        return self.revision

    def get_label(self, name):
        with self.lock:
            return dict(self.labels[name]) if name in self.labels else None

    def list_resource_labels(self):
        if self.list_error:
            raise zzzops.ReservationProviderError(self.list_error)
        with self.lock:
            return [
                dict(label) for name, label in self.labels.items()
                if name.startswith("zzzops:resource:")
            ]

    def create_label(self, name, description):
        if self.barrier and (self.barrier_prefix is None or name.startswith(self.barrier_prefix)):
            self.barrier.wait(timeout=2)
        if self.create_error:
            raise zzzops.ReservationProviderError(self.create_error)
        with self.lock:
            if name in self.labels:
                return None
            self.labels[name] = {"name": name, "description": description, "node_id": f"L{self.next_id}"}
            self.next_id += 1
            return dict(self.labels[name])

    def delete_label(self, node_id):
        with self.lock:
            if self.delete_error == "before" or node_id in self.delete_error_node_ids:
                raise zzzops.ReservationProviderError("delete failed")
            match = next((name for name, label in self.labels.items() if label["node_id"] == node_id), None)
            if match:
                del self.labels[match]
            if self.delete_error == "after":
                raise zzzops.ReservationProviderError("delete response lost")

    def update_label(self, node_id, description):
        with self.lock:
            match = next((label for label in self.labels.values() if label["node_id"] == node_id), None)
            if match:
                match["description"] = description
            if self.update_error:
                raise zzzops.ReservationProviderError("update response lost")


class ReservationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 19, 21, 0, tzinfo=timezone.utc)

    def acquire(self, adapter, owner="agent-a", run_id="run-a", revision=4, now=None):
        return zzzops.acquire_reservation(
            adapter, "owner/repo", 12, revision, owner, run_id, ttl_seconds=120, now=now or self.now,
        )

    def test_simultaneous_acquisition_has_one_winner(self):
        adapter = FakeReservationAdapter(barrier=threading.Barrier(2))
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.acquire, adapter, "agent-a", "run-a"),
                pool.submit(self.acquire, adapter, "agent-b", "run-b"),
            ]
        results = [future.result() for future in futures]
        self.assertEqual(1, sum(result["acquired"] for result in results))
        self.assertEqual({"acquired", "contended"}, {result["outcome"] for result in results})

    def test_renew_and_release_require_the_same_owner(self):
        adapter = FakeReservationAdapter()
        self.assertTrue(self.acquire(adapter)["acquired"])
        other = zzzops.renew_reservation(
            adapter, "owner/repo", 12, 4, "agent-b", "run-b", 120, self.now,
        )
        self.assertEqual("not_owned", other["outcome"])
        adapter.revision = 5  # Recording the durable claim advances canonical state.
        renewed = zzzops.renew_reservation(
            adapter, "owner/repo", 12, 5, "agent-a", "run-a", 180, self.now,
        )
        self.assertEqual("renewed", renewed["outcome"])
        metadata = zzzops.parse_reservation_description(adapter.label["description"])
        self.assertEqual(5, metadata["revision"])
        self.assertEqual(int(self.now.timestamp()), metadata["acquired_at"])
        released = zzzops.release_reservation(adapter, "owner/repo", 12, 5, "agent-a", "run-a")
        self.assertTrue(released["released"])
        self.assertIsNone(adapter.label)

    def test_expired_reservation_recovers_by_immutable_label_id(self):
        adapter = FakeReservationAdapter()
        self.acquire(adapter)
        skew_window = datetime.fromtimestamp(int(self.now.timestamp()) + 121, timezone.utc)
        self.assertEqual("contended", self.acquire(adapter, "agent-b", "run-b", now=skew_window)["outcome"])
        adapter.delete_error = "after"
        later = datetime.fromtimestamp(int(self.now.timestamp()) + 181, timezone.utc)
        result = self.acquire(adapter, "agent-b", "run-b", now=later)
        self.assertTrue(result["acquired"])
        self.assertEqual("L2", adapter.label["node_id"])
        metadata = zzzops.parse_reservation_description(adapter.label["description"])
        self.assertEqual("agent-b", metadata["owner"])

    def test_interrupted_cleanup_never_deletes_or_overwrites_a_live_owner(self):
        adapter = FakeReservationAdapter()
        self.acquire(adapter)
        adapter.delete_error = "before"
        with self.assertRaisesRegex(zzzops.ReservationProviderError, "expire safely"):
            zzzops.release_reservation(adapter, "owner/repo", 12, 4, "agent-a", "run-a")
        self.assertEqual("agent-a", zzzops.parse_reservation_description(adapter.label["description"])["owner"])
        later = datetime.fromtimestamp(int(self.now.timestamp()) + 181, timezone.utc)
        result = self.acquire(adapter, "agent-b", "run-b", now=later)
        self.assertFalse(result["acquired"])

    def test_stale_revision_and_repository_drift_fail_without_writing(self):
        adapter = FakeReservationAdapter(revision=5)
        with self.assertRaisesRegex(zzzops.ReservationProviderError, "changed from revision 4 to 5"):
            self.acquire(adapter)
        self.assertIsNone(adapter.label)
        adapter = FakeReservationAdapter(repository="other/repo")
        with self.assertRaisesRegex(zzzops.ReservationProviderError, "Repository identity changed"):
            self.acquire(adapter)
        self.assertIsNone(adapter.label)

    def test_ambiguous_renewal_is_confirmed_by_exact_readback(self):
        adapter = FakeReservationAdapter()
        self.acquire(adapter)
        adapter.update_error = True
        result = zzzops.renew_reservation(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", 180, self.now,
        )
        self.assertTrue(result["acquired"])
        adapter.label["description"] = "invalid"
        with self.assertRaisesRegex(zzzops.ReservationProviderError, "metadata is invalid"):
            self.acquire(adapter, "agent-b", "run-b")

    def test_permission_loss_and_rate_limit_never_grant_ownership(self):
        for message in ("permission denied", "rate limit exceeded"):
            with self.subTest(message=message):
                adapter = FakeReservationAdapter()
                adapter.create_error = message
                with self.assertRaisesRegex(zzzops.ReservationProviderError, message):
                    self.acquire(adapter)
                self.assertIsNone(adapter.label)

    def test_provider_metadata_is_bound_to_repository_and_goal(self):
        adapter = FakeReservationAdapter()
        adapter.label = {
            "name": zzzops.reservation_label_name(12), "node_id": "L1",
            "description": zzzops.reservation_description("other/repo", 12, 4, "agent-a", "run-a", int(self.now.timestamp()) + 120),
        }
        with self.assertRaisesRegex(zzzops.ReservationProviderError, "identity is invalid"):
            self.acquire(adapter)

    def test_github_adapter_reads_and_validates_exact_goal_revision(self):
        goal = {
            "schema_version": 1, "status": "ready", "priority": "P1", "value": "high",
            "difficulty": "S", "confidence": "high", "parent": None, "depends_on": [],
            "claim": {"owner": None}, "blockers": [], "evidence": [], "next_action": "Reserve it.",
            "revision": 7, "implementation": None,
        }
        body = f"Human goal\n\n{zzzops.GOAL_BLOCK_START}\n{json.dumps(goal)}\n{zzzops.GOAL_BLOCK_END}\n"
        adapter = object.__new__(zzzops.GitHubReservationAdapter)
        adapter.repository = "owner/repo"
        adapter.ensure_identity = mock.Mock()
        adapter._run = mock.Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps({"body": body}), stderr=""))
        self.assertEqual(7, adapter.goal_revision(12))
        adapter.ensure_identity.assert_called_once_with()
        goal["status"] = "done"
        body = f"Human goal\n\n{zzzops.GOAL_BLOCK_START}\n{json.dumps(goal)}\n{zzzops.GOAL_BLOCK_END}\n"
        adapter._run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps({"body": body}), stderr="")
        with self.assertRaisesRegex(zzzops.ReservationProviderError, "not available"):
            adapter.goal_revision(12, require_writable=True)

    def test_github_adapter_lists_only_complete_resource_labels_across_pages(self):
        adapter = object.__new__(zzzops.GitHubReservationAdapter)
        adapter.repository = "owner/repo"
        resource = {
            "name": zzzops.resource_label_name("branch:topic"), "node_id": "L1", "description": "metadata",
        }
        adapter._run = mock.Mock(return_value=SimpleNamespace(
            returncode=0, stdout=json.dumps([[resource, {"name": "ordinary", "node_id": "L2"}], []]), stderr="",
        ))
        self.assertEqual([resource], adapter.list_resource_labels())
        adapter._run.assert_called_once_with([
            "api", "--paginate", "--slurp", "repos/owner/repo/labels?per_page=100",
        ])

        adapter._run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps([[{"name": zzzops.resource_label_name("branch:topic"), "description": "metadata"}]]),
            stderr="",
        )
        with self.assertRaisesRegex(zzzops.ReservationProviderError, "incomplete resource"):
            adapter.list_resource_labels()

    def test_reservation_ttl_uses_reviewed_claim_policy(self):
        project = {"policy": {"sections": [{
            "id": "autonomy_approval_parallelism", "settings": {"claim_ttl_hours": 4},
        }]}}
        self.assertEqual(14400, zzzops.project_claim_ttl_seconds(project))

    def test_advisory_overlap_allows_both_goals_but_shared_branch_has_one_winner(self):
        adapter = FakeReservationAdapter(barrier=threading.Barrier(2), barrier_prefix="zzzops:resource:")
        shared = ["path:plugins/zzzops/zzzops/zzzops.py"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    zzzops.acquire_reservation_bundle, adapter, "owner/repo", goal, 4,
                    f"agent-{goal}", f"run-{goal}", shared, 120, self.now,
                )
                for goal in (12, 13)
            ]
        results = [future.result() for future in futures]
        self.assertTrue(all(result["acquired"] for result in results))
        self.assertTrue(all(result["reserved_resources"] == [] for result in results))

        adapter = FakeReservationAdapter(barrier=threading.Barrier(2), barrier_prefix="zzzops:resource:")
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    zzzops.acquire_reservation_bundle, adapter, "owner/repo", goal, 4,
                    f"agent-{goal}", f"run-{goal}", ["branch:shared"], 120, self.now,
                )
                for goal in (12, 13)
            ]
        results = [future.result() for future in futures]
        winner = next(result for result in results if result["acquired"])
        loser = next(result for result in results if not result["acquired"])
        self.assertEqual("resource_contended", loser["outcome"])
        self.assertEqual(
            {"goal": winner["goal"], "owner": f"agent-{winner['goal']}", "run_id": f"run-{winner['goal']}",
             "expires_at": int(self.now.timestamp()) + 120},
            loser["holder"],
        )
        self.assertIsNone(adapter.get_label(zzzops.reservation_label_name(loser["goal"])))
        self.assertIsNotNone(adapter.get_label(zzzops.reservation_label_name(winner["goal"])))

    def test_live_resource_contention_reports_only_validated_holder_fields(self):
        adapter = FakeReservationAdapter()
        resource = "branch:shared"
        self.assertTrue(
            zzzops.acquire_reservation_bundle(
                adapter, "owner/repo", 12, 4, "agent-a", "run-a", [resource], 120, self.now,
            )["acquired"]
        )
        blocked = zzzops.acquire_reservation_bundle(
            adapter, "owner/repo", 13, 4, "agent-b", "run-b", [resource], 120, self.now,
        )
        self.assertEqual("resource_contended", blocked["outcome"])
        self.assertEqual(
            {"goal": 12, "owner": "agent-a", "run_id": "run-a", "expires_at": int(self.now.timestamp()) + 120},
            blocked["holder"],
        )
        message = zzzops.reservation_cli_message(blocked, 13)
        self.assertIn("goal #12", message)
        self.assertIn("agent-a", message)
        self.assertIn("run-a", message)

        expired = zzzops.acquire_reservation_bundle(
            adapter, "owner/repo", 13, 4, "agent-b", "run-b", [resource], 120,
            datetime.fromtimestamp(int(self.now.timestamp()) + 121, timezone.utc),
        )
        self.assertEqual("resource_contended", expired["outcome"])
        self.assertNotIn("holder", expired)

        malformed = FakeReservationAdapter()
        malformed.create_label(zzzops.resource_label_name(resource), "not-reservation-metadata")
        with self.assertRaisesRegex(zzzops.ReservationProviderError, "metadata is invalid"):
            zzzops.acquire_reservation_bundle(
                malformed, "owner/repo", 13, 4, "agent-b", "run-b", [resource], 120, self.now,
            )

    def test_policy_can_make_paths_exclusive_and_strict_mode_reserves_everything(self):
        self.assertEqual(
            ["branch:topic", "external:device", "generated:dist"],
            zzzops.exclusive_resources([
                "path:src/app.py", "integration:dev", "generated:dist", "external:device", "branch:topic",
            ]),
        )
        configured = {
            "mode": "conflict_tolerant", "exclusive_prefixes": ["generated", "external"],
            "exclusive_resources": ["path:assets/logo.png"],
        }
        self.assertEqual(
            ["branch:topic", "path:assets/logo.png"],
            zzzops.exclusive_resources(
                ["integration:dev", "path:src/app.py", "path:assets/logo.png", "branch:topic"], configured,
            ),
        )
        self.assertEqual(
            ["branch:topic", "integration:dev", "path:src/app.py"],
            zzzops.exclusive_resources(
                ["integration:dev", "path:src/app.py", "branch:topic"],
                {"mode": "strict", "exclusive_prefixes": [], "exclusive_resources": []},
            ),
        )

    def test_distinct_resources_preserve_parallelism_and_bundle_lifecycle(self):
        adapter = FakeReservationAdapter()
        first = zzzops.acquire_reservation_bundle(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", ["generated:dist/a"], 120, self.now,
        )
        second = zzzops.acquire_reservation_bundle(
            adapter, "owner/repo", 13, 4, "agent-b", "run-b", ["generated:dist/b"], 120, self.now,
        )
        self.assertTrue(first["acquired"] and second["acquired"])
        adapter.revision = 5
        renewed = zzzops.renew_reservation_bundle(
            adapter, "owner/repo", 12, 5, "agent-a", "run-a", ["generated:dist/a"], 180, self.now,
        )
        self.assertTrue(renewed["acquired"])
        released = zzzops.release_reservation_bundle(
            adapter, "owner/repo", 12, 5, "agent-a", "run-a", ["generated:dist/a"],
        )
        self.assertTrue(released["released"])
        self.assertIsNone(adapter.get_label(zzzops.resource_label_name("generated:dist/a")))
        self.assertIsNotNone(adapter.get_label(zzzops.resource_label_name("generated:dist/b")))

    def test_release_discovers_owned_resources_when_arguments_are_omitted(self):
        adapter = FakeReservationAdapter()
        resources = ["branch:topic", "generated:dist/a"]
        acquired = zzzops.acquire_reservation_bundle(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", resources, 120, self.now,
        )
        self.assertTrue(acquired["acquired"])

        released = zzzops.release_reservation_bundle(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", [],
        )

        self.assertEqual({"released": True, "outcome": "released", "goal": 12}, released)
        self.assertIsNone(adapter.label)
        for resource in resources:
            self.assertIsNone(adapter.get_label(zzzops.resource_label_name(resource)))

    def test_release_preserves_foreign_and_replacement_resource_owners(self):
        adapter = FakeReservationAdapter()
        self.acquire(adapter)
        cases = {
            "branch:other-owner": ("owner/repo", 12, 4, "agent-b", "run-a"),
            "branch:other-run": ("owner/repo", 12, 4, "agent-a", "run-b"),
            "branch:other-goal": ("owner/repo", 13, 4, "agent-a", "run-a"),
            "branch:other-repo": ("other/repo", 12, 4, "agent-a", "run-a"),
            "branch:replacement": ("owner/repo", 12, 5, "agent-a", "run-a"),
        }
        for resource, (repository, goal, revision, owner, run_id) in cases.items():
            adapter.create_label(
                zzzops.resource_label_name(resource),
                zzzops.reservation_description(
                    repository, goal, revision, owner, run_id, int(self.now.timestamp()) + 120,
                ),
            )

        released = zzzops.release_reservation_bundle(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", [],
        )

        self.assertEqual("released", released["outcome"])
        self.assertIsNone(adapter.label)
        for resource in cases:
            self.assertIsNotNone(adapter.get_label(zzzops.resource_label_name(resource)))

    def test_release_fails_safely_on_malformed_or_unavailable_discovery(self):
        adapter = FakeReservationAdapter()
        self.acquire(adapter)
        adapter.create_label(zzzops.resource_label_name("branch:ambiguous"), "malformed")
        malformed = zzzops.release_reservation_bundle(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", [],
        )
        self.assertEqual("failed", malformed["outcome"])
        self.assertFalse(malformed["released"])
        self.assertIsNotNone(adapter.label)

        adapter.labels.pop(zzzops.resource_label_name("branch:ambiguous"))
        adapter.list_error = "list failed"
        unavailable = zzzops.release_reservation_bundle(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", [],
        )
        self.assertEqual("failed", unavailable["outcome"])
        self.assertIsNotNone(adapter.label)

    def test_release_reports_partial_cleanup_and_preserves_goal_for_retry(self):
        adapter = FakeReservationAdapter()
        resources = ["branch:first", "branch:second"]
        zzzops.acquire_reservation_bundle(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", resources, 120, self.now,
        )
        first = adapter.get_label(zzzops.resource_label_name("branch:first"))
        adapter.delete_error_node_ids.add(first["node_id"])

        released = zzzops.release_reservation_bundle(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", [],
        )

        self.assertEqual("partial", released["outcome"])
        self.assertEqual(1, released["released_resources"])
        self.assertIsNotNone(adapter.label)
        self.assertIsNotNone(adapter.get_label(zzzops.resource_label_name("branch:first")))
        self.assertIsNone(adapter.get_label(zzzops.resource_label_name("branch:second")))

        adapter.delete_error_node_ids.clear()
        retried = zzzops.release_reservation_bundle(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", [],
        )
        self.assertEqual("released", retried["outcome"])
        self.assertIsNone(adapter.label)
        self.assertIsNone(adapter.get_label(zzzops.resource_label_name("branch:first")))

    def test_release_recovers_resources_after_goal_label_was_already_removed(self):
        adapter = FakeReservationAdapter()
        resource = "branch:orphaned"
        zzzops.acquire_reservation_bundle(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", [resource], 120, self.now,
        )
        adapter.label = None

        released = zzzops.release_reservation_bundle(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", [],
        )

        self.assertEqual("released", released["outcome"])
        self.assertIsNone(adapter.get_label(zzzops.resource_label_name(resource)))

    def test_release_reports_stale_goal_revision_as_failed_without_writing(self):
        adapter = FakeReservationAdapter(revision=5)
        adapter.create_label(
            zzzops.resource_label_name("branch:owned"),
            zzzops.reservation_description(
                "owner/repo", 12, 4, "agent-a", "run-a", int(self.now.timestamp()) + 120,
            ),
        )
        released = zzzops.release_reservation_bundle(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", [],
        )
        self.assertEqual("failed", released["outcome"])
        self.assertIsNotNone(adapter.get_label(zzzops.resource_label_name("branch:owned")))

    def test_release_is_idempotent_when_goal_and_resources_are_already_absent(self):
        adapter = FakeReservationAdapter()
        released = zzzops.release_reservation_bundle(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", [],
        )
        self.assertEqual({"released": True, "outcome": "already_released", "goal": 12}, released)

    def test_release_cli_messages_distinguish_all_terminal_outcomes(self):
        self.assertIn("all owned resources", zzzops.reservation_cli_message({"outcome": "released"}, 12))
        self.assertIn("already released", zzzops.reservation_cli_message({"outcome": "already_released"}, 12))
        self.assertIn("Partially released", zzzops.reservation_cli_message({"outcome": "partial"}, 12))
        self.assertIn("no complete release", zzzops.reservation_cli_message({"outcome": "failed"}, 12))

    def test_release_cleans_advisory_labels_owned_under_an_earlier_strict_policy(self):
        adapter = FakeReservationAdapter()
        strict = {"mode": "strict", "exclusive_prefixes": [], "exclusive_resources": []}
        acquired = zzzops.acquire_reservation_bundle(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", ["path:shared.txt"], 120, self.now, strict,
        )
        self.assertTrue(acquired["acquired"])
        released = zzzops.release_reservation_bundle(
            adapter, "owner/repo", 12, 4, "agent-a", "run-a", ["path:shared.txt"],
        )
        self.assertTrue(released["released"])
        self.assertIsNone(adapter.get_label(zzzops.resource_label_name("path:shared.txt")))

    def test_resource_keys_are_normalized_and_bounded(self):
        self.assertEqual(["path:src/file.py"], zzzops.normalize_resources(["PATH:src\\File.py"]))
        with self.assertRaisesRegex(ValueError, "prefixes"):
            zzzops.normalize_resources(["unknown:value"])


class WorkflowContractTests(unittest.TestCase):
    def test_policy_review_reuses_capability_evidence_before_tool_selection(self):
        review = (
            PLUGIN_ROOT / "skills" / "review-zzzops-policy" / "SKILL.md"
        ).read_text(encoding="utf-8")
        for signal in (
            "Before optional tools, reuse capabilities",
            "never invoke an unavailable path",
            "an alternative or block once",
        ):
            self.assertIn(signal, review)

    def test_execute_progress_updates_require_new_information(self):
        execute = (
            PLUGIN_ROOT / "skills" / "execute-zzzops" / "references" / "EXECUTE.md"
        ).read_text(encoding="utf-8")
        for signal in (
            "new result, decision, risk, changed assumption, required action",
            "long-operation heartbeat",
            "never recap unchanged state",
        ):
            self.assertIn(signal, execute)

    def test_unknown_discovery_is_adaptive_durable_and_reviewable(self):
        root = PLUGIN_ROOT
        capture = (root / "skills" / "add-zzzops-goal" / "SKILL.md").read_text(encoding="utf-8")
        create = (root / "skills" / "execute-zzzops" / "references" / "CREATE.md").read_text(encoding="utf-8")
        execute = (root / "skills" / "execute-zzzops" / "references" / "EXECUTE.md").read_text(encoding="utf-8")
        self_review = (root / "skills" / "execute-zzzops" / "references" / "SELF_REVIEW.md").read_text(encoding="utf-8")
        docs = (root.parent.parent / "docs" / "EXECUTION.md").read_text(encoding="utf-8")

        for text in (capture, create):
            self.assertIn("bounded blind-spot pass", text)
            self.assertIn("known unknowns, tacit criteria", text)
            self.assertIn("disposable prototype", text)
        self.assertIn("Skip well-understood work", capture)
        self.assertIn("Foreground change-sensitive decisions", create)
        self.assertIn("append material assumptions, new constraints, and plan deviations", execute)
        self.assertIn("not tool logs", execute)
        self.assertIn("never interview live", execute)
        for phrase in (
            "consequential behavior, decisions/trade-offs, remaining unknowns",
            "comprehension checks only when they aid safe approval",
            "never replace tests, CI, self-review, or human approval",
        ):
            self.assertIn(phrase, self_review)
        for pattern in (
            "Blind-spot pass", "Brainstorms and prototypes", "Interviews", "References",
            "Implementation plans", "Implementation notes", "Pitches and explainers", "Quizzes",
        ):
            self.assertIn(f"| {pattern} |", docs)

    def test_execute_routes_explicit_work_states_without_blurring_write_authority(self):
        execute = (
            PLUGIN_ROOT / "skills" / "execute-zzzops" / "references" / "EXECUTE.md"
        ).read_text(encoding="utf-8")
        self.assertIn("work_state: triage|prepare", execute)
        for state in ("write", "wait_dependency", "wait_human", "blocked", "terminal"):
            self.assertIn(f"`{state}`", execute)
        self.assertIn("no goal has `work_state: triage|prepare|write`", execute)
        self.assertNotIn("portfolio's PROJECT-derived `actionable` field", execute)

    def test_github_schema_is_issue_native(self):
        self.assertIn("schema_version", zzzops.GOAL_FIELDS)
        for derived in ("id", "title", "blocks", "needs_human"):
            self.assertNotIn(derived, zzzops.GOAL_FIELDS)

    def test_policy_taxonomy_is_stable_across_templates(self):
        templates = PLUGIN_ROOT / "zzzops" / "templates" / "project-goals"
        plan = json.loads((templates / "INIT_PLAN.json").read_text(encoding="utf-8"))
        plan_ids = [section["id"] for section in plan["policy"]["sections"]]
        rendered = zzzops.render_project({
            "initialized": False, "approval": None, "charter": plan["charter"],
            "policy": plan["policy"],
        })
        project_ids = re.findall(r"\[policy:([^\]]+)\]", rendered)
        self.assertEqual(list(zzzops.POLICY_SECTION_IDS), plan_ids)
        self.assertEqual(list(zzzops.POLICY_SECTION_IDS), project_ids)
        self.assertTrue(all(section["required"] and not section["review"]["approved"] for section in plan["policy"]["sections"]))

    def test_required_pr_validation_includes_chained_targets(self):
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        trigger = workflow.split("permissions:", 1)[0]
        self.assertIn("pull_request:", trigger)
        self.assertNotIn("branches:", trigger)

    def test_branch_policy_defaults_are_structured(self):
        root = PLUGIN_ROOT / "zzzops"
        plan = json.loads((root / "templates" / "project-goals" / "INIT_PLAN.json").read_text(encoding="utf-8"))
        git_policy = next(section for section in plan["policy"]["sections"] if section["id"] == "git_review_release")["settings"]
        self.assertEqual("per_goal", git_policy["execution_branch"])
        self.assertEqual("nearest_authorized_trunk", git_policy["branch_base"])
        self.assertEqual("dependency_branch", git_policy["dependency_base"])
        self.assertEqual("wait_for_completed_dependencies", git_policy["review_pending_dependency"])
        self.assertEqual("allowed_before_completion", git_policy["read_only_dependency_investigation"])
        self.assertTrue(git_policy["parent_pseudo_trunk"])
        self.assertEqual("per_goal", git_policy["pull_request_unit"])
        self.assertEqual("explicit_reviewed_override", git_policy["shared_pull_request"])
        self.assertEqual("human_after_checks", git_policy["review_gate"])
        self.assertEqual(1, git_policy["review_state_reads_per_checkpoint"])

    def test_parallel_and_refill_defaults_are_structured(self):
        root = PLUGIN_ROOT / "zzzops"
        plan = json.loads((root / "templates" / "project-goals" / "INIT_PLAN.json").read_text(encoding="utf-8"))
        settings = next(section for section in plan["policy"]["sections"] if section["id"] == "autonomy_approval_parallelism")["settings"]
        self.assertEqual(3, settings["max_workers"])
        self.assertEqual(
            {
                "measurement": "existing_git_tracked_worktree_bytes", "threshold_bytes": 104857600,
                "below_threshold_mode": "worktrees", "at_or_above_threshold_mode": "read_only",
            },
            settings["parallelization"],
        )
        self.assertEqual(
            {
                "enabled": True,
                "allowed_categories": ["documentation", "tests", "code_quality_non_behavioral"],
                "max_per_run": 3,
            },
            settings["refill"],
        )
        self.assertEqual("dependencies_done", settings["dependency_implementation_gate"])
        self.assertTrue(settings["read_only_dependency_investigation"])
        self.assertEqual({"enabled": True}, settings["execution_reports"])
        self.assertEqual(
            {
                "capture_depth": "standard",
                "mode": "adaptive",
                "stakeholder_model": "requesting_user_only",
                "execution_questions": "durable_blockers_only",
            },
            settings["requirements_interview"],
        )
        settings["requirements_interview"]["capture_depth"] = "exhaustive"
        self.assertTrue(any(
            "requirements_interview.capture_depth is invalid" in error
            for error in zzzops.validate_policy(plan["policy"], True)
        ))
        settings["requirements_interview"]["capture_depth"] = "standard"
        self.assertEqual(
            {
                "mode": "conflict_tolerant",
                "exclusive_prefixes": ["generated", "external"],
                "exclusive_resources": [],
            },
            settings["resource_reservations"],
        )
        invalid_reservations = dict(settings["resource_reservations"])
        invalid_reservations["exclusive_prefixes"] = ["branch"]
        settings["resource_reservations"] = invalid_reservations
        self.assertTrue(any(
            "resource_reservations.exclusive_prefixes" in error
            for error in zzzops.validate_policy(plan["policy"], True)
        ))
        settings["resource_reservations"] = {
            "mode": "conflict_tolerant", "exclusive_prefixes": ["generated", "external"],
            "exclusive_resources": [],
        }
        self.assertEqual("remove_or_retain_clean_for_reuse", settings["worktree_lifecycle"]["after_task"])
        settings["execution_reports"]["enabled"] = "yes"
        self.assertTrue(any("execution_reports.enabled must be boolean" in error for error in zzzops.validate_policy(plan["policy"], True)))

    def test_verification_defaults_deduplicate_exact_required_ci(self):
        root = PLUGIN_ROOT / "zzzops"
        plan = json.loads((root / "templates" / "project-goals" / "INIT_PLAN.json").read_text(encoding="utf-8"))
        settings = next(section for section in plan["policy"]["sections"] if section["id"] == "verification_testing")["settings"]
        self.assertEqual(
            {
                "local_probe": "smallest_unique_falsifiable_signal",
                "skip_broad_local_when": "same_command_required_ci",
                "required_ci": "inspect_exact_pr_head",
                "failure": "inspect_logs_and_reprobe",
                "unavailable": "durable_blocker",
            },
            settings["ci_deduplication"],
        )

    def test_automated_design_policy_is_explicit_bounded_and_rendered(self):
        root = PLUGIN_ROOT
        plan = json.loads((root / "zzzops" / "templates" / "project-goals" / "INIT_PLAN.json").read_text(encoding="utf-8"))
        section = next(item for item in plan["policy"]["sections"] if item["id"] == "automated_design")
        self.assertEqual("enabled", section["decision"])
        self.assertEqual(
            ["project_objectives", "kpi_evidence", "constraints", "precedence"],
            section["settings"]["selection_basis"],
        )
        self.assertEqual(
            ["alternatives", "rationale", "assumptions", "falsifiable_validation_signal"],
            section["settings"]["decision_record"],
        )
        self.assertEqual("durable_design_blocker", section["settings"]["insufficient_evidence"])
        self.assertIn("destructive_migration", section["settings"]["hard_stops"])
        self.assertIn("higher_authority", section["settings"]["hard_stops"])
        self.assertEqual([], zzzops.validate_policy(plan["policy"], True))
        rendered = zzzops.render_project({
            "initialized": False, "approval": None, "charter": plan["charter"], "policy": plan["policy"],
        })
        self.assertIn("[policy:automated_design]", rendered)

        legacy = json.loads(json.dumps(plan["policy"]))
        legacy["evidence"] = plan["evidence"]
        legacy["sections"] = [item for item in legacy["sections"] if item["id"] != "automated_design"]
        self.assertEqual([], zzzops.validate_policy(legacy, False))
        self.assertTrue(any("missing sections: automated_design" in error for error in zzzops.validate_policy(legacy, True)))

        for decision in ("enabled", "disabled"):
            candidate = json.loads(json.dumps(plan["policy"]))
            next(item for item in candidate["sections"] if item["id"] == "automated_design")["decision"] = decision
            self.assertEqual([], zzzops.validate_policy(candidate, True), decision)

        mutations = {
            "decision": lambda item: item.update({"decision": "ask_agent"}),
            "selection_basis": lambda item: item["settings"]["selection_basis"].remove("kpi_evidence"),
            "privacy_security": lambda item: item["settings"].update({"privacy_security": "agent_discretion"}),
            "hard_stops": lambda item: item["settings"]["hard_stops"].remove("destructive_migration"),
        }
        for field, mutate in mutations.items():
            invalid = json.loads(json.dumps(plan["policy"]))
            mutate(next(item for item in invalid["sections"] if item["id"] == "automated_design"))
            self.assertTrue(any(field in error for error in zzzops.validate_policy(invalid, True)), field)

    def test_automated_design_execution_and_review_contracts_preserve_boundaries(self):
        root = PLUGIN_ROOT
        unblock = (root / "skills" / "execute-zzzops" / "references" / "UNBLOCK.md").read_text(encoding="utf-8")
        review = (root / "skills" / "review-zzzops-policy" / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "objectives, KPI evidence, constraints, and precedence",
            "alternatives, rationale, assumptions, and a falsifiable validation signal",
            "unambiguously reduces exposure, privilege, collection, or retention",
            "product scope, incompatible public contracts, destructive migrations, external spending, deployment",
            "durable design blocker",
        ):
            self.assertIn(phrase, unblock)
        self.assertIn("missing automated-design section", review)
        self.assertIn("without inferring approval", review)

    def test_continuation_policy_defaults_are_structured(self):
        root = PLUGIN_ROOT / "zzzops"
        plan = json.loads((root / "templates" / "project-goals" / "INIT_PLAN.json").read_text(encoding="utf-8"))
        settings = next(section for section in plan["policy"]["sections"] if section["id"] == "execution_continuation")["settings"]
        self.assertEqual("same_task_until_superseded", settings["execute_intent"])
        self.assertEqual("resume_once_and_reprioritize", settings["after_additive_capture"])
        self.assertTrue(settings["exhausted_handoff_retains_intent"])
        self.assertEqual("require_explicit_harness_signal", settings["cross_task"])
        self.assertEqual(
            {
                "enabled": False, "trigger": "disabled_for_unattended_execution", "max_blockers": 1,
                "notify_once": True, "poll_seconds": 30, "max_seconds": 180,
            },
            settings["human_unblock_watch"],
        )
    def test_completion_review_policy_defaults_are_structured(self):
        root = PLUGIN_ROOT / "zzzops"
        plan = json.loads((root / "templates" / "project-goals" / "INIT_PLAN.json").read_text(encoding="utf-8"))
        settings = next(section for section in plan["policy"]["sections"] if section["id"] == "code_quality")["settings"]
        self.assertEqual("required_before_review_or_done", settings["completion_self_review"])
        self.assertEqual("remove_only_if_evidenced_and_in_scope", settings["dead_code"])
        self.assertEqual("retain_without_proof", settings["dynamic_generated_vendor"])

    def test_skill_names_descriptions_and_modes_are_discoverable(self):
        root = PLUGIN_ROOT / "skills"
        contracts = {
            "add-zzzops-goal": ("capture", "add", "create", "record", "goal/todo", "writes canonical goal state by default"),
            "execute-zzzops": ("execute", "work all goals", "continue", "resume", "triage", "prioritize", "reprioritize", "unblock", '"dry run"', '"preview"', '"plan"', "default executes"),
            "migrate-to-zzzops": ("discover", "plan", "migrate", "import", "todos/backlogs", '"dry run"', '"preview"', '"apply"', "default builds review artifacts"),
            "review-zzzops-policy": ("review", "initialize", "summarize", "reconcile", "adjust", "policy", "preferred first workflow", "always re-summarizes"),
            "send-zzzops-feedback": ("preview", "send", "feedback", "execution reports", "exact-payload confirmation"),
            "suggest-zzzops-work": ("suggest", "discover", "audit", '"dry run"', '"preview"', '"plan"', '"apply"', '"refill"'),
        }
        self.assertEqual(set(contracts), {path.name for path in root.iterdir() if (path / "SKILL.md").is_file()})
        for name, phrases in contracts.items():
            skill = (root / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn(f"name: {name}", skill, name)
            description = re.sub(r"\s+", " ", skill.split("---", 2)[1].lower())
            for phrase in phrases:
                self.assertIn(phrase, description, f"{name}: {phrase}")

    def test_installed_skills_share_preflight_and_backend_rules(self):
        root = PLUGIN_ROOT
        names = (
            "add-zzzops-goal", "execute-zzzops", "migrate-to-zzzops",
            "review-zzzops-policy", "send-zzzops-feedback", "suggest-zzzops-work",
        )
        self.assertEqual(names, zzzops.MANAGED_SKILLS)
        for name in names:
            text = (root / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("INITIALIZATION.md", text, name)
            if name not in {"review-zzzops-policy", "send-zzzops-feedback"}:
                self.assertIn("BACKENDS.md", text, name)

        initialization = (root / "rules" / "INITIALIZATION.md").read_text(encoding="utf-8")
        for relative in (
            "README.md", "docs/INITIALIZATION.md", "docs/PERFORMANCE.md",
            "docs/ACCEPTANCE_TEST_PLAN.md", "plugins/zzzops/rules/INITIALIZATION.md",
        ):
            text = (PLUGIN_ROOT.parent.parent / relative).read_text(encoding="utf-8")
            self.assertIn("Python 3.10 or newer", text, relative)
        for phrase in (
            "Python 3.10 or newer", "older interpreter", "block once",
            "Under Codex", "authenticated context for the first attempt",
            "keep local-only commands in the normal sandbox", "Never reauthenticate or persistently relax the sandbox",
            "plugin package", "reinstalling or updating it through Codex",
        ):
            self.assertIn(phrase, initialization)
        review_skill = (root / "skills" / "review-zzzops-policy" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Ask separately", review_skill)
        for text in (review_skill, initialization):
            self.assertIn("The policy is already approved.", text)
            self.assertIn("Do not ask for approval", text)
            self.assertIn("do not", text.lower())
            self.assertIn("`init confirm`", text)
            self.assertIn("approval digest", text)
            self.assertIn("required section", text)
            self.assertIn("Changed/stale", text)
            self.assertIn("privacy-safe execution reports", text)
        manifest = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("zzzops", manifest["name"])
        self.assertEqual("2.0.0", manifest["version"])

    def test_skills_apply_shared_privacy_safe_feedback_handoff(self):
        root = PLUGIN_ROOT / "skills"
        for skill in root.iterdir():
            path = skill / "SKILL.md"
            if path.is_file():
                self.assertIn("FEEDBACK.md", path.read_text(encoding="utf-8"), skill.name)
        feedback_skill = (root / "send-zzzops-feedback" / "SKILL.md").read_text(encoding="utf-8")
        feedback_rule = (PLUGIN_ROOT / "rules" / "FEEDBACK.md").read_text(encoding="utf-8")
        self.assertIn("validated ZzzOps build provenance", feedback_skill)
        self.assertIn("legacy schema-v2 provenance is explicitly unknown", feedback_skill)
        self.assertIn("validated ZzzOps version/revision provenance", feedback_rule)

    def test_execute_feedback_queue_requires_one_session_approval(self):
        execute = (PLUGIN_ROOT / "skills" / "execute-zzzops" / "SKILL.md").read_text(encoding="utf-8")
        for phrase in ("zzzops-feedback", "current execution session", "Never ask per issue", "--include-feedback"):
            self.assertIn(phrase, execute)

    def test_execute_guidance_bounds_github_reads_without_weakening_safety_checks(self):
        root = PLUGIN_ROOT / "skills" / "execute-zzzops"
        execute = (root / "references" / "EXECUTE.md").read_text(encoding="utf-8")
        review = (root / "references" / "BRANCH_REVIEW.md").read_text(encoding="utf-8")
        for phrase in (
            "current queue read", "one consolidated PR-state read",
            "Exact-head, permission, merge, and transition readbacks remain mandatory",
        ):
            self.assertIn(phrase, execute)
        self.assertIn("bounded consolidated reads", review)
        self.assertIn("exact head", review)

    def test_execute_persists_questions_without_live_interaction(self):
        execute = (PLUGIN_ROOT / "skills" / "execute-zzzops" / "references" / "EXECUTE.md").read_text(encoding="utf-8")
        unblock = (PLUGIN_ROOT / "skills" / "execute-zzzops" / "references" / "UNBLOCK.md").read_text(encoding="utf-8")
        for phrase in (
            "Execution assumes the user is absent",
            "never asks an interactive question",
            "Persist each unanswered consequential question",
            "true queue exhaustion",
        ):
            self.assertIn(phrase, execute)
        for phrase in (
            "never asks for or waits on a live response",
            "Continue independent authorized work",
            "Do not poll, watch, notify repeatedly",
        ):
            self.assertIn(phrase, unblock)

    def test_execute_prioritization_contract_handles_adversarial_cases(self):
        execute = (
            PLUGIN_ROOT / "skills" / "execute-zzzops" / "references" / "EXECUTE.md"
        ).read_text(encoding="utf-8").lower()
        scenarios = {
            "explicit priority outranks an attractive lower-priority goal": "authority and explicit project priority first",
            "hard high-value work outranks easy low-value volume": "difficulty is cost, not value",
            "risk and unlocks outrank merely fast feedback": "risk-reducing or unlocking work over low-value easy or fast work",
            "unmeasured KPIs stay qualitative": "never invent a baseline, score, or precision",
            "an exact tie has a stable fallback": "resume policy, then the lowest goal key",
        }
        for scenario, expected in scenarios.items():
            with self.subTest(scenario=scenario):
                self.assertIn(expected, execute)

    def test_refill_and_feedback_provenance_labels_stay_distinct(self):
        skills = PLUGIN_ROOT / "skills"
        refill = (skills / "suggest-zzzops-work" / "SKILL.md").read_text(encoding="utf-8").lower()
        feedback = (skills / "send-zzzops-feedback" / "SKILL.md").read_text(encoding="utf-8")
        for phrase in ("during exhausted-queue refill", "zzzops-refill", "never copy source labels", "zzzops-feedback"):
            self.assertIn(phrase, refill)
        self.assertIn("`zzzops-feedback` label", feedback)
        self.assertEqual(
            ["zzzops", "zzzops-feedback", "zzzops:schema:v1", "zzzops:status:new", "zzzops:priority:P2"],
            zzzops.EXECUTION_REPORT_LABELS,
        )

if __name__ == "__main__":
    unittest.main()
