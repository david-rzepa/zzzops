# G1000 design: parallel review lenses in the default graph

## 1. Outcome

The shipped default graph (`plugins/zzzops/zzzops/templates/default/`) replaces `review_design` and `review_impl` with seven independent review lenses. They run in parallel on the design, and again on the implementation. An independent filter node per subject then decides which findings reopen the work and which become non-blocking notes. The project's intent becomes a declared policy input that the Intent lens reads. This repository adopts the graph afterwards through two policy branches that the root opens after G1000 merges, the first only on the owner's go-ahead (§12).

The lens set comes from the experiment in §11. The spec's five-lens hypothesis covered 17 of the 32 material issues found (12 of the 24 that would have caused harm). The seven lenses as actually run cover 28 of 32 (23 of 24); that is measured. The merged seven prompts of §4 were not run as written: their extrapolated coverage, the union of the lenses each absorbs, is 31 of 32 (23 of 24).

**Changes in revision 3** (answering `review_design` round 1): the filter's fingerprint now covers the candidate findings, and a note without a verdict counts as kept (§7, F1). The rollout is a list of root follow-ups with an owner gate, and G1003 is held until the lens graph is in force (§12, F2). Coverage is reported as measured (§11). The demotion count is corrected to 11 of 13. The budget is stated in rounds (§14). D9 is resolved by G1017, and the contract amendments are listed in §17.

**Changes in revision 4** (answering `review_tests` round 1): `edit` refuses a new skip of a node while it has any open finding that is not a note, so a lens can no longer be skipped while its findings wait for the filter (D6, §5, §13, §17). §13 also gains an explicit per-lens independence test and an intent-staleness check at the implementation stage.

## 2. Decisions (for `approve_design`)

| # | Decision | Rejected alternatives |
|---|---|---|
| D1 | **Seven lenses:** `intent`, `simplicity` (not skippable); `truth`, `adversary`, `concurrency`, `rollout`, `experience` (skippable). Each lens has one prompt, and is used by two nodes, `<lens>_design` and `<lens>_impl`. | The five-lens hypothesis (12/24 harmful issues covered). All sixteen candidates (twice the cost for one more low-severity issue). |
| D2 | **Nitpick filter = both an engine rule and a filter node.** Lens findings carry `impact` and the reviewer's `material` claim. One cheap filter node per subject (`filter_design`, `filter_impl`) gates them. A finding reopens its target if the reviewer claims it is material **or** the filter keeps it. The filter can promote a note, but **never demote** a material claim. Demotion goes through the existing dispute path (the target answers `disputed:`, then the reviewer decides, then the human). | Engine rule only: self-labelling alone lost 2/16 harmful issues on the draft and 3/8 known defects on the replay. Filter with demotion power: a blind filter dropped 9/16 harmful issues. That would recreate R2's failure mode, an authority that drops findings. |
| D3 | **The filter is the join.** Lens findings go live only once the filter has a fresh record, and the filter reads every lens's output. So the subject reopens once per round, with every finding. | A separate "reopen batching" frontier rule (draft 1). Five lenses called it unrequested scope and an unbounded wait. |
| D4 | **Project intent is `settings.intent`** in POLICY.json: `{purpose, serves, not, principles}`. The Intent lens nodes declare `"policy": ["intent"]`. Through the existing fingerprint rules, that makes intent validated (missing intent fails `validate --policy`), shown on the card, and stales Intent reviews when it changes. | A section of PROJECT.md (not bound to policy, not fingerprinted). A POLICY instruction (not fingerprinted). A new `policy.` input selector (more engine code). |
| D5 | **The template ships a placeholder intent** (strings starting with `TODO:`). `validate --policy` passes on it, with an `intent_placeholder` warning; a missing `settings.intent` is an error. The bootstrap skill requires the warning to be gone. Together these satisfy both acceptance bullets literally. **Owner: confirm, or choose the strict alternative.** | Strict alternative: the template has no intent, so `validate --dir <template>` fails with exactly that error. That contradicts "validate --policy passes for the template", and five lenses objected to it. |
| D6 | **New node field `skippable`** (default `true`). It is `false` on `intent_*`, `simplicity_*`, `filter_*` and `approve_merge`. `edit` also refuses to add a skip of a node while its latest record has any open finding that is not a note (live, or waiting for its filter): waive the findings first, visibly. | Inferring skippability from optional inputs (implicit, and it can disagree with the inputs). Visibility of skips alone, without the refusal (the "skip the objecting lens" attack). |
| D7 | **Re-review pointer:** `reviewed` also records the subject's artifact blobs, and the card shows `previous.changed = git diff <old blob> <new blob>`. `reviewed` is written only on a fresh submit, when the lease's fingerprint equals the current one, the same condition as `target_fp`. | Recording the subject at submit time even for a stale lease. The diff would then start from a version the lens never read. The same latent bug exists for checkpoints today, and this fixes both. |
| D8 | **Three-step rollout, run by the root:** (1) G1000's PR. (2) `zzzops/policy/engine-1.1.0` raising `engine.min`, opened **only after the owner says go**, because it strands the Codex agent the owner has pinned to the 15b59a5 plugin copies. Repointing Codex stays with the owner and is out of scope. (3) `zzzops/policy/lenses`, with this repository's graph, prompts and the Appendix B intent strawman. The owner rewrites and approves the intent on that PR. G1003 is held from G1000's `approve_merge` until step 3 lands (§12). | One change (integrate refuses goal diffs that touch policy files). Raising the floor automatically at merge (it would break the owner's pinned Codex agent mid-work). Raising it in step 3 (lens records would then be written while 1.0 clones may still run). |
| D9 | **SPEC.md and DESIGN.md:** G1017 brings them into the repository. G1000 does not edit the external copies. §17 lists G1000's contract amendments for G1017 to apply, or to list as pending, whichever lands first. | Editing the external copies and showing their diff at `approve_merge` (draft 2; unreviewable in the PR). |

## 3. The shipped graph (26 nodes)

```
design ─┬→ intent_design ──────┐
        ├→ simplicity_design ──┤
        ├→ truth_design ───────┤
        ├→ adversary_design ───┼→ filter_design → approve_design → base → test_design → review_tests → implement → run_tests ─┐
        ├→ concurrency_design ─┤                                                                                            │
        ├→ rollout_design ─────┤                                                                                            │
        └→ experience_design ──┘                                                                                            │
  ┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
  └→ { intent_impl … experience_impl } → filter_impl ─┬→ integrate ─────┬→ merge
                                                      └→ approve_merge ─┘
```

| Node | Definition (changes only) |
|---|---|
| `design` | `dep_reviews` reads `deps.filter_design.summary` (optional, context), replacing `deps.review_design.summary` |
| `<lens>_design` (×7) | agent, `capability: reasoning`, `stage: discovery`, `review: {"subject": "design", "filter": "filter_design"}`, inputs `spec` (`goal.spec`) and `doc` (`design.doc`), prompt `lens_<lens>.md`, instructions `review` and `communication`. `intent_design` adds `policy: ["intent"]`. `intent_design` and `simplicity_design` are `skippable: false` |
| `filter_design` | agent, `capability: bounded`, `skippable: false`, prompt `filter.md`; inputs `spec`, `doc`, and one input per lens from `<lens>_design.summary` (not context, so a lens re-run stales the filter; `optional` exactly for skippable lenses); outputs `{"summary": "text", "verdicts": "object"}` |
| `approve_design` | inputs `summary`, `doc`, `filter` (`filter_design.summary`); context: each lens summary (optional for skippable lenses) |
| `base` | context `filter_design.summary` replaces `design_review`, so `skip.approve_design` still waits for the lenses and the filter |
| `test_design`, `review_tests`, `implement`, `run_tests` | unchanged |
| `<lens>_impl` (×7) | review of `implement` with `filter: filter_impl`; inputs `doc`, `tests`, `code` (`implement.code.change`, as `review_impl` today), context `checks`; `intent_impl` also has `spec` and `policy: ["intent"]`. G1018 makes such sub-field inputs show the full checkpoint (commit, base, diff) on the card. Until it lands, code-lens workers use the WORKER.md workaround |
| `filter_impl` | as `filter_design`, with inputs `doc`, `code` and the code-lens summaries |
| `integrate` | context `filter` (`filter_impl.summary`) plus each code-lens summary, replacing `review` |
| `approve_merge` | `skippable: false`; context as `integrate`, replacing `impl_review` |
| `merge` | unchanged |

Removed: `review_design`, `review_impl`, `review_design.md`, `review_impl.md`. Both subjects use one lens set. The experiment measured design reviews only. Goals trim lenses with skips, and projects trim them in their own workflow.json.

## 4. Prompts

**POLICY instruction `review`** (shared mechanics; on every lens card):
> You are one of several independent reviewers, each with one lens; judge only what yours asks, and do not read the other reviews of this subject (`.zzzops/reviews/<goal>/` files of other nodes) before you submit. Approving with no findings is a good outcome. Raise a finding only when you can name what goes wrong if it is ignored: give `impact` (that consequence, concretely) and `material` (true: it must be fixed before the work proceeds; false: a note, preference or idea). An independent filter may promote a note; it never demotes a material finding. On a re-review, read what changed first (`previous.changed` or `previous.interdiff`) and give every prior finding a status. Check claims against the integration tip (`read_dev`). Write the full review to the artifact and a one-line verdict in `summary`.

**Lens prompts** (`prompts/lens_<lens>.md`; each ends "On code: judge the diff against the approved design."):
- **Intent:** Two questions. (1) Goal intent: does this solve the problem the goal states, faithfully to its spec and, for code, to the approved design? Look for silently dropped or weakened requirements, quiet redefinition, scope creep, and decisions taken on the owner's behalf. (2) Project intent (`policy.intent`): does it serve what the project is for and whom it serves, and keep its principles, or does it pull the project toward what it deliberately is not? Name the sentence of the spec or intent that each finding rests on. If `policy.intent` is still a `TODO:` placeholder, submit `--blocked` asking the owner to capture it.
- **Simplicity:** Is this the simplest thing that fully works, and should each part exist at all? Separate essential from accidental complexity. For each mechanism, name the failure it prevents and whether that is worth its cost. Name what can be deleted, merged or deferred. Check cohesion (parts with several responsibilities, or one idea spread over many places). Does the change leave the system simpler or more tangled? A finding names the simpler alternative.
- **Truth:** Is it true? Do its parts agree with each other and with the system's existing concepts, with no parallel concept and no silent exception? Is every claim checkable by a test, a command or a cited line? Does every failure surface honestly, with no silent fallback and no record or report that claims more than it knows? On code: do the tests check what the design promises?
- **Adversary:** How could this harm someone, or be broken or gamed? Consider security, privacy, data loss and irreversible actions; a careless, lazy or hostile agent; a worker or reviewer gaming its incentives; a human acting directly on GitHub; malformed input. Find the cheapest way to defeat each guarantee, and say who gets hurt.
- **Concurrency:** What happens when things run at the same time, fail halfway, retry, or grow? Races, ordering, atomicity, leases, idempotency and partial failure; then load, data and the number of parallel agents growing (performance pathologies, unbounded growth, contention).
- **Rollout:** How does this reach users, and how is it undone? Upgrade order, compatibility with older engines, existing data and in-flight work, format and schema changes, names others will come to depend on, and the rollback path. Is the cost of being wrong proportionate?
- **Experience:** What is it like for the person on the other end: the owner answering a human item, the operator recovering from a failure, the agent reading a task card, the future reader of the code? Clarity, messages, defaults, failure and recovery, docs.

**`filter.md`:** You are the independent filter for this subject's lens reviews. `candidates` lists every open lens finding. Findings a lens marked material reopen the work whatever you decide; you judge the notes. For each note, answer `keep` if ignoring it lets something concrete go wrong: a requirement is violated, behaviour is wrong, work or data is lost, authority or safety is weakened, or someone gets stuck. Otherwise answer `note` (nit, preference, idea, or already handled). When unsure, keep. Give every note a verdict and a short reason. In `summary`, put the lens verdicts, what reopens the work, and how many notes there are.

**Changed prompts:**
- `approve_design.md` and `approve_merge.md` show the filter summary, each lens verdict, the findings that reopen the work, the notes grouped by lens, and every skip with its reason. A note that matters to the human is recorded as a finding in their words.
- `design.md` and `implement.md` gain two lines: "Notes are optional: act on one only if it is cheap and in scope." and "If you meet a risk that a skipped lens covers, submit `--blocked` with the options `unskip <node ids>` and `continue`."

## 5. Skips

- **Engine:** `NODE_FIELDS["skippable"]` (boolean, all kinds). Goal validation adds "`<node>` is not skippable (`skippable: false` in workflow.json)". `edit` refuses a new `skip.<n>` while `n`'s latest record has any open finding that is not a note. A note is an open finding with the verdict `note` on its filter's fresh latest record (§7); every other open finding counts, whether it is live, waiting for the filter, or waiting for re-review. So the refusal holds through the filter's join window, when a lens's findings are not yet live. The message names the findings and the waiver: `edit --set records.<n>.findings[<id>].status="waived"` with a `note`. It reuses §7's note test and needs no other liveness check. It is stricter than liveness: an old finding waiting for re-review also needs a waiver before the skip, which is the visible path D6 asks for. `render.py` offers no `skip` option for non-skippable nodes. `node_def_fp` is an allowlist, so no fingerprint changes.
- **Validation:** a filter's input from a skippable lens must be `optional`, and an input from a non-skippable lens must be required.
- **Skills:**
  - add-goal proposes skips from the goal's risks. It names node ids in pairs, for example `skip.concurrency_design` and `skip.concurrency_impl` for a docs-only goal, and `experience_*` for internal-only changes.
  - A skip added after `new` needs the human's words in its reason.
  - Execute answers an `unskip` choice with `zzzops edit G --file F --base C` setting those keys to `null`. An unskipped lens becomes `ready (new)` against the current subject, and the filter and its consumers wait for it.
- **Visibility:** approval items and the PR body list every skip with its reason.

## 6. Project intent

- **Form:** `settings.intent = {"purpose": text, "serves": text, "not": [text], "principles": [text]}`, with extra keys allowed (text or list of text). `SETTINGS_SHAPE` gains it as the one optional key. *Implementation:* `schemas._check_shape` requires every key of a shape dict and allows no extras, so this needs one small new shape kind (an optional key whose value is an open dict of text or list of text). It must not loosen the check for other keys.
- **Required** by the graph, not by the schema: a node that declares `policy: ["intent"]` fails `validate --policy` when the key is missing, through the existing rule 6. Values starting with `TODO:` give the warning `intent_placeholder`.
- **Seen:** `card.build` adds `"policy": {key: value}` for an agent node's declared keys, using the same inline or blob view as inputs.
- **Staleness:** the existing `policy` part of the fingerprint. A change stales `intent_design` and `intent_impl` on every open goal, and does not count against the budget (existing rule). `validate --policy-ref` already prints the impact; MIGRATING.md advises landing intent changes when few goals are in flight.
- **Changing it** is a policy change: a `zzzops/policy/*` branch, never a goal diff.
- **Bootstrap step 2** gains: "Capture the project's intent with the owner: what it is for, whom it serves, what it deliberately is not, and the principles that must survive change. Record their words."
- **This repository:** Appendix B holds questions and a strawman. The root puts the strawman on `zzzops/policy/lenses` (§12 step 3). The owner rewrites it and approves the final text on that policy PR, not through G1000's `approve_design`.

## 7. Nitpick filter (engine)

- **Lens findings.** A review declaring `filter` must give `impact` (non-empty text) and `material` (boolean) on every new finding. These are two new optional finding keys. Other reviews, human answers and op findings are unchanged: always material, no new fields.
- **A filtered lens's record is always `ok`.** Its findings are candidates, and blocking happens through the subject reopening. The lens's `decision` keeps its existing consistency rule and is shown in displays.
- **Filter card:** `candidates` lists the open findings on its lenses' latest records: `{id, lens, target, text, impact, material, response}`.
- **Filter submit:** `verdicts` must give `keep` or `note`, with a reason, for exactly the non-material candidates on the filter's card. A missing or extra id is refused, so nothing is dropped silently. The filter's record is always `ok`.
- **The filter's freshness covers its candidates (F1).** `fp_parts` gains a `candidates` part for a node that is some review's `review.filter`: the sorted `[id, material]` pairs of the open findings on its lenses' latest records. It is computed the way the `subject` part is, from the records. So a lens that re-runs and adds, closes or relabels a finding stales the filter, even when the lens's summary and the design did not change: the intent herd, a lens prompt `rev` bump, or a def-stale "resubmit it". `stale_keys` reports `candidates`. A candidates-only stale does not count against the budget, like `def` and `policy.*` in `frontier.counts`, because the lens re-run that caused it is already counted or exempt.
- **Liveness** (frontier pass 1, one added condition): a finding carried by a filtered lens is live only if the filter's latest record is done and fresh. Fresh means its input fingerprint, from recorded values and the current candidates, equals the record's. While the filter is stale, its lenses' findings wait for it: the filter is the join. Once it is fresh, a finding is live unless it is non-material **and** the filter's latest record gives it the verdict `note`. So a note with no verdict counts as kept. The fingerprint rule makes that case unreachable, and the default makes any gap fail toward keeping, as the spec asks, rather than silently dropping the note. A note is an open finding whose verdict is `note`. Notes never reopen work, never count against the budget, and carry forward while the lens keeps them open.
- **Displays:** a target's card lists `notes` (text, impact, lens, the filter's reason). Human items for nodes that consume a filter list them grouped by lens.
- **Independence:** `start` refuses a filter holder who produced the subject, through the same `independence` check as reviews. *Implementation:* `start` finds the subject only through `graph.subject(X)` (`verbs.py:174`), and a filter is not a review. So `Graph` derives a filter's subject from the lenses that name it in `review.filter`. Validation requires every lens naming one filter to share one subject.
- **Join:** the filter reads every lens's summary, so it runs once all non-skipped lenses are current, and the subject reopens once per round. A crash-looping lens raises its own `crash_loop` item. The filter waits visibly behind it ("blocked: concurrency_design").

## 8. Re-review "what changed" pointer (engine)

- `records.reviewed()` also records each artifact output of the subject as `{"blob", "commit"}`. It records nothing unless the submit is fresh (D7).
- `card.previous()` branches on output type. For a changed artifact, `previous.changed` holds `git diff <old blob> <new blob>`, built only from validated 40-hex ids. If the old blob is missing after one fetch of the work branch, the card says "previous version not available; review in full". A missing `reviewed` (records from before 1.1) also means a full review. Checkpoints keep `interdiff`.

## 9. Fan-in and PR body

- Lenses fan out from their subject. The filter joins them. `approve_design`, `base`, `integrate` and `approve_merge` read the filter summary, plus lens summaries as context for display.
- `integrate.pr_body` writes `## Reviews`. Under it come the filter summary, then one line per input whose producer is a review node (`**<node>**: <summary>`), then `skipped: <reason>` for every node in `ctx.doc["skip"]`. Summaries are clipped to one line. It reads no node names. No op version bump: the body is refreshed on every `integrate` run.

## 10. Engine changes, and the requirement each serves

| Change | Files | Serves |
|---|---|---|
| `skippable` field; skip refusals; no skip options in items | `schemas.py`, `verbs.py`, `render.py` | acceptance: refused skip; Adversary I22 |
| `settings.intent` (optional shape), placeholder warning, card `policy` section | `schemas.py`, `cli.py`, `card.py` | spec: intent as a declared input |
| `review.filter`; filtered-lens `ok`; `impact`/`material`; `candidates`/`verdicts`; the `candidates` fingerprint part; liveness condition; `notes`; filter subject for independence | `schemas.py`, `records.py`, `fingerprint.py`, `frontier.py`, `card.py`, `render.py`, `verbs.py` | spec: nitpick filter (owner request) |
| `reviewed` artifacts, fresh-only; `previous.changed` | `records.py`, `card.py` | spec: the small engine change; Concurrency I28 |
| PR body lists review summaries and skips | `ops/integrate.py` | spec |
| `ENGINE_VERSION = "1.1.0"` | `__init__.py` | Rollout I9 |

The draft's reopen-batching rule, specialised intent message, 2 KB intent cap and approve-item interdiff sharing are dropped.

## 11. Lens experiment

**Method.**
- **Draft round.** Sixteen candidate lenses each reviewed design draft 1 as independent subagents (Opus). Each saw only the spec, the draft and its own one-paragraph lens prompt. Each was told that approving with no findings is a good outcome, and asked for `impact` and a material/note claim on every finding.
- **Prompt control.** The five hypothesis lenses re-ran without that guidance.
- **Replay.** The sixteen re-ran on a past design with known defects: revision 6's stacked-delivery decision A1 as first written, before its amendments. The ground truth is twelve defects that later passes fixed: amendments 1 and 3, `m4:F1/F2/F3/F6/F7/F9`, `x:M9`, `x:M11`, `x2:M1` and `x2:L9`.
- **Filter.** A blind Sonnet filter classified every finding of both rounds as keep or note.
- **Adjudication.** I judged each draft finding against the design: **S** (harmful if ignored), **A** (adopted improvement), **N** (nit) or **X** (false or already handled). "Material" means S+A, the findings that changed this design. Findings are grouped into issues (I1–I41) to measure uniqueness.

**Cost.** Every lens run cost about the same, because reading the documents dominates: about 42k tokens and 25–40 s on the draft, and about 35k tokens and 23–51 s on the replay. The filter cost about 40k tokens and 17 s. A lens set therefore costs about N × 42k tokens per review round.

"Unique issues" in this table are unique among all sixteen lenses; the per-set uniqueness is given below it.

| Lens | Draft findings | Material (S+A) | Nit+noise | Unique issues | Replay known defects | Unique known defects | Verdict |
|---|---|---|---|---|---|---|---|
| Intent | 5 | 4 | 1 | I25 (agent wrote the owner's intent) | 0 | – | **keep** (spec; unique harmful) |
| Simplicity | 6 | 3 | 3 | – | 2 | – | **keep** (spec; code entropy), absorbs Necessity |
| Safety | 5 | 5 | 0 | I21a | 1 | – | merge into Adversary |
| Scale | 6 | 1 | 5 | – | 0 | – | merge into Concurrency |
| Experience | 7 | 4 | 3 | I11 | 0 | – | **keep** (only human-facing lens), absorbs UX |
| Truth | 7 | 5 | 2 | I23, I26 | 1 | – | **keep**, absorbs Coherence |
| Reversibility | 6 | 3 | 3 | – | 0 | – | merge into Rollout |
| Coherence | 6 | 5 | 1 | – | 2 | – | merge into Truth |
| Necessity | 7 | 5 | 2 | I41 | 0 | – | merge into Simplicity |
| Adversary | 7 | 5 | 2 | I10, I32 | **5** | GT3, GT12 | **keep** (best yield), absorbs Safety, Security |
| Architecture (control) | 5 | 3 | 2 | – | 4 | GT6 | drop (one low-severity unique) |
| Security (control) | 5 | 2 | 3 | – | 0 | – | merge into Adversary |
| Performance (control) | 4 | 1 | 3 | – | 0 | – | merge into Concurrency |
| Concurrency (control) | 5 | 2 | 3 | I28 | 2 | GT11 | **keep**, absorbs Scale, Performance |
| Migration (control) | 6 | 5 | 1 | – | 0 | – | **keep as Rollout**, absorbs Reversibility (3 unique harmful issues as a pair) |
| UX (control) | 6 | 4 | 2 | – | 0 | – | merge into Experience |

**Coverage.** There are 32 issues. 24 come from the draft round: 16 harmful and 8 adopt-only. The other 8 are the known defects that some lens found on the replay, all harmful. So 24 of the 32 are harmful. Four known defects were found by no lens: `m4:F2`, `m4:F3`, `x:M9`, `x:M11`. "Measured" rows count the lenses as they were actually run. "Extrapolated" rows count the union of the lenses each merged prompt absorbs; the merged prompts of §4 were never run as written.

| Set | Basis | Issues covered | Harmful covered | Cost per round |
|---|---|---|---|---|
| Spec hypothesis (5) | measured | 17/32 | 12/24 | 5 runs |
| **The seven as run** (intent, simplicity, truth, adversary, concurrency, migration, experience) | **measured** | **28/32** | **23/24** | 7 runs + 1 filter |
| The same without Experience | measured | 25/32 | 22/24 | 6 + 1 |
| Merged seven (§4 prompts) | extrapolated | 31/32 | 23/24 | 7 + 1 |
| Merged seven without Experience | extrapolated | 29/32 | 23/24 | 6 + 1 |
| All sixteen | measured | 32/32 | 24/24 | 16 runs |

D1 rests on the measured row. Merging adds only three adopt-only issues: I12, I21a and I41. GT6, a low-severity defect, is the one harmful issue the seven miss.

Unique harmful issues per lens, measured: Adversary 7 (GT2, GT3, GT7, GT12, I10, I22, I32), Rollout (Migration) 4 (I3b, I7, I8, I9), Concurrency 2 (GT11, I28), Truth 2 (I3a, I23), Intent 1 (I25), Experience 1 (I4), Simplicity 0. Experience is the only lens among the seven that caught I4, which forced humans to label their findings. Simplicity stays because the spec makes it mandatory for code entropy, which a design round cannot measure. The code-lens set mirrors the design set without data, and should be re-scored on real `implement` reviews.

**Nit rate with and without the filter (draft round, 93 findings):**

| Which findings block | Blocking | Not harmful (nit rate) | Harmful issues lost |
|---|---|---|---|
| All, no filter | 93 | 54% | 0 |
| Reviewer's material claim only | 29 | 10% | 2 (I25, I32) |
| Blind filter only (can demote) | 24 | 4% | **9** |
| **Claim OR filter keep (D2)** | 37 | 11% | 1 (I25) |

| Lens | Nit rate, all blocking | Nit rate with D2 |
|---|---|---|
| Intent | 20% | 0% |
| Simplicity | 83% | – (nothing blocks) |
| Safety | 20% | 0% |
| Scale | 83% | 0% |
| Experience | 71% | 50% |
| Truth | 43% | 20% |
| Reversibility | 50% | 0% |
| Coherence | 50% | 50% |
| Necessity | 71% | 0% |
| Adversary | 29% | 0% |
| Architecture | 60% | 0% |
| Security | 60% | 0% |
| Performance | 75% | 0% |
| Concurrency | 60% | 33% |
| Migration | 17% | 0% |
| UX | 67% | 0% |

On the replay, a claim-only rule lost 3 of 8 found defects (GT3, GT6, GT8). D2 lost 1 (GT6, low severity). The filter's promotions were all correct (8/8 on the draft). Its demotions of material claims were wrong in 11 of 13 cases (in3, tr5, re2, co2, ne1, ad2, ad3, mi2, mi3, mi4, ux1), so D2 does not let it demote.

**Prompt control.** Without the "approving is good, give impact" guidance, the five hypothesis lenses raised 38 findings instead of 29, all five requested changes instead of four, and the nit rate stayed the same (37% vs 41%). The guidance cuts volume, and the material claim is what separates nits from harm.

**Findings that changed this design** (draft 1 → this revision): the filter replaces self-labelling and batching (I1, I5, I6); the template placeholder is now an owner decision (I2); fields are required only for filtered lenses, so older graphs and human answers are unchanged (I3, I4); the cutover, rollback and engine-floor ordering (I7–I9); notes persist while the lens keeps them (I10); notes guidance and the unskip option (I11, I13); paired node ids (I12); a smaller intent mechanism (I19); `dep_reviews` reads the filter (I20); `approve_merge` is not skippable (I21a); skip refusal and visibility (I22); external docs (I23); the owner writes the intent (I25); PR skips with reasons (I26); fresh-only `reviewed` (I28); sibling-review isolation (I32); no interdiff sharing (I41). One finding was false: Concurrency's claim that `base` would not wait for new lenses. Context inputs gate readiness, so it does wait.

## 12. Rollout and migration

G1000 delivers step 1. Steps 2 and 3 are follow-ups that the root performs after G1000 merges. The root records them on G1000's `approve_merge` item, so the owner sees them when approving the merge. Repointing the Codex plugin is not a step: the owner controls it and does it when they choose.

1. **G1000's PR** into `dev`: engine, template, fixture freeze, tests, skills, references, `package.py` and `docs/EXECUTION.md`. It touches no `.zzzops/` policy file. **Before approving the merge, the root holds G1003** (`zzzops edit 1003 --set 'state="held"' --base C`). The dogfood run must use the lens graph, and G1000's merge would otherwise unblock it on the 12-node graph.
   - *Between steps 1 and 2:* this repository still runs the 12-node graph. The root's Claude Code plugin may move to 1.1 while the owner's Codex agent stays on the 15b59a5 copies (1.0). That mix is safe. The old graph writes no new finding keys, workflow fields or settings, and a 1.0 engine reads 1.1's `reviewed` entries (§8; `card.previous` skips entries without `change`).
2. **`zzzops/policy/engine-1.1.0`, gated on the owner.** After the merge, the root asks the owner: "Raising `engine.min` to 1.1.0 makes every 1.0 engine, including the Codex agent pinned to 15b59a5, refuse with `engine_too_old`. May I open `zzzops/policy/engine-1.1.0`?" The root opens the branch only on an explicit yes, following REPAIR's "Upgrade the engine" recipe: wait until nothing is running, then land. An open policy branch blocks all workflow work, so no goal advances under a half-applied upgrade. If the owner says not yet, the root waits and other work continues on the old graph. G1003 stays held.
3. **`zzzops/policy/lenses`, after step 2 has landed.** It changes this repository's `workflow.json` (§3) and `prompts/` (the seven lens prompts and `filter.md`; it deletes `review_design.md` and `review_impl.md`). It also changes POLICY.json: `settings.intent`, starting as the Appendix B strawman, and the instruction `review`. PROJECT.md's "Overall goal" points to the intent. Before pushing, the root previews the change from a local ref with `validate --policy-ref` and `next --policy-ref`. It pushes the branch when the owner is ready to review, because an open branch stops all work. The owner rewrites the strawman and approves the intent text on that PR. The branch lands only with the owner's text.
4. **After step 3 lands,** the root unholds G1003 (`--set 'state="open"'`).

**Which goals wait.** G1003 (dogfood) waits for step 3, through the hold. G1002 (whitepaper) does not wait: it describes the shipped graph that step 1 delivers, and it can run on either graph. Every other goal pauses only while a policy branch is open, which the engine already enforces.

**In-flight goals at step 3:**
- `review_design`/`review_impl` records become orphans (a warning). They are not deleted.
- Goals past `design` get the lenses as `ready (new)`. `base` and everything downstream then show as blocked behind `filter_design`. No checkpoint is lost. A kept finding reopens the design, and the human is asked `approve_design` again.
- Recommended default: land step 3 when no goal is past `approve_design`. The preview lists the goals that are.

**Rollback:** a policy branch restoring the old files, keeping `engine.min`. The lens records become orphans. The old review records come back, and are current again where their inputs did not change. Engine 1.1 to 1.0 is forward-only for goals that ran lenses (new finding keys). REPAIR's revert recipe applies. MIGRATING.md documents all of this.

## 13. Tests

- **Fixture freeze:** copy today's template (`workflow.json`, `POLICY.json`, `prompts/`) to `.agents/fixtures/graph12/`. `engine_fixtures.TEMPLATES` points there, and `DEFAULT_NODES`/`RENAME` keep working, so the existing engine tests stop depending on the shipped graph. A new `SHIPPED` path is used only by the template and lens tests.
- **Template:**
  - `validate --policy --dir` on the shipped template passes with exactly one `intent_placeholder` warning.
  - Without `settings.intent` it fails.
  - Every node has a prompt.
  - The names test still finds no default node id in engine source.
- **Journey (`.agents/test_engine_lenses.py`, shipped graph):**
  1. Seven design lenses are `ready` in parallel after `design`, with distinct holders.
  2. One lens raises a material finding. The design stays current until `filter_design` submits, then reopens once.
  3. Every lens re-reviews with `previous.changed`.
  4. `skip.concurrency_design` gives "skipped" plus its reason on `approve_design`.
  5. `new` with `skip.intent_design` is refused.
  6. `edit` adding a skip of a lens with live findings is refused. **A skip is also refused before the filter runs:** a lens submits a material finding, `filter_design` has not yet submitted (another lens is still running), and `edit --set skip.<lens>` is refused; after the finding is waived the same skip is accepted. A lens whose only open findings are notes judged `note` on a fresh filter can be skipped.
  7. `approve_design`'s item lists the filter summary and every lens summary.
  8. The PR body lists every code lens and the skips.
- **Nitpick filter:**
  - A note-only review with filter verdict `note` leaves the target current.
  - A material claim reopens it.
  - A borderline note promoted to `keep` reopens it.
  - A filter submit missing a verdict is refused, and one with an extra verdict is refused.
  - Notes appear on the target's next card and on the approval item.
  - Notes do not count against the budget.
  - A crash-looping lens leaves the filter visibly blocked.
  - **Unjudged note (F1):** the filter is fresh and every lens is current. Then `settings.intent` changes, and `intent_design` re-runs with the same summary and one new non-material finding. Check that `filter_design` becomes stale with `stale_keys == ["candidates"]` and that the design stays current, not reopened and not advanced past, until the filter re-submits. After a `keep` verdict the design reopens. After a `note` verdict the design stays current, and the note shows on its next card. The filter re-run does not count against the budget. Repeat with a lens `rev` bump in place of the intent change.
  - **Missing verdict fails safe:** a hand-built filter record that is fresh but lacks a verdict for an open note (written directly to `goal.json`, as a human might) makes that note live.
  - A filter holder who produced the subject is refused at `start`.
  - **Per-lens independence:** the designer's `start` on a design lens (and the implementer's on a code lens) is refused with `independence`.
- **Intent:**
  - The Intent lens card shows `policy.intent`.
  - Changing it stales only `intent_*`, checked at both stages: at the design stage, and again once `intent_impl` has a record (it goes stale, the other code lenses stay current).
  - The placeholder warning works.
  - An unknown extra intent key with a text value passes, a non-text value fails, and other settings keys still reject extras (the new shape kind).
- **Pointer:**
  - A stale-lease submit records no `reviewed`.
  - A missing old blob says "review in full".
- **Renamed graph:** the frozen fixture's rename test still passes, and the lens journey also runs on a renamed copy of the shipped graph (name independence).
- **Prompt budgets:** `prompt_stats.py --check` passes after the skill edits.

## 14. Risks

- **Cost:** about 8 agent runs per review round instead of 1. A round costs about 7 × 42k tokens plus the filter. Mitigated by skips, `previous.changed` and the one-reopen-per-round join. The budget (`3 × agent nodes`) grows from 18 to 60, but that is less generous than it looks. One full design correction round now costs up to 9 counted runs (design, 7 lenses, filter) instead of 2. So 60 allows about 6–7 full rounds per subject, where 18 allowed about 9. Skipped lenses still count toward the limit's size but not its use. A goal that runs out raises the existing budget item, and the owner can raise `budget` per goal.
- **The filter cannot demote,** so the residual nit rate among blocking findings is about 11%. Reviewers' prompts and disputes handle the rest.
- **The intent change herd:** one change re-runs two Intent reviews on every open goal. Preview it first.
- **One shipped lens set** is now part of every bootstrapped project. Renames follow REPAIR's rename recipe.

## 15. Docs

- **SPEC and DESIGN:** G1017 brings them into the repository. G1000 does not edit them; §17 lists the amendments.
- **In this repository:**
  - MIGRATING.md: adopting the lens graph, in-flight goals, rollback, lens-set edit checklist.
  - `package.py`: the prompt list.
  - The bootstrap, add-goal and execute skills.
  - `docs/EXECUTION.md`: the diagram.

## 16. Out of scope

Lens applicability predicates in the engine; a requirements Q&A phase; findings targeting `goal.spec`; red-before-green (#457); PR-comment interpretation; decomposition; re-scoring the code-lens set on real implementation reviews; repointing the Codex plugin (owner-controlled); the card rendering of checkpoint sub-field inputs (G1018); moving SPEC and DESIGN into the repository (G1017).

## 17. Contract amendments (for G1017)

G1017 applies these to the in-repository SPEC and DESIGN if G1000 has merged first. Otherwise it lists them under "pending amendments: G1000".

- **SPEC:**
  - §3.1: node field `skippable` (default `true`); `review.filter`; filter outputs `summary` and `verdicts`; the wiring rule (a filter's input from a skippable lens is `optional`, one from a non-skippable lens is required; lenses naming one filter share one subject).
  - §3.2: `settings.intent` (`purpose`, `serves`, `not`, `principles`, extra text keys); the `intent_placeholder` warning.
  - §3.6: finding keys `impact` and `material`, required on new findings of a filtered review only.
  - §4.9: a filtered lens's record is `ok`. The filter's fingerprint gains the `candidates` part. Liveness: a filtered lens's finding is live only once the filter is fresh, and then unless it is non-material with verdict `note`. A missing verdict counts as kept.
  - §4.10: a `candidates`-only stale does not count against the budget.
  - §4.14: verdict validation (exactly the card's non-material candidates); `reviewed` records artifact blobs, on a fresh submit only.
  - §4.18: `edit` refuses a skip of a non-skippable node, and a new skip of a node whose latest record has any open finding that is not a note (live, or waiting for its filter).
  - §4.20: card sections `policy`, `candidates`, `notes`, `previous.changed`.
  - Independence: a filter's subject is derived from its lenses.
  - §5.4: the PR body's `## Reviews` section.
  - §7: the 26-node default graph and its JSON.
  - §8.2/§8.3: the lens prompts, `filter.md`, the instruction `review`, and bootstrap step 2 (capture intent).
- **DESIGN:**
  - §3.8: the filter and notes, including why it may promote but never demote (§11 data) and why its freshness covers candidates.
  - §4.1: the graph and table.
  - §10: new items (skippable, intent, filter, pointer, PR body), plus the rollout order of §12 with its owner gate.

## Appendix B: this repository's intent — questions and strawman for the owner

**Questions:**
1. What is ZzzOps for, in one sentence?
2. Whom does it serve?
3. What must it never become?
4. Which principles must survive every change?

**Strawman** (for the owner to rewrite; based on PROJECT.md):

```json
"intent": {
  "purpose": "Let coding agents carry long-running repository work through durable, reviewable goals, so a developer can stop supervising without losing progress, priorities or control.",
  "serves": "Developers who delegate project work to coding agents, and the agents doing it.",
  "not": ["A general project-management suite.", "A ceremony framework: every mechanism must prevent a real failure worth its cost.", "A second source of truth beside Git.", "An engine that invents human decisions or acts without authority."],
  "principles": ["Git is the store; state is visible and repairable by hand.", "A small engine; the graph, prompts and policy belong to the project.", "Human authority is explicit and batched.", "Reviews are independent, and a finding must matter.", "Prefer deleting to adding; keep prompts distilled."]
}
```

## Appendix C: experiment data

**Issue key** (S = harmful, A = adopt-only):
- I1 S: self-labelled material is not independent
- I2 S: template validate vs acceptance
- I3a S: legacy findings without `material`
- I3b S: fields required at release break old-prompt reviews
- I4 S: human submits forced to label
- I5 S: batching wait unbounded
- I6 S: unrequested engine scope
- I7 S: in-flight cutover
- I8 S: no rollback
- I9 S: 1.0 clones reading 1.1 records
- I10 S: notes vanish after one round
- I11 A: notes guidance for agents
- I12 A: paired node ids
- I13 A: unskip option
- I19 A: intent cap and special message
- I20 A: `dep_reviews` special case
- I21a A: `approve_merge` skippable
- I22 S: skip the objecting lens
- I23 S: unverifiable external docs
- I25 S: agent-written owner intent
- I26 A: PR "skipped" without reason
- I28 S: `reviewed` blob at the wrong time
- I32 S: lenses can read sibling reviews
- I41 A: interdiff sharing beyond spec
- other numbers: nits

**Replay ground truth:**
- GT1: amendment 1
- GT2: amendment 3
- GT3: `m4:F1`
- GT4: `m4:F2`
- GT5: `m4:F3`/`x:H1`
- GT6: `m4:F6`
- GT7: `m4:F7`/`x:M7`
- GT8: `m4:F9`
- GT9: `x:M9`
- GT10: `x:M11`
- GT11: `x2:M1`
- GT12: `x2:L9`

"claim" is the reviewer's own m(aterial)/n(ote) label; "filter" is the blind filter's K(eep)/N(ote).

### C.1 Draft round (16 lenses on draft 1)
| id | lens | sev | claim | issue | adjudged | filter | summary |
|---|---|---|---|---|---|---|---|
| in1 | intent | high | m | I1 | S | K | Reviewer self-sets material; filter not independent; no borderline-kept test |
| in2 | intent | high | m | I2 | S | K | Template fails validate by design, redefining acceptance "passes for the template" without owner decision |
| in3 | intent | med | m | I6 | S | N | Engine additions beyond the one requested change (batching etc.) not listed as scope expansions |
| in4 | intent | med | n | I25 | S | N | Agent drafts this repo's intent; owner's own words not captured |
| in5 | intent | low | n | I24 | X | N | Graph fixed before experiment; mark provisional |
| si1 | simplicity | med | n | I18 | N | N | noted status duplicates material flag; keep status open + flag |
| si2 | simplicity | med | n | I6 | S | N | Reopen batching unrequested; decide after lens set is chosen |
| si3 | simplicity | low | n | I19 | A | N | Specialised intent message, 2KB cap, optional-key shape support are extra pieces |
| si4 | simplicity | low | n | I20 | A | N | design.dep_reviews reads only intent_design summary: special case |
| si5 | simplicity | low | n | I21b | N | N | skippable allowed on all kinds; restrict to agent |
| si6 | simplicity | low | n | I31 | N | N | Four consumers wire lens inputs by hand; note checklist |
| sa1 | safety | high | m | I1 | S | K | Self-set material lets a careless/hostile lens downgrade a real harm; with skip.approve_design nobody sees it |
| sa2 | safety | med | m | I3a | S | K | Old open findings without material field: treatment undefined, could stop blocking |
| sa3 | safety | med | n | I22 | S | N | Skip of safety lens not enforced as human-agreed; any edit can skip; show skips and reasons |
| sa4 | safety | low | n | I21a | A | N | skippable default true leaves future human nodes skippable |
| sa5 | safety | low | n | I7 | S | N | New design lens on in-flight goal can reopen approved design; owner not told |
| sc1 | scale | med | m | I5 | S | K | Batching wait unbounded when a sibling crash-loops or is reclaimed repeatedly |
| sc2 | scale | med | n | I29 | N | N | Wait includes ready-but-unstarted siblings; round time grows with backlog |
| sc3 | scale | med | n | I30 | N | N | Intent change stales intent lenses on all goals at once (herd) |
| sc4 | scale | low | n | I10 | N | N | Notes never get status; pile up on cards |
| sc5 | scale | low | n | I31 | N | N | Adding a lens means editing 6 places; validate warning |
| sc6 | scale | low | n | - | N | N | Record history grows 5x per round |
| ex1 | experience | med | m | I2 | S | K | Template fails validate out of box; CI and adopters see red |
| ex2 | experience | med | n | I11 | A | K | No prompt says what to do with notes; agents treat them as must-fix |
| ex3 | experience | med | n | I13 | A | N | Unskip path has no actionable option; blocked node resume unclear |
| ex4 | experience | low | n | I16 | N | N | Waiting reason should name pending lenses and lease expiry |
| ex5 | experience | low | n | I17 | N | N | Missing-intent message points to bootstrap; upgraders use policy branch |
| ex6 | experience | low | n | I4 | S | N | Human submits must give impact/material; friction or accidental downgrade |
| ex7 | experience | low | n | I14 | N | N | Not-skippable refusal should list skippable nodes |
| tr1 | truth | high | m | I1 | S | K | Self-labelled material trusted; no independent check; borderline test cannot be written |
| tr2 | truth | med | m | I3a | S | K | Missing material on legacy records undefined; must mean true |
| tr3 | truth | med | m | I5 | S | K | Wait cannot dead-end asserted without proof/test; crash-looping sibling stalls silently |
| tr4 | truth | med | m | I24 | X | N | Experiment section empty; D1/D5 stated as decided |
| tr5 | truth | med | m | I23 | S | N | SPEC/DESIGN outside repo; only implement's own claim evidences the update |
| tr6 | truth | low | n | I26 | A | N | PR body prints (skipped) for any null; use goal.skip and reason |
| tr7 | truth | low | n | - | N | N | PR body should show decision and note count |
| re1 | reversibility | high | m | I3b | S | K | Required impact/material at release breaks reviews in repos still on old prompts until policy branch |
| re2 | reversibility | med | m | I8 | S | N | No rollback documented for the lens policy branch |
| re3 | reversibility | med | n | I24 | X | N | noted schema frozen before experiment chooses filter |
| re4 | reversibility | low | n | I40 | N | N | Node ids fixed before experiment; rename policy |
| re5 | reversibility | low | n | I39 | N | N | Intent shape fixed; allow unknown keys for forward compat |
| re6 | reversibility | low | n | I9 | S | N | Older engine may not read new finding keys/reviewed entries; forward-only? |
| co1 | coherence | high | m | I2 | S | K | D9 contradicts acceptance silently |
| co2 | coherence | med | m | I12 | A | N | Lens is two nodes; skip/unskip wording must use both node ids |
| co3 | coherence | med | n | I6 | S | N | Batching is a scope addition; list it for approval |
| co4 | coherence | med | n | I20 | A | N | dep_reviews reads only Intent; inconsistent with fan-in rule |
| co5 | coherence | low | n | I36 | N | N | §6 says step 2, §13 says step 3 |
| co6 | coherence | low | n | I4 | S | N | Human submits required to carry impact/material |
| ne1 | necessity | med | m | I6 | S | N | Batching unrequested and unmeasured; defer |
| ne2 | necessity | low | n | I21b | N | N | skippable on human/op unnecessary |
| ne3 | necessity | low | n | I19 | A | N | Cap and special message are extra code |
| ne4 | necessity | low | n | I41 | A | N | render.interdiff sharing beyond spec |
| ne5 | necessity | med | n | I7 | S | N | In-flight path costly; require landing when idle |
| ne6 | necessity | low | n | I20 | A | N | dep_reviews unexplained |
| ne7 | necessity | low | n | I24 | X | N | 10 lens nodes fixed before experiment |
| ad1 | adversary | high | m | I1 | S | K | Lens can mark real defect as note; nit inflation also passes |
| ad2 | adversary | high | m | I22 | S | N | Skip the objecting lens after it raised a finding; findings die |
| ad3 | adversary | med | m | I10 | S | N | Noted findings vanish after one round; real problem filed as note disappears |
| ad4 | adversary | med | n | I33 | N | N | impact can be vacuous |
| ad5 | adversary | med | n | I5 | S | K | Crash-looping lens holds design waiting unbounded |
| ad6 | adversary | med | n | I32 | S | K | Lens can read sibling review artifacts on the work branch; independence lost |
| ad7 | adversary | low | n | I34 | N | N | Human may land policy branch mid-run |
| ar1 | architecture | high | m | I1 | S | K | Reviewer and filter same component; spec needs independent filter |
| ar2 | architecture | med | n | I31 | N | N | Lens set spread across 6 places; validate warning |
| ar3 | architecture | med | n | I5 | S | K | Batching stall on crash-looping sibling; test on frozen fixture |
| ar4 | architecture | low | n | I38 | N | N | Old blobs reachability after rebase |
| ar5 | architecture | low | n | I20 | A | N | dep_reviews partial |
| se1 | security | med | n | I1 | S | K | Self-set material; prompt-injected safety lens can downgrade |
| se2 | security | med | n | I22 | S | N | Who may skip after capture; approve_* skippable |
| se3 | security | low | n | I27 | X | N | previous.changed command from record values; validate hex |
| se4 | security | low | n | - | N | N | PR body injects agent summaries; escape markdown/mentions |
| se5 | security | low | n | - | X | N | Intent injected into cards; acceptable (no fix) |
| pe1 | performance | med | n | I5 | S | K | Batching latency = slowest lens or lease timeout; release on expiry |
| pe2 | performance | low | n | - | N | N | Redundant fetch/diff per lens card |
| pe3 | performance | low | n | I30 | N | N | Intent change burst; preview count |
| pe4 | performance | low | n | - | X | N | Confirm impl lenses get interdiff (already) |
| cc1 | concurrency | med | m | I28 | S | K | reviewed() records submit-time blob not the one the lens read; changes between are skipped |
| cc2 | concurrency | med | m | - | X | N | base not stale on adoption so downstream runs with new lenses (false: context inputs gate readiness) |
| cc3 | concurrency | low | n | I5 | S | K | Crash-looping sibling delays reopen |
| cc4 | concurrency | low | n | I37 | N | N | Wait excludes waiting/blocked siblings |
| cc5 | concurrency | low | n | I30 | N | N | Intent change mid-run delays batch |
| mi1 | migration | high | m | I3b | S | K | Required fields at release break old-prompt reviews in the window |
| mi2 | migration | high | m | I7 | S | N | Goals past approve_design gain lenses; approved work thrown away, approve_merge waits |
| mi3 | migration | med | m | I9 | S | N | noted/new keys written before engine.min raised; old engines misread |
| mi4 | migration | med | m | I8 | S | N | No rollback path for policy branch or engine |
| mi5 | migration | low | n | - | N | N | reviewed without artifacts must fall back |
| mi6 | migration | low | n | I2 | S | K | Template fails validate; owner must accept deviation |
| ux1 | ux | med | m | I4 | S | N | Human submits require impact/material |
| ux2 | ux | med | m | I2 | S | K | Template fails validate out of the box |
| ux3 | ux | low | n | I12 | A | N | Skip pairs per lens; write both ids |
| ux4 | ux | low | n | I14 | N | N | Refusal text should say where skippable comes from |
| ux5 | ux | low | n | I15 | N | N | Approval items noisy; verdicts first |
| ux6 | ux | low | n | I13 | A | N | Unskip option lacks literal edit command |

### C.2 Replay (16 lenses on revision 6 decision A1 as first written)

Known defects found: GT1 (5 lenses), GT2 (2), GT3 (Adversary), GT6 (Architecture), GT7 (Adversary, Safety), GT8 (4), GT11 (Concurrency), GT12 (Adversary). Not found by any lens: GT4, GT5, GT9, GT10. Union recall 8/12; Adversary alone 5/12.

| id | lens | sev | claim | ground truth | filter | summary |
|---|---|---|---|---|---|---|
| rin1 | intent | med | m | - | N | approve_merge decoupled from integrate: approval before CI not asked for by human |
| rin2 | intent | low | n | - | N | Dependency correction carries dependent approval forward |
| rin3 | intent | low | n | - | N | merge PR narrowed to display-only draft |
| rin4 | intent | low | n | - | N | Engine size grows |
| rsi1 | simplicity | med | m | GT1 | K | Stack-set rule contradicts itself; merged dep A missing when B unmerged |
| rsi2 | simplicity | low | n | - | N | |S| and k two counters |
| rsi3 | simplicity | low | n | GT8 | K | Stack PR lifecycle split; base has GitHub responsibility |
| rsi4 | simplicity | low | n | - | N | merge retargets other goals' PRs (coupling) |
| rsi5 | simplicity | low | n | - | N | stack output display-only, derivable |
| rsa1 | safety | med | m | GT7 | K | Stack source live branch tip; anyone can push/merge into zzzops/pr/g<dep>; unreviewed code restacked |
| rsa2 | safety | med | n | - | K | Approval context drift after dependency changes |
| rsa3 | safety | low | n | - | K | Retarget scope includes foreign PRs; list/delete race |
| rsa4 | safety | low | n | - | K | Draft stack PR mergeable by accident |
| rsc1 | scale | med | m | - | N | Quadratic restack cascade on chain merges |
| rsc2 | scale | med | m | - | K | Race between merge retarget and dependent integrate |
| rsc3 | scale | low | n | - | N | CI amplification on stacked PRs |
| rsc4 | scale | low | n | - | N | Duplicate combine branches for same S |
| rsc5 | scale | low | n | - | N | deps_conflict wait unbounded, no aging |
| rex1 | experience | med | m | - | N | deps_conflict wait opaque; no conflicting paths |
| rex2 | experience | med | n | - | K | Draft stack PR mergeable by hand |
| rex3 | experience | low | n | - | N | Stacked PRs show missing checks |
| rex4 | experience | low | n | - | N | Approve before CI not signalled |
| rex5 | experience | low | n | - | N | k>=2 item text lists one dep |
| rex6 | experience | low | n | - | N | Retarget shows misleading diff window |
| rtr1 | truth | high | m | GT1 | K | S omits merged dependencies; conflict hidden; deps_conflict reports resolved |
| rtr2 | truth | med | m | - | K | Retarget-before-delete unchecked; partial failures |
| rtr3 | truth | med | n | - | N | ok integrate on stacked PR claims more than checked |
| rtr4 | truth | low | n | - | N | approve_merge item should say CI not run |
| rtr5 | truth | low | n | - | N | carried records lack provenance |
| rtr6 | truth | low | n | - | K | stack PR close failure invisible |
| rtr7 | truth | low | n | - | N | validation only happy paths |
| rre1 | reversibility | med | m | - | K | Draft stack PR merge is one-way door |
| rre2 | reversibility | med | m | - | K | Retarget vs branch auto-delete ordering |
| rre3 | reversibility | med | n | - | N | Graph change rollback re-asks approvals |
| rre4 | reversibility | med | n | - | N | No unstack kill switch |
| rre5 | reversibility | low | n | - | K | Old integrate records lack base field |
| rre6 | reversibility | low | n | - | N | Branch namespaces become contracts |
| rco1 | coherence | high | m | GT1 | K | Stack set drops merged deps; deps_conflict exit leads into it |
| rco2 | coherence | med | m | - | N | Combine commit text contradicts S rule (I first if present) |
| rco3 | coherence | med | m | - | N | k notation inconsistent; k=0 impossible |
| rco4 | coherence | low | n | GT8 | K | Stack PR ownership split; base GitHub side effects outside atomic push |
| rco5 | coherence | low | n | - | N | deps_conflict Blocked vs named wait |
| rne1 | necessity | low | n | - | N | Dead I handling in combine commit |
| rne2 | necessity | low | n | - | N | ci.checks snapshot unused |
| rne3 | necessity | low | n | - | N | State why approve_merge decoupled |
| rne4 | necessity | low | n | - | N | Explicit retarget duplicates GitHub |
| rad1 | adversary | high | m | GT1+GT2 | K | S drops merged deps; deps_conflict proceeds without re-running merge-tree |
| rad2 | adversary | high | m | GT7 | K | Humans merging stack PR or dependent PR into dep branch on GitHub |
| rad3 | adversary | med | m | - | K | current integrate record not tied to live head |
| rad4 | adversary | med | m | GT12 | K | merge must read PR base live |
| rad5 | adversary | med | n | GT3 | K | deps_conflict waits forever if dependency closed without merging |
| rad6 | adversary | low | n | - | K | Deleting dep branch without merging closes dependents |
| rad7 | adversary | low | n | - | K | merge-tree takes two commits; k>=3 undefined |
| rar1 | architecture | high | m | GT1+GT2 | K | S drops merged deps; conflict dropped not resolved |
| rar2 | architecture | med | m | - | N | Combine commit not deterministic |
| rar3 | architecture | low | n | GT6 | N | Redundant combine for transitive deps |
| rar4 | architecture | low | n | GT8 | K | Stack PR ownership split; base GitHub calls |
| rar5 | architecture | low | n | - | K | Dependent integrate record shows stale base |
| rse1 | security | med | m | - | K | Draft stack PR mergeable; add failing status |
| rse2 | security | low | n | - | K | Retarget picks foreign PRs |
| rse3 | security | low | n | - | K | Approval binding across restacks |
| rpe1 | performance | med | n | - | N | Restack cascade O(n^2) |
| rpe2 | performance | low | n | - | N | CI on stacked PRs wasted |
| rpe3 | performance | low | n | - | N | Batch ref reads |
| rpe4 | performance | low | n | - | N | k-1 merges in one pass |
| rcc1 | concurrency | high | m | GT11 | K | Stack-branch deletion closes goal's own PR before retarget |
| rcc2 | concurrency | med | m | - | K | Retarget-then-delete race in merge |
| rcc3 | concurrency | med | m | - | N | Combine commit not deterministic |
| rcc4 | concurrency | low | n | GT8 | K | base push and gh pr close not atomic |
| rcc5 | concurrency | low | n | - | K | integrate target from stale base record |
| rmi1 | migration | high | m | - | N | Downgrade: old engine misreads stacked records |
| rmi2 | migration | med | m | - | K | Old integrate records lack PR base |
| rmi3 | migration | med | m | - | K | Fingerprint changes on upgrade re-ask approvals |
| rmi4 | migration | low | n | - | N | Burst of stacking after upgrade |
| rmi5 | migration | low | n | - | N | Orphaned stack artifacts |
| rux1 | ux | med | m | - | K | Stack PR misuse not handled |
| rux2 | ux | med | m | - | N | deps_conflict wait message unspecified |
| rux3 | ux | low | n | - | N | Approval before CI not signalled |
| rux4 | ux | low | n | - | N | Stacked PR checks confusing |
| rux5 | ux | low | n | - | N | Goal PR should link stack PR |
| rux6 | ux | low | n | - | N | Retarget diff window |

### C.3 Prompt control (hypothesis lenses without the guidance, draft 1)

| Lens | Findings (guided → raw) | Harmful | Adopt | Nit+noise | Verdict (guided → raw) |
|---|---|---|---|---|---|
| Intent | 5 → 7 | 5 | 1 | 1 | changes → changes |
| Simplicity | 6 → 8 | 4 | 3 | 1 | approved → changes |
| Safety | 5 → 7 | 6 | 0 | 1 | changes → changes |
| Scale | 6 → 8 | 2 | 0 | 6 | changes → changes |
| Experience | 7 → 8 | 2 | 1 | 5 | changes → changes |

The raw lenses found no harmful issue that the guided set missed. They did raise one new adopt-only point: Simplicity's "skippability stored twice". That point became D6's wiring validation.

### C.4 Cost

Each subagent run read the spec and the document under review: about 41–43k tokens and 25–41 s on the draft, and about 34–36k tokens and 23–51 s on the replay. The Sonnet filter took about 36–45k tokens and 17 s. Per-lens cost differences were within 5%, so cost is per lens, not per kind of lens.
