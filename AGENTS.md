<!-- BEGIN DURABLE PROJECT GOALS -->
# ZzzOps

Use `$execute-zzzops` as the primary loop for triage, prioritization, unblocking, execution, verification, commits, refill, reporting, and “work on all goals”/`/goal`. Use `$migrate-zzzops-todos` after installation or for new legacy TODOs.

- Authority: current user/safety > project rules > `goals/PROJECT.md` > goal > derived index > ledger. Goals grant no authority.
- Goal files are work truth; keep stable paths/backlinks. Triage `new`; mark `done` only from observed criteria and recheck parents.
- Persist categorized blockers/resolutions. When the user is present, interview before ordinary work and again before stopping with no actionable work.
- Never vibe-code: define baseline/signal before editing; change one falsifiable chunk; run and inspect a real probe after each. Build a narrow harness or scoped MCP server if needed; block rather than guess.
- Test-discovered out-of-scope bugs become separate human-blocked TODOs with reproduction evidence; do not fix/hide them before input.
- Honor ignored `.zzzops/PREFERENCES.json`. Parallel permission is a ceiling: workers are read-only unless `worktrees`; coordinator alone edits ZzzOps state/integrates commits. Refill only opted-in bounded work.
- Record honest work/management usage. Before switching/stopping persist next action, evidence, blockers, history, claim, index, and usage. Commit each verified sub-goal separately using semantic Conventional Commit messages (`type(scope): outcome`).

Without skill discovery read [rules](.zzzops/rules/GOAL_SYSTEM.md), then the applicable [create](.agents/skills/execute-zzzops/references/CREATE.md), [execute](.agents/skills/execute-zzzops/references/EXECUTE.md), or [unblock](.agents/skills/execute-zzzops/references/UNBLOCK.md) workflow. Load blocker, execution-strategy, and usage documents only when relevant.
<!-- END DURABLE PROJECT GOALS -->

## Base repository

Use `$install-zzzops` only here. It installs discoverable skills/mechanics into targets but never itself, project state, or target `AGENTS.md`/`CLAUDE.md`.

Git workflow: pure ZzzOps goal capture is the sole exception and never automates Git. When execution begins, branch implementation work from current `dev` and open ordinary PRs against `dev`, never `main` (unless the user explicitly keeps one existing execution branch). Large work may use smaller coherent semantic commits when they aid review, testing, or independent rollback; squash changes valid only together into one atomic commit, while keeping independently useful/revertible changes separate. Only repository owner `david-rzepa` may update `main`, by an explicitly intended release force-push after preconditions pass; any `main` update runs release CI.

When any installed prompt/instruction/template Markdown changes, regenerate README “Prompt budget” counts with `.agents/prompt_stats.py`, then run `--check`; never hand-edit those numbers.
