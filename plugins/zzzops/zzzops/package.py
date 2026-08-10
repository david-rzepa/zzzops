"""Validate the loaded Agent Plugin package and derive local provenance."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PLUGIN_ROOT / "plugin.json"
MANIFEST_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
PLUGIN_NAME = "zzzops"
PLUGIN_FIELDS = {
    "$schema", "name", "version", "description", "author", "homepage",
    "repository", "license", "keywords", "extensions",
}
SHIPPED_SKILLS = {
    "add-zzzops-goal", "execute-zzzops", "migrate-to-zzzops",
    "review-zzzops-policy", "send-zzzops-feedback", "suggest-zzzops-work",
}
REQUIRED_FILES = {
    ".codex-plugin/plugin.json",
    "assets/legacy_install_fingerprints.json",
    "rules/BACKENDS.md", "rules/BLOCKERS.md", "rules/CONTINUATION.md",
    "rules/EXECUTION_STRATEGY.md", "rules/FEEDBACK.md", "rules/GOAL_SYSTEM.md",
    "rules/INITIALIZATION.md", "zzzops/zzzops.py",
    "scripts/cleanup_legacy.py",
    "zzzops/templates/project-goals/INIT_PLAN.json",
}
NAME_PATTERN = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")


class PluginPackageError(ValueError):
    """The loaded package is incomplete or not the supported Agent Plugin."""


def read_plugin_manifest() -> dict[str, Any]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PluginPackageError(f"could not read plugin.json: {type(exc).__name__}") from exc
    if not isinstance(manifest, dict) or set(manifest) - PLUGIN_FIELDS:
        raise PluginPackageError("plugin.json contains unsupported fields")
    if manifest.get("$schema") != MANIFEST_SCHEMA or manifest.get("name") != PLUGIN_NAME:
        raise PluginPackageError("plugin.json does not identify the supported ZzzOps Agent Plugin")
    name = manifest["name"]
    if not isinstance(name, str) or not 1 <= len(name) <= 64 or not NAME_PATTERN.fullmatch(name):
        raise PluginPackageError("plugin.json name is invalid")
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise PluginPackageError("plugin.json version is required for ZzzOps provenance")
    return manifest


def package_files() -> list[Path]:
    files: list[Path] = []
    for path in PLUGIN_ROOT.rglob("*"):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise PluginPackageError(f"plugin package contains a symlink: {path.relative_to(PLUGIN_ROOT).as_posix()}")
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda item: item.relative_to(PLUGIN_ROOT).as_posix())


def package_provenance(_repo: Path | None = None) -> dict[str, str]:
    manifest = read_plugin_manifest()
    digest = hashlib.sha256()
    for path in package_files():
        relative = path.relative_to(PLUGIN_ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return {"version": manifest["version"], "revision": digest.hexdigest()}


def package_status() -> dict[str, Any]:
    try:
        manifest = read_plugin_manifest()
        codex_manifest = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8-sig"))
        if codex_manifest.get("name") != manifest["name"] or codex_manifest.get("version") != manifest["version"]:
            raise PluginPackageError("Agent Plugins and Codex manifests disagree on name or version")
        missing = sorted(relative for relative in REQUIRED_FILES if not (PLUGIN_ROOT / relative).is_file())
        missing.extend(
            f"skills/{name}/SKILL.md" for name in sorted(SHIPPED_SKILLS)
            if not (PLUGIN_ROOT / "skills" / name / "SKILL.md").is_file()
        )
        if missing:
            raise PluginPackageError("missing package files: " + ", ".join(missing))
        provenance = package_provenance()
    except (OSError, UnicodeError, json.JSONDecodeError, PluginPackageError) as exc:
        return {
            "available": True, "ok": False, "paths": [], "processes": 0,
            "detail": f"{exc}; reinstall ZzzOps from its Codex marketplace.",
        }
    return {
        "available": True, "ok": True, "paths": [], "processes": 0,
        "detail": "ok", "version": provenance["version"], "revision": provenance["revision"],
    }
