# Goal system

## Authority and records

Order: user/safety; project instructions; reviewed `.zzzops/PROJECT.md` (bound to canonical policy); canonical GitHub issue. A repository-policy conflict invalidates the assumption: stop and reconcile rather than choosing silently.

Before every non-install workflow follow `INITIALIZATION.md`, then use the GitHub Issues authority in `BACKENDS.md`.

- Goal identity is repository plus issue number/URL; never invent another ID or duplicate GitHub title/relations in managed JSON.
- Never store secrets/raw sensitive data; link approved systems and name authority/sync direction.
- The charter defines success/value. Preserve unknown KPIs/targets/tradeoffs; capture asks, while execution records blockers rather than inventing answers.
- Reviewed PROJECT holds operational choices; installed rules are overridable defaults, not another policy layer.
- Initialization plans and migration artifact shapes live in `.agents/zzzops/templates/project-goals/`; `init apply` renders project state. Installation copies mechanics/templates only and never creates or overwrites project state.

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

One parent maximum; any children/dependencies; reject self-links/cycles. GitHub stores only parent/dependency issue numbers and derives inverse edges portfolio-wide. Create a child only for a separately verifiable/prioritized/blocked/claimed outcome or distinct risk; use checklists otherwise. Obey PROJECT depth/required-child policy. Required children finishing does not replace parent criteria.

A dependency edge preserves required ancestry and final integration order. The installed default requires every dependency to be `done` before writable implementation begins. Reviewed PROJECT policy may override actionability; for example, `stack_from_reviewed_checkpoint` may permit a child to stack from an unfinished dependency's exact technically ready checkpoint while preserving merge order. Read-only investigation may prepare dependent work when policy allows, but it does not claim, edit, branch, or mark that implementation started.

Before substantial GitHub work, declare `path:`, `branch:`, `integration:`, `generated:`, and `external:` resources; atomically reserve revision/resources with `<python> .agents/zzzops/zzzops.py reserve acquire --goal N --revision R --owner OWNER --run-id RUN`. Claims/branches are always exclusive. Default: text paths/integration targets are advisory; generated/external resources are exclusive. Policy may mark hard-to-merge paths, change configurable categories, or select strict mode. Only exclusive contention rejects bundles or creates `resource_collision`; reconcile advisory overlap in branch review. On contention refresh once and choose other work. Renew at checkpoints; release before blocking, terminal state, or handoff. Claims audit; reservations exclude. Never assume ownership; record expiry recovery.

## Update invariants

One logical update: re-read affected records/premise; perform and observe work; update state, next action, evidence, blockers, and history. Prefer a smaller consistent update if interrupted.

- Apply the PROJECT policy's triage/continuation order; every active goal has an action or gate.
- Human blockers appear in the portfolio human queue; resolutions retain request/answer/resolver/date.
- Checked criteria cite observed evidence. Reassess due reviews.
- Follow `.zzzops/rules/EXECUTION_STRATEGY.md`: baseline and observable probe before implementation; coordinator reconciles parallel work.
- Policy never justifies invented work, priority distortion, or busywork.
- The installed initialization default enables exhausted-queue refill for documentation, test coverage, and non-behavioral code quality, capped at three goals per run. It takes effect only through reviewed PROJECT policy, which may override or disable it; never loop-refill.
