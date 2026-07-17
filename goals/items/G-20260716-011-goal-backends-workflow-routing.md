---
id: G-20260716-011-goal-backends-workflow-routing
title: Add canonical goal backends and workflow routing
status: ready
priority: P1
value: high
difficulty: M
confidence: high
owner: unassigned
created: 2026-07-16
updated: 2026-07-16
target_date: null
last_reviewed: 2026-07-16
review_after: null
parent: G-20260716-008-require-project-value-interview
depends_on: [G-20260716-010-initialization-state-cli]
blocks: [G-20260716-012-initialization-install-docs-regression]
needs_human: false
tags: [github-issues, local-files, workflows, git]
external_refs: []
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-011 - Add canonical goal backends and workflow routing

## Outcome / Why

All non-install workflows run one initialization preflight and route agent-driven operations to exactly one canonical backend: native GitHub Issues when selected, otherwise local goal files.

## Success criteria

- [ ] Add concise initialization/backend rules and a deterministic managed GitHub issue schema with drift-safe updates and append-only history.
- [ ] Five non-install skills share preflight/routing semantics; installer remains exempt.
- [ ] Capture performs no Git automation; execution defaults current branch and only checkpoints pending local goal state without unrelated files or empty GitHub commits.
- [ ] Contract tests cover backend selection/failure, issue round trips/unmanaged preservation, capture Git invariants, and execution routing.

## Scope

- In: rules, managed issue parser/renderer/validator helpers, skill/reference routing, root capture exception.
- Out: universal CRUD wrapper, silent fallback/sync, project-board support, real issue mutations in tests.

## Approach and next action

**Next action:** After G-010, implement the managed issue fixture round trip, then wire one shared preflight into each workflow.

### Fast feedback

- Baseline: workflows assume local files and apply inconsistent charter checks.
- Hypothesis: one shared rule plus narrow helpers removes divergence without duplicating transport logic.
- Observation surface: fixture round trips, static contract matrix, mocked native-gh responses, Git status.
- Smallest chunk: preserve unmanaged issue text across managed-block parse/render.
- Probe/action and expected signal: exact round trip plus changed managed field leaves unmanaged bytes intact.
- Actual result/evidence: pending.
- Wider checks: all workflows, dirty tree cases, prompt budget.

### Execution constraints

- Mode: `sequential`
- Parallel exception: none
- Resources/shared state: skills/rules, CLI helpers, AGENTS.md, tests.

## Relationships

- Parent: G-008
- Children: none
- Dependencies: G-010
- Blocks: G-012

## Blockers

### Open

None.

### Resolved

None.

## Progress and evidence

Ready; G-010 supplied the initialized-state contract and deterministic CLI boundary.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex/R-20260716-execute-root | Created `triaged` | Backend/workflow integration depends on G-010. |
| 2026-07-16 | Codex/R-20260716-execute-root | Dependency satisfied; moved `ready` | G-010 tests and state contract passed. |
