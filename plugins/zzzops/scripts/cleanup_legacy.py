#!/usr/bin/env python3
"""Safely remove retired per-project ZzzOps installations."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = PLUGIN_ROOT / "assets" / "legacy_install_fingerprints.json"
LOCK_RELATIVE = ".zzzops/ZZZOPS_LOCK.json"
MANIFEST_RELATIVE = ".agents/zzzops/INSTALL_MANIFEST"
ROOT_IGNORE_START = "# BEGIN ZZZOPS DISPOSABLE MACHINERY"
ROOT_IGNORE_END = "# END ZZZOPS DISPOSABLE MACHINERY"
STATE_IGNORE_START = "# BEGIN ZZZOPS LOCAL STATE"
STATE_IGNORE_END = "# END ZZZOPS LOCAL STATE"
LEGACY_SKILLS = (
    "add-zzzops-goal",
    "execute-zzzops",
    "migrate-to-zzzops",
    "review-zzzops-policy",
    "send-zzzops-feedback",
    "suggest-zzzops-work",
)
LEGACY_ROOTS = (
    ".agents/zzzops",
    *(f".agents/skills/{name}" for name in LEGACY_SKILLS),
    *(f".claude/skills/{name}" for name in LEGACY_SKILLS),
    ".zzzops/rules",
)
CATALOG_ANCHOR = ".agents/zzzops/zzzops.py"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40,64}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_PORTABLE_PART = re.compile(r"^[A-Za-z0-9._-]+$")


class CleanupError(ValueError):
    """Legacy ownership cannot be proved safely."""


@dataclass
class CleanupPlan:
    safe: bool
    source: str | None
    remove_files: list[str]
    tracked: list[str]
    ignore_updates: dict[str, str | None]
    errors: list[str]
    warnings: list[str]
    signature: str
    catalog: dict[str, Any] = field(repr=False)


def file_digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def file_digest(path: Path) -> str:
    return file_digest_bytes(path.read_bytes())


def lock_file_digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.lower() in {".json", ".md", ".py", ".yaml", ".yml"} or path.name == "ZZZOPS_GITIGNORE":
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def safe_relative(value: Any, *, metadata: bool = False) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise CleanupError(f"unsafe managed path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(part in {"", ".", ".."} for part in path.parts):
        raise CleanupError(f"unsafe managed path: {value}")
    if any(not _PORTABLE_PART.fullmatch(part) for part in path.parts):
        raise CleanupError(f"unsafe non-portable managed path: {value}")
    if not metadata and not any(value == root or value.startswith(root + "/") for root in LEGACY_ROOTS):
        if value != ".zzzops/.gitignore":
            raise CleanupError(f"unsafe path outside retired ZzzOps roots: {value}")
    return value


def validate_files(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict) or not raw:
        raise CleanupError("fingerprint files must be a non-empty object")
    result: dict[str, str] = {}
    portable: set[str] = set()
    for raw_path, digest in raw.items():
        path = safe_relative(raw_path)
        folded = path.casefold()
        if folded in portable:
            raise CleanupError(f"duplicate cross-platform managed path: {path}")
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            raise CleanupError(f"invalid SHA-256 digest for {path}")
        portable.add(folded)
        result[path] = digest
    return dict(sorted(result.items()))


def validate_catalog(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "releases"}:
        raise CleanupError("fingerprint catalog must contain only schema_version and releases")
    if raw["schema_version"] != 1 or not isinstance(raw["releases"], dict) or not raw["releases"]:
        raise CleanupError("fingerprint catalog schema or releases are invalid")
    releases: dict[str, Any] = {}
    for name, release in raw["releases"].items():
        if not isinstance(name, str) or not name or not isinstance(release, dict) or set(release) != {"files"}:
            raise CleanupError("fingerprint release entries are invalid")
        releases[name] = {"files": validate_files(release["files"])}
    return {"schema_version": 1, "releases": dict(sorted(releases.items()))}


def load_catalog(path: Path = DEFAULT_CATALOG) -> dict[str, Any]:
    try:
        return validate_catalog(json.loads(path.read_text(encoding="utf-8-sig")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CleanupError(f"could not read the fingerprint catalog: {type(exc).__name__}") from exc


def target_path(repo: Path, relative: str) -> Path:
    current = repo
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise CleanupError(f"managed path uses a symlink or junction: {relative}")
    return current


def legacy_inventory(repo: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for root in LEGACY_ROOTS:
        directory = target_path(repo, root)
        if not directory.exists():
            continue
        if not directory.is_dir():
            raise CleanupError(f"retired machinery root is not a directory: {root}")
        for item in directory.rglob("*"):
            relative = item.relative_to(repo).as_posix()
            if item.is_symlink():
                raise CleanupError(f"managed path uses a symlink or junction: {relative}")
            if item.is_file():
                result[relative] = file_digest(item)
    return dict(sorted(result.items()))


def parse_lock(repo: Path) -> tuple[dict[str, str] | None, str | None]:
    path = target_path(repo, LOCK_RELATIVE)
    if not path.exists():
        return None, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"installation lock is unreadable: {type(exc).__name__}"
    if not isinstance(raw, dict) or raw.get("schema_version") != 1 or set(raw) != {"schema_version", "revision", "version", "files"}:
        return None, "installation lock schema is invalid"
    if not isinstance(raw["revision"], str) or not _REVISION.fullmatch(raw["revision"]):
        return None, "installation lock revision is invalid"
    if not isinstance(raw["version"], str) or not _VERSION.fullmatch(raw["version"]):
        return None, "installation lock version is invalid"
    try:
        return validate_files(raw.get("files")), None
    except CleanupError as exc:
        return None, f"installation lock is invalid: {exc}"


def manifest_digest(data: bytes, expected: str) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    constructor = hashlib.sha1 if len(expected) == 40 else hashlib.sha256
    return constructor(header + data).hexdigest()


def parse_manifest(repo: Path) -> tuple[dict[str, str] | None, str | None]:
    path = target_path(repo, MANIFEST_RELATIVE)
    if not path.exists():
        return None, None
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        return None, f"legacy manifest is unreadable: {type(exc).__name__}"
    if not lines or lines[0] != "zzzops-install-manifest-v1":
        return None, "legacy manifest header is invalid"
    files: dict[str, str] = {}
    revision = None
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) == 2 and fields[0] == "revision" and revision is None:
            revision = fields[1]
        elif len(fields) == 2 and fields[0] == "version":
            continue
        elif len(fields) == 3 and fields[0] == "file" and len(fields[1]) in {40, 64}:
            try:
                relative = safe_relative(fields[2])
            except CleanupError as exc:
                return None, f"legacy manifest is invalid: {exc}"
            if relative == ".zzzops/.gitignore" or relative in files:
                return None, f"legacy manifest contains unsupported or duplicate path: {relative}"
            files[relative] = fields[1].lower()
        else:
            return None, "legacy manifest contains an invalid record"
    if not revision or not files:
        return None, "legacy manifest lacks provenance or files"
    return dict(sorted(files.items())), None


def strip_block(text: str, start: str, end: str) -> tuple[str, bool]:
    normalized = text.replace("\r\n", "\n")
    before, marker, remainder = normalized.partition(start)
    if not marker:
        if end in normalized:
            raise CleanupError(f"ignore file contains {end} without {start}")
        return normalized, False
    discarded, closing, after = remainder.partition(end)
    if not closing or start in after or end in after:
        raise CleanupError(f"ignore file contains malformed or repeated {start} block")
    del discarded
    kept = before.rstrip("\n")
    suffix = after.lstrip("\n")
    result = (kept + "\n" if kept else "") + suffix
    return result, True


def ignore_updates(repo: Path) -> dict[str, str | None]:
    updates: dict[str, str | None] = {}
    for relative, start, end in (
        (".gitignore", ROOT_IGNORE_START, ROOT_IGNORE_END),
        (".zzzops/.gitignore", STATE_IGNORE_START, STATE_IGNORE_END),
    ):
        path = target_path(repo, relative)
        if not path.exists():
            continue
        try:
            current = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise CleanupError(f"could not read {relative}: {type(exc).__name__}") from exc
        updated, changed = strip_block(current, start, end)
        if changed:
            updates[relative] = updated or None
    return updates


def git_paths(repo: Path, files: list[str]) -> list[str]:
    if not files:
        return []
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo}", "-C", str(repo), "ls-files", "-z", "--", *files],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise CleanupError("Git could not report tracked cleanup paths")
    return sorted(path for path in result.stdout.decode("utf-8", errors="replace").split("\0") if path)


def snapshot_signature(repo: Path, inventory: dict[str, str], updates: dict[str, str | None]) -> str:
    metadata: dict[str, str | None] = {}
    for relative in (LOCK_RELATIVE, MANIFEST_RELATIVE, ".gitignore", ".zzzops/.gitignore"):
        path = target_path(repo, relative)
        metadata[relative] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return hashlib.sha256(json.dumps({"inventory": inventory, "metadata": metadata, "updates": updates}, sort_keys=True).encode()).hexdigest()


def build_plan(repo: Path, catalog: dict[str, Any] | None = None) -> CleanupPlan:
    repo = repo.resolve()
    validated = validate_catalog(catalog) if catalog is not None else load_catalog()
    errors: list[str] = []
    warnings: list[str] = []
    remove: list[str] = []
    source: str | None = None
    updates: dict[str, str | None] = {}
    inventory: dict[str, str] = {}
    try:
        inventory = legacy_inventory(repo)
        updates = ignore_updates(repo)
        lock, lock_error = parse_lock(repo)
        manifest, manifest_error = parse_manifest(repo)
        if lock_error:
            errors.append(lock_error)
        elif lock is not None:
            source = "installation lock"
            actual = {path: digest for path, digest in inventory.items() if path != MANIFEST_RELATIVE}
            unknown = sorted(set(actual) - set(lock))
            mismatched = sorted(
                path for path in set(actual) & set(lock)
                if lock_file_digest(target_path(repo, path)) != lock[path]
            )
            if unknown or mismatched:
                errors.append("installed machinery does not match the installation lock: " + ", ".join(unknown + mismatched))
            else:
                remove = sorted(actual)
                if target_path(repo, LOCK_RELATIVE).is_file():
                    remove.append(LOCK_RELATIVE)
        elif manifest_error:
            errors.append(manifest_error)
        elif manifest is not None:
            source = "legacy install manifest"
            actual = {path: digest for path, digest in inventory.items() if path != MANIFEST_RELATIVE}
            unknown = sorted(set(actual) - set(manifest))
            mismatched: list[str] = []
            for relative, expected in manifest.items():
                path = target_path(repo, relative)
                if path.is_file() and manifest_digest(path.read_bytes(), expected) != expected:
                    mismatched.append(relative)
            if unknown or mismatched:
                errors.append("installed machinery does not match the legacy manifest: " + ", ".join(unknown + mismatched))
            else:
                remove = sorted(actual) + [MANIFEST_RELATIVE]
        elif inventory:
            matches: list[tuple[str, dict[str, str]]] = []
            for name, release in validated["releases"].items():
                expected = release["files"]
                if CATALOG_ANCHOR not in inventory or inventory.get(CATALOG_ANCHOR) != expected.get(CATALOG_ANCHOR):
                    continue
                unknown = set(inventory) - set(expected)
                mismatched = [path for path in set(inventory) & set(expected) if inventory[path] != expected[path]]
                if not unknown and not mismatched:
                    matches.append((name, expected))
            if len(matches) != 1:
                errors.append("installed machinery does not match exactly one approved legacy release fingerprint")
            else:
                source = f"published {matches[0][0]} fingerprint"
                remove = sorted(inventory)
                extra_metadata = ".zzzops/.gitignore"
                expected = matches[0][1]
                metadata_path = target_path(repo, extra_metadata)
                if extra_metadata in expected:
                    if not metadata_path.is_file() or file_digest(metadata_path) != expected[extra_metadata]:
                        errors.append(f"installed machinery does not match {matches[0][0]} at {extra_metadata}")
                    else:
                        remove.append(extra_metadata)
        elif target_path(repo, LOCK_RELATIVE).exists() or target_path(repo, MANIFEST_RELATIVE).exists():
            errors.append("provenance metadata exists without matching retired machinery")
        if errors:
            remove = []
            updates = {}
        tracked = git_paths(repo, sorted(set(remove) | set(updates))) if not errors else []
        if tracked:
            warnings.append("Git-tracked paths will remain in the index as deletions; the cleaner never changes the index")
        signature = snapshot_signature(repo, inventory, updates)
    except (CleanupError, OSError) as exc:
        errors.append(str(exc))
        remove = []
        updates = {}
        tracked = []
        signature = ""
    return CleanupPlan(not errors, source, sorted(set(remove)), tracked, updates, errors, warnings, signature, validated)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".zzzops-cleanup-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def apply_plan(repo: Path, plan: CleanupPlan) -> None:
    repo = repo.resolve()
    current = build_plan(repo, plan.catalog)
    if not current.safe or current.signature != plan.signature or current.remove_files != plan.remove_files or current.ignore_updates != plan.ignore_updates:
        raise CleanupError("the target changed after preview; no cleanup was started")
    protected = None
    if plan.source == "installation lock":
        protected = LOCK_RELATIVE
    elif plan.source == "legacy install manifest":
        protected = MANIFEST_RELATIVE
    elif CATALOG_ANCHOR in plan.remove_files:
        protected = CATALOG_ANCHOR
    ordered = [path for path in plan.remove_files if path != protected]
    for relative in ordered:
        path = target_path(repo, relative)
        if not path.is_file():
            raise CleanupError(f"planned file changed during cleanup: {relative}")
        path.unlink()
    for relative, updated in plan.ignore_updates.items():
        path = target_path(repo, relative)
        if not path.is_file():
            raise CleanupError(f"planned ignore file changed during cleanup: {relative}")
        if updated is None:
            path.unlink()
        else:
            atomic_write(path, updated)
    if protected:
        path = target_path(repo, protected)
        if not path.is_file():
            raise CleanupError(f"ownership proof changed during cleanup: {protected}")
        path.unlink()
    directories: set[Path] = set()
    for relative in plan.remove_files:
        for root in LEGACY_ROOTS:
            if relative == root or relative.startswith(root + "/"):
                root_path = target_path(repo, root)
                current_path = target_path(repo, relative).parent
                while current_path != root_path.parent:
                    directories.add(current_path)
                    current_path = current_path.parent
                break
    for directory in sorted(directories, key=lambda value: len(value.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass


def print_plan(repo: Path, plan: CleanupPlan) -> None:
    print("ZzzOps legacy cleanup preview")
    print(f"Target: {repo}")
    if plan.source:
        print(f"Ownership proof: {plan.source}.")
    print(f"Files to remove: {len(plan.remove_files)}; ignore files to update: {len(plan.ignore_updates)}.")
    for relative in plan.remove_files:
        print(f"- remove {relative}")
    for relative in plan.ignore_updates:
        print(f"- remove ZzzOps-owned marker block from {relative}")
    if plan.tracked:
        print("Tracked paths (the Git index will not be changed):")
        for relative in plan.tracked:
            print(f"- {relative}")
    for warning in plan.warnings:
        print(f"Warning: {warning}")
    for error in plan.errors:
        print(f"Blocked: {error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove a proven retired per-project ZzzOps installation")
    parser.add_argument("target", nargs="?", default=".")
    parser.add_argument("--apply", action="store_true", help="apply the previewed cleanup")
    parser.add_argument("--yes", action="store_true", help="confirm non-interactively; requires --apply")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    repo = Path(args.target).resolve()
    if not repo.is_dir() or not (repo / ".git").exists():
        print("Blocked: target must be a Git working tree")
        return 2
    try:
        plan = build_plan(repo)
        print_plan(repo, plan)
        if not plan.safe:
            print("No files or Git index entries were changed.")
            return 2
        if not args.apply:
            print("Dry run only. Re-run with --apply after reviewing this exact preview.")
            return 0
        if not args.yes:
            try:
                answer = input("Type 'remove legacy ZzzOps' to confirm: ")
            except EOFError:
                answer = ""
            if answer != "remove legacy ZzzOps":
                print("Cleanup cancelled; no files or Git index entries were changed.")
                return 0
        apply_plan(repo, plan)
        print("Legacy ZzzOps project machinery was removed. Durable .zzzops state and the Git index were preserved.")
        return 0
    except (CleanupError, OSError) as exc:
        print(f"Cleanup stopped: {exc}")
        print("Current remaining work:")
        try:
            print_plan(repo, build_plan(repo))
        except (CleanupError, OSError) as remaining_error:
            print(f"Blocked: {remaining_error}")
        print("Any already removed proven files are safe to leave absent; resolve a reported blocker, then rerun.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
