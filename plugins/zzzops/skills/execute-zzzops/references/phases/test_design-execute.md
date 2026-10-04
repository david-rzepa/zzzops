# Test Design Execute

Run this prompt only when the public workflow returns this exact step. Write failing behavioural tests for every acceptance criterion, or record a specific justified exclusion. Capture the baseline-failure artifact.

Use small exploratory probes to design the test. Submit the required baseline commands once as `workspace_checks` with `verification_expectation: "observed"`; the CLI runs them and returns the immutable proof, including expected red exits. Do not pre-run the complete suite merely to predict this result. See [verification and recovery](../../../../zzzops/references/VERIFICATION.md).

Use the returned model-plus-effort pair and assignment exactly. Submit the returned `start` request to acquire the phase before doing work. When delegated, launch or resume only the selected executor and submit the returned `bind` request with its actual identity. Work only from the returned input envelope and upstream evidence. Submit the requested immutable artifact under the acquired lease by completing the returned `submission` and using its `command`. If required evidence is unavailable, submit the documented blocker; do not invent it or invoke another ZzzOps command. Release or recover a lease only as the workflow directs.
