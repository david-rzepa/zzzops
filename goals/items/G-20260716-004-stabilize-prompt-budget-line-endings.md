---
id: G-20260716-004-stabilize-prompt-budget-line-endings
title: Make prompt-budget counts line-ending invariant
status: ready
priority: P2
value: medium
difficulty: S
confidence: high
owner: unassigned
created: 2026-07-16
updated: 2026-07-16
target_date: null
last_reviewed: 2026-07-16
review_after: null
parent: null
depends_on: []
blocks: []
needs_human: false
tags: [bug, prompt-budget, portability, tests]
external_refs: [".agents/prompt_stats.py:33", "README.md:147"]
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-004-stabilize-prompt-budget-line-endings - Make prompt-budget counts line-ending invariant

## Outcome / Why

Prompt-budget estimates remain identical across Git line-ending conversion and supported operating systems, making the documented “stable cross-harness” regression signal trustworthy.

## Success criteria

- [ ] A focused test proves logically identical LF and CRLF prompt content yields the same byte/token estimate.
- [ ] `.agents/prompt_stats.py` computes counts from a documented canonical representation without changing prompt content.
- [ ] Existing prompt-budget regeneration/check behavior remains deterministic and passes on the repository.
- [ ] README accurately describes the normalization and estimate limits.

## Scope

- In: prompt-count normalization, focused regression test, and budget documentation.
- Out: changing model tokenizers, billing claims, or unrelated prompt distillation.

## Context and decisions

- Observed during release-goal combined verification: `--check` passed at 39,983 bytes before branch checkout, then failed after Git line-ending conversion; regeneration produced 40,178 bytes with no logical prompt edit.
- Source: `.agents/prompt_stats.py:33` counts raw working-tree bytes, while README calls the estimate stable across harnesses.
- Project rules require a separate human-blocked TODO for a bug discovered during testing; no fix is authorized yet.

## Approach and next action

**Next action:** After human approval, add an LF/CRLF equivalence test around a small canonical-byte function before changing production calculation.

### Fast feedback

- Baseline/current observable behavior: Same logical prompts produced totals of 39,983 and 40,178 bytes across checkout conversion.
- Hypothesis: Normalize text line endings to LF before UTF-8 byte counting.
- Observation surface (test/harness/API/UI/log/MCP/etc.): Focused Python unit test and `.agents/prompt_stats.py --check`.
- Smallest chunk: Extract canonical byte-count calculation and test LF/CRLF equivalence.
- Probe/action and expected signal: Both encodings return identical byte/token values; current script does not.
- Actual result/evidence: Bug reproduced through the failed check; no fix attempted.
- Wider checks after local proof: Regenerate README and repeat after a Git checkout on Windows.

### Execution constraints

- Mode: `sequential`
- Parallel exception: none
- Resources/shared state: README prompt-budget table and prompt files.

## Relationships

- Parent: none
- Children (required/optional + purpose/status): none
- Dependencies (status/reason): human decision required by test-discovered-bug policy.
- Blocks (impact): none; current table was regenerated for this checkout.

## Blockers

### Open

None.

### Resolved

### B-003 - Authorize prompt-count bug fix
- Status/category/raised/owner: resolved / `decision` / 2026-07-16 / user
- Blocks: resolved
- Question or required action: approve the isolated line-ending normalization fix.
- Why/options/recommendation: approved through the user's instruction to complete all queued work.
- Evidence gathered: totals changed from 39,983 to 40,178 bytes solely across checkout line-ending conversion.
- Continuation: `stop-affected-work`
- Safe work remaining/recheck trigger: goal is actionable.
- Resolution/resolved/resolved by: fix approved / 2026-07-16 / user

## Progress and evidence

Bug captured with source lines and reproduction evidence. User authorized completing all queued work; implementation is ready.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex/R-20260716-1500-root | Created `blocked` | Combined release verification exposed platform-dependent prompt counts; policy forbids fixing a test-discovered bug without human input. |
| 2026-07-16 | user/Codex | Resolved `B-003`; set `ready` | User instructed `$execute-zzzops` to complete all queued work. |
