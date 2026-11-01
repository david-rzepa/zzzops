# G1021 test review (1b17cc9)

**Verdict: changes requested. One finding.** The tests are faithful and fail for the right reasons. One property the design review required is not pinned: GitHub's conflict verdict must come after the head-not-seen wait.

## What I checked

- **The faults are off by default.** `fault_count` returns 0 when a fault is absent. `advance_before_view` pops a missing key and gets `None`. With no faults, `pr_json(view=True)` gives `shown = pr`, so the output matches the old code. The faults only touch `pr view`; `pr list`/`create`/`merge` are unchanged. I ran `test_engine_github` and `test_engine_base` on the new fake, with a sketch implementation applied: 29 tests, OK.
- **The faults match GitHub's behaviour.** `mergeable_lag` is keyed on `(shown head, base tip)`, so it reads UNKNOWN again whenever the head or the base moves. That is how GitHub's lazy recomputation behaves. `head_lag` shows the old head, and computes both mergeability and the rollup against that old head. That is right: a stale view has stale mergeability and stale checks. `advance_before_view` fires once and models dev moving between the fetch and GitHub's computation.
- **The incident regression** (`test_conflict_with_mergeability_lag_...`) reproduces #747/#748. The PR is created by the integrate run itself, dev already conflicts, the first and only `pr view` reads UNKNOWN, and the test asserts the `conflict` finding on `base` with `src/app.py` in the text, `base` reopened, and exactly one view.
- **The no-checks timing** is pinned. Polls at t=0 and t=5 return `time`, and the retry_after values are pinned at 5 and 15. The poll at t=15 returns `human`, and the question names #1, the head, MERGEABLE and both options. The 120-minute question is excluded. The contrasting case, where a pending required check is in the rollup, keeps waiting through t=35.
- **The two-goal journey** follows the design: A merges, B's first view is lagged UNKNOWN, B gets the conflict finding, `base` blocks with `rebase conflict in src/app.py`, B is resolved by hand, `base_commit` is the dev tip, `implement` is stale, and B is integrated and merged with the resolved content on dev.
- **The tests fail before the implementation, for the right reasons.** I ran them in a temporary detached worktree at 1b17cc9 (since removed). 6 of 8 fail: the 5 new behaviours, plus the journey, which fails on "required checks pending: ci" where it expects the finding. Two pass, as expected, because they are guards on unchanged behaviour: the GitHub-only conflict and the pending check that keeps waiting. A sketch implementation of the design makes all 8 pass, so the tests can be satisfied and nothing in them is self-contradictory.

## Finding 1 (test_design): the head-seen-before-GitHub-conflict ordering is not pinned

The design review's implementer note 1 requires this order: head-not-seen wait, then GitHub conflict, then UNKNOWN. A stale head can be CONFLICTING while the rebased H is clean. If the conflict check runs first, a goal that was already rebased gets sent back to `base` for nothing. `test_head_not_yet_seen_...` cannot catch this, because dev moves with a non-conflicting `other.txt`, so the stale H1 also reads MERGEABLE. **Probe:** I put the GitHub conflict check *before* the head check in the sketch implementation, and all 8 tests still passed.

**Fix:** add a test in which the stale head conflicts and the rebased head does not. I checked that this test passes with the right order and fails with the wrong one (with the wrong order, `out["ran"]` has no `blocked`, because a finding came back):

1. Set `head_lag=1`, then `deliver(g, code=CONFLICT_CODE)` and run `integrate` (GitHub has shown H1).
2. `push_dev(DEV_CODE)`, `reopen base`, and run `base`, which blocks. Resolve to content compatible with dev (for example `return 7` plus an extra function), then `rebase --continue` and run `base`, which is done.
3. Run implement, run_tests and review_impl if it is stale, as in the journey.
4. Run `integrate`. H2 must differ from H1. `assert_waits_not_on_checks(out, "has not seen the PR head")`, and assert that there are no findings.
5. `set_checks(H2, pass)`, run `integrate`, and expect ok.

GitHub CONFLICTING versus UNKNOWN needs no test. The two values exclude each other in one view.

## Not findings

- `test_conflict_seen_only_by_github_...` passes before the implementation. It is correct as a guard: it fails if an implementation relies on the local check alone, because GitHub's verdict is then lost.
