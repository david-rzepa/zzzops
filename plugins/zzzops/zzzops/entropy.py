"""Compact, Git-local repository entropy observations."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
from typing import Any


SCHEMA_VERSION = 1
DIRECTORY_RELATIVE = "zzzops/entropy-observations"
ENTROPY_CATEGORIES = frozenset({"documentation", "tests", "code_quality_non_behavioral"})
MAX_PATHS = 4
MAX_PATH_LENGTH = 240
MAX_EVIDENCE_LENGTH = 280


class EntropyObservationError(ValueError):
    """Entropy-observation input or durable state is invalid or inconsistent."""


def observation_directory(repo: Path) -> Path:
    """Resolve the ignored inbox inside the repository's common Git directory."""
    result = subprocess.run(
        ["git", "-C", str(repo.resolve()), "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode or not result.stdout.strip():
        raise EntropyObservationError("target must be a Git working tree")
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = repo.resolve() / common
    common = common.resolve()
    if not common.is_dir():
        raise EntropyObservationError("Git common directory is unavailable")
    return common / DIRECTORY_RELATIVE


def _valid_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > MAX_PATH_LENGTH or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and value == path.as_posix() and ".." not in path.parts


def _validate_observation(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "category", "paths", "evidence", "goal", "revision",
    }:
        raise EntropyObservationError("entropy observation is invalid")
    paths = value.get("paths")
    evidence = value.get("evidence")
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or value.get("category") not in ENTROPY_CATEGORIES
        or not isinstance(paths, list)
        or not 1 <= len(paths) <= MAX_PATHS
        or len(paths) != len(set(paths))
        or any(not _valid_path(path) for path in paths)
        or not isinstance(evidence, str)
        or evidence != evidence.strip()
        or not 1 <= len(evidence) <= MAX_EVIDENCE_LENGTH
        or "\n" in evidence
        or "\r" in evidence
        or not isinstance(value.get("goal"), int)
        or isinstance(value.get("goal"), bool)
        or value["goal"] < 1
        or not isinstance(value.get("revision"), int)
        or isinstance(value.get("revision"), bool)
        or value["revision"] < 1
    ):
        raise EntropyObservationError(
            "entropy observation must contain one bounded fact and 1-4 normalized repository paths"
        )


def _fingerprint(value: dict[str, Any]) -> str:
    canonical = json.dumps(
        {key: value[key] for key in ("category", "paths", "evidence")},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_observation(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EntropyObservationError(f"entropy observation {path.name} could not be read") from exc
    _validate_observation(value)
    if path.stem != _fingerprint(value):
        raise EntropyObservationError(f"entropy observation {path.name} has an inconsistent fingerprint")
    return {"fingerprint": path.stem, **value}


def enabled_categories(project: dict[str, Any]) -> frozenset[str]:
    """Use only explicitly reviewed suggestion/refill categories."""
    sections = project.get("policy", {}).get("sections", []) if isinstance(project, dict) else []
    autonomy = next(
        (section for section in sections if isinstance(section, dict) and section.get("id") == "autonomy_approval_parallelism"),
        None,
    )
    settings = autonomy.get("settings", {}) if isinstance(autonomy, dict) else {}
    refill = settings.get("refill") if isinstance(settings, dict) else None
    configured = refill.get("allowed_categories") if isinstance(refill, dict) else None
    if configured is None:
        raise EntropyObservationError("reviewed work-suggestion categories are required")
    if not isinstance(configured, list) or any(not isinstance(item, str) for item in configured):
        raise EntropyObservationError("reviewed work-suggestion categories are invalid")
    return frozenset(configured) & ENTROPY_CATEGORIES


def list_observations(repo: Path, project: dict[str, Any]) -> dict[str, Any]:
    """Return pending observations eligible under the existing category policy."""
    directory = observation_directory(repo)
    observations = [_read_observation(path) for path in sorted(directory.glob("*.json"))] if directory.exists() else []
    allowed = enabled_categories(project)
    eligible = [item for item in observations if item["category"] in allowed]
    return {
        "schema_version": SCHEMA_VERSION,
        "pending": len(observations),
        "eligible": len(eligible),
        "excluded": len(observations) - len(eligible),
        "enabled_categories": sorted(allowed),
        "observations": eligible,
    }


def record_observation(
    repo: Path,
    *,
    category: str,
    paths: list[str],
    evidence: str,
    goal: int,
    revision: int,
) -> dict[str, Any]:
    normalized_paths = (
        sorted(set(paths))
        if isinstance(paths, list) and all(isinstance(path, str) for path in paths)
        else paths
    )
    observation = {
        "schema_version": SCHEMA_VERSION,
        "category": category,
        "paths": normalized_paths,
        "evidence": evidence.strip() if isinstance(evidence, str) else evidence,
        "goal": goal,
        "revision": revision,
    }
    _validate_observation(observation)
    fingerprint = _fingerprint(observation)
    directory = observation_directory(repo)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{fingerprint}.json"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".observation-", suffix=".tmp", dir=directory)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(observation, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
            recorded = True
        except FileExistsError:
            recorded = False
        confirmed = _read_observation(target)
        return {
            "recorded": recorded,
            "reason": "observation_recorded" if recorded else "already_recorded",
            "observation": confirmed,
        }
    finally:
        temporary.unlink(missing_ok=True)


def resolve_observations(repo: Path, *, fingerprints: list[str], outcome: str) -> dict[str, Any]:
    if outcome not in {"captured", "dismissed"}:
        raise EntropyObservationError("entropy observation outcome must be captured or dismissed")
    if (
        not isinstance(fingerprints, list)
        or not fingerprints
        or len(fingerprints) != len(set(fingerprints))
        or any(
            not isinstance(item, str)
            or len(item) != 64
            or any(character not in "0123456789abcdef" for character in item)
            for item in fingerprints
        )
    ):
        raise EntropyObservationError("entropy observation fingerprints are invalid")
    directory = observation_directory(repo)
    removed = 0
    for fingerprint in fingerprints:
        target = directory / f"{fingerprint}.json"
        try:
            target.unlink()
            removed += 1
        except FileNotFoundError:
            pass
    pending = len(list(directory.glob("*.json"))) if directory.exists() else 0
    return {"resolved": removed, "outcome": outcome, "pending": pending}
