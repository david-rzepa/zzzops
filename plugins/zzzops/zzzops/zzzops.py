#!/usr/bin/env python3
"""ZzzOps CLI entrypoint: `zzzops.py <verb> …` (DESIGN.md §3.15, SPEC.md §6)."""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info < (3, 10):
    sys.stderr.write("zzzops: Python 3.10 or later is required\n")
    raise SystemExit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
