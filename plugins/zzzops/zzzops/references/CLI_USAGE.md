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
Old versions require reviewed conversion. Historical reads never migrate or reopen. Renew the same live owner; expiry permits no takeover. Recover only
with observed stopped evidence. Integration cannot mint Results.
