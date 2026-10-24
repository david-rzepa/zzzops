# #632 canonical coordinator worktree: reviewed slice v2

This document covers only workspace identity and routing. #632's always-on instruction, break-glass, terminal reachability/closure, and dirty-worktree audit remain separate acceptance slices.

## Observed state

The repository primary worktree is on `fix/522`, while the unique registered worktree on the reviewed integration branch `dev` is `/home/dave/Work/dev/zzzops-dev-integration`. The current gateway permits shared goal administration from feature worktrees. A disposable-repo probe will make a feature-worktree capture request reach the provider before the fix, then prove it is refused with zero provider writes afterward.

## Identity

Resolve the effective repository worktree from the command's parsed `--repo` target (or the dispatch default), using `git -C <effective-repo> rev-parse --show-toplevel` and `--git-common-dir`. Never infer it from process cwd after `--repo` has been parsed. Enumerate registered worktrees with `git -C <effective-repo> worktree list --porcelain`; do not run prune or move a worktree. Bind repository identity, common Git directory, effective root, selected coordinator root, integration branch, and exact branch/head to one invocation.

Once a reviewed policy exists, require an explicit reviewed integration target. Select exactly one registered worktree checked out on that branch; here `release_planning.integration_branch=dev`. If release planning is disabled but no reviewed integration target is recorded elsewhere, refuse shared administration with a policy-repair step; do not silently choose the primary feature worktree. Missing, detached, duplicated, stale, or mismatched registered candidates fail closed. Recheck at effect dispatch, not only at preview.

Before a reviewed policy exists, permit only initialization, installation validation, and policy setup from the registered primary worktree as a provisional coordinator. Goal/provider administration remains unavailable until integration authority is reviewed. Policy adoption switches subsequent requests to the selected integration worktree without relocating dirty data or changing Git refs.

## Effect boundary

Centralize a workspace-effect classification at the top-level CLI dispatch and the public workflow gateway. Every entrypoint must declare `read`, `local-scratch`, `shared-admin`, or `managed-attempt`; unknown or unclassified operations default to `shared-admin` and require coordinator. Audit all direct subcommands and workflow operation IDs before enabling the guard. `capture_propose`, exact relationship previews, and historical reads are `read`; goal create/transition, review/apply events, graph/policy/migration/portfolio/lease/installation mutations, stack_prepare/advance, and branch/worktree administration are `shared-admin` unless an explicitly reviewed managed-attempt contract owns them. `local-scratch` writes go under the Git common directory and cannot dirty a feature worktree. Worker-local Git file edits under #566 remain separate from shared goal state.

If a shared-admin call arrives from a noncanonical worktree, return a structured route step with canonical absolute `cwd`, effective repository identity, integration target, and the exact original command/input/runtime paths. Do not dispatch provider writes or alter request IDs, payload bytes, or working-input files. A prior uncertain effect must use its existing status/reconciliation command before any new request; routing never mints a replacement. Read-only calls from any registered worktree return the same coordinator path for their eventual mutation.

## Falsifiable first probe and verification

In a disposable repository with primary feature checkout and separate `dev` worktree, public capture proposal from feature remains read-only. Exact capture submission from feature currently reaches the fake provider. After the guard it returns a workspace-route step and zero provider writes; the same frozen submission from `dev` succeeds once and exact replay is idempotent. With process cwd on `dev` and `--repo <feature>`, feature is rejected; with process cwd on feature and `--repo <dev>`, dev is accepted. Missing/ambiguous integration worktree blocks with exact recovery. Pre-policy bootstrap from registered primary succeeds while goal administration does not. Paths with spaces and detached worktrees are covered.

Before marking this slice reviewed, enumerate the actual CLI subcommands and workflow operations against the effect matrix; direct entrypoints outside the gateway must not silently bypass it. The gateway must not call Git with implicit process cwd for worktree-sensitive operations.
