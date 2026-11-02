# review_tests for G1026 (attempt 2)

Subject: tests at 8b97382 (base 25186a5; round-1 subject aec3870). Design: revision 7 (blob 3ddfcf8). The only test
change since round 1 is in `test_cards_carry_the_instruction_and_stay_within_the_limit` plus the module docstring.

## Commands run (workspace root)

- `python3 -m unittest discover -s .agents -p 'test_engine_owner_questions.py'`: 41 tests, 22 failures, 7 errors,
  the same as round 1. Every failure or error stops at the missing feature (for the changed test: `owner_questions`
  not in the design card's `instructions`).
- `python3 -m unittest discover -s .agents -p 'test_design_docs.py'`: 35 OK.
- `python3 .agents/prompt_stats.py --check`: PASS.

## Prior findings

- **review_tests:1:1: resolved.** The review_design and adversary_design runs are now submitted (`self.submit(rag, ...)`
  with the Pilot's default output) instead of abandoned. Probe: a scratch export of 8b97382 (engine == read_dev) with
  only the feature assertions removed runs the test to the end and passes, so it reaches `review_impl` (card 3,948
  bytes).
- **review_tests:1:2: resolved.** The limit stays on design, review_design and adversary_design. For review_impl the
  test asserts `instructions.owner_questions` is a blob view and the card without it is `<= CARD_LIMIT`, which bounds
  growth to one view reference, as design §9 allows. Probe: in the same scratch copy I added the design §2 text to the
  template POLICY, the §4 `review` sentence, and `owner_questions` on the four nodes (§4). The test passes (the prompt
  text checks were skipped, since prompts were not edited): review_impl is 4,219 bytes with the view and 3,948 without.
  The design, review_design and adversary_design cards stay within the limit.
- **review_tests:1:3 (design): resolved.** Revision 7 states the node set: approve items read every node that is not
  a descendant of the item's node, and the PR body reads every node that is not a descendant of the writing op. For
  the shipped graph that is approve_design = its ancestors, and approve_merge and the PR body = every node except
  `merge`. This agrees with §1 step 5 and with the frozen `test_an_answered_integrate_question_is_listed_with_kind_op`.
  The other approve-item and PR-body assertions use answers on `design`, so they hold. The docstring is updated to
  match. The filter subject note (`graph.subject(n) or graph.filter_subject(n)`) is now in D5, §5 and §6.

## New finding

4. (test_design) No test checks revision 7's PR-body rule, the very case finding 3 was about. Both PR-body checks
   (lines 451 and 605) use only `design` answers, and `design` is an ancestor of `integrate`. An implementation that
   builds the PR body from `integrate`'s ancestors (revision 6's rule) passes every test, and it leaves an answered
   `integrate` question (kind `op`) out of the PR body. That breaks D5 and §1 step 5 ("approve_merge and the PR body
   list every answered question"), and the gap is invisible because `approve_merge` still shows the answer. Fix: in
   `OpDecisionTests.test_an_answered_integrate_question_is_listed_with_kind_op`, after the post-answer integrate run
   (which rewrites the body: `ops/integrate.py` edits it when it differs), assert the PR body has `## Human decisions`
   with one `- **<integrate>** (op; Claude (root agent), delegated by Dave, <date>): ...` line.

## Verdict

changes_requested: findings 1:1, 1:2 and 1:3 are resolved; one new test_design finding (4).
