# G1027 review_impl (attempt 2)

Re-reviewed `25186a5..3c27ed0` against design revision 2 and the round-1 review of `25186a5..6b068cb`. The checks cover 11 commands, including the full `.agents` suite, all passing. They ran on tree `e547d89`, which matches `3c27ed0` apart from `.zzzops/reviews`.

## Interdiff (owner reorder)
- `git range-diff 25186a5..6b068cb 25186a5..3c27ed0`: every earlier commit is `=` (patch identical). The implementation commits (`739e8f3`->`fa492f3`, `4cb2671`->`305f3e4`, `6b068cb`->`3238ab1`) are unchanged cherry-picks.
- New commits: only `a223d45` (the tests line, now placed before the implementation) and two review docs.
- Outside `.zzzops/reviews`, `git diff 6b068cb 3238ab1` is exactly the 11 added lines in `.agents/test_engine_capabilities.py`. The reorder changed no code.

## review_impl:1:1: resolved
`test_mapping_covers_the_rollouts_of_g1028_and_g1022` (a223d45) makes every assertion the finding asked for:
- the exact 1.2.0 tuple `(lens_findings, finding_follows)` and the 1.3.0 tuple `(lens_findings, finding_follows, lenses)`;
- a value between entries (1.2.5 gives 1.2.0's set);
- above the map (1.3.1 gives the `engine_min_1.3.1` sentinel);
- `follows_required` is true for `min` 1.2.0 and false for 1.1.0.

It passes in `test_engine_capabilities.py` (27 tests) and in the full suite. Existing assertions were not weakened: the commit only adds lines.

## Rest
The round-1 compliance, correctness and craft assessment still holds, since the code is unchanged. There are no new findings.

Verdict: approved.
