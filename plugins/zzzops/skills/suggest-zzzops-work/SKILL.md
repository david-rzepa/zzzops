---
name: suggest-zzzops-work
description: ZzzOps v0.0.0-dev — development plugin. Suggest, discover, or audit valuable ZzzOps work from project code, tests, docs, config, and state. "dry run", "preview", or "plan" is the no-write default; "apply" writes approved goals, and "refill" writes only when authorized by reviewed exhausted-queue policy.
---

# Suggest ZzzOps Work

Read `../../rules/COMMUNICATION.md` for user-facing messages.

Run `../../rules/INITIALIZATION.md`, then `../../rules/BACKENDS.md`. Read project instructions, charter, and minimal evidence; hydrate only likely duplicates, and history only when needed.

1. Mode defaults to `dry-run`: no edits to source, Git, goals, or index. `apply` requires explicit user request or a `$execute-zzzops` invocation explicitly allowed by reviewed PROJECT refill policy.
   Always run `<python> <zzzops-cli> --repo . entropy list` once. Validate each returned observation against current repository evidence before ranking it; excluded categories stay pending and invisible under the existing PROJECT refill `allowed_categories` policy. An explicit entropy-review request broadens the same evidence-led repository audit without adding another skill or policy knob.
2. Inspect actual architecture/entry points and relevant active code, tests/evidence, docs, CI/build/config, observability/security/performance/accessibility, and stale paths. Use focused native commands; do not run expensive suites merely for ideas.
3. Compare reviewed and goal-effective engineering rigor with the real harness. Agentic work without CI, prose-only invariants, incomplete canonical verification, unverified security-sensitive work, or repeated unenforced `AGENTS.md` rules becomes a proposed goal—not a silent change. Credit existing context/tools; prefer coherent feedback over tool quantity.
4. Compare charter, goals, and trackers. Reject duplicates, generated/dependency work, speculative rewrites, cosmetic churn, and ideas without an evidenced beneficiary/result.
5. Rank a short high-confidence list by value, risk, unlocks, confidence, difficulty, and feedback speed. Record evidence/criteria/dependencies/probe; present outcome, value, and next decision. Without observation, propose the smallest harness first.
6. Dry-run reports ranked outcomes and no changes. Apply creates only authorized goals with `$add-zzzops-goal` semantics and evidence. During exhausted-queue refill, tag every goal `zzzops-refill`; never copy source labels such as `zzzops-feedback`. Never implement or automate Git while suggesting.

For each inbox observation, inspect only enough current evidence to classify it.
Dismiss stale, disproved, or duplicate observations with `entropy resolve --outcome
dismissed`; leave supported observations pending through dry-run preview, and resolve
them as `captured` only after an ordinary goal is confirmed. The inbox is evidence,
not authority or a second backlog. Return no suggestion when no decay is evidenced.

Exhausted-queue apply honors independent opt-ins:

- `documentation`: missing, stale, misleading, or inaccessible user/developer/operations docs.
- `tests`: evidenced untested behavior, regression, boundary, or missing fast feedback—not percentage theater. Apply PROJECT `test_bug`; `capture_and_ask` records a separate human-blocked TODO before any fix.
- `code_quality_non_behavioral`: behavior-preserving naming, extraction/decomposition, dead/duplicate code cleanup, or monolith splitting. Require unchanged-behavior evidence; exclude features, architecture rewrites, and style churn.

Use only PROJECT-enabled categories and cap, then return to `$execute-zzzops`. Ask about material ambiguity; never manufacture work.

Before stopping or handing off, apply `../../rules/FEEDBACK.md`.
