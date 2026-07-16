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
| [G-20260716-001](items/G-20260716-001-automate-semantic-releases.md) | - | P1 | high | M | Automated releases | Push integrated work to `dev` and inspect the dry-run job. |

## Blocked goals
| Goal | Priority | Blockers | Recheck trigger | Safe work? |
| --- | --- | --- | --- | --- |
| [G-20260716-002](items/G-20260716-002-brand-skills-as-zzzops.md) | P1 | B-001 `human-action` | Workspace reopened at `C:\dev\zzzops` | No repository work remains; release goal is safe. |

## Root goals
| Goal | Status | Priority | Value | Difficulty | Progress summary |
| --- | --- | --- | --- | --- | --- |
| [G-20260716-001](items/G-20260716-001-automate-semantic-releases.md) | in_progress | P1 | high | M | Local planner/workflow/tests pass; live `dev` dry run is next. |
| [G-20260716-002](items/G-20260716-002-brand-skills-as-zzzops.md) | blocked | P1 | high | M | Repository rename verified; awaiting ZzzOps-path UI check. |

## Recently completed or cancelled
| Goal | Final status | Date | Evidence/rationale |
| --- | --- | --- | --- |
| [G-20260716-003](items/G-20260716-003-document-dev-branch-workflow.md) | done | 2026-07-16 | Work branch descends from `dev`; exact root policy and prompt-budget checks passed. |

## Portfolio notes
- Release tooling remains intentionally undecided pending repository investigation.
- Skill identifier compatibility remains intentionally undecided pending a complete rename map.
