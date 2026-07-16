---
id: G-20260716-006-protect-main-and-dev
title: Protect main and require validated PRs to dev
status: in_progress
priority: P1
value: high
difficulty: M
confidence: medium
owner: Codex
created: 2026-07-16
updated: 2026-07-16
target_date: null
last_reviewed: 2026-07-16
review_after: null
parent: G-20260716-001-automate-semantic-releases
depends_on: []
blocks: []
needs_human: false
tags: [github, branch-protection, rulesets, ci, pull-requests, release-safety]
external_refs: ["https://github.com/david-rzepa/zzzops", "user-request:2026-07-16"]
claim: {owner: Codex, claimed_at: "2026-07-16T15:30:00-06:00", expires_at: "2026-07-16T19:30:00-06:00"}
---

# G-20260716-006-protect-main-and-dev - Protect main and require validated PRs to dev

## Outcome / Why

GitHub enforces the repository workflow: `main` cannot change through ordinary work, while `dev` changes arrive through pull requests whose required CI validation passes. Any owner bypass is narrow, explicit, and verified rather than weakening protection for agents or collaborators.

## Success criteria

- [x] Inspect repository plan/features and current rules using GitHub CLI/API, then document whether classic branch protection or repository rulesets best express the requested policy. Evidence: repository is private on GitHub Free; protection and rulesets endpoints return 403 requiring Pro or public visibility; both branches report unprotected.
- [ ] `main` rejects every update path except force pushes performed by repository owner `david-rzepa`; ordinary pushes, PR merges, deletions, bots, collaborators, and other bypass paths cannot change it.
- [ ] `dev` requires a pull request and a passing, stable required check before merge; direct pushes and force pushes are rejected.
- [ ] Every PR targeting `dev` runs a deterministic validation job with read-only permissions; it exercises prompt accounting, semantic-release behavior, prompt-budget consistency, and Python syntax.
- [ ] Required-check name `dev-required-tests` is stable, unique, runs on every PR targeting `dev`, and matches the configured or manually documented GitHub rule exactly.
- [ ] Controlled GitHub/API evidence shows the rules encode owner-only force-push access and reject every other `main` update path, without actually force-pushing, deleting branches, or publishing a release.
- [ ] Maintainer documentation records the rules, bypass semantics, recovery path, and any GitHub-plan limitation.

## Scope

- In: GitHub branch protection/rulesets when supported, PR-targeted CI validation, minimal docs, read-only inspection, and reversible repository-setting updates after review.
- Out: Performing a destructive force push, weakening release CI, granting bots broad bypass, changing organization-wide policy, or merging/releasing as part of configuration.

## Context and decisions

- User requested this goal on 2026-07-16: protect `main`, retain an owner-only emergency capability, and require PR plus passing CI for `dev`.
- User clarified that they are repository owner `david-rzepa` and intend owner-only force-push permission on `main`; no PR merge, ordinary push, bot, collaborator, or alternative update path may change `main`.
- Prefer GitHub CLI/API configuration if the repository plan and token authority support it. If protection cannot be configured programmatically, still create and verify the PR test job so the user can manually require that exact check.
- User reaffirmed on 2026-07-16 that PRs must run CI; this is a required behavior independent of whether branch settings can be automated.
- GitHub capability finding: private branch protection/rulesets are unavailable on the current Free plan. Exact owner-force-push-only semantics are not expressible even with rulesets because an owner bypass also permits ordinary pushes/merges. The closest future configuration requires Pro/public visibility and still relies on owner discipline for update mode.

## Approach and next action

**Next action:** Open the published branch as a PR targeting `dev`, observe `dev-required-tests`, and record the result. Then preserve the GitHub-plan/semantic limitation as a blocker with exact manual upgrade configuration guidance.

### Fast feedback

- Baseline/current observable behavior: Release workflow validates pushes to `dev` and publishes from `main`; no PR-targeted required-check job or recorded branch ruleset exists in project state.
- Hypothesis: A read-only `pull_request` validation job plus branch-specific GitHub rules can enforce the documented workflow without granting write permission to PR code.
- Observation surface (test/harness/API/UI/log/MCP/etc.): `gh api` rule/branch endpoints, GitHub Actions PR run/check names, rejected-path API metadata, and repository docs.
- Smallest chunk: Add and locally validate one read-only PR job with a stable job/check name before binding branch rules to it.
- Probe/action and expected signal: A test PR to `dev` reports the required check and cannot merge until it passes; no release job runs and no tag/release is created.
- Actual result/evidence: Local prompt accounting, six release tests, prompt-budget check, and Python compilation pass. GitHub API inspection found both branches unprotected and branch protection/rulesets unavailable for this private Free repository. Live PR evidence remains next.
- Wider checks after local proof: Configure rules, query them back, verify direct-push/force-push/deletion flags and bypass actors, then document recovery.

### Execution constraints

- Mode: `sequential`
- Parallel exception: Bounded read-only inspection of GitHub rules and workflow syntax is allowed.
- Resources/shared state: GitHub repository settings, Actions, required check names, `dev`, `main`, and owner/bot permissions.

## Relationships

- Parent: [G-20260716-001](G-20260716-001-automate-semantic-releases.md)
- Children (required/optional + purpose/status): none
- Dependencies (status/reason): coordinate with sibling `G-20260716-005` so enforced PR targets match documented guidance. GitHub-plan/API capability may limit automatic settings application but does not block the CI job.
- Blocks (impact): Parent release-safety workflow remains convention-based until enforcement is verified.

## Blockers

### Open

None.

### Resolved

### B-004 - Complete fallback and owner-bypass semantics
- Status/category/raised/owner: resolved / `specification` / 2026-07-16 / user
- Blocks: resolved; exact protection and fallback requirements are now known.
- Question or required action: clarify owner capability and the truncated CI fallback.
- Why/options/recommendation: n/a after resolution.
- Evidence gathered: user confirmed they are repository owner; only their force pushes may change `main`. If settings cannot be applied with `gh`, the CI test job must still be created for manual required-check configuration.
- Continuation: `continue-bounded`
- Safe work remaining/recheck trigger: goal can be triaged/executed normally.
- Resolution/resolved/resolved by: owner-only force push; no other `main` update path; CI job always required / 2026-07-16 / user

## Progress and evidence

Implementation checkpoint: `.github/workflows/validate.yml` targets every PR into `dev`, uses `contents: read`, and locally passes all four check categories. The branch is published; next evidence is a live run named `PR validation / dev-required-tests`. Automatic protection cannot be configured on the current private Free repository.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex | Created `new` with `B-004` | User requested protected `main`, PR/CI-gated `dev`, and a CLI-or-CI fallback whose final clause was truncated. |
| 2026-07-16 | user/Codex | Resolved `B-004` | User specified owner-only force pushes as the sole `main` update path and required the CI job even when protection must be configured manually. |
| 2026-07-16 | Codex/R-20260716-queued | Triaged `ready` | Protection semantics, fallback, smallest CI chunk, and observation surfaces are defined. |
| 2026-07-16 | user/Codex | Reaffirmed PR CI requirement | Reconciled as this existing goal; no duplicate goal created. |
