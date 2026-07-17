---
id: G-20260716-008-require-project-value-interview
title: Add agent-driven deterministic project initialization and goal backends
status: triaged
priority: P1
value: high
difficulty: L
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
needs_human: true
tags: [initialization, project-charter, github-issues, local-files, workflows, git]
external_refs: ["user-request:2026-07-16"]
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-008-require-project-value-interview - Add agent-driven deterministic project initialization and goal backends

## Outcome / Why

After mechanical installation, an agent-driven initialization workflow initializes the project once. The agent inspects repository evidence, proposes the value charter and backend configuration, and interviews the user only for consequential unknowns; deterministic commands in the existing ZzzOps CLI inspect capabilities, validate the confirmed plan, and atomically write initialized state. GitHub Issues is the recommended/default backend when a usable GitHub repository is available; local goal files remain the supported fallback. Every non-install workflow starts this initialization automatically before ordinary work when required.

Goal capture itself never creates a Git branch, commit, push, or pull request. Goal execution defaults to the current branch, checkpoints pending local goal state before substantive work, and follows repository-specific Git/PR rules only when execution begins. This keeps the complete backlog easy to evaluate while respecting projects that mandate PRs for implementation.

Provisional value is high because this establishes one project-wide source of truth and removes repeated agent-led setup, split backlogs, and per-goal PR friction. Confidence remains low until this repository's own charter is initialized and GitHub/Claude/Codex capability probes validate the design.

## Success criteria

- [ ] Add an agent-driven, idempotent, resumable initialization workflow backed by deterministic `.agents/zzzops.py` inspect/validate/apply commands and a machine-readable plan; there is no user-driven initialization wizard or blank form to complete manually.
- [ ] The CLI inspection step reports current schema/state, repository evidence locations, missing charter fields, Git/GitHub capabilities, and backend constraints without making semantic project decisions or external writes.
- [ ] The agent uses repository code/docs/config/history plus CLI inspection evidence to propose outcome, beneficiaries, value rationale, KPIs/evidence/cadence, acceptance criteria, constraints/non-goals/tradeoffs, and canonical goal backend. It identifies proposals versus observed facts and interviews the user only for consequential unknowns/confirmation.
- [ ] The deterministic apply step accepts only a complete confirmed plan, validates it, detects stale/concurrent state, and writes shared project initialization atomically; rerunning inspection after success reports complete state and causes no changes.
- [ ] GitHub Issues is presented first and recommended when a GitHub remote plus authenticated issue access are verified; local files are an explicit supported fallback when GitHub is unavailable or unwanted. Exactly one backend is authoritative—no silent failover, implicit dual-write, or split-brain state.
- [ ] The backend selection and initialization/schema version are shared project state, not ignored per-user preferences. Personal operational preferences remain in git-ignored `.zzzops/PREFERENCES.json`.
- [ ] Successful initialization does not open or drive personal preferences. At the end, the agent clearly tells the user that the existing preferences CLI is available, gives the exact command, and briefly states that defaults remain active until they choose to edit them.
- [ ] Every non-install workflow runs one shared initialization preflight before ordinary work. If state is absent, partial, invalid, or from an unsupported schema, the agent automatically enters the initialization workflow, runs the deterministic inspection itself, and conducts only the evidence-backed confirmation interview; it does not merely redirect the user to a CLI command or invent values.
- [ ] `install-zzzops` remains mechanical and exempt: it installs the initialization primitives/templates but neither runs initialization nor asks project questions.
- [ ] The GitHub backend defines deterministic issue labels/body sections and update semantics for goal identity, lifecycle, value/priority/difficulty, parent/dependencies, blockers/resolutions, claims, evidence, next action, and append-only history; reads derive a portfolio without requiring committed goal files.
- [ ] Agents drive the selected backend directly through native capabilities—`gh issue`/`gh api` for GitHub and ordinary file tools for local goals. The CLI is limited to initialization, capability/schema validation, rendering/parsing managed structures, and narrow invariant helpers; it does not become a universal backend-switching CRUD abstraction.
- [ ] The local backend preserves the existing `goals/items/` plus derived `goals/INDEX.md` semantics. Switching backends or importing existing goals is an explicit, reviewed migration—not an automatic fallback.
- [ ] `$add-zzzops-todo` never branches, commits, pushes, or opens a PR. With GitHub selected it creates/updates the canonical issue; with local selected it edits goal/index/backlink files and leaves them uncommitted.
- [ ] `$execute-zzzops` defaults to the current branch. Before substantive work it commits only pending ZzzOps goal-state changes when the local backend requires a checkpoint, never absorbs unrelated user changes, never creates an empty goal commit for GitHub Issues, and obeys repository instructions for any required execution branch/PR.
- [ ] GitHub-backed execution updates/claims the issue and links implementation commits/PRs without manufacturing a Git commit solely to represent issue state.
- [ ] Installed Codex and Claude Code surfaces, initialization/migration flows, templates, CLI help, README quickstart, and maintainer docs express the same concise contract.
- [ ] Automated probes cover fresh/partial/complete/rerun initialization, inspect/plan/apply boundaries, evidence/proposal attribution, unresolved/declined answers, stale plans, invalid input, atomic interruption, GitHub success/auth/access failure, explicit local fallback, backend mismatch/switch refusal, automatic preflight initialization, final preferences-CLI notice, no-autocommit capture, current-branch execution, scoped checkpoint commits, unrelated dirty files, and repository-required branch/PR behavior.
- [ ] Clean install/update probes and existing workflow tests pass; prompt-budget counts are regenerated and `.agents/prompt_stats.py --check` passes.

## Scope

- In: Agent-driven initialization; deterministic CLI inspect/validate/apply primitives; project charter completion; shared initialized/config state; GitHub Issues and local-file goal backends; non-install preflight; capture-versus-execution Git semantics; final preferences-CLI notice; installed prompts/templates; deterministic tests and concise docs.
- Out: A user-driven initialization wizard, universal goal CRUD/backend wrapper, making the user fill a blank charter, automatically editing personal preferences, running initialization during install, silently mirroring both backends, treating local files as an automatic outage queue, autocommitting during capture, weakening project-specific Git policy, modifying target `AGENTS.md`/`CLAUDE.md`, or synchronizing arbitrary GitHub project boards.

## Context and decisions

- The user replaced the earlier wizard concept with agent-driven initialization only. The agent should do repository analysis and invoke deterministic CLI primitives; the user only reviews consequential proposals/unknowns.
- GitHub Issues is GitHub-first and preferred; local files are the explicit backup/fallback option. “Backup” currently means an alternative canonical backend, not an automatically synchronized mirror/export; a true backup export requires a separate explicit design decision.
- The user requires goal capture never to auto-commit. Branches, commits, pushes, and PRs belong to execution only, governed by repository instructions; otherwise execution stays on the current branch.
- The user does not want initialization to drive preference setup. After initialization, the agent should only advertise the reusable preferences CLI and its exact command; ignored personal settings remain separate and optional.
- The base repository's root `AGENTS.md` mandates branches/PRs for ordinary work, which caused per-goal PR friction here. Installed targets do not inherit that file, so the portable skill must distinguish capture from execution rather than impose this repository's policy globally.
- Existing initialization inputs are fragmented: `goals/PROJECT.md` is incomplete, while `.agents/zzzops.py` currently edits only ignored refill/parallelization preferences. The CLI should supply deterministic machine-facing primitives, while the agent owns semantic analysis and user interaction.
- Agents are capable of composing backend-specific operations themselves; GitHub CLI is already the GitHub transport shim. ZzzOps should standardize the managed goal schema and safety invariants without reimplementing every possible issue/file action.
- GitHub capability must be observed rather than assumed: inspect remotes, repository identity, authentication, issue permission, and API responses. Never expose credentials or store tokens.

## Approach and next action

**Next action:** Execute `G-010`; meanwhile resolve `B-001` from the user's charter confirmation, then continue through `G-011` and `G-012`.

### Fast feedback

- Baseline/current observable behavior: Installation creates an incomplete charter; workflows interpret it independently; goals are local Markdown; the CLI edits only personal preferences; root Git policy caused one branch/PR per captured goal.
- Hypothesis: Agent analysis plus deterministic inspect/plan/apply boundaries and a GitHub-first backend can eliminate blank-form setup and capture-time Git friction while preserving validated state and repository-controlled execution.
- Observation surface (test/harness/API/UI/log/MCP/etc.): Machine-readable CLI fixtures, agent initialization transcripts with evidence attribution, temporary repositories, mocked/isolated GitHub CLI responses, issue-body round trips, Git status/refs, workflow preflight transcripts, and installer probes.
- Smallest chunk: Specify the initialized-state/plan schemas, agent-versus-CLI responsibility boundary, backend capability decision table, and capture/execution Git state table without changing a real repository or GitHub issue.
- Probe/action and expected signal: Run fixtures for GitHub-ready, GitHub-unavailable, explicit-local, partial-init, proposed/confirmed/unresolved fields, stale apply, rerun, capture, and execution; each yields one deterministic next action with no unintended Git/external mutation.
- Actual result/evidence: Goal updated from user decisions; implementation probes have not run.
- Wider checks after local proof: Real disposable GitHub repository/issue probe when authorized, Codex/Claude installed surfaces, dirty-worktree safety, backend migration refusal, full installer/workflow regressions, and prompt accounting.

### Execution constraints

- Mode: `sequential`
- Parallel exception: Bounded read-only GitHub/Claude/Codex capability research and independent state-machine test proposals may run during decomposition.
- Resources/shared state: CLI, project charter/config, GitHub repository/issues/labels, local goal files/index, Git working tree/branches, installed prompts/templates, and prompt budget.

## Relationships

- Parent: none
- Children (required/optional + purpose/status): [G-010](G-20260716-010-initialization-state-cli.md) required/ready—state and deterministic CLI; [G-011](G-20260716-011-goal-backends-workflow-routing.md) required/triaged—backend contract and workflow routing; [G-012](G-20260716-012-initialization-install-docs-regression.md) required/triaged—installer/docs/regression proof.
- Dependencies (status/reason): none identified.
- Blocks (impact): [G-20260716-009](G-20260716-009-add-user-health-module.md) needs deterministic project initialization and value/backend configuration before selecting health-policy defaults.

## Blockers

### Open

### B-001 - Confirm project success charter
- Status/category/raised/owner: open / `specification` / 2026-07-16 / user
- Blocks: final charter values and parent completion; not deterministic CLI/backend mechanics.
- Question or required action: Confirm or correct the proposed outcome and KPI targets presented in the active execution interview.
- Why/options/recommendation: Recommend zero lost/duplicate canonical goals, initialization under 10 minutes, at least 80% autonomous transitions, management overhead under 25%, with safety/correctness/privacy/user authority first.
- Evidence gathered: README, goal history, and the user's repeated emphasis on autonomous durable work and token efficiency.
- Continuation: `continue-bounded`
- Safe work remaining/recheck trigger: Implement reversible schema, CLI, backend, and tests; recheck on user reply before final charter apply/completion.
- Resolution/resolved/resolved by: pending

### Resolved

None.

## Progress and evidence

Updated in place from a narrower project-value interview goal. The user selected agent-driven initialization through deterministic CLI primitives, agent-driven backends, GitHub Issues first, local files as fallback, no Git automation during capture, current-branch execution by default, and repository-guided commits/branches/PRs only when execution begins.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | user/Codex | Created `new` | User required all workflows except installation to establish project value before ordinary work. |
| 2026-07-16 | Codex | Added dependent `G-009` backlink | The health module needs initialized project value before choosing policy defaults. |
| 2026-07-16 | user/Codex | Reframed as deterministic initialization/backends | User chose GitHub Issues first, local files as fallback, CLI-owned initialization, capture without Git automation, and current-branch execution subject to repository rules. |
| 2026-07-16 | user/Codex | Replaced wizard with agent-driven initialization | Agent performs analysis and interviews through deterministic CLI primitives; completion only advertises the preferences CLI. |
| 2026-07-16 | user/Codex | Chose agent-driven backend operations | Native GitHub/file tools perform goal actions; CLI scope stays narrow and deterministic. |
| 2026-07-16 | Codex/R-20260716-execute-root | Triaged and decomposed | Three required children isolate deterministic state, backend/workflow semantics, and installation/regression proof. |
| 2026-07-16 | Codex/R-20260716-execute-root | Raised `B-001` | Project charter targets require user confirmation; bounded implementation can continue. |
