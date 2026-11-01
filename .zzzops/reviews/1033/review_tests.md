# G1033 review_tests (attempt 2)

Reviewer: claude:e6ad/rd1025. Tests at 48a9617 (base b452cd7), design revision 2 (606311b).

## Verdict

**Approved.** Finding review_tests:1:1 is resolved, and no new finding is raised.

## Prior finding

| id | status | why |
|---|---|---|
| review_tests:1:1 | resolved | The recorded commands are now (1) the six-module unittest run and (2) the offline selection check `select_native_tests(discover_native_tests())`. The full `run_product_validation.py --platform linux` (the whole suite plus npm) is gone. I ran (2) from the worktree root: 0.11 s, exit 0. `select_native_tests` raises `ValueError` on an empty, duplicated or missing id (run_product_validation.py:129-137), so the check fails when a listed id is missing. |

## What I ran (from a detached worktree at 48a9617, root as the working directory)

- **Command 1** (`cd .agents && python -m unittest …`): 76 tests, 5 failures and 9 errors. All of them are the expected failures before implementation:
  - the bundle's full package check (canonical version) and its wrong-channel hint;
  - the harness-aware hint in each of the 7 layouts, plus the shared channel rule;
  - the cachebuster's Codex hint;
  - `require_no_package_check`;
  - the new `main()` wiring test.

  Nothing fails for environmental reasons.
- **Command 2**: passes. The new `NATIVE_COVERAGE` ids exist in the discovered set.

## The added test

`test_main_requires_no_package_check_entry_from_both_runtimes` counts `require_no_package_check(` in `inspect.getsource(main)`, and needs at least 2 occurrences. It fails today, because `main` does not call the helper yet, and it closes attempt 1's non-blocking note.

It is a source-level check. A call in a comment, or two calls on one runtime, would satisfy it. That trade-off is fine as defence in depth, because the bundle test covers the regression itself.

## Notes

- Attempt 1's note on `NO_POLICY` (the pinned `not_bootstrapped` text) still applies, and is still not blocking.
