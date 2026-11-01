# G1021 design: integrate must detect a conflicting PR instead of waiting for checks

## Outcome

When a goal's PR into the integration branch cannot merge because it conflicts, `git.integrate` says so on its first run. It finishes not-ok with a `conflict` finding on its `base` input, so `base` re-runs and rebases (or asks an agent to resolve the rebase conflict). It never reports "required checks pending" for a PR that GitHub will never run checks on. A checks wait that sees no checks at all stops early with a specific question. It does not wait out the full `ci_timeout_minutes` (120).

## What actually happened (correcting the spec's premise)

The spec says integrate does not handle CONFLICTING/DIRTY. It does, and has since the op was written (840023d). At read_dev `ops/integrate.py` lines 172-175 return the same `conflict` finding on `base` that `github.merge` returns. The existing test `test_conflicting_pr_into_dev_is_a_base_finding` covers it. The bug is narrower than that.

Evidence from the goal records (`refs/zzzops/goal/origin/g1016`, `g1000`) and GitHub:

- dev reached 6747a5e (#746) at 05:59Z. G1016's integrate started at 06:18:02Z with `base` = 54d7e83, which was already stale. `gh pr create` opened #747 at 06:18:08Z, and the op then called `pr view` straight away. G1000/#748 followed the same pattern at 06:56Z.
- GitHub computes `mergeable` lazily. The first read of a PR that was just created or pushed returns `UNKNOWN`. That read also starts the computation.
- Integrate only checks for `CONFLICTING`/`DIRTY`. When the value is `UNKNOWN`, it skips the conflict check and goes on to the required-checks logic. No check exists yet, so every required check counts as pending and it records `required checks pending: dev-required-tests` with a 5-minute retry. Both records show `attempt 1, polls 1, repeats 1`: the first and only run. Today the PRs read `CONFLICTING`/`DIRTY` with an empty `statusCheckRollup`.
- The retry was due at 06:23Z. A retry would probably have seen `CONFLICTING` and raised the finding, because the check runs on every poll. The root agent reopened `base` by hand at 07:04Z before any retry ran. So "it would have waited forever" overstates what happened. What is true: the reason text pointed at CI instead of the conflict, and nothing guaranteed that GitHub's answer would arrive within the backoff (5, 10, 20, 30 minutes up to 120).
- The fake gh (`.agents/engine_fake_gh.py` `mergeability`) computes mergeability on every view with no delay. That is why no test caught the `UNKNOWN` race.

A second, similar hole: when `headRefOid != H`, meaning GitHub has not yet seen the head that was just pushed, the into-I path also skips the conflict check and reports "checks pending". The stacked path already waits explicitly in this case.

## Approach

All changes are in `_run` step 5b of `plugins/zzzops/zzzops/engine/ops/integrate.py`. It adds no GitHub calls and uses the `pr view` it already makes (`headRefOid,statusCheckRollup,mergeable,mergeStateStatus`).

1. **Local conflict check first (deterministic, no GitHub).** For `target == I`, run `git merge-tree --write-tree <snap.integration> <H>`. This is the same 3-way merge GitHub runs, against the integration tip this invocation already fetched. Exit code 1 means a conflict: return the existing `conflict` finding on `base`, with the files from `--name-only` output in the text. This catches the incident on the first run, whatever GitHub's `UNKNOWN` says. Any other non-zero exit raises `EngineError`, as `base.combine` does.
2. **GitHub's verdict second.** Keep the existing check, but drop the `headRefOid == H` guard for the conflict branch only: a conflicting PR conflicts whatever head GitHub shows. The order is:
   - `headRefOid != H`: `ctx.wait("GitHub has not seen the PR head yet", 60)`. This is the same wait as the stacked path, bounded by `ci_timeout_minutes` through `ctx.wait`.
   - `mergeable == CONFLICTING` or `mergeStateStatus == DIRTY`: the conflict finding, unchanged. This covers dev moving between our fetch and GitHub's computation.
   - `mergeable == UNKNOWN`: `ctx.wait("GitHub is computing mergeability", 60)`, as `github.merge` does. Within a few seconds the next read returns a real value. `ctx.wait` carries its own `pending_since` and asks the human after `ci_timeout_minutes`.
   - otherwise (MERGEABLE: CLEAN/BLOCKED/BEHIND/UNSTABLE/HAS_HOOKS): the required-checks logic, unchanged. `BEHIND` is not a conflict. Checks still run, and `github.merge` deals with it.
3. **No-checks bound.** In the pending branch, if `statusCheckRollup` is empty (no check of any name for head H) and `now - pending_since >= NO_CHECKS_MINUTES * 60`, return `Blocked(waiting_for=human)`. Here `NO_CHECKS_MINUTES = min(15, ci_timeout_minutes)` is a module constant, not policy. The question says no checks have appeared on PR #n for head H after m minutes, gives GitHub's `mergeable`/`mergeStateStatus`, and says workflows may not trigger for this PR (path filters, disabled Actions, or a conflict). The options are "wait" (an answer clears `op_state`, as today) or "fix verification.required_ci". GitHub Actions creates queued check runs as soon as a workflow triggers, so an empty rollup after 15 minutes means nothing triggered. With the backoff, this fires on the third poll (t = 0, 5, 15).
4. **Reason text.** The pending wait's reason becomes `required checks pending: X (mergeable: MERGEABLE/CLEAN)`. A human reading `next` then sees the merge state next to the CI wait.

The conflict path returns `Done(ok=False, findings=[{key: "conflict", input: "base", ...}])` as before. The frontier turns that into a live finding on `base` and makes it `ready` with reason `reopened`, the same path `github.merge` already uses. `base` rebases onto the current tip, or blocks for an agent to resolve the conflict. Its new `base_commit` makes `integrate` stale, and the next integrate run rebuilds the PR.

## Decision: should `base` already have been stale when dev moved?

**No. Keep it as it is.** Here is why it was not offered.

`base`'s fingerprinted inputs (from `.zzzops/workflow.json`) are only `heads` (`deps.integrate.pr.head`), `merges` (`deps.merge.merge_commit`) and two context-only review summaries. The integration tip is not an input. `git.base` reads it from `snap.integration` at run time. G1016 and G1000 have no dependencies, so both input hashes equal the empty-map hash (`44136fa…` in both records), and nothing changed when dev moved. The frontier marks a node stale only when its `input_fp` changes (`frontier.py` lines 219-220). A `done` base whose inputs are unchanged therefore stays `current`. The only way a base re-runs because of dev is a finding, from `integrate` (this goal) or `merge` (already).

Making the integration tip an input would be wrong:

- Every merge into dev would make every in-flight goal's `base` stale. That cascades through `base.base_commit` into `implement`, `integrate` and `merge`, re-running agent work and reviews for goals that do not conflict at all. On a busy dev this means churn without end.
- Moving onto the latest dev is not needed for correctness. GitHub merges a non-conflicting PR against the current tip. When the policy demands up-to-date branches, `github.merge` already raises `BEHIND` as a base finding at merge time.

So staleness is detected as late as possible and only where it matters: an actual conflict, seen by integrate (this goal) or merge (already). This design changes nothing in `base.py` or `frontier.py`.

## Alternatives rejected

- **Integration tip as a `base` input.** Rejected, see above.
- **Only wait on `UNKNOWN` (the spec's minimum).** It fixes the misleading reason but still depends on GitHub answering within a poll. The local `merge-tree` check is deterministic, costs about 5 lines and one local git call, and fires on the first run. Both are kept, because dev can move after our fetch.
- **Treating an empty rollup as a conflict.** The empty rollup is a symptom. The mergeability fields are the evidence. An empty rollup on a mergeable PR is a CI configuration question, which is why it goes to a human with a specific question.
- **A pre-push local check that skips opening the PR.** The PR record is useful even when it conflicts, and keeping the check in step 5b keeps the op's flow unchanged.

## Interfaces and data

- `git.integrate` outputs: unchanged (`pr`, `ci`). The finding key `conflict` and its target input `base` are unchanged. Only the text gains the file list for the local check.
- `op_state` for the checks wait: unchanged keys (`head`, `pending_since`, `polls`, `rerun_head`). The new waits use `ctx.wait`'s `{pending_since, polls}`.
- No policy or schema changes. `NO_CHECKS_MINUTES` is a constant.
- The engine definition fingerprint of `git.integrate` changes, so any `integrate` record that is currently blocked re-runs once. That is wanted: it re-evaluates G1016/G1000-style records.

## Tests

Fake gh (`.agents/engine_fake_gh.py`): add a `mergeable_lag` fault. It is a per-PR count of views that return `UNKNOWN/UNKNOWN` after the head or base changes. The default is 0, so existing tests are unaffected.

In `.agents/test_engine_github.py`:

1. **Conflict with lag.** dev conflicts and `mergeable_lag=1`. Integrate's first run gives the `conflict` finding on `base` (from the local check), and `base` is `ready` with reason `reopened`. This is the regression test for the incident.
2. **GitHub-only conflict.** `merge-tree` is clean against our fetched tip, and dev is pushed after the fetch, before `pr view` (fake fault). GitHub's CONFLICTING produces the finding.
3. **UNKNOWN then MERGEABLE proceeds.** With `mergeable_lag=1` on a clean PR, the first run waits ("computing mergeability", `waiting_for: time`). After `retry_after` the next run reads the checks and finishes ok when they pass.
4. **Mergeable with pending checks still waits.** This is the existing behaviour: `waiting_for: time`, and the reason includes the merge state.
5. **No checks at all.** On a mergeable PR whose required check never appears, polls at t=0 and t=5 wait, and at t≥15 the op gives `waiting_for: human` with the no-checks question. When the rollup is not empty but the required check is pending, it keeps waiting until `ci_timeout_minutes` (unchanged).
6. **Head not seen yet.** When `headRefOid != H` on the view, the op waits and does not report checks pending.

Journey (`.agents/test_engine_base.py`, `BaseJourney`): goals A and B both change line 1 of `src/app.py`. A integrates and merges. B's integrate returns the `conflict` finding on `base`, and `base` runs and blocks with `rebase conflict in src/app.py`. The test resolves the conflict in B's worktree (`git add`, `rebase --continue`) and resumes. `base` is done on the new tip, `integrate` is stale, and `implement` follows the existing replay rules. Integrate then opens or updates the PR, which is mergeable, and it finishes ok once the checks pass.

The full suite: `python3 -m unittest discover -s .agents -p 'test_engine_*.py'` (or the repository's verification commands).

## Docs

`plugins/zzzops/zzzops/references/REPAIR.md` gets a short section, "A PR that conflicts with the integration branch". GitHub runs no `pull_request` workflows on a conflicting PR, so checks never appear. `integrate` (and `merge`) raise a `conflict` finding on `base`. `base` re-runs and either rebases or asks for a hand resolution in the goal worktree, then resume. If an older record is stuck on "checks pending", run `zzzops reopen <id> base --note "conflicts with <I>"`, which is what the root did here.

## Risks

- **`merge-tree` disagrees with GitHub.** Both run a 3-way merge with the same merge base. Rename detection may differ in edge cases. A false local "conflict" sends the goal to `base`, which rebases cleanly and integrates. A false "clean" falls back to GitHub's verdict. Both failure modes are safe.
- **A 15-minute no-checks bound on slow CI.** Queued runs appear in the rollup immediately, so a slow queue does not trigger it. Only workflows that never triggered do.
- **Extra waits.** `UNKNOWN` costs one 60-second wait for a newly created PR, compared with the 5-minute checks wait it replaces.

## Out of scope

- Changing `base`'s inputs or the frontier's staleness rules (decided above).
- `BEHIND` handling in integrate. That stays with `github.merge`.
- Auto-resolving rebase conflicts. That stays with the agent through `base`'s existing blocked path.
- Making the root's loop run time-retries sooner. The incident shows the retry did not run for 46 minutes, which is a scheduling matter for the root agent and not the engine.
