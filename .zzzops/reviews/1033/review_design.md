# G1033 review_design, attempt 1

**Verdict: changes requested, for one finding about the tests.** The cause, the fix and the hint design are right; I reproduced both the bug and the fix at read_dev `8d8437a`. But the planned assertion `environment == []` also checks `gh`, so it would fail in CI for a reason that has nothing to do with this bug.

## What I verified

- **Cause.**
  - `build_marketplace_bundle.plugin_files()` (line 217) always calls `renderer(relative, data, version, "official")`.
  - `package.package_status()` (line 242) expects `"development" if version == "0.0.0-dev" else "official"`.
  - The failure detail (line 260) is hard-coded to "reinstall ZzzOps from its Codex marketplace."
- **Reproduction.** I built a Claude marketplace from a scratch extract of `8d8437a` with `build_claude_plugin.py --version 0.0.0-dev`. Its `package_status()` returns `ok: false` with exactly the reported detail (`skills/add-zzzops-goal/SKILL.md`).
- **Fix.** After patching only the channel argument to follow the version and rebuilding, `package_status()` returns `ok: true`.
- **One shared rule.** `channel_for_version` in `package.py`, used by both the build (already loaded through `runpy`) and the check, is the smallest way to stop them drifting. Release bundles are always built with a semantic version, so they stay byte-identical.
- **Rejected alternatives.** The design rejects relaxing the check, forbidding `0.0.0-dev`, a marker file, and detecting the harness from the running agent's environment. All four rejections are well argued.
- **Harness detection.**
  - The order is sound: cachebuster → Claude base → Codex base → generated-marketplace layout → `None`.
  - Rule 4 matches the c3791a0 cache layout: `.claude-plugin/` is next to `zzzops/`, and there is no `.agents/plugins/marketplace.json`.
  - Rules 2 and 3 match the real install caches here: `~/.claude/plugins/cache/<m>/zzzops/<v>/` and `~/.codex/plugins/cache/<m>/…`.
  - In the repository, `.codex-plugin/plugin.json` is plain `0.0.0-dev`, so rule 1 cannot misfire on a Claude install made from the canonical tree.
  - A wrong guess only affects advice, and the `None` fallback text is neutral.
- **Why CI missed it.** The acceptance installs from a copy of the canonical tree and runs only `--help` and `validate --policy`, and that path never calls `package_check()` (`cli.py:274`). The new full-`validate` runs close that gap.
- **docs/design.** I agree there is no contract change. If G1017 lands first, its SPEC only needs a correction if it quotes the Codex-only hint.

## F1 (target: design): `environment == []` also asserts that gh is installed and authenticated, so CI would fail

`validate`'s `environment` list is more than the package check. In `cli.py:194-202` it is `check_environment(git)` + `gh_problems(s)` + `package_check()`. `gh_problems` reports "gh is not installed …" or "gh is not authenticated: run `gh auth login`, or set GH_TOKEN" (`gh.py:72-81`).

That breaks the planned assertions:
- The `validate-linux` and `validate-claude` jobs do not export a GitHub token (`permissions: contents: read`, no `GH_TOKEN` env). Their `validate` will list the gh entry.
- A developer machine without gh lists the other gh entry.

So the new test in `test_marketplace_bundle.py` and the new acceptance checks would fail even with the fix in place. The design's local reproduction passed only because gh is authenticated on this machine.

**Fix (either option).**
- Assert that no `environment` entry starts with `plugin package:`. Also assert, positively, that the bug's text (`skill discovery metadata`) is absent. This keeps the assertion on the bug itself.
- Or put a fake `gh` on `PATH` that answers `--version` and `auth status`. `.agents/engine_fake_gh.py` is available.

The first option is simpler and does not depend on the platform. Keep the other planned assertions on the rendered `SKILL.md` channel and the `policy` entry.

## Non-blocking notes

- **"Runs on every platform leg" is not accurate.** Windows and macOS run only the test ids listed in `run_product_validation.NATIVE_COVERAGE`. The new test will run on Linux, which is enough to catch the regression. If you want it on Windows too, add it to `NATIVE_COVERAGE` and run `python <out>/zzzops/zzzops/zzzops.py validate` instead of the POSIX `bin/zzzops` launcher.
- **The new `harness` key in `package_status()`.** No test in `.agents` calls `package_status()` directly, so the new key breaks nothing. Still grep for exact-dict assertions at implement.
- **`<m>` in the Claude hint.** For a generated directory marketplace, `<m>` is the marketplace name from its `marketplace.json`, which here equals the cache segment. Taking it from the path is fine. Say so in a comment, so a future layout change does not silently break it.
