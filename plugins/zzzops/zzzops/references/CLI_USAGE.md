# ZzzOps CLI

Run package-local [`zzzops.py`](../zzzops.py), never globally. Use the skill's
semantic `--intent` with `workflow --intent INTENT`; copy returned `--goal`, runtime and input.

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
