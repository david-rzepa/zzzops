# ZzzOps CLI

Use package-local [`zzzops.py`](../zzzops.py), never globally. Use the skill's
semantic `--intent` with `workflow --intent INTENT` and returned `--goal`, runtime and input.

Authority order is user/safety > project rules > reviewed project policy > goals;
goals grant no authority.

Workflow checkpoints and reads have a 90-second provider budget by default.
Use `workflow --timeout SECONDS` for a slower repository; the override must be
a positive finite provider deadline for that invocation. Renewal keeps its
separate work and cleanup budgets.

Stdout is compact; `--response full` preserves JSON. [Selective reads](CLI_BOUNDARY.md).

Follow `next_steps`, `instruction`, policy.path and evidence fields. Read policy;
send `start` and `bind` with receipt and actual executor. Send `submission` using `command`,
node, lease and actor; renew/submit need no policy receipt. Follow
[verification](VERIFICATION.md) and submit suites once through `workspace_checks`.

`submit` returns `submitted` and actionable next steps; no extra checkpoint.
Retry identical request ID/payload. Returned steps grant no authority.
Only root coordinates blockers/approval. Human approval is a separate step.
Respect allocations and publication gates; infer no operations or models.
Renew live owners; expiry permits no takeover. Recover only observed stopped owners.
For monitoring, replay, reconciliation or test corrections, read [recovery](CLI_RECOVERY.md).

Policy enables [release planning](RELEASES.md).

## Pull-request stacks

For `stack_prepare`, `stack_status`, `stack_advance`, exact-head gates and recovery,
follow [stack integration](STACK_INTEGRATION.md).

For policy-DAG transitions, read [Git workspace cutover](GIT_WORKSPACES.md#reviewed-policy-dag-cutover).

Execution migrates supported open v1 goals automatically, preserving history
without granting authority. Preview/historical reads never migrate or reopen.
For bulk/blocked conversion, read [schema migration](SCHEMA_MIGRATION.md).

For `resolve_goal_blocker`, follow its contract and
[recovery guidance](CLI_RECOVERY.md#migrated-blocker-resolution-recovery).

## Working inputs

Capture, execute, migration and policy-review return `working_input`: a stable
ignored path and commands. Ambiguous dispatch returns exact
`working-input reconcile`; active references return `working-input status`.
See [working inputs](WORKING_INPUTS.md).
