---
name: review-zzzops-policy
description: Review, initialize, summarize, reconcile, or adjust ZzzOps project policy. Preferred first workflow; always re-summarizes existing policy.
---

# Review ZzzOps Policy

Follow `.zzzops/rules/INITIALIZATION.md`; only this workflow changes or confirms policy.

Checkpoint only for readiness; never read goals/history.

Before `init inspect`, check INITIALIZATION's exact installer commit scope. If pending, ask: `The ZzzOps installation needs to be committed before policy review. Would you like me to commit the lock file and related ZzzOps installation changes now? Unrelated changes stay untouched.` Stop for the answer; after yes, commit only that scope. Run `init inspect` once, summarize choices, and invite adjustments. Include privacy-safe execution reports (default enabled). For an existing policy with a missing automated-design section, explicitly propose enabled/disabled without inferring approval.

Compare default IDs/digests first; load full old/new snapshots only for changed or selected sections. Missing legacy provenance stays unknown. Offer replacement only when the effective value equals its stored snapshot and the installed default changed; report customized values without replacement. Unchanged or previously declined defaults need no approval. Accept/decline only through normal explicit policy review.

For valid policy with a current approval digest and all required sections approved, say `The policy is already approved.` Do not ask for approval or run `init confirm`; invite adjustments and checkpoint. Changed/stale state, pending sections, or proposals require explicit approval of the current digest, then confirmation. Ask only consequential questions. Ask separately before policy commits/PRs.

Before stopping or handing off, apply `.zzzops/rules/FEEDBACK.md`.
