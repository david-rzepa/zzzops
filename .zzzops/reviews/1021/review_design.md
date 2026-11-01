# G1021 design review

**Verdict: approved.** I checked the design's claims against the code at read_dev (6747a5e) and they hold. The approach is deterministic, adds no GitHub calls, and its risks are named and fail safe. I have no open findings. There are two notes for the implementer at the end; neither changes the design.

## The corrected premise is right

- `ops/integrate.py` lines 171-175 at read_dev already return `conflict` on `base` when `mergeable == CONFLICTING` or `mergeStateStatus == DIRTY`. The check is guarded by `v["headRefOid"] == H`.
- `.agents/test_engine_github.py:134` `test_conflicting_pr_into_dev_is_a_base_finding` covers this case.
- The fake gh (`.agents/engine_fake_gh.py` `mergeability`) computes `merge-tree` on every view with no lag. That is why no test could catch the `UNKNOWN` case.
- The goal records match the design's account. G1016 integrate is `blocked/time`, "required checks pending: dev-required-tests", `polls 1`, `repeats 1`, `retry_after 06:23:02Z`. G1000 integrate is the same, with retry 07:01:47Z, and its retry never ran. Both `base` records later blocked on real rebase conflicts with `onto` = 6747a5e. That confirms the PRs truly conflicted.
- When `headRefOid != H`, the current code skips the conflict check, and the rollup loop leaves every required check "pending". So the design's second hole is real.

## The local `merge-tree` pre-check

- **Semantics.** It is limited to `target == I` (no stack). In that case the PR's base on GitHub is `I`, and `snap.integration` is this invocation's fetch of `refs/remotes/R/I` (store.py:205). So `merge-tree --write-tree <snap.integration> <H>` is exactly GitHub's 3-way merge. It computes its own merge base, and `H` carries no review commits. Stacked goals (target `zzzops/pr/gD` or `zzzops/stack/gG`) are rightly excluded: a check against `I` would be the wrong comparison there. When a dependency merges, `base`'s `merges` input changes, the stack drops, and the target becomes `I`, so the check then applies. The stacked path (5a) gets no conflict check. That is unchanged behaviour and out of scope.
- **Git version.** `--write-tree` and `--name-only` need Git >= 2.38. ZzzOps already requires Git >= 2.41 (`engine/gitrun.py` `MIN_GIT`), and `base.combine` already uses `merge-tree --write-tree`. No new requirement.
- **Cost.** One in-memory merge per integrate run (one per poll). It writes no worktree or ref, and costs nothing next to the gh calls.
- **No false-positive loop.** A false local "conflict" sends the goal to `base`, which rebases onto the tip. After that, `I` is an ancestor of `H`, so both `merge-tree` and GitHub are trivially clean. A false GitHub-only conflict likewise cannot recur once `base` is on the tip. Neither disagreement can loop.

## Bounded waits

- `ctx.wait` (`ops/run.py:58`) carries `{pending_since, polls}` and escalates to a human after `ci_timeout_minutes`, so the `UNKNOWN` and head-not-seen waits are bounded.
- The two state shapes do not mix. The checks wait reads `op_state` only when `op_state.head == H`. `ctx.wait`'s state has no `head`, so a run going from the `UNKNOWN` wait to the checks wait starts a fresh `pending_since`. A run going the other way inherits `polls`. That only lengthens the backoff, and the timeout still bounds it. Acceptable.

## The no-checks human question

- The timing is right. The backoff is 5, 10, ... minutes, so polls at t = 0, 5 and 15 put the question on the third poll.
- Gating on an empty `statusCheckRollup` is the right signal. Actions creates queued runs as soon as a workflow triggers, so a slow queue does not trip it. A non-empty rollup without the required check keeps the existing 120-minute path, which the design states.
- An answer clears `op_state`, so "wait" re-arms the 15-minute window. This also covers the spec's "not mergeable never just waits again": a conflicting PR is now caught before this branch is reached.

## Not fingerprinting the integration tip in `base`

Sound. `base`'s inputs are only `heads`, `merges` and context summaries. Both goals' `base` `input_fp` values are identical (a63dd4f...), which fits dependency-free goals. The frontier marks a node stale only when its `input_fp` changes. Making the tip an input would invalidate every in-flight goal on every merge into dev, and that would cascade through `base_commit` into `implement`, `integrate` and `merge` for goals that do not conflict. Detecting the conflict at integrate (new) and at merge (`CONFLICTING` or `BEHIND`, existing) is the right place. It also answers the spec's "explain why".

## Implementer notes (not findings)

1. Keep the order the Approach lists: head-not-seen wait, then GitHub conflict, then `UNKNOWN`. The prose says to "drop the `headRefOid == H` guard because a conflicting PR conflicts whatever head GitHub shows". That is not true for a stale head: the old head can conflict while the rebased `H` does not. It is the ordering that makes dropping the guard harmless. If the conflict branch ran before the head-not-seen wait, a stale `CONFLICTING` could send a goal that was already rebased back to `base` for nothing.
2. Use `merge-tree --write-tree --name-only --no-messages`, and skip the first line (the tree OID) when building the file list. Without `--no-messages`, informational lines follow the file list.
