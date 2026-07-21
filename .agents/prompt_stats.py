#!/usr/bin/env python3
"""Print and enforce a stable cross-harness prompt-budget estimate."""

from __future__ import annotations

import argparse
import math
from pathlib import Path


# Goal #129 adds the privacy boundary itself: shared immutable-report rules, exact public-
# payload consent, and one session gate that prevents feedback issues entering execution silently.
MAX_ESTIMATED_TOKENS = 14_400

def canonical_size(data: bytes) -> int:
    """Count UTF-8 bytes after normalizing platform line endings to LF."""
    return len(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))


def prompt_files(root: Path) -> list[Path]:
    files = [root / "AGENTS.md", root / "CLAUDE.md"]
    files.extend((root / ".zzzops" / "rules").glob("*.md"))
    files.extend((root / ".agents" / "skills").glob("*/SKILL.md"))
    files.extend((root / ".agents" / "skills").glob("*/references/*.md"))
    files.extend((root / ".agents" / "zzzops" / "templates" / "project-goals").glob("*.md"))
    files.extend((root / ".claude" / "skills").glob("*/SKILL.md"))
    return sorted({path for path in files if path.is_file()}, key=lambda path: path.relative_to(root).as_posix())


def render_report(rows: list[tuple[str, int, int]]) -> str:
    total_bytes = sum(row[1] for row in rows)
    total_tokens = sum(row[2] for row in rows)
    table = [
        "# Prompt budget report",
        "",
        "Stable cross-harness estimate: `ceil(canonical UTF-8 bytes / 4)`; line endings normalize to LF. This is prompt-size regression evidence, not billing.",
        "",
        "| Prompt | Bytes | Est. tokens |",
        "| --- | ---: | ---: |",
    ]
    table.extend(f"| `{path}` | {size} | {tokens} |" for path, size, tokens in rows)
    table.append(f"| **Total** | **{total_bytes}** | **{total_tokens}** |")
    return "\n".join(table) + "\n"


def within_budget(rows: list[tuple[str, int, int]], limit: int = MAX_ESTIMATED_TOKENS) -> bool:
    return sum(row[2] for row in rows) <= limit


def main() -> int:
    parser = argparse.ArgumentParser(description="Print or enforce the prompt-budget estimate")
    parser.add_argument("--check", action="store_true", help="Fail when the estimated prompt budget exceeds its committed ceiling")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    rows = []
    for path in prompt_files(root):
        relative = path.relative_to(root).as_posix()
        size = canonical_size(path.read_bytes())
        rows.append((relative, size, math.ceil(size / 4)))
    if args.check:
        if not within_budget(rows):
            print(f"Prompt budget exceeds {MAX_ESTIMATED_TOKENS} estimated tokens; reduce prompts or deliberately raise the ceiling.")
            return 1
        print(f"Current: {len(rows)} prompts, {sum(row[1] for row in rows)} bytes, ~{sum(row[2] for row in rows)} tokens")
        return 0
    print(render_report(rows), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
