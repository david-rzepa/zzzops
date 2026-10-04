# Submission, recovery and correction

The acknowledgement and continuation commit with the outputs, Result and lease
release in one transaction. Replay the identical request ID and payload to
recover the original continuation; changing a request under the same ID is
rejected. After uncertain publication or partial upload, retry that exact request.
Pending artifacts grant no authority. Reconciliation's `expected_digest` binds
the original confirmed transaction envelope, including on later replay; obtain a
fresh checkpoint if that reconciliation precondition has since changed. Local
heartbeat cleanup repairs are operational annotations, separate from the durable
continuation. Returned tasks still require normal acquisition and current policy,
input, independence, capacity and workspace checks. Returning a continuation does
not acquire work, approve, integrate or close a goal.


Renew the same live owner; expiry permits no takeover. Recover only with
observed-stop evidence and the exact actor. Owned drafts preserve continuity,
not acceptance; same-task reacquisition retains verification and review gates.
Accepted-test defects use the returned interpretation/admission route, bounded
test ownership and fresh independent review. Existing graphs require reviewed
graph adoption. Integration cannot mint Results.

### Automatic local lease monitoring

Generic start (for a root task) or bind (for a delegated task) registers local
monitoring after confirmed publication when the runtime file includes
`heartbeat.probes`, a map from exact bound worker identities to local argument
lists. A probe must contain that worker identity as an exact argument; exit 0
means active, 1 means observed stopped, and other exits/timeouts mean unknown.
Use a real harness liveness capability; the CLI never invents a worker PID.
Commands remain local and are not persisted in goal evidence.

`heartbeat.grace_seconds` defaults to 120 (range 0–300), and
`heartbeat.interval_seconds` defaults to 120 (range greater than 0 through 120).
The existing temporary per-root coordinator waits through grace without probe
or renewal calls, then renews the exact qualified node before lease expiry.
It exits when no leases remain. Completing a short phase needs no additional
public heartbeat invocation. Exact acquisition replay repairs local registration
without extending an already registered grace deadline. Completion/review submit
and stopped-worker recovery remove tracking for the exact completed token.

Without a runtime file and supported worker probe, ordinary phases remain
available and `perform.monitoring` explains the limitation. Long work then needs
actual external worker observation and exact public renewal; automatic renewal
is unavailable. Local setup/transport failure does not release durable ownership,
and lease expiry never establishes that the worker stopped. After interruption,
replay the exact acquisition to restore monitoring or use observed-stopped
recovery; do not start a duplicate worker. Monitoring annotations are operational
and separate from the durable result acknowledgement.

Linked worktrees share the local registry through Git's common directory, so
completion in the coordinator checkout stops the exact originating worker token.
Each tracked lease keeps its originating checkout and runtime for probes and
renewals. Local registration/removal lock waits are bounded; a busy local lock
returns operational monitoring/cleanup guidance without undoing a committed
provider result or granting recovery authority.
