"""Reproduce the bounded ZzzOps concept-migration inventory and score."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SURFACES = (ROOT / "AGENTS.md", ROOT / "plugins" / "zzzops" / "skills", ROOT / "plugins" / "zzzops" / "rules",
            ROOT / "plugins" / "zzzops" / "templates", ROOT / "docs")
CANDIDATES = {
    "bounded commitment": (520, 0.20, 0, 0, 90),
    "exact head": (260, 0.15, 0, 10, 80),
    "safe useful work": (330, 0.20, 10, 20, 90),
    "effective engineering rigor": (420, 0.20, 20, 25, 100),
    "actionable": (300, 0.45, 80, 35, 50),
    "goal-sized change": (260, 0.55, 40, 15, 40),
    "falsifiable probe": (300, 0.55, 30, 10, 50),
    "durable blocker": (360, 0.60, 60, 40, 60),
    "authority boundary": (420, 0.65, 90, 100, 80),
    "reviewed checkpoint": (350, 0.55, 80, 60, 70),
    "hot path": (260, 0.70, 70, 20, 40),
    "progressive disclosure": (330, 0.65, 50, 20, 60),
}
MIGRATED = {"bounded commitment", "exact head", "safe useful work", "effective engineering rigor"}
VAGUE_TERMS = {
    "reversible": {"disposition": "pending-user-owned-overlap", "replacement": "bounded commitment"},
    "revertible": {"disposition": "replaced", "replacement": "bounded commitment"},
    "simple": {"disposition": "retain-contextually", "replacement": None},
    "small": {"disposition": "retain-contextually", "replacement": None},
    "safe": {"disposition": "retain-contextually", "replacement": "safe useful work when used as an execution gate"},
    "appropriate": {"disposition": "retain-contextually", "replacement": None},
    "reasonable": {"disposition": "retain-contextually", "replacement": None},
}


def documents() -> list[Path]:
    result: list[Path] = []
    for surface in SURFACES:
        result.extend([surface] if surface.is_file() else surface.rglob("*.md"))
    return sorted(path for path in set(result) if path != ROOT / "docs" / "CONCEPT_MIGRATION.md")


def route_weight(path: Path) -> int:
    relative = path.relative_to(ROOT).as_posix()
    if relative == "AGENTS.md":
        return 100
    if "/rules/" in relative:
        return 15
    if relative.endswith("/SKILL.md"):
        return 10
    if "/skills/execute-zzzops/references/" in relative:
        return 8
    if "/templates/" in relative:
        return 2
    return 1


def inventory() -> dict[str, object]:
    rows = []
    files = documents()
    concepts_root = ROOT / "plugins" / "zzzops" / "concepts"
    for term, (definition_size, read_rate, divergence, authority, maintenance) in CANDIDATES.items():
        pattern = re.compile(rf"(?<![\w-]){re.escape(term)}(?![\w-])", re.IGNORECASE)
        hits = []
        weighted = 0
        for path in files:
            count = len(pattern.findall(path.read_text(encoding="utf-8-sig")))
            if count:
                hits.append({"path": path.relative_to(ROOT).as_posix(), "occurrences": count})
                weighted += count * route_weight(path)
        definition = concepts_root / (term.replace(" ", "-") + ".md")
        cold_bytes = definition.stat().st_size if definition.exists() else definition_size
        link_overhead = 18 + len(term.replace(" ", "-"))
        score = round(weighted * definition_size - cold_bytes * read_rate - len(hits) * link_overhead
                      - divergence - authority + maintenance, 2)
        rows.append({"term": term, "occurrences": sum(hit["occurrences"] for hit in hits),
                     "documents": hits, "weighted_load": weighted, "definition_bytes": cold_bytes,
                     "expected_read_rate": read_rate, "link_overhead_bytes": link_overhead,
                     "semantic_divergence_penalty": divergence, "authority_sensitivity_penalty": authority,
                     "maintenance_value": maintenance, "score": score,
                     "disposition": "migrated" if term in MIGRATED else "retained"})
    vague_rows = []
    for term, decision in VAGUE_TERMS.items():
        pattern = re.compile(rf"(?<![\w-]){re.escape(term)}(?![\w-])", re.IGNORECASE)
        hits = []
        for path in files:
            count = len(pattern.findall(path.read_text(encoding="utf-8-sig")))
            if count:
                hits.append({"path": path.relative_to(ROOT).as_posix(), "occurrences": count})
        vague_rows.append({"term": term, "occurrences": sum(hit["occurrences"] for hit in hits),
                           "documents": hits, **decision})
    return {"schema_version": 1, "generated_distributions": "derived from canonical plugin sources",
            "stopping_rule": "migrate only repeated stable terms with positive score and no unresolved semantic or authority ambiguity",
            "candidates": rows, "vague_language_audit": vague_rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    print(json.dumps(inventory(), indent=None if args.compact else 2, sort_keys=True))
