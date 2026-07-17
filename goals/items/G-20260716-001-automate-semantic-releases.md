---
id: G-20260716-001-automate-semantic-releases
title: Automate semantic GitHub releases
status: done
priority: P1
value: high
difficulty: M
confidence: high
owner: Codex
created: 2026-07-16
updated: 2026-07-16
target_date: null
last_reviewed: 2026-07-16
review_after: null
parent: null
depends_on: []
blocks: []
needs_human: false
tags: [ci, release, semantic-versioning, github-actions]
external_refs: ["user-request:2026-07-16"]
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-001-automate-semantic-releases - Automate semantic GitHub releases

## Outcome / Why

ZzzOps derives semantic versions from repository history and publishes reproducible GitHub Releases from `main`, reducing manual release work. Changes are developed on `dev`, where a non-publishing dry run exposes the version and release output before merge.

## Success criteria

- [x] A CI workflow triggered by pushes to `main` calculates the next semantic version from an explicitly documented commit/tag convention. Evidence: `.github/workflows/release.yml`, local real-history plan `none -> v1.0.0 (major)`, and README release convention.
- [x] A qualifying `main` push creates the expected Git tag and GitHub Release with generated release notes; a non-qualifying rerun does not publish another release. Evidence: the breaking root push published `v1.0.0`; a rerun after the tag reported no releasable commits and release/tag counts remained one.
- [x] A workflow on `dev` runs the same release/version calculation in dry-run mode and cannot create tags, GitHub Releases, or other release-side effects. Evidence: runs `29535036331` and `29535149186` passed all dry-run steps, skipped `release`, and left remote releases/tags empty.
- [x] Repository documentation explains the release convention, branch behavior, required permissions/secrets, and how to diagnose a failed release. Evidence: README “Releases” section.
- [x] Tests or controlled workflow evidence demonstrate the first-release, patch/minor/major, no-release, rerun/idempotency, and dry-run paths. Evidence: six local tests include a temporary real Git history; two live `dev` runs passed.

## Scope

- In: CI configuration, semantic version calculation, GitHub tag/release publication on `main`, non-publishing validation on `dev`, minimum supporting documentation and tests.
- Out: publishing packages or binaries to registries, changing the ZzzOps goal format, and selecting a release tool without repository investigation.

## Context and decisions

- User requested this goal on 2026-07-16 after the first commit was pushed to `main`.
- Implementation work must occur on `dev`; production release publication is triggered by pushes to `main`.
- The `dev` workflow must be a true dry run with permissions configured to prevent publication, not merely a convention agents are expected to follow.
- Release tooling decision: use a dependency-free Python planner shared by both workflow paths. Breaking commits bump major; `feat` bumps minor; `fix`/`perf` bump patch; other commit types do not release. With no prior tag, the same rules apply from `0.0.0`.

## Approach and next action

**Next action:** Complete; develop future Conventional Commits through `dev` PRs and let intentional `main` release updates run the shared publisher.

### Fast feedback

- Baseline/current observable behavior: No release workflow or automated GitHub Release process is recorded.
- Hypothesis: One shared release configuration can drive a read-only `dev` preview and an authoritative `main` publication path.
- Observation surface (test/harness/API/UI/log/MCP/etc.): GitHub Actions logs, calculated next version/release notes, repository tags, and GitHub Releases.
- Smallest chunk: Calculate and print the next version/release notes from synthetic Conventional Commit histories without publishing.
- Probe/action and expected signal: Run the selected engine in dry-run mode against patch, minor, major, and no-release fixtures; each reports the expected result and produces no remote mutation.
- Actual result/evidence: Six unit/integration tests, two live `dev` dry runs, the final exact-tree planner/PR checks, the production `v1.0.0` publication, and a no-duplicate rerun all passed.
- Wider checks after local proof: Exercise `dev`, inspect token/permission boundaries, merge a controlled qualifying change to `main`, verify tag/release contents, and verify a rerun is idempotent.

### Execution constraints

- Mode: `sequential`
- Parallel exception: Read-only comparison of release tools is allowed if bounded.
- Resources/shared state: Git history, tags, GitHub Actions, repository release permissions, `dev`, and `main`.

## Relationships

- Parent: none
- Children (required/optional + purpose/status): [G-20260716-003](G-20260716-003-document-dev-branch-workflow.md) (required; initial `dev`-first Git/release guidance; `done`); [G-20260716-005](G-20260716-005-document-pr-workflow.md) (required; document `dev`-targeted PR and atomic commit policy; `done`); [G-20260716-006](G-20260716-006-protect-main-and-dev.md) (required; PR CI plus protection/fallback; `done`); [G-20260716-007](G-20260716-007-squash-v1-main-history.md) (required; published audited single-root `v1.0.0`; `done`).
- Dependencies (status/reason): none recorded; repository settings or branch creation may become a human-action blocker during investigation.
- Blocks (impact): none recorded.

## Blockers

### Open

None.

### Resolved

### B-002 - Authorize the first production release
- Status/category/raised/owner: resolved / `access-approval` / 2026-07-16 / user
- Blocks: resolved; release remains dependency-gated.
- Question or required action: authorize the first `main` release.
- Why/options/recommendation: user explicitly requested terminal goal `G-007` to owner-force-push a single-root `main` and publish `v1.0.0`.
- Evidence gathered: prior dry runs passed; user specified exact final release/history outcome.
- Continuation: `stop-affected-work`
- Safe work remaining/recheck trigger: execute `G-007` after `G-002` completes.
- Resolution/resolved/resolved by: authorized through `G-007` request / 2026-07-16 / user

## Progress and evidence

Shared planner, tests, workflows, and docs are verified. Live dry runs did not mutate releases; terminal child `G-007` published and audited the single-root `v1.0.0`, including no-release rerun behavior, so the parent is done.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex | Created `new` | User requested semantic GitHub releases from `main`, development on `dev`, and a dry-run workflow on `dev`. |
| 2026-07-16 | Codex | Added required child `G-20260716-003` | User requested explicit root `AGENTS.md` guidance for the `dev`-first/release workflow. |
| 2026-07-16 | Codex/R-20260716-zzzops | Triaged `ready`; difficulty `M` | Scope, baseline, branch targets, probes, and dependencies are concrete. |
| 2026-07-16 | Codex/R-20260716-1500-root | Required child `G-20260716-003` completed | Root policy is documented; this parent must now implement its stated `main` behavior. |
| 2026-07-16 | Codex/R-20260716-1500-root | Local implementation checkpoint | Six tests and real-history dry run passed; ready for live `dev` verification. |
| 2026-07-16 | Codex/R-20260716-1500-root | `dev` verified; set `blocked` | Two live dry runs passed with no remote mutation; explicit approval is required before the first `main` release. |
| 2026-07-16 | Codex | Added required children `G-20260716-005` and `G-20260716-006` | User expanded the release-safety workflow with PR/commit guidance and GitHub enforcement. |
| 2026-07-16 | Codex/R-20260716-queued | Required child `G-20260716-005` completed | PR/commit policy is now explicit in root instructions. |
| 2026-07-16 | Codex/R-20260716-queued | Required child `G-20260716-006` completed | Live PR CI passed; unavailable protection is covered by the user's documented manual fallback. |
| 2026-07-16 | user/Codex | Resolved `B-002`; added required child `G-007` | User explicitly authorized the terminal single-root `v1.0.0` release operation. |
| 2026-07-16 | Codex/R-20260716-release-root | Required child `G-007` completed; set `done` | Production `v1.0.0`, generated notes, no-duplicate rerun, and reconciled `dev` were verified. |
