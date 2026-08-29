# Continue and reconcile the PR review queue

Load this only after a verified PR checkpoint, at true queue exhaustion, or when ancestor review changes stacked work. PROJECT policy controls every gate.

## Verified checkpoint

For `human_at_exhaustion`, record the [[exact head]](../../../concepts/exact-head.md), checks, immediate base/target, material risks, PR, and a `human-action` review blocker with `continue-bounded`. Release the goal reservation and continue every descendant whose policy-derived `work_state` permits checkpoint stacking. Do not request conversational approval or wait merely because review is pending.

For `human_after_checks`, surface that goal's review action immediately. A separate `stack_from_reviewed_checkpoint` setting may still permit descendants; completed-dependency policy waits. Neither mode marks the goal done, self-approves, merges, bypasses checks, or weakens release authority.

## Exhaustion handoff

When no safe `triage`, `prepare`, or `write` work remains, present one concise review queue in dependency/merge order. For each PR give its goal link, PR link, immediate target, check state, material risk or decision, and the action that resumes work. Separate non-review authority blockers. Do not ask for commands such as `approve goal 1`; the repository's PR review UI is the approval surface.

## Ancestor feedback

After an ancestor checkpoint changes:

1. stop writes on affected descendants and read the ancestor feedback/exact head once;
2. implement only authorized feedback, reverify the ancestor, and record its new checkpoint;
3. invalidate every affected descendant checkpoint and approval;
4. update bases and PR targets in dependency order, using noninteractive `gh stack rebase`/`push` when locally tracked, otherwise guarded Git rebase/push; re-link and require provider readback for native stacks, and keep chained PRs explicit; recompute each immediate-base diff and resolve conflicts only when authorized;
5. rerun each affected narrow probe and required check, then record replacement checkpoints; and
6. block only the affected chain when reconciliation is unsafe, unauthorized, ambiguous, or fails, while continuing unrelated work.

Never force-rewrite shared, approved, integrated, default-branch, or ambiguously owned history. An exclusively owned unintegrated descendant may be rebased or rewritten only under the reviewed final-history policy and `--force-with-lease` safeguards.
