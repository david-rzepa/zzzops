# review_impl G1029 (attempt 1): changes requested

## Checked against design revision 2 (and the D5 review note)
- add-goal SKILL.md: new step 2 before `new`; reads `settings.intent` from the coordinator commit; absent or `intent_placeholder` skips with a tell; three ways on; only the owner chooses in their own words; spec paragraph `Project intent: ... Owner (<date>): "..."`; no owner present means no paragraph and the Intent lens raises it. Step 3 adds the no-skip rule and drops such a skip on `edit`. Steps renumbered; no cross-reference elsewhere in docs or plugins points at the old numbers.
- approve_design.md: shows the paragraph verbatim; the extra sentence (check that it quotes the owner under delegated approvals) is a good addition and is mirrored in DESIGN section 3.12.
- prompt_stats: three capture signals added and held by a unit test; `prompt_stats.py --check` passes at 80d4468 (all enforced contexts within limits).
- Tests: label agreement across skill, lens and approval; the design-stage policy:[intent] node has `goal.spec` as an input (looked up by policy, not name).
- DESIGN section 3.12 bullet and HISTORY section 4 row present. No file under `.zzzops/prompts` edited.

## Finding (target implement)
lens_intent.md: 'A departure is covered by an amendment only once `policy.intent` holds the amendment. In either case, until then, treat the departure as not accepted.' Read literally this also applies to an `Accepted as is` paragraph, so the lens would keep raising departures the owner accepted. Reword so only the `Amendment on ...` case waits for `policy.intent`, and state that `Accepted as is` with the owner's quoted, dated words counts at once. Keep `accepts nothing` (a test needs it).
