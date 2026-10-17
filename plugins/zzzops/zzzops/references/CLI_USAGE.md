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

Execution migrates supported open v1 goals automatically, preserving history
without granting authority. Preview/historical reads never migrate or reopen.
For bulk/blocked conversion, read [schema migration](SCHEMA_MIGRATION.md).

## Working inputs

Capture, execute, migration, and policy-review checkpoints return a `working_input` object containing a stable ignored path and runnable commands. Ambiguous provider dispatches return an exact `working-input reconcile` command; active references return `working-input status`. See [WORKING_INPUTS.md](WORKING_INPUTS.md) for lifecycle and recovery rules.
