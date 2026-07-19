# GitHub goal backend

`.zzzops/PROJECT.md` records GitHub Issues as the canonical goal authority.

At each decision checkpoint run `python .agents/zzzops.py --repo . portfolio --format json` once. Require `complete:true` and `valid:true`; use its compact inventory/graph/human queue. It omits criteria/history, so re-read only the selected canonical goal before writing and match revision/digest. Refresh after relevant mutation or drift.

## GitHub Issues (`github_issues`)

Require inspect plus a read-only `gh api repos/{owner}/{repo}` probe to confirm identity, authentication, Issues, and permission. Agents use native `gh issue`/`gh api`; the CLI only validates managed structures.

- Repository plus issue number/URL is identity. Use a plain human title: never add a ZzzOps/date ID. Begin the body with concise human sections; no rendered metadata/frontmatter or duplicated title.
- Append one compact hidden `<!-- zzzops-goal ... zzzops-goal -->` JSON block using `.agents/zzzops.py`. It stores state only: GitHub supplies identity/title; inverse `blocks`, human-queue membership, labels, and open/closed are derived. Preserve human/unmanaged text.
- Same-repository parent/dependency relations are positive issue numbers. Derive children/blocking edges portfolio-wide. Put resolutions/history in append-only comments; old comments remain immutable provenance.
- Use label `zzzops`, one `zzzops:status:*`, and one `zzzops:priority:*` as derived indexes.
- Before update, re-read issue plus `updated_at`; parse/validate the block and abort/reconcile if the snapshot digest/revision changed. The batch command paginates once and reports incomplete reads instead of guessing.
- Capability/auth/permission/disabled-Issues/label drift is an explicit blocker. Never invent a fallback authority.

## Git boundary

- Capture (`$add-zzzops-goal`, migrate apply, suggest apply) never creates a branch, commit, push, or PR. GitHub issue writes need no empty commit.
- Execute reads Git/review/commit behavior from reviewed PROJECT policy. Before source work, checkpoint only pending local ZzzOps state if needed; never include unrelated changes. Link implementation commits/PRs to the canonical goal when policy uses them.
