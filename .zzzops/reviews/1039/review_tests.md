# G1039 test review, cross-file line-hit correction

Approved. `review_tests:1:1` is resolved; no new findings.

The interdiff from `35bc8034d7ef6df94e0031e5af7fc6f9cf2bb54d` to source-free checkpoint `7d3e0eb2ed6c07b8a88c3d1f1c579e20dd7aa630` adds one 57-line case to the existing sync-card test file. It changes no implementation, earlier assertion, replay record or golden value.

The new fixture uses actual Git to establish a common template POLICY with `"min": "0.0.0"`, a newly added trunk graph26 POLICY containing the same plain JSON line, and a goal that removes that line only from the different template path. Assertions explicitly prove that the two changed-path sets are exactly their respective distinct files, have empty intersection, and that graph26 content remains unchanged in the goal. Thus shared-file intersections cannot satisfy the case.

The actual card builder must include the graph26 path with a reason saying trunk adds the exact JSON line that the goal removes. A code-name-only heuristic cannot satisfy these assertions: `min` is a plain word rather than a snake/camel/uppercase code name. This directly covers the motivating acceptance case rather than merely asserting a generic semantic hit.

The supplied focused run reaches the absent-sync-section assertion after the real Git/plumbing checks, which is the expected red state before implementation. Recorded production sharded orchestration accounts for all 25 new IDs exactly once, no skips, in 1.0435 seconds. I did not repeat a broad suite.

Prior carry/budget/shrink assessments and independent checks of all 54 immutable replay rows and the archived-base golden remain valid. Existing shared-path/name checks, hand-resolved-first ordering, capped detail, folding, last-resort preview and fixed-point assertions remain intact. The shipped POLICY activation restriction in design §3.6 is unchanged; implementation still must honor it.
