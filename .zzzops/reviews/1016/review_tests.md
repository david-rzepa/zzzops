# Review of the G1016 tests (attempt 6, after the rebase onto dev 6747a5e)

**Decision: approved.** No findings.

## What I checked
- `git range-diff 54d7e83..521d78b 6747a5e..e46d1d1`: commits 1-6, 8-14, 16-18 and 20 are `=`. Commits 15 and 19 (implementation) differ only in imports and context that sit on top of G1014/G1018 code. Those belong to the implementation review, not this one. The only test commit that changed is 7 (802c016 -> a3ec211).
- In a3ec211 the only change is in `.agents/test_engine_lifecycle.py::SubmitTests.test_card_shape_and_size`. The resolved body is identical to dev 6747a5e (G1018, f7c58da), except that `renew` is removed from the expected top-level keys.

## Both intents are kept
- **G1018:** the `n <= 4096 or not shrink_candidates(c)` size rule, the `commands.submit.command` string match with the optional `argv` check, and the strict requirement that `inputs.tests` is a dict containing `diff` are all kept word for word. This is stricter than the pre-rebase G1016 version, which had a 4096+2000 bound and a lenient `diff` fallback.
- **G1016:** design §5 removes the top-level `renew` and says "The `test_card_shape_and_size` key list drops `renew`". The resolution does exactly that, and `.agents/test_engine_card_ux.py` asserts the removal positively (`assertNotIn("renew", c)`, `commands.renew.when` contains the interval, and `commands.renew.argv`).

## Evidence
I ran `python -m unittest test_engine_lifecycle.SubmitTests.test_card_shape_and_size test_engine_card_ux` on a `git archive` of e46d1d1: 31 tests passed.
