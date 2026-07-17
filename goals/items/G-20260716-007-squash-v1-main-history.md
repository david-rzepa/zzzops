---
id: G-20260716-007-squash-v1-main-history
title: Publish v1.0.0 as the single main root commit
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
parent: G-20260716-001-automate-semantic-releases
depends_on: [G-20260716-002-brand-skills-as-zzzops, G-20260716-006-protect-main-and-dev]
blocks: []
needs_human: false
tags: [git, history-rewrite, release, v1, main]
external_refs: ["https://github.com/david-rzepa/zzzops", "user-request:2026-07-16"]
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-007-squash-v1-main-history - Publish v1.0.0 as the single main root commit

## Outcome / Why

After every earlier queued goal is complete, `main` contains exactly one root commit representing the finished first release, and tag/GitHub Release `v1.0.0` point to that commit. Development history remains reviewable on `dev`, while the public release history starts cleanly.

## Success criteria

- [x] Every prerequisite/peer goal queued before this terminal child is `done` with observed evidence and no blocker remains; parent `G-001` closes from this child's evidence in the same final state. Evidence: goal-file/index audit found `G-002` through `G-006` done and an empty human queue before release.
- [x] Final local tests, prompt-budget check, installer smoke test, PR CI, release dry run, and repository diff audit pass against the exact tree published. Evidence: the exact tree passed both Python suites, prompt-budget/compile checks, a 46-file clean/install/idempotency smoke probe, the final PR's `dev-required-tests`, and a `none -> v1.0.0 (major)` planner probe.
- [x] A recoverable local bundle of pre-rewrite refs is created and verified before changing remote history. Evidence: `%TEMP%\zzzops-pre-v1-929ccbe.bundle` passed `git bundle verify` and includes pre-rewrite `main`, `dev`, and the audited release branch.
- [x] A new root commit with a breaking Conventional Commit message contains the exact audited release tree and complete durable goal state. Evidence: `git commit-tree` created `feat!: release ZzzOps v1.0.0`; parent count is zero and its tree equals the CI-tested branch tree.
- [x] Owner force-pushes `main` with an explicit lease against the previously observed remote SHA; no merge, ordinary push, or unbounded force is used. Evidence: the only update used `--force-with-lease=main:929ccbe4159314aea17885eef23ba057ebf96d1f` and GitHub accepted it.
- [x] Remote `main` contains exactly one commit with no parent, and its tree matches the audited source tree. Evidence: fresh fetch/rev-list/cat-file/tree-diff probes verify the remote ref and release branch have one identical tree.
- [x] Tag `v1.0.0` and the published GitHub Release both point to that single root commit; release notes and rerun/idempotency behavior are verified. Evidence: remote refs and `gh release view v1.0.0` agree; rerunning the release workflow reports no releasable commits and creates no duplicate tag/release.
- [x] `dev` remains the ongoing integration branch and is reconciled to the released tree without losing reviewable development history or reopening completed goals. Evidence: the final PR preserves the reviewed commits, links the released root into `dev` ancestry, and leaves `git diff origin/main origin/dev` empty.

## Scope

- In: Final completion audit, local recovery bundle, orphan/squash root commit, leased owner force-push to `main`, `v1.0.0` verification, and post-release `dev` reconciliation.
- Out: Rewriting before dependencies finish, deleting recovery data before verification, rewriting unrelated repositories, or keeping multiple commits on released `main`.

## Context and decisions

- User explicitly requested this terminal goal on 2026-07-16 and authorized squashing all work into a single `main` commit.
- This required child is the operation that completes parent `G-001`; it is deliberately behind every other previously queued item and must not execute while `G-002` or `G-006` is incomplete.
- The root commit must trigger semantic release as `v1.0.0`; use a real breaking Conventional Commit marker rather than manually falsifying the calculated version.
- History rewriting is destructive externally, so use `--force-with-lease` against a freshly observed `origin/main` SHA and retain a verified local recovery artifact through final audit.
- Durable state finalization must be designed before the rewrite so completing this goal does not require a second commit on `main` or move `v1.0.0` away from the sole root commit.

## Approach and next action

**Next action:** Complete; retain the verified recovery bundle until the owner no longer needs rollback coverage, and continue ordinary work from `dev`.

### Fast feedback

- Baseline/current observable behavior: `main` has the original root commit; completed and queued work exists on `dev`/work branches; no release/tag exists.
- Hypothesis: An audited orphan commit with breaking release metadata can replace `main` safely and cause the existing release workflow to publish `v1.0.0` at that sole commit.
- Observation surface (test/harness/API/UI/log/MCP/etc.): Git commit graph/tree hashes, local bundle verification, GitHub Actions, remote refs, tag target, and GitHub Release metadata.
- Smallest chunk: In a disposable local ref, build the candidate root commit and prove its tree/parent count/version plan without touching remote refs.
- Probe/action and expected signal: Candidate has zero parents, tree equals audited source, planner reports `v1.0.0`, and all checks pass.
- Actual result/evidence: The audited final tree was published as the sole `main` root; GitHub created `v1.0.0`, an idempotent rerun produced no second release, and `dev` was reconciled with identical content while retaining review history.
- Wider checks after local proof: Verify lease SHA, backup, force-push, Actions release, tag/release target, single-commit graph, and reconciled `dev`.

### Execution constraints

- Mode: `sequential`
- Parallel exception: A read-only wait monitor may observe CI/release completion.
- Resources/shared state: `main`, `dev`, remote refs, tags, GitHub Releases, Actions, local recovery bundle, and durable goal state.

## Relationships

- Parent: [G-20260716-001](G-20260716-001-automate-semantic-releases.md)
- Children (required/optional + purpose/status): none
- Dependencies (status/reason): `G-002` and `G-006` are done. Parent `G-001` completes from this child's release evidence rather than forming a dependency cycle.
- Blocks (impact): none; this is the terminal release operation.

## Blockers

### Open

None. Dependency gates prevent premature execution.

### Resolved

None.

## Progress and evidence

The final transaction is complete: the release tree passed local/install/PR probes, a verified recovery bundle preceded the leased rewrite, `main` is one audited root commit, `v1.0.0` and its GitHub Release point to it, the rerun is idempotent, and `dev` retains reviewable integration history with identical content.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex | Created `new` as terminal goal | User requested a single-commit `main` history with `v1.0.0` on the initial/root commit after all earlier work completes. |
| 2026-07-16 | Codex/R-20260716-queued | Triaged; linked as required child of `G-001` | Removed the release parent/child dependency cycle; `G-002` remains the only unfinished prerequisite besides this operation. |
| 2026-07-16 | user/Codex/R-20260716-release-root | Set `ready` | User confirmed the ZzzOps UI grouping; both dependencies are now done. |
| 2026-07-16 | Codex/R-20260716-release-root | Completed terminal release transaction; set `done` | Exact-tree probes, verified backup, leased root rewrite, tag/release/rerun audit, and `dev` reconciliation all passed. |
