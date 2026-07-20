"""Standalone ZzzOps command-line interface."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

TARGET_SKILLS = ("add-zzzops-goal", "execute-zzzops", "migrate-to-zzzops", "suggest-zzzops-work")
PROJECT_MECHANIC_PROBES = {
    ".agents": (".agents/zzzops.py", ".agents/skills/execute-zzzops/SKILL.md"),
    ".claude": (".claude/skills/execute-zzzops/SKILL.md",),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_root() -> Path:
    return Path(__file__).resolve().parent


def files_to_copy(root: Path) -> list[str]:
    paths = [
        ".zzzops/rules/BACKENDS.md", ".zzzops/rules/BLOCKERS.md",
        ".zzzops/rules/CONTINUATION.md", ".zzzops/rules/EXECUTION_STRATEGY.md", ".zzzops/rules/GOAL_SYSTEM.md",
        ".zzzops/rules/INITIALIZATION.md",
        ".agents/.gitignore", ".agents/zzzops.py",
    ]
    sources = [
        root / ".agents" / "templates" / "project-goals",
        *(root / ".agents" / "skills" / name for name in TARGET_SKILLS),
    ]
    for base in sources:
        paths.extend(
            path.relative_to(root).as_posix()
            for path in base.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and not path.name.startswith("test_")
        )
    return sorted(set(paths))


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def safe_target(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def ignored_project_skill_roots(target: Path) -> tuple[list[str], str | None]:
    ignored: list[str] = []
    try:
        for root, probes in PROJECT_MECHANIC_PROBES.items():
            for probe in probes:
                result = subprocess.run(
                    ["git", "-c", f"safe.directory={target}", "-C", str(target), "check-ignore", "--no-index", "--quiet", "--", probe],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if result.returncode == 0:
                    ignored.append(root)
                    break
                if result.returncode != 1:
                    detail = result.stderr.strip() or result.stdout.strip() or f"git exited {result.returncode}"
                    return ignored, f"Could not verify project mechanic ignore rules: {detail}"
    except FileNotFoundError:
        return ignored, "Could not verify project mechanic ignore rules because Git is unavailable."
    return ignored, None


def collect_actions(root: Path, target: Path, overwrite: bool) -> tuple[list[tuple[str, str, bytes, str | None]], list[str]]:
    errors: list[str] = []
    actions: list[tuple[str, str, bytes, str | None]] = []
    for relative in files_to_copy(root):
        data = (root / relative).read_bytes()
        destination = target / relative
        before = destination.read_bytes() if destination.exists() else None
        if before is None:
            action = "create"
        elif before == data:
            action = "unchanged"
        elif overwrite:
            action = "overwrite"
        else:
            action = "conflict"
            errors.append(f"ZzzOps already manages {relative}, but its contents differ. Review it before using --overwrite-mechanical.")
        actions.append((relative, action, data, digest(before) if before is not None else None))

    for skill_name in TARGET_SKILLS:
        skill_root = root / ".agents" / "skills" / skill_name
        for source in sorted(skill_root.rglob("*")):
            if not source.is_file() or "__pycache__" in source.parts or source.name.startswith("test_"):
                continue
            suffix = source.relative_to(skill_root).as_posix()
            relative = f".claude/skills/{skill_name}/{suffix}"
            data = source.read_bytes()
            destination = target / relative
            before = destination.read_bytes() if destination.exists() else None
            if before is None:
                action = "create"
            elif before == data:
                action = "unchanged"
            elif overwrite:
                action = "overwrite"
            else:
                action = "conflict"
                errors.append(f"ZzzOps already manages {relative}, but its contents differ. Review it before using --overwrite-mechanical.")
            actions.append((relative, action, data, digest(before) if before is not None else None))

    for relative, data in (
        (".claude/.gitignore", (root / ".agents" / ".gitignore").read_bytes()),
        (".zzzops/.gitignore", (root / ".agents" / "templates" / "project-goals" / "ZZZOPS_GITIGNORE").read_bytes()),
    ):
        destination = target / relative
        before = destination.read_bytes() if destination.exists() else None
        if before is None:
            action = "create"
        elif before == data:
            action = "unchanged"
        elif overwrite:
            action = "overwrite"
        else:
            action = "conflict"
            errors.append(f"ZzzOps already manages {relative}, but its contents differ. Review it before using --overwrite-mechanical.")
        actions.append((relative, action, data, digest(before) if before is not None else None))
    return actions, errors


def install(args: argparse.Namespace) -> int:
    root, target = source_root(), args.target.resolve()
    errors: list[str] = []
    if not target.is_dir():
        errors.append("Target is not a directory")
    elif not (target / ".git").exists():
        errors.append("Target has no .git entry")
    try:
        actions, action_errors = collect_actions(root, target, args.overwrite_mechanical)
        errors.extend(action_errors)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Could not prepare installation: {exc}")
        return 2

    ignored_roots, ignore_probe_warning = ignored_project_skill_roots(target) if not errors else ([], None)
    planned_paths = [target / relative for relative, _action, _data, _expected in actions]
    if any(not safe_target(target, path) for path in planned_paths):
        errors.append("A managed path resolves outside the target (symlink/junction)")
    payload = {
        "files": [(path, action, digest(data), expected) for path, action, data, expected in actions],
        "ignored_project_skill_roots": ignored_roots,
        "ignore_probe_warning": ignore_probe_warning,
    }
    fingerprint = digest(json.dumps(payload, sort_keys=True).encode())
    counts: dict[str, int] = {}
    for _path, action, _data, _expected in actions:
        counts[action] = counts.get(action, 0) + 1

    if args.apply is None:
        print("ZzzOps installation preview")
        print(f"Target: {target}")
        print("This will install:")
        print("- tracked project skills for Codex and Claude Code")
        print("- shared workflow rules and the ZzzOps control CLI")
        print("- blank templates for project setup, preferences, and TODO migration")
        if counts.get("create", 0) or counts.get("overwrite", 0):
            print(f"Planned changes: {counts.get('create', 0)} new, {counts.get('overwrite', 0)} updated.")
        else:
            print("Planned changes: ZzzOps is already up to date.")
        if ignored_roots:
            names = " and ".join(f"{root}/" for root in ignored_roots)
            print(f"Warning: Git ignores required ZzzOps project mechanics under {names}.")
            print("Remove those ignore rules before committing so collaborators receive the installed workflows.")
        if ignore_probe_warning:
            print(f"Warning: {ignore_probe_warning}")
    for error in errors:
        print(f"Cannot install yet: {error}")
    if errors:
        return 2
    if args.apply is None:
        print("No files were changed.")
        print("Run this command again with --apply and the approval code to apply exactly this preview:")
        print(f"Approval code: {fingerprint}")
        return 0
    if args.apply != fingerprint:
        print("The target changed or this approval is for another preview. Run the preview again; no files were changed.")
        return 2

    backups: dict[Path, bytes | None] = {}
    writes = [
        (target / relative, data, expected)
        for relative, action, data, expected in actions
        if action in {"create", "overwrite"}
    ]
    try:
        for path, data, expected in writes:
            current = path.read_bytes() if path.exists() else None
            current_digest = digest(current) if current is not None else None
            if current_digest != expected:
                raise OSError(f"Target changed after planning: {path}")
            backups[path] = current
            atomic_write(path, data)
    except OSError:
        for path, data in backups.items():
            if data is None and path.exists():
                path.unlink()
            elif data is not None:
                atomic_write(path, data)
        raise
    print("ZzzOps is installed. Start any ZzzOps workflow to set up the project.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install ZzzOps from a normal terminal.")
    commands = parser.add_subparsers(dest="command", required=True)
    install_parser = commands.add_parser("install", help="Preview or apply a mechanics-only installation")
    install_parser.add_argument("target", type=Path)
    install_parser.add_argument("--apply", metavar="APPROVAL_CODE")
    install_parser.add_argument("--overwrite-mechanical", action="store_true")
    install_parser.set_defaults(handler=install)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
