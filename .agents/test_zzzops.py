import importlib.util
import json
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
        source = MODULE_PATH.parent / "templates" / "project-goals" / "PROJECT.md"
        (self.repo / "goals").mkdir()
        (self.repo / "goals" / "PROJECT.md").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def plan(self):
        inspection = zzzops.inspect_initialization(self.repo)
        return {
            "schema_version": 1,
            "base_digest": inspection["base_digest"],
            "confirmed": True,
            "backend": "local_files",
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
            "evidence": [{"kind": "observed", "source": "README.md", "finding": "durable goals"}],
            "confirmations": [{"field": "charter", "confirmed_by": "user", "date": "2026-07-16"}],
            "github": {"usable": False, "evidence": "local selected"},
        }

    @mock.patch.object(zzzops, "command_probe", return_value={"available": False, "ok": False, "detail": "test"})
    def test_inspect_is_read_only_and_reports_incomplete(self, _probe):
        project = self.repo / "goals" / "PROJECT.md"
        before = project.read_bytes()
        result = zzzops.inspect_initialization(self.repo)
        self.assertFalse(result["initialized"])
        self.assertTrue(result["valid_state"])
        self.assertIn("outcome", result["missing_charter_fields"])
        self.assertEqual(before, project.read_bytes())

    @mock.patch.object(zzzops, "command_probe", return_value={"available": False, "ok": False, "detail": "test"})
    def test_validate_apply_and_reinspect(self, _probe):
        plan = self.plan()
        self.assertEqual([], zzzops.validate_plan(self.repo, plan))
        applied = zzzops.apply_plan(self.repo, plan)
        self.assertTrue(applied["changed"])
        result = zzzops.inspect_initialization(self.repo)
        self.assertTrue(result["initialized"])
        self.assertEqual("local_files", result["state"]["backend"])
        self.assertEqual([], result["missing_charter_fields"])
        self.assertIn("Agents complete durable", (self.repo / "goals" / "PROJECT.md").read_text(encoding="utf-8"))

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
        project = self.repo / "goals" / "PROJECT.md"
        project.write_text("<!-- zzzops-project-state\n{bad}\nzzzops-project-state -->\n", encoding="utf-8")
        with mock.patch.object(zzzops, "command_probe", return_value={}):
            result = zzzops.inspect_initialization(self.repo)
        self.assertFalse(result["valid_state"])
        self.assertIn("Invalid project state JSON", result["state_error"])

    def test_atomic_text_cleans_temporary_file_on_replace_failure(self):
        path = self.repo / "goals" / "failure.md"
        with mock.patch.object(zzzops.os, "replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                zzzops.atomic_text(path, "new\n")
        self.assertFalse(path.exists())
        self.assertEqual([], [p for p in path.parent.iterdir() if p.name != "PROJECT.md"])


if __name__ == "__main__":
    unittest.main()
