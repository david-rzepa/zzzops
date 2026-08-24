---
name: review-zzzops-policy
description: Review, initialize, summarize, reconcile, or adjust ZzzOps policy. Preferred first workflow; always re-summarizes existing policy.
---

# Review ZzzOps Policy

Follow `../../rules/INITIALIZATION.md`; only this workflow changes or confirms policy.

Checkpoint readiness, never goals/history.

Before optional tools, reuse capabilities; never invoke an unavailable path—use an alternative or block once.

Run `init inspect` once; summarize choices and invite adjustments with privacy-safe execution reports (default enabled). For a missing automated-design section, propose enabled/disabled without inferring approval. For missing workflow-adherence sections, explain `optional`/`tracked`/`managed`; propose `tracked` for adherence.

Compare default IDs/digests first. Changed/stale: load full old/new snapshots only for changed or selected sections. Missing legacy provenance stays unknown. Replace only when effective value matches stored snapshot and default changed; report customized values without replacement.

When every required section has valid approval, say `The policy is already approved.` Do not ask for approval or run `init confirm`; invite adjustments and checkpoint. Otherwise require explicit approval of the current digest (the approval digest), then `init confirm`. Ask only consequential questions. Ask separately before policy commits/PRs.

For approved adherence, reconcile a bounded `AGENTS.md` block marked `BEGIN ZZZOPS WORKFLOW ADHERENCE`; preserve all unrelated instructions. Include level/exemptions and limits.

Before stopping or handing off, apply `../../rules/FEEDBACK.md`.
