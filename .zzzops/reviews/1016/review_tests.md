# G1016 review_tests (attempt 3)

Decision: approved.

Reviewed commit e0d8f73 (base 54d7e83) against design attempt 4 (blob 2c1af88).

## Prior findings
- review_tests:2:1 (commands narrowed): resolved. records.test_design.output.commands is again
  ["cd .agents && python3 -m unittest test_engine_card_ux test_engine_lifecycle test_engine_schemas test_engine_journeys test_engine_docs", "python3 .agents/prompt_stats.py --check"].
- review_tests:2:2 (design capability rule): resolved by design attempt 4 §2 (routine needs record_stale == ["inputs.base"] and no live corrections; plain-start of a reopened node after base moved keeps its own capability, recorded as a deliberate change).

## Capability tests vs design §2 attempt 4
- test_reclaimed_reopened_correction_keeps_its_capability: test_design reopened by a review_tests finding, base restacked during the attempt, abandon, start --reclaim; asserts reason reclaim, stale_because == ["inputs.base"], non-empty corrections, capability reasoning. Matches Tests bullet (b).
- test_plain_start_of_reopened_node_after_base_moved_keeps_its_capability (new): reason stale, stale_because ["inputs.base"], non-empty corrections, capability reasoning. Matches bullet (a) and the no-lease decision.
- Control test_record_stale_only_on_base_is_routine_on_start_and_after_reclaim now also asserts no corrections and expects routine on start and after reclaim. The design names implement for the control; the test uses test_design, which has inputs.base and the same rule, so this is equivalent.
- test_reclaimed_first_attempt_after_base_moved_keeps_its_capability unchanged (lease-side only staleness keeps own capability).

## Fails for the right reason (run at e0d8f73, pre-implementation)
- plain-start reopened test: reaches the capability assertion and fails 'reasoning' != 'routine', i.e. exactly today's behaviour the design changes (reason, stale_because and corrections already hold).
- the reclaim tests error with KeyError 'stale_because' on the reclaim card, the missing §2 staleness keys.

## Docs test
DocsTests.test_prompts_name_full_shas iterates only fx.TEMPLATES / "prompts"; the diff touches only .agents/test_engine_card_ux.py and .agents/test_engine_lifecycle.py, no policy files.

No new findings.
