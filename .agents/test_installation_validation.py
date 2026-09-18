"""Regression tests for per-repository ZzzOps installation validation."""

from __future__ import annotations

import importlib.util
import hashlib
import io
import json
from datetime import datetime, timezone
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


def load_cli():
    spec = importlib.util.spec_from_file_location("zzzops_public_cli_installation_test", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class InstallationValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.cli = load_cli()
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

    def test_changed_audit_requires_fresh_signature_before_revalidation(self) -> None:
        first_audit = {"safe": True, "cleanup_required": False, "signature": "d" * 64}
        changed_audit = {"safe": True, "cleanup_required": False, "signature": "e" * 64}
        first_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        second_time = datetime(2026, 1, 2, tzinfo=timezone.utc)
        first_clock = SimpleNamespace(now=mock.Mock(return_value=first_time))
        second_clock = SimpleNamespace(now=mock.Mock(return_value=second_time))
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            with (
                mock.patch.object(self.module, "installation_audit", return_value=first_audit),
                mock.patch.object(self.module, "datetime", first_clock),
            ):
                original = self.module.record_validation(
                    repo, self.provenance, outcome="clean", audit_signature=first_audit["signature"],
                )
            original_bytes = self.module.record_path(repo).read_bytes()

            with mock.patch.object(self.module, "installation_audit", return_value=changed_audit):
                with self.assertRaisesRegex(self.module.InstallationValidationError, "audit changed"):
                    self.module.record_validation(
                        repo, self.provenance, outcome="clean", audit_signature=first_audit["signature"],
                    )
            self.assertEqual(original_bytes, self.module.record_path(repo).read_bytes())

            with (
                mock.patch.object(self.module, "installation_audit", return_value=changed_audit),
                mock.patch.object(self.module, "datetime", second_clock),
            ):
                revalidated = self.module.record_validation(
                    repo, self.provenance, outcome="clean", audit_signature=changed_audit["signature"],
                )
            self.assertEqual("2026-01-01T00:00:00Z", original["record"]["validated_at"])
            self.assertEqual("2026-01-02T00:00:00Z", revalidated["record"]["validated_at"])
            self.assertEqual(changed_audit["signature"], revalidated["record"]["audit_signature"])

    def test_generated_pycache_does_not_make_proven_legacy_install_unsafe(self) -> None:
        source = ".agents/zzzops/zzzops.py"
        cache = ".agents/zzzops/__pycache__/zzzops.cpython-313.pyc"
        data = b"print('legacy')\n"
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            for relative, content in ((source, data), (cache, b"generated bytecode")):
                path = repo.joinpath(*relative.split("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            lock = repo / ".zzzops" / "ZZZOPS_LOCK.json"
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text(json.dumps({
                "schema_version": 1,
                "revision": "b" * 40,
                "version": "v1.0.0",
                "files": {source: hashlib.sha256(data).hexdigest()},
            }), encoding="utf-8")

            audit = self.module.installation_audit(repo)

            self.assertTrue(audit["safe"], audit["errors"])
            self.assertTrue(audit["cleanup_required"])
            self.assertIn(cache, audit["remove_files"])
            recorded = self.module.record_validation(
                repo, self.provenance, outcome="declined", audit_signature=audit["signature"],
            )
            self.assertEqual("declined", recorded["record"]["outcome"])

    def test_cli_clean_first_use_and_idempotent_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            package = {"ok": True, **self.provenance}

            def invoke(*arguments: str) -> tuple[int, dict]:
                stream = io.StringIO()
                with (
                    mock.patch.object(self.cli._package, "package_status", return_value=package),
                    mock.patch.object(sys, "argv", [str(CLI), "--repo", str(repo), *arguments]),
                    mock.patch.object(sys, "stdout", stream),
                ):
                    code = self.cli.main()
                return code, json.loads(stream.getvalue())

            code, first = invoke("--intent", "validate_installation")
            self.assertEqual(0, code)
            step = first["next_steps"][0]
            self.assertEqual("installation_validation", step["kind"])
            self.assertEqual("installation_record", step["submission"]["operation"])
            self.assertTrue(step["audit"]["safe"], step["audit"]["errors"])
            submission = {**step["submission"], "outcome": "clean"}
            request = repo / "installation-result.json"
            request.write_text(json.dumps(submission), encoding="utf-8")

            required = {"required": True, "reason": "missing"}
            first_time = datetime(2026, 2, 1, tzinfo=timezone.utc)
            second_time = datetime(2026, 2, 2, tzinfo=timezone.utc)
            first_clock = SimpleNamespace(now=mock.Mock(return_value=first_time))
            second_clock = SimpleNamespace(now=mock.Mock(return_value=second_time))
            with (
                mock.patch.object(self.cli._installation, "validation_status", return_value=required),
                mock.patch.object(self.cli._installation, "datetime", first_clock),
            ):
                code, recorded = invoke("--intent", "validate_installation", "--input", str(request))
                self.assertEqual(0, code)
                record_bytes = self.cli._installation.record_path(repo).read_bytes()
            with (
                mock.patch.object(self.cli._installation, "validation_status", return_value=required),
                mock.patch.object(self.cli._installation, "datetime", second_clock),
            ):
                code, repeated = invoke("--intent", "validate_installation", "--input", str(request))
                self.assertEqual(0, code)
            self.assertEqual(recorded, repeated)
            self.assertEqual(record_bytes, self.cli._installation.record_path(repo).read_bytes())
            self.assertEqual("2026-02-01T00:00:00Z", json.loads(record_bytes)["validated_at"])
            first_clock.now.assert_called_once_with(timezone.utc)
            second_clock.now.assert_not_called()

            status = self.cli._installation.validation_status(repo, self.provenance)
            self.assertFalse(status["required"])
            self.assertEqual("current", status["reason"])

    def test_prompt_routes_once_and_preserves_confirmation_boundary(self) -> None:
        skill = (ROOT / "plugins" / "zzzops" / "zzzops" / "references" / "next_steps" / "installation-validation.md").read_text(encoding="utf-8")
        for required in (
            "returned installation status", "returned installation audit", "exact audit signature",
            "explicit removal confirmation", "records `declined`", "returned cleanup action",
            "resume that original workflow exactly once",
        ):
            self.assertIn(required, skill)
        for retired in ("`installation status`", "`installation audit`", "--apply --yes"):
            self.assertNotIn(retired, skill)


if __name__ == "__main__":
    unittest.main()
