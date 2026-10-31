# Initializing a repository

Bootstrap is a checklist, run by the `$bootstrap-zzzops-repository` skill over the shipped templates in `plugins/zzzops/zzzops/templates/default/` and plain `git`/`gh`:

1. Choose the remote and the integration branch (`dev` or `main`).
2. Write `.zzzops/POLICY.json` (verification commands, required CI checks, integration branch, first goal id, routing tiers), `.zzzops/workflow.json` and `.zzzops/prompts/` from the templates.
3. `zzzops validate --policy --dir .zzzops` (no remote needed).
4. Land them on the integration branch (through a `zzzops/policy/bootstrap` branch and a PR when the branch is protected).
5. Per clone: `git config zzzops.integrationBranch <branch>` when it is not the remote's default branch, and `zzzops.committer`.
6. Harness setup for Codex or Claude Code: [SETUP.md](../plugins/zzzops/zzzops/references/SETUP.md).
7. GitHub settings: automatic head-branch deletion on; the merge method allowed; a ruleset protecting `zzzops/goal/**` from deletion and force-push; `zzzops/**` excluded from other branch rules ([Branch protection](BRANCH_PROTECTION.md)).
8. Optionally skip CI on `zzzops/**` pushes and add `.zzzops/worktrees/` to tool ignore files.
9. `zzzops validate`, then capture the first goals with `$add-zzzops-goal`.

A repository without `.zzzops/workflow.json` on its integration branch reports `not_bootstrapped`.

Goals created by the pre-reset engine are not migrated automatically: see [MIGRATING.md](../plugins/zzzops/zzzops/references/MIGRATING.md).
