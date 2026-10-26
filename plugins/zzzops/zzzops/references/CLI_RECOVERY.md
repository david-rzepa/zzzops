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
test ownership and fresh independent review. The fixed policy workflow supplies correction routes; findings update phase
data without changing a goal graph. Integration cannot mint Results.

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

### Stale committed workspace draft

After accepted tests or other declared inputs change, an already committed
stopped draft may bind obsolete inputs. With current independent and root
workspace approvals, unchanged material authority, no unrecovered owners, and
an exact clean Git checkout, execute returns `kind: retire_draft`.

Copy its `submission`, supply the exact original observed-stop `recover`
request as `recovery_request`, and add a unique `request_id`. Keep the qualified
node, `draft` Ref and `subject` digest exact. `retire_stale_draft` recomputes the
current policy, allocation, approvals, task contract, declared inputs,
resolutions, Git head, raw workspace and checkout overrides before writing.
Dirty files, altered stop evidence, stale requests, unknown or unrecovered
owners, and disconnected draft ancestry reject without retiring anything.

This operation appends an immutable retirement receipt. It preserves the
original draft, its authenticated same-task baseline chain, all Results and
approvals; it adopts no draft bytes and creates no semantic Result. Reinvoke
execute and acquire the current task normally from the clean checkout. Fresh
verification and independent review remain required. Exact retries replay the
original receipt without another write. An unchanged draft still requires its
exact stopped snapshot and ordinary recovery; it is not offered retirement.

### Fixed policy workflow and phase findings

Every open product goal evaluates the same versioned DAG derived from reviewed
project policy. The payload's original graph remains immutable audit history.
Current compatible Results are reused; missing or incompatible phase contracts,
inputs, schemas and reviews become pending through ordinary evaluation. No
per-goal graph preparation, review, adoption or normalization is required or
accepted. A policy change uses policy review. An unmapped historical custom
contract produces a specific mapping blocker rather than silently dropping an
obligation. Existing reviewed schema-conversion entry protocols retain their
contracts until conversion completes.

Pre-upgrade evidence can be reused when its recorded policy, task contract,
inputs and live workspace proof establish exact compatibility. Missing historical
authority or substantive drift requires fresh evidence; history is never rewritten.
A disconnected completed proof permits fresh acquisition only from an entirely
clean committed checkout; corrupt-proof errors retain priority.

Late findings enter as phase data after all owners have been resolved. Submit
`phase_finding` with a unique `request_id`, the actual root `actor`, a stable
finding `id`, `rationale`, the exact current output `subject` Ref, and an immutable
same-goal diagnostic `source` Ref. `target` is `{node, output}` for a singleton,
or `{node, output, expansion, item, generation}` for a task-set member. Reusing
an ID appends a new immutable revision for that exact target; it cannot retarget
an existing finding. Retry uncertain writes with the identical request bytes.

The authenticated event supplies context, never authority. Follow the returned
independent review, root interpretation/admission, correction and fresh-review
tasks. Only an admitted correction invalidates its exact target and dependent
evidence; unrelated work remains current. Every finding revision remains in
history, and unresolved findings withhold dependent work and completion. Do not
rewrite the managed body, invent a passing Result, or create a goal merely to
change another goal's workflow.

Historical reads remain available. Execution reconciles the selected goal
lazily; broad discovery never sweeps or hydrates closed goals. Unsupported
versions and ambiguous mappings produce specific diagnostics. Preserve original
transactions and resolve an uncertain write before attempting a replacement.

### Migrated blocker resolution recovery

`resolve_goal_blocker` identifies an obligation by the returned original
goal-context hash and exact blocker-content hash. Legacy blockers need no added
ID; identical duplicate blocker content remains ambiguous and cannot be
resolved. Stop or recover every active owner first. Cite immutable current
same-goal Result/output Refs and explain why they satisfy this exact obligation.
For a human-action blocker, obtain explicit approval in the conversation and
record both `approved_by` and `attribution`; do not infer approval from an old
phase, matching words or unrelated evidence.

The operation appends a versioned resolution event and ordinary committed
request receipt. It never edits the authenticated original context or prior
comments. Retry an uncertain publication with the identical request ID and
payload. Exact replay returns the original response; changed bytes under the
same ID are rejected. A later root may consume an authenticated historical
resolution, while current task, workspace and publication authority must still
be established independently. Missing or changed event content, provenance,
evidence or receipt fails authentication; restore the exact immutable record
rather than creating a replacement resolution.

### Stale workspace authorization

Workspace-authorization producer Results include a host-authenticated
`__policy` input. Legacy Results without that input, and Results bound to a
different policy, become stale through ordinary input identity. Execute then
returns the independent authorization producer followed by its root approval as
normal `execute` tasks. Acquire and submit them normally with the unchanged
manifest and task identities and the exact current policy digest. Old Results
remain immutable; downstream inputs become stale when the new authorization
outputs are published. No special rewrite or authorization bypass exists.
### Infrastructure prerequisites

Record missing infrastructure as phase data and use the ordinary planning,
independent review and approval tasks. Keep final verification and acceptance
requirements pending until actual infrastructure evidence exists. A genuinely
separate product prerequisite can have its own dependency goal; changing the
workflow of an existing goal is administration, not a new product goal. Never
fabricate deployed-state evidence or revive an old lease.

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

## Refresh an obsolete checkpoint retirement

If a retained retirement no longer authenticates the current provider history,
run `checkpoint_reconcile_prepare` again for the same exact transaction. Give
the returned proposal to an independent reviewer, submit the returned
`checkpoint_reconcile_review` contract, then adopt its exact proposal/review
Refs with explicit approval. Preparation and adoption require stopped ownership.
A refresh appends evidence; it never removes the original retirement, approvals,
comments or artifacts. Only a uniquely latest valid retirement on authenticated
receipt ancestry can permit the affected transaction to continue.

Use the request IDs returned by each fresh contract. They bind the complete
proposal or proposal/review pair, so the same checkpoint can receive a
fresh review without colliding with its earlier receipt. After a failed provider
confirmation, retry the frozen exact request, including its original ID and
bytes. Changed bytes under that ID remain a conflict. A retirement creates no
semantic Result, worker lease, workspace approval or CI/integration authority.
