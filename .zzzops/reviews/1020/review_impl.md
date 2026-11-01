# G1020 review_impl (commit 70531e8, base 6d4715a = origin/zzzops/pr/g1000 head)

**Verdict: approved, no findings.**

## Scope
- `git log 6d4715a..70531e8` holds only G1020 commits (design/review docs, tests 5ae4e84, impl 70531e8). Base equals G1000's PR head.
- Diff touches only engine (card, fingerprint, frontier, records, schemas, verbs), template `POLICY.json`, template `lens_truth.md` and the new test file. No `.zzzops/` change outside reviews.
- Frozen tests: `git diff 5ae4e84 70531e8 -- .agents` is empty; tests not weakened.

## is_material
- Defined once in `engine/schemas.py`: `f.get("material", True) is not False`, as the design says.
- Used in `card.candidates`, `fingerprint.candidates` (same expression as before), `frontier.is_note` (`not is_material(f)` is equivalent to the old `f.get("material", True) is False`) and `records.process_findings`. No behaviour change for existing callers.

## Filtered-lens approval rule
- `approved` is refused when any open finding in `result` is material. `result` includes carried prior open findings (which keep their stored keys), so a prior finding without `material` blocks approval. New lens findings always carry `material` from the submit. A material finding cannot get through.
- `changes_requested` still requires an open finding; `ok` is still forced True afterwards for filtered lenses, as before.
- Unfiltered reviews (`review_tests`, other reviews) keep the old `elif` branch and message unchanged. Human approvals go through `human_findings`, which is untouched.

## Hints, outcome, template
- `output_schema` decision hint: the new text for `graph.filter_of(n)` only, the old text otherwise.
- `outcome_of`: "approved with N note(s) → targets" when decision is approved and findings are open. Only a filtered lens can reach it, since every other approved path refuses open findings. Pluralisation is right.
- `instructions.review` sentence sits right after the filter sentence and before "On a re-review", wording as designed.
- `lens_truth.md` now has a single closing "On code:" sentence, matching §2.
- There is no "approved only" text in the non-Python plugin docs, so no CLI_USAGE edit is needed. No ENGINE_VERSION bump is correct while G1000 is unmerged (design: bump only if G1000 lands first).

## Evidence
context.checks passed: the polish tests (12), test_engine_lenses (61), prompt_stats --check, and the full suite.
