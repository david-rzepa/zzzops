# G1040 independent test review, round 2

Decision: **approved**. No open findings and no new findings.

Read the complete task card, approved design revision 2 (`3f7f884dc1f76f4d638f9e1f8bc3fe5c9aa0d288`), complete current 431-line test file at checkpoint `7a07144b90eccc5e63336cf7c0286f65737d1499`, previous independent review, and exact interdiff from prior test checkpoint `824c48f1a37af827423ad48d858ddd23bb7eda65`. The only substantive change is adding `repeats: 1` to the schema test's blocked record. No production code or substantive assertion changed.

The correction is necessary: `validate_blocked` requires an integer repeats >= 1. Its previous absence was hidden by the baseline schema's earlier unknown-last_output return. The new fixture is valid apart from the intentionally unimplemented key. Independently verified under Python 3.10: removing last_output yields `[]` from validate_record, and an op goal holding that same otherwise-valid blocked record yields `[]` from validate_goal. With last_output present, the focused test fails solely with `record: unknown key last_output`, the expected baseline red result. One focused test runs in <0.001 s (0.0005 s measured runner wall time); there are no unrelated setup/schema failures.

The prior review's behavioral approval remains supported: real production record creation/frontier/refusal/op recurrence logic, capability-on/off and consumer freshness, no resurrection, genuine stale carriers, second block, agent-only schema restriction, all refusal reasons, new-vs-repeat op identity and actual dispute response, two public CLI journeys, and rollout prompt pairing. The one-line fix restores the intended schema assertion without weakening coverage. Existing full-suite evidence was not redundantly rerun. No owner decision is introduced.

## Dogfood notes

None.
