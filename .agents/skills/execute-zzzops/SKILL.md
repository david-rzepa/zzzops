---
name: execute-zzzops
description: Execute the primary ZzzOps goal loop: work all goals, continue, resume, triage, prioritize, reprioritize, unblock, verify, commit, refill, and report. Default executes authorized work. "dry run", "preview", or "plan" performs read-only queue analysis with no writes. Not one-off untracked work.
---

# Execute ZzzOps

Mode: `dry run`, `preview`, or `plan` means read-only inventory, triage simulation, ordering, and blocker reporting; do not initialize/apply, claim, update goals, edit source, run mutating commands, or change Git/external state. Otherwise run the live loop below.

First run `../../../.zzzops/rules/INITIALIZATION.md`, then route through `../../../.zzzops/rules/BACKENDS.md`. Read `../../../.zzzops/rules/GOAL_SYSTEM.md` and the initialized charter; load only what applies.
Track execute intent through `../../../.zzzops/rules/CONTINUATION.md` so additive capture can safely resume without nested loops.


- Create/triage/decompose: [CREATE.md](references/CREATE.md).
- Unblock/interview: [UNBLOCK.md](references/UNBLOCK.md) and `../../../.zzzops/rules/BLOCKERS.md`.
- Select/execute/complete/handoff: [EXECUTE.md](references/EXECUTE.md).
- Source-changing branch topology/review: [BRANCH_REVIEW.md](references/BRANCH_REVIEW.md).
- Pre-handoff diff/dead-code review: [SELF_REVIEW.md](references/SELF_REVIEW.md).
- Tests, delegation, parallelism, or long commands: `../../../.zzzops/rules/EXECUTION_STRATEGY.md`.
- Exhausted-queue backlog suggestions: `$suggest-zzzops-work` when explicitly enabled by reviewed PROJECT policy.

This is the primary autonomous loop. Apply reviewed PROJECT selection, continuation, blocker-interview, refill, Git, verification, and resource policy. User authority and project rules outrank goals. Persist resumable state before switching/stopping; continue while policy permits safe useful work. Optimize verified value, not item count or limit consumption.

Before source work, read PROJECT Git/review/continuation policy and checkpoint only pending local ZzzOps state when required; never absorb unrelated changes or create an empty GitHub-state commit.
