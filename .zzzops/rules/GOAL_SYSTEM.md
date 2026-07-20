# Goal system

## Authority and records

Order: user/safety; project instructions; reviewed project policy (`.zzzops/PROJECT.md` bound to canonical `.zzzops/POLICY.json`); canonical GitHub issue. Project instructions outrank stale derived policy, but a repository-specific conflict with reviewed policy invalidates the affected assumption: stop and reconcile it instead of silently choosing either operational rule.

Before every non-install workflow follow `INITIALIZATION.md`, then use the GitHub Issues authority in `BACKENDS.md`.

- GitHub goals use repository plus issue number/URL as identity; never invent a second goal ID or duplicate GitHub title/relationship state in managed JSON.
- Never store secrets/raw sensitive data; link to approved systems and name authority/sync direction.
- Project charter defines success/value. Preserve unknown KPI/target/tradeoff fields; ask rather than invent.
- Reviewed PROJECT policy contains repository operational choices; installed rules provide overridable defaults, never a second local policy layer.
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
- Value: `critical|high|medium|low`, justified against charter acceptance/KPIs/beneficiaries/tradeoffs—not ease or code aesthetics.
- Difficulty: `unknown|XS|S|M|L|XL`, including uncertainty/risk/coordination/verification; use the PROJECT policy's decomposition threshold.
- Confidence: `low|medium|high` in outcome/scope/dependencies/estimate.
- Owner is accountability, not authority/claim. Explain target dates; `review_after` triggers reassessment, never auto-cancellation.

## Relationships and claims

One parent maximum; any children/dependencies; reject self-links/cycles. GitHub stores only parent/dependency issue numbers and derives inverse edges portfolio-wide. Create a child only for a separately verifiable/prioritized/blocked/claimed outcome or distinct risk; use checklists otherwise. Obey PROJECT depth/required-child policy. Required children finishing does not replace parent criteria.

A dependency edge preserves required ancestry and final integration order. The installed default requires every dependency to be `done` before writable implementation begins. Reviewed PROJECT policy may override actionability; for example, `stack_from_reviewed_checkpoint` may permit a child to stack from an unfinished dependency's exact technically ready checkpoint while preserving merge order. Read-only investigation may prepare dependent work when policy allows, but it does not claim, edit, branch, or mark that implementation started.

Before substantial GitHub work, declare known `path:`, `branch:`, `integration:`, `generated:`, and `external:` resources, then atomically reserve the exact revision plus repeated `--resource` values with `<python> .agents/zzzops/zzzops.py reserve acquire --goal N --revision R --owner OWNER --run-id RUN`. Only the bundle winner claims/works. On contention refresh once and choose other work. Renew at checkpoints; release before blocking, terminal state, or handoff. Claims audit; reservations exclude. Never fall back on uncertainty; record expiry recovery.

## Update invariants

One logical update: re-read affected records/premise; perform and observe work; update state, next action, evidence, blockers, and history. Prefer a smaller consistent update if interrupted.

- Apply the PROJECT policy's triage/continuation order; every active goal has an action or gate.
- Human blockers appear in the portfolio human queue; resolutions retain request/answer/resolver/date.
- Checked criteria cite observed evidence. Reassess due reviews.
- Follow `.zzzops/rules/EXECUTION_STRATEGY.md`: baseline and observable probe before implementation; coordinator reconciles parallel work.
- Policy never justifies invented work, priority distortion, or busywork.
- The installed initialization default enables exhausted-queue refill for documentation, test coverage, and non-behavioral code quality, capped at three goals per run. It takes effect only through reviewed PROJECT policy, which may override or disable it; never loop-refill.
