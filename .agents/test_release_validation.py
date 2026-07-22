"""Regression checks for the shared release-validation contract."""

from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / ".github" / "scripts" / "run_product_validation.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("run_product_validation", RUNNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseValidationTests(unittest.TestCase):
    def test_linux_failure_stops_the_shared_validation_leg(self):
        runner = load_runner()
        failure = subprocess.CalledProcessError(1, ["failed-check"])
        with mock.patch.object(runner, "run", side_effect=[None, failure]) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                runner.linux_validation()
        self.assertEqual(2, run.call_count)

    def test_release_publish_waits_for_both_shared_validation_jobs(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("validate-linux:", workflow)
        self.assertIn("validate-windows:", workflow)
        self.assertIn("needs: [validate-linux, validate-windows]", workflow)
        self.assertIn("python .github/scripts/run_product_validation.py --platform linux", workflow)
        self.assertIn("python .github/scripts/run_product_validation.py --platform windows", workflow)


if __name__ == "__main__":
    unittest.main()
