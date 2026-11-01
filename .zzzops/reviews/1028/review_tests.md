# G1028 review_tests (attempt 1)

**Verdict: changes requested, on one finding.** The new file `.agents/test_engine_findings_rounds.py` covers design §7 items 1–13 plus 9a/9b and pins the right behaviour. The four edited existing tests change only what the design reverses. The commands run from the worktree root. But the module imports `ENGINE_VERSION` unconditionally, so in the G1027-first merge order the whole file fails to import, and 9b's two-order logic never gets to run.

## What I checked (tests commit f0048e0, on base b452cd7)

- **Commands.** I ran `python3 -m unittest discover -s .agents -t .agents -p 'test_engine_findings_rounds.py'` from the root of the extracted tests commit, as `checks.run` does. It collects all 30 tests. Every one fails or errors before the implementation; the errors come from the missing `GoalResult.stale` and the missing new behaviour, not from imports. The other recorded commands use the same `discover -s .agents -t .agents` form.
- **Edited existing tests: no weakening beyond the design.**
  - `test_engine_frontier`: "stale review findings are not live" becomes "stay live while the target is unchanged". It still asserts `ready (stale)`, and now asserts the carried id. This is exactly §3.1.
  - `test_engine_card_ux` (abandon `restart` ×2, renew `argv`): these compare `argv[:-1]` with a list ending in `--repo`. They do not check the value, but `test_engine_lifecycle` (submit) and `test_engine_live_input_changes` (renew `abandon`/`restart`) check the value with `samefile` against the clone. The edit entries stay without `--repo`, matching §3.4 (worker-facing only), and nothing else changed.
- **New tests against the design.**
  - **Carry (1–5).** It covers spec and `depends_on` edits, dogfood 29, the carry ending when the target resubmits, and op findings not carried, with implement staying `current`.
  - **Lens carry (6).** Material and `keep` findings are carried; `note` and unjudged findings are not; a material finding is carried before the filter has run.
  - **Closed ids (7).** It covers the open/closed split on the card, restated `resolved` as a no-op, the "already resolved"/"already waived" messages, and `details.needs_status`.
  - **`follows` rules (9, 9a).** Inherited target and `rounds`, `upheld` always false, an immediate dispute escalation when following an upheld finding, a reset with a different target, and a split into two follow-ups.
  - **Round trip and edit preview (8, 1–2).** These are tested as journeys.
  - **`--repo` (10–11).** Commands run from outside the repository, with a relative `--output` resolved against the caller's directory. A linked worktree works as the `--repo` value. Both error messages are checked. `next` carries no `--repo`.
  - **Docs (13).**

## Finding

### F1 (material, target `test_design`): 9b's G1027-first branch cannot run, because the module imports `ENGINE_VERSION`

The file does `from engine import ENGINE_VERSION` at module level (line 39). G1027's approved design deletes `ENGINE_VERSION` and `REQUIRES_MIN` from `engine/__init__.py` ("`ENGINE_VERSION`, `REQUIRES_MIN` deleted; `CAPABILITIES`, `build_id()` added"). That is precisely the order in which `G1027_MERGED` is true.

So when G1028 is based on a dev that holds G1027, the module raises `ImportError`, and all 30 tests error. The `G1027_MERGED` branches of `follows_settings` and both 9b tests are dead code, and design §6a's "both merge orders" promise for 9b is untested.

**Fix:**
- Read the version only on the path that needs it: `ENGINE_VERSION = getattr(engine, "ENGINE_VERSION", None)` (after `import engine`), and use it only in the non-G1027 branches.
- Or pick the order from `hasattr(engine, "CAPABILITIES")`, together with the capabilities directory.

Keep the existing `assertGreater(vtuple(ENGINE_VERSION), (1, 1, 0))` for the G1028-first order.
