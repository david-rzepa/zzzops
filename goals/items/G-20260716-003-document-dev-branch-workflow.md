---
id: G-20260716-003-document-dev-branch-workflow
title: Document the dev-first Git workflow
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
tags: [git, branches, agents, release-safety]
external_refs: ["user-request:2026-07-16"]
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-003-document-dev-branch-workflow - Document the dev-first Git workflow

## Outcome / Why

Repository agents follow one safe Git workflow: create work branches from `dev`, integrate work into `dev`, and treat pushes to `main` as production release events. This prevents accidental release-CI execution and keeps ordinary development off `main`.

## Success criteria

- [ ] Root `AGENTS.md` states that all work branches must branch from `dev`, not `main`.
- [ ] Root `AGENTS.md` states that ordinary work is merged/integrated into `dev` and that pushing to `main` runs release CI.
- [ ] Guidance tells agents not to push or merge to `main` unless the user explicitly intends a release and the release preconditions are satisfied.
- [ ] Guidance is concise and unambiguous for new and resumed work; the parent goal later verifies that CI enforces the documented release trigger.
- [ ] Prompt-budget counts are regenerated and `.agents/prompt_stats.py --check` passes.

## Scope

- In: Git workflow guidance in this repository's root `AGENTS.md`, any minimal cross-reference required for consistency, and prompt-budget accounting.
- Out: Editing installed projects' `AGENTS.md`, implementing release CI, creating branch-protection rules, or documenting a workflow that CI does not actually enforce.

## Context and decisions

- User requested this TODO on 2026-07-16: work only in branches created from `dev`; pushing to `main` runs release CI.
- This is a required documentation sub-goal of `G-20260716-001-automate-semantic-releases`, not a duplicate CI implementation goal.
- The rule is the binding workflow policy and may land before its CI enforcement because the user explicitly ordered this sub-goal first; the parent must make the documented `main` behavior true before it completes.

## Approach and next action

**Next action:** Add the smallest binding Git workflow rule to root `AGENTS.md` from a work branch created from `dev`, then check it against representative branch/push scenarios.

### Fast feedback

- Baseline/current observable behavior: Root `AGENTS.md` requires semantic commits but does not define a `dev`-first branch or release-push policy.
- Hypothesis: A short explicit rule near the base-repository guidance prevents agents from branching from or casually pushing to `main`.
- Observation surface (test/harness/API/UI/log/MCP/etc.): `AGENTS.md`, actual Git branches, CI trigger YAML, and prompt-budget check.
- Smallest chunk: Add one compact paragraph specifying branch source, integration target, and `main` release semantics.
- Probe/action and expected signal: Ask the rule what to do for ordinary work, a `dev` merge, and a proposed `main` push; each yields one unambiguous safe action.
- Actual result/evidence: Not run.
- Wider checks after local proof: Compare wording to release workflow triggers and branch-protection/settings evidence, then regenerate prompt counts.

### Execution constraints

- Mode: `sequential`
- Parallel exception: none
- Resources/shared state: Root `AGENTS.md`, `dev`, `main`, release workflow configuration, and README prompt-budget table.

## Relationships

- Parent: [G-20260716-001](G-20260716-001-automate-semantic-releases.md)
- Children (required/optional + purpose/status): none
- Dependencies (status/reason): none; user explicitly ordered policy before CI enforcement.
- Blocks (impact): Parent goal cannot satisfy its branch-documentation criterion until this sub-goal is verified.

## Blockers

### Open

None at creation. Coordinate completion with the parent goal rather than inventing CI behavior.

### Resolved

None.

## Progress and evidence

Triaged as an actionable small documentation goal. Observed `dev` created from `main`, published to `origin/dev`, and current work branch created from `dev` before editing.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex | Created `new` as a required sub-goal | User requested explicit `dev`-first work and `main` release-CI guidance in root `AGENTS.md`. |
| 2026-07-16 | Codex/R-20260716-zzzops | Triaged `ready`; difficulty `S` | User resolved sequencing: document policy first and follow it during this run. |
