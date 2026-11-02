# G1027 review_tests (attempt 7)

Scope: the only tests change since the approved round 6 (`c401f1d..a223d45`): one new test, `LegacyMinTests.test_mapping_covers_the_rollouts_of_g1028_and_g1022` in `.agents/test_engine_capabilities.py`, answering review_impl:1:1.

## Against the design
- §3.3 map rule: `legacy_caps(min)` returns the capabilities of the highest listed version not above `min`; above the map gives the sentinel `engine_min_<min>`. §5: a goal that merged before G1027 gets its version added to `LEGACY_VERSIONS` with that engine's (cumulative) capabilities. G1028 (1.2.0, `finding_follows`) and G1022 (1.3.0, `lenses`) both merged first, so 1.2.0 = (lens_findings, finding_follows) and 1.3.0 = (lens_findings, finding_follows, lenses). The test pins exactly those tuples.
- Between entries: 1.2.5 -> 1.2.0's set. Above the map: 1.3.1 -> `engine_min_1.3.1`. Both match the rule.
- `follows_required` true at min 1.2.0, false at 1.1.0: pins that the `FOLLOWS_SINCE` replacement goes through the map.

## Against review_impl:1:1
Every requested case is covered: exact 1.2.0 and 1.3.0 tuples, 1.2.5, 1.3.1 sentinel, and both `follows_required` assertions. Each mutation the reviewer named (dropping `finding_follows` from 1.2.0, dropping `lenses` from 1.3.0, deleting an entry) fails at least one assertion.

## Brittleness
Exact-tuple assertions are deliberate: the map is a frozen compatibility contract, so any edit should fail loudly. Placement (tests line, before implementation) follows WORKER rule 6.

## Run
`python3 -m unittest discover -s .agents -p 'test_engine_capabilities.py'` in the g1027 worktree: Ran 27 tests, OK.

Verdict: approved, no findings.
