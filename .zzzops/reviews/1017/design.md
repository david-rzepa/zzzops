# G1017 design: bring the engine design and spec into the repository

Revision 2. It answers review_design:1:1 (the pending-amendment window has no owner) and re-reads the state at read_dev `a05fb97`, where G1001, G1014, G1015, G1016, G1018 and G1021 have merged. The layout, scrub, history summary and normativity rules from revision 1 are unchanged. What is new:
- "Contract amendments" is rewritten: it now has a fixed apply rule, a re-check whenever `base` moves, a CI guard that fails while a landed goal still has a pending row, and an owner for every remaining row.
- The amendment inventory is updated: six goals are now merged, G1000 is in G1017's base through its dependency, and G1020, G1022 and G1023 are new.

## Outcome

`docs/design/` in the repository holds the engine contract. It contains:
- a scrubbed copy of the approved revision 6.3 DESIGN.md and SPEC.md, brought up to the engine in G1017's base;
- the completed implementation plan, kept as a historical record;
- a short HISTORY.md that summarises the review history and lists every amendment made after approval;
- a README that says which document is normative for what, and lists any amendments still pending, each with an owner.

A card's `read_dev` can show them (`git show <commit>:docs/design/SPEC.md`), G1002 can cite them, and later goals amend them in their own PRs. Nothing new ships in the plugin.

This is a docs-only change: four files move, two files are new, and about six lines change elsewhere. It adds one test file.

## What was found at read_dev (a05fb97)

- `git grep 'zzzops-design-reset\|DESIGN.md\|SPEC.md\|IMPLEMENTATION_PLAN'` finds five hits, none of them a path to the external folder. G1000's PR branch has the same three shipped hits and adds none:
  - `plugins/zzzops/zzzops/zzzops.py:2` (`DESIGN.md §3.15, SPEC.md §6`)
  - `plugins/zzzops/zzzops/engine/__init__.py:1` (`DESIGN.md, SPEC.md`)
  - `docs/MAINTAINING.md:9` ("designed in the reset's DESIGN.md and SPEC.md")
  - `.agents/engine_fake_gh.py:1` and `.agents/engine_fixtures.py:1` (`IMPLEMENTATION_PLAN §1.2`)
- 44 files under `plugins/` and `.agents/` cite sections by name only (`DESIGN §10 item N`, `SPEC §4.14`, `REV6 H23`, `DESIGN C4`, and `Step N` in test docstrings). These stay valid as long as section numbering is kept, so they do not change. One sentence in MAINTAINING.md says where they resolve.
- No skill, prompt, rule, reference or template under `plugins/` names the external folder. The folder is cited by path only inside the source documents:
  - DESIGN: 18 lines cite `reviews/`, `passes/` and `audit/`.
  - SPEC: 11 lines.
  - IMPLEMENTATION_PLAN: 10 lines, plus 20 absolute paths under `/home/<user>/Work/dev/…` in §0.1, §0.3, §0.4, step 0 and §5.
- The external DESIGN.md and SPEC.md are unchanged since rev 6.3 (Oct 31). No merged goal edited them; the merged goals that change the contract recorded the change in their own design artifacts instead (the next section lists them).
- Private data in the sources:
  - absolute local paths (all in the plan);
  - the owner's name in examples (`"decided_by": "David Rzepa"`, `"agreed with David …"` in DESIGN §3/§4 and SPEC §3.3/§3.4/§3.12);
  - example holder labels with hex session prefixes (`claude:7f3e9a10/design-1`, `claude:9c1d/implement-1`, `claude:c90b/…`, `codex:77e0/…`). They look synthetic, but that cannot be proven, so all of them are treated as session names.
  - `david-rzepa/zzzops` is the public repository slug. It is already in tracked files, so it is kept.
- `.agents/concept_inventory.py` scans `docs/**/*.md`, and `test_concepts` requires zero occurrences of "reversible" and "revertible". The three sources contain neither word. `prompt_stats.py` reads only `AGENTS.md`, rules, skills, references and prompts, so its budgets are unaffected.
- CI (`validate.yml`) runs every `.agents/test_*.py` through `run_product_validation.py`, which discovers tests automatically. So a new test file runs in the required check `dev-required-tests` on every PR's merge ref with no extra wiring.

## Approach

### Target layout

| Path | Source | Content |
|---|---|---|
| `docs/design/README.md` | new, about 50 lines | Normativity, how to cite, how to amend, and the pending-amendments table. |
| `docs/design/DESIGN.md` | `DESIGN.md` rev 6.3 | The scrub, the status line, the revision-history block moved to HISTORY.md, and the applied amendments. |
| `docs/design/SPEC.md` | `SPEC.md` rev 6.3 | The scrub, the status line, the "Sources" bullet rewritten, and the applied amendments. |
| `docs/design/IMPLEMENTATION_PLAN.md` | `IMPLEMENTATION_PLAN.md` | Kept as a historical record. It is the target of the `Step N` and `IMPLEMENTATION_PLAN §1.2` test citations, and its §3 deviation log records where the engine knowingly differs from SPEC. It is scrubbed as described below. |
| `docs/design/HISTORY.md` | new, written from `reviews/`, `passes/` and `audit/` | The review history, summarised, plus the amendment log (§4). |

`docs/design/` is used rather than `docs/` because there are five files. It keeps the contract apart from the user docs, and its README works as the folder's index on GitHub.

### What stays outside

These are not copied: `reviews/` (R0–R9, REV5_CHANGES.md, REV6_CHANGES.md), `passes/` (review 2 prototype and walkthrough, review 3–5 reports, the review-5 Python model), `audit/` (A–G), and the generated `DESIGN.html` and `SPEC.html`, which GitHub's rendering replaces.

Reasons:
- They total about 1 MB of superseded working material.
- The amendments they produced are already folded into rev 6.3.
- The review-5 model is code that nothing imports, and the plan already said never to import it.
- The reports quote session-era paths and would be expensive to scrub.

A later goal can add a report under `docs/design/reviews/` if one is ever needed.

### How review history is summarised (HISTORY.md, about 150–200 lines)

1. **Revisions.** The "Revision history" block from the top of DESIGN.md (revisions 1 to 6.3) moves here, with its path citations rewritten. DESIGN.md keeps one line pointing to it.
2. **Review sources.** One line for each source the documents cite, using the tags they already use: `R0`–`R9`; `audit A`–`G`; pass 2 (prototype, walkthrough); pass 3 (consistency, evolution, generality, harness-platform, human-economics, model-check); `x`, `x2` and `m4` (review 4); `m5` (review 5). Each line gives the scope and the headline result. A header says the reports are not in the repository.
3. **Amendment index.** Every cited amendment id resolves here: REV5 A1–A4 with its B–E sections in a line each; REV6 A1–A6 with B–E summarised by theme; REV6 H1–H30, one line each. The REV6 change list is 32 KB, so this is an index, not a copy.
4. **Amendments after approval.** One row per in-repo change to the contract: goal, PR, sections touched, one-line summary. Rows are added in merge order. The documents keep the label "revision 6.3" plus this log; no new revision number is invented.

### Reference rewriting inside the moved documents

| Found | Becomes |
|---|---|
| `reviews/REV6_CHANGES.md` (optionally with an id) | `[HISTORY](HISTORY.md#amendment-index)`, REV6 *id* |
| `reviews/REV5_CHANGES.md` | the same, for REV5 |
| `reviews/R<n>-….md`, `review<n>/…`, `passes/…`, `audit/<X>…` | The prose tag only ("review R5 §B", "audit report E", "the review-5 model"). HISTORY lists each tag. |
| SPEC's "Sources" bullet | "Sources: the reviews and passes summarised in HISTORY.md." |
| `IMPLEMENTATION_PLAN.md`, `DESIGN.md`, `SPEC.md` naming each other | Relative links within `docs/design/`. |
| `.zzzops/reviews/1002/design.md` (an example artifact path) | Unchanged. It is engine data, not a folder reference. |

Tags such as `R1 A3` and `x:C1` stay as they are.

### Privacy scrub

1. **Absolute paths** (all in the plan):
   - §0.1: the path list becomes the three relative links.
   - §0.3 "Where to work": "Done on branch `reset/engine-v2` from `dev` at `64d5196`; landed as #740."
   - §0.4 and step 0: "the owner's other worktrees" replaces the named paths.
   - §5 "Prompt for the implementing model": replaced by two sentences saying the session was started from the plan and its rules are §0.4 and §0.6.
   - `~/.codex/rules/zzzops.rules` in DESIGN and SPEC is a generic per-user install path and stays.
2. **Personal names:** `"David Rzepa"` becomes `"A. Owner"`; "agreed with David" becomes "agreed with the owner".
3. **Session names:** every example holder label is replaced from one fixed synthetic map that keeps the agent prefix and hex length, so the examples still match SPEC §1.7: `7f3e9a10` → `0a0a0a01`, `9c1d4e7a` → `0a0a0a02`, `9c1d` → `0a01`, `c90b` → `0a02`, `77e0` → `0a03`. Labels that repeat within one worked example stay equal.
4. **Status lines:**
   - DESIGN and SPEC: "Revision 6.3, approved 2026-10-31 and implemented in #740. Amendments since then: HISTORY.md §4; pending: README."
   - Plan: "Completed 2026-10-31; a historical record. DESIGN and SPEC win."
5. **Gate.** The implementation shows this is empty:

   ```
   git grep -nE '/home/|/Users/|/tmp/|zzzops-design-reset|Rzepa|\bDavid\b|claude-1000' -- docs/design
   ```

   The repository slug `david-rzepa/` is allowed. The test below enforces the path part permanently.

## Contract amendments

### The rule

A goal's contract change is applied to `docs/design/` **exactly when that goal's code is in the tree it describes.** There are three cases.

1. **In G1017's base.** These are goals merged into the integration branch at G1017's `base`, and dependencies stacked into it. G1017's implement applies each one, from the goal's merged diff and its approved design artifact, and adds a HISTORY §4 row. Text from a design whose code is not in the base is never applied.
2. **Not in G1017's base, but merging before G1017.** G1017 applies these too. It finds them in two ways:
   - **Every implement run re-checks.** `implement` re-runs whenever `base` moves, because its `base` input changes. Each run lists the goals merged into its base (`git log --format=%s <base> | grep -oE '\(G1[0-9]{3}\)'`) and compares the list with HISTORY §4 and the pending table. A merged goal that changes the contract is applied and its pending row removed. A merged goal that does not change it is ignored.
   - **CI catches anything that merges later.** A landed goal that still has a pending row fails G1017's required check (see "The guard" below). Integrate then gets a failing check, the work goes back to implement, and case 1 applies on the next run. This closes the window between G1017's implement and its merge, whether or not `base` re-ran (G1021 decided that a moving dev alone does not make `base` stale).
3. **Merging after G1017.** These are listed in the README's pending table. Each row has an owner goal, which edits `docs/design/` in its own PR, adds a HISTORY §4 row, and deletes its pending row. The same guard fails that goal's own PR if it lands its code without doing this.

So a merged goal can never keep a pending row: the guard fails any tree that has a goal's code and that goal's pending row together (answers parts 1 and 2 of the correction). And each row has an owner that the guard holds to it (part 3).

### The pending table and its guard

The table in `docs/design/README.md` has one row per pending goal:

| Goal | Sections | Owner | Landed when |
|---|---|---|---|

- **Landed when** is a marker: a repository path plus a fixed string that the goal's code adds (`contains`) or removes (`lacks`). For example, `plugins/zzzops/zzzops/engine/records.py contains "full 40-hex sha"`. A marker is the cheapest signal that is visible in a tree. It is better than commit history, because CI's test shards check out a shallow clone, and a squash-merged subject is not guaranteed to carry the goal id.
- **The guard** is `.agents/test_design_docs.py::test_no_landed_goal_is_pending`. It parses the table and fails for any row whose marker matches, with the message "G<n> has landed: apply its amendments (its design, `.zzzops/reviews/<n>/design.md`) to docs/design, add a HISTORY §4 row, and delete this row". It runs in `dev-required-tests` on every PR's merge ref, so it sees the integration tip that the PR would merge into.
- **The owner** is written into the goal's spec with `zzzops edit` while that goal is still before `implement`: "Edit docs/design/DESIGN.md and SPEC.md for this change (sections …), add a HISTORY §4 row and delete your pending row in docs/design/README.md." If that goal does not already depend on G1017, it also gains `depends_on: 1017`, so that its base contains `docs/design/` (stacked delivery keeps this cheap). An owner goal that is already past `implement` gets no spec edit. Instead it falls under case 2 if it merges first. If G1017 merges first, the guard fails that goal's PR, and the recovery recipe in the README applies: `zzzops reopen <n> base --note "rebase onto docs/design (G1017)"`; implement then applies the row.
- The owner goal may correct its own marker in its PR if its design chose different names. The guard checks only that a matching marker and a remaining row never occur in the same tree.

### Inventory at read_dev a05fb97

**Applied by G1017** (all are in its base; G1000 through its dependency):

| Goal | PR | Contract change | Sections |
|---|---|---|---|
| (#742) | #742 | `--policy-ref` on `next`, `show` and `validate`: read-only, takes a ref or commit, refuses mutating verbs and `validate --policy` with it. Wording from `CLI_USAGE.md` and `engine/cli.py`. | SPEC §6, §3.15, §3.16; DESIGN §3.15 (one line) |
| G1014 | #743 | `edit` output `live_leases_on_changed_nodes` and `warning`; `renew` output `inputs_changed`, `stale_because`, `abandon`, `restart` and `hint` (evaluated with the renewed lease); `validate --policy` impact entries; the next `start` after `abandon` needs `--reclaim`. | SPEC §3.16, §4.12, §4.18 |
| G1018 | #744 | Card checkpoint views `{commit, base, change, diff}` (+`tree`) for `.change`/`.tree` selectors; whole-checkpoint inputs gain `base`; the 4,096-byte shrink steps (no `argv`, 120-character blob summaries, key summaries); approve-item checkpoint context gains `commit` and `base`. | SPEC §3.14, §4.20, §3.15 (items) |
| G1001 | #745 | `new` idempotence: the optional `request_key`, the `Request-Key:` root-commit trailer, `created.recovered` and `created.request_key`, the `duplicate_request_key` warning, the `validation` refusal on a key with different contents, and the request-key scan before allocation. | SPEC §3.13, §3.9, §3.16, §4.17; DESIGN §3.15 (one line) |
| G1015 | #746 | Legacy detection, as its design §6 lists: DESIGN §3.15 cost table and note, §10 items 2 and 10, §5 R11; SPEC §1.8, §2.3, §3.2 `settings.legacy.ignore`, §3.15/§3.16 `legacy` key and the `legacy_policy` blocker, §3.17 exit 4, §4.3 ordering. | as listed |
| G1016 | #747 | `abandon` `restart`/`hint`; card `stale_because` on reclaim cards, `changed`, `commands.renew.when` with top-level `renew` removed; `output_schema` consequence wording; the routine-capability rule keyed on record staleness and no live corrections; submit `details.respond_to` and `no_longer_live`; checkpoint overrides must be a full 40-hex sha (submit and `edit`). | SPEC §3.10, §3.14, §3.16, §4.12, §4.14, §4.20 |
| G1021 | #749 | `git.integrate` step 5b: a local `merge-tree` conflict check against the fetched tip first; then GitHub's verdict (unseen head → wait 60; CONFLICTING/DIRTY → `conflict` on `base` regardless of head; UNKNOWN → wait 60); the 15-minute no-checks human question; the reason text with merge state. `base` stays non-stale when dev moves (the decision is recorded in DESIGN §3.16). REPAIR.md recipe. | SPEC §5.4, §8.4; DESIGN §3.16 (one paragraph) |
| G1000 | #748 | The 26-node lens graph, filter, notes, skips, project intent and the re-review pointer, exactly as its design §17 lists. | SPEC §3.1, §3.2, §3.6, §4.9, §4.10, §4.14, §4.18, §4.20, §5.4, §7, §8.2, §8.3; DESIGN §3.8, §4.1, §10 |

Notes:
- G1023 adds no amendment of its own. G1016's full-sha rule is the contract. G1017 writes SPEC §4.20's `checkpoint_required` hint and §3.10's override example as `<full 40-hex sha>` under G1016's row, with a footnote that the engine's hint text matches once G1023 lands. G1023's code then only aligns a message to the SPEC.
- SPEC §7's heading "12 nodes" and DESIGN §4.1's "12 nodes" change to 26 with G1000. SPEC §7 and DESIGN §4.1 keep their numbers.

**Expected to be applied through case 2:**
- G1020 (approve-with-notes) is past implement, has not merged, and does not depend on G1017. Its change: a filtered lens may answer `approved` with only non-material findings open (`is_material`); the outcome reads "approved with N notes"; the `review` instruction gains the test_design targeting sentence. Sections: SPEC §4.14, §8.2, §3.16 (submit outcome). G1020 is about to merge, so the expected path is case 1 (merged before G1017's base) or case 2 (the implement re-check). In case it is still unmerged when G1017 implements, it gets a pending row with the marker `plugins/zzzops/zzzops/engine contains "def is_material("` and owner G1020. No spec edit is made, because it is past implement. The guard then makes whichever of G1017 and G1020 merges second apply it.

**Pending, owner assigned now:**
- G1022 (multi-lens reviewer) changes SPEC §3.1, §7 and §8.2, and DESIGN §3.8, §4.1 and §10 again. It has no records yet. Its owner action is a `zzzops edit` before its design starts:
  - add `1017` to `depends_on` (making it `[1000, 1020, 1017]`);
  - replace its acceptance line "DESIGN and SPEC amendments are listed for G1017" with "This PR edits docs/design/DESIGN.md and SPEC.md (§7 graph, DESIGN §4.1, §3.8, §10), adds a HISTORY §4 row and deletes the G1022 pending row".

  Its pending row: marker `plugins/zzzops/zzzops/templates/default/workflow.json lacks "\"truth_design\""` (consolidation removes the separate lens nodes), owner G1022. G1022 may restate the marker in its own PR.
- **Who makes the edit:** the root, right after this design is approved, so that G1022's design is written against docs/design. G1017's implement checks that the edit was made (`zzzops show 1022`), and makes it itself if not.

**At implement, also check the open goals.** Look for any other open goal whose spec or approved design names DESIGN, SPEC, "contract" or "G1017". Give each one a row and an owner by the same rule. G1002 already depends on G1017.

### Rejected alternatives for the window

- **Check once at implement (revision 1).** This leaves an unowned window between implement and merge. That was the finding.
- **Detect merged goals from `git log` in the test.** The test shards check out a shallow clone, and subject formats vary. A tree marker is deterministic.
- **Make every contract goal depend on G1017.** Goals past implement would re-run work for a docs change. Case 2 and the guard cover them at no cost.
- **Block G1017 until every listed goal merges.** This delays G1002 behind unrelated goals, such as G1022, which has not started.

## Other in-repo changes

- **Root `README.md`, "What to read next":** add "[Design and specification](docs/design/README.md) — the engine contract (SPEC) and its rationale (DESIGN)."
- **`docs/design/README.md`:**
  - SPEC is the contract: exact names, formats, algorithms and CLI.
  - DESIGN is the rationale and the record of decisions; it wins on *what* was decided (its existing precedence rule, restated).
  - IMPLEMENTATION_PLAN and HISTORY are records, not contract. The plan's §3 deviations are known divergences between the engine and SPEC.
  - How to cite: `DESIGN §x`, `SPEC §x`, `REV6 H<n>`.
  - How to amend: edit both documents in the goal's PR and add a HISTORY §4 row.
  - The pending table, its guard, and the recovery recipe.
- **`docs/MAINTAINING.md:9`:** link `design/DESIGN.md` and `design/SPEC.md`, and add one sentence saying that the `DESIGN §`, `SPEC §`, `REV6 H<n>` and `Step <n>` citations in engine code and tests resolve to `docs/design/`.
- **`zzzops.py:2` and `engine/__init__.py:1`:** the bare file names become `docs/design/DESIGN.md` and `docs/design/SPEC.md`. These two docstring lines are the only shipped change. They change the package digest, as any engine edit does, but not the version or the behaviour. If G1000 or G1020 touches `engine/__init__.py` (the `ENGINE_VERSION` line), the edit is one line away and rebases cleanly.
- **`.agents/engine_fake_gh.py:1` and `engine_fixtures.py:1`:** no change.

Nothing new is bundled. `docs/` is outside `plugins/zzzops`, so prompt budgets are unchanged.

## Alternatives rejected (layout and scope)

- **Copy `reviews/` and `passes/` verbatim.** It adds about 1 MB of superseded material and needs a large scrub, and the brief asks for a summary.
- **Leave IMPLEMENTATION_PLAN outside.** About 20 test docstrings cite its steps, and its deviation log is the only record of known divergence.
- **Fold the deviation log into SPEC.** That is a semantic edit, out of scope for a move. It would make a good follow-up.
- **Ship the documents under `references/`.** It adds about 470 KB to every install. Workers already reach them through `read_dev`.
- **Rewrite every `§` citation as a path.** That is about 60 edits for no gain.
- **Leave the HTML renders in.** They duplicate the Markdown.

## Risks

- **Section numbering drift.** The engine and tests cite section numbers, so every heading number must be kept. Amendments add content inside existing sections and never renumber. The heading diff below checks this.
- **Amendment fidelity.** Eight goals' changes are written from their designs and merged diffs. Where a design and the merged code differ, the code on the base wins, because SPEC describes the engine. Each HISTORY row names the PR, so a reviewer can diff the claim against it. review_impl should sample at least G1000, G1016 and G1021, the largest changes.
- **Merge conflicts with G1020 and G1022.** These are confined to docs/design. The guard makes the second goal to merge resolve them.
- **The marker is wrong or never matches.** The row then stays pending after its goal lands, and the documents drift silently. Mitigations:
  - the owner goal's spec tells it to delete its row, regardless of the marker;
  - G1017's implement re-check lists merged goals by history;
  - at implement, each marker is checked to not match the base (otherwise the row would fail at once) and to match the goal's PR branch where one exists (G1020: `origin/zzzops/pr/g1020`).
- **Missed private data.** The grep is mechanical. A manual read of the plan's §0 and §5, the only dense areas, backs it up.
- **The concept inventory changes** because the new docs add occurrences under `docs/`. The sources contain neither forbidden word, and the gate re-checks after the edits.

## Testing

A new `.agents/test_design_docs.py`, standard library only, under 1 s:
1. **No external folder.** Tracked content under `plugins/`, `.agents/`, `docs/`, `README.md` and `AGENTS.md` contains no `zzzops-design-reset`. `docs/design/` contains no `/home/`, `/Users/` or `/tmp/` paths. The patterns are built by concatenation so the test does not match itself.
2. **Links resolve.** Every relative Markdown link in `docs/design/*.md`, and the new links in `README.md` and `MAINTAINING.md`, resolves to an existing file.
3. **Amendment ids resolve.** Every id cited in DESIGN.md or SPEC.md (`REV[56] [A-H]\d+`, and `H\d+` in REV6 contexts) has an entry in HISTORY.md.
4. **No landed goal is pending (the guard).** It parses the README table and fails for each row whose marker matches. Unit cases use a temporary directory and a synthetic table: a `contains` marker present fails, one absent passes, a `lacks` marker works the other way round, and a malformed row fails with a parse error rather than being skipped. On the real tree the table is empty, or holds only rows whose markers do not match.
5. **Every pending row has an owner** that is a goal id and a marker with a path that exists.

Implement-time checks, recorded in the PR body:
- **Headings unchanged:** `diff <(grep -E '^#{1,4} ' <src>) <(grep -E '^#{1,4} ' docs/design/<file>)` shows only the status and revision-history lines, the "12 nodes" → "26 nodes" headings, and the scrubbed plan §0.3/§5.
- **Body diff** against the external sources: only the scrub table, the status lines, and the amendments in HISTORY §4.
- **Merged-goal re-check:** list the `(G1xxx)` subjects in `git log <base>`. Each contract-changing one has a HISTORY §4 row. Paste the list in the PR body.
- **Owner check:** `zzzops show 1022` shows the spec edit and `depends_on` containing 1017.
- **Gates:** the privacy grep is empty, `python3 .agents/prompt_stats.py` budgets are unchanged, and the full `python3 -m unittest discover -s .agents -p 'test_*.py'` passes.
- **Rendering:** the documents render on GitHub (the PR file view), and `git show <dev>:docs/design/SPEC.md` works after merge.

## Out of scope

- Semantic changes to the contract beyond the listed amendments.
- Reconciling SPEC with the plan's deviation log (a possible follow-up).
- Copying review reports.
- Changing the `§` citations in engine and tests.
- Editing historical goal specs on state branches that cite the external path.
- The whitepaper (G1002).
- Deleting the external folder, which is the owner's decision.

## Decisions taken (owner has delegated approvals)

1. The path is `docs/design/`, and IMPLEMENTATION_PLAN moves too, as a scrubbed record.
2. Reviews, passes, audit and the HTML renders stay outside. HISTORY.md summarises them and indexes every cited amendment id.
3. Example holder labels and the owner's name become synthetic values; the public repository slug is kept.
4. A contract change is applied when its goal's code is in the tree, whether merged or stacked. Every implement run re-checks, and a CI guard fails any tree where a landed goal still has a pending row. Each pending row has an owner goal, given the task by a `zzzops edit` before its implement.
5. G1022 gets `depends_on` 1017 and a docs/design acceptance line now. G1020 is covered by case 2 and the guard. G1023's wording is folded under G1016's row.
6. Nothing new ships; only two docstrings in shipped files change.
