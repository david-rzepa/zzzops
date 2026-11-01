# G1027 review_tests, attempt 1

**Verdict: changes requested, for two findings.**
1. Test 10's stale-name grep would fail the PRs of three in-flight goals that merge after G1027, because their frozen test files reference `ENGINE_VERSION` on purpose, to support both merge orders.
2. The recorded commands include the full suite (about 17 minutes), which is CI's job.

Otherwise the tests cover design revision 2 well, fail for the right reasons before the implementation, and the edits to existing tests change only what the design changes.

Subject: tests at `1782abd` (base `b452cd7`). The design is revision 2 (`0c556c2`).

## What I ran (scratch copy of 1782abd)

**`test_engine_capabilities`: 26 tests in 3.4 s; 14 failures, 10 errors, 2 passing.** Every failure and error comes from a missing feature: no `engine.CAPABILITIES` or `capabilities/`, no `build_id`, no `legacy.DETECTOR`, no `LEGACY_VERSIONS`, `--version` printing `1.1.0`, `policy_floor` without `missing`, a template still on `min: 0.0.0`, `engine_too_new` still in `EXIT`, and docs/design still describing the ceiling. The two that pass are schema guards (invalid `requires` shapes; the `engine` block is required), which hold under both engines.

**The five edited modules (`store`, `review_fixes`, `schemas`, `legacy`, `identity`): 166 tests in 107 s; 13 fail.** All 13 are edited tests or users of the edited helpers:
- `build_id` imports in `push_root`, which errors 4 Request-Key tests;
- `DETECTOR` and `build_id` in the legacy tests;
- `requires` refusals;
- the three-tuple `policy_floor`;
- `test_next_is_one_fetch_and_no_gh`. The fixture's `seed_legacy_cache` now skips while `build_id` and `DETECTOR` are missing, so `next` makes its legacy check. This is the right reason, and it goes away with the implementation.

## Edits to existing tests: only what the design changes

- **Floor tests.** `engine.min: 99.0.0` becomes `requires: ["no_such_cap"]` in store, idempotent-new and policy-branch-order. The assertions are unchanged.
- **`NewerEngineReadTests` becomes `OlderEngineReadTests`.** The ceiling is gone, so the test now asserts that reads still work under a missing capability, with `missing` on both the blocker and the refusal.
- **`policy_floor`** now returns `(sv, min, requires)`, and a malformed list gives `None` (§3.2).
- **Legacy tests** are keyed by `DETECTOR` and record `build_id()`. A new build with the same detector does not re-check, and a new detector re-checks once (§3.5). `cache_key`'s first parameter is checked to be `detector`.
- **`engine_fixtures.seed_legacy_cache`** uses the detector key and the build id, and skips cleanly before they exist.
- **The identity comment** now says "a new capability".
- `test_engine_lenses.py:81`'s hand-written `Engine: 1.1.0` trailer stays, which is correct: old trailers are valid history.

## The copied-plugin approach: sound

- `plugin_copy` copies `plugins/zzzops` without `__pycache__`.
- `zzzops.py` puts its own directory first on `sys.path`, and `World.cli_env()` sets no `PYTHONPATH`, so `run_with(code, …)` really runs the copy's engine.
- Deleting `capabilities/lens_findings.txt` is the real fail-closed path the design describes: a capability is a file.
- The damaged-provenance case appends an overriding `package_provenance` that raises, which `build_id()`'s `runpy` load will pick up.
- `engine_attr` evaluates in a fresh interpreter, so the copy's `DETECTOR` and `build_id()` never mix with the in-process engine.
- The merge test commits two capability files on branches of a real repository, and `git merge` would raise on a conflict.

## F1 (target: test_design): test 10 fails later goals' deliberate both-order fallbacks

`NoStaleReferenceTests.test_old_names_are_gone` greps `ENGINE_VERSION|…` over all of `.agents/`, excluding only this file. Three in-flight goals have frozen test files that name `ENGINE_VERSION` on purpose. Each reads it only through `getattr` or a lazy import, so the files work whichever goal merges first:
- G1022: `.agents/test_engine_review_lenses.py:238-246` (`getattr(engine, "ENGINE_VERSION", None)`);
- G1025: `.agents/test_engine_branching.py:72-82` and `358-359` (a lazy `engine.ENGINE_VERSION` in the `min` branch);
- G1028: `.agents/test_engine_findings_rounds.py:48-61` and `517`.

**If G1027 merges first**, each of those PRs runs G1027's test 10 on its merge ref and fails. Their test files are frozen, so the only way out is reopening `test_design`, for a guard that adds no protection, because the references are guarded.

**If they merge first**, G1027's implement must edit three other goals' tests to delete working fallbacks.

**Fix.** Narrow test 10's `.agents` scope to non-test modules: `.agents/*.py` minus `.agents/test_*.py` (the fixtures and helpers), plus `plugins/` and `docs/design/` as now. A test file that imports a removed name unguarded fails on its own with an ImportError, so nothing is lost. Alternatively, allow only the `getattr(engine, "ENGINE_VERSION"…)` and lazy forms. That is harder to state, so prefer the narrowing.

## F2 (target: test_design): drop the full-suite command

The seven recorded commands are the six touched modules plus `python3 -m unittest discover -s .agents`, the whole suite (about 17 minutes). `run_tests` runs every command on every attempt, and the full suite is `dev-required-tests`' job on the PR.

**Fix.** Replace the full-suite command with the few extra modules that exercise surfaces this goal changes:
- `test_design_docs`: the docs/design edits, the HISTORY §4 row, and G1027's README pending row, if one exists;
- `test_engine_sync_edit`: it asserts the `Engine:` trailer;
- `test_engine_lenses`: it writes hand-made trailers, and the shipped graph needs `lens_findings`.

The six module commands can stay as they are, or be merged into one `unittest` invocation.

## Non-blocking notes

- **`SHIPPED = {"lens_findings"}` is the one shared line**, as the design says. G1022, G1025 and the others add their names here when they ship a capability. That is worth a line in each one's rollout note, which the root relays.
- **`test_mapping` looks for `legacy_caps` in either `schemas` or `store`.** The design names `schemas`. The flexibility is harmless.
