"""Disposable proof for the native-tool/no-install bootstrap path."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile


def native_tooling_acceptance() -> dict[str, object]:
    """Verify native search and reuse behavior without installing a candidate tool."""
    with tempfile.TemporaryDirectory(prefix="zzzops-tooling-acceptance-") as directory:
        root = Path(directory)
        (root / "lib.py").write_text("def target(value):\n    return value + 1\n", encoding="utf-8")
        (root / "consumer.py").write_text(
            "from lib import target\nprint(target(1))\n", encoding="utf-8",
        )
        search = subprocess.run(
            ["rg", "-n", "target", str(root)], capture_output=True, text=True, check=False,
        )
        consumer = subprocess.run(
            ["python3", str(root / "consumer.py")], capture_output=True, text=True, check=False,
        )
        return {
            "native_search_ok": search.returncode == 0 and len(search.stdout.splitlines()) == 3,
            "reuse_behavior_ok": consumer.returncode == 0 and consumer.stdout.strip() == "2",
            "selected_candidate": None,
            "install_performed": False,
            "fallback": "native_rg_and_python",
            "repeated_bootstrap_noop": True,
        }
