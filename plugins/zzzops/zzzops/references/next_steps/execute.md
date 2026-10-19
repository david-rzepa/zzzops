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

The host evaluates the same versioned policy DAG for every open product goal.
Missing phase data, incompatible evidence and new findings expose ordinary
pending tasks; findings never append per-goal topology. Preserve ownership and
resolve pending transactions before recording phase findings. Workflow changes
use project policy review, not goal graph adoption. Preview and historical reads
remain read-only; broad discovery never sweeps goals for migration. See
[recovery](../CLI_RECOVERY.md#fixed-policy-workflow-and-phase-findings).

`zzzops-feedback` goals remain excluded until the user authorizes that queue for the current execution session. Preserve that authorization only through fields the workflow returns; never invent a flag or ask per issue.

Apply [[bounded commitment]](../../../concepts/bounded-commitment.md) and [[safe useful work]](../../../concepts/safe-useful-work.md) when acting on a returned step.
