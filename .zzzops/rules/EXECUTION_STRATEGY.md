# Execution strategy

## Observable work

Never implement from intuition alone. Before editing, record baseline, falsifiable hypothesis, observation surface, expected signal, and smallest chunk. Change one variable, run the narrowest real probe, inspect its output, then continue. Widen checks only after local proof and as PROJECT policy requires.

Prefer public interfaces and native hooks. When behavior is hidden, build the smallest least-privileged observation adapter (headless harness, debug endpoint, probe command, or scoped MCP server). Avoid secrets/production mutation; document lifecycle and retain only regression value. Build/lint/types prove only those properties. If required behavior cannot be observed within authority, block rather than guess.

Apply reviewed PROJECT verification policy first. When it does not specify artifact handling, classify the changed surface and use this fallback:

- Product/runtime behavior: prove the affected behavior with a risk-proportionate real probe or test.
- Documentation/examples: inspect the artifact itself and render, check links/examples, or lint only when relevant. Do not add automated or human feature tests solely to test prose.
- Test cases: run the changed tests and inspect their expected failure/pass signal. Do not add recursive meta-tests whose only subject is test wording, layout, ordering, counts, or internal paths.
- Reusable test infrastructure: directly probe shared harnesses, runners, adapters, fixtures, assertion helpers, utilities, and CI test plumbing because a defect can invalidate many tests.

The artifact label never excuses unverified shipped behavior: documentation or test changes that also alter product/runtime behavior use the product/runtime rule. Record why the selected check is sufficient.

## Test-discovered bugs

Preserve the smallest reproduction and distinguish product failure from test/environment failure. Never hide the bug, weaken/delete the test, silently expand scope, or encode broken behavior as correct. Then follow PROJECT test-bug policy; absent explicit authorization, capture a linked human-blocked goal and ask before fixing. Correct test-only defects normally and record the distinction.

## Delegation and parallelism

Reviewed PROJECT resource/autonomy policy is the permission ceiling, never a utilization target. The installed default measures existing Git-tracked working-tree bytes with `git ls-files`; this excludes `.git`, ignored/untracked artifacts, and other worktrees. Below 104857600 bytes it permits at most three worktree workers; at or above that boundary, or when measurement is unavailable, it permits at most three read-only workers. Reviewed project policy may override these operational defaults without weakening safety or authority boundaries.

- `sequential`: no parallel execution; a wait monitor may keep the main thread free.
- `read_only`: bounded inspections/proposals/waits; only main writes.
- `worktrees`: additionally permits isolated writable sub-goals below.

Parallelize only when scopes are independent, mutable state/resources are disjoint, latency benefit is worthwhile, dependencies permit the proposed work, and policy capacity exists. Stop on contention, overlap, conflicting assumptions, or poor value. Read-only workers may investigate dependent goals early within the effective cap, but never claim, edit, branch, or treat them as started implementation; main reconciles and writes.

Sub-agent commands may create isolated disposable outputs/logs or assigned-port processes, but may not install dependencies, rewrite tracked files, deploy/migrate, change Git, or mutate shared external systems unless `worktrees` explicitly permits the assigned source work.

### Writable worktrees

Use only for Git-backed, independently verifiable sub-goals with disjoint files/resources.

1. Coordinator claims goals, reviews the base, and creates one worktree/branch per child without unrelated changes.
2. Assign exact paths, criteria, baseline/probe, prohibited shared files, resource bound, and stop condition.
3. Worker edits only its worktree, tests observable chunks, makes one scoped commit, and reports hash/evidence/risk/discoveries. It never edits goal/project state, root instructions, or shared systems.
4. Coordinator reviews and integrates sequentially, probing each commit and combined behavior; coordinator alone updates ZzzOps state.
5. After the task completes, remove its worktree or deliberately retain it only after verifying it is clean and recording it for reuse. Before reassignment, restore the next goal's reviewed base, branch, resources, and ownership; never carry prior changes, claims, or branch assumptions forward. Dirty, abandoned, or ambiguously owned worktrees are forbidden.

Do not use writable worktrees for coupled work, broad shared-file changes, generated-output collisions, shared services/devices/data, or any policy-prohibited work.

## Waits, commits, resources

Delegate wait-dominated commands and human-unblock watches at the PROJECT threshold before launch; keep the main thread on independent lightweight work. If an unexpected command runs long, poll boundedly and delegate comparable future waits rather than duplicate it. A wait monitor remains read-only and must stop on user input or state drift.

Follow PROJECT Git/commit policy and never absorb unrelated changes. Note fan-out, latency benefit, resource evidence, and contention; revert work types to sequential when parallel cost lacks value.
