# G1022 review_impl (attempt 2): re-review after the rebase onto dev 5288bf7 (with G1028)

**Verdict: approved, no findings.** The implementation was approved before the rebase. This round reviews only the conflict resolution: `previous.interdiff` (range-diff 256ec0e..bf98f7b) and the merged files at bf98f7b. I checked that neither G1022's nor G1028's/G1029's behaviour was lost.

## Conflict resolution, file by file
- **engine/__init__.py:** `ENGINE_VERSION` is 1.3.0. G1028's `FOLLOWS_SINCE = "1.2.0"` is unchanged, so the `follows` gate (engine.min >= 1.2.0) still works, and adopters who raise the floor to 1.3.0 for lenses also get `follows`. Nothing in tests pins 1.2.0.
- **engine/card.py:** G1028's pieces stay: `from engine import schemas`, `previous.findings` (open only, with `follows`), `previous.resolved`, the two `output_schema` branches and `finding_effect`'s new wording. G1022's pieces sit beside them: the `lenses` checklist (`lens_section`), `lens_label` on notes and candidates, `Graph.reviewers`, and `new_finding_hint(graph, n, follows)`. With follows allowed, the hint renders as `{"target"?: <node>, "lens": "compliance" | … , "text": …, "follows"?: <id>}`. G1028's "partly fixed … follows" sentence is kept. Without follows, it renders as G1028's text plus the lens.
- **engine/schemas.py:** `FINDING_KEYS` holds both `follows` and `lens`. `validate_finding` checks both. `_check_new_findings` allows `follows` in all four branches (filtered or plain review, with or without lenses), validates its id format, and requires `lens` on a multi-lens reviewer. `validate_submit_output` passes `lens_names`.
- **records.py / frontier.py / fingerprint.py / verbs.py:** G1028's `nf["follows"]` and `stale` set are next to G1022's `nf["lens"]`, the `skip` argument to `fp_parts`, and the `lenses` budget exemption. The `PATH_SEG` colon fix is present.
- **add-zzzops-goal SKILL:** G1029's step 2 (intent check, three ways on, the `Project intent:` paragraph) is intact. The steps are renumbered 1-6. Step 3 has G1022's `<reviewer>:<lens>` skip text plus G1029's two sentences about not skipping `approve_design`.
- **CLI_USAGE:** the edit row has G1022's `skip.<node>:<lens>` and G1028's `carried_findings` sentence. Global `--repo` and the `follows` text are kept.
- **lens_intent.md:** G1022's paragraph 1 (no "for code" clause, since the Intent lens is now design-only) is followed by G1029's Project intent paragraph. `approve_design.md` has both G1022's lens bullet and G1029's spec bullet.
- **HISTORY:** rows run G1029, G1028, G1022, matching dev's merge order (#754 then #757). The G1022 row says 1.3.0. **README:** the G1022 pending row is removed, and G1031's row from dev is kept. **MIGRATING:** G1028's "Engine 1.2 … follows" section is intact. G1022's section is "engine 1.3" with floor `1.3.0` ("an older engine"), and the intent-change paragraph says "1.3 graph".
- **Shipped graph and G1029:** G1029's `test_design_intent_node_receives_the_goal_spec` now runs on the frozen 26-node fixture. The shipped 15-node `review_design` and `adversary_design` both still take `spec: goal.spec`, and test_engine_review_lenses.py:159/193 asserts this. So G1029's spec path into the Intent lens is kept in the shipped template.

## Test adjusted at the rebase
`test_skipping_the_lens_of_an_open_finding_keeps_it` (tests line, commit ac9ba21) was adjusted to G1028's semantics, and its docstring says so. Skipping a lens now stales the review, its material finding is carried, and the design reopens (`stale_review` correction) before `review_design` becomes ready (stale) again. Every G1022 assertion stays: the finding id is kept open, the card's `previous.findings` holds it, the skipped lens is not in `lenses.apply`, and the filter candidate is labelled `review_design:concurrency`. The added `run(adversary_design)` follows from the design re-run. The test was not weakened. The tests change is new, so review_tests should see it (the root decides).

## Card budget (4,096 bytes is a target, SPEC §3.14 and the shrink rules)
I measured this on bf98f7b with the shipped template (a scratch test, outside the repository):
- review_impl, first round: 3,948 bytes at engine.min 0.0.0, and 4,068 at 1.3.0 (`follows` offered). Prompt and lens text are already blob views.
- review_design at 1.3.0: 3,756 bytes.
- The frozen card tests (`ReviewerCardTests`, at the default floor) pass.

Observation, not a finding: at the 1.3.0 floor the first-round review_impl card has 28 bytes of headroom. A re-review with two ~150-character prior findings measured 4,819 bytes. The cause is G1028's `previous.findings`: no shrink step reduces it, and that predates this merge. The budget is a target, not a hard limit.

## Checks
`context.checks` passed: all 8 commands, including the full suite and `prompt_stats.py --check`.
