# Initializing a repository

Bootstrap is a checklist, run by the `$bootstrap-zzzops-repository` skill over the shipped templates in `plugins/zzzops/zzzops/templates/default/` and plain `git`/`gh`:

1. Choose the remote and the integration branch (`dev` or `main`).
2. Write `.zzzops/POLICY.json` (verification commands, required CI checks, integration branch, first goal id, routing tiers), `.zzzops/workflow.json` and `.zzzops/prompts/` from the templates.
3. `zzzops validate --policy --dir .zzzops` (no remote needed).
4. Land them on the integration branch (through a `zzzops/policy/bootstrap` branch and a PR when the branch is protected).
5. Per clone: `git config zzzops.integrationBranch <branch>` when it is not the remote's default branch, and `zzzops.committer`.
6. Harness setup for Codex or Claude Code: [SETUP.md](../plugins/zzzops/zzzops/references/SETUP.md).
7. GitHub settings: automatic head-branch deletion on without `settings.branching`, off with it (finish PRs would delete the kept release/hotfix branches, and deletion can close or move stacked PRs before the engine retargets them); the merge method allowed; a ruleset protecting `zzzops/goal/**` from deletion and force-push; `zzzops/**` excluded from other branch rules ([Branch protection](BRANCH_PROTECTION.md)).
8. Optionally skip CI on `zzzops/**` pushes and add `.zzzops/worktrees/` to tool ignore files.
9. `zzzops validate`, then capture the first goals with `$add-zzzops-goal`.

## When rules are unreadable

On a private repository on GitHub's free plan, rulesets and branch protection answer 403 and cannot be set. The engine never reads them, so it still works; the bootstrap skill (step 2) does not retry, and gets `required_ci` from the owner or from the check names of recent PRs, so it is filled before validation. An empty `required_ci` means integrate merges with no CI gate. Merges are then guarded only by the required-check gate and `--match-head-commit`; the `zzzops/goal/**` rule is unavailable unless the repository goes public or the plan is upgraded. Step 7 then checks only the repository settings (`delete_branch_on_merge`, the allowed merge methods).

A repository without `.zzzops/workflow.json` on its integration branch reports `not_bootstrapped`.

Goals created by the pre-reset engine are not migrated automatically: see [MIGRATING.md](../plugins/zzzops/zzzops/references/MIGRATING.md).
