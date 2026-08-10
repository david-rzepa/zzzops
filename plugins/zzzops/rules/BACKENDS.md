# GitHub goal backend

Canonical policy makes GitHub Issues goal authority; `.zzzops/PROJECT.md` summarizes it.

Require checkpoint `complete:true`/`valid:true`; never rerun `portfolio`. Stage reads from minimal indexes, to selected bodies, then material comments. Re-read only a selected goal and match revision/digest; inspect a closed goal before using its history. Refresh once after mutation/drift; standalone `portfolio` is comparison-only.

Ordinary checkpoints omit `zzzops-feedback`. `--include-feedback` requires one explicit current-session approval covering the whole queue; never persist it or ask per issue.

## GitHub Issues (`github_issues`)

`checkpoint` confirms identity, auth, Issues, and management permission in one paginated process. Use `gh` only for targeted operations and apply INITIALIZATION's authenticated-context rule.

- Identity is repository plus issue number/URL. Use a plain title and concise human sections without generated IDs, metadata, frontmatter, or repeated title. Goals inherit repository visibility; forbid secrets/raw sensitive data.
- Create with `<python> <zzzops-cli> --repo . goal create --input FILE`. Its UTF-8 JSON contains exactly `schema_version`, plain human `title`/`body`, optional non-ZzzOps `labels`, and a complete revision-1 `new` `goal` without claim/implementation. The CLI validates, renders/labels, makes one JSON-stdin create, and confirms identity. Preserve unknowns as blockers; derive inverse edges/queue.
- Parent/dependencies are same-repository positive issue numbers; derive inverse edges portfolio-wide.
- Keep bodies current-only: active human sections plus relationships, open blockers, next action, and compact managed state. Before replacement, confirm one lossless content-addressed history comment containing the prior body and requested transition. Retries reuse its transition ID and never duplicate confirmed history.
- Derive `zzzops`, current `zzzops:schema:v*`, one status, and one priority label. New goals start current; `goal inspect` repairs one selected legacy goal and `goal migrate-open` is bounded/open-only.
- Reservations use transient goal/resource labels; GitHub name uniqueness chooses one Issues-permitted winner. Metadata binds repository, goal/revision, owner/run, expiry; renew/recover by immutable node ID and exact readback so delayed cleanup cannot delete a replacement. Drift, conflict, malformed state, provider failure, or uncertainty denies ownership; no fallback lock.
- Apply updates via `<python> <zzzops-cli> goal transition --goal N --input FILE`. UTF-8 input binds expected revision/digest to the next goal, preserves human text, derives labels/state, and validates the write.
- Capability/auth/permission/Issues/label drift is an explicit blocker; never invent fallback authority.

## Git boundary

- Capture (`$add-zzzops-goal`, migrate apply, suggest apply) never creates a branch, commit, push, or PR. GitHub issue writes need no empty commit.
- Execute reads Git/review/commit behavior from reviewed PROJECT policy. Before source work, checkpoint only pending local ZzzOps state if needed; never include unrelated changes. Link implementation commits/PRs to the canonical goal when policy uses them.
