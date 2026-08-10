#!/usr/bin/env python3
"""Build and validate deterministic OpenAI skills-only submission artifacts."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(rb"\bgh[opsu]_[A-Za-z0-9]{20,}\b"),
)
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class BundleError(ValueError):
    """Marketplace sources or generated artifacts are unsafe or incomplete."""


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"could not read {path.name}: {type(exc).__name__}") from exc


def require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BundleError(f"{field} must be non-empty text")
    return value


def validate_sources(root: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    listing = read_json(root / "marketplace" / "listing.json")
    tests = read_json(root / "marketplace" / "test-cases.json")
    attestations_path = root / "marketplace" / "ATTESTATIONS.md"
    try:
        attestations = attestations_path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    except (OSError, UnicodeError) as exc:
        raise BundleError(f"could not read ATTESTATIONS.md: {type(exc).__name__}") from exc
    if not isinstance(listing, dict) or listing.get("schema_version") != 1 or listing.get("submission_type") != "skills_only":
        raise BundleError("listing.json must be a schema v1 skills_only submission")
    if set(listing) != {"schema_version", "submission_type", "official_submission_docs", "listing", "assets", "starter_prompts", "availability"}:
        raise BundleError("listing.json fields do not match the submission source contract")
    info = listing["listing"]
    required_info = {
        "name", "short_description", "long_description", "category", "developer_name",
        "website_url", "support_url", "privacy_policy_url", "terms_url",
    }
    if not isinstance(info, dict) or set(info) != required_info:
        raise BundleError("listing fields are incomplete")
    for field in required_info:
        require_text(info[field], f"listing.{field}")
    if len(info["short_description"]) > 30:
        raise BundleError("listing.short_description must be 30 characters or fewer")
    if info["website_url"] != "https://github.com/david-rzepa/zzzops":
        raise BundleError("listing.website_url must be the repository URL")
    for field in ("website_url", "support_url", "privacy_policy_url", "terms_url"):
        if not info[field].startswith("https://"):
            raise BundleError(f"listing.{field} must be a public HTTPS URL")
    prompts = listing["starter_prompts"]
    if not isinstance(prompts, list) or len(prompts) < 3 or any(not isinstance(item, str) or not item.strip() for item in prompts):
        raise BundleError("starter_prompts must contain at least three prompts")
    availability = listing["availability"]
    if not isinstance(availability, dict) or availability.get("choice") != "all_portal_supported_countries" or not availability.get("rationale"):
        raise BundleError("availability choice and rationale are required")
    assets = listing["assets"]
    required_assets = {"logo_light", "logo_dark", "composer_icon_light", "composer_icon_dark"}
    if not isinstance(assets, dict) or set(assets) != required_assets:
        raise BundleError("light and dark logo and composer assets are required")
    for relative in assets.values():
        if not isinstance(relative, str) or PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts:
            raise BundleError(f"unsafe asset path: {relative}")
        if not root.joinpath(*PurePosixPath(relative).parts).is_file():
            raise BundleError(f"missing submission asset: {relative}")
    if not isinstance(tests, dict) or set(tests) != {"schema_version", "positive", "negative"} or tests.get("schema_version") != 1:
        raise BundleError("test-cases.json fields are invalid")
    if not isinstance(tests["positive"], list) or len(tests["positive"]) < 5:
        raise BundleError("at least five positive test cases are required")
    if not isinstance(tests["negative"], list) or len(tests["negative"]) < 3:
        raise BundleError("at least three negative test cases are required")
    for case in tests["positive"]:
        if not isinstance(case, dict) or set(case) != {"id", "prompt", "expected_behavior", "expected_result_shape", "fixture"}:
            raise BundleError("positive test case fields are incomplete")
        for field, value in case.items():
            require_text(value, f"positive.{field}")
    for case in tests["negative"]:
        if not isinstance(case, dict) or set(case) != {"id", "scenario", "expected_behavior", "why_not"}:
            raise BundleError("negative test case fields are incomplete")
        for field, value in case.items():
            require_text(value, f"negative.{field}")
    if attestations.count("- [ ]") < 9 or "human review gates" not in attestations:
        raise BundleError("ATTESTATIONS.md must retain the complete unchecked human checklist")
    return listing, tests, attestations


def scan_for_secrets(relative: str, data: bytes) -> None:
    folded = PurePosixPath(relative).name.casefold()
    if folded in {".env", "credentials.json", "secrets.json"} or folded.endswith((".pem", ".key", ".p12", ".pfx")):
        raise BundleError(f"secret-bearing filename is forbidden: {relative}")
    if any(pattern.search(data) for pattern in SECRET_PATTERNS):
        raise BundleError(f"secret-like content is forbidden: {relative}")


def plugin_files(root: Path, version: str) -> dict[str, bytes]:
    plugin = root / "plugins" / "zzzops"
    result: dict[str, bytes] = {}
    allowed_top_level = {".codex-plugin", "assets", "plugin.json", "rules", "scripts", "skills", "zzzops"}
    for path in sorted(plugin.rglob("*"), key=lambda item: item.relative_to(plugin).as_posix()):
        relative = path.relative_to(plugin).as_posix()
        if PurePosixPath(relative).parts[0] not in allowed_top_level:
            raise BundleError(f"unintended top-level plugin path: {relative}")
        if path.is_symlink():
            raise BundleError(f"plugin package contains a symlink: {relative}")
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        data = path.read_bytes().replace(b"\r\n", b"\n")
        if relative in {"plugin.json", ".codex-plugin/plugin.json"}:
            manifest = json.loads(data.decode("utf-8-sig"))
            manifest["version"] = version
            data = canonical_json(manifest)
        scan_for_secrets(relative, data)
        result[relative] = data
    required = {
        "plugin.json", ".codex-plugin/plugin.json", "assets/logo.png", "assets/logo-dark.png",
        "assets/composer-icon.png", "assets/composer-icon-dark.png", "scripts/cleanup_legacy.py",
    }
    missing = sorted(required - set(result))
    if missing:
        raise BundleError("plugin package is incomplete: " + ", ".join(missing))
    if any(path.startswith("skills/run-zzzops-acceptance/") for path in result):
        raise BundleError("repository-only acceptance skill entered the plugin package")
    shipped_skills = {
        PurePosixPath(path).parts[1] for path in result
        if len(PurePosixPath(path).parts) >= 3 and PurePosixPath(path).parts[0] == "skills"
    }
    if shipped_skills != {
        "add-zzzops-goal", "execute-zzzops", "migrate-to-zzzops",
        "review-zzzops-policy", "send-zzzops-feedback", "suggest-zzzops-work",
    }:
        raise BundleError("plugin archive must contain exactly the six product skills")
    return result


def zip_bytes(files: dict[str, bytes]) -> bytes:
    temporary = io.BytesIO()
    with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, data in sorted(files.items()):
            info = ZipInfo(relative, ZIP_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=9)
    temporary.seek(0)
    return temporary.read()


def listing_markdown(listing: dict[str, Any]) -> str:
    info = listing["listing"]
    prompts = "\n".join(f"- {prompt}" for prompt in listing["starter_prompts"])
    return (
        f"# {info['name']} listing\n\n"
        f"- Submission type: Skills only\n- Short description: {info['short_description']}\n"
        f"- Category: {info['category']}\n- Developer: {info['developer_name']}\n"
        f"- Website: {info['website_url']}\n- Support: {info['support_url']}\n"
        f"- Privacy: {info['privacy_policy_url']}\n- Terms: {info['terms_url']}\n\n"
        f"## Long description\n\n{info['long_description']}\n\n## Starter prompts\n\n{prompts}\n\n"
        f"## Availability\n\n{listing['availability']['choice']}: {listing['availability']['rationale']}\n"
    )


def tests_markdown(tests: dict[str, Any]) -> str:
    sections = ["# Submission test cases\n"]
    for label, key in (("Positive", "positive"), ("Negative", "negative")):
        sections.append(f"## {label}\n")
        for case in tests[key]:
            sections.append(f"### {case['id']}\n")
            for field, value in case.items():
                if field != "id":
                    sections.append(f"- {field.replace('_', ' ').title()}: {value}\n")
    return "\n".join(sections)


def validate_archive(data: bytes, expected: dict[str, bytes], label: str) -> None:
    temporary = io.BytesIO(data)
    with ZipFile(temporary) as archive:
        if archive.namelist() != sorted(expected):
            raise BundleError(f"{label} archive file tree is not deterministic")
        for relative, content in expected.items():
            if archive.read(relative) != content:
                raise BundleError(f"{label} archive content mismatch: {relative}")


def build_bundles(root: Path, output: Path, version: str, release_notes: str) -> dict[str, Path]:
    root = root.resolve()
    output = output.resolve()
    if not SEMVER.fullmatch(version):
        raise BundleError("version must be a concrete semantic release version")
    release_notes = require_text(release_notes, "release notes").replace("\r\n", "\n").rstrip() + "\n"
    listing, tests, attestations = validate_sources(root)
    plugin_contents = plugin_files(root, version)
    plugin_data = zip_bytes(plugin_contents)
    plugin_name = f"zzzops-plugin-v{version}.zip"
    submission = {
        "schema_version": 1,
        "submission_type": "skills_only",
        "version": version,
        "listing": listing["listing"],
        "assets": listing["assets"],
        "starter_prompts": listing["starter_prompts"],
        "availability": listing["availability"],
        "tests": {"positive": tests["positive"], "negative": tests["negative"]},
        "release_notes": release_notes.strip(),
        "official_submission_docs": listing["official_submission_docs"],
        "plugin_archive": {"filename": plugin_name, "sha256": sha256(plugin_data)},
        "human_actions": ["upload", "review attestations", "submit for review", "publish after approval"],
    }
    packet_contents = {
        "ATTESTATIONS.md": attestations.encode("utf-8"),
        "LISTING.md": listing_markdown(listing).encode("utf-8"),
        "RELEASE_NOTES.md": (f"# ZzzOps v{version}\n\n" + release_notes).encode("utf-8"),
        "TEST_CASES.md": tests_markdown(tests).encode("utf-8"),
        "submission.json": canonical_json(submission),
    }
    for packet_name, source_key in (
        ("assets/logo.png", "logo_light"), ("assets/logo-dark.png", "logo_dark"),
        ("assets/composer-icon.png", "composer_icon_light"),
        ("assets/composer-icon-dark.png", "composer_icon_dark"),
    ):
        packet_contents[packet_name] = root.joinpath(*PurePosixPath(listing["assets"][source_key]).parts).read_bytes()
    for relative, data in packet_contents.items():
        scan_for_secrets(relative, data)
    manifest = {
        "schema_version": 1,
        "version": version,
        "plugin_archive": {"filename": plugin_name, "sha256": sha256(plugin_data)},
        "files": {relative: sha256(data) for relative, data in sorted(packet_contents.items())},
    }
    packet_contents["manifest.json"] = canonical_json(manifest)
    submission_data = zip_bytes(packet_contents)
    validate_archive(plugin_data, plugin_contents, "plugin")
    validate_archive(submission_data, packet_contents, "submission")
    output.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="zzzops-marketplace-", dir=output.parent))
    try:
        plugin_path = staging / plugin_name
        submission_path = staging / f"zzzops-openai-submission-v{version}.zip"
        plugin_path.write_bytes(plugin_data)
        submission_path.write_bytes(submission_data)
        final_plugin = output / plugin_path.name
        final_submission = output / submission_path.name
        plugin_path.replace(final_plugin)
        submission_path.replace(final_submission)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {"plugin": final_plugin, "submission": final_submission}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build validated OpenAI marketplace submission artifacts")
    parser.add_argument("--version", required=True)
    parser.add_argument("--release-notes-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parents[2]
    try:
        notes = args.release_notes_file.read_text(encoding="utf-8-sig")
        result = build_bundles(root, args.output, args.version, notes)
    except (BundleError, OSError, UnicodeError) as exc:
        print(f"Marketplace bundle validation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({key: str(path) for key, path in result.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
