# G1016 review_tests (attempt 2)

I re-reviewed tests commit 6234405 (base 54d7e83) against design attempt 3 and the engine at read_dev 1c1387a. Interdiff: one test commit on top of 802c016 plus the review commit.

## Prior findings

- **review_tests:1:1: resolved.** `DocsTests.test_prompts_name_full_shas` now loops over `fx.TEMPLATES / "prompts"` only, so implement no longer has to touch `.zzzops/prompts`.
- **review_tests:1:2: resolved.** The test now runs on `test_design`, which has `inputs.base`. Steps: through_design, submit, review_tests changes_requested, start (asserts `reopened` and no `stale_because`), restack_base, abandon, `start --reclaim`. It asserts `stale_because == ["inputs.base"]` and capability `reasoning`. It is no longer vacuous. Its expectation, however, depends on a rule the design does not state; see F2.

## New findings

**F1 (material, target test_design): the submitted `commands` were narrowed.**
- Attempt 1 submitted `["cd .agents && python3 -m unittest test_engine_card_ux test_engine_lifecycle test_engine_schemas test_engine_journeys test_engine_docs", "python3 .agents/prompt_stats.py --check"]`.
- `goal.json` `records.test_design.output.commands` for attempt 2 is now only `["cd .agents && python3 -m unittest test_engine_card_ux test_engine_lifecycle"]`.
- Consequence: run_tests would skip `test_engine_schemas`, `test_engine_journeys` and `test_engine_docs`, plus the prompt budget check. That matters because the design changes `schemas.py` (the 40-hex override check), says the journey tests must pass unchanged, and edits the template prompts, which the budget check covers.
- Fix: restore the full attempt-1 list.

**F2 (material, target design): §2's capability rule does not achieve its stated intent for a reopened correction on a node with `inputs.base`.**
- Design §2 says: "A reclaimed `reopened` correction (record current, so `record_stale` is empty) keeps the node's own capability". The rule it states is `record_stale == ["inputs.base"]` gives `routine`.
- The premise "record current" is false whenever base moves during the reopened attempt. In the engine (frontier.py:207-239), live corrections are not part of `fp_parts`. `reopened` requires `r["input_fp"] == f`.
- After `base` re-runs, the record's `fp_parts` differ on `inputs.base`. The design's own claim() code (`rec_sb = stale_keys(r["fp_parts"], parts) if r["input_fp"] != fp`) therefore gives `record_stale == ["inputs.base"]`, and the stated rule yields `routine`.
- Base moving whenever dev moves is exactly the case the design calls common for `implement` and `test_design`. The design's verification case for this scenario (line 158) uses `design`, which has no `inputs.base`, so it never exercises the contradiction.
- The test writer noticed this. The rewritten test asserts `reasoning` and tells implement to add a condition the design does not contain ("routine only if record_stale == ["inputs.base"] and no live corrections"). Tests must not silently require behaviour the approved design does not state.
- Fix: state in §2 the rule that actually achieves the intent. For example: `routine` only when `record_stale == ["inputs.base"]` and the node has no live corrections (claim's state carries `corrections` for reclaimable and crash-loop states).
- Also decide the no-lease case explicitly. Today the frontier checks staleness before corrections, so a plain `start` of a reopened node whose base has since moved is `ready`/`stale` with `["inputs.base"]` and gets `routine` while carrying corrections. The design should say whether that case also keeps its own capability. Then update the verification bullet to use `test_design` or `implement`, matching the test.

## Not findings

- The rewritten test's comment "lease-side only: not routine" is inaccurate, since the record side is also stale. It can be corrected when test_design re-runs for F1, but on its own it is not material.
- The control test (record stale only on base, no corrections, gives `routine`) is unchanged and consistent with either wording of the rule.

## Verdict

changes_requested: both prior findings are resolved. There are two new material findings: F1 on test_design (restore the full commands list) and F2 on design (state the corrections condition).
