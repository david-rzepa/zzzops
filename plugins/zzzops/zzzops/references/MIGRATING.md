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
`zzzops new --file goal.json` with the spec, `depends_on`, `release` (confirmed by the owner at triage; see the skill) and `links: {"issue": <old issue number>}`. New ids start at `settings.goals.first_id` (1000 here), so `G1002` never collides with an old `#812`.

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

## Partly fixed findings (capability `finding_follows`)
An engine with the capability `finding_follows` lets a reviewer link a new finding to the one it narrows (`follows`, a finding key an engine without it does not understand). `submit` accepts `follows` only once the policy requires `finding_follows`: push `zzzops/policy/requires-finding_follows` adding it to `settings.engine.requires`, with the "Upgrade the engine" recipe in REPAIR.md, after every clone has it. Until then reviewers resolve the finding and raise a plain new one. The same engine's other changes (carried findings, `previous.resolved`, `--repo`) store nothing new and need no capability. A deprecated `settings.engine.min` of `1.2.0` requires `finding_follows` too.

## Releases and housekeeping
Each migrated goal takes the release the owner confirmed at triage (the skill's step 4: from the old milestone, labels or release plan, its dependencies and priority). Releases are whole numbers; a goal waits only at its `merge` while its release is after `settings.releases.current`. A goal may not depend on a goal of a later release. Closing moot or delivered issues is what the `migrate-zzzops-repository` skill does; labels and comments stay as the archive.

## Adopting the lens graph (engine 1.1)
The 1.1 default graph replaces `review_design` and `review_impl` with seven review lenses per subject (`intent`, `simplicity`, `truth`, `adversary`, `concurrency`, `rollout`, `experience`, as `<lens>_design` and `<lens>_impl`) and a filter per subject (`filter_design`, `filter_impl`) that judges each non-material finding `keep` or `note`. A project adopts it through policy branches, in this order:
1. **Require the capability:** `zzzops/policy/requires-lens_findings` adding `lens_findings` to `settings.engine.requires`, with the "Upgrade the engine" recipe in REPAIR.md. Lens records carry finding keys (`impact`, `material`) that a 1.0 engine does not understand, so no lens may run while 1.0 clones still work. A 1.0 or 1.1 build reports `policy_invalid` on `requires`: upgrade it, never remove the key.
2. **Change the graph:** a `zzzops/policy/lenses` branch with the new `workflow.json`, the lens and filter prompts (deleting `review_design.md` and `review_impl.md`), the instruction `review`, and `settings.intent` in POLICY.json. The owner writes the intent, in their words. Preview from a local ref first: `zzzops validate --policy-ref <ref>` and `zzzops next --policy-ref <ref>`.

**In-flight goals.** Old `review_design`/`review_impl` records become orphans (a warning), never deleted. Goals past `design` get the lenses as `ready (new)`; `base` and everything after it wait behind `filter_design`. No checkpoint is lost, but a kept finding reopens the design and asks `approve_design` again. Land the graph change when no goal is past `approve_design`; the preview lists the goals that are.

**Intent changes** are policy changes (a `zzzops/policy/*` branch, never a goal diff). A change stales every node that declares `policy: ["intent"]` (`review_design` in the 1.3 graph; `intent_design` and `intent_impl` in the 1.1 graph) on every open goal, without counting against the budget; until they and the filters re-run, each goal's later nodes wait. Land intent changes when few goals are in flight.

**Rollback:** a policy branch restoring the old files, keeping `settings.engine.requires`. The lens records become orphans; the old review records come back, current again where their inputs did not change. Engine 1.1 to 1.0 is forward-only for goals that ran lenses: use REPAIR's "Bulk revert of one bad release's writes".

**From `engine.min` to `requires`.** `settings.engine.min` is deprecated but keeps working: `1.0.0` (or lower) requires nothing, `1.1.0` requires `lens_findings`, `1.2.0` requires `lens_findings` and `finding_follows`, `1.3.0` requires those and `lenses`, and anything higher is refused. `zzzops validate` warns `engine_min_deprecated` and names the capabilities to require instead; replace it through a policy branch.

## Adopting the consolidated review graph (capability `lenses`)
The 1.3 default graph has 15 nodes: one multi-lens reviewer per subject (`review_design` with seven lenses, beside a separate `adversary_design`; `review_impl` with `compliance`, `correctness`, `missing`, `tests` and `craft`), feeding `filter_design` and `filter_impl`. A reviewer's lenses are its `lenses` field; a goal removes an optional one with `skip["<node>:<lens>"]`. Adopt it through policy branches: first add the capability `lenses` to `settings.engine.requires` with the "Upgrade the engine" recipe in REPAIR.md (an engine without it reads `lenses` and tagged findings as invalid), then change `workflow.json`, add `review.md` and the five implementation lens prompts, and take the seven design lens prompts and the instruction `review` as shipped. Take the restructured `workflow.json` whole and re-apply local edits; do not text-merge it. Preview with `validate --policy-ref` and `next --policy-ref`.
- **From the 12-node graph:** `review_design`/`review_impl` records stay and re-run once as stale (`def`, `lenses`, and `policy.intent` for `review_design`), not counted against the budget; `adversary_design` and the filters are `ready (new)`; prior untagged findings count as material and are shown under the node id.
- **From the 26-node graph:** `adversary_design` stays current; the other lens records become orphans, and their open findings stop counting, so waive or resolve open material lens findings first. The default budget falls from 60 to 27: give a goal that has used more than 27 runs an explicit `budget` before landing.
- Land when no goal is past `approve_design`. **Rollback:** a policy branch restoring the old files, keeping `settings.engine.requires`.

**Editing the lens set:** add or remove an entry in the reviewer's `lenses` and its prompt file, then run `zzzops validate --policy --dir <dir>`. A non-skippable lens needs a `skippable: false` node. Separate single-lens nodes (G1000's form, such as `adversary_design`) still work: give each an input into its filter (`optional` exactly when it is skippable).

## Adopting release branching (capability `release_lines`)

Before landing a policy with `settings.branching`, require `release_lines` through the upgrade recipe in REPAIR.md and turn GitHub's "Automatically delete head branches" **off**: `gh api -X PATCH repos/{o}/{r} -F delete_branch_on_merge=false`. Merging a finish PR otherwise deletes the kept `release/N` or `hotfix/x` branch; dependency deletion can also close or move stacked and release PRs before the engine retargets them. The host-setting change needs the owner's authority; the engine never makes it. `zzzops validate` warns when the setting is on and readable, without failing validation (see SETUP.md). When removing `settings.branching`, restore the non-branching recommendation, **on**, with the owner's authority (`-F delete_branch_on_merge=true`).


## Adopting measured test cost (capability `test_cost`)

Upgrade every writer, then use a separately reviewed `zzzops/policy/*` branch requiring `test_cost`. Take the measured-review changes from the selected shipped graph/prompts: a cost object from the test writer; context inputs into test and implementation reviews; the checks result as merge-approval context; and the broader checks policy declaration `verification.commands` plus `verification`. These are configurable edges, not engine-reserved node names. The cost prompt requires observed integer milliseconds, command/exit/checkpoint and measured changed-test scope. Red observations are labeled failing; unavailable or incomplete measurements need correction/review, never guessed costs. Review prompts examine disproportionate sleeps, redundant full journeys and brittle time bounds.

Preview with `zzzops validate --policy-ref <branch>` and `zzzops next --policy-ref <branch>`. Adding a required test-writer output can stale its record and downstream review; broader declared policy can stale checks. Let live workers finish or stop/restart them as their changed-input contracts require before landing. Keep old evidence intact; do not mass-rewrite historical goals. A fresh adoption normally has no compatible timing baseline. Refresh template history with `.agents/template_history.py --write` when that updater is present in the source checkout; do not manufacture a competing store in an older checkout.

`parallel_commands` stays absent in the shipped default. Enable it only after inspecting all repository/goal commands for safety in a shared checkout and obtaining the owner's policy approval; ordered, mutating or genuinely exclusive commands remain sequential. Its presence, even false, requires test_cost and both checks policy declarations. The effective total worker budget is min(available CPUs, inherited positive ZZZOPS_TEST_WORKERS) before lane allocation; unsupported third-party commands can ignore it. Changing this repository's verification command to `python3 .github/scripts/run_product_validation.py --platform linux --local` also belongs in its separate owner-approved policy PR, not a product goal diff.

Explain both comparison scopes at approval. The whole plan includes goal-specific commands; the repository plan excludes those commands but includes actual mode and CPU allocation. Both qualify against one newest eligible merged source on the actual integration/release/hotfix target. If only goal commands differ, total can be unavailable while the nested repository delta is available; show its source and the caveat that concurrent goal workload/load/caches may differ. Changed repository plan/environment or missing narrower metadata makes that scope unavailable. Lookup caps/deadline, missing history and malformed evidence never select a convenient older baseline or fail an otherwise correct verification. No timing state service, automatic regression threshold or extra trunk suite is introduced.

If command-timeout cleanup cannot confirm a process tree or pipe has stopped, verification blocks for inspection and preserves the worktree. A parent-process kill fallback is not proof that descendants exited. Stop the reported remaining processes before retrying; the engine does not reset/clean beneath them. Optional baseline workers use their separate bounded cleanup allowance and still report unavailable rather than change the test outcome.


## Legacy detection and compatibility

**Legacy state.** When pre-reset ZzzOps state remains (old goal issues, files or install roots), `next` and `validate` carry a top-level `legacy` item: `message`, `counts` (`issues`, null when not yet counted; `files`; `refs` on the remote, counted only), `files` (at most 10), `skill` (`migrate-zzzops-repository`), `recheck`, `checked` and `dismiss`. It never pauses work: tell the user once and offer the skill. `validate` re-checks every time and adds the counted set: `issues` (up to 100 per search, linked goal issues removed), `linked`, `queries` (the exact search strings) and `truncated`. `next` checks GitHub (one search, one `ls-remote`) only when its local signals, the remote URL or the engine version change, and again daily while the item is active or after a failure; the `next` inside a write never checks. Dismiss it for the whole repository with `settings.legacy.ignore: true` (optional, default false) through a `zzzops/policy/*` branch. A pre-G1015 development build sees `legacy.ignore` as `policy_invalid` (work paused, writes refused): upgrade it.


## Clean-sync reviews and round budgets

G1039 widens merge-mode carry without changing recorded checkpoint identities: a transient scoped -U0 diff ignores context/line-number drift, plus a conservative whole-file union check protects edited hand-resolution positions. Stored change remains the carried -U3 identity. Frozen tests may carry while an implementation resolution stales code. A later real resubmit can recompute a different -U3 value and stale consumers once. Legacy rebase mode keeps its exact replay-map rule; merge_sync remains required before writing sync merges, with its existing sticky rollback restriction.

After every writer is upgraded and merge_sync is adopted, prepare a separate owner-approved policy branch requiring round_budget and taking the shipped implementation-review base input and after-sync prompt. The product source does not adopt installed policy, and the shipped default POLICY required set is unchanged. Preview with validate --policy-ref and next --policy-ref; the review definition can stale once under its existing exemption. Source rollout is not permission to reset counters or remove a capability to evade a budget item.

While round_budget is required, correction_runs accumulates done agent submits that introduce at least one new material finding, excluding follows/narrowings and notes. Count in the submitting node's stage, even when its finding targets another stage. First records can count; blocked records, ops/human answers and carry-only records do not. Existing definition/policy/candidate/lens-only exemptions stay. A no-checkpoint node stale only on inputs selecting git.base is also exempt even with new findings. A checkpoint producer stale only on base was not clean enough to carry, so a new-material round there still counts.

Each stage has the goal's explicit budget or default 10. At used >= limit, that stage's agent starts/reclaims stop; other stages, ops and human items continue. Continue sets the shared goal budget to the affected stage's used+10; hold/cancel retain their meaning. Existing cumulative counts survive activation and may require one owner raise. The internal GoalResult.budget shape is now `{limit, stages: {stage: {used, over, per_node}}}` with no old top-level used/agents/over. Public next output uses stage-specific human budget items rather than a new top-level budget object. Internal consumers must branch on the active policy/rule; without round_budget, legacy total counting, limit 3×agent-count, >limit test and old shape remain. Crash/dispute/repeat bounds are separate.

After a changed base, the configured implementation reviewer rechecks semantic interactions rather than redoing a whole carried review. sync evidence prioritizes recorded resolutions, cross-file names/removed lines and shared paths; it is a heuristic, not a carry gate. Its list/detail can be blobbed/folded; follow full read pointers. Portable literal diff commands, previous.interdiff and previous.syncs retain their existing semantics. A changed real tree reruns tree-bound checks; moving only a commit with the same tree does not force another test run.

## Shipped default updates

Copied policy is always the repository's policy; installing a plugin never replaces it. `.zzzops/TEMPLATE.json` records the default blob each file last reviewed, with removed-file tombstones, and the plugin's `templates/history/` keeps the old contents. `next` reports `policy_update` compactly; `validate` expands it. Use the bootstrap skill's “Update from the shipped defaults” section for a reviewed `zzzops/policy/*` branch, including declines that change only `record.reviewed`. For a repository without a record, `record.inferred` recovers exact history matches and marks customized files unknown; it does not invent provenance. `unknown_base` has no apply/diff and preserves its id, so upgrade first. If the newest plugin still cannot recognise it, explicitly reset that file's base to `null` or delete its tombstone in the policy branch and compare once manually.

Decide `workflow.json` before applying individual prompt changes. For the consolidated lens graph, take the restructured workflow whole and re-apply local edits as described above; copy new prompts only when the chosen graph uses them and remove old ones only when it no longer names them. Resolve conflict markers before landing, inspect line endings on Windows, and preview the policy's impact. Keeping or declining a default is a recorded review, not a promise that local content equals the default.
