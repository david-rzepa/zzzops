#!/usr/bin/env python3
"""Plan a SemVer release from Conventional Commits without remote writes."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
COMMIT = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]*\))?(?P<breaking>!)?:\s+(?P<summary>.+)$")


@dataclass(frozen=True)
class Change:
    sha: str
    subject: str
    body: str

    @property
    def parsed(self) -> re.Match[str] | None:
        return COMMIT.match(self.subject)

    @property
    def breaking(self) -> bool:
        parsed = self.parsed
        return bool((parsed and parsed.group("breaking")) or re.search(r"BREAKING[ -]CHANGE:", self.body))


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, text=True, encoding="utf-8", stdout=subprocess.PIPE
    ).stdout.rstrip("\r\n")


def latest_version() -> tuple[str | None, tuple[int, int, int]]:
    tags = []
    for name in git("tag", "--list", "v[0-9]*.[0-9]*.[0-9]*").splitlines():
        match = TAG.match(name)
        if match:
            tags.append((tuple(map(int, match.groups())), name))
    if not tags:
        return None, (0, 0, 0)
    version, name = max(tags)
    return name, version


def changes_since(tag: str | None) -> list[Change]:
    revision = f"{tag}..HEAD" if tag else "HEAD"
    raw = git("log", revision, "--format=%H%x1f%s%x1f%b%x1e")
    changes = []
    for record in raw.split("\x1e"):
        fields = record.strip("\r\n").split("\x1f", 2)
        if len(fields) == 3:
            changes.append(Change(*fields))
    return changes


def bump_for(changes: list[Change]) -> str | None:
    if any(change.breaking for change in changes):
        return "major"
    types = {match.group("type") for change in changes if (match := change.parsed)}
    if "feat" in types:
        return "minor"
    if types.intersection({"fix", "perf"}):
        return "patch"
    return None


def next_version(current: tuple[int, int, int], bump: str) -> tuple[int, int, int]:
    major, minor, patch = current
    if bump == "major":
        return major + 1, 0, 0
    if bump == "minor":
        return major, minor + 1, 0
    return major, minor, patch + 1


def release_notes(tag: str, changes: list[Change]) -> str:
    sections = {"Breaking changes": [], "Features": [], "Fixes": [], "Performance": []}
    for change in changes:
        parsed = change.parsed
        if not parsed:
            continue
        item = f"- {parsed.group('summary')} ({change.sha[:7]})"
        if change.breaking:
            sections["Breaking changes"].append(item)
        elif parsed.group("type") == "feat":
            sections["Features"].append(item)
        elif parsed.group("type") == "fix":
            sections["Fixes"].append(item)
        elif parsed.group("type") == "perf":
            sections["Performance"].append(item)
    lines = [f"# {tag}", ""]
    for heading, items in sections.items():
        if items:
            lines.extend((f"## {heading}", "", *items, ""))
    return "\n".join(lines).rstrip() + "\n"


def set_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notes", type=Path, default=Path("release-notes.md"))
    args = parser.parse_args()
    previous_tag, current = latest_version()
    changes = changes_since(previous_tag)
    bump = bump_for(changes)
    if not bump:
        print("No releasable Conventional Commits since", previous_tag or "repository start")
        set_output("release_needed", "false")
        return 0
    version = next_version(current, bump)
    tag = "v" + ".".join(map(str, version))
    args.notes.write_text(release_notes(tag, changes), encoding="utf-8", newline="\n")
    print(f"Release planned: {previous_tag or 'none'} -> {tag} ({bump})")
    set_output("release_needed", "true")
    set_output("version", ".".join(map(str, version)))
    set_output("tag", tag)
    set_output("notes", str(args.notes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
