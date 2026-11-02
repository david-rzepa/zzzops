# G1036 whitepaper design review, revision 4

Decision: approved. Both round-3 findings are resolved; no new finding is raised. This approves the design only, not writing before the dependency/report gate or external publication.

## Findings resolved

- **review_design:3:1:** §3 item 7.6, T8, §7 and W15/W16 now state the exact G1039 §3.5 exemption: a node with no checkpoint outputs that starts stale only on git.base-selecting inputs is exempt even if it raises a new material finding. The design distinguishes refused-carry checkpoint nodes and changed-subject reviews that count normally when they add a qualifying new finding. Trace/check evidence now includes stale keys, output classification and actual counter effect; evaluation distinguishes raw findings, charged rounds and exempt reruns.
- **review_design:3:2:** the definition calls 4,096 bytes a target, identifies the oversized-previous fixed point and cites the existing test. T2 reports actual size and overruns; limitations, report inputs and W18 preserve the exception and require checked-build evidence before claiming a hard maximum. G1019 remains outside the prerequisite chain and no engine fix is added. Byte-size observations do not relax the owner’s absolute token/cost restrictions.

## Retained review conclusions

WD1–WD8 are byte-for-byte unchanged from revision 3. The explicit G1037 merge plus anonymised-report gate still blocks writing even if base is stack-ready. The forward merge-sync, exact PR tree, change-based carry and paired blocked-findings/prompt account remains intact. Real observations, cited tests and not-observed cases stay distinct; no dogfood outcome or unmeasured timing result is invented. Public content remains generic about the private app. Venue/byline, claim binding, ratio restrictions, diagrams and the owner-published external blog boundary remain unchanged.

## Verification

Read the fresh card, responses and revision-4 design; compared its full diff with revision 3 and checked the owner-decision section for exact equality. Compared the corrected budget statements with G1039 revision 3 §3.5 and the card exception with the previously verified checked-build implementation/regression. Only design text changed, so no further engine test run was needed.

## Dogfood notes

None. Card and CLI behaved as expected.
