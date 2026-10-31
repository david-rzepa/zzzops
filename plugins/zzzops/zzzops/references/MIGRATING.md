# Migrating goals from the pre-reset engine

The reset builds no migration tooling. Old goals stay on GitHub untouched: issue bodies, comments, labels and branches are the archive. Migrate a goal only when someone wants to continue it.

## Read an old goal
- Use the issue text and the goal's branches.
- For phase outputs, use the old engine's read-only decoding from a worktree at the tag `zzzops-pre-reset`:
  ```sh
  git worktree add ../zzzops-pre-reset zzzops-pre-reset
  python3 -c "import sys; sys.path.insert(0, '../zzzops-pre-reset/plugins/zzzops/zzzops'); import comment_store; help(comment_store.decode_envelope)"
  ```
- Never run `zzzops goal inspect` from the old engine: it writes.

## Create the new goal
`zzzops new --file goal.json` with the spec, `depends_on`, `release` and `links: {"issue": <old issue number>}`. New ids start at `settings.goals.first_id` (1000 here), so `G1002` never collides with an old `#812`.

## Carry finished work forward (judgment)
1. Point the work branch at the accepted checkpoint commit:
   ```sh
   git push origin <accepted commit>:refs/heads/zzzops/work/g<id>
   ```
2. Record finished nodes with one `edit --file` of the whole goal document: put each finished node under `records` with `"input_fp": "current"`, its outputs, and checkpoints given as `{"commit": "<sha>"}`. The CLI completes the checkpoints (`base`, `tree`, `change`) and the fingerprints. When unsure, leave a node to re-run.
3. Run `zzzops edit` first without `--base` to see the impact preview, then with `--base`.

## Old nodes and new nodes
| Old | New |
|---|---|
| understand | design |
| review_understanding | review_design |
| approve_understanding | approve_design (`decided_by: "unknown (pre-reset)"`) |
| test_design | test_design |
| review_test_design | review_tests |
| implement | implement |
| review_implement | review_impl |

Publication nodes are not carried: the operations re-observe.

## Releases and housekeeping
Release assignments from the old release-plan issue #695 are all release 1. Closing moot or delivered issues and removing stale labels is optional and done by hand.
