# G1027 design: declared engine capabilities replace ENGINE_VERSION and engine.min

Revision 2. Read at dev `c3791a0`. It answers review_design:1:1 and 1:2, and takes the review's three notes.
- **1:1:** G1025's capability is `release_lines`. The root recorded that name in G1025's approval. Under G1025's own design, schema-2 goals and `settings.branching` are both gated by that capability; GOAL_SCHEMAS still guards reading. Both merge orders are covered, and there is no new dependency edge. The stale line references are gone (§5).
- **1:2:** the maintainers' rule is now SPEC §4.5's complete list, restated as "what ships with a new capability" (§3.6). The docs/design edit list names every section that defines or mentions the floor or the ceiling (§4), and test 10 also greps docs/design.
- **Notes:**
  - MIGRATING and the policy-branch PR body say to upgrade and never to remove `requires`, and the DESIGN amendment records the trade-off against `evo:H4` (§3.3).
  - `DETECTOR` hashes both `legacy.py` and `scripts/cleanup_legacy.py` (§3.5).
  - `store.py:321` is named (§2, §3.2).

## 1. Outcome

- The engine declares a set of capability names. Each name stands for one format or behaviour that an older engine must not touch. G1000's 1.1.0 becomes `lens_findings`.
- POLICY declares `settings.engine.requires: [names]`. If the running engine lacks any of them, writes are refused with `engine_too_old` and work is paused, as with today's floor. The message names the missing capabilities and says to upgrade the plugin.
- A goal adds a capability by adding one file in its own PR. Two goals never edit the same line, so they need no ordering between them and no shared "next number".
- `engine.min` keeps working through a fixed map from version to capabilities. `validate` warns that it is deprecated.
- `ENGINE_VERSION` and `REQUIRES_MIN` are removed. The `Engine:` trailer and `zzzops --version` show a **build id** instead: the plugin version plus the package revision that `package.py` already computes. Every build is then distinguishable, including dev builds.
- The legacy cache key stops using the engine version.

Size: about 60 changed lines of engine code across `__init__.py`, `schemas.py`, `store.py`, `cli.py`, `legacy.py` and `verbs.py`, plus one new data directory, three reference docs and the docs/design edits.

## 2. What was found at read_dev (c3791a0)

- `engine/__init__.py:3-4`: `ENGINE_VERSION = "1.1.0"` and `REQUIRES_MIN = "0.0.0"`.
- `store.py:454-475` `floor_check`. `schemas.policy_floor`, a tolerant pre-read, gives `(schema_version, engine.min)`.
  - **Too old:** `engine.min > ENGINE_VERSION` blocks with `engine_too_old` (pause, `write_block`, hint "upgrade the plugin").
  - **Too new:** `engine.min < REQUIRES_MIN` blocks with `engine_too_new`. `REQUIRES_MIN` is `0.0.0`, so this branch can never fire.
  - **Read-only special case:** `store.py:321` reads goals while writes are blocked only by `engine_too_new` ("a newer engine reads but does not write").
- `schemas.py:530`: `SETTINGS_SHAPE["engine"] = {"min": "version"}`, which is required. `schemas.py:547-549` has the rule "any new optional key must raise ENGINE_VERSION".
- `store.py:581` `goal_message` and `verbs.py:658` (abandon) write the trailer `Engine: {ENGINE_VERSION}`. Nothing in the engine parses that trailer. REPAIR uses it twice, with `git log --grep='^Engine: <version>$'`:
  - the "Upgrade the engine" rollback;
  - "Bulk revert of one bad release's writes".
- `cli.py:578`: `--version` prints `ENGINE_VERSION`.
- `legacy.py:63,199,257`: `cache_key(ENGINE_VERSION, url, signals)`, and the cache record's `engine` field (shown as `checked.engine`).
- `package.py:198` `package_provenance()` returns `{"version": <plugin.json version>, "revision": sha256 over every package file}`. The plugin version is `0.0.0-dev` on dev, and semantic-release sets it on main.
- **No reset engine has ever been released.** `origin/main` has no `engine/`, and the product tags are `v2.x` (pre-reset). So 1.0 and 1.1 engines exist only as dev builds, in this repository's clones.
- Template and policies:
  - Both `templates/default/POLICY.json` and this repository's `.zzzops/POLICY.json` have `engine.min: "0.0.0"`.
  - The shipped default graph is G1000's lens graph.
- Error codes `engine_too_old`/`engine_too_new` are in `errors.py:8`. Separately, `session.py:202`, `verbs.py:86` and `verbs.py:895` use `engine_too_old` for a newer goal schema. That check uses `GOAL_SCHEMAS` and is unchanged.
- Tests that use the version:
  - `test_engine_store.py`: lines 226, 772 and 287.
  - `test_engine_review_fixes.py`: lines 133 and 310-320 (`REQUIRES_MIN`).
  - `test_engine_schemas.py`: lines 158 and 169.
  - `test_engine_legacy.py`: lines 99-154.
  - `.agents/engine_fixtures.py`: line 214.
  - `test_engine_identity.py:227`: a comment only.

## 3. Approach

### 3.1 Declaring capabilities: one file per name

New directory: `plugins/zzzops/zzzops/engine/capabilities/`. It holds one file per capability, `<name>.txt`. Each file holds one paragraph: the format or behaviour it guards, and the goal that added it. At this goal's merge:

- `lens_findings.txt`: "Lens review records (G1000): finding keys `impact` and `material`, filter nodes and their `keep`/`note` verdicts, notes, and `skippable` review nodes. An engine without it reads these as unknown keys."

`engine/__init__.py` loads the set once:

```python
CAPABILITIES = frozenset(p.stem for p in (Path(__file__).parent / "capabilities").glob("*.txt"))
```

Names must match `^[a-z][a-z0-9_]*$` (`NODE_ID`). A test checks every file name and that no file is empty.

**Why files and not a Python set.** The acceptance test needs two goals that each add a capability to merge without conflict. Two PRs that each append a line to the same set or list insert at the same point, and git reports a conflict. Two PRs that each add a different file never conflict. The files also document themselves.

`package.py`'s `REQUIRED_FILES` is a "must exist" list, not an exhaustive one, so capability files are not listed there. Listing them would bring back the shared-line conflict. A damaged install that loses a file fails closed: the engine lacks the capability and refuses writes with "upgrade the plugin".

**Capabilities are only ever added.** An engine that dropped support for a format would need a new design (out of scope). Removing a file is a test failure: a pinned list of the names shipped so far must be a subset of `CAPABILITIES`. A goal that adds a capability appends to that list in the test file. It is the one shared line, and only the test file has it. See §6, test 6.

### 3.2 Requiring them: `settings.engine.requires`

- **Shape.** `SETTINGS_SHAPE["engine"]` becomes `{"min": ("optional", "version"), "requires": ("optional", "names")}`.
  - `names` is a new leaf shape: an array of unique strings matching `NODE_ID`.
  - The `engine` object stays required, so no existing policy becomes invalid.
- **Tolerant pre-read.** `schemas.policy_floor` returns a third value, `requires`. It is the list when that is a list of strings, else `None`. A malformed list is ignored by the floor and reported by validation as `policy_invalid`, as `min` is today.
- **Check.** `store.floor_check` computes `required = set(requires or ()) | legacy_caps(min)` (§3.3) and `missing = sorted(required - CAPABILITIES)`.
  - If `missing` is non-empty, the blocker is `{"kind": "engine_too_old", "message": …, "missing": [...]}`.
  - The message reads: "this engine lacks capabilities the policy requires (`lenses`, `release_lines`): upgrade the plugin".
  - `pause` and `write_block = Refused("engine_too_old", msg, hint="upgrade the plugin", details={"missing": missing})` are set as today.
  - The schema-version half of the floor (`schema_version > POLICY_SCHEMA`) is unchanged.
- **Unknown names.** A name this engine has never heard of is simply missing. That is the mechanism: a newer policy names a capability an older engine lacks.
- **Removed: the ceiling (`engine_too_new`, `REQUIRES_MIN`).** It can never fire today, and it is defined only in terms of `engine.min`. The code `engine_too_new` leaves `errors.py`, `cli.py:217`, `store.py:321` and the SPEC and DESIGN sections in §4. At `store.py:321`, the condition becomes `st.write_block is None`. No engine has ever emitted it, so no consumer exists. If a future engine must refuse to coexist with older ones, its goal designs that rule with capabilities.

### 3.3 Migration: `engine.min` through a fixed map

`schemas.py` gains:

```python
LEGACY_VERSIONS = {"1.0.0": (), "1.1.0": ("lens_findings",)}   # engine.min (deprecated) -> capabilities
```

- **Mapping.** `legacy_caps(min)` returns the capabilities of the highest listed version that is not above `min`. For example, `0.0.0`, `1.0.0` and `1.0.7` all give `()`.
- **Above the map.** A `min` above the highest listed version maps to the sentinel `"engine_min_<min>"`. No engine has that capability, so the floor refuses. The message names it as: "engine.min `<min>` is above `<highest>`, the last numbered engine: replace it with `settings.engine.requires`".
- **Old behaviour kept.** A policy with `engine.min: 1.1.0` keeps locking out 1.0 builds, which lack `lens_findings`. Every capability-declaring engine satisfies it.
- **Deprecation warning.** `validate` (both the repository form and `--policy --dir`) adds a warning when `engine.min` is present: `{"kind": "engine_min_deprecated", "message": "settings.engine.min is deprecated: replace it with settings.engine.requires (<mapped names, or none>) through a policy branch"}`.
  - The warning appears only on `validate`, not on every `next`, so agents' cards and `next` stay quiet.
- **No lockout sentinel for old engines.** A 1.0 or 1.1 engine that reads `requires` sees an unknown key, reports `policy_invalid`, pauses and refuses writes. That fails closed. The only cost is a less specific message, for dev builds that the owner has already approved locking out.
  - **Trade-off against `evo:H4`.** DESIGN §3.10 reads the floor tolerantly "so an agent never 'fixes' a new key by deleting it". `policy_invalid` on `requires` is exactly the prompt for that wrong fix. Two things mitigate it:
    - A change can land only through a reviewed policy branch.
    - MIGRATING, REPAIR's "Upgrade the engine" and the PR body of the policy branch that adds `requires` each say: "an older build that reports `policy_invalid` on `settings.engine.requires` must be upgraded; never remove the key."

    The DESIGN amendment records this trade-off.
  - Rejected: telling policies to also set `engine.min` to a high sentinel such as `2.0.0`, so that old engines say `engine_too_old`. The product's own tags are already `v2.x`, so a "2.0.0" in POLICY would be read as a product version. That is the two-numbers confusion this goal removes.
- **The default template** (`templates/default/POLICY.json`) becomes `"engine": {"requires": ["lens_findings"]}`, because its graph writes lens records. New repositories then declare what their graph needs from the start.
- **This repository's `.zzzops/POLICY.json`** is not changed by this PR: policy changes go through policy branches (§5).

### 3.4 Build id: the `Engine:` trailer and `--version`

- **`engine.build_id()`**, cached once per process, returns `"<version> <revision[:12]>"`.
  - It comes from `package_provenance()`, loaded with `runpy` as `cli.package_check` already does.
  - Example: `Engine: 0.0.0-dev 3f2a9c1b7d4e` on a dev build, `Engine: 2.2.0 9b0c…` on a release.
  - A space separates the two parts because Codex cachebuster versions already contain `+`.
  - If provenance fails (a damaged install), it returns `"unknown"`. A write never fails because of the trailer.
  - Cost: one sha256 over the roughly 1.5 MB package, only in processes that write.
- **`goal_message`** (`store.py:581`) and **abandon** (`verbs.py:658`) write `Engine: {build_id()}`.
  - This is the build id, not the capabilities. REPAIR's bulk-revert and rollback recipes need the trailer to name one build. A capability list is the same for many builds, so it cannot identify a bad one.
  - Old trailers (`Engine: 1.1.0`) stay valid history. Nothing parses them.
- **`zzzops --version`** prints the build id.
- **`zzzops validate` output** gains a top-level `"engine": {"build": …, "capabilities": [sorted]}`. It is additive. With it, "Upgrade the engine" can check each machine without reading files.
- `ENGINE_VERSION` is deleted, with no display alias. The build id is the display. Keeping an alias would leave the stale number that the owner asked to remove.

### 3.5 Legacy cache key

- `legacy.py` gets `DETECTOR`, and the key becomes `cache_key(DETECTOR, url, signals)`.
  - `DETECTOR` is the first 12 hex digits of a sha256 over the CRLF-normalised bytes of `legacy.py` and of `scripts/cleanup_legacy.py`.
  - The second file is included because `legacy.py:44-56` loads `LEGACY_ROOTS` and the ignore markers from it.
- The key exists so that a new detector re-checks. Hashing the detector's own sources does that automatically: any edit to the detection rules, or to the roots and markers they load, changes the key, and no number needs bumping.
- After the upgrade, every clone re-checks exactly once (one `ls-remote` and at most one search). That is the same cost as any engine upgrade today.
- The record's `engine` field (shown as `checked.engine`) holds `build_id()`. The key name stays the same, so output consumers are unaffected.
- `cache_key`'s first parameter is renamed `detector`.

### 3.6 Maintainers' rule (replaces "raise ENGINE_VERSION")

SPEC §4.5's "What ships with an `engine.min` bump (one list)" becomes **"What ships with a new capability (one list)"**. Every item is kept. A goal ships a new capability, as `engine/capabilities/<name>.txt` in its own PR, when it makes any of these changes:
- **A new goal schema.** Reading is still gated by `GOAL_SCHEMAS`: an older engine reports `engine_too_old` and treats such goals as read-only. The capability gates the policy that lets the new engine write them.
- **Fingerprint semantics:** a change to fingerprint, canonical-JSON, `code_tree` or `change` semantics, including an `FP_VERSION` change.
- **Op semantics:** any op `version` change.
- **Lease format:** a change to the lease message format.
- **New policy or workflow format:** any new POLICY or workflow key, field or op. This includes optional settings keys, node fields, and record or finding keys.

The same goal's rollout tells repositories to add `<name>` to `settings.engine.requires` before the first such write. The other places that state the old rule say the same thing, in the same words:
- **SPEC §4.8 and DESIGN D4:** a fingerprint version bump goes "always together with a new capability".
- **SPEC's op-version sentence:** an op `version` bump goes "always together with a new capability".
- **The comment at `schemas.py:547-549`**, which points to SPEC §4.5's list.
- **The maintainers' sentence in CLI_USAGE's legacy paragraph.**

This rule replaces the "next minor at merge" rules in G1022's and G1025's designs (§5).

## 4. Interfaces and data that change

| Change | Where | Compatibility |
|---|---|---|
| `settings.engine.requires` (optional names); `engine.min` becomes optional and deprecated | POLICY schema 2, `schemas.py` | Additive for the new engine. Old engines treat `requires` as unknown: `policy_invalid`, which fails closed |
| `engine_too_old` blocker and error gain `missing` | `store.py`, error `details` | Additive |
| `engine_too_new` removed | `errors.py`, `store.py`, `cli.py:217` | Never emitted |
| Warning `engine_min_deprecated` | `validate` | New warning kind |
| `validate` output `engine: {build, capabilities}` | `cli.py` | Additive |
| `Engine:` trailer value: build id | `store.py`, `verbs.py` | Free text; nothing parses it; REPAIR greps it |
| `--version` output: build id | `cli.py` | No consumer in repo, skills or docs |
| Legacy cache key and `checked.engine` value | `legacy.py` | Cache rebuilt once |
| Default template `engine` block | `templates/default/POLICY.json` | New bootstraps only |
| `ENGINE_VERSION`, `REQUIRES_MIN` deleted; `CAPABILITIES`, `build_id()` added | `engine/__init__.py` | Internal |

Docs:
- **CLI_USAGE:** settings `engine`, `requires`, the `engine_too_old` meaning, `--version`, the `validate` `engine` key, the legacy paragraph's maintainer sentence and its `engine.min` remark.
- **MIGRATING:** "Adopting the lens graph" step 1 becomes "require `lens_findings`"; the rollback note; a short "From engine.min to requires" paragraph.
- **REPAIR:** "Upgrade the engine" becomes the following.
  1. Push `zzzops/policy/requires-<name>` adding the names to `settings.engine.requires`. This pauses new starts everywhere.
  2. Wait until nothing is `running`.
  3. Upgrade the plugin on every machine. `zzzops validate` shows the names in `engine.capabilities`.
  4. Land the branch and delete it.

  The rollback removes the names, and finds the newer build's writes with `--grep='^Engine: <build id>$'`, the build id coming from `zzzops --version`. The bulk-revert recipe says "build id" for "version".
- **docs/design** (G1017's rule). The section names below come from the rev 6.3 sources that G1017 moves. The implementer finds them in the moved files with test 10's grep.
  - **SPEC:**
    - §3.2: the settings shape (`engine.min` optional and deprecated, `requires`).
    - §4.5: the tolerant floor read and the floor itself. The ceiling is removed, and the bump list is restated as in §3.6.
    - The `blockers` kinds: `engine_too_old` gains `missing`; `engine_too_new` goes.
    - The exit-code and error table: `engine_too_new` goes.
    - The tolerant read order.
    - The `new` and `start` verb rows: "outside `engine.min`" and `engine_too_new`.
    - §4.8: fingerprint versions, and the op-version sentence (both per §3.6).
    - The goal-commit trailer definition, and `--version`.
    - The REPAIR summaries ("Upgrade the engine", bulk revert by build id).
    - Test-list item 75 (the floor test), restated as tests 1-3 below.
  - **DESIGN:**
    - §3.10's floor, ceiling and upgrade bullets, including the `evo:H4` trade-off from §3.3.
    - The settings list.
    - The failure table row for an old engine.
    - D4 (fingerprint version per §3.6).
    - Invariant 21.
  - **HISTORY:** a §4 row.
  - **README:** delete this goal's pending row, if one exists.

## 5. Coordination with in-flight goals

The rule: every goal that would have raised `ENGINE_VERSION` declares a capability file instead. If it merges **after** G1027, its implement adds the file. If it merges **before**, G1027's implement (whose `base` re-runs) adds both its file and its version to `LEGACY_VERSIONS`.

- **G1022** (approved; depends on 1000, 1020, 1017, not 1027). Capability **`lenses`**: the node field `lenses` and the finding key `lens`.
  - **G1027 merges first:** G1022's implement adds `engine/capabilities/lenses.txt` instead of the "next minor" bump.
  - **G1022 merges first:** G1027 adds `"1.2.0": ("lens_findings", "lenses")` to the map, and `lenses.txt`.
  - Either way, its floor branch (G1022 §8 step 2) requires `["lens_findings", "lenses"]` instead of raising `engine.min`.
  - No new dependency edge: it would re-stale G1022's approved design for a one-file swap. The root passes this paragraph to G1022's implement as a note. The swap is the only deviation from G1022's approved design.
- **G1024** (depends on 1027, design waiting). Two points for its design:
  - Its template provenance record must not use an engine version. A template digest and/or `build_id()` serve.
  - If its record adds an optional settings key, or any other format a pre-G1024 engine rejects, it adds capability **`policy_update`** and requires it. If the record is a separate file that older engines ignore, it needs no capability.
- **G1025** (design approved; depends on 1017, not 1027). Capability **`release_lines`**. The root recorded this name in G1025's approve_design, replacing the `branching` that G1025's design text uses. The policy block stays `settings.branching`.
  - **What it gates.** As G1025's design says, `release_lines` gates both a policy that sets `settings.branching` and the writing of schema-2 goal documents. `GOAL_SCHEMAS` still guards reading: an older engine treats a schema-2 goal as newer and read-only. G1027 leaves those details to G1025.
  - **G1027 merges first:** G1025's implement adds `engine/capabilities/release_lines.txt`, and its rollout requires `release_lines` instead of raising `engine.min`.
  - **G1025 merges first:** if it raised `ENGINE_VERSION`, G1027's implement adds that version to `LEGACY_VERSIONS` with the capabilities then shipped, and adds `release_lines.txt`. If it merged already declaring `release_lines` against a capabilities form that did not exist yet, G1027 adopts its file as is.
  - **No dependency edge.** Adding G1025→G1027 would make G1025's approved design stale (root decision). The root passes this paragraph to G1025's implement as a note, as for G1022.
- **This repository** (G1000 rollout step 3, after G1022): the lens policy branch sets `settings.engine.requires` to the capabilities its graph needs, `["lens_findings", "lenses"]`, and removes `engine.min`. The owner approved locking out 1.0 engines, and the Codex agent on 15b59a5 is finished.
  - If the earlier floor branch already landed with `engine.min: 1.1.0` or `1.2.0`, it keeps working through the map, and `validate` warns until a policy branch replaces it.

## 6. Tests

New `.agents/test_engine_capabilities.py`, plus edits to the existing tests listed in §2:
1. **Missing capability refuses.** With a policy `requires: ["no_such_cap", "lens_findings"]`, `next` shows `engine_too_old` with `missing == ["no_such_cap"]`, and a write exits 1 with the code `engine_too_old` and `details.missing`. The message names the capability and says "upgrade the plugin".
2. **Present capability proceeds.** `requires: ["lens_findings"]` allows writes, as does `requires: []`.
3. **The engine.min map.** These replace `test_engine_store.py:226,772` and `test_engine_review_fixes.py:133`.
   - `0.0.0`, `1.0.0` and `1.1.0` proceed, and `validate` shows `engine_min_deprecated`.
   - `99.0.0` refuses with the "last numbered engine" message.
   - `min: 1.1.0` with `lens_findings` removed from `CAPABILITIES` (monkeypatched) refuses, naming `lens_findings`.
   - `next` carries no deprecation warning.
4. **Schema.** `requires` must be an array of unique `NODE_ID` strings (`"Bad"`, a duplicate and a non-list each fail). `min` is optional. A policy with an `engine` block but no `min` is valid. The bad-version case in `test_engine_schemas.py:158` is kept.
5. **Merge without conflict.** In a scratch repository holding a copy of `engine/capabilities/`, two branches each add a different `<name>.txt`. `git merge` succeeds cleanly, and the loaded set contains both names.
6. **Declared files.** Every file name matches `NODE_ID` and no file is empty. A pinned list, `SHIPPED = {"lens_findings"}` (plus `lenses` if G1022 merged first), must be a subset of `CAPABILITIES`, so a capability is never removed.
7. **Build id.**
   - A new goal commit ends `Engine: <version> <12 hex>`, matching `package_provenance()`. This updates `test_engine_store.py:287` and `engine_fixtures.py`.
   - `--version` prints the same string.
   - With provenance monkeypatched to raise, the trailer is `Engine: unknown` and the write succeeds.
   - `validate` shows `engine.build` and `engine.capabilities`.
8. **Legacy key.** The key uses `DETECTOR` and not the build id (rewritten `test_engine_legacy.py:99-154`), and `checked.engine` is the build id. A changed build id with the same detector does not trigger a re-check.
9. **Template.** The default template validates and requires `lens_findings`. Bootstrap copies it.
10. **No stale references.** `git grep -nE 'ENGINE_VERSION|REQUIRES_MIN|requires_min|engine_too_new|engine\.min bump'` is empty over `plugins/`, `.agents/` and `docs/design/` (excluding `docs/design/HISTORY.md`, which keeps history).
    - The test that asserts this sits in `test_engine_capabilities.py` and also excludes itself.
    - `engine.min` itself may still appear, as the deprecated key.
    - docs/design passes G1017's guard.

The full suite (`python3 -m unittest discover -s .agents`) passes.

## 7. Risks

- **Old dev builds see `policy_invalid`, not `engine_too_old`,** once a policy uses `requires`. Work is paused and writes are refused, so the failure is safe. Only the wording is less helpful. MIGRATING says so. This only affects unreleased builds the owner has already approved locking out.
- **A forgotten capability.** A goal adds a format without a capability file. This is the same risk as today's forgotten version bump, but with no ordering race. The rule sits where the old one was (the schemas comment and CLI_USAGE), and review_impl's rollout lens checks it.
- **Build id cost.** Hashing about 1.5 MB once per writing process. It is cached, and it is not computed for `next` alone (the legacy key uses `DETECTOR`).
- **Merge order with G1022 and G1025.** Both orders are covered in §5. G1027's implement re-classifies at every `base` re-run.

## 8. Out of scope

- Removing a capability, or a "ceiling" (engine refuses to coexist with older ones). A future goal designs this if it is ever needed.
- A `validate` check that a policy whose graph uses a format also requires its capability. This would be a useful follow-up, and is not needed for the acceptance.
- Changing this repository's `.zzzops/POLICY.json`. That happens through the policy branch in §5.
- Any change to semantic-release, plugin versions or `GOAL_SCHEMAS`.
