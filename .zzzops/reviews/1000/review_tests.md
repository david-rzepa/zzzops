# review_tests G1000 (attempt 5): changes requested

Range-diff: test commits unchanged by the rebase. Run at 6119eac: test_engine_lenses, test_engine_docs and test_marketplace_bundle pass (75 tests). test_engine_card_ux/card_budget: 65 run, 1 failure.

## Finding (target test_design)
`test_engine_card_ux.DocsTests.test_prompts_name_full_shas` (dev, G1016) reads `fx.TEMPLATES`, which G1000 repointed to the frozen fixture `.agents/fixtures/graph12`. The fixture copies of `prompts/test_design.md` and `prompts/implement.md` predate G1016:
- test_design.md: needs `else your work branch's HEAD. Name {"tests": {"commit": "<full 40-hex sha>"}}` wording.
- implement.md: needs `else your work branch's HEAD; omit the key unless you override.`

Fix: re-sync these from dev's `templates/default/prompts`. The other graph12 files I compared (workflow.json, POLICY.json) match dev's template; re-check the remaining prompts.
