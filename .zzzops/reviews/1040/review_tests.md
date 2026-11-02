# G1040 independent test review

Decision: **approved**. No findings.

Reviewed design revision 2 (blob `3f7f884dc1f76f4d638f9e1f8bc3fe5c9aa0d288`) and the complete tests checkpoint diff `de5640d1c5909ea924450aeea6450497a78946f6..824c48f1a37af827423ad48d858ddd23bb7eda65`.

The 20 tests map to the approved design's acceptance matrix. They call the production blocked-record writer, frontier, response-submission validation, op-finding producer and dispute renderer rather than implementing the new rules inside a mock. Only filesystem syncing is stubbed for pure checks. They distinguish a carrier fresh against a held output from one genuinely stale after a spec edit or one that saw an older output; preserve consumers' blocked state; prevent answered-finding resurrection; check repeated blocks and op-carried findings; keep the capability-off behavior and reject last_output on inappropriate records.

Refusal tests reach done_record's real response check and cover every documented reason code plus separate missing-response guidance. Op recurrence tests distinguish new failures from normalized repeats, check all five normalization token classes, uphold only the same failure, and display the actual response including historical findings with response=None. The real CLI journeys pin stale test-design corrections and owner-answer retries, required responses, re-review cards and approval decisions. The rollout pairing and template default remain explicit as requested in the design.

Independent verification: `python3 -m unittest discover -s .agents -p test_engine_blocked_findings.py` ran **20 tests in 14.325 seconds**, with expected failures from absent G1040 behavior (capability, held outputs, richer refusal codes, normalizer and documented contract). The already-supported stale replay and op-wait exclusion pass. No unrelated fixture errors occurred. Module collection yields exactly **20 distinct IDs**; test modules are imported as modules, avoiding duplicated TestCases. Python 3.10 syntax parsing passes and no newer unittest/context APIs are used. There are no sleeps or wall-clock assertions, and only two CLI journeys; the remaining coverage is fast in-process checking.

The recorded existing G1026 owner-question suite and op-recurrence regression remain unchanged and are being run separately by the test author; this review did not duplicate that suite. No prior open findings exist, and no new owner decision is needed.
