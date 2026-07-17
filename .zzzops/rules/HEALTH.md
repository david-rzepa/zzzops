# User health hooks

Health is user-level, opt-in, nonblocking, and privacy-bounded. Never infer enablement, bypass a sandbox, scrape transcripts/session files, or call receipt time “sent time.” The CLI stores preferences per user and only derived timestamps/counters in machine-local state; inaccessible storage returns `storage_unavailable` with no fallback.

After initialization, each non-install workflow runs `python .agents/zzzops.py --repo . health check` at entry and before its final request/report. `$execute-zzzops` also checks after an actual user response and at natural long-run checkpoints (about hourly, never by blocking the main thread). Emit at most the one returned `decision.message` when `nudge:true`; otherwise say nothing. A nudge never blocks authorized work or overrides the user.

Record activity only when evidence exists:

- Harness supplies an ISO send timestamp: `health record --activity-timestamp <ISO> --precision exact_message`.
- No send timestamp, but user enabled approximate receipt time: use the observed current ISO time with `--precision observed_receipt` and retain that label.
- Otherwise use `health check` (`current_only`): schedule rules may run, but session/burst duration must not be inferred.

Codex and Claude Code have no portable guaranteed send-timestamp surface. Treat exact timing as unavailable unless the active harness explicitly provides it. Missing IANA timezone data, user/machine storage denial, invalid config, or disabled health are honest no-ops; report a capability problem only when it helps the user fix requested behavior.
