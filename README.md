# ZzzOps

**Infinite backlog for agents. Finite bedtime for token-addicted humans.**

ZzzOps gives agents an infinite, prioritized backlog so token FOMO stops at bedtime—before another 3:57 a.m. run causes a domestic incident.

## Quickstart

### 1. Clone ZzzOps

```powershell
git clone https://github.com/david-rzepa/zzzops.git C:\dev\zzzops
```

Open `C:\dev\zzzops` in Codex or Claude Code.

### 2. Install it into your project

Codex:

```text
Use $install-zzzops to preview and install ZzzOps into C:\path\to\your-project.
```

Claude Code:

```text
/install-zzzops preview and install ZzzOps into C:\path\to\your-project
```

Review the preview and let the skill apply it. The installer copies discoverable skills, mechanics, and blank templates—never itself, project state, another project’s goals, or the target’s `AGENTS.md`/`CLAUDE.md`.

Open a new Codex task or Claude Code session in the target project so its ZzzOps skills are discovered.

### 3. Initialize the project

Start any non-install workflow in the target, for example:

```text
Use $add-zzzops-goal to capture our first piece of work.
```

The agent first inspects code, docs, config, history, Git, GitHub, and repository policy; proposes the outcome, KPIs, acceptance criteria, backend, and operating rules; then asks only consequential questions. Deterministic CLI primitives validate and atomically create a pending `.zzzops/PROJECT.md`. You do not fill a blank wizard.

The agent summarizes that exact file and tells you to read it in detail. Ordinary workflows remain blocked until you explicitly approve the current file digest; any edit invalidates the approval. Stable per-section checkboxes make backend, Git/review, continuation, testing, code quality, tooling, security, documentation, deployment/resources, and autonomy choices visible rather than hiding them in universal prompts.

Once reviewed, these policies let the agent make routine decisions without waking you for every tiny choice.

GitHub Issues is recommended when the repository and access probe succeed. Local `goals/items/` files are the supported alternative. One backend is authoritative; ZzzOps never silently switches or dual-writes. Initialization does not commit, branch, or mutate GitHub, and after approval mentions the optional `python .agents/zzzops.py` preferences panel without opening it.

**Visibility:** GitHub-backed goals inherit the repository's visibility. Never put secrets or raw sensitive data in a goal; redact it, link to an approved private system, or select the local-files backend before capture or migration.

Maintainers: see the [initialization and policy contract](docs/INITIALIZATION.md).

### 4. Migrate existing work

From the target project in Codex:

```text
Use $migrate-zzzops-todos to inspect and migrate existing TODOs.
```

In Claude Code, invoke the same workflow as:

```text
/migrate-zzzops-todos inspect and migrate existing TODOs
```

The agent inventories candidates, presents a human-readable plan, then migrates only after approval into the selected backend. Inline TODO comments remain; dedicated backlog files retire only after verified coverage.

### 5. Add new work

```text
Use $add-zzzops-goal to capture <the thing we should eventually do>.
```

ZzzOps checks duplicates, asks important questions, relates value to the charter, and creates a durable issue or local goal with a resumable next action. Capture never creates a branch, commit, push, or PR.

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

`/goal` is Codex-specific. Claude Code invokes ZzzOps workflows directly as `/skill-name`; ZzzOps supplies the same queue and operating rules in either tool. This is the point of ZzzOps: stop babysitting agents. When work runs dry, the agent interviews you about blockers before conceding defeat. This is your scheduled cameo. After that, please locate the bedroom; staying awake does not make the remaining tokens more valuable.

Source-changing goals follow the reviewed project branch/review policy and pause at a human review blocker after checks. Maintainers: see the [branch topology and review lifecycle](docs/EXECUTION.md).

## Useful maintenance

```text
Use $execute-zzzops to interview me about and unblock blocked goals.
Use $execute-zzzops to reprioritize all goals against project KPIs.
Use $suggest-zzzops-work in dry-run mode to audit the project and suggest valuable goals.
python .agents/zzzops.py --repo . portfolio --format summary  # compact read-only queue/DAG audit
```

In Claude Code, replace `$name` with `/name`, for example `/suggest-zzzops-work`.

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
python .agents/zzzops.py
```

It edits project preferences and optional user health settings.

## Optional health reminders

Health nudges are off until each user enables them in `python .agents/zzzops.py`. Preferences are per user; derived timestamps/counters are per machine. Windows uses roaming `%APPDATA%\ZzzOps\health_preferences.json` and local `%LOCALAPPDATA%\ZzzOps\health_state.json`; Linux uses XDG config/state; macOS uses `~/Library/Application Support/ZzzOps/`. `ZZZOPS_USER_CONFIG_DIR` and `ZZZOPS_MACHINE_STATE_DIR` provide explicit paths for sandboxes and harnesses. ZzzOps never bypasses denied storage or silently falls back into the repository.

Codex and Claude Code do not portably guarantee message-send timestamps. Exact times are used only when a harness supplies them; approximate workflow receipt time requires a separate opt-in and remains labeled approximate. Otherwise only current-time schedule rules run. State contains no prompts, messages, or event history and is retention-pruned. Nudges are non-medical, nonblocking, cooldown-limited, and active only during ZzzOps workflows.

```powershell
python .agents/zzzops.py --repo . health status
python .agents/zzzops.py --repo . health snooze
python .agents/zzzops.py --repo . health resume
python .agents/zzzops.py --repo . health reset
```

Maintainers: see [health architecture and capability matrix](docs/HEALTH.md).

## Releases

Develop on branches created from `dev` and open ordinary PRs against `dev`. The read-only **PR validation / dev-required-tests** job must pass before merge. Each push to `dev` previews the release with read-only repository permission; it cannot publish. `main` is reserved for an intended owner force-push release: the same planner then receives `contents: write` and creates the Git tag and GitHub Release.

Versions follow Conventional Commits since the latest `vMAJOR.MINOR.PATCH` tag: `!`, `BREAKING CHANGE:`, or `BREAKING-CHANGE:` bumps major, `feat` bumps minor, and `fix`/`perf` bumps patch. Other types do not release. The first release applies those rules from `0.0.0`; reruns with no new releasable commits are no-ops. No repository secret is required beyond GitHub's job token.

To diagnose a PR or release, inspect **PR validation / dev-required-tests**, the three **health-storage** platform checks, or the **Semantic release** run and its failing step. Reproduce checks locally with `python .agents/test_prompt_stats.py`, `python .agents/test_zzzops.py`, `python .agents/test_zzzops_health.py`, `python .agents/test_zzzops_cli.py`, `python .agents/test_zzzops_appdata.py`, `python -m unittest discover -s .github/scripts -p 'test_*.py'`, and `python .agents/prompt_stats.py --check`. The app-data test writes only isolated temporary directories in the real platform roots and removes them. `python .github/scripts/semantic_release.py` only writes a local notes file.

Maintainers: see [branch protection](docs/BRANCH_PROTECTION.md) for the required `dev` check, current GitHub Free limitation, closest enforceable `main` policy, and recovery procedure.

## The files that remember things

- `.zzzops/PROJECT.md` — tracked backend, success, KPIs, acceptance criteria, reviewed project policy, and what “valuable” means.
- GitHub Issues — recommended canonical goals, blockers, evidence, relations, and history when selected.
- `goals/items/` and derived `goals/INDEX.md` — created only when the local backend is selected.
- `.zzzops/rules/` — tracked ZzzOps operating rules; machinery, not project content.
- `.zzzops/PREFERENCES.json` — local, ignored user opt-ins for bounded autonomous backlog refills.
- Platform app data — opt-in per-user health preferences and minimal per-machine derived state; never repository state.
- `.zzzops/migration/STATE.json` — keeps old TODOs from returning like a low-budget horror villain.

Agents work sequentially by default, define the observable signal before editing, change one small falsifiable chunk at a time, and inspect real output after every chunk. If the project is opaque, they build a focused harness or scoped MCP observation server instead of vibe-coding and hoping. Execution defaults to the current branch, follows repository Git rules, and gives each completed sub-goal its own commit; capture itself is Git-free.

If a new test discovers a real bug, ZzzOps files a separate TODO and asks you before fixing it. It does not smuggle a surprise product change into “just adding coverage,” because we have all reviewed that pull request before.

## Prompt budget

`python .agents/prompt_stats.py` prints a stable cross-harness estimate: `ceil(canonical UTF-8 bytes / 4)`, with line endings normalized to LF. It is useful for prompt-budget regression, not billing; Codex and Claude Code tokenize differently. CI enforces the committed ceiling; inspect it after any prompt change:

```powershell
python .agents/prompt_stats.py
python .agents/prompt_stats.py --check
```

Go to bed. The backlog knows what to do.
