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

Each returned phase step names one prompt under [references/phases](../../../skills/execute-zzzops/references/phases). Read only that prompt. It describes the work; the checkpoint supplies the live evidence, command, and completion contract. Persist the returned immutable evidence before requesting another checkpoint.

Continue while the checkpoint returns actionable work. It is responsible for shared bootstrap, policy, capability, portfolio, dependency, phase-review, and stack checks; its diagnostics belong in its referenced log, not agent-visible narration.

`zzzops-feedback` goals remain excluded until the user authorizes them for the current execution session; pass that approval through `--include-feedback`. Never ask per issue.

Apply [[bounded commitment]](../../../concepts/bounded-commitment.md) and [[safe useful work]](../../../concepts/safe-useful-work.md) when acting on a returned step.
