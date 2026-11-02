# G1026 review_design (attempt 4): design revision 5

**Verdict: changes requested (one new finding).** Both round-3 findings are fixed. One gap that revision 4 already had now matters more, because review cards carry unclipped `human_decisions`. The design says `shrink` blobs the list, but the shipped `shrink` never touches a top-level card key like this one, and no SPEC or engine change in the design adds that step.

## What I checked (read_dev 25186a5)

- **r4 to r5 diff:** the changes are the revision-5 note, the summary line, §1 step 4, the §2 reviewer sentence, the size note in §2 (1,200 bytes), D5 and its alternatives, the §5 row and line count, §6 (task card, POLICY), §9 (misquoting), §10 tests 2 and 3, and §11. Nothing else changed.
- **3:1 against the frozen file** `.agents/test_engine_owner_questions.py` at a263ee7:
  - (i) The `"fixed: owner chose"` needle is in `test_design_prompt_step_4_blocks_with_every_owner_question` (line 101). The new step 4 contains both `"give no response"` and `"the review resolves"`.
  - (ii) In the journey, the retry-card `assertIn(fid, corrections)` (line 390) and the `fixed: owner chose A` response (line 398) are the only places that change. `rcard` is already bound (line 400), so adding the `human_decisions` assertion there is direct.
  - (iii) In the stale-unanswered test, the corrections assertion (line 514) and the `--blocked` submit from the stale card (line 515) are what change. `assertNotIn("human_decisions", card)` (line 513) still holds, because nothing has been answered yet.
  - (iv) The docstring wording matches lines 16 to 18.
  - `resubmit_design` responds only to live ids (line 337), so its other callers (durability, long-answer and failing-log tests) need no change.
  - No other assertion uses the needle or the stale card's corrections.
  - The list is complete.
- **3:2:**
  - `graph.subject(n)` (schemas.py:141) reads `review.subject`. The shipped workflow.json sets it on exactly the six nodes named: three on `design`, one on `test_design` and two on `implement`.
  - D5, §1 step 4, the §2 reviewer sentence, §5, §6, §9, §10 test 2 and §11 all agree with each other.
  - The new rule fails closed. With no entry (the unanswered stale case, §8) or `"unavailable"`, the reviewer keeps the finding open. That matches test 3's new ending.
  - The frozen `test_cards_carry_the_instruction_and_stay_within_the_limit` checks review cards against `CARD_LIMIT` only on a fresh goal. There are no answers there, so there is no key and that test is unaffected.

## Findings

1. **`human_decisions` on cards has no `shrink` step, so the card budget claim is false, and review cards now make it matter.**
   - D5 and §5 say that on the card, entries are not clipped and "`shrink` turns it into a blob view if needed". The frozen tests' `decisions_of` also accepts "a blob view of it after shrink".
   - The shipped `card._steps` (card.py, around line 420) can blob only these: `prompt`, `instructions.*`, `inputs`/`context`/`policy` entries, correction texts, and `candidates`/`notes`. SPEC §3.14's shrink rule lists the same set (SPEC.md line 1581). A new top-level `human_decisions` list is never a candidate, so `shrink` leaves it inline whatever its size.
   - §9 "Card size" says the list "is clipped and goes through `shrink`". That contradicts D5, which says it is not clipped on cards.
   - Revision 5 adds the list to all six review and filter cards. Those cards already carry an unshrinkable `previous.findings`: this review's own card is 7,367 canonical bytes, 4,313 of them `previous.findings`. Each entry adds the blocked `question`, which numbers every owner question, plus `text`, `quote` and the other fields. Each owner-question round adds an entry, and on `review_impl` the list covers design and implementation together. These cards will go further over the 4,096-byte target (G1018/G1022, SPEC §3.14), with no way to shrink.
   - **Fix:** in §5, add a `card.py` shrink step that blobs a top-level `human_decisions` list. Size it with the other blob candidates, or before them, with a key summary such as `N items`. In §6, add `human_decisions` to SPEC §3.14's shrink order. Correct the §9 "Card size" bullet to "not clipped on cards; `shrink` blobs it". Add a test with a long answer and question: on a `review_design` card, `human_decisions` becomes a view that `decisions_of` reads back.

## Prior findings

- `review_design:3:1`: resolved. All three frozen-test changes are listed, along with the docstring change. I checked them line by line against a263ee7.
- `review_design:3:2`: resolved. Review and filter cards carry `human_decisions` over the subject and its ancestors. The reviewer text resolves an owner question only when an engine-recorded answer covers it and the design quotes it.
