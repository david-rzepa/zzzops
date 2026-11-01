# G1022 design: one multi-lens reviewer per subject, plus a separate design Adversary

**Builds on:** G1000 design revision 4 (PR #748, `zzzops/pr/g1000`, 6d4715a) and G1020 design revision 2 (PR #750, `zzzops/pr/g1020`, 5410809), neither merged yet. It also builds on G1017 design revision 3 (blob 42144d6): G1022 is G1017's "case 3 with a pending row", so `depends_on` is `[1000, 1020, 1017]` and this PR edits `docs/design/`. G1022 stacks on G1020 and G1017. It keeps every G1000 mechanism (the filter that promotes but never demotes, `impact`/`material`, `skippable` and the skip refusal, `settings.intent`, `previous.changed`) and G1020's notes-only approval. It changes the shipped graph, adds one node field and one finding key, and gives goal skips a second key form.

**Revision 2** answers `review_design` attempt 1, and the spec edit that came with G1017's plan.
- **F1:** the Missing lens, and code review generally, search the goal's own commit (`code.commit`), not `read_dev` (§5, test 3).
- **F2:** G1017's case 3 is adopted. §12 lists the `docs/design/` edits this PR makes, together with the HISTORY §4 row and deleting the pending row. G1017 enters the delivery order (§8, test 15).
- **F3:** a new paragraph covers rollout to other repositories through G1024 (§8). The engine version becomes "the next minor version at merge".
- **F4:** `review_impl` drops `spec`, so migration is budget-free. The stale keys in §8 and test 11 are corrected, and MIGRATING tells goals moving from the 26-node graph to set a budget first.
- **New:** a section on how the graph interacts with G1025 release branching (§8a). `review_impl` gets back the `security` and `code_quality` instructions (review note). `Graph.lenses` is renamed `Graph.reviewers` (review note).

## 1. Outcome

The shipped default graph goes from 26 nodes to 15. Each subject gets one reviewer that works through several lenses, instead of one agent per lens:

- **Design:** `review_design` applies the seven design lenses (intent, simplicity, truth, adversary, concurrency, rollout, experience). A separate `adversary_design` runs beside it. Both feed `filter_design`.
- **Implementation:** `review_impl` applies five implementation lenses (compliance, correctness, missing, tests, craft) and feeds `filter_impl`. Missing looks outside the diff, for the other places that share a changed rule.
- Every finding of a multi-lens reviewer carries a `lens` tag.
- The lens set is the project's (a `lenses` field on the reviewer node in `workflow.json`). A goal removes optional lenses with skip keys of the form `<node>:<lens>`. Intent and Simplicity (design), and Compliance, Missing and Craft (implementation), cannot be removed. Approval items and the PR body show which lenses ran and which were skipped, with reasons.

**Why** (Appendix A has the numbers). On the implementation experiment, one multi-lens reviewer found 7, 7 and 6 of 7 known defects at 82–87k tokens per run. Five separate lens agents found 6 of 7 for 337k. So the multi-lens reviewer does as well or better at about a quarter of the cost, because separate agents each repeat the same discovery reading. Only the multi-lens reviewer, through its Missing lens, found the real defect that lay outside the diff (2 of 3 runs). On the design replay, a multi-lens reviewer alone was weaker (4 of 12 per run). Adding one separate Adversary brought it to 7 of 12, the same as seven separate lenses, for about 76k instead of about 245k tokens. That is why the design subject keeps a separate Adversary.

## 2. Decisions (for `approve_design`)

| # | Decision | Rejected alternatives |
|---|---|---|
| D1 | **Graph:** `review_design` (seven lenses) and `adversary_design` (G1000's single-lens node, unchanged) feed `filter_design`. `review_impl` (five lenses) feeds `filter_impl`. 15 nodes in all. | Keeping the 26 nodes: about 4× the cost per round for equal or lower recall. A multi-lens design reviewer without the separate Adversary: 4/12 against 7/12. A separate Adversary at the implementation stage as well: the spec does not ask for one, and the multi-lens Correctness lens found the planted security defect (S3) as material in 2 of 3 runs. |
| D2 | **Node ids `review_design` and `review_impl`** for the multi-lens reviewers (the 12-node graph's names). `adversary_design` keeps G1000's id and its definition byte for byte. | New ids such as `lenses_design`. They would orphan the review records of every in-flight goal in this repository, which still runs the 12-node graph. With the old ids, those records carry over (§8). |
| D3 | **The project chooses its lens set** with a new node field, `lenses`: an ordered object `{"<lens>": {"prompt": "<file>", "skippable": <bool>}}` on an agent review node. A lens is a prompt file plus a flag. The engine names no lens. | A lens list in POLICY `settings`: it would sit apart from the node that applies it, and could not say per node which lenses are mandatory. One prompt file per reviewer with every lens inlined: a goal could not then remove a lens. |
| D4 | **A goal removes a lens with the skip mechanism:** `skip["<node>:<lens>"] = "<reason>"`. This reuses what skips already have: a reason is required, human words are needed after `new`, `skippable: false` refusals apply, and approval items and the PR body already list every skip with its reason. The node keeps running, so a lens skip drops no finding. | **A node input** (an input such as `lenses` read from a goal field): it needs a new goal field and selector, and an input change counts against the budget. **A new goal field** (`lenses: {node: [...]}`): it is a second concept beside `skip`, and needs its own reasons, validation and display. Adding a key to `GOAL_KEYS` would also make every 1.1 engine refuse every goal document. **Node skips of one-lens nodes** (today's G1000 mechanism): that is the cost this goal removes. |
| D5 | **Mandatory lenses are declared, not built into the engine.** `skippable: false` on a lens refuses a goal skip of it. Validation also requires a node that holds a non-skippable lens to be `skippable: false` itself, so the lens cannot be removed by skipping the whole node. The template marks intent and simplicity (design), and compliance, missing and craft (implementation). A project may still change its own `workflow.json`: that is a reviewed policy change, and the engine names no lens. | Hard-coding lens names in the engine. That breaks the names test and the principle that the graph belongs to the project. |
| D6 | **Compliance is the implementation stage's Intent lens.** It is not skippable. It judges the code against the approved design, which was itself approved against the spec. `review_impl` has no `spec` input, as the 12-node `review_impl` had none. It does not declare `policy: ["intent"]`: project intent is judged once, at the design stage, by `review_design`'s Intent lens. | Folding project intent into Compliance. That would make every intent change re-run the whole five-lens implementation review on every open goal (about 85k tokens each, where G1000 re-runs one 42k lens). The measured Compliance prompt did not include project intent, and the approved design already carries it. |
| D7 | **Freshness:** a multi-lens reviewer's fingerprint gains a `lenses` part, the list of lenses it applies. So un-skipping a lens re-runs the reviewer. Like `def`, `policy.*` and `candidates`, a stale caused only by `lenses` does not count against the budget. `node_def_fp` covers the `lenses` field (names and flags) only on nodes that have it, so no other node's fingerprint changes. | Freshness by "the record applied a superset of the current lenses": a non-equality rule found nowhere else in the engine. Equality costs one extra run when a lens is removed after the review has run. That case is rare, because add-goal agrees skips at `new`. |
| D8 | **No skip refusal for lens skips.** G1000's refusal guards against "skip the objecting lens and its findings die". A lens skip does not skip the node: its record and every open finding stay. They keep their filter judgment and must still be given a status on re-review. A new finding tagged with a skipped lens is accepted. G1000's refusal still applies to node skips (`adversary_design`). | Extending the open-finding refusal to lens keys: it guards against a loss that cannot happen here, and it would block lens skips on migrated goals whose old findings carry no tag. |
| D9 | **Rollout:** G1000's `zzzops/policy/lenses` branch (step 3) has not landed. At a05fb97, this repository's `.zzzops/workflow.json` is the 12-node graph and `engine.min` is `0.0.0`. So that branch adopts this 15-node graph instead of the 26-node one. The engine floor branch raises `engine.min` straight to G1022's engine version. G1003 waits for G1022. Other repositories hear about the new graph through G1024's `policy_update` item, and the release that ships the 15-node template should also ship G1024 (§8). | Landing the 26-node graph first and migrating afterwards: two graph changes, and two rounds of in-flight churn. |

## 3. The shipped graph (15 nodes)

```
design ─┬→ review_design ───┐
        └→ adversary_design ┴→ filter_design → approve_design → base → test_design → review_tests → implement → run_tests ─┐
  ┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
  └→ review_impl → filter_impl ─┬→ integrate ─────┬→ merge
                                └→ approve_merge ─┘
```

| Node | Definition (changes from G1000 only) |
|---|---|
| `design` | unchanged (`dep_reviews` already reads `deps.filter_design.summary`) |
| `review_design` | agent, `capability: reasoning`, `stage: discovery`, `skippable: false`, `review: {"subject": "design", "filter": "filter_design"}`, inputs `spec` and `doc`, `policy: ["intent"]`, prompt `review.md`, instructions `review` and `communication`, and `lenses` as below |
| `adversary_design` | unchanged from G1000 (prompt `lens_adversary.md`, skippable) |
| `filter_design` | inputs `spec`, `doc`, `review` (`review_design.summary`, required), `adversary` (`adversary_design.summary`, optional). G1000's wiring rule holds: optional exactly for the skippable reviewer |
| `approve_design` | `filter` (`filter_design.summary`); context `review` and `adversary` (optional) |
| `base`, `test_design`, `review_tests`, `implement`, `run_tests` | unchanged |
| `review_impl` | agent, `capability: reasoning`, `stage: delivery`, `skippable: false`, `review: {"subject": "implement", "filter": "filter_impl"}`, inputs `doc`, `tests` (`test_design.tests.change`), `code` (`implement.code.change`) and context `checks`. These are the 12-node `review_impl`'s inputs, with no `spec` (D6). Prompt `review.md`. Instructions `review`, `communication`, `security` and `code_quality`: the last two return from the 12-node node, so a project that tightens them still reaches its implementation reviewer. And `lenses` as below |
| `filter_impl` | inputs `doc`, `code`, `review` (`review_impl.summary`, required). It no longer joins several reviewers, but it is still the independent nitpick filter |
| `integrate`, `approve_merge` | context `filter` (`filter_impl.summary`) and `review` (`review_impl.summary`), replacing the seven lens summaries |
| `merge` | unchanged |

```json
"lenses": {
  "intent":      {"prompt": "lens_intent.md", "skippable": false},
  "simplicity":  {"prompt": "lens_simplicity.md", "skippable": false},
  "truth":       {"prompt": "lens_truth.md"},
  "adversary":   {"prompt": "lens_adversary.md"},
  "concurrency": {"prompt": "lens_concurrency.md"},
  "rollout":     {"prompt": "lens_rollout.md"},
  "experience":  {"prompt": "lens_experience.md"}
}
```
`review_impl`: `compliance`, `missing` and `craft` are `skippable: false`; `correctness` and `tests` are skippable. Their prompts are `lens_compliance.md`, `lens_correctness.md`, `lens_missing.md`, `lens_tests.md` and `lens_craft.md`.

Removed: the 14 `<lens>_design`/`<lens>_impl` nodes other than `adversary_design`. Agent nodes go from 20 to 9, so the default budget (3 × agent nodes) goes from 60 to 27. One full design round now costs 4 counted runs (design, reviewer, Adversary, filter); G1000 needed 9. So 27 allows about 6–7 rounds per subject, as G1000's 60 did.

## 4. Lens configuration: interfaces and data

**`workflow.json`:**
- New node field `lenses`, allowed on agent nodes that have `review`. The value is a non-empty object. Each key is a lens name (`^[a-z][a-z0-9_]*$`). Each value is `{"prompt": <file>, "skippable"?: <bool, default true>}`, and no other keys are allowed. Each prompt must exist, like a node's `prompt`. Key order is the order the reviewer applies the lenses in.
- If any lens is `skippable: false`, the node must also be `skippable: false`.
- A node without `lenses` behaves exactly as in G1000. A 26-node graph, the graph12 fixture and every other project graph still validate unchanged.

**Goal `skip`:**
- A key is a node id, or `<node>:<lens>`. Validation splits the key at the first `:`:
  - The node must have `lenses` with that key. Otherwise the existing "skip of removed node" warning applies, worded for a lens. An unknown lens is ignored, which fails safe: the lens still runs.
  - On a write, a new key naming a `skippable: false` lens is refused: "`review_design:intent` is not skippable (lenses.intent.skippable: false in workflow.json)". This is the same rule as G1000's node refusal, and on reading it only warns.
  - The reason rules are unchanged.
- Every existing consumer compares skip keys with node ids (frontier, `card.candidates`, `process_findings`, `skip_refusal`). A key containing `:` never matches a node id, so these consumers need no change.
- `edit` paths: `PATH_SEG` accepts `:` in a segment, so `--set 'skip.review_impl:tests="docs only"'` works, and `=null` removes the key through the existing rule.

**Findings:**
- New finding key `lens` (a string).
- On a node with `lenses`, every new finding must give `lens`, and it must be one of the node's declared lenses. A lens that is currently skipped is accepted (D8): a finding is never refused because of the lens it came from.
- `process_findings` records `lens` beside `impact` and `material`. Prior findings keep whatever they had; an untagged one is shown under the node id.
- A display label is `<node>:<lens>` for a tagged finding and `<node>` otherwise. One helper, `lens_label(node, finding)`, produces it for `candidates`, `notes`, approval items and the PR body.

**Fingerprint (D7):**
- `node_def_fp` adds `"lenses": {name: skippable}` only when the field is present.
- `fp_parts` gains `skip` (the goal's skip map; three call sites in `frontier.py`). For a node with `lenses` it adds the part `lenses` = the applied lens names, in order.
- `stale_keys` reports `lenses`. `frontier.counts` exempts it with `def`, `candidates` and `policy.*`.

**Card (reviewer):**
```json
"lenses": {"apply": ["compliance", "correctness", "missing", "craft"],
           "skipped": {"tests": "docs-only goal (owner, 2026-11-01)"},
           "text": "# Compliance lens\n…\n\n# Correctness lens\n…"}
```
- `text` concatenates the applied lenses' prompt files in order. `shrink` gains one step that turns `lenses.text` into a blob view, after the prompt and instructions steps. `apply` and `skipped` always stay inline: they are the checklist.
- `output_schema.findings` for a node with `lenses` reads: `… {"target"?: <node>, "lens": "compliance" | "correctness" | "missing" | "craft" | "tests", "text": …} for new ones`. It lists every declared lens, because a skipped one is accepted too.

**Approval items and PR body:**
- `render`'s human item gains `lenses: {"<node>": {"apply": [...], "skipped": {lens: reason}}}`, for each reviewer with `lenses` among the item's inputs or context producers.
- Notes are grouped by `lens_label`.
- `integrate.reviews_section` writes a multi-lens reviewer's line as `- **review_impl** (compliance, correctness, missing, craft): <summary>`. The skip lines already list `review_impl:tests: skipped: <reason>`.
- Neither reads a node or lens name: both come from the graph.

**Engine size:** about 120 lines in `schemas.py`, `records.py`, `fingerprint.py`, `frontier.py`, `card.py`, `render.py`, `verbs.py` (`PATH_SEG` only), `ops/integrate.py` and `__init__.py` (`ENGINE_VERSION`: the next minor version at merge, 1.2.0 if no other goal has taken it; see §8). There is no new verb, no new record shape beyond the `lens` key, and no change to the filter, liveness or the skip refusal.

## 5. Prompts

- **`review.md`** (new; shared by `review_design` and `review_impl`). Adapted from the measured `multi.md`:
  > You are this subject's reviewer. `lenses.apply` on your card lists your lenses, in order, and `lenses.text` gives each lens's questions. Work through them one at a time, deliberately: give each lens its own pass over the subject (for Missing, also the code outside the diff), and do not stop at the first problems you find. Tag every new finding with the lens that produced it (`lens`). A lens under `lenses.skipped` was removed for this goal: do not work through it, but report a serious problem you meet anyway under the closest lens.
- **Instruction `review`** (POLICY): the opening "You are one of several independent reviewers, each with one lens; judge only what yours asks, and do not read…" becomes "You are an independent reviewer: do not read…". "Check claims against the integration tip (`read_dev`)" becomes "Check claims against the integration tip (`read_dev`); on code, against the subject's own commit (`code.commit`)". The rest is unchanged, including G1020's `test_design` sentence. The instruction serves both multi-lens reviewers and `adversary_design`.
- **Design lens prompts** (the seven `lens_*.md`): delete each "On code: …" line and Intent's "and, for code, to the approved design", because these lenses now run only on designs. `lens_adversary.md` keeps serving both `adversary_design` and the Adversary lens of `review_design`.
- **Implementation lens prompts** (new): `lens_compliance.md`, `lens_correctness.md`, `lens_missing.md`, `lens_tests.md` and `lens_craft.md`, using the measured text of `multi.md`'s five items (Appendix A.4). There are two edits. Tests drops "Test findings target `test_design`." because the instruction says it. Missing adds the grep hint from `new_missing.md`, aimed at the right tree (F1). The added sentence: "Search the subject's own tree, not `read_dev`: `git grep <pattern> <code.commit>` and `git show <code.commit>:<path>`, with `commit` from your card's `code` view. Grep the identifiers, the condition and the strings." The integration tip lacks a stacked goal's dependencies and can move after `base`. The experiment's reviewers searched a worktree at the submission, and `code.commit` is that same tree as git objects.
- **`approve_design.md` / `approve_merge.md`**: "each lens verdict" becomes "each reviewer's verdict and the lenses it applied (`lenses`)".
- **`design.md` / `implement.md`**: "`unskip <node ids>`" becomes "`unskip <skip keys>` (a node id, or `<node>:<lens>`)".
- `filter.md` is unchanged: candidates already carry a `lens`, now the label.

## 6. Skills and docs

- **add-goal, step 2:** propose lens skips as `skip["review_design:concurrency"]` and similar, for example `review_design:concurrency`/`rollout` for a docs-only goal, `review_design:experience` for an internal change, and `review_impl:tests` for a docs-only goal. `adversary_design` is skipped as a node. The non-removable lenses and nodes are listed. A skip added after `new` still needs the human's words.
- **execute, "Lenses." paragraph:** each subject has one multi-lens reviewer, plus a separate Adversary at design, and a filter. Dispatch each to a different worker, never the subject's holder. Answer an `unskip` choice by setting those skip keys to `null`.
- **MIGRATING.md:**
  - Adopting the consolidated graph, from 12 nodes and from 26 nodes (§8).
  - Rollback.
  - "Editing the lens set" shrinks to: add or remove an entry in the reviewer's `lenses` and its prompt file, then run `validate --policy --dir`.
- **`docs/EXECUTION.md`:** the diagram and the review paragraph.
- **`package.py`:** the prompt list.
- **CLI_USAGE:** the skip key form, wherever skip keys are described.

## 7. Engine changes, and the requirement each serves

| Change | Files | Serves |
|---|---|---|
| `lenses` node field and its validation; non-skippable lens ⇒ non-skippable node | `schemas.py` | spec 4 (configurable), acceptance (template validates) |
| `<node>:<lens>` skip keys: validation, refusal, warning; `PATH_SEG` | `schemas.py`, `verbs.py` | spec 4, acceptance (remove optional / refuse mandatory) |
| `lens` finding key: required, recorded, labelled | `schemas.py`, `records.py`, `card.py`, `render.py` | spec 2 (lens tag), acceptance (output_schema) |
| `lenses` fingerprint part, budget exemption, def allowlist | `fingerprint.py`, `frontier.py` | un-skipping a lens re-runs the reviewer |
| Card `lenses` section, shrink step, output_schema hint | `card.py` | acceptance (lens checklist on both cards) |
| Approval item `lenses`, PR body lens list | `render.py`, `ops/integrate.py` | spec 4 (shown on approvals and PR) |
| `ENGINE_VERSION`: next minor at merge | `__init__.py` | rollout (new key and field) |
| `Graph.lenses(f)` renamed `Graph.reviewers(f)` (the reviewer nodes of a filter), so `lenses` means only lens names | `schemas.py` and its callers | Craft/naming (review note) |
| `docs/design/SPEC.md`, `DESIGN.md`, `HISTORY.md` §4 row, README pending row deleted | `docs/design/` | spec acceptance (G1017's rule) |

## 8. Rollout and migration

**Order of delivery.**
1. G1000 (#748), G1020 (#750), G1017 and G1022 merge into `dev`, in that order; G1022's `depends_on` forces the order. Do not cut a release from `dev` between #748 and G1022's merge. Otherwise the 26-node template ships, and adopters migrate twice. If one is cut anyway, MIGRATING's "from 26 nodes" path applies. Once G1025 lands, its release cut waits for every Release 1 goal, G1022 included (§8a). Until then this is a note for the root.
2. **The engine floor branch** (G1000 step 2, owner-gated, the same question to the owner) raises `engine.min` to G1022's `ENGINE_VERSION` instead of `1.1.0`. G1022 takes the next minor version at merge, 1.2.0 unless another goal (G1024, for example) has already taken it; whichever of the two merges second takes the next number. A 1.1 engine reads a `lenses` field as an unknown node field and a `lens` key as an unknown finding key. Both make the policy or the goal invalid, so the floor must be raised before any multi-lens record is written. With the floor in place, the failure is a clear `engine_too_old`.
3. **`zzzops/policy/lenses`** (G1000 step 3) carries this graph: the 15-node `workflow.json`, `review.md`, the 12 lens prompts, `filter.md`, the instruction `review`, and the Appendix B intent strawman of G1000 for the owner to rewrite. Before pushing, the root previews it with `validate --policy-ref` and `next --policy-ref`.
4. **G1003.** It stays held. The root adds `1022` to its `depends_on` and a spec item ("re-score the consolidated reviewer set on real goals: recall against later-found defects, nit rate, tokens per round"). It is unheld after step 3 lands.

**In-flight goals, from the 12-node graph (this repository):**
- `review_design`/`review_impl` records stay, and their re-runs are not counted against the budget.
  - `review_design` goes stale with `stale_keys == ["def", "lenses", "policy.intent"]`.
  - `review_impl` goes stale with `["def", "lenses"]`; its inputs are unchanged (D6).
  - All of these keys are exempt in `frontier.counts`. With `spec` on `review_impl`, `inputs.spec` would have charged every in-flight goal one counted run; dropping it avoids that (F4).
- The re-run sees the old findings as prior findings, untagged. They count as material (G1020's `is_material`), and the reviewer gives each one a status.
- `adversary_design`, `filter_design` and `filter_impl` are `ready (new)`. `base` and everything downstream wait behind `filter_design`, as in G1000.
- Recommended: land step 3 when no goal is past `approve_design`. The preview lists any that are.

**From the 26-node graph** (a project that adopted G1000's graph, or this repository if step 3 lands as 26 nodes before G1022):
- A policy branch with this graph. The other 13 lens node records become orphans (a warning), never deleted.
- `adversary_design`'s definition is unchanged, so its record stays current.
- `review_design` and `review_impl` are `ready (new)`. `filter_design` goes stale (an input changed) and waits for them; `filter_impl` likewise. A kept finding reopens the subject as usual.
- Open findings on orphaned lens records stop counting. MIGRATING says so: land when no orphaned lens has an open material finding, or waive those visibly first. The preview shows them.
- **Budget:** the default limit falls from 60 to 27. A migrated goal that has already used more than 27 runs is over budget at once. MIGRATING says to set an explicit `budget` (for example, its current limit) on such goals before landing the branch. The preview's budget column shows which goals need it.

**Rollout to other repositories (G1024).** A bootstrapped repository is never told that the default graph changed; G1024 adds the notice. G1022 relies on it and does not duplicate it:
- G1024's `policy_update` item is the notice. MIGRATING's "Adopting the consolidated graph" section is the procedure the item links to when `workflow.json` changed upstream. A three-way text merge of `workflow.json` is not a safe way to adopt a restructured graph.
- Changed file shapes that G1024 must handle:
  - From a 12-node bootstrap, G1022 adds `review.md`, the five implementation lens prompts and the seven design lens prompts, and removes `review_design.md` and `review_impl.md`.
  - From a 26-node one, it adds `review.md` and the five implementation lens prompts, and changes the seven design lens prompts.
  - So the item must list added and removed files, not only changed ones.
- Engine version: whichever of G1022 and G1024 merges second takes the next minor version (item 2 above).
- This repository's record: if G1024 lands before `zzzops/policy/lenses`, that branch also refreshes the record (G1024's "created through its next policy branch"), so the record is stamped with the 15-node template, not the earlier one.
- Releases: the release that ships the 15-node template should include G1024, so adopters are told. This is a release-gating note on the root follow-ups (§13), not a `depends_on` edge. G1022 works without G1024, and G1024 works without G1022.

**Rollback:** a policy branch restoring the previous files, keeping `engine.min`. Multi-lens records stay readable by 1.2. If the restored graph has no `lenses`, the `lens` keys on old findings are inert. Lens skip keys become orphan warnings. Engine 1.2 to 1.1 is forward-only for goals with tagged findings: use REPAIR's bulk revert recipe.

## 8a. Interaction with G1025 (git-flow release branching)

G1025 changes where goals base, integrate and merge (a release branch or the integration branch), and adds scheduled downstream merges in place of rebasing. The review nodes do not touch branches, so the two are mostly independent. Where they meet:
- **Same file:** G1025 may add a downstream-merge node to the shipped `workflow.json`. G1025 depends on G1017, not on G1022, so its design should be written against the 15-node graph. The root passes this note to G1025's design (§13). The review nodes and `filter_*` need no change for it.
- **What the reviewer searches:** `review_impl`'s Missing lens searches `code.commit`, the goal's own tree, whatever branch it was based on. That stays right when the base is a release branch, which is one more reason F1 moved the search off `read_dev`. `read_dev` should name the goal's target tip once G1025 lands; that is G1025's card change.
- **Re-review after a downstream merge:** a merge commit changes `implement`'s checkpoint `change`, so `review_impl` re-reviews through `previous.interdiff`. This holds only if G1025 keeps `change` meaningful on merge commits, which is the question its spec already asks it to decide. No G1022 mechanism depends on a linear history.
- **Release cut:** G1025's cut waits until every goal of the release is complete, so the 15-node template and the G1003 re-score ship together in Release 1.

## 9. Tests

**Fixture freeze.** Copy G1020's shipped template (the 26-node `workflow.json`, `POLICY.json` and `prompts/`) to `.agents/fixtures/graph26/`, and point `test_engine_lenses.py` and `test_engine_lens_polish.py` there. Those tests still cover the multi-node filter join, per-lens independence, intent staleness at both stages and the notes-only approval. They pass unchanged, except for assertions about the shipped template itself, which move to the new file. One example is lens_truth's "On code:" count; the shipped file now has none, and the fixture keeps the check.

**New: `.agents/test_engine_review_lenses.py` (shipped graph).**
1. **Template:** `validate --policy --dir` passes with exactly one `intent_placeholder` warning. The node list is exactly the 15 of §3. `graph.lenses("filter_design") == ["review_design", "adversary_design"]` and `graph.lenses("filter_impl") == ["review_impl"]` (review fan-in). The lens names and order on both reviewers match §3, and so do the non-skippable sets. The default budget is 27. Every node and lens prompt exists.
2. **Validation:**
   - `lenses` on a non-review node is refused, and so is a lens prompt that does not exist.
   - A non-skippable lens on a skippable node is refused.
   - A graph with no `lenses` validates as before (graph12 and graph26).
3. **Card snapshots:**
   - `review_design` and `review_impl` cards carry `lenses.apply` equal to the declared order, and `lenses.text` (inline or blob) contains each applied lens's heading.
   - `output_schema.findings` names `lens` and every declared lens.
   - The `adversary_design` card has no `lenses` section.
   - Each reviewer card is within `CARD_LIMIT` after `shrink`.
   - **Search target (F1):** `review_impl`'s `lenses.text` (or its blob) contains "`git grep <pattern> <code.commit>`", and its `code` input view has `commit`. The instruction `review` on the card contains "`code.commit`". `review_impl`'s card has the `security` and `code_quality` instructions.
4. **Lens tag:**
   - A `review_impl` submit with a new finding lacking `lens` is refused, and so is one with an undeclared lens.
   - A tagged finding is recorded with `lens`, and appears on `filter_impl`'s `candidates` as `review_impl:missing`. As a note, it appears on `implement`'s next card under that label.
5. **Removing an optional lens:**
   - `new` with `skip: {"review_impl:tests": "docs only, owner agreed"}` is accepted. The `review_impl` card has `apply` without `tests` and `skipped.tests` with the reason.
   - `approve_merge`'s item shows `lenses.review_impl` with the skip.
   - The PR body has `- **review_impl** (compliance, correctness, missing, craft): …` and the skip line.
   - The same skip with `edit --set 'skip.review_impl:tests="…"'` works, and `=null` removes it.
6. **Refusing a mandatory one:**
   - `new` with `skip.review_design:intent` is refused with the not-skippable message.
   - `edit` adding `review_impl:missing` is refused.
   - A node skip of `review_design` is refused.
   - On reading, a goal that already holds such a key (a policy made it mandatory later) warns, and is not invalid.
7. **Freshness:**
   - With `review_impl` current, removing the `review_impl:tests` skip makes it `ready (stale)` with `stale_keys == ["lenses"]`, and the re-run does not count against the budget.
   - Adding a lens skip behaves the same.
   - A lens prompt text change does not stale the reviewer (prompts are not fingerprinted; `rev` is the bump).
8. **No finding lost (D8):** `review_design` raises a material finding tagged `concurrency`. `edit` adds `review_design:concurrency`, and the edit is accepted. The finding stays open, live once the filter is fresh, and reopens the design. The reviewer's next card lists it as a prior finding.
9. **Fingerprint stability:** `node_def_fp` of every graph12 and graph26 node equals its 1.1 value (golden hashes computed from the frozen fixtures before the change). Only nodes with `lenses` gain the part.
10. **Journey:**
    - After `design`, `review_design` and `adversary_design` are ready in parallel with distinct holders. `filter_design` waits for both, and the subject reopens once per round.
    - `skip.adversary_design` lets the filter run on `review_design` alone, and G1000's open-finding refusal still applies to that node skip.
    - `review_impl` gets `previous.changed`/`interdiff` on a re-review.
11. **Migration (F4):**
    - A goal built on graph12 with done `review_design` and `review_impl` records, opened under the shipped graph, shows:
      - `review_design` `ready (stale)` with `stale_keys == ["def", "lenses", "policy.intent"]`;
      - `review_impl` with `["def", "lenses"]`;
      - both re-runs leaving `budget.used` unchanged;
      - `adversary_design` and `filter_design` `ready (new)`.
    - Its prior untagged finding is labelled `review_design` and counted as material.
    - From graph26: `adversary_design` stays current, the other lens records are orphan warnings, and `review_design` is `ready (new)`.
    - A graph26 goal with `budget.used` above 27 shows over budget with the default limit, and does not once an explicit `budget` is set.
12. **Names:** no default node id and no lens name appears in engine source (extend the existing names test with the lens names).
13. **Renamed graph:** the review-lens journey runs on a renamed copy of the shipped graph, with lens names renamed too.
14. **Prompt budgets:** `prompt_stats.py --check` passes. Today capture is 2,265 of 3,700 tokens and execution 3,030 of 8,800 (G1020 tree), so there is room for the skill edits.
15. **docs/design (G1017's rule):** `.agents/test_design_docs.py` passes on this PR's tree. That means `test_no_landed_goal_is_pending` passes with the G1022 row deleted: its marker (`workflow.json lacks "\"truth_design\""`) matches on this tree, so the row must go. Amendment ids resolve, and the HISTORY §4 row names this PR. A reviewer diffs §12's list against the SPEC/DESIGN diff.

## 10. Risks

- **Correlated blind spots.** One reviewer applies every lens, so what it misses, it misses across all of them.
  - On the design replay, a multi-lens run alone found 4 of 12; the separate Adversary (D1) restores 7 of 12.
  - At the implementation stage there is no second reviewer. That rests on 3 runs on one goal (7, 7 and 6 of 7), and G1003 re-scores it on real goals.
  - If the re-score shows a gap, adding a separate node is a policy change, not an engine change: a G1000-style single-lens node naming the filter.
- **Lens dilution.** A long checklist could get shallow passes.
  - The prompt asks for one pass per lens, and not stopping at the first problems.
  - In all three implementation runs, every one of the five lenses produced findings (Appendix A.1).
  - Run-to-run variance is real: the Missing defect was found as material in 1 run, as a note in 1, and missed in 1.
- **Independence is weaker.** A lazy or hostile reviewer now controls all lenses of a subject. The filter is still independent and still cannot demote. At design, the Adversary is a second agent. At implementation, `review_tests`, `run_tests` and the human `approve_merge` remain.
- **Card size.** The seven design lens texts are about 3 KB. `shrink` moves them to a blob, which the reviewer reads with one `read`. The checklist stays inline.
- **A lens skip mid-run** stales the running reviewer's lease fingerprint, so its submit is recorded stale and it re-runs once, with no budget charge. Nothing is lost: findings of a skipped lens are accepted (D8).
- **Unknown lens keys only warn,** so a mistyped lens skip leaves the lens running. That fails safe. `edit` prints the warning.
- **Older engines** refuse the new policy and goal shapes. They are kept away by the floor (§8 step 2), as in G1000.

## 11. Out of scope

- A Missing lens at the design stage: the spec's design set has none. G1003's re-score can propose one.
- A separate implementation-stage Adversary.
- Changing the filter, its verdict rules, liveness or the budget formula.
- Ending a running lease when a node is skipped (G1000 review note).
- `edit` setting `status="resolved"` in place of `waived` (an existing gap, G1000 review note).
- G1024's notice mechanism and G1025's branching. §8 and §8a give the coordination points.
- Running the policy branches, which are root follow-ups (§8).

## 12. Contract edits in this PR (`docs/design/`, G1017's rule)

G1022 is G1017's case 3, so its base contains `docs/design/`, with G1000's and G1020's amendments already applied by G1017. This PR makes the edits below to `docs/design/SPEC.md` and `DESIGN.md`. It adds a HISTORY §4 row (G1022, this PR, the sections changed) and deletes the G1022 row from the README's pending table. The edits replace G1000's text where they conflict: the §7 default graph, and §8.2/§8.3's lens prompts.

G1017's pending row lists only SPEC §3.1, §7, §8.2 and DESIGN §3.8, §4.1, §10. This PR changes the full set below. If G1017 has not yet written its row when this design is approved, the root sends it this list (§13). Otherwise this PR's edits follow the list here, and the row is deleted regardless.

- **SPEC**
  - §3.1: node field `lenses` (`{name: {prompt, skippable?}}`, review agent nodes only); a non-skippable lens requires a non-skippable node.
  - §3.3: skip keys may be `<node>:<lens>`. A new key naming a non-skippable lens is refused; an unknown lens warns.
  - §3.6: finding key `lens`, required on new findings of a node with `lenses`, and one of its declared lenses.
  - §4.8: the `lenses` fingerprint part (applied lens names); `node_def_fp` covers `lenses` when present.
  - §4.10: a `lenses`-only stale does not count against the budget.
  - §4.18: lens skips are not subject to the open-finding refusal, because they drop nothing.
  - §4.20: card section `lenses` (`apply`, `skipped`, `text`), the shrink step, and the output_schema `lens` hint.
  - §5.4: the PR body's lens list per reviewer.
  - §7: the 15-node default graph and its JSON.
  - §8.2/§8.3: `review.md`, the 12 lens prompts, and the instruction `review` text (including the `code.commit` search sentence).
- **DESIGN**
  - §3.8: why one reviewer works through several lenses, why the design subject keeps a separate Adversary, and why lens selection reuses skips (Appendix A data).
  - §4.1: the graph and table.
  - §10: the rollout order of §8, with the floor at G1022's engine version.

**Fallback:** if G1017's approved design drops case 3 before this goal reaches `implement`, this section reverts to a list that G1017 applies or keeps pending, and the `docs/design/` edits leave this PR's scope.

## 13. Root follow-ups (after `approve_merge`; recorded on that item)

1. Floor branch at G1022's engine version (owner-gated), then `zzzops/policy/lenses` with this graph (§8). That branch also refreshes G1024's provenance record if G1024 has landed.
2. `zzzops edit 1003`: add `1022` to `depends_on` and the re-score item to its spec; keep it held until step 3 lands.
3. If G1017's README row for G1022 is not yet written, send G1017 the full section list from §12.
4. Hand G1024's design the file-shape points of §8 (added and removed files, the `workflow.json` link to MIGRATING, the version rule), and G1025's design the §8a notes.
5. Release gating: the release that ships the 15-node template includes G1024.

## Appendix A: experiment data

All runs were Opus subagents on 2026-11-01. The source files are in the session scratchpad, not in the repository, so the numbers are restated here.

### A.1 Implementation: G1016 attempt 1 with planted defects

**Subject.** G1016 attempt 1's implementation, with 6 planted defects plus 1 real one:
- **GT1** (real, the actual `review_impl` F1): `render.capability` (`render.py:82-88`, used by `next`) still returned `routine` for `stale_because == ["inputs.base"]`. Design §2 changed that rule elsewhere. This code is outside the diff.
- **S1** (compliance): the card prints the internal `record_stale`.
- **S2** (correctness): the full view is built from clipped text.
- **S3** (security): a blob sha is not validated before going into a printed `git diff`.
- **S4** (tests): a no-fetch assertion was removed.
- **S5** (craft): an inline SHA regex duplicates one, and there is dead code and an unused import.
- **S6** (compatibility): the `abandon` output key `expired` was renamed to `lease`, which is not in the design's interface table.

All 309 engine tests pass on the subject.

Detection (M = found as material, n = found as a note, – = missed):

| Defect | generic | compliance | correctness | tests | craft | compat | intent | simpl | truth | advers | conc | rollout | exper |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GT1 capability rule (outside diff) | – | – | – | – | – | – | – | – | – | – | – | – | – |
| S1 `record_stale` printed | n | M | n | n | n | n | n | M | M | n | n | n | n |
| S2 full view of clipped text | M | M | M | M | M | – | M | – | M | M | n | – | M |
| S3 blob sha unvalidated | M | n | M | – | – | – | – | – | – | M | – | – | – |
| S4 no-fetch assertion removed | – | – | – | M | – | – | – | – | n | – | – | – | – |
| S5 duplicate SHA / dead code | n | n | – | – | n | – | n | n | n | n | – | n | n |
| S6 `expired`→`lease` rename | n | M | n | – | n | M | n | n | n | n | – | M | n |

| Set | Found (of 7) | Tokens |
|---|---|---|
| Old single reviewer (`generic`, the 12-node `review_impl.md`) | 5 | 86k |
| Five separate implementation lenses (compliance, correctness, tests, craft, compatibility) | 6 | 337k |
| Seven design lenses copied to code (G1000's `*_impl`) | 6 | 436k |
| **Multi-lens run 1** (compliance, correctness, missing, tests, craft) | **7** (GT1 n, S1 n, S2 M, S3 M, S4 n, S5 n, S6 n) | 82k |
| **Multi-lens run 2** | **7** (GT1 M, S1 M, S2 M, S3 M, S4 M, S5 n, S6 n) | 86k |
| **Multi-lens run 3** | **6** (GT1 –, S1 n, S2 M, S3 n, S4 n, S5 n, S6 n) | 87k |
| Missing lens alone | GT1 M, S1 n, S6 n | 68k |

- No separate lens found GT1. The multi-lens reviewer found it in 2 of 3 runs (once as material), and the Missing lens alone found it as material. Missing alone also found two leftovers the planted set did not include: a `records.py:244` hint and `MIGRATING.md:23` still using the old sha wording.
- **Other real issues** (not planted) found by some reviewer:
  - The CLI_USAGE `abandon` row wording (compliance, intent, truth and experience M; craft n).
  - A clip test that checks presence only (tests M; generic, compliance, experience and truth n).
  - `^{object}` accepting trees (correctness n).
  - `.zzzops/prompts` not updated (rollout n).
- **Findings per multi-lens run, by lens tag:**

| Run | Findings | Material | compliance | correctness | missing | tests | craft |
|---|---|---|---|---|---|---|---|
| 1 | 10 | 3 | 3 | 1 | 3 | 2 | 1 |
| 2 | 12 | 7 | 3 | 2 | 2 | 3 | 2 |
| 3 | 11 | 2 | 3 | 1 | 2 | 2 | 3 |

The old single reviewer raised 8 findings (2 material), untagged.

### A.2 Design: revision 6 stacked-delivery replay (12 known defects)

The subject and ground truth (GT1–GT12) are G1000's replay (G1000 design §11 and Appendix C.2). The reviewer read only the decision record, with no tools.

| Set | Known defects found (of 12) | Tokens |
|---|---|---|
| Seven separate lenses (G1000's set) | 7 (GT1, 2, 3, 7, 8, 11, 12) | ~245k |
| All sixteen candidate lenses | 8 | not measured as a set (16 runs of ~35k) |
| Multi-lens run 1 (the seven lenses, one reviewer) | 4 (GT1, 7, 8, 11; GT5 partial); 19 findings, 11 material | 41k |
| Multi-lens run 2 | 4 (GT1, 3, 6, 7; GT5 partial); 17 findings, 7 material | 41k |
| Union of the two multi-lens runs | 6 (GT1, 3, 6, 7, 8, 11) | 83k |
| **Multi-lens run 1 + separate Adversary** | **7** (Adversary alone: GT1, 2, 3, 7, 12) | **~76k** |

Run 2 missed GT2, 4, 8, 9, 10, 11 and 12. G1000's Adversary was the best single lens (5 of 12, with unique GT3 and GT12), which is why it stays separate (D1).

### A.3 Cost per review round, estimated from these runs

| Subject | G1000 (26 nodes) | G1022 (15 nodes) |
|---|---|---|
| Design | 7 lenses × ~35–42k + filter ~40k ≈ 285–335k | reviewer ~41k + Adversary ~35k + filter ~40k ≈ 116k |
| Implementation | 7 lenses (436k measured) + filter ≈ 476k | reviewer ~85k + filter ~40k ≈ 125k |

The implementation runs read the codebase with tools; the design runs read one document without tools. Filter cost is from G1000 §11.

### A.4 The measured multi-lens prompt (implementation)

> You are the only reviewer. Work through each lens below in turn, deliberately, and do not stop at the first problems you find. Give each lens its own pass over the diff (and, for Missing, the code outside it). Tag every finding with the lens that produced it.
> 1. **Compliance.** Does the code do what the approved design says, no more and no less? Walk the design's decisions, interface table and test list one by one and find each in the diff. Look for requirements dropped or weakened, behaviour the design did not ask for (new outputs, renamed fields, extra flags), and changed interfaces the design does not list.
> 2. **Correctness.** Is the code actually right? Trace each changed path with concrete inputs: edge cases, empty and missing values, error paths, partial failure and retries, ordering and races, values passed to the wrong place. Untrusted or malformed input, shell and git command construction, and paths are part of correctness.
> 3. **Missing.** What should have changed but did not? For each rule, output, name or behaviour the diff changes, search the codebase for every other place that implements, duplicates, calls or documents it, and check each was updated consistently: sibling code paths, other commands sharing the rule, callers of a changed output, docs, prompts, templates and config. A finding names the file and line left behind.
> 4. **Tests.** Would the tests fail if the code were wrong? For each promise in the design's test list, find the assertion that enforces it and ask whether a plausible bug would still pass: presence checked instead of value, missing failure and control cases, promises with no test. Test findings target `test_design`.
> 5. **Craft.** Is it clean code that fits its codebase? Readability, naming, cohesion, matching the surrounding idiom, duplicated logic or a reimplemented helper, dead code and unused imports, needless abstraction.
>
> Approving with no findings is a good outcome. Raise a finding only when you can name what goes wrong if it is ignored.

The design replay used the same opening ("Review the design through each of the seven lenses below, in turn and deliberately: give each lens its own pass, and do not stop at the first problems you find. Tag every finding with its lens."), followed by G1000's seven lens texts verbatim. It also asked for a material/note mark and an impact for every finding.

### A.5 Caveats

- One goal per subject, with 3 implementation runs and 2 design runs. The variance is visible (GT1 across the three runs: M, n, –).
- The implementation ground truth is mostly planted defects.
- The design runs had no tools, and the shipped reviewers do.
- The implementation reviewers worked in a full worktree at the submission. The shipped `review_impl` reads git objects at `code.commit` instead, which is the same tree, through `git grep`/`git show` (§5, F1). It has no worktree.
- These are reasons for G1003's re-score on real goals, not for a different graph.
