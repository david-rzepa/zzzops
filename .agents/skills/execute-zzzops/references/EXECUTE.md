# Execute goals

“All goals” means cycle until no safe useful work remains; it grants no authority.

## Select

1. Read charter/preferences and use the current BACKENDS checkpoint portfolio; never reread it. Require `complete:true` and `valid:true`; resolve findings instead of selecting from an invalid graph, and use its compact relationships/claims/reviews rather than rereading goals. If the present user's human queue is non-empty, run `UNBLOCK.md` first.
2. Route `new` goals through `CREATE.md` according to PROJECT triage/continuation policy.
3. Use the portfolio's PROJECT-derived `actionable` field; do not replace it with an “all dependencies must be `done`/merged” rule. Ordinarily actionable means `ready` or resumable `in_progress` with an authorized concrete next action, satisfied gates, and no invalidating blocker/live foreign claim. With reviewed `review_pending_dependency: stack_from_reviewed_checkpoint`, the dependency remains blocked for its own review/merge while its child is actionable from the exact checkpoint. Preserve the dependency edge and stack the child as `BRANCH_REVIEW.md` requires. “Not merged” is not “not actionable.” Recheck blocked work only on its trigger.
4. Rank by evidenced charter/KPI movement and unlock value, then apply PROJECT priority, easy-win, tie-break, and resume policy.

## Execute

1. Re-read only the selected goal and selection-critical parent/dependencies; compare revision/digest, declare known resources, then reserve the bundle per `GOAL_SYSTEM.md`. On contention refresh once and choose other work; only the winner claims or begins work.
2. For source changes, establish/resume the policy-selected topology from `BRANCH_REVIEW.md` and persist branch/base/target before editing. Then follow `.zzzops/rules/EXECUTION_STRATEGY.md`: capture baseline; implement one smallest falsifiable chunk; run/inspect/record the real probe before continuing; widen only after proof.
3. Work to a verified checkpoint without silent scope expansion. Classify discoveries as scope, checklist, child, dependency, or root. Apply PROJECT test-bug policy; never hide a failure, weaken the test, or expand authority silently.
4. Persist evidence at natural checkpoints. Follow preference-limited parallel/worktree rules; coordinator owns ZzzOps state and integration.

## Block, complete, cycle

- On a blocker, follow `.zzzops/rules/BLOCKERS.md`: record continuation, ask when useful, do only bounded safe work, then keep active or block/release claim and reservation before switching.
- Before `done`, cite observed before/after evidence for each criterion; verify required children, blockers, and relevant checks; state anything unobserved. Build/lint/types/code review do not prove runtime behavior unless that is the criterion. Apply PROJECT completion-review policy through `SELF_REVIEW.md`; when required, fix/reverify in-scope findings and record even a clean result. Source-changing work then applies the reviewed gate in `BRANCH_REVIEW.md`; under the installed `human_after_checks` fallback, technical completion alone is not `done`.
- Follow PROJECT Git/review/commit policy, staging only authorized implementation and pending local ZzzOps state; a GitHub-only state change never causes an empty commit. Refresh the batch after state mutation, recheck parent/unlocks, then select again.

## Exhaustion and handoff

When no work is actionable, rebuild the human queue and apply PROJECT blocker-interview/continuation policy through `UNBLOCK.md`; persist answers and retry when policy restores work. At true exhaustion, apply PROJECT `human_unblock_watch` only when completion is safely observable.

If still empty, invoke `$suggest-zzzops-work` in apply mode only when both PROJECT policy and `.zzzops/PREFERENCES.json` authorize it. Use the lower cap; never loop-refill or enable preferences.

Stop only for user stop, runtime boundary, required authority/risk, unavailable/unresolved human/external blocker, or no qualifying refill. First make touched goals resumable (next action, evidence, blockers, claim, links, index, history). Apply INITIALIZATION's user-facing contract: report outcome, any one required action, and what remains; summarize checks and keep resume mechanics internal.
