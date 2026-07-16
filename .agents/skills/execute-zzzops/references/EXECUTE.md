# Execute goals

“All goals” means cycle until no safe useful work remains; it grants no authority.

## Select

1. Create a run ID and inspect callable usage per `.zzzops/rules/USAGE_ACCOUNTING.md`.
2. Read project charter, `.zzzops/PREFERENCES.json`, index, goals, and selection-critical relationships/claims/reviews. Repair only drift needed to select safely. If the user is present and the human queue is non-empty, run `UNBLOCK.md` first.
3. Triage every `new` goal via `CREATE.md` before steady execution.
4. Actionable = `ready` or resumable `in_progress`, authorized concrete next action, gates satisfied, no invalidating blocker/live foreign claim. Recheck blocked work only on its trigger.
5. Choose `P0`, then greatest evidenced project/KPI movement and unlock value. At run start allow at most two verified `XS/S` wins, then substantive work. Tie-break priority, value, justified date, unlocks, smaller difficulty, age; prefer valid resumed work.

## Execute

1. Re-read goal, parent, dependencies, rules, and artifacts; claim it with expiry/checkpoint.
2. Follow `.zzzops/rules/EXECUTION_STRATEGY.md`: capture baseline; implement one smallest falsifiable chunk; run/inspect/record the real probe before continuing; widen only after proof. Build a narrow harness/debug adapter/scoped MCP server when needed rather than infer behavior from code.
3. Work to a verified checkpoint without silent scope expansion. Classify discoveries as scope, checklist, child, dependency, or root. For out-of-scope bugs found by tests, create a separate human-blocked TODO; do not fix before direction.
4. Persist evidence and usage at natural checkpoints. Follow preference-limited parallel/worktree rules; coordinator owns BedOps state and integration.

## Block, complete, cycle

- On a blocker, follow `.zzzops/rules/BLOCKERS.md`: record continuation, ask when useful, do only bounded safe work, then keep active or block/release claim and switch.
- Before `done`, cite observed before/after evidence for each criterion; verify required children, blockers, and relevant checks; state anything unobserved. Build/lint/types/code review do not prove runtime behavior unless that is the criterion. Update state/history/index/usage and clear claim.
- Commit each completed sub-goal separately on the current branch, staging only its scope/state and using `type(scope): outcome` Conventional Commit syntax. Recheck parent criteria and unlocked dependents; repeat upward, then select again.

## Exhaustion and handoff

When no work is actionable, rebuild the human queue. Interview an available user via `UNBLOCK.md`; apply answers and retry until work resumes or no further answer is available.

If still empty, once per run invoke `$suggest-project-work` in apply mode only for enabled `.zzzops/PREFERENCES.json` categories. Add at most `max_goals_per_refill` high-confidence, evidenced, non-duplicate goals; triage and resume. Never loop-refill or enable preferences.

Stop only for user stop, runtime boundary, required authority/risk, unavailable/unresolved human/external blocker, or no qualifying refill. First make touched goals resumable (next action, evidence, blockers, claim, links, index, history, usage). Report outcomes, human interview/refill results, queue, and stop reason.
