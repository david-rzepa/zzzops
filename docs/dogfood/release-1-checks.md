# Release 1 private-app dogfood: acceptance protocol

This is the pre-run verification plan for G1037, approved design attempt 6. It records acceptance criteria before the run, not results. No migration, private-app change, deployment or real two-harness run is claimed here. The implementation adds the mutable report at `docs/dogfood/release-1-run.md` and its aggregate data at `docs/dogfood/release-1-run.json`. Keep this protocol separate from those files so implementing the report does not edit frozen acceptance paths.

The owner’s OD1–OD8 govern the run. Every counted old goal is triaged and assigned a release where migrated; Release 1 work is executed, later-release goals stay held. The engine remains CI/deploy agnostic. Both harnesses must really participate, with at least one Codex root. The private app is never identified in this repository.

## Before the root starts the real run

1. Confirm all dependencies are merged, not merely stack-ready. Pin the merged source, plugin build and capability list. Install that same build in both harnesses before collecting A1; journal any later reinstall and the nodes it ran.
2. Confirm that each harness can actually perform its assigned work. An installed executable, a `--version` result or an actor label is not execution evidence. If either harness cannot run, pause that prerequisite; do not relabel another harness’s work or mark participation passed.
3. Reconfirm the freeze, snapshot the owner’s checkout/worktrees read-only, and prepare two fresh run clones. Never mutate the owner’s checkout or its uncommitted work. Keep locations, branch mappings and raw evidence in the private journal.
4. Refresh the private detailed plan against the approved design and actual source. A superseded plan does not restore removed scrub machinery or grant additional authority. Any approved one-time history housekeeping must change no file; otherwise stop for the owner.
5. Capture the owner’s intent and old-policy mapping, actual CI/check commands, release assignments and migration outcomes through the bootstrap/migration approval steps. The owner selects the real stacked pair; do not manufacture one to satisfy A8.
6. Keep separate future approvals for staging and production. A design approval, release cut, routine delegation or staging approval is not production approval. No deploy is part of planning.

These are bounded execution prerequisites, not assertions that they have already happened. If an owner choice required by a step remains unanswered, block that step with concrete options. Existing plan choices remain in force; do not reopen them without conflicting evidence.

## Evidence boundary and read-only replay

Raw CLI output, real holder/session mappings, goal/issue identifiers, private Git references, checkout snapshots, deployment locations and detailed traces stay in the private journal. The public report uses clearly identified aliases and aggregate data, never aliases presented as real actor labels. Each public evidence reference resolves privately to the actual command, time, immutable input/output and executor. Record the real decision-maker; never invent an owner quote or a Claude/Codex run.

Run the following reads only in the fresh clones or against privately recorded immutable snapshots. Variable values are supplied privately; do not expand them into public text:

```sh
"$RUN_CLI" --version
"$RUN_CLI" validate --repo "$RUN_CLONE"
"$RUN_CLI" show "$GOAL" --json --repo "$RUN_CLONE"
"$RUN_CLI" show "$GOAL" --node "$NODE" --json --repo "$RUN_CLONE"
git -C "$RUN_CLONE" show "$COORDINATOR:.zzzops/POLICY.json"
git -C "$RUN_CLONE" show "$COORDINATOR:.zzzops/workflow.json"
git -C "$RUN_CLONE" show "$COORDINATOR:.zzzops/TEMPLATE.json"
```

Use the source version’s printed commands and output shapes; do not invent obsolete flags or fields. For before/after comparisons, retain the actual earlier snapshots privately; reading current state later is not proof of the earlier state. A reviewer can rerun read-only checks and inspect those snapshots without modifying the app.

## Acceptance matrix

All result statuses begin as pending. The implementation records pass, fail or explicitly not observed with a reason and an evidence reference. “Not observed” satisfies only checks that explicitly allow it; it cannot substitute for both-harness participation, the required stacked pair, or the actual release.

| ID | Evidence and falsifiable check | Expected result / stop condition |
| --- | --- | --- |
| A1 | Capture each harness’s real execution transcript, installed CLI build/capabilities and clone validation at the start. Correlate actual sessions to the private holder map. | Both harnesses performed real run work using the same initial dev build, without package/environment mismatch. Installation alone is insufficient; unavailable harness means wait. |
| A2 | Save pre-migration `validate` with `legacy`/`legacy_policy`, then post-migration validation and counted inventory. | Legacy state is detected first and absent after the agreed migration/cleanup outcome. Preserve exact counts privately; explain any remaining legacy item rather than conceal it. |
| A3 | Read the landed policy, workflow, prompts and TEMPLATE provenance at the bootstrap commit; compare the owner’s intent and every old-policy mapping against their actual approval. | Selected defaults, required capabilities, branching/check settings and reviewed provenance are installed. Kept/declined defaults are acknowledged; no adoption is inferred from package availability. |
| A4 | Reconcile the original counted inventory, approved triage proposal, creation receipts and recorded closure outcomes. | Every counted old issue has exactly the agreed disposition; every migrated goal has its owner-confirmed release. Missing/extra inventory or invented approval fails. |
| A5 | Read final goal documents for the Release 1 cohort and owner closure reasons. | Every Release 1 goal is done, or closed with the owner’s actual reason. An unfinished goal is not reported done. |
| A6 | Read final later-release documents and their dependency/release assignments. | All migrated later-release goals are valid and held with the confirmed release. Do not execute later-release work just to complete this report. |
| A7 | Audit the private command journal and relevant Git history for state/ref repairs. | No hand edits of `zzzops/**` refs beyond an applicable REPAIR recipe, with each use journaled. Undocumented mutations fail. |
| A8 | For the owner-selected real pair, retain pre/post dependency merge records, sync history and tested/integrated code identities. Check work ancestry, recorded synced base and final PR code tree. | A real dependent ran and sync-merged after its dependency merged; forward work history is retained and PR tree equals the tested tree. Empty tests/implementation parts may be omitted. No invented dependent or forced carry. |
| A9 | Read release-cut, sync and finish receipts plus the line-goal history and quoted owner finish decision. | A real release was cut, synced and finished through the engine. A plan, synthetic test or unexecuted approval is not a release. |
| A10 | Privately record the release tip, production target tip, resulting promotion candidate tree/artifact, relevant build/deploy inputs, actual staged identity and acceptance, and each actual owner decision. Refresh both tips and candidate equality immediately before irreversible promotion and after waits, retries or hotfixes; compare the actual production merge/deployed content afterward. | Separate staging and production owner approvals cover the same proven candidate and target evidence. Any relevant tip/candidate/proof change requires a stop, restaging and renewed separate approvals; missing or unequal evidence cannot pass. An unchanged release head or conflict-free merge is insufficient. External freshness is the root’s procedure, not an engine guarantee. |
| A11 | Inspect naturally occurring findings/check failures, stopped-owner lease recovery and real policy-change events. Retain relevant before/after cards and outcomes. | Each path is observed or explicitly not observed with a reason. Only a deliberately lapsed stopped worker lease and a genuinely needed policy change are safe triggers; no broken commits, dummy policies or planted findings. |
| A12 | Compare every generic engine defect in the private journal with its durable goal and source/build evidence. | Each defect has its own redacted goal in this repository; report whether it merged and whether both harnesses were reinstalled before resuming blocked work. No engine fix is hidden in this docs goal. |
| A13 | Recompute per-goal/per-node aggregates from private transcripts and the public aggregate data, retaining population/exclusion rules. | Agent runs, qualifying/charged stage rounds, exempt sync reruns, tokens by real harness/model, wall time, CI minutes and owner waits reconcile. Money estimates carry the actual rate source/date; unavailable measurements are unavailable, never zero or guessed. |
| A14 | Re-score real review rounds against defects discovered later, with consistent definitions and cohort/build evidence. | Report recall, nit rate and tokens per review round, with sample sizes and limitations. Keep synthetic lens experiments separate and do not claim a controlled causal comparison. Any graph change is separate policy work. |
| A15 | Before publication, the root performs the one-time name/slug grep and manually inspects the report, aggregate data and this goal’s public artifacts for identifying details/host paths. Values remain private. | No app name, repository slug, host path, private URL, issue title or other app-specific identifier appears. Identifying words in quotes are `[redacted]`. If a match exists, stop publication and correct it privately; no persistent deny-list or history-wide scrub system is added. |
| A16 | Compare privately retained before/after status, branch/worktree lists and tracked/untracked state of the owner’s checkout/worktrees. | They remain unchanged by the run. Any discrepancy must be explained and resolved with the owner, not reset/cleaned away. |
| A17 | Compare the freeze confirmation/window with actor transcripts and repository activity. | No non-run work touched the app during the freeze. Urgent fixes use engine hotfix goals; unidentified concurrent work stops the affected observation. |
| A18 | Inspect the actual adopted policy and prompts/graph, each engine’s declared capabilities, reviewed TEMPLATE record and owner-confirmed or readable head-delete setting. | Required `merge_sync`, `round_budget`, `blocked_findings`, `release_lines` and retained template requirements are present; add `finding_follows` if used. Revised design step 4 and non-context implementation-review base edge are installed. No `owner_answers`/`sync_carry` capability is invented. With branching, head auto-delete is off; unreadable settings are a limitation, not an automatic failure. |
| A19 | For natural syncs, compare each node’s before/after checkpoint/change/tree/base, carried/stale state, review readiness and actual budget counters. | Clean eligible changes carry; changed tree verification and configured base-focused implementation review rerun. Non-eligible hand resolutions conservatively stale. A no-checkpoint review stale only on base inputs is budget-exempt even if it raises a new material finding. Record not observed if no eligible case occurs. |
| A20 | When natural owner-question blocks, unmatched responses or recurring checks occur, retain the pertinent cards, recorded owner answer and response/refusal/finding records. | Live findings survive a block when enabled; answered owner questions do not cause another block; genuinely stale carriers remain identified; refusals explain rejected keys; different stable checks start a new round while genuine normalized repeats may escalate. Mark absent cases individually not observed. |

## Release and recovery boundaries

The root drives implementation under its actual lease and renews it while the run proceeds. Migration’s one go-ahead, bootstrap policy approval, release cut, staging and production retain their separate authority boundaries. Deletions require the owner’s word. Old approvals/local commits are carried only when actual evidence ties them to that goal; uncommitted owner work is excluded.

Derive the promotion candidate through the app’s existing merge/build/promotion flow, including production-target-only changes. Privately bind the release tip, production target tip, resulting code tree and deployable artifact identity when applicable, with the relevant build/deploy inputs. Staging occurs outside the engine through the app’s own process, under its separate owner approval for that candidate. Record what was actually staged and the owner’s acceptance. If staging cannot prove equality to the resulting production candidate, stop; staging the release branch alone is insufficient.

Only after staging acceptance may the owner separately approve production/`approve_finish` for that same candidate and target evidence. Record both actual decision-makers and their words privately; routine delegation cannot substitute. Immediately before the first irreversible promotion, including starting or resuming `finish` when its production merge can deploy, refresh both tips and re-evaluate candidate equality. Repeat after waits, retries and intervening hotfixes. Any relevant tip, candidate or build/deploy proof change invalidates the earlier external acceptance and approvals: stop, re-establish the candidate, restage and obtain renewed separate staging and production approvals. Lost or unproven equality also stops promotion. If concurrent movement cannot be excluded or accounted for through the irreversible step using the existing flow, do not promote.

After `finish`, compare the actual production merge tree and deployed artifact, when applicable, with the accepted candidate. Different or unproven content cannot be reported as success. These checks are the root’s external procedure: the engine’s line-head and mergeability checks do not prove staging freshness or exclude nonconflicting target-only changes. No deploy-flow redesign or new guard machinery is introduced. Preserve the actual outcome even if deployment fails, using the app’s approved recovery procedure under its own authority. An aborted run leaves the new engine and existing work in place, records the cause, and does not silently roll back or delete anything.

Never redeem, consume or trigger a banked usage reset through any tool, API, script, scheduled task or worker. If allowance is exhausted, stop and report its scheduled refresh; do not change models to evade the boundary.

## Report/data review

The mutable report must distinguish measured real-run evidence, cited deterministic source tests and not-observed cases. Publish no raw private trace, location or identifying actor mapping. Include engine builds and capabilities by run cohort, real harness participation, phase outcomes, A1–A20 results, defect goals, aggregates and a lens re-score with limitations. The aggregate JSON must parse and contain the quantities needed to recompute the report; syntactic validity alone does not prove the numbers.

The independent reviewer replays the read-only checks against private evidence, recomputes totals and ratios from the data and verifies the single publication name check. G1036 writing still waits for the real G1037 run, merged report and its actual findings; this protocol does not claim that dependency is complete.

No new product test, telemetry interface, deploy abstraction, privacy framework or permanent `.agents/` test is required. Existing document/link checks and the standard JSON parser validate artifact structure; the matrix and actual evidence validate the run.
