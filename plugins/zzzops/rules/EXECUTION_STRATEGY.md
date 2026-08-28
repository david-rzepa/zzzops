# Execution strategy

## Observable work

Before editing record baseline, falsifiable hypothesis, observation surface, expected signal, and smallest chunk. Change one variable; inspect the narrowest real probe, then widen per PROJECT. Prefer public/native hooks or the smallest least-privileged adapter. Avoid secrets/production mutation; retain only regression value. Build/lint/types prove only themselves. Block if required behavior is unobservable.

Apply PROJECT artifact-verification settings; missing settings defer verification to policy review. Interpret selected values:

- Product/runtime: prove affected behavior with a risk-proportionate real probe/test.
- Documentation/examples: inspect/render/check the artifact as relevant; do not add feature tests solely for prose.
- Test cases: run them and inspect the expected fail/pass signal; do not add recursive wording/layout/count/path meta-tests.
- Reusable test infrastructure: directly probe shared harnesses, fixtures, helpers, utilities, and CI plumbing.

If documentation/tests also alter runtime behavior, use the runtime rule. Record why the check is sufficient.

## CI-aware widening

Run the smallest local falsifiable probe. Map broad commands to required CI; when the same command/coverage runs at the pushed exact head, do not duplicate it locally. CI counts only after inspected completion; cancellation, timeout, skips, provider failure, or head drift is not success. Diagnose logs and reprobe narrowly. If required CI is unavailable, block—never skip or substitute. Derive equivalence from project commands/checks, not provider names.

## Test-discovered bugs

Preserve the smallest reproduction; distinguish product from test/environment failure. Never hide the bug, weaken/delete its test, expand scope silently, or encode broken behavior. Follow PROJECT test-bug policy; without authorization capture a linked human-blocked goal and wait for input. Correct test-only defects normally and record why.

## Delegation and parallelism

PROJECT resource/autonomy ceilings set measurement, threshold, mode, and worker cap; missing settings defer delegation to policy review. Policy never weakens safety/authority.

- `sequential`: no parallel execution; a wait monitor may keep the main thread free.
- `read_only`: bounded inspections/proposals/waits; only main writes.
- `worktrees`: additionally permits isolated writable sub-goals below.

Parallelize only independent, verifiable scopes with disjoint exclusive resources, permitted dependencies/capacity, and worthwhile latency benefit. Inspect and coordinate advisory overlap first; stop on exclusive contention, conflict, conflicting assumptions, or poor value. Read-only workers never claim/edit/branch/start implementation; main reconciles and writes.

Sub-agents may create isolated disposable output/logs or assigned-port processes. Unless `worktrees` permits source work, they may not install, rewrite tracked files, deploy/migrate, change Git, or mutate shared external systems.

### Writable worktrees

Use only for Git-backed, independently verifiable sub-goals with disjoint exclusive resources. Advisory text overlap needs coordinator-inspected PRs and a reconciliation order.

1. Coordinator claims, reviews the base, and creates one clean worktree/branch per child.
2. Assign paths, criteria, baseline/probe, prohibited shared files, resources, and stop.
3. Worker stays isolated, tests observable chunks, commits once, and reports hash/evidence/risk/discoveries; it never edits goal/project state, root instructions, or shared systems.
4. Coordinator sequentially integrates and probes each commit plus combined behavior; only it updates ZzzOps state.
5. Remove afterward, or verify clean and record reuse. Before reassignment restore reviewed base, branch, resources, and ownership; never carry prior work. Forbid dirty, abandoned, or ambiguously owned worktrees.

Do not use worktrees for coupled work, generated collisions, shared services/devices/data, exclusive binary/hard-to-merge paths, or prohibited work. Broad overlap needs a plan and stays sequential when merge risk outweighs latency benefit.

## Final-state commit history

Before review, keep commits only when independently useful; fold iteration-only commits and changes valid only together. Use semantic Conventional Commit messages; PR/controlled merge titles describe outcomes. Rewrite only an exclusively owned, unintegrated goal branch after checking exact local/remote/base state; if pushed use `--force-with-lease`. Never rewrite shared, upstream, default-branch, user-owned, or integrated history. Preserve stacked goal ancestry, boundaries, dependencies, and evidence; block on doubt. Cleanup is agent-led; automate only reliable violations.

## Waits, commits, resources

Delegate waits at the PROJECT threshold. Resume yielded handles and poll boundedly; never relaunch. Send multiline cross-shell payloads through secure UTF-8 files or byte-preserving stdin and verify before external writes. Read-only monitors stop on input/drift.

Follow PROJECT Git/commit policy; never absorb unrelated changes. Record parallelism evidence and go sequential when it lacks value.
