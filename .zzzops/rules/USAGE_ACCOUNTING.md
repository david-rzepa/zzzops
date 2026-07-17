# Usage accounting

Measure to improve value/effort and reduce coordination—not to consume limits. Never create/expand work or continue dead ends for usage.

## Sources

Label every number: `runtime-exact`, `api-exact`, `user-status`, `estimated` (rounded, method noted), or `unavailable`. Preserve distinct token/credit classes. Context %, rate-limit %, credits, billed tokens, and task-wide totals are not interchangeable. Multi-goal allocation is estimated even when the interval total is exact.

## Checkpoints

Inspect callable usage/limits at run start; before/after `L/XL` phases; after two transitions or ~30 minutes; on warnings; and before compaction/handoff/stop. Do not interrupt the human for `/status` or poll wastefully; record `unavailable`.

## Ledger

Before the first append run `python .agents/zzzops.py --repo . usage ensure`; it idempotently creates ignored user-local `.zzzops/USAGE_LEDGER.md` from the installed blank template. Append `R-YYYYMMDD-HHMM-agent`; never log prompts/secrets/private content. Reading or installing never creates the ledger.

- Goal work: investigation, implementation, tests, verification, domain reasoning.
- Management: inventory, prioritization, claims, links/status/blocker/index/ledger work, delegation/review/reconciliation/handoff.
- Put inseparable overhead under management with a note.

For shared intervals, retain the exact total, allocate rounded estimated shares that reconcile (or explain remainder), and append a row even if tokens are unavailable. For parallel work, use one run ID with distinct agents/goals plus `_goal-management`; note fan-out, latency benefit, usage, and contention.

## Review

For compatible measurements, management ratio = management / (management + goal work). After >=5 substantive runs, investigate ratios >25%: repeated rereads/rechecks, over-decomposition, broad index rewrites, verbose duplication, tiny goals, or low-value fan-out. Simplify without dropping safety/history/verification.

Periodically compare medians by work type/difficulty to re-estimate goals, expose recurring blockers, promote cheap unlocks, deprioritize poor value/effort with rationale, or split underestimated work. Cost alone does not override strategic priority or a human-set premise.

Use `$analyze-zzzops-usage` for value-per-token reviews. Prefer project-native KPI/outcome units per 1,000 compatible tokens. Cross-goal heuristic scores must expose their weights, realized fraction, confidence, token denominator, and uncertainty; never disguise them as objective value.
