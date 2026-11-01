# G1016 review_impl (attempt 2)

Reviewed: cc26f29 (code) and 521d78b (tests), both on base 54d7e83, against design attempt 4. The prior review was at 8da55ca/601a958. run_tests passed: 100 targeted tests, the full 407-test discovery, and prompt_stats --check. I also re-ran `test_engine_card_ux.CapabilityTests` on an export of cc26f29. All 4 passed.

## Verdict: approved

## Prior finding

- review_impl:1:1 (`next` advertised `routine` for a correction run): **resolved**. f9117d0 adds `render.run_capability(state)`, one rule that both `render.capability` (for `next` actions) and `card.build` call. A retry gets `reasoning`. A run stale only on `inputs.base` with no corrections gets `routine`. Anything else falls back to the node's own tier. The rule reads the record's staleness: it uses `record_stale` when that key is present, which it always is on a card because `verbs.staleness` always sets it, even when it is None. Otherwise it uses `stale_because`, which on a frontier `ready/stale` state comes only from the record (`frontier.py:219`). So the card gives exactly what it gave at 8da55ca. `next` now leaves out the routine downgrade when there are live corrections. The new tests in 521d78b check the `next` action's `(capability, corrections)` for three cases: a reopened correction stale on base gets reasoning with 1 correction, a reopened reclaim after abandon gets reasoning with 1 correction, and a pure base restack gets routine with no corrections.

## Scope since 8da55ca

`git diff 8da55ca cc26f29 -- ':/' ':(exclude).zzzops/reviews'` touches only engine/card.py and engine/render.py (the fix) and .agents/test_engine_card_ux.py (the ff6fb6e refspec narrowing and the 521d78b `next` assertions). Nothing else changed, and no test was weakened.

## Known, not raised

At a reclaim, `next` shows the node's own tier, while the card can show `routine` for a pure-rebase reclaim. This happens because reclaimable frontier states carry no record staleness. The mismatch only over-provisions `next`. Correction runs never get downgraded on either surface. It is a logged follow-up and outside this design's promises.

No new findings.
