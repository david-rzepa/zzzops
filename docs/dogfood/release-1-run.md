# Release 1 CLI dogfood: in-progress migration milestone

This report records completed bootstrap and backlog-migration observations. The product work and release remain in progress; this is not final acceptance. The [frozen acceptance protocol](release-1-checks.md) governs the eventual result. The [aggregate data](release-1-run.json) explicitly marks incomplete and unavailable quantities.

## Observed so far

The actual Codex executor used merged CLI build `0.0.0-dev f017a54d3e9f` with all required capabilities and no environment mismatch. Claude was not executed under the owner's explicit CLI-only scope override. Matching installations and the owner's assumption are not measured harness equivalence.

The approved one-time ancestry reconciliation changed no source files. The independently reviewed bootstrap then landed the consolidated graph, thirteen mapped operating-policy sections, preserved charter context, capability/prompt pairs and tool-generated reviewed template provenance. Both required exact-head CI checks passed for each administrative PR. Staging and production branches were unchanged.

All twelve counted legacy issues closed. Eleven goals migrated with explicit source links, priorities and releases. The current cohort is two open Release 1 goals, eight held Release 2 goals and one held Release 3 goal. The owner deferred one initial goal after its initial design work; that work is retained and excluded from the current Release 1 source scope. The remaining dependent must use the reviewed non-deferred integration foundation. Source partition and candidate-design approval remain part of the actual goal workflow. Original committed source branches and dirty owner work are preserved.

The post-migration CLI validates policy and environment, but still reports one retained old file and one old ref. Retirement or an explicit archival decision remains pending; disappearance of the legacy notice is not claimed.

The existing local CI dispatcher encountered a provider-request failure after its job succeeded. Recovery verified actual job completion, runner deregistration and exact owned VM identity before using the documented shutdown lifecycle and removing only the completed overlay. Diagnostics remain private. No credentials, trusted images, capacity guard or application source were changed by recovery. This is application-runner friction, not a new engine-defect claim.

A later test correction followed an implementation checkpoint containing product source in forward Git history and passed independent test review. Implementation refresh and source review subsequently passed. The first product goal integrated with both required CI checks passing and a PR code tree matching its tested tree. The real dependent then based onto that unmerged PR checkpoint. Its own work, the dependency merge and post-merge sync remain pending; this does not yet pass the stacked-work acceptance check.

## Measured subset and limits

The four required administrative CI jobs total **776 runner seconds (12.93 minutes)**. The JSON lists each duration so the sum is reproducible. The first product integration adds **277 runner seconds** across its two required checks, giving **1,053 seconds (17.55 minutes)** across the six observed required jobs. These subsets exclude queues, VM lifecycle overhead and agent work; they are not final release costs. 3 deduplicated blocked-agent questions have recorded answer waits totaling 1082 seconds. This subset includes the subsequently deferred initial goal and excludes outer-run waits, routine approvals and unanswered questions. The per-question sum is not unique elapsed owner time. Per-goal tokens, charged rounds, money and total owner waits remain unavailable until actual transcripts and final populations are reconciled. No lens re-score is claimed.

Public goal and evidence labels are explicit anonymized aliases. The private journal retains actual commands, executors, source identities, decisions and read-only replay evidence.

## Acceptance status at this milestone

Pass entries describe only the named interim observations. Pending entries remain required work; no release completion follows from this table or JSON syntax validity.

| Check | Status | Evidence or remaining work |
| --- | --- | --- |
| A1 | pass | Actual Codex CLI build/capabilities and environment validation are recorded; Claude was not executed under the owner override. |
| A2 | pending | The issue inventory is clear, but a retained old file/ref still produces a legacy notice. No cleanup or dismissal is claimed. |
| A3 | pass | Reviewed policy, provenance, capabilities, prompts and instruction mapping landed. |
| A4 | pass | All twelve counted old issues closed; eleven migrated goals have explicit releases and source links. |
| A5 | pending | Two Release 1 goals remain open. |
| A6 | pass | Eight Release 2 goals and the owner-deferred Release 3 goal are held; the deferred goal had initial design work while it was still in Release 1. |
| A7 | pending | Final command/ref audit remains pending. |
| A8 | pending | The dependency integrated with matching tested/PR trees; the dependent based onto its unmerged checkpoint. Actual dependent work and post-merge sync remain pending. |
| A9 | pending | Release cut, sync and finish have not occurred. |
| A10 | pending | Staging and production remain separately unapproved; candidate identity evidence is not complete. |
| A11 | pending | Natural test-review findings reopened test design and were corrected through review; safe dispatcher recovery was also observed. Remaining failure paths are not yet complete. |
| A12 | pending | The final defect inventory has not been reconciled. Existing application-runner friction is distinct from an engine defect. |
| A13 | pending | Six required CI job durations are measured across separate administrative/product subsets; final per-goal agent/token/cost totals remain unavailable. |
| A14 | pending | No final review cohort or lens re-score is available. |
| A15 | pending | The final complete artifact set has not been published/reviewed; this milestone receives its own one-time name check. |
| A16 | pending | Start snapshot and later metadata/source-ref comparisons are preserved; end-of-run comparison remains pending. |
| A17 | pending | The owner confirmed the freeze; the full execution window is still open. |
| A18 | pass | Adopted capability/prompt/base-edge pairs validate; automatic head deletion was observed off. |
| A19 | pending | No completed eligible goal sync is claimed. |
| A20 | pending | The final naturally occurring block/finding/check cases have not been audited. |

## Next boundary

The owner approved the existing non-deferred visual/UX direction. The first product integration has passed implementation review and exact-head CI but remains unmerged at this snapshot. Natural test and source-review findings exercised the reopen/correction loop. The dependent’s discovery and approval are recorded, and its base now includes the unmerged integration checkpoint. Source partition, ordinary reviews and the dependent candidate’s exact approval boundary remain part of the goal workflow. The retired file/ref remain preserved pending explicit cleanup authorization.

Complete the real Release 1 integration and dependent work through design, tests, independent review and exact-head CI. Record actual carry/stale and budget behavior rather than forcing it. Release cut, staging and production remain distinct future gates. Staging and production each need a separate explicit owner approval bound to both relevant tips and the resulting candidate full repository tree and pinned artifact identity; the reduced engine code-tree value alone is insufficient. Refresh that proof before irreversible promotion and after waits or retries. Changed or unproven evidence requires a stop, restaging and renewed separate approvals.
