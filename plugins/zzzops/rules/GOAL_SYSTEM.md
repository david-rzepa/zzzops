# Goal system

## Authority and records

Order: user/safety; project instructions; reviewed `.zzzops/PROJECT.md`; canonical GitHub issue. Repository-policy conflict stops for reconciliation. Before non-install workflows follow `INITIALIZATION.md`, then `BACKENDS.md`.

- Goal identity is repository plus issue number/URL; never invent IDs or duplicate provider-owned title/relations.
- Never store credentials, payment cards, health data, government IDs, or raw sensitive data; redact or link an approved private system.
- The charter defines value. Preserve unknown KPIs/targets/tradeoffs; capture asks and execution blocks rather than inventing answers.
- PROJECT holds operational choices; installed rules hold invariants/value interpreters. Missing choices require policy review.
- Templates live in the plugin package at `zzzops/templates/project-goals/`; plugin installation never creates or copies project state.

## Lifecycle

| Status | Meaning |
| --- | --- |
| `new` | Captured, uninvestigated |
| `triaged` | Understood; preparation/children/expected dependency remain |
| `ready` | Authorized concrete action, no gate |
| `in_progress` | Active/resumable work |
| `blocked` | Specific blocker leaves no safe useful work |
| `done` | Required criteria observed and verified |
| `cancelled` | Abandoned/superseded with rationale |

Open blockers may coexist with active states while useful work remains. Reopen terminal states only with history. A parent progressed through children names them; avoid a competing parent claim unless doing direct parent work.

## Metadata and value

- Priority: `P0` urgent safety/production/deadline; `P1` major impact/unlock; `P2` normal; `P3` opportunistic.
- Value: `critical|high|medium|low`, justified by charter outcomes—not ease/aesthetics.
- Difficulty: `unknown|XS|S|M|L|XL`, including risk/coordination/verification; obey PROJECT's decomposition threshold.
- Confidence: `low|medium|high` in outcome, scope, dependencies, and estimate.
- Owner is accountability, not authority/claim. Explain dates; `review_after` triggers reassessment, never auto-cancellation.

## Relationships and claims

One parent maximum; any children/dependencies; reject self-links/cycles. Store issue numbers and derive inverse edges. Use children only for distinct verifiable/prioritized/blocked/claimed outcomes or risks; otherwise use checklists. Obey PROJECT depth/required-child policy; children do not replace parent criteria.

Dependencies preserve ancestry/merge order. PROJECT alone derives write actionability; missing settings defer affected writes to policy review. `stack_from_reviewed_checkpoint` preserves merge order. Read-only preparation never claims, edits, branches, or starts implementation.

Declare `path:`, `branch:`, `integration:`, `generated:`, and `external:` resources; reserve with `<python> <zzzops-cli> reserve acquire --goal N --revision R --owner OWNER --run-id RUN`. Apply PROJECT resource settings; missing settings defer writes to policy review. Claims/branches are identity-exclusive. Reject exclusive contention; reconcile advisory overlap. Refresh once, renew at checkpoints, and release before blocking/terminal/handoff. Never assume ownership; claims audit, reservations exclude.

## Update invariants

One logical update: re-read affected records/premise; perform and observe work; update state, next action, evidence, blockers, and history. Prefer a smaller consistent update if interrupted.

Use BACKENDS' current-body, append-first history, and idempotent retry contract.

- Repair a selected/read goal lacking the current schema label or compact body; never sweep bodies/comments for drift.

- Apply the PROJECT policy's triage/continuation order; every active goal has an action or gate.
- Human blockers appear in the portfolio human queue; resolutions retain request/answer/resolver/date.
- Checked criteria cite observed evidence. Reassess due reviews.
- Follow `EXECUTION_STRATEGY.md`: baseline and observable probe before implementation; coordinator reconciles parallel work.
- Policy never justifies invented work, priority distortion, or busywork.
- Reviewed PROJECT may enable one capped exhausted-queue refill; never loop-refill or infer permission.
