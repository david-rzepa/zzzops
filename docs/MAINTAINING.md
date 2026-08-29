# Maintaining ZzzOps

This guide holds repository-development details intentionally kept out of the new-user [README](../README.md). User-facing workflows live in [Advanced ZzzOps workflows](ADVANCED.md).

## Repository architecture

The distributable Agent Plugin lives in `plugins/zzzops`; `.agents/plugins/marketplace.json` publishes it to Codex. Codex and Claude Code distributions are generated from shared canonical sources rather than maintained as divergent implementations.

`plugins/zzzops/zzzops/zzzops.py` is the stable installed executable and CLI composition layer. Its focused implementation modules remain acyclic:

| Module | Owns |
| --- | --- |
| `policy.py` | Reviewed project state, policy validation, initialization, and resource policy. |
| `reservation.py` | GitHub-backed goal and resource reservation coordination. |
| `feedback.py` | Privacy-safe execution reports, provenance, payload preparation, and submission. |
| `coaching.py` | Bounded, privacy-safe attribution of completed software-agent work. |
| `goals.py` | Managed-goal parsing, validation, rendering, GitHub record projection, and guarded transitions. |
| `portfolio.py` | Goal graph audits, actionability, and canonical portfolio snapshots. |
| `package.py` | Agent Plugin package validation and deterministic package provenance. |
| `installation.py` | Per-repository package validation state and composition of the cleanup audit. |
| `entropy.py` | Atomic, compact Git-local entropy observations and suggestion-category filtering. |
| `zzzops.py` | CLI parsing and dispatch, provider probes and adapters, package validation, and stable re-exports. |

The package checkpoint validates the installed manifest, required surfaces, and deterministic SHA-256 provenance before provider access. Keep cross-module dependencies one-way: focused modules may use explicitly configured entry-point callbacks, while callers continue to invoke the stable `zzzops.py` command or re-exported API.

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

Canonical repository metadata stays at `0.0.0-dev`. Release preparation renders the semantic release version and official channel into the temporary OpenAI bundle; CI never commits generated release metadata back to `dev`. Claude marketplace validation and installed-cache acceptance run directly from repository state and do not publish a duplicate archive.

A build or validation failure stops publication. Successful artifacts attach to the matching GitHub Release. OpenAI portal upload, attestation, review submission, approval, and final directory publication remain explicit human actions; see the [marketplace sources](../marketplace/README.md). Claude submission guidance lives in [Claude Code marketplace notes](CLAUDE_MARKETPLACE.md), and the shared language and intent map live in [product discovery positioning](DISCOVERY.md).

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
<python> -m unittest discover -s plugins/zzzops/skills/migrate-to-zzzops/scripts -p 'test_*.py'
npm ci
npm run test:plugin
npm run test:release
<python> .agents/manual_acceptance.py coverage
<python> .agents/prompt_stats.py --check
<python> -m compileall -q .agents plugins/zzzops .github/scripts
```

Acceptance infrastructure and manual evidence are documented in the [acceptance test plan](ACCEPTANCE_TEST_PLAN.md).

## Repository file reference

- `plugins/zzzops/plugin.json` — distributable Agent Plugins v1 manifest.
- `plugins/zzzops/skills/` — canonical skill instructions.
- `plugins/zzzops/rules/` — shared workflow rules.
- `plugins/zzzops/zzzops/` — deterministic control modules and CLI entry point.
- `plugins/zzzops/scripts/cleanup_legacy.py` — dry-run-first cleanup for proven retired installations.
- `.agents/plugins/marketplace.json` — Codex marketplace entry.
- `.claude-plugin/` — tracked Claude marketplace metadata pointing at the canonical plugin source.
- `marketplace/` — reviewed OpenAI listing, test, availability, and attestation sources.
- `.github/workflows/` — PR validation and semantic release automation.
- `.github/scripts/` — release, package, and validation helpers.

Target-project `.zzzops` policy and goal state never ships inside the plugin.

## Prompt budget

`.agents/prompt_stats.py` estimates prompt size as `ceil(canonical UTF-8 bytes / 4)` after LF normalization. It measures regression risk, not billing. CI enforces committed limits for always-loaded `AGENTS.md` context and the frequently routed goal-capture and execution paths. Other mutually exclusive workflows remain advisory rather than sharing a misleading global allowance.

After prompt Markdown changes, inspect the relevant profiles and enforce committed ceilings:

```powershell
<python> .agents/prompt_stats.py
<python> .agents/prompt_stats.py --profiles
<python> .agents/prompt_stats.py --check
```

The [context-engineering audit](CONTEXT_ENGINEERING.md) records the repository's application of modern guidance without changing installed runtime behavior.
