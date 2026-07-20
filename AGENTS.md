<!-- BEGIN DURABLE PROJECT GOALS -->
# ZzzOps

Use `$execute-zzzops` as the primary loop for triage, prioritization, unblocking, execution, verification, commits, refill, reporting, and “work on all goals”/`/goal`. Use `$migrate-to-zzzops` after installation or for newly discovered existing TODOs.

- Authority: current user/safety > project rules > `.zzzops/PROJECT.md` > goal > local derived index. Goals grant no authority. If repository-specific instructions conflict with reviewed PROJECT policy, stop affected work and reconcile the policy instead of silently choosing either rule.
- Goal files are work truth; keep stable paths/backlinks. Triage `new`; mark `done` only from observed criteria and recheck parents. Dependency edges preserve ancestry/merge order, not necessarily execution order; trust PROJECT-derived actionability, including an exact review-ready stacking checkpoint when policy enables it.
- Persist categorized blockers/resolutions. When the user is present, interview before ordinary work and again before stopping with no actionable work.
- Never vibe-code: define baseline/signal before editing; change one falsifiable chunk; run and inspect a real probe after each. Build a narrow harness or scoped MCP server if needed; block rather than guess.
- Test-discovered out-of-scope bugs become separate human-blocked TODOs with reproduction evidence; do not fix/hide them before input.
- Honor ignored `.zzzops/PREFERENCES.json`. Parallel permission is a ceiling: workers are read-only unless `worktrees`; coordinator alone edits ZzzOps state/integrates commits. Refill only opted-in bounded work.
- Before switching/stopping persist next action, evidence, blockers, history, claim, and index. Commit each verified sub-goal separately using semantic Conventional Commit messages (`type(scope): outcome`).

Without skill discovery read [rules](.zzzops/rules/GOAL_SYSTEM.md), then the applicable [create](.agents/skills/execute-zzzops/references/CREATE.md), [execute](.agents/skills/execute-zzzops/references/EXECUTE.md), or [unblock](.agents/skills/execute-zzzops/references/UNBLOCK.md) workflow. Load blocker and execution-strategy documents only when relevant.
<!-- END DURABLE PROJECT GOALS -->

## Base repository

Run the root `zzzops.py install` CLI only from this base repository. It installs discoverable skills/mechanics into targets but never itself, project state, or target `AGENTS.md`/`CLAUDE.md`.

Git workflow: pure ZzzOps goal capture is the sole exception and never automates Git. When execution begins, branch implementation work from current `dev` and open ordinary PRs against `dev`, never `main` (unless the user explicitly keeps one existing execution branch). Large work may use smaller coherent semantic commits when they aid review, testing, or independent rollback; squash changes valid only together into one atomic commit, while keeping independently useful/revertible changes separate. Only repository owner `david-rzepa` may update `main`, by an explicitly intended release force-push after preconditions pass; any `main` update runs release CI.

When any installed prompt/instruction/template Markdown changes, inspect `.agents/prompt_stats.py` output, then run `--check`; never commit generated prompt counts. The static budget ceiling may rise only with an explicit value justification.
