---
id: G-20260716-001-automate-semantic-releases
title: Automate semantic GitHub releases
status: ready
priority: P1
value: high
difficulty: M
confidence: medium
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
tags: [ci, release, semantic-versioning, github-actions]
external_refs: ["user-request:2026-07-16"]
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-001-automate-semantic-releases - Automate semantic GitHub releases

## Outcome / Why

ZzzOps derives semantic versions from repository history and publishes reproducible GitHub Releases from `main`, reducing manual release work. Changes are developed on `dev`, where a non-publishing dry run exposes the version and release output before merge.

## Success criteria

- [ ] A CI workflow triggered by pushes to `main` calculates the next semantic version from an explicitly documented commit/tag convention.
- [ ] A qualifying `main` push creates the expected Git tag and GitHub Release with generated release notes; a non-qualifying push does not publish a release.
- [ ] A workflow on `dev` runs the same release/version calculation in dry-run mode and cannot create tags, GitHub Releases, or other release-side effects.
- [ ] Repository documentation explains the release convention, branch behavior, required permissions/secrets, and how to diagnose a failed release.
- [ ] Tests or controlled workflow evidence demonstrate the first-release, patch/minor/major, no-release, rerun/idempotency, and dry-run paths.

## Scope

- In: CI configuration, semantic version calculation, GitHub tag/release publication on `main`, non-publishing validation on `dev`, minimum supporting documentation and tests.
- Out: publishing packages or binaries to registries, changing the ZzzOps goal format, and selecting a release tool without repository investigation.

## Context and decisions

- User requested this goal on 2026-07-16 after the first commit was pushed to `main`.
- Implementation work must occur on `dev`; production release publication is triggered by pushes to `main`.
- The `dev` workflow must be a true dry run with permissions configured to prevent publication, not merely a convention agents are expected to follow.
- Release tooling and the exact mapping from Conventional Commits to versions remain implementation decisions to validate against this repository's minimal Python/Markdown shape.

## Approach and next action

**Next action:** Inspect current branches, tags, repository permissions, and available CI/runtime surfaces; compare the smallest viable semantic-release approaches and stop after recording a recommended design plus an observable local or `dev` dry-run probe.

### Fast feedback

- Baseline/current observable behavior: No release workflow or automated GitHub Release process is recorded.
- Hypothesis: One shared release configuration can drive a read-only `dev` preview and an authoritative `main` publication path.
- Observation surface (test/harness/API/UI/log/MCP/etc.): GitHub Actions logs, calculated next version/release notes, repository tags, and GitHub Releases.
- Smallest chunk: Calculate and print the next version/release notes from synthetic Conventional Commit histories without publishing.
- Probe/action and expected signal: Run the selected engine in dry-run mode against patch, minor, major, and no-release fixtures; each reports the expected result and produces no remote mutation.
- Actual result/evidence: Not run.
- Wider checks after local proof: Exercise `dev`, inspect token/permission boundaries, merge a controlled qualifying change to `main`, verify tag/release contents, and verify a rerun is idempotent.

### Execution constraints

- Mode: `sequential`
- Parallel exception: Read-only comparison of release tools is allowed if bounded.
- Resources/shared state: Git history, tags, GitHub Actions, repository release permissions, `dev`, and `main`.

## Relationships

- Parent: none
- Children (required/optional + purpose/status): [G-20260716-003](G-20260716-003-document-dev-branch-workflow.md) (required; document the verified `dev`-first Git and `main` release workflow; `new`). Create further implementation sub-goals after investigation if the workflow and test harness are independently verifiable.
- Dependencies (status/reason): none recorded; repository settings or branch creation may become a human-action blocker during investigation.
- Blocks (impact): none recorded.

## Blockers

### Open

None. Preserve tool choice and permission details as unknowns until investigated.

### Resolved

None.

## Progress and evidence

Triaged as an actionable medium implementation goal. Baseline: no `.github` workflow files or tags exist; `dev` now exists and the work branch was created from it.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex | Created `new` | User requested semantic GitHub releases from `main`, development on `dev`, and a dry-run workflow on `dev`. |
| 2026-07-16 | Codex | Added required child `G-20260716-003` | User requested explicit root `AGENTS.md` guidance for the `dev`-first/release workflow. |
| 2026-07-16 | Codex/R-20260716-zzzops | Triaged `ready`; difficulty `M` | Scope, baseline, branch targets, probes, and dependencies are concrete. |
