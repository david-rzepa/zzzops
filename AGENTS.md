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

## Graft navigation

Use [Graft](docs/graft.md) first for code navigation; build/check its graph per worktree. Fall back to `rg` and source inspection for missing results, especially excluded `.agents` and `.github` paths. Graph results never authorize skipping tests.
