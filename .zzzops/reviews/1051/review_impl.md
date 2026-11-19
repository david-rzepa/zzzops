# G1051 implementation re-review

Decision: changes requested. Reviewed `4223972b644696fe9895682000ae78cc7e199615` and its interdiff against the design.

The two prior findings are resolved: merged-head verification checks the approved head and actual merge parents before propagation, including recovery; nested forward-port follows verified historical release provenance and rejects source-goal cycles. All four focused real-Git/provider tests passed locally in 37 seconds. The implementation verification reports all 1,172 tests passing; the changed-test timings and full-suite cost are proportionate to the release journeys. Hosted protected-branch behavior was not independently tested.

## New finding: unrelated historical PR blocks finish

`plugins/zzzops/zzzops/engine/ops/lines.py:298-307` selects the first merged PR for the branch and production base, even if its head predates the approved release tip. An earlier PR from the same branch can have been merged before further work and a new approval; that older PR is unrelated to the current finish, but the new verifier blocks on it and never finds or creates the PR for the approved tip. The former code filtered out such older heads. Correct candidate selection while retaining detection of a changed-head merge of the current PR, and cover this ordinary-release scenario.
