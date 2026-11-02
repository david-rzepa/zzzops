# review_tests for G1026 (attempt 1)

Subject: tests at aec3870 (base 25186a5): new `.agents/test_engine_owner_questions.py` (41 tests) and one adjusted
assertion in `.agents/test_engine_review_lenses.py`. Design: revision 6 (blob 817343d).

## Commands run (workspace root)

- `python3 -m unittest discover -s .agents -p 'test_engine_owner_questions.py'`: 41 tests, 22 failures, 7 errors.
  Every failure or error stops at the missing feature (no `owner_questions` instruction, no
  `schemas.is_owner_question`, no `render.human_decisions`, no card or approve-item key, no shrink step, no prompt
  or doc text). 12 pass on read_dev, as they should: they are regression guards (record schema, golden
  node_def_fp, no capability file, implement.md untouched, templates validate, no answers means no key or PR
  section, the answer subject, a material finding is not demoted, the stale-unanswered path, "unavailable" is
  never a shrink candidate).
- `python3 -m unittest discover -s .agents -p 'test_design_docs.py'`: 35 OK.
- `python3 .agents/prompt_stats.py --check`: PASS.

## Coverage against the design

Covered well: the journey (raise, reopen, block, `next` item, answer, retry card with `answer`, `human_decisions`
and `corrections == []`, no response, re-review sees the finding open with `human_decisions`, resolves, approve
item); the blocked-and-unanswered stale case (done from the stale card, kept open, reopened, blocks again); the
answered-then-stale case; the second round and the PR body line format; the history helper (commit order, kinds,
approval and dispute answers dropped, G10 vs G100, None on a failing log); "unavailable"; the filter refusal
(case-sensitive prefix, adversary too, no demotion, graph12); review, filter and review_impl cards carrying the
subject's and ancestors' decisions while implement carries only its own; the shrink step (candidate, ordering both
ways, `_apply` view with `1 items`, `shrink_candidates`, never "unavailable" or a view) and the 4,000-character
answer blobbed whole on the review card while the approve item still clips; prompts, skill, EXECUTION.md, SPEC
and HISTORY. The revision 5 (3:1 i-iv) and revision 6 (v) changes are all applied. Long needles (the resolve-rule
sentence, the targeting sentence, the lens_intent phrase, "never use that form for an owner question") are all
quoted from text the design fixes as shipped wording, so they are acceptable.

Filter cards (the known point): the shipped `filter_design`/`filter_impl` have no `review.subject`, so
`graph.subject()` is None for them (schemas.py:141); `graph.filter_subject()` (schemas.py:167) gives the reviewers'
subject. The design names `filter_design` and `filter_impl` among the cards that carry the list (rev 5 3:2, D5
"a review or filter node", §6 "on a review or filter card"), and the test asserts it for `filter_design`. Design
intent and test agree; only the mechanism note "`graph.subject(n)`" is imprecise. Implement should use
`graph.subject(n) or graph.filter_subject(n)`. No finding.

## Findings

1. (test_design) `test_cards_carry_the_instruction_and_stay_within_the_limit` cannot pass after implementation.
   It starts `review_design` and `adversary_design`, then `abandon`s both, then calls `until_ready(g, "review_impl")`.
   On read_dev `abandon` makes the node reclaimable (verbs.py: "The node is now reclaimable: a plain start is
   refused"), and the Pilot's plain `start` is refused with `not_ready` "the lease expired; pass --reclaim". I ran
   the same sequence on read_dev with the instruction assertions removed: it fails there. Today the test stops
   earlier (line 363), so the defect is hidden. Fix: complete the review runs (`card, _ = self.p.run(g, node)`) and
   check those cards, or restart with `--reclaim`.

2. (test_design) The same test asserts `card_size(card) <= CARD_LIMIT` for `review_impl`, which the design's own
   shipped text makes impossible. Measured on read_dev in the same world: `review_impl` is 3,948 bytes. With the
   design §2 instruction text added to the template POLICY, the §4 `review` sentence, and `owner_questions`
   listed on the four nodes (a scratch copy), the shrunk `review_impl` card is 4,219 bytes (design 3,134,
   review_design 3,985, adversary_design 3,699). The new instruction view adds about 270 bytes and no existing
   shrink step can take it back. Design §9 already says a review card can end above the target. Implement cannot
   satisfy this without changing the fixed instruction text or adding shrink steps the design does not have.
   Fix: keep the limit for `design`, `review_design` and `adversary_design`, and for `review_impl` assert only that
   the card grows by at most one view reference over the same card without the instruction (or drop the limit
   there); say in the response that design §10 test 1's "all cards stay within CARD_LIMIT" is relaxed for
   `review_impl`, as §9 allows.

3. (design) The node set for approve items conflicts with the op-decision test. Design §5 and D5 say approve
   items carry `human_decisions` "over the item's ancestor nodes", and §5 says "the PR body and items read
   ancestors from the graph". In the shipped graph `integrate` is not an ancestor of `approve_merge` (ancestors:
   adversary_design, approve_design, base, design, filter_design, filter_impl, implement, review_design, review_impl,
   review_tests, run_tests, test_design), nor of itself for the PR body, and `merge` is an op. So under the design
   rule an answered integrate question is listed nowhere, contrary to §1 step 5 ("approve_merge and the PR body
   list every answered question") and D5/revision 3 ("op questions such as integrate's 'Rebase it?' appear in
   it"). `OpDecisionTests.test_an_answered_integrate_question_is_listed_with_kind_op` asserts it on
   `approve_merge`, so an implementation that follows §5 fails a frozen test, and one that passes it departs from
   §5. The design must state the node set (for example: for `approve_merge`, every node of the goal's graph except
   its descendants, or ancestors plus the op nodes that run beside it; and whether the PR body includes
   `integrate`'s own answers), and test_design then aligns the test.
