---
name: send-zzzops-feedback
description: ZzzOps v0.0.0-dev — development plugin. Preview and send user feedback, privacy-safe execution reports, or one selected timing diagnostic to the public ZzzOps repository. Requires exact-payload confirmation before the external write.
---

# Send ZzzOps Feedback

Read `../../rules/COMMUNICATION.md` for user-facing messages.

Run `../../rules/INITIALIZATION.md`, then read `../../rules/FEEDBACK.md`. Use the resolved Python interpreter for all CLI calls.

Use checkpoint only for readiness; detailed inputs are local reports and explicit feedback, never goal bodies/history.

1. Keep user text separate from execution reports. Before public preview, reject credentials, payment cards, health data, government IDs, and other restricted data.
2. Run `report list` and inspect every valid archived report. Reports contain only constrained machinery codes, numeric impact, and validated ZzzOps build provenance; legacy schema-v2 provenance is explicitly unknown. Malformed or unknown content is a safety failure, so stop without submitting or deleting anything.
   If the user asked to share timing, also run `diagnostics list`. Include exactly one user-selected diagnostic ID and pass only observed `--diagnostic-agent`, `--diagnostic-platform`, and `--diagnostic-python` enum values; use `unknown` instead of inferring. Timing remains a separate fixed schema and is never selected automatically.
3. Pass the feedback through stdin or a securely created temporary UTF-8 file to `feedback prepare`; never put it directly in a command-line argument. By default include all archived reports unless the user selected a subset. Add the exact diagnostic selection and runtime flags only when requested.
4. Show the exact target, title, labels, and body returned by `feedback prepare`, including cause/build-specific accounts, immutable report JSON, and any selected fixed timing payload. State that `david-rzepa/zzzops` is public and ask the user to confirm that exact payload. The `zzzops-feedback` label keeps it outside ordinary execution unless a user approves the feedback queue for that session. Do not submit on an inferred, stale, or general approval.
5. After confirmation, pass the same prompt bytes, report IDs, diagnostic ID, and runtime enums to `feedback submit --confirm DIGEST`. The deterministic CLI recomputes the payload, creates the GitHub issue only if the digest still matches, validates the returned issue URL, and then deletes only the submitted reports and selected diagnostic.
6. Return the created issue link. On cancellation, drift, provider failure, or unexpected output, report that nothing was deleted and preserve the reports and diagnostic for retry.

This skill makes one external write only after exact confirmation. It never edits project source, goals, policy, Git state, or unrelated GitHub records.
