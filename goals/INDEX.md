# Goal portfolio index

Derived from `goals/items/`; repair drift. **Reviewed:** 2026-07-16.

## Human input queue
| Blocker | Goal | Category | Request | Impact | Raised |
| --- | --- | --- | --- | --- | --- |
| B-001 | [G-20260716-002](items/G-20260716-002-brand-skills-as-zzzops.md) | human-action | Reopen checkout at `C:\dev\zzzops` and verify Codex group label. | Final branding verification only. | 2026-07-16 |
| B-002 | [G-20260716-001](items/G-20260716-001-automate-semantic-releases.md) | access-approval | Authorize integrating `dev` into `main` to publish expected `v1.0.0`. | Final production-release verification. | 2026-07-16 |

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
| [G-20260716-005](items/G-20260716-005-document-pr-workflow.md) | [G-20260716-001](items/G-20260716-001-automate-semantic-releases.md) | P1 | high | S | PR workflow safety | Update and scenario-check root guidance. |
| [G-20260716-006](items/G-20260716-006-protect-main-and-dev.md) | [G-20260716-001](items/G-20260716-001-automate-semantic-releases.md) | P1 | high | M | Enforced branch safety | Inspect capabilities, add PR CI, configure rules if supported. |
| [G-20260716-004](items/G-20260716-004-stabilize-prompt-budget-line-endings.md) | - | P2 | medium | S | Stable prompt regression | Add LF/CRLF test, normalize, regenerate. |

## Blocked goals
| Goal | Priority | Blockers | Recheck trigger | Safe work? |
| --- | --- | --- | --- | --- |
| [G-20260716-002](items/G-20260716-002-brand-skills-as-zzzops.md) | P1 | B-001 `human-action` | Workspace reopened at `C:\dev\zzzops` | No repository work remains; release goal is safe. |
| [G-20260716-001](items/G-20260716-001-automate-semantic-releases.md) | P1 | B-002 `access-approval` | Explicit first-release authorization | No safe production-release work remains. |

## Root goals
| Goal | Status | Priority | Value | Difficulty | Progress summary |
| --- | --- | --- | --- | --- | --- |
| [G-20260716-001](items/G-20260716-001-automate-semantic-releases.md) | blocked | P1 | high | M | Two live `dev` dry runs passed; awaiting `v1.0.0` release approval. |
| [G-20260716-002](items/G-20260716-002-brand-skills-as-zzzops.md) | blocked | P1 | high | M | Repository rename verified; awaiting ZzzOps-path UI check. |
| [G-20260716-004](items/G-20260716-004-stabilize-prompt-budget-line-endings.md) | ready | P2 | medium | S | Approved; normalization test and fix queued. |

## Recently completed or cancelled
| Goal | Final status | Date | Evidence/rationale |
| --- | --- | --- | --- |
| [G-20260716-003](items/G-20260716-003-document-dev-branch-workflow.md) | done | 2026-07-16 | Work branch descends from `dev`; exact root policy and prompt-budget checks passed. |

## Portfolio notes
- Release tooling remains intentionally undecided pending repository investigation.
- Skill identifier compatibility remains intentionally undecided pending a complete rename map.
