# review_design for G1026 (attempt 6)

Subject: design revision 7 (blob 3ddfcf8), against revision 6 (blob 817343d, approved before). read_dev 25186a5.
Frozen tests: the test_design checkpoint aec3870 (`.agents/test_engine_owner_questions.py`).

## Verdict

Approved. Revision 7 makes only the two changes it claims. The new node set fits the shipped graph and the frozen
tests. No finding is open.

## What changed (r6 to r7, `git diff 817343d 3ddfcf8`)

Five hunks, 21 lines added and 10 removed, all inside the sections the revision-7 note lists:
- the revision-7 note (new);
- the revision-5 3:2 note: the subject is now `graph.subject(n) or graph.filter_subject(n)`, and a pointer to the
  wider approve set;
- D5: approve items read the non-descendants of the item's node; the PR body reads the non-descendants of the op
  that writes it; the card subject is as in 3:2;
- §5: the card row, the approve-item row (`{m for m in nodes if X not in graph.ancestors(m)}`), the PR-body row
  and the closing sentence;
- §6: the task card, `next` and the PR-body contract lines.

Nothing else changed. The frontier, record schema, fingerprints, shrink step (revision 6), filter refusal, prompts
and tests plan are byte-identical to revision 6.

## The rule against the shipped graph

I built the graph with `schemas.build_graph` from `templates/default/workflow.json` at read_dev. That is the
15-node graph. The repository's own `.zzzops/workflow.json` is a 12-node graph without the adversary and filter
nodes. Here `S(X) = {m | X not in ancestors(m)}`. `Graph.ancestors` leaves out the node itself, so X is in S(X):
- `approve_design`: S = its ancestors (design, review_design, adversary_design, filter_design) plus itself.
  Nothing runs beside it, as the design says. Its own answers are approvals, which D4 drops.
- `approve_merge`: S = all nodes except `merge`. Its ancestors are the 12 nodes review_tests named. The only
  node beside it is `integrate`, so `integrate`'s answers are listed.
- PR body (`integrate`): S = all nodes except `merge`: integrate's ancestors, integrate itself and
  `approve_merge`. This matches the design. `ops/integrate.py` builds `pr_body` on every run and edits the PR when
  the body differs (lines 165-176), so "the run after the answer lists it" holds.
- Subjects: `graph.subject()` is None for `filter_design` and `filter_impl`. `filter_subject()` gives `design`
  and `implement`. The other review nodes get their subject from `review.subject`. The new expression therefore
  gives the six cards D5 names. (`approve_design` and `approve_merge` also have `review.subject`, but human nodes
  get no task card, so the card rule does not reach them. This was the same in revision 6.)

## The frozen tests at aec3870

- `OpDecisionTests.test_an_answered_integrate_question_is_listed_with_kind_op` expects exactly one entry, the
  `integrate` op answer, on `approve_merge`. Under the new rule it passes. Under revision 6's rule it failed, which
  was review_tests 1:3.
- `DurabilityTests` (the `approve_design` item lists A and B, the `approve_merge` item lists both, the PR body has
  two lines): all of these answers are on `design`, which is in every set. They hold.
- `OwnerJourneyTests` and `test_long_answer_*` (the `approve_design` item): the answers are on `design`. They hold.
- `ReviewCardDecisionTests` (review_design, adversary_design, filter_design and review_impl carry the design
  entry; implement carries none): this is consistent with the card rule as revised.
- `render.human_decisions(git, tip, g, graph, nodes)` takes the node set from its caller. The new rule does not
  touch its tests.

So no frozen test needs to change, as the design says. A cosmetic note, not a finding: the module docstring
(lines 16-17) still says approve items read "their ancestor nodes". test_design may update it if it runs again.
No assertion depends on it.

## Prior findings

- review_design:4:1: resolved in revision 6. It is not open, so it is not restated.

## Findings

None.
