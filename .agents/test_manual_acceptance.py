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
            plan = {"version": 1, "items": [{"id":"A-1","status":"unchecked","paths":["zzzops.py"],"fingerprint":None,"notes":""}]}
            path = repo / "docs" / "ACCEPTANCE_TEST_PLAN.md"
            path.write_text("<!-- zzzops-acceptance-plan\n" + json.dumps(plan) + "\nzzzops-acceptance-plan -->\n")
            result = subprocess.run([sys.executable, str(SCRIPT), "coverage", "--repo", str(repo)], text=True, capture_output=True)
            self.assertEqual(1, result.returncode)
            self.assertIn(".agents/zzzops.py", json.loads(result.stdout)["unmapped_required_surfaces"])
            self.assertEqual(path.read_text(encoding="utf-8"), "<!-- zzzops-acceptance-plan\n" + json.dumps(plan) + "\nzzzops-acceptance-plan -->\n")


if __name__ == "__main__":
    unittest.main()
