# Maintaining ZzzOps

This guide holds repository-development details intentionally kept out of the new-user [README](../README.md). User-facing behaviour is described in [How execution works](EXECUTION.md).

## Repository architecture

The distributable Agent Plugin lives in `plugins/zzzops`; `.agents/plugins/marketplace.json` publishes it to Codex. Codex and Claude Code distributions are generated from shared canonical sources rather than maintained as divergent implementations.

`plugins/zzzops/zzzops/zzzops.py` is the stable installed executable; it only calls `engine.cli.main`. The engine is the package `plugins/zzzops/zzzops/engine/` (standard library only, Python 3.10+), designed in [DESIGN.md](design/DESIGN.md) and specified in [SPEC.md](design/SPEC.md). The `DESIGN §`, `SPEC §`, `REV6 H<n>` and `Step <n>` citations in engine code and tests resolve to the documents in `docs/design/` (see its [README](design/README.md)). The modules:

| Module | Owns |
| --- | --- |
| `canon.py`, `errors.py`, `schemas.py` | Canonical JSON and time, the error envelope and exit codes, validation of every file format and the parsed graph. |
| `fingerprint.py`, `frontier.py`, `records.py`, `render.py`, `card.py` | The pure core: fingerprints, the two-pass frontier and portfolio, record and finding construction, `next` and task-card rendering. No I/O in `frontier.py`. |
| `gitrun.py`, `identity.py` | The one Git runner and environment checks; `code_tree`, `change`, patch ids, artifact commits and the I1/I2 checks. |
| `store.py`, `session.py`, `leases.py`, `worktree.py` | Fetch and snapshot, reading goals and policy, per-goal compare-and-swap writes and the generic close; leases; the goal worktree and sync rule. |
| `verbs.py`, `carry.py`, `cli.py` | The lifecycle verbs, carry-forward across a clean replay, the CLI. |
| `ops/` | `git.base`, `checks.run`, `git.integrate`, `github.merge`, and the op runner; `gh.py` wraps `gh`. |
| `package.py`, `concepts.py` | Agent Plugin package validation and provenance; the concept catalog. |

Engine tests are `.agents/test_engine_*.py`; they run against a bare remote with two clones and a fake GitHub (`.agents/engine_fixtures.py`, `.agents/engine_fake_gh.py`).

## Development and review

Develop on branches created from `dev` and open PRs against `dev`. PR validation runs for every target branch so each stacked layer—or explicitly chained fallback PR—receives exact-head evidence before retargeting. The read-only **PR validation / dev-required-tests** job must pass before merge.

Source-changing goals use one branch and PR per goal, Conventional Commits, human review after checks, and dependency merge order. `main` is reserved for intentional owner releases. See [execution and review](EXECUTION.md) and [branch protection](BRANCH_PROTECTION.md).

### Test a pushed development commit in Codex

Development installs use Codex's normal Git marketplace path. Commit and push the state you want to test, copy its full immutable Git SHA, then replace any existing ZzzOps development marketplace and plugin:

```powershell
codex plugin remove zzzops@zzzops
codex plugin marketplace remove zzzops
codex plugin marketplace add david-rzepa/zzzops --ref <full-commit-sha>
codex plugin add zzzops@zzzops
```

Open a new Codex task so skill discovery reloads the plugin. The installed manifests and every skill description identify this source channel as `0.0.0-dev`; the immutable SHA identifies the exact build. Dirty or uncommitted working-tree installation is intentionally unsupported—use repository tests before pushing those changes.

## Semantic releases

Each push to `dev` runs `semantic-release --dry-run` with read-only repository permission. Dry runs skip tag creation and publication. An intended owner update to `main` runs the full product-validation matrix before semantic-release receives `contents: write`.

Every release prepares one validated versioned marketplace asset before GitHub publication:

- `zzzops-plugin-v<version>.zip` — OpenAI portal skills bundle.

Canonical Agent Plugin and Codex metadata stays at `0.0.0-dev`. Release preparation renders the semantic release version and official channel into the temporary OpenAI bundle. The channel always follows the version through `package.channel_for_version` (`0.0.0-dev` is development, anything else official), which both the bundle builder and the packaged self-check use, so a generated build cannot fail its own check; CI never commits generated release metadata back to `dev`. Claude metadata omits an explicit plugin version so Claude derives its cache identity from the Git source commit. The release-only `latest` branch controls update cadence, and installed-cache acceptance proves a real two-commit update without publishing a duplicate archive or writing release metadata back to the repository.

A build or validation failure stops publication. Successful artifacts attach to the matching GitHub Release. OpenAI portal upload, attestation, review submission, approval, and final directory publication remain explicit human actions; see the [marketplace sources](../marketplace/README.md). Claude submission guidance lives in [Claude Code marketplace notes](CLAUDE_MARKETPLACE.md).

Semantic commits since the latest reachable `vMAJOR.MINOR.PATCH` tag are the release-history source. A breaking marker produces a major release, `feat` produces minor, and `fix`, `perf`, or `revert` produces patch. Documentation, style, chores, refactors, tests, builds, and CI do not release and are omitted from notes. The highest change wins.

Release-type analysis examines the complete semantic history. For user-facing notes, a release-visible two-parent PR merge ending in `(#N)` is the canonical entry for commits structurally introduced through that merge's second parent. `.github/scripts/semantic_release_notes.cjs` proves that ancestry with Git before delegating rendering to the official release-notes generator; similar direct commits remain distinct. If an introduced commit carries a breaking change that the merge message does not represent, the adapter keeps the detailed commits instead of hiding the compatibility warning.

After GitHub publishes a semantic release, CI moves the `latest` branch to that release tag's exact commit. Immutable version tags remain reproducible installation sources. No-release runs leave `latest` unchanged, and an older workflow rerun cannot move it behind GitHub's current latest published release.

Release notes live on GitHub Releases rather than in a generated `CHANGELOG.md`. Exact Node and semantic-release plugin versions are pinned in `package-lock.json`; no repository secret is required beyond GitHub's job token.

Preview a release locally without creating a tag or GitHub Release:

```powershell
node .github/scripts/preview_semantic_release.mjs
```

## Validation and CI diagnostics

When a PR or release fails, inspect **PR validation / dev-required-tests** or the **Semantic release** run and its first failing step. Routine goal work runs the smallest distinct local probe and leaves exact-equivalent broad validation to required CI at the pushed head.

If CI is unavailable or a failure needs local reproduction:

```powershell
<python> -m unittest discover -s .agents -p 'test_*.py'
npm ci
npm run test:plugin
npm run test:release
<python> .agents/prompt_stats.py --check
<python> -m compileall -q .agents plugins/zzzops .github/scripts
```

The real-GitHub smoke test is manual: `ZZZOPS_GH_SMOKE_REPO=<owner>/<scratch repo> <python> .agents/engine_gh_smoke.py` (a scratch repository with a ZzzOps policy on its integration branch).

Codex cachebuster acceptance uses the actual upstream helper separately from self-contained unit discovery. Obtain a trusted `update_plugin_cachebuster.py` from Codex's plugin-creator skill, then run:

```powershell
<python> .agents/plugin_cachebuster_acceptance.py --helper /path/to/plugin-creator/scripts/update_plugin_cachebuster.py
```

The helper path is required; missing or unreadable helpers fail. The runner prints the helper SHA-256 and executes one acceptance test covering default and custom cachebusters, package contents, and the packaged CLI using a disposable package copy.

## Repository file reference

- `plugins/zzzops/plugin.json` — distributable Agent Plugins v1 manifest.
- `plugins/zzzops/skills/` — canonical skill instructions.
- `plugins/zzzops/rules/` — the shared communication guide.
- `plugins/zzzops/zzzops/` — the engine, the CLI entry point, references and templates.
- `plugins/zzzops/bin/zzzops` — the launcher.
- `plugins/zzzops/scripts/cleanup_legacy.py` — dry-run-first cleanup for proven retired installations.
- `.agents/plugins/marketplace.json` — Codex marketplace entry.
- `.claude-plugin/` — tracked Claude marketplace metadata pointing at the canonical plugin source.
- `marketplace/` — reviewed OpenAI listing, test, availability, and attestation sources.
- `.github/workflows/` — PR validation and semantic release automation.
- `.github/scripts/` — release, package, and validation helpers.

Target-project `.zzzops` policy and goal state never ships inside the plugin.

## Prompt budget

`.agents/prompt_stats.py` estimates prompt size as `ceil(canonical UTF-8 bytes / 4)` after LF normalization. It measures regression risk, not billing. CI enforces committed limits for the frequently routed goal-capture and execution paths. If root `AGENTS.md` is present, the checker includes it in the always-loaded profile; this repository currently has no such file. Other mutually exclusive workflows remain advisory rather than sharing a misleading global allowance.

After prompt Markdown changes, inspect the relevant profiles and enforce committed ceilings:

```powershell
<python> .agents/prompt_stats.py
<python> .agents/prompt_stats.py --profiles
<python> .agents/prompt_stats.py --check
```

