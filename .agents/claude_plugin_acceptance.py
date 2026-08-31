#!/usr/bin/env python3
"""Run Claude marketplace, cache, discovery, and packaged-runtime acceptance."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any


EXPECTED_SKILLS = {
    "add-zzzops-goal", "bootstrap-zzzops-repository", "execute-zzzops", "migrate-to-zzzops",
    "review-agentic-engineering", "review-zzzops-entropy", "review-zzzops-policy", "send-zzzops-feedback", "suggest-zzzops-work",
    "validate-zzzops-installation",
}


class AcceptanceError(ValueError):
    """The generated plugin failed an observable Claude acceptance boundary."""


NO_VERSION_WARNING = "version: No version specified. Consider adding a version following semver"


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


def validate_versionless(path: Path, *, env: dict[str, str]) -> None:
    """Keep strict validation except for Claude's warning about its documented SHA mode."""
    command = ["claude", "plugin", "validate", str(path), "--strict"]
    result = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
    if result.returncode == 0:
        return
    detail = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if (
        detail.count(NO_VERSION_WARNING) != 1
        or "Found 1 warning" not in detail
        or "Validation failed (--strict treats warnings as errors)" not in detail
    ):
        raise AcceptanceError("strict Claude validation failed beyond the documented SHA-version warning")
    run(["claude", "plugin", "validate", str(path)], env=env)


def commit_marketplace(marketplace: Path, marker: str, *, initialize: bool = False) -> str:
    """Commit one observable marketplace revision and return its Git identity."""
    if initialize:
        run(["git", "init", "--initial-branch", "main", str(marketplace)])
    (marketplace / "zzzops" / ".acceptance-revision").write_text(marker + "\n", encoding="utf-8")
    run(["git", "-C", str(marketplace), "add", "."])
    run([
        "git", "-C", str(marketplace), "-c", "user.name=ZzzOps Acceptance",
        "-c", "user.email=acceptance@invalid.example", "commit", "-m", f"revision {marker}",
    ])
    revision = run(["git", "-C", str(marketplace), "rev-parse", "HEAD"]).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise AcceptanceError("generated marketplace has no full Git commit identity")
    return revision


def write_repository_marketplace(root: Path, output: Path) -> Path:
    """Create the repository-native marketplace shape used by the Git revision probe."""
    output.mkdir()
    shutil.copytree(
        root / "plugins" / "zzzops", output / "zzzops",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    catalog = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8-sig"))
    catalog["plugins"][0]["source"] = "./zzzops"
    manifest = output / ".claude-plugin" / "marketplace.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def validate_available(records: Any, version: str | None, source: str = "./zzzops") -> None:
    expected = {
        "pluginId": "zzzops@zzzops", "name": "zzzops", "marketplaceName": "zzzops",
        "source": source,
    }
    if version is not None:
        expected["version"] = version
    if (
        not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict)
        or any(records[0].get(key) != value for key, value in expected.items())
        or (version is None and "version" in records[0])
    ):
        observed = records[0] if isinstance(records, list) and len(records) == 1 else records
        raise AcceptanceError(f"available plugin inventory mismatch: expected {expected!r}, observed {observed!r}")


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
        raise AcceptanceError(
            f"installed ZzzOps identity, version, or enabled state is invalid: "
            f"expected version {version!r}, observed {record!r}"
        )
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate generated ZzzOps through an isolated Claude installation")
    parser.add_argument("--claude-version", required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "plugins" / "zzzops" / "plugin.json").read_text(encoding="utf-8-sig"))
    product_version = manifest.get("version") if isinstance(manifest, dict) else None
    if not isinstance(product_version, str) or not product_version:
        print("Claude plugin acceptance failed: canonical plugin version is missing", file=sys.stderr)
        return 2
    try:
        with tempfile.TemporaryDirectory(prefix="zzzops-claude-acceptance-") as directory:
            workspace = Path(directory)
            marketplace = workspace / "marketplace"
            generated_marketplace = workspace / "generated"
            config = workspace / "config"
            project = workspace / "project"
            config.mkdir()
            project.mkdir()
            env = os.environ.copy()
            env["CLAUDE_CONFIG_DIR"] = str(config)
            observed_version = run(["claude", "--version"], env=env).strip()
            if not observed_version.startswith(args.claude_version + " "):
                raise AcceptanceError(f"Claude CLI version drift: expected {args.claude_version}, observed {observed_version}")
            built = json_output([
                sys.executable, str(root / ".github" / "scripts" / "build_claude_plugin.py"),
                "--version", product_version, "--output", str(generated_marketplace),
            ])
            generated = Path(built.get("marketplace", "")) if isinstance(built, dict) else Path()
            generated_plugin = generated / "zzzops"
            if generated.resolve() != generated_marketplace.resolve() or not generated_plugin.is_dir():
                raise AcceptanceError("Claude generator did not produce the expected repository marketplace")
            write_repository_marketplace(root, marketplace)
            plugin = marketplace / "zzzops"
            first_revision = commit_marketplace(marketplace, "first", initialize=True)
            first_cache_version = first_revision[:12]
            validate_versionless(root, env=env)
            validate_versionless(generated, env=env)
            validate_versionless(generated_plugin, env=env)
            validate_versionless(marketplace, env=env)
            validate_versionless(plugin, env=env)
            run(["claude", "plugin", "marketplace", "add", str(marketplace), "--scope", "user"], env=env)
            available = json_output(["claude", "plugin", "list", "--available", "--json"], env=env)
            validate_available(
                available.get("available") if isinstance(available, dict) else None,
                None,
            )
            run(["claude", "plugin", "install", "zzzops@zzzops", "--scope", "user", "--yes"], env=env)
            install = validate_install(
                json_output(["claude", "plugin", "list", "--json"], env=env), config, first_cache_version,
            )
            if (install / ".acceptance-revision").read_text(encoding="utf-8").strip() != "first":
                raise AcceptanceError("first installed cache does not contain the first Git revision")

            second_revision = commit_marketplace(marketplace, "second")
            second_cache_version = second_revision[:12]
            run(["claude", "plugin", "marketplace", "update", "zzzops"], env=env)
            run(["claude", "plugin", "update", "zzzops@zzzops", "--scope", "user"], env=env)
            updated = validate_install(
                json_output(["claude", "plugin", "list", "--json"], env=env), config, second_cache_version,
            )
            if updated == install or (updated / ".acceptance-revision").read_text(encoding="utf-8").strip() != "second":
                raise AcceptanceError("Claude did not install the second Git-backed plugin revision")
            install = updated
            details = run(["claude", "plugin", "details", "zzzops@zzzops"], env=env)
            validate_details(details)
            cached_skills = {path.name for path in (install / "skills").iterdir() if path.is_dir()}
            if cached_skills != EXPECTED_SKILLS:
                raise AcceptanceError("cached skill directories differ from the intended ZzzOps surface")
            inspection = json_output([
                sys.executable, str(install / "zzzops" / "zzzops.py"), "--repo", str(project), "init", "inspect",
            ])
            package = inspection.get("capabilities", {}).get("plugin_package", {}) if isinstance(inspection, dict) else {}
            if package.get("ok") is not True or package.get("version") != product_version:
                raise AcceptanceError("packaged ZzzOps runtime cannot validate its installed cache copy")
    except (AcceptanceError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Claude plugin acceptance failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "accepted": True, "claude_version": args.claude_version,
        "plugin_version": product_version,
        "claude_cache_versions": [first_cache_version, second_cache_version],
        "skills": sorted(EXPECTED_SKILLS),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
