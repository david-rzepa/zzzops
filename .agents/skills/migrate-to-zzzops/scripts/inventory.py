"""Read-only cross-platform TODO inventory for agent-led migration."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", ".agents", ".claude", ".codex", ".zzzops", "goals", "node_modules",
    "vendor", "packages", "dist", "build", "out", "target", "bin", "obj",
    ".cache", ".venv", "venv", "__pycache__", "Library", "Temp",
}
TEXT_SUFFIXES = {
    "", ".c", ".cc", ".cpp", ".cs", ".css", ".go", ".h", ".hpp", ".html",
    ".java", ".js", ".jsx", ".json", ".kt", ".lua", ".md", ".mdx", ".php",
    ".ps1", ".py", ".rb", ".rs", ".rst", ".sh", ".sql", ".toml", ".ts",
    ".tsx", ".txt", ".xml", ".yaml", ".yml",
}
BACKLOG_STEMS = {"todo", "todos", "backlog", "roadmap", "tasks", "pending", "work-items", "work_items"}
MARKER = re.compile(r"(?i)(?:#|//|/\*|<!--|--|;|\*)\s*(?:TODO|FIXME|HACK|XXX)\b[:\s-]*(.+)")
TASK = re.compile(r"^\s*[-*+]\s*\[\s\]\s+(.+)")
LIST = re.compile(r"^\s*[-*+]\s+(.+)")


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def fingerprint(path: str, text: str, occurrence: int) -> str:
    return hashlib.sha256(f"{path.casefold()}\0{normalized(text)}\0{occurrence}".encode()).hexdigest()


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    state_path = root / ".zzzops" / "migration" / "STATE.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8-sig")) if state_path.exists() else {"items": []}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": f"Cannot read migration state: {exc}"}))
        return 2
    migrated = {item.get("fingerprint") for item in state.get("items", []) if isinstance(item, dict)}
    found = []
    counts: dict[tuple[str, str], int] = {}
    paths: list[Path] = []
    try:
        listed = subprocess.run(
            ["git", "-c", f"safe.directory={root.as_posix()}", "ls-files", "-co", "--exclude-standard", "-z"],
            cwd=root, check=True, capture_output=True,
        ).stdout.decode("utf-8", errors="surrogateescape")
        paths = [root / name for name in listed.split("\0") if name and not any(part in SKIP_DIRS for part in Path(name).parts[:-1])]
    except (OSError, subprocess.CalledProcessError):
        for directory, names, files in os.walk(root):
            names[:] = sorted(name for name in names if name not in SKIP_DIRS)
            paths.extend(Path(directory) / name for name in sorted(files))
    for path in paths:
        if path.suffix.casefold() not in TEXT_SUFFIXES or path.stat().st_size > 2_000_000:
            continue
        relative = path.relative_to(root).as_posix()
        dedicated = path.stem.casefold() in BACKLOG_STEMS
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError):
            continue
        for number, line in enumerate(lines, 1):
            match = TASK.match(line) or MARKER.search(line) or (LIST.match(line) if dedicated else None)
            if not match:
                continue
            text = re.sub(r"\s+", " ", match.group(1)).strip()[:500]
            if not text:
                continue
            key = (relative.casefold(), normalized(text))
            counts[key] = counts.get(key, 0) + 1
            item_fingerprint = fingerprint(relative, text, counts[key])
            found.append({"path": relative, "line": number, "text": text, "dedicated_backlog": dedicated, "fingerprint": item_fingerprint, "already_migrated": item_fingerprint in migrated})
    print(json.dumps({"candidate_count": len(found), "new_count": sum(not item["already_migrated"] for item in found), "candidates": found}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
