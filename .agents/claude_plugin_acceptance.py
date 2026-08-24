#!/usr/bin/env python3
"""Run Claude marketplace, cache, discovery, and packaged-runtime acceptance."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any
from zipfile import ZipFile


EXPECTED_SKILLS = {
    "add-zzzops-goal", "bootstrap-zzzops-repository", "execute-zzzops", "migrate-to-zzzops",
    "review-agentic-engineering", "review-zzzops-policy", "send-zzzops-feedback", "suggest-zzzops-work",
    "validate-zzzops-installation",
}


class AcceptanceError(ValueError):
    """The generated plugin failed an observable Claude acceptance boundary."""


def run(command: list[str], *, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
    if result.returncode:
        detail = (result.stderr.strip() or result.stdout.strip() or "no command output").splitlines()[0]
        raise AcceptanceError(f"command failed ({command[0]} {command[1]}): {detail[:300]}")
    return result.stdout


def json_output(command: list[str], *, env: dict[str, str] | None = None) -> Any:
    output = run(command, env=env)
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"command returned invalid JSON: {command[0]} {command[1]}") from exc


def validate_available(records: Any, version: str) -> None:
    expected = {
        "pluginId": "zzzops@zzzops", "name": "zzzops", "marketplaceName": "zzzops",
        "version": version, "source": "./zzzops",
    }
    if (
        not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict)
        or any(records[0].get(key) != value for key, value in expected.items())
    ):
        raise AcceptanceError("available plugin inventory does not match the generated marketplace")


def validate_details(details: str) -> None:
    match = re.search(r"Skills \((\d+)\)\s+(.*?)\r?\n\s*Agents \(", details, re.DOTALL)
    if not match:
        raise AcceptanceError("Claude details output has no parseable skill inventory")
    skills = {name.strip() for name in match.group(2).replace("\r", "").replace("\n", " ").split(",")}
    if int(match.group(1)) != len(EXPECTED_SKILLS) or skills != EXPECTED_SKILLS:
        raise AcceptanceError("Claude skill inventory differs from the intended ZzzOps surface")


def validate_install(records: Any, config: Path, version: str) -> Path:
    if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
        raise AcceptanceError("installed plugin inventory must contain exactly ZzzOps")
    record = records[0]
    if record.get("id") != "zzzops@zzzops" or record.get("version") != version or record.get("enabled") is not True:
        raise AcceptanceError("installed ZzzOps identity, version, or enabled state is invalid")
    install_text = record.get("installPath")
    if not isinstance(install_text, str) or not install_text:
        raise AcceptanceError("installed ZzzOps has no cache path")
    install = Path(install_text).resolve()
    cache = (config / "plugins" / "cache").resolve()
    if not install.is_relative_to(cache):
        raise AcceptanceError("installed ZzzOps is not inside the isolated Claude cache")
    required = (install / ".claude-plugin" / "plugin.json", install / "zzzops" / "zzzops.py")
    if any(not path.is_file() for path in required):
        raise AcceptanceError("installed cache copy is missing its manifest or packaged runtime")
    return install


def extract_archive(archive_path: Path, destination: Path) -> None:
    with ZipFile(archive_path) as archive:
        for name in archive.namelist():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise AcceptanceError(f"release archive contains an unsafe path: {name}")
        archive.extractall(destination)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate generated ZzzOps through an isolated Claude installation")
    parser.add_argument("--claude-version", required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "plugins" / "zzzops" / "plugin.json").read_text(encoding="utf-8-sig"))
    version = manifest.get("version") if isinstance(manifest, dict) else None
    if not isinstance(version, str) or not version:
        print("Claude plugin acceptance failed: canonical plugin version is missing", file=sys.stderr)
        return 2
    try:
        with tempfile.TemporaryDirectory(prefix="zzzops-claude-acceptance-") as directory:
            workspace = Path(directory)
            marketplace = workspace / "marketplace"
            plugin = workspace / "plugin"
            artifacts = workspace / "artifacts"
            config = workspace / "config"
            project = workspace / "project"
            release_notes = workspace / "RELEASE_NOTES.md"
            config.mkdir()
            project.mkdir()
            release_notes.write_text("Claude release artifact acceptance.\n", encoding="utf-8")
            env = os.environ.copy()
            env["CLAUDE_CONFIG_DIR"] = str(config)
            observed_version = run(["claude", "--version"], env=env).strip()
            if not observed_version.startswith(args.claude_version + " "):
                raise AcceptanceError(f"Claude CLI version drift: expected {args.claude_version}, observed {observed_version}")
            built = json_output([
                sys.executable, str(root / ".github" / "scripts" / "build_marketplace_bundle.py"),
                "--version", version, "--release-notes-file", str(release_notes),
                "--output", str(artifacts),
            ])
            claude_plugin = Path(built.get("claude_plugin", "")) if isinstance(built, dict) else Path()
            claude_submission = Path(built.get("claude_submission", "")) if isinstance(built, dict) else Path()
            if not claude_plugin.is_file() or not claude_submission.is_file():
                raise AcceptanceError("release builder did not produce both Claude archives")
            extract_archive(claude_plugin, plugin)
            extract_archive(claude_submission, marketplace)
            run(["claude", "plugin", "validate", str(marketplace), "--strict"], env=env)
            run(["claude", "plugin", "validate", str(plugin), "--strict"], env=env)
            run(["claude", "plugin", "marketplace", "add", str(marketplace), "--scope", "user"], env=env)
            available = json_output(["claude", "plugin", "list", "--available", "--json"], env=env)
            validate_available(available.get("available") if isinstance(available, dict) else None, version)
            run(["claude", "plugin", "install", "zzzops@zzzops", "--scope", "user", "--yes"], env=env)
            install = validate_install(json_output(["claude", "plugin", "list", "--json"], env=env), config, version)
            details = run(["claude", "plugin", "details", "zzzops@zzzops"], env=env)
            validate_details(details)
            cached_skills = {path.name for path in (install / "skills").iterdir() if path.is_dir()}
            if cached_skills != EXPECTED_SKILLS:
                raise AcceptanceError("cached skill directories differ from the intended ZzzOps surface")
            inspection = json_output([
                sys.executable, str(install / "zzzops" / "zzzops.py"), "--repo", str(project), "init", "inspect",
            ])
            package = inspection.get("capabilities", {}).get("plugin_package", {}) if isinstance(inspection, dict) else {}
            if package.get("ok") is not True or package.get("version") != version:
                raise AcceptanceError("packaged ZzzOps runtime cannot validate its installed cache copy")
    except (AcceptanceError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Claude plugin acceptance failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"accepted": True, "claude_version": args.claude_version, "plugin_version": version, "skills": sorted(EXPECTED_SKILLS)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
