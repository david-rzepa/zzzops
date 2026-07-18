# Goal backends

`.zzzops/PROJECT.md` selects exactly one authority.

When initialization selects GitHub while local goals exist, shared state must set `migration_pending:true`. Until an approved migration clears it, local files remain transitional truth and other ordinary workflows stop; never read/write both as co-authorities.

## GitHub Issues (`github_issues`)

Prefer when inspect plus a read-only `gh api repos/{owner}/{repo}` probe confirms identity, authentication, Issues, and permission. Agents use native `gh issue`/`gh api`; the CLI only validates managed structures.

- Repository plus issue number/URL is identity. Use a plain human title: never add a ZzzOps/date ID. Begin the body with concise human sections; no rendered metadata/frontmatter or duplicated title.
- Append one compact hidden `<!-- zzzops-goal ... zzzops-goal -->` JSON block using `.agents/zzzops.py`. It stores state only: GitHub supplies identity/title; inverse `blocks`, human-queue membership, labels, and open/closed are derived. Preserve human/unmanaged text.
- Same-repository parent/dependency relations are positive issue numbers. Derive children/blocking edges portfolio-wide. Put resolutions/history in append-only comments; old comments remain immutable provenance.
- Use label `zzzops`, one `zzzops:status:*`, and one `zzzops:priority:*` as derived indexes.
- Before update, re-read issue plus `updated_at`; parse/validate the block and abort/reconcile if the observed digest/revision changed. Paginate portfolio reads.
- Capability/auth/permission/disabled-Issues/label drift is an explicit blocker. Never fall back to local files automatically.

## Local files (`local_files`)

Use `goals/items/` as truth and derive `goals/INDEX.md` only for this backend; create neither for GitHub. Start records from `.agents/templates/project-goals/GOAL.md`; follow `GOAL_SYSTEM.md`. Backend switching/import is a separate reviewed operation.

## Git boundary

- Capture (`$add-zzzops-goal`, migrate apply, suggest apply) never creates a branch, commit, push, or PR. Leave local goal edits uncommitted; GitHub issue writes need no empty commit.
- Execute reads Git/review/commit behavior from reviewed PROJECT policy. Before source work, checkpoint only pending local ZzzOps state if needed; never include unrelated changes. Link implementation commits/PRs to the canonical goal when policy uses them.
