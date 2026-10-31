# Project success charter

**Status:** complete
**Last reviewed:** 2026-10-26

## Overall goal
- Outcome: ZzzOps lets supported coding agents manage long-term project work autonomously with durable state, minimal babysitting, and explicit human control.
- Primary beneficiaries: developers delegating long-running project work to coding agents
- Why it matters: Users can stop supervising agents late into the night without losing progress, priorities, blockers, or available work.
- Time horizon: ongoing, reviewed monthly

## Success metrics
| KPI | Why it matters | Baseline | Target / threshold | Evidence source | Review cadence |
| --- | --- | --- | --- | --- | --- |
| Canonical goal integrity | Lost or duplicated goal truth defeats autonomous execution. | Goal branches (`zzzops/goal/g<id>`) are the canonical store. | Zero known lost or duplicated canonical goals. | Backend portfolio and migration/idempotency tests. | Each release |
| Time to usable backlog | Setup friction increases babysitting. | Not yet measured. | Supported plugin install to initialized, capturable backlog in under 10 minutes. | Timed supported-platform plugin installation and initialization acceptance run. | Each release |
| Autonomous workflow transitions | Measures whether agents can continue without unscheduled intervention. | Not yet measured. | At least 80% of eligible workflow transitions need no unscheduled human input. | Goal histories and categorized blocker records. | Monthly after at least 20 transitions |

## Project acceptance criteria
- [x] A clean supported Agent Plugin installation can be agent-initialized and capture a canonical goal without manual form filling.
- [x] An execution run can prioritize, unblock, verify, checkpoint, and cycle across durable goals without losing state.
- [x] Unsupported capabilities and human-only decisions become explicit categorized blockers rather than invented behavior.
- [x] Supported coding agents receive concise, discoverable Agent Plugin workflow semantics.
- [x] Tests prove Agent Plugin packaging and marketplace discovery, backend invariants, fast observable feedback, and prompt-budget accounting.

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
- Use available subscription capacity to advance evidenced project goals and safe valuable backlog work; do not let quota maximization override value, safety, or user authority.
- Keep Codex and Claude Code distributions generated from shared canonical sources; claim platform support only after platform-native validation and install/discovery/workflow acceptance evidence.

### Non-goals
- Replace general-purpose project management suites.
- Guarantee capabilities that Codex does not expose.
- Restore or maintain the retired per-project installer, or maintain divergent Codex and Claude Code workflow implementations.
- Spend tokens on work with no evidenced link to project value.

### Unacceptable tradeoffs
- More autonomy at the expense of user health, privacy, repository safety, or observable correctness.
- Lower prompt cost by omitting state required for safe resumption or human control.

## Assumptions and open questions
- None recorded at initialization; add evidence-backed changes with history.

## Operating policy

Settings and per-section agent instructions: [POLICY.json](POLICY.json). The phase graph: [workflow.json](workflow.json); node prompts: [prompts/](prompts/). Policy changes land on `dev` through a `zzzops/policy/*` branch, which pauses new work until it lands. This file is hand-edited and not bound to the policy.
