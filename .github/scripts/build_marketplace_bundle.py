#!/usr/bin/env python3
"""Build the deterministic, validated OpenAI portal skills bundle."""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import runpy
import shutil
import struct
import sys
import tempfile
from typing import Any
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo
import zlib


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


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"could not read {path.name}: {type(exc).__name__}") from exc


def require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BundleError(f"{field} must be non-empty text")
    return value


def validate_portal_png(relative: str, data: bytes) -> None:
    """Fully decode the conservative PNG profile used for portal branding."""
    if len(data) > 5 * 1024 * 1024:
        raise BundleError(f"branding PNG exceeds the portal size limit: {relative}")
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise BundleError(f"branding asset is not a PNG: {relative}")
    offset = 8
    header = None
    compressed = bytearray()
    ended = False
    chunk_types = []
    while offset < len(data):
        if offset + 12 > len(data):
            raise BundleError(f"truncated branding PNG chunk: {relative}")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        chunk_type = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data):
            raise BundleError(f"truncated branding PNG payload: {relative}")
        payload = data[offset + 8:offset + 8 + length]
        chunk_types.append(chunk_type)
        expected_crc = struct.unpack(">I", data[offset + 8 + length:end])[0]
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != expected_crc:
            raise BundleError(f"branding PNG has an invalid checksum: {relative}")
        if chunk_type == b"IHDR":
            if header is not None or length != 13:
                raise BundleError(f"branding PNG has an invalid header: {relative}")
            header = struct.unpack(">IIBBBBB", payload)
        elif chunk_type == b"IDAT":
            compressed.extend(payload)
        elif chunk_type == b"IEND":
            if length != 0 or end != len(data):
                raise BundleError(f"branding PNG has an invalid terminator: {relative}")
            ended = True
        offset = end
    if header is None:
        raise BundleError(f"branding PNG has no header: {relative}")
    width, height, bit_depth, color_type, compression, filtering, interlace = header
    if (
        width != height or not 48 <= width <= 4096
        or (bit_depth, color_type, compression, filtering, interlace) != (8, 6, 0, 0, 0)
        or not compressed or not ended
        or chunk_types[0] != b"IHDR" or chunk_types[-1] != b"IEND"
        or any(chunk not in {b"IHDR", b"IDAT", b"IEND"} for chunk in chunk_types)
    ):
        raise BundleError(f"branding PNG must be metadata-free square 8-bit RGBA: {relative}")
    try:
        pixels = zlib.decompress(bytes(compressed))
    except zlib.error as exc:
        raise BundleError(f"branding PNG pixel data cannot be decoded: {relative}") from exc
    row_size = 1 + width * 4
    if len(pixels) != row_size * height or any(pixels[row * row_size] > 4 for row in range(height)):
        raise BundleError(f"branding PNG scanlines are invalid: {relative}")


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
        asset_path = root.joinpath(*PurePosixPath(relative).parts)
        if not asset_path.is_file():
            raise BundleError(f"missing submission asset: {relative}")
        validate_portal_png(relative, asset_path.read_bytes())
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
    development_version = "0.0.0-dev"
    for relative in ("plugin.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
        manifest = read_json(plugin / relative)
        if not isinstance(manifest, dict) or manifest.get("version") != development_version:
            raise BundleError(
                f"canonical development manifest must use {development_version}: {relative}"
            )
    package = runpy.run_path(str(plugin / "zzzops" / "package.py"))
    renderer = package["render_skill_metadata"]
    result: dict[str, bytes] = {}
    allowed_top_level = {
        ".claude-plugin", ".codex-plugin", "assets", "concepts", "plugin.json", "rules", "scripts", "skills", "zzzops",
    }
    for path in sorted(plugin.rglob("*"), key=lambda item: item.relative_to(plugin).as_posix()):
        relative = path.relative_to(plugin).as_posix()
        if PurePosixPath(relative).parts[0] not in allowed_top_level:
            raise BundleError(f"unintended top-level plugin path: {relative}")
        if path.is_symlink():
            raise BundleError(f"plugin package contains a symlink: {relative}")
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        data = path.read_bytes()
        if path.suffix.casefold() in {".json", ".md", ".py", ".yaml", ".yml"}:
            data = data.replace(b"\r\n", b"\n")
        if relative in {"plugin.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json"}:
            manifest = json.loads(data.decode("utf-8-sig"))
            manifest["version"] = version
            data = canonical_json(manifest)
        try:
            data = renderer(relative, data, version, "official")
        except ValueError as exc:
            raise BundleError(f"invalid skill discovery metadata in {relative}: {exc}") from exc
        scan_for_secrets(relative, data)
        result[relative] = data
    required = {
        "plugin.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "assets/logo.png", "assets/logo-dark.png",
        "assets/composer-icon.png", "assets/composer-icon-dark.png", "concepts/bounded-commitment.md",
        "scripts/cleanup_legacy.py", "zzzops/concepts.py",
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
        "add-zzzops-goal", "bootstrap-zzzops-repository", "execute-zzzops", "migrate-to-zzzops",
        "review-agentic-engineering", "review-zzzops-policy", "send-zzzops-feedback", "suggest-zzzops-work",
        "validate-zzzops-installation",
    }:
        raise BundleError("plugin archive must contain exactly the nine product skills")
    missing_metadata = sorted(
        f"skills/{skill}/{relative}"
        for skill in shipped_skills
        for relative in ("SKILL.md", "agents/openai.yaml")
        if f"skills/{skill}/{relative}" not in result
    )
    if missing_metadata:
        raise BundleError("skill discovery metadata is incomplete: " + ", ".join(missing_metadata))
    try:
        concepts = package["_concepts"].load_catalog((plugin / "concepts",), require_concepts=True)
        package["_concepts"].validate_skill_documents(plugin, concepts)
    except ValueError as exc:
        raise BundleError(f"canonical concept package is invalid: {exc}") from exc
    return result


def claude_marketplace_files(root: Path, version: str) -> dict[str, bytes]:
    """Render a self-contained Claude marketplace from the canonical plugin."""
    if not SEMVER.fullmatch(version):
        raise BundleError("version must be a concrete semantic release version")
    canonical_manifest = read_json(root / "plugins" / "zzzops" / "plugin.json")
    required_manifest = {
        "name", "description", "author", "homepage", "repository", "license", "keywords",
    }
    if not isinstance(canonical_manifest, dict) or not required_manifest.issubset(canonical_manifest):
        raise BundleError("canonical plugin manifest is incomplete for Claude generation")
    for field in ("name", "description", "homepage", "repository", "license"):
        require_text(canonical_manifest[field], f"plugin.{field}")
    author = canonical_manifest["author"]
    if not isinstance(author, dict) or not require_text(author.get("name"), "plugin.author.name"):
        raise BundleError("plugin.author is incomplete")
    keywords = canonical_manifest["keywords"]
    if not isinstance(keywords, list) or not keywords or any(not require_text(item, "plugin.keywords") for item in keywords):
        raise BundleError("plugin.keywords must contain non-empty text")
    canonical = plugin_files(root, version)
    manifest_fields = (
        "name", "description", "author", "homepage", "repository", "license", "keywords",
    )
    manifest = {field: canonical_manifest[field] for field in manifest_fields}
    manifest["version"] = version
    marketplace = {
        "name": canonical_manifest["name"],
        "owner": canonical_manifest["author"],
        "metadata": {
            "description": canonical_manifest["description"],
            "version": version,
        },
        "plugins": [{
            "name": canonical_manifest["name"],
            "source": "./zzzops",
            "description": canonical_manifest["description"],
            "version": version,
            "keywords": canonical_manifest["keywords"],
            "category": "development",
            "tags": ["agentic-engineering", "coding-agents", "repository-bootstrap"],
        }],
    }
    result = {f"zzzops/{relative}": data for relative, data in canonical.items()}
    result["zzzops/.claude-plugin/plugin.json"] = canonical_json(manifest)
    result[".claude-plugin/marketplace.json"] = canonical_json(marketplace)
    for relative, data in result.items():
        scan_for_secrets(relative, data)
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


def validate_archive(data: bytes, expected: dict[str, bytes], label: str) -> None:
    try:
        temporary = io.BytesIO(data)
        with ZipFile(temporary) as archive:
            if archive.namelist() != sorted(expected):
                raise BundleError(f"{label} archive file tree is not deterministic")
            for relative, content in expected.items():
                if archive.read(relative) != content:
                    raise BundleError(f"{label} archive content mismatch: {relative}")
    except BadZipFile as exc:
        raise BundleError(f"{label} archive is not a valid ZIP") from exc


def validate_release_artifacts(directory: Path, expected: dict[str, tuple[dict[str, bytes], str]]) -> None:
    actual = {path.name for path in directory.iterdir() if path.is_file()}
    if actual != set(expected):
        missing = sorted(set(expected) - actual)
        stale = sorted(actual - set(expected))
        raise BundleError(f"release artifacts are missing or stale: missing={missing}, stale={stale}")
    for filename, (contents, label) in expected.items():
        validate_archive((directory / filename).read_bytes(), contents, label)


def build_bundle(root: Path, output: Path, version: str) -> dict[str, Path]:
    root = root.resolve()
    output = output.resolve()
    if not SEMVER.fullmatch(version):
        raise BundleError("version must be a concrete semantic release version")
    if output.exists() and any(output.iterdir()):
        raise BundleError("output directory must be empty before release preparation")
    validate_sources(root)
    plugin_contents = plugin_files(root, version)
    plugin_data = zip_bytes(plugin_contents)
    plugin_name = f"zzzops-plugin-v{version}.zip"
    validate_archive(plugin_data, plugin_contents, "plugin")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="zzzops-marketplace-", dir=output.parent))
    try:
        plugin_path = staging / plugin_name
        plugin_path.write_bytes(plugin_data)
        validate_release_artifacts(staging, {
            plugin_path.name: (plugin_contents, "written plugin"),
        })
        if output.exists():
            output.rmdir()
        staging.replace(output)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {"plugin": output / plugin_path.name}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the validated OpenAI portal skills bundle")
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parents[2]
    try:
        result = build_bundle(root, args.output, args.version)
    except (BundleError, OSError, UnicodeError) as exc:
        print(f"Marketplace bundle validation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({key: str(path) for key, path in result.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
