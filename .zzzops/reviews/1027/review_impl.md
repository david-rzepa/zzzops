# G1027 review_impl (attempt 1)

Reviewed `25186a5..6b068cb` against design revision 2, the tests line (`25186a5..c401f1d`) and the checks (11 commands, full suite passing on tree `ad5e320`).

## Compliance
- Capabilities: one file per name under `engine/capabilities/` (`lens_findings`, `finding_follows`, `lenses`), loaded once into `CAPABILITIES`. Since both goals merged first, the map has the 1.2.0 and 1.3.0 entries and the two extra files, as design §5 says.
- `settings.engine.requires` (optional `names` shape), `engine.min` optional; the tolerant floor read returns `(sv, min, requires)`; `floor_check` refuses with `engine_too_old` plus `missing`, and uses the "last numbered engine" message for a `min` above the map.
- `engine_too_new` and `REQUIRES_MIN` are gone from errors, the CLI, store and docs. `ENGINE_VERSION` and `FOLLOWS_SINCE` are gone. `follows_required` now goes through `required_caps`, so a policy at `min` 1.2.0 still allows `follows` (probed).
- Build id: computed once per process from `package_provenance` (which skips `__pycache__`, so it is stable), with `unknown` if provenance fails. Used in the trailer, abandon, `--version` and `validate`'s `engine` block.
- Legacy: the `DETECTOR` digest hashes `legacy.py` and `scripts/cleanup_legacy.py` (path resolved the same way as `_cleanup_constants`). `checked.engine` holds the build id.
- Template: requires `["lens_findings", "lenses"]`. `lenses` is needed because the shipped graph is G1022's multi-lens graph, and G1022's own test checks for it.
- Docs: SPEC, DESIGN, CLI_USAGE, MIGRATING, REPAIR and HISTORY are updated, and the README pending row is removed.

## Correctness
- One change goes beyond the design: `read_state`, when the floor reports missing capabilities, still runs strict validation. If validation fails, it reports nothing extra (the floor stays the only report, `evo:H4`). If validation passes, it loads the settings and graphs so reads work. Writes stay blocked by `write_block`, and the integration-branch check is still guarded on `write_block is None`. The schema-version case has no `missing`, so it behaves as before. This is an improvement, not a defect.
- The edge cases of `legacy_caps` match §3.3: 0.0.0, 1.0.7 → none; 1.2.9 → 1.2.0's capabilities; 1.3.1 or higher → sentinel.

## Missing (outside the diff)
- No remaining readers of `ENGINE_VERSION`, `REQUIRES_MIN` or `FOLLOWS_SINCE` in plugins, scripts or skills. `test_engine_findings_rounds.py` and `test_engine_review_lenses.py` read it only through `getattr`, in their "other goal merged first" branches. `IMPLEMENTATION_PLAN.md` and HISTORY are historical and excluded by the guard.
- The `.zzzops/POLICY.json` in this repository still has `engine.min: 0.0.0`. That is correct for this diff: it maps to no capabilities and `validate` will warn. The §5 lens policy branch must replace it with `requires: ["lens_findings", "lenses"]` (plus `finding_follows` if `follows` is wanted) after merge.
- The `graph12` fixture stays on `min` 0.0.0 on purpose (the deprecation test reads it). `graph26` now requires `lens_findings`, which fits its lens graph. This is the only change to the tests line after test_design, and it is a fixture, not a frozen assertion.

## Tests
- The tests were not weakened: from `c401f1d` to `6b068cb`, implement changed only the graph26 fixture.
- **Finding (test_design):** the compatibility contract for the 1.2.0 and 1.3.0 map entries is not pinned. `test_mapping` and `test_old_floors_proceed_and_validate_warns` check only 0.0.0, 1.0.0 and 1.1.0. No test anywhere uses `engine.min` 1.2.x or 1.3.x: G1028's and G1022's tests take their `requires` branch now that G1027 is merged.
  - What is unprotected: these two entries are the only thing that keeps policies whose floor was raised during the G1028/G1022 rollouts working as before.
  - Impact: a wrong edit would silently break those repositories. Dropping `finding_follows` from 1.2.0 refuses `follows` under `min` 1.2.0. Dropping `lenses` from 1.3.0 lets an engine without `lenses` write multi-lens records. Deleting an entry turns a valid floor into the sentinel refusal.
  - Fix: assert the exact 1.2.0 and 1.3.0 tuples, one value between entries (1.2.5 → 1.2.0's set), and 1.3.1 → the sentinel. Also assert that `schemas.follows_required({"engine": {"min": "1.2.0"}})` is true and the 1.1.0 case is false.

## Craft
- The code is small and readable. `engine_warnings` says "(none)" for a `min` above the map, but the floor already refuses that case with the specific message, so this is not a defect.

Verdict: changes_requested, with one Tests finding for test_design. The implementation itself is approvable.
