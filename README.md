# ZzzOps

**Infinite backlog for agents. Finite bedtime for token-addicted humans.**

ZzzOps gives agents an infinite, prioritized backlog so token FOMO stops at bedtime—before another 3:57 a.m. run causes a domestic incident.

## Quickstart

### 1. Install the Agent Plugin

ZzzOps v2 is an [Agent Plugin](https://agent-plugins.org/). The recommended installation is from the [official ZzzOps listing in the Codex Plugins Directory](https://chatgpt.com/plugins/plugins_6a7892fe4c548191a9e0dbfb8ac2c987). Install it there, then open a new Codex task in the target project so its ZzzOps skills are discovered.

As a secondary option, install a reproducible snapshot directly from a released Git tag:

```powershell
codex plugin marketplace add david-rzepa/zzzops@v2.0.0
codex plugin add zzzops@zzzops
```

A tag-pinned Git marketplace stays on that tag. To move to a newer release, remove the installed plugin and pinned source, then add and install the newer released tag. For example, after `v2.0.1` is released:

```powershell
codex plugin remove zzzops@zzzops
codex plugin marketplace remove zzzops
codex plugin marketplace add david-rzepa/zzzops@v2.0.1
codex plugin add zzzops@zzzops
```

Open a new Codex task after installing or upgrading. ZzzOps no longer copies machinery into each project or maintains an installer lock. The package contains exactly nine skills plus their shared rules, control CLI, and blank initialization templates. It never contains project policy, goals, repository instructions, or other project state.

### Claude Code

After the release containing Claude support reaches the repository's default branch, install ZzzOps directly from this repository:

```powershell
claude plugin marketplace add david-rzepa/zzzops
claude plugin install zzzops@zzzops
```

Claude and Codex use the same canonical plugin implementation; only their small platform manifests differ. Direct repository installation does not imply Anthropic directory approval. See the [Claude marketplace and submission handoff](docs/CLAUDE_MARKETPLACE.md).

On the first ZzzOps use in each repository after installation or upgrade, ZzzOps automatically routes once through its installation validator. It checks the installed version and package digest, audits for retired per-project machinery, and then resumes the workflow you originally requested. Repeated workflows use a cheap Git-local record and do not rerun the audit.

```text
Use $validate-zzzops-installation to revalidate this repository explicitly.
```

If proven legacy content exists, the validator shows the exact cleanup plan and asks before removing anything. Declining leaves every file untouched and suppresses repeat prompts for that package; explicit revalidation remains available. Modified, unknown, ambiguous, unsafe, or symlinked paths fail closed. Durable `.zzzops` state and the Git index are preserved. See the [legacy cleanup contract](docs/LEGACY_CLEANUP.md).

[Privacy policy](PRIVACY.md) · [OpenAI compliance review](docs/OPENAI_COMPLIANCE.md) · Support, privacy, and security: [zzzops.support@gmail.com](mailto:zzzops.support@gmail.com)

ZzzOps is independently developed and is not created, supported, certified, endorsed by, or affiliated with OpenAI. It uses your existing GitHub authentication to read and write GitHub Issues and, when your reviewed project policy authorizes implementation, to coordinate Git branches, commits, and pull requests. ZzzOps has no ZzzOps-operated server, telemetry, advertising, or commerce.

After installation, start the policy review workflow.

### 3. Initialize the project

Use the dedicated review skill in the target:

```text
Use $review-zzzops-policy to initialize and summarize this project's policy.
```

The agent first inspects code, docs, config, history, Git, GitHub, and repository policy; proposes the outcome, KPIs, acceptance criteria, GitHub authority, and operating rules; then asks only consequential questions. Deterministic CLI primitives validate the concise charter, detailed audit, and canonical machine policy. You do not fill a blank wizard.

The agent summarizes the meaningful choices and invites adjustments. Ordinary workflows remain blocked until you explicitly approve the current policy; any bound charter, audit, or policy edit invalidates approval. `PROJECT.md` stays a concise human charter and summary, `POLICY.json` is the single machine-readable authority, and digest-bound `PROJECT_AUDIT.md` preserves detail on demand. Running the review skill later always produces a fresh summary before inviting changes.

Once reviewed, these policies let the agent make routine decisions without waking you for every tiny choice.

GitHub Issues is the canonical goal authority. Initialization requires a successful repository and access probe; unavailable authentication, permission, or Issues support becomes an explicit blocker. Initialization does not commit, branch, or mutate GitHub.

The plugin CLI requires Python 3.10 or newer. CLI examples use `<python>` for one compatible interpreter resolved once (`python3`, `python`, Windows `py -3`, or a harness-provided runtime). Agents resolve the CLI from the installed plugin package rather than assuming it exists in the target repository.

**Visibility:** GitHub-backed goals inherit the repository's visibility. Never put authentication secrets, payment-card data, protected health information, government identifiers, or other restricted or raw sensitive data in a goal; redact it or link to an approved private system before capture or migration.

Maintainers: see the [initialization and policy contract](docs/INITIALIZATION.md).

### 4. Bootstrap a repository

For a new project, supply the initial specification:

```text
Use $bootstrap-zzzops-repository to create this project from the following specification: <purpose, stack, deployment target, constraints, and first milestone>.
```

For an established project:

```text
Use $bootstrap-zzzops-repository to make this existing repository agent-ready.
```

Bootstrap derives greenfield, early-scaffold, or brownfield behavior from repository evidence. It establishes proportionate harness goals, reconciles eligible unstarted product-goal dependencies, executes and verifies the harness through ordinary ZzzOps, and leaves substantive product goals unimplemented. Brownfield work preserves intentional architecture and strengthens evidenced gaps instead of re-scaffolding.

### 5. Migrate existing work

From the target project in Codex:

```text
Use $migrate-to-zzzops to inspect and migrate existing TODOs.
```

The agent uses section-aware inventory hints to find work hidden under completed-looking headings, reads the surrounding source itself, and performs one completeness review before presenting a human-readable plan. Similar mentions remain advisory rather than being merged automatically. Migration happens only after approval into GitHub Issues; inline TODO comments keep their useful context and gain the created issue link, while dedicated backlog files retire only after verified coverage.

### 6. Add new work

```text
Use $add-zzzops-goal to capture <the thing we should eventually do>.
```

ZzzOps checks duplicates, asks important questions, relates value to the charter, and creates a durable GitHub issue with a resumable next action. Capture never creates a branch, commit, push, or PR.

When you remember “one last thing,” capture it instead of opening six files and seeing sunrise.

### 7. Execute—and go to bed

For a normal Codex run:

```text
Use $execute-zzzops to work on all available goals until nothing safe remains.
```

For persistent Codex execution:

```text
/goal Use $execute-zzzops to work through all available project goals until complete or genuinely blocked.
```

This is the point of ZzzOps: stop babysitting agents. When work runs dry, the agent interviews you about blockers before conceding defeat. If one safely observable human action is all that remains, it notifies you and briefly watches for completion before handing off. This is your scheduled cameo. After that, please locate the bedroom; staying awake does not make the remaining tokens more valuable.

Source-changing goals follow the reviewed project branch/review policy and pause at a human review blocker after checks. Maintainers: see the [branch topology and review lifecycle](docs/EXECUTION.md).

### 8. Send ZzzOps feedback

```text
Use $send-zzzops-feedback to send <feedback about the ZzzOps workflow>.
```

ZzzOps workflows record only constrained machinery categories, cause codes, and numeric impact in immutable, content-addressed, Git-ignored execution reports. They never put project names, paths, code, goals, domain facts, user content, or secrets in those reports. When feedback is prepared, fixed catalog text turns each cause into a human-readable account of the machinery surface, observed behavior, measured impact, typical recovery, and suggested investigation; the original JSON remains in a collapsed inline appendix. Keeping evidence inline makes preview, digest confirmation, and issue creation one atomic payload without relying on a separate attachment upload. Recording is enabled by reviewed policy by default and can be disabled with `autonomy_approval_parallelism.settings.execution_reports.enabled: false`.

The feedback skill combines your text with archived reports, shows the exact issue payload, warns that `david-rzepa/zzzops` is public, and asks you to confirm that payload. Only then does it create a managed issue tagged `zzzops-feedback`. Execute excludes these issues by default; one explicit approval includes the entire feedback queue for that execution session, with no per-issue prompts. Successfully submitted reports are deleted; cancellation or failure retains them.

### 9. Review how you use software agents

On request, ZzzOps can review several completed pieces of agent work and suggest up to two improvements to your overall agentic-engineering practice:

```text
Use $review-agentic-engineering to review my recent completed software-agent work.
```

This skill is explicit-only and read-only. It distinguishes genuine specification gaps from repository or specialist context, tooling, verification, implementation, and external failures before coaching. It does not grade prompt length, change the repository, create goals, or submit ZzzOps feedback.

## Control-module boundaries

`plugins/zzzops/zzzops/zzzops.py` is the stable installed executable and CLI composition layer. It loads focused, acyclic implementation modules and preserves the public command surface:

| Module | Owns |
| --- | --- |
| `policy.py` | Reviewed project state, policy validation, initialization, and resource policy. |
| `reservation.py` | GitHub-backed goal and resource reservation coordination. |
| `feedback.py` | Privacy-safe execution reports, provenance, payload preparation, and submission. |
| `coaching.py` | Bounded, privacy-safe attribution of completed software-agent work. |
| `goals.py` | Managed-goal parsing, validation, rendering, GitHub record projection, and guarded transitions. |
| `portfolio.py` | Goal graph audits, actionability, and canonical portfolio snapshots. |
| `package.py` | Agent Plugin package validation and deterministic package provenance. |
| `installation.py` | Per-repository package validation state and composition of the legacy cleanup audit. |
| `zzzops.py` | CLI parsing/dispatch, provider probes/adapters, package validation, and stable re-exports. |

The package checkpoint validates the installed manifest, required surfaces, and deterministic SHA-256 provenance before provider access. Keep cross-module dependencies one-way: focused modules may use explicitly configured entry-point callbacks, while callers continue to invoke the stable `zzzops.py` command or re-exported API.

## Full feature list

This is the complete list of shipped user-facing ZzzOps features. It is a catalogue, not exhaustive documentation. Keep it current whenever a user-facing surface changes.

| Feature | Primary surface |
| --- | --- |
| Discover, install, update, and remove ZzzOps through Codex | `.agents/plugins/marketplace.json` / `plugins/zzzops/plugin.json` |
| Validate each repository once per installed package and confirm legacy cleanup | `plugins/zzzops/skills/validate-zzzops-installation/SKILL.md` |
| Safely preview and remove retired per-project installations | `plugins/zzzops/scripts/cleanup_legacy.py` / `plugins/zzzops/assets/legacy_install_fingerprints.json` |
| Publish the privacy boundary, compliance review, and support contact | `PRIVACY.md` / `docs/OPENAI_COMPLIANCE.md` / `README.md` |
| Initialize, summarize, and adjust reviewed project policy | `plugins/zzzops/skills/review-zzzops-policy/SKILL.md` |
| Bootstrap a new or existing repository into an agent-ready harness | `plugins/zzzops/skills/bootstrap-zzzops-repository/SKILL.md` |
| Review completed software-agent work and suggest concise practice improvements | `plugins/zzzops/skills/review-agentic-engineering/SKILL.md` |
| Use GitHub Issues as the canonical goal backend | `plugins/zzzops/rules/BACKENDS.md` |
| Capture durable work | `plugins/zzzops/skills/add-zzzops-goal/SKILL.md` |
| Migrate repository TODOs and backlogs | `plugins/zzzops/skills/migrate-to-zzzops/SKILL.md` |
| Suggest evidence-backed backlog work | `plugins/zzzops/skills/suggest-zzzops-work/SKILL.md` |
| Preview and send user feedback plus privacy-safe execution reports | `plugins/zzzops/skills/send-zzzops-feedback/SKILL.md` |
| Execute, prioritize, unblock, briefly watch human gates, verify, and hand off goals | `plugins/zzzops/skills/execute-zzzops/SKILL.md` |
| Record constrained, project-free machinery friction with a policy opt-out | `plugins/zzzops/rules/FEEDBACK.md` / `plugins/zzzops/zzzops/zzzops.py` |
| Give project-policy-driven updates, defaulting to concise outcomes and clear user actions | `plugins/zzzops/rules/INITIALIZATION.md` |
| Review or override refill, dependency, and parallel execution policy | `plugins/zzzops/skills/review-zzzops-policy/SKILL.md` |
| Select up to three worktree workers below 100 MB, otherwise read-only workers, from tracked repository size | `plugins/zzzops/zzzops/zzzops.py` / `plugins/zzzops/rules/EXECUTION_STRATEGY.md` |
| Keep writable dependent goals gated while allowing read-only advance investigation | `plugins/zzzops/rules/GOAL_SYSTEM.md` |
| Clean completed worktrees or safely retain and reassign them | `plugins/zzzops/rules/EXECUTION_STRATEGY.md` |
| Inspect initialized capability and the canonical portfolio in one CLI checkpoint | `plugins/zzzops/zzzops/zzzops.py` |
| Atomically reserve goals and known shared resources so concurrent agents avoid duplicate or colliding work | `plugins/zzzops/zzzops/zzzops.py` |
| Validate dev PRs and preview or publish semantic releases | `.github/workflows` |

```text
Use $execute-zzzops to interview me about and unblock blocked goals.
Use $execute-zzzops to reprioritize all goals against project KPIs.
Use $suggest-zzzops-work in dry-run mode to audit the project and suggest valuable goals.
<python> plugins/zzzops/zzzops/zzzops.py --repo . checkpoint  # one initialized capability/queue/DAG read
```

ZzzOps keeps its detailed audit trail in canonical goals and logs. Its installed communication default leads with what changed, whether you need to act, and what happens next; reviewed project policy can choose another style. Technical diagnostics remain available when they affect a decision or you ask for them.

Maintainers: see the [skill discovery and mode contract](docs/SKILLS.md).

Portfolio batching benchmarks and the machine contract are documented in [portfolio performance](docs/PERFORMANCE.md).

Suggestions are preview-only unless you request apply. Once the initialization policy is reviewed, autonomous exhausted-queue refill defaults on for documentation, test coverage, and non-behavioral code quality, capped at three goals per run. A repository may override or disable those categories and limits in `PROJECT.md`.

The installed parallel default measures existing Git-tracked working-tree bytes, excluding `.git`, ignored/untracked files, and other worktrees. Repositories below 100 MB may use up to three isolated worktree sub-agents; repositories at or above the boundary, or whose size cannot be measured, may use up to three read-only agents. Reviewed project policy can override these operational defaults. Writable implementation waits for completed dependencies by default, although read-only agents may investigate later goals in advance. Every completed-task worktree is removed or deliberately retained clean and safely reassigned before reuse.

## License, name, and feedback

ZzzOps is licensed under [Apache-2.0](LICENSE), including its patent grant. The license permits forks and reuse, but does not grant rights to use the ZzzOps name or imply endorsement. Forks may accurately describe themselves as based on ZzzOps, but must not present themselves as the official project.

The feedback workflow submits only an exactly previewed, user-confirmed payload to this public repository. Do not submit secrets, personal data, or project-confidential material. Contributions and issue content intentionally submitted for inclusion are governed by Apache-2.0 unless explicitly marked otherwise.

## Releases

Every semantic release on `main` prepares two validated, versioned OpenAI marketplace assets before GitHub publication: `zzzops-plugin-v<version>.zip` for the portal's skills upload and `zzzops-openai-submission-v<version>.zip` for listing copy, light/dark assets, starter prompts, review tests, availability, release notes, manifests, and the human attestation checklist. A build or validation failure stops semantic-release before GitHub publication; successful artifacts are attached to the matching GitHub Release.

The version-controlled sources live in `marketplace/`. OpenAI portal upload, attestation, review submission, approval, and final publication remain explicit human actions. ZzzOps does not use browser automation or undocumented endpoints, and a future documented publication API requires a separately approved integration. See [marketplace submission sources](marketplace/README.md) and the [official submission documentation](https://developers.openai.com/plugins/deploy/submission).

Develop on branches created from `dev` and open ordinary PRs against `dev`. PR validation runs for every target branch so chained PRs receive exact-head evidence before they are retargeted; the read-only **PR validation / dev-required-tests** job must pass before merge. Each push to `dev` runs `semantic-release --dry-run` with read-only repository permission; dry-run skips tag creation and publication. `main` is reserved for an intended owner force-push release: semantic-release then receives `contents: write` and creates the Git tag and GitHub Release.

Semantic commits since the latest reachable `vMAJOR.MINOR.PATCH` tag are the release-history source. `!` or a `BREAKING CHANGE` footer produces a major release, `feat` produces minor, and `fix`, `perf`, or `revert` produces patch. The highest change wins. Documentation, style, chores, refactors, tests, builds, and CI do not release and are omitted from notes. The conventional-commits generator emits sections in its fixed significance order—Features, Bug Fixes, Performance Improvements, then Reverts—with a distinct breaking-changes section; empty sections are omitted and entries are sorted by subject then scope. Reruns with no releasable commits are no-ops.

Release notes live on the GitHub Release rather than in a versioned `CHANGELOG.md`, avoiding a release-generated commit and duplicate history. The exact Node and semantic-release/plugin versions are pinned in `package-lock.json`; no repository secret is required beyond GitHub's job token.

To diagnose a PR or release, inspect **PR validation / dev-required-tests** or the **Semantic release** run and its failing step. Routine implementation uses the smallest distinct local probe and leaves an exact-equivalent broad command to required CI at the pushed head. When CI fails or is unavailable, reproduce its commands locally with:

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

`node .github/scripts/preview_semantic_release.mjs` previews the next version and release notes against a temporary local bare remote. It uses only semantic-release's analysis and note-generation plugins, so it neither needs GitHub write permission nor can create a repository tag or GitHub Release.

Maintainers: see [branch protection](docs/BRANCH_PROTECTION.md) for the required `dev` check, current GitHub Free limitation, closest enforceable `main` policy, and recovery procedure.

## The files that remember things

- `.zzzops/PROJECT.md` — concise human charter and reviewed policy summary.
- `.zzzops/POLICY.json` — canonical reviewed machine policy, loaded only by deterministic controls.
- `.zzzops/PROJECT_AUDIT.md` — digest-bound evidence, rationales, review metadata, and history for review or reconciliation.
- GitHub Issues — canonical goals, blockers, evidence, relations, and history.
- `plugins/zzzops/plugin.json` — Agent Plugins v1 manifest for the distributable package.
- `plugins/zzzops/scripts/cleanup_legacy.py` — dry-run-first cleanup for proven retired per-project installations.
- `marketplace/` — reviewed OpenAI listing, test, availability, and attestation sources for generated release packets.
- `.agents/plugins/marketplace.json` — Codex marketplace entry for the package.
- `.zzzops/migration/STATE.json` — records reviewed import fingerprints so repeat migrations propose only new work.

Agents follow the reviewed project resource policy, define the observable signal before editing, change one small falsifiable chunk at a time, and inspect real output after every chunk. Verification is proportional: documentation is inspected, changed tests are run, and product/runtime behavior plus reusable test infrastructure receive direct behavioral coverage—ZzzOps does not recursively add tests for prose or test cases. If the project is opaque, agents build a focused harness or scoped MCP observation server instead of vibe-coding and hoping. Execution follows the reviewed project branch, review, and commit policy; capture itself is Git-free.

If a new test discovers a real bug, ZzzOps files a separate TODO and asks you before fixing it. It does not smuggle a surprise product change into “just adding coverage,” because we have all reviewed that pull request before.

## Prompt budget

`<python> .agents/prompt_stats.py` prints a stable estimate: `ceil(canonical UTF-8 bytes / 4)`, with line endings normalized to LF. It is useful for prompt-size regression, not billing. CI enforces committed limits for always-loaded `AGENTS.md` context and the frequently routed goal-capture and execution paths. The complete inventory and other routed workflows remain advisory, so mutually exclusive one-off workflows do not compete for a misleading global allowance. Inspect the relevant reports after any prompt change:

```powershell
<python> .agents/prompt_stats.py
<python> .agents/prompt_stats.py --profiles
<python> .agents/prompt_stats.py --check
```

The [repository context-engineering audit](docs/CONTEXT_ENGINEERING.md) records how modern guidance applies to the context used by ZzzOps maintainers without changing installed runtime behavior.

Go to bed. The backlog knows what to do.
