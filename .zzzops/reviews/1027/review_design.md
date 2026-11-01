# G1027 review_design, attempt 1

**Verdict: changes requested, for two findings.** The core of the design is right, and it answers the owner's question. A capability is a name, not a number, so builds from dev and from main no longer need a shared counter. The build id (plugin version plus package revision) separates every dev build. One file per capability removes the merge race.

Two things need to change before implement:
- **F1.** The design names G1025's capability differently from G1025's own design, and contradicts G1025 on goal schema 2.
- **F2.** The new maintainers' rule covers less than the contract it replaces, and the docs/design edit list does not cover every place the version floor appears.

Neither raises an owner question. Each has a clear winner, and both stay inside the engine and docs.

Checked at read_dev `c3791a0` (G1000 and G1023 merged; G1017 approved but not merged, so `docs/design/` is not on dev yet). I read the engine, the references, G1022's and G1025's current design blobs, the goal state branches, and the rev 6.3 SPEC and DESIGN that G1017 will move.

## What checks out

- **The floor check** (`store.py:454-475`) is as described. The ceiling cannot fire, because `REQUIRES_MIN = "0.0.0"`. `store.py:321` also special-cases `engine_too_new` ("a newer engine reads but does not write"). The design does not list that line, but test 10's grep will find it.
- **`policy_floor`** reads `(schema_version, engine.min)` tolerantly. Adding `requires` as a third value fits.
- **`SETTINGS_SHAPE["engine"]`** is strict and required, and `_optional` supports `("optional", …)` leaves. Making `min` optional and adding `requires` therefore keeps every existing policy valid.
- **Provenance.** `package_provenance()` (`package.py:198`) hashes every file under `PLUGIN_ROOT` except `__pycache__`, `.pyc` and `.pyo`, so the build id is stable across runs of one install. The release bundle (`build_marketplace_bundle.py`) rewrites the manifest `version`, so releases get a real semantic version and dev builds get `0.0.0-dev <rev>`. `.txt` capability files pass the bundle's top-level allowlist and are bundled.
- **The legacy cache key** uses `ENGINE_VERSION` at `legacy.py:63`, `199` and `257`, as stated.
- **REPAIR's two `--grep='^Engine: …$'` recipes** (lines 61 and 106) are the only parsers of the trailer. The hand-written `Engine: hand` trailers (lines 25 and 91) are unaffected.
- **The merge-without-conflict claim** for one file per name holds. The single pinned list in the test file is an acceptable shared line.
- **G1024** depends on `[1017, 1027]`, so its provenance record will be designed against capabilities, as §5 asks.
- **G1022** is approved and not dependent on 1027. Both merge orders are covered. If G1022 merges after G1027 without the note, its edit of the `ENGINE_VERSION` line conflicts, and test 10's grep refuses a re-introduction. The new schemas.py comment then tells its implement what to do. So the informal "root passes a note" fails safe.
- **G1017 fit.** G1027 depends on 1017, which is the right shape under G1017's rule. G1017's inventory predates G1027, but G1017's implement classifies every open goal again, so it will give G1027 a row. G1027's text should say "delete this goal's README pending row, if one exists".

## F1 (target: design): G1025's capability name and goal-schema rule contradict G1025's own design

G1027 §5 names G1025's capability `release_lines` and says goal schema 2 "needs no capability". It also cites "its design, lines 55 and 258". G1025's current design (blob `f240bd5`, design attempt 3) says otherwise:
- **Line 19:** older engines are kept away "by requiring a capability, `branching`".
- **Lines 71-73:** "A policy that sets `settings.branching`, and a goal document of schema 2, requires the capability `branching`". Under the capabilities scheme, "the engine lists `branching` in `CAPABILITIES`".
- **Lines 322 and 350:** the same.

Capability names are written into users' `settings.engine.requires`, so the two goals must agree before either ships. The cited line numbers also belong to an older revision.

**Fix.**
- **Naming rule.** The goal that adds a capability names it. G1027 should not choose names for other goals. Replace `release_lines` with `branching`, or with "the name G1025's design chooses".
- **Schema 2.** Drop the claim that schema 2 needs no capability, or reconcile it with G1025. GOAL_SCHEMAS guards the reading of a goal, but G1025 also gates the policy that makes such goals. Leave that to G1025.
- **Line references.** Remove them.
- **Dependency.** G1025 is being redesigned (design reopened, attempt 3). Recommend that it take `depends_on: 1027` now, at no cost. Its "merges before G1027" branch, and with it the last "next minor" race, then disappears. Its design already describes the capabilities form. G1022, which is approved, keeps the both-orders treatment.

## F2 (target: design): the capability rule covers less than SPEC §4.5's bump list, and the docs/design edits miss where the floor is defined

§3.6's rule names only "a new optional settings key, a new record or finding key, or a new node field". The contract it replaces is broader.
- **SPEC §4.5, "What ships with an `engine.min` bump (one list)":** a new goal schema; any change to fingerprint, canonical-JSON, `code_tree` or `change` semantics; any op `version`; the lease message format; any new POLICY or workflow key, field or op.
- **SPEC §4.8 and DESIGN D4 (line 355):** a fingerprint version bump goes "always together with an `engine.min` bump".
- **SPEC line 1565:** an op `version` is bumped "always together with an `engine.min` bump".

If these keep saying "engine.min bump", the rule no longer exists for new goals. If they are dropped, a future `FP_VERSION` or op-semantics change ships with no floor, and an older engine writes records with the old semantics into goals that the new engine has written.

The design's docs list ("SPEC §3.2, §4.5, the trailer and `--version`; DESIGN's version-floor rationale") also leaves out the other places that define or name the floor and the ceiling:
- SPEC's `blockers` kinds (line 536);
- the exit-code table (line 610, `engine_too_new`);
- the tolerant read order (line 679);
- the `new` and `start` verb rows (1975-1976, "outside `engine.min`", `engine_too_new`);
- the REPAIR summaries (2266, 2269);
- test-list item 75 (2365);
- in DESIGN, §3.10's floor, ceiling and upgrade bullets (581-589), the settings list (621), the failure table (793) and invariant 21 (1262).

Test 10's grep covers only `plugins/` and `.agents/`, so nothing catches these.

**Fix.**
- Restate SPEC §4.5's list as "What ships with a new capability". Keep every item: goal schema (still gated by `GOAL_SCHEMAS`, and say so), fingerprint or canonical semantics, op `version`, lease format, and new POLICY or workflow keys, fields or ops.
- Make the §3.6 maintainers' rule and the `schemas.py` comment say the same.
- Change §4.8, the op-version sentence and DESIGN D4 to "together with a new capability".
- List the sections above in §4's docs/design bullet.
- Extend test 10's grep (`engine.min bump|REQUIRES_MIN|engine_too_new|requires_min`) to `docs/design/` except HISTORY.md.

## Non-blocking notes

- **Old dev builds will see `policy_invalid`.** DESIGN §3.10 reads the floor tolerantly "so an agent never 'fixes' a new key by deleting it" (`evo:H4`). With `requires`, 1.0 and 1.1 dev builds see `policy_invalid`, which is exactly the prompt for that wrong fix. Today's changes can only land through a reviewed policy branch, and the owner approved the lockout, so this is acceptable. Still, MIGRATING and the policy branch's PR body should say "an older build reporting `policy_invalid` on `settings.engine.requires` must be upgraded; do not remove the key". Record the trade-off against `evo:H4` in the DESIGN amendment.
- **Legacy `DETECTOR`.** `legacy.py:46-52` loads `LEGACY_ROOTS` and the ignore markers from `scripts/cleanup_legacy.py`. Hash both files into `DETECTOR`, or argue that those values reach the key only through `signals`.
- **`store.py:321`.** The `engine_too_new` read-only branch goes along with the ceiling. Name it in §2 and §4.
