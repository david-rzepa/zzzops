# Execute a brownfield bootstrap

Brownfield bootstrap is an evidence-led product/harness audit, not a re-scaffold. Preserve established architecture and conventions unless a reviewed goal authorizes change. Reuse or create one adequate top-level product-outcome goal, record justified gaps and milestones beneath it, then let `$execute-zzzops` own implementation, verification, review, and resumability.

## Audit and closure

1. Refresh the approved analysis, repository head, and canonical portfolio. Re-analyze if source, manifests, instructions, CI, or reviewed policy changed consequentially.
2. Run the repository's documented build, tests, analysis, and verification paths where safe. Inspect their actual output and CI definitions. Distinguish an absent capability from an existing but undocumented or disconnected one.
3. Compare the observed harness with effective rigor and applicable risks. Report only evidenced gaps: missing or divergent canonical verification, unenforced material invariants, inadequate risk-specific checks, stale context, or absent required CI. Do not impose a preferred layout, tool, or architecture on a working repository.
4. Build the root/harness/product DAG through `PLAN.md`. Preserve valid product hierarchy and add harness dependencies only to eligible unstarted goals. Send TODO/backlog migration to `$migrate-to-zzzops`; bootstrap does not import it itself.
5. Invoke `$execute-zzzops` for every authorized gap and product goal until exhaustion. Each change uses repository conventions, runs its narrow probe, and produces observed evidence; a new file or command that was not executed is not closure.
6. Reconcile `AGENTS.md` in place. Preserve unrelated instructions and the ZzzOps-adherence block owned and updated by `$review-zzzops-policy`; do not generate another policy renderer. Add only stable, high-signal commands, invariants, and links justified by the audit. Prefer existing deterministic enforcement when practical, but prose remains valid when machinery would not earn its complexity.
7. At combined harness and product checkpoints, run canonical verification and inspect equivalent exact-head CI. Report the product root, preserved decisions, closed gaps, product outcomes, ordered PR queue, conflicts, and hard blockers.
8. Repeat the audit. A clean rerun creates no duplicate goals, rewrites no context, and makes no source change.

## Representative fixture

Use a temporary established library with a pinned runtime, intentional package layout, passing build and unit tests, CI, architecture documentation, and an existing `AGENTS.md`. Its local `verify` command omits an already-configured lint check, CI independently calls build and tests, and one architectural invariant appears only in prose despite an existing dependency-test facility.

The audit must:

- classify the repository as `brownfield` and retain its structure, stack, test framework, CI provider, and unrelated agent instructions;
- observe each current command before proposing changes;
- create ordinary goals to make `verify` compose the existing lint/build/test/dependency gates and make CI invoke `verify`;
- reconcile the prose invariant with the existing dependency-test facility without introducing a second architecture tool;
- preserve the policy-owned ZzzOps block in `AGENTS.md` byte-for-byte unless `$review-zzzops-policy` changes it;
- route an unrelated legacy TODO collection to `$migrate-to-zzzops` rather than absorbing it;
- execute the gap goals through `$execute-zzzops`, then observe one passing local canonical command and equivalent exact-head CI;
- leave product behavior and established architecture unchanged, and make a second bootstrap run a no-op.

The fixture fails if bootstrap re-scaffolds the project, overwrites instructions, duplicates existing tooling, silently changes architecture, migrates backlog itself, treats file presence as proof, or maintains a verification contract different from CI.
