#!/usr/bin/env python3
"""Small interactive ZzzOps control panel."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

PREFERENCE_LABELS = (
    ("documentation", "Fill backlog with documentation work"),
    ("tests", "Fill backlog with test work"),
    ("code_quality_non_behavioral", "Fill backlog with non-behavioral code-quality work"),
)
PARALLEL_MODES = (
    ("sequential", "Sequential only"),
    ("read_only", "Read-only parallel work"),
    ("worktrees", "Writable parallel work in Git worktrees"),
)


def load_preferences(repo: Path) -> tuple[Path, dict[str, Any]]:
    path = repo / ".zzzops" / "PREFERENCES.json"
    template = repo / ".agents" / "templates" / "project-goals" / "PREFERENCES.json"
    source = path if path.exists() else template
    try:
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read preferences from {source}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Preferences root must be a JSON object")
    fill = data.setdefault("fill_backlog", {})
    if not isinstance(fill, dict):
        raise ValueError("fill_backlog must be a JSON object")
    for key, _label in PREFERENCE_LABELS:
        if not isinstance(fill.setdefault(key, False), bool):
            raise ValueError(f"fill_backlog.{key} must be true or false")
    cap = fill.setdefault("max_goals_per_refill", 3)
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1 or cap > 25:
        raise ValueError("max_goals_per_refill must be an integer from 1 to 25")
    parallel = data.setdefault("parallelization", {})
    if not isinstance(parallel, dict):
        raise ValueError("parallelization must be a JSON object")
    mode = parallel.setdefault("mode", "read_only")
    if mode not in {value for value, _label in PARALLEL_MODES}:
        raise ValueError("parallelization.mode must be sequential, read_only, or worktrees")
    workers = parallel.setdefault("max_workers", 2)
    if not isinstance(workers, int) or isinstance(workers, bool) or workers < 1 or workers > 8:
        raise ValueError("parallelization.max_workers must be an integer from 1 to 8")
    return path, data


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(encoded)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def edit_preferences(repo: Path) -> None:
    path, preferences = load_preferences(repo)
    fill = preferences["fill_backlog"]
    while True:
        print("\nBacklog refill preferences")
        for number, (key, label) in enumerate(PREFERENCE_LABELS, 1):
            print(f"  {number}. [{'x' if fill[key] else ' '}] {label}")
        print(f"  4. Maximum goals per refill: {fill['max_goals_per_refill']}")
        print("  s. Save and return")
        print("  q. Discard and return")
        choice = input("> ").strip().casefold()
        if choice in {"1", "2", "3"}:
            key = PREFERENCE_LABELS[int(choice) - 1][0]
            fill[key] = not fill[key]
        elif choice == "4":
            value = input("Maximum goals per refill (1-25): ").strip()
            if value.isdigit() and 1 <= int(value) <= 25:
                fill["max_goals_per_refill"] = int(value)
            else:
                print("Enter an integer from 1 to 25.")
        elif choice == "s":
            atomic_json(path, preferences)
            print(f"Saved local preferences to {path}")
            return
        elif choice == "q":
            print("No changes saved.")
            return
        else:
            print("Choose 1-4, s, or q.")


def edit_parallelization(repo: Path) -> None:
    path, preferences = load_preferences(repo)
    parallel = preferences["parallelization"]
    while True:
        print("\nParallelization preferences")
        for number, (value, label) in enumerate(PARALLEL_MODES, 1):
            print(f"  {number}. {'*' if parallel['mode'] == value else ' '} {label}")
        print(f"  4. Maximum workers: {parallel['max_workers']}")
        print("  s. Save and return")
        print("  q. Discard and return")
        choice = input("> ").strip().casefold()
        if choice in {"1", "2", "3"}:
            parallel["mode"] = PARALLEL_MODES[int(choice) - 1][0]
        elif choice == "4":
            value = input("Maximum workers (1-8): ").strip()
            if value.isdigit() and 1 <= int(value) <= 8:
                parallel["max_workers"] = int(value)
            else:
                print("Enter an integer from 1 to 8.")
        elif choice == "s":
            atomic_json(path, preferences)
            print(f"Saved local preferences to {path}")
            return
        elif choice == "q":
            print("No changes saved.")
            return
        else:
            print("Choose 1-4, s, or q.")


def interactive(repo: Path) -> None:
    while True:
        print("\nZzzOps control panel")
        print("  1. Edit preferences")
        print("  2. Edit parallelization")
        print("  q. Exit")
        choice = input("> ").strip().casefold()
        if choice == "1":
            edit_preferences(repo)
        elif choice == "2":
            edit_parallelization(repo)
        elif choice == "q":
            return
        else:
            print("Choose 1, 2, or q.")


def main() -> int:
    parser = argparse.ArgumentParser(description="ZzzOps control panel")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Project root (default: current directory)")
    args = parser.parse_args()
    repo = args.repo.resolve()
    if not (repo / ".agents" / "templates" / "project-goals" / "PREFERENCES.json").is_file():
        print(f"ERROR: ZzzOps is not installed at {repo}")
        return 2
    try:
        interactive(repo)
    except (EOFError, KeyboardInterrupt):
        print("\nNo further changes made.")
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
