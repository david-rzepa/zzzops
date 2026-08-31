#!/usr/bin/env python3
"""Classify policy-default context and reject operational defaults in routed prompts."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROMPT_STATS_PATH = ROOT / ".agents" / "prompt_stats.py"
SPEC = importlib.util.spec_from_file_location("zzzops_prompt_stats_inventory", PROMPT_STATS_PATH)
assert SPEC and SPEC.loader
prompt_stats = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prompt_stats
SPEC.loader.exec_module(prompt_stats)

COLD_ONLY_PROMPT_PATHS = {"plugins/zzzops/skills/review-zzzops-policy/SKILL.md"}
DEFAULT_CATALOG_PATH = "plugins/zzzops/zzzops/templates/project-goals/INIT_PLAN.json"
PUBLIC_DOCUMENTATION_ROOT = "docs"
RUNTIME_ROOT = "plugins/zzzops/zzzops"

FORBIDDEN_HOT_PHRASES = {
    "artifact_handling_fallback": "when it does not specify artifact handling",
    "dependency_done_fallback": "dependencies default to `done` before writes",
    "branch_done_fallback": "fallback waits for `done`",
    "blocker_order_fallback": "fallback: safety/access/human",
    "execution_reports_default": "execution_reports.enabled` defaults true",
    "parallelism_default": "default measures git-tracked bytes",
    "resource_exclusivity_default": "paths/integration default advisory",
}

ALLOWED_CATALOG_OCCURRENCES = {
    ("capture_and_ask", "plugins/zzzops/skills/suggest-zzzops-work/SKILL.md"): "selected-value interpreter",
    ("code_quality_non_behavioral", "plugins/zzzops/skills/execute-zzzops/references/ENTROPY_OBSERVATIONS.md"): "runtime category schema",
    ("code_quality_non_behavioral", "plugins/zzzops/skills/suggest-zzzops-work/SKILL.md"): "selected-value interpreter",
    ("agent_observability", "plugins/zzzops/zzzops/entropy.py"): "runtime category schema",
    ("agent_observability", "plugins/zzzops/skills/suggest-zzzops-work/SKILL.md"): "selected-value interpreter",
    ("agent_observability", "plugins/zzzops/skills/execute-zzzops/references/ENTROPY_OBSERVATIONS.md"): "runtime category schema",
    ("human_at_exhaustion", "plugins/zzzops/skills/execute-zzzops/references/BRANCH_REVIEW.md"): "selected-value interpreter",
    ("human_at_exhaustion", "plugins/zzzops/skills/execute-zzzops/references/REVIEW_QUEUE.md"): "selected-value interpreter",
    ("github_issues", "plugins/zzzops/rules/BACKENDS.md"): "runtime backend schema",
    ("resume_once_and_reprioritize", "plugins/zzzops/rules/CONTINUATION.md"): "selected-value interpreter",
    ("same_task_until_superseded", "plugins/zzzops/rules/CONTINUATION.md"): "selected-value interpreter",
    ("stack_from_reviewed_checkpoint", "plugins/zzzops/rules/GOAL_SYSTEM.md"): "selected-value interpreter",
    ("stack_from_reviewed_checkpoint", "plugins/zzzops/skills/execute-zzzops/references/BRANCH_REVIEW.md"): "selected-value interpreter",
    ("stack_from_reviewed_checkpoint", "plugins/zzzops/skills/execute-zzzops/references/REVIEW_QUEUE.md"): "selected-value interpreter",
}

CLASSIFIED_FAMILIES = {
    "artifact_verification": "PROJECT value plus interpreter; no missing-policy fallback",
    "dependency_gating": "PROJECT value plus ancestry invariant; no done fallback",
    "resource_parallelism": "PROJECT value plus mode interpreter; measurement is evidence only",
    "blocker_order": "PROJECT value; missing policy routes to review",
    "execution_reports": "PROJECT boolean; missing policy routes to review",
    "refill_categories": "PROJECT list; missing policy routes to review",
    "review_modes": "PROJECT values interpreted in the review queue; recommendation stays cold",
    "workflow_invocation_modes": "skill interface and safety semantics, not project policy",
    "authority_and_verification": "invariant; never weakened by policy",
}


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def hot_prompt_paths(root: Path = ROOT) -> list[Path]:
    return [
        path for path in prompt_stats.prompt_files(root)
        if _relative(path, root) not in COLD_ONLY_PROMPT_PATHS
    ]


def _catalog(root: Path) -> dict[str, Any]:
    plan = json.loads((root / DEFAULT_CATALOG_PATH).read_text(encoding="utf-8-sig"))
    return {
        section["id"]: {"decision": section["decision"], "settings": section["settings"]}
        for section in plan["policy"]["sections"]
    }


def _markers(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for item in value.values():
            result.update(_markers(item))
    elif isinstance(value, list):
        for item in value:
            result.update(_markers(item))
    elif isinstance(value, str) and (("_" in value and len(value) >= 12) or len(value) >= 24):
        result.add(value.casefold())
    return result


def inventory(
    root: Path = ROOT, *, catalog: dict[str, Any] | None = None,
    hot_texts: dict[str, str] | None = None,
) -> dict[str, Any]:
    if hot_texts is None:
        hot_texts = {
            _relative(path, root): path.read_text(encoding="utf-8")
            for path in hot_prompt_paths(root)
        }
    catalog = _catalog(root) if catalog is None else catalog
    markers = sorted(_markers(catalog))
    occurrences = []
    unclassified = []
    for marker in markers:
        for path, content in sorted(hot_texts.items()):
            if marker not in content.casefold():
                continue
            classification = ALLOWED_CATALOG_OCCURRENCES.get((marker, path))
            item = {"value": marker, "path": path, "classification": classification}
            occurrences.append(item)
            if classification is None:
                unclassified.append(item)
    forbidden = []
    for family, phrase in FORBIDDEN_HOT_PHRASES.items():
        for path, content in sorted(hot_texts.items()):
            if phrase in content.casefold():
                forbidden.append({"family": family, "phrase": phrase, "path": path})
    hot_bytes = sum(prompt_stats.canonical_size(text.encode("utf-8")) for text in hot_texts.values())
    cold_review_paths = set(prompt_stats.WORKFLOW_PROMPTS["policy-review"]) | {DEFAULT_CATALOG_PATH}
    return {
        "boundary": {
            "hot_prompt_paths": sorted(hot_texts),
            "cold_policy_review_paths": sorted(cold_review_paths),
            "cold_only_paths": sorted(COLD_ONLY_PROMPT_PATHS | {DEFAULT_CATALOG_PATH}),
            "public_documentation_root": PUBLIC_DOCUMENTATION_ROOT,
            "runtime_schema_interpreter_root": RUNTIME_ROOT,
        },
        "classified_families": CLASSIFIED_FAMILIES,
        "static_hot_bytes": hot_bytes,
        "catalog_occurrences": occurrences,
        "unclassified_catalog_occurrences": unclassified,
        "forbidden_hot_defaults": forbidden,
        "valid": not unclassified and not forbidden,
    }


def validate(root: Path = ROOT) -> dict[str, Any]:
    report = inventory(root)
    if not report["valid"]:
        problems = report["unclassified_catalog_occurrences"] + report["forbidden_hot_defaults"]
        raise ValueError("hot-path policy default leakage: " + json.dumps(problems, sort_keys=True))
    return report


if __name__ == "__main__":
    print(json.dumps(validate(), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
