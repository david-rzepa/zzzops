# Execute goals

“All goals” means cycle until no safe useful work remains; it grants no authority.

## Select

1. Create a run ID and inspect callable usage per `.zzzops/rules/USAGE_ACCOUNTING.md`.
2. Read project charter, `.zzzops/PREFERENCES.json`, the canonical backend portfolio, and selection-critical relationships/claims/reviews. Repair only derived drift needed to select safely. If the user is present and the human queue is non-empty, run `UNBLOCK.md` first.
3. Route `new` goals through `CREATE.md` according to PROJECT triage/continuation policy.
4. Actionable = `ready` or resumable `in_progress`, authorized concrete next action, gates satisfied, no invalidating blocker/live foreign claim. Recheck blocked work only on its trigger.
5. Rank by evidenced charter/KPI movement and unlock value, then apply PROJECT priority, easy-win, tie-break, and resume policy.

## Execute

1. Re-read goal, parent, dependencies, rules, and artifacts; claim it with expiry/checkpoint.
2. For source changes, establish/resume the policy-selected topology from `BRANCH_REVIEW.md` and persist branch/base/target before editing. Then follow `.zzzops/rules/EXECUTION_STRATEGY.md`: capture baseline; implement one smallest falsifiable chunk; run/inspect/record the real probe before continuing; widen only after proof.
3. Work to a verified checkpoint without silent scope expansion. Classify discoveries as scope, checklist, child, dependency, or root. Apply PROJECT test-bug policy; never hide a failure, weaken the test, or expand authority silently.
4. Persist evidence and usage at natural checkpoints. Follow preference-limited parallel/worktree rules; coordinator owns ZzzOps state and integration.

## Block, complete, cycle

- On a blocker, follow `.zzzops/rules/BLOCKERS.md`: record continuation, ask when useful, do only bounded safe work, then keep active or block/release claim and switch.
- Before `done`, cite observed before/after evidence for each criterion; verify required children, blockers, and relevant checks; state anything unobserved. Build/lint/types/code review do not prove runtime behavior unless that is the criterion. Source-changing work then enters the `BRANCH_REVIEW.md` human gate; technical completion alone is not `done`.
- Follow PROJECT Git/review/commit policy, staging only authorized implementation and pending local ZzzOps state; a GitHub-only state change never causes an empty commit. Recheck parent criteria and unlocked dependents; repeat upward, then select again.

## Exhaustion and handoff

When no work is actionable, rebuild the human queue and apply PROJECT blocker-interview/continuation policy through `UNBLOCK.md`; persist answers and retry when policy restores work.

If still empty, invoke `$suggest-zzzops-work` in apply mode only when both PROJECT policy and `.zzzops/PREFERENCES.json` authorize it. Use the lower cap; never loop-refill or enable preferences.

Stop only for user stop, runtime boundary, required authority/risk, unavailable/unresolved human/external blocker, or no qualifying refill. First make touched goals resumable (next action, evidence, blockers, claim, links, index, history, usage). Report outcomes, human interview/refill results, queue, and stop reason.
