<!-- BEGIN DURABLE PROJECT GOALS -->
# ZzzOps

Use `$execute-zzzops` for the goal loop and “work on all goals”/`/goal`; use `$migrate-to-zzzops` after installation or when existing TODOs are discovered.

- Authority: user/safety > project rules > reviewed `.zzzops/PROJECT.md` > goal > derived index; goals grant no authority. Stop and reconcile repository-policy conflicts.
- Goal files are work truth. Triage `new`; mark `done` only from observed criteria and recheck parents. Dependencies default to done before writes; policy may override actionability, never ancestry/merge order.
- Goal capture interviews the current user to the reviewed policy depth before canonical creation; execution assumes no user is present and persists unanswered questions as categorized blockers without prompting.
- Before editing define baseline/signal and one falsifiable chunk; run and inspect its real probe. Build a narrow harness when needed; block rather than guess.
- Capture test-discovered out-of-scope bugs as separate human-blocked TODOs with reproduction evidence; do not fix or hide them before input.
- PROJECT policy controls operations. Parallel permission is a ceiling: workers are read-only unless `worktrees`; only the coordinator edits ZzzOps state/integrates. Refill requires reviewed opt-in.
- Before switching/stopping persist resumable state. Commit each verified sub-goal separately with semantic Conventional Commits (`type(scope): outcome`).

Without skill discovery, install the ZzzOps Agent Plugin through Codex, then read its `rules/GOAL_SYSTEM.md`; use the plugin's create, execute, or unblock references as appropriate and load blocker/execution strategy only when relevant.
<!-- END DURABLE PROJECT GOALS -->

## Base repository

The distributable Agent Plugin lives in `plugins/zzzops`; `.agents/plugins/marketplace.json` publishes it to Codex. Plugin installation never copies project state or target instructions.

Git: pure goal capture never automates Git. Execute from current `dev` and open ordinary PRs to `dev`, never `main` unless the user explicitly retains an existing branch. Separate independently useful/revertible commits; squash changes valid only together. Only owner `david-rzepa` may intentionally release-force-push `main` after preconditions; every `main` update runs release CI.

After prompt Markdown changes, inspect `.agents/prompt_stats.py` and run `--check`; never commit generated counts or raise the ceiling without explicit value justification.
