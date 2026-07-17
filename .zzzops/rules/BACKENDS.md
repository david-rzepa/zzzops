# Goal backends

`.zzzops/PROJECT.md` selects exactly one authority.

When initialization selects GitHub while local goals exist, shared state must set `migration_pending:true`. Until an approved migration clears it, local files remain transitional truth and other ordinary workflows stop; never read/write both as co-authorities.

## GitHub Issues (`github_issues`)

Prefer when inspect plus a read-only `gh api repos/{owner}/{repo}` probe confirms identity, authentication, Issues, and permission. Agents use native `gh issue`/`gh api`; the CLI only validates managed structures.

- Use label `zzzops`, one `zzzops:status:*`, and one `zzzops:priority:*`. Treat labels as indexes; the managed body is truth.
- Put current state in one `<!-- zzzops-goal ... zzzops-goal -->` JSON block using the fields enforced by `.agents/zzzops.py`. Preserve all unmanaged body text.
- Put resolutions/history in append-only issue comments. Relations use issue URLs/numbers and stable ZzzOps IDs.
- Before update, re-read issue plus `updated_at`; parse/validate the block and abort/reconcile if the observed digest/revision changed. Paginate portfolio reads.
- Capability/auth/permission/disabled-Issues/label drift is an explicit blocker. Never fall back to local files automatically.

## Local files (`local_files`)

Use `goals/items/` as truth and derive `goals/INDEX.md` only for this backend; create neither for GitHub. Start records from `.agents/templates/project-goals/GOAL.md`; follow `GOAL_SYSTEM.md`. Backend switching/import is a separate reviewed operation.

## Git boundary

- Capture (`$add-zzzops-todo`, migrate apply, suggest apply) never creates a branch, commit, push, or PR. Leave local goal edits uncommitted; GitHub issue writes need no empty commit.
- Execute defaults to the current branch. Before source work, checkpoint only pending local ZzzOps state if needed; never include unrelated changes. Then obey repository branch/PR rules and link implementation commits/PRs to the canonical goal.
