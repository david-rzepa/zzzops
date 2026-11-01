# Review of the implementation: G1000, attempt 1

**Subject:** code checkpoint e270a25 (base 54d7e83). It holds three commits: 5281509 (engine), d40bb54 (templates) and 9b1fbaa (docs). The frozen tests are at 12e8d29.
**Measured against:** design revision 4 (`.zzzops/reviews/1000/design.md`) and the delegate's approval directive (`approve_design` attempt 2). The directive requires that approval items and the PR body list open findings recorded on skipped nodes.
**Checks:** `run_tests` passed. It ran 438 tests, then the 61 lens tests, then `prompt_stats --check`, all on tree 221f1d8.

## Verdict

**Approved. There are no material findings.** The change delivers the design: the seven lenses and two filters, the filter-as-join, promote-never-demote, `candidates` freshness, skip refusals, `settings.intent`, `previous.changed` and the `## Reviews` PR section. The implementation stays small and Git-native (about 400 lines of engine code). One cross-goal hand-off is missing: the extra validation rules are not recorded for G1017. That needs a root action, not an `implement` change (see "Follow-ups for the root").

## How it was checked

- I read the whole engine diff (`git diff 54d7e83 e270a25 -- plugins/zzzops/zzzops/engine package.py`), the shipped `workflow.json` node by node, every changed prompt, skill and reference, and the fixture freeze.
- The tests are not weakened. No implementation commit touches `.agents/` except d40bb54's one-line bundle count. 12e8d29 changes two lens tests only, as the implementer's findings asked; `review_tests` attempt 3 approved that change.
- The fixture freeze is exact. Each `.agents/fixtures/graph12/*` blob is identical to the 54d7e83 template file (I compared `git rev-parse` for workflow.json, POLICY.json and all eight prompts).
- `.agents/test_marketplace_bundle.py`: the 12→26 change is mechanical. Only the asserted node count changed, and the loop that checks every non-op node has a bundled prompt still runs over all 26 nodes.
- No `.zzzops/` policy file changed. The only `.zzzops/` paths in the range are `reviews/1000/*`.

## Lenses

**Intent.**
- Every row of design §10 is implemented in the files it names.
- The directive is implemented: `render.skips()` adds `open_findings` per skipped node to every approval item, and `integrate.reviews_section()` adds an "open finding … (on a skipped node)" line.
- The scope is not widened. The only additions beyond the design are the validation rules discussed under Truth.
- `ENGINE_VERSION = "1.1.0"`. `REQUIRES_MIN` is unchanged, because the rollout relies on `engine.min` (D8).
- The template carries a `TODO:` intent. `validate --policy` reports one `intent_placeholder` warning (D5).

**Simplicity.**
- The mechanism is the minimum the design asks for: one `fresh` map and one `filter_verdicts`/`is_note` test in frontier pass 1, one `candidates` fingerprint part, one `check_verdicts`, and one `skip_refusal`.
- Two small duplications, neither worth a round:
  - The candidate set is computed twice, in `card.candidates` and `fingerprint.candidates`. They agree, because both drop skipped lenses; `R` excludes skip.
  - `Graph.lenses` caches through `self.__dict__`.

**Truth.**
- Claims match the code:
  - EXECUTION.md: non-skippable nodes, "promote but never demote", skips shown on approvals and in the PR.
  - CLI_USAGE: the `impact`/`material`/`verdicts` shapes match `_check_new_findings` and `check_verdicts`.
  - MIGRATING: the order (floor, then graph), in-flight goals, rollback, and the lens-set checklist.
  - The `skip_refusal` hint: `findings[<id>]` is a real `apply_sets` selector, and test lines 590 and 615 use it.
- The implementer added three validation rules: the filter is not skippable, a lens→filter input is not `context`, and every lens feeds its filter. A fourth is implied (the filter is an agent with `verdicts: object`, not a review). All are sound:
  - A skipped filter would leave `filter_verdicts` returning `False` forever, so every lens finding would be silently non-live. That is the R2 failure mode.
  - A `context` input from a lens, or a missing one, would break the join D3 depends on.

  None of them is listed for G1017 (see the follow-ups).

**Adversary.**
- **Verdicts cannot demote.** `check_verdicts` requires exactly the lease's non-material candidate ids and refuses an extra id with "material findings reopen the work whatever you decide". `is_note` requires `material is False`.
- **A missing or malformed verdict keeps the finding.** `is_note` needs `verdict == "note"`, and a non-dict `verdicts` becomes `{}`.
- **The lens's own label is preserved.** A carried-forward finding keeps `material` (`dict(f, …)` in `process_findings`), so a note is not silently turned blocking, or non-blocking, across rounds.
- **The skip refusal holds through the join window.** It checks the pre-edit record against `res.notes`, which only a fresh filter populates.
- **Non-skippable nodes are refused at `new`/`edit`.** A grandfathered skip (one already in `old`, or read with `reading=True`) does not brick a stored goal after a policy change.
- **Filter independence** goes through `filter_subject`.
- **Residual paths need a deliberate `edit` and stay in Git history, so they are not material for this goal.** An `edit` can forge a verdict, delete the lens record (`records.<lens>=null`) and then skip, or waive with any note. These are the same powers `edit` already has over every finding. The refusal guards against careless skips, as D6 intends.

**Concurrency.**
- The running-lease fingerprint in pass 2 includes `candidates`. A lens that submits while the filter holds a lease therefore makes the filter's submit stale (`L.input_fp != x_fp`). That record is not fresh, its lenses' findings keep waiting, and the filter re-runs once. It does not loop.
- `check_verdicts` validates against the lease's own `fp_parts.candidates`, which is exactly what its card showed.
- `candidates` holds only `[id, material]`. So a designer's `responses` and a resolved target do not stale the filter.
- A candidates-only stale does not count against the budget (`counts`). The lens re-run that caused it does count.
- `reviewed` is written only when `L.input_fp == x_fp` (D7). This now also fixes the latent checkpoint case.

**Rollout.**
- On the 12-node graph, a 1.1 engine writes only `reviewed` artifact entries `{blob, commit}`. A 1.0 engine reads them safely: 1.0 `card.previous` and `render.interdiff` compare `change` (both `None`) and skip, and 1.0 `validate_record` does not check the shape of `reviewed`. This confirms the design's "safe mix" between steps 1 and 2.
- The lens graph uses `skippable`, `review.filter`, `settings.intent` and the new finding keys, so a 1.0 engine rejects that policy outright. Landing it in the wrong order fails closed.
- The three-step adoption is documented in MIGRATING. The root's G1003 hold is a root action at `approve_merge`, not code.

**Experience.**
- The seven lens prompts follow §4 verbatim. Each is one question-led paragraph, clear and philosophical, and the questions matter more than any checklist.
- "Approving with no findings is a good outcome" and the impact/material discipline are in the shared `review` instruction. That instruction is on every lens card (`instructions: ["review", "communication"]`), so it is not repeated in each lens prompt.
- `filter.md` is crisp. It says when unsure, keep; gives the exact verdict JSON; and says "exactly one entry per non-material candidate".
- The skip refusal names the findings and gives the literal waiver command.
- Minor points, none material:
  - `lens_truth.md` has two "On code:" sentences; the design's own text produces that.
  - A lens with only notes must still say `changes_requested`, because "approved" requires no open finding. Approval items therefore show `changes_requested` for lenses that block nothing. The filter summary explains this.
  - The removed `review_impl.md` told the reviewer to target `test_design` for test problems. No lens prompt does now. A Truth finding about tests aimed at `implement`, which cannot change preserved tests, costs a dispute round.

## Follow-ups for the root (not findings on `implement`)

1. **G1017 hand-off.** Add these rules to G1017's input, next to design §17's wiring rule, for SPEC §3.1:
   - a filter is an agent node, not a review, with output `verdicts: object`;
   - a filter is `skippable: false`;
   - a lens→filter input must not be `context`;
   - every lens naming a filter has an input into it.

   Without this, SPEC will omit rules the engine enforces. A graph that is valid by SPEC would then be refused by `validate`.
2. **Step 3 (`zzzops/policy/lenses`).** Consider one sentence in this repository's lens prompts, or in the `review` instruction: "On code, target `test_design` for test problems." This keeps the guidance `review_impl.md` gave.
