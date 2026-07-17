---
name: suggest-zzzops-work
description: Suggest, discover, or audit valuable ZzzOps work from project code, tests, docs, config, and state. "dry run", "preview", or "plan" is the no-write default; "apply" writes approved goals, and "refill" writes only when authorized by exhausted-queue preferences.
---

# Suggest ZzzOps Work

Run `.zzzops/rules/INITIALIZATION.md`, then `.zzzops/rules/BACKENDS.md`. Read project instructions, charter, local preferences, and canonical goals.
Run `.zzzops/rules/HEALTH.md` entry/final hooks; health never changes dry-run/apply authority.

1. Mode defaults to `dry-run`: no edits to source, Git, goals, index, or preferences. `apply` requires explicit user request or `$execute-zzzops` invocation under an enabled refill preference. Never edit/commit preferences.
2. Inspect actual architecture/entry points and relevant active code, tests/coverage evidence, user/developer/operations docs, CI/build/config, errors/observability/security/performance/accessibility, and stale/dead paths. Use focused native commands; do not run expensive suites merely for ideas.
3. Compare charter, goals, blockers/history, and trackers. Reject duplicates, generated/dependency work, speculative rewrites, cosmetic churn, and ideas without evidenced beneficiary/observable result.
4. Rank a short high-confidence list by acceptance/KPI value, risk/urgency, unlocks, confidence, difficulty, and feedback speed. For each give path/line evidence, outcome/criteria, value rationale, dependencies/blockers, baseline, observation surface, smallest chunk/probe, and estimate. No observation surface means no suggestion unless a concrete harness/debug-adapter plan exists.
5. Dry-run: report ranking and state no files changed. Apply: create only approved/authorized canonical goals using `$add-zzzops-goal` semantics and record evidence/source. Never implement while suggesting; never automate Git for capture.

Exhausted-queue apply honors independent opt-ins:

- `documentation`: missing/stale/misleading/inaccessible user, developer, or operations docs.
- `tests`: evidenced untested behavior, regression, boundary, or missing fast feedback—not percentage theater. A discovered bug becomes a separate human-blocked TODO and is not fixed before input.
- `code_quality_non_behavioral`: behavior-preserving naming, extraction/decomposition, dead/duplicate code cleanup, or monolith splitting. Require unchanged-behavior evidence; exclude features, architecture rewrites, and style churn.

Use enabled categories only; cap the entire refill at `max_goals_per_refill`, then return to `$execute-zzzops`. Ask about material ambiguity; never manufacture utilization work.
