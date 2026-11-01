# G1025 review_tests, attempt 3

**Verdict: approved.** The last open finding, review_tests:1:2, is now fixed, and I have no new findings.

Subject: tests at `67a38f5`. The change since `d863ad0` is in one test.

## review_tests:1:2: resolved

`test_superseded_goal_neither_blocks_the_cut_nor_completes_the_release_alone` now has three steps:
1. It closes `sup` as superseded and asserts that there is no `release_cut` item and that `releases.effective` is 1. At this point `sup` is the only release-1 goal.
2. It creates `a` only after that, and marks it done.
3. It asserts that the cut item is offered and lists `a`.

Step 1 now checks the "alone" half. An implementation that counts superseded as done (for example `reason != "cancelled"`) would offer the cut there and fail the test. Step 3 still checks that a superseded goal does not block the cut. The trailer test still asserts `Closed: superseded`.

review_tests:1:1 was already resolved in attempt 2, when I simulated G1027 merging first by deleting `ENGINE_VERSION` in-process and the file still imported cleanly. Nothing in this change touches it.
