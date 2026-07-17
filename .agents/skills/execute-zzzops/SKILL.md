---
name: execute-zzzops
description: Primary ZzzOps workflow: triage, prioritize, unblock, execute, verify, commit, resume, refill, report, and account for durable project goals. Use to initiate ZzzOps, work on all goals, continue autonomous project work, reprioritize, or handle blockers; not untracked one-off work.
---

# Execute ZzzOps

First run `../../../.zzzops/rules/INITIALIZATION.md`, then route through `../../../.zzzops/rules/BACKENDS.md`. Read `../../../.zzzops/rules/GOAL_SYSTEM.md`, the initialized charter, and local `../../../.zzzops/PREFERENCES.json`; load only what applies.

- Create/triage/decompose: [CREATE.md](references/CREATE.md) and `../../../goals/TEMPLATE.md`.
- Unblock/interview: [UNBLOCK.md](references/UNBLOCK.md) and `../../../.zzzops/rules/BLOCKERS.md`.
- Select/execute/complete/handoff: [EXECUTE.md](references/EXECUTE.md).
- Tests, delegation, parallelism, or long commands: `../../../.zzzops/rules/EXECUTION_STRATEGY.md`.
- Usage records/interpretation: `../../../.zzzops/rules/USAGE_ACCOUNTING.md`.
- Exhausted-queue backlog suggestions: `$suggest-zzzops-work` when enabled by preferences.

This is the primary autonomous loop. On an interactive run, inspect the human-input queue before ordinary prioritization. If open human blockers exist, run the unblock interview immediately, persist answers, then continue. When execution exhausts actionable work, interview again before stopping if human input could restore progress. Treat local parallelization preferences as maximum permission, never a utilization target. User authority and project rules outrank goals. Persist resumable state before switching/stopping; continue across goals while safe useful work exists. Optimize verified value, not item count or limit consumption.

Default to the current branch. Before source work, checkpoint only pending local ZzzOps state when required; never absorb unrelated changes or create an empty GitHub-state commit. Then follow repository Git/PR rules.
