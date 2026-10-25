# ZzzOps CLI

Run package-local [`zzzops.py`](../zzzops.py), never globally. Use the skill's
semantic `--intent` with `workflow --intent INTENT`; copy returned `--goal`, runtime and input.

Workflow checkpoints and reads have a 90-second provider budget by default.
Use `workflow --timeout SECONDS` for a slower repository; the override applies
to the provider deadline for that invocation and must be
a positive finite number and applies only to that invocation. Renewal keeps its
separate work and cleanup budgets.

Stdout is compact; `--response full` preserves full JSON. For minimal inputs and selective reads, use [response references](CLI_BOUNDARY.md).

Follow `next_steps`, `instruction`, policy.path and evidence fields. Read policy;
send `start` and `bind` with receipt and actual executor. Send `submission`
using `command`, acquired node, lease and actor; renew/submit need no policy receipt.
For authoritative checks and retry rules, follow [verification](VERIFICATION.md); submit suites once through `workspace_checks`.

`submit` returns `submitted` and actionable next steps; no extra checkpoint.
Retry identical request ID/payload. Returned steps grant no authority.
Only root coordinates blockers/approval. Human approval is a separate step.
Respect allocations and publication gates; infer no operations or models.
Renew live owners; expiry permits no takeover. Recover only observed stopped owners.
For monitoring, replay, reconciliation or test corrections, read [recovery](CLI_RECOVERY.md).

Reviewed policy enables [release planning](RELEASES.md).

## Reviewed policy-DAG cutover

When a goal has accepted Results under a different reviewed policy graph,
checkpoint returns `policy_dag_cutover` and pauses affected execution. Submit
the returned `policy_dag_cutover_prepare` contract with one unique mapping for
each retained Result/output. The host derives input, output, scope, role,
independence, and approval equivalence from both exact node contracts; caller
assertions cannot make changed contracts equivalent. Resolve every old-policy
lease before preparing the transition.

An actor independent of the coordinating root submits the exact returned
`policy_dag_cutover_review` contract. Only an approved review returns
`policy_dag_cutover_apply`. Apply uses the fresh post-review goal revision and
the exact proposal/review references. Exact retries first observe the durable
receipt, so an uncertain provider response cannot create a second current
graph. A rollback is another independently reviewed reverse cutover with a new
receipt; never rewrite either graph, its Results, or the forward receipt.

Replacement Results similarly name the immediately preceding Result and the
goal revision observed at acquisition. A competing or disconnected successor
is rejected instead of being selected by append time, branch name, or local
worktree state.

Execution migrates supported open v1 goals automatically, preserving history
without granting authority. Preview/historical reads never migrate or reopen.
For bulk/blocked conversion, read [schema migration](SCHEMA_MIGRATION.md).

For `resolve_goal_blocker`, follow its contract and
[recovery guidance](CLI_RECOVERY.md#migrated-blocker-resolution-recovery).

## Working inputs

Capture, execute, migration, and policy-review checkpoints return a `working_input` object containing a stable ignored path and runnable commands. Ambiguous provider dispatches return an exact `working-input reconcile` command; active references return `working-input status`. See [WORKING_INPUTS.md](WORKING_INPUTS.md) for lifecycle and recovery rules.
