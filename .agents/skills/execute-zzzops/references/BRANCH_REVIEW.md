# Branch and human-review lifecycle

Apply reviewed PROJECT Git/review policy to source-changing goals. Capture stays Git-free. Never absorb unrelated work, duplicate a live goal branch/PR, or branch without safe repository support.

## Topology and overlap

1. Record/reuse one `implementation` identity per goal: branch, base, target, PR, review state/checkpoint.
2. Resolve bases/dependencies from PROJECT. The fallback waits for dependencies to be `done`, then branches from the nearest authorized trunk containing them; read-only preparation cannot claim, edit, branch, or mark work started. `stack_from_reviewed_checkpoint` preserves the edge/exact reviewed ancestry and merges dependency before child. Unresolved dependencies, change requests, missing checkpoints, or conflicting parent changes block writes.
3. Apply `parent_pseudo_trunk`/`child_target` recursively. By default a parent with children owns their pseudo-trunk; children target the nearest parent and may base on a sibling dependency. Integrate reviewed children there in dependency order, then run combined checks/parent criteria before presenting upstream.

Create/resume the recorded branch before edits. Stop on unattributable dirt; record authorized topology exceptions.

Before implementation inspect open PRs overlapping advisory paths/target. Compare each PR with its immediate base; inherited upstream commits are not child overlap. Branches stay exclusive. Sibling/chained PRs may share an eventual target; a child may target its reviewed parent/dependency.

When upstream changes/merges, update or retarget downstream branches, recompute immediate-base diffs, resolve conflicts, and rerun affected checks. Repeat target, mergeability, overlap, conflict, and risk inspection before review/integration. Advisory overlap never waives reconciliation/regression proof.

Under `pull_request_unit: per_goal`, each source goal owns one branch/PR; size or one run never implies bundling. Combine only under authorized `shared_pull_request`, recording rationale, identity, target, and review effect on every goal. Reuse identities after blockers. Parent/child PRs remain distinct and follow resolved topology. A PR may hold coherent commits; commit policy is separate. Without PR capability, follow PROJECT integration policy or block on missing required authority/capability.

## Issue links

Use `Tracks #N`; default-branch closing keywords are insufficient. Only after the target contains the exact head: re-read the issue, record done/merge evidence, run `gh issue close N --reason completed`, and verify. Never close stacked/incomplete work.

## Review gate

At each checkpoint, perform PROJECT `review_state_reads_per_checkpoint` bounded consolidated reads of review state, unresolved inline threads, relevant comments, PR checks, and exact head. Prefer thread-aware data; classify actionable, resolved/outdated, discussion-only, automated, ambiguous, or unauthorized. Reuse the one result for that checkpoint instead of issuing equivalent separate reads. Record actionable file/line context. Poll only under an enabled human-unblock watch.

Change only authorized actionable feedback on the recorded branch/PR. Re-read head/threads first; after each verified change rerun self-review/checks, record the new exact checkpoint, and invalidate approval. Ambiguous, expanding, conflicting, or unauthorized feedback becomes a categorized blocker. Code changes do not resolve provider threads.

After implementation, checks, comments, and self-review pass, apply PROJECT `review_gate`. `human_after_checks` means record links/checks/risks and present the review action/resume condition, but do not merge or mark done. Omit hashes/mechanics unless useful or requested.

- Apply `pr_approval`/`conversational_approval`; never self-approve or bypass required checks.
- Changes requested: retain branch, implement/reverify, then create a new checkpoint.
- Approved: retain resolution and apply `merge_after_approval`. Before merging re-read exact head, feedback, checks, target, mergeability, and permission. Merge only with every gate/authority; mergeability is not authorization. Verify target ancestry/post-merge checks and record evidence. Missing approval/checks/conflict resolution/authority is a precise blocker; missing merge authority is `access-approval`.

Review a parent only after required children integrate and combined regressions, parent criteria, and parent self-review pass.
