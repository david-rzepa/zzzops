---
id: G-20260716-010-initialization-state-cli
title: Add deterministic initialization state and CLI
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
depends_on: []
blocks: [G-20260716-011-goal-backends-workflow-routing]
needs_human: false
tags: [initialization, cli, schema, atomicity]
external_refs: []
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-010 - Add deterministic initialization state and CLI

## Outcome / Why

`goals/PROJECT.md` contains machine-readable initialization metadata plus the human charter, and `.agents/zzzops.py init inspect|validate|apply` provides idempotent, stale-safe, atomic primitives without making semantic decisions or external writes.

## Success criteria

- [ ] Define compact versioned project/plan schemas with observed facts, proposals, confirmations, backend capability evidence, and a base digest.
- [ ] Inspect reports fresh/partial/complete state and repository facts as JSON; validate rejects unknown, incomplete, unconfirmed, or stale plans.
- [ ] Apply atomically renders the confirmed charter/state and reruns as a no-op.
- [ ] Focused temporary-repository tests cover malformed, partial, stale, atomic-failure, and repeat paths while preserving the existing preferences UI.

## Scope

- In: shared PROJECT metadata, ignored resumable plan template/path, deterministic CLI and tests.
- Out: issue CRUD, semantic project interpretation, Git commits, network writes, or workflow routing.

## Context and decisions

- Keep one authoritative shared file to avoid cross-file atomicity; store the resumable plan under ignored `.zzzops/init/plan.json`.

## Approach and next action

**Next action:** Specify fixtures and implement inspect/validate/apply until the smallest temporary-repository tests pass.

### Fast feedback

- Baseline/current observable behavior: CLI only edits preferences; PROJECT is unstructured and incomplete.
- Hypothesis: a JSON metadata block plus pure plan validation makes initialization deterministic and resumable.
- Observation surface (test/harness/API/UI/log/MCP/etc.): CLI JSON/stdout, temp repositories, file digests, injected replace failure.
- Smallest chunk: parse/render PROJECT metadata and inspect a fresh fixture.
- Probe/action and expected signal: inspect returns schema-valid `initialized:false` without mutation.
- Actual result/evidence: pending.
- Wider checks after local proof: validate/apply/rerun, preferences UI, compile and prompt checks.

### Execution constraints

- Mode: `sequential`
- Parallel exception: none
- Resources/shared state: `.agents/zzzops.py`, PROJECT/plan templates, tests.

## Relationships

- Parent: [G-008](G-20260716-008-require-project-value-interview.md)
- Children: none
- Dependencies: none
- Blocks: G-011

## Blockers

### Open

None.

### Resolved

None.

## Progress and evidence

Triaged from the initialization audit; ready for execution.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex/R-20260716-execute-root | Created `ready` | Required deterministic foundation isolated from semantic/backend integration. |
