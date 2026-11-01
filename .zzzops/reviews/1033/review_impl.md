# G1033 review_impl, attempt 1

**Verdict: approved.** The implementation matches design revision 2, release bundles stay byte-identical apart from `package.py` itself, and nothing outside the diff depends on the old hint text. I have no findings.

Subject: code at `a1d408f`, tests at `48a9617`, base `b452cd7`. `run_tests` passed.

## package.py

- **`channel_for_version`** returns `development` for exactly `0.0.0-dev` (`DEVELOPMENT_VERSION`) and `official` otherwise. `package_status()` now uses it in place of its inline expression.
- **`_is_codex_cachebuster`** is the old inline check, extracted unchanged: the same regex and the same "`+` not in the version" guard. It now also type-checks both arguments. `package_status()` and `install_harness()` share it.
- **`install_harness()` follows the design's order:**
  1. The cachebuster gives `codex`. Manifest read errors, including a non-dict manifest (`AttributeError`), are swallowed.
  2. Under `<base>/plugins/` for a Claude base, either `$CLAUDE_CONFIG_DIR` or `~/.claude`, gives `claude`.
  3. The same test for a Codex base, either `$CODEX_HOME` or `~/.codex`, gives `codex`.
  4. A sibling `.claude-plugin/marketplace.json` with no `.agents/plugins/marketplace.json` gives `claude`. It takes the catalog `name` when that matches `NAME_PATTERN`.
  5. Anything else gives `(None, None)`.

  The bases are resolved, and a missing home is guarded (`RuntimeError`, `KeyError`, `OSError`). `PLUGIN_ROOT` is already resolved, and `Path.is_relative_to` is fine on the engine's Python 3.10 floor.
- **`_cache_marketplace`** takes the segment after `plugins/cache/`, which is `<m>` in `cache/<m>/zzzops/<version>`. It returns `None`, and so falls back to `zzzops`, for any other layout under `plugins/`, such as `plugins/marketplaces/…`. The docstring explains where `<m>` comes from and why a layout change falls back instead of guessing, as the review asked.
- **`reinstall_hint`:**
  - Claude: `update or reinstall ZzzOps in Claude Code: claude plugin marketplace update <m>, then claude plugin update zzzops@<m>.`
  - Codex: the previous text, unchanged.
  - Otherwise: the neutral text.
- **The `harness` key** is on both the ok dict and the failure dict. `cli.package_check()` still reads only `ok` and `detail`, so the CLI output shape is unchanged.

## Build script

`plugin_files()` gets `channel_for_version` from the `runpy`-loaded `package.py` and passes its result to the renderer in place of the literal `"official"`.

**Byte-identity check.** I ran `plugin_files(root, "2.0.0")` on extracts of `b452cd7` and of `a1d408f`. Both give 74 files, and the only one that differs is `zzzops/package.py`, whose source this goal changes. Release rendering is therefore unchanged.

## claude_plugin_acceptance.py

- **`require_no_package_check`** checks the report's shape: it needs a dict with a list of strings. It fails only on entries that start with `plugin package` or that contain `skill discovery metadata`, so gh and git entries are ignored.
- **`prepare_validate_project`** gives the project one empty commit (with an inline identity), a bare origin, a pushed `main` and `zzzops.integrationBranch main`. The project is now initialised with `-b main`.
- **`full_validate`** runs `sys.executable <runtime> validate` in the project and reads its JSON whatever the exit code. That is correct, because a repository without a policy exits non-zero.
- **The two calls are in place:**
  - on the generated marketplace's runtime, right after the generator check;
  - on the installed cache's runtime, after the shipped-templates check.

## Docs

- **`CLAUDE_MARKETPLACE.md`** states the channel rule, the two full-`validate` runs, that git and gh entries are ignored (CI has no token), and the hint for each harness.
- **`MAINTAINING.md`** states that the bundle builder and the self-check share `package.channel_for_version`.
- **SPEC and DESIGN** quote no hint text, so no contract amendment is needed.

## Outside the diff

- **"Codex marketplace" / "reinstall ZzzOps".** The other matches are only the tests this goal updated (`test_agent_plugin`, `test_plugin_cachebuster`) and unrelated prose (`LEGACY_CLEANUP.md`, `MAINTAINING.md:101`).
- **`package_status()` callers:**
  - `cli.package_check` uses only `ok` and `detail`;
  - `test_engine_legacy.py:554` asserts only `ok`;
  - the remaining matches are the tests this goal updated, plus historical migration notes under `.zzzops/migration`.

  Nothing asserts an exact key set.
