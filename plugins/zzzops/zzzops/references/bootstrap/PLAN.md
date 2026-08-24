# Plan bootstrap as ordinary ZzzOps goals

Use this stage only after the repository analysis and any consequential proposal review. It configures the factory; it does not scaffold the repository, execute goals, or maintain a private checklist.

## Build the harness DAG

1. Refresh the canonical portfolio once and reuse it for duplicate, ancestry, cycle, status, claim, and implementation checks. Treat the approved proposal and repository evidence as inputs, not a generic template.
2. Select only justified, independently useful outcomes. Possible outcomes include pinned toolchain, repository structure, architecture boundaries, tests, formatting/lint/types, dependency/security checks, canonical verification, CI equivalence, deterministic guardrails, concise `AGENTS.md`, architecture context, and an initial product milestone. Omit anything without a beneficiary, risk reduction, or feedback value.
3. Express every selected outcome as an ordinary managed goal using `$add-zzzops-goal` semantics. Each leaf needs observable acceptance evidence, the smallest real probe, resources, explicit dependencies, and risk inputs from which effective rigor is derived. Never persist a second effective-rigor value.
4. Order dependencies by usable outcomes, not implementation steps. Canonical verification depends on the checks it composes; CI depends on canonical verification; product implementation depends on the harness outcomes it needs. Bootstrap goals must not depend on the product goals they unlock.
5. Seed only the agreed first milestone as product goals. Do not implement it. Existing TODO/backlog import belongs to `$migrate-to-zzzops`.

## Reconcile existing goals

After all harness goals have stable identities, inspect each open goal and add the minimum required harness dependencies when all are true:

- it represents product/repository implementation affected by the harness;
- implementation has not started: no claim, branch, checkpoint, or completed source work;
- it is not a bootstrap goal, ZzzOps administration, feedback, release-only human action, or another non-implementation outcome;
- the new edge is not already present and cannot create a dependency or parent cycle.

Preserve priority, blockers, human text, and unrelated dependencies. Report an already-started goal or ambiguous ownership as a conflict; never rewrite it silently. A goal blocked on a product decision may receive a harness dependency only when that does not imply the decision is resolved.

## Resumability and idempotence

Before each write, recheck exact revision/digest and duplicate intent. Create goals in dependency order, recording their canonical IDs before dependents. Apply existing-goal edge updates separately after creation. On interruption, resume from canonical outcomes and IDs: reuse exact matches, repair only missing safe edges, and reject divergent near-duplicates or cycles. Repeating the completed stage creates no goals and changes no revisions.

## Fixtures

Greenfield structured API:

```text
Pin runtime
  → Establish project structure and architecture
    → Establish tests and static analysis
      → Establish canonical verification
        → Add equivalent CI
          → Seed first product milestone (unimplemented)
```

Brownfield library with working build/tests/CI but an incomplete verification command:

```text
Repair canonical verification to compose existing gates
  → Add the missing evidenced architecture guardrail
```

Preserve the established package layout and CI. Applicable unstarted product goals depend on the repair; an in-progress release, feedback goal, human portal task, and bootstrap goals remain unchanged. A retry reuses both harness goals and adds no duplicate edges.
