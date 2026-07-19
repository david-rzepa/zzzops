# Branch and human-review lifecycle

Use this only for source-changing goals and apply reviewed PROJECT Git/review policy. Capture remains Git-free. Never absorb unrelated work, duplicate a live goal branch/PR, or branch where the repository cannot safely support it.

## Resolve topology

1. Record one stable `implementation` identity per goal: branch, base, integration target, PR, and review status/checkpoint. Reuse it on resume.
2. Resolve root base from PROJECT `branch_base`; dependent ancestry from `dependency_base`, `multiple_dependency_base`, and `review_pending_dependency`. Under the installed fallback, use the nearest authorized trunk, dependency branch, or a reviewed base containing every required ancestor. `stack_from_reviewed_checkpoint` deliberately separates execution order from merge order: a dependency awaiting only human review/merge stays blocked itself, but its exact technically ready checkpoint makes the child actionable. Stack the child branch/PR and preserve the dependency edge, ancestry, and merge/review order. The dependency must merge into its upstream target before the child is retargeted or merged upstream—not before child implementation or review. An unresolved technical dependency, changes request, missing checkpoint, or conflicting parent change still blocks the child; rebase and retest as its parent advances.
3. Apply PROJECT `parent_pseudo_trunk` and `child_target` recursively. Under the installed fallback, a goal with children owns their pseudo-trunk even without a direct commit; a child targets the nearest parent pseudo-trunk and may base on a sibling dependency branch.
4. Follow policy integration order. Under the installed fallback, integrate reviewed children into their parent pseudo-trunk in dependency order and run combined checks/parent criteria before presenting the parent upstream.

Create/resume the recorded branch before source edits. If dirty work cannot be proven to belong to this goal, stop and ask. Repository rules or explicit instructions may justify a different topology or no branch; record the evidence and decision.

When PROJECT `pull_request_unit` is `per_goal`, each source-changing goal owns one branch and one PR when the repository supports PRs. Related/small goals or one execute run do not imply bundling. A repository rule or explicit user instruction may authorize a shared PR only under `shared_pull_request`; before combining work, record the override/rationale, shared branch/PR, target, and review effect in every affected goal. Reuse that identity after blockers—never open a duplicate. Parent and child goals keep distinct PRs targeting the resolved pseudo-trunk/dependency topology. One PR may retain multiple coherent semantic commits; commit/squash policy is separate. Capture stays Git-free, and repositories without PR capability follow reviewed PROJECT integration policy or block when required authority/capability is missing.

## Canonical issue links

Every implementation PR uses `Tracks #N`. Do not rely on closing keywords: GitHub applies them only on default-branch merges. After verifying the exact head is in the integration target, re-read the issue, record `done`/merge evidence, run `gh issue close N --reason completed`, and verify closure. Stacked or incomplete PRs never close an issue.

## Review gate

At each review checkpoint for a recorded PR, apply PROJECT `review_state_reads_per_checkpoint`; the installed fallback makes one bounded provider read of review state, unresolved inline threads, and relevant top-level comments. Prefer thread-aware data; classify each as actionable, resolved/outdated, discussion-only, automated, ambiguous, or unauthorized. Record concise actionable file/line context on the canonical goal. Do not poll outside an enabled PROJECT human-unblock watch.

Address authorized actionable feedback only on the recorded branch/PR. Re-read the PR head and threads before mutation; after each small verified change, repeat self-review and required checks, record the new exact head/checkpoint, and invalidate prior approval. Ambiguous, scope-expanding, policy-conflicting, or unauthorized feedback is a categorized blocker; code changes never imply a provider thread was resolved.

After implementation, checks, comments, and self-review pass, apply PROJECT `review_gate`. `human_after_checks` records full links/checks/risks internally; do not merge or mark done. Tell the user the change is ready, give the review link/action, and say what resumes. Omit hashes and review mechanics unless decision-relevant, diagnostic, or requested.

- Apply PROJECT `pr_approval` and `conversational_approval`: where PR UI approval is required, open/update the correct PR and accept only valid approval with required checks; never self-approve or bypass policy. Otherwise explicit conversational approval may resolve the gate when policy permits it.
- Changes requested: keep the branch, implement/reverify, and create a new review checkpoint.
- Approved: retain the blocker resolution and apply PROJECT `merge_after_approval`; before merging, re-read the exact PR head, actionable feedback, checks, target, mergeability, and permission. Merge only when every policy gate and authority is present; `mergeable` is not authorization. Verify the target contains the reviewed head and required post-merge checks, then record merge evidence and cycle. Missing approval, clean checks, conflict resolution, or merge authority becomes the precise categorized blocker; Missing merge authority is an `access-approval` blocker.

The parent receives its own review gate only after required children are integrated, combined regression passes, parent criteria pass, and parent self-review completes.
