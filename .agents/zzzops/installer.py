#!/usr/bin/env python3
"""Cross-platform implementation for the native ZzzOps installer wrappers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

from install_lock import InstallLockError, LOCK_RELATIVE, read_install_lock, validate_install_lock


SOURCE_ROOT = Path(__file__).resolve().parents[2]
TARGET_SKILLS = (
    "add-zzzops-goal",
    "execute-zzzops",
    "migrate-to-zzzops",
    "review-zzzops-policy",
    "send-zzzops-feedback",
    "suggest-zzzops-work",
)
ROOT_IGNORE_START = "# BEGIN ZZZOPS DISPOSABLE MACHINERY"
ROOT_IGNORE_END = "# END ZZZOPS DISPOSABLE MACHINERY"
STATE_IGNORE_START = "# BEGIN ZZZOPS LOCAL STATE"
STATE_IGNORE_END = "# END ZZZOPS LOCAL STATE"
LEGACY_STATE_IGNORES = {
    "init/plan.json",
    "init/*.tmp",
    "migration/plan.json",
    "migration/SUMMARY.md",
    "migration/*.tmp",
    "execution-reports/",
}


class InstallError(RuntimeError):
    """The requested installation cannot proceed safely."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str, cwd: Path = SOURCE_ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={cwd}", "-C", str(cwd), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        raise InstallError(f"Git could not {' '.join(args)}: {result.stderr.strip() or result.stdout.strip()}")
    return result


def source_provenance() -> tuple[str, str]:
    revision = git("rev-parse", "HEAD").stdout.strip()
    version = git("-c", "core.excludesFile=/dev/null", "describe", "--tags", "--always", "--long", "--dirty").stdout.strip()
    try:
        validate_install_lock({"schema_version": 1, "revision": revision, "version": version, "files": {".agents/zzzops/probe": "0" * 64}})
    except InstallLockError as exc:
        raise InstallError(f"Source provenance is invalid: {exc}") from exc
    return revision, version


def included(path: Path) -> bool:
    return (
        path.is_file()
        and "__pycache__" not in path.parts
        and not path.name.startswith("test_")
        and path.suffix not in {".pyc", ".pyo"}
        and path.name != ".gitignore"
    )


def add_tree(result: dict[str, Path], source_root: Path, target_root: str) -> None:
    for source in sorted(source_root.rglob("*")):
        if included(source):
            suffix = source.relative_to(source_root).as_posix()
            result[f"{target_root}/{suffix}"] = source


def distribution_sources() -> dict[str, Path]:
    """Return the one canonical source-to-materialized-path contract."""
    result: dict[str, Path] = {}
    add_tree(result, SOURCE_ROOT / ".agents" / "zzzops", ".agents/zzzops")
    add_tree(result, SOURCE_ROOT / ".zzzops" / "rules", ".zzzops/rules")
    for name in TARGET_SKILLS:
        source = SOURCE_ROOT / ".agents" / "skills" / name
        add_tree(result, source, f".agents/skills/{name}")
        add_tree(result, source, f".claude/skills/{name}")
    result[".agents/zzzops/LICENSE"] = SOURCE_ROOT / "LICENSE"
    missing = [relative for relative, source in result.items() if not source.is_file()]
    if missing:
        raise InstallError("Source machinery is incomplete: " + ", ".join(missing))
    return dict(sorted(result.items()))


def distribution_lock(sources: dict[str, Path]) -> dict[str, object]:
    revision, version = source_provenance()
    return validate_install_lock({
        "schema_version": 1,
        "revision": revision,
        "version": version,
        "files": {relative: sha256(source) for relative, source in sources.items()},
    })


def managed_roots(paths: object) -> tuple[str, ...]:
    roots: set[str] = set()
    for relative in paths:
        parts = PurePosixPath(str(relative)).parts
        if parts[:2] == (".agents", "zzzops"):
            roots.add(".agents/zzzops")
        elif len(parts) >= 3 and parts[:2] in {(".agents", "skills"), (".claude", "skills")}:
            roots.add("/".join(parts[:3]))
        elif parts[:2] == (".zzzops", "rules"):
            roots.add(".zzzops/rules")
        else:
            raise InstallError(f"Lock path has no disposable root: {relative}")
    return tuple(sorted(roots))


def safe_target_path(target: Path, relative: str) -> Path:
    current = target
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise InstallError(f"A managed path uses a symlink or junction: {relative}")
    return current


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeError) as exc:
        raise InstallError(f"Could not read {path}: {type(exc).__name__}") from exc


def managed_block(existing: str, start: str, end: str, lines: list[str], legacy: set[str] | None = None) -> str:
    source = existing.replace("\r\n", "\n")
    before, marker, remainder = source.partition(start)
    if marker:
        _discarded, closing, after = remainder.partition(end)
        if not closing:
            raise InstallError(f"Ignore file contains {start} without {end}")
        source = before.rstrip("\n") + "\n" + after.lstrip("\n")
    kept = [line for line in source.splitlines() if not legacy or line not in legacy]
    base = "\n".join(kept).rstrip()
    block = "\n".join((start, *lines, end))
    return (base + "\n\n" if base else "") + block + "\n"


def expected_ignore_texts(target: Path, roots: tuple[str, ...]) -> tuple[str, str]:
    root_lines = [f"/{root}/" for root in roots]
    root_ignore = managed_block(read_text(target / ".gitignore"), ROOT_IGNORE_START, ROOT_IGNORE_END, root_lines)
    state_lines = ["init/", "migration/plan.json", "migration/SUMMARY.md", "migration/*.tmp", "execution-reports/"]
    state_ignore = managed_block(
        read_text(target / ".zzzops" / ".gitignore"),
        STATE_IGNORE_START,
        STATE_IGNORE_END,
        state_lines,
        LEGACY_STATE_IGNORES,
    )
    return root_ignore, state_ignore


def target_inventory(target: Path, roots: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for root in roots:
        path = safe_target_path(target, root)
        if not path.exists():
            continue
        if not path.is_dir():
            result[root] = "not-a-directory"
            continue
        for item in path.rglob("*"):
            relative = item.relative_to(target).as_posix()
            if item.is_symlink():
                result[relative] = "symlink"
            elif item.is_file() and "__pycache__" not in item.parts and item.suffix not in {".pyc", ".pyo"}:
                result[relative] = sha256(item)
    return dict(sorted(result.items()))


def lock_text(lock: dict[str, object]) -> str:
    return json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def read_old_lock(target: Path) -> tuple[dict[str, object] | None, str | None]:
    try:
        return read_install_lock(target), None
    except InstallLockError as exc:
        if not (target / LOCK_RELATIVE).exists():
            return None, None
        return None, str(exc)


def installation_state(target: Path, lock: dict[str, object]) -> dict[str, object]:
    old_lock, old_warning = read_old_lock(target)
    current_roots = managed_roots(lock["files"])
    old_roots = managed_roots(old_lock["files"]) if old_lock else ()
    roots = tuple(sorted(set(current_roots) | set(old_roots)))
    inventory = target_inventory(target, roots)
    root_ignore, state_ignore = expected_ignore_texts(target, current_roots)
    expected = lock["files"]
    matching = inventory == expected
    same_lock = old_lock == lock
    ignores_match = read_text(target / ".gitignore").replace("\r\n", "\n") == root_ignore
    state_ignores_match = read_text(target / ".zzzops" / ".gitignore").replace("\r\n", "\n") == state_ignore
    if old_lock is None and not inventory:
        kind = "fresh install"
    elif old_lock and old_lock.get("revision") != lock.get("revision"):
        kind = "upgrade"
    elif matching and same_lock and ignores_match and state_ignores_match:
        kind = "reinstall"
    else:
        kind = "repair"
    signature = hashlib.sha256(json.dumps({
        "inventory": inventory,
        "old_lock": old_lock,
        "old_lock_bytes": read_text(target / LOCK_RELATIVE),
        "root_ignore": read_text(target / ".gitignore"),
        "state_ignore": read_text(target / ".zzzops" / ".gitignore"),
    }, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "kind": kind,
        "roots": roots,
        "current_roots": current_roots,
        "old_warning": old_warning,
        "root_ignore": root_ignore,
        "state_ignore": state_ignore,
        "signature": signature,
    }


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".zzzops-install-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def apply_install(target: Path, sources: dict[str, Path], lock: dict[str, object], state: dict[str, object]) -> None:
    if installation_state(target, lock)["signature"] != state["signature"]:
        raise InstallError("The target changed after the preview. Run the installer again; no files were changed.")
    for root in state["roots"]:
        path = safe_target_path(target, str(root))
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    for relative, source in sources.items():
        destination = safe_target_path(target, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    actual = target_inventory(target, tuple(state["current_roots"]))
    if actual != lock["files"]:
        mismatches = sorted(set(actual) ^ set(lock["files"]))
        mismatches.extend(path for path in set(actual) & set(lock["files"]) if actual[path] != lock["files"][path])
        raise InstallError("Fresh machinery validation failed: " + ", ".join(sorted(set(mismatches))))
    atomic_write(target / ".gitignore", str(state["root_ignore"]).encode("utf-8"))
    atomic_write(target / ".zzzops" / ".gitignore", str(state["state_ignore"]).encode("utf-8"))
    atomic_write(target / LOCK_RELATIVE, lock_text(lock).encode("utf-8"))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install disposable ZzzOps machinery")
    parser.add_argument("target")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--overwrite-mechanical", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    target = Path(args.target).resolve()
    try:
        if not target.is_dir():
            raise InstallError("Target is not a directory")
        if not (target / ".git").exists():
            raise InstallError("Target has no .git entry")
        sources = distribution_sources()
        lock = distribution_lock(sources)
        state = installation_state(target, lock)
        print("ZzzOps installation preview")
        print(f"Target: {target}")
        print(f"Operation: {state['kind']}.")
        print(f"Disposable machinery roots: {len(state['current_roots'])}; managed files: {len(sources)}.")
        print("The confirmed install will wipe and recreate only those roots, validate every file, update scoped ignore entries, then write .zzzops/ZZZOPS_LOCK.json.")
        print("Local workflow scratch under .zzzops/init/ will be ignored but preserved.")
        if state["old_warning"]:
            print(f"Warning: the previous lock is invalid ({state['old_warning']}); current owned roots will still be reconstructed, but unknown obsolete paths cannot be inferred.")
        if args.dry_run:
            print("No files or Git index entries were changed.")
            return 0
        if not args.yes:
            try:
                answer = input(f"Confirm {state['kind']}? [y/N] ")
            except EOFError:
                answer = ""
            if answer.strip().casefold() not in {"y", "yes"}:
                print("Installation cancelled; no files or Git index entries were changed.")
                return 0
        apply_install(target, sources, lock, state)
        print("ZzzOps machinery was reconstructed and validated.")
        print("Commit .zzzops/ZZZOPS_LOCK.json and the scoped ignore-file changes; keep the installed machinery local.")
        print("Open the target repository in Codex or Claude Code; restart or reopen the harness if the new skills are not discovered.")
        return 0
    except InstallError as exc:
        print(f"Cannot install yet: {exc}")
        return 2
    except (OSError, shutil.Error) as exc:
        print(f"Installation stopped with disposable machinery possibly incomplete: {type(exc).__name__}: {exc}")
        print("Rerun the regular installer to reconstruct it.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
