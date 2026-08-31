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

Apply the shared [delegation contract](DELEGATION.md) and PROJECT ceilings; missing settings defer to policy review. Inspect advisory overlap; stop on contention/conflict. Assigned disposable output/processes are allowed, but without `worktrees` workers never install, edit, deploy, change Git, or mutate shared systems.

### Writable worktrees

Use only for Git-backed, independently verifiable sub-goals with disjoint exclusive resources.

1. Coordinator claims, reviews the base, and creates a clean worktree/branch per child.
2. Assign paths, criteria, probe, prohibited files, resources, and stop.
3. Worker stays isolated, tests chunks, commits once, and reports hash/evidence/risks; it never edits goal/project state or shared systems.
4. Coordinator integrates sequentially, probes each commit and the combination, then updates state.
5. Remove afterward or verify clean reuse. Before reassignment restore base/branch/resources/owner; never carry prior work.

Keep coupled work, generated collisions, shared systems/data, binary conflicts, and broad risky overlap sequential.

## Final-state commit history

Before review, keep commits only when independently useful; fold iteration-only commits and changes valid only together. Use semantic Conventional Commit messages; PR/controlled merge titles describe outcomes. Rewrite only an exclusively owned, unintegrated goal branch after checking exact local/remote/base state; if pushed use `--force-with-lease`. Never rewrite shared, upstream, default-branch, user-owned, or integrated history. Preserve stacked goal ancestry, boundaries, dependencies, and evidence; block on doubt. Cleanup is agent-led; automate only reliable violations.

## Waits, commits, resources

Delegate eligible waits. Resume yielded handles and poll boundedly; never relaunch. Send multiline cross-shell payloads through secure UTF-8 files or byte-preserving stdin and verify before external writes. Read-only monitors stop on input/drift.

Follow PROJECT Git/commit policy; never absorb unrelated changes. Record parallelism evidence and go sequential when it lacks value.
