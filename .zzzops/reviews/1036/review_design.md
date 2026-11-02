# G1036 whitepaper design review, revision 3

Decision: changes requested, for two factual corrections to the proposed paper/checks. This review approves no writing or external publication.

## What checks out

- WD1–WD8 are unchanged byte for byte from revision 2: audience, progressive-disclosure focus, repository paper and blog draft, owner publication boundary, brief generic related work, coined term, byline, ratios/trends with sample sizes.
- The design explicitly waits for G1037 to merge and its anonymised report to exist before either writing phase. Stack-ready base is explicitly insufficient. G1037 attempt 5 has the corresponding dependency-merge boundary for the real run.
- The revised merge-sync account agrees with G1038 revision 3: forward work history, tests/implementation PR parts on the recorded synced base, tested code-tree equality, scoped frozen paths and test fixes after implementation.
- The carry account preserves G1039 revision 3’s per-node own-change and whole-side-union checks, conservative refusal, verification rerun and configuration-driven implementation-review base edge. Its budget wording needs the correction below.
- G1040 adoption includes blocked_findings and the paired revised design prompt. Answered owner decisions, other live findings and genuinely stale carriers remain distinct.
- Evaluation separates actual observations, cited deterministic tests and absent cases; it keeps population/build/capability denominators and avoids inventing G1043 timing results. The design claims no dogfood outcome.
- Public artifacts remain generic about the private app. The paper, report and blog check use privately supplied identifiers, and no extra public app detail is proposed.
- Earlier review findings are already resolved; their corrections remain intact. No closed finding is re-opened or restated in the submission.

## Findings

1. **Clean-sync budget exemption.** G1039 §3.5 exempts base-only stale records of nodes with no checkpoint outputs even when they raise material findings. T8’s statement that a genuinely new material finding spends a round is false for the sync-focused review it describes. State and test the precise exemption and distinguish it from checkpoint-node or changed-subject reruns that count.
2. **Card-size target versus guarantee.** The 4,096-byte hard-bound claim is unsupported by the checked build. G1039 explicitly leaves previous-card oversize to G1019, an open Release 2 goal. Describe the target and current exception, add it to limitations/evidence, and upgrade to a hard guarantee only when the final checked source actually supports one.

## Verification

Read the full task card, prompt, spec, current and prior design blobs and their diff. Read G1037 attempt 5, G1038 revision 3, G1039 revision 3 and G1040 revision 2; checked relevant current templates, normative documents and card implementation at de5640d1c5909ea924450aeea6450497a78946f6.

Ran the existing ShrinkBudgetTests.test_a_card_over_budget_because_of_previous_is_a_fixed_point without editing it: passed in 0.011 seconds. Its normal fixture yields an 8,537-byte card against a 4,096-byte target with zero remaining shrink candidates. This is a documented current limitation, not a new engine defect to fix inside G1036.

## Dogfood notes

None. CLI and card behaved as expected.
