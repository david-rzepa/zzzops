import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("zzzops.py")
SPEC = importlib.util.spec_from_file_location("zzzops", MODULE_PATH)
zzzops = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(zzzops)


class InitializationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        template_dir = self.repo / ".agents" / "templates" / "project-goals"
        template_dir.mkdir(parents=True)
        (template_dir / "PREFERENCES.json").write_text("{}\n", encoding="utf-8")
        ledger_template = MODULE_PATH.parent / "templates" / "project-goals" / "USAGE_LEDGER.md"
        (template_dir / "USAGE_LEDGER.md").write_text(ledger_template.read_text(encoding="utf-8"), encoding="utf-8")
        source = MODULE_PATH.parent / "templates" / "project-goals" / "PROJECT.md"
        (self.repo / ".zzzops").mkdir()
        (self.repo / ".zzzops" / "PROJECT.md").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def plan(self):
        inspection = zzzops.inspect_initialization(self.repo)
        init_template = MODULE_PATH.parent / "templates" / "project-goals" / "INIT_PLAN.json"
        policy = json.loads(init_template.read_text(encoding="utf-8"))["policy"]
        policy["sections"][0]["settings"]["repository_identity"] = "example/repo"
        policy["sections"][0]["decision"] = "local_files"
        policy["sections"][0]["settings"]["authority"] = "local_files"
        return {
            "schema_version": 1,
            "base_digest": inspection["base_digest"],
            "confirmed": True,
            "backend": "local_files",
            "migration_pending": False,
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
            "github": {"usable": False, "evidence": "local selected"},
            "policy": policy,
        }

    @mock.patch.object(zzzops, "command_probe", return_value={"available": False, "ok": False, "detail": "test"})
    @mock.patch.object(zzzops, "github_repository_probe", return_value={"available": False, "usable": False})
    def test_inspect_is_read_only_and_reports_incomplete(self, _github, _probe):
        project = self.repo / ".zzzops" / "PROJECT.md"
        before = project.read_bytes()
        result = zzzops.inspect_initialization(self.repo)
        self.assertFalse(result["initialized"])
        self.assertTrue(result["valid_state"])
        self.assertIn("outcome", result["missing_charter_fields"])
        self.assertEqual(before, project.read_bytes())

    @mock.patch.object(zzzops, "command_probe", return_value={"available": False, "ok": False, "detail": "test"})
    @mock.patch.object(zzzops, "github_repository_probe", return_value={"available": False, "usable": False})
    def test_validate_apply_and_reinspect(self, _github, _probe):
        plan = self.plan()
        self.assertEqual([], zzzops.validate_plan(self.repo, plan))
        applied = zzzops.apply_plan(self.repo, plan)
        self.assertTrue(applied["changed"])
        self.assertEqual("python .agents/zzzops.py", applied["preferences_command"])
        result = zzzops.inspect_initialization(self.repo)
        self.assertFalse(result["initialized"])
        self.assertEqual("local_files", result["state"]["backend"])
        self.assertEqual([], result["missing_charter_fields"])
        self.assertEqual(len(zzzops.POLICY_SECTION_IDS), len(result["decision_blockers"]))
        project_text = (self.repo / ".zzzops" / "PROJECT.md").read_text(encoding="utf-8")
        self.assertIn("Agents complete durable", project_text)
        self.assertIn("E-002: agent synthesis — charter", project_text)
        reviewed = zzzops.confirm_project(
            self.repo, result["base_digest"], "test-user", [], True,
        )
        self.assertTrue(reviewed["initialized"])
        self.assertEqual([], reviewed["decision_blockers"])
        self.assertTrue(zzzops.inspect_initialization(self.repo)["initialized"])

    def test_review_is_exact_digest_explicit_and_incremental(self):
        applied = zzzops.apply_plan(self.repo, self.plan())
        with self.assertRaisesRegex(ValueError, "digest changed"):
            zzzops.confirm_project(self.repo, "sha256:stale", "test-user", [], True)
        first = zzzops.confirm_project(
            self.repo, applied["project_digest"], "test-user", ["backend"], False,
        )
        self.assertFalse(first["initialized"])
        self.assertNotIn("policy:backend", first["decision_blockers"])
        self.assertIn("policy:verification_testing", first["decision_blockers"])
        final = zzzops.confirm_project(self.repo, first["project_digest"], "test-user", [], True)
        self.assertTrue(final["initialized"])

    def test_policy_preserves_unknown_settings_and_agents_cannot_preapprove(self):
        plan = self.plan()
        section = plan["policy"]["sections"][4]
        section["settings"]["project_extension"] = {"custom": True}
        section["review"]["approved"] = True
        self.assertTrue(any("review must be pending" in error for error in zzzops.validate_plan(self.repo, plan)))
        section["review"]["approved"] = False
        applied = zzzops.apply_plan(self.repo, plan)
        zzzops.confirm_project(self.repo, applied["project_digest"], "test-user", [], True)
        state = zzzops.parse_project_state((self.repo / ".zzzops" / "PROJECT.md").read_text(encoding="utf-8"))
        self.assertEqual({"custom": True}, state["policy"]["sections"][4]["settings"]["project_extension"])

    def test_project_policy_requires_resolvable_source_citations(self):
        applied = zzzops.apply_plan(self.repo, self.plan())
        path = self.repo / ".zzzops" / "PROJECT.md"
        state = zzzops.parse_project_state(path.read_text(encoding="utf-8"))
        state["policy"]["evidence"] = []
        self.assertIn("policy.evidence must be a non-empty list", zzzops.validate_project_state(state))

    def test_not_applicable_policy_requires_explicit_review(self):
        plan = self.plan()
        section = plan["policy"]["sections"][7]
        section["applicable"] = False
        section["decision"] = "not applicable"
        section["rationale"] = "No user or developer documentation exists in this repository."
        applied = zzzops.apply_plan(self.repo, plan)
        self.assertIn("policy:documentation_style", applied["decision_blockers"])
        reviewed = zzzops.confirm_project(
            self.repo, applied["project_digest"], "test-user", ["documentation_style"], False,
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
                self.repo, applied["project_digest"], "test-user", ["git_review_release"], False,
            )
        self.assertIn("policy:git_review_release", zzzops.inspect_initialization(self.repo)["decision_blockers"])

    def test_cli_confirm_requires_and_uses_current_digest(self):
        applied = zzzops.apply_plan(self.repo, self.plan())
        result = subprocess.run(
            [
                zzzops.sys.executable, str(MODULE_PATH), "--repo", str(self.repo),
                "init", "confirm", "--project-digest", applied["project_digest"],
                "--reviewer", "test-user", "--all",
            ],
            text=True, encoding="utf-8", capture_output=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        self.assertTrue(json.loads(result.stdout)["initialized"])

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
        plan["backend"] = "github_issues"
        self.assertIn("github.usable must be true for github_issues", zzzops.validate_plan(self.repo, plan))

    def test_invalid_project_state_is_reported(self):
        project = self.repo / ".zzzops" / "PROJECT.md"
        project.write_text("<!-- zzzops-project-state\n{bad}\nzzzops-project-state -->\n", encoding="utf-8")
        with mock.patch.object(zzzops, "command_probe", return_value={}), mock.patch.object(zzzops, "github_repository_probe", return_value={}):
            result = zzzops.inspect_initialization(self.repo)
        self.assertFalse(result["valid_state"])
        self.assertIn("Invalid project state JSON", result["state_error"])

    def test_atomic_text_cleans_temporary_file_on_replace_failure(self):
        path = self.repo / ".zzzops" / "failure.md"
        with mock.patch.object(zzzops.os, "replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                zzzops.atomic_text(path, "new\n")
        self.assertFalse(path.exists())
        self.assertEqual([], [p for p in path.parent.iterdir() if p.name != "PROJECT.md"])

    def test_rejects_unconfirmed_proposal(self):
        plan = self.plan()
        plan["confirmations"] = []
        errors = zzzops.validate_plan(self.repo, plan)
        self.assertIn("confirmations must be a non-empty list", errors)
        self.assertIn("unconfirmed proposals: E-002", errors)

    def test_rejects_unsupported_project_state_schema(self):
        project = self.repo / ".zzzops" / "PROJECT.md"
        project.write_text(
            '<!-- zzzops-project-state\n{"schema_version": 99, "initialized": false, "backend": null, "repository": null, "revision": 0}\nzzzops-project-state -->\n',
            encoding="utf-8",
        )
        with mock.patch.object(zzzops, "command_probe", return_value={}), mock.patch.object(zzzops, "github_repository_probe", return_value={}):
            result = zzzops.inspect_initialization(self.repo)
        self.assertFalse(result["valid_state"])
        self.assertIn("schema_version must be 1", result["state_error"])

    def test_probe_output_redacts_url_userinfo(self):
        self.assertEqual("https://***@example.test/repo.git", zzzops.sanitize_output("https://secret@example.test/repo.git"))

    def test_shared_and_user_local_state_paths_are_separate(self):
        self.assertEqual(self.repo / ".zzzops" / "PROJECT.md", zzzops.project_path(self.repo))
        self.assertEqual(self.repo / ".zzzops" / "USAGE_LEDGER.md", zzzops.usage_ledger_path(self.repo))

    def test_usage_ledger_is_created_lazily_and_idempotently(self):
        path = zzzops.usage_ledger_path(self.repo)
        expected = (self.repo / ".agents" / "templates" / "project-goals" / "USAGE_LEDGER.md").read_text(encoding="utf-8")
        self.assertFalse(path.exists())
        self.assertTrue(zzzops.ensure_usage_ledger(self.repo)["created"])
        self.assertEqual(expected, path.read_text(encoding="utf-8"))
        self.assertFalse(zzzops.ensure_usage_ledger(self.repo)["created"])

    def test_usage_ledger_storage_failure_has_no_tracked_fallback(self):
        path = zzzops.usage_ledger_path(self.repo)
        with mock.patch.object(zzzops, "atomic_text", side_effect=OSError("denied")):
            result = zzzops.ensure_usage_ledger(self.repo)
        self.assertFalse(result["ok"])
        self.assertEqual("storage_unavailable", result["reason_code"])
        self.assertEqual("none; grant write access to the repository-local .zzzops directory", result["fallback"])
        self.assertFalse(path.exists())

    @mock.patch.object(zzzops, "command_probe", return_value={"available": False, "ok": False, "detail": "test"})
    @mock.patch.object(zzzops, "github_repository_probe", return_value={"available": False, "usable": False})
    def test_missing_project_reports_final_path_without_creating_state(self, _github, _probe):
        (self.repo / ".zzzops" / "PROJECT.md").unlink()
        result = zzzops.inspect_initialization(self.repo)
        self.assertEqual(str(self.repo / ".zzzops" / "PROJECT.md"), result["project_path"])
        self.assertFalse(result["initialized"])
        self.assertFalse(result["valid_state"])
        self.assertFalse((self.repo / ".zzzops" / "PROJECT.md").exists())
        self.assertFalse(zzzops.usage_ledger_path(self.repo).exists())

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
        self.assertFalse(zzzops.github_repository_probe(self.repo)["usable"])


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


class WorkflowContractTests(unittest.TestCase):
    def test_github_schema_is_issue_native_while_local_ids_remain(self):
        self.assertIn("schema_version", zzzops.GOAL_FIELDS)
        for derived in ("id", "title", "blocks", "needs_human"):
            self.assertNotIn(derived, zzzops.GOAL_FIELDS)
        root = Path(__file__).parent
        backend = (root.parent / ".zzzops" / "rules" / "BACKENDS.md").read_text(encoding="utf-8")
        for phrase in (
            "Repository plus issue number/URL is identity", "plain human title", "no rendered metadata/frontmatter",
            "compact hidden", "Same-repository parent/dependency relations are positive issue numbers",
            "Derive children/blocking edges", "old comments remain immutable provenance",
        ):
            self.assertIn(phrase, backend)
        local_template = (root / "templates" / "project-goals" / "GOAL.md").read_text(encoding="utf-8")
        self.assertIn("id: G-YYYYMMDD-NNN-slug", local_template)

    def test_policy_taxonomy_is_stable_across_templates(self):
        templates = Path(__file__).parent / "templates" / "project-goals"
        plan = json.loads((templates / "INIT_PLAN.json").read_text(encoding="utf-8"))
        plan_ids = [section["id"] for section in plan["policy"]["sections"]]
        project = (templates / "PROJECT.md").read_text(encoding="utf-8")
        project_ids = re.findall(r"\[policy:([^\]]+)\]", project)
        self.assertEqual(list(zzzops.POLICY_SECTION_IDS), plan_ids)
        self.assertEqual(list(zzzops.POLICY_SECTION_IDS), project_ids)
        self.assertTrue(all(section["required"] and not section["review"]["approved"] for section in plan["policy"]["sections"]))

    def test_branch_policy_and_workflow_cover_reviewed_topologies(self):
        root = Path(__file__).parent
        plan = json.loads((root / "templates" / "project-goals" / "INIT_PLAN.json").read_text(encoding="utf-8"))
        git_policy = next(section for section in plan["policy"]["sections"] if section["id"] == "git_review_release")["settings"]
        self.assertEqual("per_goal", git_policy["execution_branch"])
        self.assertEqual("nearest_authorized_trunk", git_policy["branch_base"])
        self.assertEqual("dependency_branch", git_policy["dependency_base"])
        self.assertTrue(git_policy["parent_pseudo_trunk"])
        self.assertEqual("per_goal", git_policy["pull_request_unit"])
        self.assertEqual("explicit_reviewed_override", git_policy["shared_pull_request"])
        self.assertEqual("human_after_checks", git_policy["review_gate"])
        workflow = (root / "skills" / "execute-zzzops" / "references" / "BRANCH_REVIEW.md").read_text(encoding="utf-8")
        for phrase in (
            "one stable `implementation` identity per goal", "multiple_dependency_base", "parent pseudo-trunk",
            "recursively", "dependency order", "human-action", "PR UI approval",
            "explicit conversational approval", "Changes requested", "Missing merge authority",
            "each source-changing goal owns one branch and one PR", "Related/small goals",
            "explicit user instruction", "record the override/rationale", "Parent and child goals keep distinct PRs",
            "commit/squash policy is separate", "Capture stays Git-free", "without PR capability",
        ):
            self.assertIn(phrase, workflow)

    def test_continuation_policy_and_prompt_cover_turn_scenarios(self):
        root = Path(__file__).parent
        plan = json.loads((root / "templates" / "project-goals" / "INIT_PLAN.json").read_text(encoding="utf-8"))
        settings = next(section for section in plan["policy"]["sections"] if section["id"] == "execution_continuation")["settings"]
        self.assertEqual("same_task_until_superseded", settings["execute_intent"])
        self.assertEqual("resume_once_and_reprioritize", settings["after_additive_capture"])
        self.assertTrue(settings["exhausted_handoff_retains_intent"])
        self.assertEqual("require_explicit_harness_signal", settings["cross_task"])
        rule = (root.parent / ".zzzops" / "rules" / "CONTINUATION.md").read_text(encoding="utf-8")
        for phrase in (
            "not elapsed-time inference", "queue exhaustion/yield", "explicit stop/pause/replacement/capture-only",
            "required-authority or blocking boundary", "never nest/duplicate execute", "standalone adjacent capture",
            "re-enter `$execute-zzzops` once", "no priority shortcut", "steer and ordinary follow-up",
            "Compacted context", "Separate tasks/threads", "Capture itself remains Git-free",
        ):
            self.assertIn(phrase, rule)

    def test_completion_review_policy_covers_scoped_cleanup_scenarios(self):
        root = Path(__file__).parent
        plan = json.loads((root / "templates" / "project-goals" / "INIT_PLAN.json").read_text(encoding="utf-8"))
        settings = next(section for section in plan["policy"]["sections"] if section["id"] == "code_quality")["settings"]
        self.assertEqual("required_before_review_or_done", settings["completion_self_review"])
        self.assertEqual("remove_only_if_evidenced_and_in_scope", settings["dead_code"])
        self.assertEqual("retain_without_proof", settings["dynamic_generated_vendor"])
        review = (root / "skills" / "execute-zzzops" / "references" / "SELF_REVIEW.md").read_text(encoding="utf-8")
        for phrase in (
            "actual implementation", "goal criteria, diff, tests", "compatibility paths", "demonstrably unused/superseded",
            "Dynamic/reflection use", "generated/vendor", "Out-of-scope cleanup", "test-discovered product bugs",
            "one observable chunk", "relevant wider regression", "idempotent", "clean result", "Never invent findings",
        ):
            self.assertIn(phrase, review)

    def test_skill_names_descriptions_and_modes_are_discoverable(self):
        root = Path(__file__).parent / "skills"
        contracts = {
            "add-zzzops-goal": ("capture", "add", "create", "record", "goal/todo", "writes canonical goal state by default"),
            "execute-zzzops": ("execute", "work all goals", "continue", "resume", "triage", "prioritize", "reprioritize", "unblock", '"dry run"', '"preview"', '"plan"', "default executes"),
            "install-zzzops": ("install", "set up", "copy", "refresh", "update", '"preview"', '"dry run"', '"apply"', '"setup"'),
            "migrate-zzzops-todos": ("discover", "plan", "migrate", "import", "todos/backlogs", '"dry run"', '"preview"', '"apply"', "default builds review artifacts"),
            "suggest-zzzops-work": ("suggest", "discover", "audit", '"dry run"', '"preview"', '"plan"', '"apply"', '"refill"'),
            "analyze-zzzops-usage": ("tokens", "usage", "cost", "management overhead", "value-per-token"),
        }
        self.assertEqual(set(contracts), {path.name for path in root.iterdir() if (path / "SKILL.md").is_file()})
        for name, phrases in contracts.items():
            skill = (root / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn(f"name: {name}", skill, name)
            description = skill.split("---", 2)[1].lower()
            for phrase in phrases:
                self.assertIn(phrase, description, f"{name}: {phrase}")

    def test_first_release_has_no_obsolete_add_skill(self):
        root = Path(__file__).parent / "skills"
        obsolete = "-".join(("add", "zzzops", "todo"))
        self.assertFalse((root / obsolete / "SKILL.md").exists())

    def test_non_install_skills_share_preflight_and_backend_rules(self):
        root = Path(__file__).parent
        names = (
            "add-zzzops-goal", "execute-zzzops", "migrate-zzzops-todos",
            "suggest-zzzops-work", "analyze-zzzops-usage",
        )
        for name in names:
            text = (root / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("INITIALIZATION.md", text, name)
            self.assertIn("BACKENDS.md", text, name)
            self.assertIn("HEALTH.md", text, name)
        install = (root / "skills" / "install-zzzops" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("INITIALIZATION.md", install)
        self.assertNotIn("HEALTH.md", install)

    def test_non_install_health_hooks_are_project_policy_driven(self):
        root = Path(__file__).parent / "skills"
        for name in ("add-zzzops-goal", "analyze-zzzops-usage", "execute-zzzops", "migrate-zzzops-todos", "suggest-zzzops-work"):
            text = (root / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("HEALTH.md", text, name)
            self.assertIn("reviewed PROJECT policy", text, name)

    def test_capture_and_execution_git_boundaries_are_explicit(self):
        root = Path(__file__).parent
        add = (root / "skills" / "add-zzzops-goal" / "SKILL.md").read_text(encoding="utf-8")
        execute = (root / "skills" / "execute-zzzops" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("never creates a branch, commit, push, or PR", add)
        self.assertIn("read PROJECT Git/review/continuation policy", execute)
        self.assertIn("never absorb unrelated changes", execute)
        self.assertIn("empty GitHub-state commit", execute)

    def test_static_prompts_do_not_hardcode_customizable_policy_defaults(self):
        root = Path(__file__).parent.parent
        prompt_roots = (root / ".zzzops" / "rules", root / ".agents" / "skills")
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for prompt_root in prompt_roots
            for path in prompt_root.rglob("*.md")
        )
        for phrase in ("default four hours", "at most two verified", "prefer depth <=3", "execute defaults to the current branch"):
            self.assertNotIn(phrase, text.casefold())


if __name__ == "__main__":
    unittest.main()
