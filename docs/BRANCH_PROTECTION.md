# Branch protection

ZzzOps is a public GitHub repository. Protection is implemented through active repository rulesets, not classic branch-protection endpoints. A `404` from `repos/{owner}/{repo}/branches/{branch}/protection` therefore does not mean that the branch is unprotected.

Read rulesets before relying on them; do not test protection with force-pushes, deletion, or direct updates.

```powershell
gh repo view david-rzepa/zzzops --json visibility,url
gh api repos/david-rzepa/zzzops/rulesets
gh api repos/david-rzepa/zzzops/rulesets/19287297 # dev
gh api repos/david-rzepa/zzzops/rulesets/19287218 # main
gh api repos/david-rzepa/zzzops/branches/dev/protection # classic endpoint; 404 is expected here
```

## `dev`

The active `dev` ruleset targets only `refs/heads/dev` and:

- blocks deletion, non-fast-forward updates, and direct updates;
- requires merge-only pull requests;
- requires last-push approval and resolved review threads, while requiring zero approving reviews by count;
- requires the stable GitHub Actions check `dev-required-tests` (the rule does not require the branch to be current);
- has an always-bypass RepositoryRole actor. Read the ruleset before relying on bypass scope; the current caller can bypass it.

`dev-required-tests` is the stable aggregate emitted on every PR to `dev`. It succeeds only when `Core validation (Linux, Python <version>)`, `Plugin core validation (Windows)`, and `Plugin core validation (macOS)` have all succeeded. The workflow has no path filters, dynamic check names, secrets, or write permission, so protection can rely on that one stable context.

Native stacked PRs merge through GitHub's asynchronous stack operation, which does not support administrator bypass. If a fully verified stack is rejected only by a bypassable review rule, preserve it by default. An exact user authorization may permit unstacking after the metadata loss and non-atomic consequence are disclosed, followed by bottom-up `--admin` merges pinned to each head SHA. Failed or pending checks, changed heads, unresolved feedback, and release or safety gates are never bypassed.

## `main`

The active `main` ruleset targets only `refs/heads/main` and blocks deletion, non-fast-forward updates, and direct updates. It currently has no bypass actors and no required-status-check rule.

This means the repository's owner-only release-force-push policy cannot be carried out while the current `main` ruleset remains active: GitHub will reject it. Reconcile the ruleset and the root release policy through an explicit reviewed change before attempting a release rewrite; never work around this by destructive testing.

## Recovery

If `dev-required-tests` is renamed, update the ruleset only after a PR has emitted the replacement successful check. If validation fails, fix it through a PR rather than bypassing `dev`. Before any future, explicitly authorized `main` history rewrite, create and verify a local Git bundle and use `--force-with-lease` against a freshly observed remote SHA.
