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

Empty legacy metadata migrates normally. Risk categories are preserved with their
current policy-derived rigor; executor capability floors can rise but never fall.
Nonexclusive resource declarations remain planning information and never grant
file ownership. Policy-exclusive resources (including branch reservations) need
a compatible shared ownership protocol and remain blocked with targeted guidance.
Expired ownership still requires observed-stop recovery.

If a member is blocked, follow its `remediation.fields` and `remediation.steps`,
then submit its exact `remediation.retry` object through `workflow --intent execute
--runtime <runtime.json> --input <request.json>`. This is a targeted retry, not a
new conversion approval. For example:

```json
{"operation":"migration_batch","action":"migrate","goals":[123]}
```

Before manual repair, save the exact issue body and comments. Resolve the named
field against issue history and current policy: reconcile unknown risk tags or
explicit rigor overrides, restore the actual revision, align priority labels,
or recover the recorded stopped owner. Keep parent/dependency/blocker constraints
and human text. Existing custom conversions must resume their own contract;
retired policy entries need explicit reconciliation. Prepared transactions need
their original exact artifacts and policy. Do not erase metadata merely to clear
a diagnostic. Successful conversions retain the complete original issue in the
receipt's immutable `source` Ref, readable using the public `read` operation.
There is no destructive reset switch; unsupported semantics remain explicit.

Renew the same live owner; expiry permits no takeover. Recover only
with observed stopped evidence. Integration cannot mint Results.
