# Project success charter

<!-- zzzops-project-state
{
  "backend": "github_issues",
  "initialized": true,
  "migration_pending": false,
  "repository": {
    "identity": "david-rzepa/zzzops",
    "remote": "https://github.com/david-rzepa/zzzops.git"
  },
  "revision": 2,
  "schema_version": 1
}
zzzops-project-state -->

**Status:** complete
**Last reviewed:** 2026-07-16

## Overall goal
- Outcome: ZzzOps lets Codex and Claude Code manage long-term project work autonomously with durable state, minimal babysitting, and explicit human control.
- Primary beneficiaries: developers delegating long-running project work to coding agents
- Why it matters: Users can stop supervising agents late into the night without losing progress, priorities, blockers, or available work.
- Time horizon: ongoing, reviewed monthly

## Success metrics
| KPI | Why it matters | Baseline | Target / threshold | Evidence source | Review cadence |
| --- | --- | --- | --- | --- | --- |
| Canonical goal integrity | Lost or duplicated goal truth defeats autonomous execution. | Local goal files are canonical; backend initialization is not yet applied. | Zero known lost or duplicated canonical goals. | Backend portfolio and migration/idempotency tests. | Each release |
| Time to usable backlog | Setup friction increases babysitting. | Not yet measured. | Clean install to initialized, capturable backlog in under 10 minutes. | Timed clean-install and initialization acceptance run. | Each release |
| Autonomous workflow transitions | Measures whether agents can continue without unscheduled intervention. | Not yet measured. | At least 80% of eligible workflow transitions need no unscheduled human input. | Goal histories and categorized blocker records. | Monthly after at least 20 transitions |
| Management token overhead | Goal administration should not consume the value it enables. | Exact harness usage is currently unavailable. | Below 25% of compatible measured work plus management tokens. | Local `.zzzops/USAGE_LEDGER.md` compatible-token reviews. | Monthly when sufficient comparable samples exist |

## Project acceptance criteria
- [x] A clean installation can be agent-initialized and capture a canonical goal without manual form filling.
- [x] An execution run can prioritize, unblock, verify, checkpoint, and cycle across durable goals without losing state.
- [x] Unsupported capabilities and human-only decisions become explicit categorized blockers rather than invented behavior.
- [x] Codex and Claude Code receive equivalent concise workflow semantics.
- [x] Tests prove installer preservation, backend invariants, fast observable feedback, and prompt-budget accounting.

## Value rubric
- `critical`: required for project acceptance, safety, or a binding deadline.
- `high`: materially moves a priority KPI or unlocks critical/high-value work.
- `medium`: useful measurable contribution with limited leverage.
- `low`: weak, speculative, cosmetic, or currently unmeasured contribution.

When KPIs conflict, prefer: user authority and safety, correctness, privacy, verified project value, autonomy, then prompt savings

## Constraints and non-goals
### Constraints
- Remain primarily agent-driven and keep deterministic scripts narrow and cross-platform.
- Do not silently dual-write, fail over, invent user decisions, or expose secrets.
- Keep installed prompts distilled and prompt counts current.

### Non-goals
- Replace general-purpose project management suites.
- Guarantee capabilities that Codex or Claude Code does not expose.
- Consume usage limits merely to maximize token spend.

### Unacceptable tradeoffs
- More autonomy at the expense of user health, privacy, repository safety, or observable correctness.
- Lower prompt cost by omitting state required for safe resumption or human control.

## Assumptions and open questions
- None recorded at initialization; add evidence-backed changes with history.

## History
| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | ZzzOps initialization | Initialized revision 1 | Confirmed agent-generated plan; backend `github_issues`. |
| 2026-07-16 | ZzzOps migration | Migrated revision 2 | All 15 local goals verified as managed GitHub issues #7–#21; transitional files retired. |
