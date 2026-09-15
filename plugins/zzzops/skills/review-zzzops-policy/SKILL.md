---
name: review-zzzops-policy
description: ZzzOps v0.0.0-dev — development plugin. Review, initialize, summarize, reconcile, or adjust ZzzOps project policy. Preferred first workflow; always re-summarizes existing policy.
---

# Review ZzzOps Policy

Read `../../rules/COMMUNICATION.md` for user-facing messages.

Follow `../../rules/INITIALIZATION.md`; only this workflow changes or confirms policy.

Before optional tools, reuse capabilities; never invoke an unavailable path—use an alternative or block once.

Run `init inspect` once. Show its `policy_review_table` exactly once before detail or action; never filter rows, even when policy is unchanged and approved. Keep hashes, snapshots, raw settings, and provenance progressive. Offer privacy-safe execution reports. For a missing automated-design section explain enabled/disabled. For missing workflow-adherence sections explain `optional`/`tracked`/`managed` and propose `tracked` for adherence; for missing rigor explain `vibe`/`structured`/`agentic` and propose `structured`—all without inferring approval.

Always foreground approval timing. Recommend `human_at_exhaustion`: policy approval gates execution once, verified per-goal PRs stack until safe work is exhausted, then the user reviews the ordered queue. Explain `human_after_checks` plus completed-dependency gating as the stricter per-goal alternative. Describe [[bounded commitment]](../../concepts/bounded-commitment.md) before automated-design authority; neither option bypasses checks, PR approval, merge authority, or release policy.

Alongside Git/review policy, show `capabilities.github_stack` and `stack_tooling_offer`
from inspection. When native stacks are preferred and the official extension is
missing, offer `gh extension install github/gh-stack` before choosing chained PRs.
Explain the host tooling change and request explicit approval; reuse applicable
installation approval already provided in this session. A missing or too-old GitHub
CLI needs separate explicit install/upgrade authority, using the reported minimum.
Never silently upgrade it. Existing usable tooling needs no offer.

After approved installation, rerun only `gh --version`, `gh extension list`, and
`gh stack --version`; verify official source plus usable version. Installation does
not prove provider stack membership.
If declined, record the offer's `capability_digest` as Git/review settings
`stacked_tooling_decline` through normal reviewed policy changes; do not repeat an
offer at unchanged capability. Explicit reconsideration removes that decline record;
changed capability evidence makes it stale. Preserve explicit PR-mode decisions and
history. If declined, unsupported, failed, or unverifiable, explain and record the
reviewed chained-PR fallback or a blocker according to policy. Unattended execution
never interviews or installs without prior applicable authority; it consumes the
reviewed decision and follows the recorded fallback or persists a blocker.

Review rigor defaults/escalation/minimums/overrides/interview depth. More rigor costs upfront but cuts ambiguity/rework/regressions; never silently lower or undercut a minimum.

Compare default IDs/digests first. Changed/stale: load full old/new snapshots only for changed or selected sections. Missing legacy provenance stays unknown. Replace matching stored defaults only; report customized values without replacement.

If every required section has valid approval, say `The policy is already approved.` Do not ask for approval or run `init confirm`. Else require explicit approval of the current digest (`approval digest`), then `init confirm`. Approved policy artifacts may enter ordinary PR review without another conversational gate.

Approved adherence: reconcile a bounded `AGENTS.md` block (`BEGIN ZZZOPS WORKFLOW ADHERENCE`); preserve all unrelated instructions.

Before stopping or handing off, apply `../../rules/FEEDBACK.md`.
