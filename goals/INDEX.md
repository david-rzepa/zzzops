# Goal portfolio index

Derived from `goals/items/`; repair drift. **Reviewed:** 2026-07-16.

## Human input queue
| Blocker | Goal | Category | Request | Impact | Raised |
| --- | --- | --- | --- | --- | --- |
| B-001 | [G-20260716-002](items/G-20260716-002-brand-skills-as-zzzops.md) | human-action | Reopen checkout at `C:\dev\zzzops` and verify Codex group label. | Final branding verification only. | 2026-07-16 |
| B-002 | [G-20260716-001](items/G-20260716-001-automate-semantic-releases.md) | access-approval | Authorize integrating `dev` into `main` to publish expected `v1.0.0`. | Final production-release verification. | 2026-07-16 |
| B-006 | [G-20260716-006](items/G-20260716-006-protect-main-and-dev.md) | technical-unknown | Upgrade to Pro or make public; accept closest owner-bypass semantics. | Branch protection cannot otherwise be configured/verified. | 2026-07-16 |

## Active claims
| Goal | Owner | Claimed | Expires | Checkpoint |
| --- | --- | --- | --- | --- |
| None | - | - | - | - |

## New goals awaiting triage
| Goal | Priority | Created | Provisional outcome |
| --- | --- | --- | --- |
| [G-20260716-007](items/G-20260716-007-squash-v1-main-history.md) | P1 | 2026-07-16 | Publish the completed first release as the sole `main` root commit tagged `v1.0.0`. |

## Ready queue
| Goal | Parent | Priority | Value | Difficulty | Unlocks | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| None | - | - | - | - | - | - |

## Blocked goals
| Goal | Priority | Blockers | Recheck trigger | Safe work? |
| --- | --- | --- | --- | --- |
| [G-20260716-002](items/G-20260716-002-brand-skills-as-zzzops.md) | P1 | B-001 `human-action` | Workspace reopened at `C:\dev\zzzops` | No repository work remains; release goal is safe. |
| [G-20260716-001](items/G-20260716-001-automate-semantic-releases.md) | P1 | B-002 `access-approval` | Explicit first-release authorization | No safe production-release work remains. |
| [G-20260716-006](items/G-20260716-006-protect-main-and-dev.md) | P1 | B-005 access; B-006 capability | GitHub auth restored and plan/policy chosen | CI is published; no remaining unauthenticated work. |

## Root goals
| Goal | Status | Priority | Value | Difficulty | Progress summary |
| --- | --- | --- | --- | --- | --- |
| [G-20260716-001](items/G-20260716-001-automate-semantic-releases.md) | blocked | P1 | high | M | Two live `dev` dry runs passed; awaiting `v1.0.0` release approval. |
| [G-20260716-002](items/G-20260716-002-brand-skills-as-zzzops.md) | blocked | P1 | high | M | Repository rename verified; awaiting ZzzOps-path UI check. |
| [G-20260716-004](items/G-20260716-004-stabilize-prompt-budget-line-endings.md) | done | P2 | medium | S | Canonical LF byte counting and regression test verified. |
| [G-20260716-007](items/G-20260716-007-squash-v1-main-history.md) | new | P1 | high | M | Terminal squash/release goal; gated by all earlier incomplete work. |

## Recently completed or cancelled
| Goal | Final status | Date | Evidence/rationale |
| --- | --- | --- | --- |
| [G-20260716-003](items/G-20260716-003-document-dev-branch-workflow.md) | done | 2026-07-16 | Work branch descends from `dev`; exact root policy and prompt-budget checks passed. |
| [G-20260716-005](items/G-20260716-005-document-pr-workflow.md) | done | 2026-07-16 | Root policy now requires `dev`-targeted PRs and intentional atomic commit boundaries. |
| [G-20260716-004](items/G-20260716-004-stabilize-prompt-budget-line-endings.md) | done | 2026-07-16 | LF/CRLF/CR estimates match; regenerated prompt budget passes. |

## Portfolio notes
- Release tooling remains intentionally undecided pending repository investigation.
- Skill identifier compatibility remains intentionally undecided pending a complete rename map.
