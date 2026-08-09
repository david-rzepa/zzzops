---
name: review-zzzops-policy
description: Review, initialize, summarize, reconcile, or adjust ZzzOps project policy. Preferred first workflow; always re-summarizes existing policy.
---

# Review ZzzOps Policy

Follow `../../rules/INITIALIZATION.md`; only this workflow changes or confirms policy.

Checkpoint only for readiness; never read goals/history.

Before optional tools, reuse capabilities; never invoke an unavailable path—use an alternative or block once.

Run `init inspect` once, summarize choices, and invite adjustments. Include privacy-safe execution reports (default enabled). For existing policy with a missing automated-design section, propose enabled/disabled without inferring approval.

Compare default IDs/digests first; load full old/new snapshots only for changed or selected sections. Missing legacy provenance stays unknown. Replace only when effective value matches stored snapshot and installed default changed; report customized values without replacement. Unchanged/declined defaults need no approval; accept/decline only in explicit review.

For valid policy with a current approval digest and all required sections approved, say `The policy is already approved.` Do not ask for approval or run `init confirm`; invite adjustments and checkpoint. Changed/stale state, pending sections, or proposals require explicit approval of the current digest, then confirmation. Ask only consequential questions. Ask separately before policy commits/PRs.

Before stopping or handing off, apply `../../rules/FEEDBACK.md`.
