---
id: G-20260716-007-squash-v1-main-history
title: Publish v1.0.0 as the single main root commit
status: new
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
depends_on: [G-20260716-001-automate-semantic-releases, G-20260716-002-brand-skills-as-zzzops, G-20260716-006-protect-main-and-dev]
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

- [ ] Every goal that existed before this goal is either `done` with observed evidence or explicitly cancelled by the user; no prerequisite blocker remains.
- [ ] Final local tests, prompt-budget check, installer smoke test, PR CI, release dry run, and repository diff audit pass against the exact tree to publish.
- [ ] A recoverable local bundle or equivalent immutable backup of pre-rewrite `main` and `dev` is created and verified before changing remote history.
- [ ] A new root commit with a breaking Conventional Commit message contains the exact audited release tree and complete durable goal state.
- [ ] Owner force-pushes `main` with an explicit lease against the previously observed remote SHA; no merge, ordinary push, or unbounded force is used.
- [ ] Remote `main` contains exactly one commit with no parent, and its tree matches the audited source tree.
- [ ] Tag `v1.0.0` and the published GitHub Release both point to that single root commit; release notes and rerun/idempotency behavior are verified.
- [ ] `dev` remains the ongoing integration branch and is reconciled to the released tree without losing reviewable development history or reopening completed goals.

## Scope

- In: Final completion audit, local recovery bundle, orphan/squash root commit, leased owner force-push to `main`, `v1.0.0` verification, and post-release `dev` reconciliation.
- Out: Rewriting before dependencies finish, deleting recovery data before verification, rewriting unrelated repositories, or keeping multiple commits on released `main`.

## Context and decisions

- User explicitly requested this terminal goal on 2026-07-16 and authorized squashing all work into a single `main` commit.
- This goal is deliberately behind every previously queued item; it must not be selected while `G-001`, `G-002`, or `G-006` is incomplete.
- The root commit must trigger semantic release as `v1.0.0`; use a real breaking Conventional Commit marker rather than manually falsifying the calculated version.
- History rewriting is destructive externally, so use `--force-with-lease` against a freshly observed `origin/main` SHA and retain a verified local recovery artifact through final audit.
- Durable state finalization must be designed before the rewrite so completing this goal does not require a second commit on `main` or move `v1.0.0` away from the sole root commit.

## Approach and next action

**Next action:** Wait until all dependencies are verified `done`, then design the state-finalization/release observation sequence and stop unless it proves the final `main` can remain one root commit with `v1.0.0` pointing to it.

### Fast feedback

- Baseline/current observable behavior: `main` has the original root commit; completed and queued work exists on `dev`/work branches; no release/tag exists.
- Hypothesis: An audited orphan commit with breaking release metadata can replace `main` safely and cause the existing release workflow to publish `v1.0.0` at that sole commit.
- Observation surface (test/harness/API/UI/log/MCP/etc.): Git commit graph/tree hashes, local bundle verification, GitHub Actions, remote refs, tag target, and GitHub Release metadata.
- Smallest chunk: In a disposable local ref, build the candidate root commit and prove its tree/parent count/version plan without touching remote refs.
- Probe/action and expected signal: Candidate has zero parents, tree equals audited source, planner reports `v1.0.0`, and all checks pass.
- Actual result/evidence: Not run.
- Wider checks after local proof: Verify lease SHA, backup, force-push, Actions release, tag/release target, single-commit graph, and reconciled `dev`.

### Execution constraints

- Mode: `sequential`
- Parallel exception: A read-only wait monitor may observe CI/release completion.
- Resources/shared state: `main`, `dev`, remote refs, tags, GitHub Releases, Actions, local recovery bundle, and durable goal state.

## Relationships

- Parent: none
- Children (required/optional + purpose/status): none
- Dependencies (status/reason): `G-001`, `G-002`, and `G-006` collectively cover all earlier unfinished work and must be `done` first.
- Blocks (impact): none; this is the terminal release operation.

## Blockers

### Open

None. Dependency gates prevent premature execution.

### Resolved

None.

## Progress and evidence

Captured as the last queued goal. No history rewrite, tag, release, or `main` update has occurred.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | Codex | Created `new` as terminal goal | User requested a single-commit `main` history with `v1.0.0` on the initial/root commit after all earlier work completes. |
