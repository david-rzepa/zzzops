# Continue and reconcile the PR review queue

Load this only after a verified PR checkpoint, at true queue exhaustion, or when ancestor review changes stacked work. PROJECT policy controls every gate.

## Verified checkpoint

`human_at_exhaustion` uses one canonical checkpoint transition: `status: blocked`, no claim, [[exact head]](../../../concepts/exact-head.md), pending review, checks/base/risks/PR, `human-action`/`continue-bounded`; release reservation. Continue permitted descendants. Do not request conversational approval or wait for review.

For `human_after_checks`, surface that goal's review action immediately. A separate `stack_from_reviewed_checkpoint` setting may still permit descendants; completed-dependency policy waits. Neither mode marks the goal done, self-approves, merges, bypasses checks, or weakens release authority.

After every gate passes, prefer atomic stack merge. A rule rejection preserves it unless exact administrator-bypass authority permits the [guarded fallback](ADMIN_STACK_MERGE.md).

## Exhaustion handoff

<!-- entropy-exhaustion-protocol:start -->
| State | Guard | Operation | Success | Failure |
| --- | --- | --- | --- | --- |
| `mark` | `observed=verified_checkpoint,integrated_change,completed_goal` | `entropy_mark_exact` | `recorded:cycle,duplicate:cycle` | `actionable_stop` |
| `exhaustion` | `checkpoint_refreshed=true,safe_work=false` | `entropy_status_recent` | `due_unattempted:review,due_attempted:actionable_stop,not_due:refill` | `actionable_stop` |
| `review` | `due=true,attempted_current_exact_state=false` | `entropy_review_automatic_recent_once` | `clean:refill,findings:refill` | `actionable_stop` |
| `refill` | `review=clean,findings,not_due;refill_used=false,true` | `refill_gate_once` | `work:cycle,empty:handoff,disabled:handoff,used:handoff` | `actionable_stop` |
| `handoff` | `safe_work=false,refill=used,disabled,empty` | `final_review_handoff` | `ready:stop` | `actionable_stop` |
<!-- entropy-exhaustion-protocol:meta qualifying=verified_checkpoint,integrated_change,completed_goal;nonqualifying=claim,reservation,schema_repair,blocker_update,administrative_transition,new_suggested_goal;review_may_call_execute=false;same_exact_state_may_review_again=false;order=entropy_status_recent<entropy_review_automatic_recent_once<refill_gate_once<final_review_handoff;mark_before_next_exhaustion=true -->
<!-- entropy-exhaustion-protocol:end -->

Apply this order exactly after refreshed goals/dependencies and rebuilt blockers prove no safe `triage`, `prepare`, or `write` work remains:

1. Run `entropy review status` once against the current exact event frontier from [the event contract](ENTROPY_OBSERVATIONS.md). Freeze that frontier as the session attempt key.
2. On `due:false`, do not load or invoke the entropy-review skill. On `due:true`, stop if that exact frontier was already attempted in this session. Otherwise record the exact-frontier attempt first, then invoke `$review-zzzops-entropy automatic recent` exactly once. Show the frozen recent scope and its evidenced findings or clean result. A genuinely new exact frontier may be checked and reviewed at a later exhaustion in the same session.
3. Interruption, provider failure, malformed state, or drift leaves coverage due. Persist an actionable continuation, stop before refill/final-exhaustion claims, and never retry the same event set or alter identifiers in this session.
4. Only after the exact completion receipt succeeds, apply at most one exhausted-queue refill when PROJECT explicitly enables it. Fixed review findings reuse suggestion category/cap and goal-creation authority; the automatic review itself grants none. Post-receipt review capture consumes the session refill. If that capture fails, persist the frozen finding set and an actionable continuation. Otherwise `$suggest-zzzops-work` may run once under the same policy.
5. If refill creates work, return once to ordinary selection. Entropy review never invokes execute, execute never recursively invokes the same reviewed event set, and newly suggested goals do not themselves create review events.
6. When no work was created, present one concise review queue in dependency/merge order. For each PR give its goal link, PR link, immediate target, check state, material risk or decision, and the action that resumes work. Separate non-review authority blockers. Do not ask for commands such as `approve goal 1`; the repository's PR review UI is the approval surface.

The exact-frontier attempt guard is session-local; durable exact receipts alone establish coverage. Never retry the same frontier or enable or loop-refill. Once the session refill has been used, its gate routes every later exhaustion directly to handoff.

## Ancestor feedback

After an ancestor checkpoint changes:

1. stop writes on affected descendants and read the ancestor feedback/exact head once;
2. implement only authorized feedback, reverify the ancestor, and record its new checkpoint;
3. invalidate every affected descendant checkpoint and approval;
4. update bases/targets in dependency order with `gh stack rebase`/`push` when tracked, otherwise guarded Git; require provider readback for native stacks or keep chained PRs explicit; recompute each immediate-base diff and resolve only authorized conflicts;
5. rerun each affected narrow probe and required check, then record replacement checkpoints; and
6. block only the affected chain when reconciliation is unsafe, unauthorized, ambiguous, or fails, while continuing unrelated work.

Never force-rewrite shared, approved, integrated, default-branch, or ambiguously owned history. An exclusively owned unintegrated descendant may be rebased or rewritten only under the reviewed final-history policy and `--force-with-lease` safeguards.
