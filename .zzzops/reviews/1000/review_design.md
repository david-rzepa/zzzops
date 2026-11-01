# G1000 review_design, round 3: re-review of design revision 4

**Verdict: approved.** Revision 4 closes the skip window that `review_tests` found, and it opens no new material hole. The new rule says that `edit` refuses a new `skip.<n>` while `n`'s latest record has any open finding that is not a note. That rule is stated the same way in D6, §5 and §17 §4.18. It is tested in §13 journey 6. Both of my prior findings stay resolved. I have two non-blocking notes below.

I checked against design revision 4 (blob 5ed045b), the diff from revision 3, `review_tests-1000.md` and `read_dev` 1c1387a.

## Prior findings

| id | status | why |
|---|---|---|
| review_design:1:1 (F1, filter blind to new notes) | resolved | Unchanged since round 2. The filter's fingerprint includes `candidates`, and a note with no verdict counts as kept (§7, §17 §4.9). |
| review_design:1:2 (F2, owner and trigger for rollout steps 2-3) | resolved | Unchanged since round 2 (§12). |

The `review_tests` finding (review_tests:1:1, a skip during the join window) is answered as well. See the next section.

## The new rule

**It closes the window.**
- Before revision 4, the refusal applied only to *live* findings. A filtered lens's findings are not live until its filter is fresh (§7).
- The rule now covers every open finding except a note. A note is an open finding with the verdict `note` on its filter's fresh latest record.
- So a finding counts whether it is live, waiting for the filter, or waiting for re-review. Between the lens's submit and the filter's fresh submit, the finding is open and has no fresh `note` verdict, so the skip is refused. This is exactly the I22 case: skip the lens after it has raised a finding.

**"Note" is judged only from a fresh filter record.** "Fresh" is §7's definition: the input fingerprint covers the recorded values and the current candidates.
- A lens re-run that adds a new note makes the filter stale (the F1 fix). The new note then has no verdict, so it blocks the skip.
- An old `note` verdict on a stale filter does not count either.
- So nothing can be classed as a note without a filter verdict that is current for the current candidate set. The rule fails toward refusing.

**A re-running lens.** "Latest record" is the previous record. If that record holds open findings that are waiting for re-review, they block the skip. That is correct.

**Unfiltered review nodes (older graphs).** These have no filter, so every open finding blocks a skip. That is stricter than 1.0, but only as an `edit` guard. Records, frontier and cards stay the same, so I3/I4 hold.

**The waiver is visible.**
- `render.py:196` already lists waived findings on approval items ("waived: ...").
- The refusal message points to `status="waived"` with a `note`.
- So the skip-after-waive path shows up on `approve_design` and `approve_merge`, as D6 asks.

**Consistency.** D6, §5, §13 journey 6, §17 §4.18 and the revision-4 changelog all state the same predicate. §5 also says the rule reuses §7's note test, which keeps the implementation small.

**Tests (§13 journey 6).** Three cases are added:
- a skip refused before `filter_design` runs, while another lens is still running;
- the same skip accepted after a visible waiver;
- a skip allowed when the lens's only open findings are notes judged `note` on a fresh filter.

These cover both sides of the predicate. The added per-lens independence assertion and the intent-staleness check at the implementation stage answer `review_tests`' two notes.

## Non-blocking notes

1. **A lens with no record yet, or one re-running from a clean record, can still be skipped while it runs.**
   - Its latest record has no open finding, so `edit` accepts the skip.
   - Then the lens submits. `verbs.submit` checks only the lease, not the skip, so the record lands. Frontier drops it (`frontier.py:150`), and any material finding in it goes unseen.
   - This is not the I22 attack, because nobody can see a finding before its submit. It is also the same as skipping before the lens starts, which the human sees as "skipped: <reason>".
   - Still, a recorded material finding that nobody ever shows is a small "silent drop". It is cheap to close in implementation in one of two ways:
     - `edit` adding `skip.<n>` also ends `n`'s valid lease, so the submit is refused with "superseded";
     - or approval items list the open findings on skipped nodes.
   - Optional. The engine behaves this way for any node today.
2. **`edit --set ...status="resolved"` bypasses the waiver display.** An edit can mark an open finding `resolved` instead of `waived`, and then the skip is accepted with "waived: none" on the item. This is not new; revision 3's rule had the same gap. It is still visible in git history, and the skill rule requires the human's words. One way to close it: the refusal message names only `waived`, and `edit` refuses to set `resolved` on a finding. That is a possible follow-up, not a design change.
