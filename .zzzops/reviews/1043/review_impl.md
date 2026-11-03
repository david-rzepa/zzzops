# G1043 independent implementation re-review — portable property guard

Decision: **approved**. No prior open implementation findings and no new findings. No unrelated finding statuses are invented.

Read the complete fresh official card and actual checks blob, then its previous.interdiff before reconciling source/tests/design and the new exact acceptance evidence. Implementation is `2b79bafc79427c08d7d9456c66ce7ab43b6c4700`; frozen tests are `932af741d3a7475c8ec63b8141549fa91330db30`; approved design remains revision 3 (`a361e31ab8798ddb675ac6b835eda82dd46266c9`); base remains `575015a9831ccd2ce724c3125dd74dd20029c1b5`.

## Code and coverage equivalence

Independently recomputed binary product patches from old tests5907d057 to old code53cc184c and new tests932af741 to new code2b79bafc, excluding review artifacts: **byte-identical**, SHA256 `91c2875e8b5400acb715e95077daaad55e92220c24908973b0f94111fd481502`. The restored implementation, docs/templates/package, process lifecycle/report fixes, timing data and nonfrozen fixture adaptations therefore retain the previous whole-diff approval recorded in `review-1043-implementation-codex.md`.

Independently checked source-tree differences between old/new implementations: only the two accepted frozen-test portability paths changed (`.agents/fixtures/g1043_property_ast.json`, `.agents/test_engine_cost_context.py`). Their new semantic guard was separately independently reviewed: hashes derive from immutable audited de5640d1 property blobebfd8a8c, preserve node kinds/order/scalars including None/False/empty string, and reject actual seed/step/assertion weakening. The guard/subcontrols pass under both Python3.10 and3.14. Property algorithm/seeds/steps/assertions are byte-identical to the audited source. Product paths were reverted before test_design, reviewed separately, then restored normally; no product implementation was frozen into the new tests.

The existing correctness assessment stands: every canonical ID is scheduled independent of hints; children and command lanes complete or fail with retained evidence; CPU limits clamp before allocation; exact-tree/global-timeout/termination safety is preserved; integer command timing and independent whole/repository comparisons share one bounded local newest-merged-source proof; contexts do not change approval identity; package/capability/schema/template/docs and separate policy rollout remain coherent. No new product difference warranted repeating the whole audit or suites.

## Actual verification and acceptance

The new official `context.checks` blob is `78f8c0ae9ef27de2136e22a22333139da643dd6b`. It records passed=true and eight command results with exit=0: all seven targeted commands plus the canonical serial suite, which took **1102 seconds**. Independently recomputed Identity.code_tree of actual code2b79bafc and obtained **c6baab65505807deb96ce5e053588a5da47fff18**, exactly matching that official check result. This installed-policy legacy result is distinct from the feature's sharded acceptance observation.

Independently inspected the complete final all-ID report and launch/checkpoint metadata: source2b79bafc stayed unchanged; **985 unique selected/executed/completed IDs**, all accounted for exactly once; zero failures/errors/invalid skips; **123.408907303 seconds** with20 workers on Python3.14.7. The extra ID is the accepted pure weakening-control test and uses the existing positive scheduling fallback. The measured owner-machine acceptance remains below300s; no source/hint change occurred during the run and no portable speed guarantee is claimed.

No redundant suites were run during this re-review. Installed policy and frozen graph fixtures remain unchanged. Informational baseline limits/load caveats and the separate owner-reviewed runtime/policy adoption remain as documented; this review does not replace new-head CI or merge authority.

## Dogfood notes

None.
