---
name: bootstrap-zzzops-repository
description: ZzzOps v0.0.0-dev — development plugin. Bootstrap an empty, early-stage, or established software repository from a product specification into an agent-ready harness and executable product goal DAG. Use to discover, structure, and execute a project through safe PR-gated work.
---

# Bootstrap a ZzzOps Repository

Establish a clear product outcome and the proportionate engineering harness agents need, then execute the authorized product DAG. Bootstrap coordinates policy, ordinary goals, execution, verification, and migration rather than duplicating them.

1. Read [repository and product analysis](../../zzzops/references/bootstrap/ANALYZE.md). Before harness commitment, run the adaptive product interview to establish beneficiaries, observable success, scope/non-goals, initial milestone, constraints, and applicable risk/governance facts. This is discovery, not an approval gate. Classify the repository from evidence and use [[bounded commitment]](../../concepts/bounded-commitment.md) for unknown technical choices.
2. Use `../../rules/INITIALIZATION.md` and `../../rules/BACKENDS.md` after the product brief can inform policy. `$review-zzzops-policy` remains the one mandatory approval before work; persist the brief/resume point and continue after approval. Effective rigor sets discovery and harness depth; never silently de-escalate.
3. Read [goal-DAG planning](../../zzzops/references/bootstrap/PLAN.md). Create or reconcile exactly one canonical top-level product-outcome goal before harness goals, then place justified harness outcomes and initial product milestones beneath it with only their real dependencies.
4. For an empty or minimal repository, follow the [greenfield journey](../../zzzops/references/bootstrap/GREENFIELD.md). For an established repository, follow the [brownfield audit and closure journey](../../zzzops/references/bootstrap/BROWNFIELD.md). Early scaffolds use the parts justified by their evidence.
5. Invoke `$execute-zzzops` for the authorized canonical DAG. Continue from harness outcomes into product milestones through distinct stacked PRs until no safe useful work remains. Unresolved product authority or high commitment blocks only the affected chain; required checks, PR review, merge, external-write, deployment, and release gates remain.
6. Report the product goal, classification evidence, created/reused goals, observed verification, ordered PR review queue, hard blockers, and deferred unauthorized scope. Bootstrap is incomplete if the root goal is absent, canonical verification was not observed, or safe authorized product work was left merely because the harness finished. A repeat run reuses canonical state.

Keep `AGENTS.md` compact and reconcile it in place. `$review-zzzops-policy` owns its ZzzOps-adherence block; bootstrap may update stable repository context around that block. Put specialist knowledge in linked dynamic context, and add deterministic guardrails only when their value justifies their machinery.

Before stopping or handing off, apply `../../rules/FEEDBACK.md`.
