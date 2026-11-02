# Review of the G1025 tests, round 5 (sync onto dev 262d780)

Decision: **approved**. No findings open.

The tests were approved in round 4. This round checks only what changed when the tests were rebased onto dev 262d780 (G1027 capabilities, G1026 and G1041 merged). I compared the two lines with `git range-diff b452cd7e..848e66c4 262d7807..28990205`.

## Changes and how I checked them

1. **`.agents/test_engine_capabilities.py`: `SHIPPED` gains `release_lines`.** G1027 §3.1 says that a goal adding a capability appends its name to this set. G1025's capability is `release_lines`, which replaces the old `engine.min 1.2.0` gate. The implementation ships `engine/capabilities/release_lines.txt`, so this test fails without it. Correct.
2. **`.agents/test_engine_branching.py`, `ValidationTests.test_validate_policy_dir_needs_a_release_graph_with_branching`.** The copied template's `integration_branch` is now set to `"dev"` before `branching` is added. Two parts of the design require this:
   - Design §1: "The shipped `POLICY.json` template does not gain the block" and "The POLICY template is unchanged". dev's template keeps `integration_branch: "main"`, and the implementation diff (28990205..HEAD) does not touch `templates/default/POLICY.json`.
   - Design §1 validation: "a production branch equal to `integration_branch`" is refused. `BRANCHING.production` is `"main"`, so the test has to move integration to `dev`.

   The test still checks what it is meant to: validation passes with a release graph and fails without one. Reverting the template change and fixing the test setup was the right choice.
3. **`.agents/test_design_docs.py` (commit 7).** The only difference is conflict context. dev's `AMENDMENT_SENTINELS` now has the G1022 row where the G1020 row was. G1025's sentinel row is unchanged. No action needed.
4. **Post-implementation commit `28b1a103 test: count the new conflict exit code`.** It changes the exit-1 count in `.agents/test_engine_schemas.py` to 28, which is dev's 27 (after G1027 removed `engine_too_new`) plus G1025's new `conflict` refusal. This file is not frozen. The new count matches `EXIT` at HEAD.

Every other commit on the tests line is identical in the range-diff.

## Verification (worktree g1025, HEAD a08254c6)

- `python3 -m unittest discover -s .agents -p test_engine_branching.py`: 56 tests, OK
- `python3 -m unittest discover -s .agents -p test_engine_capabilities.py`: 27 tests, OK
- `python3 -m unittest discover -s .agents -p test_engine_schemas.py`: 35 tests, OK
