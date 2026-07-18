# Goal template

For the `local_files` backend, copy to `goals/items/<id>.md`; replace placeholders.

```markdown
---
id: G-YYYYMMDD-NNN-slug
title: Outcome title
status: new
priority: P2
value: medium
difficulty: unknown
confidence: low
owner: unassigned
created: YYYY-MM-DD
updated: YYYY-MM-DD
target_date: null
last_reviewed: YYYY-MM-DD
review_after: null
parent: null
depends_on: []
blocks: []
needs_human: false
tags: []
external_refs: []
claim: {owner: null, claimed_at: null, expires_at: null}
implementation:
  branch: null
  base: null
  target: null
  pr: null
  review: {status: not_started, checkpoint: null}
---

# ID - Title

## Outcome / Why

Observable end state, beneficiary, value, urgency evidence.

## Success criteria

- [ ] Verifiable result and evidence method.

## Scope

- In: ...
- Out: ...

## Context and decisions

- Facts, constraints, assumptions, links, durable decisions.

## Approach and next action

**Next action:** Verb + target + stop condition.

### Fast feedback

- Baseline/current observable behavior:
- Hypothesis:
- Observation surface (test/harness/API/UI/log/MCP/etc.):
- Smallest chunk:
- Probe/action and expected signal:
- Actual result/evidence:
- Wider checks after local proof:

### Execution constraints

- Mode: resolve from reviewed PROJECT resource policy
- Parallel exception: record only when PROJECT and user ceilings permit it
- Resources/shared state: `none`

## Relationships

- Parent: none
- Children (required/optional + purpose/status): none
- Dependencies (status/reason): none
- Blocks (impact): none

## Blockers

### Open

None. Use `.zzzops/rules/BLOCKERS.md` schema.

### Resolved

None.

## Progress and evidence

Current resumable state and verification artifacts.

## Implementation and review

- Branch/base/target/PR: not started
- Human review checkpoint/status: not started

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| YYYY-MM-DD | actor | Created `new` | source |
```
