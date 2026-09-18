---
name: review-zzzops-policy
description: ZzzOps v0.0.0-dev — development plugin. Review, initialize, summarize, reconcile, or adjust ZzzOps project policy. Preferred first workflow; always re-summarizes existing policy.
---

# Review ZzzOps Policy

Only this workflow changes or confirms the reviewed configuration and agent policy. Each category has typed `configuration` consumed by the CLI and natural-language `instructions` followed by agents. Put enforceable controls only in supported configuration keys; put judgment and project-specific constraints in instructions. Do not duplicate a configuration value in separately editable prose.

Before optional tools, reuse capabilities; never invoke an unavailable path—use an alternative or block once.

Use the inspection evidence returned for this workflow once. Never ask to start policy review. For missing, changed, or stale policy, inspect and show the proposal; after its table and changes, ask only for approval or adjustments, never approval to review. Show its `policy_review_table` exactly once before detail or action; never filter rows, even when policy is unchanged and approved. Keep detail progressive. Offer privacy-safe execution reports. Explain the proposed design authority and goal-tracking instructions. For missing rigor, explain the supported `configuration.level` values and propose `structured`, without inferring approval. When replacing a legacy schema, inspect every old choice, retain meaningful project constraints in instructions or supported configuration, and show the changes; old approval does not authorize the new representation.

Show `capabilities.release_status` and `capabilities.legacy_migration_review` with the table. New/reviewed policy must include `legacy_migration`; an existing policy without it means treat execution as uninitialized and re-review before migration. A public GitHub Release is evidence; no release is ambiguous unless the owner says `never_released`. Route ambiguity to a decision/blocker. `never_released` stales at first release and blocks reset until review.

Foreground the configured phase DAG and its human-review requirements, CI mode, and the agent instructions for collecting PR approval. Explain which requirements the CLI enforces and which require agent judgment. Describe [[bounded commitment]](../../../concepts/bounded-commitment.md) before automated-design authority; neither option bypasses checks, PR approval, merge authority, or release policy.

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
If declined, record the offer's `capability_digest` as Git/review configuration
`stacked_tooling_decline` through normal reviewed policy changes; do not repeat an
offer at unchanged capability. Explicit reconsideration removes that decline record;
changed capability evidence makes it stale. Preserve explicit PR-mode decisions and
history. If declined, unsupported, failed, or unverifiable, explain and record the
reviewed chained-PR fallback or a blocker according to policy. Unattended execution
never interviews or installs without prior applicable authority; it consumes the
reviewed decision and follows the recorded fallback or persists a blocker.

Review rigor defaults/escalation/minimums/overrides/interview depth. More rigor costs upfront but cuts ambiguity/rework/regressions; never silently lower or undercut a minimum.

Each `reviewed_pairs` entry needs `model`, `effort`, `tier`, and integer `cost`: use one relative-cost scale and document estimates.

Compare default IDs/digests first. Changed/stale: load full old/new snapshots only for changed or selected sections. Missing legacy provenance stays unknown. Replace matching stored defaults only; report customized values without replacement.

If every required section has valid approval, say `The policy is already approved.` Do not ask for approval again. Otherwise require explicit approval of the current digest from the root-mediated human interaction, then submit that approval using the exact returned input contract. Approved policy artifacts may enter ordinary PR review without another conversational gate.

Approved adherence: reconcile a bounded `AGENTS.md` block (`BEGIN ZZZOPS WORKFLOW ADHERENCE`); preserve all unrelated instructions.
