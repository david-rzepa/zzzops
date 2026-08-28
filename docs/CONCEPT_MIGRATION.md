# Concept migration report

Goal #334 audited repeated operational vocabulary after the bounded-commitment, exhaustion-review, and bootstrap changes. Reproduce the inventory with `python3 .agents/concept_inventory.py`.

## Method

The inventory scans `AGENTS.md`, canonical plugin skills and rules, templates, and agent-facing documentation. Codex and Claude distributions are derived from those canonical plugin sources and are validated by their package tests; generated copies are not edited or double-counted.

Each candidate records exact boundary-matched occurrences, document paths, routed-load weight, estimated repeated-definition bytes, cold definition bytes, expected on-demand read rate, concept-link overhead, semantic-divergence penalty, authority-sensitivity penalty, and maintenance value. The deterministic score is:

```text
weighted_load × repeated_definition_bytes
− cold_definition_bytes × expected_read_rate
− bound_document_count × link_overhead_bytes
− divergence_penalty − authority_penalty + maintenance_value
```

The stopping rule migrates only repeated stable terms with a positive score and no unresolved semantic or authority ambiguity. A high numeric score cannot override that semantic gate.

The same command performs a separate vague-language audit. It boundary-matches qualifiers such as `reversible`, `revertible`, `simple`, `small`, `safe`, `appropriate`, and `reasonable` even when they are not proposed concept terms. Each receives an explicit replacement or contextual-retention disposition. This prevents an imprecise phrase from escaping review merely because it is infrequent.

## Result

Migrated definitions:

- `bounded commitment`: replaces the vague Git-revert interpretation with a one-goal recovery and fan-out test.
- `exact head`: centralizes immutable checkpoint identity and stale-evidence invalidation.
- `safe useful work`: centralizes the authorization, value, observability, and non-invalidating-assumption test used by execution and bootstrap.
- `effective engineering rigor`: centralizes per-goal derivation, escalation, and minimum-preservation behavior used by capture and execution.

Retained candidates include `actionable`, `goal-sized change`, `falsifiable probe`, `durable blocker`, `authority boundary`, `reviewed checkpoint`, `hot path`, and `progressive disclosure`. Exact occurrences were absent or sparse, wording carried document-local nuance, or extraction risked hiding authority and blocker procedures. They remain inventory rows so later changes can alter the evidence without silently changing the stopping rule.

The vague-language audit confirms that `revertible` has no remaining occurrence and replaces its root-instruction use with `bounded commitment`. One `reversible` occurrence remains explicitly reported in `docs/ACCEPTANCE_TEST_PLAN.md`; that file has an overlapping user-owned working-tree edit, so this goal retains it rather than overwriting or silently resolving the user's change. Its disposition is `pending-user-owned-overlap`, with `bounded commitment` recorded as the intended replacement. Other qualifiers remain only where their local noun, threshold, or procedure supplies the meaning; `safe` binds to `safe useful work` when it acts as the execution-continuation gate. A future occurrence changes the reproducible audit rather than passing unnoticed.

The pre-migration routed baseline was 625 estimated tokens always-loaded, 3,322 capture, and 8,251 execution. The post-migration values are 624 always-loaded, 3,303 capture, and 8,233 execution. Cold concept definitions total 7,744 advisory bytes, including 5,512 new bytes, and are loaded only when a document explicitly links them. No enforced budget was raised.
