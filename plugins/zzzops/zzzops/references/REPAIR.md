# ZzzOps repair recipes

Every recipe uses plain Git or `zzzops edit`. `<R>` is the remote (usually `origin`), `<id>` a goal id.

## A force-pushed goal branch (`goal_rewritten`)
Reads use the accepted tip; writes to that goal are refused. Make a forward commit that descends from both tips, keeping the good document:
<!-- run -->
```sh
good=$(git rev-parse refs/zzzops/goal/<R>/g<id>)
bad=$(git ls-remote <R> refs/heads/zzzops/goal/g<id> | cut -f1)
git fetch <R> refs/heads/zzzops/goal/g<id>
fix=$(git commit-tree "$good^{tree}" -p "$good" -p "$bad" -m "zzzops: repair G<id>")
git push <R> "$fix:refs/heads/zzzops/goal/g<id>"
```
A deleted goal branch (`goal_deleted`) is restored with `git push <R> refs/zzzops/goal/<R>/g<id>:refs/heads/zzzops/goal/g<id>`.

## Edit a goal branch directly
A commit on the goal branch is as valid as one made by `zzzops`: one file, `goal.json` (`json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False)` plus a newline), one parent (the current tip), and the trailers `Outcome:`, `State:` and `Engine:` in the message. `zzzops validate <id>` checks the result. Prefer `zzzops edit --file … --base …`, which validates before it pushes.
```sh
tip=$(git ls-remote <R> refs/heads/zzzops/goal/g<id> | cut -f1)
blob=$(git hash-object -w goal.json)
tree=$(printf '100644 blob %s\tgoal.json\n' "$blob" | git mktree)
c=$(git commit-tree "$tree" -p "$tip" -m "zzzops: edit G<id>" -m "Outcome: hand edit
State: open
Engine: hand")
git push <R> --force-with-lease=refs/heads/zzzops/goal/g<id>:$tip "$c:refs/heads/zzzops/goal/g<id>"
```

## Undo a goal change
```sh
git show <bad commit>^:goal.json > g<id>.json        # the document before the change
zzzops edit <id> --file g<id>.json --base <current goal commit>
```

## Delete an orphan or unparsable lease
<!-- run -->
```sh
tip=$(git ls-remote <R> refs/heads/zzzops/lease/g<id>/<node> | cut -f1)
git push <R> --force-with-lease=refs/heads/zzzops/lease/g<id>/<node>:$tip :refs/heads/zzzops/lease/g<id>/<node>
```

## Salvage work after `sync_refused` or `superseded`
```sh
git -C <worktree> branch zzzops-salvage/g<id>-<node>-a<attempt> HEAD
git -C <worktree> reset --keep <R>/zzzops/work/g<id>
```
Tell the human which commits were saved; nothing was pushed.

## Push work a crashed agent committed but never pushed
```sh
git -C <worktree> push <R> HEAD:refs/heads/zzzops/work/g<id>
```
(only when the remote branch is an ancestor of the local one).

## Upgrade the engine
1. Push `zzzops/policy/requires-<name>` adding the capability names to `settings.engine.requires` (this pauses new starts everywhere). Say in its PR body: an older build that reports `policy_invalid` on `settings.engine.requires` must be upgraded; never remove the key.
2. Wait until `zzzops next --all` shows nothing `running`.
3. Upgrade the plugin on every machine; `zzzops validate` lists the names under `engine.capabilities`.
4. Land the branch on the integration branch and delete it.

A policy that still has the deprecated `settings.engine.min` keeps working; replace it with `requires` in the same branch.

**Rollback:** land a policy change removing the names, then reinstall the older plugin. Goal documents the newer engine wrote with a newer goal schema are read-only for the older engine: revert each to its last older-schema version with the "Undo a goal change" recipe (find them with `git log --grep='^Engine: <newer build>$'`, the build from `zzzops --version`).

## Rename a node
While a policy branch is open, stage `records.<new>` (a copy of the old record), `skip.<new>` and any finding `target` rewrites on every goal, closed ones included, with one multi-goal `edit --file … --base …`; then land the workflow change and remove the old keys.

## Seed a child goal's work branch from its parent
A child goal created after its parent's design can start from the parent's work instead of the integration tip. Before its first artifact submit:
```sh
git push <R> <parent's checkpoint commit>:refs/heads/zzzops/work/g<child id>
```
Its `base` then rebases the child's own commits onto its stack base as usual; prefer a `depends_on` on the parent, which stacks automatically.

## A PR that conflicts with the integration branch
GitHub runs no `pull_request` workflows on a conflicting PR, so its checks never appear. `integrate` checks the merge locally (`git merge-tree`) and reads GitHub's `mergeable`; on a conflict it (like `merge`) raises a `conflict` finding on `base`. `base` then re-runs: it rebases onto the integration tip, or blocks with `rebase conflict in <files>`; resolve that in the goal worktree (`git add`, `git rebase --continue`) and run `start <id> base` again. If an older record is stuck on "required checks pending" for such a PR, reopen `base` by hand:
```sh
zzzops reopen <id> base --note "conflicts with <I>"
```

## Record a merge done on GitHub
Nothing to do by hand: `start <id> merge` observes a PR already merged into the integration branch and records it (and `approve_merge` records the human's merge as the approval, as the execute skill says).

## Purge data from a goal's history
`edit` writes a new version; earlier versions stay in the goal branch's history, and every clone keeps its accepted copy. To remove data (for example a pasted secret — rotate it first):
1. Temporarily lift the ruleset that blocks force-pushes on `zzzops/goal/**`.
2. Write the cleaned document as a new parentless commit and force-push it:
   ```sh
   blob=$(git hash-object -w goal.json)
   tree=$(printf '100644 blob %s\tgoal.json\n' "$blob" | git mktree)
   c=$(git commit-tree "$tree" -m "zzzops: purge G<id>" -m "Outcome: purged
State: open
Engine: hand")
   git push --force <R> "$c:refs/heads/zzzops/goal/g<id>"
   ```
3. On **every** clone: `git update-ref -d refs/zzzops/goal/<R>/g<id>` and `git gc --prune=now`, then `zzzops next`. A clone that skips this reports `goal_rewritten` and still holds the old data.
4. Restore the ruleset. Copies already fetched elsewhere (forks, caches) cannot be recalled; ask GitHub Support to purge cached views of a public repository.

## Delete old work branches
For goals closed more than N months ago with no open dependents:
```sh
git push <R> --delete zzzops/work/g<id>
```
Their artifacts then show "(full text no longer available)".

## Bulk revert of one bad release's writes
```sh
git log --format=%H --grep='^Engine: <build>$' refs/zzzops/goal/<R>/g<id>   # <build>: the bad build's `zzzops --version`
git show <commit>^:goal.json > g<id>.json      # the document before the bad write
zzzops edit <id> --file g<id>.json --base <current goal commit>
```

## Close a cancelled goal's PR and issue
`edit` makes no GitHub calls; it prints the `follow_up` commands, for example `gh pr close <n>` and `gh issue close <issue>`. Deleting a goal's stack branch (done by its close) lets GitHub close its PR and stack PR.

## Auto-deleted head branch in a branching repository

A stacked or release PR closed or moved to another base just after its dependency merged: GitHub's automatic head-branch deletion may have beaten the engine's retargeting. With the owner's authority, turn "Automatically delete head branches" off (`gh api -X PATCH repos/{o}/{r} -F delete_branch_on_merge=false`). Reopen the affected PR (`gh pr reopen <n>`) and correct its base (`gh pr edit <n> --base <target>`), or recreate it if GitHub cannot reopen it. The next `base` or `integrate` run reconciles its target.

## release/N or hotfix/x deleted after finish

Merging a finish PR uses the line branch itself as head, so automatic head-branch deletion removes a branch ZzzOps intends to keep. Read the line goal with `zzzops show <line-goal> --json`: `goal.records.sync.output.merged` is the recorded tip approved for and consumed by `finish`. Confirm it is the approved tip, not a newer unapproved sync, then restore the missing branch (never force-update an existing one):

```sh
git push <R> <recorded-tip>:refs/heads/<branch>
```

Once the finish PR has merged, its approved tip is reachable through production history, even if a back-merge has not finished; fetch that history if the tip is not local. Turn automatic deletion off with the owner's authority as above; `finish` back-merges use the approved SHA rather than the deleted branch name.
