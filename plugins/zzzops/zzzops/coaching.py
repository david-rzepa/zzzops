#!/usr/bin/env python3
"""Bounded, privacy-safe attribution for completed software-agent work."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


COACHING_SCHEMA_VERSION = 1
ENGINEERING_RIGOR = {"vibe": 0, "structured": 1, "agentic": 2}
CONTEXT_STATES = {
    "not_available", "static_available", "static_missing", "dynamic_available",
    "dynamic_missing", "reasonably_discoverable", "not_applicable", "unknown",
}
COACHING_SIGNAL_CATEGORIES = {
    "specification_outcome_ambiguous": "prompt_specification_gap",
    "specification_acceptance_subjective": "prompt_specification_gap",
    "specification_constraint_missing": "prompt_specification_gap",
    "agentic_risk_behavior_unspecified": "prompt_specification_gap",
    "repeated_repository_fact": "static_repository_context_gap",
    "specialist_procedure_missing": "dynamic_context_or_skill_gap",
    "missing_guardrail": "tooling_or_guardrail_gap",
    "prose_only_invariant": "tooling_or_guardrail_gap",
    "canonical_verification_incomplete": "verification_gap",
    "acceptance_evidence_missing": "verification_gap",
    "implementation_defect": "implementation_error",
    "regression_introduced": "implementation_error",
    "external_service_failure": "external_failure",
    "permission_or_provider_failure": "external_failure",
}
SIGNAL_MINIMUM_RIGOR = {
    "specification_acceptance_subjective": "structured",
    "agentic_risk_behavior_unspecified": "agentic",
}
CATEGORY_DESTINATIONS = {
    "prompt_specification_gap": ("user_coaching",),
    "static_repository_context_gap": ("agents_md", "project_policy", "architecture_context"),
    "dynamic_context_or_skill_gap": ("specialist_skill_or_reference", "context_index"),
    "tooling_or_guardrail_gap": ("deterministic_guardrail", "ci_or_static_analysis"),
    "verification_gap": ("canonical_verification", "tests_or_evals"),
    "implementation_error": ("implementation_correction", "regression_test"),
    "external_failure": ("external_recovery",),
}


def _bounded_occurrences(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 1_000_000:
        raise ValueError("observation.occurrences must be an integer from 1 to 1000000")
    return value


def _contextual_category(signal: str, context: str) -> tuple[str | None, tuple[str, ...]]:
    category = COACHING_SIGNAL_CATEGORIES[signal]
    if category == "prompt_specification_gap":
        if context == "unknown":
            return None, ("implementation_error", "prompt_specification_gap")
        if context == "static_missing":
            return "static_repository_context_gap", ()
        if context == "dynamic_missing":
            return "dynamic_context_or_skill_gap", ()
        if context in {"static_available", "dynamic_available", "reasonably_discoverable"}:
            return "implementation_error", ()
    elif category == "static_repository_context_gap":
        if context == "unknown":
            return None, ("implementation_error", "static_repository_context_gap")
        if context in {"static_available", "reasonably_discoverable"}:
            return "implementation_error", ()
    elif category == "dynamic_context_or_skill_gap":
        if context == "unknown":
            return None, ("dynamic_context_or_skill_gap", "implementation_error")
        if context in {"dynamic_available", "reasonably_discoverable"}:
            return "implementation_error", ()
    return category, ()


def attribute_agent_work(request: Any) -> dict[str, Any]:
    """Attribute bounded observations without echoing or retaining source content."""
    if not isinstance(request, dict) or set(request) != {"schema_version", "completions"}:
        raise ValueError("attribution request must contain only schema_version and completions")
    if request.get("schema_version") != COACHING_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {COACHING_SCHEMA_VERSION}")
    completions = request.get("completions")
    if not isinstance(completions, list) or len(completions) > 1_000:
        raise ValueError("completions must be a list of at most 1000 bounded records")

    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"occurrences": 0, "completions": set(), "signals": set()}
    )
    ambiguous: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = defaultdict(
        lambda: {"occurrences": 0, "completions": set()}
    )
    signal_occurrences: dict[str, int] = defaultdict(int)
    substantial_completions = 0
    ignored = 0

    for completion_index, completion in enumerate(completions):
        if not isinstance(completion, dict):
            raise ValueError("each completion must be an object")
        unknown = sorted(set(completion) - {"substantial", "effective_rigor", "observations"})
        missing = sorted({"substantial", "effective_rigor", "observations"} - set(completion))
        if unknown:
            raise ValueError("unknown completion fields: " + ", ".join(unknown))
        if missing:
            raise ValueError("missing completion fields: " + ", ".join(missing))
        if not isinstance(completion["substantial"], bool):
            raise ValueError("completion.substantial must be boolean")
        rigor = completion["effective_rigor"]
        if rigor not in ENGINEERING_RIGOR:
            raise ValueError("completion.effective_rigor is invalid")
        observations = completion["observations"]
        if not isinstance(observations, list) or not 1 <= len(observations) <= 100:
            raise ValueError("completion.observations must contain 1 to 100 bounded observations")
        substantial_completions += int(completion["substantial"])

        for observation in observations:
            if not isinstance(observation, dict) or set(observation) != {"signal", "context", "occurrences"}:
                raise ValueError("observation must contain only signal, context, and occurrences")
            signal, context = observation["signal"], observation["context"]
            if signal not in COACHING_SIGNAL_CATEGORIES:
                raise ValueError("observation.signal is invalid")
            if context not in CONTEXT_STATES:
                raise ValueError("observation.context is invalid")
            occurrences = _bounded_occurrences(observation["occurrences"])
            minimum = SIGNAL_MINIMUM_RIGOR.get(signal, "vibe")
            if ENGINEERING_RIGOR[rigor] < ENGINEERING_RIGOR[minimum]:
                ignored += 1
                continue
            signal_occurrences[signal] += occurrences
            category, candidates = _contextual_category(signal, context)
            if category is None:
                key = (signal, tuple(sorted(candidates)))
                ambiguous[key]["occurrences"] += occurrences
                ambiguous[key]["completions"].add(completion_index)
                continue
            grouped[category]["occurrences"] += occurrences
            grouped[category]["completions"].add(completion_index)
            grouped[category]["signals"].add(signal)

    repeated_pattern = any(count >= 2 for count in signal_occurrences.values())
    if substantial_completions >= 3:
        status, basis = "ready", "three_substantial_completions"
    elif repeated_pattern:
        status, basis = "ready", "strong_repeated_pattern"
    else:
        status, basis = "insufficient_evidence", "insufficient_evidence"

    attributions = []
    for category in sorted(grouped):
        value = grouped[category]
        attributions.append({
            "category": category,
            "completion_count": len(value["completions"]),
            "occurrences": value["occurrences"],
            "signals": sorted(value["signals"]),
            "destinations": list(CATEGORY_DESTINATIONS[category]),
            "user_coaching_candidate": status == "ready" and category == "prompt_specification_gap",
        })
    ambiguous_output = [
        {
            "signal": signal,
            "candidates": list(candidates),
            "completion_count": len(value["completions"]),
            "occurrences": value["occurrences"],
        }
        for (signal, candidates), value in sorted(ambiguous.items())
    ]
    return {
        "schema_version": COACHING_SCHEMA_VERSION,
        "status": status,
        "basis": basis,
        "substantial_completions": substantial_completions,
        "attributions": attributions,
        "ambiguous": ambiguous_output,
        "ignored_observations": ignored,
    }
