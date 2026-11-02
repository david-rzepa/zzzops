# G1039 design: a clean trunk sync keeps the design and tests reviews; run_tests and a sync-focused review_impl re-run; the budget counts only rounds that raise new material findings

Revision 2, read at dev `f4eaf74` (G1022, G1027 merged), spec blob 6bc8a96 (with the "Budget redefinition" block). It builds on revision 1 and on G1038's approved revision 3. G1038 §6 is adopted verbatim (§5 here), and G1039 depends on G1038 and merges after it.

Changes from revision 1 (re-run because G1038's design was approved; no review findings were open):
- The carry predicate is G1038's `carry.unchanged(ident, node, key, old_cp, new_cp, scope)`. There is no checkpoint `scope` key: the scope is `records.checkpoint_scope(graph, node, record)`, derived from `record.frozen`. `Identity.change(base, commit, paths=None)` is G1038's; G1039 adds `unified=` (§3.1, §3.2, §5).
- The writer already keeps `change` (G1038 §6 item 5, `carry.relocate`), so G1039's revision-1 writer edit is gone (§3.2).
- The sync record is `synced = {old, onto, work, tip, merge, resolved}`, null when the base did not move and always null in rebase mode. The card treats null as "no merge information" (§3.4).
- `previous.interdiff` after a moved base is G1038's first-parent, no-merges log, plus `previous.syncs` (remerge-diffs). No range-diff in merge mode. The sync section no longer carries its own remerge-diff list (§3.4).
- New §3.7: what G1039 does in rebase mode (the policy does not yet require `merge_sync`): carry stays today's replay map, and the review_impl re-run, the sync card and the budget exemption still apply. Merge mode is sticky per branch, so the widened predicate never meets a branch that was rebased after a merge sync.
- §3.6 is checked against G1027's merged code: `round_budget` is one file under engine/capabilities/, and the new rule is written only while the policy requires it (SPEC §4.5, as `follows` is).
- Tests and fixture commits use conventional subjects (G1038 §4.8); the acceptance replays run with the policy requiring `merge_sync` (§6).
- The budget redefinition (§3.5) is unchanged.

## 1. Outcome
- A sync that leaves a node's own diff unchanged apart from context and line numbers carries that node. The node keeps its `change`, so everything bound to that change stays current. In the common case test_design and implement are carried, and design, review_design, approve_design, review_tests and approve_merge stay current. The check is per node: when a conflict resolution changes only implementation lines, test_design and review_tests stay current and implement re-runs.
- run_tests always re-runs after a sync, because the tree changed.
- review_impl always re-runs after a sync. Its card gains a `sync` section: what trunk brought in that touches the goal (files the goal also changes, lines the goal removes, names the goal removes or uses). It asks the reviewer for semantic conflicts only, not a full re-review.
- A sync that changes a node's own lines stales that node as today. This covers trunk edits inside the goal's hunks and any conflict resolution other than "keep both sides".
- The budget becomes a limit per stage on agent rounds that raise at least one new material finding. The default is 10 per stage. Reaching the limit asks the owner to continue, hold or cancel, as today. Clean-sync re-runs, resubmits that only carry findings forward, op reruns (run_tests) and human answers never count.

## 2. What was found at 25186a5
- **Staleness.** Frontier pass 2 compares record.input_fp with input_fp(fp_parts) (frontier.py:243-250). test_design and implement take `base.base_commit` as a non-context input, so every base move stales them unless `carry_forward` (carry.py, SPEC §4.21) rewrites their records inside base's finishing write.
- **Who is bound to what.** fp(checkpoint) = "change:"+change (fingerprint.py:14). review_tests (`tests` = test_design.tests.change), review_impl (`tests`, `code` = implement.code.change), filter_impl and approve_merge are bound to the change: they are current iff `change` is unchanged. run_tests (`code` = implement.code.tree) and integrate are bound to the tree, so they always re-run. review_impl's `checks` (run_tests.result) is a context input, so it never stales review_impl.
- **Today's carry predicate.** Every commit in old..checkpoint must appear in base's `replay_map` (identical per-commit patch ids at -U3). Any context change, any hand-touched commit or any shifted commit breaks it. The whole node then re-runs, and so does everything below it.
- **G1027 history** (zzzops/goal/g1027). Both syncs were rebase conflicts. In the second sync (5288bf7 -> 25186a5, the G1022 merge), docs/design/HISTORY.md, engine/__init__.py (ENGINE_VERSION 1.2.0->1.3.0, inside G1027's removal hunk) and references/CLI_USAGE.md conflicted. The resolver also amended the tests commit (e1e8d0f -> c401f1d, which landed in replay_pos, not replay_map), so test_design was not carried. As a result test_design att 7, review_tests att 6, implement att 4-7 and run_tests att 3-5 all re-ran. run_tests then failed twice on the graph26 fixture: G1022 added .agents/fixtures/graph26/POLICY.json with `"min": "0.0.0"`, which G1027 deprecates (engine_min_deprecated in test_engine_lenses' exact-warnings checks).
- **Verified on the real commits.** `git merge-tree 3b49062 25186a5`, the same sync done as a merge, conflicts in the same three implementation files and touches no tests path. The tests view (the paths of 5288bf7..e1e8d0f) has the same -U0 patch id before and after (89e6255c036f on both sides), so tests would be carried. The implementation view's -U0 id differs (942a830c vs 0eca9707, from the ENGINE_VERSION hunk), so implement stales, as it should.
- **Verified in a scratch repo.** A patch id over a `--unified=0` diff ignores line numbers, `index` blob ids and hunk-header function context. A trunk edit 2 lines from a goal hunk keeps the -U0 id, while the -U3 id changes. An adjacent-append conflict (a HISTORY row) resolved as "both rows" keeps the -U0 id.
- **Budget today** (SPEC §4.10): the sum of correction_runs over agent nodes must not exceed 3*agents (27; G1027's limit was raised to 30). G1027 reached 19 of 18, mostly through re-runs caused by syncs.

## 3. Approach
### 3.1 Clean, per checkpoint: the zero-context patch id
`delta(base, commit, scope) = ident.change(base, commit, paths=scope, unified=0)` (G1038 §6 item 3). `unified` replaces the `--unified=3` element of identity.py's `DIFF` list; everything else (CFG, `--attr-source`, PATHSPEC, G1038's literal pathspec from `paths`, `patch-id --verbatim`) is shared with `change`. The scope is `records.checkpoint_scope(graph, node, record)`: the record's `frozen` paths for the preserved node (test_design), else None. It identifies the node's own -/+ lines regardless of context and line numbers.
A checkpoint is clean across a sync from B1 to B2 iff `delta(B1, old_cp.commit, scope) == delta(B2, new_cp.commit, scope)`. Here `new_cp.commit = carry.relocate(old_cp, synced)`, the sync's work tip (the merge commit M). **This is G1039's definition of a clean sync for a node.** It does not use G1038's `synced.resolved`: equal -U0 ids mean the result is exactly "new trunk plus the goal's own lines". A conflict resolved as both sides is therefore clean, and one that changed or dropped either side is not. This matters because every goal adds a HISTORY §4 row, so adjacent-row conflicts happen on nearly every sync. `resolved` is used only in the card (§3.4).
Rejected alternatives:
- git range-diff: it needs commit series, gives text output, pairs commits heuristically and does not handle merge commits.
- The per-commit patch-id map used today: it is sensitive to context.
- Comparing file contents of the goal's paths: it fails whenever trunk touches the same file anywhere.
- `resolved == []` as the test: it is too strict (the HISTORY row) and too coarse (it cannot keep test_design when only implementation files were resolved).
- Redefining `change` itself at -U0: that changes `change` semantics (a capability, SPEC §4.5), and every checkpoint consumer of every in-flight goal would go stale once.

Re-verified at f4eaf74's exact flags (`--unified=0 --inter-hunk-context=0 --diff-algorithm=myers --indent-heuristic --full-index`, `patch-id --verbatim`): a goal edit on line 20, with trunk inserting a line at the top and editing line 22, gives equal -U0 ids across the merge (1c1ced131674 both sides) and different -U3 ids (6e8bb2bb7bfa vs 8af955757f23).

### 3.2 Carry: widening G1038's single predicate
G1038 owns the sync record, `carry.relocate`, `records.checkpoint_scope`, the carry loop and the single predicate `carry.unchanged(ident, node, key, old_cp, new_cp, scope)`. In merge mode its loop relocates every checkpoint of a candidate node to `synced.tip`, writes `new_cp = {commit, base: synced.onto, tree: code_tree(commit), change: old_cp["change"]}`, and carries the node iff `unchanged` holds for every checkpoint key. G1039 makes one edit: the predicate body.

```python
def unchanged(ident, node, key, old_cp, new_cp, scope):
    return (ident.change(old_cp["base"], old_cp["commit"], paths=scope, unified=0)
            == ident.change(new_cp["base"], new_cp["commit"], paths=scope, unified=0))
```

- G1038's body (`ident.change(new base, new commit, paths=scope) == old_cp["change"]`) tests for an identical -U3 diff. An identical -U3 diff has the same -/+ lines, so the widened body carries it too, except when Myers aligns the -U0 diff differently elsewhere in the file, which errs toward staling (§7).
- The written `change` is the recorded one (G1038 already writes it). So when the widened predicate carries a node whose -U3 diff did change, `change` is kept anyway, and the fingerprints of review_tests, review_impl's subject, filter_impl and approve_merge stay unchanged. Live findings stay live, because target_fp uses out_fp, which is keyed on the change.
- `scope` is passed in by the loop; legacy records without `frozen` are unscoped (G1038 §9).

The check runs per node, so G1027's merge replay carries test_design and stales implement. Responses are pruned and `carried_by: "base"` is set, as G1038 does.
Accepted risk: if a later real resubmit has the same diff, its change is recomputed at -U3 and its consumers stale once. That is rare and safe.

### 3.3 review_impl re-runs after every sync (workflow data, no engine rule)
review_impl gets a non-context input `"base": {"from": "base.base_commit"}` in templates/default/workflow.json; this repository's .zzzops/workflow.json gets it through a policy branch after merge. base_commit moves only on a sync, so after every sync review_impl is stale with `inputs.base`. After a clean sync that is its only stale key: `checks` is context, and `tests` and `code` are kept by §3.2. review_tests gets no such edge, so it stays current, which is the owner's choice. filter_impl re-runs after review_impl because its `review` input changes. It raises no findings, so it costs one cheap run and never counts toward the budget.
Adoption cost: review_impl's node definition changes, so it stales once (def only) in every in-flight goal. counts() already exempts definition changes.
Rejected alternatives:
- An engine rule that re-runs reviews whose subject was carried: it would also re-run review_tests, which the owner chose to keep.
- A new node field: it would need a new workflow format.

### 3.4 The sync-focused card (card.py, SPEC §4.20)
When a review node's stale_because contains an input that selects a `git.base` node, the card gets a `sync` section. B1 is the base recorded in the node's previous reviewed checkpoint (= `synced.old` when only one sync happened since), and B2 is the current base input (= `synced.onto`). The section is built from B1, B2 and the checkpoints only, so it is the same in both modes. `synced` (the base record's output key) only marks hand-resolved files; when it is null (no sync, or rebase mode) there is no merge information and nothing is marked.
```
"sync": {"from": B1, "to": B2, "commits": n, "files": m,
         "touching": [{"path": p, "why": "..."}],      # at most 12 inline: name/line hits first, then shared files
         "more": k, "all": <blob view of the full list, only when capped>,
         "diff": "git diff B1 B2 -- <touching paths>", "log": "git log --oneline --first-parent B1..B2",
         "ask": "The trunk moved under this goal. Review only for semantic conflicts between the goal and what trunk brought in: the touching entries first, then the rest of diff. previous.syncs shows how each sync merge was resolved. The goal's own commits since your last review are in previous.interdiff (empty when only syncs happened); review only those, not the whole goal. Raise one finding per conflict; approve if none."}
```
`touching` is built from two `git diff --unified=0` runs, with .zzzops/reviews excluded: T is the trunk diff B1..B2, and G is the goal's diff on the new base, cp.base..cp.commit.
- "the goal also changes this file (+a/-r)": paths in both T and G.
- "trunk adds `<line>`, a line the goal removes": a '+' line in T that equals (after stripping; at least 8 characters with a letter) a '-' line in G that is not also a '+' line in G.
- "trunk uses `<names>`, which the goal removes": '+' lines in T that contain a code-like name (snake_case, UPPER_CASE, camelCase or CamelCase; plain words are ignored) which appears in G's '-' lines and not in G's '+' lines.
- "trunk removes `<names>`, which the goal uses": code-like names in T's '-' lines and not in T's '+' lines that appear in G's '+' lines.
- "resolved by hand in sync <sha7>": a path in `synced.resolved` (merge mode only). These entries come first, before the name/line hits.

`commits` counts `git rev-list --count --first-parent B1..B2`, so a trunk that merges PRs with merge commits counts one per PR.

Prototype on the real G1027 second sync (5288bf7, 3b49062, 25186a5): 11 shared files and exactly one name/line hit, `.agents/fixtures/graph26/POLICY.json`: trunk adds `"min": "0.0.0"`, a line the goal removes (from templates/default/POLICY.json). The code-like filter leaves no prose-word noise. The section is about 1.3 KB inline. If the card is over 4,096 bytes, G1018's shrink steps blob `sync.touching`.
`previous` is G1038's, unchanged (G1038 §6 item 6). After a moved base in merge mode, `previous.interdiff` is `git log -p --first-parent --no-merges <old.commit>..<new.commit> -- <view paths>`: empty when implement was carried (only the sync merge lies between), and the goal's own new commits when implement re-ran after a conflict. `previous.syncs` lists `git show --remerge-diff <M>` for each sync merge on that path. In rebase mode `previous.interdiff` stays today's `git range-diff`, and there is no `syncs`. G1039 adds nothing to `previous`; the ask text points at it. The `touching` heuristic only orders what the reviewer reads. It never decides staleness.

### 3.5 Budget redefinition (SPEC §4.10; frontier.counts and finish_goal; records.py)
- **Round:** a done record of an agent node that adds at least one new material finding. That means an id `<node>:<attempt>:<k>` that is new in this submit, has `material` not false (schemas.py:579) and has no `follows`. Narrowings are already covered by the per-finding round and dispute caps. Human and op records never count.
- **Exempt:** a record that started `stale` with all of its stale keys being inputs that select a `git.base` node, even when it raises findings. This is exactly the clean-sync review_impl re-run (spec: "re-runs caused by a clean sync do not count"). If the sync was not clean for the subject, implement re-ran, review_impl is also stale on `inputs.code`, and the round counts normally. Carried records add no new record, so their counts stay. Carry-only resubmits raise no new ids, so they count 0 by definition. The existing definition, candidates, lenses and policy exemptions stay.
- **Storage: reuse `correction_runs` (decided).** records.py:231 keeps `previous + counts(...)`. counts() gains the submit's new findings as an argument and applies the rule above. Reasons:
  - The field already does exactly this job: it is the per-record cumulative counter that the budget reads.
  - Schema validation (integer >= 0) already covers it.
  - A new key would need a schema change and would leave a dead counter that every reader must learn to ignore.
  - The cost is a change of meaning in a stored field, and capability `round_budget` covers that (§3.6).

  Upgrade cost: in-flight goals keep the counts made under the old rule. A goal may therefore show a budget item once, and the owner raises it. Rejected: renaming the key, which costs a schema migration of every record for no behavioural gain.
- **Per stage, counted in the round's own node's stage (decided).** used[stage] is the sum of correction_runs over that stage's agent nodes. Because reviewers raise findings, a round counts in the reviewer's stage. Reasons:
  - A round is one submit of one node, so it has exactly one stage. Counting by target would split one round across stages (one review_impl submit can target design and implement) or count it twice.
  - The non-convergence the budget detects is a reviewer/subject loop, and the reviewer's stage is where that loop runs.
  - The value can be read from the record alone, with no finding-to-node join.

  Consequence: a delivery reviewer that keeps reopening design spends the delivery budget, which is where the loop is visible.
- **Limit and firing.** limit = doc.budget if set, else 10, applied to each stage. A stage is over iff used[stage] >= limit ("reaching it"). Then starts and reclaims of that stage's agents are refused with `budget_exceeded`. Ops, human items and the other stage continue. The item reads: "G<g> has had <n> rounds with new material findings in <stage> (limit <l>): <per node>. Continue, hold, or cancel?". Continue sets budget = n + 10. `res.budget` becomes `{"limit", "stages": {stage: {"used", "over", "per_node"}}}`. render, verbs.py:172 and the CLI_USAGE/MIGRATING texts follow.
- **Replays** (from goal-branch history, under the new rule):
  - G1026: discovery 3 (review_design a1, a3, a4); delivery 4 (review_tests a1, a2; test_design a1; implement a1). Its correction_runs sum was 22.
  - G1027: discovery 1, delivery 4. It never reaches 10 (it was 19 of 18).
  - G1022 1/1, G1025 2/2, G1028 1/1.

### 3.6 Capability (settled: `round_budget`), checked against G1027's merged code
G1027 is merged at f4eaf74: a capability is one file, `engine/capabilities/<name>.txt` (engine/__init__.py builds `CAPABILITIES` from the directory), the policy lists required names in `settings.engine.requires` (`schemas.required_caps`), and `store.floor_check` puts an engine lacking a required name on `engine_too_old` (it still reads, it never writes). SPEC §4.5 ("What ships with a new capability") requires a capability for a change in meaning of a stored field, and requires the rollout to add the name before the first such write. So:
- G1039 adds `engine/capabilities/round_budget.txt`: "Round budget (G1039): `correction_runs` counts review rounds that raise new material findings, and the budget is a per-stage limit on them. An engine without it counts every correction run against one total limit." `round_budget` is appended to `SHIPPED` in .agents/test_engine_capabilities.py (after G1038's `merge_sync`).
- **The new rule is gated, as `follows` is.** `records` and `finish_goal` use the round rule and the per-stage limit (§3.5) iff `"round_budget" in schemas.required_caps(settings)`. Otherwise `counts()` and `finish_goal` keep today's rule and total limit. Before the policy step older and newer engines therefore write the same meaning; after it, older engines are paused. The old branch is kept only until a follow-up deletes it (with G1038's rebase mode).
- The carry change needs no capability. `change` keeps its -U3 meaning; `delta` is never stored; an older engine just carries less. The work-branch format belongs to G1038's `merge_sync`.
- The review_impl `base` edge is plain workflow data that older engines read.

Rollout: one owner-gated policy branch, after G1038's `merge_sync` step, adds `round_budget` to `settings.engine.requires` and review_impl's `base` input to .zzzops/workflow.json. The provisional name `sync_carry` stays dropped.

### 3.7 Rebase mode and sticky merge mode
Until the policy requires `merge_sync`, G1038's `base` rebases, `synced` is null and `replay_map` is set, so `carry_forward` takes today's replay-map path and `unchanged()` is never called (G1038 §6 item 4). G1039 does not widen that path:
- **Carry in rebase mode is today's**: a node is carried only when every commit of its range has an identical per-commit -U3 patch id in `replay_map`. A rebase conflict or a hand-amended commit re-runs the node, as in G1027's second sync. Widening it would need positional relocation through `replay_pos` and a second predicate, for a mode G1038 plans to delete (G1038 §8 follow-up), so it is rejected.
- **The rest works in both modes.** review_impl's `base` input moves on every sync, so review_impl re-runs. When the replay map carried implement, its only stale key is `inputs.base`, and its card has the `sync` section (with no resolved marks and today's range-diff interdiff). The budget exemption (§3.5) keys on stale inputs, not on the mode. run_tests always re-runs.
- **Sticky merge mode** (G1038 D9): once a work branch has a sync merge, the new engine never rebases it; without `merge_sync` in the policy, `base` blocks with a policy item and writes no record. So a branch that the widened predicate has carried across a merge is never later rebased, and `old_cp` and `new_cp` always come from merge-mode syncs on that branch.
- **The first merge sync of a linear branch** uses merge base = the recorded `base_commit` (G1038 §8). Its checkpoints relocate to M and the widened predicate applies from that sync on.

So spec acceptance 1 (G1027's conflicting rebase sync) is met in merge mode: the replay runs with `merge_sync` required. In rebase mode G1027's history is unchanged except for review_impl's sync card and the budget.

## 4. Interfaces and data that change
| What | Where | Kind |
|---|---|---|
| `carry.unchanged(ident, node, key, old_cp, new_cp, scope)` body -> -U0 delta (merge mode) | carry.py (G1038's function) | Behaviour |
| `Identity.change(base, commit, paths=None, unified=3)`: the `unified` keyword | identity.py | Internal, additive |
| card `sync` section, constant ask text | card.py | Card, additive |
| counts() rule and signature; finish_goal per stage; `res.budget` shape; budget item text and raise; start/reclaim refusal per stage; all gated on `round_budget` in the policy | frontier.py, records.py, render.py, verbs.py | Behaviour; `res.budget` is internal and in `next --json` (additive `stages`) |
| review_impl input `base` | templates/default/workflow.json | Workflow data |
| `round_budget.txt`; `SHIPPED` in test_engine_capabilities.py | engine/capabilities/ | Capability |
| SPEC §3.4 (correction_runs meaning), §4.5 (the `round_budget` entry), §4.7 (`unified`, delta), §4.10 (budget), §4.20 (sync card), §4.21 (the widened predicate, merge mode only), §7; DESIGN amendment and decisions row; HISTORY §4 row; MIGRATING and CLI_USAGE budget text | docs | Contract |

## 5. The split with G1038, and the contract adopted verbatim
G1038 owns the sync record, relocation, the scope helper, the carry loop, the single carry predicate and its exact body, the moved-base interdiff, rebase mode and sticky merge mode. G1039 owns the widened predicate body (§3.1, §3.2), `unified=`, the review_impl `base` edge and the sync card (§3.3, §3.4), and the budget (§3.5, §3.6). G1039 implements no carry loop and no relocation.

G1038 §6, adopted verbatim:
1. **The predicate.** `carry.unchanged(ident: Identity, node: str, key: str, old_cp: dict, new_cp: dict, scope: list[str] | None) -> bool`, called once per checkpoint key of each candidate node; its results alone decide carry. G1039 replaces the body with `delta(old_cp["base"], old_cp["commit"], scope) == delta(new_cp["base"], new_cp["commit"], scope)`.
2. **The scope.** `records.checkpoint_scope(graph, node, record) -> list[str] | None`: `sorted(record["frozen"])` if `node` is named by some node's `preserve` and the record has `frozen`, else None. Derived, never stored: checkpoints have no `scope` key. `carry_forward` computes it and passes it to `unchanged`.
3. **`change`.** `Identity.change(base, commit, paths=None) -> str`. G1039 adds `unified: int = 3` (passed as `--unified=<n>` to the diff that feeds the patch id) and defines `delta(base, commit, scope) = ident.change(base, commit, paths=scope, unified=0)`.
4. **The sync record.** The base output key `synced` (undeclared, unfingerprinted; also `Done.synced`): `{"old", "onto", "work", "tip", "merge", "resolved"}`. It is null when the base did not move, and always null in rebase mode (then `replay_map` is set, carry takes today's path and `unchanged()` is not called). The card reads `resolved` (and `merge` for the sha in the `why` text) and treats null as no merge information.
5. **Relocation.** `carry.relocate(cp, synced) -> str | None`: `synced["tip"]` if `cp["commit"]` is `synced["work"]` or an ancestor of it, else None. The writer builds `new_cp = {commit, base: synced["onto"], tree: code_tree(commit), change: old_cp["change"]}`, so the kept `change` is already written. Carried records get `carried_by: "base"` and keep `frozen`. `base_commit` stays a declared base output (= `synced.onto`), which review_impl's new input selects.
6. **The moved-base interdiff.** `previous.interdiff`: same base, `git diff <old.commit> <new.commit> -- <view paths>`; moved base in merge mode, `git log -p --first-parent --no-merges <old.commit>..<new.commit> -- <view paths>`; moved base in rebase mode, today's `git range-diff`. `previous.syncs`: `git show --remerge-diff <M>` per merge commit on the first-parent path, oldest first, absent when none. No range-diff for merge-synced branches.

The G1039 edits G1038 §6 lists, all made in this revision:
- §3.2 and §5 item 1: the signature is `unchanged(ident, node, key, old_cp, new_cp, scope)`, with `scope` passed in.
- §3.1, §3.2 and §5 item 3: no checkpoint `scope` key; the scope is `records.checkpoint_scope(graph, node, record)`; `change`'s keyword is `paths`, and G1039 adds `unified`.
- §3.4 and §5 item 4: `synced = {old, onto, work, tip, merge, resolved}`; `sync.from` is `synced.old`, `sync.onto` is `synced.onto`; null means no merge information.
- §5 item 6: `previous.interdiff` is the first-parent, no-merges log, plus `previous.syncs`.
- §5 items 2 and 5: no edit needed (the writer keeps `change`; `carried_by` and `base_commit` as before).
- The widened predicate applies to merge mode only; rebase mode keeps today's patch-id map (§3.7).

**Ordering.** G1039 depends on G1038 and merges after it (already in its `depends_on`). Its rollout step follows G1038's `merge_sync` step.

## 6. Tests
A new file, `.agents/test_engine_clean_sync.py`, plus edits to test_engine_frontier.py (counts), test_engine_card_budget.py (card size) and G1027's capabilities test (pinned list). Fixtures use engine_fixtures and test_engine_lifecycle helpers: a temporary bare remote, a trunk, and one goal on the default graph driven through the CLI with scripted submits. Unless a test says otherwise, the fixture policy requires `merge_sync` and `round_budget`. Every fixture commit has a conventional subject (G1038 §4.8 refuses others at submit): tests commits are `test: …`, implementation commits `feat: …` or `fix: …`, trunk commits `chore: …` or `docs: …`.
Commands, run from the worktree root:
- `python3 -m unittest discover -s .agents -p 'test_engine_clean_sync.py'`
- `python3 -m unittest discover -s .agents -p 'test_engine_frontier.py'`
- `python3 -m unittest discover -s .agents -p 'test_engine_card_budget.py'`
- `python3 -m unittest discover -s .agents -p 'test_engine_capabilities.py'`

1. **delta properties** (Identity, scratch repo, the real `DIFF` flags with `unified=0`). Equal -U0 id under: a line shift, a changed `index` line, changed hunk-header function context, a trunk edit 2 lines from a goal hunk, and an adjacent-append conflict resolved as both sides. In the last two cases the -U3 change differs; asserting that proves the widening. A different id when: one goal line changes, or a resolution drops one side. With `paths=checkpoint_scope(...)`, a change outside the frozen paths leaves the id equal. `unified` defaults to 3, so `change` values are unchanged (the pinned identity fixtures still pass).
2. **G1027 replay in miniature (acceptance 1).**
   - Setup: the goal removes `"min": "0.0.0"` from templates/default/POLICY.json, edits engine/__init__.py inside a version hunk, and adds a HISTORY row. Trunk then adds .agents/fixtures/graph26/POLICY.json containing `"min": "0.0.0"`, appends an adjacent HISTORY row, and bumps the version line inside the goal's hunk. Base conflicts; the fixture resolves HISTORY as both rows and __init__.py with the new version, then resumes.
   - Expect: test_design carried (`carried_by == "base"`, tests.change identical, commit == `synced.tip` == M, no `scope` key). design, review_design, approve_design and review_tests current. implement stale. After implement resubmits, run_tests is ready. The review_impl card has `sync.touching` with an entry for `.agents/fixtures/graph26/POLICY.json` whose `why` is "trunk adds `\"min\": \"0.0.0\"`, a line the goal removes". Its `touching` lists HISTORY.md and engine/__init__.py first, as "resolved by hand in sync <sha7>"; `previous.syncs` has the remerge-diff of M, and `previous.interdiff` is the first-parent log of implement's new commits.
3. **Clean variant.** Same setup without the version bump. implement is carried too. review_impl `stale_because == ["inputs.base"]`; its card has `sync` with the ask text, and `previous.interdiff` lists no commits. run_tests is ready; review_tests, filter_impl (until review_impl submits) and approve_merge are current. review_impl then submits a new material finding: every node's correction_runs is unchanged.
4. **Context-only trunk edit** 2 lines from a goal hunk, merged with no conflict: both nodes carried. G1038's exact predicate alone would not carry them; the test asserts the -U3 change differs.
5. **Rebase mode and sticky mode.** Without `merge_sync` in the policy: a clean rebase whose per-commit patch ids are identical carries both nodes through `replay_map` (`unchanged` is not called; a spy asserts it), review_impl is stale only on `inputs.base`, its card has `sync` with no resolved marks and a range-diff `previous.interdiff`, and its finding counts 0. A context-only trunk edit beside a goal hunk re-runs the node in rebase mode (today's rule) but carries it in merge mode (test 4). A branch with a sync merge, under a policy without `merge_sync`, blocks `base` (G1038's item) and nothing is carried or counted.
6. **Conflicting sync stales as today (acceptance 2).** A resolution that changes a test line: test_design and review_tests stale, and implement stale through its tests input. A HISTORY resolution that drops trunk's row: the node owning HISTORY stales.
7. **counts() table** (unit tests over records.py/frontier). New material finding -> 1. Only `follows` -> 0. `material: false` -> 0. No findings -> 0. Stale only on `inputs.base` with a finding -> 0. Stale on `inputs.base` and `inputs.code` with a finding -> 1. Definition-only re-run -> 0. Human or op record -> 0. Without `round_budget` in the policy, today's rule and total limit apply (the old table still passes).
8. **Per-stage limit.** With delivery used = 9, there is no item. At 10: `next` shows the delivery budget item with the text above. `start` of a delivery agent is refused with `budget_exceeded`, a reclaim too. A discovery agent start, run_tests and human items proceed. Continue sets budget = 20. doc.budget = 4 applies to each stage.
9. **Replays (acceptance, budget).** The G1026 and G1027 round sequences (node, attempt, new material ids, stale keys) are encoded as literal data derived from their goal branches. Expected counts: G1026 discovery 3 / delivery 4; G1027 1 / 4; neither stage reaches 10. An extra check runs only when refs/zzzops/goal/origin/g1026 and g1027 exist (skipUnless): it recomputes the counts from the real records and expects the same numbers.
10. **Real-commit card check** (skipUnless 5288bf7, 3b49062 and 25186a5 exist). The `touching` builder over those commits has 11 shared files and exactly one name/line hit, the graph26 POLICY.json entry.
11. **Workflow and size.** The template's review_impl has a non-context `base` input from base.base_commit; review_tests and filter_impl have none. A review_impl card with `sync`, at real sizes, is at most 4,096 bytes after shrink, and with 40 touching paths `sync.all` is a blob view and only 12 entries are inline (G1018 guarantees G1-G3 still hold).
12. **Capability and docs.** `round_budget` is in CAPABILITIES and in `SHIPPED`. A policy requiring `round_budget` puts an engine copy without the file on `engine_too_old` (CapWorld.without). The docs guard passes, and the HISTORY §4 row is present.

## 7. Risks and out of scope
- A kept `change` can stale consumers once on a later identical resubmit.
- -U0 alignment shifts err conservative: they stale the node.
- Name matching is a heuristic that only orders the card.
- Upgrading resets nothing: old correction_runs values may show one budget item per goal.
- One `doc.budget` value applies to both stages. A per-stage override is left for later if ever needed.
- Two budget rules live in the code until rebase mode and the old rule are deleted together (follow-up).
- Rebase mode carries less than merge mode (§3.7); the gap closes when the policy requires `merge_sync`.
- approve_merge stays current after a clean sync, as today. The owner approved the change, and the tree check is run_tests' job.
- Out of scope:
  - merge mechanics, the conflict flow, sticky mode, the integrate squash and conventional-commit enforcement (G1038);
  - widening carry in rebase mode;
  - this repository's policy branch (a follow-up with the rollout);
  - any change to the per-finding round and dispute caps.
