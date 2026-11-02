# G1037 design: dogfood Release 1 on a private web app, from migration to a finished release

Attempt 5: updated for the reviewed G1038/G1039/G1040 dependency designs, against read_dev `de5640d1c5909ea924450aeea6450497a78946f6`. The nine phases, OD1–OD8, private journal and separate deploy approvals remain. This revision adds explicit adoption and observation of merge sync, clean-sync carry and blocked findings (§4, §5), and distinguishes the engine's stack-ready `base` from the root's requirement to wait for all dependencies to merge before the real run. Earlier revisions aligned the spec with OD8 and answered review_design:1:1 (§11). It replaces G1003 and G1035.

The app's identity and every fact specific to it are kept out of this repository (OD7). **The detailed plan is in the root's private journal**: per-phase steps, evidence about the app, triage proposals, and the release mechanics against the app's own deploy flow. This document is the generic plan the reviewers judge, and it is what the whitepaper can cite.

## 1. Outcome

The Release 1 engine is exercised end to end on a real repository that has a pre-reset installation:
- install the dev build in both harnesses;
- detect the legacy state and migrate it;
- bootstrap the new policy with the owner's intent;
- run the migrated goals through the default graph;
- cut, sync and finish one release through the engine.

Defects become goals here. An anonymised report with costs and a lens re-score is committed here for the whitepaper (G1036).

## 2. Owner decisions (2026-11-01, relayed by the coordinator)

Identifying words are replaced by `[redacted]`. Everything else is verbatim.

- **OD1:** "All goals are in scope - as part of the migration releases should be assigned". Every open old goal is migrated and gets a release. The migrate skill does not assign releases today, so this is captured as G1034, which G1037 depends on.
- **OD2:** "The only reason I want dogfood before whitepaper is in case we need to make changes". G1036 (the whitepaper) can be designed once this design is approved. Its writing waits for G1037's merge, through its `depends_on: [1000, 1017, 1037]`.
- **OD3:** "still use release branches, when ready to deploy, merge to [redacted] for staging, then merge to [redacted]. zzzops should be CI/release flow agnostic". G1025's release lines are used as designed. The app's own promotion steps stay outside the engine.
- **OD4:** "Push per migrated goal". Local-only commits that belong to a migrated goal are pushed to that goal's work branch. The owner's uncommitted state is out of scope.
- **OD5:** "Freeze, hotfixes via engine". No other work happens on the app during the run. Urgent fixes become engine hotfix goals.
- **OD6:** "Both real, approved separately". Each deploying step needs its own owner approval, at a time the owner names.
- **OD7:** "Anonymised entirely", and later "Purge, keep plan private". Nothing in this repository names the app (§6).
- **OD8:** "I don't think we need to worry too much about scrubbing secrets, that's intent drift in my opinion..". The scrub machinery is dropped. The convention stays (§6).

## 3. The graph: what each node means

| Node | Meaning for G1037 | Who |
|---|---|---|
| `design` | This plan (public, generic) and the private detailed plan. | worker |
| `review_design` (+ `adversary_design`, `filter_design`) | Is the plan feasible? Are deploy and data safe? Is the naming convention kept? Which owner questions are left open (G1026)? | workers |
| `approve_design` | The owner approves. This is the authority to write to the app's repository within the plan, and nothing more: it grants no deploy authority (OD6). | owner |
| `base` | Unchanged engine operation, which can run on integrated dependency heads before they merge. The root does not begin the real run until all dependencies have merged, so the build under test contains them all. | op |
| `test_design` | Commits the acceptance checks (§5) into the report skeleton before the run starts. | worker |
| `review_tests` | Do the checks cover the spec and OD1 to OD8? Can each one be falsified? | worker |
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
   - The freeze is in effect (OD5).
   - Two fresh clones, one per harness. The owner's own checkout is only read.
   - The private journal is ready: plan, holder map and cost exports.
   - Any one-time branch housekeeping the app needs before the engine owns refs is listed in the private plan. It is approved with this design, and it stops if it would change any file.
2. **Install.** One build from the merged dev commit goes into both harnesses, and `validate` shows no environment mismatch (G1033). Record the engine's `build` and `capabilities` (G1027), rather than treating `0.0.0-dev` as a numbered engine version. Each reinstall during the run is journaled, together with the nodes it ran. Both harnesses must actually participate; an unavailable harness delays that observation rather than becoming an assumed pass. Existing checkouts and other active host sessions are preserved.
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
   - Drive the app's `next` loop. Workers are routed across both harnesses, and at least one session has a Codex root.
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
   - The app's own staging step happens **outside the engine**, on the exact release tip, with its own owner approval.
   - The owner approves `approve_finish` (production) only after staging is accepted. The bound tip must equal the staged tip. A tip that moves makes both stale.
   - `finish` merges into the production branch and back-merges.
   - The engine stays CI- and deploy-agnostic. **No G1025 change is needed.** If the outside step proves error-prone, a generic defect is captured.
8. **Abort.** The new engine stays. Nothing is deleted. The report records the cause.
9. **Report.** The anonymised write-up and data are committed (§7).

## 5. Acceptance checks (written by `test_design`, re-run by `review_impl`)

| Id | Check |
|---|---|
| A1 | Both harnesses ran the same dev build at the start, with no environment mismatch. |
| A2 | Legacy detection showed the migrate item before migration and nothing after it. |
| A3 | Bootstrap landed the selected consolidated graph/prompts, owner-worded intent, G1024 provenance record, required capabilities, branching block and old-policy mapping. The record acknowledges kept/declined defaults. |
| A4 | Every counted old issue has a recorded outcome, and every migrated goal has a release. |
| A5 | Every Release 1 goal closed done, or closed with the owner's reason. |
| A6 | Later-release goals are migrated, valid, carry their release and are held. |
| A7 | No hand edits of `zzzops/**` refs beyond REPAIR.md recipes, each of which is journaled. |
| A8 | A real stacked dependent ran and synced after its dependency merged. The sync follows merge mode, preserves forward work history, and integrate produces the tests/implementation PR parts on the synced base with the tested code tree. |
| A9 | One release was cut, synced and finished through the engine, with the owner's finish approval quoted (redacted where needed). |
| A10 | Staging and production each had their own owner approval, and both were bound to the same release tip. |
| A11 | Each failure path was observed, or marked not observed with a reason. |
| A12 | Every defect has its own goal in this repository. |
| A13 | Per-goal costs are reported and can be recomputed from the data file. |
| A14 | The lens re-score is reported. |
| A15 | The report and this goal's public artifacts do not name the app. Checked by a quick grep for the app's name and repository slug before the report is published. |
| A16 | The owner's checkout and worktrees are unchanged since the start snapshot. |
| A17 | No non-run work touched the app during the freeze. |
| A18 | The bootstrap's actual policy requires `merge_sync`, `round_budget` and `blocked_findings`, includes the revised design step 4 and review_impl base edge, and both engines declare the required capabilities. With branching, head auto-delete is off as owner-confirmed or observed. |
| A19 | On naturally occurring syncs, record whether each node was carried or staled; for a clean carry, its change-bound reviews stay current, while verification and review_impl re-run on the new tree/base. Report not observed if no eligible clean sync occurs; do not invent work or force carry. |
| A20 | On naturally occurring owner-question blocks/check failures, record whether live findings survived the block, answered owner questions avoided a second block, refusals explained unmatched responses, and distinct check failures started a new round. Mark each unobserved case honestly. |

The spec's "every migrated goal closes done" is read under OD1 as applying to Release 1 goals. Later-release goals are covered by A6.

No permanent test goes into `.agents/`: the checks are commands with recorded outputs.

## 6. Naming convention (OD7, OD8)

- The app is never named in this repository. Public artifacts (designs, reviews, findings, defect goals, PR text, the report) describe it generically. Owner quotes are verbatim, with identifying words replaced by `[redacted]`.
- The detailed plan and every app-specific fact stay in the root's private journal.
- Before the report is published, one quick grep checks it and this goal's public artifacts for the app's name and repository slug (A15). There is no per-write gate, history-wide scan or deny list (OD8).

## 7. Report for G1036 (anonymised)

- **Engine builds:** each `build` id and required/available capabilities, and which nodes each build ran.
- **Engine changes caused by the run:** defect goals, and whether each merged before the release.
- **What worked and what did not,** per phase.
- **Costs** per goal and per node:
  - agent runs, new material-finding rounds and budget used by stage; sync-only reruns separately;
  - tokens by harness and model;
  - wall-clock time;
  - CI minutes;
  - owner items and waits;
  - an estimated money cost, labelled with its price date.

  Costs are summed from the harness transcripts by holder label, in the private journal. Only the totals are published.
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
- Defects that block the run are fixed and merged, and both harnesses are reinstalled.
- The owner sets the release of the others when they are captured.

## 9. Risks

- **Production impact:** low-risk Release 1 content, separate approvals for each deploying step, and tip binding.
- **Naming the app in public text:** the convention in §6, plus A15.
- **Owner load and CI throughput:** both measured, not worked around.
- **Mixed engine builds during the run:** every node is journaled with its build; required capabilities refuse older writers.
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


## 12. Dependency reconciliation for attempt 5

- **G1024 revision 4:** provenance is a separate `.zzzops/TEMPLATE.json`; its history-backed comparison and tombstones prevent older-plugin ping-pong. This run uses its bootstrap/update workflow, with no goal edits to policy files.
- **G1025 revision 3 / G1027 revision 2:** the branching capability is `release_lines`; line sync/finish and recorded-tip deploy boundaries are unchanged. G1038 supersedes the earlier goal-branch rebase choice only where `merge_sync` is required.
- **G1026 revision 7 / G1028 revision 2:** human decisions come from goal history; carried stale findings still require responses. There is no `owner_answers` rollout.
- **G1031 revision 2:** head auto-delete is off with branching, primarily to retain finished line branches; a read failure does not fail validation.
- **G1034:** migration confirms releases/priority/dependencies in one triage proposal and creates dependencies first. Later-release holds remain this run's choice under OD1.
- **G1038 revision 3 / G1039 revision 3:** explicit adoption enables merge-mode carry and per-stage budgets; the workflow base edge makes implementation review repeat after sync. Hand resolution can conservatively stale a node and is never treated as proof of a clean carry.
- **G1040 revision 2:** `blocked_findings` must be paired with revised prompt step 4. Its stored output and finding liveness stay inside that dependency; this run gathers evidence without changing the rules.

No new owner choice is introduced: these are the already reviewed dependency contracts applied to the same approved dogfood plan. The existing separate deployment approvals and private journal remain authoritative for the real run.
