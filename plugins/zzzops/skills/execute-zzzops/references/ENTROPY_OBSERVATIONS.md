# Incidental entropy observations

This is an evidence inbox, not an audit, backlog, or completion requirement. Use it
only when ordinary execution already exposes concrete repository decay. Never pause
the current goal to search for observations, investigate adjacent code, or design
future work.

Record at most one bounded fact at a time:

```text
<python> <zzzops-cli> --repo . entropy observe \
  --category documentation|tests|code_quality_non_behavioral \
  --path REPOSITORY/PATH --evidence "ONE OBSERVED FACT" \
  --goal N --revision R
```

Use one to four normalized repository-relative paths and a single-line evidence
statement of at most 280 characters. Do not include secrets, raw sensitive data,
speculative solutions, acceptance criteria, priority, or a designed goal. Record
only decay distinct from the current goal: stale or contradictory context, repeated
patterns, an obsolete/prose-only guardrail, or verification drift. In-scope defects
remain part of the current goal; test-discovered out-of-scope bugs follow PROJECT
test-bug policy instead.

The ignored common-Git-dir inbox is shared by worktrees. Each fact is an atomically
created, fingerprint-named file, so concurrent duplicates collapse without a global
counter or lock. Recording grants no goal-write authority and needs no user
notification. `$suggest-zzzops-work` owns later validation, dismissal, and capture.
