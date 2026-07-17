# Goal portfolio index

Derived from `goals/items/`; repair drift. **Reviewed:** 2026-07-16.

## Human input queue
| Blocker | Goal | Category | Request | Impact | Raised |
| --- | --- | --- | --- | --- | --- |
| B-001 | [G-008](items/G-20260716-008-require-project-value-interview.md) | specification | Confirm project outcome, KPI targets, and precedence. | Blocks final charter/completion; bounded mechanics continue. | 2026-07-16 |
| B-001 | [G-009](items/G-20260716-009-add-user-health-module.md) | decision | Confirm health enablement, privacy, timestamp fallback, storage, and timezone defaults. | Blocks health implementation. | 2026-07-16 |

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
| [G-20260716-011](items/G-20260716-011-goal-backends-workflow-routing.md) | [G-008](items/G-20260716-008-require-project-value-interview.md) | P1 | high | M | G-012 | Implement managed issue round trips and shared workflow routing; stop when contract tests pass. |

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
| [G-20260716-008](items/G-20260716-008-require-project-value-interview.md) | triaged | P1 | high | L | G-010 ready; charter confirmation remains open for completion. |
| [G-20260716-009](items/G-20260716-009-add-user-health-module.md) | triaged | P1 | high | L | Depends on G-008 and confirmed health defaults. |
| [G-20260716-010](items/G-20260716-010-initialization-state-cli.md) | done | P1 | high | M | Six focused initialization/atomicity tests pass. |
| [G-20260716-011](items/G-20260716-011-goal-backends-workflow-routing.md) | ready | P1 | high | M | Initialization dependency satisfied. |
| [G-20260716-012](items/G-20260716-012-initialization-install-docs-regression.md) | triaged | P1 | high | M | Depends on G-010/G-011. |
| [G-20260716-013](items/G-20260716-013-health-policy-schema.md) | triaged | P1 | high | M | Depends on G-008 and health decision. |
| [G-20260716-014](items/G-20260716-014-health-preferences-cli.md) | triaged | P1 | high | M | Depends on G-013. |
| [G-20260716-015](items/G-20260716-015-health-workflow-integration.md) | triaged | P1 | high | M | Depends on G-014. |

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
- G-008/G-009 are decomposed into six sequential children. Execute G-010 first; charter confirmation does not block mechanics, while health decisions stop G-013 onward. All work stays on the current single branch.
