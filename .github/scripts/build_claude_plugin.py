#!/usr/bin/env python3
"""Generate a self-contained Claude Code marketplace from canonical ZzzOps sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import shutil
import sys

import build_marketplace_bundle as bundles


def write_marketplace(root: Path, output: Path, version: str) -> Path:
    root = root.resolve()
    output = output.resolve()
    if output in {root, output.parent}:
        raise bundles.BundleError("output must be a dedicated child directory")
    if output.exists():
        raise bundles.BundleError("output must not already exist")
    files = bundles.claude_marketplace_files(root, version)
    output.parent.mkdir(parents=True, exist_ok=True)
    owns_output = False
    try:
        output.mkdir()
        owns_output = True
        for relative, data in sorted(files.items()):
            path = PurePosixPath(relative)
            if path.is_absolute() or ".." in path.parts:
                raise bundles.BundleError(f"unsafe generated path: {relative}")
            destination = output.joinpath(*path.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
    except Exception:
        if owns_output and output.exists():
            shutil.rmtree(output)
        raise
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a generated Claude Code marketplace")
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parents[2]
    try:
        result = write_marketplace(root, args.output, args.version)
    except (bundles.BundleError, OSError, UnicodeError) as exc:
        print(f"Claude plugin generation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"marketplace": str(result)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
