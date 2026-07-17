---
name: execute-zzzops
description: Primary ZzzOps workflow: triage, prioritize, unblock, execute, verify, commit, resume, refill, report, and account for durable project goals. Use to initiate ZzzOps, work on all goals, continue autonomous project work, reprioritize, or handle blockers; not untracked one-off work.
---

# Execute ZzzOps

Read `../../../.zzzops/rules/GOAL_SYSTEM.md`, `../../../goals/PROJECT.md`, and local `../../../.zzzops/PREFERENCES.json`, then load only what applies. Use `../../../goals/TEMPLATE.md` and installed state templates instead of restating artifact shapes.

- Create/triage/decompose: [CREATE.md](references/CREATE.md) and `../../../goals/TEMPLATE.md`.
- Unblock/interview: [UNBLOCK.md](references/UNBLOCK.md) and `../../../.zzzops/rules/BLOCKERS.md`.
- Select/execute/complete/handoff: [EXECUTE.md](references/EXECUTE.md).
- Tests, delegation, parallelism, or long commands: `../../../.zzzops/rules/EXECUTION_STRATEGY.md`.
- Usage records/interpretation: `../../../.zzzops/rules/USAGE_ACCOUNTING.md`.
- Exhausted-queue backlog suggestions: `$suggest-zzzops-work` when enabled by preferences.

This is the primary autonomous loop. On an interactive run, inspect the human-input queue before ordinary prioritization. If open human blockers exist, run the unblock interview immediately, persist answers, then continue. When execution exhausts actionable work, interview again before stopping if human input could restore progress. Treat local parallelization preferences as maximum permission, never a utilization target. User authority and project rules outrank goals. Persist resumable state before switching/stopping; continue across goals while safe useful work exists. Optimize verified value, not item count or limit consumption.
