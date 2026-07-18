# Execution strategy

## Observable work

Never implement from intuition alone. Before editing, record baseline, falsifiable hypothesis, observation surface, expected signal, and smallest chunk. Change one variable, run the narrowest real probe, inspect its output, then continue. Widen checks only after local proof and as PROJECT policy requires.

Prefer public interfaces and native hooks. When behavior is hidden, build the smallest least-privileged observation adapter (headless harness, debug endpoint, probe command, or scoped MCP server). Avoid secrets/production mutation; document lifecycle and retain only regression value. Build/lint/types prove only those properties. If required behavior cannot be observed within authority, block rather than guess.

## Test-discovered bugs

Preserve the smallest reproduction and distinguish product failure from test/environment failure. Never hide the bug, weaken/delete the test, silently expand scope, or encode broken behavior as correct. Then follow PROJECT test-bug policy; absent explicit authorization, capture a linked human-blocked goal and ask before fixing. Correct test-only defects normally and record the distinction.

## Delegation and parallelism

Effective permission is the stricter of reviewed PROJECT resource/autonomy policy and ignored user `.zzzops/PREFERENCES.json`; it is a ceiling, never a utilization target.

- `sequential`: no parallel execution; a wait monitor may keep the main thread free.
- `read_only`: bounded inspections/proposals/waits; only main writes.
- `worktrees`: additionally permits isolated writable sub-goals below.

Parallelize only when scopes are independent, mutable state/resources are disjoint, latency benefit is worthwhile, and policy capacity exists. Stop on contention, overlap, conflicting assumptions, or poor value. Read-only workers may decompose distinct children within the effective cap; main reconciles and writes.

Sub-agent commands may create isolated disposable outputs/logs or assigned-port processes, but may not install dependencies, rewrite tracked files, deploy/migrate, change Git, or mutate shared external systems unless `worktrees` explicitly permits the assigned source work.

### Writable worktrees

Use only for Git-backed, independently verifiable sub-goals with disjoint files/resources.

1. Coordinator claims goals, reviews the base, and creates one worktree/branch per child without unrelated changes.
2. Assign exact paths, criteria, baseline/probe, prohibited shared files, resource bound, and stop condition.
3. Worker edits only its worktree, tests observable chunks, makes one scoped commit, and reports hash/evidence/risk/discoveries. It never edits goal/project state, root instructions, or shared systems.
4. Coordinator reviews and integrates sequentially, probing each commit and combined behavior; coordinator alone updates ZzzOps state/usage and cleans worktrees safely.

Do not use writable worktrees for coupled work, broad shared-file changes, generated-output collisions, shared services/devices/data, or any policy-prohibited work.

## Waits, commits, accounting

Delegate wait-dominated commands at the PROJECT threshold before launch; keep the main thread on independent lightweight work. If an unexpected command runs long, poll boundedly and delegate comparable future waits rather than duplicate it.

Follow PROJECT Git/commit policy and never absorb unrelated changes. Record agents separately when possible; charge coordination/reconciliation/conflict cleanup to management. Note fan-out, latency benefit, usage evidence, and contention; revert work types to sequential when parallel cost lacks value.
