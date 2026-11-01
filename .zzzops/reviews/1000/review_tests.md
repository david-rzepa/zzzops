# G1000 review_tests: independent review of the lens tests (a5b5579)

**Verdict: changes requested, on `design`, for one gap.** The tests themselves are sound. The fixture freeze weakens no existing test. The new file covers every item of §13 and the goal's acceptance. All 46 new tests that should be red are red, and they fail because the feature is missing. The test writer flagged one gap: a lens can be skipped while its findings are waiting for the filter. That gap is material. It reopens the "skip the objecting lens" attack (I22), which D6 exists to close. The fix is one sentence in the design plus one test case.

I reviewed against design revision 3 (`design-1000-3.md`), its round-2 review notes, and `read_dev` 54d7e83 / a5b5579. The diff reviewed is `git diff 54d7e83 a5b5579`: 13 files, +1408/−2.

## 1. The fixture freeze weakens no existing test

- `.agents/fixtures/graph12/` is byte-identical to the 54d7e83 template. I diffed all ten files (`workflow.json`, `POLICY.json` and the eight prompts) and found no difference.
- `engine_fixtures.py`: `TEMPLATES` now points at the fixture, and `SHIPPED` is new. `load_template`, `prompt_exists`, `World.bootstrap`'s prompt copy, `DEFAULT_NODES`, `RENAME` and `renamed_workflow` all go through `TEMPLATES`. So every engine test (base, frontier, portfolio, lifecycle, ops, github, checkpoint, schemas, store, names) now runs on the frozen graph, and the engine tests no longer depend on the shipped graph.
- These are the only existing-test changes:
  - `test_engine_docs.py`: one line, `TEMPLATES` becomes `SHIPPED`. The test's purpose is that the shipped template validates without a repository, and it keeps that purpose. After implementation it passes with rc 0 (a warning is not an error).
  - `test_engine_store.test_validate_policy_dir_needs_no_repository` and `test_engine_schemas.test_shipped_templates_validate` now check the fixture instead of the shipped template. That is no loss of coverage: `ShippedTemplateTests.test_shipped_templates_validate` and the `validate --dir` tests cover the shipped template.
- No existing test was removed. The full suite at a5b5579 ran 430 tests: 384 pass and 46 fail, and every failure is in `test_engine_lenses.py`.
- Tests that still read the shipped template on purpose: `test_marketplace_bundle`, `prompt_stats`, `claude_plugin_acceptance` and `test_plugin_cachebuster`. They follow the shipped graph, which is correct.

## 2. Coverage of §13 and the acceptance

| §13 / acceptance item | Test(s) |
|---|---|
| Template passes with exactly one `intent_placeholder` warning; no intent fails; every node has a prompt; names test | `ShippedTemplateTests` (validate ×3, `test_every_node_has_a_prompt…`, `test_engine_source_names_no_shipped_node` over the 26 ids) |
| Journey 1: seven lenses in parallel, distinct holders | `test_1_…` (the filter is blocked while they run) |
| Journey 2: design current until the filter submits, then reopens once | `test_2_…` (approve_design blocked, records `ok`, the candidates' shape, `correction_runs == 1`) |
| Journey 3: re-review with `previous.changed` | `test_2_…` second half (`git diff <old> <new>` on every lens) |
| Journey 4 and 7: skip with reason; approve item lists the filter and every lens | `test_4_and_7_…`, and `test_a_skipped_approval_still_waits…` (§3 `base`) |
| Journey 5: `new` refuses a non-skippable skip | `test_5_…` (intent, simplicity_impl, filter, approve_merge) and `test_edit_refuses_a_skip_of_a_non_skippable_node` |
| Journey 6: `edit` refuses a skip of a lens with live findings | `test_6_…` (with waive-then-skip) |
| Journey 8: PR body lists every code lens and the skips | `test_8_…` (through to merge) |
| Filter: note stays current; material reopens; borderline `keep` reopens; missing or extra verdict refused | `FilterTests` (the extra-verdict cases cover a material id and an unknown id; also a bad verdict value and a missing reason) |
| Notes on the next card and on the approval item; notes not counted | `test_a_note_judged_note…`, `test_a_note_promoted…` |
| Crash-looping lens leaves the filter visibly blocked | `test_a_crash_looping_lens…` (also: no `skip` option for a non-skippable lens) |
| F1 unjudged note, intent change and `rev` bump, keep and note; `stale_because == ["candidates"]`; not budgeted | `test_unjudged_note_*` ×4 |
| Missing verdict fails safe | `test_a_fresh_filter_record_without_a_verdict_keeps_the_note` |
| Filter independence at `start` | `test_a_filter_holder_who_produced_the_subject_is_refused` |
| Intent card; stales only `intent_*` (budget-exempt); placeholder; shape kind | `IntentTests`, `IntentShapeTests`, `test_real_intent_gives_no_warning…` |
| Pointer: stale lease records no `reviewed`; missing blob says "review in full" | `PointerTests` |
| Renamed graph | `RenamedLensJourneyTests`, `RenamedFullLensJourneyTests`; the frozen rename test is kept |
| Prompt budgets | `prompt_stats.py --check` in the commands |
| Wiring validation (optional and required filter inputs, one subject per filter, `skippable` boolean) | `LensSchemaTests` |
| Unfiltered reviews unchanged (I3/I4) | `test_unfiltered_reviews_and_humans_are_unchanged` |
| Re-confirming the same notes keeps the filter fresh (round-2 review's no-loop point) | `test_a_lens_reconfirming_the_same_notes…` |

## 3. The choices fixed in the docstring are consistent with the design

- **Verdict shape** `{"<id>": {"verdict": "keep"|"note", "reason": text}}`, exactly for the non-material candidates. This matches §7 ("keep or note, with a reason, for exactly the non-material candidates"). It also keeps the verdict out of the finding's own `note` key, as the round-2 review's third note asked.
- **`previous.changed`** contains `git diff <old blob> <new blob>`. This matches §8.
- **`reviewed` keying**, `reviewed[<output key>] = {blob, commit}`. This matches §8 and today's per-output keying in `records.reviewed`. A 1.0 `card.previous` skips such entries, because both `change` values are `None`, which agrees with §12's compatibility claim.
- **"not skippable" message.** This matches §5's text.
- **Waive through `edit --set records.<lens>.findings[<id>].status="waived"` plus a `note`.** This is the existing `apply_sets` element path and the existing `waived` status, and it is the visible waiver that D6 asks for.

None of them contradicts the design.

## 4. Finding: a skip can drop a lens's findings while they wait for the filter (target `design`)

**What happens.** D6 and §5 refuse a new `skip.<n>` only while `n` has *live* findings. Under §7, a filtered lens's findings are not live until the filter is fresh. So the refusal does not apply between the lens's submit and the filter's next fresh submit. In that window, `edit --set skip.<lens>="…"` is accepted. Frontier's `R` drops skipped nodes (`frontier.py:148`), so those findings never become candidates and never reopen anything.

**Why this is not a corner case.** The window is not rare. Every round has one, because the filter is the join (D3). It stays open until the slowest lens finishes, or indefinitely while another lens crash-loops (§7 "Join"). It is also exactly when an interested party knows the finding exists: the finding is on the work branch, and it is the target author who is waiting for it.

**Impact.** A material finding the target has never seen is deleted by a one-line edit. The human sees only "skipped: <reason>" on `approve_design`, not the finding. That is the "visibility of skips alone, without the refusal" alternative that D6 explicitly rejected, and it brings back I22 (adjudged harmful; Adversary ad2: "Skip the objecting lens after it raised a finding; findings die"). The skill rule "a skip added after `new` needs the human's words" is guidance, not enforcement.

**Fix (one sentence in D6/§5 and §17 §4.18).** `edit` refuses a new `skip.<n>` while `n`'s latest record has an open finding that is live **or waiting for its filter**. "Waiting" means open, its `target_fp` matching the target's current output, the lens's own record fresh, and no `note` verdict on a fresh filter. That predicate is the liveness test without the filter-fresh condition, so the implementation shares pass 1's code. A simpler alternative: refuse while `n` has any open non-note finding. That is stricter, because prior findings that are waiting for re-review would also need a waiver. Waiving first remains the visible path.

**Tests.** `test_6` should gain a case: a lens with a material finding, the filter not yet run, and `edit skip.<lens>` refused. The current `test_6` covers only the post-filter (live) case.

## 5. The tests fail for the right reason

I ran the full suite in a temporary detached worktree at a5b5579 (since removed).

- `python3 -m unittest discover -s .agents -t .agents -p 'test_*.py'`: 430 tests, 41 failures and 5 errors, all in `test_engine_lenses.py`. The rest pass.
- Each failure names a missing feature:
  - `settings: unknown key 'intent'`. This refuses `new` in every World-based test, and makes `test_5` see `policy_invalid` instead of "not skippable".
  - `unknown field 'skippable'`.
  - `KeyError: 'filter_design'` and `KeyError: 'intent'` in the template tests, because the shipped graph has no such nodes or keys yet.
  - No `intent_placeholder` warning, and no lens prompts.
  - The 26-node list differs.
- 6 lens tests pass now, legitimately:
  - the frozen-fixture check;
  - the shipped-node names test;
  - human prompts starting with a question;
  - intent optional;
  - other settings still rejecting extras;
  - non-text intent values failing.
  These are regression guards. The last one passes today only because `intent` is rejected outright, and after implementation it guards the new shape kind.
- Caveat (inherent, not a finding): the World-based tests all stop at their first step until intent validation lands, so their later assertions are first exercised during implementation. I read them by hand against the design (§3 above) and found them consistent.
- Brittleness is acceptable. State strings (`ready (stale: candidates)`, `ready (stale: policy.intent)`) follow the engine's existing `state_string` format. Item checks use substring matches on the JSON.

## Notes (non-blocking)

1. **Per-lens reviewer independence (acceptance "Reviewer independence holds per lens").** It is exercised only implicitly. `Pilot.start` silently skips agents that hit an `independence` error, and `test_1` uses fresh holders. One assertion would make it explicit: the designer's `start` on a lens is refused with `independence`. It goes through the same `review.subject` path that the frozen-graph tests already cover, so this is cheap but not required.
2. **"Changing intent stales only `intent_*`"** is checked at the design stage only, before `intent_impl` exists. That is enough for the rule.
