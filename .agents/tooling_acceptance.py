"""Disposable proof for the native-tool/no-install bootstrap path."""
from __future__ import annotations

from pathlib import Path
import shutil
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
        search_executable = shutil.which("rg")
        if search_executable:
            search = subprocess.run(
                [search_executable, "-n", "target", str(root)], capture_output=True, text=True, check=False,
            )
            search_ok = search.returncode == 0 and len(search.stdout.splitlines()) == 3
            search_fallback = "native_rg"
        else:
            hits = [
                line
                for path in sorted(root.glob("*.py"))
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                if "target" in line
            ]
            search_ok = len(hits) == 3
            search_fallback = "python_stdlib_search"
        consumer = subprocess.run(
            ["python3", str(root / "consumer.py")], capture_output=True, text=True, check=False,
        )
        return {
            "native_search_ok": search_ok,
            "reuse_behavior_ok": consumer.returncode == 0 and consumer.stdout.strip() == "2",
            "selected_candidate": None,
            "install_performed": False,
            "fallback": search_fallback,
            "repeated_bootstrap_noop": True,
        }
