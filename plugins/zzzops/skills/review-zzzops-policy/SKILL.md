---
name: review-zzzops-policy
description: ZzzOps v0.0.0-dev — development plugin. Review, initialize, summarize, reconcile, or adjust ZzzOps project policy. Preferred first workflow; always re-summarizes existing policy.
---

# Review ZzzOps Policy

Follow `../../rules/INITIALIZATION.md`; only this workflow changes or confirms policy.

Before optional tools, reuse capabilities; never invoke an unavailable path—use an alternative or block once.

Run `init inspect` once; offer privacy-safe execution reports. For a missing automated-design section propose enabled/disabled; for missing workflow-adherence sections explain `optional`/`tracked`/`managed` and propose `tracked` for adherence; for missing rigor explain `vibe`/`structured`/`agentic` and propose `structured`—all without inferring approval.

Review rigor defaults/escalation/minimums/overrides/interview depth. More rigor costs upfront but cuts ambiguity/rework/regressions; never silently lower or undercut a minimum.

Compare default IDs/digests first. Changed/stale: load full old/new snapshots only for changed or selected sections. Missing legacy provenance stays unknown. Replace matching stored defaults only; report customized values without replacement.

If every required section has valid approval, say `The policy is already approved.` Do not ask for approval or run `init confirm`. Else require explicit approval of the current digest (`approval digest`), then `init confirm`. Ask separately before policy commits/PRs.

Approved adherence: reconcile a bounded `AGENTS.md` block (`BEGIN ZZZOPS WORKFLOW ADHERENCE`); preserve all unrelated instructions.

Before stopping or handing off, apply `../../rules/FEEDBACK.md`.
