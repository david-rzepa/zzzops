# G1022 review_design (attempt 2)

**Verdict: approved.** Revision 2 (blob 496ddd5) resolves all four findings from attempt 1. It is consistent with G1017's case 3, G1024 and G1025, and I found no new problem that would change the design. None of the open choices calls for an owner question under rule 4; my reasons are below.

What I read: the edited spec (blob 6400218; only the docs/design acceptance line changed), the full diff from revision 1 to revision 2, G1022's goal state (`depends_on` is now `[1000, 1020, 1017]`), G1025's spec and the release fields of G1003, G1017, G1022, G1024 and G1025 (all Release 1). I checked the code claims against `origin/zzzops/pr/g1020` (5410809).

## Prior findings

- **review_design:1:1 (Missing lens searched the wrong tree): resolved.**
  - `lens_missing.md` gains "Search the subject's own tree, not `read_dev`: `git grep <pattern> <code.commit>` …".
  - The `review` instruction gains "on code, against the subject's own commit (`code.commit`)".
  - Test 3 asserts both, and A.5 records that the reviewer reads git objects, not a worktree.
  - The G1018 checkpoint view does carry `commit` (card.py:57), so the command is runnable as written.
- **review_design:1:2 (G1017 alignment): resolved.**
  - Case 3 is adopted: `depends_on` and the spec acceptance line are updated, and §12 becomes the edits this PR makes, plus the HISTORY §4 row and deleting the pending row.
  - G1017 is in the delivery order, test 15 runs G1017's guard, and §13 step 3 sends the full section list.
  - The guard's marker (`workflow.json lacks "\"truth_design\""`) matches on this tree, so deleting the row is enforced.
  - A fallback covers G1017 dropping case 3.
- **review_design:1:3 (G1024): resolved.**
  - §8 now names G1024's `policy_update` item as the notice, and MIGRATING as the procedure for a restructured `workflow.json`.
  - It lists the added and removed files for both 12-node and 26-node starting points, which I checked against the template prompt lists.
  - The provenance record is refreshed by `zzzops/policy/lenses` if G1024 lands first.
  - The version is "next minor at merge, whichever merges second takes the next number".
  - G1024 and G1022 are both Release 1, so the release-gating note costs nothing.
- **review_design:1:4 (migration stale keys and budget): resolved.**
  - `review_impl` drops `spec` (D6), so its inputs equal graph12's (`doc`, `tests`, `code`; `checks` is context).
  - The stale keys are therefore `["def", "lenses"]`, against `["def", "lenses", "policy.intent"]` for `review_design`. All are exempt under the extended `frontier.counts`, and test 11 asserts that `budget.used` does not change.
  - MIGRATING and a new test cover the 60→27 default limit for goals moving from the 26-node graph.

The review notes from attempt 1 were also taken up: `Graph.lenses` is renamed `Graph.reviewers`, and the `security` and `code_quality` instructions return to `review_impl` and are asserted on its card.

## New content checked

- **§8a (G1025).** It matches G1025's spec:
  - The release cut waits for every release-N goal (item 1).
  - Merge commits and `change` identity are G1025's open question (item 4).
  - G1025 depends on G1017, not G1022, so handing it the "15-node graph" note is the right direction.
  - Searching `code.commit` stays correct when the base is a release branch.
  - No G1022 mechanism assumes linear history.
- **Dropping `spec` from `review_impl`.** Compliance judges against the approved design, which `approve_design` and its Intent lens already approved against the spec. This matches the measured A.4 Compliance text ("what the approved design says") and the 12-node node.

## Owner questions: none

Under rule 4, I considered three choices:
- **The `<node>:<lens>` skip-key syntax.** It is an inherited format. But the spec explicitly delegates "node input, goal field or skip mechanism" to the design, and the skip form clearly dominates. It reuses reasons, refusals and the existing approval and PR display, and needs no new `GOAL_KEYS` entry that would make 1.1 engines refuse every goal.
- **The default budget falling from 60 to 27.** This is bounded. The formula is unchanged and rounds per subject stay about equal. A goal or project can set `budget`, and MIGRATING says so.
- **Which lenses are mandatory, and no project-intent check at the implementation stage (D6).** This is bounded: both are `workflow.json` policy entries, and restoring `policy: ["intent"]` on `review_impl` is a one-line reviewed policy change. The mandatory set follows the spec (Intent at implementation is Compliance; Simplicity at design, Craft at implementation; Missing). The design records its reasoning.

## Notes (non-blocking)

- Test 15 says "a reviewer diffs §12's list against the SPEC/DESIGN diff". That is a manual check. `review_impl`'s Compliance lens is the natural owner of it, and no extra engine check is needed.
