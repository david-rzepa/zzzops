# Execute goals

“All goals” means cycle until no safe useful work remains; it grants no authority.

## Select

1. Use the charter and current BACKENDS checkpoint; require `complete:true`/`valid:true` and resolve findings before selecting. Use compact relationships/claims/reviews without rereading goals. If the human queue exists, use `UNBLOCK.md` to persist/order gates, then continue independent work. Include `zzzops-feedback` only with queue-wide current-session approval and preserve `--include-feedback` on refresh. Treat it as the current queue read until mutation, provider failure, required freshness, or drift permits one refresh; do not rediscover via `portfolio`.
2. Route `work_state: triage|prepare` through `CREATE.md`; it may update state/justified children, never claim, branch, edit, or implement.
3. `write` alone permits reservation/source changes, with valid effective engineering rigor. `wait_dependency` permits policy-authorized read-only investigation; `wait_human`, `blocked`, and `terminal` wait. PROJECT alone derives `write`, including allowed review-checkpoint stacking.
4. Obey authority and explicit PROJECT priority first. At equal priority choose risk-reducing or unlocking work over low-value easy or fast work; then confidence, feedback speed, and lower difficulty; difficulty is cost, not value. Never invent a baseline, score, or precision. Exact tie: PROJECT resume policy, then the lowest goal key.

Execution assumes the user is absent and never asks an interactive question. Persist each unanswered consequential question with category, evidence, recommendation, boundary, safe work, and trigger. Never infer approval; stop affected work only and continue to true queue exhaustion.

Before substantive work on a newly selected goal or resume, state outcome/scope before reservation/edits; do not repeat or make it an approval gate.

Update the user only for a new result, decision, risk, changed assumption, required action, or long-operation heartbeat; never recap unchanged state.

## Execute

1. Re-read only the selected goal and critical parent/dependencies; match revision/digest, declare resources, then reserve per `GOAL_SYSTEM.md`. On contention refresh once and switch; only the winner starts. If schema/body is legacy, `goal inspect` it and refresh—never sweep others.
2. For source changes, establish `BRANCH_REVIEW.md` topology and persist branch/base/target before editing. Follow `../../../rules/EXECUTION_STRATEGY.md`: baseline, one smallest falsifiable chunk, then run/inspect/record its real probe; widen only after proof and leave exact-equivalent broad checks to required CI.
3. Work to a verified checkpoint without scope expansion. Classify discoveries as scope, checklist, child, dependency, or root. Apply PROJECT test-bug policy; never hide failures, weaken tests, or expand authority.
4. At checkpoints append material assumptions, new constraints, and plan deviations—not tool logs. Resolve in-scope decisions under automated-design policy or record one blocker; never interview live.
5. Persist evidence naturally. Follow PROJECT parallel/worktree limits; coordinator owns state/integration.

## GitHub read budget

- Use one consolidated PR-state read per review checkpoint for state, exact head, checks, review decision, and comments; reuse it.
- Poll only through enabled bounded watch/heartbeat using that consolidated read; never while implementing, and stop at terminal/human decision.
- Exact-head, permission, merge, and transition readbacks remain mandatory; reuse never authorizes stale state.

## Block, complete, cycle

- On blockers use `../../../rules/BLOCKERS.md`: persist request/continuation, do bounded safe work, then stay active or block/release claim/reservation before switching.
- Before `done`, apply effective engineering rigor: `vibe` may accept observed behavior when policy permits; `structured` requires observable criteria, targeted checks, and canonical verification; `agentic` requires relevant deterministic gates, regressions, architecture guardrails, and security/data/recovery/operations evidence. Created-but-unrun machinery is not proof. Cite each criterion, verify children/blockers/checks, and state gaps; build/lint/types/review prove only themselves. Apply `SELF_REVIEW.md` and `BRANCH_REVIEW.md`; `human_after_checks` still requires approval.
- Follow PROJECT Git/review/commit policy; stage only authorized implementation/pending local state, never an empty commit for GitHub-only state. After mutation refresh, recheck parents/unlocks, and select again.

## Exhaustion and handoff

When no goal has `work_state: triage|prepare|write`, rebuild the durable human queue via `UNBLOCK.md` and hand off highest-leverage actions without asking live. Later resolve supplied answers and retry when policy restores work; never poll for human input.

If empty, `$suggest-zzzops-work` may apply only under explicit reviewed refill policy and its limits; never enable or loop-refill.

Stop only for user stop, runtime boundary, authority/risk, unresolved human/external blocker, or no refill. First make touched goals resumable (action, evidence, blockers, claim, links/history). Report outcome, one required action, remaining work, and checks; keep mechanics internal.
