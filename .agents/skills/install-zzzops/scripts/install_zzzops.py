"""Preview/apply a mechanics-only ZzzOps installation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

TARGET_SKILLS = ("add-zzzops-todo", "analyze-zzzops-usage", "execute-zzzops", "migrate-zzzops-todos", "suggest-zzzops-work")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_root() -> Path:
    return Path(__file__).resolve().parents[4]


def files_to_copy(root: Path) -> list[str]:
    paths = [
        ".zzzops/rules/BACKENDS.md", ".zzzops/rules/BLOCKERS.md",
        ".zzzops/rules/EXECUTION_STRATEGY.md", ".zzzops/rules/GOAL_SYSTEM.md",
        ".zzzops/rules/HEALTH.md", ".zzzops/rules/INITIALIZATION.md",
        ".zzzops/rules/USAGE_ACCOUNTING.md",
        ".agents/.gitignore", ".agents/zzzops.py", ".agents/zzzops_health.py",
    ]
    for base in [root / ".agents" / "templates" / "project-goals", *(root / ".agents" / "skills" / name for name in TARGET_SKILLS)]:
        paths.extend(path.relative_to(root).as_posix() for path in base.rglob("*") if path.is_file() and "__pycache__" not in path.parts and not path.name.startswith("test_"))
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Install ZzzOps mechanics; never migrate TODOs or overwrite state.")
    parser.add_argument("target", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-plan")
    parser.add_argument("--overwrite-mechanical", action="store_true")
    parser.add_argument("--allow-non-git", action="store_true")
    args = parser.parse_args()
    root, target = source_root(), args.target.resolve()
    errors: list[str] = []
    if not target.is_dir():
        errors.append("Target is not a directory")
    elif not args.allow_non_git and not (target / ".git").exists():
        errors.append("Target has no .git entry")
    try:
        manifest = files_to_copy(root)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2
    actions: list[tuple[str, str, bytes, str | None]] = []
    for relative in manifest:
        data = (root / relative).read_bytes()
        destination = target / relative
        before = destination.read_bytes() if destination.exists() else None
        if before is None:
            action = "create"
        elif before == data:
            action = "unchanged"
        elif args.overwrite_mechanical:
            action = "overwrite"
        else:
            action = "conflict"
            errors.append(f"Mechanical file differs: {relative}; review and pass --overwrite-mechanical")
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
            elif args.overwrite_mechanical:
                action = "overwrite"
            else:
                action = "conflict"
                errors.append(f"Mechanical file differs: {relative}; review and pass --overwrite-mechanical")
            actions.append((relative, action, data, digest(before) if before is not None else None))
    claude_ignore = (root / ".agents" / ".gitignore").read_bytes()
    destination = target / ".claude" / ".gitignore"
    before = destination.read_bytes() if destination.exists() else None
    if before is None:
        action = "create"
    elif before == claude_ignore:
        action = "unchanged"
    elif args.overwrite_mechanical:
        action = "overwrite"
    else:
        action = "conflict"
        errors.append("Mechanical file differs: .claude/.gitignore; review and pass --overwrite-mechanical")
    actions.append((".claude/.gitignore", action, claude_ignore, digest(before) if before is not None else None))
    zzzops_ignore = (root / ".agents" / "templates" / "project-goals" / "ZZZOPS_GITIGNORE").read_bytes()
    destination = target / ".zzzops" / ".gitignore"
    before = destination.read_bytes() if destination.exists() else None
    if before is None:
        action = "create"
    elif before == zzzops_ignore:
        action = "unchanged"
    elif args.overwrite_mechanical:
        action = "overwrite"
    else:
        action = "conflict"
        errors.append("Mechanical file differs: .zzzops/.gitignore; review and pass --overwrite-mechanical")
    actions.append((".zzzops/.gitignore", action, zzzops_ignore, digest(before) if before is not None else None))
    planned_paths = [target / relative for relative, _action, _data, _expected in actions]
    if any(not safe_target(target, path) for path in planned_paths):
        errors.append("A managed path resolves outside the target (symlink/junction)")
    payload = {"files": [(p, a, digest(d), expected) for p, a, d, expected in actions]}
    fingerprint = digest(json.dumps(payload, sort_keys=True).encode())
    counts: dict[str, int] = {}
    for _path, action, _data, _expected in actions:
        counts[action] = counts.get(action, 0) + 1
    print(f"Mode: {'APPLY' if args.apply else 'PREVIEW (no writes)'}")
    print(f"Target: {target}")
    print("Mechanical files: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 2
    print(f"Plan fingerprint: {fingerprint}")
    if not args.apply:
        return 0
    if args.confirm_plan != fingerprint:
        print("ERROR: --confirm-plan does not match; no writes made")
        return 2
    backups: dict[Path, bytes | None] = {}
    writes: list[tuple[Path, bytes, str | None]] = []
    writes.extend((target / relative, data, expected) for relative, action, data, expected in actions if action in {"create", "overwrite"})
    try:
        for path, data, expected in writes:
            current = path.read_bytes() if path.exists() else None
            current_digest = digest(current) if current is not None else None
            if current_digest != expected:
                raise OSError(f"Target changed after planning: {path}")
            backups[path] = path.read_bytes() if path.exists() else None
            atomic_write(path, data)
    except OSError:
        for path, data in backups.items():
            if data is None and path.exists():
                path.unlink()
            elif data is not None:
                atomic_write(path, data)
        raise
    print("Apply complete. Start any non-install ZzzOps workflow; its agent will initialize the project before ordinary work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
