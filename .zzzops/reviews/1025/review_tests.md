# G1025 review_tests (attempt 1): `.agents/test_engine_branching.py` and the docs sentinel

Reviewer: claude:e6ad/rd1025. Tests at e4e9334 (base b452cd7), design revision 3 (f240bd5).

## Verdict

**Changes requested: two findings.** The suite covers design §13 well:
- the pure frontier: pass 3, the bound, `line_complete`, the `release_sync` wait, the target fp part;
- a golden no-settings regression;
- validation;
- CLI journeys for the cut (racing, adoption, a goal reopened before the cut), the ledger, targets, required checks, sync (clean, conflict and approval, dev moving underneath), the scheduled restack, finish (late member, cancel, production conflict), hotfix lines (record-only sync, recorded-tip back-merges after auto-delete, single-use names) and stacking.

I ran the file at e4e9334 in a scratch copy: 55 tests, 6 failures and 46 errors. Every error is `KeyError: 'release'` (no shipped `graphs.release` yet), and every failure is a missing feature: `branching` is an unknown settings key, `GOAL_SCHEMAS` is `(1,)`, `ENGINE_VERSION` is 1.1.0, and so on. They fail for the right reason. The regression tests pass at the base: `GOLDEN_FP` matches the b452cd7 engine, and `NoBranchingTests` and `NoBranchingRestackTests` pass.

## Findings

**F1 (test_design): `require_release_lines` imports `ENGINE_VERSION` unconditionally, so every branching test errors if G1027 merges first.**
- Line 72 runs `from engine import ENGINE_VERSION, schemas` before it decides which scheme applies. G1027's approved design (§3.4, "`ENGINE_VERSION` is deleted, with no display alias") removes that name.
- `branching_policy()` calls this helper, and almost every class uses it. In the G1027-first order, the whole file errors with an ImportError, even though its `requires` branch is correct. This is the same way another goal's tests broke.
- In the G1025-first order, G1027's own PR inherits the breakage and has to repair this file.
- **Fix:** import `schemas` alone, and read the version lazily inside the `engine.min` branch, e.g. `import engine; policy[...]["min"] = engine.ENGINE_VERSION`.
- Simplify the `pop(...) if ... else None` expression. Under G1027's shape `min` is optional, and leaving the template's `0.0.0` produces an `engine_min_deprecated` warning. Pop `min` whenever `requires` is used, so validate outputs stay clean under both orders.
- `test_capability_release_lines_is_declared` already guards its `ENGINE_VERSION` import inside the else branch, so it is fine.

**F2 (test_design, minor): superseded goals are not tested where design revision 3 promised.**
- §13 test 2a says "the cut item counts closed done, cancelled and superseded goals from trailers alone".
- `LedgerTests` asserts `Closed: cancelled` and `Closed: done`, but never `Closed: superseded`.
- No cut test includes a superseded release-N goal. The only superseded case is `line_members_open` in the frontier test.
- **Fix:** close one release-1 goal as superseded in `test_trailers_are_written_with_branching`, asserting `Closed: superseded`, and in a cut-item test, asserting that it neither blocks the cut nor alone makes the release complete.

## Interface readings (the docstring's list): all consistent with the design

| Reading | Design | Verdict |
|---|---|---|
| `portfolio(..., ledger=, upstream=)` | §3.1 "`portfolio` receives the ledger"; §5.3/§8 "the session passes `upstream` … into `portfolio`" | consistent |
| ledger entry `{release, state, closed, line, hotfix}`, with `line` = "release:1" | §3.1 `{g: {release, state, closed, line, hotfix}}` and the trailer `Line: release:<N>` | consistent |
| cut answer keys `decision, quote, decided_by` | §3.2 `answer_template` | consistent |
| `created.recovered` on a recovered cut, plus top-level `goal` | §3.3 step 1 (`created.recovered`) and step 7 (`{release, branch, cut, goal}`) | consistent. The racing test needs both keys on recovery and `recovered` only on the loser, which is a fair reading. |
| hand-resolved sync approved through `answer <line> sync --fp … --file {text, quote, decided_by}` | §5.4 "raises a human item before it merges"; this is the existing blocked-human `answer` path (as in `test_engine_github.py:271`) | consistent |
| `show` text contains "target release/1" | §4 "`show` prints `— open, target release/1`" | consistent |
| capability `release_lines`, not `branching` | the design text says `branching`; G1027 and approve_design say `release_lines` | correct reading. The sentinel in test_design_docs also requires `release_lines` in SPEC. |

Other unlisted readings are also consistent with §9: `next.releases.{effective, lines, waiting}`, state strings such as `waiting (line_members_open)` and `ready (upstream…)`, `scheduled_for` in `base`'s output, and `finish`'s `back_merges` containing `dev`.

## Other checks

- **Working directory.** CLI calls go through `World.run`, whose cwd is the clone root. The `validate --policy --dir` test runs from the temp directory with an absolute `--dir`, which is the dir form's contract. The docs tests use `fx.ROOT`. Fine.
- **Docs sentinel.** The G1025 entry in `AMENDMENT_SENTINELS` fails until the PR edits SPEC/DESIGN, which is intended. The README pending row exists at the base, and `DocsTests` requires the PR to delete it. Consistent with design §10.
- **The racing-cuts test** is deterministic whatever the interleaving. A sequential "race" still gives exactly one `recovered`, through the step-1 key scan.

## Notes (not findings)

- **`GOLDEN_FP`** is an absolute digest of the b452cd7 engine. It is correct now, but it breaks after a rebase onto any goal that legitimately changes fingerprints of the frozen 12-node graph. The comment should give the regeneration rule: recompute at the base commit with this file's `journey_fps`, and never at the head.
- **G1027 coordination (for the root, not this file).** If G1025 merges first and repositories set `engine.min` to G1025's version (1.2.0 or later), G1027's `LEGACY_VERSIONS` must map that version to `("release_lines",)`. Otherwise its "above the map" sentinel refuses those policies. G1027's PR must also add `release_lines.txt` and append it to the pinned-capabilities list.
