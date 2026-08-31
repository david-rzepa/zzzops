---
name: review-zzzops-entropy
description: ZzzOps v0.0.0-dev — development plugin. Review repository entropy from the exact pending recent change batch or an explicitly requested full audit. Preview-only by default; explicit completion records exact review coverage, while apply uses existing suggestion and goal authority. Not routine work suggestion and does not itself trigger exhausted-queue execution.
---

# Review ZzzOps Entropy

Read `../../rules/COMMUNICATION.md` for user-facing messages. Run `../../rules/INITIALIZATION.md`, then `../../rules/BACKENDS.md`, and read `../../rules/DELEGATION.md` before inspecting the repository.

For preview, keep preflight read-only: run status/checkpoint reads, but stop and report if initialization would require installation validation, policy reconciliation, or another state-changing handoff. Do not persist execution reports during preview.

Choose the narrowest requested mode and action:

- `recent` is the default. It reviews only the current uncovered event batch. Read [the recent review contract](references/RECENT.md).
- `full` requires an explicit full or repository-wide request. It ignores prior coverage for scope selection. Read [the full review contract](references/FULL.md).
- `preview` is the default action. It does not freeze a manifest, resolve inbox items, record coverage, create goals, or edit repository content.
- `complete` requires an explicit manual request to record the successfully finished review. It is independent of `apply`.
- `automatic recent` exists only when `$execute-zzzops` explicitly invokes this skill after true exhaustion with uncovered exact events. That caller authorization permits one recent manifest and exact completion receipt, but grants no goal-write authority. This skill never decides or triggers that invocation itself.
- `apply` requires explicit user authority and creates approved findings with `$add-zzzops-goal` semantics after applying the existing suggestion ranking, category, cap, and refill-authority contracts. Do not invoke `$suggest-zzzops-work` as a second broad audit. This skill never edits source, policy, tests, CI, or documentation directly.

1. Run `<python> <zzzops-cli> --repo . entropy list` once to read policy-eligible observations with their fingerprints. Validate every returned record even when recent coverage is not due; observations are leads, not durable review coverage.
2. In preview, use `entropy review status` for recent mode and do not call `entropy review plan` in either mode. Only an execute-authorized `automatic recent` invocation or explicit manual `apply`/`complete` may call `entropy review plan --mode recent|full` once. Keep the returned batch ID, exact event IDs and records, and selected observation fingerprints together.
3. For recent mode, `due:false` means no uncovered recent change batch, but eligible inbox leads still require validation and reporting. Never call the repository clean from that result. For a due batch, inspect only the exact event-linked goals, changes, and relevant observations described in `RECENT.md`. Full mode follows `FULL.md` even when there are no events or observations.
4. Preview reports stale, disproved, or duplicate fingerprints without resolving them. Resolve only with explicit mutation authority, using `entropy resolve --fingerprint ID --outcome dismissed`; supported observations stay pending until a corresponding ordinary goal is confirmed.
5. Rank a short set of findings by concrete impact, risk, repeated cost, confidence, and smallest useful boundary. Give repository paths and observed evidence, or explicitly report that the selected review completed with no findings. Never infer cleanliness from an empty inbox.
6. Preview stops after the report. Apply reuses the existing suggestion/capture contracts and their approval rules for the fixed reviewed findings; it does not launch another discovery pass or invent a second goal-creation path.
7. Complete only after every selected scope item was actually inspected and no interruption remains. Rehydrate the current goal revisions and PR heads, derive the current exact event IDs, then pass a bounded temporary JSON object containing `schema_version:1`, the exact `batch_id`, `outcome:clean|findings`, and those derived IDs as `current_events` to `entropy review complete --input FILE`. Delete only that temporary request after the command. Drift, malformed state, or failure leaves coverage due; never retry with altered identifiers or claim completion.

Keep review manifests and inbox state separate. Do not run this skill as ordinary work suggestion, silently create work, or route it recursively from its own findings.

Before stopping, apply the privacy and classification rules in `../../rules/FEEDBACK.md`. Preview never calls `report record`; if eligible machinery friction occurred, report it to the user without persisting it.
