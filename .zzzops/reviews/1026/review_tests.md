# review_tests for G1026 (attempt 3)

Subject: tests at 3974afd (base 25186a5; round-2 subject 8b97382, review commit 348a901). Design: revision 7 (blob 3ddfcf8).
The only test change since round 2 is 7 lines in `OpDecisionTests.test_an_answered_integrate_question_is_listed_with_kind_op`.

## Commands run (workspace root)

- `python3 -m unittest discover -s .agents -p 'test_engine_owner_questions.py'`: 41 tests, 23 failures, 6 errors (round 2:
  22/7). The changed test moved from an error (KeyError `human_decisions` on approve_merge) to a failure at the new
  assertion: the body is `design summary / ## Reviews / filter_impl summary / - **review_impl** (...) / ZzzOps goal ...`
  with no `## Human decisions`, i.e. it stops at the missing feature.
- `python3 -m unittest discover -s .agents -p 'test_design_docs.py'`: OK.
- `python3 .agents/prompt_stats.py --check`: PASS.

## Prior findings

- **review_tests:2:1: resolved.** After the post-answer integrate run succeeds, the test reads the fake-gh PR body and
  asserts `## Human decisions` with exactly one `- **` line after it, matching
  `^- \*\*<integrate>\*\* \(op; Claude \(root agent\), delegated by Dave, \d{4}-\d\d-\d\d[^)]*\): .+ → "Wait for it\."$`.
  A revision-6 implementation (integrate's ancestors only) leaves the integrate answer out and fails here.

## Format check against design revision 7

D5 gives the line as `- **<node>** (<kind>; <decided_by>, <date>): <question, one line> → "<quote, one line>"`, with the
section after `## Reviews`. The regex matches that form exactly (same arrow character, quote in double quotes, date
prefix with any time suffix allowed, so implement may render a date or a timestamp). Counting `- **` lines from the
heading onward is safe: in `ops/integrate.py` `pr_body` only the footer ("ZzzOps goal G...") and optional "Stacked on"
text follow the reviews section, neither starts with `- **`; and it implicitly checks the section comes after
`## Reviews` (whose lines start with `- **`), as D5 requires. The test answers only integrate, so one line is right.
Implement can satisfy it by appending the section in `pr_body` over the non-descendants of the writing op.

## Verdict

approved: 2:1 resolved; no new findings.
