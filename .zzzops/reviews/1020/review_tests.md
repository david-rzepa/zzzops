# G1020 review_tests, attempt 1 (tests 5ae4e84, design revision 2)

**Verdict: approved.** The 12 tests in `.agents/test_engine_lens_polish.py` cover all six tests in the design. They pin the materiality default and the unchanged unfiltered rule. Run against the base without the implementation, they fail for the right reasons. I found no material problems.

## Coverage against the design's tests

| Design test | Test(s) | Covered |
|---|---|---|
| 1 Card snapshot (truth_impl, intent_impl, inline or blob) | `CodeLensCardTests.test_code_lens_cards_carry_the_test_design_sentence` (it also checks the "approve with notes" decision hint) | yes |
| 2 Notes-only approval is accepted, candidate on filter card, outcome "approved with 1 note" | `test_2_a_filtered_lens_approves_with_only_notes`, `test_2_two_notes_read_plural` | yes |
| 3 Material approval refused; prior finding with no `material` key blocks | `test_3_approved_with_a_material_finding_is_refused`, `test_3_an_open_prior_finding_without_material_blocks_approved` | yes |
| 4 Approval item notes and context; keep reopens | `test_4_approval_item_for_a_notes_only_lens`, `test_4_a_kept_note_from_an_approving_lens_reopens_the_subject` | yes |
| 5 Unfiltered review_tests unchanged | `test_5_review_tests_approved_with_an_open_finding_is_still_refused` (a finding with no key and a `material: false` note are both refused, with the old message) | yes |
| 6 prompt_stats --check; lens_truth "On code:" once | `test_prompt_stats_check_passes`, `test_lens_truth_has_one_on_code_sentence` (plus a guard that the other six prompts are unchanged) | yes |

The test for §1 also pins where the sentence goes: after the filter sentence and before "On a re-review".

## Materiality default

`test_3_an_open_prior_finding_without_material_blocks_approved` removes `material` from a recorded prior finding by pushing goal.json directly, and asserts that the key is really gone. The lens then re-reviews, keeps the finding open, and answers `approved`. If an implementation treated a missing key as a note (for example `f.get("material") is True`), that submit would be accepted and the test would fail at `assertNotEqual(0, rc)`. So the default is pinned. Resolving the finding then lets the lens approve, which shows that the refusal comes from the open finding and nothing else.

## Fail-for-the-right-reason run

I checked out 5ae4e84 in a temporary detached worktree under the scratchpad, ran `python -m unittest test_engine_lens_polish`, and removed the worktree afterwards. 12 ran, 9 failed and 3 passed:
- Failed as expected: the sentence is missing from the template and from the cards. `lens_truth.md` has "On code:" twice. Approved plus notes is refused with "approved requires no open findings". The material refusal does not yet carry the new message.
- Passed as expected, because they guard regressions and do not specify new behaviour: the other six lens prompts are unchanged, `prompt_stats --check` passes, and the unfiltered review_tests rule holds.

No test failed on a fixture or setup error.

## Notes (non-blocking)

- In test 5, the final submit repeats an earlier one just to read the message. The loop could capture it instead. This is cosmetic.
- No test drives `candidates`, `fingerprint` or `frontier` through the new shared `is_material` helper directly. The design moves them to the helper as a pure refactor, and the existing lens tests cover their behaviour.
