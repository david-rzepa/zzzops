# G1038 design: sync goal branches with trunk by merge, squash at integrate, let test fixes land after implementation

Revision 1. Read at dev `25186a5`. Dependencies: G1025 (release lines, scheduled restack), G1026, G1027 (capabilities). Sibling: G1039 (clean-sync carry and budget), designed in parallel; the shared interface is in section 6.

## 1. Outcome

- `base` brings trunk (or the stack base) into the goal's work branch with a merge commit. The work branch only ever moves forward. No rebase, no force-push, and no owner-run rewrite at any point in a goal's normal flow.
- A conflicting sync is resolved once, in the goal worktree, and is recorded in the merge commit. Later syncs merge from that point, so they never redo it.
- Which tests are frozen, and which diff is the implementation, come from paths (the frozen set) and checkpoints, not from commit order. test_design may commit a test fix on top of implement's commits. It is accepted as is, implement may not edit it, and review_impl's view leaves it out.
- integrate builds the PR branch as exactly two commits, tests then implementation, on the trunk commit of the last sync. Its tree equals the work branch's code tree, which is the work branch merged with trunk. The work branch is left as is. Review records stay out of the PR, as today.

## 2. Decisions

### 2.1 Owner decisions (verbatim, from the spec)
- "For updating the branch with the trunk, I think merges might work better as conflict resolution doesn't get lost. Then maybe a final rebase when integrating in order to clean up the history?"
- On the integrate history, the owner chose "Squash to tests + code" over rebasing with reused resolutions or keeping the merges: integrate collapses the goal into two commits (tests, implementation) on the trunk tip.
- "I think we may as well get these done now, before dogfooding again"

These replace G1025's O1 ("goal work branches keep rebasing as today") for goal work branches only. That was the owner's choice for G1025, and the owner has now made a newer one. G1025's release-to-dev merges and line syncs are unchanged.

### 2.2 Root decisions
- **R1. The PR commits sit on the trunk commit of the last sync (`base_commit`), not the live tip.** Root's reasoning: the PR tree then equals the tree run_tests tested. When trunk moves, the base goes stale and syncs again before integrate (G1025's scheduled restack, or a G1021 conflict or BEHIND finding). So at integrate time, in the normal flow, the last synced trunk commit is the live tip. This reading of the owner's "on the trunk tip" clearly dominates the alternative (always the live tip: the PR tree would differ from the tested tree, and every trunk move would churn the PR). So it is recorded as a root decision, not raised as an owner question.

### 2.3 Design decisions (mine, with reasons)

| # | Decision | Reason |
|---|---|---|
| D1 | The sync merge is computed with `git merge-tree --write-tree --merge-base <old base_commit> <onto> <tip>`, then `commit-tree -p <tip> -p <onto>`. | An explicit merge base means "apply the goal's own change (old..tip) onto onto". That is the rebase result, as one tree. It is also correct when a dependency was dropped, a dependency's PR head was rewritten, or G1025's target changed. A plain `git merge` (true merge base) gets those three cases wrong. |
| D2 | A conflict is checked out into the worktree as merge-tree's conflicted tree (`read-tree -u --reset`), with HEAD left at the tip. The resume builds the merge from the edited worktree. | No `MERGE_HEAD` state to recover, no commit for the agent to make, and the same "edit files, run resume" path as today. Verified in section 10. |
| D3 | The preserved node's checkpoint `change` (test_design's `tests.change`) is computed over its frozen paths only. No new stored key. | A tests checkpoint on top of implement's commits otherwise includes the implementation. The scope can be derived (it is the record's `frozen`), so the stored format does not change. For a legacy linear record the scoped and unscoped values are equal (section 9). |
| D4 | `implement`'s `code.change` stays the whole goal diff. | approve_merge binds `code.change` only, so it stays bound to what is delivered: tests plus implementation. |
| D5 | The default checkpoint is always HEAD. The suggested-checkpoint machinery is removed. | With D3, a no-commit test_design re-run after implement keeps `tests.change` (H26 still holds). A tests fix on top of implement is an ordinary checkpoint. The rebase-map suggestions have nothing left to do. |
| D6 | Carry-forward after a sync moves every carried checkpoint to the sync's work tip, and carries a node iff its (scoped) `change` is unchanged. It is one function, and G1039 widens its predicate. | It keeps today's meaning, an identical diff, with no per-commit patch-id map, which a merge does not produce. Section 6 splits the work between the two goals. |
| D7 | integrate squashes by tree overlay: the tests tree = `tree(base_commit)` with the frozen paths taken from the tip. The implementation commit has the tip's code tree. Commit metadata is deterministic. | No rebase, so it works with merges in the history. A re-run over the same inputs gives the same commits. The PR tree equals the tested tree by construction. |
| D8 | No op version bump, and no change to `base`'s declared outputs. | Both are in node_def_fp: either would stale every `base` record of every in-flight goal at once. |
| D9 | One capability, `merge_sync`. | Old engines refuse merge commits in work branches (I1/I2), and they would rebase them away. The policy must stop them writing (G1027 mechanism). |

## 3. What was found at 25186a5

- Frozen tests are already path-based: `record.frozen`, built by `verbs.frozen_paths` and checked by `verbs.preserve_check` (SPEC §4.16). The dependence on commit order comes from three other places:
  - `tests.change = change(base, tests.commit)` is computed over the whole tree. A tests checkpoint on top of implement's commits includes the implementation, so review_tests sees it. A no-commit re-run that defaults to HEAD changes `tests.change` and stales implement, which is the H26 problem that `records.suggested_checkpoint` works around.
  - Carry-forward (`carry.py`) and the suggested checkpoint read the per-commit patch-id maps from the rebase (`replay_map`, `replay_pos`).
  - `base` is `rebase --onto` plus a non-fast-forward push of the work branch. integrate is a `rebase -i` drop/pick rebuild on `base_commit`. `Identity.check_i1_i2` refuses merge commits ("work branches are linear").
- `.zzzops/reviews` never exists on trunk, on dependency PR heads or on combine commits. Only work branches carry it.
- The review_impl `code` view is `git diff <base> <code.commit>` with tests included (card.py:59). `previous.interdiff` is a `git range-diff` (card.py:387).
- `merge` uses `settings.merge.method`, so PR commits may land in trunk as they are. semantic-release analyses them on the way to main.

## 4. Approach

### 4.1 base syncs by merge (SPEC §5.2)

What `base` stacks on is unchanged: `onto`, the stack set S, the combine commit, G1025's `target(g)`, `deps_conflict` and the dependency waits.

Steps after `onto` is known, with `old` = the recorded `base_commit` and `tip` = the local work tip after `wt.sync` (as today):
1. **No artifact yet:** the branch is born on `onto`, as today. `synced` is null.
2. **Nothing to do:** `onto == old`. Output as today, with `synced: null`.
3. **Already contained:** `onto` is an ancestor of `tip`. No merge: `base_commit = onto`, and `synced = {old, onto, work: tip, tip, merge: null, resolved: []}`.
4. **Merge:** `B0 = old` if `old` is an ancestor of `tip`, else `git merge-base onto tip` (a fallback for odd histories). `T = git merge-tree --write-tree --merge-base B0 onto tip`.
   - Exit 0: the `.zzzops/reviews` entry of T is set to tip's (a guard: onto never has it). `M = commit-tree T -p tip -p onto`, with the message `Merge <onto description> into zzzops/work/g<g> (zzzops base)` and committer `zzzops.committer` (the author and committer date are those of the newest parent, so the commit is deterministic). The push `(work, W, M)` is always a fast-forward, and the engine asserts that `M` descends from `W`. The worktree moves to M in `after_push`, so a crash leaves nothing behind. `synced = {old, onto, work: tip, tip: M, merge: M, resolved: []}`.
   - Exit 1 (conflict): see 4.2.
5. `base_commit = onto`. The `branch` and `stack` outputs are unchanged.

`replay_map` and `replay_pos` stay declared in the template, because removing them would change the node fingerprint (D8). They are written as `{}` and no longer read. `OpSpec` stops requiring them.

The op's `Done` field `replayed` becomes `synced`. It is not an output, so it is not fingerprinted. It is also stored in the record as the output key `synced`, which is undeclared and unfingerprinted, like G1025's `scheduled_for`:

```json
"synced": {"old": "<old base_commit>", "onto": "<new base_commit>", "work": "<work tip before the sync>",
           "tip": "<work tip after the sync>", "merge": "<merge commit or null>", "resolved": ["<paths hand-resolved>"]}
```

### 4.2 Conflicts

- On exit 1, `base` checks out T, the conflicted tree that merge-tree writes, in the goal worktree: `git read-tree -u --reset T`. HEAD stays at the tip, and conflict markers are in the files (verified, section 10). It blocks `{category: conflict, waiting_for: agent}` with `reason: "merge conflict in <files>"`. Each file in the list comes with merge-tree's message (content, modify/delete, rename). The instructions say: "In <worktree>: edit these files to the intended result of the goal's change on top of <onto> (for modify/delete, keep or delete the file), then run the resume command. Do not commit, and do not change the goal's meaning." The op_state is `{work: W, onto, old, files}`.
- **Resume:** it accepts when the remote W moved only by `docs(review):` commits, onto is unchanged, and no listed file still has a conflict-marker line (`^<<<<<<< ` or `^>>>>>>> `). Then: `git add -A`, `T' = write-tree`, the reviews subtree from the current remote W, and `M = commit-tree T' -p W -p onto`. Otherwise it re-blocks with the reason. `synced.resolved` = the listed files.
- A later sync uses this `onto` as its merge base, and the resolution is already in W, so the same hunks never conflict again (verified, section 10).
- **The conflict changed under us** (onto moved during the conflict): the worktree is reset to W (`read-tree -u --reset W`) and the sync is recomputed. The agent's edits are lost only in this case, and the new block says so. This is the same as today's rebase restart.
- **A rebase in progress** (left by an older engine): `rebase --abort`, then sync as above, which re-offers the conflict as a merge conflict.
- G1021's integrate and merge conflict findings still target `base`. `base` re-runs and merges the fresh target tip.

### 4.3 Tests and implementation by paths (SPEC §3.5, §4.16, §4.20)

- **F** = the preserved node's `record.frozen` (generic: whichever node a `preserve` names). `frozen_paths` and `preserve_check` are unchanged. At submit, `frozen_paths` runs before the change is computed, because the change needs F.
- `Identity.change(base, commit, paths=None)` gains `paths`: a literal pathspec list (`--literal-pathspecs`, passed on stdin with `--pathspec-from-file=- --pathspec-file-nul`). With `paths`, the diff is limited to them. The preserved node's checkpoint is written with `change(base, commit, paths=F)`. Every other checkpoint is unscoped. An empty F gives `ZERO`. One helper decides the scope: `checkpoint_scope(graph, node, record) -> list | None` (F if the node is named by some node's `preserve` and its record has `frozen`, else None). Submit, carry and the cards all use it.
- The default checkpoint is HEAD. `records.suggested_checkpoint`, `GitView`, the card's `suggested_checkpoint` and the `checkpoint_required` refusal are removed. The refusal code stays listed in `errors.py`, so a consumer that matches it does not break.
- **A tests fix after implement**: test_design commits on top of W, which already has implement's commits. `frozen_paths` adds only that phase's paths (`W..checkpoint`). `tests.change` covers F only. implement goes stale through `inputs.tests` as today. It resubmits, with or without commits, and preserve_check refuses any change to F.
- **A no-commit test_design re-run after implement**: the checkpoint is HEAD and the scoped change is unchanged, so implement stays current.
- **Agent merges are refused**: an agent submit refuses a merge commit in its own range (`remote W..head`). Only `base` makes merges.
- A path that test_design commits becomes frozen as a whole, even if implement edited it earlier. That is today's rule, and it is now stated.

### 4.4 Carry-forward on a sync (SPEC §4.21 rewritten, carry.py)

```text
def relocate(cp, synced):                 # the commit a carried checkpoint points at after the sync
  if synced is None: return None
  if cp.commit == synced.work or is_ancestor(cp.commit, synced.work): return synced.tip
  return None

def clean(node, k, r, cp2, scope):        # the carry predicate; G1039 replaces its body (section 6)
  return change(cp2.base, cp2.commit, paths=scope) == r.output[k].change

def carry_forward(g, X, new_output, synced, doc, live):
  for each workspace agent node n consuming X, with a done record r whose checkpoints all have base == synced.old:
    for each checkpoint k: c2 = relocate(r.output[k], synced); scope = checkpoint_scope(n, r)
                           cp2 = {commit: c2, base: synced.onto, tree: code_tree(c2), change: r.output[k].change}
    carry n iff every c2 is set and clean(n, k, r, cp2, scope) holds for every k
    the rest as today: inputs fed by X recomputed, responses pruned, carried_by: X, frozen kept
```

- The written `change` is the recorded one. Under G1038's exact predicate it equals the recomputed value. This is what lets G1039 widen the predicate without touching the writer.
- **Effect.** A clean sync carries test_design and implement. A resolution or a trunk change inside a node's scope changes that node's change, so the node re-runs. A resolution only in implementation files still carries test_design. A checkpoint below uncommitted-to-checkpoint work (W beyond c) relocates to the tip, its change grows, and it is not carried, as today. `replay_map`, `replay_pos` and `patch_ids`-based carry are deleted.
- **preserve_check after a carry** compares `code_tree(M)` at F with the new checkpoint. M has the goal's tests plus any trunk change to the same paths, and implement's later checkpoints descend from M, so they match. Nothing in the check changes.

### 4.5 integrate squash (SPEC §5.4)

- **P = `base_commit`** (R1). For stacked goals, P is the dependency head or the combine commit, as today.
- `X = code_tree(W)`, which must equal the input T (today's `work-beyond-checkpoint` check). `F` = the preserved node's frozen set, or empty if the graph has no preserve.
- `tests_tree` = `tree(P)` with every path in F replaced by X's entry (deleted where X has none). Built with `read-tree` into a temporary index file (`GIT_INDEX_FILE`), then `update-index --index-info` and `write-tree`, so the worktree is not touched.
- `c1 = commit-tree tests_tree -p P`; `c2 = commit-tree X -p c1`. A part with an empty diff is omitted (no tests, or a tests-only goal). If `X == tree(P)`, the result is today's "no code commits" question.
- **Messages** (deterministic):
  - c1: `test: <goal title> (G<g>)`.
  - c2: `<type>[!]: <goal title> (G<g>)`. The type is derived from the goal's own commits: first-parent, not merges, not `docs(review):`, in `P..W`. Priority: feat > fix > perf > any other conventional type > `chore`. `!` is set if any subject has `!` or a body has `BREAKING CHANGE:`.
  - Body: the own commit subjects (at most 30, then "and N more"), plus the BREAKING CHANGE footers copied. semantic-release then computes the same release bump as it would from today's per-commit history.
- **Identity**: the author and author date come from the newest own commit in each part (F paths for c1, the rest for c2; c2 uses c1's when it has none). The committer is `zzzops.committer`, with the same date. The same inputs give the same SHAs, so an unchanged re-run does not update the PR.
- **Checks kept**: I1/I2 and the policy-path check run over the first-parent history `P..W` (section 4.6) and the tree diff `P..W`. The new heads are checked: `code_tree(c2) == T`, and no review files in `P..c2`.
- The work branch is never touched. When a later sync changes `base_commit`, integrate re-runs and the engine force-updates its own PR branch, as today (engine-owned, never the owner). Dependents re-merge the new head on their next sync.
- **"Its tree equals the work branch merged with trunk"**: `tree(c2) = X = code_tree(W)`, and W contains the merge with `base_commit` = trunk at the last sync.

### 4.6 Identity (I1/I2)

`check_i1_i2(a, b)` walks `--first-parent a..b`. A merge commit is accepted iff it has exactly two parents, its subject does not start `docs(review):`, and its `.zzzops/reviews` subtree equals its first parent's. A merge's second-parent side (trunk) is not walked. The non-merge rules are unchanged.

### 4.7 Cards (SPEC §4.20)

- **Checkpoint views.** For the preserved node (review_tests' `tests`): `git diff <base> <commit> -- <F>`. For a checkpoint of a node that preserves it (review_impl's `code`, filter_impl's `code`, approve_merge's `code`): the existing pathspec plus `':(exclude,top,literal)<p>'` for each p in F. Up to 12 paths go inline. Beyond that, the card points to a blob that holds the path list, with `--pathspec-from-file`. That is how review_impl "sees only implementation changes", while `code.change` stays whole (D4).
- **`previous.interdiff`.** Same base: `git diff <old.commit> <new.commit> -- <view paths>`. Moved base: `git log -p --first-parent --no-merges <old.commit>..<new.commit> -- <view paths>` (the goal's new commits), plus `previous.syncs: ["git show --remerge-diff <M>", ...]` for each merge on the first-parent path in between (what each sync resolved). range-diff is dropped for merge-synced branches (section 10: it skips merges, and it shows every unrewritten commit as `=`).
- **Texts:**
  - integrate.conflict and merge: "rebase the work branch" becomes "sync the work branch (base merges the target)".
  - merge: "Rebase it?" becomes "Sync it?".
  - render.py's routine rebase wording becomes merge wording.
  - REPAIR.md's conflict paragraph describes the merge resume.
  - The test_design.md and implement.md prompts drop the suggested-checkpoint lines (in the template, plus a policy notice).

## 5. Interfaces and data that change

| Where | Change |
|---|---|
| `ops/base.py` | merge sync (4.1, 4.2); `Done.synced` replaces `replayed`; output key `synced`; `replay_map`/`replay_pos` written `{}`; rebase code and `unpushed_replay` removed (after an abort of a legacy rebase) |
| `ops/integrate.py` | tree-overlay squash (4.5); `rebase -i` rebuild removed |
| `ops/merge.py`, `render.py`, REPAIR.md | texts (4.7) |
| `identity.py` | `change(base, commit, paths=None)`; `check_i1_i2` merges and the first-parent walk; `patch_ids` kept only if a caller remains (none in G1038) |
| `carry.py` | `relocate`, `clean`, `carry_forward(…, synced, …)` (4.4) |
| `records.py`, `card.py`, `verbs.py` | suggested checkpoint removed; `checkpoint_scope`; submit computes `frozen` then the scoped change; agent merges refused; views and interdiff (4.7) |
| `ops/__init__.py` (OpSpec) | `git.base` no longer requires `replay_map`/`replay_pos` |
| `engine/capabilities/merge_sync.txt` | new (G1027): merge commits in work branches, the scoped preserved checkpoint change, the `synced` key |
| templates | prompts (test_design, implement); workflow.json unchanged |
| Stored formats | record output key `synced` (new, unfingerprinted); checkpoint values unchanged in shape; `.zzzops/reviews` unchanged |

## 6. The G1039 interface (who builds what)

G1038 provides the sync result, relocation, the scoped view and the single carry function. G1039 widens the predicate and adds the re-review and budget behaviour. Carry-forward is built once, in G1038's `carry.py`.

| G1039 need (its §5) | G1038 provides | G1039 adds |
|---|---|---|
| 1. `Done.synced = {old, onto, tip}` on every base run that moved the base, including a hand-resolved merge | Adopted as asked: `Done.synced` and output key `synced` with `old`, `onto` and `tip`. It also has `work`, `merge` and `resolved`. It is null when the base did not move. | nothing |
| 2. `relocate(node, key, cp, synced) -> commit or None` | Adopted, with the proposed rule: `synced.tip` for every checkpoint at or below `synced.work`, else None (4.4). The signature is `relocate(cp, synced)`; the node and key are not needed. | nothing |
| 3. `change` accepting a zero-context option, with the same view | `change(base, commit, paths=None)` and `checkpoint_scope` (the view G1039's delta must use) | the `unified=3` keyword and the -U0 `delta` |
| 4. base keeps `base_commit` | Kept, same meaning (= `synced.onto`) | review_impl's `base` input edge |
| 5. preserve/frozen accepts a carried tests checkpoint (commit W2, change kept) | Yes, unchanged code: the carried checkpoint has commit `synced.tip`, the recorded change, and `frozen` kept. preserve_check compares trees at F (4.4). | nothing |
| carry predicate | `clean()` with exact equality; the writer already keeps the recorded `change` | replaces `clean()`'s body with the -U0 delta comparison |

**Order.** If G1038 merges first, G1039 only swaps `clean()` and adds `unified`. If G1039 merges first, its replay-map `relocate` branch is replaced by G1038's merge one, and G1039's predicate is kept. Either way there is one carry function. I recommend that the root make G1039 depend on G1038, so that G1039's rebase fallback (`replayed`, `replay_pos`) never has to be built.

## 7. Other goals

- **G1025** (release lines, scheduled restack): pass 3 and the `restack` reason, `scheduled_for` and the one-per-attempt bound are kept as identifiers and behaviour. The run they schedule is now a merge sync. Each option-A cost in G1025's §5.1 table is answered:
  - Identity: 4.6.
  - Staleness and preserve: 4.4. The carried tests checkpoint is the real merge commit, not a virtual merge-tree.
  - Integrate rebuild: 4.5.
  - Successive combine commits: the explicit merge base (D1) merges only the goal's own change onto each new combine.
  - `line_sync`, the release-to-dev merges, `finish` and hotfix lines are unchanged.
  - A target change (`target` fp part) syncs with merge base = the old `base_commit`, which keeps exactly the goal's own change.
- **G1021**: conflict findings (`local_conflict`, CONFLICTING/DIRTY/BEHIND) still target `base`. Only their text changes (4.7).
- **G1026**: the PR body is unchanged. "Built from zzzops/work/g<g> without docs(review) commits" becomes "squashed from zzzops/work/g<g> into tests and implementation".
- **G1027**: ships `merge_sync.txt` and appends `merge_sync` to the pinned capability test list.
- **G1040** (`blocked_findings`): no functional overlap. Both append one line to the pinned capability list, a trivial adjacent conflict that `base` resolves.

## 8. Rollout and mid-flight goals

- **Linear, rebased work branches** (every in-flight goal): the next `base` run merges with merge base = the recorded `base_commit`. That gives the tree a rebase would give, and every checkpoint relocates to M. Their recorded tests changes were computed unscoped, over a range that touched only the test paths, so the scoped value is equal and they carry (section 9).
- **Records with a non-empty `replay_map`** are ignored. A leftover rebase in a worktree is aborted (4.2).
- **Existing PR branches** are re-squashed on their next integrate run: one engine force-update of `zzzops/pr/g<g>` per goal.
- No op version bump and no declared-output change (D8), so nothing goes stale on upgrade.
- **Policy**: a policy branch adds `merge_sync` to `settings.engine.requires`. It is owner-gated, like G1025's and G1027's steps. Until it lands, an older engine could still write. It would refuse a work branch with merges (I1/I2), so the window is short and fails closed.
- **Root**: WORKER.md rule 6 ("put test fixes on the tests line BEFORE implementation commits") becomes obsolete once this ships. The root updates it, since it is not repository content.

## 9. Legacy equivalence of the scoped change

For a record written before G1038, the tests checkpoint sat below implement's commits (H26, the suggested checkpoint and the hand reorders ensured that). So `diff(base, tests.commit)` touched only paths that test_design's phases committed, which is a subset of `frozen`. A pathspec that includes every changed path gives the same diff output, so the patch id is the same. The one exception is a legacy record with no `frozen` key. `checkpoint_scope` then returns None (unscoped), and its next submit scopes it.

## 10. Verified Git behaviours (Git 2.55.0, scratch repository)

- **range-diff and merge commits.** `git range-diff B..W O2..M2` (W linear, M2 = W plus two zzzops merges) lists only the three non-merge commits, each as `=`. range-diff skips merges, and because a merge sync never rewrites the goal's commits, every pair is identical. It has no `--first-parent`. So it shows nothing useful after a merge sync, and the card uses the first-parent log plus `--remerge-diff` (4.7).
- **`git show --remerge-diff <M>`** shows the conflict that merge-ort would have produced, with markers, against the recorded resolution, and names the modify/delete case. This is the "what the sync resolved" view.
- **Checking out a conflicted merge in the worktree.** `git merge-tree --write-tree --merge-base B O W` exits 1 and prints the tree OID, the conflicted stages (content conflict in `a.txt`, modify/delete for `d.txt`) and messages. After `git read-tree -u --reset <tree>`, the worktree holds `a.txt` with standard markers and `d.txt` with the modified version left in the tree. HEAD and the branch stay at W, and no merge state exists. Editing the files, then `git add -A`, `write-tree` and `commit-tree -p W -p O`, produced the merge.
  - The markers are labelled with raw commit SHAs (merge-tree takes no labels). The block's file list says which side is the trunk.
  - Modify/delete leaves the file with no markers, so the marker check cannot prove that it was decided. The block lists the conflict kind for each file, and the agent is told to keep or delete.
- **No redo.** After the resolved M1, trunk changed another line of the same file. `merge-tree --merge-base O O2 M1` exited 0 with the first resolution intact, and the true merge base of O2 and M1 was O, as expected.
- `--merge-base` for merge-tree needs Git 2.40, and `--remerge-diff` needs 2.36. Both are below the engine's 2.41 floor.

## 11. Alternatives rejected

- **Rebase with rerere**: the resolution cache is local to one clone, and the branch is still rewritten and force-pushed.
- **Keeping the merges in the PR**: the owner chose squash.
- **A plain `git merge`** (true merge base): it brings stale content back for dropped or rewritten dependencies and target changes (D1).
- **A synthetic merge commit per checkpoint**: such commits are not on the branch, so the trees diverge from what was tested.
- **Integrating on the live tip**: R1.
- **Excluding F from `code.change`**: approve_merge would no longer bind the delivered tests (D4).
- **A stored `scope` key on checkpoints** (the earlier draft): it is derivable from `frozen` (D3).
- **Bumping op_version, or removing `replay_map`/`replay_pos` from the declared outputs**: either stales every goal once (D8).

## 12. Risks

- **merge-ort rename detection** can move a goal edit across the F boundary, or into a renamed file. The conflict and carry checks still see it, because the scoped change differs, so the node re-runs. It never carries silently.
- **One-time costs**: one forced PR-branch update per in-flight goal. The first sync of an in-flight goal is a merge on top of rebased history, which is harmless.
- **Release notes**: semantic-release's notes list one line per goal (c2's subject) instead of one per commit. The bump is the same. The body keeps every subject.
- **A wrong type derivation** (for example a goal with only `refactor:` commits gets `refactor`, so no release): this is the same result semantic-release reaches today from those commits.
- **Card length with many frozen paths**: the blob fallback beyond 12 paths.
- **Lost edits on a moved onto during a conflict** (4.2): rare, and the block says so.

## 13. Testing

A new `.agents/test_engine_merge_sync.py`, and updates to test_engine_base, checkpoint, identity, integrate_conflict, sync_edit, lifecycle and card_ux:
1. Trunk moves twice: two merge commits on W, both pushes fast-forward (no force). The first sync conflicts and is resolved through the worktree resume. The second sync touches the same file and is conflict-free (no redo). (Acceptance 1)
2. A tests fix after implement: accepted with no rewrite. implement editing that path is refused with `test_freeze`. The review_impl and approve_merge code views exclude F, and the review_tests view is only F. (Acceptance 2)
3. A no-commit test_design re-run after implement: `tests.change` is unchanged and implement is not stale.
4. Carry: a clean sync carries test_design and implement. A resolution in implementation files only carries test_design. A trunk change inside a test file's hunk stales test_design. preserve_check passes after a carry.
5. integrate: the PR head is exactly c1 (tests) and c2 (implementation) on `base_commit`, and `tree(c2) == code_tree(W)`. Two runs give identical SHAs. Type derivation: feat, fix, `!` and footer. A tests-only goal, an implementation-only goal and a no-code goal. (Acceptance 3)
6. Explicit merge base: a dropped dependency, a rewritten dependency head, and a G1025 target change each give exactly the goal's own change on the new onto.
7. I1/I2: an engine merge is accepted, a merge touching `.zzzops/reviews` is refused, and an agent merge is refused at submit.
8. Mid-flight: a linear rebased branch with old records syncs by merge and carries. A rebase in progress is aborted and re-offered as a merge conflict. Legacy `tests.change` equals the scoped value.
9. Golden: no node_def_fp or input_fp changes for the default, release and 26-node graphs.
10. G1025 scheduled restack fires a merge sync. G1021 conflict findings re-run base, which merges.
11. The docs guard, the capability list, and the HISTORY §4 row.

Commands: `python3 -m unittest discover -s .agents -p 'test_engine_merge_sync.py'` plus the updated files. CI runs the full suite.

## 14. Contract edits (this PR, per acceptance 4)

- **SPEC:** §2.1 (the work branch is fast-forward only), §3.5 (the preserved checkpoint's change is scoped to `frozen`; the `synced` key), §4.7 (`change` with `paths`), §4.13, §4.14 (submit: `frozen` before the change, agent merges refused, no suggested checkpoint), §4.16, §4.20 (views, interdiff, syncs), §4.21 (rewritten), §5.2, §5.4, §5.5 (texts), §7, §8.4 (REPAIR).
- **DESIGN:** the test-freeze section, the ops table, §3.16, and a decisions row recording that this supersedes G1025 O1 for goal work branches.
- **HISTORY:** a §4 row.

No pending-amendment row is needed: this PR applies its own amendments, as G1026 did. If the root added one, this PR deletes it.

## 15. Out of scope

- Widening carry beyond an identical change (G1039).
- The sync-focused review_impl card and the budget (G1039).
- Resolving conflicts inside the stack set S (`deps_conflict` stays a wait).
- Release-line merges and `line_sync` (G1025, unchanged).
- Making the merge method or the PR shape configurable.

Size: about 700 to 1,000 lines of engine and tests. One goal, no child goals.
