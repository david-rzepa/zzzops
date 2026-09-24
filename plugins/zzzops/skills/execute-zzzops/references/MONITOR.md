# Monitor active work

An `await_worker` step is not convergence and never justifies ending execution. Preserve its goal, phase, bound worker, lease expiry, last durable operation, heartbeat state, and recheck command. The heartbeat is primary liveness evidence: `active` means wait and re-inspect the same handle after its interval; `stopped` means inspect results before recovery; `unknown` means diagnose the real worker/process and backend lease.

For Codex workers, use `list_agents` to observe real status and `wait_agent` against that handle; after a wait timeout, list it again before any recovery. Use `interrupt_agent` only as an explicit intervention, not as a probe. A stale lease file, old checkpoint, or repeated transition fingerprint is not liveness evidence. On one unchanged fingerprint, inspect the backend goal, lease, worker status, and process/result handle, then follow the returned route. Do not duplicate a worker, fabricate a shell probe, or finalise while a verified handle remains live.

These are the official OpenAI multi-agent coordination actions: <https://developers.openai.com/api/docs/guides/responses-multi-agent>.
