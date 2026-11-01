# G1016 review_tests (attempt 1)

Reviewed tests commit 802c016 (base 54d7e83): new `.agents/test_engine_card_ux.py`, and `test_engine_lifecycle.py` drops `renew` from the card key list. Design: attempt 3.

## Evidence

I ran `python3 -m unittest test_engine_card_ux` in a temporary detached worktree at 802c016. There is no implementation at that commit. The worktree has since been removed. Result: 29 tests ran, 10 failed and 16 errored, all on the missing feature: `KeyError: 'restart'`, `'stale_because'`, `'changed'`, `'respond_to'` and `'no_longer_live'`, the old output_schema text, the old CLI_USAGE rows, the missing schema 40-hex check, and `edit` accepting `{"commit":"HEAD"}`. The implement override case fails today with `test_freeze` instead of `validation`. That is the F2 bug in action ("HEAD" resolves in the main repository), so it fails for the right reason.

Three tests pass before implementation:
- `test_reclaim_with_no_edit_has_no_staleness`, twice (once also via RenamedCardTests). These are controls, so passing is correct.
- `test_reclaimed_reopened_correction_keeps_its_capability`. This one is vacuous; see F2 below.

## Coverage against the design

Everything the design promises is covered with meaningful assertions:
- abandon restart, both plain and `--force`
- reclaim after a spec edit, including running the `changed` diff, plus the no-edit control
- union staleness on attempt 3
- crash-loop reclaim (`--force --reclaim`)
- the artifact blob-diff pointer, and the missing-blob note with no work-branch fetch in the trace
- submit refusal: `respond_to` with from, target, text and upheld; `no_longer_live`; clipping with `full`
- card text for review, non-review and checkpoint cards, and the single renew entry
- schema full-sha check: HEAD, a branch, a short sha, uppercase, 39 and 41 characters, and omitting the key
- submit end to end: refused overrides record nothing; outside-branch and nonexistent shas are still refused; a full sha succeeds
- `edit` record completion
- CLI_USAGE lines

**F1 adaptation (implement to test_design): acceptable.** The design's intent is that staleness on the lease side only (base re-ran while a first attempt with no record was running) must not downgrade capability to `routine`. `test_design` has `inputs.base`, and its own capability (`reasoning`) differs from `routine`. A base restack would also make `test_design`'s record stale and stall `implement`, so this is the cleaner fixture. The test checks `stale_because == ["inputs.base"]` and `capability == "reasoning"`, so it covers that intent. The control (`record_stale == ["inputs.base"]` gives `routine` on start and after reclaim) is also on test_design. That is consistent.

## Findings

**F1 (material, target test_design): the docs test makes the goal edit this repo's `.zzzops/prompts`.**
`DocsTests.test_prompts_name_full_shas` loops over both `fx.TEMPLATES / "prompts"` and `fx.ROOT / ".zzzops" / "prompts"`. It asserts that `.zzzops/prompts/test_design.md` and `.zzzops/prompts/implement.md` carry the new wording. To pass, `implement` would have to change `.zzzops/prompts/*`, and integrate refuses goal diffs that touch policy files (`.zzzops/POLICY.json`, `workflow.json`, `prompts`). The goal could never integrate.
Fix: assert only the template prompts (`plugins/zzzops/zzzops/templates/default/prompts`). The `.zzzops/prompts` copies follow through a separate policy change after the release. If a parity check is wanted, it belongs in that policy PR, not in this goal's tests.
Design note: design §4a's "Prompts" bullet names `.zzzops/prompts/...` paths. The implementer should edit the template copies only.

**F2 (material, target test_design): `test_reclaimed_reopened_correction_keeps_its_capability` cannot fail.**
The test runs on `design`, but in the default graph `design` has no `inputs.base` (its inputs are spec, dep_designs and dep_reviews). The test also only calls `push_dev` and never re-runs `base`. So the reclaimed card has no lease-side staleness at all, and the capability check (`architectural`) passes before and after any implementation, including one that wrongly keys the downgrade on the lease/record union.
This is the second F1 case in the design: a reopened correction, where the record is current and `record_stale` is empty, but base moved during the attempt. It has no teeth as written.
Fix: use a node with `inputs.base`, for example `test_design`. Steps:
1. Run `through_tests`.
2. Have review_tests raise a finding with `changes_requested`.
3. Start `test_design`. Its reason is `reopened`.
4. Call `restack_base`.
5. Abandon, then `start --reclaim`.
6. Assert `stale_because == ["inputs.base"]` and `run.capability == "reasoning"`, not `routine`.

## Not findings

- The lifecycle edit only drops `renew` from the key list. That is correct per design §5.
- `assert_renew` checks the argv and that the interval and timeout appear in `when`. That is enough without being brittle.
- The `at()` minute offsets give the goal-commit pointer distinct commit times, which handles the design's committer-date risk.

## Verdict

changes_requested: two material findings, both on test_design. Everything else is sound.
