# Execute goals

“All goals” means cycle until no safe useful work remains; it grants no authority.

## Select

1. Read the charter and use the current BACKENDS checkpoint portfolio; never reread it. Require `complete:true` and `valid:true`; resolve findings instead of selecting from an invalid graph, and use its compact relationships/claims/reviews rather than rereading goals. If the human queue is non-empty, run `UNBLOCK.md` to order and persist consequential gates, then continue independently actionable work.
   Specially tagged `zzzops-feedback` goals are absent unless the user approved them for this execution session. One session approval includes the whole feedback queue; never request approval per issue, and retain `--include-feedback` on every checkpoint refresh in that session.
   Treat that complete checkpoint as the current queue read until a local state mutation, provider failure, explicit freshness requirement, or observed drift requires one refresh. Do not run an extra portfolio command merely to rediscover the same goals.
2. Route `new` goals through `CREATE.md` according to PROJECT triage/continuation policy.
3. Use the portfolio's PROJECT-derived `actionable` field. The installed default waits for every dependency to be `done` before writable implementation; a reviewed PROJECT override such as `stack_from_reviewed_checkpoint` may make a child actionable earlier. Read-only investigation may prepare waiting work when policy permits, but never claims, edits, branches, or marks it started. Recheck blocked work only on its trigger.
4. Obey authority and explicit PROJECT priority first. Within the same effective priority, prefer evidenced charter/KPI value, safety/risk reduction, and unlocks: choose high-value, risk-reducing or unlocking work over low-value easy or fast work. Then prefer confidence, faster observable feedback, and lower difficulty; difficulty is cost, not value and never a reason to maximize item count. Unmeasured KPIs may support qualitative rationale, but never invent a baseline, score, or precision. On an exact tie use PROJECT resume policy, then the lowest goal key.

Execution assumes the user is absent and never asks an interactive question, including for decisions, authority, or safety boundaries. Persist each unanswered consequential question on the affected goal with its category, evidence, recommendation, continuation boundary, safe work, and recheck trigger. Stop only affected work, never infer approval, and continue independent authorized goals until true queue exhaustion.

## Execute

1. Re-read only the selected goal and selection-critical parent/dependencies; compare revision/digest, declare known resources, then reserve the bundle per `GOAL_SYSTEM.md`. On contention refresh once and choose other work; only the winner claims or begins work.
2. For source changes, establish/resume the policy-selected topology from `BRANCH_REVIEW.md` and persist branch/base/target before editing. Then follow `.zzzops/rules/EXECUTION_STRATEGY.md`: capture baseline; implement one smallest falsifiable chunk; run/inspect/record the real probe before continuing; widen only after proof.
3. Work to a verified checkpoint without silent scope expansion. Classify discoveries as scope, checklist, child, dependency, or root. Apply PROJECT test-bug policy; never hide a failure, weaken the test, or expand authority silently.
4. Persist evidence at natural checkpoints. Follow PROJECT-limited parallel/worktree rules; coordinator owns ZzzOps state and integration.

## GitHub read budget

- Use one consolidated PR-state read per review checkpoint: request the PR state, exact head, checks, review decision, and comments together. Reuse that result for the matching checkpoint rather than issuing separate status, checks, and review reads.
- Poll only through an enabled bounded watch or heartbeat. Each unchanged poll uses one consolidated PR-state read; do not poll while implementing, and stop the watch as soon as a terminal state or a human decision is reached.
- Exact-head, permission, merge, and transition readbacks remain mandatory at their safety boundaries. Reuse reduces equivalent reads; it never authorizes stale cached state.

## Block, complete, cycle

- On a blocker, follow `.zzzops/rules/BLOCKERS.md`: record the unanswered request and continuation, do only bounded safe work, then keep active or block/release claim and reservation before switching.
- Before `done`, cite observed before/after evidence for each criterion; verify required children, blockers, and relevant checks; state anything unobserved. Build/lint/types/code review do not prove runtime behavior unless that is the criterion. Apply PROJECT completion-review policy through `SELF_REVIEW.md`; when required, fix/reverify in-scope findings and record even a clean result. Source-changing work then applies the reviewed gate in `BRANCH_REVIEW.md`; under the installed `human_after_checks` fallback, technical completion alone is not `done`.
- Follow PROJECT Git/review/commit policy, staging only authorized implementation and pending local ZzzOps state; a GitHub-only state change never causes an empty commit. Refresh the batch after state mutation, recheck parent/unlocks, then select again.

## Exhaustion and handoff

When no work is actionable, rebuild the human queue through `UNBLOCK.md`, leave every request durable, and hand off the highest-leverage required actions without asking for a live response. On a later invocation, resolve any supplied answers and retry when policy restores work. Do not poll or watch for human input during execution.

If still empty, invoke `$suggest-zzzops-work` in apply mode only when reviewed PROJECT policy explicitly enables refill. Use its category and count limits; never loop-refill or enable policy yourself.

Stop only for user stop, runtime boundary, required authority/risk, unavailable/unresolved human/external blocker, or no qualifying refill. First make touched goals resumable (next action, evidence, blockers, claim, links, index, history). Apply INITIALIZATION's user-facing contract: report outcome, any one required action, and what remains; summarize checks and keep resume mechanics internal.
