# GitHub goal backend

`.zzzops/PROJECT.md` records GitHub Issues as the canonical goal authority.

Use the portfolio embedded by `INITIALIZATION.md`'s single checkpoint; never run a second portfolio command there. Require `complete:true` and `valid:true`; use its compact inventory/graph/human queue. It omits criteria/history, so re-read only the selected goal before writing and match revision/digest. Refresh the checkpoint once after mutation/drift. Standalone `portfolio` is for explicit CLI inspection/comparison.

Closed goals are fully validated, then emitted as minimal archived projections. Re-read only likely duplicates, selection-critical relations, or explicit user targets.

## GitHub Issues (`github_issues`)

The checkpoint's single paginated GitHub process must confirm identity, authentication, Issues, and management permission while fetching managed issues. Agents use native `gh issue`/`gh api` only for targeted reads/writes; the CLI validates managed structures.

- Repository plus issue number/URL is identity. Use a plain human title: never add a ZzzOps/date ID. Begin the body with concise human sections; no rendered metadata/frontmatter or duplicated title.
- When introducing this backend, explain that goals inherit the repository's visibility and must not contain secrets or raw sensitive data.
- Append one compact hidden `<!-- zzzops-goal ... zzzops-goal -->` JSON block with `.agents/zzzops.py`'s `render_managed_goal` helper. It stores state only: GitHub supplies identity/title; inverse `blocks`, human-queue membership, labels, and open/closed are derived. Preserve human/unmanaged text.
- Same-repository parent/dependency relations are positive issue numbers. Derive children/blocking edges portfolio-wide. Put resolutions/history in append-only comments; old comments remain immutable provenance.
- Use label `zzzops`, one `zzzops:status:*`, and one `zzzops:priority:*` as derived indexes.
- Before update, re-read issue plus `updated_at`; parse/validate the block and abort/reconcile if the snapshot digest/revision changed. The batch command paginates once and reports incomplete reads instead of guessing.
- Capability/auth/permission/disabled-Issues/label drift is an explicit blocker. Never invent a fallback authority.

## Git boundary

- Capture (`$add-zzzops-goal`, migrate apply, suggest apply) never creates a branch, commit, push, or PR. GitHub issue writes need no empty commit.
- Execute reads Git/review/commit behavior from reviewed PROJECT policy. Before source work, checkpoint only pending local ZzzOps state if needed; never include unrelated changes. Link implementation commits/PRs to the canonical goal when policy uses them.
