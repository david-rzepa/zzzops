---
id: G-20260716-012-initialization-install-docs-regression
title: Prove initialization installation and user guidance
status: triaged
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
depends_on: [G-20260716-010-initialization-state-cli, G-20260716-011-goal-backends-workflow-routing]
blocks: []
needs_human: false
tags: [installer, documentation, tests, prompt-budget]
external_refs: []
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-012 - Prove initialization installation and user guidance

## Outcome / Why

Clean installs and updates deliver initialization/backend mechanics without running initialization, and concise Codex/Claude/README guidance accurately explains the agent-driven flow and preferences CLI notice.

## Success criteria

- [ ] Installer copies all new mechanics/templates/rules but never initializes, mutates GitHub, or overwrites state.
- [ ] Clean/update/rerun tests prove preservation and initialization exemption.
- [ ] README, maintainer docs, CLI help, Codex and Claude surfaces agree and prompt counts are current.
- [ ] CI runs all new tests plus existing release/prompt checks.

## Scope

- In: installer manifest/output/tests, docs, CI test discovery, prompt counts.
- Out: target-project initialization or real GitHub mutation.

## Approach and next action

**Next action:** After G-010/G-011, run a fresh temp install and close every missing-file/contract gap until full CI passes.

### Fast feedback

- Baseline: installer knows no init/backend rule and CI discovers only existing tests.
- Hypothesis: explicit manifest and temp-target probes prevent silent packaging drift.
- Observation surface: installer preview/apply/rerun, filesystem assertions, prompt stats, CI command.
- Smallest chunk: fresh install contains new artifacts and leaves PROJECT uninitialized.
- Probe/action and expected signal: temp-target assertion passes with no external calls.
- Actual result/evidence: pending.
- Wider checks: update preservation, Claude parity, full regression.

### Execution constraints

- Mode: `sequential`
- Parallel exception: wait-only CI monitoring
- Resources/shared state: installer, templates, docs, workflow.

## Relationships

- Parent: G-008
- Children: none
- Dependencies: G-010, G-011
- Blocks: none

## Blockers

### Open

None.

### Resolved

None.

## Progress and evidence

Triaged; waits for implementation artifacts.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex/R-20260716-execute-root | Created `triaged` | Packaging/docs proof isolated as a terminal child. |
