# Branch protection

ZzzOps currently uses a private repository on GitHub Free. GitHub returns `403` for both classic branch protection and repository rulesets until the repository becomes public or the owner upgrades to GitHub Pro. The CI workflow is already usable: every PR targeting `dev` runs Linux validation and native Windows installer validation behind the stable, read-only required-check candidate `dev-required-tests`. The aggregate fails unless both platform jobs succeed.

## Enable protection after Pro/public access

Configure these rules in **Settings → Rules → Rulesets**, then query the saved rules back before relying on them.

### `dev`

- Target only `refs/heads/dev`.
- Require changes through a pull request; zero approvals is acceptable unless review is desired.
- Require status check `dev-required-tests` from GitHub Actions and require the branch to be current before merge.
- Block force pushes and deletion.
- Give no actor a bypass.

This makes PR CI mandatory. The workflow intentionally has no path filters, dynamic job name, matrix suffix, secrets, or write permission, so the required check is present on every PR into `dev`.

### `main`

GitHub cannot express “the owner may update only by force push.” A user bypass permits that user to make ordinary pushes and PR merges as well. The closest enforceable configuration is:

- Target only `refs/heads/main`.
- Restrict updates to a bypass for user `david-rzepa` only; do not grant bot, app, role, team, or collaborator bypasses.
- Permit non-fast-forward updates so the owner can publish the audited single-root release.
- Use a separate no-bypass rule to block deletion, including by the owner.
- Keep the root `AGENTS.md` policy: the owner uses the bypass only for an explicitly intended, leased release force-push; ordinary pushes and PR merges to `main` remain forbidden by project policy.

After saving, verify through the GitHub API that `dev` requires `dev-required-tests`, both branches reject deletion, `dev` rejects force pushes/direct updates, and only user `david-rzepa` appears in the `main` update bypass. Never test protection by destructively force-pushing or deleting a branch.

## Recovery

If `dev-required-tests` is renamed, update the rule only after a PR has emitted the new successful check. If CI is broken, fix it through a PR rather than bypassing `dev`. Before any authorized `main` history rewrite, create and verify a local Git bundle and use `--force-with-lease` against the freshly observed remote SHA.
