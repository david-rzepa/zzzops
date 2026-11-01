# G1029 review_design (attempt 1)

**Verdict: changes requested, on one finding.** The skill-only approach is the right size. It meets the spec, and choosing no engine change is well argued under spec item 3. The path from a `Project intent:` paragraph in the spec to the Intent lens holds on both graphs. However, the lens paragraph lets an agent-written label switch off the project-intent check, and the design gives nobody, human or lens, a way to see that the owner actually accepted the departure.

## Claims checked at read_dev 8d8437a and on G1022's 15-node graph

- **The intent path reaches the lens.**
  - On G1022's 15-node graph, `review_design` declares `policy: ["intent"]`, has the input `spec` from `goal.spec`, and applies `lens_intent.md` as its first lens through `lenses.text` (G1022 §3, §4).
  - On the 26-node graph, `intent_design` has the same `spec` input.
  - So a closing spec paragraph reaches the Intent lens's card on both graphs, next to `policy.intent`.
  - `adversary_design` also reads `spec`, which is harmless.
  - Test 3's lookup by the node's `policy` field, not by its name, survives G1022's rebase.
- **Placeholder and absent intent.** `Session.warnings` adds `schemas.intent_warnings` (session.py:130-132), so `next` shows `intent_placeholder`. An absent intent warns nothing, which is why the skill checks absence itself. Correct.
- **Prompt budget.** `prompt_stats --check` gives capture 2,363 of 3,700 at dev, as stated. The roughly 330 added tokens fit.
- **Overlap with G1022.** `lens_intent.md` has the two parts described. G1022 edits the existing paragraph and its "On code:" line, and this design adds a separate paragraph, so a merge conflict would be trivial. Agreed that no dependency is needed.
- **Worked table.** The table against `intent-zzzops.json` uses the owner's actual sentences and a sensible threshold, including the auto-approve judgement call.

## Finding

### F1 (material, target `design`): a recorded departure must carry verifiable owner acceptance, and must stay visible

D3's lens paragraph says: "If the spec ends with a `Project intent:` paragraph, the owner already accepted that departure … Do not raise it again." But nothing ensures that the owner wrote or saw that paragraph:
- The spec is agent-written. In this repository, the root often captures goals from dogfood findings with no owner in the conversation (G1028's spec, for example).
- `edit --set spec=…` can add the paragraph later.
- D4's step offers "Proceed" as an option the capturing agent itself could take.

Two paths therefore remove project intent from every human view after capture:
- **The lens is suppressed.** G1022 D6 makes the Intent lens the only project-intent guard, so a label silences it.
- **Approval may be skipped or uninformed.** add-goal may skip `approve_design` for small goals, and `approve_design.md` does not mention the paragraph.

The intent's own principle requires the opposite: "the owner either changes the goal or amends the intent", and "decisions with big consequences go to the owner". A departure from project intent is such a decision.

**Fix (prompt text only, no engine change):**
- **Skill step 2.** "Amend" and "Proceed" need the owner's own words. With no owner present, create the goal without a `Project intent:` paragraph and say that the design's Intent lens will raise the departure. That lens finding becomes an owner question under G1026.
- **Skill step 3.** Never offer to skip `approve_design` for a goal whose spec has a `Project intent:` paragraph.
- **Lens paragraph (D3).** Honour the paragraph only when it quotes the owner's words with a date, in the D2 format. Otherwise, treat the departure as not accepted.
- **`approve_design.md`.** Show any `Project intent:` paragraph next to the lens verdicts.
- **Tests.** Extend test 2 so the label also appears in `approve_design.md`.

## Owner questions: none

The choices here can be undone inside this goal's change (prompt text and a spec convention), or have a clear winner:
- no engine output at `new`;
- a spec paragraph rather than a goal field.
