# Create and triage

1. Search goals/project/trackers for duplicates and authoritative facts. Capture outcome, value, constraints, owner, dates, evidence, and non-goals. Link/refine existing work rather than duplicate it.
2. Promptly create a provisional canonical goal using `BACKENDS.md`: a managed issue or a local file from `goals/TEMPLATE.md`; use `new`, `P2`, difficulty `unknown`, confidence `low` unless evidence says otherwise.
3. Investigate boundedly: observable end state/beneficiary; completion evidence; scope; relevant components/decisions; dependencies/risks/authority; and whether this is a goal, checklist item, duplicate, or child. Persist findings, not raw logs.
4. If consequential ambiguity remains, follow `.zzzops/rules/BLOCKERS.md`: record it, set `needs_human`, queue it, and ask one compact batch with recommended defaults and continuation boundaries. Proceed on reversible cosmetic assumptions; never speculate across foundational choices.
5. Write independently verifiable criteria and explicit scope. Avoid vague completion language.
6. Map parent/dependencies, then create a child only for a separately verifiable, independently prioritized/blocked/claimed outcome or distinct risk/workstream; use parent checklists otherwise. Prefer depth <=3; label required/optional; update both directions and reject cycles.
7. Set priority/value/difficulty/confidence/owner/dates from `goals/PROJECT.md`, `.zzzops/rules/GOAL_SYSTEM.md`, and analogous ledger evidence. State which acceptance criterion/KPI/beneficiary the goal advances; if the charter cannot support a value judgment, keep confidence low and record/ask about the gap. Preserve user budgets; otherwise bound a checkpoint, not invented token cost.
8. Give every actionable leaf one verb-led next action with target/stop condition, plus baseline, falsifiable hypothesis, observation surface, smallest code/work chunk, probe/action, expected signal, wider checks, and resource constraints. If no existing surface reveals the behavior, scope the smallest harness/debug adapter/MCP server needed; otherwise record the observability gap as a blocker. Default execution to sequential.
9. Set state: `ready` if actionable/no gate; `triaged` if understood but preparation/children/expected dependency remain; `blocked` only if a specific blocker leaves no useful work; `cancelled` with rationale/replacement.
10. Update canonical goal, relations, `needs_human`, history, and any local derived index consistently. If execution was requested, continue with `EXECUTE.md`.

For independent child breakdowns, `.zzzops/rules/EXECUTION_STRATEGY.md` permits up to two read-only proposal sub-agents; main agent resolves overlap/cycles and performs every write.
