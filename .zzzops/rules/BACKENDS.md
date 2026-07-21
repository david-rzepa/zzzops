# GitHub goal backend

Canonical `.zzzops/POLICY.json` makes GitHub Issues the goal authority; `.zzzops/PROJECT.md` summarizes it.

Use `INITIALIZATION.md`'s checkpoint portfolio; never rerun `portfolio` there. Require `complete:true` and `valid:true`; use its inventory/graph/human queue. It omits criteria/history, so re-read only the selected goal and match revision/digest. Refresh once after mutation/drift. Standalone `portfolio` is only for explicit inspection/comparison.

Closed goals become validated minimal projections. Re-read only likely duplicates, selection-critical relations, or explicit targets.

Managed issues labeled `zzzops-feedback` are omitted from ordinary portfolio checkpoints. Include them with `--include-feedback` only after one explicit approval for the current execution session; the choice covers the whole feedback queue, is not persisted, and never causes per-issue approval prompts.

## GitHub Issues (`github_issues`)

The checkpoint's one paginated GitHub process confirms identity, authentication, Issues, and management permission. Use native `gh issue`/`gh api` only for targeted reads/writes; the CLI validates structures. If direct `gh` auth works but a sandboxed CLI child fails authentication, rerun the same bounded command once in an approved authenticated context; never reauthenticate or vary commands.

- Repository plus issue number/URL is identity. Use a plain human title: never add a ZzzOps/date ID. Begin the body with concise human sections; no rendered metadata/frontmatter or duplicated title.
- When introducing this backend, explain that goals inherit the repository's visibility and must not contain secrets or raw sensitive data.
- Append one compact hidden `<!-- zzzops-goal ... zzzops-goal -->` JSON block with `.agents/zzzops/zzzops.py`'s `render_managed_goal` helper. It stores state only: GitHub supplies identity/title; inverse `blocks`, human-queue membership, labels, and open/closed are derived. Preserve human/unmanaged text.
- Same-repository parent/dependency relations are positive issue numbers. Derive children/blocking edges portfolio-wide. Put resolutions/history in append-only comments; old comments remain immutable provenance.
- Use label `zzzops`, one `zzzops:status:*`, and one `zzzops:priority:*` as derived indexes.
- Reservations use transient `zzzops:reserve:<issue>` and `zzzops:resource:<hash>` labels. GitHub name uniqueness chooses one winner with Issues permission; metadata binds repository, goal/revision, owner/run, and expiry. Renew/recover by immutable node ID and exact readback, so delayed cleanup cannot delete a replacement. Drift, conflict, malformed state, provider failure, or uncertainty denies ownership; no alternate lock or advisory fallback.
- Before update, re-read issue plus `updated_at`; parse/validate the block and abort/reconcile if the snapshot digest/revision changed. The batch command paginates once and reports incomplete reads instead of guessing.
- Capability/auth/permission/disabled-Issues/label drift is an explicit blocker. Never invent a fallback authority.

## Git boundary

- Capture (`$add-zzzops-goal`, migrate apply, suggest apply) never creates a branch, commit, push, or PR. GitHub issue writes need no empty commit.
- Execute reads Git/review/commit behavior from reviewed PROJECT policy. Before source work, checkpoint only pending local ZzzOps state if needed; never include unrelated changes. Link implementation commits/PRs to the canonical goal when policy uses them.
