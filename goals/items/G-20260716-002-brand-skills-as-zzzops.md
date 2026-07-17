---
id: G-20260716-002-brand-skills-as-zzzops
title: Brand all skills clearly as ZzzOps
status: done
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
parent: null
depends_on: []
blocks: []
needs_human: false
tags: [skills, naming, branding, discovery, installer]
external_refs: ["user-request:2026-07-16"]
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-002-brand-skills-as-zzzops - Brand all skills clearly as ZzzOps

## Outcome / Why

Every installed and repository-local skill is unmistakably part of ZzzOps in agent discovery surfaces, commands, documentation, and generated mechanics. Generic `project-goals`, `project-work`, and `Project TODO` naming no longer causes skills to be grouped or understood as “agent-goals”; specifically, the current “Add Project TODO” skill becomes “Add ZzzOps TODO.”

## Success criteria

- [x] Define and apply one concise ZzzOps naming map for every skill identifier, directory, frontmatter name, UI display name, default prompt, and user-facing heading; it includes `Add ZzzOps TODO`. Evidence: new directories/metadata use `add-zzzops-todo`, `install-zzzops`, `migrate-zzzops-todos`, and `suggest-zzzops-work`.
- [x] Installer and Claude Code bootstrap mechanics install and reference only the renamed skills, with no stale generic skill directories created in a fresh target. Evidence: fresh-install probe listed five ZzzOps-named skill directories in both harness layouts.
- [x] All repository prompts, scripts, templates, README examples, cross-skill calls, and generated prompt-budget paths use the new names consistently. Evidence: old-name scan found only the deliberate legacy compatibility tuple.
- [x] A repository-wide search finds no obsolete skill invocation or display-name references except explicitly documented compatibility fixtures. Evidence: focused `rg` scan returned only `LEGACY_SKILLS`.
- [x] A clean install into a temporary repository makes the skills discoverable under clear ZzzOps names in supported harness layouts. Evidence: installer preview/apply succeeded with 46 mechanical files and exact Codex/Claude directory listings.
- [x] The compatibility policy for repositories that already contain the first-release skill names is explicit and verified; stale aliases are intentionally retained and documented. Evidence: update preview reported `Legacy skill directories retained: add-project-todo`; README explains manual removal after verification.
- [x] Prompt budget counts are regenerated and pass `.agents/prompt_stats.py --check`. Evidence: 22 prompts, 39,983 bytes, ~10,006 estimated tokens.
- [x] Reopen the checkout at `C:\dev\zzzops` and verify Codex groups its project-local skills under ZzzOps rather than `agent-goals`. Evidence: user confirmed “the zzzops folder worked” after opening the renamed checkout in Codex.

## Scope

- In: Skill IDs/directories, display metadata, descriptions, headings, prompts, installer inventory/copy logic, Claude Code bootstrap, docs, templates, tests/probes, and installed-copy compatibility behavior.
- Out: Renaming the ZzzOps product again, changing durable goal semantics, or renaming ordinary project concepts where “project” remains accurate and is not skill branding.

## Context and decisions

- User requested the goal on 2026-07-16 because skills are currently grouped under “agent-goals” and generic names obscure their ZzzOps identity.
- Required visible rename: `Add Project TODO` → `Add ZzzOps TODO`.
- Current generic identifiers include `$add-project-todo`, `$install-project-goals`, `$migrate-project-goals`, and `$suggest-project-work`; current ZzzOps identifiers include `$execute-zzzops` and `$analyze-zzzops-usage`.
- Identifier changes affect discoverability, documentation, cross-skill references, installer output, and existing installations, so a single atomic rename map is required before edits.

## Approach and next action

**Next action:** Complete; preserve the verified ZzzOps-named checkout and skill paths.

### Fast feedback

- Baseline/current observable behavior: Repository search shows generic “Project” names and `*-project-*` identifiers alongside ZzzOps-branded skills.
- Hypothesis: Consistent `*-zzzops-*` identifiers and `ZzzOps` display names will cause agent harnesses and humans to recognize one coherent skill family.
- Observation surface (test/harness/API/UI/log/MCP/etc.): Repository search, installer dry run/apply output, installed `.agents/skills` and `.claude/skills` trees, and harness skill discovery lists.
- Smallest chunk: Express the old-to-new naming map as a table and validate that each old identifier/path occurrence is assigned exactly one disposition.
- Probe/action and expected signal: Scan all tracked files and a clean install; no unapproved old skill name remains and each renamed skill is discoverable once.
- Actual result/evidence: Fresh install, legacy-update preview, old-name scan, Python parse, and prompt-budget probes passed. The user reopened `C:\dev\zzzops` and confirmed Codex displayed the expected ZzzOps grouping.
- Wider checks after local proof: Fresh install, update over a first-release install, prompt-budget verification, Python parsing, and README quickstart command validation.

### Execution constraints

- Mode: `sequential`
- Parallel exception: A bounded read-only inventory across prompts, scripts, and documentation is allowed.
- Resources/shared state: Skill discovery paths, installer targets, existing installed repositories, README prompt-budget table, and supported agent harnesses.

## Relationships

- Parent: none
- Children (required/optional + purpose/status): none; create sub-goals only if compatibility migration is materially independent from the atomic repository rename.
- Dependencies (status/reason): none.
- Blocks (impact): none.

## Blockers

### Open

None.

### Resolved

### B-001 - Reopen from a ZzzOps-named checkout
- Status/category/raised/owner: resolved / `human-action` / 2026-07-16 / user
- Blocks: final UI grouping verification only
- Question or required action: after this run, rename or clone the checkout to `C:\dev\zzzops`, reopen it in Codex, and confirm the group label is ZzzOps.
- Why/options/recommendation: Codex groups project-local `.agents/skills` by workspace path; keep the canonical discovery folder and rename the checkout rather than moving skills out of `.agents/skills`.
- Evidence gathered: current workspace and skill source paths are rooted at `C:\dev\agent-goals`; README already instructs cloning to `C:\dev\zzzops`.
- Continuation: `continue-bounded`
- Safe work remaining/recheck trigger: correctly named checkout now exists at `C:\dev\zzzops`; recheck after the user opens it in Codex.
- Resolution/resolved/resolved by: user confirmed “the zzzops folder worked” / 2026-07-16 / user

## Progress and evidence

Repository-side rename and UI discovery are complete. A fresh `dev` checkout at `C:\dev\zzzops` exposes the project-local skills under ZzzOps, as confirmed by the user.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex | Created `new` | User requested clear ZzzOps skill grouping and “Add ZzzOps TODO” naming. |
| 2026-07-16 | Codex/R-20260716-zzzops | Triaged `ready`; difficulty `M` | Full rename surface and observable fresh/update-install probes are defined. |
| 2026-07-16 | Codex/R-20260716-1500-root | Repository rename verified; set `blocked` | Fresh/update installs and scans pass; Codex group header requires reopening a ZzzOps-named checkout. |
| 2026-07-16 | Codex/R-20260716-queued | Created `C:\dev\zzzops` checkout | Removed the filesystem action; user must reopen it once for UI evidence. |
| 2026-07-16 | user/Codex/R-20260716-release-root | Confirmed UI grouping; set `done` | User reported that the ZzzOps-named folder worked, satisfying the final observable criterion and resolving B-001. |
