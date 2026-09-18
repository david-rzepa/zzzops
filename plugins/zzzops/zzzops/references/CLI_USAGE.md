# Using the ZzzOps CLI

Run package-local [`zzzops.py`](../zzzops.py), never a global command. Start with the
skill's semantic `--intent`; continue with `workflow --intent INTENT` and
returned `--goal`, `--runtime`, or `--input` arguments.

Obey `next_steps`. Read `instruction`, `policy.path`, and evidence fields.
Unchanged policy reuses its path and receipt. Copy its `policy_receipt` into
`start`. Delegated workers read the file and supply its receipt for `bind` before
working. If missing, request a fresh checkpoint. Renewals/submissions need no receipt.

Before work, send `start`, bind the actual executor, then complete `submission`
under its lease using `command`. Preserve assignments, authority, and evidence;
invent no arguments, operations, models, phase order, or private handlers.

Invoke again after each step. Only root resolves blockers or asks the human.
Human approval is a separate step, never implied by execution or review.
