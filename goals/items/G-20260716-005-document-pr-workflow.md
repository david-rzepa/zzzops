---
id: G-20260716-005-document-pr-workflow
title: Document the dev-targeted pull request workflow
status: ready
priority: P1
value: high
difficulty: S
confidence: high
owner: unassigned
created: 2026-07-16
updated: 2026-07-16
target_date: null
last_reviewed: 2026-07-16
review_after: null
parent: G-20260716-001-automate-semantic-releases
depends_on: []
blocks: []
needs_human: false
tags: [git, pull-requests, agents, commits, release-safety]
external_refs: ["user-request:2026-07-16"]
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-005-document-pr-workflow - Document the dev-targeted pull request workflow

## Outcome / Why

Root `AGENTS.md` gives agents one complete contribution path: branch from `dev`, make reviewable commits, open pull requests targeting `dev`, and reserve `main` for the release path. Commit structure balances reviewability with atomic rollback safety.

## Success criteria

- [ ] Root `AGENTS.md` requires every ordinary work branch to start from current `dev` and every ordinary PR to target `dev`, never `main`.
- [ ] Guidance permits large features to contain smaller coherent commits when that aids review, testing, or partial integration.
- [ ] Guidance prefers squashing changes that are only valid together into one atomic semantic commit so incomplete units are not independently merged or reverted.
- [ ] Guidance explains that independently useful/revertible changes should remain separate commits, making partial rollback safer rather than mechanically squashing every PR.
- [ ] The new wording is concise, consistent with actual branch protection/release CI, and does not alter installed projects' `AGENTS.md`.
- [ ] README prompt-budget counts are regenerated and `.agents/prompt_stats.py --check` passes.

## Scope

- In: This repository's root `AGENTS.md`, minimal consistency updates, prompt-budget accounting, and scenario-based documentation checks.
- Out: GitHub ruleset configuration, merging a PR, changing installed project instructions, or prescribing one commit per entire feature regardless of separability.

## Context and decisions

- User requested this goal on 2026-07-16 after `G-20260716-003` documented the initial `dev`-first rule.
- This extends rather than invalidates `G-20260716-003`: branches originate from `dev`, PRs target `dev`, and only intended releases advance to `main`.
- User preference: large work may use smaller commits, but work that is all required together should ideally be squashed to preserve atomic rollback behavior.

## Approach and next action

**Next action:** Draft one compact replacement for the existing `AGENTS.md` Git paragraph, then scenario-check branch source, PR target, separable commits, inseparable commits, partial revert, and release behavior before editing.

### Fast feedback

- Baseline/current observable behavior: `AGENTS.md:21` defines branch source/integration target but does not explicitly require PRs or explain commit grouping.
- Hypothesis: One short expanded paragraph can encode the complete workflow without burdening every agent prompt.
- Observation surface (test/harness/API/UI/log/MCP/etc.): Root `AGENTS.md`, representative workflow scenarios, prompt-budget check, and GitHub branch settings from the enforcement sibling.
- Smallest chunk: Add only PR target and atomic-commit guidance to the existing paragraph.
- Probe/action and expected signal: Six representative scenarios each yield one unambiguous branch/PR/commit action.
- Actual result/evidence: Not run.
- Wider checks after local proof: Compare against live rulesets and CI triggers, then regenerate prompt counts.

### Execution constraints

- Mode: `sequential`
- Parallel exception: none
- Resources/shared state: Root `AGENTS.md`, README prompt-budget table, `dev`, and `main`.

## Relationships

- Parent: [G-20260716-001](G-20260716-001-automate-semantic-releases.md)
- Children (required/optional + purpose/status): none
- Dependencies (status/reason): none; coordinate wording with sibling `G-20260716-006` so policy and enforcement agree.
- Blocks (impact): none directly; incomplete guidance increases accidental `main` PR/release risk.

## Blockers

### Open

None.

### Resolved

None.

## Progress and evidence

Triaged as an actionable small documentation goal. The existing `AGENTS.md:21` paragraph is the exact edit surface and the sibling enforcement goal supplies the consistency boundary.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex | Created `new` | User requested explicit `dev`-origin/target PR rules and atomic-but-reviewable commit guidance. |
| 2026-07-16 | Codex/R-20260716-queued | Triaged `ready` | Scope, scenarios, edit surface, and verification are concrete. |
