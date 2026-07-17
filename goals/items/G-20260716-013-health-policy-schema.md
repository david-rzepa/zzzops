---
id: G-20260716-013-health-policy-schema
title: Define deterministic health policy and schema
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
depends_on: [G-20260716-008-require-project-value-interview]
blocks: [G-20260716-014-health-preferences-cli]
needs_human: true
tags: [health, policy, privacy, time]
external_refs: []
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-013 - Define deterministic health policy and schema

## Outcome / Why

A pure standard-library policy evaluates injected time, explicitly qualified activity evidence, preferences, and minimal state into at most one explainable non-medical nudge.

## Success criteria

- [ ] Validate finely grained grouped settings and distinguish `exact_message`, `observed_receipt`, and `current_only` evidence.
- [ ] Deterministic precedence/cooldown/snooze/quiet/pause logic returns reason/evidence without unsupported inference.
- [ ] Synthetic-clock tests cover DST, midnight, weekends, overnight schedules, inactivity, cooldown, missing/stale evidence, and privacy retention.

## Scope

- In: pure policy/schema module and unit tests.
- Out: I/O, transcript scraping, medical quantities, workflow hooks, or hard blocking by default.

## Approach and next action

**Next action:** Resolve parent `B-001`, then encode the confirmed defaults as table-driven tests before implementation.

### Fast feedback

- Baseline: no portable exact message timestamps or health policy exists.
- Hypothesis: capability-qualified evidence prevents false timing claims.
- Observation surface: injected-clock table tests and returned reason/evidence.
- Smallest chunk: one late-night case and one unsupported-evidence no-op.
- Probe/action and expected signal: exactly one nudge versus deterministic no-op.
- Actual result/evidence: pending.
- Wider checks: full boundary/property matrix.

### Execution constraints

- Mode: `sequential`
- Parallel exception: none
- Resources/shared state: new health module/tests.

## Relationships

- Parent: G-009
- Children: none
- Dependencies: G-008
- Blocks: G-014

## Blockers

### Open

See parent `B-001` for required policy decisions.

### Resolved

None.

## Progress and evidence

Triaged from capability audit; blocked at execution by parent decision.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex/R-20260716-execute-root | Created `triaged` | Pure deterministic policy isolated from state/UI. |
