---
id: G-20260716-015-health-workflow-integration
title: Integrate health nudges across ZzzOps workflows
status: triaged
priority: P1
value: high
difficulty: M
confidence: medium
owner: unassigned
created: 2026-07-16
updated: 2026-07-16
target_date: null
last_reviewed: 2026-07-16
review_after: null
parent: G-20260716-009-add-user-health-module
depends_on: [G-20260716-014-health-preferences-cli]
blocks: []
needs_human: false
tags: [health, workflows, installer, documentation, tests]
external_refs: []
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-015 - Integrate health nudges across ZzzOps workflows

## Outcome / Why

Every non-install workflow invokes one concise, capability-honest health hook; installs preserve preferences, never create health state, and Codex/Claude documentation sets accurate expectations.

## Success criteria

- [ ] A shared rule defines entry/response/checkpoint/exit hooks, at most one nudge per hook, and graceful no-op behavior.
- [ ] Five non-install skills use it after initialization; execute adds bounded long-run checkpoints; installer remains exempt from prompting.
- [ ] Installer preserves preferences, ignores but does not create state, and delivers identical Codex/Claude behavior.
- [ ] Integration/tests/docs cover exact/approximate/current-only capability, no-repeat/privacy, clean/update install, CI, and prompt budget.

## Scope

- In: workflow prompts/rules, installer, README/capability matrix, integration tests/CI.
- Out: guarantees outside active ZzzOps workflows or private transcript scraping.

## Approach and next action

**Next action:** After G-014, integrate one add-workflow hook and prove no-op/nudge transcripts before widening to all workflows.

### Fast feedback

- Baseline: workflows have no health hook.
- Hypothesis: one shared rule keeps prompt cost low and behavior consistent.
- Observation surface: synthetic workflow transcripts, installer fixture, prompt stats.
- Smallest chunk: add workflow entry emits zero/one expected nudge.
- Probe/action and expected signal: capability/default matrix passes without duplicate output.
- Actual result/evidence: pending.
- Wider checks: all workflows, install/update, full CI.

### Execution constraints

- Mode: `sequential`
- Parallel exception: wait-only CI monitoring
- Resources/shared state: five skills, shared rules, installer/docs/tests.

## Relationships

- Parent: G-009
- Children: none
- Dependencies: G-014
- Blocks: none

## Blockers

### Open

None beyond dependencies.

### Resolved

None.

## Progress and evidence

Triaged; waits for policy and CLI.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex/R-20260716-execute-root | Created `triaged` | Prompt/install integration isolated as terminal health child. |
