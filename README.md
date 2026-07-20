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

The installer previews the tracked project mechanics, warns if Git ignores required `.agents/` or `.claude/` content, and asks once before writing. The default answer is no. Use `-DryRun` on Windows or `--dry-run` on macOS/Linux for a non-interactive preview.

The CLI copies discoverable skills, mechanics, and blank templates—never itself, project state, another project’s goals, or the target’s `AGENTS.md`/`CLAUDE.md`.

Open a new Codex task or Claude Code session in the target project so its ZzzOps skills are discovered.

### 3. Initialize the project

Start any non-install workflow in the target, for example:

```text
Use $add-zzzops-goal to capture our first piece of work.
```

The agent first inspects code, docs, config, history, Git, GitHub, and repository policy; proposes the outcome, KPIs, acceptance criteria, GitHub authority, and operating rules; then asks only consequential questions. Deterministic CLI primitives validate and atomically create a pending `.zzzops/PROJECT.md`. You do not fill a blank wizard.

The agent summarizes that exact file and tells you to read it in detail. Ordinary workflows remain blocked until you explicitly approve the current file digest; any edit invalidates the approval. Stable per-section checkboxes make GitHub authority, Git/review, continuation, testing, code quality, tooling, security, documentation, deployment/resources, and autonomy decisions visible rather than hiding them in universal prompts. After approval, `PROJECT.md` keeps only the charter and runtime decisions; digest-bound `PROJECT_AUDIT.md` preserves the full review record on demand.

Once reviewed, these policies let the agent make routine decisions without waking you for every tiny choice.

GitHub Issues is the canonical goal authority. Initialization requires a successful repository and access probe; unavailable authentication, permission, or Issues support becomes an explicit blocker. Initialization does not commit, branch, or mutate GitHub, and after approval mentions the optional preferences panel without opening it.

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

The agent inventories candidates, presents a human-readable plan, then migrates only after approval into GitHub Issues. Inline TODO comments remain; dedicated backlog files retire only after verified coverage.

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

## Full feature list

This is the complete list of shipped user-facing ZzzOps features. It is a catalogue, not exhaustive documentation. Keep it current whenever a user-facing surface changes.

| Feature | Primary surface |
| --- | --- |
| Preview and install ZzzOps mechanics from a normal terminal without Python or Node | `install.ps1` / `install.sh` |
| Initialize a project with reviewed operating policies | `.agents/zzzops.py` |
| Use GitHub Issues as the canonical goal backend | `.zzzops/rules/BACKENDS.md` |
| Capture durable work | `.agents/skills/add-zzzops-goal/SKILL.md` |
| Migrate repository TODOs and backlogs | `.agents/skills/migrate-to-zzzops/SKILL.md` |
| Suggest evidence-backed backlog work | `.agents/skills/suggest-zzzops-work/SKILL.md` |
| Execute, prioritize, unblock, briefly watch human gates, verify, and hand off goals | `.agents/skills/execute-zzzops/SKILL.md` |
| Give project-policy-driven updates, defaulting to concise outcomes and clear user actions | `.zzzops/rules/INITIALIZATION.md` |
| Configure backlog refill and parallelization preferences | `.agents/zzzops.py` |
| Inspect initialized capability and the canonical portfolio in one CLI checkpoint | `.agents/zzzops.py` |
| Atomically reserve goals and known shared resources so concurrent agents avoid duplicate or colliding work | `.agents/zzzops.py` |
| Validate dev PRs and preview or publish semantic releases | `.github/workflows` |

```text
Use $execute-zzzops to interview me about and unblock blocked goals.
Use $execute-zzzops to reprioritize all goals against project KPIs.
Use $suggest-zzzops-work in dry-run mode to audit the project and suggest valuable goals.
<python> .agents/zzzops.py --repo . checkpoint  # one initialized capability/queue/DAG read
```

In Claude Code, replace `$name` with `/name`, for example `/suggest-zzzops-work`.

ZzzOps keeps its detailed audit trail in canonical goals and logs. Its installed communication default leads with what changed, whether you need to act, and what happens next; reviewed project policy can choose another style. Technical diagnostics remain available when they affect a decision or you ask for them.

Maintainers: see the [skill discovery and mode contract](docs/SKILLS.md).

Portfolio batching benchmarks and the machine contract are documented in [portfolio performance](docs/PERFORMANCE.md).

Suggestions are preview-only unless you request apply. To let an exhausted execution run refill selected kinds of evidence-backed work, configure local, git-ignored `.zzzops/PREFERENCES.json`:

```json
{
  "fill_backlog": {
    "documentation": true,
    "tests": true,
    "code_quality_non_behavioral": false,
    "max_goals_per_refill": 3
  },
  "parallelization": {
    "mode": "read_only",
    "max_workers": 2
  }
}
```

Parallel modes are `sequential`, `read_only`, and `worktrees`. `worktrees` permits isolated writable sub-agents: one disjoint sub-goal and commit each, reviewed and integrated sequentially by the coordinator. It is an upper bound, not a request to turn your laptop into a space heater.

Or use the interactive control panel from your project root:

```powershell
<python> .agents/zzzops.py
```

It edits project preferences and parallelization settings.

## Releases

Develop on branches created from `dev` and open ordinary PRs against `dev`. The read-only **PR validation / dev-required-tests** job must pass before merge. Each push to `dev` previews the release with read-only repository permission; it cannot publish. `main` is reserved for an intended owner force-push release: the same planner then receives `contents: write` and creates the Git tag and GitHub Release.

Versions follow Conventional Commits since the latest `vMAJOR.MINOR.PATCH` tag: `!`, `BREAKING CHANGE:`, or `BREAKING-CHANGE:` bumps major, `feat` bumps minor, and `fix`/`perf` bumps patch. Other types do not release. The first release applies those rules from `0.0.0`; reruns with no new releasable commits are no-ops. No repository secret is required beyond GitHub's job token.

To diagnose a PR or release, inspect **PR validation / dev-required-tests** or the **Semantic release** run and its failing step. Reproduce the same checks locally with:

```powershell
<python> -m unittest discover -s .agents -p 'test_*.py'
<python> -m unittest discover -s .agents/skills/migrate-to-zzzops/scripts -p 'test_*.py'
<python> -m unittest discover -s .github/scripts -p 'test_*.py'
<python> .agents/manual_acceptance.py coverage
<python> .agents/prompt_stats.py --check
<python> -m compileall -q .agents .github/scripts
bash -n install.sh
powershell -NoProfile -Command "[void][scriptblock]::Create((Get-Content -Raw ./install.ps1))"
```

`<python> .github/scripts/semantic_release.py` only writes a local notes file.

Maintainers: see [branch protection](docs/BRANCH_PROTECTION.md) for the required `dev` check, current GitHub Free limitation, closest enforceable `main` policy, and recovery procedure.

## The files that remember things

- `.zzzops/PROJECT.md` — compact authoritative charter and reviewed runtime policy.
- `.zzzops/PROJECT_AUDIT.md` — digest-bound evidence, rationales, review metadata, and history for initialization or reconciliation.
- GitHub Issues — canonical goals, blockers, evidence, relations, and history.
- `.zzzops/rules/` — tracked ZzzOps operating rules; machinery, not project content.
- `.zzzops/PREFERENCES.json` — local, ignored user opt-ins for bounded autonomous backlog refills.
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
