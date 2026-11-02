# review_tests G1026 (attempt 4)

Decision: approved.

- Change since round 3: 60efe14. It changes only `ReviewerCardTests.test_review_impl_card_searches_the_goals_own_commit`, which now checks the size against `CARD_LIMIT` with `instructions.owner_questions` removed.
- Design: revision 7, section 9 (Card size). The instruction is a blob view, and a review card may end above the target. This matches the frozen owner-questions test, `OwnerJourneyTests.test_cards_carry_the_instruction_and_stay_within_the_limit`, which removes the same view.
- Strength: only that one key is removed, so the size check still covers every other part of the card.
- Evidence: in the g1026 worktree, `python3 -m unittest discover -s .agents -p 'test_engine_review_lenses.py'` gives 59 tests OK, and `-p 'test_engine_owner_questions.py'` gives 41 tests OK.
