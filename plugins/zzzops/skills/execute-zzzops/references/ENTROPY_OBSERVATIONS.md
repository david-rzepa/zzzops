# Incidental entropy observations

This is an evidence inbox, not an audit or backlog. When ordinary execution already
exposes a concrete, bounded, out-of-scope decay fact, record it; this is required.
Never pause the current goal to search for observations, investigate adjacent code,
or design future work. A persistence failure becomes actionable ZzzOps machinery
continuation at the next safe boundary; it never expands the current goal.

Record at most one bounded fact at a time:

```text
<python> <zzzops-cli> --repo . entropy observe \
  --category documentation|tests|code_quality_non_behavioral|agent_observability \
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
notification. `$review-zzzops-entropy` owns explicit recent/full review and always
validates policy-eligible inbox leads. `$suggest-zzzops-work` continues to validate
the same eligible leads during ordinary suggestion/refill and supplies the ranking,
category, cap, and capture authority reused by entropy review. Neither workflow gains
goal-write authority from the inbox itself.

## Exact review events

Immediately after a canonical mutation and readback proves one unique new goal
revision/digest in a qualifying state, write a bounded temporary JSON request and run:

```text
<python> <zzzops-cli> --repo . entropy review mark --input FILE
```

Delete only that request after the command. Supply exactly `schema_version`,
`repository`, `goal`, `revision`, `goal_digest`, `status`, `kind`, `pr`, `base_oid`,
`head_oid`, and `merge_oid`, all from observed canonical/provider evidence:

- `verified_checkpoint`: pending-review `blocked` goal with PR, immediate base, exact
  head, and null merge;
- `integrated_change`: the new persisted goal revision after target ancestry proves
  the exact PR head integrated, with PR/base/head/merge; or
- `completed_goal`: a `done` goal without a newly integrated PR at that revision;
  use null PR/object IDs when none are actually available.

Persist a new goal revision before marking each later qualifying transition. Never
mark two kinds at the same latest revision, reconstruct missing identifiers, or mark
claims, reservations, schema repair, blocker administration, or the creation or
administrative transition of newly suggested/refill goals. Their later qualifying
checkpoint, integration, or completion is marked normally. Marking is idempotent. Failure or ambiguous evidence leaves an actionable
continuation and never silently skips review coverage.
