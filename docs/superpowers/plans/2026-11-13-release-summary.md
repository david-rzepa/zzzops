# Release Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make existing Git-flow release progress and publication evidence inspectable through `next`.
**Architecture:** Add derived summaries to `next.releases`; retain the current release line map. Hydrate closed line documents locally for evidence without reading every closed member. Reuse existing rendered actions, decisions and waits.
**Tech Stack:** Python standard library, existing unittest and bare-Git CLI fixtures.
**Spec:** docs/superpowers/specs/2026-11-13-release-summary-design.md

## Global Constraints

- Read-only derived output; no workflow, approval, release numbering or deployment changes.
- Existing fields remain compatible; normal output trims advisory detail before actions.
- Python 3.10+; no dependencies.

## Review Focus

- Closure without merge evidence must not claim publication.
- Paused/offline views must not offer executable next actions.
- Late and held members must remain visible; hotfix members belong only to their own line.
- Closed line evidence must survive fresh sessions without hydrating all closed member goals.
- Large summaries must not displace existing actionable items; full detail remains available with --all.

### Task 1: Release summaries

**Files:** Modify `engine/render.py`, `engine/store.py` and `engine/session.py` under `plugins/zzzops/zzzops`; create a small `engine/release_summary.py` if rendering helpers warrant separation; add `.agents/test_engine_release_summary.py`; document the output in `docs/design/SPEC.md`.

- [x] Add behavioral tests for membership, workflow/action/blocker rendering, publication evidence and cancellation, paused output and size handling.
- [x] Run the focused tests and observe missing-summary failures.
- [x] Implement the derived view and closed-line hydration; use node operation identities rather than default node names.
- [x] Verify through the real CLI/bare-Git release journey, including a fresh next after finish and a read-only ref comparison.
- [x] Run focused release/portfolio/store suites and appropriate product validation; inspect all failures.
- [x] Review the final diff, update progress, and commit the implementation.

## Verification and decisions

- Baseline: 44 portfolio tests passed before implementation.
- Added 15 summary tests, including two real CLI/bare-Git journeys with fake GitHub and a read-only remote-ref comparison. Missing behavior was observed before implementation.
- Independent review found malformed back-merge receipt handling and portfolio expansion links; regressions were reproduced and fixed. Closed workflows retain recorded states.
- Lifecycle validation caught recursive consumers counting advisory references as duplicate decisions. References now use item_kind; the fast reproduction and original CLI regression both pass.
- Final frozen-source validation through sched adapter-check: all 1,136 local Python tests passed, zero failures/errors/skips, four workers, 715.3 seconds. All 15 summary tests were included. No scheduler daemon or remote CI was started.
- Prompt context limits and git diff --check passed.
- Decision: extend existing next output rather than add another command; publication describes recorded Git merge facts, while unavailable evidence remains unknown.
- Decision: trim advisory details before actionable items; next --all retains the complete view.
