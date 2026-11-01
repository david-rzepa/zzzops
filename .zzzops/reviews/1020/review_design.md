# G1020 review_design

**Verdict: changes requested. One finding, a one-line fix to the design's material predicate.** The rest of the design is sound and I checked it against G1000's code at `fd32b9e`.

## Finding

**F1 (design): the "material" predicate inverts the engine's default.** Section 3 says a filtered lens may answer `approved` unless an open finding has `f.get("material")` true. Everywhere else in G1000 a finding with no `material` key counts as material:
- `card.candidates` uses `f.get("material", True) is not False` (card.py:168).
- `fingerprint` documents and uses the same rule (fingerprint.py:50-56).
- `frontier` treats only `material is False` as a note (frontier.py:296).

Built as written, a lens could answer `approved` while one of its open prior findings has no `material` key. The filter would treat that finding as material and reopen the subject, so behaviour does not change. But the lens's `approved` would be false: it would approve while holding a finding the engine counts as material, which is exactly what the decision says cannot happen. New lens findings always carry `material`, because schemas.py:1014 requires it. So the gap is limited to prior findings recorded without the key, for example after a policy change attaches a filter to an existing review node, or after the G1000 rollout moves in-flight goals. **Fix:** state the predicate as "any open finding with `f.get("material", True) is not False`", matching `candidates`/`fingerprint`, and ideally share one helper. Add a test case to test 3: an open prior finding without `material` makes `approved` refused.

## Checks that passed

- **The filter still judges notes.** `process_findings` forces `ok = True` for any filtered lens, and `card.candidates` lists every open lens finding whatever the decision. `decision` is read only in `records.process_findings` and `verbs.outcome_of`, and nowhere in `frontier`, `fingerprint` or `candidates` (checked with `git grep decision`). Allowing `approved` with notes therefore changes no candidate set or promotion. `keep` still reopens the subject.
- **Unfiltered reviews are unchanged.** The relaxation is gated on `graph.filter_of(X)`. In the template, `review_tests` has no filter. Human approvals go through `human_findings` and `answer`, which do not touch this check. Test 5 covers `review_tests`.
- **`outcome_of`.** Changing the head to "approved with N note(s)" when `decision == approved` is right. Op callers in `ops/run.py` have no `decision`, so they still read `failed`.
- **The `output_schema` hint** is the only place a lens learns the rule. Changing it only for filtered lenses is correct. `git grep "approved only"` finds only card.py:183, so no CLI_USAGE edit is needed.
- **Targeting sentence.** The `review` instruction goes only to the 14 lens nodes (template workflow.json). `test_design` is an ancestor of every `*_impl` lens through `implement`. Putting the sentence in the instruction rather than in seven prompts is the cheaper and single-source choice. **Non-blocking placement note:** inserting it straight after "Raise a finding only when … idea)." separates the `material` definition from "An independent filter may promote a note; it never demotes a material finding", which explains it. Put the sentence after the filter sentence, or before "On a re-review", so the impact/material/filter text stays together. This is wording only and needs no new round.
- **`lens_truth.md`.** At fd32b9e it has two "On code:" sentences. The merged sentence keeps both questions.
- **ENGINE_VERSION.** Stored records are not checked for consistency between decision and findings (schemas.py only checks the enum). A 1.1.0 engine reading a record written by 1.1.1 behaves the same, so `REQUIRES_MIN` correctly stays put. The only effect of mixed engines is that a 1.1.0 worker refuses an approve-with-notes submit and the lens resubmits `changes_requested`, which is benign. The conditional bump note is adequate. Because G1020 stacks on G1000, "G1000 lands first" will normally hold, so in practice the bump is to 1.1.1 unless both land in one integration.
- **Tests** cover the spec's acceptance: a card snapshot on `truth_impl`/`intent_impl`, approval-item rendering for a notes-only lens with promotion, and `prompt_stats --check`.
