<!-- BEGIN DURABLE PROJECT GOALS -->
# ZzzOps

Use `$execute-zzzops` for the goal loop and “work on all goals”/`/goal`; use `$migrate-to-zzzops` after installation or when existing TODOs are discovered.

- Authority: user/safety > project rules > reviewed `.zzzops/PROJECT.md` > goal > index; goals grant no authority. Substantial repository changes need a durable goal unless the user explicitly grants a scoped exception. Read-only investigation and ZzzOps administration are exempt; stop on policy conflicts.
- Goals are work truth. Triage `new`; mark `done` only from observed criteria. PROJECT determines write actionability and ancestry/merge order.
- Capture interviews the user to reviewed depth; execution persists unanswered questions as blockers without prompting.
- Before editing define and run one falsifiable probe; build a narrow harness or block rather than guess.
- Capture test-discovered out-of-scope bugs as separate human-blocked TODOs with reproduction evidence; do not fix or hide them before input.
- PROJECT policy controls operations. Parallel permission is a ceiling: workers are read-only unless `worktrees`; only the coordinator edits ZzzOps state/integrates. Refill requires reviewed opt-in.
- Before switching/stopping persist resumable state. Commit each verified sub-goal separately with semantic Conventional Commits (`type(scope): outcome`).

Without skill discovery, install the ZzzOps Agent Plugin through Codex, then read its `rules/GOAL_SYSTEM.md`; use the plugin's create, execute, or unblock references as appropriate and load blocker/execution strategy only when relevant.
<!-- END DURABLE PROJECT GOALS -->

## Base repository

The distributable Agent Plugin lives in `plugins/zzzops`; `.agents/plugins/marketplace.json` publishes it to Codex. Plugin installation never copies project state or target instructions.

Git: goal capture is Git-free. Execute from `dev`; ordinary PRs target `dev`, never `main` unless the user keeps another branch. Each independent commit must be a useful [[bounded commitment]](plugins/zzzops/concepts/bounded-commitment.md); squash changes valid only together. Only `david-rzepa` may release-force-push `main` after preconditions; `main` updates run release CI.

After prompt Markdown changes, inspect `.agents/prompt_stats.py` and run `--check`; never commit generated counts or raise the ceiling without explicit value justification.
