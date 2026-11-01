# G1017 review_impl (attempt 2)

**Verdict: approved.** Both prior findings are resolved. The rewritten history changes only what the fixes needed, and the private scratch repository's name no longer appears in this goal's commits, tree or goal state.

## Checks

- **History rewrite.**
  - `a2ccc6b..72df95f` is now two commits: `9afbabf` (all implement work, squashed) and `72df95f` (the earlier review artifact, cherry-picked).
  - `git diff e99dc46 72df95f` (the old head against the new) touches exactly three files, `DESIGN.md`, `IMPLEMENTATION_PLAN.md` and `README.md`, with 7 lines added and 4 removed. Every hunk is one of the two fixes. There is no other content change.
  - Tests are untouched: `git diff 8e6185a 72df95f -- .agents` is empty.
- **Name removed.** A case-insensitive grep for the private repository's name (two spellings) and for the private app's name finds nothing in:
  - the patches and messages of `a2ccc6b..72df95f`;
  - the tree at `72df95f`;
  - the full history of `zzzops/goal/g1017`.

  The superseded range `a2ccc6b..e99dc46` still holds it. That range is no longer on the work branch, which is now at `72df95f`. The only owner/repo slug left in the goal's diff is this repository's own.
- **review_impl:1:1: resolved.** The Step 9 record now reads "a private scratch repository". The implementer disputed my suggested scrub-test pattern (on `test_design`), and the owner called it intent drift. I do not re-raise it.
- **review_impl:1:2: resolved.**
  - **New rows.** The README adds rows for G1027, G1028 and G1031, each with sections from its approved design. Their markers (`engine/__init__.py lacks "ENGINE_VERSION"`, `engine contains "carried_findings"`, `engine contains "auto_delete_head_branches"`) are all false at `72df95f`, as are G1022's, G1024's and G1025's.
  - **Changed row.** G1024's row gains §9.
  - **Closing sentence.** It now states why G1026, G1029, G1032, G1033 and G1034 need no row.
  - **DESIGN line 64.** It now reads "12 nodes in revision 6.3 (26 after G1000, §4.1)".
- **run_tests** passed on the new head.
