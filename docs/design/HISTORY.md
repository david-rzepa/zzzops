# ZzzOps engine design: history

How the engine contract in this folder came to be. [DESIGN.md](DESIGN.md) and [SPEC.md](SPEC.md) are revision 6.3, approved on 2026-10-31 and implemented in #740; §4 lists every amendment made in the repository since then. The review reports, audit reports and review passes that produced revision 6.3 are not in the repository: §2 summarises each one, and §3 indexes every amendment id that DESIGN and SPEC cite.

## 1. Revisions

This is the revision history that stood at the top of DESIGN.md until revision 6.3. Review reports are named by tag; §2 lists every tag.

- **Revision 1:** design from the audit.
- **Revision 2 (human review):**
  - D1 approved: goal state lives on `zzzops/state`.
  - Migration is documentation only.
  - Leases are empty commits, kept off the goal branch (D7 approved).
  - New D10: goal ids.
- **Revision 3 (2026-10-30), two new human requirements and three reviews:**
  - **Discovery runs ahead of delivery.** Discovery phases, including human gates, are scheduled across all goals before implementation work.
  - **Capture flows into discovery.** `goal new` returns the new goal's discovery actions, so the conversation that added the goal goes straight into design.
  - **Reviews applied:** a self-review (review R0), an independent performance and Git review with experiments run in scratch repositories (review R1), and an independent repairability and simplicity review covering 48 failure scenarios (review R2).
  - **DESIGN §11 lists every change and its source.**
- **Revision 4 (2026-10-30), human decisions:**
  - D3, D4, D5, D6 and D10 approved.
  - D9 changed: feedback is dropped too (to be rebuilt as transcript-based).
  - D11 replaced: an open policy change is detected by a branch prefix, `zzzops/policy/*`, not a GitHub PR query. Normal work now makes **no GitHub API calls**; only the `integrate`, `ci` and `merge` operations use GitHub (revision 5 folds `ci` into `integrate`).
- **Revision 5 (2026-10-30), human decisions and a second review pass.** The decision record is the REV5 decision record (§3); the pinned detail is in the new companion SPEC.md.
  - **A1, default graph:** 12 nodes. `prepare` is removed (the first artifact submit creates the work branch, and discovery needs no worktree). `ci` is folded into `integrate`. `review_tests` is kept, and there is no decomposition node (D12).
  - **A2, policy keeps progressive disclosure:** POLICY.json stays separate, with per-section instructions selected per node (D13).
  - **A3, one branch per goal:** `zzzops/state` is replaced by `zzzops/goal/g<id>`, so writes to different goals never contend (D1 modified; D10's allocation follows).
  - **A4, two code identities:** checkpoints carry `tree` and `change`. Checks bind `tree`; reviews and approvals bind `change`. Settled choice S7 is replaced (D14).
  - **B, C, D:** the correctness fixes (B1–B29), the 11-verb CLI (C) and the skill and output fixes (D1–D9) from the second review pass (reviews R3–R9) are applied. DESIGN §11 maps each change to its source.
- **Revision 6 (2026-10-31), human decisions and a third review pass.** The decision record is the REV6 decision record (§3). The third pass had six lenses: consistency, model checking, harness and platform, generality and bootstrap, human economics, and evolution.
  - **A1, stacked delivery (D5 reversed):** a dependent no longer waits for its dependency's merge. It stacks on the dependency's PR branch, with GitHub stacked PRs (DESIGN §3.16).
  - **A2–A4:** `approve_merge` stays required; `next` gains `wake_at`; `design` runs as a worker.
  - **A5, speculative guards cut:** the self-test, the verb-scoped diff check, the clock-skew refusal, the edit confirmation threshold, orphan pruning in writes, the work-in-progress push in `renew`, and the eight dependency miss reasons.
  - **A6, carry-forward:** a clean `base` replay carries the checkpoint records forward, so a restack runs no administrative agent phase.
  - **B–E:** correctness, platform, bootstrap, evolution and human-experience fixes. DESIGN §11 maps each change to its source.
- **Revision 6.1 (2026-10-31), a fourth review pass.** The amendments are REV6 §H, from a cross-check of REV6, DESIGN and SPEC (`x`) and a model check of the SPEC rules (`m4`).
  - **Stacking waits for the chain root's CI:** a dependent stacks once its dependency's `integrate` is current and ok, which for a PR into the integration branch means its required checks passed (DESIGN §3.16).
  - **Carry-forward is per node,** from the replay's own commit map, also after a hand-resolved conflict.
  - **Dependents are retargeted only after a merge is observed;** a closed `done` goal means delivered; the correction budget counts re-runs; `wake_at` has no release-gate time; and smaller correctness and wording fixes. DESIGN §11 maps each change to its source.
- **Revision 6.2 (2026-10-31), a final cross-check.** The amendments are REV6 H23–H25, from a cross-check of revision 6.1 against DESIGN and SPEC (`x2`).
  - **Retiring a stack** retargets the goal's PR and closes the stack PR before the stack branch is deleted.
  - **The op-finding cap** counts a recurring finding only while the op's inputs are unchanged, and an op target answers a finding by a later attempt, with no clock comparison.
  - **After a hand-resolved conflict,** a racing review commit is re-applied, and the suggested checkpoint follows the replay's positions; plus smaller wording fixes and two stated limitations. DESIGN §11 maps each change to its source.
- **Revision 6.3 (2026-10-31), a model check of revision 6.2.** The amendments are REV6 H26–H30 (`m5`). No critical or high finding.
  - **A re-run that commits nothing keeps its checkpoint** (a dispute, a `fixed:` answer without a change), instead of defaulting to `HEAD`, which may hold a later node's code.
  - Smaller fixes: `replay_pos` declared in the default graph, retargeting wording, a crash-loop option that the budget would refuse, and the suggested checkpoint computed at submit.

**Audit revisions:**
- **Pinned baseline:** `21e5021f9dd384c828e2a4eb5a32bc96a68f24a1`.
- **Supplemental #566 pin:** `692b7f973308e09384240806e11df3876740049b`.
- **Both pins are contained in `origin/dev` = `64d5196f6f4f91e4d7b5ca773cd6c821c694c0ea`,** the #739 integration. The owner confirmed that all unintegrated work was merged into dev.
- **Citations** in the audit and review reports are paths and lines in `64d5196`.
- **Implementation starting point:** `origin/dev @ 64d5196`. No reconciliation of the pins is needed (audit report G, §F1).

## 2. Review sources

The reports themselves are not in the repository. They were working material, and every amendment they produced is folded into revision 6.3 or listed in §3. The documents cite them by these tags.

**First pass (revision 2 → 3)**
- **R0, self-review:** the designer's own pass over revision 2. It found six correctness bugs, including the work branch being rewritten by integrate, dependencies serializing design, and an impure frontier.
- **R1, performance and Git:** IO scaling and Git mechanics, with experiments in scratch repositories. It found that the `code_tree` recipe silently returned the unfiltered tree, plus fingerprint and findings issues.
- **R2, repairability and simplicity:** 48 failure scenarios checked for repair with the verbs, goal-JSON edits and plain Git. The core held; the weak spots were dead ends from disputes, human rejection and undefined op outcomes.

**Second pass (revision 4 → 5)**
- **R3, prototype:** a throwaway build of the core (about 1,600 lines) fuzzed with concurrent agents. It reported where the text forced a guess, for example missing findings on task cards and the integrate head value.
- **R4, prior art:** the core semantics compared with proven systems. They matched closely; it proposed lease timeouts in the lease message, an interdiff on re-review and a crash-loop cap.
- **R5, implementability:** read as the model that must build the engine unaided. It found five places where a literal build deadlocks: circular findings liveness, no "local ahead" sync row, `--lease` breaking after renew, a non-snapshot fetch, and more.
- **R6, deletion:** argued for deleting each remaining concept. About a quarter was duplication, one-value knobs or speculative cases; the `stuck` item fired on every legitimate wait.
- **R7, blast radius:** how far honest mistakes spread and how they are contained. It proposed small guards (held-goal leases are not orphans, settings ranges, the edit fence).
- **R8, walkthrough (Sonnet):** an agent ran a scripted multi-session journey with only the skills and references. It found oversized task cards and unclear wait-versus-stop guidance.
- **R9, walkthrough (Haiku):** the same journey with a smaller model. It found gaps in capture defaults, approval wording and command text.

**Third pass (revision 5 → 6), cited by lens**
- **cons, consistency:** DESIGN against SPEC against the REV5 decision record. Largely consistent; the worked examples had the serious problems.
- **model, model-check:** an exhaustive model of SPEC §4.8–§4.19 and the ops. It found rebase-conflict, test-freeze and budget defects (`model:C1`, `model:H1`, `model:H2`).
- **harn, harness-platform:** Codex and Claude Code as shipped, on Linux, macOS and Windows. It led to the harness requirements, verb-relative `argv`, unique claims and process handling.
- **gen, generality:** other repositories and bootstrap. The Git-only core travels well; bootstrap became a checklist over `validate`, and merge method and GitHub blocks were made explicit.
- **econ, human-economics:** the human's week and the token cost. A phase is cheap, but delivery stalled on waits and merge gates; it led to stacked delivery, `wake_at` and compact items.
- **evo, evolution:** months of use, with 5,000 goals measured. It led to engine and fingerprint versions, the impact preview, context edges and growth limits.

**Fourth pass and later**
- **x, cross-check (revision 6):** the REV6 decision record against DESIGN and SPEC. It found 1 critical, 3 high, 11 medium and 14 low findings, which led to H1–H22.
- **m4, model check (revision 6):** the review-3 model re-implemented at full stacking detail. Its findings F1–F10 fed H1–H22.
- **x2, cross-check (revision 6.1):** REV6 §H against DESIGN and SPEC. It found 0 critical, 0 high, 5 medium and 10 low findings, which led to H23–H25.
- **m5, model check (revision 6.2):** the model updated to H1–H25. It found N1–N5 (no critical or high), which led to H26–H30. A re-run after H26 found no violations.

**Pass 2 support material**
- **prototype:** the R3 prototype code and fuzz runs, useful for Git command shapes only.
- **walkthrough:** the R8/R9 scenario pack and logs, output-shape fixtures from older revisions.

**Audit (revision 1 input), read-only reports at `64d5196`**
- **audit A, goal persistence:** the comment-envelope goal store and its three storage generations.
- **audit B, engine:** graph definition, frontier, phase execution, findings and graph migration; two different default DAGs shipped.
- **audit C, trust and administration:** identity, approvals, allocation and evidence; the identity layer was a string comparison, and each phase cost three durable GitHub transactions.
- **audit D, Git and dependencies:** worktrees, checkpoints, restacks, publication and integration; worktree preparation was a side effect of `start`.
- **audit E, policy:** policy location, invalidation, model routing and packaging.
- **audit F, CLI and cost:** the CLI boundary, progressive disclosure and provider round trips.
- **audit G, revisions and work:** revision reconciliation, the inventory of existing work, and test-suite shape.

## 3. Amendment index

Each line gives an amendment id, its title and one clause. The full decision records are not in the repository.

### REV5 decision record

The revision 5 change list (2026-10-30), from the human's decisions and the second review pass.

- **A1. Default graph: 12 nodes.** `prepare` removed, `ci` folded into `integrate`, `review_tests` kept, no decomposition node.
- **A2. Policy keeps progressive disclosure.** POLICY.json stays separate, with per-section instructions selected per node.
- **A3. One branch per goal.** `zzzops/goal/g<id>` replaces `zzzops/state`, so writes to different goals never contend.
- **A4. Two code identities.** Checkpoints carry `tree` (bound by checks) and `change` (bound by reviews and approvals).
- **B1.** The lease handle is `--attempt N`, which survives renew, not the sha.
- **B2.** The lease message records `Timeout:` minutes, so policy edits never change a live lease.
- **B3.** A held goal's leases are not orphans; `hold` lets running phases finish.
- **B4.** Findings liveness is computed in a first pass from recorded outputs, before the frontier pass.
- **B5.** A ready node's task card carries every live finding targeting it, and its submit must answer each one.
- **B6.** `ok` replaces `require`: every record carries `ok: true|false`.
- **B7.** The stuck rule is portfolio-aware.
- **B8.** `node_def_fp` uses an allowlist of semantic fields.
- **B9.** A dependent design consumes the dependency's design gated on its approval.
- **B10.** Test freeze: the frozen paths are those changed by `test_design`'s own commits.
- **B11.** `workspace` is a node-level flag for any kind, with one workspace lease per goal.
- **B12.** The sync rule gains "local ahead of remote → push", and patch-id equivalence.
- **B13.** `integrate` uses the PR-head value from this invocation's fetch, never the recorded one.
- **B14.** `merge`'s atomic push records the merge and closes the goal, deleting no branches.
- **B15.** Generic close: when every terminal node is current and ok, the same push closes the goal.
- **B16.** Ops are parameterized by their inputs, never by node names.
- **B17.** CI handling lives inside `integrate`.
- **B18.** Agents can submit a blocked outcome with `--blocked F`.
- **B19.** Human answers are fenced by `--fp <input_fp>`.
- **B20.** `edit` requires `--base <goal commit>` or prints the impact preview and requires `--yes`.
- **B21.** Correction budget: re-runs beyond `3 × agent nodes` raise a human item.
- **B22.** Crash-loop cap: a lease attempt at least three past the record attempt raises a human item.
- **B23.** Engine version: `settings.engine.min` and an `Engine:` trailer on goal commits.
- **B24.** Verb-scoped diff check before pushing (cut again in REV6 A5).
- **B25.** Settings ranges are validated.
- **B26.** Clock-skew refusal in `start` (cut again in REV6 A5).
- **B27.** Environment checks: git ≥ 2.41 and `gh` for the ops that need it.
- **B28.** Re-review task cards include the interdiff and the previous findings.
- **B29.** Task cards are at most 4 KB; long inputs are referenced by blob with a summary.
- **C. Verbs.** The 11-verb CLI (`next`, `show`, `new`, `start`, `submit`, `renew`, `abandon`, `answer`, `reopen`, `edit`, `validate`), with the older admin verbs folded in.
- **D1.** Wait versus stop: report what is waiting and when, then stop.
- **D2.** Scope: pass `--goal` when the user scopes work; `next` echoes the filter and `also_pending`.
- **D3.** A human "not yet" records nothing.
- **D4.** Approvals record what was approved in the agent's own words.
- **D5.** Dispatch: the root does root nodes, and workers do worker and review nodes.
- **D6.** The implement task card includes `test_design.commands`.
- **D7.** Renew guidance is one number: "renew every N minutes (timeout T)".
- **D8.** `new`'s required fields and defaults are documented.
- **D9.** The policy-branch blocker message says how to resolve it.
- **E. SPEC.md.** The new companion document holding schemas, pseudocode and the CLI table.

### REV6 decision record

The revision 6 change list (2026-10-31), from the human's decisions and the third review pass, with §H added by the later passes.

- **A1. Stacked delivery (reverses D5).** A dependent stacks on its dependency's PR branch instead of waiting for the merge.
- **A2. `approve_merge` stays required.** The human merge gate is kept.
- **A3. `wake_at` only.** `next` reports the earliest time worth waking.
- **A4. `design` runs as a worker.** It no longer runs in the root conversation.
- **A5. Cut the speculative guards.** Self-test, verb-scoped diff check, clock-skew refusal, edit threshold, orphan pruning, WIP push in `renew`, dependency miss reasons.
- **A6. Carry-forward.** A clean `base` replay carries checkpoint records forward.
- **B1.** Hand-resolved rebase conflicts record `op_state {work, onto}` (`model:C1`).
- **B2.** The `change` recipe uses `-O/dev/null` and raises on a non-zero `git diff`.
- **B3.** Engine-written dates use `@<seconds> +0000`.
- **B4.** `responses` are kept out of the subject fingerprint.
- **B5.** Test freeze uses a `frozen` path list and a `Work:` lease trailer.
- **B6.** The checkpoint defaults to `suggested_checkpoint` when the card has one.
- **B7.** No attempt reuse: `abandon` pushes an expired renewal (`Timeout: 0`) and never deletes a lease.
- **B8.** Unique claims carry a `Nonce:` trailer.
- **B9.** Unknown lease trailers are ignored; an unparsable lease is excluded and reported.
- **B10.** A live lease renders `running` before input checks.
- **B11.** Escalation rule: recurrence is read from the target's recorded `responses`.
- **B12.** Op-carried disputes offer uphold, skip or cancel, never waive.
- **B13.** Repeat cap: three Blocked records with the same reason give `needs_human (crash_loop)`.
- **B14.** Flaky CI: `reopen G X` also waives X's own open findings.
- **B15.** Reopen of a stale node is defined (`model:M5`).
- **B16.** The correction budget counts corrections only (revised by H12).
- **B17.** Dependencies: a held dependency is a named wait, not stuck.
- **B18.** Skips: `base` consumes `review_design.summary`; skip keys that name terminal nodes are refused.
- **B19.** The first `base` run always rebases onto the current integration branch.
- **B20.** The answer fence covers `claimed_at` (`model:L2`, `model:L4`).
- **B21.** Graph validation: every node reaches a terminal.
- **B22.** Post-merge correction is defined (`evo:M1`).
- **B23.** Text size limits (`evo:M8`).
- **B24.** Small fixes from the consistency and model reports.
- **C1.** Harness requirements and documented Codex configurations.
- **C2.** Commands: verb-relative `argv`, with the prefix rendered at print time.
- **C3.** Process handling, keeping the git ≥ 2.41 floor.
- **C4.** Bootstrap becomes a checklist over `validate` and the shipped templates.
- **C5.** Push refusals give `push_refused`.
- **C6.** Merge method and GitHub blocks: `settings.merge.method` and `BLOCKED` handling.
- **C7.** `settings.integration_branch` is checked against `I` on every verb.
- **C8.** Shallow clones are refused; hooks stay on work and PR pushes.
- **C9.** A policy branch already contained in `I` does not block.
- **C10.** Documentation-only lows become stated limitations or setup notes.
- **C11.** Model tiers list Claude model ids beside GPT ids.
- **D1.** Impact preview: `validate --policy --dir D` prints `impact`.
- **D2.** Context edges, with the "if it still holds, resubmit it" hint.
- **D3.** Engine versions (`evo:H4` (a)–(e)).
- **D4.** A record's fingerprint is compared only in the version it carries.
- **D5.** An engine reads every goal schema it has shipped and writes the newest.
- **D6.** Renames are a REPAIR/MIGRATING recipe.
- **D7.** `review_path` is deleted; `.zzzops/reviews` is a constant.
- **D8.** Worktrees (`evo:M9`).
- **D9.** Growth: a `State:` trailer, and reading only open goals and their dependencies.
- **E1.** Since-T view: an `Outcome:` line and `last_change`.
- **E2.** Decision facts: `implement.summary`, and checkpoint inputs shown as a diffstat plus a diff command.
- **E3.** Dependents' discovery gates on the dependency's `review_design.summary`.
- **E4.** Compact items.
- **E5.** Lows: check `gh pr view` before presenting `approve_merge`.
- **H1.** Fence fingerprint: a `running` state also carries `fp`.
- **H2.** Stacking waits for the root dependency's CI.
- **H3.** Commit map and per-node carry-forward (`replay_map`).
- **H4.** A restack racing a review commit re-runs the replay.
- **H5.** `submit` and `renew` on an abandoned lease refuse with `superseded`.
- **H6.** Carry-forward drops `responses` whose findings are no longer live.
- **H7.** Closed `done` means delivered.
- **H8.** Dependents are retargeted only after a merge is observed.
- **H9.** `base` resets the local branch to the stack base it creates.
- **H10.** A conflicting PR into `I` gives a `conflict` finding on `base`.
- **H11.** The repeat cap ignores the agent's wording.
- **H12.** The budget counts re-runs, not only corrections.
- **H13.** Stack set minimality: drop members that are ancestors of others.
- **H14.** `base` makes its `gh` calls only after its push succeeds.
- **H15.** An op's Blocked record carries the previous findings unchanged and inert.
- **H16.** A policy branch landed by squash counts as landed.
- **H17.** `wake_at` is the earliest `retry_after` or lease expiry; release gates carry no time.
- **H18.** One fetch for `start G base`, including the dependencies' PR refspecs.
- **H19.** `base` fingerprints `pr.head`, not the whole PR object.
- **H20.** The interdiff after a restack uses `git range-diff`, or is omitted when `change` is identical.
- **H21.** Wording and slips from the fourth pass.
- **H22.** Op targets answer findings by re-running.
- **H23.** Final cross-check fixes (`x2:M1`, `x2:M2`, `x2:M4`, `x2:M5`).
- **H24.** An op-target finding records `target_attempt`.
- **H25.** Every `x2` low adopted, with one stated limitation.
- **H26.** A re-run that commits nothing keeps its checkpoint (`m5:N1`).
- **H27.** `replay_pos` is declared in `git.base`'s outputs.
- **H28.** Retargeting wording.
- **H29.** The crash-loop item under an exhausted budget prints the budget refusal.
- **H30.** The suggested checkpoint is computed at submit, not from the card.

## 4. Amendments after approval

One row per change to the contract after revision 6.3 was approved, in merge order. The documents keep the label "revision 6.3" plus this log; no new revision number is used. A goal that changes the contract edits DESIGN and SPEC in its own PR and adds its row here ([README](README.md#how-to-amend)).

| Change | PR | Sections | Summary |
|---|---|---|---|
| `--policy-ref` | #742 | SPEC §6, §3.15, §3.16; DESIGN §3.15 | A read-only policy preview for `next`, `show` and `validate`; `validate` adds the impact. |
| G1014 | #743 | SPEC §3.16, §4.12, §4.18 | `edit` lists the live leases whose inputs it changes; `renew` reports `inputs_changed` with restart commands. |
| G1018 | #744 | SPEC §3.14, §4.20 | Checkpoint inputs selected by `change` or `tree` show the full checkpoint; the card's shrink steps; approve-item checkpoint context. |
| G1001 | #745 | SPEC §3.9, §3.13, §3.16, §4.17; DESIGN §3.15, §10 | `new` is idempotent through `request_key` and the `Request-Key:` trailer. |
| G1015 | #746 | SPEC §1.8, §2.3, §3.2, §3.15, §3.16, §3.17, §4.3; DESIGN §3.15, §5 (R11), §10 | Pre-reset state is disclosed as the non-blocking `legacy` item; `legacy_policy`; `settings.legacy.ignore`. |
| G1016 | #747 | SPEC §3.10, §3.14, §3.16, §4.12, §4.14, §4.20; DESIGN §10 | Cards and lease verbs explain restarts, staleness and findings; checkpoint overrides must be a full 40-hex sha. |
| G1021 | #749 | SPEC §5.4, §8.4; DESIGN §3.16, §10 | `integrate` detects a conflicting PR locally and from GitHub, and asks a human when no checks appear. |
| G1000 | #748 | SPEC §3.1, §3.2, §3.6, §3.10, §3.14, §4.9, §4.10, §4.14, §4.18, §4.20, §5.4, §8.3; DESIGN §3.8, §4.1, §10 | Engine: `review.filter`, lens findings with `impact` and `material`, the filter that promotes but never demotes, the `candidates` fingerprint part and liveness, `skippable` and the skip refusal, `settings.intent`, the re-review pointer `previous.changed`, and the PR body's reviews. Configuration (DESIGN §4.1 only): the 26-node lens graph. |
| G1023 | #751 | SPEC §3.10, §4.20 | Checkpoint override hints say `<full 40-hex sha>`; written into SPEC together with G1016's rule. |
| G1020 | #750 | SPEC §4.14; DESIGN §3.8 | A filtered lens with only notes open answers `approved` ("approved with N notes"). Its prompt changes (the `review` instruction tells code lenses to target `test_design` for test problems) are configuration. |
| Owner decision | this PR | SPEC §7, §8.1, §8.2; DESIGN §4.1 | **The default graph, prompts and policy values are configuration, not engine contract** (owner, 2026-11-01: "But G1000 just changes the default DAG no? Does that even need to be in the spec? Surely just the engine needs to be in the spec, default DAG is configuration?"). SPEC §7 and §8.1–§8.2 keep their numbers but state only the rules any `workflow.json`, `POLICY.json` and prompt must satisfy, and point to `plugins/zzzops/zzzops/templates/default/` as the source of truth. Revision 6.3's listings (the 12-node JSON, the template POLICY values, the prompt table) are removed, not updated. The default graph's bindings and rationale moved to DESIGN §4.1. This departs from G1017's approved design, which kept a full copy. |
| G1034 | this PR | DESIGN §7 | Migration assigns each goal an owner-confirmed release (skill and MIGRATING; no engine change). |
| G1017 | this PR | all files | Moved into the repository from the external design folder, scrubbed of private data, with this history; the amendments above applied. No other semantic change. |
| G1029 | this PR | DESIGN §3.12 | Capture-time intent check (skill only); the Intent lens honours a departure recorded with the owner's dated words; `approve_design` shows it. |

Worked examples in DESIGN §4 and SPEC (finding ids such as `review_impl:2:1`, the 12-node walkthroughs) still use revision 6.3's node names. They illustrate mechanisms that the lens graph keeps unchanged.
