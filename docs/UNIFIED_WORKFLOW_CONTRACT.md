# Unified workflow contract

The public `workflow` entrypoint implements the generic evidence DAG approved in
[#498](https://github.com/david-rzepa/zzzops/issues/498). Repository policy remains
reviewed authority. A goal, task name, parent relationship, artifact type, or
caller-provided approval boolean grants no authority by itself.

## Public surface

Invoke package-local `zzzops.py --repo REPOSITORY workflow --intent INTENT` through
the installed skill. Follow the returned `next_steps`, exact goal, runtime and
input arguments. Context, installation, policy and actual capability gates apply
before execution. Preview accepts no mutations. Only the coordinator writes
canonical state or integrates work; a delegated worker follows its acquired
contract and finite workspace allocation.

Normal goal execution uses one schema-2 engine. `start`, `bind`, `renew`, `block`,
`recover` and `submit` operate on qualified generic tasks. Evidence inspection is
`read`. Operational `integrate`, `reconcile` and `complete` consume authenticated
current graph evidence. They do not manufacture semantic Results. Capture,
policy approval, installation validation and other administrative intents retain
their own public contracts. Retired phase `assess`, `verify`, `record_result`,
`record_review`, `approve`, `withdraw` and automatic bulk adoption are not a second
normal execution grammar.

## Canonical data and identity

A schema-2 GoalEnvelope contains exactly `schema_version`, `repository`, `issue`,
`revision`, `state`, `parent` and `payload`. State is `open` or `archived`; parent
is a positive same-repository issue number or explicit null. Provider issue
closure is separate from envelope state. Payload is an immutable Ref resolving
to `{spec, graph, evidence, operational}`. Operational data contains `leases` and
`receipts`; accepted evidence is an ordered array of immutable Result Refs.

A Ref is `{hash, uri}`. The SHA-256 hash authenticates content; the URI locates it.
Local `urn:sha256:...` reads retain their behavior. A same-repository qualified
locator is `zzzops:OWNER/REPOSITORY:goal:NUMBER:sha256:HASH`. Its repository, positive
goal and embedded hash must agree exactly before a targeted provider read.
Published Git references pin an exact commit, repository-relative path and raw
bytes hash. Location never supplies execution authority.

An Artifact contains `{type, content, producer, provenance}`. A host-issued
Result binds its qualified node, attempt, contract hash, exact input bindings,
actual executor, output Refs and selector resolutions. Qualified task identity
contains goal, node, item and generation. Null item denotes a static node.
Receipts contain exactly `{request, payload, result}`: the stable request ID,
request hash and immutable response Ref. Exact retries return the same response;
reuse of an ID for different bytes is rejected.

## One graph and one evaluator

Graph contains exactly `nodes`, `task_sets` and `terminals`. A task declares its
prompt, typed inputs and outputs, prerequisites, executor capability/resources
and authority selector, independence, finding gates, resolutions and permits.
There is no phase-to-runtime dispatch table. The shipped graph expresses design,
decomposition, test design, implementation and publication with ordinary tasks
and explicit reviews/authorizations. Extra risk-review topology is outside this
foundation.

Inputs select a declared external slot or a node output, a path, identity/content
mode and a closed TypeContract. Static, member and join selectors use an explicit
goal number or `#this`, `#parent`, `#children`. Member identity includes generation;
join and plural-child inputs produce canonical keyed maps, including nested maps
when both dimensions apply. Types must describe the resulting aggregate, not
just each leaf. Every required immediate child participates, including archived
children. Known empty, unknown, null and missing are distinct observations.

The pure evaluator derives current Results, readiness, findings and terminals
from Graph, Payload and resolved evidence. It performs no provider or process
I/O. Host adapters supply authenticated observations; they cannot insert tasks or
skip declared prerequisites. Projected cross-goal cycles are rejected. Relevant
subject, membership, contract or evidence drift makes affected consumers stale;
unrelated goals and lease/receipt bookkeeping do not invalidate reusable work.

## Relationship and historical reads

Canonical GoalEnvelope.parent is relationship truth. The host enumerates scoped
provider metadata with complete pagination, then reads candidate envelopes to
establish canonical membership. A native sub-issue index can corroborate or
locate candidates; an empty native index alone does not prove empty canonical
membership. Partial, mismatched or unknown facts block affected consumers.

The host relationship context retains exact envelope Refs as provenance while
semantic selector fingerprints exclude irrelevant bookkeeping. Targeted reads
may retrieve closed/archived goal bodies and exact immutable history. They do not
reopen, migrate, compact or authorize execution. Broad portfolio discovery does
not automatically hydrate closed bodies. A parent change is root-controlled,
requires the exact current predecessor and preserves self/cross-repository/cycle
guards. Its own acquisition bookkeeping does not simulate external drift.

## Ownership and atomic submission

Acquisition pins current contract, input fingerprint, actual routing choice and
host observations. The worker reads the exact policy file and supplies its
receipt at start/bind; the bound actual model/effort and actor must match. An
independent reviewer cannot be the actual subject executor. Reviewed capacity
and declared resources include unresolved owners, even when expired or stale.

Staleness or expiry never proves a worker stopped. Recovery requires root's exact
owner/token and observed terminal evidence. Heartbeat returns a same-node,
same-token public renewal contract; callers observe real worker liveness and
renew that ownership rather than dispatching another worker. Infrastructure
blockers remain operational facts, not invented semantic Results.

Submit accepts exactly the declared output bundle. The host validates types,
current authority, ownership, input identity and proofs before publishing typed
Artifacts and one Result. The operational lease removal and request receipt share
the checkpoint. Partial provider writes require exact readback/retry; no silent
rollback, dropped history or completed-owner resurrection is permitted.

## Workspace evidence

Repository editing requires the explicit `repository_workspace` resource and a
declared allocation input. An authenticated root allocation names exact qualified
tasks and finite owned/consumed paths. Current independent authorization and
root approval bind the exact manifest, task identities and policy. A child also
needs matching immediate-parent grant and authorization inputs; ancestry alone
cannot expand its scope.

Owned paths are disjoint from another task's write authority. Traversal, absolute
paths, symbolic links, directories, wildcards and administrative authority files
cannot be converted into permission by a manifest. The bounded migration
preparation file may be an explicit consumed input, never an owned path.

Acquisition pins raw checkout files, actual commit, consumed/owned boundaries,
input hash and host-verified checkout overrides. Changed owned files require
observed `workspace_checks` command results before candidate publication.
A failing test result may be recorded factually for independent review; it does
not authorize completion. Output, proof, acquisition, actual actor/token and
Result identities remain connected across commits and retries.

Reuse follows exact accepted whole before/after snapshots. Individually valid
historical bytes cannot be combined into an unobserved workspace. Host-issued
predecessor evidence binds qualified node, allocation, authorization, prior
Result/proof/review and predecessor Ref. Correction count does not limit later
attempts. Each acquisition requires current allocation, independent authorization,
root approval, ownership and input checks. Reuse also requires the exact accepted
prior candidate and verified workspace connectivity. Older predecessor links retain provenance;
their historical grants cannot authorize new work. Link identity, checksum and
cycle checks remain, as do required historical whole-workspace proof edges.

All transactions and exact historical Refs remain retained. Canonical payload and
receipt membership use the existing trusted canonical-state boundary; content
hashes establish byte identity, not cryptographic author authenticity. Eager
history hydration and evidence scans still grow with retained history. This
contract does not promise bounded total acquisition work or unlimited storage;
codec depth, decoded-size and reconstruction-work limits remain separate resource
constraints, never a semantic correction-count policy.

Git-clean CRLF normalization is only a host-verified read observation. Raw
acquisition and consumed pins remain exact. A later Git configuration change
cannot bless different raw bytes; exact durable acquisition evidence can retain
a previously verified override. Unrelated clean committed paths do not invalidate
a task whose authenticated finite scope does not consume them.

## Findings and correction

Findings have stable identity/revision, exact subject Refs, target scope and
provenance. Root admission determines applicability under declared permits.
Accepted obligations persist when the admitting Result later becomes stale;
that persistence does not make the Result current or bypass an ordinary requires
edge. Distinct unresolved findings remain distinct obligations.

Resolution needs the current finding revision, current exact subject and a
current independent review that consumed that subject. Supersession transfers
coverage explicitly; withdrawal and retirement require declared root authority.
Literal findings do not silently become plural, even when a selector currently
has one member. Correction cannot erase prior evidence or release an owner.

## Publication and completion

The explicit `repository_publication` adapter consumes a declared root-issued
`repository_context` `{branch, base, target, pr}` and current independently reviewed
root authorization. Context is issued when the actual PR exists. Node IDs and
output type names do not select authority implicitly.

Provider observations bind exact repository, PR, head, base and CI. CI is the
closed enum `verified|unverified|absent|unknown`; absent requires complete known
provider evidence. Failed/unknown observations remain recordable factual evidence.
Configured strict, inspect-when-present or disabled CI policy controls approval,
effects and completion rather than suppressing facts.

`publication_authorization` binds exact current subject, independent review and
policy. Integration checks current provider head/base, topology, ownership and
CI, and uses exact-head protection plus readback. It may occur before a declared
post-effect node, avoiding a cycle between integration and merge observation.
`merge_observation` binds that authorization and actual provider merge identity.
Reconciliation cannot mint missing Results; semantic completion still requires
all declared terminals and retained obligations. Provider closure/archival alone
is not evidence that required children or publication work completed.

## Trusted predecessor conversion

Version 1 remains a supported historical source, not an active execution engine.
Authorized execution automatically performs deterministic lossless conversion of
supported open v1 goals before dispatching normal v2 work. The same converter is
available through `migration_batch` with `discover`, `migrate`, and `status`.
Running migration requires no per-conversion reviewer or human approval; review
and approval apply to developing and integrating the converter itself.

Discovery uses the minimal open index and bounded canonical body reads. Labels
are hints: canonical v2 records with stale v1 labels are already current. Preview,
status, discovery and historical reads do not mutate goals. Closed members are
never reopened, and broad selection never hydrates closed goals. Each selected
member has its own transaction; partial failure preserves unrelated successes.
A stale task request that encounters v1 receives the migrated normal checkpoint
without being executed against the new graph.

The source issue, complete human prefix/suffix, all historical comments and
transactions, priority, parent and immutable Refs are preserved. Dependency
review/merge ordering and unresolved blockers become explicit current graph
gates where the converter has a supported mapping. Unsupported semantics block
the affected member. Old approvals and Results remain historical data; migration
creates no current product evidence, workspace grant or publication authority.
Existing ownership, whether live or expired, requires observed-stopped recovery.

Before replacing the managed block, the existing immutable transaction writer
stores checksummed source, target intent, current policy and conversion receipt.
The receipt's `target_intent` has empty operational receipts; the transaction
context's `target_envelope` binds the exact published envelope after adding the
operational receipt. Successful responses expose that envelope as
`published_target`. This avoids a circular receipt/target hash. It
checks concurrent source changes, closure and current policy, and reconciles
uncertain append/body responses through exact readback. Retry can resume from
another process using remote state. A pending transaction with changed policy or
missing artifacts cannot publish its stale target. Concurrent labels/state are
not resent by a managed-body write. No cross-version global revision numbering
is implied; ambiguous historical revision reads diagnose rather than guess.

Existing reviewed custom migration entries, including in-progress conversions,
remain under their declared generic analysis/review/root-activation contracts.
The automatic converter never issues those Results or replaces their semantics.
Only their reviewed compatible mappings may become current generic evidence.

Migration preparation consumes its exact declared path and schema-2 spec Ref
hash with live provider/release assessment. Unknown stays unknown. An ordinary
root factual report can preserve a blocker reason and preparation observations;
it grants no eligibility and is not a forged host attestation.

## Bounded immutable storage

The adapter catalogs retained comment locations and resolves only the selected
artifact representations and delta bases under the shared codec limits. Total
unrelated history does not consume an active read's working-set budget. Every
selected representation/base is validated; conflicting appended representations
invalidate affected closures before publication. Changed old comment bytes cannot
reuse cached validation. Cached values are bounded observations, not authority.

The existing artifact size, delta depth, reconstruction work, record count and
provider comment limits remain unchanged. Payload deltas choose addressed bases
within those bounds while preserving all receipts and evidence. Public reads
return detached values. Internal borrowed snapshots are read-only and reused only
with exact provider-body/base signatures and unchanged validation limits.
