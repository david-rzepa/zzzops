# G1028 review_design (attempt 2)

**Verdict: approved.** Revision 2 (blob 6f4c785) resolves both of my findings and takes up the review note. The diff from revision 1 touches only §3.1 (preview), §3.3, §4, §5, §6, the new §6a, tests 9, 9a and 9b, §9 and D5/D8. Nothing else changed. No new finding, and no owner question.

## Prior findings

- **review_design:1:1 (`follows` as a G1027 capability): resolved.**
  - §6a names the capability `finding_follows` and ships `engine/capabilities/finding_follows.txt` in G1027's form.
  - Submit refuses `follows` unless G1027's required set (`requires ∪ legacy_caps(min)`) contains it. This is the real guard: once the policy requires the capability, G1027's floor check refuses writes from any engine that lacks it. That closes the other-clone gap I raised.
  - `output_schema` mentions `follows` only when it is required, so no reviewer is told to use a refused key.
  - Both merge orders are stated, in the same way G1027 §5 handles G1022, including the `LEGACY_VERSIONS` mapping when G1028 merges first.
  - §4, §9 (SPEC §4.5), the HISTORY row and D8 are updated, and test 9b covers the gate.
- **review_design:1:2 (`upheld` inheritance): resolved.**
  - Every new finding starts at `upheld: false`, and only `rounds` is inherited (§3.3, D5).
  - The consequence is stated and tested (9a). A finding becomes upheld only through a dispute item, which needs rounds ≥ 2 (`escalates`, frontier.py:302; the uphold path in verbs.py:703-714). So a follow-up of an upheld finding goes to the human at once, with its new text.
  - That is what I asked for: the human sees any text that would be beyond dispute.

## Review note

- `carried_findings` now lists every finding that is live after the edit only because its carrier is stale. That covers a second edit and a pre-filter material lens finding.

## Notes (non-blocking)

- **Follow-ups of disputed findings go straight to the human.** A follow-up of a finding that was disputed once (rounds 2) escalates as soon as it is live, before the target has tried to fix the remaining part. This matches how a finding that is kept open after a dispute behaves today, so it is consistent. The dogfood run should watch whether it creates many human dispute items.
- **Owner questions: none.** The capability name `finding_follows` is a published name, but G1027's rule fixes its form and it has no competing alternative. The other choices are unchanged from attempt 1, where I judged them the designer's.
