# ZzzOps CLI

Run package-local [`zzzops.py`](../zzzops.py), never globally. Use the skill's semantic `--intent` with `workflow --intent INTENT`; copy returned `--goal`,
runtime and input.

Follow `next_steps`, `instruction`, policy.path and evidence fields. Read policy;
then send `start` and `bind` with receipt and actual executor.
Send `submission` using `command` when supplied, with acquired node, lease and actor.
No policy receipt for renewals/submissions. Successful `submit` returns the next
required tasks and review, approval or publication boundaries directly in
`next_steps`; `submitted` acknowledges the exact goal, node and Result reference.
Follow that continuation without a mechanical checkpoint. Explicit checkpoints
remain available for inspection and recovery.

The acknowledgement and continuation commit with the outputs, Result and lease
release in one transaction. Replay the identical request ID and payload to
recover the original continuation; changing a request under the same ID is
rejected. After uncertain publication or partial upload, retry that exact request.
Pending artifacts grant no authority. Reconciliation's `expected_digest` binds
the original confirmed transaction envelope, including on later replay; obtain a
fresh checkpoint if that reconciliation precondition has since changed. Local
heartbeat cleanup repairs are operational annotations, separate from the durable
continuation. Returned tasks still require normal acquisition and current policy,
input, independence, capacity and workspace checks. Returning a continuation does
not acquire work, approve, integrate or close a goal.

Infer no operations, models, task order or authority. Follow finite resource
allocations and publication authorization. Only root coordinates blockers
and human approval. Human approval is a separate step; execution/review implies
no approval. Reinvoke.
Execution automatically migrates supported open v1 goals to v2. Running this
lossless schema migration needs no conversion review or human approval. It
preserves human text/history, relationships and unresolved obligations, creates
no product Results, and grants no workspace or publication authority. Historical
reads and preview never migrate or reopen.

For bulk migration or a blocked conversion, read [schema migration guidance](SCHEMA_MIGRATION.md) and follow the returned remediation.

Renew the same live owner; expiry permits no takeover. Recover only with
observed-stop evidence and the exact actor. Owned drafts preserve continuity,
not acceptance; same-task reacquisition retains verification and review gates.
Accepted-test defects use the returned interpretation/admission route, bounded
test ownership and fresh independent review. Existing graphs require reviewed
graph adoption. Integration cannot mint Results.
