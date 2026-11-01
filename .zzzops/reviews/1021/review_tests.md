# G1021 test re-review (280a301)

**Verdict: approved.** Finding review_tests:1:1 is resolved. No new findings.

## Finding review_tests:1:1 (ordering not pinned): resolved

Commit 280a301 adds `SameFileJourney.test_stale_conflicting_head_waits_for_the_rebased_head_instead_of_a_finding`. It follows the fix I asked for. With `head_lag=1`, H1 is CONFLICT_CODE and GitHub has seen it. dev then moves to DEV_CODE, `base` reopens and blocks, and the conflict is resolved by hand to `return 7` plus `extra()`. Then implement, run_tests and review_impl (if it is stale) run. The test asserts H1 != H2, no findings, a time wait with "has not seen the PR head" and no "checks pending", and that the op finishes ok on H2 once the checks pass.

I checked it in a temporary detached worktree at 280a301 (since removed), with a sketch of design step 5b applied: local merge-tree check, head-not-seen wait, GitHub conflict, then UNKNOWN wait.
- **Right order:** the new test passes.
- **Wrong order** (GitHub CONFLICTING checked before the head check): it fails on `assertFalse(findings)` with `integrate:conflict` "PR #1 conflicts with dev (DIRTY)". This is the regression it has to catch.
- **Unmodified code:** it fails with `'has not seen the PR head' not found in 'required checks pending: ci'`. That is the right red state before implementation.

The fake makes the failure real. With `head_lag`, `pr_json` computes mergeability against the shown head (H1), and H1 conflicts with the new dev tip. H2 is rebased onto dev, so the local merge-tree check is clean, and only GitHub's stale verdict can produce the finding.

## Scope

Between 1b17cc9 and 280a301, excluding `.zzzops/reviews`, only `.agents/test_engine_integrate_conflict.py` changed, and only by adding the one test method. `engine_fake_gh.py`, the other tests, and the verification commands and workflow are untouched.
