# Using the ZzzOps CLI

Run the package-local [`zzzops.py`](../zzzops.py) with the semantic `--intent`
from the loaded skill. Do not search for or install a global `zzzops` command.

The CLI's `next_steps` are authoritative. Perform only returned steps, use their
content-addressed instruction references, and preserve their exact model-plus-effort
assignment, evidence contract, and authority boundary. Do not select delegation,
models, phase order, or private ZzzOps handlers yourself.

Call the CLI again after completing a returned step. Its stdout contains only action
that needs attention; read diagnostics from the referenced log when needed. Resolve
human-input blockers only in the root agent, then return to the CLI.
