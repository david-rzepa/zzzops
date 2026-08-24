# GitHub goal backend

GitHub Issues is goal authority; `.zzzops/PROJECT.md` summarizes policy. Require checkpoint `complete:true`/`valid:true`; never rerun `portfolio`. Read minimal indexes, selected bodies, then material comments. Match the selected revision/digest; inspect closed goals before using history. Refresh once after mutation/drift; standalone `portfolio` only compares. Ordinary checkpoints omit `zzzops-feedback`; `--include-feedback` needs one current-session queue-wide approval—never persist or ask per issue.

## GitHub Issues (`github_issues`)

`checkpoint` confirms identity, auth, Issues, and management permission once. Use `gh` only for targeted operations under INITIALIZATION's authenticated-context rule.

- Identity is repository plus issue number/URL. Use a plain title and concise human sections without generated IDs/frontmatter/repeated title. Goals inherit visibility; forbid secrets/raw sensitive data.
- Create via `<python> <zzzops-cli> --repo . goal create --input FILE`. UTF-8 JSON has exactly `schema_version`, human `title`/`body`, optional non-ZzzOps `labels`, and a complete revision-1 `new` goal without claim/implementation. The CLI validates, labels, creates via JSON stdin, and confirms identity. Preserve unknowns as blockers; derive inverse edges/queue.
- Parent/dependencies are same-repository positive issue numbers; derive inverse edges portfolio-wide.
- Bodies keep current human sections, relationships, open blockers, next action, and compact state. Before replacement confirm one lossless content-addressed history comment with prior body/requested transition. Retries reuse its transition ID without duplicate history.
- Derive `zzzops`, current schema, one status, and one priority label. `goal inspect` repairs one selected legacy goal; `goal migrate-open` is bounded/open-only.
- Transient goal/resource labels reserve one GitHub-name-unique winner. Bind repository, goal/revision, owner/run, expiry; renew/recover by immutable node ID and exact readback. Drift, conflict, malformed/provider failure, or uncertainty denies ownership; no fallback lock.
- Update via `<python> <zzzops-cli> goal transition --goal N --input FILE`; input binds expected revision/digest, preserves human text, derives labels/state, and validates the write.
- Capability/auth/permission/Issues/label drift blocks explicitly; invent no fallback authority.

## Git boundary

- Capture/migrate/suggest writes never create branch, commit, push, PR, or empty checkpoint.
- Execute takes Git/review/commit behavior from PROJECT. Before source work checkpoint only pending local ZzzOps state, exclude unrelated changes, and link commits/PRs when policy requires.
