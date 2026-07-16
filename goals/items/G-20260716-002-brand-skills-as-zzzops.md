---
id: G-20260716-002-brand-skills-as-zzzops
title: Brand all skills clearly as ZzzOps
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

- [ ] Define and apply one concise ZzzOps naming map for every skill identifier, directory, frontmatter name, UI display name, default prompt, and user-facing heading; it includes `Add ZzzOps TODO`.
- [ ] Installer and Claude Code bootstrap mechanics install and reference only the renamed skills, with no stale generic skill directories created in a fresh target.
- [ ] All repository prompts, scripts, templates, README examples, cross-skill calls, and generated prompt-budget paths use the new names consistently.
- [ ] A repository-wide search finds no obsolete skill invocation or display-name references except any explicitly documented compatibility fixture.
- [ ] A clean install into a temporary repository makes the skills discoverable under clear ZzzOps names in supported harness layouts.
- [ ] The compatibility policy for repositories that already contain the first-release skill names is explicit and verified; stale aliases are either safely removed/migrated or intentionally retained and documented.
- [ ] Prompt budget counts are regenerated and pass `.agents/prompt_stats.py --check`.

## Scope

- In: Skill IDs/directories, display metadata, descriptions, headings, prompts, installer inventory/copy logic, Claude Code bootstrap, docs, templates, tests/probes, and installed-copy compatibility behavior.
- Out: Renaming the ZzzOps product again, changing durable goal semantics, or renaming ordinary project concepts where “project” remains accurate and is not skill branding.

## Context and decisions

- User requested the goal on 2026-07-16 because skills are currently grouped under “agent-goals” and generic names obscure their ZzzOps identity.
- Required visible rename: `Add Project TODO` → `Add ZzzOps TODO`.
- Current generic identifiers include `$add-project-todo`, `$install-project-goals`, `$migrate-project-goals`, and `$suggest-project-work`; current ZzzOps identifiers include `$execute-zzzops` and `$analyze-zzzops-usage`.
- Identifier changes affect discoverability, documentation, cross-skill references, installer output, and existing installations, so a single atomic rename map is required before edits.

## Approach and next action

**Next action:** Inventory every skill-facing identifier and path, propose the shortest consistent ZzzOps rename map plus first-release compatibility behavior, and stop after proving the mapping covers every repository reference.

### Fast feedback

- Baseline/current observable behavior: Repository search shows generic “Project” names and `*-project-*` identifiers alongside ZzzOps-branded skills.
- Hypothesis: Consistent `*-zzzops-*` identifiers and `ZzzOps` display names will cause agent harnesses and humans to recognize one coherent skill family.
- Observation surface (test/harness/API/UI/log/MCP/etc.): Repository search, installer dry run/apply output, installed `.agents/skills` and `.claude/skills` trees, and harness skill discovery lists.
- Smallest chunk: Express the old-to-new naming map as a table and validate that each old identifier/path occurrence is assigned exactly one disposition.
- Probe/action and expected signal: Scan all tracked files and a clean install; no unapproved old skill name remains and each renamed skill is discoverable once.
- Actual result/evidence: Initial search recorded in this goal; implementation not run.
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

None. Exact identifiers beyond the required `Add ZzzOps TODO` display name remain a design choice to settle during investigation.

### Resolved

None.

## Progress and evidence

Triaged as actionable. `rg` identified affected references in `README.md`, `AGENTS.md`, `.agents/skills/`, `.claude/skills/`, installer code, templates, and prompt accounting.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex | Created `new` | User requested clear ZzzOps skill grouping and “Add ZzzOps TODO” naming. |
| 2026-07-16 | Codex/R-20260716-zzzops | Triaged `ready`; difficulty `M` | Full rename surface and observable fresh/update-install probes are defined. |
