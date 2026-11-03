# G1037 design: dogfood Release 1 on a private web app, from migration to a finished release

Attempt 7: answers implement:2:1 and records the owner's 2026-11-03 CLI-only scope override (OD9). Codex-only CLI execution is permitted; genuine Claude participation and cross-harness comparison are no longer acceptance prerequisites. The report records only actual executors, builds and observations, without asserting untested equivalence. OD1–OD8, the confirmed freeze, private owner-state protection, real stacked/release requirements and separate deployment approvals with candidate freshness proof remain unchanged. Read_dev: `edb9b2c9aa317220a8e1340f27c40b6a4b6a1b5a`.

The app's identity and every fact specific to it are kept out of this repository (OD7). **The detailed plan is in the root's private journal**: per-phase steps, evidence about the app, triage proposals, and the release mechanics against the app's own deploy flow. This document is the generic plan the reviewers judge, and it is what the whitepaper can cite.

## 1. Outcome

The Release 1 engine is exercised end to end on a real repository that has a pre-reset installation:
- install and exercise the merged dev CLI through Codex, recording the actual executor and build (OD9);
- detect the legacy state and migrate it;
- bootstrap the new policy with the owner's intent;
- run the migrated goals through the default graph;
- cut, sync and finish one release through the engine.

Defects become goals here. An anonymised report with costs and a lens re-score is committed here for the whitepaper (G1036).

## 2. Owner decisions (2026-11-01 and 2026-11-03, relayed by the coordinator)

Identifying words are replaced by `[redacted]`. Everything else is verbatim.

- **OD1:** "All goals are in scope - as part of the migration releases should be assigned". Every open old goal is migrated and gets a release. The migrate skill does not assign releases today, so this is captured as G1034, which G1037 depends on.
- **OD2:** "The only reason I want dogfood before whitepaper is in case we need to make changes". G1036 (the whitepaper) can be designed once this design is approved. Its writing waits for G1037's merge, through its `depends_on: [1000, 1017, 1037]`.
- **OD3:** "still use release branches, when ready to deploy, merge to [redacted] for staging, then merge to [redacted]. zzzops should be CI/release flow agnostic". G1025's release lines are used as designed. The app's own promotion steps stay outside the engine.
- **OD4:** "Push per migrated goal". Local-only commits that belong to a migrated goal are pushed to that goal's work branch. The owner's uncommitted state is out of scope.
- **OD5:** "Freeze, hotfixes via engine". No other work happens on the app during the run. Urgent fixes become engine hotfix goals.
- **OD6:** "Both real, approved separately". Each deploying step needs its own owner approval, at a time the owner names.
- **OD7:** "Anonymised entirely", and later "Purge, keep plan private". Nothing in this repository names the app (§6).
- **OD8:** "I don't think we need to worry too much about scrubbing secrets, that's intent drift in my opinion..". The scrub machinery is dropped. The convention stays (§6).
- **OD9 (2026-11-03; implement:2:1):** "Yeah, nothing else is modifying the target repo. We don't need to worry about Claude, we can assume Codex and Claude work similarly enough, we're dogfooding the CLI, not the model/harness". The owner confirms OD5's freeze and permits Codex-only CLI execution, superseding the spec's and earlier designs' mandatory participation by both harnesses. This is scope authority, not measured evidence of Claude execution or cross-harness equivalence. Report Claude as not executed unless actual participation is separately evidenced; no Claude call or installation is required to satisfy this run.

## 3. The graph: what each node means

| Node | Meaning for G1037 | Who |
|---|---|---|
| `design` | This plan (public, generic) and the private detailed plan. | worker |
| `review_design` (+ `adversary_design`, `filter_design`) | Is the plan feasible? Are deploy and data safe? Is the naming convention kept? Which owner questions are left open (G1026)? | workers |
| `approve_design` | The owner approves. This is the authority to write to the app's repository within the plan, and nothing more: it grants no deploy authority (OD6). | owner |
| `base` | Unchanged engine operation, which can run on integrated dependency heads before they merge. The root does not begin the real run until all dependencies have merged, so the build under test contains them all. | op |
| `test_design` | Commits the acceptance checks (§5) into the report skeleton before the run starts. | worker |
| `review_tests` | Do the checks cover the spec as amended by OD9, and OD1 to OD9? Can each one be falsified? | worker |
| `implement` | Executes the run (§4) and commits the anonymised report and data at milestones. **The root holds this lease** and renews it while it drives the app. A lapse is reclaimed with `start --reclaim`. | root |
| `run_tests` | Unchanged: the suite runs on the report commit. | op |
| `review_impl` | Re-runs the checks' read-only commands, recomputes the tables from the data file, runs the A15 name check, and confirms that every listed defect goal exists. | worker |
| `integrate`, `approve_merge`, `merge` | Unchanged: a docs PR, approved by the owner. | op / owner / op |

**Rejected alternatives:**
- **Child goals per phase.** Each would cost a full graph, and the phases cannot be reviewed apart.
- **A custom process graph.** It needs a policy change, which pauses all work.
- **Running the work with no lease.** The run would be invisible to other roots.

## 4. Phases

1. **Preconditions.**
   - Dependencies merged: every goal in G1037's dependency list, including G1024, G1031, G1038, G1039 and G1040. Design/review and a stack-ready `base` can advance earlier; the actual run cannot.
   - The freeze is in effect (OD5), explicitly confirmed by the owner in OD9.
   - Use a fresh run clone for the Codex CLI actor; keep a separate clone available for the lease-reclaim observation when needed. Clones are not assigned to mandatory different harnesses. The owner's own checkout is only read.
   - The private journal is ready: plan, holder map and cost exports.
   - Any one-time branch housekeeping the app needs before the engine owns refs is listed in the private plan. It is approved with this design, and it stops if it would change any file.
2. **Install.** Install the CLI build from the merged dev commit for the actual Codex executor and record its `validate` result, `build` and `capabilities` (G1027), rather than treating `0.0.0-dev` as a numbered engine version. Journal every actual executor, reinstall and node/build association. Codex-only execution satisfies the owner's revised scope (OD9); Claude execution is not required. An installed Claude copy, matching bytes or the owner's assumption is not proof that Claude ran a node or behaved equivalently. If another executor participates, record its actual build, validation and actions; otherwise label that participation not executed under OD9. Existing checkouts and other active host sessions are preserved.
3. **Detect and bootstrap.**
   - `validate` shows the legacy item and the old-policy blocker.
   - The bootstrap skill writes the policy from the complete merged templates: the intent in the owner's words, the consolidated graph and prompts (G1022/G1026), `TEMPLATE.json` (G1024), `engine.requires` (G1027), the branching block (G1025), `required_ci`, verification commands and `first_id`.
   - Adopt the reviewed friction fixes explicitly; copying the default POLICY alone does not enable their gated behaviour. Require the capabilities the selected features need, retaining the template's requirements and adding `release_lines`, `merge_sync`, `round_budget`, `blocked_findings`, and `finding_follows` when that finding form is used. G1026 reads human decisions from history and needs no separate `owner_answers` capability. Use the settled names; `sync_carry` is not a capability.
   - Pair `blocked_findings` with the revised design prompt step 4 from G1040 in the same policy change (or land the prompt earlier). An answered owner question is recorded and answered as a correction; an unanswered one blocks. Never enable the capability with the older instruction to block on every owner-question correction.
   - The chosen graph includes G1039's non-context `review_impl.inputs.base` edge from `base.base_commit` and the review prompt's after-sync instructions. The default graph stays configuration, not an engine rule. G1038's test-design and implement prompts allow test fixes after implementation and use HEAD/scoped frozen paths, replacing the older root instruction to reorder tests before code.
   - Use G1024's `record.reviewed` for the final selected defaults; use `record.inferred` only when recovering an existing policy's factual provenance without reviewing updates. A kept or declined default is recorded through the policy process, never a goal's code diff. Review `workflow.json` before copying or removing its prompts.
   - With branching enabled, turn automatic head-branch deletion off under the existing host-settings approval (G1031), because finish uses the kept release/hotfix branch as the PR head. `validate`'s best-effort warning is evidence when readable, not a prerequisite that fails on an unreadable host setting.
   - Each old operating-policy rule is mapped into the new instruction texts, and the owner reviews the mapping.
   - The policy lands through a `zzzops/policy/*` branch.
4. **Migrate.**
   - Inventory exactly the counted issues, reading bodies only.
   - Triage each issue, and give each one a release (OD1, G1034).
   - Get one owner go-ahead, then apply.
   - Carry forward each goal's own local commits (OD4), plus only the approvals the owner actually gave.
   - Later-release goals are created **held**. The release gate guards only `merge`, so an open later-release goal would spend budget and owner time now. Release 1 goals are created open.
   - Clean up only on the owner's word. Re-validate.
5. **Execute.**
   - Drive the app's `next` loop with the actual Codex root/CLI executor and workers. Codex-only routing is allowed (OD9); journal the real actor/holder/build for each phase, without relabeling a Codex worker as Claude or claiming a cross-harness comparison.
   - Follow the owner's existing delegation for routine approvals. Every consequential owner choice, every review-raised owner question, and each separate staging/production decision goes to the owner; record the actual decision-maker and journal the wait. A delegate never records their own answer as the owner's words.
   - Release 1 includes at least one real stacked dependent that syncs after its dependency merges. The pair is the owner's choice and is never invented. With `merge_sync` required, the work branch moves forward through engine sync merges, and integrate creates the tests/implementation PR commits on the recorded synced base (not whatever trunk tip is live later). The final PR code tree must equal the tested work tree; empty tests or implementation parts may be omitted, as G1038 defines.
   - Observe G1039 on that sync when it leaves a node's own change clean: the carried tests/implementation checkpoints keep their change identities and their bound reviews stay current, while the changed tree re-runs verification and the base edge re-runs `review_impl` for semantic conflicts. If a hand resolution changes the node's own lines or is not an accepted whole-side union, expect that node to stale instead. Record which case happened; never waive or force carry to satisfy the report.
   - Journal budget use by stage under `round_budget`; clean-sync review reruns do not spend a new finding round. This is an observation of G1039, not a new budget counter or a new policy rule.
6. **Failure paths.**
   - A review finding that reopens its target, a failing check, an expired lease reclaimed from the second clone, and a policy branch that pauses work.
   - Natural occurrences are preferred. Only safe triggers are used: a deliberately lapsed lease, and a real policy change.
   - Nothing is planted in the owner's repository. A path that does not occur is reported as not observed.
   - When a real owner-question block follows a review containing other findings, keep the before-block and retry card observations privately. After the answer, G1040 must show the still-live corrections, and the designer answers them without re-blocking on the already-answered question. A genuinely stale carrier is identified separately. An unmatched response refusal must explain why; a different failing check is a new round, while an equivalent normalized failure may repeat. These paths are observed only if they occur; existing dependency tests cover the deterministic cases.
7. **Release (G1025, OD3, OD6).**
   - The owner approves `release_cut`, which cuts the release line. Stabilisation goals target the line, and `sync` back-merges it into the integration branch.
   - In the private release runbook, the root records the release tip, the current production target tip, and the resulting promotion candidate code tree and deployable artifact identity (when the app deploys an artifact). Derive the candidate using the app's existing merge/build/promotion flow, including target-only changes; the release tip alone is not the candidate identity. Keep the relevant build/deploy inputs and evidence linking the staged content to that candidate privately. Do not infer equality merely from conflict-free mergeability.
   - The app's own staging step happens **outside the engine**, with its own owner approval covering that candidate. Record what was actually staged, its tree/artifact identity, the relevant tips and the owner's acceptance. If the existing staging flow cannot demonstrate equality to the resulting production candidate, stop; do not substitute staging of the release branch alone.
   - The owner approves `approve_finish` (production) only after staging is accepted, with a separate decision covering the same candidate and target evidence. The root records the actual decision-maker and the owner's words for both deploying steps; routine delegated approvals never substitute for OD6.
   - Immediately before the first irreversible promotion, including starting/resuming `finish` when its production merge can deploy, the root refreshes both relevant tips and re-evaluates the resulting candidate against the accepted staging evidence. Repeat this after waits, retries or intervening hotfixes. Any relevant tip, candidate or build/deploy proof change invalidates the earlier external acceptance/approvals for this run: stop, re-establish the candidate, restage it and obtain renewed separate staging and production approvals. Lost or unproven equality is a stop, never permission to rely on an unchanged release head. Preserve the freeze and engine-managed hotfix rules; if concurrent movement cannot be excluded or accounted for through the irreversible step using the existing flow, do not promote.
   - `finish` merges into the production branch and back-merges. Record the actual production merge tree and deployed artifact, when applicable, against the accepted candidate; do not report success if the resulting content is different or unproven.
   - These external evidence and approval freshness checks are the root's procedure, **not an automatic engine guarantee**. G1025 binds the recorded line head and checks mergeability, but a nonconflicting production-target change can survive its merge while the line head stays unchanged. The engine stays CI- and deploy-agnostic. **No G1025 change, app deploy-flow redesign or new guard machinery is needed.** If the outside step proves error-prone, a generic defect is captured.
8. **Abort.** The new engine stays. Nothing is deleted. The report records the cause.
9. **Report.** The anonymised write-up and data are committed (§7).

## 5. Acceptance checks (written by `test_design`, re-run by `review_impl`)

| Id | Check |
|---|---|
| A1 | Actual Codex CLI execution is evidenced with executor/holder, merged dev build, available/required capabilities, validation result and the nodes/actions it ran. Claude participation is not required under OD9 and is recorded as not executed unless independently evidenced. Matching installed bytes or the owner's assumption is not a participation or equivalence result. |
| A2 | Legacy detection showed the migrate item before migration and nothing after it. |
| A3 | Bootstrap landed the selected consolidated graph/prompts, owner-worded intent, G1024 provenance record, required capabilities, branching block and old-policy mapping. The record acknowledges kept/declined defaults. |
| A4 | Every counted old issue has a recorded outcome, and every migrated goal has a release. |
| A5 | Every Release 1 goal closed done, or closed with the owner's reason. |
| A6 | Later-release goals are migrated, valid, carry their release and are held. |
| A7 | No hand edits of `zzzops/**` refs beyond REPAIR.md recipes, each of which is journaled. |
| A8 | A real stacked dependent ran and synced after its dependency merged. The sync follows merge mode, preserves forward work history, and integrate produces the tests/implementation PR parts on the synced base with the tested code tree. |
| A9 | One release was cut, synced and finished through the engine, with the owner's finish approval quoted (redacted where needed). |
| A10 | Private evidence records the release tip, production target tip, resulting promotion candidate tree/artifact and what was actually staged. Staging and production each had a separate owner approval for that candidate. The root refreshed both tips and re-evaluated candidate equality immediately before irreversible promotion and after waits/retries; relevant tip/proof changes caused a stop, restaging and renewed separate approvals. Actual production merge/deployed content matched the accepted candidate. Missing or unequal evidence is not a pass; external freshness is a root procedure, not an engine guarantee. |
| A11 | Each failure path was observed, or marked not observed with a reason. |
| A12 | Every defect has its own goal in this repository. |
| A13 | Per-goal costs are reported and can be recomputed from the data file. |
| A14 | The lens re-score is reported. |
| A15 | The report and this goal's public artifacts do not name the app. Checked by a quick grep for the app's name and repository slug before the report is published. |
| A16 | The owner's checkout and worktrees are unchanged since the start snapshot. |
| A17 | No non-run work touched the app during the freeze. |
| A18 | The bootstrap's actual policy requires `merge_sync`, `round_budget` and `blocked_findings`, includes the revised design step 4 and review_impl base edge, and each CLI executor that actually writes declares the required capabilities. No second harness is required by this check (OD9). With branching, head auto-delete is off as owner-confirmed or observed. |
| A19 | On naturally occurring syncs, record whether each node was carried or staled; for a clean carry, its change-bound reviews stay current, while verification and review_impl re-run on the new tree/base. Report not observed if no eligible clean sync occurs; do not invent work or force carry. |
| A20 | On naturally occurring owner-question blocks/check failures, record whether live findings survived the block, answered owner questions avoided a second block, refusals explained unmatched responses, and distinct check failures started a new round. Mark each unobserved case honestly. |

The spec's "every migrated goal closes done" is read under OD1 as applying to Release 1 goals. Later-release goals are covered by A6. OD9 supersedes the spec's requirement that both harnesses participate: A1 tests actual CLI execution and truthful attribution, not model/harness equivalence.

No permanent test goes into `.agents/`: the checks are commands with recorded outputs.

## 6. Naming convention (OD7, OD8)

- The app is never named in this repository. Public artifacts (designs, reviews, findings, defect goals, PR text, the report) describe it generically. Owner quotes are verbatim, with identifying words replaced by `[redacted]`.
- The detailed plan and every app-specific fact stay in the root's private journal.
- Before the report is published, one quick grep checks it and this goal's public artifacts for the app's name and repository slug (A15). There is no per-write gate, history-wide scan or deny list (OD8).

## 7. Report for G1036 (anonymised)

- **Actual executors and engine builds:** each actor/holder, `build` id and required/available capabilities, and which nodes/actions each actually ran. Explicitly record Claude as not executed under OD9 when applicable; do not claim measured model/harness equivalence or count installation as participation.
- **Engine changes caused by the run:** defect goals, and whether each merged before the release.
- **What worked and what did not,** per phase.
- **Costs** per goal and per node:
  - agent runs, new material-finding rounds and budget used by stage; sync-only reruns separately;
  - tokens by actual executor/harness and model where measured; unexecuted actors are labelled not executed, not assigned invented runs or costs;
  - wall-clock time;
  - CI minutes;
  - owner items and waits;
  - an estimated money cost, labelled with its price date.

  Costs are summed from actual executor transcripts and CLI/run evidence by holder label, in the private journal. Preserve attribution and identify unavailable measurements; do not infer cross-harness cost or performance equivalence from a Codex-only run. Only the anonymised totals are published.
- **Lens re-score** (G1022 follow-up): recall against defects found later, nit rate, and tokens per review round, compared with G1022's synthetic numbers. Any graph change is proposed as a separate policy goal.
- **Limitations and check results.**

## 8. Defect goals already captured

- G1034 (P1, blocks the run): migration assigns releases.
- G1031: bootstrap's branch-deletion advice must match release branching.
- G1032: bootstrap must work when rulesets and branch protection cannot be read.
- G1033 (P1): false skill-metadata mismatch on Claude installs.
- G1038: merge-based goal sync, path-scoped frozen tests and PR squash.
- G1039: clean-sync carry, sync-focused review and per-stage round budgets.
- G1040: findings across blocks and actionable response/check recurrence errors.

Their reviewed designs define the mechanisms; this goal only installs/adopts and observes them. There are no new engine interfaces, stored formats, capability names or permanent test helpers in this revision.

Defects found during the run follow the same path:
- Each becomes its own goal via add-goal, with the intent check, and is redacted.
- Defects that block the run are fixed and merged, and the CLI installations used by actual run executors are updated and journaled. An unused Claude installation is not a run prerequisite (OD9).
- The owner sets the release of the others when they are captured.

## 9. Risks

- **Production impact:** low-risk Release 1 content, separate approvals for each deploying step, and release-tip/production-target/candidate binding. A moved target can change the resulting code even when the release head and mergeability are unchanged; Phase 7 stops for restaging and renewed approvals when the relevant proof changes.
- **Naming the app in public text:** the convention in §6, plus A15.
- **Owner load and CI throughput:** both measured, not worked around.
- **Mixed engine builds during the run:** every actual actor/node is journaled with its build; required capabilities refuse older writers. Codex-only execution is permitted, and its evidence cannot establish untested Claude behavior or cross-harness equivalence (OD9).
- **An accidental return to rebase mode:** never remove `merge_sync` while an open work branch contains sync merges. G1038's rollback restriction applies; any abort preserves the new engine and branches.
- **Adoption gaps:** A18 checks what was actually installed, not just what the templates happen to declare. A19/A20 distinguish observations from cases proved only by dependency tests.
- **A long dependency chain:** this delays G1036's writing.

## 10. Out of scope

- Changing the app's deploy or CI, except through a migrated goal.
- Finishing later-release goals.
- Engine fixes inside this goal's diff.
- Making the engine deploy-aware.
- New rollout, privacy or failure-injection machinery; forcing a real goal to manufacture a desired sync or review result.
- Restoring the old engine.
- Deletions without the owner's word.
- Graph changes from the re-score.
- Publishing anything that identifies the app.

## 11. Response to corrections

- **review_design:1:1:** fixed. The owner judged the scrub machinery intent drift (OD8), so A15 is reduced to a name check on the report and this goal's artifacts.
- **adversary_design:1:1:** fixed. Phase 7 and A10 bind approval evidence to both relevant tips and the resulting promotion candidate tree/artifact, re-evaluate immediately before irreversible promotion and after waits/retries, and stop for restaging plus renewed separate owner approvals when relevant proof changes or equality is unproven. External staging freshness is explicitly a root procedure, not an engine guarantee.

- **implement:2:1:** fixed. Recorded the owner's exact scope override as OD9, removed mandatory dual-harness installation/participation from Outcome, Install, Execute, A1/A18 and costs/reporting, and retained actual-actor/build evidence with explicit non-execution and no untested equivalence claims. The freeze is confirmed; all private-repository and deployment proof/approval boundaries remain.


## 12. Dependency reconciliation for attempt 5

- **G1024 revision 4:** provenance is a separate `.zzzops/TEMPLATE.json`; its history-backed comparison and tombstones prevent older-plugin ping-pong. This run uses its bootstrap/update workflow, with no goal edits to policy files.
- **G1025 revision 3 / G1027 revision 2:** the branching capability is `release_lines`; line sync/finish and recorded-tip deploy boundaries are unchanged. G1038 supersedes the earlier goal-branch rebase choice only where `merge_sync` is required.
- **G1026 revision 7 / G1028 revision 2:** human decisions come from goal history; carried stale findings still require responses. There is no `owner_answers` rollout.
- **G1031 revision 2:** head auto-delete is off with branching, primarily to retain finished line branches; a read failure does not fail validation.
- **G1034:** migration confirms releases/priority/dependencies in one triage proposal and creates dependencies first. Later-release holds remain this run's choice under OD1.
- **G1038 revision 3 / G1039 revision 3:** explicit adoption enables merge-mode carry and per-stage budgets; the workflow base edge makes implementation review repeat after sync. Hand resolution can conservatively stale a node and is never treated as proof of a clean carry.
- **G1040 revision 2:** `blocked_findings` must be paired with revised prompt step 4. Its stored output and finding liveness stay inside that dependency; this run gathers evidence without changing the rules.

No new owner choice is introduced: these are the already reviewed dependency contracts applied to the same approved dogfood plan. The existing separate deployment approvals and private journal remain authoritative for the real run.


## 13. Attempt 6 correction evidence

At read_dev, `engine/ops/lines.py:finish` uses the recorded sync tip, checks whether the line moved and tests production mergeability; `merge_pr` matches the PR head. These checks do not bind external staging acceptance to the production target tip or resulting merge tree. The independent synthetic proof records an unchanged release tip and conflict-free merge with a resulting tree different from staging. This revision corrects only the runbook and A10 evidence; it preserves OD1–OD8 verbatim and introduces no new engine interface, deployment mechanism or privacy checklist. Rejected: treating an unchanged line head or successful CI/mergeability as proof of staged production content.


## 14. Attempt 7 scope reconciliation

The owner's explicit override in OD9 controls over the earlier dual-harness spec text. This run dogfoods the CLI through Codex; it does not test or certify model/harness equivalence. A second clone remains available for the existing lease-reclaim scenario, without requiring a different model or harness. The accepted protocol must be refreshed through test_design to match A1/A18 and this attribution scope; implementation must not edit its frozen acceptance file directly. No real-run success, app mutation or deployment is claimed by this design update.
