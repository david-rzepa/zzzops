# G1037 design: dogfood Release 1 on a private web app, from migration to a finished release

Attempt 2. Written against read_dev 8d8437a. It replaces G1003 and G1035, and answers review_design:1:1 (§11).

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
- **OD7:** "Anonymised entirely", and later "Purge, keep plan private". Nothing in this repository identifies the app (§6).

## 3. The graph: what each node means

| Node | Meaning for G1037 | Who |
|---|---|---|
| `design` | This plan (public, generic) and the private detailed plan. | worker |
| `review_design` (+ `adversary_design`, `filter_design`) | Is the plan feasible? Are deploy and data safe? Is the redaction rule enforced? Which owner questions are left open (G1026)? | workers |
| `approve_design` | The owner approves. This is the authority to write to the app's repository within the plan, and nothing more: it grants no deploy authority (OD6). | owner |
| `base` | Unchanged. It runs once every dependency has merged, so the build under test is the complete Release 1 engine. | op |
| `test_design` | Commits the acceptance checks (§5) into the report skeleton before the run starts. | worker |
| `review_tests` | Do the checks cover the spec and OD1 to OD7? Can each one be falsified? | worker |
| `implement` | Executes the run (§4) and commits the anonymised report and data at milestones. **The root holds this lease** and renews it while it drives the app. A lapse is reclaimed with `start --reclaim`. | root |
| `run_tests` | Unchanged: the suite runs on the report commit. | op |
| `review_impl` | Re-runs the checks' read-only commands, recomputes the tables from the data file, runs the redaction scan, and confirms that every listed defect goal exists. | worker |
| `integrate`, `approve_merge`, `merge` | Unchanged: a docs PR, approved by the owner. | op / owner / op |

**Rejected alternatives:**
- **Child goals per phase.** Each would cost a full graph, and the phases cannot be reviewed apart.
- **A custom process graph.** It needs a policy change, which pauses all work.
- **Running the work with no lease.** The run would be invisible to other roots.

## 4. Phases

1. **Preconditions.**
   - Dependencies merged: the Release 1 engine goals, plus G1029 and G1031 to G1034.
   - The freeze is in effect (OD5).
   - Two fresh clones, one per harness. The owner's own checkout is only read.
   - The private journal is ready: plan, holder map, cost exports, deny patterns.
   - **The deny list is clean on what already exists.** `git grep -i -E -f <deny list>` over the integration tip prints nothing, and so does the scan of the existing defect goals and of this goal's and G1036's goal branches. This is re-checked whenever the list changes (§6).
   - Any one-time branch housekeeping the app needs before the engine owns refs is listed in the private plan. It is approved with this design, and it stops if it would change any file.
2. **Install.** One dev build goes into both harnesses, and `validate` shows no environment mismatch (G1033). Each reinstall during the run is journaled, together with the nodes it ran.
3. **Detect and bootstrap.**
   - `validate` shows the legacy item and the old-policy blocker.
   - The bootstrap skill writes the policy from the templates: the intent in the owner's words, `TEMPLATE.json`, `engine.requires`, the branching block, `required_ci`, verification commands and `first_id`.
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
   - Every human item and every review-raised owner question goes to the owner, and the wait is journaled.
   - Release 1 includes at least one real stacked dependent that restacks after its dependency merges. The pair is the owner's choice and is never invented.
6. **Failure paths.**
   - A review finding that reopens its target, a failing check, an expired lease reclaimed from the second clone, and a policy branch that pauses work.
   - Natural occurrences are preferred. Only safe triggers are used: a deliberately lapsed lease, and a real policy change.
   - Nothing is planted in the owner's repository. A path that does not occur is reported as not observed.
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
| A3 | Bootstrap landed policy from the templates: owner-worded intent, provenance record, required capabilities, branching block, old-policy mapping. |
| A4 | Every counted old issue has a recorded outcome, and every migrated goal has a release. |
| A5 | Every Release 1 goal closed done, or closed with the owner's reason. |
| A6 | Later-release goals are migrated, valid, carry their release and are held. |
| A7 | No hand edits of `zzzops/**` refs beyond REPAIR.md recipes, each of which is journaled. |
| A8 | A stacked dependent ran and restacked after its dependency merged. |
| A9 | One release was cut, synced and finished through the engine, with the owner's finish approval quoted (redacted where needed). |
| A10 | Staging and production each had their own owner approval, and both were bound to the same release tip. |
| A11 | Each failure path was observed, or marked not observed with a reason. |
| A12 | Every defect has its own goal in this repository. |
| A13 | Per-goal costs are reported and can be recomputed from the data file. |
| A14 | The lens re-score is reported. |
| A15 | Nothing public identifies the app. The deny-pattern scan prints nothing over the run's own commits on every zzzops ref it touched, `git log -p <I>..<ref>` with I the integration branch. For goal branches, which share no history with I, that is their whole history. It must also print nothing over the tree of the report and data file, every PR title, body and comment the run created, and every defect goal document. |
| A16 | The owner's checkout and worktrees are unchanged since the start snapshot. |
| A17 | No non-run work touched the app during the freeze. |

The spec's "every migrated goal closes done" is read under OD1 as applying to Release 1 goals. Later-release goals are covered by A6.

No permanent test goes into `.agents/`: the checks are commands with recorded outputs.

## 6. Redaction rule (OD7)

- **Scope:** every public write by the root **or any worker** is redacted, then scanned before it is made. That covers:
  - goal-branch content: summaries, findings, responses, designs, review artifacts and human-item records;
  - owner quotes, with identifying words replaced by `[redacted]` and the replacement noted;
  - commit messages and branch names;
  - PR titles, bodies and comments;
  - defect goal documents, which cite app goals only as "app G<id>".
- **Scan:** `grep -i -E -f <private deny-patterns file>` runs over the exact text before every `submit`, `answer`, `edit`, `new`, PR write and commit in this repository. A hit blocks the write until the text is rewritten.
- **Workers:** every worker brief for this goal and its defect goals carries the rule. Each worker reports its scan result.
- **The patterns file** stays in the private journal and is never committed.
- **App-side writes** in the private repository are not redacted.
- **A15** re-scans the run's own output at the end, scoped as in §5. A hit there is a process defect, purged with the owner's word.
- **List maintenance.** The list uses app-specific compounds and anchored ids, not bare common words. A term that also appears in ordinary engine text or in a generic public spec phrase is narrowed in the list; the public text is not rewritten. Whenever the list changes, the precondition scan (§4, phase 1) is re-run, and any hit is resolved before more writes. A real leak is purged with the owner's word. A false positive is narrowed.

## 7. Report for G1036 (anonymised)

- **Engine versions:** the engine versions used, and which nodes each one ran.
- **Engine changes caused by the run:** defect goals, and whether each merged before the release.
- **What worked and what did not,** per phase.
- **Costs** per goal and per node:
  - agent runs, correction rounds and budget used;
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

Defects found during the run follow the same path:
- Each becomes its own goal via add-goal, with the intent check, and is redacted.
- Defects that block the run are fixed and merged, and both harnesses are reinstalled.
- The owner sets the release of the others when they are captured.

## 9. Risks

- **Production impact:** low-risk Release 1 content, separate approvals for each deploying step, and tip binding.
- **Leaks into public text:** §6 and A15.
- **Owner load and CI throughput:** both measured, not worked around.
- **Mixed engine versions during the run:** every node is journaled with its engine version.
- **A long dependency chain:** this delays G1036's writing.

## 10. Out of scope

- Changing the app's deploy or CI, except through a migrated goal.
- Finishing later-release goals.
- Engine fixes inside this goal's diff.
- Making the engine deploy-aware.
- Restoring the old engine.
- Deletions without the owner's word.
- Graph changes from the re-score.
- Publishing anything that identifies the app.

## 11. Response to corrections

- **review_design:1:1** (A15 and the write gate could not pass, because the work and PR branches carry the integration branch's history and the list matched existing text there): fixed.
  - A15 is scoped to the run's own commits, `git log -p <I>..<ref>` for every ref the run touched, plus goal branches, PR text, defect goals and the report tree (§5).
  - A new precondition requires the integration tip, the existing defect goals and the related goal branches to scan clean before the run, re-checked whenever the list changes (§4 phase 1, §6).
  - The private list has been tuned to app-specific compounds and anchored ids. The generic phrase in G1032's spec was handled by narrowing the list, and G1032 is unchanged.
  - The tuned list now prints nothing on the integration tip and on the goal branches of G1031 to G1034, G1036 and G1037.
  - The private plan carries the same fixes.
