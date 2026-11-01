# review_tests for G1000 (attempt 4, after rebase onto dev 6747a5e)

**Decision: approved.** No findings.

## Scope
The tests were approved at 12e8d29 (base 54d7e83). G1000 was rebased onto dev 6747a5e; the test checkpoint is now 4087d8d. This review checks that the rebase left the tests unchanged and that they still pass.

## Rebase check
`git range-diff 54d7e83..12e8d29 6747a5e..4087d8d`:
- Test commits: `63c757e` (freeze the 12-node graph, lens tests), `91aec68` (rev 4 skip refusals, per-lens independence, impl intent staleness, skipped-node findings) and `4087d8d` (filter freshness without the state string; re-run intent_design) are all `=`, so they are byte-identical patches.
- Review/design doc commits: all `=`.
- Adapted commits: only `28ee9a2` (engine) and `f455c98` (skills and references docs). The engine changes are merge adaptations to dev's refactors: card shrink moved to `_steps`/`_apply` (G1018), and the `fp_parts(..., R)` call moved into the new `rparts` form in `frontier.py` (G1014). The docs changes keep dev's new text (G1001 idempotent `new`, G1014 edit/live-lease guidance, G1015 legacy item, migrate skill) next to the G1000 additions. None of this touches test code or test fixtures.

## Execution (on a `git archive` of 4087d8d)
- `.agents/test_engine_lenses.py`: 61 tests, OK (218 s). The only output is a harmless ResourceWarning from an unclosed file in a test helper.
- `.agents/test_engine_docs.py`: 3 tests, OK.
- `.agents/test_marketplace_bundle.py`: 10 tests, OK.

## Prior findings
None open.
