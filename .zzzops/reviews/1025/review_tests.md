# G1025 review_tests, attempt 2

**Verdict: changes requested.** review_tests:1:1 is fixed. review_tests:1:2 is only half fixed: the new test's "superseded does not complete the release alone" assertion runs while another release-1 goal is still open, so it cannot tell the two rules apart.

Subject: tests at `d863ad0` (base `b452cd7`; the changes since `e4e9334` are `9352cf2` and `d863ad0`). The design is revision 3 (`f240bd5`).

## review_tests:1:1: resolved

- `require_release_lines` now imports only `schemas`. It reads `engine.ENGINE_VERSION` lazily, inside the `engine.min` branch, and pops `min` whenever `requires` is used.
- **I simulated G1027 merging first.** In a scratch extract of `d863ad0`, I ran `del engine.ENGINE_VERSION` in-process and then imported `test_engine_branching`.
  - The import succeeds.
  - With `SETTINGS_SHAPE["engine"]` patched to G1027's shape (`min` optional, `requires` names), the helper returns `{"requires": ["release_lines"]}` with `min` removed.
  - With the current shape, it returns `{"min": "1.1.0"}`.
- The only other `ENGINE_VERSION` use (`test_capability_release_lines_is_declared`, lines 358-359) sits in the branch where no `capabilities/` directory exists, so it is safe under both merge orders.
- **The whole file at `d863ad0`:** 56 tests, 6 failures, 47 errors. This is the same missing-feature profile as attempt 1, plus the new test, so everything still fails for the right reason before implement.
- **The `GOLDEN_FP` regeneration rule is now written down.** Use the new base commit's engine, never the head, and the comment gives the command. This answers the attempt-1 note.

## review_tests:1:2: still open (one assertion)

The trailer half is fixed: `test_trailers_are_written_with_branching` closes a release-1 goal as superseded and asserts `Closed: superseded`.

The cut half is not fully fixed. Design §3.2 and D6 require every release-N goal to be closed, at least one of them `done`, with cancelled and superseded goals never blocking. `test_superseded_goal_neither_blocks_the_cut_nor_completes_the_release_alone` does this:
1. It creates `sup` and `a`.
2. It closes `sup` as superseded.
3. It asserts there is no cut item, commented "alone it does not complete release 1".

But `a` is still open at step 3, so the open-goal rule alone explains the empty result. The plausible wrong implementation counts superseded as done, for example `reason != "cancelled"`, mirroring the existing cancelled-only test. That implementation passes this test: it offers no cut while `a` is open, and it offers the cut once `a` is done.

**Fix.** Make the "alone" assertion run with the superseded goal as the only release-1 goal. Either:
- assert that no cut item exists after closing `sup` and before creating `a`; or
- add `test_only_superseded_goals_do_not_make_a_release_complete`, mirroring `test_only_cancelled_goals_do_not_make_a_release_complete`.

The "does not block" half of the test, where the cut is offered once `a` is done and lists `a`, is correct as written.
