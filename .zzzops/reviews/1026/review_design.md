# G1026 review_design, round 5 (revision 6)

**Verdict: approved.** Revision 6 fixes review_design:4:1 and changes nothing else.

## What changed (r5 to r6)

`git diff 0b1b68b 817343d` (the committed revision 6 blob is the same as `g1026-design-r6.md`) touches only the areas the revision note lists: the revision-6 note, one clause of D5, §5 (a new `card.py` shrink row and the line count, 36 to 39), §6 (task card and the SPEC §3.14 shrink list), §9 (card size), §10 (the test-list pointer and new test 2b). Revision 5 text (3:1 items i to iv, D1 to D4, D6, D7, §4, §7, §8, the other tests) is unchanged.

## Check against shipped code (read_dev 25186a5)

- `card._steps` (plugins/zzzops/zzzops/engine/card.py:418) builds blob candidates only from prompt, instructions, inputs/context/policy, corrections and candidates/notes, sorted largest first. The new candidate `(len(canonical(list)), ("human_decisions",))` gives step `("blob", "human_decisions")`, which is what test 2b's unit check expects.
- `_apply`'s fallback `else` branch indexes `step[2]`, so a two-element step needs its own branch. The design adds `elif step[1] == "human_decisions"`. `_blob` on a list stores `json.dumps(indent=2, sort_keys=True)` and gives `key_summary` "N items", so test 2b's "1 items" summary and the frozen `decisions_of` (a263ee7, `json.loads(read_text_view(...))`) both hold. No helper change is needed, as the design says.
- Once blobbed, the value is a dict, so it is no longer a candidate. The `"unavailable"` string is excluded. `shrink_candidates` drops steps that would not shrink the card, so a short list is never blobbed against the rule. `_is_view` does not match entries (they carry `commit` but no `diff`), so entries are not treated as checkpoint views.
- `build` calls `shrink` last (card.py:195), so a `human_decisions` list added in `build` reaches the new step.
- SPEC §3.14's shrink list ("prompt, instructions, inputs, context, correction texts") gains `human_decisions`, as §6 says. §9 no longer says "clipped", which removes the contradiction with D5. The note that `previous.findings` stays unshrinkable is accurate.
- Frozen-test change (v) names `test_long_answer_text_is_clipped_on_the_item` (a263ee7, line 427). It keeps that test's approve-item assertions, so it does not conflict with changes i to iv.

## Prior findings

- review_design:4:1: **resolved.** Each part of the fix is in place: the shrink step (§5), the SPEC shrink order (§6), the §9 correction, and a long-answer review-card test with a `_steps` unit check (§10 2b), recorded as frozen-test change (v).

No new findings.
