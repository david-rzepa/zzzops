# G1025 review_design (attempt 1): git-flow release branching

Reviewer: claude:e6ad/rd1025. Design revision 1, checked against read_dev a05fb97. Lenses: correctness, Adversary, Concurrency, Rollout.

## Verdict

**Changes requested.** The design follows the owner's answers O1–O4 and the spec's quoted direction, and its shape is right: an optional `settings.branching` block; line goals on a separate `release` graph; goal branches that keep rebasing; merges only between long-lived branches; and nothing added to the default graph. Most of its claims about the engine hold at a05fb97. One claim does not: the effective release gate and the cut-completeness rule are said to be computed "from the documents", and the engine does not read closed goals' documents. Left as is, finishing a release would freeze dev again. There are also three ownership races (two open release lines, a duplicate cut, a member created after finish was approved) and a wrong retarget rule for cross-target stacks. All eight findings are fixable inside the design. None needs the owner.

## Owner decisions and the spec's direction

| Source | Honoured? | Notes |
|---|---|---|
| Spec: "branch off of that tip, not dev" | yes | §4 targets; `base`, `integrate`, `merge`, worktree and first artifact all use `target(g)`. |
| Spec: "scheduled downstream merges", "before starting work on a tip … upstream tips are checked" | yes, as O1 narrows it | release→dev is a scheduled merge (§5.4). Goal branches get a scheduled rebase (§5.3). |
| Spec: "deploy/CI/actual release flow agnostic" | yes | §14. |
| O1 "Merge for release→dev only" | yes | Goal branches keep rebasing. Identity, carry, `change` and the integrate rebuild are untouched (§9). The scheduled restack is the designer's call that O1 allowed ("say which": D1 says yes). |
| O2 "dev moves on" | yes, but see F1 | The effective release becomes N+1 at the cut. F1 shows it falls back to N after finish. |
| O3 finish into main and dev, hotfix branches too, release branch kept | yes | D9 adds the open release branch as a third back-merge target. That is a superset of O3 and follows git flow, so it needs no owner question. Its stated reason is weaker than written, though: merging release/N into main keeps a hotfix already on main. The real gain is that release/N is *stabilised* with the fix. |
| O4 "All merged to dev" | yes | D6's exclusion of cancelled goals is a fair reading, since a cancelled goal has nothing to merge. |
| Spec item 1, "decide releases.current vs branch existing" | decided (D3) | It is the line's existence. F1 is about how that existence is read. |

## Claims checked at a05fb97

Confirmed:
- `frontier.py:204` is the release gate.
- `cli.py:352` defaults `release` to `releases.current`.
- `OPTIONAL_SETTINGS` holds only `legacy`, with the ENGINE_VERSION rule (`schemas.py:488-490`).
- `GOAL_SCHEMAS = (1,)`, and `GOAL_KEYS` is strict.
- `store.py:394` treats a newer schema as `newer`.
- `base`'s inputs are `heads, prs, merges, design_review, approval`, with no integration tip, so dev moves do not restack. The design's correction of the spec premise is right.
- `snap.I` / `snap.integration` appear in base.py:19/48/72/78, integrate.py:77-198, merge.py:29-69, worktree.py:59, identity.py:146 and card.py:176.
- `check_i1_i2` is used at base, integrate and submit.
- Required checks come from `verification.required_ci`, not from the branch, so "checks enforced on PRs into release/N" is a one-condition change at integrate.py:182.
- The only workspace agents are `test_design` and `implement`, so D1's "the agent re-runs CI anyway" holds.
- `merge.method` is `merge`, `releases.current` is 1, origin/main is an ancestor of origin/dev, and no `release/*` branch exists.

Not true: "computed in `portfolio` from the documents" (F1).

## Findings

**F1 (major, design): the effective release and the cut-completeness rule need closed goals, and the engine does not read closed goals' documents.**
- `store.read_state` (store.py:379) reads a document only when the goal is named, or `all_goals`, or its commit trailer `State` is not `closed`.
- `effective = max(current, 1 + highest N with a release line goal)`. Once `finish` closes the line goal for N, its document is no longer read. `effective` falls back to `releases.current` (1 here), and every release N+1 goal's `merge` returns to `waiting: release`. Dev would freeze right after Release 1 finishes.
- The cut condition "every goal with release == N is closed, at least one closed done" needs the `release` and `closed.reason` of closed goals. Neither is in the trailers (`goal_message` writes Outcome, State, Request-Key and Engine only).
- Fix: make line existence and release membership cheap to read. For example, add `Release: <n>`, `Closed: <reason>` and `Line: release/<n>` trailers to the goal commits this engine writes, and fall back to reading the document only for closed goals that lack them, only when branching is on. Or always load every line goal and closed goal when branching is on, and state the cost.
- Add tests: after `finish` of release 1, a release 2 goal still passes its merge gate; the cut item counts closed done and cancelled goals correctly in a fresh `next` that reads no document by name.

**F2 (concurrency, design): two release lines can be open at once, and nothing defines that state.**
- §3 offers the cut for N = effective without requiring line N−1 to be finished. Release N+1 can complete on dev and be cut while release/N is still stabilising.
- Then release/N's syncs reach dev but never release/N+1. The finish order into production is undefined. D9's "the open release branch" is ambiguous.
- git flow, and the git-flow tool, refuse to start a release while another release branch exists, so one open release line at a time is the clear winner.
- Fix: add "no open release line goal" to the cut conditions, and show the cut item as waiting ("waiting: release N not finished"). Say that D9's target is then unique.
- Add tests: the cut for N+1 is absent while line N is open, and present after it finishes.

**F3 (concurrency, design): concurrent `release cut` (and `hotfix start`) can create two line goals for one branch.**
- §3 step 3 adopts an existing `release/N` that is an ancestor of the I tip. A second cutter whose push lost the race refetches and sees `release/N`, created moments ago at the same tip and so an ancestor. It then adopts the branch and creates a second "Release N" goal. The adopt path does not re-check "no line goal exists for N" after the rejection.
- Idempotency "through G1001's request key" helps only if the key depends on the line alone, not on the answer file F (two delegates write different F).
- Fix:
  - The request key is a function of (line kind, name), for example `sha256({"line":"release","name":"1"})`.
  - After a rejected push, re-run the whole condition check, including line existence, before the adopt path.
  - The portfolio treats two open line goals with the same `flow.branch` as a human item ("duplicate line"), never as two owners.
  - The same rules apply to `hotfix start`.
- Add a test with two racing cuts.

**F4 (correctness, design): cross-target stacks are retargeted to the wrong branch.**
- §4 says "dependents are retargeted to the merged goal's target" (today merge.py:51 retargets them to `I`). For §8's case, a dev goal stacked on a release-N goal, that puts a release N+1 PR's base on `release/N`. The PR then shows every dev commit since the cut, and if a person merges it, N+1 work lands in the release branch.
- GitHub does the same on its own when the dependency's PR branch is deleted: it retargets dependent PRs to the merged PR's base.
- Fix: retarget each dependent to its own `target(d)`, and do so before the dependency's PR branch is deleted. Until the sync lands, the dependent's PR diff still includes the dependency's change. That is acceptable, because its `base` waits on `release_sync` and nothing integrates in the meantime.
- Add a test: after the release-N dependency merges, the dependent's PR base is dev and its `base` waits with `release_sync`.

**F5 (concurrency, design): a release-N member created after `approve_finish` is approved escapes the release.**
- `line_complete` gates the human node only, and `finish`'s inputs do not include it.
- A goal created with `release: N` (or edited onto N) between the approval and the end of `finish` starts on `release/N`. After `finish` closes the line, that goal silently retargets to dev (the `target` fp part goes away and `base` restacks), so it misses release N.
- Fix: `finish` re-checks completeness when it runs. If a member is open, it blocks and returns the line to `approve_finish`. `new` and `edit` warn (`release_finishing`) once `approve_finish` is current.
- Add a test.

**F6 (correctness and liveness, design): the scheduled-restack rule needs a defined frontier mechanism and a bound.**
- The frontier is a single topological pass (frontier.py, pass 2). `base` is decided before its consumers, so "base is ready if some workspace agent *would be* ready" needs a second pass that overrides already-computed states. Say so, and say which nodes it rewrites.
- Only agents are blocked, so a `ready` workspace op such as `run_tests` (stale on the same history) can be dispatched beside `base` on the pre-restack tree. Block every workspace node downstream of `base`, not only agents.
- In a busy repository, dev can move between `base` finishing and the agent's `start`, which re-triggers the restack. State the bound, for example "at most one scheduled restack per agent ready-epoch", or "behind is measured against the target tip at the agent's ready transition". Otherwise name the starvation risk in §12.
- Add tests for the second-pass override and for an op that is not dispatched while the restack is pending.

**F7 (correctness, design): the line goal's branches and fetch need defining against the work-branch machinery.**
- `sync` resets `zzzops/work/g<line>` and puts merge commits on it. The generic workspace paths assume a linear review/code history: `wt.sync` and `unpushed_replay` use `patch_ids --no-merges`, there is `salvage_lines`, the worktree is born at `snap.integration`, and `verbs.py:476` calls `check_i1_i2`. Name the sync's branch (for example a dedicated `zzzops/sync/g<line>`, never pushed as `work`), and say which of those paths line ops bypass. The hand-resolved merge commit must survive `start`'s resume.
- Say what happens when dev moves after a hand resolution and the sync PR turns DIRTY or BEHIND. For example: merge again on the new I tip, and require the resolution approval again if a new conflict appears.
- §4's snapshot says it fetches the production branch and the open line branches with explicit refspecs. The policy, and so `branching`, is read from the I tip fetched in that same round, and line goals come from the goal refs of that round. That needs a second fetch round, or a prefix wildcard taken from the last-seen policy. Say which, and that it applies only when branching is on.

**F8 (minor, design): G1017's rule.**
- G1017's design (case 3) gives a pending README row to a case-3 goal "when its contract sections are already known". §15 now names them, so §10's "no pending row" is out of date.
- Fix: as G1022 §12 does, send §15's list to G1017 or the root for a row, and add "this PR deletes the G1025 pending row" to the PR's docs edits. Otherwise `test_no_landed_goal_is_pending` fails on the PR if a row was added.

## Notes (not findings)

- Validation could refuse `settings.branching` without a valid `graphs.release` up front, instead of only at `release cut` and `hotfix start`. That is the designer's call.
- §11 rollout order is sound. G1025 is itself Release 1, so its own close is part of the cut's completeness. The cut also waits on the owner-gated engine floor and on G1003 being unheld or moved. G1022 §8a's three points are met.
- G1024: the shipped `POLICY.json` is unchanged and `graphs.release` is inert without `branching`. Agreed.
