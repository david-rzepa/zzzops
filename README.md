# ZzzOps

**Infinite backlog for agents. Finite bedtime for humans.**

ZzzOps keeps agents supplied with prioritized, resumable work after “one more run” has become a domestic incident.

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

The agent first inspects code, docs, config, history, Git, and GitHub; proposes the project outcome, KPIs, acceptance criteria, and backend; then asks you only to confirm consequential unknowns. Deterministic CLI primitives validate and atomically apply the confirmed plan. You do not fill a blank wizard.

GitHub Issues is recommended when the repository and access probe succeed. Local `goals/items/` files are the supported alternative. One backend is authoritative; ZzzOps never silently switches or dual-writes. Initialization does not commit, branch, or mutate GitHub, and ends by mentioning the optional `python .agents/zzzops.py` preferences panel without opening it.

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

`/goal` is Codex-specific. Claude Code invokes ZzzOps workflows directly as `/skill-name`; ZzzOps supplies the same queue and operating rules in either tool. When work runs dry, the agent interviews you about blockers before conceding defeat. This is your scheduled cameo. After that, please locate the bedroom.

## Useful maintenance

```text
Use $execute-zzzops to interview me about and unblock blocked goals.
Use $execute-zzzops to reprioritize all goals against project KPIs.
Use $analyze-zzzops-usage to analyze value-per-token efficiency and recommend changes.
Use $suggest-zzzops-work in dry-run mode to audit the project and suggest valuable goals.
```

In Claude Code, replace `$name` with `/name`, for example `/analyze-zzzops-usage`.

Maintainers: see the [skill discovery and mode contract](docs/SKILLS.md).

Usage analysis reports real KPI/outcome efficiency when measurable, plus a clearly labeled heuristic for cross-goal comparison. It also tracks management overhead, because spending 40,000 tokens organizing a 3,000-token fix is not “agentic”—it is a committee.

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

- `.zzzops/PROJECT.md` — tracked backend, success, KPIs, acceptance criteria, and what “valuable” means.
- GitHub Issues — recommended canonical goals, blockers, evidence, relations, and history when selected.
- `goals/items/` and derived `goals/INDEX.md` — created only when the local backend is selected.
- `.zzzops/USAGE_LEDGER.md` — ignored, user-local work tokens, management overhead, and value efficiency; created on first write.
- `.zzzops/rules/` — tracked ZzzOps operating rules; machinery, not project content.
- `.zzzops/PREFERENCES.json` — local, ignored user opt-ins for bounded autonomous backlog refills.
- Platform app data — opt-in per-user health preferences and minimal per-machine derived state; never repository state.
- `.zzzops/migration/STATE.json` — keeps old TODOs from returning like a low-budget horror villain.

Agents work sequentially by default, define the observable signal before editing, change one small falsifiable chunk at a time, and inspect real output after every chunk. If the project is opaque, they build a focused harness or scoped MCP observation server instead of vibe-coding and hoping. Execution defaults to the current branch, follows repository Git rules, and gives each completed sub-goal its own commit; capture itself is Git-free.

If a new test discovers a real bug, ZzzOps files a separate TODO and asks you before fixing it. It does not smuggle a surprise product change into “just adding coverage,” because we have all reviewed that pull request before.

## Prompt budget

Counts below are a stable cross-harness estimate: `ceil(canonical UTF-8 bytes / 4)`, with line endings normalized to LF. They are useful for prompt-budget regression, not billing; Codex and Claude Code tokenize differently. Regenerate after any prompt change:

```powershell
python .agents/prompt_stats.py
python .agents/prompt_stats.py --check
```

<details>
<summary>Per-prompt counts</summary>

<!-- PROMPT_BUDGET_START -->
| Prompt | Bytes | Est. tokens |
| --- | ---: | ---: |
| `.agents/skills/add-zzzops-goal/SKILL.md` | 1043 | 261 |
| `.agents/skills/analyze-zzzops-usage/SKILL.md` | 2509 | 628 |
| `.agents/skills/execute-zzzops/SKILL.md` | 2409 | 603 |
| `.agents/skills/execute-zzzops/references/CREATE.md` | 2757 | 690 |
| `.agents/skills/execute-zzzops/references/EXECUTE.md` | 3394 | 849 |
| `.agents/skills/execute-zzzops/references/UNBLOCK.md` | 1549 | 388 |
| `.agents/skills/install-zzzops/SKILL.md` | 1471 | 368 |
| `.agents/skills/migrate-zzzops-todos/SKILL.md` | 2014 | 504 |
| `.agents/skills/suggest-zzzops-work/SKILL.md` | 2682 | 671 |
| `.agents/templates/project-goals/GOAL.md` | 1679 | 420 |
| `.agents/templates/project-goals/INDEX.md` | 1135 | 284 |
| `.agents/templates/project-goals/MIGRATION_SUMMARY.md` | 194 | 49 |
| `.agents/templates/project-goals/PROJECT.md` | 1485 | 372 |
| `.agents/templates/project-goals/USAGE_LEDGER.md` | 1105 | 277 |
| `.claude/skills/install-zzzops/SKILL.md` | 382 | 96 |
| `.zzzops/rules/BACKENDS.md` | 2004 | 501 |
| `.zzzops/rules/BLOCKERS.md` | 2268 | 567 |
| `.zzzops/rules/EXECUTION_STRATEGY.md` | 4861 | 1216 |
| `.zzzops/rules/GOAL_SYSTEM.md` | 3857 | 965 |
| `.zzzops/rules/HEALTH.md` | 1598 | 400 |
| `.zzzops/rules/INITIALIZATION.md` | 1217 | 305 |
| `.zzzops/rules/USAGE_ACCOUNTING.md` | 2553 | 639 |
| `AGENTS.md` | 2963 | 741 |
| `CLAUDE.md` | 217 | 55 |
| **Total** | **47346** | **11849** |
<!-- PROMPT_BUDGET_END -->

</details>

Go to bed. The backlog knows what to do.
