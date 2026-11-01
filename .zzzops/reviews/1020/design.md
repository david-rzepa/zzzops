# G1020 design: polish the shipped lens prompts

**Builds on:** G1000 design revision 4 and its code at `zzzops/work/g1000` (fd32b9e, not yet merged). G1020 stacks on G1000; nothing here changes G1000's mechanism.

## Outcome

1. Code-stage lens reviewers are told to aim test problems at `test_design`. This is one sentence in the shared `review` instruction.
2. `lens_truth.md` has one "On code:" sentence, not two.
3. A lens whose only findings are notes answers `approved`. Its submit outcome reads "approved with N notes" instead of "failed: N findings".

This repository's own `.zzzops/` policy and prompts are not touched (spec item 4). They move through G1000 rollout step 3.

## 1. Targeting `test_design`: put it in the `review` instruction

**Change.** Add one sentence to `instructions.review` in `plugins/zzzops/zzzops/templates/default/POLICY.json`. Put it after "Raise a finding only when …":

> On code, target `test_design` for a problem in the tests; `implement` cannot change them.

**Why the instruction, not the seven lens prompts (decided by prompt budget):**
- The per-card cost is the same either way, about 75 bytes on each lens card. Every lens card, design and code, carries `instructions: ["review", "communication"]` and exactly one lens prompt.
- The static cost is not the same. The seven `lens_*.md` files are in `prompt_stats`' `static-hot-prompts` profile, so the prompt route adds about 7 × 75 ≈ 525 bytes there. The template `POLICY.json` is only in `cold-default-review`, so the instruction route adds about 75 bytes once. Neither profile has an enforced budget (`ENFORCED_PROMPT_BUDGETS` covers only the skill paths), so `prompt_stats --check` holds either way. The instruction is still the smaller footprint.
- It is one source of truth. The `review` instruction already holds the finding mechanics (`impact`, `material`, the filter). Where a finding is aimed belongs with those mechanics, not with what a lens asks.
- Design-stage lens cards carry the sentence too. That is harmless: "On code" scopes it, and `test_design` is not an ancestor of a design lens, so the engine would refuse such a target anyway.

**Rejected:**
- Appending the sentence to each prompt's existing "On code:" line. That costs seven copies, and they can drift apart.
- An engine-side hint, such as rewriting a test-path finding's target. That is new mechanism for a one-sentence problem.

**Card size.** The `review` text grows from about 1,050 to about 1,125 bytes. If a lens card goes over `CARD_LIMIT` (4,096), `shrink` already moves the largest inline text, often this instruction, to a blob view. The sentence then stays reachable through `read`. Nothing new is needed.

## 2. `lens_truth.md`: merge the two "On code:" sentences

Replace the two sentences ("… On code: do the tests check what the design promises?" and the closing "On code: judge the diff against the approved design.") with one closing sentence:

> On code: judge the diff against the approved design, and ask whether the tests check what it promises.

The other six lens prompts keep their single "On code:" line unchanged.

## 3. Notes-only lens: decision

**Recommendation: such a lens answers `approved` with its notes.** Do not add a "notes only" label to approval items.

**Reasons:**
- For a filtered lens, `decision` is already only a label. In `records.review_findings`, `ok` is forced to `True` when `graph.filter_of(X)`: the findings become filter candidates and the subject reopens through the filter. `decision` is read nowhere in `frontier`, `fingerprint` or `card.candidates`. Letting it mean "nothing I would block on" makes the label true and changes no behaviour.
- The data already says it. "Approved" plus non-material findings is exactly a notes-only lens. A separate "notes only" label would derive the same fact again in `render.approve_item`, `integrate.reviews_section` and `outcome_of`. The lens would still be told to say `changes_requested`, and its own summary, which approval items show verbatim as `context`, would still read that way. A render label cannot fix free text the lens writes.
- Promotion stays honest. If the filter keeps a note, the work reopens whatever the lens said, as it does today. The filter summary and the approval item's `notes` already report that. The lens said "I would not block"; the filter disagreed. That is the record we want.

**Rejected:**
- Labelling approval items "notes only". It adds rendering code in three places, keeps a misleading decision, and leaves the lens's summary saying "changes requested".
- Making `decision` strictly derived, so `changes_requested` with only notes is refused. That breaks in-flight goals and existing tests (`test_engine_lenses.py` line 345 submits `changes_requested` for any open finding) for no gain.

**Changes (engine, about 10 lines):**
- `engine/records.py` `review_findings`. For a filtered lens (`graph.filter_of(X)`), `approved` requires no open **material** finding (`f.get("material")` is true). A lens with any material finding open must still say `changes_requested`. `changes_requested` still requires some open finding. Non-filtered reviews (`review_tests`, the human approvals) keep "approved requires no open findings" unchanged.
  - Refusal text: "approved requires no open material finding". A lens may approve with notes (`material: false`).
- `engine/card.py` `output_schema`. A filtered lens's `decision` hint becomes "approved | changes_requested (changes_requested only with a material finding open; approve with notes)". Other review nodes keep the current text.
- `engine/verbs.py` `outcome_of`. When `decision == "approved"` and findings are open, the head reads `approved with N note(s) → <targets>`, not `failed: …`. Today that label is unreachable for reviews; with this change it would be wrong.
- Docs: the CLI_USAGE submit-output line for lenses, if it repeats the old rule (check with `git grep "approved only"`). No prompt change is needed: `filter.md` and the lens prompts do not state the rule.

**Hand-off (root action, not this goal):** SPEC §4.14's "approved requires no open findings" gains the filtered-lens exception. Add it to G1017's input next to G1000's validation rules.

## Interfaces and data

- No schema, record shape or fingerprint change. The `decision` enum is unchanged.
- A 1.1 engine accepts `approved` plus notes; G1000's engine refuses it. Engine-version handling is G1000's existing `engine.min` rollout (G1000 D8). Bump `ENGINE_VERSION` to 1.1.1 only if G1000 lands first as 1.1.0.

## Risks

- **A lens marks a real problem `material: false` and approves.** The filter still sees it as a candidate and can keep it. Approving changes nothing in the candidate set. This is the same guard as today.
- **A test that pins the template `review` text.** None was found (`git grep` over `.agents/*.py`). The graph12 fixtures are frozen copies and unaffected.
- **A card goes over its size limit.** This is handled by `shrink` (see §1).

## Tests

1. **Card snapshot.** In `test_engine_lenses.py`, take the `truth_impl` card. Its `instructions.review` (inline `text`, or the blob it references) contains "target `test_design`". Do the same for `intent_impl`, to cover a non-skippable lens.
2. **Notes-only approval is accepted.** A filtered lens submits `approved` with one `material: false` finding. The submit is accepted, the finding is an open candidate on the filter card, and the outcome text starts "approved with 1 note".
3. **Material approval is refused.** `approved` with a `material: true` finding is refused with the new message.
4. **Approval-item rendering for a notes-only lens.** This is the spec's acceptance. Lens approves with one note, the filter answers `note`, and the item reaches `approve_design`. The item's `notes` holds the finding under that lens, and the lens's `context` summary is the lens's own approved text. Then the filter answers `keep` and the subject reopens (promotion still works).
5. **Unfiltered reviews are unchanged.** `review_tests` answering `approved` with an open finding is still refused.
6. **`prompt_stats --check` passes.** Also check that `lens_truth.md` contains "On code:" exactly once.

## Out of scope

- This repository's `.zzzops/POLICY.json` and `.zzzops/prompts` (G1000 rollout step 3).
- SPEC text (G1017).
- Any change to the filter's verdict rules, or to how notes are rendered beyond the outcome label.
