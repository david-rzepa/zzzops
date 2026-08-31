# Branch and human-review lifecycle

Apply PROJECT Git/review policy; capture stays Git-free. Never absorb unrelated work, duplicate a live goal branch/PR, or branch without safe support.

## Topology and overlap

1. Record/reuse one `implementation` identity per goal: branch, base, target, PR, review state/checkpoint.
2. Resolve bases/dependencies from PROJECT. Missing dependency gates or base rules block affected writes for policy review; read-only preparation cannot start work. `stack_from_reviewed_checkpoint` preserves exact reviewed ancestry and merges dependency first. Unresolved dependencies, change requests, absent checkpoints, or parent conflicts block writes.
3. Apply `parent_pseudo_trunk`/`child_target` recursively. A parent normally owns the pseudo-trunk; children target it and may base on sibling dependencies. Integrate reviewed children in dependency order, then run combined parent checks before upstream review.

Create/resume the recorded branch before edits. Stop on unattributable dirt; record authorized topology exceptions.

Compare overlapping PRs to their immediate base; inherited commits are not overlap. Branches stay exclusive. Sibling PRs may share a target; a child may target its reviewed parent/dependency. Before opening a PR and each review checkpoint, inspect immediate-base history and apply `EXECUTION_STRATEGY.md` final-state cleanup.

Apply PROJECT's PR mode. For native GitHub stacks, first check the documented `gh` minimum and official `gh stack` capability. Installing/upgrading host tooling needs explicit approval. Link ordered same-repository PRs bottom-to-top with noninteractive `gh stack link --base TRUNK ...`; then require provider readback proving one stack identity, trunk, size/positions, and every immediate PR base. Capability absence, denied installation, cross-repository topology, command failure, or unverifiable readback means the PRs are **chained PRs**, never claimed as stacked; follow PROJECT's fallback or block. Preserve branch/PR ownership, exact-head evidence, checks, review, merge, and release authority in either mode.

For verified-checkpoint continuation, exhaustion handoff, or ancestor feedback, follow [the PR review queue](REVIEW_QUEUE.md). Recheck target, mergeability, immediate-base diff, overlap, conflict, and risk before review/integration.

With `pull_request_unit: per_goal`, each source goal owns one branch/PR; size/run does not imply bundling. Combine only under authorized `shared_pull_request`, recording rationale, identity, target, and review effect per goal. Reuse after blockers; parent/child PRs stay distinct. Commit policy is separate. Without PR capability follow PROJECT or block.

## Issue links

Use `Tracks #N`; default-branch closing keywords are insufficient. Only after the target contains the [[exact head]](../../../concepts/exact-head.md): re-read the issue, record done/merge evidence, run `gh issue close N --reason completed`, and verify. Never close stacked/incomplete work.

## Review gate

At each checkpoint, use one PROJECT-bounded consolidated read for reviews, unresolved threads/comments, checks, and exact head. Classify feedback; persist ambiguous, expanding, conflicting, or unauthorized items as blockers. Change only authorized actionable feedback, then reverify, clean history, replace the checkpoint, and invalidate stale approval; code changes do not resolve provider threads.

After implementation, checks, comments, and self-review pass, apply PROJECT `review_gate` through [the PR review queue](REVIEW_QUEUE.md). `human_at_exhaustion` queues review and continues allowed work; `human_after_checks` surfaces the review action immediately. Never self-approve, bypass checks, merge without every gate, or mark pending work done.

Review a parent only after required children integrate and combined regressions, parent criteria, and parent self-review pass.
