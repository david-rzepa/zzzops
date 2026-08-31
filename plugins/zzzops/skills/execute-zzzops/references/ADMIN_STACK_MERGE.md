# Guarded administrator fallback for native stack merges

Load this only when an otherwise-ready native GitHub stack cannot merge because a repository rule needs an administrator bypass. This is a destructive, non-atomic fallback—not the normal merge path.

## Default and stop boundary

1. Reverify the stack identity, same-repository topology, trunk, ordered PRs and immediate bases, every [[exact head]](../../../concepts/exact-head.md), successful required check, resolved feedback, review decision, mergeability, and project merge/release authority.
2. Prefer the atomic asynchronous stack merge (`gh stack merge ... --yes`; GitHub uses `merge-async`). It either merges every PR through the selected layer or none. The observed rule failure contains `approving review is required`.
3. Do not retry with ordinary `gh pr merge --admin` while membership exists: stacked PRs require the `asynchronous merge endpoint`, whose documented options provide no administrator bypass. Preserve the stack and record one action unless the user explicitly authorized administrator bypass for this exact current stack.
4. Never infer bypass authority from conversational approval, ordinary merge authority, repository administration, or an earlier stack. Never change repository rules or install tooling as a workaround.

## Authorized fallback

Before mutation, explain that unstacking removes GitHub stack metadata but retains the branches and PRs, and that later merges are no longer atomic. Then:

1. Re-read provider state immediately. Stop on a changed head, failed check, pending check, unresolved feedback, draft/closed/unmergeable PR, altered membership/base/trunk, missing exact scoped authority, cross-repository topology, or any safety, privacy, release, or project-policy gate.
2. Run `gh stack unstack STACK_NUMBER` without `--local`. Require provider readback that every intended PR is unstacked while its branch, PR, exact head, and immediate base still match. Any partial or unverifiable unstack stops.
3. Merge the bottom PR first with the authorized method, `--admin`, and `--match-head-commit EXACT_SHA`. Read back that its exact head reached the trunk before changing goal state.
4. Re-read the next PR. Require its expected retarget, exact head, clean mergeability, successful checks, resolved feedback, and independently reviewed diff; then repeat bottom-to-top. Never reuse an earlier read.
5. After each merge, persist the actual provider state and goal result. If a later layer fails, keep every completed merge recorded, stop the remaining layers, and give the exact recoverable next action. Never report the fallback as atomic or retry blindly.

The fallback cannot bypass failed or pending checks, changed heads, unresolved feedback, safety/privacy constraints, merge or release authority, or any unrelated requirement.
