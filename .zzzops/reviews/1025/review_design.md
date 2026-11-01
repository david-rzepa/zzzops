# G1025 review_design (attempt 2): git-flow release branching, revision 2

Reviewer: claude:e6ad/rd1025. Checked against read_dev c3791a0. Lenses: correctness, Adversary, Concurrency, Rollout.

## Verdict

**Changes requested.** All eight attempt-1 findings are answered, and seven are fully resolved. The new mechanisms are well specified: the closed-goal trailer ledger, the one-open-line rule, the request key derived from the line, `duplicate_line`, retargeting to `target(d)`, the frontier's pass 3 with a per-attempt bound, the `zzzops/sync/g<line>/<into>` branches, and the second fetch round. Revision 2 still has four holes, all fixable inside the design:
- two new waits (`release_sync`, `line_members_open`) are recorded blocks that nothing ever re-evaluates, so they hang forever;
- hotfix lines have no tip binding for `approve_finish`;
- a hotfix name cannot be reused after its line finishes;
- the `Closed` trailer omits `superseded`.

None of the four is an owner question.

The capability requirement (`branching`, under `engine.min` or under G1027's declared capabilities) is consistent with the owner's G1027 decision and fails closed on both schemes.

## Prior findings

| id | status | why |
|---|---|---|
| review_design:1:1 (closed goals) | resolved | §3.1 ledger: `Release`/`Closed`/`Line`/`Hotfix` trailers, written only in branching mode (byte-identical commits otherwise). Legacy closed goals are read in one batch. `effective` counts closed lines. Test 2a covers it. One gap in the trailer values is raised separately (new 4). |
| review_design:1:2 (two open lines) | resolved | §3.2/D16. The cut waits while any release line is open. D9's target is unique. |
| review_design:1:3 (racing cuts) | resolved | §3.3/D17. The key comes from (kind, name). A rejected push re-runs the scan, adoption happens only when no line goal exists, and `duplicate_line` covers the rest. The same steps apply to hotfix start (a consequence for hotfix names is new 3). |
| review_design:1:4 (retarget) | resolved | §4/§8. Each dependent is retargeted to `target(d)`. Confirmed at c3791a0: merge.py never deletes the dependency's PR branch, and it retargets only after observing the merge. A PR that GitHub has already moved is corrected by the dependent's next run. |
| review_design:1:5 (late members) | resolved for release lines | §6. `approve_finish` is bound to `sync.merged`, `finish` re-checks members and the approved tip, and `new`/`edit` warn. The two holes this fix opens (a hang on a cancelled member, and hotfix lines) are new 1 and new 2. |
| review_design:1:6 (scheduled restack) | resolved | §5.3/D18. An explicit pass 3 keeps `cur[base]`, blocks every ready or reclaimable workspace node downstream of `base`, and fires once per agent attempt through the unfingerprinted `scheduled_for`. |
| review_design:1:7 (sync branch, fetch) | resolved | §5.4/D19. There is no work branch. A detached worktree, self_sync, and an explicit bypass list. DIRTY/BEHIND is handled by merging the new I tip and keeping an approved resolution. A second fetch round runs only in branching mode. |
| review_design:1:8 (G1017 row) | resolved | §10. The row text and marker are given, and this PR deletes the row. |

## New findings

**New 1 (major, design): the `release_sync` and `line_members_open` waits are recorded `waiting_for: dependency` blocks, and nothing re-evaluates them.**
- In the frontier (frontier.py:243 at c3791a0), a blocked record whose `waiting_for` is `dependency` stays `waiting` until the node's `input_fp` changes. `ready (stale)` is checked first; nothing else moves the node.
- **`release_sync`** (§8). The dependent's `base` blocks once the dependency has merged into `release/N`. Its inputs (heads, prs, merges, approvals, plus the `target` name) are already final at that point, and G1021 keeps the integration tip out of `base`'s fingerprint. The sync landing on dev therefore changes nothing `base` sees, so the dependent waits forever. Pass 3 does not rescue it, because it requires `st[base]` to be `current`.
- **`line_members_open`** (§6). If the late member is merged, the release tip moves, `sync` re-runs and the approval goes stale, so `finish`'s inputs change and the wait ends. But the design states that a cancelled late member "leaves the approval valid". In that case nothing in `finish`'s inputs changes, and `finish` waits forever.
- **Fix:** make both conditions frontier-computed waits, not recorded blocks:
  - `base` is `waiting (release_sync)` while some `merges[d]` is not an ancestor of the target tip. That fact comes from the `upstream` input that pass 3 already receives.
  - `finish` is `waiting (line_members_open)` from the ledger, as `line_complete` already is for `approve_finish`.
  - Alternatively, give each block a re-check hook that `portfolio` evaluates.
- **Tests:** "sync lands, then the dependent's `base` runs without any other change", and "a late member is cancelled, then `finish` runs on the existing approval".

**New 2 (design): hotfix lines have no tip binding.**
- §7 puts a hotfix line's `sync` in `skip`. `approve_finish`'s only input, `sync.merged`, then resolves to the skipped placeholder, so the approval is not bound to `hotfix/x`'s tip.
- Step 1 of `finish` ("release tip equals the approved `sync.merged`") is undefined for hotfix lines.
- A member that merges into `hotfix/x` after the approval (late-created, as in the attempt-1 finding review_design:1:5) is merged into production without a new approval. That is exactly what the attempt-1 fix closed for release lines.
- **Fix:** bind the approval to the line tip for both kinds. For example:
  - run `sync` on hotfix lines in "record only" mode, so that `merged` is the `hotfix/x` tip and nothing is merged;
  - or add a small `git.line_tip` op that both `approve_finish` and `finish` read.
- **Test:** a hotfix member merged after the approval makes `approve_finish` stale.

**New 3 (design): a hotfix name cannot be reused after its line finishes.**
- §3.3's key for `hotfix start` is `{"line": "hotfix", "name": x}`, and the scan returns any goal with that key, closed included.
- D14 keeps `hotfix/x`.
- Suppose a later goal is marked `flow.hotfix = x` (a recurring "login-crash", say). Its target is "no line yet", and `next` offers `hotfix_start`. The verb then finds the finished line and returns it as `recovered`, so no branch or open line is ever created. The member's `base` waits for ever ("hotfix x not started"), and the item repeats.
- **Fix:** refuse `flow.hotfix` naming a hotfix line that has finished (`new`/`edit` validation via the ledger's `Line: hotfix:x`, with the hint "choose a new name"). Alternatively, include a generation in the key and branch name. The refusal is simpler, and it matches release numbers, which are never reused.
- **Test:** marking a goal with a finished hotfix name is refused.

**New 4 (minor, design): the `Closed` trailer omits `superseded`.**
- §3.1 writes `Closed: done|cancelled`, but `closed.reason` is `done | cancelled | superseded` (schemas.py `validate_goal`).
- Cut completeness (D6: closed, at least one done; a cancelled goal does not block) must classify superseded goals from the trailer alone. Otherwise every superseded release-N goal falls back to a document read, or is miscounted.
- **Fix:** write `Closed: <reason>` for all three reasons, and say in D6 that `superseded` counts like `cancelled`.
- **Test:** add a superseded goal to test 2a.

## Notes (not findings)

- Pass 3 also blocks `reclaimable` workspace nodes. A reclaim then meets a rebased worktree: `base` refuses a dirty tree with an agent item, so the outcome is safe, but the design could say so.
- D9's reason ("otherwise release/N would ship without the fix") is still overstated: merging release/N into main keeps a hotfix that is already on main. The real gain is that release/N is stabilised with the fix. The decision stands.
- G1022 §8a, G1024 and G1017 are consistent with this revision. The §11 rollout is sound, with the capability step gated as the owner decided in G1027.
