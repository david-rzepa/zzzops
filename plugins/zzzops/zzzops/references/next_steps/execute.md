---
name: execute-zzzops
description: >-
  ZzzOps v0.0.0-dev — development plugin. Execute the primary ZzzOps goal loop:
  work all goals, continue, resume, triage, prioritize, reprioritize, unblock,
  verify, commit, refill, and report. Default executes authorized work. "dry run",
  "preview", or "plan" performs read-only queue analysis with no writes. Not
  one-off untracked work.
---

# Execute ZzzOps

Each returned phase step names one prompt under [references/phases](../../../skills/execute-zzzops/references/phases). Read only that prompt. It describes the work; the step supplies the live input, upstream evidence, `start`, optional `bind`, `submission`, `command`, and completion contract. Acquire the phase before work, bind its actual executor, and submit its immutable evidence under the returned lease before invoking the workflow again.

Continue while the workflow returns actionable work. It is responsible for shared bootstrap, policy, capability, portfolio, dependency, phase-review, and stack checks; its diagnostics belong in its referenced log, not agent-visible narration. Keep execution, independent review, and any root-only human approval as separate returned steps. When review requests changes, correct only the evidenced scope, submit replacement evidence through the returned contract, and let the workflow derive the next step.

The host lazily compiles supported missing correction routes for the one selected
open execution goal through guarded `graph_normalize` maintenance. Follow any
ownership or pending-transaction recovery first, then use the refreshed frontier
after confirmed publication. Do not create a graph-repair goal or request a new
human approval for this deterministic, append-only, zero-invalidation operation.
Arbitrary graph changes still require the returned independent review and exact
human approval. Preview, closed and historical reads remain read-only; broad
discovery never sweeps goals for normalization or v1 conversion. See
[recovery](../CLI_RECOVERY.md#deterministic-graph-maintenance).

`zzzops-feedback` goals remain excluded until the user authorizes that queue for the current execution session. Preserve that authorization only through fields the workflow returns; never invent a flag or ask per issue.

Apply [[bounded commitment]](../../../concepts/bounded-commitment.md) and [[safe useful work]](../../../concepts/safe-useful-work.md) when acting on a returned step.
