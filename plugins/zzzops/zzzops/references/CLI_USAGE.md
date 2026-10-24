# ZzzOps CLI

Use package-local [`zzzops.py`](../zzzops.py), never globally. Use the skill's
semantic `--intent` with `workflow --intent INTENT` and returned `--goal`, runtime and input.

Checkpoints/reads default to a 90-second provider budget. Set positive finite
`workflow --timeout SECONDS` for one invocation; renewal keeps separate work and
cleanup budgets.

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

`stack_prepare` authenticates pages of at most 50 PRs and seals topology before effects.
`stack_status` pages progress; `stack_advance` performs one authorized transition.
Replay uncertainty unchanged. See [stack integration](STACK_INTEGRATION.md).

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
