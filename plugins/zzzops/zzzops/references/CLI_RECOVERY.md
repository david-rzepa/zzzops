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

### Historical stopped workspace draft

When an older CLI committed an observed-stop `recover` transaction but removed
the lease without publishing a workspace-draft receipt, execute may return
`kind: recover_draft`. It is returned only when the host can authenticate one
original acquisition receipt, the committed recovery result, the removed lease,
fresh current allocation/reviewer/root authority, and an exact current delta
limited to the task's owned paths.

Copy the returned `submission` and replace only `recovery_request` with the
exact original recover request. Add a new unique `request_id`. The operation is
`preserve_historical_draft`; all returned hashes, Refs, workspace identity, delta
and qualified node must remain exact.

The operation preserves the bytes as unaccepted work and returns a new
workspace-draft Ref. Reinvoke execute and acquire the current task normally.
The draft records a continuity transition under the stopped task's fresh
current allocation and approvals. A later task may consume the exact resulting
snapshot as its raw baseline, including when it only reads the recovered paths;
its lease uses its own current semantic inputs and write scope. Normal
verification, independent review, workspace gates, and publication gates still
apply. The operation never revives the old lease or approval and never creates
a Result.

### Read-only historical semantic identity

A read-only acquisition can reuse a connected historical semantic workspace
identity. Its lease separately records `acquisition.read_files`, the exact raw
workspace observed when the lease starts. Live validation compares current raw
bytes with `read_files`, while the semantic `files` identity remains available
for legitimate proof-chain reuse. Any post-acquisition raw drift still rejects
the submission, and neither pin grants write authority.

### Historical applicability assessment

When an unresolved historical admission blocks its target and the current graph
has no route that can run before that target, execute returns a `repair` step
with diagnostic `Finding applicability unresolved`. Its `obligations` carry the
exact immutable admission, finding and target, and its `submission` contains the
complete append-only target graph. Save that submission as JSON and run the
returned public command, or invoke the installed CLI with `--intent execute`, the
affected `--goal`, current `--runtime`, and `--input` pointing to that JSON file.
This `graph_prepare` operation persists no adoption and grants no authority.

The returned proposal must be produced and independently reviewed in a dedicated
review goal. A fresh review goal can first use `graph_review_bootstrap` with
explicit human approval; then its root proposal task and independent review task
bind the exact manifest. Submit the returned `graph_adopt` continuation to the
affected goal only after the user approves that exact reviewed proposal. Adoption
recomputes the source, target, policy and Result-impact manifest, rejects stale or
tampered reviews, and is idempotent when the same transaction is retried.

Bind the returned historical entry through the host-authenticated input producer
`{"slot":"obligations"}` at path `["<finding id>"]`. Its content contains only
the exact `admission`, `finding`, `target`, and current `applicability`; this is a
read route, not authority. Bind corrected subjects and reviewer output through
their ordinary current node producers.

The appended root node emits `applicability_assessment` with exactly:
`admission`, `finding`, nonempty `subjects`, `reviewer_result`, `authority`,
`applicability`, and `rationale`. It must bind the exact admission and finding,
each current corrected subject, and an output from the current independent
reviewer Result. `authority` must be a current authenticated root Result.
`applicability` is `applicable` or `not_applicable`; uncertainty remains the
original unresolved admission and must not produce an assessment. The evaluator
retains the original source, finding and admission, records the assessment as a
separate immutable output, and applies normal correction and resolution gates.
Classification alone never resolves the finding or authorizes implementation.

Do not use graph adoption for a stale workspace or an unavailable model. A
workspace invalidation requires normal stopped-owner/workspace recovery. A model
or reasoning-effort blocker requires an available policy-allowed capability.
Installation validation confirms package integrity; it does not repair a goal
whose reviewed graph lacks the required route.

Use this flow when a goal has a missing graph route or capability.

A current independent review with `decision: changes_requested` must have a
typed correction route before downstream work can proceed. If an older graph
lacks that route, execute returns `Rejected review lacks correction route` and a
concrete append-only `graph_prepare` submission. The proposed graph adds root
interpretation and admission, reacquires only the exact rejected producer after
an applicable admission, requires a fresh independent review, retains every
admitted finding, and independently resolves each retained finding. Review and
adopt that proposal through the same bootstrap flow above; do not bypass the
rejection by changing the downstream approval input.

### Stale workspace authorization

Workspace-authorization producer Results include a host-authenticated
`__policy` input. Legacy Results without that input, and Results bound to a
different policy, become stale through ordinary input identity. Execute then
returns the independent authorization producer followed by its root approval as
normal `execute` tasks. Acquire and submit them normally with the unchanged
manifest and task identities and the exact current policy digest. Old Results
remain immutable; downstream inputs become stale when the new authorization
outputs are published. No special rewrite or authorization bypass exists.

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

## Delegation above root capability

The reviewed `model_routing.configuration.allow_above_root_delegation` boolean
permits worker tasks to select a stronger reviewed, available model/effort pair
while the actual root remains unchanged. It defaults to false, including in
older policies where the field is absent. Change it through policy review; a
session override alone cannot override a denying project policy. The same
eligibility checks apply to preview and acquisition. Root-only tasks retain
their declared capability and actual-root requirement.

Capability is the pair's reviewed tier, not its name, price or an inferred
reasoning-effort ordering. Pairs assigned the same tier remain equivalent for
capability selection; enabling delegation does not resolve that separate
policy-mapping limitation. Existing leases retain their exact selected pair.
