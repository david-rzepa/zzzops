"""Regression tests for per-repository ZzzOps installation validation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "plugins" / "zzzops" / "zzzops" / "installation.py"
CLI = ROOT / "plugins" / "zzzops" / "zzzops" / "zzzops.py"


def load_module():
    spec = importlib.util.spec_from_file_location("zzzops_installation_test", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class InstallationValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.provenance = {"version": "2.0.0", "revision": "a" * 64}

    def make_repo(self, directory: str) -> Path:
        repo = Path(directory)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        return repo

    def test_clean_record_is_git_local_current_and_invalidated_by_package_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            missing = self.module.validation_status(repo, self.provenance)
            self.assertTrue(missing["required"])
            self.assertEqual("missing", missing["reason"])

            audit = self.module.installation_audit(repo)
            self.assertTrue(audit["safe"], audit["errors"])
            self.assertFalse(audit["cleanup_required"])
            recorded = self.module.record_validation(
                repo, self.provenance, outcome="clean", audit_signature=audit["signature"],
            )
            self.assertTrue(recorded["recorded"])
            self.assertFalse(self.module.validation_status(repo, self.provenance)["required"])
            changed = {"version": "2.0.1", "revision": "b" * 64}
            self.assertEqual("package_changed", self.module.validation_status(repo, changed)["reason"])
            self.assertEqual("", subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True))
            self.assertTrue(str(self.module.record_path(repo)).startswith(str((repo / ".git").resolve())))

    def test_malformed_and_interrupted_records_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            path = self.module.record_path(repo)
            path.parent.mkdir(parents=True)
            path.write_text("{broken", encoding="utf-8")
            status = self.module.validation_status(repo, self.provenance)
            self.assertTrue(status["required"])
            self.assertEqual("invalid", status["reason"])

    def test_decline_requires_current_safe_cleanup_preview(self) -> None:
        plan = SimpleNamespace(
            safe=True, remove_files=[".agents/zzzops/zzzops.py"], ignore_updates={}, source="fixture",
            tracked=[], errors=[], warnings=[], signature="c" * 64,
        )
        cleaner = SimpleNamespace(build_plan=lambda _repo: plan)
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            self.module, "_cleanup_module", return_value=cleaner,
        ):
            repo = self.make_repo(directory)
            result = self.module.record_validation(
                repo, self.provenance, outcome="declined", audit_signature=plan.signature,
            )
            self.assertEqual("declined", result["record"]["outcome"])
            self.assertFalse(self.module.validation_status(repo, self.provenance)["required"])
            with self.assertRaisesRegex(self.module.InstallationValidationError, "cleanup remains"):
                self.module.record_validation(
                    repo, self.provenance, outcome="clean", audit_signature=plan.signature,
                )

    def test_unsafe_or_drifted_audit_never_records(self) -> None:
        unsafe = SimpleNamespace(
            safe=False, remove_files=[], ignore_updates={}, source=None, tracked=[],
            errors=["unknown file"], warnings=[], signature="d" * 64,
        )
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            self.module, "_cleanup_module", return_value=SimpleNamespace(build_plan=lambda _repo: unsafe),
        ):
            repo = self.make_repo(directory)
            with self.assertRaisesRegex(self.module.InstallationValidationError, "unsafe or ambiguous"):
                self.module.record_validation(
                    repo, self.provenance, outcome="clean", audit_signature=unsafe.signature,
                )
            self.assertFalse(self.module.record_path(repo).exists())

    def test_cli_clean_first_use_and_idempotent_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            audit = json.loads(subprocess.check_output(
                [sys.executable, str(CLI), "--repo", str(repo), "installation", "audit"], text=True,
            ))
            subprocess.run([
                sys.executable, str(CLI), "--repo", str(repo), "installation", "record",
                "--outcome", "clean", "--audit-signature", audit["signature"],
            ], check=True, capture_output=True, text=True)
            status = json.loads(subprocess.check_output(
                [sys.executable, str(CLI), "--repo", str(repo), "installation", "status"], text=True,
            ))
            self.assertFalse(status["required"])
            self.assertEqual("current", status["reason"])

    def test_prompt_routes_once_and_preserves_confirmation_boundary(self) -> None:
        initialization = (ROOT / "plugins" / "zzzops" / "rules" / "INITIALIZATION.md").read_text(encoding="utf-8")
        skill = (ROOT / "plugins" / "zzzops" / "skills" / "validate-zzzops-installation" / "SKILL.md").read_text(encoding="utf-8")
        for required in ("installation status", "required:true", "$validate-zzzops-installation", "resume the requested workflow once"):
            self.assertIn(required, initialization)
        for required in ("explicit removal confirmation", "records `declined`", "--apply --yes", "resume that original workflow exactly once"):
            self.assertIn(required, skill)


if __name__ == "__main__":
    unittest.main()
