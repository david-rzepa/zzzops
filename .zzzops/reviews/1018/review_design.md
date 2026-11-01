# G1018 review_design, round 2

**Verdict: approved.** F1 is resolved. The design now meets the budget it claims on real-size cards, says plainly that 4,096 bytes is a target, and tests the bound that actually holds. The new `shrink` steps lose no information an agent needs. I have no new material findings. Four implementation notes are listed at the end.

## F1 (review_design:1:1): resolved

I checked the replay against `shrink`, `view`, `render.command` and `reader.blob_view` at 54d7e83 (card.py:197-232, render.py:50, session.py:49), then ran `g1018/sim2.py` and `g1018/all.py` myself. Results:

- **The replay is faithful.** It rebuilds each pre-`shrink` card from the real prompt and policy blobs and inlines exactly the texts that `build` would inline (INLINE = 600). On HEAD it shows implement at 4,219 bytes before `shrink`, which confirms the design's claim that today's `shrink` makes a card larger. One difference: the replay's old `shrink` uses 120-character summaries where the engine uses 200, so its "today" figure (4,410) comes out below the real 4,621. That only makes the old baseline look better, so it doesn't weaken the comparison. The new-`shrink` replay clips fewer summaries than the design does (it never clips the prompt's), so its numbers are conservative.
- **Numbers reproduce exactly:** implement 3,745 (tests view inline), review_tests 3,829, the synthesized review_impl 3,765 with both views inline, 1015-design-2 at 4,092, and every card without `previous` at 4,096 or less.
- **A real review_impl card exists now** (`card-1014-review_impl-z.json`, 3,821 bytes, with bare `tests` and `code` ids and `checks` blobbed to `{`). The design's table says "no real card yet". I put both views into it: 4,327 bytes before `shrink`, and 3,973 after it drops only `argv`. Both views stay inline. So the card the spec most needs to fix meets the target with about 120 bytes to spare. My extra script is `g1018/rv_ri.py`.
- **G2 and idempotence:** across all 42 run-folder cards, with every bare 40-hex `tests` or `code` input replaced by a view, the new `shrink` never made a card larger, and a second `shrink` changed nothing. No card without `previous` ended over 4,096 bytes.

**The decision is stated honestly.** "4,096 is a target, not a hard limit" is in the Outcome section. The module docstring changes to match. The `4096 + 2000` allowance is replaced by G3. `previous`, the one thing that keeps cards over (1.3–4.7 KB measured), is named and deferred to a proposed child goal after G1000. G1 to G3 are structural and each one has a test. G4 is clearly marked as measured, not guaranteed.

## Information-loss check (new shrink steps)

- **`argv` dropped, `command` kept.** `command` is the full runnable string (`render.command` joins `ctx.prefix` with shlex-quoted argv), so nothing an agent runs is lost. The step applies only to cards over budget, and the only consumer at 54d7e83 is `test_engine_lifecycle.py:313` (`test_card_shape_and_size`), which the design already changes. Nothing under plugin references, rules or skills reads `argv`. The step pops only `argv`, so G1016's new `commands.renew.when` survives it.
- **`context.commands` becomes "see commands_to_run"** only when it equals `commands_to_run.list`. No information is lost.
- **Summaries clipped to 120 characters.** Every blob view keeps its `blob` and `read`, so the full text is one command away. The design doc summary is the only clip a reviewer would notice, and a reviewer reads that doc in full anyway.
- **Blobbed dict/list key summary.** I checked it against the real `checks` blob (40e522f8): its keys are `details`, `passed` and `tree`, so the summary reads `details: 2 items; passed=true; tree=…`. That is useful where `{` was not.
- **Correction `full` drops its `summary`.** That summary only repeats the first 200 characters of `text`, so this loses nothing.
- **Checkpoint views are never candidates.** The default graph has no `deps` checkpoint inputs (I checked workflow.json), so no view can sit inside a deps map and be blobbed along with it.

## Mergeability with G1016 and G1000

- **G1016 (design attempt 3)** edits `build`: it removes the top-level `renew`, adds `commands.renew.when` and a `changed` section, and changes `output_schema` text and the `record_stale` rules. G1016 states "`shrink()` needs no change". G1018 edits `value_of`, `view`, `checkpoint_view` and `shrink`. The two touch different functions, and the argv drop works on any command dict. The one shared spot is the key list in `test_card_shape_and_size`: G1016 drops `renew` and G1018 switches to `command` plus G3. That is a trivial textual merge.
- **G1000** edits `previous()` (`previous.changed`) and adds the `policy`, `candidates` and `notes` sections in `build`. These are also new sections `shrink` doesn't touch, so they share `previous`'s status: G3 still holds, and G4 may get tighter. G1018 deliberately sequences the "bound `previous`" child goal after G1000. No function overlaps.

## Notes for implementation (not findings)

1. **The "G4 catches the drift in CI" claim (Risks) is too strong.** G4 is tested with hand-built dicts of fixed size (test 6), so new card sections from G1016 or G1000 won't change those fixtures. The journey test checks only G3. Either reword the risk to "G4 guards the measured shapes", or build one G4 fixture through `card.build` with real-length labels.
2. **Use the key summary in `view()` too.** On the real review_impl, `checks` is blobbed by `value_of`/`view()` at INLINE = 600, not by `shrink`, so it shows `{` unless the new card-local helper also serves `view()`. The design already lists `view` among the functions it edits. Make it explicit.
3. **Step 1b and G2.** The string "see commands_to_run" is longer than a very short list such as `["make"]`. Apply 1b only when the swap makes the card smaller, as step 3 does, so G2 holds unconditionally.
4. **`shrink_candidates` should report the lossless and clip steps as well as blob steps.** Otherwise the journey test's "≤ 4,096 or no candidates" check could pass on an over-budget card that still carries `argv`.
