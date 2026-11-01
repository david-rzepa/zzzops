# G1018 review_tests, round 1

**Verdict: approved.** I found nothing material. The tests (bcf4ecf, base 54d7e83: new `.agents/test_engine_card_budget.py`, edit to `test_card_shape_and_size`) cover design-1018-2 tests 1-8 and review_design round 2 notes 1-4. On the pre-fix engine they fail for the right reasons. A small prototype of the rendering part makes every view test pass.

## How I checked
- Ran the new file in a detached worktree at bcf4ecf under the scratchpad (since removed) on the unmodified 54d7e83 engine: 35 tests, 30 failures, 4 errors.
- Patched that throwaway worktree with a minimal design-shaped `value_of`/`checkpoint_view(cp, sub)`/`render.checkpoint_view` (commit, base), plus a stub `shrink_candidates`. The rendering does not cover shrink. Then I ran ValueOf*, CardView*, CardJourney* (default and renamed) and `test_card_shape_and_size`: 19 of 19 passed.
- Measured the fixtures and, with an instrumented `shrink`, the cards that `card.build` makes before `shrink` runs.

## Coverage against the design
- **G1** (a view is never blobbed): `test_real_size_cards_fit_with_every_view_inline`, `test_never_offers_a_checkpoint_view` (the view is the largest value on the card), and the G3 fixed-point test. On base, review_impl fails because old `shrink` blobs the `code` view, so it fails for the right reason.
- **G2** (shrink never grows a card): checked on the three fixtures, the small-instructions card and the `previous` card. On base these fail by 32 bytes (4,709 > 4,677) and by 331 bytes.
- **G3** (at most 4,096 bytes or nothing left to shrink; idempotent): a fixed point with `previous`, `shrink_candidates` empty after `shrink`, the argv and clip steps reported before `shrink` runs (review note 4), and the journey check on every card.
- **G4** (measured): hand-built fixtures, plus `RealLengthCardTests` through `card.build`, which grows when G1016 or G1000 add sections (review note 1).
- **Step order and lossless steps**: a card 100 bytes over loses only `argv`. `context.commands` is replaced only when the swap is smaller, and `["make"]` is kept (review note 3). A different `context.commands` is never replaced. A blobbed correction's `full` has no `summary`. Summaries are clipped to 120 characters and keep blob and read.
- **value_of**: `.change` gives no `tree`; `.tree` gives `tree`; a recorded producer works when it is not current; mismatched, missing and SKIPPED producers fall back to the bare value; a whole checkpoint gains `base`; a `deps` sub-field selector renders the view.
- **Cards and approve items**: review_tests shows the view (keys, values equal to the record, the diff lists `work/x.txt`, commit and base are commits). review_impl shows both views. The approve_merge `code` entry carries the implement commit and base. Fingerprints of all six consumers are checked against `fp_selected` of the recorded sub-field.

## Realistic fixtures
The fixtures load this repository's `.zzzops/POLICY.json` instruction texts, and on base the clip failure shows the real "Preserve behavior unless..." text. Sizes before `shrink` match the design's replay: implement 4,677 bytes (old `shrink` gives 4,709; the design says 4,710), review_tests 3,828 (design 3,829), review_impl 4,326 (the real card with views, per review_design, is 4,327). Cards from `card.build`: implement 4,693, review_impl 4,329, goal 1000, 28-character holders. These are not toy sizes.

## Key-summary format
The tests require `k=v` for scalars (JSON-style `true`, strings unquoted), `k: N items` for lists and `k: {…}` for nested dicts. Keys are sorted, joined with `; ` and clipped to 120 characters. Both `view()` and `shrink` use it (review note 2). This matches the design's rule and its example `details: 1 items; passed=true; tree=…`, where the full 40-hex tree fits in 76 characters. FakeReader matches `session.Reader.blob_view` exactly, so the helper has to post-process the summary rather than change `blob_view`. That fits the design's out-of-scope line.

## Lifecycle edit
The edit does not weaken the test. `4096 + 2000` becomes G3, as the design specifies. `submit.command` is now asserted as the exact string, which is stronger than before. `argv` is checked whenever it is present. `inputs.tests` must be a dict containing `diff`, where before a bare id was accepted. With the rendering prototype it passes.

## Notes (not findings)
1. The `ShrinkCandidatesTests` check `repr()` for "argv" and "clip|summar". That fixes the naming of the candidates a little, but any natural path or step label passes.
2. The fingerprint tests compare `fp_parts` with `fp_selected(recorded sub-field)` and do not use a pin captured on the pre-fix engine. That still catches the risky regression, where `resolve` returns the whole checkpoint, so I accept it.
