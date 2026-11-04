# Release 1 CLI dogfood: in-progress migration milestone

This report records completed bootstrap and backlog-migration observations. The product work and release remain in progress; this is not final acceptance. The [frozen acceptance protocol](release-1-checks.md) governs the eventual result. The [aggregate data](release-1-run.json) explicitly marks incomplete and unavailable quantities.

## Observed so far

The actual Codex executor used merged CLI build `0.0.0-dev f017a54d3e9f` with all required capabilities and no environment mismatch. Claude was not executed under the owner's explicit CLI-only scope override. Matching installations and the owner's assumption are not measured harness equivalence.

The approved one-time ancestry reconciliation changed no source files. The independently reviewed bootstrap then landed the consolidated graph, thirteen mapped operating-policy sections, preserved charter context, capability/prompt pairs and tool-generated reviewed template provenance. Both required exact-head CI checks passed for each administrative PR. Staging and production branches were unchanged.

All twelve counted legacy issues closed. Eleven goals migrated with explicit source links, priorities and releases. The migration cohort contains two initial Release 1 goals, now completed and merged, eight held Release 2 goals and one held Release 3 goal. A later full staging failure added a separate Release 1 corrective goal; it has now merged and is not counted as a migrated goal. The owner deferred one initial goal after its initial design work; that work is retained and excluded from the current Release 1 source scope. The remaining dependent must use the reviewed non-deferred integration foundation. Source partition and candidate-design approval remain part of the actual goal workflow. Original committed source branches and dirty owner work are preserved.

The post-migration CLI validates policy and environment, but still reports one retained old file and one old ref. The owner explicitly chose to keep both items intact. Their notice remains visible; the legacy-absence acceptance expectation is unmet and no cleanup or suppression is claimed.

The existing local CI dispatcher encountered a provider-request failure after its job succeeded. Recovery verified actual job completion, runner deregistration and exact owned VM identity before using the documented shutdown lifecycle and removing only the completed overlay. Diagnostics remain private. No credentials, trusted images, capacity guard or application source were changed by recovery. This is application-runner friction, not a new engine-defect claim.

A later test correction followed an implementation checkpoint containing product source in forward Git history and passed independent test review. Implementation refresh and source review subsequently passed. A further source guard correction followed the normal reviewed workflow and fresh required CI before the first product goal merged. The real dependent had already created its own test work on the unmerged parent checkpoint. Its post-parent-merge sync retained that original checkpoint in forward ancestry and preserved all four own file blobs. Final dependent verification, independent source review, integrated PR and actual merge agree on the tested tree. A real release was then cut and synced. The owner later approved one concrete staging attempt; production remains separately unapproved.


The owner approved the exact staging candidate and retained both legacy items. Its full build then failed in real containerized studio controls: 746 tests, with 740 passing, four failing and two cancelled. A preview test timed out after 180 seconds; other failures concerned built files, assets and font readiness. The earlier 142 second cleanup signature was not established. Actual cache authentication, image provenance resolution and locked private profile preparation succeeded, but they do not make the failed producer acceptable. The main-controlled candidate check rejected it; production backup, staging restore/browser acceptance and seal were all skipped. No active staging operation or sealed acceptance occurred, and no production/finish authority was granted. A changed candidate will require reviewed correction, fresh source/artifact proof and renewed staging approval.

The corrective goal subsequently merged after full image verification and official exact-head CI. Its verification image passed all 758 studio tests and thirteen publication controls, plus the native card check using the exact default production ICC profile. The release synced again and its corrected full-tree candidate is proven. Renewed staging approval and new-source producer/artifact acceptance remain pending. One nonblocking engine defect was observed: a current release-sync ref is counted as legacy; public goal G1044 captures it without private identifiers. No engine fix or installation is claimed.

## Measured subset and limits

The four required administrative CI jobs total **776 runner seconds (12.93 minutes)**. The JSON lists each duration so the sum is reproducible. The product integration checks add **1,109 runner seconds** across nine execution intervals, giving **1,885 seconds (31.42 minutes)** across thirteen required job executions. Two failed jobs are included. A successful interval copied into the provider's retry response is counted once, despite its new reported job ID. The attempted staging producer/controller adds **1,121 seconds** across four executed jobs, giving **3,006 seconds (50.10 minutes)** across seventeen measured workflow jobs. Required checks account for 2,896 seconds; publication/controller jobs are listed separately. Skipped jobs are excluded. Correction verification, its official PR and release sync add **3,766 seconds** across eight jobs. The observed total is **6,772 seconds (112.87 minutes)** across twenty-five executed provider jobs, of which required checks account for 6,662 seconds. Queue/VM overhead and agent cost are not estimated; these remain measured subsets, not final release costs. 3 deduplicated blocked-agent questions have recorded answer waits totaling 1082 seconds. This subset includes the subsequently deferred initial goal and excludes outer-run waits, routine approvals and unanswered questions. The per-question sum is not unique elapsed owner time. Per-goal tokens, charged rounds, money and total owner waits remain unavailable until actual transcripts and final populations are reconciled. No lens re-score is claimed.

Public goal and evidence labels are explicit anonymized aliases. The private journal retains actual commands, executors, source identities, decisions and read-only replay evidence.

## Acceptance status at this milestone

Pass entries describe only the named interim observations. Pending entries remain required work; no release completion follows from this table or JSON syntax validity.

| Check | Status | Evidence or remaining work |
| --- | --- | --- |
| A1 | pass | Actual Codex CLI build/capabilities and environment validation are recorded; Claude was not executed under the owner override. |
| A2 | fail | Owner explicitly retained both legacy items; their visible notice remains, so this legacy-absence expectation is unmet. No cleanup or suppression was performed. |
| A3 | pass | Reviewed policy, provenance, capabilities, prompts and instruction mapping landed. |
| A4 | pass | All twelve counted old issues closed; eleven migrated goals have explicit releases and source links. |
| A5 | pass | Both initial product goals and the staging correction merged; the release itself is unfinished. |
| A6 | pass | Eight Release 2 goals and the owner-deferred Release 3 goal are held; the deferred goal had initial design work while it was still in Release 1. |
| A7 | pending | Final command/ref audit remains pending. |
| A8 | pass | Real dependent tests preceded the parent merge; forward sync retained that history and file blobs, and final reviewed/tested/integrated/merged trees agree. |
| A9 | pending | The actual release was cut and synced again after correction; finish remains pending after successful staging and separate production approval. |
| A10 | pending | The old approved candidate failed before deployment. The corrected full-tree candidate is proven and awaits renewed staging approval and actual original artifacts/acceptance. |
| A11 | pending | Natural review findings, CI failures, retry and correction were observed. Stopped-worker expiry/reclaim and a policy-change pause remain unaudited. |
| A12 | pending | One nonblocking generic engine defect is durably captured as public goal1044, still open; no hidden fix or installation is claimed. Final inventory audit remains pending. |
| A13 | pending | Twenty-five unique executed provider jobs total 6,772 seconds, with required checks separately identified. Final agent/token/cost populations remain unavailable. |
| A14 | pending | No final review cohort or lens re-score is available. |
| A15 | pending | The final complete artifact set has not been published/reviewed; this milestone receives its own one-time name check. |
| A16 | pending | Start snapshot and later metadata/source-ref comparisons are preserved; end-of-run comparison remains pending. |
| A17 | pending | The owner confirmed the freeze; the full execution window is still open. |
| A18 | pass | Adopted capability/prompt/base-edge pairs validate; automatic head deletion was observed off. |
| A19 | pending | A clean sync preserved the dependent test change and file blobs while updating its base/checkpoint. Other carry/stale and base-only review cases remain unaudited. |
| A20 | pending | The final naturally occurring block/finding/check cases have not been audited. |

## Next boundary

Both initial product goals and the later correction are merged. The release synced after correction; its new full-tree candidate is ready for a renewed explicit staging decision. Prior failed staging evidence is retained. No corrected staging push, production action or finish is claimed. The owner retains both genuine legacy items; the warning remains visible, with the current-sync false positive tracked separately as G1044.

Complete the actual staging, production and release-finish gates and final evidence audits. Record actual carry/stale and budget behavior rather than forcing it. Staging and production each need a separate explicit owner approval bound to both relevant tips and the resulting candidate full repository tree and pinned artifact identity; the reduced engine code-tree value alone is insufficient. Refresh that proof before irreversible promotion and after waits or retries. Changed or unproven evidence requires a stop, restaging and renewed separate approvals.

The outer phase is blocked pending the owner’s fresh explicit staging decision for the privately pinned corrected candidate. The earlier approval covered the failed candidate. Both legacy items remain intact with their warning visible. Production and release finish remain separately unapproved; the run is incomplete.
