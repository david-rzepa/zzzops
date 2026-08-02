---
name: suggest-zzzops-work
description: Suggest, discover, or audit valuable ZzzOps work from project code, tests, docs, config, and state. "dry run", "preview", or "plan" is the no-write default; "apply" writes approved goals, and "refill" writes only when authorized by reviewed exhausted-queue policy.
---

# Suggest ZzzOps Work

Run `.zzzops/rules/INITIALIZATION.md`, then `.zzzops/rules/BACKENDS.md`. Read project instructions, charter, and minimal discovery; hydrate only likely duplicate bodies, and history only when current intent is insufficient.

1. Mode defaults to `dry-run`: no edits to source, Git, goals, or index. `apply` requires explicit user request or a `$execute-zzzops` invocation explicitly allowed by reviewed PROJECT refill policy.
2. Inspect actual architecture/entry points and relevant active code, tests/coverage evidence, user/developer/operations docs, CI/build/config, errors/observability/security/performance/accessibility, and stale/dead paths. Use focused native commands; do not run expensive suites merely for ideas.
3. Compare charter, current goals, and trackers. Reject duplicates, generated/dependency work, speculative rewrites, cosmetic churn, and ideas without evidenced beneficiary/observable result.
4. Rank a short high-confidence list by value, risk, unlocks, confidence, difficulty, and feedback speed. Record full evidence/criteria/dependencies/probe internally; present outcome, why it matters, and the next useful decision. No observation surface means no suggestion without a concrete harness plan.
5. Dry-run: report the ranked outcomes and say that nothing changed. Apply: create only approved/authorized canonical goals using `$add-zzzops-goal` semantics and record evidence/source. During exhausted-queue refill, tag every goal `zzzops-refill`; never copy source labels such as `zzzops-feedback`, reserved for explicit feedback submissions. Never implement while suggesting; never automate Git for capture.

Exhausted-queue apply honors independent opt-ins:

- `documentation`: missing/stale/misleading/inaccessible user, developer, or operations docs.
- `tests`: evidenced untested behavior, regression, boundary, or missing fast feedback—not percentage theater. Apply PROJECT `test_bug`; under the installed `capture_and_ask` fallback, a discovered bug becomes a separate human-blocked TODO and is not fixed before input.
- `code_quality_non_behavioral`: behavior-preserving naming, extraction/decomposition, dead/duplicate code cleanup, or monolith splitting. Require unchanged-behavior evidence; exclude features, architecture rewrites, and style churn.

Use only PROJECT-enabled categories and its cap, then return to `$execute-zzzops`. Ask about material ambiguity; never manufacture utilization work.

Before stopping or handing off, apply `.zzzops/rules/FEEDBACK.md`.
