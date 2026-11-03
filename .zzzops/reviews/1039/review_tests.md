# G1039 test review

Changes requested for one narrow acceptance-coverage gap. Independent provenance and the remaining substantive coverage check out.

## Finding: cover the cross-file plain-line hit from acceptance 1

`SyncCardTests.test_real_diffs_prioritize_hand_resolutions_and_semantic_hits_and_cap_at_twelve` uses forty files that both trunk and goal change. Its semantic example is `newName()` within one of those shared files. This proves some semantic prioritization, but it cannot establish the required G1027/graph26 case: trunk adds a new graph26 POLICY file containing a plain JSON line that the goal removes from a different template POLICY file.

A faulty implementation that only searches code-like names (and shared-file intersections) passes this test while omitting `.agents/fixtures/graph26/POLICY.json` from the sync card. The JSON key `min` is deliberately not a code-like snake/camel/uppercase name. Approved design §6.2 and acceptance 1 specifically require a direct removed-line match across different paths and identify that graph26 change as the motivating evidence.

Extend the existing small real-Git card fixture, or add one equally small case, so the goal removes `"min": "0.0.0"` from `templates/default/POLICY.json`, while trunk adds the same line under `.agents/fixtures/graph26/POLICY.json`. These paths must be different and the new graph26 file must not be in the goal's changed-file intersection. Assert the graph26 entry is present with a reason identifying the added line that the goal removes (not merely a shared-file or code-name reason). Preserve the hand-resolved-first ordering and bounded preview assertions already covered. No full goal journey, history-ref dependency or broad suite is needed.

## Coverage and independent evidence retained

I read the approved design revision 3, spec, full frozen diff and all three new test modules. The checkpoint changes only the seven intended test/fixture paths and no implementation.

- Real Git fixtures check U0 versus stored U3 identities, context-only changes, both whole-file union orders, interleaving/dropped/moved/wrong-copy/mixed-hunk counterexamples, binary/missing versions, unrelated scope, contained checkpoints and memoized resolution work. The carry/frontier fixture verifies kept recorded changes and frozen paths, current design/test reviews, fresh tree checks and the new base-sensitive code review.
- The material-round matrix distinguishes new material findings, notes, follows and carried/foreign findings, done agent records and op/human/blocked records. Exemptions distinguish non-checkpoint base-only stale nodes from checkpoint producers and code changes. Stage/frontier rendering and one tiny actual CLI journey check the stage-specific gate, continuation and legacy positional/shape compatibility.
- Sync shrink tests cover size-sorted touching blobs, folding after blob steps, bounded detail, unchanged previous evidence, idempotence, the existing final 80-character preview and under-budget preservation. The template test checks only the approved review_impl base edge and leaves tests review/filter edges unchanged.
- I independently matched all 54 literal replay rows to their named immutable goal records, including exact node attempt/status/reason, fingerprint parts and projected finding fields. Only minimal hashes/IDs/material/follows/target data are retained; no raw human questions or command tails are added. The literal expected totals remain G1026 3/4 and G1027 1/4.
- I independently archived immutable `8e5b98b63dd2ad6c8f719fbf1bd5ac273c9af9a7` and regenerated the shipped node/journey golden with only `review_impl.inputs.base = {from: base.base_commit}`. Both match the fixture; the archived shipped POLICY was left unchanged. This does not authorize adding round_budget to the shipped POLICY: activation remains the later installed-policy step in design §3.6.
- Recorded red evidence accounts for all 24 new IDs without skips in 0.8122 seconds. Collection is reported on Python 3.10 and 3.14. Those red results are intentional absent-feature evidence, not a passing product claim; the tiny CLI case still needs to reach its post-capability assertions after implementation.

The approved design's blanket equality between diff(T,M) and the full listed conflict set is not required by these tests. The documented modify/delete scratch counterexamples remain fail-closed under the observable U0/union contract. No false equality assertion or extra algorithm is requested here.

No broad suite was repeated, no product source was edited, and no owner decision is needed for this focused fixture correction.
