# G1051 implementation review

Decision: changes requested. Reviewed commit `12b1237dd5e0ae45f99847632787c22d078ff287` against the approved design and assigned lenses.

## Findings

1. **Approved PR head can be bypassed after an external merge.** `plugins/zzzops/zzzops/engine/ops/lines.py:167-177,283-284` accepts already-merged PRs without requiring the approved head. A local real-Git/fake-provider fixture paused finish at provider `pr view` after approval of T, advanced and externally merged the PR at H, and resumed. Production included H; finish requested forward-port approval instead of detecting the divergence. Existing merge-base and provenance checks do not establish the approved head was merged. Handle already-merged and recovery paths with exact-head evidence and block propagation on a mismatch.

2. **Nested maintenance forward-port can reject a valid released common base.** `plugins/zzzops/zzzops/engine/forward_port.py:91-95` checks only the maintenance source and its direct parents. If 2.1 contains multiple commits after the verified release-2 base, 2.1.1 based on 2.1 cannot be forwarded to dev or release 3 despite the legitimate release-2 common ancestor. Traverse and verify recorded release provenance and test this scenario.

## Validation and scope

The local full engine suite passed 1,168 tests in approximately 209 seconds; the focused goal-specific tests passed. The race was exercised against the actual changed engine and real Git using the repository fake GitHub provider. This review separately considered identity normalization and aliases, legacy writer opt-in, approval refusal, source/destination races, maintenance no-diff evidence and scope. GitHub protected-branch staging was not run here; local provider tests do not replace it.
