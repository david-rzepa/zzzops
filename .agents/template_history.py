#!/usr/bin/env python3
"""Preserve shipped template versions: run --write whenever a default changes.

History is append-only and deduplicated by normalised Git blob id. A removed
file name must never be reused for a re-added default: choose a new name,
because older engines treat a recognised tombstone as reviewed. --seed-ref is
for the initial seed from published dev history; normal upkeep reads only the
current files and needs no Git history (so it also works in source bundles).
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REL = "plugins/zzzops/zzzops/templates/default"
TEMPLATE = ROOT / REL
HISTORY = TEMPLATE.parent / "history"


def content_id(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="append missing current template versions")
    parser.add_argument("--seed-ref", help="also preserve every template version reachable from this Git ref")
    args = parser.parse_args()
    versions = {(p.suffix, p.read_bytes().replace(b"\r\n", b"\n")) for p in TEMPLATE.rglob("*") if p.is_file()}
    if args.seed_ref:
        def git(*argv):
            return subprocess.check_output(["git", "-C", str(ROOT), *argv])
        commits = git("log", "--format=%H", args.seed_ref, "--", REL).decode().splitlines()
        blobs = set()
        for commit in commits:
            for entry in git("ls-tree", "-r", "-z", commit, "--", REL).split(b"\0"):
                if not entry:
                    continue
                obj, path = entry.split(b"\t", 1)
                _, kind, oid = obj.split()
                if kind == b"blob":
                    blobs.add((Path(path.decode()).suffix, oid.decode()))
        versions.update((ext, git("cat-file", "blob", oid).replace(b"\r\n", b"\n")) for ext, oid in blobs)
    missing = []
    for ext, data in sorted(versions):
        path = HISTORY / (content_id(data) + ext)
        if path.exists():
            if path.read_bytes().replace(b"\r\n", b"\n") != data:
                raise SystemExit(f"History content mismatch: {path}; never replace a published base")
            continue
        missing.append(path.name)
        if args.write:
            HISTORY.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print(f"{len(versions)} distinct template versions; {len(missing)} " + ("added" if args.write else "missing"))
    return 0 if args.write or not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
