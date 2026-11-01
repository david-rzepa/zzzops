# G1018 review_design

**Verdict: changes requested, one finding (F1, card size budget).** The rendering and fingerprint parts of the design are sound and I checked them against read_dev 54d7e83. The size budget section does not hold up against real cards. As designed, the fix would be undone on the cards it targets.

## Claims checked and confirmed

- **Rendering cannot move a fingerprint.** `value_of` has one caller, `card.build` (card.py:75), and `build` has one caller, `verbs.start` (verbs.py:200). `build` runs after `claim` has fixed the lease and its fingerprint parts. Fingerprints come from `resolve` values through `fp_selected`. `selector_type` returns `plain` for any selector with a path, so the fingerprint is `sha256(H(<change id>))` and has nothing to do with the view. `checkpoint_view` builds a new dict and does not mutate `vals`. Test 5 is a reasonable belt-and-braces check.
- **The guard is sound.** For `node` selectors, `build` resolves with `res.cur[p] if p in res.cur else recorded_out(doc, p)`. The design takes `full` from exactly that source, so `full[sub] == x` always holds when the producer is present. The guard is effectively a check of type and presence: `recorded_out` can return `SKIPPED` or `Missing`, and neither is a dict. That is harmless and correct. For `deps` selectors, `resolve` reads `dep_view[d]["cur"][sel.node]` from `session.portfolio().views`, which is the same object `value_of` already uses, so the guard is also exact for stacked goals. One leftover gap, which I am not raising as a finding: a dependency's commit may not be fetched locally, so its `diff` may not run. That already happens today for whole-checkpoint `deps` inputs, and no default-graph input uses a `deps` sub-field.
- **Approve items.** `approve_context` already expands `change`/`tree` from `res.cur`. Adding `commit`/`base` to `render.checkpoint_view` is enough.
- The selector table and the `commands_to_run` note match `templates/default/workflow.json` and card.py.

## F1 (target: design): the 4 KB budget does not hold, and `shrink` will blob the new views on the cards that need them

The design says a view costs about 330 bytes, that prompts and instructions go first, and that "the 4,096-byte limit is still enforced by `shrink`". The real cards at this tip say otherwise:

- `card-1014-implement` at 54d7e83 is **4,621 canonical bytes** before this change. Its prompt and all four instructions are already blobs. `shrink` stops when no candidate over 100 bytes is left and returns an oversized card. The existing `test_card_shape_and_size` allows `4096 + 2000` for this reason. So the limit is not enforced today.
- A sub-field view adds about 303 bytes (355 vs 52 bytes for `"tests":…`). On implement, the new `tests` view becomes the largest remaining candidate, so `shrink` replaces it at once with `{"summary": "{", "blob", "read"}`. `blob_view` summarises the first line of the `indent=2` JSON, and that line is `{`. The card then shows less than it does today: no inline id and no commit.
- review_impl, worked out from the implement and review_tests cards: three instruction blobs, the doc artifact, a `checks` context blob, the review `output_schema`, the artifact and `--artifact` in the commands. That is about 4.1 KB before the fix and about 4.7 KB with two views. `shrink` would blob both views. This is the card the spec most needs to fix.

**Consequences.** On real-size cards the acceptance criterion "a review_impl card carries commit, base and diff" fails. The reviewer still has to dig: `cat-file` a blob whose summary is `{`, which is arguably worse than the bare id. The design's own journey test either fails, because no inline commit is found and cards exceed 4,096 bytes, or passes only because fixture holders, paths and model lists are shorter than real ones. In that case it hides the problem instead of guarding against it.

**What would fix it:** pick one approach and state measured numbers for real implement and review_impl cards.
1. Exempt checkpoint views from `shrink`, as the last resort or never. The design's out-of-scope list says otherwise, and that would have to change. Then recover space elsewhere in `shrink`, for example by truncating artifact `summary` (up to 400 bytes per artifact, and never a `shrink` candidate today because the dict holds `blob`) before anything else, and/or by dropping the duplicate `argv` or `command` form in `commands` (about 350 bytes over four commands).
2. Make the view smaller: drop `tree` unless the selected sub-field is `tree`. `diff` already carries base and commit, but the spec asks for `base` explicitly, so the saving is about 50 bytes. On its own this is not enough.
3. If 4 KB cannot be met without wider changes, record that as an explicit decision, and make the journey test assert the actual limit `shrink` guarantees (and that views stay inline) instead of a 4,096 bound that already fails at HEAD.

A secondary fix belongs with any of these: if a view is ever blobbed, give `blob_view` a useful summary (for example `commit <sha>`) instead of `{`.

## Minor (no finding)

- Journey test bullet "no value is a bare 40-hex string that does not resolve to a commit": keep it to top-level `inputs`/`context` values. Artifact dicts hold `blob` ids, which are not commits, so a recursive walk would fail falsely.
