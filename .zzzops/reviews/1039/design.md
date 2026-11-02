# G1039 design: a clean trunk sync keeps the design and tests reviews; run_tests and a sync-focused review_impl re-run; the budget counts only rounds that raise new material findings

Revision 1, read at dev `25186a5` (G1022 merged), spec blob 6bc8a96 (with the "Budget redefinition" block). G1039 builds on G1038 (sync by merge), which is designed in parallel. §5 says exactly what it takes from G1038, and why G1039 must merge after it.

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
`delta(base, commit, scope)` is `Identity.change(base, commit, scope, unified=0)`. It uses the same config, environment and pathspec as `change`, including G1038's checkpoint `scope`. It identifies the node's own -/+ lines regardless of context and line numbers.
A checkpoint is clean across a sync from B1 to B2 iff `delta(B1, old.commit) == delta(B2, new.commit)`. Here `new.commit` is the merge commit M that G1038 gives every carried checkpoint. **This is G1039's definition of a clean sync for a node.** It does not use G1038's `sync.resolved`: equal -U0 ids mean the result is exactly "new trunk plus the goal's own lines". A conflict resolved as both sides is therefore clean, and one that changed or dropped either side is not. This matters because every goal adds a HISTORY §4 row, so adjacent-row conflicts happen on nearly every sync. `resolved` is used only in the card (§3.4).
Rejected alternatives:
- git range-diff: it needs commit series, gives text output, pairs commits heuristically and does not handle merge commits.
- The per-commit patch-id map used today: it is sensitive to context.
- Comparing file contents of the goal's paths: it fails whenever trunk touches the same file anywhere.
- `resolved == []` as the test: it is too strict (the HISTORY row) and too coarse (it cannot keep test_design when only implementation files were resolved).
- Redefining `change` itself at -U0: that changes fingerprint semantics, so every checkpoint consumer of every in-flight goal would go stale once.

### 3.2 Carry: widening G1038's single predicate
G1038 owns the sync record, the carry loop and the existence of its single predicate `unchanged(node, old_cp, new_cp)` in carry.py. Its loop moves every carried checkpoint to commit M on base `onto`, and its predicate is "recomputed change == recorded change". G1039 makes two edits:
1. **The predicate body** becomes `delta(old_cp.base, old_cp.commit, scope) == delta(new_cp.base, new_cp.commit, scope)`. The scope is the checkpoint's recorded `scope`; a legacy record without one is unscoped, as G1038 does.
2. **The written `change` is kept:** `new_cp.change = old_cp.change` whenever the predicate holds. Under G1038's exact predicate the kept and recomputed values are identical, so this edit does nothing until the predicate is widened. Keeping `change` keeps the fingerprints of review_tests, review_impl's subject, filter_impl and approve_merge unchanged. Live findings also stay live, because target_fp uses out_fp, which is keyed on the change.

The check runs per node, so G1027's merge replay carries test_design and stales implement. Responses are pruned and `carried_by: "base"` is set, as G1038 does.
Accepted risk: if a later real resubmit has the same diff, its change is recomputed at -U3 and its consumers stale once. That is rare and safe.

### 3.3 review_impl re-runs after every sync (workflow data, no engine rule)
review_impl gets a non-context input `"base": {"from": "base.base_commit"}` in templates/default/workflow.json; this repository's .zzzops/workflow.json gets it through a policy branch after merge. base_commit moves only on a sync, so after every sync review_impl is stale with `inputs.base`. After a clean sync that is its only stale key: `checks` is context, and `tests` and `code` are kept by §3.2. review_tests gets no such edge, so it stays current, which is the owner's choice. filter_impl re-runs after review_impl because its `review` input changes. It raises no findings, so it costs one cheap run and never counts toward the budget.
Adoption cost: review_impl's node definition changes, so it stales once (def only) in every in-flight goal. counts() already exempts definition changes.
Rejected alternatives:
- An engine rule that re-runs reviews whose subject was carried: it would also re-run review_tests, which the owner chose to keep.
- A new node field: it would need a new workflow format.

### 3.4 The sync-focused card (card.py, SPEC §4.20)
When a review node's stale_because contains an input that selects a `git.base` node, the card gets a `sync` section. B1 is the base recorded in the node's previous `reviewed` checkpoint (= G1038 `sync.from` when only one sync happened since), and B2 is the current base input (= `sync.onto`):
```
"sync": {"from": B1, "to": B2, "commits": n, "files": m,
         "touching": [{"path": p, "why": "..."}],      # at most 12 inline: name/line hits first, then shared files
         "more": k, "all": <blob view of the full list, only when capped>,
         "diff": "git diff B1 B2 -- <touching paths>", "log": "git log --oneline B1..B2",
         "resolved": ["git show --remerge-diff <M>"],  # only when G1038's sync.resolved is non-empty
         "ask": "The trunk moved under this goal. Review only for semantic conflicts between the goal and what trunk brought in: the touching entries first, then the rest of diff. The goal's own diff is unchanged since your last review unless interdiff is shown; review only that interdiff. Raise one finding per conflict; approve if none."}
```
`touching` is built from two `git diff --unified=0` runs, with .zzzops/reviews excluded: T is the trunk diff B1..B2, and G is the goal's diff on the new base, cp.base..cp.commit.
- "the goal also changes this file (+a/-r)": paths in both T and G.
- "trunk adds `<line>`, a line the goal removes": a '+' line in T that equals (after stripping; at least 8 characters with a letter) a '-' line in G that is not also a '+' line in G.
- "trunk uses `<names>`, which the goal removes": '+' lines in T that contain a code-like name (snake_case, UPPER_CASE, camelCase or CamelCase; plain words are ignored) which appears in G's '-' lines and not in G's '+' lines.
- "trunk removes `<names>`, which the goal uses": code-like names in T's '-' lines and not in T's '+' lines that appear in G's '+' lines.

Prototype on the real G1027 second sync (5288bf7, 3b49062, 25186a5): 11 shared files and exactly one name/line hit, `.agents/fixtures/graph26/POLICY.json`: trunk adds `"min": "0.0.0"`, a line the goal removes (from templates/default/POLICY.json). The code-like filter leaves no prose-word noise. The section is about 1.3 KB inline. If the card is over 4,096 bytes, G1018's shrink steps blob `sync.touching`.
`interdiff` (G1038's moved-base form) appears when the subject's change changed, for example when implement re-ran after a conflict. The card then asks for the interdiff plus the sync, still not a full re-review. The `touching` heuristic only orders what the reviewer reads. It never decides staleness.

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

### 3.6 Capability (settled: `round_budget`)
G1039 adds one file, `engine/capabilities/round_budget.txt` (G1027's form). It guards the new meaning of `correction_runs` and the per-stage budget. An older engine writing records would add increments under the old rule, which inflates the new counter, and it would apply the old total limit. So a mixed fleet must be locked out. The name is appended to G1027's pinned test list.
The carry change needs no capability:
- `change` is an opaque fingerprint that no engine recomputes and checks (verbs.py:496 and 1064 only write it).
- An older engine just carries less.
- The work-branch format change belongs to G1038's `merge_sync`.

The review_impl edge is plain workflow data that older engines read. Rollout: one policy branch adds `round_budget` to settings.engine.requires and review_impl's `base` input, after G1038's `merge_sync` step. It is owner-gated, like G1025's step.
The provisional name `sync_carry` is dropped: it described the carry, which needs no gate.

## 4. Interfaces and data that change
| What | Where | Kind |
|---|---|---|
| `unchanged()` body -> -U0 delta; carried `change` kept | carry.py (G1038's function) | Behaviour |
| `Identity.change(..., unified=3)` keyword | identity.py | Internal, additive |
| card `sync` section, constant ask text | card.py | Card, additive |
| counts() rule and signature; finish_goal per stage; `res.budget` shape; budget item text and raise; start/reclaim refusal per stage | frontier.py, records.py, render.py, verbs.py | Behaviour; `res.budget` is internal and in `next --json` (additive `stages`) |
| review_impl input `base` | templates/default/workflow.json | Workflow data |
| `round_budget.txt` | engine/capabilities/ | Capability |
| SPEC §3.4 (correction_runs meaning), §3.5 (change kept on carry), §4.7 (delta), §4.10 (budget), §4.20 (sync card), §4.21 (carry predicate), §7; DESIGN amendment and decisions row; HISTORY §4 row; MIGRATING and CLI_USAGE budget text | docs | Contract |

## 5. The split with G1038, and what G1039 depends on
G1038 owns:
- the sync record;
- the carry loop;
- the existence of the single carry predicate;
- the unchanged-change carry it already defines.

G1039 owns:
- the clean-sync definition by zero-context patch id (§3.1);
- keeping reviews current through the kept `change` (§3.2);
- the review_impl `base` edge and the sync-focused card (§3.3, §3.4);
- the budget (§3.5).

G1039 implements no carry loop and no relocation of its own.
What G1039 uses from G1038, exactly:
1. **`unchanged(node, old_cp, new_cp)`** in carry.py: one function, called once per checkpoint of each candidate node, whose result alone decides carry. G1039 replaces its body.
2. **The carry writer**: it builds `new_cp = {commit: M, base: onto, tree: code_tree(M), change: ...}` and lets G1039 write `change` from `old_cp`. If G1038 writes `change: old_cp["change"]` when the predicate holds, which is equivalent under its exact predicate, G1039 needs no edit there.
3. **The checkpoint `scope` key** and an `Identity.change(base, commit, scope/paths)` that G1039 can extend with `unified=` so that delta and change use the same view.
4. **The base output `sync = {from, onto, merge, resolved}`** (undeclared, not fingerprinted). The card reads `merge` and `resolved`. `from` and `onto` cross-check B1 and B2.
5. **`base_commit` stays a declared base output (= onto)**, which review_impl's new input selects. **`carried_by: "base"`** is set on carried records.
6. **G1038's moved-base `previous.interdiff`** (range-diff plus `previous.syncs`), which the card reuses unchanged when the subject's change changed.

**Ordering.** G1039 must merge after G1038. Without G1038, carry still runs on rebase replay maps, and a fallback would mean implementing carry twice. The root should add 1038 to G1039's `depends_on` before G1039's base runs. Undoing this order would cost duplicated carry code, so the order clearly dominates and it is not an owner question.

## 6. Tests
A new file, `.agents/test_engine_clean_sync.py`, plus edits to test_engine_frontier.py (counts), test_engine_card_budget.py (card size) and G1027's capabilities test (pinned list). Fixtures use engine_fixtures and test_engine_lifecycle helpers: a temporary bare remote, a trunk, and one goal on the default graph driven through the CLI with scripted submits.
Commands, run from the worktree root:
- `python3 -m unittest discover -s .agents -p 'test_engine_clean_sync.py'`
- `python3 -m unittest discover -s .agents -p 'test_engine_frontier.py'`
- `python3 -m unittest discover -s .agents -p 'test_engine_card_budget.py'`
- `python3 -m unittest discover -s .agents -p 'test_engine_capabilities.py'`

1. **delta properties** (Identity, scratch repo). Equal -U0 id under: a line shift, a changed `index` line, changed hunk-header function context, a trunk edit 2 lines from a goal hunk, and an adjacent-append conflict resolved as both sides. In the last two cases the -U3 change differs; asserting that proves the widening. A different id when: one goal line changes, or a resolution drops one side. With a scope, a change outside the scope leaves the id equal.
2. **G1027 replay in miniature (acceptance 1).**
   - Setup: the goal removes `"min": "0.0.0"` from templates/default/POLICY.json, edits engine/__init__.py inside a version hunk, and adds a HISTORY row. Trunk then adds .agents/fixtures/graph26/POLICY.json containing `"min": "0.0.0"`, appends an adjacent HISTORY row, and bumps the version line inside the goal's hunk. Base conflicts; the fixture resolves HISTORY as both rows and __init__.py with the new version, then resumes.
   - Expect: test_design carried (`carried_by == "base"`, tests.change identical, commit == M). design, review_design, approve_design and review_tests current. implement stale. After implement resubmits, run_tests is ready. The review_impl card has `sync.touching` with an entry for `.agents/fixtures/graph26/POLICY.json` whose `why` is "trunk adds `\"min\": \"0.0.0\"`, a line the goal removes". It also has `interdiff` and `sync.resolved`.
3. **Clean variant.** Same setup without the version bump. implement is carried too. review_impl `stale_because == ["inputs.base"]`; its card has `sync` with the ask text and no `interdiff`. run_tests is ready; review_tests, filter_impl (until review_impl submits) and approve_merge are current. review_impl then submits a new material finding: every node's correction_runs is unchanged.
4. **Context-only trunk edit** 2 lines from a goal hunk, merged with no conflict: both nodes carried. G1038's exact predicate alone would not carry them; the test asserts the -U3 change differs.
5. **Conflicting sync stales as today (acceptance 2).** A resolution that changes a test line: test_design and review_tests stale, and implement stale through its tests input. A HISTORY resolution that drops trunk's row: the node owning HISTORY stales.
6. **counts() table** (unit tests over records.py/frontier). New material finding -> 1. Only `follows` -> 0. `material: false` -> 0. No findings -> 0. Stale only on `inputs.base` with a finding -> 0. Stale on `inputs.base` and `inputs.code` with a finding -> 1. Definition-only re-run -> 0. Human or op record -> 0.
7. **Per-stage limit.** With delivery used = 9, there is no item. At 10: `next` shows the delivery budget item with the text above. `start` of a delivery agent is refused with `budget_exceeded`, a reclaim too. A discovery agent start, run_tests and human items proceed. Continue sets budget = 20. doc.budget = 4 applies to each stage.
8. **Replays (acceptance, budget).** The G1026 and G1027 round sequences (node, attempt, new material ids, stale keys) are encoded as literal data derived from their goal branches. Expected counts: G1026 discovery 3 / delivery 4; G1027 1 / 4; neither stage reaches 10. An extra check runs only when refs/zzzops/goal/origin/g1026 and g1027 exist (skipUnless): it recomputes the counts from the real records and expects the same numbers.
9. **Real-commit card check** (skipUnless 5288bf7, 3b49062 and 25186a5 exist). The `touching` builder over those commits has 11 shared files and exactly one name/line hit, the graph26 POLICY.json entry.
10. **Workflow and size.** The template's review_impl has a non-context `base` input from base.base_commit; review_tests and filter_impl have none. A review_impl card with `sync`, at real sizes, is at most 4,096 bytes after shrink, and with 40 touching paths `sync.all` is a blob view and only 12 entries are inline (G1018 guarantees G1-G3 still hold).
11. **Capability and docs.** `round_budget` is in CAPABILITIES and in the pinned list. The docs guard passes, and the HISTORY §4 row is present.

## 7. Risks and out of scope
- A kept `change` can stale consumers once on a later identical resubmit.
- -U0 alignment shifts err conservative: they stale the node.
- Name matching is a heuristic that only orders the card.
- Upgrading resets nothing: old correction_runs values may show one budget item per goal.
- One `doc.budget` value applies to both stages. A per-stage override is left for later if ever needed.
- approve_merge stays current after a clean sync, as today. The owner approved the change, and the tree check is run_tests' job.
- Out of scope:
  - merge mechanics, the conflict flow and the integrate squash (G1038);
  - this repository's policy branch (a follow-up with the rollout);
  - any change to the per-finding round and dispute caps.
