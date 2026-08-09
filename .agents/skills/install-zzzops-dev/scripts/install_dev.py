#!/usr/bin/env python3
"""Install the current ZzzOps checkout with a temporary Codex cachebuster."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PLUGIN_NAME = "zzzops"
MARKETPLACE_RELATIVE = Path(".agents/plugins/marketplace.json")
PLUGIN_RELATIVE = Path("plugins/zzzops")
CODEX_MANIFEST_RELATIVE = PLUGIN_RELATIVE / ".codex-plugin/plugin.json"
OPEN_MANIFEST_RELATIVE = PLUGIN_RELATIVE / "plugin.json"


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / MARKETPLACE_RELATIVE).is_file() and (candidate / CODEX_MANIFEST_RELATIVE).is_file():
            return candidate
    raise RuntimeError("run inside a ZzzOps checkout containing the plugin and local marketplace")


def run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)


def load_marketplace(repo_root: Path) -> tuple[str, Path]:
    path = repo_root / MARKETPLACE_RELATIVE
    payload = json.loads(path.read_text(encoding="utf-8"))
    marketplace_name = payload.get("name")
    plugins = payload.get("plugins")
    if not isinstance(marketplace_name, str) or not isinstance(plugins, list):
        raise RuntimeError(f"invalid marketplace metadata: {path}")
    entry = next((item for item in plugins if item.get("name") == PLUGIN_NAME), None)
    if not isinstance(entry, dict):
        raise RuntimeError(f"marketplace does not contain {PLUGIN_NAME!r}")
    source = entry.get("source")
    if not isinstance(source, dict) or source.get("source") != "local" or not isinstance(source.get("path"), str):
        raise RuntimeError(f"marketplace entry for {PLUGIN_NAME!r} is not a local source")
    plugin_path = (repo_root / source["path"]).resolve()
    expected = (repo_root / PLUGIN_RELATIVE).resolve()
    if plugin_path != expected:
        raise RuntimeError(f"marketplace resolves {PLUGIN_NAME!r} to {plugin_path}, expected {expected}")
    return marketplace_name, plugin_path


def configured_marketplace_root(codex: str, marketplace_name: str, repo_root: Path) -> Path | None:
    output = run([codex, "plugin", "marketplace", "list"], cwd=repo_root).stdout
    pattern = re.compile(rf"^\s*{re.escape(marketplace_name)}\s+(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
    match = pattern.search(output)
    return Path(match.group(1)).resolve() if match else None


def cachebusted_manifest(original: bytes, manifest_path: Path, cachebuster: str) -> bytes:
    payload = json.loads(original.decode("utf-8"))
    version = payload.get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError(f"missing version in {manifest_path}")
    base_version = version.split("+", 1)[0]
    payload["version"] = f"{base_version}+codex.{cachebuster}"
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


def main() -> int:
    repo_root = find_repo_root(Path.cwd())
    marketplace_name, plugin_path = load_marketplace(repo_root)
    codex = shutil.which("codex")
    if codex is None:
        raise RuntimeError("codex CLI is not available on PATH")

    manifest_status = run([
        "git", "status", "--short", "--",
        CODEX_MANIFEST_RELATIVE.as_posix(), OPEN_MANIFEST_RELATIVE.as_posix(),
    ], cwd=repo_root).stdout.strip()
    if manifest_status:
        raise RuntimeError(f"refusing to overwrite a changed plugin manifest: {manifest_status}")

    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm is not available on PATH")
    run([npm, "run", "test:plugin"], cwd=repo_root)
    run([sys.executable, str(repo_root / ".agents/test_agent_plugin.py")], cwd=repo_root)
    run([sys.executable, str(repo_root / ".agents/prompt_stats.py"), "--check"], cwd=repo_root)
    print("Validated plugin schema, repository package invariants, and prompt budget.")

    configured_root = configured_marketplace_root(codex, marketplace_name, repo_root)
    if configured_root is None:
        result = run([codex, "plugin", "marketplace", "add", str(repo_root), "--json"], cwd=repo_root)
        if result.stdout.strip():
            print(result.stdout.strip())
    elif configured_root != repo_root.resolve():
        raise RuntimeError(
            f"marketplace {marketplace_name!r} is registered to {configured_root}, not {repo_root.resolve()}; "
            "remove and re-add it only after confirming the other checkout can be disconnected"
        )

    manifest_paths = [plugin_path / "plugin.json", plugin_path / ".codex-plugin/plugin.json"]
    originals = {path: path.read_bytes() for path in manifest_paths}
    cachebuster = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    temporary = {
        path: cachebusted_manifest(originals[path], path, cachebuster) for path in manifest_paths
    }
    try:
        for path in manifest_paths:
            path.write_bytes(temporary[path])
        result = run([codex, "plugin", "add", f"{PLUGIN_NAME}@{marketplace_name}", "--json"], cwd=repo_root)
        if result.stdout.strip():
            print(result.stdout.strip())
    finally:
        for path in manifest_paths:
            path.write_bytes(originals[path])

    installed_version = json.loads(temporary[manifest_paths[0]].decode("utf-8"))["version"]
    print(f"Installed {PLUGIN_NAME}@{marketplace_name} from {plugin_path} as {installed_version}.")
    print("Start a new Codex task to load the refreshed skills.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            detail = (error.stderr or error.stdout or "").strip()
            if detail:
                print(detail, file=sys.stderr)
        print(f"install-zzzops-dev: {error}", file=sys.stderr)
        raise SystemExit(1) from error
