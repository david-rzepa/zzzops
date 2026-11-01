# Review of the G1016 tests (attempt 5)

Scope: commit 521d78b, which adds `next --goal` capability assertions to `CapabilityTests` in `.agents/test_engine_card_ux.py`. Nothing else changed since the approved tests: the range-diff is identical through ff6fb6e, plus 601a958/7921d86 (reviews), f9117d0 (the fix) and 521d78b.

## Evidence

I made two scratch copies of 521d78b. "new" is unchanged. In "old", `engine/render.py` and `engine/card.py` are reverted to 7921d86, the commit before the fix.

- new: `CapabilityTests` gives 4/4 OK, and the whole `test_engine_card_ux` module gives 30/30 OK.
- old: only `test_plain_start_of_reopened_node_after_base_moved_keeps_its_capability` fails, with `('reasoning', 1) != ('routine', 1)`. So the plain-start `next` assertion is what pins the fix (implement:3:1).

## Why the reclaim-case `next` assertion passes on both

I dumped the `next` action for the reclaimed, reopened `test_design`. It is the same on old and new:

`{"capability": "reasoning", "reason": "reclaim", "corrections": 1, ...}`. It has no `stale_because` and no `record_stale`.

The cause is in the frontier (frontier.py, the `reclaimable` branch). A reclaimable state is `{name, lease, fp, parts, corrections}`. Record staleness is only worked out at claim time, inside `start`. `run_capability` gets neither `record_stale` nor `stale_because`, so it returns None on both old and new code, and the node's own tier is used. `next` never shows a reclaimable node as base-stale, so this assertion cannot tell the two behaviours apart. That is expected, and it is not material:

- The design's reclaim promise (§2 "Reclaim", Verification (b)) is about the card. `test_reclaimed_reopened_correction_keeps_its_capability` already asserts `stale_because == ["inputs.base"]`, non-empty corrections and `run.capability == "reasoning"` on the reclaim card. That assertion was approved earlier and does catch the old card rule.
- The `next` assertion still guards against regressions. If a later change put `record_stale` on reclaimable states and dropped the corrections check, it would fail. It is cheap and not brittle.

## Non-blocking note (implementation, not a test gap)

I added a probe to the control test (scratch only). After the abandon, `next` shows the reclaim as `capability: "reasoning"` (test_design's own tier). The reclaim card then gives `routine`. So for a pure-rebase reclaim, `next` and the card still disagree, for the frontier reason above. The commit message's "next and the card share one rule" is true of the function, but not of the inputs it gets at reclaim.

This mismatch already existed before the fix. It errs on the safe side: it over-advertises the tier and never hands correction work to `routine`. The design makes no promise about `next` at reclaim. So it is not a finding against `test_design`. If wanted, a follow-up could carry `stale_keys(L.fp_parts, parts) ∪ record staleness` on reclaimable states. The control test could then assert `routine` from `next` after the abandon.

## Decision

Approved. No findings are open. The new assertions are sound. The plain-start one tells old code from new, and the reclaim and control ones are consistent regression guards.
