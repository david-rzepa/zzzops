# G1017 review_design, attempt 3: re-review of design revision 3

**Verdict: approved.** Revision 3 fixes both of my attempt-2 findings, and I have no new ones. Every contract-changing goal that has not merged is now ordered against G1017 by a dependency, in one direction or the other. So the tree-marker guard only trips in the owner goal's own PR, and that holds even though dev does not use strict status checks. G1024 is in the inventory, and the keyword search has been replaced by a classification based on what each goal changes.

I checked the design against read_dev `a05fb97`, the goal state branches, the PR branches `zzzops/pr/g1000` and `zzzops/pr/g1020`, PR #750, and `references/CLI_USAGE.md`.

## Prior findings

- **review_design:1:1: resolved** (unchanged from attempt 2).
- **review_design:2:1: resolved.**
  - The new subsection "What CI can and cannot see here" states the facts correctly: strict status checks are off, CI runs only on `pull_request`, and G1021's check catches textual conflicts only. It withdraws both claims from revision 2.
  - Case 3 allows a pending row only for a goal with `1017` in `depends_on`. That goal's base contains docs/design and its own row, so its own PR is the first tree that holds both its code and its row, and the guard trips there.
  - Case 2 turns a goal that is past implement but unmerged into a G1017 dependency, with no row. This is what I asked for. I checked G1020: integrate is done, and #750 is still open, so the "if unmerged at approval" branch is live.
  - The README Repair paragraph covers a hand merge or a dependency that `edit` removes.
  - `edit` supports `depend`, per CLI_USAGE, so every root action the design names can be run.
- **review_design:2:2: resolved.**
  - G1024 now has a row. Its sections are plausible for its spec: the provenance record, `policy_update` in `next` and `validate --policy`, the decline and the missing-record item, and bootstrap. Its marker is sound: `policy_update` appears in no file under `plugins/zzzops/zzzops/engine` on `a05fb97`, on `zzzops/pr/g1000` or on `zzzops/pr/g1020`, so the row will not fail as soon as it is added.
  - The behavioural classification lists the right kinds of change. Applied to today's open goals, it gives a sensible split:
    - G1004, G1005, G1007, G1008, G1009, G1010, G1011, G1012 and G1019 get `depends_on` 1017 and a docs/design acceptance line. I checked their state branches: none of them has any records, so the edit loses no work.
    - G1006 and G1013 are left out.
    - G1002 and G1003 already depend on G1017.
    - G1023 is correctly classified as not changing the contract, because its wording is already written into SPEC under G1016's row.

## Non-blocking notes

- **Backlog goals without a row** depend on their own reviews to catch a missing docs/design edit, because the guard cannot see them. This is an acceptable trade-off, and the design states it.
- **The four acceptance-line edits plus the 1017 dependency** mean those goals' `base` waits for G1017 to integrate. G1017 is a docs-only change and is nearly done, so the delay is small. Still, the root should run the edits soon after approval, together with the G1022 and G1024 edits.
- **Goals created before G1017 merges** rely on the add-goal step remembering to add `1017` to `depends_on`. The window is short, but the root should keep this in mind until G1017 merges.
