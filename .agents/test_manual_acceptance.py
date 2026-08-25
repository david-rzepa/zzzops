import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / ".agents" / "manual_acceptance.py"


class ManualAcceptanceTests(unittest.TestCase):
    def test_check_and_audit_only_affect_mapped_item(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "docs").mkdir()
            (repo / "a.txt").write_text("one")
            (repo / "b.txt").write_text("two")
            plan = {"version": 1, "items": [{"id":"A-1","status":"unchecked","paths":["a.txt"],"fingerprint":None,"notes":""},{"id":"A-2","status":"unchecked","paths":["b.txt"],"fingerprint":None,"notes":""}]}
            (repo / "docs" / "ACCEPTANCE_TEST_PLAN.md").write_text("# Plan\n\n<!-- zzzops-acceptance-plan\n" + json.dumps(plan) + "\nzzzops-acceptance-plan -->\n")
            def run(*args):
                return subprocess.run([sys.executable, str(SCRIPT), *args, "--repo", str(repo)], text=True, capture_output=True, check=True)
            self.assertEqual("A-1", json.loads(run("next").stdout)["id"])
            run("check", "A-1")
            (repo / "b.txt").write_text("changed")
            self.assertEqual([], json.loads(run("audit").stdout)["stale"])
            (repo / "a.txt").write_text("changed")
            self.assertEqual(["A-1"], json.loads(run("audit").stdout)["stale"])

    def test_coverage_reports_missing_required_surfaces_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "docs").mkdir()
            plan = {"version": 1, "items": [{"id":"A-1","status":"unchecked","paths":["plugins/zzzops/plugin.json"],"fingerprint":None,"notes":""}]}
            path = repo / "docs" / "ACCEPTANCE_TEST_PLAN.md"
            path.write_text("<!-- zzzops-acceptance-plan\n" + json.dumps(plan) + "\nzzzops-acceptance-plan -->\n")
            result = subprocess.run([sys.executable, str(SCRIPT), "coverage", "--repo", str(repo)], text=True, capture_output=True)
            self.assertEqual(1, result.returncode)
            self.assertIn(".agents/plugins/marketplace.json", json.loads(result.stdout)["unmapped_required_surfaces"])
            self.assertIn("plugins/zzzops/skills/add-zzzops-goal", json.loads(result.stdout)["unmapped_required_surfaces"])
            self.assertIn("plugins/zzzops/skills/bootstrap-zzzops-repository", json.loads(result.stdout)["unmapped_required_surfaces"])
            self.assertIn("plugins/zzzops/skills/review-agentic-engineering", json.loads(result.stdout)["unmapped_required_surfaces"])
            self.assertIn("plugins/zzzops/skills/send-zzzops-feedback", json.loads(result.stdout)["unmapped_required_surfaces"])
            self.assertIn("plugins/zzzops/skills/validate-zzzops-installation", json.loads(result.stdout)["unmapped_required_surfaces"])
            self.assertEqual(path.read_text(encoding="utf-8"), "<!-- zzzops-acceptance-plan\n" + json.dumps(plan) + "\nzzzops-acceptance-plan -->\n")

    def test_coverage_accepts_plugin_manifests_and_packaged_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "docs").mkdir()
            surfaces = [
                "plugins/zzzops/plugin.json", ".agents/plugins/marketplace.json",
                "plugins/zzzops/skills/add-zzzops-goal", "plugins/zzzops/skills/bootstrap-zzzops-repository",
                "plugins/zzzops/skills/migrate-to-zzzops",
                "plugins/zzzops/skills/review-zzzops-policy", "plugins/zzzops/skills/suggest-zzzops-work",
                "plugins/zzzops/skills/execute-zzzops", "plugins/zzzops/skills/review-agentic-engineering",
                "plugins/zzzops/skills/send-zzzops-feedback",
                "plugins/zzzops/skills/validate-zzzops-installation",
            ]
            plan = {
                "version": 1,
                "items": [{"id": "A-1", "status": "unchecked", "paths": surfaces, "fingerprint": None, "notes": ""}],
            }
            path = repo / "docs" / "ACCEPTANCE_TEST_PLAN.md"
            path.write_text(
                "<!-- zzzops-acceptance-plan\n" + json.dumps(plan) + "\nzzzops-acceptance-plan -->\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "coverage", "--repo", str(repo)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual([], json.loads(result.stdout)["unmapped_required_surfaces"])

    def test_coverage_accepts_automated_contracts_only_with_present_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "docs").mkdir()
            evidence = repo / "tests" / "test_marketplace.py"
            evidence.parent.mkdir()
            evidence.write_text("# automated contract\n", encoding="utf-8")
            plan = {
                "version": 2,
                "items": [{
                    "id": "UX-1", "status": "unchecked",
                    "paths": ["plugins/zzzops/plugin.json"],
                    "surfaces": ["plugins/zzzops/plugin.json"],
                    "fingerprint": None, "notes": "",
                }],
                "automated_surfaces": [{
                    "surface": ".agents/plugins/marketplace.json",
                    "evidence": ["tests/test_marketplace.py"],
                }],
            }
            plan_path = repo / "docs" / "ACCEPTANCE_TEST_PLAN.md"
            plan_path.write_text(
                "<!-- zzzops-acceptance-plan\n" + json.dumps(plan) + "\nzzzops-acceptance-plan -->\n",
                encoding="utf-8",
            )

            def coverage():
                return subprocess.run(
                    [sys.executable, str(SCRIPT), "coverage", "--repo", str(repo)],
                    text=True, capture_output=True,
                )

            present = coverage()
            present_data = json.loads(present.stdout)
            self.assertNotIn(".agents/plugins/marketplace.json", present_data["unmapped_required_surfaces"])
            self.assertEqual([], present_data["automated_surfaces_without_evidence"])

            evidence.unlink()
            missing = coverage()
            missing_data = json.loads(missing.stdout)
            self.assertEqual(1, missing.returncode)
            self.assertIn(".agents/plugins/marketplace.json", missing_data["unmapped_required_surfaces"])
            self.assertEqual(
                [{"surface": ".agents/plugins/marketplace.json", "missing": ["tests/test_marketplace.py"]}],
                missing_data["automated_surfaces_without_evidence"],
            )

            plan["automated_surfaces"][0]["evidence"] = []
            plan_path.write_text(
                "<!-- zzzops-acceptance-plan\n" + json.dumps(plan) + "\nzzzops-acceptance-plan -->\n",
                encoding="utf-8",
            )
            undeclared = coverage()
            self.assertEqual(1, undeclared.returncode)
            self.assertEqual(
                [{"surface": ".agents/plugins/marketplace.json", "missing": []}],
                json.loads(undeclared.stdout)["automated_surfaces_without_evidence"],
            )


if __name__ == "__main__":
    unittest.main()
