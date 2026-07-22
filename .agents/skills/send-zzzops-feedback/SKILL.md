---
name: send-zzzops-feedback
description: Preview and send user feedback plus privacy-safe archived ZzzOps execution reports to the public ZzzOps repository. Requires exact-payload confirmation before the external write.
---

# Send ZzzOps Feedback

Run `.zzzops/rules/INITIALIZATION.md`, then read `.zzzops/rules/FEEDBACK.md`. Use the resolved Python interpreter for all CLI calls.

1. Treat the user's text after the invocation as user-authored feedback. It may contain project information because the user controls it, but never merge that text into an execution report.
2. Run `report list` and inspect every valid archived report. Reports contain only constrained machinery codes, numeric impact, and validated ZzzOps build provenance; legacy schema-v2 provenance is explicitly unknown. Malformed or unknown content is a safety failure, so stop without submitting or deleting anything.
3. Pass the feedback through stdin or a securely created temporary UTF-8 file to `feedback prepare`; never put it directly in a command-line argument. By default include all archived reports unless the user selected a subset.
4. Show the exact target, title, labels, and body returned by `feedback prepare`, including cause/build-specific natural-language accounts and the collapsed immutable JSON appendix. State that `david-rzepa/zzzops` is public and ask the user to confirm that exact payload. The `zzzops-feedback` label keeps it outside ordinary execution unless a user approves the feedback queue for that session. Do not submit on an inferred, stale, or general approval.
5. After confirmation, pass the same prompt bytes and selected report IDs to `feedback submit --confirm DIGEST`. The deterministic CLI recomputes the payload, creates the GitHub issue only if the digest still matches, validates the returned issue URL, and then deletes the submitted reports.
6. Return the created issue link. On cancellation, drift, provider failure, or unexpected output, report that nothing was deleted and preserve the reports for retry.

This skill makes one external write only after exact confirmation. It never edits project source, goals, policy, Git state, or unrelated GitHub records.
