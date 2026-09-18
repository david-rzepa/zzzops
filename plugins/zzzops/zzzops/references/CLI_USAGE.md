# Using the ZzzOps CLI

Run the package-local [`zzzops.py`](../zzzops.py), never a global command. Start with
the skill's semantic `--intent`. Continue with `workflow --intent INTENT` and only the
returned `--goal`, `--runtime`, or `--input` JSON-file arguments that apply.

Obey `next_steps`. Read the returned `instruction`, `policy.path`, and evidence fields.
The policy file contains agent instructions, not CLI configuration. Pass it to the assigned worker; if missing, request a fresh
checkpoint. For mutating
phase work, send `start`, bind the actual executor with `bind` when delegated, then
complete `submission` under its lease using `command`. Preserve the exact assignment,
authority, and evidence contract; invent no arguments, operations, models, phase
order, or private handlers.

Invoke the workflow again after each step. Only root resolves blockers or asks the
human. Human approval is a separate step, never implied by execution or review.
