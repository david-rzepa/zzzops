"""Privacy-safe local timing diagnostics."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any, Callable, Iterator


SCHEMA_VERSION = 1
DIRECTORY_RELATIVE = "zzzops/timing-diagnostics"
MAX_RECORDS = 32
MAX_DURATION_MS = 86_400_000
MAX_TOTAL_MS = MAX_DURATION_MS * 1_000_000
PHASES = frozenset({
    "startup", "package", "policy_validation", "git_origin", "repository_size",
    "github_discovery", "goal_hydration", "graph_validation", "rendering",
    "tool_wait", "model", "context_compaction",
})
PROVENANCE = frozenset({"measured", "inferred", "unavailable"})
PHASE_FIELDS = {"provenance", "count", "total_ms", "min_ms", "max_ms", "failures"}


class DiagnosticError(ValueError):
    """Timing diagnostic input or durable state is invalid."""


def diagnostic_directory(repo: Path) -> Path:
    """Resolve the ignored diagnostic store in the repository's common Git directory."""
    result = subprocess.run(
        ["git", "-C", str(repo.resolve()), "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode or not result.stdout.strip():
        raise DiagnosticError("target must be a Git working tree")
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = repo.resolve() / common
    common = common.resolve()
    if not common.is_dir():
        raise DiagnosticError("Git common directory is unavailable")
    return common / DIRECTORY_RELATIVE


def _bounded_duration(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_DURATION_MS


def _bounded_total(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_TOTAL_MS


def validate_diagnostic(value: Any) -> list[str]:
    """Return every structural or privacy-boundary error in a diagnostic artifact."""
    if not isinstance(value, dict):
        return ["diagnostic must be an object"]
    errors: list[str] = []
    if set(value) != {"schema_version", "phases"}:
        errors.append("diagnostic fields must be exactly schema_version and phases")
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    phases = value.get("phases")
    if not isinstance(phases, dict):
        errors.append("phases must be an object")
        return errors
    if not phases:
        errors.append("diagnostic must contain at least one fixed phase")
    for phase, aggregate in phases.items():
        if phase not in PHASES:
            errors.append("diagnostic phase is invalid")
            continue
        if not isinstance(aggregate, dict) or set(aggregate) != PHASE_FIELDS:
            errors.append(f"{phase} fields are invalid")
            continue
        provenance = aggregate.get("provenance")
        count = aggregate.get("count")
        total = aggregate.get("total_ms")
        minimum = aggregate.get("min_ms")
        maximum = aggregate.get("max_ms")
        failures = aggregate.get("failures")
        if provenance not in PROVENANCE:
            errors.append(f"{phase} provenance is invalid")
            continue
        if provenance == "unavailable":
            if (count, total, minimum, maximum, failures) != (0, None, None, None, 0):
                errors.append(f"{phase} unavailable aggregate must not contain measurements")
            continue
        if (
            not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 1_000_000
            or not _bounded_total(total)
            or not _bounded_duration(minimum)
            or not _bounded_duration(maximum)
            or not isinstance(failures, int) or isinstance(failures, bool) or not 0 <= failures <= count
        ):
            errors.append(f"{phase} aggregate contains invalid bounded integers")
            continue
        if minimum > maximum or not count * minimum <= total <= count * maximum:
            errors.append(f"{phase} aggregate totals are inconsistent")
    return errors


class TimingSession:
    """Aggregate fixed timing phases immediately using an injectable monotonic clock."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._phases: dict[str, dict[str, Any]] = {}
        self._active_phase: str | None = None

    def mark(
        self,
        phase: str,
        *,
        provenance: str,
        milliseconds: int | None = None,
        failed: bool = False,
    ) -> None:
        if phase not in PHASES:
            raise DiagnosticError("diagnostic phase is invalid")
        if provenance not in PROVENANCE:
            raise DiagnosticError("diagnostic provenance is invalid")
        if provenance == "unavailable":
            if milliseconds is not None or failed:
                raise DiagnosticError("unavailable phases cannot contain measurements")
            existing = self._phases.get(phase)
            if existing is not None and existing["provenance"] != "unavailable":
                raise DiagnosticError("one phase cannot mix timing provenance")
            self._phases[phase] = {
                "provenance": "unavailable", "count": 0, "total_ms": None,
                "min_ms": None, "max_ms": None, "failures": 0,
            }
            return
        if not _bounded_duration(milliseconds):
            raise DiagnosticError("measured durations must be bounded integer milliseconds")
        existing = self._phases.get(phase)
        if existing is None:
            existing = {
                "provenance": provenance, "count": 0, "total_ms": 0,
                "min_ms": milliseconds, "max_ms": milliseconds, "failures": 0,
            }
            self._phases[phase] = existing
        elif existing["provenance"] != provenance:
            raise DiagnosticError("one phase cannot mix timing provenance")
        existing["count"] += 1
        existing["total_ms"] += milliseconds
        existing["min_ms"] = min(existing["min_ms"], milliseconds)
        existing["max_ms"] = max(existing["max_ms"], milliseconds)
        existing["failures"] += int(failed)

    @contextmanager
    def span(self, phase: str) -> Iterator[None]:
        """Measure one phase and retain its duration even when work raises."""
        if phase not in PHASES:
            raise DiagnosticError("diagnostic phase is invalid")
        if self._active_phase is not None:
            raise DiagnosticError("timing spans cannot overlap or nest")
        started = self._clock()
        self._active_phase = phase
        try:
            try:
                yield
            except BaseException:
                try:
                    self._finish_span(phase, started, failed=True)
                except DiagnosticError:
                    pass
                raise
            else:
                self._finish_span(phase, started, failed=False)
        finally:
            self._active_phase = None

    def _finish_span(self, phase: str, started: float, *, failed: bool) -> None:
        ended = self._clock()
        if not isinstance(started, (int, float)) or not isinstance(ended, (int, float)) or ended < started:
            raise DiagnosticError("monotonic clock returned an invalid interval")
        self.mark(phase, provenance="measured", milliseconds=round((ended - started) * 1000), failed=failed)

    def snapshot(self) -> dict[str, Any]:
        value = {
            "schema_version": SCHEMA_VERSION,
            "phases": json.loads(json.dumps(self._phases, sort_keys=True)),
        }
        errors = validate_diagnostic(value)
        if errors:
            raise DiagnosticError("invalid diagnostic snapshot: " + "; ".join(errors))
        return value


def _diagnostic_id(value: dict[str, Any]) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_diagnostic(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DiagnosticError("stored diagnostic could not be read") from exc
    errors = validate_diagnostic(value)
    if errors:
        raise DiagnosticError("stored diagnostic is invalid: " + "; ".join(errors))
    if path.stem != _diagnostic_id(value):
        raise DiagnosticError("stored diagnostic has an inconsistent fingerprint")
    return value


def _prune(directory: Path) -> int:
    candidates: list[tuple[int, str, Path]] = []
    for path in directory.glob("*.json"):
        try:
            candidates.append((path.stat().st_mtime_ns, path.name, path))
        except FileNotFoundError:
            continue
    removed = 0
    for _mtime, _name, path in sorted(candidates)[:-MAX_RECORDS]:
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            pass
    return removed


def record_diagnostic(repo: Path, value: dict[str, Any]) -> dict[str, Any]:
    """Atomically retain one validated aggregate and prune the bounded local store."""
    errors = validate_diagnostic(value)
    if errors:
        raise DiagnosticError("invalid diagnostic: " + "; ".join(errors))
    identifier = _diagnostic_id(value)
    directory = diagnostic_directory(repo)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{identifier}.json"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".diagnostic-", suffix=".tmp", dir=directory)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
            recorded = True
        except FileExistsError:
            recorded = False
        confirmed = _read_diagnostic(target)
        pruned = _prune(directory)
        return {"recorded": recorded, "id": identifier, "pruned": pruned, "diagnostic": confirmed}
    finally:
        temporary.unlink(missing_ok=True)


def list_diagnostics(repo: Path) -> dict[str, Any]:
    directory = diagnostic_directory(repo)
    items = []
    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            items.append({"id": path.stem, "diagnostic": _read_diagnostic(path)})
    return {"schema_version": SCHEMA_VERSION, "count": len(items), "diagnostics": items}


def purge_diagnostics(repo: Path) -> dict[str, int]:
    """Delete only timing diagnostic JSON artifacts from the exact local store."""
    directory = diagnostic_directory(repo)
    purged = 0
    if directory.exists():
        for path in directory.glob("*.json"):
            try:
                path.unlink()
                purged += 1
            except FileNotFoundError:
                pass
    return {"purged": purged}
