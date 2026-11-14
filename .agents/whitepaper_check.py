#!/usr/bin/env python3
"""Manual whitepaper audit; deliberately outside test discovery and CI.

Run from the repository root:
  python3 .agents/whitepaper_check.py
  python3 .agents/whitepaper_check.py --source-only --commit <40-hex-sha>

The normal mode reads docs/WHITEPAPER.md. Labelled header lines (optional
Markdown emphasis/backticks) are Source commit, Package build, Checked date,
and Integration status. Optional Supplementary source commit, Supplementary
package build, and Supplementary status bind an unmerged extension separately.
Build values are the complete --version output, e.g. 0.0.0-dev d0738ea601d8.

Keep the reader-facing claim table in ordinary Markdown. Its machine references
live in one hidden comment, with no duplicated prose required:
  <!-- whitepaper-ledger
  [{"id":"C1", "family":"snapshot", "scope":"engine",
    "source":[{"binding":"primary", "path":"plugins/zzzops/zzzops/engine/store.py",
               "symbol":"Store"}],
    "evidence":[{"binding":"primary", "path":".agents/test_engine_store.py",
                 "symbol":"NewAndNextTests.test_new_creates_goal"}],
    "limit":"Declared state only"}]
  -->
Use actual qualified Python names (Class.method), not this illustrative example.
Source refs may instead name a numbered Markdown section via "section":"4.20".
Evidence names a test_ method/function, or {"reproduction":"card-previous"} /
{"reproduction":"next-waiting"}. Each ref defaults to binding "primary";
use "supplementary" only for unmerged-scope rows. Required families are listed
in FAMILIES below. Multiple rows per family are welcome. Scope is one of engine,
default, procedure, aim, unmerged. Every row needs a nonempty limit.

This checks binding integrity, not whether a citation proves a sentence. Human
review still covers wording, privacy, examples, authority, links and print form.
It archives pinned Git snapshots locally, runs their version command and the
two bounded production-function reproductions with existing synthetic fixtures.
No network access, dependency installation, engine edits or binding rewrites.
"""

from __future__ import annotations

import argparse
import ast
import datetime
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "plugins/zzzops/zzzops/zzzops.py"
FAMILIES = {"snapshot", "frontier", "identity", "cards", "next", "leases", "review", "sync", "delivery"}
SCOPES = {"engine", "default", "procedure", "aim", "unmerged"}
HEX = re.compile(r"[0-9a-f]{40}")

# Subprocess isolation ensures imports and fixture roots come from the archive,
# even when auditing two different source snapshots in a single invocation.
REPRODUCE = '''
import json
import test_engine_card_budget as cards
from engine.canon import canonical
from engine import render
from engine_sim import Sim
from test_engine_portfolio import ctx

card = cards.shrink(cards.implement_fixture(previous=cards.big_previous(4200)))
assert len(canonical(card)) > 4096, "card-previous exception changed; review the paper"
assert card == cards.shrink(card) and not cards.shrink_candidates(card)
sim = Sim()
sim.goal(1, state="held")
for goal in range(2, 152):
    sim.goal(goal, deps=[1])
out = render.render_next(ctx(sim), sim.eval())
assert len(out["waiting"]) == 150
assert not out["actions"] and not out["needs_human"]
assert len(canonical(out)) > 8192, "next-waiting exception changed; review the paper"
print(json.dumps({"card-previous": {"bytes": len(canonical(card)), "target": 4096,
    "previous_chars": 4200, "fixed_point": True},
    "next-waiting": {"bytes": len(canonical(out)), "target": 8192,
    "held_goals": 1, "dependents": 150, "waiting": len(out["waiting"])}}))
'''


def run(*args, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, timeout=120).stdout.decode().strip()


def git(*args):
    return run("git", *args)


def field(paper, label, required=True):
    match = re.search(r"^\s*" + re.escape(label) + r"\s*:\s*(.+?)\s*$", paper.replace("**", ""), re.M)
    if not match:
        if required:
            raise ValueError(f"missing labelled field: {label}")
        return None
    return match[1].strip("` ")


def snapshot(commit, target):
    if not HEX.fullmatch(commit):
        raise ValueError("source commit must be a full 40-hex SHA")
    if git("cat-file", "-t", commit) != "commit":
        raise ValueError(f"not a commit: {commit}")
    archive = subprocess.run(["git", "archive", commit], cwd=ROOT, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(target, filter="data")
    return run(sys.executable, PLUGIN, "--version", cwd=target)


def symbols(text):
    def walk(body, prefix=""):
        for node in body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + node.name
                yield name
                yield from walk(node.body, name + ".")
    return set(walk(ast.parse(text).body))


def reference(ref, roots, evidence=False):
    if "reproduction" in ref:
        if not evidence or ref["reproduction"] not in {"card-previous", "next-waiting"}:
            raise ValueError(f"unknown reproduction: {ref}")
        if ref.get("binding", "primary") != "primary":
            raise ValueError("size reproductions bind to primary source")
        return
    binding = ref.get("binding", "primary")
    path = Path(ref["path"])
    if binding not in roots or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"invalid binding/path: {ref}")
    file = roots[binding] / path
    if not file.is_file():
        raise ValueError(f"missing pinned path: {binding}:{path}")
    text = file.read_text(encoding="utf-8")
    if "symbol" in ref:
        name = ref["symbol"].replace("::", ".")
        if path.suffix != ".py" or name not in symbols(text):
            raise ValueError(f"missing pinned symbol: {binding}:{path}::{name}")
        if evidence and (not path.name.startswith("test_") or not name.rsplit(".", 1)[-1].startswith("test_")):
            raise ValueError(f"evidence must name an exact test method/function: {ref}")
    elif "section" in ref and not evidence:
        if not re.search(r"^#+\s+" + re.escape(ref["section"]) + r"(?:\s|$)", text, re.M):
            raise ValueError(f"missing pinned section: {binding}:{path} §{ref['section']}")
    else:
        raise ValueError(f"reference needs an exact symbol or source section: {ref}")


def ledger(paper, roots):
    match = re.search(r"<!--\s*whitepaper-ledger\s*\n(.*?)-->", paper, re.S)
    if not match:
        raise ValueError("missing hidden whitepaper-ledger JSON comment")
    rows = json.loads(match[1])
    if not isinstance(rows, list) or not rows:
        raise ValueError("claim ledger must be a nonempty JSON array")
    ids, families = set(), set()
    for row in rows:
        claim = row["id"]
        if not isinstance(claim, str) or not claim.strip() or claim in ids:
            raise ValueError(f"empty or duplicate claim id: {claim}")
        ids.add(claim)
        families.add(row["family"])
        if row["scope"] not in SCOPES or not isinstance(row["limit"], str) or not row["limit"].strip():
            raise ValueError(f"{claim}: scope and nonempty limit required")
        if row["scope"] == "unmerged" and "supplementary" not in roots:
            raise ValueError(f"{claim}: unmerged claim requires supplementary binding")
        for key in ("source", "evidence"):
            if not isinstance(row[key], list) or not row[key]:
                raise ValueError(f"{claim}: nonempty {key} list required")
            for ref in row[key]:
                if ref.get("binding", "primary") == "supplementary" and row["scope"] != "unmerged":
                    raise ValueError(f"{claim}: supplementary reference requires unmerged scope")
                reference(ref, roots, evidence=key == "evidence")
    missing = FAMILIES - families
    if "supplementary" in roots and "supplementary" not in families:
        missing.add("supplementary")
    if missing:
        raise ValueError(f"missing claim families: {', '.join(sorted(missing))}")
    print(f"Ledger: {len(rows)} claims; exact pinned references resolved")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--paper", type=Path, default=ROOT / "docs/WHITEPAPER.md")
    parser.add_argument("--source-only", action="store_true", help="audit a snapshot before the paper exists")
    parser.add_argument("--commit", help="full source SHA; required with --source-only")
    args = parser.parse_args()
    if args.source_only != bool(args.commit):
        parser.error("--source-only and --commit must be supplied together")
    paper = None if args.source_only else args.paper.read_text(encoding="utf-8")
    bindings = {"primary": (args.commit, None)} if paper is None else {
        "primary": (field(paper, "Source commit"), field(paper, "Package build"))}
    if paper is not None:
        datetime.date.fromisoformat(field(paper, "Checked date"))
        field(paper, "Integration status")
        supp = field(paper, "Supplementary source commit", required=False)
        if supp:
            bindings["supplementary"] = (supp, field(paper, "Supplementary package build"))
            field(paper, "Supplementary status")
    with tempfile.TemporaryDirectory(prefix="zzzops-whitepaper-") as tmp:
        roots = {}
        for binding, (commit, expected) in bindings.items():
            root = Path(tmp) / binding
            root.mkdir()
            roots[binding] = root
            actual = snapshot(commit, root)
            if expected is not None and actual != expected:
                raise ValueError(f"{binding} build mismatch: paper={expected!r}, source={actual!r}")
            print(f"{binding}: {commit}; package build: {actual}")
        if paper is not None:
            ledger(paper, roots)
        primary = roots["primary"]
        print("Size discrepancies: " + run(sys.executable, "-c", REPRODUCE, cwd=primary / ".agents"))
    drift = git("diff", "--name-only", bindings["primary"][0], "--", "plugins/zzzops")
    untracked = git("ls-files", "--others", "--exclude-standard", "plugins/zzzops")
    print("Plugin drift (refresh/review required):\n" + "\n".join(filter(None, (drift, untracked)))
          if drift or untracked else "Plugin drift: none")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"whitepaper check failed: {exc}", file=sys.stderr)
        sys.exit(1)
