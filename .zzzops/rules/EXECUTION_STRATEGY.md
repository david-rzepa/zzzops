# Execution strategy

## Observable work

Never implement from intuition alone. Before editing, record baseline, falsifiable hypothesis, observation surface, expected signal, and smallest chunk. After each chunk run the narrowest real probe—test, reproduction, API/CLI call, query, log/event assertion, screenshot, benchmark, or harness—and inspect/record its output. Change one variable at a time; do not accumulate an untested diff.

Prefer existing public interfaces and native test hooks. If a GUI/editor/engine/device/service hides behavior, build the smallest local, least-privileged observation adapter: headless harness, debug endpoint, probe command, or scoped MCP server. Avoid secrets/production mutation; document lifecycle. Keep it only if it has regression value. Build/lint/types prove only those properties. If behavior cannot be observed within scope/authority, block rather than guess. After local proof widen only as relevant: component -> integration -> regression -> project.

Each active goal records baseline, hypothesis, surface, chunk, probe, expected/actual signal, wider checks, and resources.

## Test-discovered bugs

For an out-of-scope product bug exposed by test work: preserve the smallest safe reproduction; distinguish product failure from faulty test/environment; create a linked TODO with observed/expected behavior, impact, and verification path; add a `decision` blocker and interview the user. Before input, do not fix it, expand scope, weaken/delete the test, or encode the bug as correct. Correct test-only defects normally and record the distinction.

## Delegation and parallelism

Read `.zzzops/PREFERENCES.json`; its mode/cap are maximum permission, never a utilization target.

- `sequential`: no parallel sub-goal execution; a wait monitor may keep the main thread free.
- `read_only`: bounded inspections/proposals/waits; only main writes.
- `worktrees`: additionally permits isolated writable sub-goals below.

Parallelize only with explicit scopes/stops, no design dependency, disjoint mutable state/resources, worthwhile latency gain, and adequate CPU/GPU/memory/disk/quota. Never exceed `max_workers`; normally allow at most one wait/command worker and never overlap resource-heavy work. Stop on contention, overlap, conflicting assumptions, or poor value. Up to two read-only workers may independently decompose distinct children; main reconciles/writes.

Sub-agent commands may create isolated disposable outputs/logs or assigned-port processes, but must not install dependencies, rewrite tracked files, deploy/migrate, change Git, or mutate shared external systems unless `worktrees` applies and scope explicitly permits the source edits.

### Writable worktrees

Use only for Git-backed, independently verifiable sub-goals with disjoint files/resources.

1. Coordinator claims goals, checks the working tree, and creates one branch/worktree per child from one reviewed base; exclude unrelated user changes.
2. Assign one worker exact paths, criteria, baseline/probe, prohibited shared files, resource bound, and stop condition.
3. Worker edits only its worktree, tests each observable chunk, makes exactly one scoped commit, and reports hash/evidence/risk/discoveries. It never edits `goals/`, `.goal-migration/`, `.zzzops/`, root instructions, or shared systems.
4. Coordinator reviews and integrates commits sequentially onto the current branch, probing after each and running combined regressions. Coordinator alone updates ZzzOps state/usage and cleans worktrees when safe.

Do not use writable worktrees for coupled work, migrations, broad shared-file refactors, formatting, dependency upgrades, generated-output collisions, or shared services/devices/data. Stop on conflicts, shared design changes, contention, or a test-discovered bug needing input.

## Waits, commits, accounting

Delegate known >~1-minute/wait-dominated commands before launch; main continues independent lightweight work. If a main command unexpectedly runs long, do not duplicate it; poll boundedly and delegate comparable future runs.

Work on the current branch except preference-authorized temporary worktrees. Commit each verified sub-goal separately using Conventional Commits: `type(scope): concise outcome` (for example `fix(parser): reject malformed headers` or `docs(api): document retry limits`). Choose the semantic type from the actual change (`feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`); use `!`/`BREAKING CHANGE:` only for a real breaking change. Never absorb unrelated changes. Parent bookkeeping joins a child commit only when inseparable.

Record agents separately when possible; charge coordination/reconciliation/conflict cleanup to management. Note fan-out, latency benefit, usage evidence, and contention; revert work types to sequential when parallel cost lacks value.
