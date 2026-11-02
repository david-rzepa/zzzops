# G1043 review_design round 3 — approved

Reviewed revision 3's diff (`4f9af989059cfa941d80e35d7bcee2094bea961c` → `a361e31ab8798ddb675ac6b835eda82dd46266c9`) against the unchanged spec and coordinator `de5640d1c5909ea924450aeea6450497a78946f6`. This is the narrow pre-implementation correction for `design:reopen:1`; no full suite was rerun.

The correction is sound. `verification_plan_sha256` hashes the ordered repository commands and actual execution mode/effective total/repository allocation, while excluding goal-command text and elapsed time. The whole-run hash stays strict. Thus two goals with different targeted commands can have an unavailable total comparison and an available repository comparison without claiming equivalent whole workloads.

The lookup selects one newest eligible actually-tested merged source before qualifying either scope. The nested `baseline.verification` has an independent status/reason, integer duration and signed delta, source goal/node/accepted commit/merge commit/tree/target/timestamp and source hash. An incompatible newer source is never replaced with a convenient older one. Missing narrow metadata, changed repository commands/allocation/environment and incomplete lookup remain explicitly unavailable; a total-unavailable result cannot suppress separately available repository evidence.

The approval example and required card tests show the repository delta even when the total comparison is unavailable. The concurrency caveat is necessary and now explicit: the same allocated workers and repository command do not make different concurrent goal workloads, machine load, caches or CPU types identical. This remains informational evidence, outside approval/review identity, without another scan, persistent state or regression gate.

The three previously resolved findings stay fixed: total CPU clamp precedes lane allocation; removal of the demonstrably stale property isolation entry preserves all semantic assertions; historical lookup retains the 64-document/256-history/16-tree and deadline/cleanup bounds, with no partial/older fallback. No new finding or owner-only question remains.
