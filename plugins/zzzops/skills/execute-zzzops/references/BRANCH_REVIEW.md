# Branch and human-review lifecycle

Apply PROJECT Git/review policy; capture stays Git-free. Never absorb unrelated work, duplicate a live goal branch/PR, or branch without safe support.

## Topology and overlap

1. Record/reuse one `implementation` identity per goal: branch, base, target, PR, review state/checkpoint.
2. Resolve bases/dependencies from PROJECT. Fallback waits for `done`, then branches from the nearest authorized trunk containing them; read-only preparation cannot start work. `stack_from_reviewed_checkpoint` preserves exact reviewed ancestry and merges dependency first. Unresolved dependencies, change requests, absent checkpoints, or parent conflicts block writes.
3. Apply `parent_pseudo_trunk`/`child_target` recursively. A parent normally owns the pseudo-trunk; children target it and may base on sibling dependencies. Integrate reviewed children in dependency order, then run combined parent checks before upstream review.

Create/resume the recorded branch before edits. Stop on unattributable dirt; record authorized topology exceptions.

Compare overlapping PRs to their immediate base; inherited commits are not overlap. Branches stay exclusive. Sibling/chained PRs may share a target; a child may target its reviewed parent/dependency. Before opening a PR and each review checkpoint, inspect immediate-base history and apply `EXECUTION_STRATEGY.md` final-state cleanup.

After upstream changes, update/retarget downstream branches, recompute immediate-base diffs, resolve conflicts, and rerun affected checks. Recheck target, mergeability, overlap, conflict, and risk before review/integration; advisory overlap waives no proof.

With `pull_request_unit: per_goal`, each source goal owns one branch/PR; size/run does not imply bundling. Combine only under authorized `shared_pull_request`, recording rationale, identity, target, and review effect per goal. Reuse after blockers; parent/child PRs stay distinct. Commit policy is separate. Without PR capability follow PROJECT or block.

## Issue links

Use `Tracks #N`; default-branch closing keywords are insufficient. Only after the target contains the exact head: re-read the issue, record done/merge evidence, run `gh issue close N --reason completed`, and verify. Never close stacked/incomplete work.

## Review gate

At each checkpoint, use PROJECT bounded consolidated reads for review, unresolved threads/comments, checks, and exact head. Classify actionable, resolved/outdated, discussion, automated, ambiguous, or unauthorized; reuse the result and record actionable file/line. Poll only under enabled human-unblock watch.

Change only authorized actionable feedback after re-reading the recorded head/threads. After review feedback, reverify, clean immediate-base history, record the new exact checkpoint, and invalidate approval; code changes do not resolve provider threads. Persist ambiguous, expanding, conflicting, or unauthorized feedback as a categorized blocker.

After implementation, checks, comments, and self-review pass, apply PROJECT `review_gate`. `human_after_checks` means record links/checks/risks and present the review action/resume condition, but do not merge or mark done. Omit hashes/mechanics unless useful or requested.

- Apply `pr_approval`/`conversational_approval`; never self-approve or bypass required checks.
- Changes requested: retain branch, implement/reverify, then create a new checkpoint.
- Approved: retain resolution and apply `merge_after_approval`. Before merging re-read exact head, feedback, checks, target, mergeability, and permission. Merge only with every gate/authority; mergeability is not authorization. Verify target ancestry/post-merge checks and record evidence. Missing approval/checks/conflict resolution/authority is a precise blocker; missing merge authority is `access-approval`.

Review a parent only after required children integrate and combined regressions, parent criteria, and parent self-review pass.
