"""Validated GitHub reservation metadata, adapters, and lifecycle coordination."""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import re
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

_POLICY_PATH = Path(__file__).with_name("policy.py")
_POLICY_SPEC = importlib.util.spec_from_file_location("zzzops_reservation_policy", _POLICY_PATH)
assert _POLICY_SPEC and _POLICY_SPEC.loader
_policy = importlib.util.module_from_spec(_POLICY_SPEC)
_POLICY_SPEC.loader.exec_module(_policy)
normalize_resources = _policy.normalize_resources
normalize_resource_policy = _policy.normalize_resource_policy
exclusive_resources = _policy.exclusive_resources

GITHUB_MANAGEMENT_PERMISSIONS = {"TRIAGE", "WRITE", "MAINTAIN", "ADMIN"}
RESERVATION_COLOR = "5319E7"
RESERVATION_ID = re.compile(r"^[A-Za-z0-9._-]+$")
RESERVATION_EXPIRY_GRACE_SECONDS = 60
RESOURCE_LABEL_PREFIX = "zzzops:resource:"
PHASE_LEASE_LABEL_PREFIX = "zzzops:phase:"
STORAGE_LOCK_LABEL_PREFIX = "zzzops:lock:"
PHASE_LEASE_VERSION = "z2"
_parse_goal: Callable[[str, int | None], dict[str, Any] | None] | None = None
_sanitize_output: Callable[[str], str] = lambda value: value

class ReservationProviderError(ValueError):
    """The provider did not produce a safe, confirmed reservation result."""


def configure_entrypoint(parse_goal: Callable[[str, int | None], dict[str, Any] | None], sanitize: Callable[[str], str]) -> None:
    global _parse_goal, _sanitize_output
    _parse_goal, _sanitize_output = parse_goal, sanitize

def _reservation_actor(value: str, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value or len(value) > limit or not RESERVATION_ID.fullmatch(value):
        raise ValueError(f"{field} must be 1-{limit} characters using letters, numbers, dot, underscore, or hyphen")
    return value


def reservation_label_name(goal: int) -> str:
    if not isinstance(goal, int) or isinstance(goal, bool) or goal < 1:
        raise ValueError("goal must be a positive issue number")
    return f"zzzops:reserve:{goal}"


def reservation_repository_key(repository: str) -> str:
    return hashlib.sha256(repository.casefold().encode("utf-8")).hexdigest()[:12]


def resource_label_name(resource: str) -> str:
    normalized = normalize_resources([resource])[0]
    return RESOURCE_LABEL_PREFIX + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def reservation_description(
    repository: str, goal: int, revision: int, owner: str, run_id: str, expires_at: int,
    acquired_at: int | None = None,
) -> str:
    owner = _reservation_actor(owner, "owner", 20)
    run_id = _reservation_actor(run_id, "run-id", 32)
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValueError("revision must be a positive integer")
    repository_key = reservation_repository_key(repository)
    acquired_at = expires_at if acquired_at is None else acquired_at
    description = f"z1|r={repository_key}|g={goal}|v={revision}|o={owner}|u={run_id}|a={acquired_at}|x={expires_at}"
    if len(description) > 100:
        raise ValueError("reservation metadata exceeds GitHub's label-description limit")
    return description


def parse_reservation_description(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        raise ReservationProviderError("Reservation metadata is missing; no ownership assumed.")
    parts = value.split("|")
    if not parts or parts[0] != "z1":
        raise ReservationProviderError("Reservation metadata is invalid; no ownership assumed.")
    fields = {}
    for part in parts[1:]:
        key, separator, item = part.partition("=")
        if not separator or key in fields:
            raise ReservationProviderError("Reservation metadata is invalid; no ownership assumed.")
        fields[key] = item
    if set(fields) != {"r", "g", "v", "o", "u", "a", "x"}:
        raise ReservationProviderError("Reservation metadata is incomplete; no ownership assumed.")
    try:
        metadata = {
            "repository_key": fields["r"], "goal": int(fields["g"]), "revision": int(fields["v"]),
            "owner": _reservation_actor(fields["o"], "owner", 20),
            "run_id": _reservation_actor(fields["u"], "run-id", 32), "acquired_at": int(fields["a"]),
            "expires_at": int(fields["x"]),
        }
        if metadata["goal"] < 1 or metadata["revision"] < 1 or metadata["acquired_at"] < 0 or metadata["expires_at"] < metadata["acquired_at"]:
            raise ValueError("reservation timestamps or identity are invalid")
        return metadata
    except ValueError as exc:
        raise ReservationProviderError("Reservation metadata is invalid; no ownership assumed.") from exc


class GitHubReservationAdapter:
    def __init__(self, repo: Path, repository: str):
        self.repo = repo
        self.repository = repository
        self.executable = shutil.which("gh")
        if not self.executable:
            raise ReservationProviderError("GitHub CLI is unavailable; no reservation was made.")
        self._identity_checked = False

    def _run(self, arguments: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
        if getattr(self, 'timeout_budget', None):
            timeout = self.timeout_budget(timeout)
        try:
            return subprocess.run(
                [self.executable, *arguments], cwd=self.repo, capture_output=True, text=True,
                encoding="utf-8", timeout=timeout, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ReservationProviderError(f"GitHub did not confirm the reservation request ({type(exc).__name__}); no ownership assumed.") from exc

    def _provider_error(self, result: subprocess.CompletedProcess[str]) -> ReservationProviderError:
        detail = _sanitize_output((result.stderr.strip() or result.stdout.strip() or "unknown GitHub error").splitlines()[0][:300])
        return ReservationProviderError(f"GitHub did not confirm the reservation request: {detail}")

    def ensure_identity(self) -> None:
        if self._identity_checked:
            return
        result = self._run(["repo", "view", self.repository, "--json", "nameWithOwner,hasIssuesEnabled,viewerPermission"])
        if result.returncode:
            raise self._provider_error(result)
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ReservationProviderError("GitHub returned invalid repository metadata; no reservation was made.") from exc
        if data.get("nameWithOwner", "").casefold() != self.repository.casefold():
            raise ReservationProviderError("GitHub repository identity changed; no reservation was made.")
        if not data.get("hasIssuesEnabled") or data.get("viewerPermission") not in GITHUB_MANAGEMENT_PERMISSIONS:
            raise ReservationProviderError("GitHub Issues management permission is required; no reservation was made.")
        self._identity_checked = True

    def goal_revision(self, goal: int, require_writable: bool = False) -> int:
        self.ensure_identity()
        result = self._run(["api", f"repos/{self.repository}/issues/{goal}"])
        if result.returncode:
            raise self._provider_error(result)
        try:
            issue = json.loads(result.stdout)
            parsed = _parse_goal(issue.get("body"), goal)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ReservationProviderError("The goal could not be validated; no reservation was made.") from exc
        if parsed is None:
            raise ReservationProviderError("The goal could not be validated; no reservation was made.")
        if require_writable and parsed["status"] not in {"ready", "in_progress"}:
            raise ReservationProviderError(f"Goal #{goal} is not available for work; no reservation was made.")
        return parsed["revision"]

    def get_label(self, name: str) -> dict[str, Any] | None:
        result = self._run(["api", f"repos/{self.repository}/labels/{quote(name, safe='')}"])
        if result.returncode:
            if "404" in result.stderr or "Not Found" in result.stderr:
                return None
            raise self._provider_error(result)
        try:
            label = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ReservationProviderError("GitHub returned invalid reservation metadata; no ownership assumed.") from exc
        if not isinstance(label, dict) or not label.get("node_id"):
            raise ReservationProviderError("GitHub returned incomplete reservation metadata; no ownership assumed.")
        return label

    def list_resource_labels(self) -> list[dict[str, Any]]:
        result = self._run([
            "api", "--paginate", "--slurp", f"repos/{self.repository}/labels?per_page=100",
        ])
        if result.returncode:
            raise self._provider_error(result)
        try:
            pages = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ReservationProviderError(
                "GitHub returned invalid resource reservation metadata; no release was assumed."
            ) from exc
        if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
            raise ReservationProviderError(
                "GitHub returned incomplete resource reservation metadata; no release was assumed."
            )
        labels = []
        for label in (item for page in pages for item in page):
            if not isinstance(label, dict):
                raise ReservationProviderError(
                    "GitHub returned incomplete resource reservation metadata; no release was assumed."
                )
            if str(label.get("name", "")).startswith(RESOURCE_LABEL_PREFIX):
                if not label.get("node_id"):
                    raise ReservationProviderError(
                        "GitHub returned incomplete resource reservation metadata; no release was assumed."
                    )
                labels.append(label)
        return labels

    def create_label(self, name: str, description: str) -> dict[str, Any] | None:
        result = self._run([
            "api", "--method", "POST", f"repos/{self.repository}/labels",
            "-f", f"name={name}", "-f", f"color={RESERVATION_COLOR}", "-f", f"description={description}",
        ])
        if result.returncode:
            existing = self.get_label(name)
            if existing is not None:
                return None
            raise self._provider_error(result)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            confirmed = self.get_label(name)
            if confirmed and confirmed.get("description") == description:
                return confirmed
            raise ReservationProviderError("GitHub did not confirm the created reservation; no ownership assumed.") from exc

    def delete_label(self, node_id: str) -> None:
        query = "mutation($id:ID!){deleteLabel(input:{id:$id}){clientMutationId}}"
        result = self._run(["api", "graphql", "-F", f"id={node_id}", "-f", f"query={query}"])
        if result.returncode:
            raise self._provider_error(result)

    def update_label(self, node_id: str, description: str) -> None:
        query = "mutation($id:ID!,$description:String!){updateLabel(input:{id:$id,description:$description}){label{id description}}}"
        result = self._run([
            "api", "graphql", "-F", f"id={node_id}", "-F", f"description={description}", "-f", f"query={query}",
        ])
        if result.returncode:
            raise self._provider_error(result)


def _validate_reservation_goal(
    adapter: Any, repository: str, goal: int, revision: int, require_writable: bool = False,
) -> None:
    if adapter.repository.casefold() != repository.casefold():
        raise ReservationProviderError("Repository identity changed; no reservation was made.")
    observed_revision = adapter.goal_revision(goal, require_writable=require_writable)
    if observed_revision != revision:
        raise ReservationProviderError(
            f"Goal #{goal} changed from revision {revision} to {observed_revision}; refresh before reserving it."
        )


def _reservation_matches(label: dict[str, Any], description: str) -> bool:
    return label.get("description") == description and bool(label.get("node_id"))


def _validate_reservation_metadata(metadata: dict[str, Any], repository: str, goal: int) -> None:
    if metadata["repository_key"] != reservation_repository_key(repository) or metadata["goal"] != goal:
        raise ReservationProviderError("Reservation identity is invalid; no ownership assumed.")


def _validate_reservation_repository(metadata: dict[str, Any], repository: str) -> None:
    if metadata["repository_key"] != reservation_repository_key(repository):
        raise ReservationProviderError("Reservation repository identity is invalid; no ownership assumed.")


def _live_reservation_holder(metadata: dict[str, Any], now_epoch: int) -> dict[str, Any] | None:
    """Project only bounded, validated metadata for a presently live holder."""
    if metadata["expires_at"] <= now_epoch:
        return None
    return {key: metadata[key] for key in ("goal", "owner", "run_id", "expires_at")}


def acquire_reservation(
    adapter: Any, repository: str, goal: int, revision: int, owner: str, run_id: str,
    ttl_seconds: int = 900, now: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 60 <= ttl_seconds <= 86400:
        raise ValueError("ttl-seconds must be from 60 to 86400")
    now = now or datetime.now(timezone.utc)
    now_epoch = int(now.timestamp())
    expires_at = now_epoch + ttl_seconds
    name = reservation_label_name(goal)
    description = reservation_description(repository, goal, revision, owner, run_id, expires_at, now_epoch)
    _validate_reservation_goal(adapter, repository, goal, revision, require_writable=True)
    existing = adapter.get_label(name)
    if existing is not None:
        current = parse_reservation_description(existing.get("description"))
        _validate_reservation_metadata(current, repository, goal)
        if current["owner"] == owner and current["run_id"] == run_id and current["revision"] <= revision and current["expires_at"] > now_epoch:
            return {"acquired": True, "outcome": "already_owned", "goal": goal, "expires_at": current["expires_at"]}
        if current["expires_at"] + RESERVATION_EXPIRY_GRACE_SECONDS > now_epoch:
            return {"acquired": False, "outcome": "contended", "goal": goal}
        try:
            adapter.delete_label(existing["node_id"])
        except ReservationProviderError:
            pass
    created = adapter.create_label(name, description)
    if created is None:
        return {"acquired": False, "outcome": "contended", "goal": goal}
    if not _reservation_matches(created, description):
        confirmed = adapter.get_label(name)
        if confirmed is None or not _reservation_matches(confirmed, description):
            raise ReservationProviderError("GitHub did not confirm reservation ownership; no ownership assumed.")
    return {"acquired": True, "outcome": "acquired", "goal": goal, "acquired_at": now_epoch, "expires_at": expires_at}


def renew_reservation(
    adapter: Any, repository: str, goal: int, revision: int, owner: str, run_id: str,
    ttl_seconds: int = 900, now: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 60 <= ttl_seconds <= 86400:
        raise ValueError("ttl-seconds must be from 60 to 86400")
    now = now or datetime.now(timezone.utc)
    now_epoch = int(now.timestamp())
    name = reservation_label_name(goal)
    _validate_reservation_goal(adapter, repository, goal, revision)
    existing = adapter.get_label(name)
    if existing is None:
        return {"acquired": False, "outcome": "missing", "goal": goal}
    current = parse_reservation_description(existing.get("description"))
    _validate_reservation_metadata(current, repository, goal)
    if current["owner"] != owner or current["run_id"] != run_id or current["revision"] > revision or current["expires_at"] <= now_epoch:
        return {"acquired": False, "outcome": "not_owned", "goal": goal}
    expires_at = now_epoch + ttl_seconds
    description = reservation_description(
        repository, goal, revision, owner, run_id, expires_at, current["acquired_at"],
    )
    try:
        adapter.update_label(existing["node_id"], description)
    except ReservationProviderError:
        confirmed = adapter.get_label(name)
        if confirmed is None or confirmed.get("node_id") != existing["node_id"] or not _reservation_matches(confirmed, description):
            raise ReservationProviderError("GitHub did not confirm reservation renewal; no ownership assumed.")
    return {"acquired": True, "outcome": "renewed", "goal": goal, "expires_at": expires_at}


def release_reservation(
    adapter: Any, repository: str, goal: int, revision: int, owner: str, run_id: str, *, _validated: bool = False,
) -> dict[str, Any]:
    name = reservation_label_name(goal)
    if not _validated:
        _validate_reservation_goal(adapter, repository, goal, revision)
    existing = adapter.get_label(name)
    if existing is None:
        return {"released": True, "outcome": "already_released", "goal": goal}
    current = parse_reservation_description(existing.get("description"))
    _validate_reservation_metadata(current, repository, goal)
    if current["owner"] != owner or current["run_id"] != run_id or current["revision"] > revision:
        return {"released": False, "outcome": "not_owned", "goal": goal}
    try:
        adapter.delete_label(existing["node_id"])
    except ReservationProviderError:
        confirmed = adapter.get_label(name)
        if confirmed is not None and confirmed.get("node_id") == existing["node_id"]:
            raise ReservationProviderError("GitHub did not confirm reservation release; it will expire safely.")
    return {"released": True, "outcome": "released", "goal": goal}


def _acquire_resource(
    adapter: Any, repository: str, resource: str, goal: int, revision: int, owner: str, run_id: str,
    ttl_seconds: int, now: datetime,
) -> dict[str, Any]:
    now_epoch = int(now.timestamp())
    expires_at = now_epoch + ttl_seconds
    name = resource_label_name(resource)
    description = reservation_description(repository, goal, revision, owner, run_id, expires_at, now_epoch)
    existing = adapter.get_label(name)
    if existing is not None:
        current = parse_reservation_description(existing.get("description"))
        _validate_reservation_repository(current, repository)
        if (
            current["goal"] == goal and current["owner"] == owner and current["run_id"] == run_id
            and current["revision"] <= revision and current["expires_at"] > now_epoch
        ):
            return {"acquired": True, "outcome": "already_owned", "resource": resource}
        if current["expires_at"] + RESERVATION_EXPIRY_GRACE_SECONDS > now_epoch:
            result = {"acquired": False, "outcome": "resource_contended", "resource": resource}
            holder = _live_reservation_holder(current, now_epoch)
            return {**result, "holder": holder} if holder is not None else result
        try:
            adapter.delete_label(existing["node_id"])
        except ReservationProviderError:
            pass
    created = adapter.create_label(name, description)
    if created is None:
        result = {"acquired": False, "outcome": "resource_contended", "resource": resource}
        confirmed = adapter.get_label(name)
        if confirmed is None:
            return result
        current = parse_reservation_description(confirmed.get("description"))
        _validate_reservation_repository(current, repository)
        holder = _live_reservation_holder(current, now_epoch)
        return {**result, "holder": holder} if holder is not None else result
    if not _reservation_matches(created, description):
        confirmed = adapter.get_label(name)
        if confirmed is None or not _reservation_matches(confirmed, description):
            raise ReservationProviderError("GitHub did not confirm resource ownership; no ownership assumed.")
    return {"acquired": True, "outcome": "acquired", "resource": resource}


def _renew_resource(
    adapter: Any, repository: str, resource: str, goal: int, revision: int, owner: str, run_id: str,
    ttl_seconds: int, now: datetime,
) -> dict[str, Any]:
    name = resource_label_name(resource)
    existing = adapter.get_label(name)
    if existing is None:
        return {"acquired": False, "outcome": "missing", "resource": resource}
    current = parse_reservation_description(existing.get("description"))
    _validate_reservation_repository(current, repository)
    now_epoch = int(now.timestamp())
    if (
        current["goal"] != goal or current["owner"] != owner or current["run_id"] != run_id
        or current["revision"] > revision or current["expires_at"] <= now_epoch
    ):
        return {"acquired": False, "outcome": "not_owned", "resource": resource}
    description = reservation_description(
        repository, goal, revision, owner, run_id, now_epoch + ttl_seconds, current["acquired_at"],
    )
    try:
        adapter.update_label(existing["node_id"], description)
    except ReservationProviderError:
        confirmed = adapter.get_label(name)
        if confirmed is None or confirmed.get("node_id") != existing["node_id"] or not _reservation_matches(confirmed, description):
            raise ReservationProviderError("GitHub did not confirm resource renewal; no ownership assumed.")
    return {"acquired": True, "outcome": "renewed", "resource": resource}


def _release_resource(
    adapter: Any, repository: str, resource: str, goal: int, revision: int, owner: str, run_id: str,
    *, ignore_not_owned: bool = False,
) -> None:
    name = resource_label_name(resource)
    existing = adapter.get_label(name)
    if existing is None:
        return
    current = parse_reservation_description(existing.get("description"))
    _validate_reservation_repository(current, repository)
    if current["goal"] != goal or current["owner"] != owner or current["run_id"] != run_id or current["revision"] > revision:
        if ignore_not_owned:
            return
        raise ReservationProviderError("This run does not own every declared resource; no release was assumed.")
    try:
        adapter.delete_label(existing["node_id"])
    except ReservationProviderError:
        confirmed = adapter.get_label(name)
        if confirmed is not None and confirmed.get("node_id") == existing["node_id"]:
            raise ReservationProviderError("GitHub did not confirm resource release; it will expire safely.")


def _owned_resource_labels(
    adapter: Any, repository: str, goal: int, revision: int, owner: str, run_id: str,
) -> list[dict[str, Any]]:
    owned = []
    for label in adapter.list_resource_labels():
        metadata = parse_reservation_description(label.get("description"))
        if metadata["repository_key"] != reservation_repository_key(repository):
            continue
        if (
            metadata["goal"] == goal and metadata["owner"] == owner and metadata["run_id"] == run_id
            and metadata["revision"] <= revision
        ):
            owned.append(label)
    return owned


def _delete_discovered_resource(adapter: Any, label: dict[str, Any]) -> None:
    try:
        adapter.delete_label(label["node_id"])
    except ReservationProviderError:
        confirmed = adapter.get_label(label["name"])
        if confirmed is not None and confirmed.get("node_id") == label["node_id"]:
            raise ReservationProviderError("GitHub did not confirm resource release; it will expire safely.")


def acquire_reservation_bundle(
    adapter: Any, repository: str, goal: int, revision: int, owner: str, run_id: str,
    resources: list[str], ttl_seconds: int = 900, now: datetime | None = None, resource_policy: Any = None,
) -> dict[str, Any]:
    resources = normalize_resources(resources)
    reserved_resources = exclusive_resources(resources, resource_policy)
    now = now or datetime.now(timezone.utc)
    goal_result = acquire_reservation(adapter, repository, goal, revision, owner, run_id, ttl_seconds, now)
    if not goal_result["acquired"]:
        return goal_result
    acquired = []
    try:
        for resource in reserved_resources:
            result = _acquire_resource(adapter, repository, resource, goal, revision, owner, run_id, ttl_seconds, now)
            if not result["acquired"]:
                for held in reversed(acquired):
                    _release_resource(adapter, repository, held, goal, revision, owner, run_id)
                release_reservation(adapter, repository, goal, revision, owner, run_id, _validated=True)
                contention = {"acquired": False, "outcome": "resource_contended", "goal": goal, "resource": resource}
                return {**contention, "holder": result["holder"]} if "holder" in result else contention
            acquired.append(resource)
    except Exception:
        for held in reversed(acquired):
            _release_resource(adapter, repository, held, goal, revision, owner, run_id)
        release_reservation(adapter, repository, goal, revision, owner, run_id, _validated=True)
        raise
    return {**goal_result, "resources": resources, "reserved_resources": reserved_resources}


def renew_reservation_bundle(
    adapter: Any, repository: str, goal: int, revision: int, owner: str, run_id: str,
    resources: list[str], ttl_seconds: int = 900, now: datetime | None = None, resource_policy: Any = None,
) -> dict[str, Any]:
    resources = normalize_resources(resources)
    reserved_resources = exclusive_resources(resources, resource_policy)
    now = now or datetime.now(timezone.utc)
    result = renew_reservation(adapter, repository, goal, revision, owner, run_id, ttl_seconds, now)
    if not result["acquired"]:
        return result
    for resource in reserved_resources:
        resource_result = _renew_resource(adapter, repository, resource, goal, revision, owner, run_id, ttl_seconds, now)
        if not resource_result["acquired"]:
            return {"acquired": False, "outcome": "resource_lost", "goal": goal, "resource": resource}
    return {**result, "resources": resources, "reserved_resources": reserved_resources}


def release_reservation_bundle(
    adapter: Any, repository: str, goal: int, revision: int, owner: str, run_id: str, resources: list[str],
    resource_policy: Any = None,
) -> dict[str, Any]:
    exclusive_resources(resources, resource_policy)  # Validate retained CLI arguments and reviewed policy.
    try:
        _validate_reservation_goal(adapter, repository, goal, revision)
    except ReservationProviderError as exc:
        return {"released": False, "outcome": "failed", "goal": goal, "detail": str(exc)}
    removed = 0
    try:
        owned = _owned_resource_labels(adapter, repository, goal, revision, owner, run_id)
    except ReservationProviderError as exc:
        return {"released": False, "outcome": "failed", "goal": goal, "detail": str(exc)}
    for label in reversed(owned):
        try:
            _delete_discovered_resource(adapter, label)
            removed += 1
        except ReservationProviderError as exc:
            outcome = "partial" if removed else "failed"
            return {
                "released": False, "outcome": outcome, "goal": goal,
                "released_resources": removed, "detail": str(exc),
            }
    try:
        remaining = _owned_resource_labels(adapter, repository, goal, revision, owner, run_id)
    except ReservationProviderError as exc:
        outcome = "partial" if removed else "failed"
        return {
            "released": False, "outcome": outcome, "goal": goal,
            "released_resources": removed, "detail": str(exc),
        }
    if remaining:
        return {
            "released": False, "outcome": "partial", "goal": goal,
            "released_resources": removed, "detail": "Owned resource reservations remain after release.",
        }
    try:
        goal_result = release_reservation(adapter, repository, goal, revision, owner, run_id, _validated=True)
    except ReservationProviderError as exc:
        outcome = "partial" if removed else "failed"
        return {
            "released": False, "outcome": outcome, "goal": goal,
            "released_resources": removed, "detail": str(exc),
        }
    if goal_result["outcome"] == "already_released" and not removed:
        return goal_result
    return {"released": True, "outcome": "released", "goal": goal}


def reservation_cli_message(result: dict[str, Any], goal: int) -> str:
    outcome = result.get("outcome")
    if result.get("acquired") is True:
        return f"Reserved goal #{goal}."
    if outcome == "released":
        return f"Released goal #{goal} and all owned resources."
    if outcome == "already_released":
        return f"Goal #{goal} and its owned resources were already released."
    if outcome == "partial":
        return f"Partially released goal #{goal}; owned reservations remain. Retry after refreshing."
    if outcome == "failed":
        return f"Could not safely release goal #{goal}; no complete release was assumed."
    if outcome in {"contended", "resource_contended"}:
        holder = result.get("holder")
        if isinstance(holder, dict):
            try:
                holder_goal = holder["goal"]
                holder_owner = _reservation_actor(holder["owner"], "owner", 20)
                holder_run = _reservation_actor(holder["run_id"], "run-id", 32)
                holder_expiry = holder["expires_at"]
                if isinstance(holder_goal, int) and not isinstance(holder_goal, bool) and holder_goal > 0 and isinstance(holder_expiry, int) and not isinstance(holder_expiry, bool) and holder_expiry >= 0:
                    return f"Overlapping work is held by goal #{holder_goal}, owner {holder_owner}, run {holder_run}, until {holder_expiry}. Refresh and choose different work."
            except (KeyError, ValueError):
                pass
        return f"Another agent is handling overlapping work for goal #{goal}. Refresh and choose different work."
    return f"Goal #{goal} is not reserved by this run. Refresh before continuing."


def phase_lease_label_name(goal: int, phase: str) -> str:
    """Return the repository-global label used for one persisted phase lease."""
    if not isinstance(goal, int) or isinstance(goal, bool) or goal < 1:
        raise ValueError("goal must be a positive issue number")
    phase = _reservation_actor(phase, "phase", 24)
    return f"{PHASE_LEASE_LABEL_PREFIX}{goal}:{phase}"


def storage_lock_label_name(key: str) -> str:
    """Return a bounded stable label for a brief backend-storage lock."""
    key = _reservation_actor(key, "storage key", 24)
    return f"{STORAGE_LOCK_LABEL_PREFIX}{key}"


def storage_lock_description(repository: str, key: str, owner: str, run_id: str, expires_at: int) -> str:
    key = _reservation_actor(key, "storage key", 24)
    owner = _reservation_actor(owner, "owner", 20)
    run_id = _reservation_actor(run_id, "run-id", 32)
    value = f"z3|r={reservation_repository_key(repository)}|k={key}|o={owner}|u={run_id}|x={expires_at}"
    if len(value) > 100:
        raise ValueError("storage lock metadata exceeds GitHub's label-description limit")
    return value


def parse_storage_lock_description(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value.startswith("z3|"):
        raise ReservationProviderError("Storage lock metadata is invalid; no ownership assumed.")
    fields = dict(part.split("=", 1) for part in value.split("|")[1:] if "=" in part)
    if set(fields) != {"r", "k", "o", "u", "x"}:
        raise ReservationProviderError("Storage lock metadata is incomplete; no ownership assumed.")
    try:
        return {
            "repository_key": fields["r"], "key": _reservation_actor(fields["k"], "storage key", 24),
            "owner": _reservation_actor(fields["o"], "owner", 20), "run_id": _reservation_actor(fields["u"], "run-id", 32),
            "expires_at": int(fields["x"]),
        }
    except ValueError as exc:
        raise ReservationProviderError("Storage lock metadata is invalid; no ownership assumed.") from exc


def acquire_storage_lock(adapter: Any, repository: str, key: str, owner: str, run_id: str, ttl_seconds: int = 60, now: datetime | None = None) -> dict[str, Any]:
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 10 <= ttl_seconds <= 300:
        raise ValueError("storage-lock ttl-seconds must be from 10 to 300")
    now_epoch = int((now or datetime.now(timezone.utc)).timestamp())
    name = storage_lock_label_name(key)
    expected = storage_lock_description(repository, key, owner, run_id, now_epoch + ttl_seconds)
    existing = adapter.get_label(name)
    if existing is not None:
        current = parse_storage_lock_description(existing.get("description"))
        if current["repository_key"] != reservation_repository_key(repository) or current["key"] != key:
            raise ReservationProviderError("Storage lock identity is invalid; no ownership assumed.")
        if current["expires_at"] > now_epoch:
            return {"acquired": False, "outcome": "contended", "key": key}
        adapter.delete_label(existing["node_id"])
    created = adapter.create_label(name, expected)
    if created is None:
        return {"acquired": False, "outcome": "contended", "key": key}
    if created.get("description") != expected or not created.get("node_id"):
        raise ReservationProviderError("GitHub did not confirm storage lock ownership; no ownership assumed.")
    return {"acquired": True, "outcome": "acquired", "key": key, "expires_at": now_epoch + ttl_seconds}


def renew_storage_lock(adapter: Any, repository: str, key: str, owner: str, run_id: str, ttl_seconds: int = 60, now: datetime | None = None) -> dict[str, Any]:
    now_epoch = int((now or datetime.now(timezone.utc)).timestamp())
    existing = adapter.get_label(storage_lock_label_name(key))
    if existing is None:
        return {"acquired": False, "outcome": "missing", "key": key}
    current = parse_storage_lock_description(existing.get("description"))
    if (current["repository_key"] != reservation_repository_key(repository) or current["key"] != key
            or current["owner"] != owner or current["run_id"] != run_id):
        return {"acquired": False, "outcome": "not_owned", "key": key}
    expected = storage_lock_description(repository, key, owner, run_id, now_epoch + ttl_seconds)
    adapter.update_label(existing["node_id"], expected)
    confirmed = adapter.get_label(storage_lock_label_name(key))
    if confirmed is None or confirmed.get("node_id") != existing["node_id"] or confirmed.get("description") != expected:
        raise ReservationProviderError("GitHub did not confirm storage lock renewal; no ownership assumed.")
    return {"acquired": True, "outcome": "renewed", "key": key, "expires_at": now_epoch + ttl_seconds}


def release_storage_lock(adapter: Any, repository: str, key: str, owner: str, run_id: str) -> dict[str, Any]:
    existing = adapter.get_label(storage_lock_label_name(key))
    if existing is None:
        return {"released": True, "outcome": "already_released", "key": key}
    current = parse_storage_lock_description(existing.get("description"))
    if (current["repository_key"] != reservation_repository_key(repository) or current["key"] != key
            or current["owner"] != owner or current["run_id"] != run_id):
        return {"released": False, "outcome": "not_owned", "key": key}
    adapter.delete_label(existing["node_id"])
    if adapter.get_label(storage_lock_label_name(key)) is not None:
        raise ReservationProviderError("GitHub did not confirm storage lock release; no ownership assumed.")
    return {"released": True, "outcome": "released", "key": key}


def apply_independent_batch(items: list[dict[str, Any]], apply: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    """Apply independent items in order, preserving confirmed per-item results."""
    seen: set[str] = set()
    validated_ids: list[str] = []
    for item in items:
        item_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(item_id, str) or not item_id or item_id in seen:
            results = [{"id": value, "result": {"ok": False, "outcome": "batch_rejected"}}
                       for value in validated_ids]
            return {"applied": False, "results": results, "error": "batch item id is invalid"}
        seen.add(item_id)
        if item.get("depends_on"):
            results = [{"id": value, "result": {"ok": False, "outcome": "batch_rejected"}}
                       for value in validated_ids]
            return {"applied": False, "results": results, "error": f"batch item {item_id} is dependent"}
        validated_ids.append(item_id)

    results = []
    all_applied = True
    for item in items:
        item_id = item["id"]
        try:
            result = apply(item)
        except Exception as exc:  # Each independent item owns its failure boundary.
            all_applied = False
            results.append({"id": item_id, "result": {
                "ok": False, "outcome": "error", "error": f"{type(exc).__name__}: {exc}",
            }})
            continue
        results.append({"id": item_id, "result": result})
        if not isinstance(result, dict) or result.get("ok") is not True:
            all_applied = False
    response: dict[str, Any] = {"applied": all_applied, "results": results}
    if not all_applied:
        response["error"] = "one or more independent batch items failed"
    return response


def phase_lease_description(
    repository: str, goal: int, phase: str, revision: int, owner: str, run_id: str,
    expires_at: int, generation: int = 1,
) -> str:
    phase = _reservation_actor(phase, "phase", 24)
    owner = _reservation_actor(owner, "owner", 20)
    run_id = _reservation_actor(run_id, "run-id", 32)
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValueError("revision must be a positive integer")
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise ValueError("generation must be a positive integer")
    value = f"{PHASE_LEASE_VERSION}|r={reservation_repository_key(repository)}|g={goal}|p={phase}|v={revision}|o={owner}|u={run_id}|n={generation}|x={expires_at}"
    if len(value) > 100:
        raise ValueError("phase lease metadata exceeds GitHub's label-description limit")
    return value


def parse_phase_lease_description(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        raise ReservationProviderError("Phase lease metadata is missing; no ownership assumed.")
    parts = value.split("|")
    if not parts or parts[0] != PHASE_LEASE_VERSION:
        raise ReservationProviderError("Phase lease metadata is invalid; no ownership assumed.")
    fields: dict[str, str] = {}
    for part in parts[1:]:
        key, separator, item = part.partition("=")
        if not separator or key in fields:
            raise ReservationProviderError("Phase lease metadata is invalid; no ownership assumed.")
        fields[key] = item
    if set(fields) != {"r", "g", "p", "v", "o", "u", "n", "x"}:
        raise ReservationProviderError("Phase lease metadata is incomplete; no ownership assumed.")
    try:
        result = {
            "repository_key": fields["r"], "goal": int(fields["g"]), "phase": _reservation_actor(fields["p"], "phase", 24),
            "revision": int(fields["v"]), "owner": _reservation_actor(fields["o"], "owner", 20),
            "run_id": _reservation_actor(fields["u"], "run-id", 32), "generation": int(fields["n"]), "expires_at": int(fields["x"]),
        }
        if result["goal"] < 1 or result["revision"] < 1 or result["generation"] < 1 or result["expires_at"] < 0:
            raise ValueError("invalid phase lease fields")
        return result
    except ValueError as exc:
        raise ReservationProviderError("Phase lease metadata is invalid; no ownership assumed.") from exc


def acquire_phase_lease(
    adapter: Any, repository: str, goal: int, phase: str, revision: int, owner: str, run_id: str,
    ttl_seconds: int = 900, now: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 60 <= ttl_seconds <= 86400:
        raise ValueError("ttl-seconds must be from 60 to 86400")
    _validate_reservation_goal(adapter, repository, goal, revision, require_writable=True)
    now_epoch = int((now or datetime.now(timezone.utc)).timestamp())
    name = phase_lease_label_name(goal, phase)
    existing = adapter.get_label(name)
    generation = 1
    if existing is not None:
        current = parse_phase_lease_description(existing.get("description"))
        if current["repository_key"] != reservation_repository_key(repository) or current["goal"] != goal or current["phase"] != phase:
            raise ReservationProviderError("Phase lease identity is invalid; no ownership assumed.")
        if current["expires_at"] > now_epoch:
            return {"acquired": False, "outcome": "contended", "goal": goal, "phase": phase,
                    "holder": {key: current[key] for key in ("owner", "run_id", "generation", "expires_at")}}
        return {"acquired": False, "outcome": "recovery_required", "goal": goal, "phase": phase,
                "holder": {key: current[key] for key in ("owner", "run_id", "generation", "expires_at")}}
    description = phase_lease_description(repository, goal, phase, revision, owner, run_id, now_epoch + ttl_seconds, generation)
    created = adapter.create_label(name, description)
    if created is None:
        confirmed = adapter.get_label(name)
        if confirmed is None or confirmed.get("description") != description:
            return {"acquired": False, "outcome": "contended", "goal": goal, "phase": phase}
        created = confirmed
    if created.get("description") != description or not created.get("node_id"):
        raise ReservationProviderError("GitHub did not confirm phase lease ownership; no ownership assumed.")
    return {"acquired": True, "outcome": "acquired", "goal": goal, "phase": phase, "generation": generation,
            "expires_at": now_epoch + ttl_seconds}


def recover_phase_lease(
    adapter: Any, repository: str, goal: int, phase: str, revision: int,
    observed_owner: str, observed_run_id: str, observed_generation: int,
    replacement_owner: str, replacement_run_id: str, worker_stopped: bool,
    ttl_seconds: int = 900, now: datetime | None = None,
) -> dict[str, Any]:
    """Replace an expired lease after its exact owner is confirmed stopped."""
    if worker_stopped is not True:
        return {"acquired": False, "outcome": "worker_not_confirmed_stopped", "goal": goal, "phase": phase}
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 60 <= ttl_seconds <= 86400:
        raise ValueError("ttl-seconds must be from 60 to 86400")
    _validate_reservation_goal(adapter, repository, goal, revision, require_writable=True)
    now_epoch = int((now or datetime.now(timezone.utc)).timestamp())
    name = phase_lease_label_name(goal, phase)
    existing = adapter.get_label(name)
    if existing is None:
        return {"acquired": False, "outcome": "missing", "goal": goal, "phase": phase}
    current = parse_phase_lease_description(existing.get("description"))
    if (current["repository_key"] != reservation_repository_key(repository) or current["goal"] != goal
            or current["phase"] != phase):
        raise ReservationProviderError("Phase lease identity is invalid; no ownership assumed.")
    if (current["owner"] != observed_owner or current["run_id"] != observed_run_id
            or current["generation"] != observed_generation):
        return {"acquired": False, "outcome": "observation_stale", "goal": goal, "phase": phase}
    if current["expires_at"] > now_epoch:
        return {"acquired": False, "outcome": "not_expired", "goal": goal, "phase": phase}

    try:
        adapter.delete_label(existing["node_id"])
    except ReservationProviderError:
        # A lost delete response is safe to continue only when the exact label is
        # observably absent. A replacement at the same name must be preserved.
        confirmed = adapter.get_label(name)
        if confirmed is not None:
            return {"acquired": False, "outcome": "replacement_detected", "goal": goal, "phase": phase}
    confirmed = adapter.get_label(name)
    if confirmed is not None:
        return {"acquired": False, "outcome": "replacement_detected", "goal": goal, "phase": phase}

    generation = observed_generation + 1
    description = phase_lease_description(
        repository, goal, phase, revision, replacement_owner, replacement_run_id,
        now_epoch + ttl_seconds, generation,
    )
    created = adapter.create_label(name, description)
    if created is None:
        confirmed = adapter.get_label(name)
        if confirmed is None or confirmed.get("description") != description:
            return {"acquired": False, "outcome": "contended", "goal": goal, "phase": phase}
        created = confirmed
    if created.get("description") != description or not created.get("node_id"):
        raise ReservationProviderError("GitHub did not confirm recovered phase lease ownership; no ownership assumed.")
    return {"acquired": True, "outcome": "recovered", "goal": goal, "phase": phase,
            "generation": generation, "expires_at": now_epoch + ttl_seconds}


def renew_phase_lease(adapter: Any, repository: str, goal: int, phase: str, revision: int, owner: str, run_id: str, generation: int, ttl_seconds: int = 900, now: datetime | None = None) -> dict[str, Any]:
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 60 <= ttl_seconds <= 86400:
        raise ValueError("ttl-seconds must be from 60 to 86400")
    _validate_reservation_goal(adapter, repository, goal, revision, require_writable=True)
    existing = adapter.get_label(phase_lease_label_name(goal, phase))
    if existing is None:
        return {"acquired": False, "outcome": "missing", "goal": goal, "phase": phase}
    current = parse_phase_lease_description(existing.get("description"))
    if (current["repository_key"] != reservation_repository_key(repository) or current["goal"] != goal
            or current["phase"] != phase or current["owner"] != owner or current["run_id"] != run_id
            or current["generation"] != generation):
        return {"acquired": False, "outcome": "not_owned", "goal": goal, "phase": phase}
    now_epoch = int((now or datetime.now(timezone.utc)).timestamp())
    description = phase_lease_description(repository, goal, phase, revision, owner, run_id, now_epoch + ttl_seconds, generation)
    adapter.update_label(existing["node_id"], description)
    confirmed = adapter.get_label(phase_lease_label_name(goal, phase))
    if confirmed is None or confirmed.get("node_id") != existing["node_id"] or confirmed.get("description") != description:
        raise ReservationProviderError("GitHub did not confirm phase lease renewal; no ownership assumed.")
    return {"acquired": True, "outcome": "renewed", "goal": goal, "phase": phase, "generation": generation, "expires_at": now_epoch + ttl_seconds}


def release_phase_lease(adapter: Any, repository: str, goal: int, phase: str, revision: int, owner: str, run_id: str, generation: int) -> dict[str, Any]:
    _validate_reservation_goal(adapter, repository, goal, revision)
    existing = adapter.get_label(phase_lease_label_name(goal, phase))
    if existing is None:
        return {"released": True, "outcome": "already_released", "goal": goal, "phase": phase}
    current = parse_phase_lease_description(existing.get("description"))
    if (current["repository_key"] != reservation_repository_key(repository) or current["goal"] != goal or current["phase"] != phase
            or current["owner"] != owner or current["run_id"] != run_id or current["generation"] != generation):
        return {"released": False, "outcome": "not_owned", "goal": goal, "phase": phase}
    adapter.delete_label(existing["node_id"])
    if adapter.get_label(phase_lease_label_name(goal, phase)) is not None:
        raise ReservationProviderError("GitHub did not confirm phase lease release; no ownership assumed.")
    return {"released": True, "outcome": "released", "goal": goal, "phase": phase}


class PhaseLeaseHeartbeat:
    """Renew one local worker lease while its local liveness probe remains true."""

    def __init__(self, renew: Callable[[], dict[str, Any]], alive: Callable[[], bool]):
        self._renew = renew
        self._alive = alive
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.result: dict[str, Any] | None = None

    def tick(self) -> dict[str, Any]:
        if self._stop.is_set():
            self.result = {"outcome": "stopped"}
        elif not self._alive():
            self.result = {"outcome": "worker_not_live"}
        else:
            try:
                result = self._renew()
                self.result = result if result.get("acquired") is True else {"outcome": "uncertain", "result": result}
            except ReservationProviderError as exc:
                self.result = {"outcome": "uncertain", "detail": str(exc)}
        return self.result

    def stop(self) -> None:
        self._stop.set()

    def start(self, interval_seconds: float) -> None:
        if interval_seconds <= 0:
            raise ValueError("heartbeat interval must be positive")
        if self._thread is not None and self._thread.is_alive():
            raise ValueError("heartbeat is already running")
        def run() -> None:
            while not self._stop.wait(interval_seconds):
                outcome = self.tick()
                if outcome.get("outcome") in {"worker_not_live", "uncertain"}:
                    return
        self._thread = threading.Thread(target=run, name="zzzops-phase-lease-heartbeat", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)
