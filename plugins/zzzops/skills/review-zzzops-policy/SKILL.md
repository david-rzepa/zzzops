---
name: review-zzzops-policy
description: Review, initialize, summarize, reconcile, or adjust ZzzOps project policy. Preferred first workflow; always re-summarizes existing policy.
---

# Review ZzzOps Policy

Follow `../../rules/INITIALIZATION.md`; only this workflow changes or confirms policy.

Checkpoint readiness, never goals/history.

Before optional tools, reuse capabilities; never invoke an unavailable path—use an alternative or block once.

Run `init inspect` once; summarize choices and invite adjustments with privacy-safe execution reports (default enabled). For a missing automated-design section, propose enabled/disabled without inferring approval. For missing workflow-adherence sections, explain `optional`/`tracked`/`managed`; propose `tracked` for adherence.

Compare default IDs/digests first. Changed/stale: load full old/new snapshots only for changed or selected sections. Missing legacy provenance stays unknown. Replace only when effective value matches stored snapshot and default changed; report customized values without replacement. Explicit review alone accepts/declines.

With valid approval and every required section approved, say `The policy is already approved.` Do not ask for approval or run `init confirm`; invite adjustments and checkpoint. Otherwise require explicit approval of the current digest (the approval digest), then `init confirm`. Ask only consequential questions. Ask separately before policy commits/PRs.

Confirmation writes approved adherence to a bounded `AGENTS.md` block without replacing other text; report unsupported enforcement.

Before stopping or handing off, apply `../../rules/FEEDBACK.md`.
