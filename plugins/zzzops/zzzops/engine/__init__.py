"""ZzzOps engine: per-goal state branches, a pure frontier and four operations (docs/design/DESIGN.md, docs/design/SPEC.md)."""

from pathlib import Path as _Path

# SPEC §4.5: one file per capability (`capabilities/<name>.txt`), so goals add theirs without touching a shared line.
CAPABILITIES = frozenset(p.stem for p in (_Path(__file__).parent / "capabilities").glob("*.txt"))
GOAL_SCHEMAS = (1, 2)           # goal schemas this engine reads; it writes 2 only for a document with `flow` (G1025)
WORKFLOW_SCHEMA = 1
POLICY_SCHEMA = 2
FP_VERSION = "v1"

_BUILD = None


def build_id() -> str:
    """`<plugin version> <package revision[:12]>` (SPEC §3.9): the `Engine:` trailer and `--version`; `unknown` when
    the package provenance cannot be read (a write never fails for it)."""
    global _BUILD
    if _BUILD is None:
        try:
            import runpy
            prov = runpy.run_path(str(_Path(__file__).resolve().parent.parent / "package.py"))["package_provenance"]()
            _BUILD = f"{prov['version']} {prov['revision'][:12]}"
        except Exception:
            _BUILD = "unknown"
    return _BUILD
