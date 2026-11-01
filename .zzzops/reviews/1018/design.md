# G1018 design: show the full checkpoint for inputs selected by `change` or `tree`

## Outcome

A card input whose selector is `<node>.<checkpoint output>.change` or `.tree` will render the producer's full checkpoint view: `commit`, `base`, `tree`, `change` and the `diff` command. Today the card shows only the selected id, which is a patch id or tree id. That id is not a commit and cannot be diffed. The change is limited to rendering. Fingerprints are still built from the selected sub-field and from nothing else, so no in-flight goal goes stale.

Approve items already expand these selectors. They will now also show `commit` and `base` explicitly, so the approve_merge item names the code commit.

Affected default-graph inputs (`templates/default/workflow.json`):

| consumer | input | selector |
|---|---|---|
| review_tests, implement, review_impl | tests | `test_design.tests.change` |
| review_impl, approve_merge | code | `implement.code.change` |
| run_tests, integrate | code | `implement.code.tree` |

## Findings at read_dev 54d7e83

- `engine/card.py` `value_of` (line 32) computes the output type only when `not sel.path`. For a sub-field selector `t` is therefore `None`, and the bare value goes through `view()`. Example: card-1014 review_tests shows `"tests": "3a1bf34f…"`.
- `card.checkpoint_view` renders `commit, tree, change, diff`. It leaves out `base`, which the acceptance asks for. `base` appears only inside the diff string.
- `engine/render.py` `approve_context` already has a branch for `sel.path[0] in ("change", "tree")`. It reads the whole checkpoint from `res.cur` and renders `render.checkpoint_view`, which returns only `diff` and `diffstat`. The commit is visible only inside the diff string. This is a small gap, not the blind spot the cards have.
- `value_of` is called only from `card.build`. Fingerprints come from `resolve` values through `fingerprint.fp_selected` / `carry.py` and never read the card. A rendering change cannot move a fingerprint.

## Approach

### card.py: `value_of` and `checkpoint_view` only

1. `checkpoint_view(cp)` also emits `"base": cp["base"]`. This applies to whole-checkpoint inputs as well. It adds about 50 bytes per checkpoint input.
2. In `value_of`, compute the producer's output type regardless of path, then derive:
   - `t` = that type when `not sel.path` (unchanged behaviour)
   - `sub` = `sel.path[0]` when the type is `checkpoint` and `sel.path` is `("change",)` or `("tree",)`, otherwise `None`.
3. When `sub` is set, `one(x, full)` renders `checkpoint_view(full)`. `full` is the producer's whole checkpoint output, taken from the same source `resolve` used for the value:
   - `node` kind: `res.cur[sel.node]` if present, else `recorded_out(res.doc, sel.node)`. This is the same `out_of` that `build` passes to `resolve`. The current `producer_out` lookup uses only `res.cur`, so it can disagree with `resolve` on a recorded-but-not-current producer.
   - `deps` kind: `portfolio().views[d]["cur"][sel.node][sel.output]`, which is the same place `resolve` read it.
   - Consistency guard: the full view is used only if `full` is a dict and `full[sub] == x`. Otherwise (missing, skipped, or mismatched) the card falls back to today's bare value. A wrong commit is never shown next to a fingerprinted id.
4. No extra `selected` key. The view already contains both `change` and `tree`, so the fingerprinted value is visible by name.

`commit` and `base` sub-fields are deliberately left alone. They already yield commit SHAs that a consumer may use verbatim (`_yields_sha`, base inputs), and the spec names only `change` and `tree`.

The `commands_to_run` loop in `build` (line 106) also tests `not sel.path`. It only handles `strings` outputs and is not touched.

### render.py: approve items

`render.checkpoint_view(ctx, cp)` adds `"commit": cp["commit"], "base": cp["base"]` before `diff`/`diffstat`. The existing sub-field branch in `approve_context` already selects the right checkpoint. No other change is needed.

### Size budget

A full checkpoint view is about 330 bytes. review_impl carries two (tests and code), so about 660 bytes, up from about 100. `shrink` blob-ifies the largest inline value first. Prompts and instructions (at most 600 bytes inline each) normally go before a checkpoint view does. The 4,096-byte limit is still enforced by `shrink`. The journey regression test (below) fails if a checkpoint view is ever pushed into a blob on a default-graph card, because it then finds no inline `commit`.

## Alternatives rejected

- **Change the graph selectors to whole checkpoints** (`test_design.tests`). This would change the fingerprints of every affected node and make every in-flight goal stale, and the sub-field binding exists for fingerprint identity. Rejected by the spec.
- **Resolve the full checkpoint inside `resolve` and carry it alongside `vals`.** This touches the fingerprint path and `frontier.py`, which G1014 is also changing. It is more risk for a rendering fix.
- **Add a separate `checkpoint` key to the card next to the bare id.** This is a second place to look and gives a different shape for the same output type. Rejected for uniformity: whole and sub-field inputs render alike.
- **Expand all four checkpoint keys.** This would change what `commit`/`base` consumers receive. Not asked for.

## Interfaces and data that change

- Card `inputs.<name>` / `context.<name>` for checkpoint `change`/`tree` selectors changes from a string to `{commit, base, tree, change, diff}`. A card is read by agents only. No stored data, fingerprint, schema or CLI argument changes.
- Whole-checkpoint card inputs gain `base`.
- Approve item `context[]` checkpoint entries gain `commit` and `base`.
- Docs: if `references/CLI_USAGE.md` or the card section of SPEC §3.14 lists the checkpoint view keys, it gets `base` and a note on sub-field selectors. I will check during implementation and touch one sentence at most.
- After merge, WORKER.md rule 9 (the manual goal.json workaround) can be dropped.

## Coordination with G1000 and G1016

The edit stays inside `value_of`, `checkpoint_view` (card.py) and `render.checkpoint_view`. G1000 adds a card `policy` section and `previous.changed` in `build`/`previous`. G1016's changes in card.py are also outside `value_of`. Any overlap is textual only, and whichever merges second rebases.

## Risks

- **Stale or mismatched producer**: handled by the equality guard and the bare-value fallback.
- **Deps sub-field inputs**: none exist in the default graph today. They are covered by the same code path and get one unit test.
- **Card growth**: covered under Size budget above. The worst case is an extra `shrink` step on an already large card, never a lost value.
- **Agents that parsed the bare string**: only the prompts read these inputs, and they already speak of "the checkpoint's `diff` command" (review_tests prompt), so this fixes the prompt/card mismatch.

## Tests

In `.agents/`, using existing fixtures (`engine_fixtures`, `self.n()` for renamed names), all run on both the default and the renamed graph:

1. **review_tests card** (lifecycle style): after test_design commits `work/x.txt`, `inputs.tests` has `commit`, `base`, `tree`, `change` and `diff`. `change` equals the recorded `test_design.tests.change`. Running the `diff` argv in the goal repo outputs `work/x.txt`. `git cat-file -t <commit>` is `commit`.
2. **review_impl card**: both `tests` and `code` carry the full view, and `code.diff` shows the implement change.
3. **run_tests / integrate** take `.tree`: covered by the journey test (ops have no card, so where only an approve item shows `.tree` this is a render check).
4. **approve_merge item**: `next --goal` approve item `context` entry for `code` has `commit` equal to the recorded implement commit, plus `diff`.
5. **Fingerprints unchanged**: for review_tests, implement, review_impl, approve_merge, run_tests and integrate, the input fingerprint the engine records/reports equals `fp_selected(graph, node, name, <recorded sub-field value>)`. In other words it is still a function of the bare `change`/`tree` id, and it is identical before and after the node's card is built (start). A test-only fingerprint pin captured on the pre-fix engine during implementation guards against a rendering-to-fingerprint leak.
6. **Fallback**: a unit test on `value_of` with a producer output whose `change` differs from the resolved value (stale case) returns the bare value. A `deps` sub-field selector renders the full view.
7. **Journey regression** (`test_engine_journeys.py`): `Autopilot.run_agent` keeps every card. Afterwards, for every `inputs`/`context` value of every card:
   - any dict carrying `commit` and `diff` must satisfy `git cat-file -t commit == "commit"`, and `base` must also be a commit;
   - no value is a bare 40-hex string that does not resolve to a commit. This generically catches a regression back to a patch id or tree id without naming nodes;
   - at least one checkpoint view was seen, so the test is not vacuous;
   - every card is at most 4,096 canonical bytes.
   It runs in `JourneyTests` and `RenamedJourneyTests`.

## Out of scope

- Expanding `commit`/`base` sub-field selectors, artifact sub-field selectors, or `deps` checkpoints in approve items (`approve_context` handles only `node` kind today).
- Exempting checkpoint views from `shrink`.
- Any change to fingerprints, `resolve`, the graph or the prompts.
