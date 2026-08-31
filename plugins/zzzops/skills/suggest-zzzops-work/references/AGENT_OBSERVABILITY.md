# Agent observability suggestions

Use this category only when a coding agent lacks bounded, queryable evidence about a running or failed system. The beneficiary is faster, more reliable diagnosis, verification, or performance investigation without unscheduled user help—not more tooling.

## Candidate contract

Require each candidate to name:

- the diagnostic question current code, tests, and signals cannot answer;
- the costly fallback or user-dependent reproduction and who benefits;
- the smallest proposed signal and smallest falsifiable probe;
- how autonomous iteration improves; and
- lifecycle boundaries: how to start/request it, artifact location, size/retention and cleanup, supported platforms, failure behavior, and proof that evidence is current rather than stale.

Choose the smallest repository-native mechanism. Options include a project-scoped read-only MCP server or debug adapter, structured filterable diagnostic logging, trace capture, CPU/memory profiling, bounded heap/thread/core-style dumps, deterministic state snapshots, health/introspection endpoints, or reusable reproduction capture. Never prefer MCP when a simpler native probe answers the question.

Do not suggest this category for a pure test gap, production monitoring feature, speculative optimization, generic developer tooling, logging churn, or a repository with adequate diagnostics. No demonstrated beneficiary or blocked question means no suggestion.

## Safety boundary

Reject uncontrolled external telemetry, credential or secret capture, raw sensitive-data retention, production mutation, unrestricted command execution, and an MCP surface broader than the project need. Constrain accepted proposals to local/on-demand operation, read-only interfaces, redaction, explicit size/retention limits, ignored disposable artifacts, and applicable engineering-rigor escalation. A signal that can be stale must expose freshness or fail closed.

## Focused cases

- An opaque service whose failure mode is visible only to a user may justify a read-only debug adapter or narrow MCP query that returns current component state; an unrestricted shell MCP does not.
- Repeated requests for ad-hoc console output may justify structured, filterable, redacted diagnostic logs with a bounded local lifecycle; blanket logging does not.
- An evidenced latency or memory question may justify an on-demand profile or bounded dump with cleanup and platform behavior; “make it faster” does not.
- An otherwise identical repository with an existing current, queryable, safe signal receives credit and no suggestion.
