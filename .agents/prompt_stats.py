#!/usr/bin/env python3
"""Update README prompt-budget table with a stable cross-harness estimate."""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

START = "<!-- PROMPT_BUDGET_START -->"
END = "<!-- PROMPT_BUDGET_END -->"


def canonical_size(data: bytes) -> int:
    """Count UTF-8 bytes after normalizing platform line endings to LF."""
    return len(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))


def prompt_files(root: Path) -> list[Path]:
    files = [root / "AGENTS.md", root / "CLAUDE.md"]
    files.extend((root / ".zzzops" / "rules").glob("*.md"))
    files.extend((root / ".agents" / "skills").glob("*/SKILL.md"))
    files.extend((root / ".agents" / "skills").glob("*/references/*.md"))
    files.extend((root / ".agents" / "templates" / "project-goals").glob("*.md"))
    files.extend((root / ".claude" / "skills").glob("*/SKILL.md"))
    return sorted({path for path in files if path.is_file()}, key=lambda path: path.relative_to(root).as_posix())


def main() -> int:
    parser = argparse.ArgumentParser(description="Update or verify README prompt-budget counts")
    parser.add_argument("--check", action="store_true", help="Fail instead of updating when counts are stale")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    rows = []
    for path in prompt_files(root):
        relative = path.relative_to(root).as_posix()
        size = canonical_size(path.read_bytes())
        rows.append((relative, size, math.ceil(size / 4)))
    total_bytes = sum(row[1] for row in rows)
    total_tokens = sum(row[2] for row in rows)
    table = [START, "| Prompt | Bytes | Est. tokens |", "| --- | ---: | ---: |"]
    table.extend(f"| `{path}` | {size} | {tokens} |" for path, size, tokens in rows)
    table.append(f"| **Total** | **{total_bytes}** | **{total_tokens}** |")
    table.append(END)
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8")
    replacement = "\n".join(table)
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(text):
        raise SystemExit("README prompt-budget markers are missing")
    updated = pattern.sub(replacement, text)
    if args.check:
        if updated != text:
            print("README prompt budget is stale; run python .agents/prompt_stats.py")
            return 1
        print(f"Current: {len(rows)} prompts, {total_bytes} bytes, ~{total_tokens} tokens")
        return 0
    readme.write_text(updated, encoding="utf-8", newline="\n")
    print(f"Updated {len(rows)} prompts: {total_bytes} bytes, ~{total_tokens} tokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
