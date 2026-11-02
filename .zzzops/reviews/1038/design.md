# G1038 design: sync goal branches with trunk by merge, squash at integrate, let test fixes land after implementation

Revision 2. Read at dev `25186a5`. Dependencies: G1025 (release lines, scheduled restack), G1026, G1027 (capabilities). G1039 (clean-sync carry and budget) now depends on G1038 and re-runs its design after this one is approved. Section 6 is the contract G1039 adopts verbatim.

Changes from revision 1, by finding:
- F1: section 6 is rewritten as an exact contract (names, signatures, keys, scope, interdiff), with the edits G1039 makes.
- F2: the goal's own commits exclude every previous base, through an `Zzzops-Old-Base:` trailer on each sync merge (4.5.1).
- F3: c2's type is ranked by release effect from release.config.cjs, over implementation commits only, and c1 is always `test:` (4.5.2).
- F4: R1 is restated with the correct reasoning, and acceptance 3 is mapped explicitly.
- F5: the merge sync is a precondition on the policy. Until the policy requires `merge_sync`, `base` keeps rebasing (D9, 4.1, section 8).
- F6: the conflict resume stages only the listed files and refuses anything else (4.2).
- F7 (owner decision): conventional commits on every work, stack and PR branch commit, with two new submit refusals and conventional engine subjects (4.8).
- Root extra (dogfood note 83): the squashed commits get strictly increasing dates, after any earlier PR head (4.5.3).

## 1. Outcome

- Once the policy requires `merge_sync`, `base` brings trunk (or the stack base) into the goal's work branch with a merge commit. The work branch then only moves forward. There is no rebase, no force-push, and no owner-run rewrite at any point in a goal's normal flow.
- A conflicting sync is resolved once, in the goal worktree, and is recorded in the merge commit. Later syncs merge from that point, so they never redo it.
- Which tests are frozen, and which diff is the implementation, come from paths (the frozen set) and checkpoints, not from commit order. test_design may commit a test fix on top of implement's commits. It is accepted as is, implement may not edit it, and review_impl's view leaves it out.
- integrate builds the PR branch as exactly two commits, `test: …` then `<type>: …`, on the trunk commit of the last sync (today's behaviour, R1). Its tree equals the work branch's code tree, which is the work branch merged with trunk. The work branch is left as is. Review records stay out of the PR, as today.
- Every commit on a work, stack or PR branch has a conventional-commit subject (owner decision, 4.8).

## 2. Decisions

### 2.1 Owner decisions (verbatim)
- "For updating the branch with the trunk, I think merges might work better as conflict resolution doesn't get lost. Then maybe a final rebase when integrating in order to clean up the history?"
- On the integrate history, the owner chose "Squash to tests + code" over rebasing with reused resolutions or keeping the merges: integrate collapses the goal into two commits (tests, implementation) on the trunk tip.
- "I think we may as well get these done now, before dogfooding again"
- "Yeah, we should ensure we always use conventional commit messages" (relayed by the root in review_design:1:7, in reply to the proposal adopted in 4.8).

These replace G1025's O1 ("goal work branches keep rebasing as today") for goal work branches only, once the policy requires `merge_sync`. That was the owner's choice for G1025, and the owner has now made a newer one. G1025's release-to-dev merges and line syncs are unchanged.

### 2.2 Root decisions
- **R1. The PR commits sit on `base_commit`, the trunk commit of the last sync, not on the live tip.** This is today's behaviour: integrate.py already rebuilds the PR branch on `ctx.inputs["base"]` (`rebase … B`). It is not true that the base always re-syncs before integrate. Outside branching mode nothing re-syncs `base` on a dev move (G1025 §2), and in branching mode G1025's pass 3 fires only before agent phases of unstacked goals, never before ops (G1025 §5.3, D1). So the PR often sits on an older trunk commit. That is acceptable for three reasons:
  - The PR tree equals the tree run_tests tested.
  - If trunk moved since the last sync, CI on the PR runs on GitHub's merge of the PR into trunk, and GitHub's mergeability check reports CONFLICTING or BEHIND. G1021 turns those into `base` findings. `base` then merges the new tip, and integrate re-squashes onto it.
  - Building on the live tip would make the PR tree differ from the tested tree, and every trunk move would churn the PR.
  This is how acceptance 3's "on the trunk tip" is met: the two commits sit on the trunk commit the goal last synced with, and GitHub's checks cover any later trunk move. The alternative clearly loses, so this is a root decision, not an owner question.
- **R2. Engine record commits on goal and lease refs keep their machine subjects** (4.8). The root recommended this scope. The reason is in 4.8.

### 2.3 Design decisions (mine, with reasons)

| # | Decision | Reason |
|---|---|---|
| D1 | The sync merge is computed with `git merge-tree --write-tree --merge-base <old base_commit> <onto> <tip>`, then `commit-tree -p <tip> -p <onto>`. | An explicit merge base means "apply the goal's own change (old..tip) onto onto". That is the rebase result, as one tree. It is also correct when a dependency was dropped, a dependency's PR head was rewritten, or G1025's target changed. A plain `git merge` (true merge base) gets those three cases wrong. |
| D2 | A conflict is checked out into the worktree as merge-tree's conflicted tree (`read-tree -u --reset`), with HEAD left at the tip. The resume builds the merge from the listed files only. | No `MERGE_HEAD` state to recover, no commit for the agent to make, and the same "edit files, run resume" path as today. Verified in section 10. |
| D3 | The preserved node's checkpoint `change` (test_design's `tests.change`) is computed over its frozen paths only. The scope is derived from `record.frozen` every time and is never stored. | A tests checkpoint on top of implement's commits otherwise includes the implementation. The scope can be derived, so the stored format does not change. For a legacy linear record the scoped and unscoped values are equal (section 9). |
| D4 | `implement`'s `code.change` stays the whole goal diff. | approve_merge binds `code.change` only, so it stays bound to what is delivered: tests plus implementation. |
| D5 | The default checkpoint is always HEAD. The suggested-checkpoint machinery is removed. | With D3, a no-commit test_design re-run after implement keeps `tests.change` (H26 still holds). A tests fix on top of implement is an ordinary checkpoint. |
| D6 | One carry function. After a merge sync it moves every carried checkpoint to the sync's work tip and carries a node iff `unchanged()` holds for each of its checkpoints. G1039 replaces `unchanged()`'s body. | It keeps today's meaning, an identical diff, with no per-commit patch-id map, which a merge does not produce. Section 6 is the contract. |
| D7 | integrate squashes by tree overlay: the tests tree = `tree(base_commit)` with the frozen paths taken from the tip. The implementation commit has the tip's code tree. Messages are derived; dates are strictly increasing (4.5). | No rebase, so it works with merges in the history. The PR tree equals the tested tree by construction. |
| D8 | No op version bump, and no change to `base`'s declared outputs. | Both are in node_def_fp: either would stale every `base` record of every in-flight goal at once. |
| D9 | One capability, `merge_sync`, and the merge sync is gated on it: the new engine writes a merge commit into a work branch only when `settings.engine.requires` contains `merge_sync`. Until then `base` keeps today's rebase. | An older engine's `base` does not fail closed on a merged branch: it rebases the merges away, redoes their conflicts and force-pushes (review_design:1:5). Requiring the capability first pauses older engines (G1027: `engine_too_old`, or `policy_invalid` on 1.x), so no older engine can ever see a merge-synced branch. |
| D10 | Conventional subjects are enforced at submit for agent commits, and are used by every engine commit on work, stack and PR branches (4.8). | Owner decision. These are the only branches whose commits reach trunk, where semantic-release reads them. |

## 3. What was found at 25186a5

- Frozen tests are already path-based: `record.frozen`, built by `verbs.frozen_paths` and checked by `verbs.preserve_check` (SPEC §4.16). The dependence on commit order comes from three other places:
  - `tests.change = change(base, tests.commit)` is computed over the whole tree. A tests checkpoint on top of implement's commits includes the implementation, so review_tests sees it. A no-commit re-run that defaults to HEAD changes `tests.change` and stales implement, which is the H26 problem that `records.suggested_checkpoint` works around.
  - Carry-forward (`carry.py`) and the suggested checkpoint read the per-commit patch-id maps from the rebase (`replay_map`, `replay_pos`).
  - `base` is `rebase --onto` plus a non-fast-forward push of the work branch. integrate is a `rebase -i --committer-date-is-author-date` drop/pick rebuild on `ctx.inputs["base"]`. `Identity.check_i1_i2` refuses merge commits ("work branches are linear").
- integrate's `--committer-date-is-author-date` gives a reordered tests fix a later date than the implementation commits after it. GitHub lists a PR's commits by date and reads the check rollup from the newest one, so after a reorder the PR head was not the newest commit and the rollup stayed empty (dogfood note 83, while merging G1027).
- `.zzzops/reviews` never exists on trunk, on dependency PR heads or on combine commits. Only work branches carry it.
- The review_impl `code` view is `git diff <base> <code.commit>` with tests included (card.py:59). `previous.interdiff` is a `git range-diff` (card.py:387).
- `merge` uses `settings.merge.method`, so PR commits may land in trunk as they are. semantic-release analyses them on the way to main with release.config.cjs: breaking is major; feat minor; fix, perf and revert patch; docs, style, chore, refactor, test, build and ci no release.
- Engine commit subjects (`git grep commit_tree`): `docs(review): <node> for G<g>` on work branches (identity.py:150); `zzzops: partial stack` and `zzzops: stack for G<g> (combines …)` on stack branches (base.py:150-152); `zzzops renew|abandon|start …` on lease refs and `zzzops: answer G<g> …` and other record commits on goal refs (verbs.py, store.py:620).

## 4. Approach

### 4.1 base syncs by merge (SPEC §5.2)

What `base` stacks on is unchanged: `onto`, the stack set S, the combine commit, G1025's `target(g)`, `deps_conflict` and the dependency waits.

**Mode.** `mode = "merge"` iff `"merge_sync"` is in the policy's `settings.engine.requires`, else `"rebase"`. In rebase mode `base` runs today's code unchanged: rebase, `replay_map`/`replay_pos`, the non-fast-forward push, today's conflict resume, and `synced: null`. Only the combine subjects change (4.8). Everything below is merge mode.

Steps after `onto` is known, with `old` = the recorded `base_commit` and `tip` = the local work tip after `wt.sync` (as today):
1. **No artifact yet:** the branch is born on `onto`, as today. `synced` is null.
2. **Nothing to do:** `onto == old`. Output as today, with `synced: null`.
3. **Already contained:** `onto` is an ancestor of `tip`. No merge: `base_commit = onto`, and `synced = {old, onto, work: tip, tip, merge: null, resolved: []}`.
4. **Merge:** `B0 = old` if `old` is an ancestor of `tip`, else `git merge-base onto tip` (a fallback for odd histories). `T = git merge-tree --write-tree --merge-base B0 onto tip`.
   - Exit 0: the `.zzzops/reviews` entry of T is set to tip's (a guard: onto never has it). `M = commit-tree T -p tip -p onto` with the message in 4.8 (subject `chore(sync): merge <onto label> into G<g>`, trailer `Zzzops-Old-Base: <B0>`) and committer `zzzops.committer`. The author and committer date are those of the newest parent, so the commit is deterministic. The push `(work, W, M)` is always a fast-forward, and the engine asserts that `M` descends from `W`. The worktree moves to M in `after_push`, so a crash leaves nothing behind. `synced = {old, onto, work: tip, tip: M, merge: M, resolved: []}`.
   - Exit 1 (conflict): see 4.2.
5. `base_commit = onto`. The `branch` and `stack` outputs are unchanged.

`replay_map` and `replay_pos` stay declared, because removing them would change the node fingerprint (D8). In merge mode they are written as `{}`.

The op's `Done` field `synced` (new; `replayed` stays for rebase mode) is not an output, so it is not fingerprinted. It is also stored in the record as the output key `synced`, which is undeclared and unfingerprinted, like G1025's `scheduled_for`. Its shape is in section 6, item 4.

**Mid-flight switch.** When the policy starts requiring `merge_sync`, a linear rebased branch's next `base` merges with merge base = the recorded `base_commit`. A rebase left in progress by an older engine is aborted (`rebase --abort`) and the sync is recomputed as a merge.

### 4.2 Conflicts (merge mode)

- On exit 1, `base` checks out T, the conflicted tree that merge-tree writes, in the goal worktree: `git read-tree -u --reset T`. HEAD stays at the tip, and conflict markers are in the files (verified, section 10). It blocks `{category: conflict, waiting_for: agent}` with `reason: "merge conflict in <files>"`. Each file in the list comes with merge-tree's message (content, modify/delete, rename). The instructions say: "In <worktree>: edit only these files to the intended result of the goal's change on top of <onto> (for modify/delete, keep or delete the file), then run the resume command. Do not commit, do not touch other files, and do not change the goal's meaning." The op_state is `{work: W, onto, old, files, tree: T}`.
- **Resume.** It accepts when the remote W moved only by `docs(review):` commits, onto is unchanged, and:
  1. no listed file still has a conflict-marker line (`^<<<<<<< ` or `^>>>>>>> `);
  2. `git status --porcelain=v1 -z --untracked-files=all` lists no path outside the listed files. Ignored files are left alone, since they are never staged. Any other modified, deleted or untracked path re-blocks with "these paths are not part of the conflict: <paths>; revert or remove them, then resume", listing each.
  Then: `git add -A --literal-pathspecs -- <listed files>` (only those), `T' = write-tree`, the reviews subtree from the current remote W, and `M = commit-tree T' -p W -p onto` with the 4.8 message. Otherwise it re-blocks with the reason. `synced.resolved` = the listed files.
- A later sync uses this `onto` as its merge base, and the resolution is already in W, so the same hunks never conflict again (verified, section 10).
- **The conflict changed under us** (onto moved during the conflict): the worktree is reset to W (`read-tree -u --reset W`) and the sync is recomputed. The agent's edits are lost only in this case, and the new block says so. This is the same as today's rebase restart.
- G1021's integrate and merge conflict findings still target `base`. `base` re-runs and merges the fresh target tip.

### 4.3 Tests and implementation by paths (SPEC §3.5, §4.16, §4.20)

- **F** = the preserved node's `record.frozen` (generic: whichever node a `preserve` names). `frozen_paths` and `preserve_check` are unchanged. At submit, `frozen_paths` runs before the change is computed, because the change needs F.
- `Identity.change(base, commit, paths=None)` gains the keyword `paths`: a literal pathspec list (`--literal-pathspecs`, passed on stdin with `--pathspec-from-file=- --pathspec-file-nul`). With `paths`, the diff is limited to them. An empty list gives `ZERO`. The scope comes from one helper, `checkpoint_scope` (section 6, item 2). Submit, carry and the cards all use it.
- The default checkpoint is HEAD. `records.suggested_checkpoint`, `GitView`, the card's `suggested_checkpoint` and the `checkpoint_required` refusal are removed. The refusal code stays listed in `errors.py`, so a consumer that matches it does not break.
- **A tests fix after implement**: test_design commits a `test:` commit on top of W, which already has implement's commits. `frozen_paths` adds only that phase's paths (`W..checkpoint`). `tests.change` covers F only. implement goes stale through `inputs.tests` as today. It resubmits, with or without commits, and its commits may not touch F (4.8). This works in both modes: a linear branch with the tests fix on top is still linear.
- **A no-commit test_design re-run after implement**: the checkpoint is HEAD and the scoped change is unchanged, so implement stays current.
- **Agent merges are refused**: an agent submit refuses a merge commit in its own range (`remote W..head`) with today's I1/I2 code (`validation`) and the text "merge commit <sha>: only base makes merge commits in a work branch". Only `base` makes merges.
- A path that test_design commits becomes frozen as a whole, even if implement edited it earlier. That is today's rule, and it is now stated.

### 4.4 Carry-forward (SPEC §4.21 rewritten, carry.py)

`carry_forward` dispatches on the base record:
- **`output.synced` set (merge mode):** the merge path below, with the section 6 functions.
- **`replay_map` non-empty (rebase mode):** today's code, unchanged, except that the written `change` uses `paths=checkpoint_scope(...)`.
- Otherwise nothing is carried.

The merge path, for each workspace agent node n that consumes X (the base node) and has a done record r whose checkpoints all have `base == synced.old`:
- for each checkpoint key k: `c2 = relocate(r.output[k], synced)`; `scope = checkpoint_scope(graph, n, r)`; `new_cp = {commit: c2, base: synced.onto, tree: code_tree(c2), change: r.output[k].change}`;
- carry n iff every `c2` is set and `unchanged(ident, n, k, r.output[k], new_cp, scope)` holds for every k;
- the rest as today: inputs fed by X recomputed, responses pruned, `carried_by: X`, `frozen` kept.

- The written `change` is the recorded one. Under G1038's exact predicate it equals the recomputed value. This is what lets G1039 widen the predicate without touching the writer.
- **Effect.** A clean sync carries test_design and implement. A resolution or a trunk change inside a node's scope changes that node's change, so the node re-runs. A resolution only in implementation files still carries test_design. A checkpoint below uncommitted-to-checkpoint work (W beyond c) relocates to the tip, its change grows, and it is not carried, as today.
- **preserve_check after a carry** compares `code_tree(M)` at F with the new checkpoint. M has the goal's tests plus any trunk change to the same paths, and implement's later checkpoints descend from M, so they match. Nothing in the check changes.

### 4.5 integrate squash (SPEC §5.4)

- **P = `base_commit`** (R1). For stacked goals, P is the dependency head or the combine commit, as today.
- `X = code_tree(W)`, which must equal the input T (today's `work-beyond-checkpoint` check). `F` = the preserved node's frozen set, or empty if the graph has no preserve.
- `tests_tree` = `tree(P)` with every path in F replaced by X's entry (deleted where X has none). Built with `read-tree` into a temporary index file (`GIT_INDEX_FILE`), then `update-index --index-info` and `write-tree`, so the worktree is not touched.
- `c1 = commit-tree tests_tree -p P`; `c2 = commit-tree X -p c1`. A part with an empty diff is omitted (no tests, or a tests-only goal). If `X == tree(P)`, the result is today's "no code commits" question.
- The same squash runs in both modes; on a linear branch the overlay gives the same trees.

#### 4.5.1 The goal's own commits

`own(W, P)` = `git rev-list --first-parent --no-merges W ^P ^<b> …`, excluding `docs(review):` commits, where the `<b>` are, for every merge commit on W's first-parent chain, its second parent and the value of its `Zzzops-Old-Base:` trailer. The first merge sync's trailer is the base the linear branch was last born or rebased on, so the walk stops there even when P does not descend from it (a rewritten dependency PR head, a dropped dependency, a G1025 target change). A branch without merges (rebase mode) has no trailers and is walked as `P..W`, which is linear and correct.

Each own commit is classified:
- **tests commit:** its type is `test` and every path it touches is in F;
- **implementation commit:** every other own commit.

#### 4.5.2 Messages

- c1: `test: <goal title> (G<g>)`, always. Body: the tests commits' subjects (at most 30, then "and N more").
- c2: `<type>[!]: <goal title> (G<g>)`. The type comes from the implementation commits' conventional subjects only, ranked by release effect in release.config.cjs:
  1. `feat` (minor);
  2. `fix`, `perf`, `revert` (patch), in that order of preference;
  3. any no-release type: the most common one among the implementation commits, with ties broken by the newest commit;
  4. no implementation commits: `chore`.
  `!` is added iff an implementation commit's subject has `!` or its body has a `BREAKING CHANGE:` or `BREAKING-CHANGE:` footer (major). Body: the implementation commits' subjects (at most 30), then their breaking footers copied.
- So semantic-release computes, from c1 and c2, the highest release any implementation commit would have produced. The tests commits produce no release either way (`test` is no release). Subject lengths: the goal title is cut at 72 characters minus the prefix.

#### 4.5.3 Identity and dates

- The author is the author of the newest commit in each part (tests commits for c1, implementation commits for c2; a part with no commits uses the other part's). The committer is `zzzops.committer`.
- **Dates.** GitHub lists a PR's commits by date and reads the check rollup from the newest one, so the PR head must be the newest commit:
  - `t1` = the newest author date among the tests commits; `t2` = the newest among the implementation commits.
  - `prev` = the newest author or committer date on the current remote PR head and its first parent, if the PR branch exists.
  - `d1 = max(t1, prev + 1s)`; `d2 = max(t2, d1 + 1s)`. When c1 is omitted, `d2 = max(t2, prev + 1s)`. Both the author and the committer date of each commit get its value, passed as `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` to `commit_tree` (which gains an `env` keyword).
  - So c2 is strictly newer than c1 and than any earlier PR head, including after a tests fix whose date is newer than the implementation's.
- **Idempotence.** Before the dates are applied, the candidate (trees, parents, messages, authors) is compared with the current remote PR head and its parent. If they are the same, the existing head is kept and nothing is pushed. So an unchanged re-run does not update the PR, and the `prev` rule only moves dates forward when the content changed.
- **Checks kept**: I1/I2 and the policy-path check run over the first-parent history of `own(W, P)` (4.6) and the tree diff `P..W`. The new heads are checked: `code_tree(c2) == T`, and no review files in `P..c2`.
- The work branch is never touched. When a later sync changes `base_commit`, integrate re-runs and the engine force-updates its own PR branch, as today (engine-owned, never the owner). Dependents merge the new head on their next sync.
- **"Its tree equals the work branch merged with trunk"**: `tree(c2) = X = code_tree(W)`, and W contains the merge with `base_commit`, which is trunk at the last sync.

### 4.6 Identity (I1/I2)

`check_i1_i2(a, b)` walks `--first-parent a..b`. A merge commit is accepted iff it has exactly two parents, its subject starts `chore(sync): `, and its `.zzzops/reviews` subtree equals its first parent's. A merge's second-parent side (trunk) is not walked. The non-merge rules are unchanged. In an agent's own range a merge is refused (4.3).

### 4.7 Cards (SPEC §4.20)

- **Checkpoint views.** For the preserved node (review_tests' `tests`): `git diff <base> <commit> -- <F>`. For a checkpoint of a node that preserves it (review_impl's `code`, filter_impl's `code`, approve_merge's `code`): the existing pathspec plus `':(exclude,top,literal)<p>'` for each p in F. Up to 12 paths go inline. Beyond that, the card points to a blob that holds the path list, with `--pathspec-from-file`. That is how review_impl "sees only implementation changes", while `code.change` stays whole (D4).
- **`previous.interdiff` and `previous.syncs`**: section 6, item 6.
- **Texts:**
  - integrate.conflict and merge: "rebase the work branch" becomes "sync the work branch (base merges the target)" in merge mode.
  - merge: "Rebase it?" becomes "Sync it?".
  - render.py's routine rebase wording becomes merge wording in merge mode.
  - REPAIR.md's conflict paragraph describes the merge resume.
  - The test_design.md and implement.md prompts drop the suggested-checkpoint lines and state the commit rules of 4.8 (in the template, plus a policy notice).

### 4.8 Conventional commits (owner decision; SPEC §4.14, §5.2, §5.4)

**Which commits.**
- Covered: every commit on a work branch (`zzzops/work/g<g>`), a stack branch (`zzzops/stack/g<g>`) or a PR branch (`zzzops/pr/g<g>`), agent-made and engine-made. These are the branches whose commits reach trunk, or that PRs target.
- Not covered: engine record commits on goal refs (`zzzops: answer G<g> …` and the other `store.py`/`verbs.py` record commits) and lease refs (`zzzops start|renew|abandon …`). Their subjects are machine-parsed (G1026 reads `zzzops: answer`), they have the empty tree or record trees, and they never reach trunk, so semantic-release never sees them. Changing them would change a format another goal consumes, for no release effect.

**The grammar.** A subject is conventional iff it matches `^(feat|fix|perf|revert|docs|style|chore|refactor|test|build|ci)(\([^()\r\n]+\))?!?: \S` (the release.config.cjs types). The type list is one constant, `CONVENTIONAL_TYPES`, in `identity.py`.

**Agent commits (submit).** Over the agent's own range (`remote W..head`, non-merge, as today's I1/I2 check):
- `commit_subject` (new code, exit 1): "commit <sha12> has a subject that is not a conventional commit (`type(scope): summary`, type one of feat, fix, perf, revert, docs, style, chore, refactor, test, build, ci): <subject>". Hint: "reword your unpushed commits (git commit --amend, or git rebase -i on them), then submit again". `details: {commit, subject}`. The range is unpushed, so rewording it is not a force-push.
- `test_commit_type` (new code, exit 1), for the preserved node (test_design): "<node> commits are frozen tests and must be `test:` commits; commit <sha12> is `<type>`: <subject>". `details: {commit, subject, type}`. `test(scope):` and `test!:` pass.
- `test_freeze` (existing code), for a node that preserves (implement): any own commit whose diff touches a path in F is refused, not only a final tree that differs at F. Text: "commit <sha12> touches frozen test paths: <paths>; raise a finding on <preserved node> instead". This is today's tree check plus a per-commit check.
- The order is: merges, then subjects, then the type, then frozen paths, so one refusal names the first problem.
- Old commits already on a work branch are not checked again; only new ranges are.

**Engine commits.**
- Sync merge: `chore(sync): merge <onto label> into G<g>`, where `<onto label>` is the trunk name (`dev`, `release/N`), `G<d>` for a dependency head, or `stack` for a combine. Body: `Zzzops-Old-Base: <B0>` as a trailer.
- Combine commits: `chore(stack): combine <names> for G<g>` and, for the intermediate ones, `chore(stack): partial combine for G<g>`. These change in rebase mode too.
- Review records: `docs(review): <node> for G<g>`, unchanged.
- Squash: `test: …` and `<type>[!]: …` (4.5.2).

## 5. Interfaces and data that change

| Where | Change |
|---|---|
| `ops/base.py` | mode from the policy (D9); merge sync (4.1, 4.2); `Done.synced`; output key `synced`; `replay_map`/`replay_pos` written `{}` in merge mode; combine subjects (4.8) |
| `ops/integrate.py` | tree-overlay squash, own-commit walk, messages, dates and idempotence (4.5); `rebase -i` rebuild removed |
| `ops/merge.py`, `render.py`, REPAIR.md | texts (4.7) |
| `identity.py` | `change(base, commit, paths=None)`; `check_i1_i2` merges and the first-parent walk; `CONVENTIONAL_TYPES` and `conventional(subject) -> (type, scope, bang) or None` |
| `gitrun.py` | `commit_tree(..., env=None)` for the squash dates |
| `carry.py` | `relocate`, `unchanged`, `carry_forward` dispatch (4.4, section 6) |
| `records.py` | `checkpoint_scope` (section 6); suggested checkpoint removed |
| `card.py`, `verbs.py` | submit computes `frozen` then the scoped change; agent merges, `commit_subject`, `test_commit_type` and per-commit `test_freeze` refusals; views, interdiff and syncs (4.7) |
| `errors.py` | codes `commit_subject`, `test_commit_type` (exit 1); `checkpoint_required` kept listed |
| `ops/__init__.py` (OpSpec) | `git.base` no longer requires `replay_map`/`replay_pos` to be non-empty |
| `engine/capabilities/merge_sync.txt` | new (G1027): merge commits in work branches, the scoped preserved checkpoint change, the `synced` key |
| templates | prompts (test_design, implement); workflow.json unchanged |
| Stored formats | record output key `synced` (new, unfingerprinted); checkpoint values unchanged in shape (no `scope` key); `.zzzops/reviews` unchanged; the merge trailer `Zzzops-Old-Base:` |

## 6. The G1039 contract

G1038 builds the sync record, relocation, the scope helper, the carry loop and the single carry predicate. G1039 replaces the predicate's body, adds `unified` to `change`, and builds the review_impl `base` edge, the sync card and the budget. Carry-forward is built once, in G1038's `carry.py`. G1039 adopts these names verbatim.

1. **The predicate.** `carry.unchanged(ident: Identity, node: str, key: str, old_cp: dict, new_cp: dict, scope: list[str] | None) -> bool`. It is called once per checkpoint key of each candidate node, and its results alone decide carry. G1038's body: `ident.change(new_cp["base"], new_cp["commit"], paths=scope) == old_cp["change"]`. G1039 replaces the body with `delta(old_cp["base"], old_cp["commit"], scope) == delta(new_cp["base"], new_cp["commit"], scope)`.
2. **The scope.** `records.checkpoint_scope(graph, node: str, record: dict) -> list[str] | None`. It returns `sorted(record["frozen"])` if `node` is named by some node's `preserve` and the record has `frozen`, else `None` (unscoped). The scope is **derived, never stored**: checkpoints have no `scope` key. `carry_forward` computes it and passes it to `unchanged`. A legacy record without `frozen` is unscoped.
3. **`change`.** `Identity.change(base: str, commit: str, paths: list[str] | None = None) -> str`. G1039 adds the keyword `unified: int = 3` (passed as `--unified=<n>` to the diff that feeds the patch id), and defines `delta(base, commit, scope) = ident.change(base, commit, paths=scope, unified=0)`.
4. **The sync record.** The base output key **`synced`** (undeclared, unfingerprinted; the same value is `Done.synced`):
   `{"old": <previous base_commit>, "onto": <new base_commit>, "work": <work tip before the sync>, "tip": <work tip after the sync>, "merge": <merge commit or null>, "resolved": [<hand-resolved paths>]}`.
   It is `null` when the base did not move, and always `null` in rebase mode (then `replay_map` is set, and carry uses today's path, so `unchanged()` is not called). `synced.tip == synced.merge` when a merge was made; `merge` is null when onto was already contained.
5. **Relocation.** `carry.relocate(cp: dict, synced: dict | None) -> str | None`: `synced["tip"]` if `cp["commit"]` is `synced["work"]` or an ancestor of it, else `None`. The writer builds `new_cp = {commit: relocate(...), base: synced["onto"], tree: code_tree(commit), change: old_cp["change"]}`, so the kept `change` is already written. Carried records get `carried_by: <base node name>` (`"base"` in the default graph) and keep `frozen`. `base_commit` stays a declared base output (= `synced.onto`).
6. **The moved-base interdiff.** In `previous`:
   - `interdiff`: same base: `git diff <old.commit> <new.commit> -- <view paths>`. Moved base, merge mode: `git log -p --first-parent --no-merges <old.commit>..<new.commit> -- <view paths>` (the goal's commits since the last review; empty when only syncs happened). Moved base, rebase mode: today's `git range-diff`.
   - `syncs`: `["git show --remerge-diff <M>", …]`, one per merge commit on the first-parent path `<old.commit>..<new.commit>`, oldest first. Absent when there are none.
   range-diff is not used for merge-synced branches (section 10: it skips merges and shows every unrewritten commit as `=`).

**Edits G1039 makes to its revision 1** (the root relays these):
- §3.2 and §5 item 1: `unchanged(node, old_cp, new_cp)` becomes `unchanged(ident, node, key, old_cp, new_cp, scope)`, with `scope` passed in.
- §3.1, §3.2 and §5 item 3: drop the checkpoint `scope` key. The scope is `records.checkpoint_scope(graph, node, record)`, derived from `record.frozen`. `change`'s keyword is `paths`; G1039 adds `unified`.
- §3.4 and §5 item 4: `sync = {from, onto, merge, resolved}` becomes `synced = {old, onto, work, tip, merge, resolved}`. `sync.from` becomes `synced.old`, and `sync.onto` becomes `synced.onto`. The card treats `synced: null` (no sync, or rebase mode) as "no merge information".
- §5 item 6: "range-diff plus previous.syncs" becomes "`previous.interdiff` as the first-parent, no-merges log, plus `previous.syncs`".
- §5 item 2 and item 5 need no edit.
- G1039's widened predicate applies to merge mode only. In rebase mode carry stays today's patch-id map.

## 7. Other goals

- **G1025** (release lines, scheduled restack): pass 3 and the `restack` reason, `scheduled_for` and the one-per-attempt bound are kept as identifiers and behaviour. In merge mode the run they schedule is a merge sync. Each option-A cost in G1025's §5.1 table is answered:
  - Identity: 4.6.
  - Staleness and preserve: 4.4. The carried tests checkpoint is the real merge commit, not a virtual merge-tree.
  - Integrate rebuild: 4.5.
  - Successive combine commits: the explicit merge base (D1) merges only the goal's own change onto each new combine.
  - `line_sync`, the release-to-dev merges, `finish` and hotfix lines are unchanged.
  - A target change (`target` fp part) syncs with merge base = the old `base_commit`, which keeps exactly the goal's own change, and the trailer keeps the old line's history out of c2 (4.5.1).
- **G1021**: conflict findings (`local_conflict`, CONFLICTING/DIRTY/BEHIND) still target `base`. Only their text changes (4.7).
- **G1026**: the PR body is unchanged. "Built from zzzops/work/g<g> without docs(review) commits" becomes "squashed from zzzops/work/g<g> into tests and implementation". Its `zzzops: answer` record subjects are unchanged (4.8).
- **G1027**: ships `merge_sync.txt` and appends `merge_sync` to the pinned capability test list.
- **G1039**: section 6.
- **G1040** (`blocked_findings`): no functional overlap. Both append one line to the pinned capability list, a trivial adjacent conflict that `base` resolves.

## 8. Rollout and mid-flight goals

- **Before the policy requires `merge_sync`:** the new engine rebases as today. Already active: the scoped tests change, tests fixes on top, the squash, the date rule, the commit rules and the conventional engine subjects. None of them produces anything an older engine misreads destructively: an older engine recomputing an unscoped tests change only stales review_tests (safe), and the squashed PR branch is rebuilt by any engine's integrate.
- **The policy step** (owner-gated, like G1025's and G1027's): a policy branch adds `merge_sync` to `settings.engine.requires`. From then on older engines are paused (`engine_too_old`, or `policy_invalid` on 1.x builds, G1027), so no older engine can run `base` on a merged branch. Only then does the new engine write merge syncs. This is a precondition, not a race (D9).
- **Linear, rebased work branches** (every in-flight goal): the first merge-mode `base` merges with merge base = the recorded `base_commit`. That gives the tree a rebase would give, and every checkpoint relocates to M. Their recorded tests changes were computed unscoped, over a range that touched only the test paths, so the scoped value is equal and they carry (section 9).
- **Records with a non-empty `replay_map`** are ignored in merge mode. A leftover rebase in a worktree is aborted (4.1).
- **Existing PR branches** are re-squashed on their next integrate run: one engine force-update of `zzzops/pr/g<g>` per goal.
- No op version bump and no declared-output change (D8), so nothing goes stale on upgrade.
- **Root**: WORKER.md rule 6 ("put test fixes on the tests line BEFORE implementation commits") becomes obsolete once this ships. The root updates it, since it is not repository content.
- **Follow-up (proposed, not created):** once every repository using this engine requires `merge_sync`, a later goal deletes the rebase mode (base's rebase path, `replay_map` carry, `patch_ids`, the range-diff interdiff).

## 9. Legacy equivalence of the scoped change

For a record written before G1038, the tests checkpoint sat below implement's commits (H26, the suggested checkpoint and the hand reorders ensured that). So `diff(base, tests.commit)` touched only paths that test_design's phases committed, which is a subset of `frozen`. A pathspec that includes every changed path gives the same diff output, so the patch id is the same. The one exception is a legacy record with no `frozen` key. `checkpoint_scope` then returns None (unscoped), and its next submit scopes it.

## 10. Verified Git behaviours (Git 2.55.0, scratch repository)

- **range-diff and merge commits.** `git range-diff B..W O2..M2` (W linear, M2 = W plus two zzzops merges) lists only the three non-merge commits, each as `=`. range-diff skips merges, and because a merge sync never rewrites the goal's commits, every pair is identical. It has no `--first-parent`. So it shows nothing useful after a merge sync, and the card uses the first-parent log plus `--remerge-diff` (section 6, item 6).
- **`git show --remerge-diff <M>`** shows the conflict that merge-ort would have produced, with markers, against the recorded resolution, and names the modify/delete case.
- **Checking out a conflicted merge in the worktree.** `git merge-tree --write-tree --merge-base B O W` exits 1 and prints the tree OID, the conflicted stages (content conflict in `a.txt`, modify/delete for `d.txt`) and messages. After `git read-tree -u --reset <tree>`, the worktree holds `a.txt` with standard markers and `d.txt` with the modified version left in the tree. HEAD and the branch stay at W, and no merge state exists. Editing the files, then staging them, `write-tree` and `commit-tree -p W -p O`, produced the merge.
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
- **A stored `scope` key on checkpoints**: it is derivable from `frozen` (D3).
- **Bumping op_version, or removing `replay_map`/`replay_pos` from the declared outputs**: either stales every goal once (D8).
- **Blocking `base` until the policy requires `merge_sync`** (the other option in review_design:1:5): it would stop every goal's sync between the engine release and the policy step. Rebasing until then keeps today's behaviour in that window.
- **Walking the own commits as `P..W` only**: it walks into old bases' history (4.5.1).
- **Dates from the commits only (`--committer-date-is-author-date`, today)**: a reordered or later tests fix makes the PR head older than c1 (dogfood note 83).
- **Splitting tests and implementation commits by subject alone**: the owner's proposal keeps the split by frozen paths and phase ranges; the subject only adds the `test` requirement.

## 12. Risks

- **merge-ort rename detection** can move a goal edit across the F boundary, or into a renamed file. The conflict and carry checks still see it, because the scoped change differs, so the node re-runs. It never carries silently.
- **One-time costs**: one forced PR-branch update per in-flight goal. The first merge sync of an in-flight goal is a merge on top of rebased history, which is harmless.
- **Release notes**: semantic-release's notes list one line per goal (c2's subject) instead of one per commit. The release is the highest of the implementation commits'. The bodies keep every subject.
- **A missing trailer** (a merge made by hand outside the engine): the walk then falls back to its second parent only; it is refused by I1/I2 anyway unless it has the `chore(sync):` subject.
- **Test fixture churn**: engine_fixtures and many tests commit with free-form subjects; they get conventional subjects. Large but mechanical.
- **Dates ahead of the wall clock**: `prev + 1s` can put c1 and c2 a few seconds after the newest earlier head; harmless.
- **Card length with many frozen paths**: the blob fallback beyond 12 paths.
- **Lost edits on a moved onto during a conflict** (4.2): rare, and the block says so.
- **Rebase mode stays until the follow-up**: two sync paths live in base and carry for a while.

## 13. Testing

A new `.agents/test_engine_merge_sync.py`, a new `.agents/test_engine_conventional.py`, and updates to test_engine_base, checkpoint, identity, integrate_conflict, sync_edit, lifecycle and card_ux:
1. Trunk moves twice (merge mode): two merge commits on W, both pushes fast-forward (no force), both with `chore(sync):` subjects and a `Zzzops-Old-Base:` trailer. The first sync conflicts and is resolved through the worktree resume. The second sync touches the same file and is conflict-free (no redo). The resume with an untracked scratch file, a `*.orig` file, or an edit to a non-listed file re-blocks and lists those paths; after they are removed it stages only the listed files, and the merge tree has none of them. (Acceptance 1)
2. A tests fix after implement: accepted with no rewrite, in both modes. implement editing that path is refused with `test_freeze`, also when a later commit reverts it. The review_impl and approve_merge code views exclude F, and the review_tests view is only F. (Acceptance 2)
3. A no-commit test_design re-run after implement: `tests.change` is unchanged and implement is not stale.
4. Carry: a clean merge sync carries test_design and implement. A resolution in implementation files only carries test_design. A trunk change inside a test file's hunk stales test_design. preserve_check passes after a carry. `unchanged`, `relocate` and `checkpoint_scope` are called with the section 6 signatures, and no checkpoint has a `scope` key.
5. integrate: the PR head is exactly c1 (`test: …`) and c2 on `base_commit`, the trunk commit of the last sync (today's behaviour, R1), and `tree(c2) == code_tree(W)`. Two runs push nothing the second time. Type derivation: feat; fix; `revert:` + `refactor:` gives `revert` (patch); `!` and a `BREAKING CHANGE:` footer; only `refactor:` gives `refactor`; test_design's `test:` commits never decide c2. A tests-only goal, an implementation-only goal and a no-code goal. **Dates:** a goal whose tests fix is authored after the implementation gives `date(c2) > date(c1)`; a re-integrate after a sync gives both dates after the previous PR head's; the author and committer dates of each commit are equal. (Acceptance 3)
6. Explicit merge base and the own-commit walk: a dropped dependency, a rewritten dependency head, and a G1025 target change from dev to `release/N` each give exactly the goal's own change on the new onto, and c2's subject and body list only the goal's own commits (a dev `feat!:` commit does not appear and does not add `!`).
7. I1/I2: an engine merge is accepted; a merge touching `.zzzops/reviews`, or one without a `chore(sync):` subject, is refused; an agent merge is refused at submit.
8. The precondition: without `merge_sync` in `settings.engine.requires`, `base` rebases (today's outputs, `synced: null`, no merge commit on W); with it, `base` merges. A policy that requires `merge_sync` pauses an engine without the capability (`engine_too_old`).
9. Mid-flight: a linear rebased branch with old records syncs by merge once the policy requires `merge_sync` and carries. A rebase in progress is aborted and re-offered as a merge conflict. Legacy `tests.change` equals the scoped value.
10. Conventional commits: submit refuses a free-form subject with `commit_subject`; test_design refuses a `fix:` commit with `test_commit_type`, and accepts `test(engine):`; the combine commits are `chore(stack): …`; the review commits are still `docs(review): …`; goal-ref record commits keep `zzzops: answer …` (G1026's parser still matches).
11. Golden: no node_def_fp or input_fp changes for the default, release and 26-node graphs.
12. G1025 scheduled restack fires a merge sync in merge mode. G1021 conflict findings re-run base, which merges.
13. The docs guard, the capability list, and the HISTORY §4 row.

Commands: `python3 -m unittest discover -s .agents -p 'test_engine_merge_sync.py'`, `python3 -m unittest discover -s .agents -p 'test_engine_conventional.py'`, plus the updated files. CI runs the full suite.

## 14. Contract edits (this PR, per acceptance 4)

- **SPEC:**
  - §2.1 (the work branch is fast-forward only in merge mode), §3.5 (the preserved checkpoint's change is scoped to `frozen`, derived; the `synced` key), §3.17 (codes `commit_subject`, `test_commit_type`), §4.7 (`change` with `paths`), §4.13, §4.16, §4.20 (views, interdiff, syncs), §4.21 (rewritten), §5.2 (mode, merge sync, subjects, trailer), §5.4 (squash, own commits, messages, dates), §5.5 (texts), §7, §8.4 (REPAIR).
  - §4.14 (submit), new text: "Submit computes `frozen` before the checkpoint change. It checks the agent's own commits (`remote W..head`) in this order: a merge commit is refused (`validation`; only base makes merges); a subject that is not a conventional commit (`type(scope)!: summary`, type one of feat, fix, perf, revert, docs, style, chore, refactor, test, build, ci) is refused with `commit_subject`; a commit of the preserved node whose type is not `test` is refused with `test_commit_type`; a commit of a node that preserves which touches a frozen path is refused with `test_freeze`. Engine commits on work, stack and PR branches use the same grammar (`chore(sync):`, `chore(stack):`, `docs(review):`, the squash's `test:` and derived type). Record commits on goal and lease refs keep their machine subjects; they never reach the trunk. There is no suggested checkpoint: the default checkpoint is HEAD."
- **DESIGN:** the test-freeze section, the ops table, §3.16, and decisions rows recording that this supersedes G1025 O1 for goal work branches (gated on `merge_sync`) and the owner's conventional-commit rule.
- **HISTORY:** a §4 row.

No pending-amendment row is needed: this PR applies its own amendments, as G1026 did. If the root added one, this PR deletes it.

## 15. Out of scope

- Widening carry beyond an identical change (G1039).
- The sync-focused review_impl card and the budget (G1039).
- Resolving conflicts inside the stack set S (`deps_conflict` stays a wait).
- Release-line merges and `line_sync` (G1025, unchanged).
- Making the merge method or the PR shape configurable.
- Deleting the rebase mode (the proposed follow-up in section 8).
- Checking the subjects of commits made before this ships.

Size: about 1,000 to 1,300 lines of engine and tests. One goal, no child goals.
