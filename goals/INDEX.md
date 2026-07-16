# Goal portfolio index

Derived from `goals/items/`; repair drift. **Reviewed:** 2026-07-16.

## Human input queue
| Blocker | Goal | Category | Request | Impact | Raised |
| --- | --- | --- | --- | --- | --- |
| B-001 | [G-20260716-002](items/G-20260716-002-brand-skills-as-zzzops.md) | human-action | Reopen checkout at `C:\dev\zzzops` and verify Codex group label. | Final branding verification only. | 2026-07-16 |

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
| [G-20260716-002](items/G-20260716-002-brand-skills-as-zzzops.md) | P1 | B-001 `human-action` | Workspace reopened at `C:\dev\zzzops` | No repository work remains; release goal is safe. |

## Root goals
| Goal | Status | Priority | Value | Difficulty | Progress summary |
| --- | --- | --- | --- | --- | --- |
| [G-20260716-001](items/G-20260716-001-automate-semantic-releases.md) | triaged | P1 | high | M | Release authorized; terminal child `G-007` awaits `G-002` UI check. |
| [G-20260716-002](items/G-20260716-002-brand-skills-as-zzzops.md) | blocked | P1 | high | M | Repository rename verified; awaiting ZzzOps-path UI check. |
| [G-20260716-004](items/G-20260716-004-stabilize-prompt-budget-line-endings.md) | done | P2 | medium | S | Canonical LF byte counting and regression test verified. |

## Recently completed or cancelled
| Goal | Final status | Date | Evidence/rationale |
| --- | --- | --- | --- |
| [G-20260716-003](items/G-20260716-003-document-dev-branch-workflow.md) | done | 2026-07-16 | Work branch descends from `dev`; exact root policy and prompt-budget checks passed. |
| [G-20260716-005](items/G-20260716-005-document-pr-workflow.md) | done | 2026-07-16 | Root policy now requires `dev`-targeted PRs and intentional atomic commit boundaries. |
| [G-20260716-004](items/G-20260716-004-stabilize-prompt-budget-line-endings.md) | done | 2026-07-16 | LF/CRLF/CR estimates match; regenerated prompt budget passes. |
| [G-20260716-006](items/G-20260716-006-protect-main-and-dev.md) | done | 2026-07-16 | PR #1 passed `dev-required-tests`; Free-plan limitation and exact manual fallback documented. |

## Portfolio notes
- Release tooling remains intentionally undecided pending repository investigation.
- Skill identifier compatibility remains intentionally undecided pending a complete rename map.
