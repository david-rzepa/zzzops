"""Durable, exact state for recent and full repository entropy reviews."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any


SCHEMA_VERSION = 1
SCOPE_VERSION = 1
DIRECTORY_RELATIVE = "zzzops/entropy-reviews"
EVENT_KINDS = {"verified_checkpoint", "integrated_change", "completed_goal"}
EVENT_FIELDS = {
    "schema_version", "repository", "goal", "revision", "goal_digest", "status", "kind",
    "pr", "base_oid", "head_oid", "merge_oid",
}
COMPLETION_FIELDS = {"schema_version", "batch_id", "outcome", "current_events"}
SUCCESS_OUTCOMES = {"clean", "findings"}
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
GIT_OID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
MAX_REQUEST_BYTES = 64 * 1024


class EntropyReviewError(ValueError):
    """Entropy-review state is invalid, inconsistent, or stale."""


def review_directory(repo: Path) -> Path:
    """Resolve the ignored review store inside the repository's common Git directory."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo.resolve()), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise EntropyReviewError("Git common directory could not be inspected") from exc
    if result.returncode or not result.stdout.strip():
        raise EntropyReviewError("target must be a Git working tree")
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = repo.resolve() / common
    common = common.resolve()
    if not common.is_dir():
        raise EntropyReviewError("Git common directory is unavailable")
    return common / DIRECTORY_RELATIVE


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _optional_oid(value: Any) -> bool:
    return value is None or isinstance(value, str) and GIT_OID.fullmatch(value) is not None


def _validate_fingerprints(values: Any, field: str) -> list[str]:
    if not isinstance(values, list) or any(
        not isinstance(item, str) or HEX_64.fullmatch(item) is None for item in values
    ):
        raise EntropyReviewError(f"{field} must be unique content-addressed identifiers")
    if len(values) != len(set(values)):
        raise EntropyReviewError(f"{field} must be unique content-addressed identifiers")
    return sorted(values)


def normalize_review_event(value: Any) -> dict[str, Any]:
    """Validate and normalize one exact goal-change event."""
    if not isinstance(value, dict) or set(value) != EVENT_FIELDS:
        raise EntropyReviewError("entropy-review event is invalid")
    event = dict(value)
    if (
        event.get("schema_version") != SCHEMA_VERSION
        or not isinstance(event.get("repository"), str)
        or len(event["repository"]) > 200
        or REPOSITORY_PATTERN.fullmatch(event["repository"]) is None
        or not _positive_integer(event.get("goal"))
        or not _positive_integer(event.get("revision"))
        or not isinstance(event.get("goal_digest"), str)
        or HEX_64.fullmatch(event["goal_digest"]) is None
        or event.get("kind") not in EVENT_KINDS
        or event.get("status") not in {"in_progress", "blocked", "done"}
        or not (event.get("pr") is None or _positive_integer(event.get("pr")))
        or any(not _optional_oid(event.get(field)) for field in ("base_oid", "head_oid", "merge_oid"))
    ):
        raise EntropyReviewError("entropy-review event fields are invalid")
    kind = event["kind"]
    oid_values = (event["base_oid"], event["head_oid"], event["merge_oid"])
    if event["pr"] is None and any(value is not None for value in oid_values):
        raise EntropyReviewError("event without a pull request cannot contain Git object identifiers")
    if any(value is not None for value in oid_values) and (
        event["pr"] is None or event["base_oid"] is None or event["head_oid"] is None
    ):
        raise EntropyReviewError("event Git object identifiers require a pull request, base, and head")
    if kind == "verified_checkpoint" and (
        event["status"] != "blocked"
        or event["pr"] is None
        or event["base_oid"] is None
        or event["head_oid"] is None
        or event["merge_oid"] is not None
    ):
        raise EntropyReviewError("verified checkpoint event is incomplete")
    if kind == "integrated_change" and (
        event["pr"] is None
        or event["base_oid"] is None
        or event["head_oid"] is None
        or event["merge_oid"] is None
    ):
        raise EntropyReviewError("integrated change event is incomplete")
    if kind == "completed_goal" and event["status"] != "done":
        raise EntropyReviewError("completed goal event must have done status")
    return event


def _read_json(path: Path, kind: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EntropyReviewError(f"entropy-review {kind} {path.name} could not be read") from exc
    if not isinstance(value, dict):
        raise EntropyReviewError(f"entropy-review {kind} {path.name} is invalid")
    return value


def _write_content_addressed(directory: Path, prefix: str, value: dict[str, Any]) -> tuple[str, bool]:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        identifier = _fingerprint(value)
        target = directory / f"{identifier}.json"
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{prefix}-", suffix=".tmp", dir=directory)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(_canonical(value) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
                recorded = True
            except FileExistsError:
                recorded = False
            if _read_json(target, prefix) != value or target.stem != _fingerprint(value):
                raise EntropyReviewError(f"entropy-review {prefix} write could not be confirmed")
            return identifier, recorded
        finally:
            temporary.unlink(missing_ok=True)
    except EntropyReviewError:
        raise
    except OSError as exc:
        raise EntropyReviewError(f"entropy-review {prefix} state could not be written") from exc


def _write_receipt(directory: Path, batch_id: str, value: dict[str, Any]) -> tuple[str, bool]:
    """Create the one allowed outcome for a batch, failing closed on disagreement."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{batch_id}.json"
        descriptor, temporary_name = tempfile.mkstemp(prefix=".receipt-", suffix=".tmp", dir=directory)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(_canonical(value) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
                recorded = True
            except FileExistsError:
                recorded = False
            existing = _read_json(target, "receipt")
            if existing != value:
                raise EntropyReviewError("entropy-review batch already has a different outcome")
            return _fingerprint(value), recorded
        finally:
            temporary.unlink(missing_ok=True)
    except EntropyReviewError:
        raise
    except OSError as exc:
        raise EntropyReviewError("entropy-review receipt state could not be written") from exc


def _event_records(repo: Path) -> dict[str, dict[str, Any]]:
    directory = review_directory(repo) / "events"
    records: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        event = normalize_review_event(_read_json(path, "event"))
        identifier = _fingerprint(event)
        if path.stem != identifier:
            raise EntropyReviewError(f"entropy-review event {path.name} has an inconsistent fingerprint")
        records[identifier] = event
    return records


def _validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "scope_version", "mode", "events", "observations",
    }:
        raise EntropyReviewError("entropy-review manifest is invalid")
    if value.get("schema_version") != SCHEMA_VERSION or value.get("scope_version") != SCOPE_VERSION:
        raise EntropyReviewError("entropy-review manifest version is invalid")
    if value.get("mode") not in {"recent", "full"}:
        raise EntropyReviewError("entropy-review manifest mode is invalid")
    return {
        "schema_version": SCHEMA_VERSION,
        "scope_version": SCOPE_VERSION,
        "mode": value["mode"],
        "events": _validate_fingerprints(value.get("events"), "manifest events"),
        "observations": _validate_fingerprints(value.get("observations"), "manifest observations"),
    }


def _manifest_records(repo: Path) -> dict[str, dict[str, Any]]:
    directory = review_directory(repo) / "manifests"
    records: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        manifest = _validate_manifest(_read_json(path, "manifest"))
        identifier = _fingerprint(manifest)
        if path.stem != identifier:
            raise EntropyReviewError(f"entropy-review manifest {path.name} has an inconsistent fingerprint")
        records[identifier] = manifest
    return records


def _validate_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "batch_id", "events", "observations", "outcome",
    }:
        raise EntropyReviewError("entropy-review receipt is invalid")
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or not isinstance(value.get("batch_id"), str)
        or HEX_64.fullmatch(value["batch_id"]) is None
        or value.get("outcome") not in SUCCESS_OUTCOMES
    ):
        raise EntropyReviewError("entropy-review receipt fields are invalid")
    return {
        "schema_version": SCHEMA_VERSION,
        "batch_id": value["batch_id"],
        "events": _validate_fingerprints(value.get("events"), "receipt events"),
        "observations": _validate_fingerprints(value.get("observations"), "receipt observations"),
        "outcome": value["outcome"],
    }


def _receipt_records(repo: Path, manifests: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    directory = review_directory(repo) / "receipts"
    records: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        receipt = _validate_receipt(_read_json(path, "receipt"))
        identifier = _fingerprint(receipt)
        if path.stem != receipt["batch_id"]:
            raise EntropyReviewError(f"entropy-review receipt {path.name} has an inconsistent batch identifier")
        manifest = manifests.get(receipt["batch_id"])
        if manifest is None or (
            receipt["events"] != manifest["events"]
            or receipt["observations"] != manifest["observations"]
        ):
            raise EntropyReviewError(f"entropy-review receipt {path.name} does not match its manifest")
        records[identifier] = receipt
    return records


def _current_events(
    events: dict[str, dict[str, Any]], fingerprints: Any,
) -> dict[str, dict[str, Any]]:
    frontiers: dict[tuple[str, int], list[tuple[str, dict[str, Any]]]] = {}
    for identifier, event in events.items():
        frontiers.setdefault((event["repository"], event["goal"]), []).append((identifier, event))
    if fingerprints is None:
        identifiers = []
        for candidates in frontiers.values():
            maximum = max(candidate[1]["revision"] for candidate in candidates)
            latest = [candidate_id for candidate_id, candidate in candidates if candidate["revision"] == maximum]
            if len(latest) != 1:
                raise EntropyReviewError("current event frontier is ambiguous for one goal")
            identifiers.extend(latest)
        identifiers.sort()
    else:
        identifiers = _validate_fingerprints(fingerprints, "current events")
    current: dict[str, dict[str, Any]] = {}
    goal_keys: set[tuple[str, int]] = set()
    for identifier in identifiers:
        event = events.get(identifier)
        if event is None:
            raise EntropyReviewError(f"current event {identifier} does not exist")
        key = (event["repository"], event["goal"])
        if key in goal_keys:
            raise EntropyReviewError("current events contain multiple revisions for one goal")
        goal_keys.add(key)
        current[identifier] = event
    for identifier, event in current.items():
        candidates = frontiers[(event["repository"], event["goal"])]
        maximum = max(candidate[1]["revision"] for candidate in candidates)
        latest = [candidate_id for candidate_id, candidate in candidates if candidate["revision"] == maximum]
        if len(latest) != 1:
            raise EntropyReviewError("current event frontier is ambiguous for one goal")
        if identifier != latest[0]:
            raise EntropyReviewError("current event is not the latest recorded revision for its goal")
    return current


def _validate_repository(events: dict[str, dict[str, Any]], expected_repository: str | None) -> None:
    if expected_repository is None:
        return
    if REPOSITORY_PATTERN.fullmatch(expected_repository) is None:
        raise EntropyReviewError("expected repository identity is invalid")
    if any(event["repository"].casefold() != expected_repository.casefold() for event in events.values()):
        raise EntropyReviewError("entropy-review state does not match project repository identity")


def _public_event_records(
    events: dict[str, dict[str, Any]], identifiers: list[str],
) -> list[dict[str, Any]]:
    return [{"event_id": identifier, **events[identifier]} for identifier in identifiers]


def record_review_event(repo: Path, event: Any) -> dict[str, Any]:
    """Record one immutable exact event; concurrent duplicates collapse."""
    normalized = normalize_review_event(event)
    identifier, recorded = _write_content_addressed(review_directory(repo) / "events", "event", normalized)
    return {
        "schema_version": SCHEMA_VERSION,
        "recorded": recorded,
        "reason": "event_recorded" if recorded else "already_recorded",
        "event_id": identifier,
    }


def _coverage(
    repo: Path,
    event_ids: set[str],
) -> tuple[dict[str, dict[str, Any]], set[str], set[str], int]:
    manifests = _manifest_records(repo)
    for batch_id, manifest in manifests.items():
        if not set(manifest["events"]).issubset(event_ids):
            raise EntropyReviewError(f"entropy-review manifest {batch_id} references a missing event")
    receipts = _receipt_records(repo, manifests)
    covered_events: set[str] = set()
    covered_observations: set[str] = set()
    for receipt in receipts.values():
        covered_events.update(receipt["events"])
        covered_observations.update(receipt["observations"])
    return manifests, covered_events, covered_observations, len(receipts)


def entropy_review_status(
    repo: Path,
    current_event_fingerprints: list[str] | None = None,
    observation_fingerprints: list[str] | None = None,
    expected_repository: str | None = None,
) -> dict[str, Any]:
    """Report uncovered exact events and caller-supplied eligible observations without writing."""
    observations = _validate_fingerprints(observation_fingerprints or [], "observation fingerprints")
    events = _event_records(repo)
    _validate_repository(events, expected_repository)
    current = _current_events(events, current_event_fingerprints)
    _, covered_events, _, receipt_count = _coverage(repo, set(events))
    pending_events = sorted(set(current) - covered_events)
    return {
        "schema_version": SCHEMA_VERSION,
        "due": bool(pending_events),
        "pending_events": pending_events,
        "event_records": _public_event_records(events, pending_events),
        "pending_observations": observations,
        "event_count": len(events),
        "receipt_count": receipt_count,
    }


def plan_entropy_review(
    repo: Path,
    *,
    mode: str,
    current_event_fingerprints: list[str] | None = None,
    observation_fingerprints: list[str] | None = None,
    expected_repository: str | None = None,
) -> dict[str, Any]:
    """Freeze one exact recent or full review manifest without advancing coverage."""
    if mode not in {"recent", "full"}:
        raise EntropyReviewError("entropy-review mode must be recent or full")
    observations = _validate_fingerprints(observation_fingerprints or [], "observation fingerprints")
    events = _event_records(repo)
    _validate_repository(events, expected_repository)
    current = _current_events(events, current_event_fingerprints)
    _, covered_events, _, _ = _coverage(repo, set(events))
    if mode == "recent":
        selected_events = sorted(set(current) - covered_events)
        selected_observations = observations
        if not selected_events:
            return {
                "schema_version": SCHEMA_VERSION,
                "mode": mode,
                "due": False,
                "batch_id": None,
                "events": [],
                "observations": [],
                "recorded": False,
            }
    else:
        selected_events = sorted(current)
        selected_observations = observations
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "scope_version": SCOPE_VERSION,
        "mode": mode,
        "events": selected_events,
        "observations": selected_observations,
    }
    batch_id, recorded = _write_content_addressed(
        review_directory(repo) / "manifests", "manifest", manifest,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "due": True,
        "batch_id": batch_id,
        "events": selected_events,
        "event_records": _public_event_records(events, selected_events),
        "observations": selected_observations,
        "recorded": recorded,
    }


def complete_entropy_review(
    repo: Path, request: Any, *, expected_repository: str | None = None,
) -> dict[str, Any]:
    """Record successful exact coverage after confirming the reviewed events remain current."""
    if not isinstance(request, dict) or set(request) != COMPLETION_FIELDS:
        raise EntropyReviewError("entropy-review completion is invalid")
    if (
        request.get("schema_version") != SCHEMA_VERSION
        or not isinstance(request.get("batch_id"), str)
        or HEX_64.fullmatch(request["batch_id"]) is None
        or request.get("outcome") not in SUCCESS_OUTCOMES
    ):
        raise EntropyReviewError("entropy-review completion fields are invalid")
    events = _event_records(repo)
    _validate_repository(events, expected_repository)
    current_events = _current_events(events, request.get("current_events"))
    manifests, _, _, _ = _coverage(repo, set(events))
    manifest = manifests.get(request["batch_id"])
    if manifest is None:
        raise EntropyReviewError("entropy-review batch does not exist")
    current_by_goal = {
        (event["repository"], event["goal"]): identifier
        for identifier, event in current_events.items()
    }
    for identifier in manifest["events"]:
        event = events[identifier]
        if current_by_goal.get((event["repository"], event["goal"])) != identifier:
            raise EntropyReviewError("entropy-review batch is stale; exact events changed")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": request["batch_id"],
        "events": manifest["events"],
        "observations": manifest["observations"],
        "outcome": request["outcome"],
    }
    receipt_id, recorded = _write_receipt(
        review_directory(repo) / "receipts", request["batch_id"], receipt,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "completed": True,
        "recorded": recorded,
        "reason": "review_completed" if recorded else "already_completed",
        "batch_id": request["batch_id"],
        "receipt_id": receipt_id,
        "outcome": request["outcome"],
    }


def load_review_json(path: Path) -> dict[str, Any]:
    """Read a bounded UTF-8 JSON request for mark or complete operations."""
    try:
        if path.stat().st_size > MAX_REQUEST_BYTES:
            raise EntropyReviewError("entropy-review request exceeds the size limit")
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except EntropyReviewError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EntropyReviewError(f"could not read entropy-review request: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise EntropyReviewError("entropy-review request must be an object")
    return value
