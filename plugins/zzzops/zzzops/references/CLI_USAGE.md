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

Execution migrates supported open v1 goals automatically, preserving history
without granting authority. Preview/historical reads never migrate or reopen.
For bulk/blocked conversion, read [schema migration](SCHEMA_MIGRATION.md).

An unresolved migrated blocker is returned as `kind: goal_blocker_resolution`
with a root-only `resolve_goal_blocker` submission. Supply the actual root actor,
the returned original context and blocker hashes, a rationale, an explicit root
resolution basis, and authentic current same-goal Result/output Refs. A
`human-action` blocker also requires the approving user and exact conversational
attribution. This is root judgement: approval text is never matched
automatically. Resolution appends an immutable journal event and preserves the
original migration context, dependencies, metadata, comments and phase Results.
It does not acquire work or satisfy review, workspace, CI, merge or release
gates. Preview exposes the contract without writing.

## Working inputs

Capture, execute, migration, and policy-review checkpoints return a `working_input` object containing a stable ignored path and runnable commands. Ambiguous provider dispatches return an exact `working-input reconcile` command; active references return `working-input status`. See [WORKING_INPUTS.md](WORKING_INPUTS.md) for lifecycle and recovery rules.
