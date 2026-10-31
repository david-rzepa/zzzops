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
1. Push `zzzops/policy/engine-<X>` raising `settings.engine.min` to `<X>` (this pauses new starts everywhere).
2. Wait until `zzzops next --all` shows nothing `running`.
3. Upgrade the plugin on every machine.
4. Land the branch on the integration branch and delete it.

**Rollback:** land a policy change lowering `engine.min`, then reinstall the older plugin. Goal documents written by the newer engine stay readable only if their schema did not change.

## Rename a node
While a policy branch is open, stage `records.<new>` (a copy of the old record), `skip.<new>` and any finding `target` rewrites on every goal, closed ones included, with one multi-goal `edit --file … --base …`; then land the workflow change and remove the old keys.

## Delete old work branches
For goals closed more than N months ago with no open dependents:
```sh
git push <R> --delete zzzops/work/g<id>
```
Their artifacts then show "(full text no longer available)".

## Bulk revert of one bad release's writes
```sh
git log --format=%H --grep='^Engine: <version>$' refs/zzzops/goal/<R>/g<id>
git show <commit>^:goal.json > g<id>.json      # the document before the bad write
zzzops edit <id> --file g<id>.json --base <current goal commit>
```

## Close a cancelled goal's PR and issue
`edit` makes no GitHub calls; it prints the `follow_up` commands, for example `gh pr close <n>` and `gh issue close <issue>`. Deleting a goal's stack branch (done by its close) lets GitHub close its PR and stack PR.
