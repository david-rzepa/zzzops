# G1041 review_design (attempt 1)

**Verdict: approved.** The diagnosis matches the code at the read_dev commit, and the fix is the smallest one that works. No findings.

## Diagnosis checked against read_dev (f4eaf74)

- `Git.discover` (engine/gitrun.py:71) runs `git worktree list --porcelain` with `subprocess.run` and never checks `returncode`. If stdout is empty, the loop finds no `worktree ` line and refuses with "cannot find the primary worktree". This is exactly the CI symptom.
- `update_mirror` (engine/store.py:489) takes `coordinator.lock` without blocking. Only when `<common>/zzzops/coordinator` is missing does it run `git worktree add --detach`. The lock orders mirror updates against each other and nothing else, as the design says. So in the 20-way `next` test, one process adds the worktree while the other 19 run `discover`.
- `registered_worktrees` (engine/worktree.py:22) uses `git.run(..., check=True)`, so today the same race makes it raise `GitError`. The design keeps that failure path for the case where the retries run out.
- The jitter precedents the design cites (store.py:133, session.py:271) exist.

## Contention and budget

I ran an extra experiment (Git 2.55; 20 reader threads looping over the proposed 6-try helper for 15 s each; 1, 4 and 8 threads continuously adding and removing linked worktrees):

| churners | calls | needed a retry | max retries | exhausted |
|---|---|---|---|---|
| 1 | 58412 | 131 | 1 | 0 |
| 4 | 42996 | 75 | 1 | 0 |
| 8 | 35734 | 67 | 1 | 0 |

This churn is heavier than 20 workers running `start` at once (each adds one worktree, and housekeeping removes at most one). Under it, no call ever needed a second retry. Six tries is plenty. A healthy call costs nothing extra, and the about 1.3 s worst case applies only to a persistent failure, which then refuses with Git's stderr. That is reasonable for interactive verbs. The real-race test (test 5) should not be flaky.

## Simpler alternatives

- `git rev-parse --show-toplevel` run against the common dir does not help. Inside a `.git` directory it errors. Running it from the common dir's parent is the same derivation the design rejects, with the same `--separate-git-dir`, submodule and `core.worktree` gaps, and it changes the path form on Windows.
- Reading or holding the mirror lock covers only ZzzOps's own mirror add. It misses `start`/housekeeping worktree adds and removes, and the user's own. It would also serialize verbs.
- Checking the exit status and retrying is simpler than either.

## Non-blocking notes for implement

- The helper sketch returns `list | None`, but both callers need the last stderr (`details["git"]`, and `GitError(args, rc, stderr)`). Return it alongside the result, for example `(paths, rc, stderr)`.
- No SPEC edit is needed. `details.git` is additive and matches the existing not-a-repository refusal.
