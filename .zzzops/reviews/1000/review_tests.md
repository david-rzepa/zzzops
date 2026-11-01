# G1000 review_tests, round 2: re-review of the rev-4 tests (d5e46d1)

**Verdict: approved.** The added tests cover design revision 4's new skip rule, both non-blocking notes from round 1, and the approve_design directive. They are consistent with the design and the engine's existing surfaces. Each one fails today for the expected reason, the missing feature. Finding review_tests:1:1 is resolved.

Reviewed: `git diff a5b5579 d5e46d1` (test_engine_lenses.py +110, design.md rev 4), against design-1000-4.md and answer-1000-approve_design-2.json.

## Prior finding
- **review_tests:1:1 (skip during the filter's join window): resolved.** D6, §5 and §17 §4.18 now refuse a new skip while the node's latest record has any open finding that is not a filter-judged note. §13 journey 6 names the test case, and the tests below implement it.

## New tests, checked against the design
- **`test_6_a_skip_is_refused_while_findings_wait_for_the_filter_…`** sets up the window: a material finding is recorded, another lens is still running, the filter is blocked with no record, and the design is still `current`. The test asserts all four facts first, so it really is testing the pre-filter case. The edit is then refused, and the refusal must name the finding id and "waived". It must also not be the "not skippable" refusal, so it cannot pass for the wrong reason. After a waiver through the existing `records.<n>.findings[<id>]` path, the skip is accepted. On approve_design, the waived id comes from the existing `facts()` "waived:" list, which covers every record, skipped ones included. The skip reason comes from the journey-4 behaviour. This matches §5 and §13.6.
- **`test_6_a_lens_whose_only_open_findings_are_judged_notes_can_be_skipped`**: an unjudged note blocks the skip, and once the filter's fresh record judges it `note`, the skip is accepted. This is exactly §5's definition of a note, tested from both sides.
- **`test_reviewer_independence_holds_per_lens`**: the designer's `start` is refused with `independence` on all seven design lenses, and the implementer's on all seven code lenses. The tests call `Agent.start` directly, so `Pilot.start`'s silent fallback no longer hides the refusal. At the stopping points every lens in each set is ready together, because the lenses share inputs (§3: the code lenses all take `doc`/`tests`/`code` with context `checks`). So the only possible refusal is the independence one.
- **`test_changing_intent_at_the_impl_stage_stales_only_the_intent_lenses`**: once all code lenses are current, an intent change makes `intent_impl` `ready (stale: policy.intent)`. No node other than `intent_*` is stale, the other code lenses stay current, and `implement` stays current. This matches §6 and §13.
- **`test_open_findings_on_skipped_nodes_are_listed_on_approvals_and_the_pr_body`** (the directive): the test skips a lens while it runs with no record, which the skip rule allows. The lens then submits a material finding. The test checks that the finding stays open on a skipped node and does not reopen the subject, and that the text and the node name both appear on approve_design. It repeats this at the code stage for approve_merge and the PR body. This is exactly the directive's case, and the renamed-graph subclass runs it too. The engine's records validation only rejects a finding whose *target* is skipped (records.py:94), so the late submit itself is accepted. The test therefore depends on no undocumented refusal.

## Failing for the right reason
I ran the full suite in a temporary detached worktree at d5e46d1, since removed. Result: 438 tests, 49 failures and 5 errors, all in `test_engine_lenses.py`. There are 8 new failures: the five tests above, plus the renamed variants of the journey-6 and directive tests. Each stops at `new` with `settings: unknown key 'intent'`, the same missing-feature failure as round 1. No test outside the lens file fails.

The same caveat as round 1 applies, and it is not a finding: the later assertions first run during implementation, so I checked them by hand against the design and against the engine surfaces they rely on (`facts()` waived list, `frontier` skip handling, `records` target validation).

No new findings.
