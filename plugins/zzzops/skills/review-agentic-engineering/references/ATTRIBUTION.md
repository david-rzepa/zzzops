# Evidence and attribution

## Select evidence

Use completed software-agent work, not prompt length or style. Prefer the original request, clarifications, blockers, corrections, replanning, scope changes, acceptance/verification failures, and final outcome already visible in the current environment. Inspect repository context the agent had or should reasonably have found. Never persist or quote raw prompts, goal text, code, paths, secrets, or domain facts for this review.

A normal review needs at least three substantial completions. One completion is enough only when it contains a strong repeated pattern. A substantial completion exercised a meaningful outcome and acceptance boundary; trivial edits and abandoned starts do not count.

## Build bounded input

Create a temporary JSON file outside the repository for `<python> <zzzops-cli> coaching attribute --input <file>`, then remove it. Use only this schema:

```json
{"schema_version":1,"completions":[{"substantial":true,"effective_rigor":"structured","observations":[{"signal":"specification_acceptance_subjective","context":"not_available","occurrences":2}]}]}
```

`effective_rigor` is `vibe`, `structured`, `agentic`, or `unknown`. Use the reviewed goal value when present. Otherwise derive a level only from explicit task stakes; preserve `unknown` when evidence does not support one. Rigor-specific observations are ignored when the effective level is lower or unknown.

`context` is one of `not_available`, `static_available`, `static_missing`, `dynamic_available`, `dynamic_missing`, `reasonably_discoverable`, `not_applicable`, or `unknown`.

Signals are bounded:

- specification: `specification_outcome_ambiguous`, `specification_acceptance_subjective`, `specification_constraint_missing`, `agentic_risk_behavior_unspecified`;
- static context: `repeated_repository_fact`;
- dynamic context: `specialist_procedure_missing`;
- tooling: `missing_guardrail`, `prose_only_invariant`;
- verification: `canonical_verification_incomplete`, `acceptance_evidence_missing`;
- implementation: `implementation_defect`, `regression_introduced`;
- external: `external_service_failure`, `permission_or_provider_failure`.

Do not add free-text fields or identifiers. The interface rejects unknown fields and emits only aggregate codes/counts. It writes no repository or ZzzOps state.

## Interpret and coach

When `status` is `insufficient_evidence`, give no improvement unless the result identifies a strong repeated pattern. Do not resolve `ambiguous` candidates by guessing.

At most two determinate attributions may become observations:

- `prompt_specification_gap`: suggest a more observable outcome, example, constraint, delegation boundary, or definition of done. Only entries with `user_coaching_candidate: true` support this advice.
- `static_repository_context_gap`: recommend concise `AGENTS.md`, project policy, or architecture context; prefer deterministic enforcement for must-not-forget rules.
- `dynamic_context_or_skill_gap`: recommend a specialist skill/reference or context index.
- `tooling_or_guardrail_gap`: recommend the relevant test, static rule, schema, CI gate, or deterministic guardrail.
- `verification_gap`: improve canonical verification, tests, evals, or observable acceptance evidence.
- `implementation_error`: treat it as agent correction and regression-prevention work, not prompting advice.
- `external_failure`: recommend recovery/coordination only; do not infer a specification lesson.

Prefer patterns with broader downstream benefit and stronger evidence. State observed evidence separately from inference. A short request is excellent when repository context and verification make intent clear; do not reward verbosity.
