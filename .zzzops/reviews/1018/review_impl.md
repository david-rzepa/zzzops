# G1018 review_impl (a18ca9a)

**Verdict: approved.** No material findings.

Scope: `git diff bcf4ecf a18ca9a` (implementation only; the frozen tests at bcf4ecf are untouched by a18ca9a, so the tests were not weakened). run_tests passed: the budget suite has 35 tests, lifecycle has 27, and the full suite has 412.

## Checks

- **Fingerprints untouched.** `value_of` is called only from `card.build` (card.py:119), after `resolve` has produced `vals`. It reads `res.cur` / `recorded_out(res.doc, …)`, both of which are pure, and nothing it returns flows back into `resolve`, `fp_selected` or the claim. No change to frontier.py, resolve, the graph or the schemas.
- **Same source as resolve.** For the `node` kind, the producer is `res.cur[p] if p in res.cur else recorded_out(doc, p)`, which is the same lambda `build` passes to `resolve`. For `deps`, it is `views[d]["cur"][node][output]`, as designed.
- **Match guard.** The view is rendered only when `full` is a dict, `full[sub] == x`, and `commit`/`base`/`change` are all present. Otherwise the input falls back to `view(reader, x)`, which is the old behaviour. `SKIPPED`/`Missing` are not dicts, so they fall back too. `sub` is set only for checkpoint outputs with path `("change",)` or `("tree",)`. The `commit` and `base` sub-fields are untouched.
- **checkpoint_view.** Renders `commit, base, change, diff`, plus `tree` only for `sub in (None, "tree")`. Whole-checkpoint inputs gain `base`, as specified.
- **render.checkpoint_view.** Adds `commit` and `base` ahead of `diff`/`diffstat`.
- **Never grow.** `shrink` accepts a step only if `len(out) < n`, and returns when no candidate reduces size. Step 1b ("see commands_to_run") is filtered the same way, which resolves review_design note 3. In my probe, `context.commands = ["make"]` was kept.
- **Never blob a view.** `_is_view` excludes any top-level input or context value that is, or contains, a dict with `commit`+`diff`. Prompts, instructions and corrections can't hold views.
- **shrink_candidates does not write to Git.** It measures with `_apply(card, st, None)`, and `_blob(None, …)` hashes locally with a stand-in the same shape as `session.Reader.blob_view`. In `shrink`, `reader.blob_view` is called only for the chosen step. In my probe, a 4.9 KB card made one reader call (the prompt), dropped `argv` first, ended at 2.9 KB, and a second `shrink` returned an identical card.
- **Step order.** The order is drop argv, point context.commands, clip summaries to 120, then blob the largest. `shrink_candidates` reports every kind of step, which resolves note 4. Correction `full` drops `summary`. Neither `_summaries` nor the blob candidates touch `previous`.
- **key_summary.** Output for a `checks`-shaped dict: `details: 1 items; passed=true; tree=abab…`. Scalars are `k=v`, with JSON for non-strings. Lists give `k: N items` and nested dicts give `k: {…}`. Keys are sorted and the result is clipped to 120. `view()` uses it too, through `_blob`, which resolves note 2.
- **Edit scope.** Changes are limited to imports, the docstring, `value_of`, `view`, `checkpoint_view`, `shrink`, new helpers placed before `shrink` (`key_summary`, `_blob`, `_is_view`, `_summaries`, `_steps`, `_apply`, `shrink_candidates`), and `render.checkpoint_view`. There are more helpers than the design's "one card-local blob helper", but they are all new top-level functions next to `shrink`, and nothing in `build`, `previous` or `finding_effect` was touched.
- **Mergeability.** `git merge-tree` of a18ca9a with `zzzops/work/g1000` (d5e46d1) is clean. With `zzzops/work/g1016` (601a958) there are two textual conflicts, both trivial: (1) the `from engine.render import …` line (this goal adds `clip`, G1016 adds `from engine.schemas import SHA`; keep both), and (2) the key list in `test_card_shape_and_size` (G1016 drops `renew`; keep G1018's G3 assertion), which review_design had predicted. There are no semantic overlaps.

## Non-material notes

- `producer_out` for the `node` kind now falls back to `recorded_out` when the producer is not current. As a result, artifact inputs from a non-current producer now show the recorded `summary`, where before they showed none. This is consistent with the value resolve used, so it is harmless.
- When the reader is the render-only null reader, `_blob` returns only `{summary}`, which is smaller than the stand-in it was measured with. The measurement is therefore conservative, and that is fine.
