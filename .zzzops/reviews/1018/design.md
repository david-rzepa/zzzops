# G1018 design (attempt 2): show the full checkpoint for inputs selected by `change` or `tree`

## Outcome

A card input whose selector is `<node>.<checkpoint output>.change` or `.tree` will render the producer's checkpoint view: `commit`, `base`, `change`, the `diff` command, and `tree` only when `tree` is the selected sub-field. Today the card shows only the selected id, which is a patch id or tree id. That id is not a commit and cannot be diffed. Fingerprints are still built from the selected sub-field and from nothing else, so no in-flight goal goes stale.

Checkpoint views are never moved into a blob by `shrink`. To pay for them, `shrink` first removes parts of the card that are truly redundant, and it no longer makes a card bigger. Measured on the real cards at 54d7e83, the implement card goes from 4,621 to about 3,745 bytes with the new view, and review_impl comes out at about 3,765 bytes with both views inline.

**Budget decision: 4,096 bytes is a target, not a hard limit.** Every measured card without a `previous` section meets it after this change. Review cards from round 2 on carry `previous` (prior findings and responses, up to 4.7 KB on its own), which `shrink` does not touch. Those cards stay over the target, as they are today. The tests assert the bound that is actually guaranteed (see Size budget).

Approve items already expand these selectors. They will now also show `commit` and `base` explicitly, so the approve_merge item names the code commit.

Affected default-graph inputs (`templates/default/workflow.json`):

| consumer | input | selector |
|---|---|---|
| review_tests, implement, review_impl | tests | `test_design.tests.change` |
| review_impl, approve_merge | code | `implement.code.change` |
| run_tests, integrate | code | `implement.code.tree` |

## Findings at read_dev 54d7e83

- `engine/card.py` `value_of` (line 32) computes the output type only when `not sel.path`. For a sub-field selector `t` is therefore `None`, and the bare value goes through `view()`. Example: card-1014 review_tests shows `"tests": "3a1bf34f…"`.
- `card.checkpoint_view` renders `commit, tree, change, diff`. It leaves out `base`, which the acceptance asks for.
- `engine/render.py` `approve_context` already expands `sel.path[0] in ("change", "tree")` from `res.cur`, but `render.checkpoint_view` returns only `diff` and `diffstat`.
- `value_of` is called only from `card.build`, after `claim` has fixed the fingerprint parts. Fingerprints come from `resolve` values through `fp_selected`. A rendering change cannot move a fingerprint (confirmed by review_design).
- **`shrink` does not enforce 4,096 bytes, and it can grow a card.** Measured with a replay of `shrink` on the real cards (the replay reproduces card-1014-implement at exactly 4,621 bytes):
  - Before `shrink`, the implement card is 4,219 bytes. `shrink` blobs its prompt and four instructions. Each `blob_view` (200-character summary, 40-hex blob id, and a `read` command that repeats the id) is larger than the instruction text it replaces, so the card ends at 4,621 bytes, 402 bytes bigger. It then stops, because nothing over 100 bytes is left to blob.
  - The parts `shrink` never touches are `commands` (676–760 bytes: each command appears twice, as `argv` and as `command`), artifact summaries (up to 400 bytes each), the `full.summary` of a blobbed correction (it repeats the first 200 characters of `text`), and `previous`.
  - Blobbing a dict or list uses `json.dumps(indent=2)`, so its summary is `{` or `[`. This affects `run_tests.result` (`checks` on review_impl, up to 4 KB of `details`) today, and it would affect a checkpoint view.
  - `test_card_shape_and_size` allows `4096 + 2000`, and its last assertion accepts a bare id for `inputs.tests`.

## Approach

All code edits stay inside `value_of`, `view`, `checkpoint_view` and `shrink` in card.py (plus one card-local blob helper and the module docstring), and `render.checkpoint_view`. G1016 edits other parts of card.py (the renew field, `output_schema` wording, `finding_effect`), and G1000 edits `build`/`previous`. Any overlap is textual only.

### 1. Rendering the view (`value_of`, `checkpoint_view`)

1. `checkpoint_view(cp, sub=None)` returns `commit`, `base`, `change` and `diff`, and adds `tree` when `sub` is `"tree"` or `None` (a whole-checkpoint input, which keeps today's keys plus `base`). Leaving out `tree` on `change` inputs saves about 50 bytes per view. `tree` is useless to a reviewer, and `change` stays because it is the fingerprinted value.
2. In `value_of`, compute the producer's output type regardless of path, then derive:
   - `t` = that type when `not sel.path` (unchanged behaviour)
   - `sub` = `sel.path[0]` when the type is `checkpoint` and `sel.path` is `("change",)` or `("tree",)`, otherwise `None`.
3. When `sub` is set, `one(x, full)` renders `checkpoint_view(full, sub)`. `full` is the producer's whole checkpoint output, taken from the same source `resolve` used:
   - `node` kind: `res.cur[sel.node]` if present, else `recorded_out(res.doc, sel.node)` (the same `out_of` that `build` passes to `resolve`).
   - `deps` kind: `portfolio().views[d]["cur"][sel.node][sel.output]`.
   - Guard: the view is used only if `full` is a dict and `full[sub] == x`. Otherwise (missing, `SKIPPED`, mismatch) the card falls back to today's bare value. A wrong commit is never shown next to a fingerprinted id.
4. `commit` and `base` sub-fields are left alone: they already yield commit SHAs.

### 2. Approve items (`render.checkpoint_view`)

`render.checkpoint_view(ctx, cp)` adds `"commit"` and `"base"` before `diff`/`diffstat`. The existing sub-field branch in `approve_context` already picks the right checkpoint.

### 3. Size budget (`shrink`, blob summaries)

`shrink` still runs only when the card is over `CARD_LIMIT` (4,096). It applies steps in this order and stops as soon as the card fits:

1. **Lossless.**
   a. Drop `argv` from each `commands` entry and keep `command`. The entry stays a dict, so the shape agents read does not change, and `command` is the form workers copy. This saves about 400 bytes on a review card.
   b. If `context.commands` equals `commands_to_run.list`, replace it with the string `"see commands_to_run"` (implement: about 50 bytes).
2. **Shorter previews.** Clip the `summary` of every blob view already on the card (artifact inputs and context, blobbed prompt and instructions) to 120 characters. The full text is one `read` away. This saves about 280 bytes on implement and review_impl.
3. **Blob the largest inline text, as today**, with three changes:
   - Checkpoint views (a dict with `commit` and `diff`) are never candidates.
   - A step is kept only if it makes the card smaller. Otherwise that candidate is skipped and the next largest is tried. When no candidate shrinks the card, `shrink` stops. A card can therefore never leave `shrink` larger than it entered.
   - New blob views get a 120-character summary. A blobbed dict or list gets a generic one-line summary instead of `{`: top-level scalars as `k=v`, lists as `k: N items`, nested dicts as `k: {…}`, sorted by key and clipped to 120 characters. For `checks` this gives `details: 1 items; passed=true; tree=…`. A blobbed correction's `full` drops its `summary`, because `text` already holds those 200 characters.

The blob views themselves keep their `read` command. Dropping it would save about 57 bytes per blob, but it changes what workers are told to run, so it is not worth it.

**Measured result** (the replay above, the real 54d7e83 cards with the new views put in, real prompts and policy texts):

| card | today | with views, old `shrink` | with views, new `shrink` | views inline |
|---|---|---|---|---|
| implement (1014) | 4,621 | 4,710 (tests blobbed to `{`) | 3,745 | tests |
| review_tests (1014, round 1) | 3,576 | 3,829 | 3,829 (no shrink needed) | tests |
| review_impl (made from the 1014 cards: 3 instructions, 726-byte prompt, doc, checks, review schema, artifact) | n/a (no real card yet; 4,842 with views before `shrink`) | 4,067, both views blobbed to `{` | 3,765 | tests, code |
| design with 1 long correction (1015-design-2) | 5,341 | n/a | 4,092 | n/a |
| review_tests round 2 with `previous` (1014-y) | 4,997 | 5,086 | 4,532 | tests |
| review_design round 2 with `previous` (1015-x) | 8,520 | n/a | 7,560 | n/a |

All 38 real cards in the run folder were replayed. Every card without `previous` ends at or under 4,096. All six that stay over carry `previous` (1.3–4.7 KB of it). Margins are thin (implement about 350 bytes, 1015-design-2 about 4), so the tests use cards of this size, not small fixtures.

**What is guaranteed, and what the tests assert:**

- G1: a checkpoint view is never blobbed.
- G2: `shrink(card)` is never larger than `card`.
- G3: after `shrink`, either the card is at most 4,096 bytes, or no step can shrink it further. `shrink` is idempotent, and a helper `shrink_candidates(card)` returns no candidate that reduces size.
- G4 (measured, not structural): default-graph cards without `previous`, at real sizes, are at most 4,096 bytes.

The module docstring changes from "at most 4,096 bytes" to "aimed at 4,096 bytes; see `shrink`". Bounding `previous` is out of scope (see below).

## Alternatives rejected

- **Change the graph selectors to whole checkpoints.** This would change the fingerprints of every affected node and make in-flight goals stale. Rejected by the spec.
- **Resolve the full checkpoint inside `resolve`.** This touches the fingerprint path and `frontier.py`. It is more risk for a rendering fix.
- **A separate `checkpoint` key next to the bare id.** This gives a second place to look and a second shape for the same output type.
- **Blob checkpoint views last instead of never.** On the measured cards they are never needed, and a blobbed view brings back the blind spot this goal fixes. G1 is simpler to state and to test.
- **Make 4,096 a hard limit now.** `previous` alone reaches 4.7 KB. Meeting the limit would mean bounding prior findings and responses inside `previous`, which G1000 is changing. That is a separate decision about what a re-reviewer must see inline.
- **Drop `command` and keep `argv`, or turn commands into bare strings.** `command` is the form workers copy, and keeping the dict keeps the card shape stable.
- **Drop the `read` command from blob views.** See above.

## Interfaces and data that change

- Card `inputs.<name>` / `context.<name>` for checkpoint `change`/`tree` selectors changes from a string to `{commit, base, change, diff}` (plus `tree` for `.tree`). Whole-checkpoint card inputs gain `base`.
- On a card that was over 4,096 bytes: `commands.*` lose `argv`; blob summaries are at most 120 characters; a blobbed correction's `full` has no `summary`; a blobbed dict or list has a key summary; `context.commands` can read `"see commands_to_run"`. Cards under 4,096 bytes are unchanged apart from the views.
- Approve item `context[]` checkpoint entries gain `commit` and `base`.
- No stored data, fingerprint, schema or CLI argument changes.
- Docs: if `references/CLI_USAGE.md` describes the checkpoint view keys or says cards carry `argv`, it gets one sentence each. After merge, WORKER.md rule 9 (the goal.json workaround) can be dropped.

## Risks

- **Stale or mismatched producer**: handled by the equality guard and the bare-value fallback.
- **Agents that use `argv`**: only on over-budget cards, and `command` is always present. The engine fixtures build their own argv (engine_fixtures.py:311). `test_card_shape_and_size` asserts `submit.argv` and changes to assert `command`, plus `argv` when present.
- **Thin margins**: a longer policy text or a longer holder label can push a card without `previous` over 4,096. The result is a blobbed instruction or prompt, never a blobbed view (G1). G4 catches the drift in CI.
- **Deps sub-field inputs**: none in the default graph. They use the same code path and get one unit test.

## Tests

In `.agents/`, using the existing fixtures (`engine_fixtures`, `self.n()` for renamed names). All run on both the default and the renamed graph.

1. **review_tests card**: after test_design commits `work/x.txt`, `inputs.tests` has `commit`, `base`, `change` and `diff`, and no `tree`. `change` equals the recorded `test_design.tests.change`. Running the `diff` argv in the goal repo outputs `work/x.txt`. `git cat-file -t <commit>` is `commit`.
2. **review_impl card**: `tests` and `code` both carry the view, and `code.diff` shows the implement change.
3. **approve_merge item**: the `code` context entry has `commit` equal to the recorded implement commit, plus `base` and `diff`.
4. **Fingerprints unchanged**: for review_tests, implement, review_impl, approve_merge, run_tests and integrate, the input fingerprint equals `fp_selected(graph, node, name, <recorded sub-field value>)`. It is identical before and after the card is built. A pin captured on the pre-fix engine guards against leaks.
5. **Fallback and deps**: `value_of` with a producer whose `change` differs from the resolved value returns the bare value. A `deps` sub-field selector renders the view.
6. **`shrink` unit tests** (`test_engine_card_shrink.py`, plain dicts plus a fake reader):
   - Real-size fixtures: card dicts with the same field lengths as card-1014-implement, card-1014-review_tests and the review_impl made from them (real prompt and default-policy texts, 28-character holder, 51-character title, 400-character design summary, 4-digit goal, neutral paths of the same length; no local paths). After `shrink`, each is at most 4,096 bytes and every view is inline and unchanged (G1, G4).
   - G2: for each fixture and for a card made only of small instructions (the case that grows today), `len(shrink(c)) <= len(c)`.
   - G3: on a card with a 4 KB `previous`, `shrink` returns a card over 4,096 that is unchanged by a second `shrink`, and `shrink_candidates` returns no reducing candidate. Its views are inline.
   - Steps run in order: a card 100 bytes over loses only `argv`. Its instructions and prompt stay inline.
   - A blobbed `checks` dict has the summary `details: 1 items; passed=true; tree=…`, not `{`.
7. **Journey regression** (`test_engine_journeys.py`): `Autopilot.run_agent` keeps every card. Afterwards, for every top-level value of `inputs` and `context` of every card (not nested values: artifact dicts hold `blob` ids, which are not commits):
   - a dict with `commit` and `diff` must have `git cat-file -t commit == "commit"`, and `base` must also be a commit;
   - a bare 40-hex string must resolve to a commit (this catches a regression back to a patch id or tree id);
   - at least one checkpoint view was seen, so the test is not vacuous;
   - the card satisfies G3: at most 4,096 bytes, or `shrink_candidates` is empty. The bare 4,096 bound is not asserted here, because journey fixtures are smaller than real cards and would hide drift. G4 is covered by test 6.
   It runs in `JourneyTests` and `RenamedJourneyTests`.
8. `test_card_shape_and_size` drops its `4096 + 2000` allowance in favour of G3, asserts `submit.command`, and requires `inputs.tests` to be a dict with `diff` (it accepts a bare id today).

## Out of scope

- Bounding `previous` (prior findings, responses, interdiff). It is the one section that keeps review cards from round 2 on over 4,096. Proposed child goal after approval: "Bound the `previous` section of re-review cards", sequenced after G1000, which is changing `previous`.
- Expanding `commit`/`base` sub-field selectors, artifact sub-field selectors, or `deps` checkpoints in approve items.
- Any change to fingerprints, `resolve`, the graph, the prompts, `reader.blob_view` in session.py, or the `renew`/`commands` construction in `build` (G1016's area).
