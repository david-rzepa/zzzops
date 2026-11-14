"""Read-only current-default comparison and review receipts (SPEC §3.16)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates/default"
OID = re.compile(r"[0-9a-f]{40}")
POWERSHELL = sys.platform == "win32"


def blob_id(data):
    data = data.replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def shipped():
    return {p.relative_to(TEMPLATE_DIR).as_posix(): p.read_bytes()
            for p in sorted(Path(TEMPLATE_DIR).rglob("*")) if p.is_file()}


def read_record(data):
    if data is None:
        return None, "no_record", []
    try:
        record = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None, "invalid_record", ["TEMPLATE.json is not valid UTF-8 JSON"]
    if isinstance(record, dict) and type(record.get("schema")) is int and record["schema"] > 1:
        return None, "newer_record", []
    errors = []
    if not isinstance(record, dict):
        return None, "invalid_record", ["TEMPLATE.json must be an object"]
    if set(record) - {"schema", "template", "files", "removed"}:
        errors.append("TEMPLATE.json has unknown keys")
    if type(record.get("schema")) is not int or record["schema"] != 1 or record.get("template") != "default":
        errors.append("TEMPLATE.json needs schema 1 and template default")
    for field in ("files", "removed"):
        values = record.get(field, {} if field == "removed" else None)
        if not isinstance(values, dict):
            errors.append(f"{field} must map safe relative paths to blob ids")
            continue
        for path, oid in values.items():
            if (not isinstance(path, str) or not path or "\\" in path or ":" in path
                    or any(part in ("", ".", "..") for part in path.split("/")) or any(ord(c) < 32 for c in path)):
                errors.append(f"unsafe {field} path: {path!r}")
            if not (oid is None and field == "files") and not (isinstance(oid, str) and OID.fullmatch(oid)):
                errors.append(f"{field}.{path}: expected a lowercase 40-hex blob id")
    if isinstance(record.get("files"), dict) and isinstance(record.get("removed", {}), dict):
        if set(record["files"]) & set(record.get("removed", {})):
            errors.append("a path cannot be in both files and removed")
    return (None, "invalid_record", errors) if errors else (record, "update", [])


def compare(record, local, ids):
    files = record["files"] if record else {}
    removed = record.get("removed", {}) if record else {}
    rows = []
    for path in sorted(set(ids) | set(files) | set(removed)):
        source = ids.get(path)
        base = files.get(path)
        content = local.get(path)
        here = blob_id(content) if content is not None else None
        # A legacy tombstone records absence, not an archived version to restore.
        if path in removed and source is None:
            continue
        if path in files and (base == source or (base is None and here == source)):
            continue
        if path not in files:
            upstream, state = "added", "absent" if here is None else "changed"
        else:
            upstream = "changed" if source else "removed"
            state = ("unknown" if base is None else "deleted" if here is None
                     else "unchanged" if here == base else "changed")
        rows.append((path, upstream, state))
    return rows


def shell(*args):
    if POWERSHELL:
        return "& " + " ".join("'" + str(a).replace("'", "''") + "'" for a in args)
    return " ".join(shlex.quote(str(a)) for a in args)


def cli_shell(prefix, *args):
    if POWERSHELL and not os.environ.get("ZZZOPS_PREFIX"):
        return shell(sys.executable, Path(__file__).resolve().parents[1] / "zzzops.py", *args)
    # An explicit ZZZOPS_PREFIX is trusted caller-supplied shell syntax.
    tail = (" ".join("'" + str(a).replace("'", "''") + "'" for a in args) if POWERSHELL else shell(*args))
    return prefix + " " + tail


def item(local, raw_record, prefix, directory, full):
    current = shipped()
    ids = {p: blob_id(data) for p, data in current.items()}
    record, kind, errors = read_record(raw_record)
    template = hashlib.sha256("".join(f"{p}\0{oid}\n" for p, oid in sorted(ids.items())).encode()).hexdigest()[:12]
    if kind == "newer_record":
        return {"kind": kind, "message": "Default record written by a newer engine: upgrade the plugin to see default updates.",
                "template": template, **({} if full else {"expand": cli_shell(prefix, "validate")})}
    rows = compare(record, local, ids)
    if not rows and kind == "update":
        return None
    edited = sum(state in ("changed", "unknown", "deleted") for _, _, state in rows)
    message = (f"The shipped default policy differs from this repository's last review: {len(rows)} files "
               f"({edited} also edited here). Review or decline through a zzzops/policy/* branch "
               "(bootstrap skill, Update from the shipped defaults); other work is not blocked.")
    if kind in ("no_record", "invalid_record"):
        message = ("No default-policy record exists. " if kind == "no_record" else "The default-policy record is invalid. ") + message
    result = {"kind": kind, "message": message, "template": template}
    if not full:
        result.update(counts={"files": len(rows), "edited_here": edited}, files=[str(Path(directory) / p) for p, *_ in rows[:10]],
                      expand=cli_shell(prefix, "validate"))
        return result
    result["files"] = []
    for path, upstream, state in rows:
        local_path = Path(directory) / path
        new = Path(TEMPLATE_DIR).resolve() / path
        row = {"path": str(local_path), "upstream": upstream, "local": state}
        if upstream == "removed":
            manual = "absent from current defaults; decide manually whether to keep this local choice"
        elif path not in local:
            manual = "absent locally; inspect the current default and decide manually whether to retain that absence"
        else:
            manual = "compare local and current defaults; choose any edits manually"
        row["apply"] = {"manual": manual}
        if path in local and path in ids:
            row["diff"] = shell("git", "diff", "--no-index", "--", local_path, new)
        result["files"].append(row)
    result["record"] = {"path": str(Path(directory) / "TEMPLATE.json"),
                        "reviewed": {"schema": 1, "template": "default", "files": ids}}
    if errors:
        result["errors"] = errors
    result["see"] = str(Path(__file__).resolve().parents[1] / "references/MIGRATING.md") + " (read the workflow.json section before merging)"
    result["recheck"] = cli_shell(prefix, "validate", "--policy", "--dir", directory)
    return result


def policy_file(path):
    return path in ("POLICY.json", "workflow.json") or path.startswith("prompts/")


def read_local(session):
    P = session.snap.policy_commit
    paths = session.git.run("ls-tree", "-r", "--name-only", "-z", P, "--", ".zzzops").stdout.split("\0")
    return {path[len(".zzzops/"):]: session.git.cat(f"{P}:{path}") for path in paths
            if path.startswith(".zzzops/") and not any(ord(c) < 32 for c in path)
            and policy_file(path[len(".zzzops/"):])}


def merge_markers(local, directory):
    return [{"kind": "policy_merge_markers", "message": f"{Path(directory) / path} holds merge conflict markers: resolve them before landing"}
            for path, data in sorted(local.items()) if data is not None
            and any(line.startswith((b"<<<<<<< ", b">>>>>>> ")) for line in data.splitlines())]


def status(session, full=False):
    try:
        if session.state.settings is None:
            return None
        from engine.session import cli_prefix
        local = read_local(session)
        raw = session.git.cat(f"{session.snap.policy_commit}:.zzzops/TEMPLATE.json")
        return item(local, raw, cli_prefix(), ".zzzops", full)
    except Exception:                           # advisory; damaged/mixed plugin installs never fail a verb
        return None


def status_dir(directory):
    try:
        from engine.session import cli_prefix
        directory = Path(directory)
        local = {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*")
                 if p.is_file() and policy_file(p.relative_to(directory).as_posix())}
        record = directory / "TEMPLATE.json"
        return item(local, record.read_bytes() if record.is_file() else None, cli_prefix(), directory, True)
    except Exception:
        return None


def warnings(session=None, directory=None):
    try:
        if session is not None:
            return merge_markers(read_local(session), ".zzzops")
        directory = Path(directory)
        local = {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*")
                 if p.is_file() and policy_file(p.relative_to(directory).as_posix())}
        return merge_markers(local, directory)
    except Exception:
        return []
