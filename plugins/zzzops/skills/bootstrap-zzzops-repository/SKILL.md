---
name: bootstrap-zzzops-repository
description: Bootstrap an empty, early-stage, or established software repository from a project specification into an agent-ready ZzzOps harness and executable goal DAG. Use to create a project or make an existing repository agent-ready; stops before substantive product implementation.
---

# Bootstrap a ZzzOps Repository

Establish the proportionate engineering harness that later agents need. Bootstrap coordinates reviewed policy, ordinary goals, execution, verification, and migration; it does not duplicate them or implement the product.

1. Inspect initialization through `../../rules/INITIALIZATION.md` and use `../../rules/BACKENDS.md` for canonical portfolio operations. If project policy is not reviewed, hand off to `$review-zzzops-policy`, persist the resume point, and continue after approval. Effective engineering rigor and risk escalation set the harness bar; never silently de-escalate.
2. Read [repository analysis](../../zzzops/references/bootstrap/ANALYZE.md). Classify greenfield, early scaffold, or brownfield from evidence and resolve only consequential unknowns. Present an architecture/harness proposal when reviewed autonomy does not cover a material choice.
3. Read [goal-DAG planning](../../zzzops/references/bootstrap/PLAN.md). Create meaningful bootstrap outcomes as canonical goals, reconcile eligible unstarted product-goal dependencies, and seed—but do not implement—the agreed first product milestone.
4. For an empty or minimal repository, follow the [greenfield journey](../../zzzops/references/bootstrap/GREENFIELD.md). For an established repository, follow the [brownfield audit and closure journey](../../zzzops/references/bootstrap/BROWNFIELD.md). Early scaffolds use the parts justified by their evidence.
5. Invoke `$execute-zzzops` to implement the authorized harness/scaffolding goals and observe their real verification output. The skill invocation authorizes those approved bootstrap outcomes only; substantive product work requires its own goal execution authority.
6. Report classification, preserved decisions, assumptions and blockers, created/reused goals and dependencies, exact verification evidence, review gates, deferred work, and the next unimplemented product goal. A repeat run must reuse canonical state and avoid gratuitous repository changes.

Keep `AGENTS.md` compact and reconcile it in place. `$review-zzzops-policy` owns its ZzzOps-adherence block; bootstrap may update stable repository context around that block. Put specialist knowledge in linked dynamic context, and add deterministic guardrails only when their value justifies their machinery.

Before stopping or handing off, apply `../../rules/FEEDBACK.md`.
