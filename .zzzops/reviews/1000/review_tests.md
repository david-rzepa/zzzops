# Review of the tests: G1000, attempt 3

Subject: tests checkpoint 12e8d29 (base 54d7e83). Design: `.zzzops/reviews/1000/design.md`, revision 4. The only change since the approved tests is 12e8d29, which edits two tests in `.agents/test_engine_lenses.py`.

## 1. `test_a_fresh_filter_record_without_a_verdict_keeps_the_note` (design §13, "Missing verdict fails safe"; §7 liveness)

The test no longer asserts `filter_design == "current"` after the hand edit. It now asserts two things: the filter is not in a `ready (stale…)` state, and the filter record's `input_fp` has not changed. Once the note goes live, design reopens and the filter, which is downstream of design, is blocked. So `current` was the wrong expectation.

- The `input_fp` check is close to a tautology, because the hand edit only touches `output.verdicts`. It is harmless, though. The real proof that the filter is fresh is still in the test: `design == "ready (reopened)"`, and the design card's corrections are exactly `[nid]`. Under §7, a filtered lens's finding is live only when the filter's latest record is done and fresh. So the note reopening design is only possible if the engine treats the hand-built record as fresh and counts the missing verdict as "kept". That is exactly the property §13 asks for.
- The test is not weakened. The unjudged note still goes live and still reaches the target's card.

## 2. `test_changing_intent_at_the_impl_stage_stales_only_the_intent_lenses` (design §13, intent staleness at both stages; D4, §6)

After the intent change, the test re-runs `intent_design`, plus `filter_design` if it is no longer current, before reading the states. Without that re-run, the stale design-stage intent lens holds the downstream impl nodes behind it, and `intent_impl` cannot show its own stale state. This re-run is needed to observe the property at the implementation stage. It does not mask it:

- `intent_impl` must still be exactly `ready (stale: policy.intent)`.
- Every node's stale set, minus `intent_design` and `intent_impl`, must still be empty. None of the other nodes are re-run, so a stale non-intent node would still fail the test.
- Every other impl lens, and `implement`, must still be `current`.
- The filter re-run is conditional. It only re-settles the design-stage join and does not reach any impl-stage assertion. The F1 tests cover the filter's own staleness separately.

## Run

I extracted 12e8d29 with `git archive` and ran both tests with `python -m unittest`: both pass (13.7s).

## Verdict

Both edits follow design revision 4 and keep what the tests prove. The unjudged note still goes live, and only the intent lenses go stale. No findings. Approved.
