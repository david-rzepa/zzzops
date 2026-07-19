# Goal system

## Authority and records

Order: user/safety; project instructions; `.zzzops/PROJECT.md`; canonical GitHub issue.

Before every non-install workflow follow `INITIALIZATION.md`, then use the GitHub Issues authority in `BACKENDS.md`.

- GitHub goals use repository plus issue number/URL as identity; never invent a second goal ID or duplicate GitHub title/relationship state in managed JSON.
- Never store secrets/raw sensitive data; link to approved systems and name authority/sync direction.
- Project charter defines success/value. Preserve unknown KPI/target/tradeoff fields; ask rather than invent.
- Ignored `.zzzops/PREFERENCES.json` is user-local: validate types/ranges, preserve unknown keys, never commit/enable options yourself.
- Canonical project and migration artifact shapes live in `.agents/templates/project-goals/`. Installation copies mechanics/templates only and never creates or overwrites project state.

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
- Value: `critical|high|medium|low`, justified against charter acceptance/KPIs/beneficiaries/tradeoffs—not ease or code aesthetics.
- Difficulty: `unknown|XS|S|M|L|XL`, including uncertainty/risk/coordination/verification; use the PROJECT policy's decomposition threshold.
- Confidence: `low|medium|high` in outcome/scope/dependencies/estimate.
- Owner is accountability, not authority/claim. Explain target dates; `review_after` triggers reassessment, never auto-cancellation.

## Relationships and claims

One parent maximum; any children/dependencies; reject self-links/cycles. GitHub stores only parent/dependency issue numbers and derives inverse edges portfolio-wide. Create a child only for a separately verifiable/prioritized/blocked/claimed outcome or distinct risk; use checklists otherwise. Obey PROJECT depth/required-child policy. Required children finishing does not replace parent criteria.

Claim before substantial work with owner, timestamp/offset, policy-defined expiry, and checkpoint. Claims are advisory and goal-scoped; refresh at checkpoints, clear on release/block/terminal/handoff, and do not take a live claim. Record expired-claim replacement.

## Update invariants

One logical update: re-read affected records/premise; perform and observe work; update state, next action, evidence, blockers, and history. Prefer a smaller consistent update if interrupted.

- Apply the PROJECT policy's triage/continuation order; every active goal has an action or gate.
- Human blockers appear in the portfolio human queue; resolutions retain request/answer/resolver/date.
- Checked criteria cite observed evidence. Reassess due reviews.
- Follow `.zzzops/rules/EXECUTION_STRATEGY.md`: baseline and observable probe before implementation; coordinator reconciles parallel work.
- Preferences never justify invented work, priority distortion, or busywork.
- Exhausted-queue refill requires user opt-in and stays within both user and PROJECT policy ceilings.
