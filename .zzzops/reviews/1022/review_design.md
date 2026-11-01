# G1022 review_design (attempt 1)

**Verdict: changes requested.** The design meets the spec and follows the owner's direction. It has one multi-lens reviewer per subject, a Missing lens, lenses the user can configure through `lenses` plus `<node>:<lens>` skips, and the filter kept. The engine change is small and gets no new verb or record shape. The appendix restates the experiment numbers correctly. Four problems would change the design:

1. The Missing lens would search the wrong tree. This is the lens that produced the experiment's main result.
2. The design does not match G1017's in-progress plan, which makes G1022 depend on G1017.
3. It does not mention G1024, and the new graph reaches other repositories through G1024.
4. One migration claim and test 11 give the wrong stale keys and the wrong budget charge for `review_impl`.

What I checked: the spec, the design (blob 0424a9a), `origin/zzzops/pr/g1020` at 5410809 (which contains G1000 at 6d4715a), the scratchpad files `implx/RESULTS.md`, `run/exp/replay_multi_scores.md` and the `implx` briefs and prompts, G1017's current design (blob 42144d6, attempt 3), and G1024's spec.

## Claims verified against the code (G1020 tree)

- **Skip consumers compare keys with node ids,** so a key containing `:` never matches a node. I checked `frontier.frontier`/`recorded_out` (frontier.py:134, 149), `card.candidates` (card.py:204), `records.process_findings` and `human_findings` (records.py:91, `T in skip`), and `verbs.skip_refusal` (verbs.py:936, which skips non-nodes with `if n not in res.graph.nodes: continue`). `render.skips` (render.py:299) and `integrate.reviews_section` (ops/integrate.py:251) already list every skip key with its reason, so `review_impl:tests: skipped: <reason>` shows without change. Claim holds.
- **The goal skip check is in `validate_goal` rule 2/3** (schemas.py:767-774). It has an orphan warning, a terminal refusal and a `skippable: false` refusal on write (not on read). The design extends exactly this code. Holds.
- **`PATH_SEG`** (verbs.py:796) is `^([A-Za-z0-9_]+)…`, so `skip.review_impl:tests` is refused today and the regex needs the change the design names. `=null` removal goes through `i == 1 and parsed[0][0] == "skip"`. Holds.
- **Older engines.** `NODE_FIELDS` and `FINDING_KEYS` refuse unknown keys (schemas.py:28, 921). A 1.1 engine would therefore treat both the new policy and a goal with tagged findings as invalid, and the floor is needed. Holds.
- **Fingerprints.** `node_def_fp` is an allowlist (fingerprint.py:38). `fp_parts` has three call sites, all in frontier.py (164, 213, 223). `frontier.counts` exempts `def`, `candidates` and `policy.*` (frontier.py:521). Holds.
- **Filter rules** (schemas.py:353-371). Every reviewer of a filter needs a non-context input, which is optional exactly when that reviewer is skippable. The §3 wiring (`review` required, `adversary` optional) satisfies this. A filter with a single reviewer (`filter_impl`) is allowed. Holds.
- **Card text.** `reader.blob_view(text)` already blobs arbitrary text (card.py:35-43, 144), so a blob view of the concatenated `lenses.text` works. Holds.
- **Prompt budgets.** `prompt_stats.py --check` on the G1020 tree gives capture 2,265 of 3,700 and execution 3,030 of 8,800, as stated.
- **Experiment numbers.** Appendix A.1–A.2 match RESULTS.md and replay_multi_scores.md, including run 1 plus the Adversary reaching 7 of 12 (GT1, 7, 8, 11 together with GT1, 2, 3, 7, 12) and S3 being material in 2 of 3 multi-lens runs.
- **G1017's marker** for G1022 (`workflow.json lacks "\"truth_design\""`) becomes true with this graph, because the `lenses` entry is `"truth": {…}` and graph26 moves to `.agents/fixtures/`. It is compatible.

## Findings

### F1 (material, target `design`): the Missing lens is pointed at the wrong tree

In the experiment, every implementation reviewer worked in a full worktree at the submission (`implx/briefs/multi_1.md`: "The code, in the git worktree … (HEAD is the submission) … You may read any file in the worktree"). That is how Missing found GT1: an unchanged `render.py:82-88` in the goal's own tree. The shipped `review_impl` gets no workspace. It gets the `code` checkpoint view (`commit`, `base`, `diff`) and `read_dev`, which is the integration tip. The `review` instruction, which this design keeps, says "Check claims against the integration tip (`read_dev`)". The card offers only `read_dev.grep` (`git grep <pattern> <I>`, card.py:177).

For a stacked goal, and G1022 is one (it stacks on G1000 and G1020), the integration tip lacks the dependencies' code. So a Missing pass over `read_dev` searches a tree that is not the one under review. It misses places the dependency introduced, and reports places the dependency already changed. Even for an unstacked goal, the tip can move after `base`. The consolidation's main justification (Missing found GT1 when no separate lens did) was measured under conditions the shipped card does not reproduce.

**Fix:** say where Missing searches. Two options:
- **Prompt only (preferred).** `lens_missing.md` says to search the subject's own tree, using `git grep <pattern> <code.commit>` and `git show <code.commit>:<path>` with `commit` from the card's `code` view, not `read_dev`. The `review` instruction's `read_dev` sentence gains "for code, the subject's commit".
- **Engine.** The checkpoint view gains a `grep` command beside `diff`.

Add a card-snapshot test asserting that `review_impl`'s lens text, or the view, names the subject commit for search. Note in A.5 that the shipped reviewer reads git objects, not a worktree.

### F2 (material, target `design`): not aligned with G1017's dependency plan

G1017's current design (attempt 3, "Case 3 with a pending row") makes the root run `zzzops edit 1022` to set `depends_on` to `[1000, 1020, 1017]`. It also replaces G1022's acceptance line with "This PR edits docs/design/DESIGN.md and SPEC.md …, adds a HISTORY §4 row and deletes the G1022 pending row".

This design still assumes either outcome: §11 puts "SPEC and DESIGN text" out of scope, §12 says "G1017 applies these if G1022 merges first", §13 says "hand §12 to G1017", and §8 orders delivery G1000 → G1020 → G1022. Under G1017's plan, G1022 cannot merge first, its own PR must edit `docs/design/`, and G1017 merges between G1020 and G1022. G1017's edit will make this design stale and force a second design pass. That pass can be avoided by deciding now.

G1017's pending row for G1022 also lists too few sections: SPEC §3.1, §7, §8.2 and DESIGN §3.8, §4.1, §10. This design's §12 also changes SPEC §3.3, §3.6, §4.8, §4.10, §4.18, §4.20, §5.4 and §8.3. A row that understates the sections lets amendments drift unnoticed.

**Fix:**
- Adopt G1017's case 3 explicitly: `depends_on` `[1000, 1020, 1017]`.
- Bring the docs/design edits into scope: §12's list becomes the edits this PR makes to `docs/design/SPEC.md` and `DESIGN.md`, plus a HISTORY §4 row and deleting the pending row. Add a test-list item for G1017's guard.
- Put G1017 into the §8 delivery order and the "no release cut" window.
- Change §13 step 3 to "the root sends G1017 the full section list for its G1022 row".

Keep the current text only as a fallback, used if G1017's approved design drops case 3.

### F3 (material, target `design`): the rollout to other repositories ignores G1024

§8 covers this repository by a hand-made policy branch, plus MIGRATING. A bootstrapped repository is never told that the default graph changed. G1024's spec names G1000 and G1022 as the reason it exists. The new graph's rollout therefore depends on G1024, but the design does not mention it. The design also creates four coordination points G1024 needs to know about:

- **Files added and removed.** Relative to a 12-node bootstrap, this change adds `review.md` and five `lens_*` prompts and removes `review_design.md` and `review_impl.md`. Relative to the 26-node template, it changes all seven design lens prompts. G1024's item must handle added and removed files, not only changed ones.
- **`workflow.json`.** The `workflow.json` change is a restructuring, and a three-way text merge is not a safe way to adopt it. G1024's `policy_update` step should point to MIGRATING's "Adopting the consolidated graph" when `workflow.json` changed upstream.
- **This repository's record.** G1024 says "This repository's record is created through its next policy branch." If G1024 lands before `zzzops/policy/lenses`, that branch should create or refresh the record. Otherwise the record is stamped with the pre-G1022 template.
- **Engine version.** The design hard-codes `ENGINE_VERSION = "1.2.0"` and floor `1.2.0`. G1024 may need its own minor bump: a new optional POLICY setting requires one (schemas.py:553). Whichever merges second must not reuse 1.2.0.

**Fix:**
- Add a "Rollout to other repositories" paragraph to §8: G1024's `policy_update` item is the notice, and MIGRATING is the procedure it links to.
- Decide whether the release that ships the 15-node template must include G1024. I recommend yes, with no `depends_on` edge, as a release-gating note on the root follow-ups.
- Phrase the version as "the next minor version at merge, and the floor branch uses that version".
- Add a §13 follow-up handing the three file-shape points above to G1024's design.

### F4 (minor but it changes test 11, target `design`): wrong stale keys and budget charge on migration

§8 says the carried-over `review_design` and `review_impl` records are "def-stale … and not counted against the budget". Test 11 expects `stale_keys == ["def"]`. Against the code:

- **`review_design`.** It gains `policy: ["intent"]`, a new `policy.intent` stale key, and the new `lenses` part, so `stale_keys` gives `["def", "lenses", "policy.intent"]`. All three are exempt, so it is uncounted, as claimed, but the expected value in test 11 is wrong.
- **`review_impl`.** The graph12 node's inputs are `doc`, `tests` and `code` (`.agents/fixtures/graph12/workflow.json`). The new node adds `spec`, so `stale_keys` includes `inputs.spec`. `frontier.counts` counts any `inputs.*` stale (frontier.py:525), so the re-run is charged to the budget. The design claims it is not.

**Fix:** correct §8 and test 11 to the actual keys, and choose one of two options:
- Accept one counted run per in-flight goal past `implement`, and say so in MIGRATING.
- Drop `spec` from `review_impl`. Compliance already has the approved design.

Related, for the "from 26 nodes" path: the default limit falls from 60 to 27. A migrated goal that has already used more than 27 runs is over budget at once. MIGRATING should say to set an explicit `budget` first.

## Notes (not findings)

- **Engine naming.** `Graph.lenses(f)` already means "the reviewer nodes of filter `f`", and `card.candidates` uses `"lens"` for the node id. This design adds `lenses` as a node field meaning lens names, and `lens` as a finding key meaning a lens name. Renaming the method to `reviewers` (or similar) during the implementation would avoid two meanings for one word. Test 1 already reads like that.
- **Instructions.** `review_impl` no longer receives POLICY's `security` and `code_quality` instructions, which the 12-node `review_impl` had. G1000's lenses already dropped them, and Correctness covers security generically. A project that tightens `security` therefore no longer reaches its implementation reviewer. This is worth one sentence in D6 or §5.
- **D6.** D6 (no project intent at the implementation stage) is a reasoned call, and I accept it. It is visible on `approve_design`.
