# G1027 review_tests, attempt 2

**Verdict: changes requested, for one new, small finding.** Both prior findings are fixed. But test 10's grep, now that I ran it against the base, also covers `docs/design/IMPLEMENTATION_PLAN.md`. That file is a historical record, so the test would force the implementation to rewrite it.

Subject: tests at `4d0d880` (the change since `1782abd` is in test 10 only, plus the recorded commands).

## Prior findings

- **review_tests:1:1: resolved.** Test 10 now excludes `:(exclude,glob).agents/test_*.py`. I ran the grep with the same pathspecs:
  - **At base `b452cd7`:** it still reports the shared helper (`.agents/engine_fixtures.py`), the engine and `CLI_USAGE.md` in `plugins/`, and `docs/design/`. No test module appears.
  - **Over `origin/zzzops/work/g1025`:** only `engine_fixtures.py` matches in `.agents/`, which G1027's own edit clears. G1025's `test_engine_branching.py` fallbacks are excluded, as are G1022's and G1028's. The docstring records why.
- **review_tests:1:2: resolved.** The full-suite command is gone. The nine module commands are `test_engine_capabilities`, the five edited modules, and `test_design_docs`, `test_engine_sync_edit` and `test_engine_lenses`. The slowest is the five-module set, which took about 2 minutes in my run at attempt 1. That replaces about 17 minutes.

## F1 (target: test_design): exclude IMPLEMENTATION_PLAN.md from test 10 as well as HISTORY.md

At base, the grep matches three lines of `docs/design/IMPLEMENTATION_PLAN.md`:
- line 82: the `engine/__init__.py` row naming `ENGINE_VERSION`;
- line 327: "SPEC §4.5: the engine floor and ceiling, and `requires_min`";
- line 346: item 21, "`settings.engine.min` above `ENGINE_VERSION` refuses writes".

G1017 moved the plan in as "Completed 2026-10-31; a historical record. DESIGN and SPEC win". G1027's design §4 does not list the plan among the docs it edits. As written, test 10 makes the implementation rewrite those lines, which would make the record describe a plan that never existed. That is the same reason HISTORY.md is excluded.

**Fix.** Add `':(exclude)docs/design/IMPLEMENTATION_PLAN.md'` next to the HISTORY.md exclusion, and say in the docstring that both are historical records.

(`docs/design/README.md:28` also matches, through G1027's own pending-row marker `lacks "ENGINE_VERSION"`. That is fine: G1017's guard requires G1027's PR to delete that row.)
