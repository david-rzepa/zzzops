# G1023 design: say "full 40-hex sha" wherever a checkpoint override is shown

## Outcome
After G1016, submit and edit refuse checkpoint overrides that are not full 40-hex shas. Every place that tells a user or agent how to write an override must say so, with the placeholder `<full 40-hex sha>`, the wording the card, CLI_USAGE and the template prompt already use. No behavior changes; only text and tests.

## Change (three text edits, one new test file section)
Found at tip a05fb97 by grepping `"commit": "<sha>"`:
1. `plugins/zzzops/zzzops/engine/records.py:244`, the `checkpoint_required` hint: `{\"%s\": {\"commit\": \"<sha>\"}}` becomes `{\"%s\": {\"commit\": \"<full 40-hex sha>\"}}`. The sentence stays otherwise as is.
2. `plugins/zzzops/zzzops/references/MIGRATING.md:26`: "Give checkpoint outputs as `{"commit": "<sha>"}`" becomes `{"commit": "<full 40-hex sha>"}`. (Line 25's `"commit": "<commit>"` is an artifact value, not a checkpoint override; leave it.)
3. `.zzzops/prompts/test_design.md:8`, the repo's own copy of the prompt, still says `<sha>`; the packaged template (`templates/default/prompts/test_design.md`) is already correct. Bring the repo copy in line (the spec's grep scope omits it, but it is the same defect and is shown to agents).

Rejected: rewording to a prose rule ("a full sha") instead of the placeholder. The placeholder form is what G1016's tests already assert elsewhere, so one phrase stays greppable. Rejected: making the hint print the actual suggested sha; that is a feature, not this goal.

## Tests
- Engine test: trigger `checkpoint_required` (no-commit phase) and assert the message contains `full 40-hex sha`. Reuse the existing fixture that produces this refusal.
- Docs test: assert MIGRATING.md contains `"commit": "<full 40-hex sha>"`.
- Grep test: over engine, references, skills, templates and `.zzzops/prompts`, assert no `"commit": "<sha>"` (and the escaped `\"commit\": \"<sha>\"` form) remains. The existing check at `.agents/test_engine_card_ux.py:472` is the neighbouring pattern; add beside it.

## Risks
Very low. The only risk is a test pinning the old hint text; grep before editing. The repo prompt copy may be generated from the template by a sync check; if so, edit via the template and sync rather than by hand.

## Avoiding conflicts with G1000 (PR #748, unmerged)
G1000 also edits CLI_USAGE and MIGRATING.md. This goal touches only MIGRATING.md line 26, one sentence, and not CLI_USAGE at all (its line 33 is already correct). To keep merges clean:
- Change only that one fragment in MIGRATING.md; do not reflow or renumber surrounding lines.
- Implement after rebasing onto the integration tip; if #748 merges first, re-run the grep at the new tip and apply the edit to wherever the string moved, rather than to remembered line numbers.
- If #748 rewrites that step, the grep test still guards the outcome: whichever lands second must keep the placeholder, and a conflict is resolved by taking G1000's text with `<full 40-hex sha>` in it.

## Out of scope
Validation logic (G1016), CLI_USAGE rewording, any other `<sha>` placeholders that are not checkpoint overrides.
