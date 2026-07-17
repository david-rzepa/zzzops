---
id: G-20260716-008-require-project-value-interview
title: Require a project-value interview before non-install workflows
status: new
priority: P1
value: high
difficulty: M
confidence: low
owner: unassigned
created: 2026-07-16
updated: 2026-07-16
target_date: null
last_reviewed: 2026-07-16
review_after: null
parent: null
depends_on: []
blocks: [G-20260716-009-add-user-health-module]
needs_human: false
tags: [project-charter, interviews, workflows, prioritization, value]
external_refs: ["user-request:2026-07-16"]
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-008-require-project-value-interview - Require a project-value interview before non-install workflows

## Outcome / Why

Every ZzzOps workflow except installation checks whether `goals/PROJECT.md` adequately defines project value before performing its ordinary task. When that charter is missing or incomplete, the workflow immediately interviews the user, persists the answers, and only then resumes, so goal creation, migration, execution, suggestions, and usage analysis are grounded in the project's actual outcomes and success measures.

Provisional value is high because this gate prevents every downstream prioritization/value decision from operating on placeholders. Confidence remains low until this repository's own incomplete charter supplies project-specific KPIs and acceptance criteria.

## Success criteria

- [ ] Define one concise, reusable completeness rule for `goals/PROJECT.md`, covering missing/unreadable files, explicit incomplete status, placeholder/unknown value fields, and absent usable success/acceptance signals without requiring needless repeated interviews.
- [ ] `add-zzzops-todo`, `execute-zzzops`, `migrate-zzzops-todos`, `suggest-zzzops-work`, and `analyze-zzzops-usage` all check that rule before their ordinary workflow and immediately interview the user when it fails.
- [ ] The interview collects only the missing consequential value context, persists it in `goals/PROJECT.md` with history, and resumes the invoked workflow; declined/unavailable answers produce an explicit categorized blocker rather than invented values or silent continuation.
- [ ] `install-zzzops` remains exempt: it may initialize the blank project template but does not force a project interview during mechanics installation.
- [ ] Installed Codex and Claude Code skill surfaces, workflow references, templates, and concise user/maintainer documentation express the same behavior without adding redundant prompt text.
- [ ] Automated probes cover complete, missing, partially complete, declined/unavailable, resume, no-repeat, and installer-exemption paths; a clean install exposes the updated non-install workflow behavior.
- [ ] Prompt-budget counts are regenerated and `.agents/prompt_stats.py --check` passes.

## Scope

- In: Shared charter-completeness semantics; all non-install skill entry points; compact interview, persistence, blocker, and resume behavior; installed Codex/Claude surfaces; focused tests and documentation.
- Out: Interviewing during installation, inventing project KPIs, redesigning the project charter wholesale, executing unrelated queued work, or modifying target `AGENTS.md`/`CLAUDE.md`.

## Context and decisions

- The project-value source is currently `goals/PROJECT.md`; `.zzzops/rules/GOAL_SYSTEM.md:9` already says it defines success/value and unknowns must be asked rather than invented.
- The base repository's own `goals/PROJECT.md:3-34` is explicitly incomplete and contains unknown outcome, beneficiary, KPI, acceptance, and constraint fields, demonstrating the required baseline case.
- Current entry points read or use the charter inconsistently: `.agents/skills/add-zzzops-todo/SKILL.md:8`, `.agents/skills/execute-zzzops/SKILL.md:8`, `.agents/skills/analyze-zzzops-usage/SKILL.md:8`, `.agents/skills/migrate-zzzops-todos/SKILL.md:13`, and `.agents/skills/suggest-zzzops-work/SKILL.md:13`.
- The user explicitly exempted installation and required an interview in every other workflow when the value-defining project file is not set.

## Approach and next action

**Next action:** Triage every workflow entry point and define the smallest shared completeness/interview contract; stop when each required workflow and test path has exactly one unambiguous disposition.

### Fast feedback

- Baseline/current observable behavior: `goals/PROJECT.md` is incomplete, yet several non-install skills can proceed with only generic instructions to preserve unknowns or relate work to the charter.
- Hypothesis: A short shared gate referenced by each non-install skill will force value context to be established once while avoiding duplicated prompt cost and repeated interviews.
- Observation surface (test/harness/API/UI/log/MCP/etc.): Static skill/reference scan, temporary complete/incomplete project fixtures, captured interview/persistence behavior, installer preview/apply, and prompt-budget output.
- Smallest chunk: Specify the completeness predicate and an interview/resume state table for the five non-install workflows plus the installer exemption.
- Probe/action and expected signal: Run each workflow against an incomplete fixture; it asks before ordinary work, updates only missing charter context, and resumes once without re-asking on the complete fixture.
- Actual result/evidence: Not run; goal captured from the user's requirement and repository baseline.
- Wider checks after local proof: Clean Codex/Claude install, declined-answer blocker behavior, all workflow-specific regressions, prompt accounting, and documentation scan.

### Execution constraints

- Mode: `sequential`
- Parallel exception: A bounded read-only inventory of distinct workflow entry points is allowed during triage.
- Resources/shared state: Shared project charter, installed prompt surfaces, workflow tests, and README prompt-budget table.

## Relationships

- Parent: none
- Children (required/optional + purpose/status): none; decompose only if shared gate implementation and workflow integration become independently verifiable.
- Dependencies (status/reason): none identified during capture.
- Blocks (impact): [G-20260716-009](G-20260716-009-add-user-health-module.md) needs the project-value interview before selecting health-policy defaults and confidently assigning value.

## Blockers

### Open

None. Preserve charter unknowns during capture; triage should use the new interview requirement to complete this repository's charter before assigning confident value.

### Resolved

None.

## Progress and evidence

Captured as a new root goal. Repository search found no existing goal covering a mandatory pre-workflow project-value interview; existing rules only say to preserve/ask about unknowns and individual workflows apply that guidance inconsistently.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | user/Codex | Created `new` | User required all workflows except installation to interview when the project-value charter is not set. |
| 2026-07-16 | Codex | Added dependent `G-009` backlink | The health module must establish project value and interview semantics before choosing policy defaults. |
