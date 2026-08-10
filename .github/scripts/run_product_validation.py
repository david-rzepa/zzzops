"""Run one named, read-only ZzzOps product-validation leg."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run(*command: str) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def linux_validation() -> None:
    run(sys.executable, "-m", "unittest", "discover", "-s", ".agents", "-p", "test_*.py")
    run(sys.executable, "-m", "unittest", "discover", "-s", "plugins/zzzops/skills/migrate-to-zzzops/scripts", "-p", "test_*.py")
    run(sys.executable, ".agents/manual_acceptance.py", "coverage")
    run("npm", "run", "test:plugin")
    run("npm", "run", "test:release")
    run(sys.executable, ".agents/prompt_stats.py", "--check")
    run(sys.executable, "-m", "compileall", "-q", ".agents", "plugins/zzzops", ".github/scripts")


def windows_validation() -> None:
    run(sys.executable, ".agents/test_zzzops.py")
    run(sys.executable, ".agents/test_legacy_cleanup.py")
    run(sys.executable, ".agents/test_marketplace_bundle.py")
    run(sys.executable, "-m", "unittest", "discover", "-s", "plugins/zzzops/skills/migrate-to-zzzops/scripts", "-p", "test_*.py")


def macos_validation() -> None:
    run(sys.executable, ".agents/test_zzzops.py")
    run(sys.executable, ".agents/test_legacy_cleanup.py")
    run(sys.executable, ".agents/test_marketplace_bundle.py")
    run(sys.executable, "-m", "unittest", "discover", "-s", "plugins/zzzops/skills/migrate-to-zzzops/scripts", "-p", "test_*.py")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("linux", "windows", "macos"), required=True)
    args = parser.parse_args()
    {"linux": linux_validation, "windows": windows_validation, "macos": macos_validation}[args.platform]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
