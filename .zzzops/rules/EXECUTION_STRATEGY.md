# Execution strategy

## Observable work

Before editing record baseline, falsifiable hypothesis, observation surface, expected signal, and smallest chunk. Change one variable; run and inspect the narrowest real probe before continuing, then widen as PROJECT requires. Prefer public/native hooks; for hidden behavior build the smallest least-privileged adapter. Avoid secrets/production mutation, retain only regression value, and remember build/lint/types prove only themselves. Block if required behavior cannot be observed within authority.

Apply reviewed PROJECT verification policy first. When it does not specify artifact handling, classify the changed surface and use this fallback:

- Product/runtime: prove affected behavior with a risk-proportionate real probe/test.
- Documentation/examples: inspect/render/check the artifact as relevant; do not add feature tests solely for prose.
- Test cases: run them and inspect the expected fail/pass signal; do not add recursive wording/layout/count/path meta-tests.
- Reusable test infrastructure: directly probe shared harnesses, fixtures, helpers, utilities, and CI plumbing.

If documentation/tests also alter runtime behavior, use the runtime rule. Record why the check is sufficient.

## CI-aware widening

Run the smallest local falsifiable probe. Map broader commands to the project's required CI; when CI runs the same command and coverage at the pushed head, do not duplicate it locally. CI counts only after inspected completion at that exact head. Diagnose failures from logs and reprobe narrowly; cancellation, timeout, skipped jobs, provider failure, or head drift is not success. If required CI is unavailable, block durably rather than skip or substitute. Derive equivalence from project commands and checks, not provider names.

## Test-discovered bugs

Preserve the smallest reproduction and distinguish product from test/environment failure. Never hide the bug, weaken/delete its test, expand scope silently, or encode broken behavior. Follow PROJECT test-bug policy; without authorization capture a linked human-blocked goal and do not fix it until later input resolves the blocker. Correct test-only defects normally and record why.

## Delegation and parallelism

PROJECT resource/autonomy policy is a permission ceiling, not a target. The installed default measures existing Git-tracked working-tree bytes via `git ls-files` (excluding `.git`, ignored/untracked artifacts, and other worktrees): below 104857600 bytes it permits up to three worktree workers; otherwise up to three read-only workers. Reviewed policy may override these operational defaults, never safety/authority.

- `sequential`: no parallel execution; a wait monitor may keep the main thread free.
- `read_only`: bounded inspections/proposals/waits; only main writes.
- `worktrees`: additionally permits isolated writable sub-goals below.

Parallelize only independent, verifiable scopes with disjoint exclusive resources, worthwhile latency benefit, permitted dependencies, and capacity. Advisory overlap requires pre-edit PR inspection, recording, and base coordination. Stop on exclusive contention, merge conflict, conflicting assumptions, or poor value. Read-only workers may investigate within cap but never claim/edit/branch/start implementation; main reconciles and writes.

Sub-agents may create isolated disposable output/logs or assigned-port processes. They may not install, rewrite tracked files, deploy/migrate, change Git, or mutate shared external systems unless `worktrees` permits that source work.

### Writable worktrees

Use only for Git-backed, independently verifiable sub-goals with disjoint exclusive resources. Advisory text overlap requires coordinator-inspected PRs and an explicit reconciliation order.

1. Coordinator claims, reviews the base, and creates one clean worktree/branch per child.
2. Assign paths, criteria, baseline/probe, prohibited shared files, resource bound, and stop condition.
3. Worker stays in its worktree, tests observable chunks, commits once, and reports hash/evidence/risk/discoveries; it never edits goal/project state, root instructions, or shared systems.
4. Coordinator reviews/integrates sequentially and probes each commit plus combined behavior; only it updates ZzzOps state.
5. Remove the worktree afterward, or verify it clean and record reuse. Before reassignment restore reviewed base, branch, resources, and ownership; never carry prior changes/claims/assumptions. Forbid dirty, abandoned, or ambiguously owned worktrees.

Do not use worktrees for coupled work, generated collisions, shared services/devices/data, policy-exclusive binary/hard-to-merge paths, or prohibited work. Broad advisory overlap needs a reconciliation plan and stays sequential when merge risk outweighs latency benefit.

## Waits, commits, resources

Delegate waits/human watches at the PROJECT threshold. Resume yielded handles; poll boundedly, never relaunch deferred work. Send quote-heavy/multiline cross-shell payloads through secure UTF-8 files or byte-preserving stdin and verify bytes before external writes. Read-only monitors stop on input/drift.

Follow PROJECT Git/commit policy; never absorb unrelated changes. Record fan-out, latency benefit, resource evidence, and contention; revert to sequential when parallel cost lacks value.
