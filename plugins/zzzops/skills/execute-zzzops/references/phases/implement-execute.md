# Implement Execute

Run this prompt only when the public workflow returns this exact step. Implement the reviewed plan and test design. Run the prescribed checks and capture immutable verification evidence.

Use small exploratory probes while implementing. Submit the full required checks once as `workspace_checks` with `verification_expectation: "passed"`; the CLI runs them and returns the immutable proof. Failed checks retain the lease for a corrected new request. Do not pre-run the same complete suite. See [verification and recovery](../../../../zzzops/references/VERIFICATION.md).

Use the returned model-plus-effort pair and assignment exactly. Submit the returned `start` request to acquire the phase before doing work. When delegated, launch or resume only the selected executor and submit the returned `bind` request with its actual identity. Work only from the returned input envelope and upstream evidence. Submit the requested immutable artifact under the acquired lease by completing the returned `submission` and using its `command`. If required evidence is unavailable, submit the documented blocker; do not invent it or invoke another ZzzOps command. Release or recover a lease only as the workflow directs.
