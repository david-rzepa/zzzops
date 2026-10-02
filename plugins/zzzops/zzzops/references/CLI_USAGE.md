# ZzzOps CLI

Run package-local [`zzzops.py`](../zzzops.py), never globally. Use the skill's semantic `--intent` with `workflow --intent INTENT`; copy returned `--goal`,
runtime and input.

Follow `next_steps`, `instruction`, policy.path and evidence fields. Read policy;
then send `start` and `bind` with receipt and actual executor.
Send `submission` using `command` when supplied, with acquired node, lease and actor.
No receipt for renewals/submissions. Checkpoint missing context.

Infer no operations, models, task order or authority. Follow finite resource
allocations and publication authorization. Only root coordinates blockers
and human approval. Human approval is a separate step; execution/review implies
no approval. Reinvoke.
Execution automatically migrates supported open v1 goals to v2. Running this
lossless schema migration needs no conversion review or human approval. It
preserves human text/history, relationships and unresolved obligations, creates
no product Results, and grants no workspace or publication authority. Historical
reads and preview never migrate or reopen.

For bounded bulk migration, submit `{"operation":"migration_batch","action":"migrate","limit":20}`
or use an explicit `goals` array (1–20 distinct positive issue numbers). Follow
the returned `submission` for the next page (`cursor` becomes `after`); `remaining` counts unexamined open
index entries, not necessarily v1 goals. `discover` and `status` are read-only.
Each member reports `migrated`, `already_current`, `closed`, `custom_migration`,
or `blocked`, with its receipt or diagnostic and normal next steps. Retries use
remote immutable source/target/policy records; no local batch manifest or approval
is needed. A failed member does not roll back others. Existing custom migration
entries retain their declared contracts and are not replaced automatically.
A pending transaction with changed policy requires resolving that mismatch
before its old target can publish.

Renew the same live owner; expiry permits no takeover. Recover only
with observed stopped evidence. Integration cannot mint Results.
