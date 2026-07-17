---
id: G-20260716-014-health-preferences-cli
title: Add private health preferences state and CLI
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
depends_on: [G-20260716-013-health-policy-schema]
blocks: [G-20260716-015-health-workflow-integration]
needs_human: false
tags: [health, preferences, cli, privacy]
external_refs: []
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-014 - Add private health preferences state and CLI

## Outcome / Why

The existing ZzzOps CLI edits/resets grouped health preferences and evaluates/records minimal ignored state without storing messages or raw event history.

## Success criteria

- [ ] Schema-driven interactive editing preserves existing/unknown preferences and supports cancel/reset.
- [ ] Machine-facing health check/record/status/reset commands are atomic and return structured capability-qualified results.
- [ ] `HEALTH_STATE.json` is lazy, ignored, minimal, retention-pruned, and never installed as user state.
- [ ] Temp-repository CLI tests cover round trips, invalid values, cancellation, reset, and unknown-key preservation.

## Scope

- In: CLI, preference template, ignored state, tests.
- Out: workflow hooks and cross-project/global surveillance.

## Approach and next action

**Next action:** After G-013, add one schema-driven health group and prove an edit/check/reset round trip.

### Fast feedback

- Baseline: CLI has only refill/parallelization groups.
- Hypothesis: declarative fields keep fine-grained configuration maintainable.
- Observation surface: subprocess JSON and temp files.
- Smallest chunk: preserve unknown keys while toggling enablement.
- Probe/action and expected signal: exact round trip except selected field.
- Actual result/evidence: pending.
- Wider checks: all fields/state/reset/platform paths.

### Execution constraints

- Mode: `sequential`
- Parallel exception: none
- Resources/shared state: CLI, preferences/state templates, tests.

## Relationships

- Parent: G-009
- Children: none
- Dependencies: G-013
- Blocks: G-015

## Blockers

### Open

None beyond dependencies.

### Resolved

None.

## Progress and evidence

Triaged; waits for policy schema.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex/R-20260716-execute-root | Created `triaged` | Private state/UI isolated from pure policy. |
