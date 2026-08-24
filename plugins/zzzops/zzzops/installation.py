"""Per-repository validation state for the installed ZzzOps Agent Plugin."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any


SCHEMA_VERSION = 1
RECORD_RELATIVE = "zzzops/installation-validation.json"
OUTCOMES = {"clean", "declined"}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_CLEANUP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "cleanup_legacy.py"


class InstallationValidationError(ValueError):
    """Installation validation state or evidence is unsafe or inconsistent."""


def _cleanup_module():
    spec = importlib.util.spec_from_file_location("zzzops_legacy_cleanup", _CLEANUP_PATH)
    if not spec or not spec.loader:
        raise InstallationValidationError("legacy cleanup support is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def record_path(repo: Path) -> Path:
    """Resolve ignored validation state inside the repository's common Git directory."""
    result = subprocess.run(
        ["git", "-C", str(repo.resolve()), "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode or not result.stdout.strip():
        raise InstallationValidationError("target must be a Git working tree")
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = repo.resolve() / common
    common = common.resolve()
    if not common.is_dir():
        raise InstallationValidationError("Git common directory is unavailable")
    return common / RECORD_RELATIVE


def _valid_provenance(provenance: Any) -> bool:
    return (
        isinstance(provenance, dict)
        and set(provenance) == {"revision", "version"}
        and isinstance(provenance.get("version"), str)
        and bool(provenance["version"])
        and isinstance(provenance.get("revision"), str)
        and bool(_DIGEST.fullmatch(provenance["revision"]))
    )


def _load_record(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "invalid"
    if (
        not isinstance(value, dict)
        or set(value) != {"audit_signature", "outcome", "package", "schema_version", "validated_at"}
        or value.get("schema_version") != SCHEMA_VERSION
        or not _valid_provenance(value.get("package"))
        or value.get("outcome") not in OUTCOMES
        or not isinstance(value.get("audit_signature"), str)
        or not _DIGEST.fullmatch(value["audit_signature"])
        or not isinstance(value.get("validated_at"), str)
        or not _TIMESTAMP.fullmatch(value["validated_at"])
    ):
        return None, "invalid"
    return value, None


def validation_status(repo: Path, provenance: dict[str, str]) -> dict[str, Any]:
    if not _valid_provenance(provenance):
        raise InstallationValidationError("installed package provenance is invalid")
    path = record_path(repo)
    record, error = _load_record(path)
    if error:
        return {
            "schema_version": SCHEMA_VERSION,
            "required": True,
            "reason": error,
            "package": provenance,
            "record": None,
        }
    if record["package"] != provenance:
        return {
            "schema_version": SCHEMA_VERSION,
            "required": True,
            "reason": "package_changed",
            "package": provenance,
            "record": record,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "required": False,
        "reason": "current",
        "package": provenance,
        "record": record,
    }


def installation_audit(repo: Path) -> dict[str, Any]:
    cleaner = _cleanup_module()
    plan = cleaner.build_plan(repo.resolve())
    return {
        "schema_version": SCHEMA_VERSION,
        "safe": plan.safe,
        "cleanup_required": bool(plan.remove_files or plan.ignore_updates),
        "source": plan.source,
        "remove_files": plan.remove_files,
        "ignore_files": sorted(plan.ignore_updates),
        "tracked": plan.tracked,
        "errors": plan.errors,
        "warnings": plan.warnings,
        "signature": plan.signature,
    }


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".installation-validation-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def record_validation(
    repo: Path,
    provenance: dict[str, str],
    *,
    outcome: str,
    audit_signature: str,
) -> dict[str, Any]:
    if outcome not in OUTCOMES:
        raise InstallationValidationError("validation outcome must be clean or declined")
    audit = installation_audit(repo)
    if not audit["safe"]:
        raise InstallationValidationError("unsafe or ambiguous legacy content cannot be recorded as validated")
    if not _DIGEST.fullmatch(audit_signature) or audit_signature != audit["signature"]:
        raise InstallationValidationError("installation audit changed; rerun the preview")
    if outcome == "clean" and audit["cleanup_required"]:
        raise InstallationValidationError("legacy cleanup remains; record declined or remove the previewed files")
    if outcome == "declined" and not audit["cleanup_required"]:
        raise InstallationValidationError("declined is valid only when cleanup was offered")
    if not _valid_provenance(provenance):
        raise InstallationValidationError("installed package provenance is invalid")
    record = {
        "schema_version": SCHEMA_VERSION,
        "package": provenance,
        "outcome": outcome,
        "audit_signature": audit_signature,
        "validated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    path = record_path(repo)
    _atomic_json(path, record)
    confirmed, error = _load_record(path)
    if error or confirmed != record:
        raise InstallationValidationError("validation record could not be confirmed")
    return {"recorded": True, "record": record}
