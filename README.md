# ZzzOps

**Infinite backlog for agents. Finite bedtime for token-addicted humans.**

ZzzOps gives agents an infinite, prioritized backlog so token FOMO stops at bedtime—before another 3:57 a.m. run causes a domestic incident.

## Quickstart

### 1. Clone ZzzOps

```powershell
git clone https://github.com/david-rzepa/zzzops.git C:\dev\zzzops
```

### 2. Install it into your project

From a normal terminal on Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\dev\zzzops\install.ps1 C:\path\to\your-project
```

On macOS or Linux:

```bash
/path/to/zzzops/install.sh /path/to/your-project
```

The installer previews tracked project mechanics, warns if Git ignores required `.agents/` or `.claude/` content, and defaults confirmation to no. Accepted installs record the source revision and exact managed-file baseline. A later source version offers `Upgrade ZzzOps? [y/N]`, lists changed mechanics and recent source changes, and upgrades files still matching that baseline; locally divergent files remain protected behind the explicit overwrite option. Truly current installs exit without prompting. Use `-DryRun` on Windows or `--dry-run` on macOS/Linux for a non-interactive preview.

After project policy is initialized and reviewed, the first ordinary ZzzOps checkpoint requires the installer-managed skills, shared rules, control CLI/templates, and machinery ignore files to be committed. Untracked, staged, modified, or deleted machinery stops ordinary workflows with a commit-first action; project policy/state and root repository instructions are not part of this machinery check.

The CLI copies discoverable skills, mechanics, and blank templates—never itself, project state, another project’s goals, or the target’s `AGENTS.md`/`CLAUDE.md`.

Discoverable skills stay in `.agents/skills/` and `.claude/skills/`. Other harness support is grouped under `.agents/zzzops/`, while shared project rules and state use the root `.zzzops/` folder.

Target projects receive exactly six skills: `add-zzzops-goal`, `execute-zzzops`, `migrate-to-zzzops`, `review-zzzops-policy`, `send-zzzops-feedback`, and `suggest-zzzops-work`. The `run-zzzops-acceptance` skill, [human acceptance plan](docs/ACCEPTANCE_TEST_PLAN.md), and `.agents/manual_acceptance.py` harness are maintenance and release infrastructure for this base repository; installers exclude them because target users exercise the six shipped workflows rather than maintain ZzzOps itself.

Open a new Codex task or Claude Code session in the target project so its ZzzOps skills are discovered, then start the policy review workflow.

### 3. Initialize the project

Use the dedicated review skill in the target:

```text
Use $review-zzzops-policy to initialize and summarize this project's policy.
```

The agent first inspects code, docs, config, history, Git, GitHub, and repository policy; proposes the outcome, KPIs, acceptance criteria, GitHub authority, and operating rules; then asks only consequential questions. Deterministic CLI primitives validate the concise charter, detailed audit, and canonical machine policy. You do not fill a blank wizard.

The agent summarizes the meaningful choices and invites adjustments. Ordinary workflows remain blocked until you explicitly approve the current policy; any bound charter, audit, or policy edit invalidates approval. `PROJECT.md` stays a concise human charter and summary, `POLICY.json` is the single machine-readable authority, and digest-bound `PROJECT_AUDIT.md` preserves detail on demand. Running the review skill later always produces a fresh summary before inviting changes.

Once reviewed, these policies let the agent make routine decisions without waking you for every tiny choice.

GitHub Issues is the canonical goal authority. Initialization requires a successful repository and access probe; unavailable authentication, permission, or Issues support becomes an explicit blocker. Initialization does not commit, branch, or mutate GitHub.

The native installer does not require Python or Node. Post-install CLI examples use `<python>` for one Python 3 interpreter resolved once (`python3`, `python`, Windows `py -3`, or a harness-provided runtime). Agents must discover it before launching instead of first trying an assumed executable.

**Visibility:** GitHub-backed goals inherit the repository's visibility. Never put secrets or raw sensitive data in a goal; redact it or link to an approved private system before capture or migration.

Maintainers: see the [initialization and policy contract](docs/INITIALIZATION.md).

### 4. Migrate existing work

From the target project in Codex:

```text
Use $migrate-to-zzzops to inspect and migrate existing TODOs.
```

In Claude Code, invoke the same workflow as:

```text
/migrate-to-zzzops inspect and migrate existing TODOs
```

The agent uses section-aware inventory hints to find work hidden under completed-looking headings, reads the surrounding source itself, and performs one completeness review before presenting a human-readable plan. Similar mentions remain advisory rather than being merged automatically. Migration happens only after approval into GitHub Issues; inline TODO comments keep their useful context and gain the created issue link, while dedicated backlog files retire only after verified coverage.

### 5. Add new work

```text
Use $add-zzzops-goal to capture <the thing we should eventually do>.
```

ZzzOps checks duplicates, asks important questions, relates value to the charter, and creates a durable GitHub issue with a resumable next action. Capture never creates a branch, commit, push, or PR.

When you remember “one last thing,” capture it instead of opening six files and seeing sunrise.

### 6. Execute—and go to bed

For a normal Codex run:

```text
Use $execute-zzzops to work on all actionable goals until nothing safe remains.
```

For Claude Code:

```text
/execute-zzzops work on all actionable goals until nothing safe remains
```

For persistent Codex execution:

```text
/goal Use $execute-zzzops to work through all actionable project goals until complete or genuinely blocked.
```

`/goal` is Codex-specific. Claude Code invokes ZzzOps workflows directly as `/skill-name`; ZzzOps supplies the same queue and operating rules in either tool. This is the point of ZzzOps: stop babysitting agents. When work runs dry, the agent interviews you about blockers before conceding defeat. If one safely observable human action is all that remains, it notifies you and briefly watches for completion before handing off. This is your scheduled cameo. After that, please locate the bedroom; staying awake does not make the remaining tokens more valuable.

Source-changing goals follow the reviewed project branch/review policy and pause at a human review blocker after checks. Maintainers: see the [branch topology and review lifecycle](docs/EXECUTION.md).

### 7. Send ZzzOps feedback

```text
Use $send-zzzops-feedback to send <feedback about the ZzzOps workflow>.
```

ZzzOps workflows record only constrained machinery categories, cause codes, and numeric impact in immutable, content-addressed, Git-ignored execution reports. They never put project names, paths, code, goals, domain facts, user content, or secrets in those reports. When feedback is prepared, fixed catalog text turns each cause into a human-readable account of the machinery surface, observed behavior, measured impact, typical recovery, and suggested investigation; the original JSON remains in a collapsed inline appendix. Keeping evidence inline makes preview, digest confirmation, and issue creation one atomic payload without relying on a separate attachment upload. Recording is enabled by reviewed policy by default and can be disabled with `autonomy_approval_parallelism.settings.execution_reports.enabled: false`.

The feedback skill combines your text with archived reports, shows the exact issue payload, warns that `david-rzepa/zzzops` is public, and asks you to confirm that payload. Only then does it create a managed issue tagged `zzzops-feedback`. Execute excludes these issues by default; one explicit approval includes the entire feedback queue for that execution session, with no per-issue prompts. Successfully submitted reports are deleted; cancellation or failure retains them.

## Control-module boundaries

`.agents/zzzops/zzzops.py` is the stable installed executable and CLI composition layer. It loads focused, acyclic implementation modules and preserves the public command surface:

| Module | Owns |
| --- | --- |
| `policy.py` | Reviewed project state, policy validation, initialization, and resource policy. |
| `reservation.py` | GitHub-backed goal and resource reservation coordination. |
| `feedback.py` | Privacy-safe execution reports, provenance, payload preparation, and submission. |
| `goals.py` | Managed-goal parsing, validation, rendering, GitHub record projection, and guarded transitions. |
| `portfolio.py` | Goal graph audits, actionability, and canonical portfolio snapshots. |
| `zzzops.py` | CLI parsing/dispatch, provider probes/adapters, installed-file manifest, and stable re-exports. |

Both installers copy, hash, protect, upgrade, and validate this complete module set. Keep cross-module dependencies one-way: focused modules may use explicitly configured entry-point callbacks, while callers continue to invoke the stable `zzzops.py` command or re-exported API.

## Full feature list

This is the complete list of shipped user-facing ZzzOps features. It is a catalogue, not exhaustive documentation. Keep it current whenever a user-facing surface changes.

| Feature | Primary surface |
| --- | --- |
| Preview and install ZzzOps mechanics from a normal terminal without Python or Node | `install.ps1` / `install.sh` |
| Initialize, summarize, and adjust reviewed project policy | `.agents/skills/review-zzzops-policy/SKILL.md` |
| Use GitHub Issues as the canonical goal backend | `.zzzops/rules/BACKENDS.md` |
| Capture durable work | `.agents/skills/add-zzzops-goal/SKILL.md` |
| Migrate repository TODOs and backlogs | `.agents/skills/migrate-to-zzzops/SKILL.md` |
| Suggest evidence-backed backlog work | `.agents/skills/suggest-zzzops-work/SKILL.md` |
| Preview and send user feedback plus privacy-safe execution reports | `.agents/skills/send-zzzops-feedback/SKILL.md` |
| Execute, prioritize, unblock, briefly watch human gates, verify, and hand off goals | `.agents/skills/execute-zzzops/SKILL.md` |
| Record constrained, project-free machinery friction with a policy opt-out | `.zzzops/rules/FEEDBACK.md` / `.agents/zzzops/zzzops.py` |
| Give project-policy-driven updates, defaulting to concise outcomes and clear user actions | `.zzzops/rules/INITIALIZATION.md` |
| Review or override refill, dependency, and parallel execution policy | `.agents/skills/review-zzzops-policy/SKILL.md` |
| Select up to three worktree workers below 100 MB, otherwise read-only workers, from tracked repository size | `.agents/zzzops/zzzops.py` / `.zzzops/rules/EXECUTION_STRATEGY.md` |
| Keep writable dependent goals gated while allowing read-only advance investigation | `.zzzops/rules/GOAL_SYSTEM.md` |
| Clean completed worktrees or safely retain and reassign them | `.zzzops/rules/EXECUTION_STRATEGY.md` |
| Inspect initialized capability and the canonical portfolio in one CLI checkpoint | `.agents/zzzops/zzzops.py` |
| Atomically reserve goals and known shared resources so concurrent agents avoid duplicate or colliding work | `.agents/zzzops/zzzops.py` |
| Validate dev PRs and preview or publish semantic releases | `.github/workflows` |

```text
Use $execute-zzzops to interview me about and unblock blocked goals.
Use $execute-zzzops to reprioritize all goals against project KPIs.
Use $suggest-zzzops-work in dry-run mode to audit the project and suggest valuable goals.
<python> .agents/zzzops/zzzops.py --repo . checkpoint  # one initialized capability/queue/DAG read
```

In Claude Code, replace `$name` with `/name`, for example `/suggest-zzzops-work`.

ZzzOps keeps its detailed audit trail in canonical goals and logs. Its installed communication default leads with what changed, whether you need to act, and what happens next; reviewed project policy can choose another style. Technical diagnostics remain available when they affect a decision or you ask for them.

Maintainers: see the [skill discovery and mode contract](docs/SKILLS.md).

Portfolio batching benchmarks and the machine contract are documented in [portfolio performance](docs/PERFORMANCE.md).

Suggestions are preview-only unless you request apply. Once the initialization policy is reviewed, autonomous exhausted-queue refill defaults on for documentation, test coverage, and non-behavioral code quality, capped at three goals per run. A repository may override or disable those categories and limits in `PROJECT.md`.

The installed parallel default measures existing Git-tracked working-tree bytes, excluding `.git`, ignored/untracked files, and other worktrees. Repositories below 100 MB may use up to three isolated worktree sub-agents; repositories at or above the boundary, or whose size cannot be measured, may use up to three read-only agents. Reviewed project policy can override these operational defaults. Writable implementation waits for completed dependencies by default, although read-only agents may investigate later goals in advance. Every completed-task worktree is removed or deliberately retained clean and safely reassigned before reuse.

## License, name, and feedback

ZzzOps is licensed under [Apache-2.0](LICENSE), including its patent grant. The license permits forks and reuse, but does not grant rights to use the ZzzOps name or imply endorsement. Forks may accurately describe themselves as based on ZzzOps, but must not present themselves as the official project.

The feedback workflow submits only an exactly previewed, user-confirmed payload to this public repository. Do not submit secrets, personal data, or project-confidential material. Contributions and issue content intentionally submitted for inclusion are governed by Apache-2.0 unless explicitly marked otherwise.

## Releases

Develop on branches created from `dev` and open ordinary PRs against `dev`. The read-only **PR validation / dev-required-tests** job must pass before merge. Each push to `dev` runs `semantic-release --dry-run` with read-only repository permission; dry-run skips tag creation and publication. `main` is reserved for an intended owner force-push release: semantic-release then receives `contents: write` and creates the Git tag and GitHub Release.

Semantic commits since the latest reachable `vMAJOR.MINOR.PATCH` tag are the release-history source. `!` or a `BREAKING CHANGE` footer produces a major release, `feat` produces minor, and `fix`, `perf`, or `revert` produces patch. The highest change wins. Documentation, style, chores, refactors, tests, builds, and CI do not release and are omitted from notes. The conventional-commits generator emits sections in its fixed significance order—Features, Bug Fixes, Performance Improvements, then Reverts—with a distinct breaking-changes section; empty sections are omitted and entries are sorted by subject then scope. Reruns with no releasable commits are no-ops.

Release notes live on the GitHub Release rather than in a versioned `CHANGELOG.md`, avoiding a release-generated commit and duplicate history. The exact Node and semantic-release/plugin versions are pinned in `package-lock.json`; no repository secret is required beyond GitHub's job token.

To diagnose a PR or release, inspect **PR validation / dev-required-tests** or the **Semantic release** run and its failing step. Reproduce the same checks locally with:

```powershell
<python> -m unittest discover -s .agents -p 'test_*.py'
<python> -m unittest discover -s .agents/skills/migrate-to-zzzops/scripts -p 'test_*.py'
npm ci
npm run test:release
<python> .agents/manual_acceptance.py coverage
<python> .agents/prompt_stats.py --check
<python> -m compileall -q .agents
bash -n install.sh
powershell -NoProfile -Command "[void][scriptblock]::Create((Get-Content -Raw ./install.ps1))"
```

`node .github/scripts/preview_semantic_release.mjs` previews the next version and release notes against a temporary local bare remote. It uses only semantic-release's analysis and note-generation plugins, so it neither needs GitHub write permission nor can create a repository tag or GitHub Release.

Maintainers: see [branch protection](docs/BRANCH_PROTECTION.md) for the required `dev` check, current GitHub Free limitation, closest enforceable `main` policy, and recovery procedure.

## The files that remember things

- `.zzzops/PROJECT.md` — concise human charter and reviewed policy summary.
- `.zzzops/POLICY.json` — canonical reviewed machine policy, loaded only by deterministic controls.
- `.zzzops/PROJECT_AUDIT.md` — digest-bound evidence, rationales, review metadata, and history for review or reconciliation.
- GitHub Issues — canonical goals, blockers, evidence, relations, and history.
- `.zzzops/rules/` — tracked ZzzOps operating rules; machinery, not project content.
- `.zzzops/migration/STATE.json` — records reviewed import fingerprints so repeat migrations propose only new work.

Agents follow the reviewed project resource policy, define the observable signal before editing, change one small falsifiable chunk at a time, and inspect real output after every chunk. Verification is proportional: documentation is inspected, changed tests are run, and product/runtime behavior plus reusable test infrastructure receive direct behavioral coverage—ZzzOps does not recursively add tests for prose or test cases. If the project is opaque, agents build a focused harness or scoped MCP observation server instead of vibe-coding and hoping. Execution follows the reviewed project branch, review, and commit policy; capture itself is Git-free.

If a new test discovers a real bug, ZzzOps files a separate TODO and asks you before fixing it. It does not smuggle a surprise product change into “just adding coverage,” because we have all reviewed that pull request before.

## Prompt budget

`<python> .agents/prompt_stats.py` prints a stable cross-harness estimate: `ceil(canonical UTF-8 bytes / 4)`, with line endings normalized to LF. It is useful for prompt-budget regression, not billing; Codex and Claude Code tokenize differently. CI enforces the committed ceiling; inspect it after any prompt change:

```powershell
<python> .agents/prompt_stats.py
<python> .agents/prompt_stats.py --check
```

Go to bed. The backlog knows what to do.
