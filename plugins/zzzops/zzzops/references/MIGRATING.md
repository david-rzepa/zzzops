# Migrating goals from the pre-reset engine

The CLI detects pre-reset state: `next` and `validate` show a `legacy` item (old goal issues, files and install roots), and an old-format `.zzzops/POLICY.json` is the `legacy_policy` blocker. Both point to the `migrate-zzzops-repository` skill, which inventories, triages and closes the old issues with one go-ahead from the user. This page covers the per-goal details.

The reset builds no automatic migration. Old goals stay on GitHub untouched: issue bodies, comments, labels and branches are the archive. Migrate a goal only when someone wants to continue it.

## Read an old goal
- Use the issue text and the goal's branches.
- For phase outputs, use the old engine's read-only decoding from a clone of the ZzzOps repository at the tag `zzzops-pre-reset` (the tag is only in that repository, so clone it outside yours):
  ```sh
  git clone https://github.com/david-rzepa/zzzops ../zzzops-pre-reset
  git -C ../zzzops-pre-reset checkout zzzops-pre-reset   # or 64d5196f6f4f if the tag is not published
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
2. Put artifacts on the work branch: for a design (and reviews you carry), commit the old text as `.zzzops/reviews/<id>/<node>.md` in a commit whose subject is `docs(review): <node> for G<id>` and which touches nothing else, then push the branch. Its value is `{"path": ".zzzops/reviews/<id>/<node>.md", "blob": "$(git rev-parse <commit>:<path>)", "commit": "<commit>"}`.
3. Record finished nodes with one `edit --file` of the whole goal document (`zzzops show <id> --json` gives the current one). Each record needs every field: `{"status": "done", "ok": true, "attempt": 1, "holder": "human"` (or the old agent's label) `, "reason": "new", "correction_runs": 0, "input_fp": "current", "fp_parts": {"def": "", "inputs": {}, "policy": {}}, "output": {…}, "findings": [], "finished_at": "<iso>"}`. Give checkpoint outputs as `{"commit": "<full 40-hex sha>"}`; the CLI completes them (`base`, `tree`, `change`) and replaces `"current"` with the real fingerprint and parts. Human approvals also need `decision`, `summary`, `decided_by`, `quote` and `decided_at` in `output`. When unsure, leave a node to re-run.
4. Run `zzzops edit` first without `--base` to see the impact preview, then with `--base`.

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
Release assignments from the old release-plan issue #695 are all release 1. Closing moot or delivered issues is what the `migrate-zzzops-repository` skill does; labels and comments stay as the archive.

## Adopting the lens graph (engine 1.1)
The 1.1 default graph replaces `review_design` and `review_impl` with seven review lenses per subject (`intent`, `simplicity`, `truth`, `adversary`, `concurrency`, `rollout`, `experience`, as `<lens>_design` and `<lens>_impl`) and a filter per subject (`filter_design`, `filter_impl`) that judges each non-material finding `keep` or `note`. A project adopts it through policy branches, in this order:
1. **Raise the floor:** `zzzops/policy/engine-1.1.0` raising `settings.engine.min` to `1.1.0`, with the "Upgrade the engine" recipe in REPAIR.md. Lens records carry finding keys (`impact`, `material`) that a 1.0 engine does not understand, so no lens may run while 1.0 clones still work.
2. **Change the graph:** a `zzzops/policy/lenses` branch with the new `workflow.json`, the lens and filter prompts (deleting `review_design.md` and `review_impl.md`), the instruction `review`, and `settings.intent` in POLICY.json. The owner writes the intent, in their words. Preview from a local ref first: `zzzops validate --policy-ref <ref>` and `zzzops next --policy-ref <ref>`.

**In-flight goals.** Old `review_design`/`review_impl` records become orphans (a warning), never deleted. Goals past `design` get the lenses as `ready (new)`; `base` and everything after it wait behind `filter_design`. No checkpoint is lost, but a kept finding reopens the design and asks `approve_design` again. Land the graph change when no goal is past `approve_design`; the preview lists the goals that are.

**Intent changes** are policy changes (a `zzzops/policy/*` branch, never a goal diff). A change stales `intent_design` and `intent_impl` on every open goal, without counting against the budget; until they and the filters re-run, each goal's later nodes wait. Land intent changes when few goals are in flight.

**Rollback:** a policy branch restoring the old files, keeping `engine.min`. The lens records become orphans; the old review records come back, current again where their inputs did not change. Engine 1.1 to 1.0 is forward-only for goals that ran lenses: use REPAIR's "Bulk revert of one bad release's writes".

**Editing the lens set** (adding, removing or renaming a lens): change both nodes of the lens, the filter's input from it (`optional` exactly when the lens is skippable), the context inputs of `approve_design`, `integrate` and `approve_merge`, and the prompt; then run `zzzops validate --policy --dir <dir>`. Renaming follows REPAIR's "Rename a node".
