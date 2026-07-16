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

Review the preview and let the skill apply it. The installer copies discoverable skills, mechanics, and blank state—never itself, another project’s goals, or the target’s `AGENTS.md`/`CLAUDE.md`.

Open a new Codex task or Claude Code session in the target project so its ZzzOps skills are discovered.

### 3. Migrate existing work

From the target project in Codex:

```text
Use $migrate-zzzops-todos to inspect and migrate existing TODOs.
```

In Claude Code, invoke the same workflow as:

```text
/migrate-zzzops-todos inspect and migrate existing TODOs
```

The agent inventories candidates, asks about project goals/KPIs and exclusions, presents a human-readable plan, then migrates only after approval. Inline TODO comments remain; dedicated backlog files retire only after verified coverage.

### 4. Add new work

```text
Use $add-zzzops-todo to capture <the thing we should eventually do>.
```

ZzzOps checks duplicates, asks important questions, relates value to `goals/PROJECT.md`, and creates a durable goal with a resumable next action.

### 5. Execute—and go to bed

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

First-release installs may retain the old generic skill directories after an update so local customizations are never deleted automatically. Once the renamed skills are discovered and verified, remove the obsolete `add-project-todo`, `migrate-project-goals`, and `suggest-project-work` directories from `.agents/skills/` and `.claude/skills/`.

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

Today it edits preferences. Tomorrow it may achieve sentience and add a “notify spouse that deployment is stable” menu item, so the command has room to grow.

## Releases

Develop on branches created from `dev` and integrate ordinary work back into `dev`. Each push to `dev` runs the release planner and tests with read-only repository permission; it prints the next version and notes but cannot publish anything. Push or merge to `main` only for an intended release: the same planner then receives `contents: write` and creates the Git tag and GitHub Release.

Versions follow Conventional Commits since the latest `vMAJOR.MINOR.PATCH` tag: `!`, `BREAKING CHANGE:`, or `BREAKING-CHANGE:` bumps major, `feat` bumps minor, and `fix`/`perf` bumps patch. Other types do not release. The first release applies those rules from `0.0.0`; reruns with no new releasable commits are no-ops. No repository secret is required beyond GitHub's job token.

To diagnose a release, inspect the **Semantic release** run and its test, preview, or publish step. Reproduce the planner locally with `python -m unittest discover -s .github/scripts -p 'test_*.py'` and `python .github/scripts/semantic_release.py`; the latter only writes a local notes file. Confirm branch, commit messages, latest tag, job permission, and GitHub CLI output before retrying.

## The files that remember things

- `goals/PROJECT.md` — success, KPIs, acceptance criteria, and what “valuable” means.
- `goals/items/` — goals, sub-goals, blockers, evidence, and next actions.
- `goals/INDEX.md` — prioritized queue and human-input desk.
- `goals/USAGE_LEDGER.md` — work tokens, management overhead, and value efficiency.
- `.zzzops/rules/` — tracked ZzzOps operating rules; machinery, not project content.
- `.zzzops/PREFERENCES.json` — local, ignored user opt-ins for bounded autonomous backlog refills.
- `.zzzops/migration/STATE.json` — keeps old TODOs from returning like a low-budget horror villain.

Agents work sequentially by default, define the observable signal before editing, change one small falsifiable chunk at a time, and inspect real output after every chunk. If the project is opaque, they build a focused harness or scoped MCP observation server instead of vibe-coding and hoping. Each completed sub-goal gets its own commit on the current branch.

If a new test discovers a real bug, ZzzOps files a separate TODO and asks you before fixing it. It does not smuggle a surprise product change into “just adding coverage,” because we have all reviewed that pull request before.

## Prompt budget

Counts below are a stable cross-harness estimate: `ceil(UTF-8 bytes / 4)`. They are useful for prompt-budget regression, not billing; Codex and Claude Code tokenize differently. Regenerate after any prompt change:

```powershell
python .agents/prompt_stats.py
python .agents/prompt_stats.py --check
```

<details>
<summary>Per-prompt counts</summary>

<!-- PROMPT_BUDGET_START -->
| Prompt | Bytes | Est. tokens |
| --- | ---: | ---: |
| `.agents/skills/add-zzzops-todo/SKILL.md` | 737 | 185 |
| `.agents/skills/analyze-zzzops-usage/SKILL.md` | 2265 | 567 |
| `.agents/skills/execute-zzzops/SKILL.md` | 1772 | 443 |
| `.agents/skills/execute-zzzops/references/CREATE.md` | 2644 | 661 |
| `.agents/skills/execute-zzzops/references/EXECUTE.md` | 3285 | 822 |
| `.agents/skills/execute-zzzops/references/UNBLOCK.md` | 1532 | 383 |
| `.agents/skills/install-zzzops/SKILL.md` | 1465 | 367 |
| `.agents/skills/migrate-zzzops-todos/SKILL.md` | 1854 | 464 |
| `.agents/skills/suggest-zzzops-work/SKILL.md` | 2497 | 625 |
| `.agents/templates/project-goals/INDEX.md` | 1135 | 284 |
| `.agents/templates/project-goals/MIGRATION_SUMMARY.md` | 222 | 56 |
| `.agents/templates/project-goals/PROJECT.md` | 1295 | 324 |
| `.agents/templates/project-goals/TEMPLATE_DIFF.md` | 352 | 88 |
| `.agents/templates/project-goals/USAGE_LEDGER.md` | 1105 | 277 |
| `.claude/skills/install-zzzops/SKILL.md` | 382 | 96 |
| `.zzzops/rules/BLOCKERS.md` | 2213 | 554 |
| `.zzzops/rules/EXECUTION_STRATEGY.md` | 4861 | 1216 |
| `.zzzops/rules/GOAL_SYSTEM.md` | 3641 | 911 |
| `.zzzops/rules/USAGE_ACCOUNTING.md` | 2355 | 589 |
| `AGENTS.md` | 2506 | 627 |
| `CLAUDE.md` | 217 | 55 |
| `goals/TEMPLATE.md` | 1648 | 412 |
| **Total** | **39983** | **10006** |
<!-- PROMPT_BUDGET_END -->

</details>

Go to bed. The backlog knows what to do.
