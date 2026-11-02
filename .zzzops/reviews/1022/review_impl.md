# G1022 review_impl (attempt 1)

**Verdict: approved.** The implementation does what design revision 2 says. Both departures the implementer reported are sound. I found no correctness, security or compliance defect, and the tests were not weakened.

Subject: code `256ec0e` (base `b452cd7`), tests `18fdceb`. The run_tests tree `d5ab0d4` is the code commit's tree with `.zzzops/reviews` excluded (checked with `git mktree`), so the checks ran on this code.

## Compliance (design vs diff)
- **Graph (D1, D2, §3):** the template has exactly 15 nodes. `review_design` has the seven lenses, `policy: ["intent"]`, `skippable: false` and prompt `review.md`. `adversary_design` is unchanged. `review_impl` has the five lenses, with compliance, missing and craft non-skippable. It has no `spec` and no `policy`, and has the instructions `review`, `communication`, `security` and `code_quality`. The wiring of `filter_*`, `approve_*`, `base` and `integrate` matches §3. That gives 9 agent nodes, so the budget is 27.
- **`lenses` field (D3, D5):** `NODE_FIELDS`, `_validate_lenses` (non-empty object, name regex, `prompt`/`skippable` only, the prompt file exists, and a non-skippable lens needs a non-skippable node). The field is allowed only on agent review nodes.
- **Lens skips (D4, D8):** `_check_lens_skip` warns on an unknown lens. It refuses a new non-skippable key on a write, and only warns on a read or when the key was already held. `skip_refusal` ignores keys that are not node ids, so lens skips skip G1000's open-finding refusal. Every other consumer of `skip` compares against node ids, which a key containing `:` never matches (checked: frontier, candidates, process_findings, render.skips, integrate). `PATH_SEG` accepts `:`.
- **Finding tag:** `_check_new_findings(lens_names=…)` requires a declared lens and accepts a skipped one. `process_findings` records `lens`, `FINDING_KEYS` and `validate_finding` accept it, and `lens_label` is used for candidates, notes, approval notes and the PR body.
- **Freshness (D7):** `node_def_fp` adds `lenses` only when the field is present, and the golden 1.1 hashes are tested. `fp_parts(skip=…)` is threaded through all three frontier call sites, which are the only callers. `stale_keys` reports `lenses`, and `counts` exempts it.
- **Card, approvals, PR body:** `lens_section` (apply, skipped, text), the `output_schema` hint naming every declared lens, `lenses_applied` on approval items, and `reviews_section` writing `**review_impl** (…)`.
- **Prompts:** `review.md`, the five implementation lens prompts and the instruction `review` match §5. The Missing lens says to search `code.commit` (`git grep <pattern> <code.commit>`), as F1 asks. The design lenses lost their "On code:" lines. Approval and worker prompts use the new forms.
- **Docs:** EXECUTION, the add-goal and execute skills, CLI_USAGE, MIGRATING (from 12 nodes, from 26 nodes, the budget note, the lens-set edit), package.py, SPEC/DESIGN/HISTORY, and the README row is deleted. The HISTORY section list matches the SPEC sections the diff touches (§3.1, §3.3, §3.6, §3.14, §4.8, §4.10, §4.14, §4.18, §4.20, §5.4, §7). SPEC §8.2 and §8.3 were not edited, which is correct: per the owner decision in HISTORY, prompts are configuration. The design's §12 list was older than that decision.
- **Graph.lenses renamed to Graph.reviewers:** done in every caller. No other open PR branch (g1028, g1029, g1032, g1033, g1034) adds a new `.lenses(` call against its merge base, so the rename creates no silent conflict at rebase.

## Departures judged
1. **Wider budget exemption (SPEC §4.10): accepted.** When `def` is stale, an `inputs.<k>` key that appears in only one side's parts is not charged. In `fp_parts`, input keys come only from the definition (every non-context input, whatever its value is), so the symmetric difference is exactly what the redefinition added or removed. A value change in an input both sides share is still charged. Migrating from 12 nodes needs this: `approve_design` gains the non-context input `filter` and its `design_review` was context. I probed `counts` directly:
   - rename plus `def` gives 0;
   - `def` plus a changed shared input gives 1;
   - an added input without `def` gives 1;
   - a `reopened` reason gives 1;
   - `lenses` only gives 0.

   Only a reviewed policy branch can change `def`, so nobody can use this to get free corrections. SPEC §4.10's prose and pseudocode and the HISTORY row both record it.
2. **No shrink step for `lenses.text`: accepted.** The text becomes a blob view above `INLINE` (600 bytes), exactly as `prompt` and `instructions` do. Every shipped lens set is well above 600 bytes, so the text is always a blob. Below 600 bytes it is too small to matter to `CARD_LIMIT`. A shrink step would add a code path that never fires. SPEC §4.20 describes what was built.

## Correctness and security
- Lens names are validated with `NODE_ID`. Skip keys split at the first `:`. An empty or unknown lens warns and the lens still runs, which fails safe.
- No new shell or git command construction. Lens prompts are read through the existing policy reader.
- Edge (not a defect): a project whose lenses are all skippable could skip every one, leaving `apply == []`. The reviewer would still run. The shipped graph cannot reach this.

## Missing (searched at `256ec0e` with git grep)
Nothing left that blocks. Leftovers, all non-blocking:
- DESIGN §4.1 keeps G1000's 26-node diagram and its "Why seven lenses" paragraph, including the paired-skip example `skip.concurrency_design`/`skip.concurrency_impl`. The new G1022 banner above it says how to read the old text, which is the same pattern G1000 used over the 12-node text. A later docs pass could change that one example to `review_design:concurrency`.
- SPEC §4.10 now states "the shipped default graph has 9 agent nodes … 27". The old line said 6 and 18, which was already stale. The new number is right, but it is configuration in the engine contract. DESIGN §4.1 already carries 27. A later cleanup could reduce SPEC to the formula.
- MIGRATING's 1.1 section (lines 46–50) still describes the 26-node adoption. That is correct as history for 1.1.
- This repository's `.zzzops/workflow.json` is still the 12-node graph, intentionally: it changes through the policy-branch follow-up (§8 step 3).
- No remaining text describes `review_design` or `review_impl` as single-lens, or the default as 26 nodes, outside the annotated historical passages above.

## Tests
- `implement` did not touch `.agents/`, so the frozen tests stand.
- The G1000 and G1020 suites moved to the frozen `graph26` fixture as §9 asks. They have the same assertions; only the template path and the 15-node count in `test_marketplace_bundle` changed.
- The new suite covers design tests 1–15.
- Small gap (a note): no test pins the negative control of the redefined-input exemption, that `def` plus a changed shared input still counts. My direct probe confirms the behaviour.

## Rebase notes for the root (ENGINE_VERSION)
G1028 already uses 1.2.0, so G1022 takes 1.3.0 when it rebases. The code makes this easy: one constant, and the only test checks `>= 1.2.0` (or the G1027 capability). Three text places also name the version and must change together:
- `engine/__init__.py`;
- the HISTORY G1022 row ("`ENGINE_VERSION` 1.2.0");
- MIGRATING: the heading "Adopting the consolidated review graph (engine 1.2)", "The 1.2 default graph", "raise `settings.engine.min` to `1.2.0`", and in the intent paragraph, "`review_design` in the 1.2 graph; … in the 1.1 graph".

After G1028, 1.2 means G1028's engine with the 26-node graph. So that paragraph should read "1.3 graph" and "1.1/1.2 graphs". G1028's own MIGRATING section, "Partly fixed findings (engine 1.2)", sits in the same file, a textual neighbour but not a conflict.
