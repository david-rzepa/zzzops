# Goal system

## Authority and records

Order: user/safety; project instructions; `goals/PROJECT.md`; goal; derived `goals/INDEX.md`; append-only ledger. Repair derived drift from goal truth.

- Stable goals: `goals/items/G-YYYYMMDD-NNN-slug.md`; follow `goals/TEMPLATE.md`. Use relative links; keep progress resumable and history append-only.
- Never store secrets/raw sensitive data; link to approved systems and name authority/sync direction.
- Project charter defines success/value. Preserve unknown KPI/target/tradeoff fields; ask rather than invent.
- Ignored `.zzzops/PREFERENCES.json` is user-local: validate types/ranges, preserve unknown keys, never commit/enable options yourself.
- Canonical blank shapes live in `.agents/templates/project-goals/`. Never overwrite state mechanically; `$migrate-project-goals` processes pending `.zzzops/migration/template-diffs/` preservation-aware.

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
- Difficulty: `unknown|XS|S|M|L|XL`, including uncertainty/risk/coordination/verification; usually decompose `L/XL`.
- Confidence: `low|medium|high` in outcome/scope/dependencies/estimate.
- Owner is accountability, not authority/claim. Explain target dates; `review_after` triggers reassessment, never auto-cancellation.

## Relationships and claims

One parent maximum; any children/dependencies. Update both directions atomically; reject self-links/cycles. Create a child only for a separately verifiable/prioritized/blocked/claimed outcome or distinct risk; use checklists otherwise. Prefer depth <=3 and label required/optional. Required children finishing does not replace parent criteria.

Claim before substantial work with owner, timestamp/offset, expiry (default four hours), and checkpoint. Claims are advisory and goal-scoped; refresh at checkpoints, clear on release/block/terminal/handoff, and do not take a live claim. Record expired-claim replacement.

## Update invariants

One logical update: re-read affected records/premise; perform and observe work; update state, next action, evidence, blockers, history, backlinks/index, and usage. Prefer a smaller consistent update if interrupted.

- Triage all `new` goals before steady execution; every active goal has an action or gate.
- Human blockers appear in the index; resolutions retain request/answer/resolver/date.
- Checked criteria cite observed evidence. Reassess due reviews.
- Follow `.zzzops/rules/EXECUTION_STRATEGY.md`: baseline and observable probe before implementation; coordinator reconciles parallel work.
- Every run gets a usage row, even `unavailable`. Usage/preferences never justify invented work, priority distortion, or busywork.
- Exhausted-queue refill is bounded to opted-in categories, one cycle/run, with evidenced non-duplicates.
