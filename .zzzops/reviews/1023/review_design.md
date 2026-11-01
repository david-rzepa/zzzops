# Review of G1023 design

Verdict: changes_requested. One blocking finding; the rest of the design is sound.

## Verified against tip a05fb97
- records.py:244 hint, MIGRATING.md:26 and .zzzops/prompts/test_design.md:8 all contain the old `<sha>` form; these are the only three hits of `<sha>` in the tree. MIGRATING.md line 25's `<commit>` is correctly left alone. The template prompt and test_engine_card_ux.py:472 already use `<full 40-hex sha>`.

## Finding 1 (blocking): edit 3 breaks the project's policy rules
`.zzzops/prompts/` is policy, not goal code.
- `engine/ops/integrate.py:104` diffs `.zzzops/POLICY.json`, `.zzzops/workflow.json` and `.zzzops/prompts` between base and work branch and fails integration with `policy-paths`: "goal diffs must not touch policy files; change policy through a zzzops/policy/* branch". A G1023 implementation that edits `.zzzops/prompts/test_design.md` can never integrate.
- docs/EXECUTION.md:32-34 and BRANCH_PROTECTION.md say policy changes go through a human-created `zzzops/policy/*` branch, which also pauses all new work until it lands.
- test_engine_card_ux.py:469 already records the convention: "Template prompts only: this repo's .zzzops/prompts follow through a separate policy change."

Fix: drop edit 3 from this goal and from the grep test's scope (scope: engine, references, skills, templates only, matching the spec). Record the repo copy as a follow-up to be carried by a policy branch, or by the next policy change already planned, and say so in the design's Out of scope. Also remove the "sync from template" risk note, which is moot (no sync check exists; grep of .agents finds none).

## Other notes (non-blocking)
- Tests: the hint test should reuse the fixture in .agents/test_engine_checkpoint.py (the checkpoint_required refusals); the design says "existing fixture" without naming it; the implementer should name it.
- The grep test must cover both the raw `"commit": "<sha>"` and escaped `\"commit\": \"<sha>\"` forms; the design says so. Good.
- G1000/#748 conflict handling is reasonable.
