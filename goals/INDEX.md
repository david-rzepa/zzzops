# Goal portfolio index

Derived from `goals/items/`; repair drift. **Reviewed:** 2026-07-16.

## Human input queue
| Blocker | Goal | Category | Request | Impact | Raised |
| --- | --- | --- | --- | --- | --- |
| None | - | - | - | - | - |

## Active claims
| Goal | Owner | Claimed | Expires | Checkpoint |
| --- | --- | --- | --- | --- |
| None | - | - | - | - |

## New goals awaiting triage
| Goal | Priority | Created | Provisional outcome |
| --- | --- | --- | --- |
| None | - | - | - |

## Ready queue
| Goal | Parent | Priority | Value | Difficulty | Unlocks | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| None | - | - | - | - | - | - |

## Blocked goals
| Goal | Priority | Blockers | Recheck trigger | Safe work? |
| --- | --- | --- | --- | --- |
| None | - | - | - | - |

## Root goals
| Goal | Status | Priority | Value | Difficulty | Progress summary |
| --- | --- | --- | --- | --- | --- |
| [G-20260716-001](items/G-20260716-001-automate-semantic-releases.md) | done | P1 | high | M | Semantic release and the single-root `v1.0.0` production path are verified. |
| [G-20260716-002](items/G-20260716-002-brand-skills-as-zzzops.md) | done | P1 | high | M | Repository rename and ZzzOps-path Codex grouping verified. |
| [G-20260716-004](items/G-20260716-004-stabilize-prompt-budget-line-endings.md) | done | P2 | medium | S | Canonical LF byte counting and regression test verified. |

## Recently completed or cancelled
| Goal | Final status | Date | Evidence/rationale |
| --- | --- | --- | --- |
| [G-20260716-003](items/G-20260716-003-document-dev-branch-workflow.md) | done | 2026-07-16 | Work branch descends from `dev`; exact root policy and prompt-budget checks passed. |
| [G-20260716-005](items/G-20260716-005-document-pr-workflow.md) | done | 2026-07-16 | Root policy now requires `dev`-targeted PRs and intentional atomic commit boundaries. |
| [G-20260716-004](items/G-20260716-004-stabilize-prompt-budget-line-endings.md) | done | 2026-07-16 | LF/CRLF/CR estimates match; regenerated prompt budget passes. |
| [G-20260716-006](items/G-20260716-006-protect-main-and-dev.md) | done | 2026-07-16 | PR #1 passed `dev-required-tests`; Free-plan limitation and exact manual fallback documented. |
| [G-20260716-002](items/G-20260716-002-brand-skills-as-zzzops.md) | done | 2026-07-16 | Fresh install/update probes passed and the user confirmed Codex groups the renamed checkout under ZzzOps. |
| [G-20260716-007](items/G-20260716-007-squash-v1-main-history.md) | done | 2026-07-16 | Exact-tree audit, backup, leased rewrite, `v1.0.0`, idempotent rerun, and `dev` reconciliation passed. |
| [G-20260716-001](items/G-20260716-001-automate-semantic-releases.md) | done | 2026-07-16 | Shared dry-run/publish planner is proven locally, on `dev`, and by the production `v1.0.0` release. |

## Portfolio notes
- All queued goals are complete. Future ordinary work starts from `dev`; `main` is the clean single-root `v1.0.0` release line.
