---
name: send-zzzops-feedback
description: ZzzOps v0.0.0-dev — development plugin. Preview and send user feedback, privacy-safe execution reports, or one selected timing diagnostic to the public ZzzOps repository. Requires exact-payload confirmation before the external write.
---

# Send ZzzOps Feedback

Use the returned readiness evidence only to decide whether this workflow can proceed; detailed inputs are local reports and explicit feedback, never goal bodies/history.

1. Keep user text separate from execution reports. Before public preview, reject credentials, payment cards, health data, government IDs, and other restricted data.
2. Inspect every archived report exposed by the returned evidence. Reports contain only constrained machinery codes, numeric impact, and validated ZzzOps build provenance; legacy schema-v2 provenance is explicitly unknown. Malformed or unknown content is a safety failure, so stop without submitting or deleting anything.
   If the user asked to share timing, inspect the available diagnostics in that evidence and include exactly one user-selected diagnostic ID. Use only its observed agent, platform, and Python enum values; use `unknown` instead of inferring. Timing remains a separate fixed schema and is never selected automatically.
3. Supply feedback only through the returned input contract, backed by stdin or a securely created temporary UTF-8 file when requested; never put sensitive text directly in a command-line argument. By default select all valid archived reports unless the user selected a subset. Add the exact diagnostic selection and runtime values only when requested.
4. Show the exact target, title, labels, and body returned in the preview, plus its digest, including cause/build-specific accounts, immutable report JSON, and any selected fixed timing payload. State that `david-rzepa/zzzops` is public and ask the user to confirm that exact payload. The `zzzops-feedback` label keeps it outside ordinary execution unless a user approves the feedback queue for that session. Do not submit on an inferred, stale, or general approval.
5. After confirmation, submit the unchanged prompt bytes, report IDs, diagnostic ID, runtime enums, and confirmed digest using the exact returned input contract and `command`. The workflow must recompute the payload, create the GitHub issue only if the digest still matches, validate the returned issue URL, and then delete only the submitted reports and selected diagnostic.
6. Return the created issue link. On cancellation, drift, provider failure, or unexpected output, report that nothing was deleted and preserve the reports and diagnostic for retry.

This skill makes one external write only after exact confirmation. It never edits project source, goals, policy, Git state, or unrelated GitHub records.
