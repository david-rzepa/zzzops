# G1025 review_tests, attempt 4

Subject: tests checkpoint 848e66c (base b452cd7). Previous checkpoint 67a38f5. Design: `.zzzops/reviews/1025/design.md` revision 3.

## Verdict: approved

848e66c changes only `.agents/test_engine_branching.py` (plus the review file). It fixes five test setups that implement raised (implement:1:1 to 1:5). None of the changes weakens what a test asserts. Each one corrects a setup that implement could not satisfy without editing the frozen tests.

## Fixes checked against the design

- **implement:1:1 (§5.3, §13 item 5, a ready workspace op is blocked while base restacks).** On graph12, every agent workspace node feeds `run_tests`, so a ready agent never sits beside a ready `run_tests`. The old setup (reopening `test_design`) therefore could not hold. The fixture now adds a workspace agent `notes` that reads `base.base_commit`, so it is downstream of `base`, and `run_tests` does not read it. `BSim` gains a `workflow=` parameter for this. Before the target moves, the test asserts that `base` is current and that both `notes` and `run_tests` are ready. After `behind()`, it asserts `base` ready(upstream) and both nodes blocked with `restack`. This matches §5.3: pass 3 blocks every ready or reclaimable workspace node downstream of `base`, agents and ops alike. The `if current: reopen` guard only normalises the fixture's state. The precondition asserts that follow it keep the test strict.
- **implement:1:2 (§5.5, §13 item 7, release_sync ends on its own).** G1001's `integrate` is now stepped with a PR output shaped like the real one (`base: release/1`), so the dependent's heads input resolves. The asserts are unchanged: first `waiting(release_sync)`, then `ready` once only `merged_in_target` flips. This matches "the next evaluation with no other change makes base ready".
- **implement:1:3 (§7, hotfix member).** After `hotfix start`, the test continues from `base` through `merge`, rather than calling `done()`, which would re-run discovery. It still asserts that the merge closes the goal as done and that the PR base is `hotfix/<x>`.
- **implement:1:4 (ledger, corrupt document).** The seed fetches the goal ref before `commit-tree`. This is a fixture fix only.
- **implement:1:5 (§4 legacy fallback, one batch).** A warm-up `next` keeps the one-time policy download out of both counts. The equality `n1 == n3`, which checks for no git call per closed legacy goal, and the batch bound are unchanged. The count is still falsifiable: a per-goal `cat-file` would make n3 larger than n1, because the legacy set shrinks from 3 goals to 1.

## Run

In `/home/dave/Work/dev/zzzops/.zzzops/worktrees/g1025` at 5061b79 (implementation 2f583cf, on top of tests 848e66c):
`python3 -m unittest discover -s .agents -p 'test_engine_branching.py'` ran 56 tests in 223 s with result OK.
`git diff 848e66c 5061b79 -- .agents/test_engine_branching.py` is empty, so implement did not edit the frozen tests. 5061b79 touches only `.agents/test_engine_schemas.py`.

## Prior findings

review_tests:1:2 was already resolved, and no prior finding is open.

## New findings

None.
