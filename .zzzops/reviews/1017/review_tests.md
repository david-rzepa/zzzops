# G1017 review_tests, attempt 1

**Verdict: changes requested, for two gaps.** The guard and its parser are tested well, and the scrub, link, citation and HISTORY-log tests match the design. But two plausible wrong implementations would pass the suite:
1. One that writes the HISTORY §4 rows but never changes SPEC or DESIGN.
2. One that leaves out the case-3 pending rows for G1022 and G1024.

Subject: `.agents/test_design_docs.py` at `559bbb6` (base `8d8437a`, where G1020 #750 has merged). The design is revision 3 (`42144d6`).

## How I checked

- I read all 33 tests.
- I simulated a naive implementation in a scratch copy of `559bbb6`. I copied the rev 6.3 DESIGN, SPEC and IMPLEMENTATION_PLAN into `docs/design/` unchanged, with a stub HISTORY (the two section headings only) and an empty pending table. 12 tests then fail:
  - the amendment index and HISTORY log;
  - the entry-point links;
  - the external folder and local paths;
  - the private data;
  - the README;
  - the shipped docstrings;
  - the source-folder paths;
  - the status lines (×3).

  These are the ones that should fail on such a copy.
- In that same copy, `test_cited_sections_exist`, `test_relative_links_resolve` and `test_moved_documents_keep_their_numbered_headings` pass. So the engine's existing `§` and `Step` citations already resolve against the sources, and those tests are achievable without edits outside scope.
- CI runs the file at the repository root (`run_product_validation.py`). Linux checks out with `fetch-depth: 0`, so `refs/remotes/origin/zzzops/goal/g<N>` exist there, and the depends-on check runs in CI rather than always skipping.

## What is good

- **The guard.** It tests `contains` and `lacks` both ways, escaped quotes, directory markers recursing two levels, the "every file lacks it" rule for directory `lacks`, untracked files being ignored, a directory not matching as a string prefix, a trailing slash, a missing path for both operators, 14 malformed-row cases that error instead of being skipped, a bad row after a good one, duplicates, and a missing or doubled table. The landed message matches the design word for word.
- **Pending rows.** `test_pending_rows_belong_to_open_goals_that_depend_on_g1017` enforces the revision-3 rule: an open goal with 1017 in `depends_on`, and never G1017 itself. It skips cleanly where goal refs are absent.
- **Scrub.** The external folder is checked over `plugins/`, `.agents/`, `docs/`, `README.md` and `AGENTS.md`. Local paths and the name, session and holder-label patterns are checked in `docs/design`. The patterns are built by concatenation, so the file does not match itself.
- **Links and citations.**
  - Relative links, with heading anchors checked inside `docs/design`.
  - Engine and test `SPEC §`, `DESIGN §` and `Step N` citations against the real headings, with a floor of more than 30 citations so the test cannot pass vacuously.
  - REV5/REV6 ids against the HISTORY amendment index.
- **HISTORY log.** `MERGED_AMENDMENTS` lists exactly the goals in G1017's base (#742, G1014, G1018, G1001, G1015, G1016, G1000, G1021, G1020). G1023 is correctly absent.
- **Robust to later goals.** Goals landing later (G1022, G1024, G1025, G1027) only add HISTORY rows or delete their own pending rows, and nothing here breaks when they do.

## F1 (target: test_design): nothing checks that SPEC and DESIGN were actually amended

The goal's acceptance, and the design's "Applied by G1017" table, require the documents to describe the engine at the base. Every test passes if HISTORY §4 gets one row per goal and SPEC and DESIGN stay at rev 6.3 apart from the scrub and the status lines. That is the cheapest wrong implementation, and its failure is exactly the drift this goal exists to remove.

**Fix.** Add one sentinel per applied amendment: a contract term that the amendment introduces and that rev 6.3 lacks. Assert that each one appears in SPEC.md (or DESIGN.md). Each candidate below is absent from the rev 6.3 sources (I grepped them):

| Amendment | Sentinel |
|---|---|
| #742 | `--policy-ref` |
| G1001 | `request_key` or `Request-Key:` |
| G1014 | `inputs_changed` |
| G1015 | `legacy_policy` and `settings.legacy` |
| G1016 | `no_longer_live` or `respond_to` |
| G1000 | `filter_design` |
| G1020 | its approve-with-notes outcome wording ("approved with") |
| G1023's footnote, under G1016 | `<full 40-hex sha>` in §4.20 |

- **G1018 and G1021.** Pick a term the designer is sure of, such as the `diff` card checkpoint view for G1018, or the 60-second unseen-head wait for G1021. Their obvious words (`4,096`, `merge-tree`, `CONFLICTING`) already appear in rev 6.3.
- **Stability.** Use terms that G1022, G1024, G1025 and G1027 are not expected to remove. Avoid node counts and `engine.min`.
- **Key it by goal.** If a later goal legitimately renames a term, its own PR updates one entry.

## F2 (target: test_design): nothing checks that the case-3 pending rows exist

The design gives G1022 and G1024 pending rows with fixed markers (`workflow.json lacks "\"truth_design\""` and `engine contains "policy_update"`). The tests accept an empty table. An implementation that leaves out these rows passes, and then G1022 and G1024 can land without the guard ever running on them. That re-opens the window the whole design closes.

**Fix.** For each of G1022 and G1024, assert that either a pending row exists or HISTORY §4 has a row naming that goal. The second branch keeps the test green after the goal lands and deletes its row in its own PR. Optionally also assert the row's marker path, so a typo cannot silently turn a row into one that never fires.

## Non-blocking notes

- **The depends-on check reads live goal state.** Its result on a fixed commit can change when a goal ref changes. Example: a stale PR's checks re-run after a pending goal closed, while its tree still holds that row. This is rare and the failure is honest. A one-line comment would help whoever meets it.
- **`test_source_folder_paths_are_rewritten` also scans HISTORY.md.** HISTORY must therefore name the reports in prose ("the R0–R9 reviews"), never `` `reviews/` `` or `REV6_CHANGES.md`. That matches the design's rewrite table, but the implementer should know.
- **The heading test samples a few prefixes.** Together with the citation test this is enough. The full heading diff stays an implement-time check, as the design says.
