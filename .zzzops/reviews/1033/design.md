# G1033 design: the Claude build reports a false skill-metadata mismatch with a Codex-only hint

Revision 1.

## Outcome

- A Claude marketplace built by `.github/scripts/build_claude_plugin.py` passes the package self-check. This covers installs made from that marketplace and runs in place from its directory. `zzzops validate` run from it reports no `environment` entry.
- The rule that maps a version to a channel lives in one place, and both the build and the check use it, so the two cannot drift apart again.
- When the self-check does fail, the reinstall hint names the harness the package was installed for: Claude Code, Codex, or both when that cannot be told.
- CI runs the full `validate` from a generated Claude marketplace, not only `validate --policy`, so this regression cannot come back unseen.

## Reproduction (read_dev 8d8437a; cache built from c3791a0)

- I made a fresh repository with one commit, pushed it to a local bare origin and set `zzzops.integrationBranch main`. Running `~/.cache/zzzops-claude-marketplace-c3791a0-20261101/zzzops/bin/zzzops validate` there prints:
  `environment: ["plugin package: skill discovery metadata does not match the plugin build: skills/add-zzzops-goal/SKILL.md; reinstall ZzzOps from its Codex marketplace."]`
- A scratch clone of this repository (with `zzzops.integrationBranch dev`) prints the same entry.
- **Difference from the card's note:** in this session, `validate` run in `/home/dave/Work/dev/zzzops` from that cache also prints the entry. The check does not depend on the repository at all: `package_status()` reads only the plugin's own tree (`PLUGIN_ROOT`). Nothing about the repository explains a run without the error. The earlier run most likely used another command (only `validate` reports `environment`) or another launcher, such as the Codex install or the source tree. The check's inputs do not support any other explanation.
- The real Claude install on this machine, `~/.claude/plugins/cache/zzzops/zzzops/unknown/`, was installed from a generated directory marketplace. Claude shows its version as `unknown` because the marketplace is not Git-backed. It has the same `— official plugin.` text and the same error. So the bug reaches real Claude installs, not only in-place runs.
- Installs from the repository marketplace itself (`.claude-plugin/marketplace.json` → `./plugins/zzzops`) are not affected. The canonical source passes the check: I ran `plugins/zzzops/bin/zzzops validate` from a dev checkout and got `environment: []`.

## Cause

- `build_marketplace_bundle.plugin_files(root, version)` always calls `render_skill_metadata(relative, data, version, "official")`. This function backs both the OpenAI release bundle and `claude_marketplace_files`.
- `package_status()` works out the channel it expects from the manifest: `"development" if version == "0.0.0-dev" else "official"`.
- The Claude build is run with the canonical version. `claude_plugin_acceptance.py` passes `--version <plugins/zzzops/plugin.json version>`, which is `0.0.0-dev`, and the c3791a0 cache was built the same way. The output therefore says `ZzzOps v0.0.0-dev — official plugin.` in every `SKILL.md`, and `[ZzzOps] …` in every `agents/openai.yaml`. The check expects `— development plugin.` and `[ZzzOps 0.0.0-dev] …`. It reports the first file it reaches, `skills/add-zzzops-goal/SKILL.md`.
- The release bundle never hits this case, because it is built with a real semantic version, for which "official" is correct.
- CI missed it because `claude_plugin_acceptance.py` installs from a copy of the canonical tree (`write_repository_marketplace`), which is the development channel and passes. It checks the generated marketplace only with `claude plugin validate`. It runs the packaged CLI only as `--help` and `validate --policy`, and that offline path (`validate_policy_dir`) never calls `package_check()`.
- The hint is hard-coded in `package_status()`: `f"{exc}; reinstall ZzzOps from its Codex marketplace."`.

I checked the fix: I patched only the channel argument in a scratch clone and rebuilt with `--version 0.0.0-dev`. `validate` then gives `environment: []`. A `--version 1.2.0` build also gives `[]`. The generated `skills/` then differ from the canonical tree only in YAML quoting.

## Approach

### 1. One channel rule, used by the build and the check (fix the build, keep the check)

- Add `channel_for_version(version: str) -> str` to `plugins/zzzops/zzzops/package.py`. It returns `"development"` for `0.0.0-dev` and `"official"` for anything else. `package_status()` uses it in place of its inline expression.
- `plugin_files()` already loads `package.py` through `runpy`. It now calls `package["channel_for_version"](version)` and passes the result to the renderer, instead of the literal `"official"`.
- Effects:
  - The OpenAI release bundle is unchanged, because it is always built with a semantic release version.
  - A Claude build with `0.0.0-dev` now renders the development channel, the same as the canonical source.

### 2. A harness-aware hint

- `package.py` gains `install_harness() -> "claude" | "codex" | None`, which works from `PLUGIN_ROOT`. The first rule that matches wins:
  1. The Codex manifest version has the `+codex.` cachebuster shape the check already accepts → `codex`.
  2. `PLUGIN_ROOT` is under `<base>/plugins/` for a Claude base (`$CLAUDE_CONFIG_DIR` if set, then `~/.claude`) → `claude`.
  3. `PLUGIN_ROOT` is under `<base>/plugins/` for a Codex base (`$CODEX_HOME` if set, then `~/.codex`) → `codex`.
  4. `PLUGIN_ROOT.parent/.claude-plugin/marketplace.json` exists and `PLUGIN_ROOT.parent/.agents/plugins/marketplace.json` does not → `claude`. This is the generated Claude marketplace run in place, like the c3791a0 cache.
  5. Otherwise `None`. This covers a source checkout (`plugins/zzzops`, where both marketplaces sit two levels up) and unknown layouts.
- `package_status()` builds the failure detail as `f"{exc}; {reinstall_hint(harness)}"`:
  - `claude`: `update or reinstall ZzzOps in Claude Code: claude plugin marketplace update <m>, then claude plugin update zzzops@<m>.` Here `<m>` is the path segment after `plugins/cache/` when installed, and `zzzops` otherwise.
  - `codex`: `reinstall ZzzOps from its Codex marketplace.` This is today's text, kept for Codex.
  - `None`: `reinstall ZzzOps from the Claude Code or Codex marketplace it was installed from.`
- `package_status()` also returns `"harness"` in both the ok and the failure dict, which tests can use. `cli.package_check()` still uses only `detail`, so the CLI output shape does not change.
- Rules 2 and 3 do the main work. They follow each harness's documented install cache. On this machine those are `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` and `~/.codex/plugins/cache/<marketplace>/<plugin>/…`. The environment variables cover isolated configurations; CI's acceptance sets `CLAUDE_CONFIG_DIR`.
- The detection only shapes the hint and gates nothing. If it guesses wrong, the hint names the wrong harness but the check still fails correctly. The `None` text is safe in every case.

### 3. Docs

- `docs/CLAUDE_MARKETPLACE.md`, "Verification evidence": state that the generated marketplace renders skill metadata for the channel that matches its version. Also state that acceptance runs the full `validate` from the generated marketplace and from the installed cache, and requires `environment` to be empty.
- `docs/MAINTAINING.md`, Semantic releases: one sentence saying the channel comes from the version through `package.channel_for_version`, and that the build and the check share it.
- No DESIGN or SPEC contract change. DESIGN C4 and R11 only keep the `package_status` self-check. They do not fix its text or harness. Two cases if G1017's `docs/design/` lands first:
  - If its SPEC names the Codex-only hint, this goal's PR corrects that line.
  - Otherwise there is nothing to add to its pending-amendments list.

## Alternatives rejected

- **Relax the check to accept either channel in `SKILL.md`.** This hides the false claim instead of fixing it: a development build would keep telling users it is the "official plugin" in skill discovery. It would also weaken the check against mixed installs.
- **Make `build_claude_plugin.py` reject `0.0.0-dev`, or always pass a release version.** Claude's cache identity comes from the Git commit, and the documented contract is that CI never writes a second semantic version. Acceptance would need a fake version, and a generated dev marketplace would still be impossible to build.
- **Stamp a harness marker file at build time.** The main Claude install path (the repository marketplace) consumes `plugins/zzzops` directly, with no build step. A marker would cover only generated marketplaces and would be a second piece of state to keep in step.
- **Detect the harness from the running agent's environment** (for example `CLAUDECODE`). This shows which agent is running the CLI, not which harness installed the package. It is also undocumented as a contract. Install location is the fact that matters.

## Interfaces and data that change

- `package.py`:
  - new `channel_for_version()`, `install_harness()` and `reinstall_hint()`;
  - `package_status()` gains a `harness` key, and its failure `detail` ends with the harness-specific hint.
- `build_marketplace_bundle.plugin_files()`: the rendered channel follows the version. Generated `0.0.0-dev` marketplaces change from "official" to "development" metadata. Release bundles are byte-identical.
- `claude_plugin_acceptance.py`: it gains full-`validate` runs (see Tests).
- CLI output: only the text of an `environment` entry changes, and only when the self-check fails. No schema, key or exit code changes. Stored records and policy formats are untouched.

## Risks

- **Tests that pin the old hint text.** I found none that assert on "Codex marketplace". The cachebuster and agent-plugin tests assert on `ok` and version, but a grep for the string will be part of implement.
- **Wrong harness guess.** Covered above: it affects only advice, and the `None` fallback is neutral.
- **Home directory not resolvable** (`Path.home()` raises). Guard it and treat that base as absent.
- **Symlinked install roots.** `PLUGIN_ROOT` is already resolved, so compare against resolved bases.
- **Existing generated installs.** Users with a Claude install from an old generated marketplace keep seeing the error until they rebuild and update. The new hint tells them how. The machine's `~/.claude/plugins/cache/zzzops/zzzops/unknown/` is one of these; this goal does not touch it.

## Tests

- `.agents/test_marketplace_bundle.py` runs on every platform leg and needs no Claude CLI.
  - **New test:** `build_claude_plugin.write_marketplace(ROOT, tmp/out, <canonical version>)`, as acceptance does. Then create a temp repository with one commit, a local bare origin and `zzzops.integrationBranch main`, and run `tmp/out/zzzops/bin/zzzops validate` in it. Assert:
    - `environment == []`;
    - the `policy` entry is the expected "no ZzzOps policy" one, which shows that `validate` got past setup.
  - Repeat with `--version 2.0.0`.
  - Assert the generated `SKILL.md` for `0.0.0-dev` contains `— development plugin.`, and for `2.0.0` contains `— official plugin.` The existing official-channel assertion stays.
- `.agents/test_agent_plugin.py`:
  - `channel_for_version` cases: `0.0.0-dev` gives development, and `1.0.0` gives official. Also assert that a copy whose Codex manifest has a `+codex.` cachebuster still uses the development channel. The channel comes from the Agent Plugins manifest version, which the cachebuster never changes.
  - Copy the plugin tree to a temp location and break one `SKILL.md`. Load `package.py` from the copy with `runpy` and check the hint:
    - under `<tmp>/claude/plugins/cache/mk/zzzops/abc/` with `CLAUDE_CONFIG_DIR=<tmp>/claude`, the detail contains `claude plugin update zzzops@mk`, and `harness == "claude"`;
    - under `<tmp>/codex/plugins/cache/...` with `CODEX_HOME`, it contains `Codex marketplace`;
    - with a generated-marketplace layout (sibling `.claude-plugin/marketplace.json`), the result is `claude`;
    - with no recognisable layout, the result is the neutral text, and `harness is None`.
- `.agents/test_plugin_cachebuster.py`: one assertion that a failing cachebustered copy names Codex.
- `.agents/claude_plugin_acceptance.py`, CI's `validate-claude` leg:
  - Give `project` a commit, a bare origin and `zzzops.integrationBranch`.
  - Run `<generated>/zzzops/bin/zzzops validate` and `<install>/zzzops/zzzops.py validate` there, and require `environment == []` for both.
  - `.agents/test_claude_plugin_acceptance.py` gets matching fakes if it stubs those calls.
- Manual check before submit of implement: rebuild a marketplace from the goal branch with `--version 0.0.0-dev` and repeat the reproduction above. Expect `environment: []`.

## Out of scope

- Changing which harness channel users install from, or the `0.0.0-dev` and Git-SHA versioning contract.
- Repairing the installed caches on this machine (`~/.cache/zzzops-claude-marketplace-c3791a0-20261101`, `~/.claude/plugins/cache/zzzops/zzzops/unknown`). Rebuild and update them after merge.
- Making `validate --policy` run the package self-check.
- Any other `package_status` failure modes, beyond giving them the new hint.

No child goals are needed; this is one PR.
