"""Shared fixtures for the engine tests (IMPLEMENTATION_PLAN §1.2)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_CODE = ROOT / "plugins" / "zzzops" / "zzzops"
TEMPLATES = PLUGIN_CODE / "templates" / "default"
if str(PLUGIN_CODE) not in sys.path:
    sys.path.insert(0, str(PLUGIN_CODE))

DEFAULT_NODES = ["design", "review_design", "approve_design", "base", "test_design", "review_tests", "implement",
                 "run_tests", "review_impl", "integrate", "approve_merge", "merge"]
RENAME = {n: f"n{i + 1:02d}_{chr(ord('a') + i)}" for i, n in enumerate(DEFAULT_NODES)}


def load_template(name: str) -> dict:
    return json.loads((TEMPLATES / name).read_text(encoding="utf-8"))


def prompt_exists(name: str) -> bool:
    return (TEMPLATES / "prompts" / name).is_file()


def renamed_workflow(wf: dict | None = None, mapping: dict | None = None) -> dict:
    """A copy of the workflow with every node id renamed, selectors and references included (DESIGN §10 item 3)."""
    wf = copy.deepcopy(wf or load_template("workflow.json"))
    mapping = mapping or RENAME

    def sel(text):
        parts = text.split(".")
        if parts[0] == "deps":
            parts[1] = mapping.get(parts[1], parts[1])
        elif parts[0] != "goal":
            parts[0] = mapping.get(parts[0], parts[0])
        return ".".join(parts)

    for g in wf["graphs"].values():
        g["terminal"] = [mapping.get(t, t) for t in g["terminal"]]
        nodes = {}
        for n, nd in g["nodes"].items():
            for spec in (nd.get("inputs") or {}).values():
                spec["from"] = sel(spec["from"])
            if "review" in nd:
                nd["review"]["subject"] = mapping.get(nd["review"]["subject"], nd["review"]["subject"])
            if "preserve" in nd:
                nd["preserve"] = mapping.get(nd["preserve"], nd["preserve"])
            nodes[mapping.get(n, n)] = nd
        g["nodes"] = nodes
    return wf
